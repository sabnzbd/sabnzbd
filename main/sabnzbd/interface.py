#!/usr/bin/python -OO
#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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
import urllib
from xml.sax.saxutils import escape

from sabnzbd.utils.rsslib import RSS, Item, Namespace
from sabnzbd.utils.json import JsonWriter
import sabnzbd
import sabnzbd.rss
import sabnzbd.scheduler as scheduler

from sabnzbd.utils import listquote
from sabnzbd.utils.configobj import ConfigObj
from Cheetah.Template import Template
import sabnzbd.email as email
from sabnzbd.misc import real_path, create_real_path, save_configfile, \
     to_units, from_units, SameFile, \
     decodePassword, encodePassword
from sabnzbd.nzbstuff import SplitFileName
from sabnzbd.newswrapper import GetServerParms
import sabnzbd.newzbin as newzbin
import sabnzbd.urlgrabber as urlgrabber
from sabnzbd.codecs import TRANS, xml_name
import sabnzbd.config as config
import sabnzbd.newsunpack as newsunpack
from sabnzbd.database import HistoryDB, build_history_info, unpack_history_info

from sabnzbd.constants import *

RE_URL = re.compile('(.+)/sabnzbd(/m)?/rss', re.I)

#------------------------------------------------------------------------------

#PROVIDER = DictAuthProvider({})

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
            logging.warning('Too little diskspace forcing PAUSE')
            # Pause downloader, but don't save, since the disk is almost full!
            sabnzbd.pause_downloader(save=False)
            email.diskfull()


def check_timeout(timeout):
    """ Check sensible ranges for server timeout """
    timeout = Strip(timeout)
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


def ListScripts(default=False):
    """ Return a list of script names """
    lst = []
    dd = sabnzbd.SCRIPT_DIR
    
    if dd and os.access(dd, os.R_OK):
        if default:
            lst = ['Default', 'None']
        else:
            lst = ['None']
        for script in glob.glob(dd + '/*'):
            if os.path.isfile(script):
                sc= os.path.basename(script)
                if sc != "_svn" and sc != ".svn":
                    lst.append(sc)
    return lst


def ListCats(default=False):
    """ Return list of categories """
    content = False
    if default:
        lst = ['Default', 'None']
    else:
        lst = ['None']

    for cat in sorted(config.get_categories().keys()):
        content = True
        lst.append(cat)
    if content:
        return lst
    else:
        return []

def ConvertSpecials(p):
    """ Convert None to 'None' and 'Default' to ''
    """
    if p == None:
        p = 'None'
    elif p.lower() == 'default':
        p = ''
    return p


def Raiser(root, *args, **kwargs):
    root = '%s?%s' % (root, urllib.urlencode(kwargs))
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

def Strip(txt):
    """ Return stripped string, can handle None """
    try:
        return txt.strip()
    except:
        return None

def get_arg(args, kw):
    """ Get a value from a dictionary, None if not available """
    try:
        return args[kw]
    except KeyError:
        return None


#------------------------------------------------------------------------------
#class DummyFilter(MultiAuthFilter):
#    def beforeMain(self):
#        pass
#
#    def beforeFinalize(self):
#        if isinstance(cherrypy.response.body, SecureResource):
#            rsrc = cherrypy.response.body
#            if 'ma_username' in rsrc.callable_kwargs: del rsrc.callable_kwargs['ma_username']
#            if 'ma_password' in rsrc.callable_kwargs: del rsrc.callable_kwargs['ma_password']
#            cherrypy.response.body = rsrc.callable(rsrc.instance,
#                                                   *rsrc.callable_args,
#                                                   **rsrc.callable_kwargs)

#------------------------------------------------------------------------------
def get_users():
    global USERNAME, PASSWORD
    users = {}
    users[USERNAME] = PASSWORD
    return users

def encrypt_pwd(pwd):
    return pwd

def connect_db(thread_index): 
    # Create a connection and store it in the current thread 
    db_history = os.path.join(sabnzbd.DIR_LCLDATA, DB_HISTORY_NAME)
    cherrypy.thread_data.history_db = HistoryDB(db_history)
    
cherrypy.engine.subscribe('start_thread', connect_db)

class LoginPage:
    def __init__(self, web_dir, root, web_dir2=None, root2=None):
        self.sabnzbd = MainPage(web_dir, root, prim=True)
        self.root = root
        if web_dir2:
            self.sabnzbd.m = MainPage(web_dir2, root2, prim=False)
        else:
            self.sabnzbd.m = NoPage()
        pass

    @cherrypy.expose
    def index(self, _dc = None):
        return ""

    def change_web_dir(self, web_dir):
        self.sabnzbd = MainPage(web_dir, self.root, prim=True)
        
    def change_web_dir2(self, web_dir):
        self.sabnzbd.m = MainPage(web_dir, self.root, prim=False)


#------------------------------------------------------------------------------
class NoPage:
    def __init__(self):
        pass

    @cherrypy.expose
    def index(self, _dc = None):
        return badParameterResponse('Error: No secondary interface defined.')


#------------------------------------------------------------------------------
class MainPage:
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
    def index(self, _dc = None):
        info, pnfo_list, bytespersec = build_header(self.__prim)

        if newzbin.USERNAME_NEWZBIN.get() and newzbin.PASSWORD_NEWZBIN.get():
            info['newzbinDetails'] = True

        info['script_list'] = ListScripts(default=True)
        info['script'] = sabnzbd.misc.DIRSCAN_SCRIPT.get()

        info['cat'] = 'Default'
        info['cat_list'] = ListCats(True)

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
    def addID(self, id = None, pp=None, script=None, cat=None, redirect = None, priority=NORMAL_PRIORITY):
        RE_NEWZBIN_URL = re.compile(r'/browse/post/(\d+)')
        newzbin_url = RE_NEWZBIN_URL.search(id.lower())
        
        id = Strip(id)
        if id and (id.isdigit() or len(id)==5):
            sabnzbd.add_msgid(id, pp, script, cat, priority)
        elif newzbin_url:
            sabnzbd.add_msgid(Strip(newzbin_url.group(1)), pp, script, cat, priority)
        elif id:
            sabnzbd.add_url(id, pp, script, cat, priority)
        if not redirect:
            redirect = self.__root
        raise cherrypy.HTTPRedirect(redirect)


    @cherrypy.expose
    def addURL(self, url = None, pp=None, script=None, cat=None, redirect = None, priority=NORMAL_PRIORITY):
        url = Strip(url)
        if url and (url.isdigit() or len(url)==5):
            sabnzbd.add_msgid(url, pp, script, cat, priority)
        elif url:
            sabnzbd.add_url(url, pp, script, cat, priority)
        if not redirect:
            redirect = self.__root
        raise cherrypy.HTTPRedirect(redirect)


    @cherrypy.expose
    def addFile(self, nzbfile, pp=None, script=None, cat=None, _dc = None, priority=NORMAL_PRIORITY):
        if nzbfile.filename and nzbfile.value:
            sabnzbd.add_nzbfile(nzbfile, pp, script, cat, priority)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def shutdown(self, _dc=None):
        yield "Initiating shutdown..."
        sabnzbd.halt()
        yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True

    @cherrypy.expose
    def pause(self, _dc = None):
        sabnzbd.pause_downloader()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def resume(self, _dc = None):
        sabnzbd.resume_downloader()
        raise Raiser(self.__root, _dc=_dc)

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
    def rss(self, mode='history', limit=50):
        url = cherrypy.url()
        if mode == 'history':
            return rss_history(url, limit=limit)
        elif mode == 'warnings':
            return rss_warnings()

    @cherrypy.expose
    def tapi(self, **kwargs):
        """Handler for API over http, for template use
        """
        return self.api_handler(kwargs)

    @cherrypy.expose
    def api(self, **kwargs):
        """Handler for API over http, with explicit authentication parameters
        """
        if USERNAME and PASSWORD:
            ma_username = get_arg(kwargs, 'ma_username')
            ma_password = get_arg(kwargs, 'ma_password')
            if not (ma_password == PASSWORD and ma_username == USERNAME):
                return "Missing authentication"

        return self.api_handler(kwargs)


    def api_handler(self, kwargs):
        """ Actual API handler, not exposed to Web-ui
        """
        mode = get_arg(kwargs, 'mode')
        output = get_arg(kwargs, 'output')

        if mode == 'set_config':
            res = config.set_config(kwargs)
            if output == 'json':
                return json_result(res, None)
            elif output == 'xml':                   
                return xml_result(res, None)
            else:
                return 'not implemented\n'

        if mode == 'get_config':
            res, data = config.get_dconfig(kwargs)
            if output == 'json':
                return json_result(res, data)
            elif output == 'xml':                   
                return xml_result(res, data)
            else:
                return 'not implemented\n'

        if mode == 'qstatus':
            if output == 'json':
                return json_qstatus()
            elif output == 'xml':                   
                return xml_qstatus()
            else:
                return 'not implemented\n'
            
        if mode == 'queue':
            name = get_arg(kwargs, 'name')
            sort = get_arg(kwargs, 'sort')
            dir = get_arg(kwargs, 'dir')
            value = get_arg(kwargs, 'value')
            value2 = get_arg(kwargs, 'value2')
            start = get_arg(kwargs, 'start')
            limit = get_arg(kwargs, 'limit')

            if output == 'xml':
                if sort and sort != 'index':
                    reverse=False
                    if dir.lower() == 'desc':
                        reverse=True
                    sabnzbd.sort_queue(sort,reverse)
                return queueStatus(start,limit)
            elif output == 'json':
                if sort and sort != 'index':
                    reverse=False
                    if dir.lower() == 'desc':
                        reverse=True
                    sabnzbd.sort_queue(sort,reverse)
                return queueStatusJson(start,limit)
            elif output == 'rss':
                return rss_qstatus()
            elif name == 'delete':
                if value.lower()=='all':
                    sabnzbd.remove_all_nzo()
                    return 'ok\n'
                elif value:
                    items = value.split(',')
                    sabnzbd.remove_multiple_nzos(items, False)
                    return 'ok\n'
                else:
                    return 'error\n'
            elif name == 'delete_nzf':
                # Value = nzo_id Value2 = nzf_id
                if value and value2:
                    sabnzbd.remove_nzf(value, value2)
                    return 'ok\n'
                else:
                    return 'error: specify the nzo id\'s in the value param and nzf_id in value2 param\n'
            elif name == 'rename':
                if value and value2:
                    sabnzbd.rename_nzo(value, value2)
                else:
                    return 'error\n'
            elif name == 'change_complete_action': 
                # http://localhost:8080/sabnzbd/api?mode=queue&name=change_complete_action&value=hibernate_pc
                sabnzbd.change_queue_complete_action(value)
                return 'ok\n'
            elif name == 'purge':
                sabnzbd.remove_all_nzo()
                return 'ok\n'
            elif name == 'pause':
                if value:
                    items = value.split(',')
                    sabnzbd.pause_multiple_nzo(items)
            elif name == 'resume':
                if value:
                    items = value.split(',')
                    sabnzbd.resume_multiple_nzo(items)
            elif name == 'priority':
                if value and value2:
                    try:
                        priority = int(value2)
                        items = value.split(',')
                        if len(items) > 1:
                            sabnzbd.set_priority_multiple(items, priority)
                        else:
                            sabnzbd.set_priority(value, priority)
                    except:
                        return 'error: correct usage: &value=NZO_ID&value2=PRIORITY_VALUE'
                else:
                    return 'error: correct usage: &value=NZO_ID&value2=PRIORITY_VALUE'
            else:
                return 'not implemented\n'

        name = get_arg(kwargs, 'name')
        pp = get_arg(kwargs, 'pp')
        script = get_arg(kwargs, 'script')
        cat = get_arg(kwargs, 'cat')
        priority = get_arg(kwargs, 'priority')
        value = get_arg(kwargs, 'value')
        value2 = get_arg(kwargs, 'value2')
        start = get_arg(kwargs, 'start')
        limit = get_arg(kwargs, 'limit')

        if mode == 'addfile':
            if name.filename and name.value:
                sabnzbd.add_nzbfile(name, pp, script, cat, priority)
                return 'ok\n'
            else:
                return 'error\n'
            
        if mode == 'switch':
            if value and value2:
                sabnzbd.switch(value, value2)
                return 'ok\n'
            else:
                return 'error\n'
            
                
        if mode == 'change_cat':
            if value and value2:
                nzo_id = value
                cat = value2
                if cat == 'None':
                    cat = None
                sabnzbd.change_cat(nzo_id, cat)
                item = config.get_config('categories', cat)
                if item:
                    script = item.script.get()
                    pp = item.pp.get()
                else:
                    script = sabnzbd.misc.DIRSCAN_SCRIPT.get()
                    pp = sabnzbd.misc.DIRSCAN_PP.get()
    
                sabnzbd.change_script(nzo_id, script)
                sabnzbd.change_opts(nzo_id, pp)
                return 'ok\n'
            else:
                return 'error\n'
            
        if mode == 'change_script':
            if value and value2:
                nzo_id = value
                script = value2
                if script == 'None':
                    script = None
                sabnzbd.change_script(nzo_id, script)
                return 'ok\n'
            else:
                return 'error\n'
            
        if mode == 'change_opts':
            if value and value2 and value2.isdigit():
                sabnzbd.change_opts(value, int(value2))
            
        if mode == 'fullstatus':
            if output == 'xml':
                return xml_full()
            else:
                return 'not implemented\n'
            
        if mode == 'history':
            if output == 'xml':
                return xml_history(start, limit)
            elif output == 'json':
                return json_history(start, limit)
            elif name == 'delete':
                if value.lower()=='all':
                    history_db = cherrypy.thread_data.history_db
                    history_db.remove_history()
                    return 'ok\n'
                elif value:
                    jobs = value.split(',')
                    history_db = cherrypy.thread_data.history_db
                    history_db.remove_history(jobs)
                    return 'ok\n'
                else:
                    return 'error\n'
            else:
                return 'not implemented\n'

        if mode == 'get_files':
            if value:
                if output == 'xml':
                    return xml_files(value)
                elif output == 'json':
                    return json_files(value)
                else:
                    return 'not implemented\n'
            
        if mode == 'addurl':
            if name:
                sabnzbd.add_url(name, pp, script, cat, priority)
                return 'ok\n'
            else:
                return 'error\n'

        if mode == 'addid':
            RE_NEWZBIN_URL = re.compile(r'/browse/post/(\d+)')
            newzbin_url = RE_NEWZBIN_URL.search(name.lower())
            
            if name: name = name.strip()
            if name and (name.isdigit() or len(name)==5):
                sabnzbd.add_msgid(name, pp, script, cat, priority)
                return 'ok\n'
            elif newzbin_url:
                sabnzbd.add_msgid(newzbin_url.group(1), pp, script, cat, priority)
                return 'ok\n'
            elif name:
                sabnzbd.add_url(name, pp, script, cat, priority)
                return 'ok\n'
            else:
                return 'error\n'
            
        if mode == 'pause':
            sabnzbd.pause_downloader()
            return 'ok\n'

        if mode == 'resume':
            sabnzbd.resume_downloader()
            return 'ok\n'

        if mode == 'shutdown':
            sabnzbd.halt()
            cherrypy.engine.exit()
            sabnzbd.SABSTOP = True

        if mode == 'warnings':
            if output == 'json':
                return json_list("warnings", sabnzbd.GUIHANDLER.content())
            elif output == 'xml':
                return xml_list("warnings", "warning", sabnzbd.GUIHANDLER.content())
            else:
                return 'not implemented\n'
            
        if mode == 'config':
            if name == 'speedlimit' or name == 'set_speedlimit': # http://localhost:8080/sabnzbd/api?mode=config&name=speedlimit&value=400
                if not value: value = '0'
                if value.isdigit():
                    try: value = int(value)
                    except: return 'error: Please submit a value\n'
                    sabnzbd.CFG['misc']['bandwith_limit'] = value
                    sabnzbd.BANDWITH_LIMIT = value
                    sabnzbd.limit_speed(value)
                    save_configfile(sabnzbd.CFG)
                    return 'ok\n'
                else:
                    return 'error: Please submit a value\n'
            elif name == 'get_speedlimit':
                band = '-1'
                try:
                    band = str(int(sabnzbd.BANDWITH_LIMIT))
                except:
                    pass
                return band
            elif name == 'set_colorscheme':
                if value:
                    if self.__prim:
                        sabnzbd.CFG['misc']['web_color'] = value
                        sabnzbd.WEB_COLOR = value
                    else:
                        sabnzbd.CFG['misc']['web_color2'] = value
                        sabnzbd.WEB_COLOR2 = value
                    return 'ok\n'
                else:
                    return 'error: Please submit a value\n'
                
            else:
                return 'not implemented\n'

        if mode == 'get_cats':
            if output == 'json':
                return json_list("categories", ListCats())
            elif output == 'xml':
                return xml_list("categories", "category", ListCats())
            else:
                return 'not implemented\n'

        if mode == 'get_scripts':
            if output == 'json':
                return json_list("scripts", ListScripts())
            elif output == 'xml':
                return xml_list("scripts", "script", ListScripts())
            else:
                return 'not implemented\n'

        if mode == 'version':
            if output == 'json':
                return json_list('version', sabnzbd.__version__)
            elif output == 'xml':
                return xml_list('versions', 'version', (sabnzbd.__version__, ))
            else:
                return 'not implemented\n'
        
        return 'not implemented\n'

    @cherrypy.expose
    def scriptlog(self, name=None, _dc=None):
        """ Duplicate of scriptlog of History, needed for some skins """
        if name:
            history_db = cherrypy.thread_data.history_db
            return ShowString(name, history_db.get_script_log(name))
        else:
            raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def retry(self, url=None, pp=None, cat=None, script=None, _dc=None):
        """ Duplicate of retry of History, needed for some skins """
        if url: url = url.strip()
        if url and (url.isdigit() or len(url)==5):
            sabnzbd.add_msgid(url, pp, script, cat)
        elif url:
            sabnzbd.add_url(url, pp, script, cat)
        if url:
            return ShowOK(url)
        else:
            raise Raiser(self.__root, _dc)

#------------------------------------------------------------------------------
class NzoPage:
    def __init__(self, web_dir, root, nzo_id, prim):
        self.roles = ['admins']
        self.__nzo_id = nzo_id
        self.__root = '%s%s/' % (root, nzo_id)
        self.__web_dir = web_dir
        self.__verbose = False
        self.__prim = prim
        self.__cached_selection = {} #None

    @cherrypy.expose
    def index(self, _dc = None):
        info, pnfo_list, bytespersec = build_header(self.__prim)

        this_pnfo = None
        for pnfo in pnfo_list:
            if pnfo[PNFO_NZO_ID_FIELD] == self.__nzo_id:
                this_pnfo = pnfo
                break

        if this_pnfo:
            info['nzo_id'] = self.__nzo_id
            info['filename'] = xml_name(pnfo[PNFO_FILENAME_FIELD])

            active = []
            for tup in pnfo[PNFO_ACTIVE_FILES_FIELD]:
                bytes_left, bytes, fn, date, nzf_id = tup
                checked = False
                if nzf_id in self.__cached_selection and \
                   self.__cached_selection[nzf_id] == 'on':
                    checked = True

                line = {'filename':xml_name(fn),
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

        if '_dc' in kwargs:
            raise Raiser(self.__root, _dc=kwargs['_dc'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def tog_verbose(self, _dc = None):
        self.__verbose = not self.__verbose
        raise Raiser(self.__root, _dc=_dc)

#------------------------------------------------------------------------------
class QueuePage:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verboseList = []
        self.__prim = prim

        self.__nzo_pages = []

    @cherrypy.expose
    def index(self, _dc = None, start=None, limit=None, dummy2=None):

        info, pnfo_list, bytespersec, self.__verboseList, self.__nzo_pages, self.__dict__ = build_queue(self.__web_dir, self.__root, self.__verbose, self.__prim, self.__verboseList, self.__nzo_pages, self.__dict__, start=start, limit=limit, dummy2=dummy2)

        template = Template(file=os.path.join(self.__web_dir, 'queue.tmpl'),
                            searchList=[info],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()
    


    @cherrypy.expose
    def delete(self, uid = None, _dc = None, start=None, limit=None):
        if uid:
            sabnzbd.remove_nzo(uid, False)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def purge(self, _dc = None, start=None, limit=None):
        sabnzbd.remove_all_nzo()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def removeNzf(self, nzo_id = None, nzf_id = None, _dc = None, start=None, limit=None):
        if nzo_id and nzf_id:
            sabnzbd.remove_nzf(nzo_id, nzf_id)
        raise Raiser(self.__root,  _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def tog_verbose(self, _dc = None, start=None, limit=None):
        self.__verbose = not self.__verbose
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def tog_uid_verbose(self, uid, _dc = None, start=None, limit=None):
        if self.__verboseList.count(uid):
            self.__verboseList.remove(uid)
        else:
            self.__verboseList.append(uid)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def change_queue_complete_action(self, action = None, _dc = None, start=None, limit=None):
        """
        Action or script to be performed once the queue has been completed
        Scripts are prefixed with 'script_'
        """
        sabnzbd.change_queue_complete_action(action)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def switch(self, uid1 = None, uid2 = None, _dc = None, start=None, limit=None):
        if uid1 and uid2:
            sabnzbd.switch(uid1, uid2)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def change_opts(self, nzo_id = None, pp = None, _dc = None, start=None, limit=None):
        if nzo_id and pp and pp.isdigit():
            sabnzbd.change_opts(nzo_id, int(pp))
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def change_script(self, nzo_id = None, script = None, _dc = None, start=None, limit=None):
        if nzo_id and script:
            if script == 'None':
                script = None
            sabnzbd.change_script(nzo_id, script)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def change_cat(self, nzo_id = None, cat = None, _dc = None, start=None, limit=None):
        if nzo_id and cat:
            if cat == 'None':
                cat = None
            sabnzbd.change_cat(nzo_id, cat)
            item = config.get_config('categories', cat)
            if item:
                script = item.script.get()
                pp = item.pp.get()
            else:
                script = sabnzbd.misc.DIRSCAN_SCRIPT.get()
                pp = sabnzbd.misc.DIRSCAN_PP.get()

            sabnzbd.change_script(nzo_id, script)
            sabnzbd.change_opts(nzo_id, pp)

        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def shutdown(self):
        yield "Initiating shutdown..."
        sabnzbd.halt()
        cherrypy.engine.exit()
        yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
        sabnzbd.SABSTOP = True

    @cherrypy.expose
    def pause(self, _dc = None, start=None, limit=None):
        sabnzbd.pause_downloader()
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def resume(self, _dc = None, start=None, limit=None):
        sabnzbd.resume_downloader()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)
    
    @cherrypy.expose
    def pause_nzo(self, uid=None, _dc = None, start=None, limit=None):
        items = uid.split(',')
        sabnzbd.pause_multiple_nzo(items)
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)
    
    @cherrypy.expose
    def resume_nzo(self, uid=None, _dc = None, start=None, limit=None):
        items = uid.split(',')
        sabnzbd.resume_multiple_nzo(items)
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)
    
    @cherrypy.expose
    def set_priority(self, nzo_id=None, priority=None, _dc = None, start=None, limit=None):
        sabnzbd.set_priority(nzo_id, priority)
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def sort_by_avg_age(self, _dc = None, start=None, limit=None):
        sabnzbd.sort_by_avg_age()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def sort_by_name(self, _dc = None, start=None, limit=None):
        sabnzbd.sort_by_name()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def sort_by_size(self, _dc = None, start=None, limit=None):
        sabnzbd.sort_by_size()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)
    
    @cherrypy.expose
    def set_speedlimit(self, _dc = None, value=None):
        if not value:
            value = '0'
        try:
            value = int(value)
        except:
            return 'error: Please submit a value\n'
        sabnzbd.limit_speed(value)
        raise Raiser(self.__root, _dc)

class HistoryPage:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verbose_list = []
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None, start=None, limit=None, dummy2=None):
        history, pnfo_list, bytespersec = build_header(self.__prim)

        history['isverbose'] = self.__verbose

        if newzbin.USERNAME_NEWZBIN.get() and newzbin.PASSWORD_NEWZBIN.get():
            history['newzbinDetails'] = True

        #history_items, total_bytes, bytes_beginning = sabnzbd.history_info()
        #history['bytes_beginning'] = "%.2f" % (bytes_beginning / GIGI)
        
        history['total_size'] = get_history_size()
        
        history['start'] = IntConv(start)
        history['limit'] = IntConv(limit)
        # Should really find the actual maximum
        history['end'] = history['start'] + history['limit']

        history['lines'], history['noofslots'] = build_history(limit=limit, start=start, verbose=self.__verbose, verbose_list=self.__verbose_list)


        template = Template(file=os.path.join(self.__web_dir, 'history.tmpl'),
                            searchList=[history],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def purge(self, _dc = None, start=None, limit=None):
        history_db = cherrypy.thread_data.history_db
        history_db.remove_history()
        raise Raiser(self.__root, _dc, start, limit)

    @cherrypy.expose
    def delete(self, job=None, _dc = None, start=None, limit=None):
        if job:
            jobs = job.split(',')
            history_db = cherrypy.thread_data.history_db
            history_db.remove_history(jobs)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def reset(self, _dc = None, start=None, limit=None):
        sabnzbd.reset_byte_counter()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def tog_verbose(self, _dc = None, start=None, limit=None, jobs=None):
        if not jobs:
            self.__verbose = not self.__verbose
            self.__verbose_list = []
        else:
            if self.__verbose:
                self.__verbose = False
            else:
                jobs = jobs.split(',')
                for job in jobs:
                    if job in self.__verbose_list:
                        self.__verbose_list.remove(job)
                    else:
                        self.__verbose_list.append(job)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def scriptlog(self, name=None, _dc=None, start=None, limit=None):
        """ Duplicate of scriptlog of History, needed for some skins """
        if name:
            history_db = cherrypy.thread_data.history_db
            return ShowString(name, history_db.get_script_log(name))
        else:
            raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def retry(self, url=None, pp=None, cat=None, script=None, _dc=None):
        if url: url = url.strip()
        if url and (url.isdigit() or len(url)==5):
            sabnzbd.add_msgid(url, pp, script, cat)
        elif url:
            sabnzbd.add_url(url, pp, script, cat)
        if url:
            return ShowOK(url)
        else:
            raise Raiser(self.__root, _dc)

#------------------------------------------------------------------------------
class ConfigPage:
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
        self.sorting = ConfigSorting(web_dir, root+'sorting/', prim)


    @cherrypy.expose
    def index(self, _dc = None):
        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['configfn'] = sabnzbd.CFG.filename
        
        new = {}
        org = sabnzbd.CFG['servers']
        for svr in org:
            new[svr] = {}
        config['servers'] = new

        template = Template(file=os.path.join(self.__web_dir, 'config.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def restart(self, _dc = None):
        sabnzbd.halt()
        init_ok = sabnzbd.initialize()
        if init_ok:
            sabnzbd.start()
            raise Raiser(self.__root, _dc=_dc)
        else:
            return "SABnzbd restart failed! See logfile(s)."

#------------------------------------------------------------------------------
class ConfigDirectories:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']

        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
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
        config['email_dir'] = sabnzbd.CFG['misc']['email_dir']
        config['my_home'] = sabnzbd.DIR_HOME
        config['my_lcldata'] = sabnzbd.DIR_LCLDATA
        config['permissions'] = sabnzbd.UMASK
        
        template = Template(file=os.path.join(self.__web_dir, 'config_directories.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveDirectories(self, download_dir = None, download_free = None, complete_dir = None, log_dir = None,
                        cache_dir = None, nzb_backup_dir = None, permissions=None,
                        date_cat=None, movie_cat=None, dirscan_dir = None, email_dir = None,
                        dirscan_speed = None, script_dir = None, _dc = None):

        if permissions:
            try:
                int(permissions,8)
            except:
                return badParameterResponse('Error: use octal notation for permissions')

        if not sabnzbd.empty_queues():
            if download_dir != sabnzbd.CFG['misc']['download_dir']:
                return badParameterResponse('Error: Queue not empty, cannot change download directory.')
            if cache_dir != sabnzbd.CFG['misc']['cache_dir']:
                return badParameterResponse('Error: Queue not empty, cannot change cache directory.')
        
        (dd, path) = create_real_path('download_dir', sabnzbd.DIR_HOME, download_dir)
        if not dd:
            return badParameterResponse('Error: cannot create download directory "%s".' % path)
        if path.startswith('\\\\'):
            return badParameterResponse('Error: UNC path "%s" not supported as download directory.' % path)

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

        if email_dir:
            (dd, path) = create_real_path('email_dir', sabnzbd.DIR_HOME, email_dir)
            if not dd:
                return badParameterResponse('Error: cannot create email_dir directory "%s".' % path)

        #if SameFile(download_dir, complete_dir):
        #    return badParameterResponse('Error: DOWNLOAD_DIR and COMPLETE_DIR should not be the same (%s)!' % path)


        sabnzbd.CFG['misc']['download_dir'] = download_dir
        sabnzbd.CFG['misc']['download_free'] = download_free
        sabnzbd.CFG['misc']['cache_dir'] = cache_dir
        sabnzbd.CFG['misc']['log_dir'] = log_dir
        sabnzbd.CFG['misc']['dirscan_dir'] = dirscan_dir
        sabnzbd.CFG['misc']['dirscan_speed'] = sabnzbd.minimax(dirscan_speed, 1, 3600)
        sabnzbd.CFG['misc']['script_dir'] = script_dir
        sabnzbd.CFG['misc']['email_dir'] = email_dir
        sabnzbd.CFG['misc']['complete_dir'] = complete_dir
        sabnzbd.CFG['misc']['nzb_backup_dir'] = nzb_backup_dir
        if permissions: sabnzbd.CFG['misc']['permissions'] = permissions

        return saveAndRestart(self.__root, _dc)


SWITCH_LIST = \
    ('par_option', 'enable_unrar', 'enable_unzip', 'enable_filejoin',
     'enable_tsjoin', 'send_group', 'fail_on_crc', 'top_only',
     'dirscan_opts', 'enable_par_cleanup', 'auto_sort', 'check_new_rel', 'auto_disconnect',
     'safe_postproc', 'no_dupes', 'replace_spaces', 'replace_illegal', 'auto_browser',
     'ignore_samples', 'pause_on_post_processing', 'quick_check', 'dirscan_script', 'ionice'
    )

#------------------------------------------------------------------------------
class ConfigSwitches:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        cfg, pnfo_list, bytespersec = build_header(self.__prim)

        cfg['nt'] = os.name == 'nt'

        for kw in SWITCH_LIST:
            cfg[kw] = config.get_config('misc', kw).get()

        cfg['script_list'] = ListScripts()

        template = Template(file=os.path.join(self.__web_dir, 'config_switches.tmpl'),
                            searchList=[cfg],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveSwitches(self, **kwargs):

        for kw in SWITCH_LIST:
            item = config.get_config('misc', kw)
            try:
                value = kwargs[kw]
            except:
                value = None
            if not item.set(value):
                return badParameterResponse('Error: incorrect value "%s" for config-item "%s".' % (value, kw))

        try:
            _dc = kwargs['_dc']
        except:
            _dc = ''
        return saveAndRestart(self.__root, _dc)

#------------------------------------------------------------------------------

class ConfigGeneral:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
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
    def saveGeneral(self, host = None, port = None, web_username = None, web_password = None, web_dir = None,
                    web_dir2 = None, web_color = None,
                    cronlines = None, refresh_rate = None, rss_rate = None,
                    bandwith_limit = None, cleanup_list = None, cache_limitstr = None, _dc = None):


        if web_color:
            if self.__prim:
                sabnzbd.CFG['misc']['web_color'] = web_color
            else:
                sabnzbd.CFG['misc']['web_color2'] = web_color

        sabnzbd.CFG['misc']['host'] = Strip(host)
        sabnzbd.CFG['misc']['port'] = Strip(port)
        sabnzbd.CFG['misc']['username'] = Strip(web_username)
        if (not web_password) or (web_password and web_password.strip('*')):
            sabnzbd.CFG['misc']['password'] = encodePassword(web_password)
        sabnzbd.CFG['misc']['bandwith_limit'] = bandwith_limit
        sabnzbd.CFG['misc']['refresh_rate'] = refresh_rate
        sabnzbd.CFG['misc']['rss_rate'] = sabnzbd.minimax(rss_rate, 15, 24*60)
        if os.name == 'nt':
            cleanup_list = cleanup_list.lower()
        sabnzbd.CFG['misc']['cleanup_list'] = listquote.simplelist(cleanup_list)
        sabnzbd.CFG['misc']['cache_limit'] = cache_limitstr

        web_dir_path = real_path(sabnzbd.DIR_INTERFACES, web_dir)
        web_dir2_path = real_path(sabnzbd.DIR_INTERFACES, web_dir2)
        
        if not os.path.exists(web_dir_path):
            logging.warning('Cannot find web template: %s', web_dir_path)
        else:    
            sabnzbd.CFG['misc']['web_dir']  = web_dir
            self.__web_dir = web_dir
            
        if web_dir2 == 'None':
            sabnzbd.CFG['misc']['web_dir2'] = ''
        elif os.path.exists(web_dir2_path):
            sabnzbd.CFG['misc']['web_dir2'] = web_dir2
          
        if os.path.exists(web_dir_path) and os.path.exists(web_dir2_path):
            
            web_dir_path = real_path(web_dir_path, "templates")
            web_dir2_path = real_path(web_dir2_path, "templates")
            sabnzbd.change_web_dir(web_dir_path)
            sabnzbd.change_web_dir2(web_dir2_path)
            
       
       
        return saveAndRestart(self.__root, _dc)


#------------------------------------------------------------------------------

class ConfigServer:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
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
            new[svr]['enable'] = org[svr]['enable']
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
                  password = None, connections = None, ssl = None, fillserver = None, enable=None, _dc = None):

        timeout = check_timeout(timeout)

        host = Strip(host)
        port = Strip(port)
        if connections == "":
            connections = '1'
        if port == "":
            port = '119'
        if not fillserver:
            fillserver = '0'
        if not ssl:
            ssl = '0'
        if enable == None:
            enable = '1'
        if host and port and port.isdigit() \
           and connections.isdigit() and fillserver.isdigit() \
           and ssl.isdigit():
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
                sabnzbd.CFG['servers'][server]['enable'] = enable

        save_configfile(sabnzbd.CFG)
        sabnzbd.update_server(None, server)
        raise Raiser(self.__root, _dc=_dc)


    @cherrypy.expose
    def saveServer(self, server = None, host = None, port = None, username = None, timeout = None,
                   password = None, connections = None, fillserver = None, ssl = None, enable=None, _dc = None):

        timeout = check_timeout(timeout)

        oldserver = Strip(server)
        port = Strip(port)

        if connections == "":
            connections = '1'
        if port == "":
            port = '119'
        if not ssl:
            ssl = '0'
        if not fillserver:
            fillserver = '0'
        if not enable:
            enable = '0'
        if host and port and port.isdigit() \
           and connections.isdigit() and fillserver and fillserver.isdigit() \
           and ssl and ssl.isdigit():
            msg = check_server(host, port)
            if msg:
                return msg

            if password and not password.strip('*'):
                password = sabnzbd.CFG['servers'][oldserver]['password']

            del sabnzbd.CFG['servers'][oldserver]

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
            sabnzbd.CFG['servers'][server]['enable'] = enable

        save_configfile(sabnzbd.CFG)
        sabnzbd.update_server(oldserver, server)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def delServer(self, *args, **kwargs):
        if 'server' in kwargs and kwargs['server'] in sabnzbd.CFG['servers']:
            server = kwargs['server']
            del sabnzbd.CFG['servers'][server]
            save_configfile(sabnzbd.CFG)
            sabnzbd.update_server(server, None)
        
        if '_dc' in kwargs:
            raise Raiser(self.__root, _dc=kwargs['_dc'])
        else:
            raise Raiser(self.__root, _dc='')

#------------------------------------------------------------------------------

def ListFilters(feed):
    """ Make a list of all filters of this feed """
    n = 0
    filters= []
    config = sabnzbd.CFG['rss'][feed]
    while True:
        try:
            tup = config['filter'+str(n)]
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
    config = sabnzbd.CFG['rss'][feed]
    n = 0
    while True:
        try:
            del config['filter'+str(n)]
            n = n + 1
        except:
            break

    for n in xrange(len(filters)):
        config['filter'+str(n)] = filters[n]



def GetCfgRss(config, keyword):
    """ Get a keyword from an RSS entry """
    try:
        return config[keyword]
    except:
        return ''

class ConfigRss:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['have_feedparser'] = sabnzbd.rss.have_feedparser()

        config['script_list'] = ListScripts(default=True)

        config['cat_list'] = ListCats(default=True)

        rss = {}
        unum = 1
        for feed in sabnzbd.CFG['rss']:
            rss[feed] = {}
            cfg = sabnzbd.CFG['rss'][feed]
            rss[feed]['uri'] = GetCfgRss(cfg, 'uri')
            rss[feed]['cat'] = GetCfgRss(cfg, 'cat')
            rss[feed]['pp'] = GetCfgRss(cfg, 'pp')
            rss[feed]['script'] = GetCfgRss(cfg, 'script')
            if GetCfgRss(cfg, 'priority'):
                rss[feed]['priority'] = GetCfgRss(cfg, 'priority')
            else:
                rss[feed]['priority'] = 0
            rss[feed]['enable'] = IntConv(GetCfgRss(cfg, 'enable'))
            rss[feed]['pick_cat'] = config['cat_list'] != []
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
    def upd_rss_feed(self, feed=None, uri=None, cat=None, pp=None, script=None, priority=None, enable=None, _dc=None):
        uri = Strip(uri)
        try:
            cfg = sabnzbd.CFG['rss'][feed]
        except:
            feed = None
        if feed and uri:
            cfg['uri'] = uri
            cfg['cat'] = ConvertSpecials(cat)
            if IsNone(pp): pp = ''
            cfg['pp'] = pp
            cfg['script'] = ConvertSpecials(script)
            cfg['priority'] = IntConv(priority)
            save_configfile(sabnzbd.CFG)

        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def toggle_rss_feed(self, feed=None, uri=None, cat=None, pp=None, script=None, priority=None, enable=None, _dc=None):
        try:
            cfg = sabnzbd.CFG['rss'][feed]
        except:
            feed = None
        if feed:
            cfg['enable'] = int(not int(cfg['enable']))
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def add_rss_feed(self, feed=None, uri=None, _dc=None):
        feed= Strip(feed)
        uri = Strip(uri)
        try:
            sabnzbd.CFG['rss'][feed]
        except:
            sabnzbd.CFG['rss'][feed] = {}
            cfg = sabnzbd.CFG['rss'][feed]
            cfg['uri'] = uri
            cfg['cat'] = ''
            cfg['pp'] = ''
            cfg['script'] = ''
            cfg['priority'] = 0
            cfg['enable'] = 0
            cfg['filter0'] = ('', '', '', 'A', '*')
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def upd_rss_filter(self, feed=None, index=None, filter_text=None,
                       filter_type=None, cat=None, pp=None, script=None, _dc=None):
        try:
            cfg = sabnzbd.CFG['rss'][feed]
        except:
            raise Raiser(self.__root, _dc=_dc)

        if IsNone(pp): pp = ''
        script = ConvertSpecials(script)
        cat = ConvertSpecials(cat)

        cfg['filter'+str(index)] = (cat, pp, script, filter_type, filter_text)
        save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def pos_rss_filter(self, feed=None, current=None, new=None, _dc=None):
        if current != new:
            filters = ListFilters(feed)
            filter = filters.pop(int(current))
            filters.insert(int(new), filter)
            UnlistFilters(feed, filters)
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def del_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            try:
                del sabnzbd.CFG['rss'][feed]
                sabnzbd.rss.del_feed(feed)
            except:
                pass
            save_configfile(sabnzbd.CFG)
        if '_dc' in kwargs:
            raise Raiser(self.__root, _dc=kwargs['_dc'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def del_rss_filter(self, feed=None, index=None, _dc=None):
        if feed and index!=None:
            filters = ListFilters(feed)
            filter = filters.pop(int(index))
            UnlistFilters(feed, filters)
            save_configfile(sabnzbd.CFG)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def download_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            sabnzbd.rss.run_feed(feed, download=True)
            return ShowRssLog(feed, False)
        if '_dc' in kwargs:
            raise Raiser(self.__root, _dc=kwargs['_dc'])
        else:
            raise Raiser(self.__root, '')

    @cherrypy.expose
    def test_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            sabnzbd.rss.run_feed(feed, download=False)
            return ShowRssLog(feed, True)
        if '_dc' in kwargs:
            raise Raiser(self.__root, _dc=kwargs['_dc'])
        else:
            raise Raiser(self.__root, '')


    @cherrypy.expose
    def rss_download(self, feed=None, id=None, cat=None, pp=None, script=None, _dc=None, priority=NORMAL_PRIORITY):
        if id and id.isdigit():
            sabnzbd.add_msgid(id, pp, script, cat, priority)
        elif id:
            sabnzbd.add_url(id, pp, script, cat, priority)
        # Need to pass the title instead
        sabnzbd.rss.flag_downloaded(feed, id)
        raise Raiser(self.__root, _dc=_dc)


#------------------------------------------------------------------------------

class ConfigScheduling:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['schedlines'] = []
        for ev in scheduler.sort_schedules(forward=True):
            config['schedlines'].append(ev[3])

        actions = ['resume', 'pause', 'shutdown', 'speedlimit']
        servers = sabnzbd.CFG['servers']
        for server in servers:
            actions.append(server)
        config['actions'] = actions

        template = Template(file=os.path.join(self.__web_dir, 'config_scheduling.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def addSchedule(self, minute = None, hour = None, dayofweek = None,
                    action = None, arguments = None, _dc = None):

        arguments = arguments.strip().lower()
        if arguments in ('on', 'enable'):
            arguments = '1'
        elif arguments in ('off','disable'):
            arguments = '0'

        if minute and hour  and dayofweek and action:
            if (action == 'speedlimit') and arguments.isdigit():
                pass
            elif action in ('resume', 'pause', 'shutdown'):
                arguments = ''
            elif action.find(':') > 0:
                if arguments == '1':
                    arguments = action
                    action = 'enable_server'
                else:
                    arguments = action
                    action = 'disable_server'
            else:
                action = None

            if action:
                sched = scheduler.SCHEDULES.get()
                sched.append('%s %s %s %s %s' %
                                 (minute, hour, dayofweek, action, arguments))
                scheduler.SCHEDULES.set(sched)

        config.save_config()
        scheduler.restart(force=True)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def delSchedule(self, line = None, _dc = None):
        schedules = scheduler.SCHEDULES.get()
        if line and line in schedules:
            schedules.remove(line)
            scheduler.SCHEDULES.set(schedules)
        config.save_config()
        scheduler.restart(force=True)
        raise Raiser(self.__root, _dc=_dc)

#------------------------------------------------------------------------------

class ConfigNewzbin:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__bookmarks = []

    @cherrypy.expose
    def index(self, _dc = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['username_newzbin'] = newzbin.USERNAME_NEWZBIN.get()
        config['password_newzbin'] = newzbin.PASSWORD_NEWZBIN.get_stars()
        config['newzbin_bookmarks'] = int(newzbin.NEWZBIN_BOOKMARKS.get())
        config['newzbin_unbookmark'] = int(newzbin.NEWZBIN_UNBOOKMARK.get())
        config['bookmark_rate'] = newzbin.BOOKMARK_RATE.get()

        config['bookmarks_list'] = self.__bookmarks

        config['username_matrix'] = urlgrabber.USERNAME_MATRIX.get()
        config['password_matrix'] = urlgrabber.PASSWORD_MATRIX.get_stars()

        template = Template(file=os.path.join(self.__web_dir, 'config_newzbin.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveNewzbin(self, username_newzbin = None, password_newzbin = None,
                    create_category_folders = None, newzbin_bookmarks = None,
                    newzbin_unbookmark = None, bookmark_rate = None,
                    username_matrix = None, password_matrix = None, _dc = None):

        
        newzbin.USERNAME_NEWZBIN.set(username_newzbin)
        newzbin.PASSWORD_NEWZBIN.set(password_newzbin)
        newzbin.NEWZBIN_BOOKMARKS.set(newzbin_bookmarks)
        newzbin.NEWZBIN_UNBOOKMARK.set(newzbin_unbookmark)
        newzbin.BOOKMARK_RATE.set(bookmark_rate)

        urlgrabber.USERNAME_MATRIX.set(username_matrix)
        urlgrabber.PASSWORD_MATRIX.set(password_matrix)

        config.save_config()
        scheduler.restart()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def saveMatrix(self, username_matrix = None, password_matrix = None, _dc = None):

        urlgrabber.USERNAME_MATRIX.set(username_matrix)
        urlgrabber.PASSWORD_MATRIX.set(password_matrix)

        config.save_config()
        raise Raiser(self.__root, _dc=_dc)


    @cherrypy.expose
    def getBookmarks(self, _dc = None):
        newzbin.getBookmarksNow()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def showBookmarks(self, _dc = None):
        self.__bookmarks = newzbin.getBookmarksList()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def hideBookmarks(self, _dc = None):
        self.__bookmarks = []
        raise Raiser(self.__root, _dc=_dc)

#------------------------------------------------------------------------------

class ConfigCats:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        if newzbin.USERNAME_NEWZBIN.get() and newzbin.PASSWORD_NEWZBIN.get():
            conf['newzbinDetails'] = True

        conf['script_list'] = ListScripts(default=True)

        categories = config.get_categories()
        conf['have_cats'] =  categories != {}
        conf['defdir'] = sabnzbd.COMPLETE_DIR


        empty = { 'name':'', 'pp':'-1', 'script':'', 'dir':'', 'newzbin':'' }
        slotinfo = []
        slotinfo.append(empty)
        for cat in sorted(categories):
            slot = categories[cat].get_dict()
            slot['name'] = cat
            slotinfo.append(slot)
        conf['slotinfo'] = slotinfo

        template = Template(file=os.path.join(self.__web_dir, 'config_cat.tmpl'),
                            searchList=[conf],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def delete(self, name = None, _dc = None):
        if name:
            config.delete('categories', name)
            config.save_config()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def save(self, **kwargs):
        newname = Strip(get_arg(kwargs, 'newname'))
        name = get_arg(kwargs, 'name')
        _dc = get_arg(kwargs, '_dc')

        if newname:
            if name:
                config.delete('categories', name)
            name = newname.lower()
            config.ConfigCat(name, kwargs)

        config.save_config()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def init_newzbin(self, _dc = None):
        config.define_categories()
        config.save_config()
        raise Raiser(self.__root, _dc=_dc)


SORT_LIST = ( \
    'enable_tv_sorting', 'tv_sort_string', 'enable_movie_sorting',
    'movie_sort_string', 'movie_sort_extra', 'movie_extra_folder',
    'enable_date_sorting', 'date_sort_string', 'movie_categories', 'date_categories'
    )

#------------------------------------------------------------------------------
class ConfigSorting:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']

        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        cfg, pnfo_list, bytespersec = build_header(self.__prim)
        cfg['complete_dir'] = sabnzbd.COMPLETE_DIR

        for kw in SORT_LIST:
            cfg[kw] = config.get_config('misc', kw).get()
        cfg['cat_list'] = ListCats(True)
        #tvSortList = []
        
        template = Template(file=os.path.join(self.__web_dir, 'config_sorting.tmpl'),
                            searchList=[cfg],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveSorting(self, **kwargs):

        try:
            kwargs['movie_categories'] = kwargs['movie_cat']
        except:
            pass
        try:
            kwargs['date_categories'] = kwargs['date_cat']
        except:
            pass

        for kw in SORT_LIST:
            item = config.get_config('misc', kw)
            try:
                value = kwargs[kw]
            except:
                value = None
            if not item.set(value):
                return badParameterResponse('Error: incorrect value "%s" for config-item "%s".' % (value, kw))

        config.save_config()
        try:
            _dc = kwargs['_dc']
        except:
            _dc = ''
        raise Raiser(self.__root, _dc=_dc)
    

#------------------------------------------------------------------------------

class ConnectionInfo:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__lastmail = None

    @cherrypy.expose
    def index(self, _dc = None):
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

                    art_name = xml_name(article.article)
                    #filename field is not always present
                    try:
                        nzf_name = xml_name(nzf.get_filename())
                    except: #attribute error
                        nzf_name = xml_name(nzf.get_subject())
                    nzo_name = xml_name(nzo.get_filename())

                busy.append((nw.thrdnum, art_name, nzf_name, nzo_name))

                if nw.connected:
                    connected += 1

            busy.sort()
            header['servers'].append((server.host, server.port, connected, busy, server.ssl))

        wlist = []
        for w in sabnzbd.GUIHANDLER.content():
            wlist.append(xml_name(w))
        header['warnings'] = wlist

        template = Template(file=os.path.join(self.__web_dir, 'connection_info.tmpl'),
                            searchList=[header],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def disconnect(self, _dc = None):
        sabnzbd.disconnect()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def testmail(self, _dc = None):
        logging.info("[%s] Sending testmail", __NAME__)
        pack = {}
        pack[0] = {}
        pack[0]['action1'] = 'done 1'
        pack[0]['action2'] = 'done 2'
        pack[1] = {}
        pack[1]['action1'] = 'done 1'
        pack[1]['action2'] = 'done 2'
        
        self.__lastmail= email.endjob('Test Job', 'unknown', True,
                                      os.path.normpath(os.path.join(sabnzbd.COMPLETE_DIR, '/unknown/Test Job')),
                                      str(123*MEBI), pack, 'my_script', 'Line 1\nLine 2\nLine 3\n')
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def showlog(self):
        try:
            sabnzbd.LOGHANDLER.flush()
        except:
            pass
        return cherrypy.lib.static.serve_file(sabnzbd.LOGFILE, "application/x-download", "attachment")

    @cherrypy.expose
    def showweb(self):
        if sabnzbd.WEBLOGFILE:
            return cherrypy.lib.static.serve_file(sabnzbd.WEBLOGFILE, "application/x-download", "attachment")
        else:
            return "Web logging is off!"

    @cherrypy.expose
    def clearwarnings(self, _dc = None):
        sabnzbd.GUIHANDLER.clear()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def change_loglevel(self, loglevel=None, _dc = None):
        loglevel = IntConv(loglevel)
        if loglevel >= 0 and loglevel < 3:
            sabnzbd.LOGLEVEL = loglevel
            sabnzbd.CFG['logging']['log_level'] = loglevel
            save_configfile(sabnzbd.CFG)

        raise Raiser(self.__root, _dc=_dc)


def saveAndRestart(redirect_root, _dc, evalSched=False):
    save_configfile(sabnzbd.CFG)
    sabnzbd.halt()
    init_ok = sabnzbd.initialize(evalSched=evalSched)
    if init_ok:
        sabnzbd.start()
        raise Raiser(redirect_root, _dc=_dc)
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
        msg = TRANS(f.read())
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

def ShowString(name, string):
    """Return a html page listing a file and a 'back' button
    """
    try:
        msg = TRANS(string)
    except:
        msg = "Encoding Error\n"

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


def ShowOK(url):
    return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
           <title>%s</title>
</head>
<body>
           <FORM><INPUT TYPE="BUTTON" VALUE="Go Back" ONCLICK="history.go(-1)"></FORM>
           <br/><br/>
           Job %s was re-added to the queue.
           <br/><br/>
</body>
</html>
''' % (escape(url), escape(url))


def ShowRssLog(feed, all):
    """Return a html page listing an RSS log and a 'back' button
    """
    jobs = sabnzbd.rss.show_result(feed)
    qfeed = escape(feed.replace('/','%2F').replace('?', '%3F'))

    doneStr = ""
    for x in jobs:
        job = jobs[x]
        if job[0] == 'D':
            doneStr += '%s<br/>' % xml_name(job[1])
    goodStr = ""
    for x in jobs:
        job = jobs[x]
        if job[0] == 'G':
            goodStr += '%s<br/>' % xml_name(job[1])
    badStr = ""
    for x in jobs:
        job = jobs[x]
        if job[0] == 'B':
            name = urllib.quote_plus(job[2])
            if job[3]:
                cat = '&cat=' + escape(job[3])
            else:
                cat = ''
            if job[4]:
                pp = '&pp=' + escape(job[4])
            else:
                pp = ''
            badStr += '<a href="rss_download?feed=%s&id=%s%s%s">Download</a>&nbsp;&nbsp;&nbsp;%s<br/>' % \
                   (qfeed, name, cat, pp, xml_name(job[1]))

    if all:
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
    else:
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
               <b>Downloaded so far</b><br/>
               %s
               <br/>
</body>
</html>
''' % (escape(feed), escape(feed), doneStr)


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
    try:
        if int(sabnzbd.BANDWITH_LIMIT) > 0:
            speed_limit = sabnzbd.BANDWITH_LIMIT
        else:
            speed_limit = ''
    except:
        speed_limit = ''

    header['helpuri'] = 'http://sabnzbd.wikidot.com'
    header['diskspace1'] = "%.2f" % diskfree(sabnzbd.DOWNLOAD_DIR)
    header['diskspace2'] = "%.2f" % diskfree(sabnzbd.COMPLETE_DIR)
    header['diskspacetotal1'] = "%.2f" % disktotal(sabnzbd.DOWNLOAD_DIR)
    header['diskspacetotal2'] = "%.2f" % disktotal(sabnzbd.COMPLETE_DIR)
    header['speedlimit'] = "%s" % speed_limit
    header['have_warnings'] = str(sabnzbd.GUIHANDLER.count())
    header['last_warning'] = sabnzbd.GUIHANDLER.last()
    if prim:
        header['webdir'] = sabnzbd.WEB_DIR
    else:
        header['webdir'] = sabnzbd.WEB_DIR2

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
    
    status = ''
    if sabnzbd.paused():
        status = 'Paused'
    elif bytespersec > 0:
        status = 'Downloading'
    else:
        status = 'Idle'
    header['status'] = "%s" % status

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

class ConfigEmail:
    def __init__(self, web_dir, root, prim):
        self.roles = ['admins']
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if sabnzbd.CONFIGLOCK:
            return Protected()

        config, pnfo_list, bytespersec = build_header(self.__prim)

        config['email_server'] = email.EMAIL_SERVER.get()
        config['email_to'] = email.EMAIL_TO.get()
        config['email_from'] = email.EMAIL_FROM.get()
        config['email_account'] = email.EMAIL_ACCOUNT.get()
        config['email_pwd'] = email.EMAIL_PWD.get_stars()
        config['email_endjob'] = email.EMAIL_ENDJOB.get()
        config['email_full'] = email.EMAIL_FULL.get()

        template = Template(file=os.path.join(self.__web_dir, 'config_email.tmpl'),
                            searchList=[config],
                            compilerSettings={'directiveStartToken': '<!--#',
                                              'directiveEndToken': '#-->'})
        return template.respond()

    @cherrypy.expose
    def saveEmail(self, email_server = None, email_to = None, email_from = None,
                  email_account = None, email_pwd = None,
                  email_endjob = None, email_full = None, _dc = None):

        email_server = Strip(email_server)
        email_to = Strip(email_to)
        email_from = Strip(email_from)
        email_account = Strip(email_account)

        email.EMAIL_ENDJOB.set(email_endjob)
        email.EMAIL_FULL.set(email_full)

        on = (email.EMAIL_ENDJOB.get() > 0) or email.EMAIL_FULL.get()
        
        ok = email.EMAIL_TO.set(email_to)
        if on and not (ok and email_to):
            return badParameterResponse('Invalid email address "%s"' % email_to)

        ok = email.EMAIL_FROM.set(email_from)
        if on and not (ok and email_from):
            return badParameterResponse('Invalid email address "%s"' % email_from)

        ok = email.EMAIL_SERVER.set(email_server)
        if on and not (ok and email_server):
            return badParameterResponse('Need a server address')

        email.EMAIL_ACCOUNT.set(email_account)
        email.EMAIL_PWD.set(email_pwd)

        config.save_config()
        raise Raiser(self.__root, _dc=_dc)


def std_time(when):
    # Fri, 16 Nov 2007 16:42:01 GMT +0100
    item  = time.strftime('%a, %d %b %Y %H:%M:%S', time.localtime(when))
    item += " GMT %+05d" % (-time.timezone/36)
    return item


def rss_history(url, limit=50):
    m = RE_URL.search(url)
    if not m:
        url = 'http://%s:%s' % (sabnzbd.CFG['misc']['host'], sabnzbd.CFG['misc']['port'])
    else:
        url = m.group(1)
        
    youngest = None

    rss = RSS()
    rss.channel.title = "SABnzbd History"
    rss.channel.description = "Overview of completed downloads"
    rss.channel.link = "http://sourceforge.net/projects/sabnzbdplus/"
    rss.channel.language = "en"

    items, max_items = build_history(limit=limit)
    
    for history in items:
        item = Item()
        
        item.pubDate = std_time(history['completed'])
        item.title = history['name']
        
        if not youngest:
            youngest = history['completed']
        elif history['completed'] < youngest:
            youngest = history['completed']
        
        if history['report']:
            item.link = "https://www.newzbin.com/browse/post/%s/" % history['report']
        elif history['url_info']:
            item.link = history['url_info']
        else:
            item.link = url + '/sabnzbd/'
            
        stageLine = ""
        for stage in history['stage_log']:
            stageLine += "<tr><dt>Stage %s</dt>" % stage['name']
            actions = []
            for action in stage['actions']:
                actionLine = "<dd>%s</dd>" % (action)
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
    
def format_bytes(bytes):
    try:
        if bytes >= MEBI and bytes < GIGI:
            size = '%0.0f MB' % (bytes/MEBI)
        elif bytes >= GIGI:
            size = '%0.2f GB' % (bytes/GIGI)
        else:
            size = '%0.0f KB' % (bytes/KIBI)
    except:
        size = ''
        
    return size


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
        "have_warnings" : str(sabnzbd.GUIHANDLER.count()),
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
        name = xml_name(filename)
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append( { "id" : nzo_id, "mb":bytes, "mbleft":bytesleft, "filename":name, "msgid":msgid } )

    status = {
        "paused" : sabnzbd.paused(),
        "kbpersec" : sabnzbd.bps() / KIBI,
        "mbleft" : qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
        "mb" : qnfo[QNFO_BYTES_FIELD] / MEBI,
        "noofslots" : len(pnfo_list),
        "have_warnings" : str(sabnzbd.GUIHANDLER.count()),
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


def build_file_list(id):
    qnfo = sabnzbd.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]
    
    jobs = []
    for pnfo in pnfo_list:
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        if nzo_id == id:
            finished_files = pnfo[PNFO_FINISHED_FILES_FIELD]
            active_files = pnfo[PNFO_ACTIVE_FILES_FIELD]
            queued_files = pnfo[PNFO_QUEUED_FILES_FIELD]
    
    
            n = 0
            for tup in finished_files:
                bytes_left, bytes, fn, date = tup
                fn = xml_name(fn)
    
                age = calc_age(date)
    
                line = {'filename':str(fn),
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'bytes':"%.2f" % bytes,
                        'age':age, 'id':str(n), 'status':'finished'}
                jobs.append(line)
                n += 1
    
            for tup in active_files:
                bytes_left, bytes, fn, date, nzf_id = tup
                fn = xml_name(fn)
    
                age = calc_age(date)
    
                line = {'filename':str(fn),
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'bytes':"%.2f" % bytes,
                        'nzf_id':nzf_id,
                        'age':age, 'id':str(n), 'status':'active'}
                jobs.append(line)
                n += 1
    
            for tup in queued_files:
                _set, bytes_left, bytes, fn, date = tup
                fn = xml_name(fn)
    
                age = calc_age(date)
    
                line = {'filename':str(fn), 'set':_set,
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'bytes':"%.2f" % bytes,
                        'age':age, 'id':str(n), 'status':'queued'}
                jobs.append(line)
                n += 1
                
    return jobs

def xml_files(id):
    
    #Collect all Queue data
    status_str = '<?xml version="1.0" encoding="UTF-8" ?> \n'
    
    jobs = build_file_list(id)

                
    xmlmaker = xml_factory()
    status_str += xmlmaker.run("files",jobs)
                
    #status_str += '</files>\n'
    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str

def json_files(id):
    
    #Collect all Queue data    
    jobs = build_file_list(id)
                
    status_str = JsonWriter().write(jobs)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str

def get_history_size():
    history_db = cherrypy.thread_data.history_db
    bytes = history_db.get_history_size()
    return format_bytes(bytes)

def build_history(loaded=False, start=None, limit=None, verbose=False, verbose_list=[]):
    
    # Get the currently in progress and active history queue.
    queue = sabnzbd.get_history_queue()
    
    try:
        limit = int(limit)
    except:
        limit = 0
    try:
        start = int(start)
    except:
        start = 0
    
    if start:
        if start > len(queue):
            queue = []
        else:
            queue[start:]
        start -= len(queue)
            

    history_db = cherrypy.thread_data.history_db
    items, total_items = history_db.fetch_history(start,limit)

    # Fetch which items should show details from the cookie
    k = []
    if verbose:
        details_show_all = True
    else:
        details_show_all = False
    cookie = cherrypy.request.cookie
    if cookie.has_key('history_verbosity'):
        k = cookie['history_verbosity'].value
        c_path = cookie['history_verbosity']['path']
        c_age = cookie['history_verbosity']['max-age']
        c_version = cookie['history_verbosity']['version']

        if k == 'all':
            details_show_all = True
        k = k.split(',')
    k.extend(verbose_list)
    '''
    # Remove any non-existent nzo_ids out of the cookie
    m = [item['nzo_id'] for item in items]
    uniq = [x for x in k if x in m]
    future_cookie = cherrypy.response.cookie
    future_cookie['history_verbosity'] = ','.join(uniq)
    future_cookie['history_verbosity']['path'] = c_path
    future_cookie['history_verbosity']['max-age'] = c_age
    future_cookie['history_verbosity']['version'] = c_version
    '''

    # Reverse the queue to add items to the top (faster than insert)
    items.reverse()
    
    # Add currently in progress items to the queue.
    for nzo in queue:
        t = build_history_info(nzo)
        item = {}
        item['completed'], item['name'], item['nzb_name'], item['category'], item['pp'], item['script'], item['report'], \
            item['url'], item['status'], item['nzo_id'], item['storage'], item['path'], item['script_log'], \
            item['script_line'], item['download_time'], item['postproc_time'], item['stage_log'], \
            item['downloaded'], item['completeness'], item['fail_message'], item['url_info'], item['bytes'] = t
        '''
        if item['status'] != 'Queued':
            item['show_details'] = 'True'
        else:
            item['show_details'] = 'False'
        '''
        item['action_line'] = nzo.get_action_line()
        item = unpack_history_info(item)
        items.append(item)
        
    for item in items:
        if details_show_all:
            item['show_details'] = 'True'
        else:
            if item['nzo_id'] in k:
                item['show_details'] = 'True'
            else:
                item['show_details'] = ''
        if item['bytes']:
            item['size'] = format_bytes(item['bytes'])
        else:
            item['size'] = ''
        
    # Unreverse the queue
    items.reverse()
    
    return (items, total_items)
    
def xml_history(start=None, limit=None):
    items, total_items = build_history(start=start, limit=limit, verbose=True)
    status_lst = []
    status_lst.append('<?xml version="1.0" encoding="UTF-8" ?> \n')
    #Compile the history data
    
    xmlmaker = xml_factory()
    status_lst.append(xmlmaker.run("history",items))
            
    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return ''.join(status_lst)

def json_history(start=None, limit=None):
    #items = {}
    #items['history'],
    items, total_items = build_history(start=start, limit=limit, verbose=True)
    #Compile the history data

    status_str = JsonWriter().write(items)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str


def json_list(section, lst, headers=True):
    """Output a simple list as a JSON object
    """

    i = 0
    d = []
    for item in lst:
        c = {}
        c['id'] = '%s' % i
        c['name'] = item
        i += 1
        d.append(c)
        
    obj = { section : d }
    
    if headers:
        text = JsonWriter().write(obj)
        cherrypy.response.headers['Content-Type'] = "application/json"
        cherrypy.response.headers['Pragma'] = 'no-cache'
        return text
    else:
        return obj


def xml_list(section, keyw, lst):
    """Output a simple list as an XML object
    """
    text= '<?xml version="1.0" encoding="UTF-8" ?> \n<%s>\n' % section
    n = 0
    for cat in lst:
        text += '<%s>\n' % (keyw)
        text += '<id>%s</id>\n' % (n)
        text += '<name>%s</name>\n' % xml_name(cat)
        text += '</%s>\n' % (keyw)
        n+=1

    text += '</%s>' % section

    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return text


class xml_factory:
    """
    Recursive xml string maker. Feed it a mixed tuple/dict/item object and will output into an xml string
    Current limitations: 
        In Two tiered lists hardcoded name of "item": <cat_list><item> </item></cat_list>
        In Three tiered lists hardcoded name of "slot": <tier1><slot><tier2> </tier2></slot></tier1>
    """
    def __init__(self):
        self.__text = ''
        
    
    def tuple(self, keyw, lst, text = ''):
        for item in lst:
            text += self.run(keyw, item)
        return text
    
    def dictn(self, keyw, lst, text = ''):
        for key in lst.keys():
            found = self.run(key,lst[key])
            if found:
                text += found
            else:
                text += '<%s>%s</%s>\n' % (str(key), str(lst[key]), str(key))
                
        if keyw and text:
            return '<%s>%s</%s>\n' % (keyw,text,keyw)
        else:
            return ''
        


    def list(self, keyw, lst, text = ''):
        #deal with lists
        #found = False
        for cat in lst:
            if isinstance(cat, dict):
                #debug = 'dict%s' % n
                text += self.dictn('slot', cat) 
            elif isinstance(cat, list):
                debug = 'list'
                text  += self.list(debug, cat) 
            elif isinstance(cat, tuple):
                debug = 'tuple'
                text += self.tuple(debug, cat) 
            else:
                text += '<item>%s</item>\n' % str(cat)
            
        if keyw and text:
            return '<%s>%s</%s>\n' % (keyw,text,keyw)
        else:    
            return ''
        
    def run(self, keyw, lst):
        if isinstance(lst, dict):
            text = self.dictn(keyw,lst) 
        elif isinstance(lst, list):
            text = self.list(keyw,lst)
        elif isinstance(lst, tuple):
            text = self.tuple(keyw,lst) 
        else:     
            text = ''
        return text
    

def queueStatus(start, limit):
    #gather the queue details
    info, pnfo_list, bytespersec, verboseList, nzo_pages, dictn = build_queue(history=True, start=start, limit=limit)
    text = '<?xml version="1.0" encoding="UTF-8" ?><queue> \n'
    
    #Use xmlmaker to make an xml string out of info which is a tuple that contains lists/strings/dictionaries
    xmlmaker = xml_factory()
    text += xmlmaker.run("mainqueue",info)
    text += "</queue>"
    
    #output in xml with no caching
    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return text

def queueStatusJson(start, limit):
    #gather the queue details
    info = {}
    info['mainqueue'], pnfo_list, bytespersec, verboseList, nzo_pages, dictn = build_queue(history=True, start=start, limit=limit, json_output=True)

    
    status_str = JsonWriter().write(info)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str

def build_queue(web_dir=None, root=None, verbose=False, prim=True, verboseList=[], pages=None,
                dictionary=None, history=False, start=None, limit=None, dummy2=None, json_output=False):
    if dictionary:
        dictn = dictionary
    else:
        dictn = []
    if pages:
        nzo_pages = pages
    else:
        nzo_pages = []
    #build up header full of basic information
    info, pnfo_list, bytespersec = build_header(prim)

    info['isverbose'] = verbose
    if newzbin.USERNAME_NEWZBIN.get() and newzbin.PASSWORD_NEWZBIN.get():
        info['newzbinDetails'] = True

    if int(sabnzbd.CFG['misc']['refresh_rate']) > 0:
        info['refresh_rate'] = sabnzbd.CFG['misc']['refresh_rate']
    else:
        info['refresh_rate'] = ''
        
    info['limit'] = IntConv(dummy2)

    datestart = datetime.datetime.now()

    if json_output:
        info['script_list'] = json_list("scripts", ListScripts(), headers=False)
        info['cat_list'] = json_list("categories", ListCats(), headers=False)
    else:
        info['script_list'] = ListScripts()
        info['cat_list'] = ListCats()
    

    n = 0
    found_active = False
    running_bytes = 0
    slotinfo = []
    nzo_ids = []

    try: limit = int(limit)
    except: limit = 0
    try: start = int(start)
    except: start = 0
    
    
    #Collect nzo's from the history that are downloaded but not finished (repairing, extracting)
    if history:
        slotinfo = get_history()
        #if the specified start value is greater than the amount of history items, do no include the history (used for paging the queue)
        if len(slotinfo) < start:
            slotinfo = []
    else:
        slotinfo = []
        
    info['noofslots'] = len(pnfo_list) + len(slotinfo)
    
    #Paging of the queue using limit and/or start values
    if limit > 0:
        try:
            if start > 0:               
                if start > len(pnfo_list):
                    pnfo_list = []
                else:
                    end = start+limit
                    if start+limit > len(pnfo_list):
                        end = len(pnfo_list)                  
                    pnfo_list = pnfo_list[start:end]
            else:
                if not limit > len(pnfo_list):
                    pnfo_list = pnfo_list[:limit]
        except:
            pass


    for pnfo in pnfo_list:
        repair = pnfo[PNFO_REPAIR_FIELD]
        unpack = pnfo[PNFO_UNPACK_FIELD]
        delete = pnfo[PNFO_DELETE_FIELD]
        script = pnfo[PNFO_SCRIPT_FIELD]
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        cat = pnfo[PNFO_EXTRA_FIELD1]
        if not cat:
            cat = 'None'
        filename = pnfo[PNFO_FILENAME_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD]
        bytes = pnfo[PNFO_BYTES_FIELD]
        average_date = pnfo[PNFO_AVG_DATE_FIELD]
        status = pnfo[PNFO_STATUS_FIELD]
        priority = pnfo[PNFO_PRIORITY_FIELD]
        mbleft = (bytesleft / MEBI)
        mb = (bytes / MEBI)
        if verbose or verboseList:
            finished_files = pnfo[PNFO_FINISHED_FILES_FIELD]
            active_files = pnfo[PNFO_ACTIVE_FILES_FIELD]
            queued_files = pnfo[PNFO_QUEUED_FILES_FIELD]

        nzo_ids.append(nzo_id)

        if web_dir:#DONT WANT TO RUN THIS FOR XML OUTPUT#
            if nzo_id not in dictn:
                dictn[nzo_id] = NzoPage(web_dir, root, nzo_id, prim)
                nzo_pages.append(nzo_id)
            
        slot = {'index':n, 'nzo_id':str(nzo_id)}
        unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)

        slot['unpackopts'] = str(unpackopts)
        if script:
            slot['script'] = script
        else:
            slot['script'] = 'None'
        fn, slot['msgid'] = SplitFileName(filename)
        slot['filename'] = xml_name(fn)
        slot['cat'] = cat
        slot['mbleft'] = "%.2f" % mbleft
        slot['mb'] = "%.2f" % mb
        slot['size'] = "%s" % format_bytes(bytes)
        if not sabnzbd.paused() and status != 'Paused' and status != 'Fetching' and not found_active:
            slot['status'] = "Downloading"
            found_active = True
        else:
            slot['status'] = "%s" % (status)
        if priority == HIGH_PRIORITY or priority == TOP_PRIORITY:
            slot['priority'] = 'High'
        elif priority == LOW_PRIORITY:
            slot['priority'] = 'Low'
        else:
            slot['priority'] = 'Normal'
        if mb == mbleft:
            slot['percentage'] = "0"
        else:
            slot['percentage'] = "%s" % (int(((mb-mbleft) / mb) * 100))
            
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
        slot['verbosity'] = ""
        if web_dir:
            finished = []
            active = []
            queued = []
            if verbose or nzo_id in verboseList:#this will list files in the xml output, wanted yes/no?
                slot['verbosity'] = "True"
                for tup in finished_files:
                    bytes_left, bytes, fn, date = tup
                    fn = xml_name(fn)
    
                    age = calc_age(date)
    
                    line = {'filename':str(fn),
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size':'%s' % (format_bytes(bytes)),
                            'age':age}
                    finished.append(line)
    
                for tup in active_files:
                    bytes_left, bytes, fn, date, nzf_id = tup
                    fn = xml_name(fn)
    
                    age = calc_age(date)
    
                    line = {'filename':str(fn),
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size':'%s' % (format_bytes(bytes)),
                            'nzf_id':nzf_id,
                            'age':age}
                    active.append(line)
    
                for tup in queued_files:
                    _set, bytes_left, bytes, fn, date = tup
                    fn = xml_name(fn)
    
                    age = calc_age(date)
    
                    line = {'filename':str(fn), 'set':_set,
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size':'%s' % (format_bytes(bytes)),
                            'age':age}
                    queued.append(line)

            slot['finished'] = finished
            slot['active'] = active
            slot['queued'] = queued

        slotinfo.append(slot)
        n += 1

    if slotinfo:
        info['slotinfo'] = slotinfo
    else:
        info['slotinfo'] = ''
        verboseList = []
        if web_dir: #DONT WANT TO RUN THIS FOR XML OUTPUT#
            for nzo_id in nzo_pages[:]:
                if nzo_id not in nzo_ids:
                    nzo_pages.remove(nzo_id)
                    dictn.pop(nzo_id)

    return info, pnfo_list, bytespersec, verboseList, nzo_pages, dictn


#depreciated
def xmlSimpleDict(keyw,lst):
    """
    Output a simple dictionary as an XML string
    """

    text = '<%s>' % (keyw)
    for key in lst.keys():
        text += '<%s>%s</%s>\n' % (escape(key),escape(lst[key]),escape(key))
    text += '</%s>' % keyw
    return text

def rss_qstatus():
    """ Return a RSS feed with the queue status
    """
    qnfo = sabnzbd.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    rss = RSS()
    rss.channel.title = "SABnzbd Queue"
    rss.channel.description = "Overview of current downloads"
    rss.channel.link = "http://%s:%s/sabnzbd/queue" % ( \
        sabnzbd.CFG['misc']['host'], sabnzbd.CFG['misc']['port'] )
    rss.channel.language = "en"

    item = Item()
    item.title  = "Total ETA: " + calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], sabnzbd.bps()) + " - "
    item.title += "Queued: %.2f MB - " % (qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI)
    item.title += "Speed: %.2f kB/s" % (sabnzbd.bps() / KIBI)
    rss.addItem(item)

    sum_bytesleft = 0
    for pnfo in pnfo_list:
        filename, msgid = SplitFileName(pnfo[PNFO_FILENAME_FIELD])
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        mbleft = (bytesleft / MEBI)
        mb = (bytes / MEBI)
        
        
        if mb == mbleft:
            percentage = "0%"
        else:
            percentage = "%s%%" % (int(((mb-mbleft) / mb) * 100))
            
        filename = xml_name(filename)
        name = u'%s (%s)' % (filename, percentage)

        item = Item()
        item.title = name
        if msgid:
            item.link    = "https://newzbin.com/browse/post/%s/" % msgid
        else:
            item.link    = "http://%s:%s/sabnzbd/history" % ( \
            sabnzbd.CFG['misc']['host'], sabnzbd.CFG['misc']['port'] )
        statusLine  = ""
        statusLine += '<tr>'
        #Total MB/MB left
        statusLine +=  '<dt>Remain/Total: %.2f/%.2f MB</dt>' % (bytesleft, bytes)
        #ETA
        sum_bytesleft += pnfo[PNFO_BYTES_LEFT_FIELD]
        statusLine += "<dt>ETA: %s </dt>" % calc_timeleft(sum_bytesleft, sabnzbd.bps())
        statusLine += "<dt>Age: %s</dt>" % calc_age(pnfo[PNFO_AVG_DATE_FIELD])
        statusLine += "</tr>"
        item.description = statusLine
        rss.addItem(item)

    rss.channel.lastBuildDate = std_time(time.time())
    rss.channel.pubDate = rss.channel.lastBuildDate
    rss.channel.ttl = "1"
    return rss.write()


def json_result(result, data):
    """ Return data in a json structure
    """
    dict = { 'status' : result }
    if data != None:
        dict['value'] = data

    status_str = JsonWriter().write(dict)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str


def xml_result(result, data):
    """ Return data as XML
    """
    return "Not yet implemented\n"
