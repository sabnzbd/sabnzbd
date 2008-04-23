#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#           2007 The ShyPike <shypike@users.sourceforge.net>
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
import re
import glob
from xml.sax.saxutils import escape

from sabnzbd.utils.rsslib import RSS, Item, Namespace
from sabnzbd.utils.json import JsonWriter
import sabnzbd

from cherrypy.filters.gzipfilter import GzipFilter

from sabnzbd.utils.multiauth.filter import MultiAuthFilter
from sabnzbd.utils.multiauth.auth import ProtectedClass, SecureResource
from sabnzbd.utils.multiauth.providers import DictAuthProvider

from sabnzbd.utils import listquote
from sabnzbd.utils.configobj import ConfigObj
from Cheetah.Template import Template
from sabnzbd.email import email_send
from sabnzbd.misc import real_path, create_real_path, save_configfile, \
                         to_units, from_units, SameFile, encode_for_xml, \
                         decodePassword, encodePassword
from sabnzbd.nzbstuff import SplitFileName
from sabnzbd.newswrapper import GetServerParms
from sabnzbd.newzbin import InitCats, IsNewzbin

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
            return (s[statvfs.F_BAVAIL] * s[statvfs.F_FRSIZE]) / GIGI
        except OSError:
            return 0.0
    def disktotal(_dir):
        try:
            s = os.statvfs(_dir)
            return (s[statvfs.F_BLOCKS] * s[statvfs.F_FRSIZE]) / GIGI
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
    def disktotal(_dir):
        try:
            secp, byteper, freecl, noclu = win32api.GetDiskFreeSpace(_dir)
            return (secp * byteper * noclu) / GIGI
        except:
            return 0.0


def CheckFreeSpace():
    if sabnzbd.DOWNLOAD_FREE > 0 and not sabnzbd.paused():
        if diskfree(sabnzbd.DOWNLOAD_DIR) < float(sabnzbd.DOWNLOAD_FREE) / GIGI:
            logging.info('Too little diskspace forcing PAUSE')
            # Pause downloader, but don't save, since the disk is almost full!
            sabnzbd.pause_downloader(save=False)
            if sabnzbd.EMAIL_FULL:
                email_send("SABnzbd has halted", "SABnzbd has halted because diskspace is below the minimum.\n\nSABnzbd")


def check_timeout(timeout):
    """ Check sensible ranges for server timeout """
    if timeout.isdigit():
        if int(timeout) < MIN_TIMEOUT:
            timeout = MIN_TIMEOUT
        elif int(timeout) > MAX_TIMEOUT:
            timeout = MAX_TIMEOUT
    else:
        timeout = DEF_TIMEOUT
    return timeout


def check_server(host, port):
    """ Check if server address resolves properly """

    if host.lower() == 'localhost' and sabnzbd.AMBI_LOCALHOST:
        return badParameterResponse('Warning: LOCALHOST is ambiguous, use numerical IP-address.')

    if GetServerParms(host, port):
        return ""
    else:
        return badParameterResponse('Server address "%s:%s" is not valid.' % (host, port))

def ListScripts():
    """ Return a list of script names """
    lst = []
    dd = sabnzbd.SCRIPT_DIR
    if dd and os.access(dd, os.R_OK):
        lst = ['None']
        for script in glob.glob(dd + '/*'):
            if os.path.isfile(script):
                sc= os.path.basename(script)
                if sc != "_svn" and sc != ".svn":
                    lst.append(sc)
    return lst


def ListCats():
    """ Return list of categories """
    lst = ['None']
    for cat in sabnzbd.CFG['categories']:
        lst.append(cat)
    if len(lst) < 2:
        return []
    return lst


def Raiser(root, dummy):
    if dummy:
        root += '?dummy=' + dummy
    return cherrypy.HTTPRedirect(root)


def IntConv(value):
    """Safe conversion to int"""
    try:
        value = int(value)
    except:
        value = 0
    return value

def IsNone(value):
    """ Return True if either None, 'None' or '' """
    return value==None or value=="" or value.lower()=='none'


def List2String(lst):
    """ Return list as a comma-separated string """
    if type(lst) == type(""):
        return lst
    txt = ''
    r = len(lst)
    for n in xrange(r):
        txt += lst[n]
        if n < r-1: txt += ', '

    return txt

def String2List(txt):
    """ Return comma-separated string as a list """

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
class LoginPage:
    def __init__(self, web_dir, root, web_dir2=None, root2=None):
        self._cpFilterList = [GzipFilter()]

        if USERNAME and PASSWORD:
            PROVIDER.add(USERNAME, PASSWORD, ['admins'])

            self._cpFilterList.append(MultiAuthFilter('/unauthorized', PROVIDER))
        else:
            self._cpFilterList.append(DummyFilter('', PROVIDER))

        self.sabnzbd = MainPage(web_dir, root, prim=True)
        if web_dir2:
            self.sabnzbd.m = MainPage(web_dir2, root2, prim=False)
        else:
            self.sabnzbd.m = NoPage()

    @cherrypy.expose
    def index(self, dummy = None):
        return ""

    @cherrypy.expose
    def unauthorized(self):
        return "<h1>You are not authorized to view this resource</h1>"


#------------------------------------------------------------------------------
class NoPage(ProtectedClass):
    def __init__(self):
        pass

    @cherrypy.expose
    def index(self, dummy = None):
        return badParameterResponse('Error: No secondary interface defined.')


#------------------------------------------------------------------------------
class MainPage(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.queue = QueuePage(web_dir, root+'queue/', prim)
        self.history = HistoryPage(web_dir, root+'history/', prim)
        self.connections = ConnectionInfo(web_dir, root+'connections/', prim)
        self.config = ConfigPage(web_dir, root+'config/', prim)


    @cherrypy.expose
    def index(self, dummy = None):
        info, pnfo_list, bytespersec = build_header(self.__prim)

        if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
            info['newzbinDetails'] = True

        info['script_list'] = ListScripts()
        info['script_list'].insert(0, 'Default')
        info['script'] = sabnzbd.DIRSCAN_SCRIPT

        info['cat'] = 'None'
        info['cat_list'] = ListCats()

        info['warning'] = ""
        if not sabnzbd.CFG['servers']:
            info['warning'] = "No Usenet server defined, please check Config-->Servers<br/>"

        if not sabnzbd.newsunpack.PAR2_COMMAND:
            info['warning'] += "No PAR2 program found, repairs not possible<br/>"

        template = Template(file=os.path.join(self.__web_dir, 'main.tmpl'),
                            searchList=[info],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def addID(self, id = None, pp=None, script=None, cat=None, redirect = None):
        if pp and pp=="-1": pp = None
        if script and script.lower()=='default': script = None

        if id: id = id.strip()
        if id and (id.isdigit() or len(id)==5):
            sabnzbd.add_msgid(id, pp, script, cat)
        elif id:
            sabnzbd.add_url(id, pp, script, cat)
        if not redirect:
            redirect = self.__root
        raise cherrypy.HTTPRedirect(redirect)


    @cherrypy.expose
    def addURL(self, url = None, pp=None, script=None, cat=None, redirect = None):
        if pp and pp=="-1": pp = None
        if script and script.lower()=='default': script = None

        if url: url = url.strip()
        if url and (url.isdigit() or len(url)==5):
            sabnzbd.add_msgid(url, pp, script, cat)
        elif url:
            sabnzbd.add_url(url, pp, script, cat)
        if not redirect:
            redirect = self.__root
        raise cherrypy.HTTPRedirect(redirect)


    @cherrypy.expose
    def addFile(self, nzbfile, pp=None, script=None, cat=None, dummy = None):
        if pp and pp=="-1": pp = None
        if script and script.lower()=='default': script = None

        if nzbfile.filename and nzbfile.value:
            sabnzbd.add_nzbfile(nzbfile, pp, script, cat)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def shutdown(self):
        yield "Initiating shutdown..."
        sabnzbd.halt()
        cherrypy.server.stop()
        yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
        raise KeyboardInterrupt()

    @cherrypy.expose
    def pause(self, dummy = None):
        sabnzbd.pause_downloader()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def resume(self, dummy = None):
        sabnzbd.resume_downloader()
        raise Raiser(self.__root, dummy)

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

    @cherrypy.expose
    def rss(self, mode='history'):
        if mode == 'history':
            return rss_history()
        elif mode == 'warnings':
            return rss_warnings()


    @cherrypy.expose
    def api(self, mode='', name=None, pp=None, script=None, cat=None,
            output='plain', value = None, dummy = None):
        """Handler for API over http
        """
        if mode == 'qstatus':
            if output == 'json':
                return json_qstatus()
            elif output == 'xml':
                return xml_qstatus()
            else:
                return 'not implemented\n'
        elif mode == 'addfile':
            if name.filename and name.value:
                sabnzbd.add_nzbfile(name, pp, script, cat)
                return 'ok\n'
            else:
                return 'error\n'

        elif mode == 'addurl':
            if name:
                sabnzbd.add_url(name, pp, script, cat)
                return 'ok\n'
            else:
                return 'error\n'

        elif mode == 'addid':
            if name and (name.isdigit() or len(name)==5):
                sabnzbd.add_msgid(name, pp, script)
                return 'ok\n'
            else:
                return 'error\n'

        elif mode == 'pause':
            sabnzbd.pause_downloader()
            return 'ok\n'

        elif mode == 'resume':
            sabnzbd.resume_downloader()
            return 'ok\n'

        elif mode == 'shutdown':
            sabnzbd.halt()
            cherrypy.server.stop()
            raise KeyboardInterrupt()

        elif mode == 'warnings':
            if output == 'json':
                return json_list("warnings", sabnzbd.GUIHANDLER.content())
            elif output == 'xml':
                return xml_list("warnings", "warning", sabnzbd.GUIHANDLER.content())
            else:
                return 'not implemented\n'

        elif mode == 'queue':
            if name == 'change_complete_action': # http://localhost:8080/sabnzbd/api?mode=queue&name=change_complete_action&value=hibernate_pc
                if value:
                    sabnzbd.change_queue_complete_action(value)
                    return 'ok\n'
                else:
                    return 'error: Please submit a value\n'
            elif name == 'purge':
                sabnzbd.remove_all_nzo()
                return 'ok\n'
            else:
                return 'error: Please submit a value\n'

        elif mode == 'config':
            if name == 'speedlimit': # http://localhost:8080/sabnzbd/api?mode=config&name=speedlimit&value=400
                if value.isdigit():
                    sabnzbd.CFG['misc']['bandwith_limit'] = value
                    sabnzbd.BANDWITH_LIMIT = value
                    save_configfile(sabnzbd.CFG)
                    return 'ok\n'
                else:
                    return 'error: Please submit a value\n'
            else:
                return 'not implemented\n'

        elif mode == 'get_cats':
            if output == 'json':
                return json_list("categories", ListCats())
            elif output == 'xml':
                return xml_list("categories", "category", ListCats())
            else:
                return 'not implemented\n'

        elif mode == 'get_scripts':
            if output == 'json':
                return json_list("scripts", ListScripts())
            elif output == 'xml':
                return xml_list("scripts", "script", ListScripts())
            else:
                return 'not implemented\n'

        else:
            return 'not implemented\n'

    @cherrypy.expose
    def scriptlog(self, name=None, dummy=None):
        """ Duplicate of scriptlog of History, needed for some skins """
        if name:
            path = os.path.dirname(sabnzbd.LOGFILE)
            return ShowFile(name, os.path.join(path, name))
        else:
            raise Raiser(self.__root, dummy)

#------------------------------------------------------------------------------
class NzoPage(ProtectedClass):
    def __init__(self, web_dir, root, nzo_id, prim):
        self.roles = ['admins']
        self.__nzo_id = nzo_id
        self.__root = '%s%s/' % (root, nzo_id)
        self.__web_dir = web_dir
        self.__verbose = False
        self.__prim = prim
        self.__cached_selection = {} #None

    @cherrypy.expose
    def index(self, dummy = None):
        info, pnfo_list, bytespersec = build_header(self.__prim)

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

        if 'dummy' in kwargs:
            raise Raiser(self.__root, kwargs['dummy'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def tog_verbose(self, dummy = None):
        self.__verbose = not self.__verbose
        raise Raiser(self.__root, dummy)

#------------------------------------------------------------------------------
class QueuePage(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verboseList = []
        self.__prim = prim

        self.__nzo_pages = []

    @cherrypy.expose
    def index(self, dummy = None):
        info, pnfo_list, bytespersec = build_header(self.__prim)

        info['isverbose'] = self.__verbose
        if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
            info['newzbinDetails'] = True

        if int(sabnzbd.CFG['misc']['refresh_rate']) > 0:
            info['refresh_rate'] = sabnzbd.CFG['misc']['refresh_rate']
        else:
            info['refresh_rate'] = ''

        info['noofslots'] = len(pnfo_list)
        datestart = datetime.datetime.now()

        info['script_list'] = ListScripts()
        info['cat_list'] = ListCats()

        n = 0
        running_bytes = 0
        slotinfo = []

        nzo_ids = []

        for pnfo in pnfo_list:
            repair = pnfo[PNFO_REPAIR_FIELD]
            unpack = pnfo[PNFO_UNPACK_FIELD]
            delete = pnfo[PNFO_DELETE_FIELD]
            script = pnfo[PNFO_SCRIPT_FIELD]
            nzo_id = pnfo[PNFO_NZO_ID_FIELD]
            cat = pnfo[PNFO_EXTRA_FIELD1]
            filename = pnfo[PNFO_FILENAME_FIELD]
            bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD]
            bytes = pnfo[PNFO_BYTES_FIELD]
            average_date = pnfo[PNFO_AVG_DATE_FIELD]
            finished_files = pnfo[PNFO_FINISHED_FILES_FIELD]
            active_files = pnfo[PNFO_ACTIVE_FILES_FIELD]
            queued_files = pnfo[PNFO_QUEUED_FILES_FIELD]

            nzo_ids.append(nzo_id)

            if nzo_id not in self.__dict__:
                self.__dict__[nzo_id] = NzoPage(self.__web_dir, self.__root, nzo_id, self.__prim)
                self.__nzo_pages.append(nzo_id)

            slot = {'index':n, 'nzo_id':str(nzo_id)}
            n += 1
            unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)

            slot['unpackopts'] = str(unpackopts)
            slot['script'] = str(script)
            fn, slot['msgid'] = SplitFileName(filename)
            slot['filename'] = escape(fn)
            slot['cat'] = str(cat)
            slot['mbleft'] = "%.2f" % (bytesleft / MEBI)
            slot['mb'] = "%.2f" % (bytes / MEBI)

            running_bytes += bytesleft

            slot['timeleft'] = calc_timeleft(running_bytes, bytespersec)

            try:
                datestart = datestart + datetime.timedelta(seconds=bytesleft / bytespersec)
                #new eta format: 16:00 Fri 07 Feb
                slot['eta'] = '%s' % datestart.strftime('%H:%M %a %d %b')
            except:
                datestart = datetime.datetime.now()
                slot['eta'] = 'unknown'

            slot['avg_age'] = calc_age(average_date)

            finished = []
            active = []
            queued = []
            if self.__verbose or nzo_id in self.__verboseList:

                date_combined = 0
                num_dates = 0

                for tup in finished_files:
                    bytes_left, bytes, fn, date = tup
                    if isinstance(fn, unicode):
                        fn = escape(fn.encode('utf-8'))

                    age = calc_age(date)

                    line = {'filename':str(fn),
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'age':age}
                    finished.append(line)

                for tup in active_files:
                    bytes_left, bytes, fn, date, nzf_id = tup
                    if isinstance(fn, unicode):
                        fn = escape(fn.encode('utf-8'))

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
                        fn = escape(fn.encode('utf-8'))

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
        else:
            self.__verboseList = []

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
    def delete(self, uid = None, dummy = None):
        if uid:
            sabnzbd.remove_nzo(uid, False)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def purge(self, dummy = None):
        sabnzbd.remove_all_nzo()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def removeNzf(self, nzo_id = None, nzf_id = None, dummy = None):
        if nzo_id and nzf_id:
            sabnzbd.remove_nzf(nzo_id, nzf_id)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def tog_verbose(self, dummy = None):
        self.__verbose = not self.__verbose
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def tog_uid_verbose(self, uid, dummy = None):
        if self.__verboseList.count(uid):
            self.__verboseList.remove(uid)
        else:
            self.__verboseList.append(uid)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def change_queue_complete_action(self, action = None, dummy = None):
        """
        Action or script to be performed once the queue has been completed
        Scripts are prefixed with 'script_'
        """
        sabnzbd.change_queue_complete_action(action)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def switch(self, uid1 = None, uid2 = None, dummy = None):
        if uid1 and uid2:
            sabnzbd.switch(uid1, uid2)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def change_opts(self, nzo_id = None, pp = None, dummy = None):
        if nzo_id and pp and pp.isdigit():
            sabnzbd.change_opts(nzo_id, int(pp))
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def change_script(self, nzo_id = None, script = None, dummy = None):
        if nzo_id and script:
            if script == 'None':
                script = None
            sabnzbd.change_script(nzo_id, script)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def change_cat(self, nzo_id = None, cat = None, dummy = None):
        if nzo_id and cat:
            if cat == 'None':
                cat = None
            sabnzbd.change_cat(nzo_id, cat)
            try:
                script = sabnzbd.CFG['categories'][cat]['script']
            except:
                script = sabnzbd.DIRSCAN_SCRIPT
            try:
                pp = int(sabnzbd.CFG['categories'][cat]['pp'])
            except:
                pp = sabnzbd.DIRSCAN_PP

            sabnzbd.change_script(nzo_id, script)
            sabnzbd.change_opts(nzo_id, pp)

        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def shutdown(self):
        yield "Initiating shutdown..."
        sabnzbd.halt()
        cherrypy.server.stop()
        yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
        raise KeyboardInterrupt()

    @cherrypy.expose
    def pause(self, dummy = None):
        sabnzbd.pause_downloader()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def resume(self, dummy = None):
        sabnzbd.resume_downloader()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def sort_by_avg_age(self, dummy = None):
        sabnzbd.sort_by_avg_age()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def sort_by_name(self, dummy = None):
        sabnzbd.sort_by_name()
        raise Raiser(self.__root, dummy)

class HistoryPage(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = True
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        history, pnfo_list, bytespersec = build_header(self.__prim)

        history['isverbose'] = self.__verbose

        if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
            history['newzbinDetails'] = True

        history_items, total_bytes, bytes_beginning = sabnzbd.history_info()

        history['total_bytes'] = "%.2f" % (total_bytes / GIGI)

        history['bytes_beginning'] = "%.2f" % (bytes_beginning / GIGI)

        items = []
        while history_items:
            added = max(history_items.keys())

            history_item_list = history_items.pop(added)

            for history_item in history_item_list:
                filename, unpackstrht, loaded, bytes, nzo, status = history_item
                name, msgid = SplitFileName(filename)
                stages = []
                item = {'added':time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(added)),
                        'nzo':nzo,
                        'msgid':msgid, 'filename':escape(name), 'loaded':loaded,
                        'stages':stages, 'status':status}
                if self.__verbose:
                    stage_keys = unpackstrht.keys()
                    stage_keys.sort()
                    for stage in stage_keys:
                        stageLine = {'name':STAGENAMES[stage]}
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
    def purge(self, dummy = None):
        sabnzbd.purge_history()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def delete(self, job=None, dummy = None):
        if job:
            sabnzbd.purge_history(job)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def reset(self, dummy = None):
        sabnzbd.reset_byte_counter()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def tog_verbose(self, dummy = None):
        self.__verbose = not self.__verbose
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def scriptlog(self, name=None, dummy=None):
        if name:
            path = os.path.dirname(sabnzbd.LOGFILE)
            return ShowFile(name, os.path.join(path, name))
        else:
            raise Raiser(self.__root, dummy)

#------------------------------------------------------------------------------
class ConfigPage(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']

        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.directories = ConfigDirectories(web_dir, root+'directories/', prim)
        self.email = ConfigEmail(web_dir, root+'email/', prim)
        self.general = ConfigGeneral(web_dir, root+'general/', prim)
        self.newzbin = ConfigNewzbin(web_dir, root+'newzbin/', prim)
        self.rss = ConfigRss(web_dir, root+'rss/', prim)
        self.scheduling = ConfigScheduling(web_dir, root+'scheduling/', prim)
        self.server = ConfigServer(web_dir, root+'server/', prim)
        self.switches = ConfigSwitches(web_dir, root+'switches/', prim)
        self.categories = ConfigCats(web_dir, root+'categories/', prim)


    @cherrypy.expose
    def index(self, dummy = None):
        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['configfn'] = sabnzbd.CFG.filename

        template = Template(file=os.path.join(self.__web_dir, 'config.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def restart(self, dummy = None):
        sabnzbd.halt()
        init_ok = sabnzbd.initialize()
        if init_ok:
            sabnzbd.start()
            raise Raiser(self.__root, dummy)
        else:
            return "SABnzbd restart failed! See logfile(s)."

#------------------------------------------------------------------------------
class ConfigDirectories(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']

        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['download_dir'] = sabnzbd.CFG['misc']['download_dir']
        config['download_free'] = sabnzbd.CFG['misc']['download_free'].upper()
        config['complete_dir'] = sabnzbd.CFG['misc']['complete_dir']
        config['cache_dir'] = sabnzbd.CFG['misc']['cache_dir']
        config['log_dir'] = sabnzbd.CFG['misc']['log_dir']
        config['nzb_backup_dir'] = sabnzbd.CFG['misc']['nzb_backup_dir']
        config['dirscan_dir'] = sabnzbd.CFG['misc']['dirscan_dir']
        config['dirscan_speed'] = sabnzbd.CFG['misc']['dirscan_speed']
        config['script_dir'] = sabnzbd.CFG['misc']['script_dir']
        config['my_home'] = sabnzbd.DIR_HOME
        config['my_lcldata'] = sabnzbd.DIR_LCLDATA
        config['permissions'] = sabnzbd.UMASK
        config['enable_tv_sorting'] = IntConv(sabnzbd.CFG['misc']['enable_tv_sorting'])
        config['tv_sort_seasons'] = IntConv(sabnzbd.CFG['misc']['tv_sort_seasons'])
        config['tv_sort'] = IntConv(sabnzbd.CFG['misc']['tv_sort'])
        tvSortList = []
        for tvsort in TVSORTINGLIST:
            tvSortList.append(tvsort)
        config['tvsort_list'] = tvSortList

        template = Template(file=os.path.join(self.__web_dir, 'config_directories.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveDirectories(self, download_dir = None, download_free = None, complete_dir = None, log_dir = None,
                        cache_dir = None, nzb_backup_dir = None, permissions=None,
                        tv_sort = None, enable_tv_sorting = None, tv_sort_seasons = None,
                        dirscan_dir = None, dirscan_speed = None, script_dir = None, dummy = None):

        if permissions:
            try:
                int(permissions,8)
            except:
                return badParameterResponse('Error: use octal notation for permissions')

        (dd, path) = create_real_path('download_dir', sabnzbd.DIR_HOME, download_dir)
        if not dd:
            return badParameterResponse('Error: cannot create download directory "%s".' % path)

        (dd, path) = create_real_path('cache_dir', sabnzbd.DIR_LCLDATA, cache_dir)
        if not dd:
            return badParameterResponse('Error: cannot create cache directory "%s".' % path)

        (dd, path) = create_real_path('log_dir', sabnzbd.DIR_LCLDATA, log_dir)
        if not dd:
            return badParameterResponse('Error: cannot create log directory "%s".' % path)

        if dirscan_dir:
            (dd, path) = create_real_path('dirscan_dir', sabnzbd.DIR_HOME, dirscan_dir)
            if not dd:
                return badParameterResponse('Error: cannot create dirscan_dir directory "%s".' % path)

        (dd, path) = create_real_path('complete_dir', sabnzbd.DIR_HOME, complete_dir)
        if not dd:
            return badParameterResponse('Error: cannot create complete_dir directory "%s".' % path)

        if nzb_backup_dir:
            (dd, path) = create_real_path('nzb_backup_dir', sabnzbd.DIR_LCLDATA, nzb_backup_dir)
            if not dd:
                return badParameterResponse('Error: cannot create nzb_backup_dir directory %s".' % path)

        if script_dir:
            (dd, path) = create_real_path('script_dir', sabnzbd.DIR_HOME, script_dir)
            if not dd:
                return badParameterResponse('Error: cannot create script_dir directory "%s".' % path)

        #if SameFile(download_dir, complete_dir):
        #    return badParameterResponse('Error: DOWNLOAD_DIR and COMPLETE_DIR should not be the same (%s)!' % path)


        sabnzbd.CFG['misc']['download_dir'] = download_dir
        sabnzbd.CFG['misc']['download_free'] = download_free
        sabnzbd.CFG['misc']['cache_dir'] = cache_dir
        sabnzbd.CFG['misc']['log_dir'] = log_dir
        sabnzbd.CFG['misc']['dirscan_dir'] = dirscan_dir
        sabnzbd.CFG['misc']['dirscan_speed'] = dirscan_speed
        sabnzbd.CFG['misc']['script_dir'] = script_dir
        sabnzbd.CFG['misc']['complete_dir'] = complete_dir
        sabnzbd.CFG['misc']['nzb_backup_dir'] = nzb_backup_dir
        if permissions: sabnzbd.CFG['misc']['permissions'] = permissions
        sabnzbd.CFG['misc']['tv_sort'] = IntConv(tv_sort)
        sabnzbd.CFG['misc']['enable_tv_sorting'] = IntConv(enable_tv_sorting)
        sabnzbd.CFG['misc']['tv_sort_seasons'] = IntConv(tv_sort_seasons)

        return saveAndRestart(self.__root, dummy)

#------------------------------------------------------------------------------
class ConfigSwitches(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['enable_unrar'] = IntConv(sabnzbd.CFG['misc']['enable_unrar'])
        config['enable_unzip'] = IntConv(sabnzbd.CFG['misc']['enable_unzip'])
        config['enable_filejoin'] = IntConv(sabnzbd.CFG['misc']['enable_filejoin'])
        config['enable_save'] = IntConv(sabnzbd.CFG['misc']['enable_save'])
        config['enable_par_cleanup'] = IntConv(sabnzbd.CFG['misc']['enable_par_cleanup'])
        config['send_group'] = IntConv(sabnzbd.CFG['misc']['send_group'])
        config['fail_on_crc'] = IntConv(sabnzbd.CFG['misc']['fail_on_crc'])
        config['create_group_folders'] = IntConv(sabnzbd.CFG['misc']['create_group_folders'])
        config['dirscan_opts'] = IntConv(sabnzbd.CFG['misc']['dirscan_opts'])
        config['top_only'] = IntConv(sabnzbd.CFG['misc']['top_only'])
        config['auto_sort'] = IntConv(sabnzbd.CFG['misc']['auto_sort'])
        config['check_rel'] = IntConv(sabnzbd.CFG['misc']['check_new_rel'])
        config['auto_disconnect'] = IntConv(sabnzbd.CFG['misc']['auto_disconnect'])
        config['replace_spaces'] = IntConv(sabnzbd.CFG['misc']['replace_spaces'])
        config['safe_postproc'] = IntConv(sabnzbd.CFG['misc']['safe_postproc'])
        config['auto_browser'] = IntConv(sabnzbd.CFG['misc']['auto_browser'])
        config['ignore_samples'] = IntConv(sabnzbd.CFG['misc']['ignore_samples'])
        config['pause_on_post_processing'] = IntConv(sabnzbd.CFG['misc']['pause_on_post_processing'])
        config['script'] = sabnzbd.CFG['misc']['dirscan_script']
        if not config['script']:
            config['script'] = 'None'
        config['script_list'] = ListScripts()

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
                     check_rel = None,
                     auto_disconnect = None,
                     safe_postproc = None,
                     replace_spaces = None,
                     auto_browser = None,
                     ignore_samples = None,
                     pause_on_post_processing = None,
                     script = None,
                     dummy = None
                     ):

        sabnzbd.CFG['misc']['enable_unrar'] = IntConv(enable_unrar)
        sabnzbd.CFG['misc']['enable_unzip'] = IntConv(enable_unzip)
        sabnzbd.CFG['misc']['enable_filejoin'] = IntConv(enable_filejoin)
        sabnzbd.CFG['misc']['enable_save'] = IntConv(enable_save)
        sabnzbd.CFG['misc']['send_group'] = IntConv(send_group)
        sabnzbd.CFG['misc']['fail_on_crc'] = IntConv(fail_on_crc)
        sabnzbd.CFG['misc']['create_group_folders'] = IntConv(create_group_folders)
        sabnzbd.CFG['misc']['dirscan_opts'] = IntConv(dirscan_opts)
        if script == 'None':
            sabnzbd.CFG['misc']['dirscan_script'] = None
        else:
            sabnzbd.CFG['misc']['dirscan_script'] = script
        sabnzbd.CFG['misc']['enable_par_cleanup'] = IntConv(enable_par_cleanup)
        sabnzbd.CFG['misc']['top_only'] = IntConv(top_only)
        sabnzbd.CFG['misc']['auto_sort'] = IntConv(auto_sort)
        sabnzbd.CFG['misc']['check_new_rel'] = IntConv(check_rel)
        sabnzbd.CFG['misc']['auto_disconnect'] = IntConv(auto_disconnect)
        sabnzbd.CFG['misc']['safe_postproc'] = IntConv(safe_postproc)
        sabnzbd.CFG['misc']['replace_spaces'] = IntConv(replace_spaces)
        sabnzbd.CFG['misc']['auto_browser'] = IntConv(auto_browser)
        sabnzbd.CFG['misc']['ignore_samples'] = IntConv(ignore_samples)
        sabnzbd.CFG['misc']['pause_on_post_processing'] = IntConv(pause_on_post_processing)

        return saveAndRestart(self.__root, dummy)

#------------------------------------------------------------------------------

class ConfigGeneral(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        def ListColors(web_dir):
            lst = []
            dd = os.path.abspath(web_dir + '/static/stylesheets/colorschemes')
            if (not dd) or (not os.access(dd, os.R_OK)):
                return lst
            for color in glob.glob(dd + '/*'):
                col= os.path.basename(color).replace('.css','')
                if col != "_svn" and col != ".svn":
                    lst.append(col)
            return lst

        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['configfn'] = sabnzbd.CFG.filename

        config['host'] = sabnzbd.CFG['misc']['host']
        config['port'] = sabnzbd.CFG['misc']['port']
        config['username'] = sabnzbd.CFG['misc']['username']
        config['password'] = '*' * len(decodePassword(sabnzbd.CFG['misc']['password'], 'web'))
        config['bandwith_limit'] = sabnzbd.CFG['misc']['bandwith_limit']
        config['refresh_rate'] = sabnzbd.CFG['misc']['refresh_rate']
        config['rss_rate'] = sabnzbd.CFG['misc']['rss_rate']
        config['cache_limitstr'] = sabnzbd.CFG['misc']['cache_limit'].upper()

        wlist = [DEF_STDINTF]
        wlist2 = ['None', DEF_STDINTF]
        for web in glob.glob(sabnzbd.DIR_INTERFACES + "/*"):
            rweb= os.path.basename(web)
            if rweb != DEF_STDINTF and rweb != "_svn" and rweb != ".svn" and \
               os.access(web + '/' + DEF_MAIN_TMPL, os.R_OK):
                wlist.append(rweb)
                wlist2.append(rweb)
        config['web_list'] = wlist
        config['web_list2'] = wlist2

        config['web_dir']  = sabnzbd.CFG['misc']['web_dir']
        config['web_dir2'] = sabnzbd.CFG['misc']['web_dir2']

        if self.__prim:
            config['web_colors'] = ListColors(sabnzbd.WEB_DIR)
            config['web_color'] = sabnzbd.WEB_COLOR
        else:
            config['web_colors'] = ListColors(sabnzbd.WEB_DIR2)
            config['web_color'] = sabnzbd.WEB_COLOR2

        config['cleanup_list'] = List2String(sabnzbd.CFG['misc']['cleanup_list'])

        template = Template(file=os.path.join(self.__web_dir, 'config_general.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveGeneral(self, host = None, port = None, username = None, password = None, web_dir = None,
                    web_dir2 = None, web_color = None,
                    cronlines = None, refresh_rate = None, rss_rate = None,
                    bandwith_limit = None, cleanup_list = None, cache_limitstr = None, dummy = None):

        sabnzbd.CFG['misc']['web_dir']  = web_dir
        if web_dir2 == 'None':
            sabnzbd.CFG['misc']['web_dir2'] = ''
        else:
            sabnzbd.CFG['misc']['web_dir2'] = web_dir2

        if web_color:
            if self.__prim:
                sabnzbd.CFG['misc']['web_color'] = web_color
            else:
                sabnzbd.CFG['misc']['web_color2'] = web_color

        sabnzbd.CFG['misc']['host'] = host
        sabnzbd.CFG['misc']['port'] = port
        sabnzbd.CFG['misc']['username'] = username
        if (not password) or (password and password.strip('*')):
            sabnzbd.CFG['misc']['password'] = encodePassword(password)
        sabnzbd.CFG['misc']['bandwith_limit'] = bandwith_limit
        sabnzbd.CFG['misc']['refresh_rate'] = refresh_rate
        sabnzbd.CFG['misc']['rss_rate'] = rss_rate
        sabnzbd.CFG['misc']['cleanup_list'] = listquote.simplelist(cleanup_list)
        sabnzbd.CFG['misc']['cache_limit'] = cache_limitstr

        return saveAndRestart(self.__root, dummy)


#------------------------------------------------------------------------------

class ConfigServer(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        new = {}
        org = sabnzbd.CFG['servers']
        for svr in org:
            new[svr] = {}
            new[svr]['host'] = org[svr]['host']
            new[svr]['port'] = org[svr]['port']
            new[svr]['username'] = org[svr]['username']
            new[svr]['password'] = '*' * len(decodePassword(org[svr]['password'], 'server'))
            new[svr]['connections'] = org[svr]['connections']
            new[svr]['timeout'] = org[svr]['timeout']
            new[svr]['fillserver'] = org[svr]['fillserver']
            new[svr]['ssl'] = org[svr]['ssl']
        config['servers'] = new

        if sabnzbd.newswrapper.HAVE_SSL:
            config['have_ssl'] = 1
        else:
            config['have_ssl'] = 0

        template = Template(file=os.path.join(self.__web_dir, 'config_server.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def addServer(self, server = None, host = None, port = None, timeout = None, username = None,
                         password = None, connections = None, ssl = None, fillserver = None, dummy = None):

        timeout = check_timeout(timeout)

        if connections == "":
            connections = '1'
        if port == "":
            port = '119'
        if not fillserver:
            fillserver = 0
        if not ssl:
            ssl = 0

        if host and port and port.isdigit() \
        and connections.isdigit() and fillserver and fillserver.isdigit() \
        and ssl and ssl.isdigit():
            msg = check_server(host, port)
            if msg:
                return msg

            server = "%s:%s" % (host, port)

            msg = check_server(host, port)
            if msg:
                return msg

            if server not in sabnzbd.CFG['servers']:
                sabnzbd.CFG['servers'][server] = {}

                sabnzbd.CFG['servers'][server]['host'] = host
                sabnzbd.CFG['servers'][server]['port'] = port
                sabnzbd.CFG['servers'][server]['username'] = username
                sabnzbd.CFG['servers'][server]['password'] = encodePassword(password)
                sabnzbd.CFG['servers'][server]['timeout'] = timeout
                sabnzbd.CFG['servers'][server]['connections'] = connections
                sabnzbd.CFG['servers'][server]['fillserver'] = fillserver
                sabnzbd.CFG['servers'][server]['ssl'] = ssl
        return saveAndRestart(self.__root, dummy)

    @cherrypy.expose
    def saveServer(self, server = None, host = None, port = None, username = None, timeout = None,
                         password = None, connections = None, fillserver = None, ssl = None, dummy = None):

        timeout = check_timeout(timeout)

        if connections == "":
            connections = '1'
        if port == "":
            port = '119'
        if not ssl:
            ssl = 0
        if host and port and port.isdigit() \
        and connections.isdigit() and fillserver and fillserver.isdigit() \
        and ssl and ssl.isdigit():
            msg = check_server(host, port)
            if msg:
                return msg

            if password and not password.strip('*'):
                password = sabnzbd.CFG['servers'][server]['password']

            del sabnzbd.CFG['servers'][server]

            # Allow IPV6 numerical addresses, '[]' is not compatible with
            # INI file handling, replace by '{}'
            ihost = host.replace('[','{')
            ihost = ihost.replace(']','}')
            server = "%s:%s" % (ihost, port)

            sabnzbd.CFG['servers'][server] = {}

            sabnzbd.CFG['servers'][server]['host'] = host
            sabnzbd.CFG['servers'][server]['port'] = port
            sabnzbd.CFG['servers'][server]['username'] = username
            sabnzbd.CFG['servers'][server]['password'] = encodePassword(password)
            sabnzbd.CFG['servers'][server]['connections'] = connections
            sabnzbd.CFG['servers'][server]['timeout'] = timeout
            sabnzbd.CFG['servers'][server]['fillserver'] = fillserver
            sabnzbd.CFG['servers'][server]['ssl'] = ssl
        return saveAndRestart(self.__root, dummy)

    @cherrypy.expose
    def delServer(self, *args, **kwargs):
        if 'server' in kwargs and kwargs['server'] in sabnzbd.CFG['servers']:
            del sabnzbd.CFG['servers'][kwargs['server']]

        if 'dummy' in kwargs:
            return saveAndRestart(self.__root, kwargs['dummy'])
        else:
            return saveAndRestart(self.__root, '')

#------------------------------------------------------------------------------

def ListFilters(feed):
    """ Make a list of all filters of this feed """
    n = 0
    filters= []
    cfg = sabnzbd.CFG['rss'][feed]
    while True:
        try:
            tup = cfg['filter'+str(n)]
            try:
                cat, pp, scr, act, txt = tup
                filters.append(tup)
            except:
                logging.warning('[%s] Incorrect filter', __NAME__)
            n = n + 1
        except:
            break
    return filters

def UnlistFilters(feed, filters):
    """ Convert list to filter list for this feed """
    cfg = sabnzbd.CFG['rss'][feed]
    n = 0
    while True:
        try:
            del cfg['filter'+str(n)]
            n = n + 1
        except:
            break

    for n in xrange(len(filters)):
        cfg['filter'+str(n)] = filters[n]



def GetCfgRss(cfg, keyword):
    """ Get a keyword from an RSS entry """
    try:
        return cfg[keyword]
    except:
        return ''

class ConfigRss(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['have_feedparser'] = sabnzbd.rss.HAVE_FEEDPARSER

        config['script_list'] = ListScripts()
        config['script_list'].insert(0, 'Default')

        config['cat_list'] = ListCats()

        rss = {}
        unum = 1
        for feed in sabnzbd.CFG['rss']:
            rss[feed] = {}
            cfg = sabnzbd.CFG['rss'][feed]
            rss[feed]['uri'] = GetCfgRss(cfg, 'uri')
            rss[feed]['cat'] = GetCfgRss(cfg, 'cat')
            rss[feed]['pp'] = GetCfgRss(cfg, 'pp')
            rss[feed]['script'] = GetCfgRss(cfg, 'script')
            rss[feed]['enable'] = IntConv(GetCfgRss(cfg, 'enable'))
            rss[feed]['pick_cat'] = config['cat_list'] != [] and not IsNewzbin(GetCfgRss(cfg, 'uri'))
            rss[feed]['pick_script'] = config['script_list'] != []
            filters = ListFilters(feed)
            rss[feed]['filters'] = filters
            rss[feed]['filtercount'] = len(filters)
            unum += 1
        config['rss'] = rss
        config['feed'] = 'Feed' + str(unum)

        template = Template(file=os.path.join(self.__web_dir, 'config_rss.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def upd_rss_feed(self, feed=None, uri=None, cat=None, pp=None, script=None, dummy=None):
        try:
            cfg = sabnzbd.CFG['rss'][feed]
        except:
            feed = None
        if feed and uri:
            cfg['uri'] = uri
            if IsNone(cat): cat = ''
            cfg['cat'] = cat
            if IsNone(pp): pp = ''
            cfg['pp'] = pp
            if script==None or script=='Default': script = ''
            cfg['script'] = script
            cfg['enable'] = 0
            save_configfile(sabnzbd.CFG)

        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def add_rss_feed(self, feed=None, uri=None, dummy=None):
        try:
            sabnzbd.CFG['rss'][feed]
        except:
            sabnzbd.CFG['rss'][feed] = {}
            cfg = sabnzbd.CFG['rss'][feed]
            cfg['uri'] = uri
            cfg['cat'] = ''
            cfg['pp'] = ''
            cfg['script'] = ''
            cfg['enable'] = 0
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def upd_rss_filter(self, feed=None, index=None, filter_text=None,
                       filter_type=None, cat=None, pp=None, script=None, dummy=None):
        try:
            cfg = sabnzbd.CFG['rss'][feed]
        except:
            raise Raiser(self.__root, dummy)

        if IsNone(cat): cat = ''
        if IsNone(pp): pp = ''
        if script==None or script=='Default': script = ''
        cfg['filter'+str(index)] = (cat, pp, script, filter_type, filter_text)
        cfg['enable'] = 0
        save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def pos_rss_filter(self, feed=None, current=None, new=None, dummy=None):
        if current != new:
            filters = ListFilters(feed)
            filter = filters.pop(int(current))
            filters.insert(int(new), filter)
            UnlistFilters(feed, filters)
            sabnzbd.CFG['rss'][feed]['enable'] = 0
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def del_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            try:
                del sabnzbd.CFG['rss'][feed]
                sabnzbd.del_rss_feed(feed)
            except:
                pass
            save_configfile(sabnzbd.CFG)
        if 'dummy' in kwargs:
            raise Raiser(self.__root, kwargs['dummy'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def del_rss_filter(self, feed=None, index=None, dummy=None):
        if feed and index!=None:
            filters = ListFilters(feed)
            filter = filters.pop(int(index))
            UnlistFilters(feed, filters)
            sabnzbd.CFG['rss'][feed]['enable'] = 0
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def query_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            sabnzbd.CFG['rss'][feed]['enable'] = 0
            sabnzbd.run_rss_feed(feed)
            return ShowRssLog(feed)
        if 'dummy' in kwargs:
            raise Raiser(self.__root, kwargs['dummy'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def rematch_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            sabnzbd.CFG['rss'][feed]['enable'] = 0
            sabnzbd.run_rss_feed(feed, True)
            return ShowRssLog(feed)
        if 'dummy' in kwargs:
            raise Raiser(self.__root, kwargs['dummy'])
        else:
            raise Raiser(self.__root, '')


    @cherrypy.expose
    def rsslog(self, *args, **kwargs):
        if 'feed' in kwargs:
            return ShowRssLog(kwargs['feed'])
        if 'dummy' in kwargs:
            raise Raiser(self.__root, kwargs['dummy'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def enable_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            try:
                feed = kwargs['feed']
                sabnzbd.CFG['rss'][feed]['enable'] = 1
                save_configfile(sabnzbd.CFG)
                sabnzbd.run_rss_feed(feed, True)
            except:
                pass
        if 'dummy' in kwargs:
            raise Raiser(self.__root, kwargs['dummy'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def disable_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            try:
                sabnzbd.CFG['rss'][kwargs['feed']]['enable'] = 0
                save_configfile(sabnzbd.CFG)
            except:
                pass
        if 'dummy' in kwargs:
            raise Raiser(self.__root, kwargs['dummy'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def rss_download(self, feed=None, id=None, cat=None, pp=None, script=None, dummy=None):
        if id and id.isdigit():
            sabnzbd.add_msgid(id, pp, script, cat)
        elif id:
            sabnzbd.add_url(id, pp, script, cat)
        sabnzbd.rss_flag_downloaded(feed, id)
        raise Raiser(self.__root, dummy)


#------------------------------------------------------------------------------

class ConfigScheduling(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['schedlines'] = sabnzbd.CFG['misc']['schedlines']

        template = Template(file=os.path.join(self.__web_dir, 'config_scheduling.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def addSchedule(self, minute = None, hour = None, dayofweek = None,
                    action = None, arguments = None, dummy = None):
        if minute and hour  and dayofweek and action:
            sabnzbd.CFG['misc']['schedlines'].append('%s %s %s %s %s' %
                                              (minute, hour, dayofweek, action, arguments))
        return saveAndRestart(self.__root, dummy, evalSched=True)

    @cherrypy.expose
    def delSchedule(self, line = None, dummy = None):
        if line and line in sabnzbd.CFG['misc']['schedlines']:
            sabnzbd.CFG['misc']['schedlines'].remove(line)
        return saveAndRestart(self.__root, dummy, evalSched=True)

#------------------------------------------------------------------------------

class ConfigNewzbin(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__bookmarks = []

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['username_newzbin'] = sabnzbd.CFG['newzbin']['username']
        config['password_newzbin'] = '*' * len(decodePassword(sabnzbd.CFG['newzbin']['password'], 'password_newzbin'))
        config['create_category_folders'] = IntConv(sabnzbd.CFG['newzbin']['create_category_folders'])
        config['newzbin_bookmarks'] = IntConv(sabnzbd.CFG['newzbin']['bookmarks'])
        config['newzbin_unbookmark'] = IntConv(sabnzbd.CFG['newzbin']['unbookmark'])
        config['bookmark_rate'] = sabnzbd.BOOKMARK_RATE

        config['bookmarks_list'] = self.__bookmarks

        template = Template(file=os.path.join(self.__web_dir, 'config_newzbin.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveNewzbin(self, username_newzbin = None, password_newzbin = None,
                    create_category_folders = None, newzbin_bookmarks = None,
                    newzbin_unbookmark = None, bookmark_rate = None, dummy = None):

        sabnzbd.CFG['newzbin']['username'] = username_newzbin
        if (not password_newzbin) or (password_newzbin and password_newzbin.strip('*')):
            sabnzbd.CFG['newzbin']['password'] = encodePassword(password_newzbin)
        sabnzbd.CFG['newzbin']['create_category_folders'] = create_category_folders
        sabnzbd.CFG['newzbin']['bookmarks'] = newzbin_bookmarks
        sabnzbd.CFG['newzbin']['unbookmark'] = newzbin_unbookmark
        sabnzbd.CFG['newzbin']['bookmark_rate'] = bookmark_rate

        return saveAndRestart(self.__root, dummy)

    @cherrypy.expose
    def getBookmarks(self, dummy = None):
        sabnzbd.getBookmarksNow()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def showBookmarks(self, dummy = None):
        self.__bookmarks = sabnzbd.getBookmarksList()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def hideBookmarks(self, dummy = None):
        self.__bookmarks = []
        raise Raiser(self.__root, dummy)

#------------------------------------------------------------------------------

class ConfigCats(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
            config['newzbinDetails'] = True

        config['script_list'] = ListScripts()
        config['script_list'].insert(0, 'Default')

        config['have_cats'] = len(sabnzbd.CFG['categories']) > 0
        config['defdir'] = sabnzbd.COMPLETE_DIR

        empty = { 'name':'', 'pp':'0', 'script':'', 'dir':'', 'newzbin':'' }
        slotinfo = []
        slotinfo.append(empty)
        for cat in sabnzbd.CFG['categories']:
            slot = {}
            slot['name'] = cat
            try:
                slot['pp'] = str(sabnzbd.CFG['categories'][cat]['pp'])
            except:
                slot['pp'] = ''
            try:
                slot['script'] = sabnzbd.CFG['categories'][cat]['script']
            except:
                slot['script'] = 'Default'
            if slot['script'] == '': slot['script'] = 'Default'
            try:
                slot['dir'] = sabnzbd.CFG['categories'][cat]['dir']
            except:
                slot['dir'] = ''
            try:
                slot['newzbin'] = List2String(sabnzbd.CFG['categories'][cat]['newzbin'])
            except:
                slot['newzbin'] = ''
            slotinfo.append(slot)
        config['slotinfo'] = slotinfo

        template = Template(file=os.path.join(self.__web_dir, 'config_cat.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def delete(self, name = None, dummy = None):
        if name:
            try:
                del sabnzbd.CFG['categories'][name]
            except:
                pass
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def save(self, name=None, newname=None, pp=None, script=None, dir=None, newzbin=None, dummy=None):
        if newname:
            if name:
                try:
                    del sabnzbd.CFG['categories'][name]
                except:
                    pass
            name = newname.lower()
            sabnzbd.CFG['categories'][name] = {}

            if pp and pp.isdigit():
                try:
                    sabnzbd.CFG['categories'][name]['pp'] = str(pp)
                except:
                    pass
            if script != None:
                if not script or script=='Default': script = ''
                try:
                    sabnzbd.CFG['categories'][name]['script'] = script
                except:
                    pass
            if dir:
                try:
                    sabnzbd.CFG['categories'][name]['dir'] = dir
                except:
                    pass
            if newzbin:
                try:
                    sabnzbd.CFG['categories'][name]['newzbin'] = listquote.simplelist(newzbin)
                except:
                    pass
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def init_newzbin(self, dummy = None):
        InitCats()
        save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, dummy)


#------------------------------------------------------------------------------

class ConnectionInfo(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__lastmail = None

    @cherrypy.expose
    def index(self, dummy = None):
        header, pnfo_list, bytespersec = build_header(self.__prim)

        header['logfile'] = sabnzbd.LOGFILE
        header['weblogfile'] = sabnzbd.WEBLOGFILE
        header['loglevel'] = str(sabnzbd.LOGLEVEL)

        header['lastmail'] = self.__lastmail

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

                    art_name = escape(article.article)
                    #filename field is not always present
                    try:
                        nzf_name = escape(nzf.get_filename())
                    except: #attribute error
                        nzf_name = escape(nzf.get_subject())
                    nzo_name = escape(nzo.get_filename())

                busy.append((nw.thrdnum, art_name, nzf_name, nzo_name))

                if nw.connected:
                    connected += 1

            busy.sort()
            header['servers'].append((server.host, server.port, connected, busy, server.ssl))

        wlist = []
        for w in sabnzbd.GUIHANDLER.content():
            wlist.append(escape(w))
        header['warnings'] = wlist

        template = Template(file=os.path.join(self.__web_dir, 'connection_info.tmpl'),
                            searchList=[header],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def disconnect(self, dummy = None):
        sabnzbd.disconnect()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def testmail(self, dummy = None):
        logging.info("Sending testmail")
        self.__lastmail= email_send("SABnzbd testing email connection", "All is OK")
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def showlog(self):
        try:
            sabnzbd.LOGHANDLER.flush()
        except:
            pass
        return cherrypy.lib.cptools.serveFile(sabnzbd.LOGFILE, disposition='attachment')

    @cherrypy.expose
    def showweb(self):
        if sabnzbd.WEBLOGFILE:
            return cherrypy.lib.cptools.serveFile(sabnzbd.WEBLOGFILE, disposition='attachment')
        else:
            return "Web logging is off!"

    @cherrypy.expose
    def clearwarnings(self, dummy = None):
        sabnzbd.GUIHANDLER.clear()
        raise Raiser(self.__root, dummy)

    @cherrypy.expose
    def change_loglevel(self, loglevel=None, dummy = None):
        loglevel = IntConv(loglevel)
        if loglevel >= 0 and loglevel < 3:
            sabnzbd.LOGLEVEL = loglevel
            sabnzbd.CFG['logging']['log_level'] = loglevel
            save_configfile(sabnzbd.CFG)

        raise Raiser(self.__root, dummy)


def saveAndRestart(redirect_root, dummy, evalSched=False):
    save_configfile(sabnzbd.CFG)
    sabnzbd.halt()
    init_ok = sabnzbd.initialize(evalSched=evalSched)
    if init_ok:
        sabnzbd.start()
        raise Raiser(redirect_root, dummy)
    else:
        return "SABnzbd restart failed! See logfile(s)."

def Protected():
    return badParameterResponse("Configuration is locked")

def badParameterResponse(msg):
    """Return a html page with error message and a 'back' button
    """
    return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
    <title>SABnzbd+ %s - Error</title>
</head>
<body>
    <h3>Incorrect parameter</h3>
    %s
    <br><br>
    <FORM><INPUT TYPE="BUTTON" VALUE="Go Back" ONCLICK="history.go(-1)"></FORM>
</body>
</html>
''' % (sabnzbd.__version__, msg)

def ShowFile(name, path):
    """Return a html page listing a file and a 'back' button
    """
    try:
        f = open(path, "r")
        msg = f.read()
        f.close()
    except:
        msg = "FILE NOT FOUND\n"

    return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
    <title>%s</title>
</head>
<body>
    <FORM><INPUT TYPE="BUTTON" VALUE="Go Back" ONCLICK="history.go(-1)"></FORM>
    <h3>%s</h3>
    <code><pre>
    %s
    </pre></code><br/><br/>
</body>
</html>
''' % (name, name, escape(msg))


def ShowRssLog(feed):
    """Return a html page listing an RSS log and a 'back' button
    """
    jobs = sabnzbd.show_rss_result(feed)
    qfeed = escape(feed.replace('/','%2F').replace('?', '%3F'))

    doneStr = ""
    for x in jobs:
        job = jobs[x]
        if job[0] == 'D':
            doneStr += '%s<br/>' % encode_for_xml(escape(job[1]))
    goodStr = ""
    for x in jobs:
        job = jobs[x]
        if job[0] == 'G':
            goodStr += '%s<br/>' % encode_for_xml(escape(job[1]))
    badStr = ""
    for x in jobs:
        job = jobs[x]
        if job[0] == 'B':
            name = escape(job[2]).replace('/','%2F').replace('?', '%3F')
            if job[3]:
                cat = '&cat=' + escape(job[3])
            else:
                cat = ''
            if job[4]:
                pp = '&pp=' + escape(job[4])
            else:
                pp = ''
            if job[5]:
                script = '&script=' + escape(job[5])
            else:
                script = ''
            badStr += '<a href="rss_download?feed=%s&id=%s%s%s">Download</a>&nbsp;&nbsp;&nbsp;%s<br/>' % \
                (qfeed, name, cat, pp, encode_for_xml(escape(job[1])))

    return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
    <title>%s</title>
</head>
<body>
    <form>
    <input type="submit" onclick="this.form.action='.'; this.form.submit(); return false;" value="Back"/>
    </form>
    <h3>%s</h3>
    <b>Matched</b><br/>
    %s
    <br/>
    <b>Not matched</b><br/>
    %s
    <br/>
    <b>Downloaded</b><br/>
    %s
    <br/>
</body>
</html>
''' % (escape(feed), escape(feed), goodStr, badStr, doneStr)


def build_header(prim):
    try:
        uptime = calc_age(sabnzbd.START)
    except:
        uptime = "-"

    if prim:
        color = sabnzbd.WEB_COLOR
    else:
        color = sabnzbd.WEB_COLOR2
    if color:
         color = color + '.css'
    else:
        color = ''

    header = { 'version':sabnzbd.__version__, 'paused':sabnzbd.paused(),
               'uptime':uptime, 'color_scheme':color }

    header['helpuri'] = 'http://sabnzbd.wikidot.com'
    header['diskspace1'] = "%.2f" % diskfree(sabnzbd.DOWNLOAD_DIR)
    header['diskspace2'] = "%.2f" % diskfree(sabnzbd.COMPLETE_DIR)
    header['diskspacetotal1'] = "%.2f" % disktotal(sabnzbd.DOWNLOAD_DIR)
    header['diskspacetotal2'] = "%.2f" % disktotal(sabnzbd.COMPLETE_DIR)

    header['finishaction'] = sabnzbd.QUEUECOMPLETE
    header['nt'] = os.name == 'nt'
    if prim:
        header['web_name'] = os.path.basename(sabnzbd.CFG['misc']['web_dir'])
    else:
        header['web_name'] = os.path.basename(sabnzbd.CFG['misc']['web_dir2'])

    bytespersec = sabnzbd.bps()
    qnfo = sabnzbd.queue_info()

    bytesleft = qnfo[QNFO_BYTES_LEFT_FIELD]
    bytes = qnfo[QNFO_BYTES_FIELD]

    header['kbpersec'] = "%.2f" % (bytespersec / KIBI)
    header['mbleft']   = "%.2f" % (bytesleft / MEBI)
    header['mb']       = "%.2f" % (bytes / MEBI)

    anfo  = sabnzbd.cache_info()

    header['cache_art'] = str(anfo[ANFO_ARTICLE_SUM_FIELD])
    header['cache_size'] = str(anfo[ANFO_CACHE_SIZE_FIELD])
    header['cache_limit'] = str(anfo[ANFO_CACHE_LIMIT_FIELD])

    header['nzb_quota'] = ''

    if sabnzbd.NEW_VERSION:
        header['new_release'], header['new_rel_url'] = sabnzbd.NEW_VERSION.split(';')
    else:
        header['new_release'] = ''
        header['new_rel_url'] = ''

    header['timeleft'] = calc_timeleft(bytesleft, bytespersec)

    try:
        datestart = datetime.datetime.now() + datetime.timedelta(seconds=bytesleft / bytespersec)
        #new eta format: 16:00 Fri 07 Feb
        header['eta'] = '%s' % datestart.strftime('%H:%M %a %d %b')
    except:
        datestart = datetime.datetime.now()
        header['eta'] = 'unknown'

    return (header, qnfo[QNFO_PNFO_LIST_FIELD], bytespersec)

def calc_timeleft(bytesleft, bps):
    """
    Calculate the time left in the format HH:MM:SS
    """
    try:
        totalseconds = int(bytesleft / bps)
        minutes, seconds = divmod(totalseconds, 60)
        hours, minutes = divmod(minutes, 60)
        if minutes <10:
            minutes = '0%s' % minutes
        if seconds <10:
            seconds = '0%s' % seconds
        return '%s:%s:%s' % (hours, minutes, seconds)
    except:
        return '0:00:00'

def calc_age(date):
    """
    Calculate the age difference between now and date.
    Value is returned as either days, hours, or minutes.
    """
    try:
        now = datetime.datetime.now()
        #age = str(now - date).split(".")[0] #old calc_age

        #time difference
        dage = now-date
        seconds = dage.seconds
        #only one value should be returned
        #if it is less than 1 day then it returns in hours, unless it is less than one hour where it returns in minutes
        if dage.days:
            age = '%sd' % (dage.days)
        elif seconds/3600:
            age = '%sh' % (seconds/3600)
        else:
            age = '%sm' % (seconds/60)
    except:
        age = "-"

    return age

#------------------------------------------------------------------------------

class ConfigEmail(ProtectedClass):
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, dummy = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['email_server'] = sabnzbd.CFG['misc']['email_server']
        config['email_to'] = sabnzbd.CFG['misc']['email_to']
        config['email_from'] = sabnzbd.CFG['misc']['email_from']
        config['email_account'] = sabnzbd.CFG['misc']['email_account']
        config['email_pwd'] = '*' * len(decodePassword(sabnzbd.CFG['misc']['email_pwd'], 'email'))
        config['email_endjob'] = IntConv(sabnzbd.CFG['misc']['email_endjob'])
        config['email_full'] = IntConv(sabnzbd.CFG['misc']['email_full'])

        template = Template(file=os.path.join(self.__web_dir, 'config_email.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveEmail(self, email_server = None, email_to = None, email_from = None,
                  email_account = None, email_pwd = None,
                  email_endjob = None, email_full = None, dummy = None):

        VAL = re.compile('[^@ ]+@[^.@ ]+\.[^.@ ]')

        if VAL.match(email_to):
            sabnzbd.CFG['misc']['email_to'] = email_to
        else:
            return badParameterResponse('Invalid email address "%s"' % email_to)
        if VAL.match(email_from):
            sabnzbd.CFG['misc']['email_from'] = email_from
        else:
            return badParameterResponse('Invalid email address "%s"' % email_from)

        sabnzbd.CFG['misc']['email_server'] = email_server
        sabnzbd.CFG['misc']['email_account'] = email_account
        if (not email_pwd) or (email_pwd and email_pwd.strip('*')):
            sabnzbd.CFG['misc']['email_pwd'] = encodePassword(email_pwd)
        sabnzbd.CFG['misc']['email_endjob'] = email_endjob
        sabnzbd.CFG['misc']['email_full'] = email_full

        return saveAndRestart(self.__root, dummy)


def std_time(when):
    # Fri, 16 Nov 2007 16:42:01 GMT +0100
    item  = time.strftime('%a, %d %b %Y %H:%M:%S', time.localtime(when))
    item += " GMT %+05d" % (-time.timezone/36)
    return item


def rss_history():

    rss = RSS()
    rss.channel.title = "SABnzbd History"
    rss.channel.description = "Overview of completed downloads"
    rss.channel.link = "http://sourceforge.net/projects/sabnzbdplus/"
    rss.channel.language = "en"

    if sabnzbd.USERNAME_NEWZBIN and sabnzbd.PASSWORD_NEWZBIN:
        newzbin = True

    history_items, total_bytes, bytes_beginning = sabnzbd.history_info()

    youngest = None
    while history_items:
        added = max(history_items.keys())

        history_item_list = history_items.pop(added)

        for history_item in history_item_list:
            item = Item()
            filename, unpackstrht, loaded, bytes, nzo, status = history_item
            if added > youngest:
                youngest = added
            item.pubDate = std_time(added)
            item.title, msgid = SplitFileName(filename)
            if (msgid):
                item.link    = "https://v3.newzbin.com/browse/post/%s/" % msgid
            else:
                item.link    = "http://%s:%s/sabnzbd/history" % ( \
                                sabnzbd.CFG['misc']['host'], sabnzbd.CFG['misc']['port'] )

            if loaded:
                stageLine = "Post-processing active.<br>"
            else:
                stageLine = ""

            stageLine += "[%s] Finished at %s and downloaded %sB" % ( \
                         status,
                         time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(added)), \
                         to_units(bytes) )

            stage_keys = unpackstrht.keys()
            stage_keys.sort()
            for stage in stage_keys:
                stageLine += "<tr><dt>Stage %s</dt>" % STAGENAMES[stage]
                actions = []
                for action in unpackstrht[stage]:
                    actionLine = "<dd>%s %s</dd>" % (action, unpackstrht[stage][action])
                    actions.append(actionLine)
                actions.sort()
                actions.reverse()
                for act in actions:
                    stageLine += act
                stageLine += "</tr>"
            item.description = stageLine
            rss.addItem(item)

    rss.channel.lastBuildDate = std_time(youngest)
    rss.channel.pubDate = std_time(time.time())

    return rss.write()


def rss_warnings():
    """ Return an RSS feed with last warnings/errors
    """
    rss = RSS()
    rss.channel.title = "SABnzbd Warnings"
    rss.channel.description = "Overview of warnings/errors"
    rss.channel.link = "http://sourceforge.net/projects/sabnzbdplus/"
    rss.channel.language = "en"

    for warn in sabnzbd.GUIHANDLER.content():
        item = Item()
        item.title = warn
        rss.addItem(item)

    rss.channel.lastBuildDate = std_time(time.time())
    rss.channel.pubDate = rss.channel.lastBuildDate
    return rss.write()


def json_qstatus():
    """Build up the queue status as a nested object and output as a JSON object
    """

    qnfo = sabnzbd.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    for pnfo in pnfo_list:
        filename, msgid = SplitFileName(pnfo[PNFO_FILENAME_FIELD])
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append( { "id" : nzo_id, "mb":bytes, "mbleft":bytesleft, "filename":filename, "msgid":msgid } )

    status = {
               "paused" : sabnzbd.paused(),
               "kbpersec" : sabnzbd.bps() / KIBI,
               "mbleft" : qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
               "mb" : qnfo[QNFO_BYTES_FIELD] / MEBI,
               "noofslots" : len(pnfo_list),
               "diskspace1" : diskfree(sabnzbd.DOWNLOAD_DIR),
               "diskspace2" : diskfree(sabnzbd.COMPLETE_DIR),
               "timeleft" : calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], sabnzbd.bps()),
               "jobs" : jobs
             }
    status_str= JsonWriter().write(status)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str

def xml_qstatus():
    """Build up the queue status as a nested object and output as a XML string
    """

    qnfo = sabnzbd.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    for pnfo in pnfo_list:
        filename, msgid = SplitFileName(pnfo[PNFO_FILENAME_FIELD])
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        name = encode_for_xml(escape(filename), 'UTF-8')
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append( { "id" : nzo_id, "mb":bytes, "mbleft":bytesleft, "filename":name, "msgid":msgid } )

    status = {
               "paused" : sabnzbd.paused(),
               "kbpersec" : sabnzbd.bps() / KIBI,
               "mbleft" : qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
               "mb" : qnfo[QNFO_BYTES_FIELD] / MEBI,
               "noofslots" : len(pnfo_list),
               "diskspace1" : diskfree(sabnzbd.DOWNLOAD_DIR),
               "diskspace2" : diskfree(sabnzbd.COMPLETE_DIR),
               "timeleft" : calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], sabnzbd.bps()),
               "jobs" : jobs
             }

    status_str= '<?xml version="1.0" encoding="UTF-8" ?> \n\
                <queue> \n\
                <paused>%(paused)s</paused> \n\
                <kbpersec>%(kbpersec)s</kbpersec> \n\
                <mbleft>%(mbleft)s</mbleft> \n\
                <mb>%(mb)s</mb> \n\
                <noofslots>%(noofslots)s</noofslots> \n\
                <diskspace1>%(diskspace1)s</diskspace1> \n\
                <diskspace2>%(diskspace2)s</diskspace2> \n\
                <timeleft>%(timeleft)s</timeleft> \n' % status

    status_str += '<jobs>\n'
    for job in jobs:
        status_str += '<job> \n\
                    <id>%(id)s</id> \n\
                    <msgid>%(msgid)s</msgid> \n\
                    <filename>%(filename)s</filename> \n\
                    <mbleft>%(mbleft)s</mbleft> \n\
                    <mb>%(mb)s</mb> \n\
                    </job>\n' % job

    status_str += '</jobs>\n'


    status_str += '</queue>'
    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str



def json_list(section, lst):
    """Output a simple list as a JSON object
    """

    obj = { section : lst }
    text = JsonWriter().write(obj)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return text


def xml_list(section, keyw, lst):
    """Output a simple list as an XML object
    """
    text= '<?xml version="1.0" encoding="UTF-8" ?> \n<%s>\n' % section

    for cat in lst:
        text += '<%s>%s</%s>\n' % (keyw, escape(cat), keyw)

    text += '</%s>' % section

    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return text
