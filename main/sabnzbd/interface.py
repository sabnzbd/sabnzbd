#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
sabnzbd.interface - webinterface
"""

__NAME__ = "interface"

import os
import datetime
import time
import cherrypy
import logging
import sabnzbd

from cherrypy.filters.gzipfilter import GzipFilter

from sabnzbd.utils.multiauth.filter import MultiAuthFilter
from sabnzbd.utils.multiauth.auth import ProtectedClass, SecureResource
from sabnzbd.utils.multiauth.providers import DictAuthProvider

from sabnzbd.utils import listquote
from sabnzbd.utils.configobj import ConfigObj
from Cheetah.Template import Template
from sabnzbd.email import email_send
from sabnzbd.misc import real_path, create_real_path

from sabnzbd.constants import *

#------------------------------------------------------------------------------

PROVIDER = DictAuthProvider({})

USERNAME = None
PASSWORD = None

#------------------------------------------------------------------------------
try:
    os.statvfs
    import statvfs
    # posix diskfree
    def diskfree(_dir):
        try:
            s = os.statvfs(_dir)
            return (s[statvfs.F_BFREE] * s[statvfs.F_FRSIZE]) / GIGI
        except OSError:
            return 0.0
except AttributeError:
    try:
        import win32api
    except ImportError:
        pass
    # windows diskfree
    def diskfree(_dir):
        try:
            secp, byteper, freecl, noclu = win32api.GetDiskFreeSpace(_dir)
            return (secp * byteper * freecl) / GIGI
        except:
            return 0.0
            
def CheckFreeSpace():
    if sabnzbd.DOWNLOAD_FREE > 0 and not sabnzbd.paused():
        if diskfree(sabnzbd.DOWNLOAD_DIR) < float(sabnzbd.DOWNLOAD_FREE) / 1024.0:
            logging.info('Too little diskspace forcing PAUSE')
            sabnzbd.pause_downloader()
            if sabnzbd.EMAIL_FULL:
                email_send("SABnzbd has halted", "SABnzbd has halted because diskspace is below the minimum.\n\nSABnzbd")

            
#------------------------------------------------------------------------------
class DummyFilter(MultiAuthFilter):
    def beforeMain(self):
        pass
            
    def beforeFinalize(self):
        if isinstance(cherrypy.response.body, SecureResource):
            rsrc = cherrypy.response.body
            cherrypy.response.body = rsrc.callable(rsrc.instance,
                                                   *rsrc.callable_args,
                                                   **rsrc.callable_kwargs)
                                                   
#------------------------------------------------------------------------------
class BlahPage:
    def __init__(self):
        self._cpFilterList = [GzipFilter()]
        
        if USERNAME and PASSWORD:
            PROVIDER.add(USERNAME, PASSWORD, ['admins'])
            
            self._cpFilterList.append(MultiAuthFilter('/unauthorized', PROVIDER))
        else:
            self._cpFilterList.append(DummyFilter('', PROVIDER))
            
    @cherrypy.expose
    def index(self):
        return ""
        
    @cherrypy.expose
    def unauthorized(self):
        return "<h1>You are not authorized to view this resource</h1>"
        
#------------------------------------------------------------------------------
class MainPage(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        info, pnfo_list, bytespersec = build_header()
        
        if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
            info['newzbinDetails'] = True
            
        template = Template(file=os.path.join(self.__web_dir, 'main.tmpl'),
                            searchList=[info],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def addID(self, id = None, pp = 0, redirect = None):
        if id:
            id = id.strip()
            
        if id and id.isdigit() and pp.isdigit():
            sabnzbd.add_msgid(int(id), int(pp))
            
        if not redirect:
            redirect = self.__root
            
        raise cherrypy.HTTPRedirect(redirect)
        
    @cherrypy.expose
    def addURL(self, url = None, pp = 0, redirect = None):
        if url and pp.isdigit():
            sabnzbd.add_url(url, int(pp))
            
        if not redirect:
            redirect = self.__root
            
        raise cherrypy.HTTPRedirect(redirect)
        
    @cherrypy.expose
    def addFile(self, nzbfile, pp = 0):
        if pp.isdigit() and nzbfile.filename and nzbfile.value:
            sabnzbd.add_nzbfile(nzbfile, int(pp))
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def shutdown(self):
        yield "Initiating shutdown..."
        sabnzbd.halt()
        cherrypy.server.stop()
        yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
        raise KeyboardInterrupt()
        
    @cherrypy.expose
    def pause(self):
        sabnzbd.pause_downloader()
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def resume(self):
        sabnzbd.resume_downloader()
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def debug(self):
        return '''cache_limit: %s<br>
                  cache_size: %s<br>
                  downloaded_items: %s<br>
                  nzo_list: %s<br>
                  article_list: %s<br>
                  nzo_table: %s<br>
                  nzf_table: %s<br>
                  article_table: %s<br>
                  try_list: %s''' % sabnzbd.debug()
                  
#------------------------------------------------------------------------------
class NzoPage(ProtectedClass):
    def __init__(self, web_dir, nzo_id):
        self.roles = ['admins']
        
        self.__nzo_id = nzo_id
        self.__root = '/sabnzbd/queue/%s/' % nzo_id
        self.__web_dir = web_dir
        self.__verbose = False
        self.__cached_selection = {} #None
        
    @cherrypy.expose
    def index(self):
        info, pnfo_list, bytespersec = build_header()
        
        this_pnfo = None
        for pnfo in pnfo_list:
            if pnfo[PNFO_NZO_ID_FIELD] == self.__nzo_id:
                this_pnfo = pnfo
                break
                
        if this_pnfo:
            info['nzo_id'] = self.__nzo_id
            info['filename'] = pnfo[PNFO_FILENAME_FIELD]
            
            active = []
            for tup in pnfo[PNFO_ACTIVE_FILES_FIELD]:
                bytes_left, bytes, fn, date, nzf_id = tup
                checked = False
                if nzf_id in self.__cached_selection and \
                self.__cached_selection[nzf_id] == 'on':
                    checked = True
                    
                line = {'filename':str(fn),
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'nzf_id':nzf_id,
                        'age':calc_age(date),
                        'checked':checked}
                active.append(line)
                
            info['active_files'] = active
                
            template = Template(file=os.path.join(self.__web_dir, 'nzo.tmpl'),
                                searchList=[info],
                                compilerSettings={'directiveStartToken': '<!--#', 
                                                  'directiveEndToken': '#-->'})
            return template.respond()
        else:
            return "ERROR: %s deleted" % self.__nzo_id
            
    @cherrypy.expose
    def bulk_operation(self, *args, **kwargs):
        self.__cached_selection = kwargs
        if kwargs['action_key'] == 'Delete':
            for key in kwargs:
                if kwargs[key] == 'on':
                    sabnzbd.remove_nzf(self.__nzo_id, key)
                    
        elif kwargs['action_key'] == 'Top' or kwargs['action_key'] == 'Up' or \
             kwargs['action_key'] == 'Down' or kwargs['action_key'] == 'Bottom':
            nzf_ids = []
            for key in kwargs:
                if kwargs[key] == 'on':
                    nzf_ids.append(key)
            if kwargs['action_key'] == 'Top':
                sabnzbd.move_top_bulk(self.__nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Up':
                sabnzbd.move_up_bulk(self.__nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Down':
                sabnzbd.move_down_bulk(self.__nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Bottom':
                sabnzbd.move_bottom_bulk(self.__nzo_id, nzf_ids)
                
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def tog_verbose(self):
        self.__verbose = not self.__verbose
        
        raise cherrypy.HTTPRedirect(self.__root)
#------------------------------------------------------------------------------
class QueuePage(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/queue/'
        
        self.__web_dir = web_dir
        
        self.__verbose = False
        
        self.__nzo_pages = []
    
    @cherrypy.expose
    def index(self):
        info, pnfo_list, bytespersec = build_header()
        
        if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
            info['newzbinDetails'] = True

        if int(sabnzbd.CFG['misc']['refresh_rate']) > 0:
            info['refresh_rate'] = sabnzbd.CFG['misc']['refresh_rate']
        else:
            info['refresh_rate'] = ''
            
        info['noofslots'] = len(pnfo_list)
        datestart = datetime.datetime.now()
        
        n = 0
        slotinfo = []
        
        nzo_ids = []
        
        for pnfo in pnfo_list:
            repair = pnfo[PNFO_REPAIR_FIELD]
            unpack = pnfo[PNFO_UNPACK_FIELD]
            delete = pnfo[PNFO_DELETE_FIELD]
            script = pnfo[PNFO_SCRIPT_FIELD]
            nzo_id = pnfo[PNFO_NZO_ID_FIELD]
            filename = pnfo[PNFO_FILENAME_FIELD]
            bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD]
            bytes = pnfo[PNFO_BYTES_FIELD]
            average_date = pnfo[PNFO_AVG_DATE_FIELD]
            finished_files = pnfo[PNFO_FINISHED_FILES_FIELD]
            active_files = pnfo[PNFO_ACTIVE_FILES_FIELD]
            queued_files = pnfo[PNFO_QUEUED_FILES_FIELD]
            
            nzo_ids.append(nzo_id)
            
            if nzo_id not in self.__dict__:
                self.__dict__[nzo_id] = NzoPage(self.__web_dir, nzo_id)
                self.__nzo_pages.append(nzo_id)
            
            slot = {'index':n, 'nzo_id':str(nzo_id)}
            n += 1
            unpackopts = 0
            if repair:
                unpackopts += 1
                if unpack:
                    unpackopts += 1
                    if delete:
                        unpackopts += 1
            if (unpackopts > 0) & script:
            	  unpackopts= unpackopts + 3
            	                          
            slot['unpackopts'] = str(unpackopts)
            slot['filename'] = filename
            slot['mbleft'] = "%.2f" % (bytesleft / MEBI)
            slot['mb'] = "%.2f" % (bytes / MEBI)
            
            try:
                datestart = datestart + datetime.timedelta(seconds=bytesleft / bytespersec)
                slot['eta'] = '%s' % datestart.isoformat(' ').split('.')[0]
            except:
                datestart = datetime.datetime.now()
                slot['eta'] = 'unknown'
                
            slot['avg_age'] = calc_age(average_date)
                
            finished = []
            active = []
            queued = []
            if self.__verbose:
                
                date_combined = 0
                num_dates = 0
                
                for tup in finished_files:
                    bytes_left, bytes, fn, date = tup
                    if isinstance(fn, unicode): 
                        fn = fn.encode('utf-8')
                        
                    age = calc_age(date)
                    
                    line = {'filename':str(fn), 
                            'mbleft':"%.2f" % (bytes_left / MEBI), 
                            'mb':"%.2f" % (bytes / MEBI),
                            'age':age}
                    finished.append(line)
                    
                for tup in active_files:
                    bytes_left, bytes, fn, date, nzf_id = tup
                    if isinstance(fn, unicode): 
                        fn = fn.encode('utf-8')
                        
                    age = calc_age(date)
                    
                    line = {'filename':str(fn), 
                            'mbleft':"%.2f" % (bytes_left / MEBI), 
                            'mb':"%.2f" % (bytes / MEBI), 
                            'nzf_id':nzf_id,
                            'age':age}
                    active.append(line)
                    
                for tup in queued_files:
                    _set, bytes_left, bytes, fn, date = tup
                    if isinstance(fn, unicode): 
                        fn = fn.encode('utf-8')
                    
                    age = calc_age(date)
                    
                    line = {'filename':str(fn), 'set':_set, 
                            'mbleft':"%.2f" % (bytes_left / MEBI), 
                            'mb':"%.2f" % (bytes / MEBI),
                            'age':age}
                    queued.append(line)
                    
            slot['finished'] = finished
            slot['active'] = active
            slot['queued'] = queued
            
            slotinfo.append(slot)
            
        if slotinfo:
            info['slotinfo'] = slotinfo
        
        for nzo_id in self.__nzo_pages[:]:
            if nzo_id not in nzo_ids:
                self.__nzo_pages.remove(nzo_id)
                self.__dict__.pop(nzo_id)
            
        template = Template(file=os.path.join(self.__web_dir, 'queue.tmpl'),
                            searchList=[info],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def delete(self, uid = None):
        if uid:
            sabnzbd.remove_nzo(uid, False)
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def removeNzf(self, nzo_id = None, nzf_id = None):
        if nzo_id and nzf_id:
            sabnzbd.remove_nzf(nzo_id, nzf_id)
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def tog_verbose(self):
        self.__verbose = not self.__verbose
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def tog_shutdown(self):
        if os.name == 'nt':
            sabnzbd.AUTOSHUTDOWN = not sabnzbd.AUTOSHUTDOWN
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def switch(self, uid1 = None, uid2 = None):
        if uid1 and uid2:
            sabnzbd.switch(uid1, uid2)
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def change_opts(self, nzo_id = None, pp = None):
        if nzo_id and pp and pp.isdigit():
            sabnzbd.change_opts(nzo_id, int(pp))
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def shutdown(self):
        yield "Initiating shutdown..."
        sabnzbd.halt()
        cherrypy.server.stop()
        yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
        raise KeyboardInterrupt()
        
    @cherrypy.expose
    def pause(self):
        sabnzbd.pause_downloader()
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def resume(self):
        sabnzbd.resume_downloader()
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def sort_by_avg_age(self):
        sabnzbd.sort_by_avg_age()
        raise cherrypy.HTTPRedirect(self.__root)
        
class HistoryPage(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/history/'
        
        self.__web_dir = web_dir
        
        self.__verbose = True
        
    @cherrypy.expose
    def index(self):
        history, pnfo_list, bytespersec = build_header()
            
        if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
            history['newzbinDetails'] = True

        history_items, total_bytes, bytes_beginning = sabnzbd.history_info()
        
        history['total_bytes'] = "%.2f" % (total_bytes / GIGI)
        
        history['bytes_beginning'] = "%.2f" % (bytes_beginning / GIGI)
        
        stagenames = {1:"Par2", 2:"Unrar", 3:"Unzip", 4:"Filejoin"}
        
        items = []
        while history_items:
            added = max(history_items.keys())
            
            history_item_list = history_items.pop(added)
            
            for history_item in history_item_list:
                filename, unpackstrht, loaded = history_item
                stages = []
                item = {'added':time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(added)),
                        'filename':filename, 'loaded':loaded, 'stages':stages}
                if self.__verbose:
                    stage_keys = unpackstrht.keys()
                    stage_keys.sort()
                    for stage in stage_keys:
                        stageLine = {'name':stagenames[stage]}
                        actions = []
                        for action in unpackstrht[stage]:
                            actionLine = {'name':action, 'value':unpackstrht[stage][action]}
                            actions.append(actionLine)
                        actions.sort()
                        actions.reverse()
                        stageLine['actions'] = actions
                        stages.append(stageLine)
                item['stages'] = stages
                items.append(item)
        history['lines'] = items
        
        
        template = Template(file=os.path.join(self.__web_dir, 'history.tmpl'),
                            searchList=[history],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def purge(self):
        sabnzbd.purge_history()
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def reset(self):
        sabnzbd.reset_byte_counter()
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def tog_verbose(self):
        self.__verbose = not self.__verbose
        raise cherrypy.HTTPRedirect(self.__root)
        
#------------------------------------------------------------------------------
class ConfigPage(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose    
    def index(self):
        config, pnfo_list, bytespersec = build_header()

        config['configfn'] = sabnzbd.CFG.filename
            
        template = Template(file=os.path.join(self.__web_dir, 'config.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def restart(self):
        sabnzbd.halt()
        init_ok = sabnzbd.initialize()
        if init_ok:
            sabnzbd.start()
            raise cherrypy.HTTPRedirect(self.__root)
        else:
            return "SABnzbd restart failed! See logfile(s)."
            
#------------------------------------------------------------------------------
class ConfigDirectories(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/directories/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        config, pnfo_list, bytespersec = build_header()
        
        config['download_dir'] = sabnzbd.CFG['misc']['download_dir']
        config['download_free'] = sabnzbd.CFG['misc']['download_free']
        config['complete_dir'] = sabnzbd.CFG['misc']['complete_dir']
        config['cache_dir'] = sabnzbd.CFG['misc']['cache_dir']
        config['log_dir'] = sabnzbd.CFG['misc']['log_dir']
        config['nzb_backup_dir'] = sabnzbd.CFG['misc']['nzb_backup_dir']
        config['dirscan_dir'] = sabnzbd.CFG['misc']['dirscan_dir']
        config['dirscan_speed'] = sabnzbd.CFG['misc']['dirscan_speed']
        config['extern_proc'] = sabnzbd.CFG['misc']['extern_proc']
        config['my_home'] = sabnzbd.DIR_HOME
        config['my_lcldata'] = sabnzbd.DIR_LCLDATA
            
        template = Template(file=os.path.join(self.__web_dir, 'config_directories.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def saveDirectories(self, download_dir = None, download_free = None, complete_dir = None, log_dir = None,
                        cache_dir = None, nzb_backup_dir = None,
                        dirscan_dir = None, dirscan_speed = None, extern_proc = None):
                        
        dd = create_real_path('download_dir', sabnzbd.DIR_LCLDATA, download_dir)
        if not dd:
            return "Error: cannot create download directory %s." % dd
            
        dd = create_real_path('cache_dir', sabnzbd.DIR_LCLDATA, cache_dir)
        if not dd:
            return "Error: cannot create cache directory %s." % dd
            
        dd = create_real_path('log_dir', sabnzbd.DIR_LCLDATA, log_dir)
        if not dd:
            return "Error: cannot create log directory %s." % dd

        dd = create_real_path('dirscan_dir', sabnzbd.DIR_HOME, dirscan_dir)
        if not dd:
            return "Error: cannot create dirscan_dir directory %s." % dd
            
        dd = create_real_path('complete_dir', sabnzbd.DIR_HOME, complete_dir)
        if not dd:
            return "Error: cannot create complete_dir directory %s." % dd
            
        dd = create_real_path('nzb_backup_dir', sabnzbd.DIR_LCLDATA, nzb_backup_dir)
        if not dd:
            return "Error: cannot create nzb_backup_dir directory %s." % dd

        if extern_proc and not os.access(real_path(sabnzbd.DIR_HOME, extern_proc), os.R_OK):
            return "Error: cannot find extern_proc %s." % real_path(sabnzbd.DIR_HOME, extern_proc)

            
        sabnzbd.CFG['misc']['download_dir'] = download_dir
        sabnzbd.CFG['misc']['download_free'] = download_free
        sabnzbd.CFG['misc']['cache_dir'] = cache_dir
        sabnzbd.CFG['misc']['log_dir'] = log_dir
        sabnzbd.CFG['misc']['dirscan_dir'] = dirscan_dir
        sabnzbd.CFG['misc']['dirscan_speed'] = dirscan_speed
        sabnzbd.CFG['misc']['extern_proc'] = extern_proc
        sabnzbd.CFG['misc']['complete_dir'] = complete_dir
        sabnzbd.CFG['misc']['nzb_backup_dir'] = nzb_backup_dir
        
        return saveAndRestart(self.__root)
        
#------------------------------------------------------------------------------
class ConfigSwitches(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/switches/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        config, pnfo_list, bytespersec = build_header()
        
        config['enable_unrar'] = int(sabnzbd.CFG['misc']['enable_unrar'])
        config['enable_unzip'] = int(sabnzbd.CFG['misc']['enable_unzip'])
        config['enable_filejoin'] = int(sabnzbd.CFG['misc']['enable_filejoin'])
        config['enable_save'] = int(sabnzbd.CFG['misc']['enable_save'])
        config['enable_par_cleanup'] = int(sabnzbd.CFG['misc']['enable_par_cleanup'])
        config['send_group'] = int(sabnzbd.CFG['misc']['send_group'])
        config['fail_on_crc'] = int(sabnzbd.CFG['misc']['fail_on_crc'])
        config['create_group_folders'] = int(sabnzbd.CFG['misc']['create_group_folders'])
        config['dirscan_opts'] = int(sabnzbd.CFG['misc']['dirscan_opts'])
        config['top_only'] = int(sabnzbd.CFG['misc']['top_only'])
        config['auto_sort'] = int(sabnzbd.CFG['misc']['auto_sort'])
        config['create_category_folders'] = int(sabnzbd.CFG['newzbin']['create_category_folders'])
        
        template = Template(file=os.path.join(self.__web_dir, 'config_switches.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def saveSwitches(self, enable_unrar = None, enable_unzip = None,
                     enable_filejoin = None, enable_save = None,
                     send_group = None, fail_on_crc = None, top_only = None,
                     create_group_folders = None, dirscan_opts = None,
                     enable_par_cleanup = None, auto_sort = None,
                     create_category_folders = None):
                     
        sabnzbd.CFG['misc']['enable_unrar'] = int(enable_unrar)
        sabnzbd.CFG['misc']['enable_unzip'] = int(enable_unzip)
        sabnzbd.CFG['misc']['enable_filejoin'] = int(enable_filejoin)
        sabnzbd.CFG['misc']['enable_save'] = int(enable_save)
        sabnzbd.CFG['misc']['send_group'] = int(send_group)
        sabnzbd.CFG['misc']['fail_on_crc'] = int(fail_on_crc)
        sabnzbd.CFG['misc']['create_group_folders'] = int(create_group_folders)
        sabnzbd.CFG['misc']['dirscan_opts'] = int(dirscan_opts)
        sabnzbd.CFG['misc']['enable_par_cleanup'] = int(enable_par_cleanup)
        sabnzbd.CFG['misc']['top_only'] = int(top_only)
        sabnzbd.CFG['misc']['auto_sort'] = int(auto_sort)
        sabnzbd.CFG['newzbin']['create_category_folders'] = int(create_category_folders)
        
        return saveAndRestart(self.__root)
        
#------------------------------------------------------------------------------

class ConfigGeneral(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/general/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        config, pnfo_list, bytespersec = build_header()
        
        config['host'] = sabnzbd.CFG['misc']['host']
        config['port'] = sabnzbd.CFG['misc']['port']
        config['username'] = sabnzbd.CFG['misc']['username']
        config['password'] = sabnzbd.CFG['misc']['password']
        config['web_dir'] = sabnzbd.CFG['misc']['web_dir']
        config['bandwith_limit'] = sabnzbd.CFG['misc']['bandwith_limit']
        config['refresh_rate'] = sabnzbd.CFG['misc']['refresh_rate']
        config['rss_rate'] = sabnzbd.CFG['misc']['rss_rate']
        config['username_newzbin'] = sabnzbd.CFG['newzbin']['username']
        config['password_newzbin'] = sabnzbd.CFG['newzbin']['password']
        config['cache_limit'] = sabnzbd.CFG['misc']['cache_limit']
        
        if not sabnzbd.CFG['misc']['cleanup_list']:
            config['cleanup_list'] = ','
        
        elif len(sabnzbd.CFG['misc']['cleanup_list']) == 1:
            config['cleanup_list'] = '%s,' % sabnzbd.CFG['misc']['cleanup_list'][0]
        
        else:
            config['cleanup_list'] = listquote.makelist(sabnzbd.CFG['misc']['cleanup_list'])
        
        template = Template(file=os.path.join(self.__web_dir, 'config_general.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def saveGeneral(self, host = None, port = None, username = None, password = None, web_dir = None,
                    cronlines = None, username_newzbin = None, password_newzbin = None,
                    refresh_rate = None, rss_rate = None,
                    bandwith_limit = None, cleanup_list = None, cache_limit = None):
        sabnzbd.CFG['misc']['host'] = host
        sabnzbd.CFG['misc']['port'] = port
        sabnzbd.CFG['misc']['username'] = username
        sabnzbd.CFG['misc']['password'] = password
        sabnzbd.CFG['misc']['web_dir'] = web_dir
        sabnzbd.CFG['misc']['bandwith_limit'] = bandwith_limit
        sabnzbd.CFG['misc']['refresh_rate'] = refresh_rate
        sabnzbd.CFG['misc']['rss_rate'] = rss_rate
        sabnzbd.CFG['newzbin']['username'] = username_newzbin
        sabnzbd.CFG['newzbin']['password'] = password_newzbin
        sabnzbd.CFG['misc']['cleanup_list'] = listquote.simplelist(cleanup_list)
        sabnzbd.CFG['misc']['cache_limit'] = cache_limit
        
        if not web_dir:
            web_dir= 'templates'
        dd = os.path.abspath(sabnzbd.DIR_PROG + '/' + web_dir)
        if dd and not os.access(dd, os.R_OK):
            return "Error: cannot access template directory %s" % dd
        if dd and not os.access(dd + '/main.tmpl', os.R_OK):
        	  return "Error: \"%s\" is not a valid template directory (cannot see main.tmpl)." % dd
        sabnzbd.CFG['misc']['web_dir'] = web_dir

        return saveAndRestart(self.__root)
        
    
#------------------------------------------------------------------------------

class ConfigServer(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/server/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        config, pnfo_list, bytespersec = build_header()
        
        config['servers'] = sabnzbd.CFG['servers']
        
        template = Template(file=os.path.join(self.__web_dir, 'config_server.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def addServer(self, server = None, host = None, port = None, username = None,
                         password = None, connections = None, fillserver = None):

        if connections == "":
            connections = '1'
        if port == "":
            port = '119'
        if host and port and port.isdigit() \
        and connections.isdigit() and fillserver and fillserver.isdigit():
            server = "%s:%s" % (host, port)
            
            if server not in sabnzbd.CFG['servers']:
                sabnzbd.CFG['servers'][server] = {}
                
                sabnzbd.CFG['servers'][server]['host'] = host
                sabnzbd.CFG['servers'][server]['port'] = port
                sabnzbd.CFG['servers'][server]['username'] = username
                sabnzbd.CFG['servers'][server]['password'] = password
                sabnzbd.CFG['servers'][server]['connections'] = connections
                sabnzbd.CFG['servers'][server]['fillserver'] = fillserver
                return saveAndRestart(self.__root)
                
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def saveServer(self, server = None, host = None, port = None, username = None,
                         password = None, connections = None, fillserver = None):
        
        if connections == "":
            connections = '1'
        if port == "":
            port = '119'
        if host and port and port.isdigit() \
        and connections.isdigit() and fillserver and fillserver.isdigit():
            try:
            	 oldhost, oldport = server.split(":")
            except ValueError:
            	 oldhost= server
            	 oldport= "119"
            if not port == oldport:
                del sabnzbd.CFG['servers'][server]
                server = host + ":" + port
                sabnzbd.CFG['servers'][server] = {}
                
            sabnzbd.CFG['servers'][server]['host'] = host
            sabnzbd.CFG['servers'][server]['port'] = port
            sabnzbd.CFG['servers'][server]['username'] = username
            sabnzbd.CFG['servers'][server]['password'] = password
            sabnzbd.CFG['servers'][server]['connections'] = connections
            sabnzbd.CFG['servers'][server]['fillserver'] = fillserver
            return saveAndRestart(self.__root)
            
        raise cherrypy.HTTPRedirect(self.__root)
            
    @cherrypy.expose
    def delServer(self, *args, **kwargs):
        if 'server' in kwargs and kwargs['server'] in sabnzbd.CFG['servers']:
            del sabnzbd.CFG['servers'][kwargs['server']]
            return saveAndRestart(self.__root)
            
#------------------------------------------------------------------------------
        
class ConfigRss(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/rss/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        config, pnfo_list, bytespersec = build_header()
        
        config['have_feedparser'] = sabnzbd.rss.HAVE_FEEDPARSER
        
        rss_tup = sabnzbd.get_rss_info()
        if rss_tup:
            config['uris'], config['uri_table'] = rss_tup
            
        template = Template(file=os.path.join(self.__web_dir, 'config_rss.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def add_rss_feed(self, uri = None, text_filter = None, re_filter = None, 
                     unpack_opts = None, match_multiple = None):
        if uri and match_multiple and unpack_opts and (text_filter or re_filter):
            unpack_opts = int(unpack_opts)
            match_multiple = bool(int(match_multiple))
            sabnzbd.add_rss_feed(uri, text_filter, re_filter, unpack_opts, 
                                 match_multiple)
        return saveAndRestart(self.__root)
            
    @cherrypy.expose
    def del_rss_feed(self, uri_id = None):
        if uri_id:
            sabnzbd.del_rss_feed(uri_id)
        return saveAndRestart(self.__root)
        
    @cherrypy.expose    
    def del_rss_filter(self, uri_id = None, filter_id = None):
        if uri_id and filter_id:
            sabnzbd.del_rss_filter(uri_id, filter_id)
        return saveAndRestart(self.__root)
        
#------------------------------------------------------------------------------

class ConfigScheduling(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/scheduling/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        config, pnfo_list, bytespersec = build_header()
        
        config['schedlines'] = sabnzbd.CFG['misc']['schedlines']
        
        template = Template(file=os.path.join(self.__web_dir, 'config_scheduling.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def addSchedule(self, minute = None, hour = None, dayofweek = None, 
                    action = None):
        if minute and hour  and dayofweek and action:
            sabnzbd.CFG['misc']['schedlines'].append('%s %s %s %s' %
                                              (minute, hour, dayofweek, action))
        return saveAndRestart(self.__root)
        
    @cherrypy.expose
    def delSchedule(self, line = None):
        if line and line in sabnzbd.CFG['misc']['schedlines']:
            sabnzbd.CFG['misc']['schedlines'].remove(line)
        return saveAndRestart(self.__root)
        
#------------------------------------------------------------------------------

class ConnectionInfo(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/connections/'
        
        self.__web_dir = web_dir
        self.lastmail = None
        
    @cherrypy.expose
    def index(self):
        header, pnfo_list, bytespersec = build_header()
        
        header['lastmail'] = self.lastmail

        header['servers'] = []
        
        for server in sabnzbd.DOWNLOADER.servers[:]:
            busy = []
            connected = 0
            
            for nw in server.idle_threads[:]:
                if nw.connected:
                    connected += 1
                    
            for nw in server.busy_threads[:]:
                article = nw.article
                art_name = ""
                nzf_name = ""
                nzo_name = ""
                
                if article:
                    nzf = article.nzf
                    nzo = nzf.nzo
                    
                    art_name = article.article
                    nzf_name = nzf.get_filename()
                    nzo_name = nzo.get_filename()
                    
                busy.append((nw.thrdnum, art_name, nzf_name, nzo_name))
                
                if nw.connected:
                    connected += 1
            
            busy.sort()
            header['servers'].append((server.host, server.port, connected, busy))
            
        template = Template(file=os.path.join(self.__web_dir, 'connection_info.tmpl'),
                            searchList=[header],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def disconnect(self):
        sabnzbd.disconnect()
        
        raise cherrypy.HTTPRedirect(self.__root)
        
    @cherrypy.expose
    def testmail(self):
        logging.debug("Sending testmail")
        self.lastmail= email_send("SABnzbd testing email connection", "All is OK")
        
        raise cherrypy.HTTPRedirect(self.__root)
    
def saveAndRestart(redirect_root):
    sabnzbd.CFG.write()
    f = open(sabnzbd.CFG.filename)
    x = f.read()
    f.close()
    f = open(sabnzbd.CFG.filename, "w")
    f.write(x)
    f.flush()
    f.close()
    sabnzbd.halt()
    init_ok = sabnzbd.initialize()
    if init_ok:
        sabnzbd.start()
        raise cherrypy.HTTPRedirect(redirect_root)
    else:
        return "SABnzbd restart failed! See logfile(s)."
    
def build_header():
    try:
        uptime = calc_age(sabnzbd.START)
    except:
        uptime = "Error"
        
    header = { 'version':sabnzbd.__version__, 'paused':sabnzbd.paused(),
               'uptime':uptime }
               
    header['diskspace1'] = "%.2f" % diskfree(sabnzbd.DOWNLOAD_DIR)
    header['diskspace2'] = "%.2f" % diskfree(sabnzbd.COMPLETE_DIR)
    header['shutdown'] = sabnzbd.AUTOSHUTDOWN
    header['nt'] = os.name == 'nt'
    
    bytespersec = sabnzbd.bps()
    qnfo = sabnzbd.queue_info()
    
    mbleft = qnfo[QNFO_BYTES_LEFT_FIELD]
    mb = qnfo[QNFO_BYTES_FIELD]
    
    header['kbpersec'] = "%.2f" % (bytespersec / KIBI)
    header['mbleft']   = "%.2f" % (mbleft / MEBI)
    header['mb']       = "%.2f" % (mb / MEBI)
    
    anfo  = sabnzbd.cache_info()
    
    header['cache_art'] = str(anfo[ANFO_ARTICLE_SUM_FIELD])
    header['cache_size'] = str(anfo[ANFO_CACHE_SIZE_FIELD])
    header['cache_limit'] = str(anfo[ANFO_CACHE_LIMIT_FIELD])
    
    header['nzb_quota'] = sabnzbd.nzbgrab.QUOTA
    
    return (header, qnfo[QNFO_PNFO_LIST_FIELD], bytespersec)
    
def calc_age(date):
    try:
        now = datetime.datetime.now()
        
        age = str(now - date).split(".")[0]
    except:
        age = "Error"
        
    return age

#------------------------------------------------------------------------------

class ConfigEmail(ProtectedClass):
    def __init__(self, web_dir):
        self.roles = ['admins']
        
        self.__root = '/sabnzbd/config/email/'
        
        self.__web_dir = web_dir
        
    @cherrypy.expose
    def index(self):
        config, pnfo_list, bytespersec = build_header()
        
        config['email_server'] = sabnzbd.CFG['misc']['email_server']
        config['email_to'] = sabnzbd.CFG['misc']['email_to']
        config['email_from'] = sabnzbd.CFG['misc']['email_from']
        config['email_account'] = sabnzbd.CFG['misc']['email_account']
        config['email_pwd'] = sabnzbd.CFG['misc']['email_pwd']
        config['email_endjob'] = int(sabnzbd.CFG['misc']['email_endjob'])
        config['email_full'] = int(sabnzbd.CFG['misc']['email_full'])
        
        template = Template(file=os.path.join(self.__web_dir, 'config_email.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#', 
                                              'directiveEndToken': '#-->'})
        return template.respond()
        
    @cherrypy.expose
    def saveEmail(self, email_server = None, email_to = None, email_from = None,
                  email_account = None, email_pwd = None,
                  email_endjob = None, email_full = None):
        sabnzbd.CFG['misc']['email_server'] = email_server
        sabnzbd.CFG['misc']['email_to'] = email_to
        sabnzbd.CFG['misc']['email_from'] = email_from
        sabnzbd.CFG['misc']['email_account'] = email_account
        sabnzbd.CFG['misc']['email_pwd'] = email_pwd
        sabnzbd.CFG['misc']['email_endjob'] = email_endjob
        sabnzbd.CFG['misc']['email_full'] = email_full
        
        return saveAndRestart(self.__root)

    