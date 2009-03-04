#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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
from sabnzbd.utils.servertests import test_nntp_server
import sabnzbd
import sabnzbd.rss
import sabnzbd.scheduler as scheduler

from sabnzbd.utils import listquote
from sabnzbd.utils.configobj import ConfigObj
from Cheetah.Template import Template
import sabnzbd.email as email
from sabnzbd.misc import real_path, create_real_path, loadavg, \
     to_units, from_units, SameFile, diskfree, disktotal, get_ext, get_filename
from sabnzbd.newswrapper import GetServerParms
import sabnzbd.newzbin as newzbin
from sabnzbd.codecs import TRANS, xml_name
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.articlecache as articlecache
import sabnzbd.newsunpack
import sabnzbd.postproc as postproc
import sabnzbd.downloader as downloader
import sabnzbd.bpsmeter as bpsmeter
import sabnzbd.nzbqueue as nzbqueue
from sabnzbd.database import get_history_handle, build_history_info, unpack_history_info

from sabnzbd.constants import *

#------------------------------------------------------------------------------
# Global constants

DIRECTIVES = {'directiveStartToken': '<!--#', 'directiveEndToken': '#-->'}
RESTART_MSG1 = '''
Initiating restart...
'''
RESTART_MSG2 = '''
<br/>SABnzbd shutdown finished.
<br/>Wait for about 5 second and then click the button below.
<br/><br/><strong><a href="..">Refresh</a></strong>
'''

#------------------------------------------------------------------------------
#
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
    dd = cfg.SCRIPT_DIR.get_path()

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


def Raiser(root, **kwargs):
    args_copy = kwargs.copy()
    for key, value in args_copy.iteritems():
        if value == None:
            kwargs.pop(key)
    root = '%s?%s' % (root, urllib.urlencode(kwargs))
    return cherrypy.HTTPRedirect(root)

def dcRaiser(root, kwargs):
    if '_dc' in kwargs:
        return Raiser(root, _dc=kwargs['_dc'])
    else:
        return Raiser(root)

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

def Strip(txt):
    """ Return stripped string, can handle None """
    try:
        return txt.strip()
    except:
        return None


#------------------------------------------------------------------------------
# Web login support
def get_users():
    users = {}
    users[cfg.USERNAME.get()] = cfg.PASSWORD.get()
    return users

def encrypt_pwd(pwd):
    return pwd


def set_auth(conf):
    """ Set the authentication for CherryPy
    """
    if cfg.USERNAME.get():
        conf.update({'tools.basic_auth.on' : True, 'tools.basic_auth.realm' : 'SABnzbd',
                            'tools.basic_auth.users' : get_users, 'tools.basic_auth.encrypt' : encrypt_pwd})
        conf.update({'/api':{'tools.basic_auth.on' : False},
                     '/m/api':{'tools.basic_auth.on' : False},
                     '/sabnzbd/api':{'tools.basic_auth.on' : False},
                     '/sabnzbd/m/api':{'tools.basic_auth.on' : False},
                     })
    else:
        conf.update({'tools.basic_auth.on':False})



#------------------------------------------------------------------------------
class NoPage:
    def __init__(self):
        pass

    @cherrypy.expose
    def index(self, **kwargs):
        return badParameterResponse('Error: No secondary interface defined.')


#------------------------------------------------------------------------------
class MainPage:
    def __init__(self, web_dir, root, web_dir2=None, root2=None, prim=True, first=0):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        if first >= 1:
            self.m = MainPage(web_dir2, root2, prim=False)
        if first == 2:
            self.sabnzbd = MainPage(web_dir, '/sabnzbd/', web_dir2, '/sabnzbd/m/', prim=True, first=1)
        self.queue = QueuePage(web_dir, root+'queue/', prim)
        self.history = HistoryPage(web_dir, root+'history/', prim)
        self.connections = ConnectionInfo(web_dir, root+'connections/', prim)
        self.config = ConfigPage(web_dir, root+'config/', prim)
        self.nzb = NzoPage(web_dir, root+'nzb/', prim)
        self.wizard = Wizard(web_dir, root+'wizard/', prim)


    @cherrypy.expose
    def index(self, _dc=None, skip_wizard=False):
        # IMPORTANT: Remove the 'not' when done testing
        if skip_wizard or config.get_servers():
            info, pnfo_list, bytespersec = build_header(self.__prim)

            if cfg.USERNAME_NEWZBIN.get() and cfg.PASSWORD_NEWZBIN.get_stars():
                info['newzbinDetails'] = True

            info['script_list'] = ListScripts(default=True)
            info['script'] = cfg.DIRSCAN_SCRIPT.get()

            info['cat'] = 'Default'
            info['cat_list'] = ListCats(True)

            info['warning'] = ""

            if not sabnzbd.newsunpack.PAR2_COMMAND:
                info['warning'] += "No PAR2 program found, repairs not possible<br/>"

            template = Template(file=os.path.join(self.__web_dir, 'main.tmpl'),
                                searchList=[info], compilerSettings=DIRECTIVES)
            return template.respond()
        else:
            # Redirect to the setup wizard
            raise cherrypy.HTTPRedirect('/wizard/')


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
        downloader.pause_downloader()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def resume(self, _dc = None):
        downloader.resume_downloader()
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
               try_list: %s''' % nzbqueue.debug()

    @cherrypy.expose
    def rss(self, mode='history', limit=50, search=None):
        url = cherrypy.url()
        if mode == 'history':
            return rss_history(url, limit=limit, search=search)
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
        if cfg.USERNAME.get() and cfg.PASSWORD.get():
            ma_username = kwargs.get('ma_username')
            ma_password = kwargs.get('ma_password')
            if not (ma_password == cfg.PASSWORD.get() and ma_username == cfg.USERNAME.get()):
                return "Missing authentication"

        return self.api_handler(kwargs)


    def api_handler(self, kwargs):
        """ Actual API handler, not exposed to Web-ui
        """
        mode = kwargs.get('mode')
        output = kwargs.get('output')

        if mode == 'set_config':
            res = config.set_config(kwargs)
            if output == 'json':
                return json_result(res)
            elif output == 'xml':
                return xml_result(res)
            else:
                return 'not implemented\n'

        if mode == 'get_config':
            res, data = config.get_dconfig(kwargs)
            if output == 'json':
                return json_result(res, kwargs.get('section'), kwargs.get('keyword'), data)
            elif output == 'xml':
                return xml_result(res, kwargs.get('section'), kwargs.get('keyword'), data)
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
            name = kwargs.get('name')
            sort = kwargs.get('sort')
            dir = kwargs.get('dir')
            value = kwargs.get('value')
            value2 = kwargs.get('value2')
            start = kwargs.get('start')
            limit = kwargs.get('limit')

            if output == 'xml':
                if sort and sort != 'index':
                    reverse=False
                    if dir.lower() == 'desc':
                        reverse=True
                    nzbqueue.sort_queue(sort,reverse)
                return queueStatus(start,limit)
            elif output == 'json':
                if sort and sort != 'index':
                    reverse=False
                    if dir.lower() == 'desc':
                        reverse=True
                    nzbqueue.sort_queue(sort,reverse)
                return queueStatusJson(start,limit)
            elif output == 'rss':
                return rss_qstatus()
            elif name == 'delete':
                if value.lower()=='all':
                    nzbqueue.remove_all_nzo()
                    return 'ok\n'
                elif value:
                    items = value.split(',')
                    nzbqueue.remove_multiple_nzos(items, False)
                    return 'ok\n'
                else:
                    return 'error\n'
            elif name == 'delete_nzf':
                # Value = nzo_id Value2 = nzf_id
                if value and value2:
                    nzbqueue.remove_nzf(value, value2)
                    return 'ok\n'
                else:
                    return 'error: specify the nzo id\'s in the value param and nzf_id in value2 param\n'
            elif name == 'rename':
                if value and value2:
                    nzbqueue.rename_nzo(value, value2)
                else:
                    return 'error\n'
            elif name == 'change_complete_action':
                # http://localhost:8080/sabnzbd/api?mode=queue&name=change_complete_action&value=hibernate_pc
                sabnzbd.change_queue_complete_action(value)
                return 'ok\n'
            elif name == 'purge':
                nzbqueue.remove_all_nzo()
                return 'ok\n'
            elif name == 'pause':
                if value:
                    items = value.split(',')
                    nzbqueue.pause_multiple_nzo(items)
            elif name == 'resume':
                if value:
                    items = value.split(',')
                    nzbqueue.resume_multiple_nzo(items)
            elif name == 'priority':
                if value and value2:
                    try:
                        try:
                            priority = int(value2)
                        except:
                            return 'error: please enter an integer for the priority'
                        items = value.split(',')
                        if len(items) > 1:
                            pos = nzbqueue.set_priority_multiple(items, priority)
                        else:
                            pos = nzbqueue.set_priority(value, priority)
                        # Returns the position in the queue
                        return str(pos)
                    except:
                        return 'error: correct usage: &value=NZO_ID&value2=PRIORITY_VALUE'
                else:
                    return 'error: correct usage: &value=NZO_ID&value2=PRIORITY_VALUE'
            elif name == 'sort':
                if sort:
                    nzbqueue.sort_queue(sort,dir)
                    return 'ok\n'
                else:
                    return 'error: correct usage: &sort=name&dir=asc'

            else:
                return 'not implemented\n'

        name = kwargs.get('name')
        pp = kwargs.get('pp')
        script = kwargs.get('script')
        cat = kwargs.get('cat')
        priority = kwargs.get('priority')
        value = kwargs.get('value')
        value2 = kwargs.get('value2')
        start = kwargs.get('start')
        limit = kwargs.get('limit')

        if mode == 'addfile':
            # When uploading via flash it will send the nzb in a kw arg called Filedata
            flash_upload = kwargs.get('Filedata', '')
            if flash_upload:
                name = flash_upload
            # Normal upload will send the nzb in a kw arg called nzbfile
            normal_upload = kwargs.get('nzbfile', '')
            if normal_upload:
                name = normal_upload
                
            if name.filename and name.value:
                sabnzbd.add_nzbfile(name, pp, script, cat, priority)
                return 'ok\n'
            else:
                return 'error\n'

        if mode == 'addlocalfile':
            if name:
                if os.path.exists(name):
                    fn = get_filename(name)
                    if fn:
                        if get_ext(name) in ('.zip','.rar', '.gz'):
                            sabnzbd.dirscanner.ProcessArchiveFile(\
                                fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True)
                        elif get_ext(name) in ('.nzb'):
                            sabnzbd.dirscanner.ProcessSingleFile(\
                                fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True)
                    else:
                        return 'error: no filename found'
                else:
                    return 'error: path does not exist'
                return 'ok\n'
            else:
                return 'error\n'

        if mode == 'switch':
            if value and value2:
                pos, prio = nzbqueue.switch(value, value2)
                # Returns the new position and new priority (if different)
                return '%s %s' % (pos, prio)
            else:
                return 'error\n'


        if mode == 'change_cat':
            if value and value2:
                nzo_id = value
                cat = value2
                if cat == 'None':
                    cat = None
                nzbqueue.change_cat(nzo_id, cat)
                item = config.get_config('categories', cat)
                if item:
                    script = item.script.get()
                    pp = item.pp.get()
                else:
                    script = cfg.DIRSCAN_SCRIPT.get()
                    pp = cfg.DIRSCAN_PP.get()

                nzbqueue.change_script(nzo_id, script)
                nzbqueue.change_opts(nzo_id, pp)
                return 'ok\n'
            else:
                return 'error\n'

        if mode == 'change_script':
            if value and value2:
                nzo_id = value
                script = value2
                if script == 'None':
                    script = None
                nzbqueue.change_script(nzo_id, script)
                return 'ok\n'
            else:
                return 'error\n'

        if mode == 'change_opts':
            if value and value2 and value2.isdigit():
                nzbqueue.change_opts(value, int(value2))

        if mode == 'fullstatus':
            if output == 'xml':
                return 'not implemented YET\n' #xml_full()
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
            downloader.pause_downloader()
            return 'ok\n'

        if mode == 'resume':
            downloader.resume_downloader()
            return 'ok\n'

        if mode == 'shutdown':
            sabnzbd.halt()
            cherrypy.engine.exit()
            sabnzbd.SABSTOP = True
            return 'ok\n'

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
                    try:
                        value = int(value)
                    except:
                        return 'error: Please submit a value\n'
                    downloader.limit_speed(value)
                    return 'ok\n'
                else:
                    return 'error: Please submit a value\n'
            elif name == 'get_speedlimit':
                return str(int(downloader.get_limit()))
            elif name == 'set_colorscheme':
                if value:
                    if self.__prim:
                        cfg.WEB_COLOR.set(value)
                    else:
                        cfg.WEB_COLOR2.set(value)
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
                return str(sabnzbd.__version__)

        if mode == 'newzbin':
            if name == 'get_bookmarks':
                newzbin.getBookmarksNow()
                return 'ok\n'
            return 'not implemented\n'

        if mode == 'restart':
            sabnzbd.halt()
            cherrypy.engine.restart()
            return 'ok\n'

        return 'not implemented\n'

    @cherrypy.expose
    def scriptlog(self, name=None, _dc=None):
        """ Duplicate of scriptlog of History, needed for some skins """
        if name:
            history_db = cherrypy.thread_data.history_db
            return ShowString(history_db.get_name(name), history_db.get_script_log(name))
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
            raise Raiser(self.__root, _dc=_dc)

class Wizard:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        # Get the path for the folder named wizard
        self.__web_dir = sabnzbd.WIZARD_DIR
        self.__prim = prim
        self.info = {'webdir': sabnzbd.WIZARD_DIR,
                     'steps':5, 'version':sabnzbd.__version__}

    @cherrypy.expose
    def index(self, **kwargs):
        info = self.info.copy()
        info['num'] = 'One'
        info['number'] = 1
        info['skin'] = cfg.WEB_DIR.get().lower()

        if not os.path.exists(self.__web_dir):
            # If the wizard folder does not exist, simply load the normal page
            raise cherrypy.HTTPRedirect('')
        else:
            template = Template(file=os.path.join(self.__web_dir, 'index.html'),
                                searchList=[info], compilerSettings=DIRECTIVES)
            return template.respond()

    @cherrypy.expose
    def two(self, **kwargs):
        # Save skin setting
        if kwargs:
            if 'skin' in kwargs:
                change_web_dir(kwargs['skin'])

        info = self.info.copy()
        info['num'] = 'Two'
        info['number'] = 2

        host = cfg.CHERRYHOST.get()
        info['host'] = host
        # Allow special operation if host is not one of the defaults
        if host not in ('localhost','0.0.0.0'):
            info['custom_host'] = True
        else:
            info['custom_host'] = False

        info['enable_https'] = cfg.ENABLE_HTTPS.get()
        info['autobrowser'] = cfg.AUTOBROWSER.get()

        template = Template(file=os.path.join(self.__web_dir, 'two.html'),
                            searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def three(self, **kwargs):
        # Save access/autobrowser/autostart
        if kwargs:
            if 'access' in kwargs:
                cfg.CHERRYHOST.set(kwargs['access'])
            cfg.AUTOBROWSER.set(kwargs.get('autobrowser',0))
        info = self.info.copy()
        info['num'] = 'Three'
        info['number'] = 3

        servers = config.get_servers()
        if not servers:
            info['host'] = ''
            info['port'] = ''
            info['username'] = ''
            info['password'] = ''
            info['connections'] = ''
            info['ssl'] = 0
        else:
            for server in servers:
                # If there are multiple servers, just use the first enabled one
                s = servers[server]
                info['host'] = s.host.get()
                info['port'] = s.port.get()
                info['username'] = s.username.get()
                info['password'] = s.password.get_stars()
                info['connections'] = s.connections.get()
                info['ssl'] = s.ssl.get()
                if s.enable.get():
                    break
        template = Template(file=os.path.join(self.__web_dir, 'three.html'),
                            searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def four(self, **kwargs):
        # Save server details
        if kwargs:
            kwargs['enable'] = 1
            handle_server(kwargs)

        info = self.info.copy()
        info['num'] = 'Four'
        info['number'] = 4
        info['newzbin_user'] = cfg.USERNAME_NEWZBIN.get()
        info['newzbin_pass'] = cfg.PASSWORD_NEWZBIN.get_stars()
        info['newzbin_bookmarks'] = cfg.NEWZBIN_BOOKMARKS.get()
        info['matrix_user'] = cfg.USERNAME_MATRIX.get()
        info['matrix_pass'] = cfg.PASSWORD_MATRIX.get_stars()
        template = Template(file=os.path.join(self.__web_dir, 'four.html'),
                            searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def five(self, **kwargs):
        # Save server details
        if kwargs:
            if 'newzbin_user' in kwargs and 'newzbin_pass' in kwargs:
                cfg.USERNAME_NEWZBIN.set(kwargs.get('newzbin_user',''))
                cfg.PASSWORD_NEWZBIN.set(kwargs.get('newzbin_pass',''))
            cfg.NEWZBIN_BOOKMARKS.set(kwargs.get('newzbin_bookmarks', '0'))
            if 'matrix_user' in kwargs and 'matrix_pass' in kwargs:
                cfg.USERNAME_MATRIX.set(kwargs.get('matrix_user',''))
                cfg.PASSWORD_MATRIX.set(kwargs.get('matrix_pass',''))

        config.save_config()

        info = self.info.copy()
        info['num'] = 'Five'
        info['number'] = 5
        info['helpuri'] = 'http://sabnzbd.wikidot.com/'
        # Access_url is used to provide the user a link to sabnzbd depending on the host
        access_uri = 'localhost'
        cherryhost = cfg.CHERRYHOST.get()
        if cherryhost == '0.0.0.0':
            import socket
            # Grab a list of all ips for the hostname
            host = socket.gethostname()
            addr = socket.gethostbyname_ex(host)[2]
            if cherrypy.request.headers.has_key('host') and \
               not 'localhost' in cherrypy.request.headers['host']:
                access_uri = host
                socks = [host]
            else:
                socks = ['localhost', host]
            socks.extend(addr)
        elif not cherryhost:
            import socket
            socks = [socket.gethostname()]
        else:
            socks = [cherryhost]
        info['urls'] = []
        for sock in socks:
            if sock:
                if cfg.ENABLE_HTTPS.get():
                    url = 'https://%s:%s/sabnzbd/' % (sock, cfg.HTTPS_PORT.get())
                else:
                    url = 'http://%s:%s/sabnzbd/' % (sock, cfg.CHERRYPORT.get())
                    
                info['urls'].append(url)
                
        if cfg.ENABLE_HTTPS.get():
            info['access_url'] = 'https://%s:%s/sabnzbd/' % (access_uri, cfg.HTTPS_PORT.get())
        else:
            info['access_url'] = 'http://%s:%s/sabnzbd/' % (access_uri, cfg.CHERRYPORT.get())

        template = Template(file=os.path.join(self.__web_dir, 'five.html'),
                            searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def servertest(self, **kwargs):
        # Grab the host/port/user/pass/connections/ssl
        host = kwargs.get('host','')
        if not host:
            return 'Hostname not set'
        username = kwargs.get('username',None)
        password = kwargs.get('password',None)
        connections = IntConv(kwargs.get('connections',0))
        if not connections:
            return 'Connections not set'
        ssl = IntConv(kwargs.get('ssl',0))
        port = IntConv(kwargs.get('port',0))
        if not port:
            if ssl:
                port = 563
            else:
                port = 119


        return test_nntp_server(host, port, username=username, \
                                password=password, ssl=ssl)


#------------------------------------------------------------------------------
class NzoPage:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__prim = prim
        self.__cached_selection = {} #None

    @cherrypy.expose
    def default(self, *args, **kwargs):
        # Allowed URL's
        # /nzb/SABnzbd_nzo_xxxxx/
        # /nzb/SABnzbd_nzo_xxxxx/details
        # /nzb/SABnzbd_nzo_xxxxx/files
        # /nzb/SABnzbd_nzo_xxxxx/bulk_operation
        # /nzb/SABnzbd_nzo_xxxxx/save

        info, pnfo_list, bytespersec = build_header(self.__prim)
        nzo_id = None

        for a in args:
            if a.startswith('SABnzbd_nzo'):
                nzo_id = a

        if nzo_id:
            # /SABnzbd_nzo_xxxxx/bulk_operation
            if 'bulk_operation' in args:
                return self.bulk_operation(nzo_id, kwargs)

            # /SABnzbd_nzo_xxxxx/details
            elif 'details' in args:
                info =  self.nzo_details(info, pnfo_list, nzo_id)

            # /SABnzbd_nzo_xxxxx/files
            elif 'files' in args:
                info =  self.nzo_files(info, pnfo_list, nzo_id)

            # /SABnzbd_nzo_xxxxx/save
            elif 'save' in args:
                self.save_details(nzo_id, args, kwargs)
                return

            # /SABnzbd_nzo_xxxxx/
            else:
                info =  self.nzo_details(info, pnfo_list, nzo_id)
                info =  self.nzo_files(info, pnfo_list, nzo_id)

        template = Template(file=os.path.join(self.__web_dir, 'nzo.tmpl'),
                            searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()


    def nzo_details(self, info, pnfo_list, nzo_id):
        slot = {}
        for pnfo in pnfo_list:
            if pnfo[PNFO_NZO_ID_FIELD] == nzo_id:
                repair = pnfo[PNFO_REPAIR_FIELD]
                unpack = pnfo[PNFO_UNPACK_FIELD]
                delete = pnfo[PNFO_DELETE_FIELD]
                unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)
                script = pnfo[PNFO_SCRIPT_FIELD]
                cat = pnfo[PNFO_EXTRA_FIELD1]
                if not cat:
                    cat = 'None'
                filename = pnfo[PNFO_FILENAME_FIELD]
                priority = pnfo[PNFO_PRIORITY_FIELD]

                slot['nzo_id'] =  str(nzo_id)
                slot['cat'] = cat
                slot['filename'] = filename
                slot['script'] = script
                slot['priority'] = str(priority)
                slot['unpackopts'] = str(unpackopts)

        info['slot'] = slot
        info['script_list'] = ListScripts()
        info['cat_list'] = ListCats()

        return info

    def nzo_files(self, info, pnfo_list, nzo_id):

        active = []
        for pnfo in pnfo_list:
            if pnfo[PNFO_NZO_ID_FIELD] == nzo_id:
                info['nzo_id'] = nzo_id
                info['filename'] = xml_name(pnfo[PNFO_FILENAME_FIELD])

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
        return info


    def save_details(self, nzo_id, args, kwargs):
        name = kwargs.get('name',None)
        pp = kwargs.get('pp',None)
        script = kwargs.get('script',None)
        cat = kwargs.get('cat',None)
        priority = kwargs.get('priority',None)

        if name != None:
            sabnzbd.nzbqueue.change_name(nzo_id, name)
        if cat != None:
            sabnzbd.nzbqueue.change_cat(nzo_id,cat)
        if script != None:
            sabnzbd.nzbqueue.change_script(nzo_id,script)
        if pp != None:
            sabnzbd.nzbqueue.change_opts(nzo_id,pp)
        if priority != None:
            sabnzbd.nzbqueue.set_priority(nzo_id, priority)

        args = [arg for arg in args if arg != 'save']
        extra = '/'.join(args)
        url = cherrypy._urljoin(self.__root,extra)
        if url and not url.endswith('/'):
            url += '/'
        raise dcRaiser(url, {})

    def bulk_operation(self, nzo_id, kwargs):
        self.__cached_selection = kwargs
        if kwargs['action_key'] == 'Delete':
            for key in kwargs:
                if kwargs[key] == 'on':
                    nzbqueue.remove_nzf(nzo_id, key)

        elif kwargs['action_key'] == 'Top' or kwargs['action_key'] == 'Up' or \
             kwargs['action_key'] == 'Down' or kwargs['action_key'] == 'Bottom':
            nzf_ids = []
            for key in kwargs:
                if kwargs[key] == 'on':
                    nzf_ids.append(key)
            if kwargs['action_key'] == 'Top':
                nzbqueue.move_top_bulk(nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Up':
                nzbqueue.move_up_bulk(nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Down':
                nzbqueue.move_down_bulk(nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Bottom':
                nzbqueue.move_bottom_bulk(nzo_id, nzf_ids)

        url = cherrypy._urljoin(self.__root,nzo_id)
        if url and not url.endswith('/'):
            url += '/'
        raise dcRaiser(url, kwargs)

#------------------------------------------------------------------------------
class QueuePage:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verboseList = []
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None, start=None, limit=None, dummy2=None):

        info, pnfo_list, bytespersec, self.__verboseList, self.__dict__ = build_queue(self.__web_dir, self.__root, self.__verbose, self.__prim, self.__verboseList, self.__dict__, start=start, limit=limit, dummy2=dummy2)

        template = Template(file=os.path.join(self.__web_dir, 'queue.tmpl'),
                            searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()



    @cherrypy.expose
    def delete(self, uid = None, _dc = None, start=None, limit=None):
        if uid:
            nzbqueue.remove_nzo(uid, False)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def purge(self, _dc = None, start=None, limit=None):
        nzbqueue.remove_all_nzo()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def removeNzf(self, nzo_id = None, nzf_id = None, _dc = None, start=None, limit=None):
        if nzo_id and nzf_id:
            nzbqueue.remove_nzf(nzo_id, nzf_id)
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
            nzbqueue.switch(uid1, uid2)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def change_opts(self, nzo_id = None, pp = None, _dc = None, start=None, limit=None):
        if nzo_id and pp and pp.isdigit():
            nzbqueue.change_opts(nzo_id, int(pp))
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def change_script(self, nzo_id = None, script = None, _dc = None, start=None, limit=None):
        if nzo_id and script:
            if script == 'None':
                script = None
            nzbqueue.change_script(nzo_id, script)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def change_cat(self, nzo_id = None, cat = None, _dc = None, start=None, limit=None):
        if nzo_id and cat:
            if cat == 'None':
                cat = None
            nzbqueue.change_cat(nzo_id, cat)
            item = config.get_config('categories', cat)
            if item:
                script = item.script.get()
                pp = item.pp.get()
            else:
                script = cfg.DIRSCAN_SCRIPT.get()
                pp = cfg.DIRSCAN_PP.get()

            nzbqueue.change_script(nzo_id, script)
            nzbqueue.change_opts(nzo_id, pp)

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
        downloader.pause_downloader()
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def resume(self, _dc = None, start=None, limit=None):
        downloader.resume_downloader()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def pause_nzo(self, uid=None, _dc = None, start=None, limit=None):
        items = uid.split(',')
        nzbqueue.pause_multiple_nzo(items)
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def resume_nzo(self, uid=None, _dc = None, start=None, limit=None):
        items = uid.split(',')
        nzbqueue.resume_multiple_nzo(items)
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def set_priority(self, nzo_id=None, priority=None, _dc = None, start=None, limit=None):
        nzbqueue.set_priority(nzo_id, priority)
        raise Raiser(self.__root,_dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def sort_by_avg_age(self, _dc = None, start=None, limit=None, dir=None):
        nzbqueue.sort_queue('avg_age',dir)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def sort_by_name(self, _dc = None, start=None, limit=None, dir=None):
        nzbqueue.sort_queue('name',dir)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def sort_by_size(self, _dc = None, start=None, limit=None, dir=None):
        nzbqueue.sort_queue('size',dir)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit)

    @cherrypy.expose
    def set_speedlimit(self, _dc = None, value=None):
        downloader.limit_speed(IntConv(value))
        raise Raiser(self.__root, _dc=_dc)

class HistoryPage:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verbose_list = []
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None, start=None, limit=None, dummy2=None, search=None):
        history, pnfo_list, bytespersec = build_header(self.__prim)

        history['isverbose'] = self.__verbose

        if cfg.USERNAME_NEWZBIN.get() and cfg.PASSWORD_NEWZBIN.get():
            history['newzbinDetails'] = True

        #history_items, total_bytes, bytes_beginning = sabnzbd.history_info()
        #history['bytes_beginning'] = "%.2f" % (bytes_beginning / GIGI)

        history['total_size'], history['month_size'], history['week_size'] = get_history_size()

        history['lines'], history['fetched'], history['noofslots'] = build_history(limit=limit, start=start, verbose=self.__verbose, verbose_list=self.__verbose_list, search=search)

        if search:
            history['search'] = escape(search)
        else:
            history['search'] = ''

        history['start'] = IntConv(start)
        history['limit'] = IntConv(limit)
        history['finish'] = history['start'] + history['limit']
        if history['finish'] > history['noofslots']:
            history['finish'] = history['noofslots']
        if not history['finish']:
            history['finish'] = history['fetched']


        template = Template(file=os.path.join(self.__web_dir, 'history.tmpl'),
                            searchList=[history], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def purge(self, _dc = None, start=None, limit=None, search=None):
        history_db = cherrypy.thread_data.history_db
        history_db.remove_history()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit, search=search)

    @cherrypy.expose
    def delete(self, job=None, _dc = None, start=None, limit=None, search=None):
        if job:
            jobs = job.split(',')
            history_db = cherrypy.thread_data.history_db
            history_db.remove_history(jobs)
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit, search=search)

    @cherrypy.expose
    def purge_failed(self, _dc = None, start=None, limit=None, search=None):
        history_db = cherrypy.thread_data.history_db
        history_db.remove_failed()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit, search=search)

    @cherrypy.expose
    def reset(self, _dc = None, start=None, limit=None, search=None):
        #sabnzbd.reset_byte_counter()
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit, search=search)

    @cherrypy.expose
    def tog_verbose(self, _dc = None, start=None, limit=None, jobs=None, search=None):
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
        raise Raiser(self.__root, _dc=_dc, start=start, limit=limit, search=search)

    @cherrypy.expose
    def scriptlog(self, name=None, _dc=None, start=None, limit=None, search=None):
        """ Duplicate of scriptlog of History, needed for some skins """
        if name:
            history_db = cherrypy.thread_data.history_db
            return ShowString(history_db.get_name(name), history_db.get_script_log(name))
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
            raise Raiser(self.__root, _dc=_dc)

#------------------------------------------------------------------------------
class ConfigPage:
    def __init__(self, web_dir, root, prim):
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
        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['configfn'] = config.get_filename()

        new = {}
        for svr in config.get_servers():
            new[svr] = {}
        conf['servers'] = new

        template = Template(file=os.path.join(self.__web_dir, 'config.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def restart(self, **kwargs):
        yield RESTART_MSG1
        sabnzbd.halt()
        yield RESTART_MSG2
        cherrypy.engine.restart()


#------------------------------------------------------------------------------
LIST_DIRPAGE = ( \
    'download_dir', 'download_free', 'complete_dir', 'cache_dir',
    'nzb_backup_dir', 'dirscan_dir', 'dirscan_speed', 'script_dir',
    'email_dir', 'permissions', 'log_dir'
    )

class ConfigDirectories:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        for kw in LIST_DIRPAGE:
            conf[kw] = config.get_config('misc', kw).get()

        conf['my_home'] = sabnzbd.DIR_HOME
        conf['my_lcldata'] = sabnzbd.DIR_LCLDATA

        # Temporary fix, problem with build_header
        conf['restart_req'] = sabnzbd.RESTART_REQ

        template = Template(file=os.path.join(self.__web_dir, 'config_directories.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveDirectories(self, **kwargs):

        for kw in LIST_DIRPAGE:
            value = kwargs.get(kw)
            if value != None:
                msg = config.get_config('misc', kw).set(value)
                if msg:
                    return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


SWITCH_LIST = \
    ('par_option', 'enable_unrar', 'enable_unzip', 'enable_filejoin',
     'enable_tsjoin', 'send_group', 'fail_on_crc', 'top_only',
     'dirscan_opts', 'enable_par_cleanup', 'auto_sort', 'check_new_rel', 'auto_disconnect',
     'safe_postproc', 'no_dupes', 'replace_spaces', 'replace_illegal', 'auto_browser',
     'ignore_samples', 'pause_on_post_processing', 'quick_check', 'dirscan_script', 'nice', 'ionice'
    )

#------------------------------------------------------------------------------
class ConfigSwitches:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['nt'] = os.name == 'nt'
        conf['have_nice'] = bool(sabnzbd.newsunpack.NICE_COMMAND)
        conf['have_ionice'] = bool(sabnzbd.newsunpack.IONICE_COMMAND)

        for kw in SWITCH_LIST:
            conf[kw] = config.get_config('misc', kw).get()

        conf['script_list'] = ListScripts()

        template = Template(file=os.path.join(self.__web_dir, 'config_switches.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveSwitches(self, **kwargs):

        for kw in SWITCH_LIST:
            item = config.get_config('misc', kw)
            value = kwargs.get(kw)
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


#------------------------------------------------------------------------------
LIST_GENERAL = (
    'host', 'port', 'username', 'password',
    'bandwith_limit', 'refresh_rate', 'rss_rate',
    'cache_limit', 'web_dir', 'web_dir2',
    'cleanup_list'
    )

class ConfigGeneral:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        def ListColors(web_dir):
            lst = []
            web_dir = os.path.join(sabnzbd.DIR_INTERFACES ,web_dir)
            dd = os.path.abspath(web_dir + '/templates/static/stylesheets/colorschemes')
            if (not dd) or (not os.access(dd, os.R_OK)):
                return lst
            for color in glob.glob(dd + '/*'):
                col= os.path.basename(color).replace('.css','')
                if col != "_svn" and col != ".svn":
                    lst.append(col)
            return lst

        def add_color(dir, color):
            if color:
                return dir + ' - ' + color
            else:
                return dir

        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['configfn'] = config.get_filename()

        # Temporary fix, problem with build_header
        conf['restart_req'] = sabnzbd.RESTART_REQ

        wlist = []
        wlist2 = ['None']
        interfaces = glob.glob(sabnzbd.DIR_INTERFACES + "/*")
        for k in interfaces:
            if k.endswith(DEF_STDINTF):
                interfaces.remove(k)
                interfaces.insert(0, k)
                break
        for web in interfaces:
            rweb = os.path.basename(web)
            if rweb != '.svn' and rweb != '_svn' and os.access(web + '/' + DEF_MAIN_TMPL, os.R_OK):
                cols = ListColors(rweb)
                if cols:
                    for col in cols:
                        wlist.append(add_color(rweb, col))
                        wlist2.append(add_color(rweb, col))
                else:
                    wlist.append(rweb)
                    wlist2.append(rweb)
        conf['web_list'] = wlist
        conf['web_list2'] = wlist2

        conf['web_colors'] = ['None'] #ListColors(cfg.WEB_DIR.get())
        conf['web_color'] = 'None' #cfg.WEB_COLOR.get()
        conf['web_colors2'] = ['None'] #ListColors(cfg.WEB_DIR2.get())
        conf['web_color2'] = 'None' #cfg.WEB_COLOR2.get()

        conf['web_dir']  = add_color(cfg.WEB_DIR.get(), cfg.WEB_COLOR.get())
        conf['web_dir2'] = add_color(cfg.WEB_DIR2.get(), cfg.WEB_COLOR2.get())
        conf['host'] = cfg.CHERRYHOST.get()
        conf['port'] = cfg.CHERRYPORT.get()
        conf['https_port'] = cfg.HTTPS_PORT.get()
        conf['https_cert'] = cfg.HTTPS_CERT.get()
        conf['https_key'] = cfg.HTTPS_KEY.get()
        conf['enable_https'] = cfg.ENABLE_HTTPS.get()
        conf['username'] = cfg.USERNAME.get()
        conf['password'] = cfg.PASSWORD.get_stars()
        conf['bandwith_limit'] = cfg.BANDWIDTH_LIMIT.get()
        conf['refresh_rate'] = cfg.REFRESH_RATE.get()
        conf['rss_rate'] = cfg.RSS_RATE.get()
        conf['cache_limitstr'] = cfg.CACHE_LIMIT.get()
        conf['cleanup_list'] = List2String(cfg.CLEANUP_LIST.get())

        template = Template(file=os.path.join(self.__web_dir, 'config_general.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveGeneral(self, host=None, port=None,
                    https_port=None, https_cert=None, https_key=None, enable_https=None,
                    web_username=None, web_password=None, web_dir = None,
                    web_dir2=None, web_color=None,
                    refresh_rate=None, rss_rate=None,
                    bandwith_limit=None, cleanup_list=None, cache_limitstr=None, _dc=None):

        cfg.CHERRYHOST.set(host)
        cfg.CHERRYPORT.set(port)

        cfg.ENABLE_HTTPS.set(enable_https)
        cfg.HTTPS_PORT.set(https_port)
        cfg.HTTPS_CERT.set(https_cert)
        cfg.HTTPS_KEY.set(https_key)

        cfg.USERNAME.set(web_username)
        cfg.PASSWORD.set(web_password)

        cfg.BANDWIDTH_LIMIT.set(bandwith_limit)
        cfg.RSS_RATE.set(rss_rate)
        cfg.REFRESH_RATE.set(refresh_rate)
        if cleanup_list and os.name == 'nt':
            cleanup_list = cleanup_list.lower()
        cfg.CLEANUP_LIST.set_string(cleanup_list)
        cfg.CACHE_LIMIT.set(cache_limitstr)

        change_web_dir(web_dir)
        try:
            web_dir2, web_color2 = web_dir2.split(' - ')
        except:
            web_color2 = ''
        web_dir2_path = real_path(sabnzbd.DIR_INTERFACES, web_dir2)

        if web_dir2 == 'None':
            cfg.WEB_DIR2.set('')
        elif os.path.exists(web_dir2_path):
            cfg.WEB_DIR2.set(web_dir2)
        cfg.WEB_COLOR2.set(web_color2)

        config.save_config()

        # Update CherryPy authentication
        set_auth(cherrypy.config)
        raise Raiser(self.__root, _dc=_dc)

def change_web_dir(web_dir):
        try:
            web_dir, web_color = web_dir.split(' - ')
        except:
            web_color = ''

        web_dir_path = real_path(sabnzbd.DIR_INTERFACES, web_dir)

        if not os.path.exists(web_dir_path):
            return badParameterResponse('Cannot find web template: %s' % web_dir_path)
        else:
            cfg.WEB_DIR.set(web_dir)
            cfg.WEB_COLOR.set(web_color)


#------------------------------------------------------------------------------

class ConfigServer:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        new = {}
        servers = config.get_servers()
        for svr in servers:
            new[svr] = servers[svr].get_dict()
        conf['servers'] = new

        if sabnzbd.newswrapper.HAVE_SSL:
            conf['have_ssl'] = 1
        else:
            conf['have_ssl'] = 0

        template = Template(file=os.path.join(self.__web_dir, 'config_server.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()


    @cherrypy.expose
    def addServer(self, **kwargs):
        return handle_server(kwargs, self.__root)


    @cherrypy.expose
    def saveServer(self, **kwargs):
        return handle_server(kwargs, self.__root)


    @cherrypy.expose
    def delServer(self, *args, **kwargs):
        if 'server' in kwargs:
            server = kwargs['server']
            svr = config.get_config('servers', server)
            if svr:
                svr.delete()
                del svr
                config.save_config()
                downloader.update_server(server, None)

        raise dcRaiser(self.__root, kwargs)

def handle_server(kwargs, root=None):
    """ Internal server handler """
    try:
        host = kwargs['host']
    except:
        return badParameterResponse('Error: Need host name.')

    port = kwargs.get('port', '')
    if not port.strip():
        if not kwargs.get('ssl', '').strip():
            port = '119'
        else:
            port = '563'
        kwargs['port'] = port

    if kwargs.get('connections', '').strip() == '':
        kwargs['connections'] = '1'

    msg = check_server(host, port)
    if msg:
        return msg

    # Replace square by curly brackets to avoid clash
    # between INI format and IPV6 notation
    server = '%s:%s' % (host.replace('[','{').replace(']','}'), port)

    svr = config.get_config('servers', server)
    if svr:
        old_server = server
        for kw in ('fillserver', 'ssl', 'enable'):
            if kw not in kwargs.keys():
                kwargs[kw] = None
        svr.set_dict(kwargs)
    else:
        old_server = None
        config.ConfigServer(server, kwargs)

    config.save_config()
    downloader.update_server(old_server, server)
    if root:
        raise dcRaiser(root, kwargs)


#------------------------------------------------------------------------------

class ConfigRss:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['script_list'] = ListScripts(default=True)
        pick_script = conf['script_list'] != []

        conf['cat_list'] = ListCats(default=True)
        pick_cat = conf['cat_list'] != []

        rss = {}
        unum = 1
        feeds = config.get_rss()
        for feed in feeds:
            rss[feed] = feeds[feed].get_dict()
            filters = feeds[feed].filters.get()
            rss[feed]['filters'] = filters
            rss[feed]['filtercount'] = len(filters)

            rss[feed]['pick_cat'] = pick_cat
            rss[feed]['pick_script'] = pick_script

            unum += 1
        conf['rss'] = rss
        conf['feed'] = 'Feed' + str(unum)

        template = Template(file=os.path.join(self.__web_dir, 'config_rss.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def upd_rss_feed(self, **kwargs):
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            cfg = None
        if cfg and Strip(kwargs.get('uri')):
            cfg.set_dict(kwargs)
            config.save_config()

        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def toggle_rss_feed(self, **kwargs):
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            cfg = None
        if cfg:
            cfg.enable.set(not cfg.enable.get())
            config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add_rss_feed(self, **kwargs):
        feed= Strip(kwargs.get('feed'))
        uri = Strip(kwargs.get('uri'))
        try:
            cfg = config.get_rss()[feed]
        except KeyError:
            cfg = None
        if (not cfg) and uri:
            config.ConfigRSS(feed, kwargs)
            config.save_config()

        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def upd_rss_filter(self, feed=None, index=None, filter_text=None,
                       filter_type=None, cat=None, pp=None, script=None, _dc=None):
        try:
            cfg = config.get_rss()[feed]
        except KeyError:
            raise Raiser(self.__root, _dc=_dc)

        if IsNone(pp): pp = ''
        script = ConvertSpecials(script)
        cat = ConvertSpecials(cat)

        cfg.filters.update(int(index), (cat, pp, script, filter_type, filter_text))
        config.save_config()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def pos_rss_filter(self, feed=None, current=None, new=None, _dc=None):
        try:
            cfg = config.get_rss()[feed]
        except KeyError:
            raise Raiser(self.__root, _dc=_dc)

        if current != new:
            cfg.filters.move(int(current), int(new))
            config.save_config()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def del_rss_feed(self, *args, **kwargs):
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            cfg = None

        if cfg:
            cfg.delete()
            del cfg
            config.save_config()

        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def del_rss_filter(self, feed=None, index=None, _dc=None):
        try:
            cfg = config.get_rss()[feed]
        except KeyError:
            raise Raiser(self.__root, _dc=_dc)

        cfg.filters.delete(int(index))
        config.save_config()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def download_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            sabnzbd.rss.run_feed(feed, download=True)
            return ShowRssLog(feed, False)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def test_rss_feed(self, *args, **kwargs):
        if 'feed' in kwargs:
            feed = kwargs['feed']
            sabnzbd.rss.run_feed(feed, download=False)
            return ShowRssLog(feed, True)
        raise dcRaiser(self.__root, kwargs)


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
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['schedlines'] = []
        for ev in scheduler.sort_schedules(forward=True):
            conf['schedlines'].append(ev[3])

        actions = ['resume', 'pause', 'shutdown', 'restart', 'speedlimit']
        for server in config.get_servers():
            actions.append(server)
        conf['actions'] = actions

        template = Template(file=os.path.join(self.__web_dir, 'config_scheduling.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
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
            elif action in ('resume', 'pause', 'shutdown', 'restart'):
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
                sched = cfg.SCHEDULES.get()
                sched.append('%s %s %s %s %s' %
                                 (minute, hour, dayofweek, action, arguments))
                cfg.SCHEDULES.set(sched)

        config.save_config()
        scheduler.restart(force=True)
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def delSchedule(self, line = None, _dc = None):
        schedules = cfg.SCHEDULES.get()
        if line and line in schedules:
            schedules.remove(line)
            cfg.SCHEDULES.set(schedules)
        config.save_config()
        scheduler.restart(force=True)
        raise Raiser(self.__root, _dc=_dc)

#------------------------------------------------------------------------------

class ConfigNewzbin:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__bookmarks = []

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['username_newzbin'] = cfg.USERNAME_NEWZBIN.get()
        conf['password_newzbin'] = cfg.PASSWORD_NEWZBIN.get_stars()
        conf['newzbin_bookmarks'] = int(cfg.NEWZBIN_BOOKMARKS.get())
        conf['newzbin_unbookmark'] = int(cfg.NEWZBIN_UNBOOKMARK.get())
        conf['bookmark_rate'] = cfg.BOOKMARK_RATE.get()

        conf['bookmarks_list'] = self.__bookmarks

        conf['username_matrix'] = cfg.USERNAME_MATRIX.get()
        conf['password_matrix'] = cfg.PASSWORD_MATRIX.get_stars()

        template = Template(file=os.path.join(self.__web_dir, 'config_newzbin.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveNewzbin(self, username_newzbin = None, password_newzbin = None,
                    newzbin_bookmarks = None,
                    newzbin_unbookmark = None, bookmark_rate = None,
                    username_matrix = None, password_matrix = None, _dc = None):


        cfg.USERNAME_NEWZBIN.set(username_newzbin)
        cfg.PASSWORD_NEWZBIN.set(password_newzbin)
        cfg.NEWZBIN_BOOKMARKS.set(newzbin_bookmarks)
        cfg.NEWZBIN_UNBOOKMARK.set(newzbin_unbookmark)
        cfg.BOOKMARK_RATE.set(bookmark_rate)

        cfg.USERNAME_MATRIX.set(username_matrix)
        cfg.PASSWORD_MATRIX.set(password_matrix)

        config.save_config()
        scheduler.restart()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def saveMatrix(self, username_matrix = None, password_matrix = None, _dc = None):

        cfg.USERNAME_MATRIX.set(username_matrix)
        cfg.PASSWORD_MATRIX.set(password_matrix)

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
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        if cfg.USERNAME_NEWZBIN.get() and cfg.PASSWORD_NEWZBIN.get():
            conf['newzbinDetails'] = True

        conf['script_list'] = ListScripts(default=True)

        categories = config.get_categories()
        conf['have_cats'] =  categories != {}
        conf['defdir'] = cfg.COMPLETE_DIR.get_path()


        empty = { 'name':'', 'pp':'-1', 'script':'', 'dir':'', 'newzbin':'' }
        slotinfo = []
        slotinfo.append(empty)
        for cat in sorted(categories):
            slot = categories[cat].get_dict()
            slot['name'] = cat
            slotinfo.append(slot)
        conf['slotinfo'] = slotinfo

        template = Template(file=os.path.join(self.__web_dir, 'config_cat.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def delete(self, name = None, _dc = None):
        if name:
            config.delete('categories', name)
            config.save_config()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def save(self, **kwargs):
        newname = Strip(kwargs.get('newname'))
        name = kwargs.get('name')
        _dc = kwargs.get('_dc')

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
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)
        conf['complete_dir'] = cfg.COMPLETE_DIR.get_path()

        for kw in SORT_LIST:
            conf[kw] = config.get_config('misc', kw).get()
        conf['cat_list'] = ListCats(True)
        #tvSortList = []

        template = Template(file=os.path.join(self.__web_dir, 'config_sorting.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
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
            value = kwargs.get(kw)
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        _dc = kwargs.get('_dc', '')
        raise Raiser(self.__root, _dc=_dc)


#------------------------------------------------------------------------------

class ConnectionInfo:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__lastmail = None

    @cherrypy.expose
    def index(self, _dc = None):
        header, pnfo_list, bytespersec = build_header(self.__prim)

        header['logfile'] = sabnzbd.LOGFILE
        header['weblogfile'] = sabnzbd.WEBLOGFILE
        header['loglevel'] = str(cfg.LOG_LEVEL.get())

        header['lastmail'] = self.__lastmail

        header['servers'] = []

        for server in downloader.servers()[:]:
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
                    nzo_name = xml_name(nzo.get_dirname())

                busy.append((nw.thrdnum, art_name, nzf_name, nzo_name))

                if nw.connected:
                    connected += 1

            busy.sort()
            header['servers'].append((server.host, server.port, connected, busy, server.ssl, server.active))

        wlist = []
        for w in sabnzbd.GUIHANDLER.content():
            wlist.append(xml_name(w))
        header['warnings'] = wlist

        template = Template(file=os.path.join(self.__web_dir, 'connection_info.tmpl'),
                            searchList=[header], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def disconnect(self, _dc = None):
        downloader.disconnect()
        raise Raiser(self.__root, _dc=_dc)

    @cherrypy.expose
    def testmail(self, _dc = None):
        logging.info("Sending testmail")
        pack = {}
        pack['download'] = ['action 1', 'action 2']
        pack['unpack'] = ['action 1', 'action 2']

        self.__lastmail= email.endjob('Test Job', 123, 'unknown', True,
                                      os.path.normpath(os.path.join(cfg.COMPLETE_DIR.get_path(), '/unknown/Test Job')),
                                      str(123*MEBI), pack, 'my_script', 'Line 1\nLine 2\nLine 3\n', 0)
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
        cfg.LOG_LEVEL.set(loglevel)
        config.save_config()

        raise Raiser(self.__root, _dc=_dc)


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
''' % (xml_name(name), xml_name(name), escape(msg))


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
    names = jobs.keys()
    # Sort in reverse chronological order (newest first)
    names.sort(lambda x, y: int(jobs[y][6]*100.0 - jobs[x][6]*100.0))

    qfeed = escape(feed.replace('/','%2F').replace('?', '%3F'))

    doneStr = ""
    for x in names:
        job = jobs[x]
        if job[0] == 'D':
            doneStr += '%s<br/>' % xml_name(job[1])
    goodStr = ""
    for x in names:
        job = jobs[x]
        if job[0] == 'G':
            goodStr += '%s<br/>' % xml_name(job[1])
    badStr = ""
    for x in names:
        job = jobs[x]
        if job[0] == 'B':
            name = urllib.quote_plus(job[2])
            if job[3]:
                cat = '&cat=' + escape(job[3])
            else:
                cat = ''
            if job[4]:
                pp = '&pp=' + escape(str(job[4]))
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

    header = { 'version':sabnzbd.__version__, 'paused':downloader.paused(),
               'uptime':uptime, 'color_scheme':color }
    speed_limit = downloader.get_limit()
    if speed_limit <= 0:
        speed_limit = ''

    header['helpuri'] = 'http://sabnzbd.wikidot.com/'
    header['diskspace1'] = "%.2f" % diskfree(cfg.DOWNLOAD_DIR.get_path())
    header['diskspace2'] = "%.2f" % diskfree(cfg.COMPLETE_DIR.get_path())
    header['diskspacetotal1'] = "%.2f" % disktotal(cfg.DOWNLOAD_DIR.get_path())
    header['diskspacetotal2'] = "%.2f" % disktotal(cfg.COMPLETE_DIR.get_path())
    header['loadavg'] = loadavg()
    header['speedlimit'] = "%s" % speed_limit
    header['restart_req'] = sabnzbd.RESTART_REQ
    header['have_warnings'] = str(sabnzbd.GUIHANDLER.count())
    header['last_warning'] = sabnzbd.GUIHANDLER.last()
    if prim:
        header['webdir'] = sabnzbd.WEB_DIR
    else:
        header['webdir'] = sabnzbd.WEB_DIR2

    header['finishaction'] = sabnzbd.QUEUECOMPLETE
    header['nt'] = os.name == 'nt'
    header['darwin'] = sabnzbd.DARWIN

    bytespersec = bpsmeter.method.get_bps()
    qnfo = nzbqueue.queue_info()

    bytesleft = qnfo[QNFO_BYTES_LEFT_FIELD]
    bytes = qnfo[QNFO_BYTES_FIELD]

    header['kbpersec'] = "%.2f" % (bytespersec / KIBI)
    header['mbleft']   = "%.2f" % (bytesleft / MEBI)
    header['mb']       = "%.2f" % (bytes / MEBI)

    status = ''
    if downloader.paused():
        status = 'Paused'
    elif bytespersec > 0:
        status = 'Downloading'
    else:
        status = 'Idle'
    header['status'] = "%s" % status

    anfo  = articlecache.method.cache_info()

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
LIST_EMAIL = (
    'email_endjob', 'email_full',
    'email_server', 'email_to', 'email_from',
    'email_account', 'email_pwd', 'email_dir'
    )

class ConfigEmail:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, _dc = None):
        if cfg.CONFIGLOCK.get():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['my_home'] = sabnzbd.DIR_HOME
        conf['my_lcldata'] = sabnzbd.DIR_LCLDATA

        for kw in LIST_EMAIL:
            if kw == 'email_pwd':
                conf[kw] = config.get_config('misc', kw).get_stars()
            else:
                conf[kw] = config.get_config('misc', kw).get()

        template = Template(file=os.path.join(self.__web_dir, 'config_email.tmpl'),
                            searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveEmail(self, **kwargs):

        for kw in LIST_EMAIL:
            msg = config.get_config('misc', kw).set(kwargs.get(kw))
            if msg:
                return badParameterResponse('Incorrect value for %s: %s' % (kw, msg))

        config.save_config()
        scheduler.restart()
        raise dcRaiser(self.__root, kwargs)

def std_time(when):
    # Fri, 16 Nov 2007 16:42:01 GMT +0100
    item  = time.strftime('%a, %d %b %Y %H:%M:%S', time.localtime(when))
    item += " GMT %+05d" % (-time.timezone/36)
    return item


def rss_history(url, limit=50, search=None):
    url = url.replace('rss','')

    youngest = None

    rss = RSS()
    rss.channel.title = "SABnzbd History"
    rss.channel.description = "Overview of completed downloads"
    rss.channel.link = "http://sourceforge.net/projects/sabnzbdplus/"
    rss.channel.language = "en"

    items, fetched_items, max_items = build_history(limit=limit, search=search)

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
            item.link = url

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
    b = to_units(bytes)
    if b == '':
        return b
    else:
        return b + 'B'


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

    qnfo = nzbqueue.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    for pnfo in pnfo_list:
        filename = pnfo[PNFO_FILENAME_FIELD]
        msgid = pnfo[PNFO_MSGID_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append( { "id" : nzo_id, "mb":bytes, "mbleft":bytesleft, "filename":filename, "msgid":msgid } )

    status = {
        "paused" : downloader.paused(),
        "kbpersec" : bpsmeter.method.get_bps() / KIBI,
        "mbleft" : qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
        "mb" : qnfo[QNFO_BYTES_FIELD] / MEBI,
        "noofslots" : len(pnfo_list),
        "have_warnings" : str(sabnzbd.GUIHANDLER.count()),
        "diskspace1" : diskfree(cfg.DOWNLOAD_DIR.get_path()),
        "diskspace2" : diskfree(cfg.COMPLETE_DIR.get_path()),
        "timeleft" : calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsmeter.method.get_bps()),
        "jobs" : jobs
    }
    status_str= JsonWriter().write(status)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str

def xml_qstatus():
    """Build up the queue status as a nested object and output as a XML string
    """

    qnfo = nzbqueue.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    for pnfo in pnfo_list:
        filename = pnfo[PNFO_FILENAME_FIELD]
        msgid = pnfo[PNFO_MSGID_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        name = xml_name(filename)
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append( { "id" : nzo_id, "mb":bytes, "mbleft":bytesleft, "filename":name, "msgid":msgid } )

    status = {
        "paused" : downloader.paused(),
        "kbpersec" : bpsmeter.method.get_bps() / KIBI,
        "mbleft" : qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
        "mb" : qnfo[QNFO_BYTES_FIELD] / MEBI,
        "noofslots" : len(pnfo_list),
        "have_warnings" : str(sabnzbd.GUIHANDLER.count()),
        "diskspace1" : diskfree(cfg.DOWNLOAD_DIR.get_path()),
        "diskspace2" : diskfree(cfg.COMPLETE_DIR.get_path()),
        "timeleft" : calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsmeter.method.get_bps()),
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
    qnfo = nzbqueue.queue_info()
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
                _set = xml_name(_set)

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
    bytes, month, week = history_db.get_history_size()
    return (format_bytes(bytes), format_bytes(month), format_bytes(week))

def build_history(loaded=False, start=None, limit=None, verbose=False, verbose_list=None, search=None):

    if not verbose_list:
        verbose_list = []

    try:
        limit = int(limit)
    except:
        limit = 0
    try:
        start = int(start)
    except:
        start = 0

    def matches_search(text, search_text):
        # Replace * with .* and ' ' with .
        search_text = search_text.replace('*','.*').replace(' ','.*')
        try:
            re_search = re.compile(search_text)
        except:
            logging.error('Failed to compile regex for search term: %s', search_text)
            return False
        return re_search.search(text)

    queue = postproc.history_queue()
    if search:
        queue = [nzo for nzo in queue if matches_search(nzo.get_original_dirname(), search)]

    if start > len(queue):
        queue = []
    else:
        try:
            if start:
                if limit:
                    queue = queue[start:start+limit]
                else:
                    queue = queue[start:]
        except:
            pass
    limit -= len(queue)



    history_db = cherrypy.thread_data.history_db
    items, fetched_items, total_items = history_db.fetch_history(start,limit,search)

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

    items = get_active_history(queue, items)

    # Unreverse the queue
    items.reverse()

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
        if not item.has_key('loaded'):
            item['loaded'] = False

    return (items, fetched_items, total_items)

def xml_history(start=None, limit=None, search=None):
    history, pnfo_list, bytespersec = build_header(True)
    history['slots'], fetched_items, history['noofslots'] = build_history(start=start, limit=limit, verbose=True, search=search)
    status_lst = []
    status_lst.append('<?xml version="1.0" encoding="UTF-8" ?> \n')
    #Compile the history data

    xmlmaker = xml_factory()
    t = time.time()
    status_lst.append(xmlmaker.run("history",history))
    total = time.time() - t

    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return ''.join(status_lst)

def json_history(start=None, limit=None, search=None):
    history, pnfo_list, bytespersec = build_header(True)
    history['slots'], fetched_items, history['noofslots'] = build_history(start=start, limit=limit, verbose=True, search=search)
    #Compile the history data

    status_str = JsonWriter().write(history)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str.encode("ISO-8859-1", 'replace')


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


    def _tuple(self, keyw, lst, text=None):
        if text == None:
            text = []
            
        for item in lst:
            text.append(self.run(keyw, item))
        return ''.join(text)

    def _dict(self, keyw, lst, text=None):
        if text == None:
            text = []
        
        for key in lst.keys():
            found = self.run(key,lst[key])
            if found:
                text.append(found)
            else:
                value = lst[key]
                if not isinstance(value, basestring):
                    value = str(value)
                text.append('<%s>%s</%s>\n' % (str(key), xml_name(value, encoding='utf-8'), str(key)))

        if keyw and text:
            return '<%s>%s</%s>\n' % (keyw,''.join(text),keyw)
        else:
            return ''

    def _list(self, keyw, lst, text=None):
        if text == None:
            text = []
            
        #deal with lists
        #found = False
        for cat in lst:
            if isinstance(cat, dict):
                #debug = 'dict%s' % n
                text.append(self._dict('slot', cat))
            elif isinstance(cat, list):
                debug = 'list'
                text.append(self._list(debug, cat))
            elif isinstance(cat, tuple):
                debug = 'tuple'
                text.append(self._tuple(debug, cat))
            else:
                if not isinstance(cat, basestring):
                    cat = str(cat)
                text.append('<item>%s</item>\n' % xml_name(cat, encoding='utf-8'))

        if keyw and text:
            return '<%s>%s</%s>\n' % (keyw,''.join(text),keyw)
        else:
            return ''

    def run(self, keyw, lst):
        if isinstance(lst, dict):
            text = self._dict(keyw,lst)
        elif isinstance(lst, list):
            text = self._list(keyw,lst)
        elif isinstance(lst, tuple):
            text = self._tuple(keyw,lst)
        else:
            text = ''
        return text


def queueStatus(start, limit):
    #gather the queue details
    info, pnfo_list, bytespersec, verboseList, dictn = build_queue(history=True, start=start, limit=limit)
    text = ['<?xml version="1.0" encoding="UTF-8" ?>']

    #Use xmlmaker to make an xml string out of info which is a tuple that contains lists/strings/dictionaries
    xmlmaker = xml_factory()
    text.append(xmlmaker.run("queue",info))

    #output in xml with no caching
    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return ''.join(text)

def queueStatusJson(start, limit):
    #gather the queue details
    info, pnfo_list, bytespersec, verboseList, dictn = build_queue(history=True, start=start, limit=limit, json_output=True)

    status_str = JsonWriter().write(info)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str

def build_queue(web_dir=None, root=None, verbose=False, prim=True, verboseList=None,
                dictionary=None, history=False, start=None, limit=None, dummy2=None, json_output=False):
    if not verboseList:
        verboseList = []
    if dictionary:
        dictn = dictionary
    else:
        dictn = []
    #build up header full of basic information
    info, pnfo_list, bytespersec = build_header(prim)
    info['isverbose'] = verbose
    cookie = cherrypy.request.cookie
    if cookie.has_key('queue_details'):
        info['queue_details'] = str(IntConv(cookie['queue_details'].value))
    else:
        info['queue_details'] = '0'

    if cfg.USERNAME_NEWZBIN.get() and cfg.PASSWORD_NEWZBIN.get():
        info['newzbinDetails'] = True

    if cfg.REFRESH_RATE.get() > 0:
        info['refresh_rate'] = str(cfg.REFRESH_RATE.get())
    else:
        info['refresh_rate'] = ''

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

    limit = IntConv(limit)
    start = IntConv(start)

    if history:
        #Collect nzo's from the history that are downloaded but not finished (repairing, extracting)
        slotinfo = format_history_for_queue()
        #if the specified start value is greater than the amount of history items, do no include the history (used for paging the queue)
        if len(slotinfo) < start:
            slotinfo = []
    else:
        slotinfo = []

    info['noofslots'] = len(pnfo_list) + len(slotinfo)

    info['start'] = start
    info['limit'] = limit
    info['finish'] = info['start'] + info['limit']
    if info['finish'] > info['noofslots']:
        info['finish'] = info['noofslots']

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
        msgid = pnfo[PNFO_MSGID_FIELD]
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

        slot = {'index':n, 'nzo_id':str(nzo_id)}
        unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)

        slot['unpackopts'] = str(unpackopts)
        if script:
            slot['script'] = script
        else:
            slot['script'] = 'None'
        slot['msgid'] = msgid
        slot['filename'] = xml_name(filename)
        slot['cat'] = cat
        slot['mbleft'] = "%.2f" % mbleft
        slot['mb'] = "%.2f" % mb
        slot['size'] = "%s" % format_bytes(bytes)
        if not downloader.paused() and status != 'Paused' and status != 'Fetching' and not found_active:
            slot['status'] = "Downloading"
            found_active = True
        else:
            slot['status'] = "%s" % (status)
        if priority == TOP_PRIORITY:
            slot['priority'] = 'Force'
        elif priority == HIGH_PRIORITY:
            slot['priority'] = 'High'
        elif priority == LOW_PRIORITY:
            slot['priority'] = 'Low'
        else:
            slot['priority'] = 'Normal'
        if mb == mbleft:
            slot['percentage'] = "0"
        else:
            slot['percentage'] = "%s" % (int(((mb-mbleft) / mb) * 100))

        if status == 'Paused':
            slot['timeleft'] = '0:00:00'
            slot['eta'] = 'unknown'
        else:
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
        info['slots'] = slotinfo
    else:
        info['slots'] = ''
        verboseList = []

    return info, pnfo_list, bytespersec, verboseList, dictn


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
    qnfo = nzbqueue.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    rss = RSS()
    rss.channel.title = "SABnzbd Queue"
    rss.channel.description = "Overview of current downloads"
    rss.channel.link = "http://%s:%s/sabnzbd/queue" % ( \
        cfg.CHERRYHOST.get(), cfg.CHERRYPORT.get() )
    rss.channel.language = "en"

    item = Item()
    item.title  = "Total ETA: " + calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsmeter.method.get_bps()) + " - "
    item.title += "Queued: %.2f MB - " % (qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI)
    item.title += "Speed: %.2f kB/s" % (bpsmeter.method.get_bps() / KIBI)
    rss.addItem(item)

    sum_bytesleft = 0
    for pnfo in pnfo_list:
        filename = pnfo[PNFO_FILENAME_FIELD]
        msgid = pnfo[PNFO_MSGID_FIELD]
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
            cfg.CHERRYHOST.get(), cfg.CHERRYPORT.get() )
        statusLine  = ""
        statusLine += '<tr>'
        #Total MB/MB left
        statusLine +=  '<dt>Remain/Total: %.2f/%.2f MB</dt>' % (bytesleft, bytes)
        #ETA
        sum_bytesleft += pnfo[PNFO_BYTES_LEFT_FIELD]
        statusLine += "<dt>ETA: %s </dt>" % calc_timeleft(sum_bytesleft, bpsmeter.method.get_bps())
        statusLine += "<dt>Age: %s</dt>" % calc_age(pnfo[PNFO_AVG_DATE_FIELD])
        statusLine += "</tr>"
        item.description = statusLine
        rss.addItem(item)

    rss.channel.lastBuildDate = std_time(time.time())
    rss.channel.pubDate = rss.channel.lastBuildDate
    rss.channel.ttl = "1"
    return rss.write()


def json_result(result, section=None, keyword=None, data=None):
    """ Return data in a json structure
    """
    dd = { 'status' : result }
    if section and (data or data == ''):
        if section in ('servers', 'categories', 'rss'):
            dd[section] = {keyword : data}
        else:
            dd[section] = data

    status_str = JsonWriter().write(dd)

    cherrypy.response.headers['Content-Type'] = "application/json"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str


def xml_result(result, section=None, keyword=None, data=None):
    """ Return data as XML
    """
    status_str = '<?xml version="1.0" encoding="UTF-8" ?> \n'
    xmlmaker = xml_factory()
    dd = {'status' : int(result) }
    if data or data == '':
        if section in ('servers', 'categories', 'rss'):
            keyword = keyword.replace(':', '_')
            dd[section] = {keyword : data}
        else:
            dd[section] = data
    status_str += xmlmaker.run('result', dd)

    cherrypy.response.headers['Content-Type'] = "text/xml"
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return status_str


def format_history_for_queue():
    ''' Retrieves the information on currently active history items, and formats them for displaying in the queue '''
    slotinfo = []
    history_items = get_active_history()

    for item in history_items:
        slot = {'nzo_id':item['nzo_id'],
                'msgid':item['report'], 'filename':xml_name(item['name']), 'loaded':True,
                'stages':item['stage_log'], 'status':item['status'], 'bytes':item['bytes'],
                'size':item['size']}
        slotinfo.append(slot)

    return slotinfo

def get_active_history(queue=None, items=None):
    # Get the currently in progress and active history queue.
    if not items:
        items = []
    if not queue:
        queue = postproc.history_queue()

    for nzo in queue:
        t = build_history_info(nzo)
        item = {}
        item['completed'], item['name'], item['nzb_name'], item['category'], item['pp'], item['script'], item['report'], \
            item['url'], item['status'], item['nzo_id'], item['storage'], item['path'], item['script_log'], \
            item['script_line'], item['download_time'], item['postproc_time'], item['stage_log'], \
            item['downloaded'], item['completeness'], item['fail_message'], item['url_info'], item['bytes'] = t
        item['action_line'] = nzo.get_action_line()
        item = unpack_history_info(item)

        item['loaded'] = True
        if item['bytes']:
            item['size'] = format_bytes(item['bytes'])
        else:
            item['size'] = ''

        # Queue display needs Unicode instead of UTF-8
        for kw in item:
            if isinstance(item[kw], str):
                item[kw] = item[kw].decode('utf-8')

        items.append(item)

    return items
