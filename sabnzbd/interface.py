#!/usr/bin/python -OO
# Copyright 2008-2010 The SABnzbd-Team <team@sabnzbd.org>
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

from sabnzbd.utils.rsslib import RSS, Item
from sabnzbd.utils.json import JsonWriter
import sabnzbd
import sabnzbd.rss
import sabnzbd.scheduler as scheduler

from Cheetah.Template import Template
import sabnzbd.emailer as emailer
from sabnzbd.misc import real_path, loadavg, \
     to_units, diskfree, disktotal, get_ext, sanitize_foldername, \
     get_filename, cat_to_opts, IntConv, panic_old_queue, globber
from sabnzbd.newswrapper import GetServerParms
from sabnzbd.newzbin import Bookmarks, MSGIDGrabber
from sabnzbd.encoding import TRANS, xml_name, LatinFilter, unicoder, special_fixer, platform_encode, latin1
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.articlecache import ArticleCache
import sabnzbd.newsunpack
from sabnzbd.postproc import PostProcessor
import sabnzbd.downloader as downloader
from sabnzbd.bpsmeter import BPSMeter
import sabnzbd.nzbqueue as nzbqueue
from sabnzbd.database import build_history_info, unpack_history_info
import sabnzbd.wizard
from sabnzbd.utils.servertests import test_nntp_server_dict

from sabnzbd.constants import *
from sabnzbd.lang import T, Ta, Tspec, list_languages, reset_language

#------------------------------------------------------------------------------
# Global constants

DIRECTIVES = {
           'directiveStartToken': '<!--#',
           'directiveEndToken': '#-->',
           'prioritizeSearchListOverSelf' : True
           }
FILTER = LatinFilter

#------------------------------------------------------------------------------
#
def check_server(host, port):
    """ Check if server address resolves properly """

    if host.lower() == 'localhost' and sabnzbd.AMBI_LOCALHOST:
        return badParameterResponse(T('msg-warning-ambiLocalhost'))

    if GetServerParms(host, IntConv(port)):
        return ""
    else:
        return badParameterResponse(T('msg-invalidServer@2') % (host, port))


def ListScripts(default=False):
    """ Return a list of script names """
    lst = []
    dd = cfg.script_dir.get_path()

    if dd and os.access(dd, os.R_OK):
        if default:
            lst = ['Default', 'None']
        else:
            lst = ['None']
        for script in globber(dd):
            if os.path.isfile(script):
                sc= os.path.basename(script)
                if sc != "_svn" and sc != ".svn":
                    lst.append(sc)
    return lst


def ListCats(default=False):
    """ Return list of categories """
    lst = sorted(config.get_categories().keys())
    if lst:
        lst.insert(0, 'None')
        if default:
            lst.insert(0, 'Default')
    return lst


def ConvertSpecials(p):
    """ Convert None to 'None' and 'Default' to ''
    """
    if p is None:
        p = 'None'
    elif p.lower() == T('default').lower():
        p = ''
    return p


def Raiser(root, **kwargs):
    args = {}
    for key in kwargs:
        val = kwargs.get(key)
        if val:
            args[key] = val
    root = '%s?%s' % (root, urllib.urlencode(args))
    return cherrypy.HTTPRedirect(root)


def queueRaiser(root, kwargs):
    return Raiser(root, start=kwargs.get('start'),
                        limit=kwargs.get('limit'),
                        search=kwargs.get('search'),
                        _dc=kwargs.get('_dc'))

def dcRaiser(root, kwargs):
    return Raiser(root, _dc=kwargs.get('_dc'))


#------------------------------------------------------------------------------
def IsNone(value):
    """ Return True if either None, 'None' or '' """
    return value==None or value=="" or value.lower()=='none'


def List2String(lst):
    """ Return list as a comma-separated string """
    if type(lst) == type(""):
        return lst
    return ', '.join(lst)

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
    users[cfg.username()] = cfg.password()
    return users

def encrypt_pwd(pwd):
    return pwd


def set_auth(conf):
    """ Set the authentication for CherryPy
    """
    if cfg.username() and cfg.password():
        conf.update({'tools.basic_auth.on' : True, 'tools.basic_auth.realm' : 'SABnzbd',
                            'tools.basic_auth.users' : get_users, 'tools.basic_auth.encrypt' : encrypt_pwd})
        conf.update({'/api':{'tools.basic_auth.on' : False},
                     '/m/api':{'tools.basic_auth.on' : False},
                     '/sabnzbd/api':{'tools.basic_auth.on' : False},
                     '/sabnzbd/m/api':{'tools.basic_auth.on' : False},
                     })
    else:
        conf.update({'tools.basic_auth.on':False})


def check_session(kwargs):
    """ Check session key """
    key = kwargs.get('session')
    if not key:
        key = kwargs.get('apikey')
    msg = None
    if not key:
        logging.warning(Ta('warn-missingKey'))
        msg = T('error-missingKey')
    elif key != cfg.api_key():
        logging.warning(Ta('error-badKey'))
        msg = T('error-badKey')
    return msg


def check_apikey(kwargs, nokey=False):
    """ Check api key """
    output = kwargs.get('output')
    mode = kwargs.get('mode', '')

    # Don't give a visible warning: these commands are used by some
    # external utilities to detect if username/password is required
    special = mode in ('get_scripts', 'qstatus')

    # First check APIKEY, if OK that's sufficient
    if not (cfg.disable_key() or nokey):
        key = kwargs.get('apikey')
        if not key:
            if not special:
                logging.warning(Ta('warn-apikeyNone'))
            return report(output, 'API Key Required')
        elif key != cfg.api_key():
            logging.warning(Ta('warn-apikeyBad'))
            return report(output, 'API Key Incorrect')
        else:
            return None

    # No active APIKEY, check web credentials instead
    if cfg.username() and cfg.password():
        if kwargs.get('ma_username') == cfg.username() and kwargs.get('ma_password') == cfg.password():
            pass
        else:
            if not special:
                logging.warning(Ta('warn-authMissing'))
            return report(output, 'Missing authentication')
    return None


def del_from_section(kwargs):
    """ Remove keyword in section """
    section = kwargs.get('section', '')
    if section in ('servers', 'rss', 'categories'):
        keyword = kwargs.get('keyword')
        if keyword:
            item = config.get_config(section, keyword)
            if item:
                item.delete()
                del item
                config.save_config()
                if section == 'servers':
                    downloader.update_server(keyword, None)
        return True
    else:
        return False


#------------------------------------------------------------------------------
class NoPage(object):
    def __init__(self):
        pass

    @cherrypy.expose
    def index(self, **kwargs):
        return badParameterResponse(T('error-noSecUI'))


#------------------------------------------------------------------------------
_MSG_NO_VALUE         = 'expect one parameter'
_MSG_NO_VALUE2        = 'expect two parameters'
_MSG_INT_VALUE        = 'expect integer value'
_MSG_NO_ITEM          = 'item does not exist'
_MSG_NOT_IMPLEMENTED  = 'not implemented'
_MSG_NO_FILE          = 'no file given'
_MSG_NO_PATH          = 'file does not exist'
_MSG_OUTPUT_FORMAT    = 'Format not supported'
_MSG_NO_SUCH_CONFIG   = 'Config item does not exist'
_MSG_BAD_SERVER_PARMS = 'Incorrect server settings'

def remove_callable(dic):
    """ Remove all callable items from dictionary """
    for key, value in dic.items():
        if callable(value):
            del dic[key]
    return dic

_PLURAL_TO_SINGLE = {
    'categories' : 'category',
    'servers' : 'server',
    'rss' : 'feed',
    'scripts' : 'script',
    'warnings' : 'warning',
    'files' : 'file',
    'jobs' : 'job'
    }
def plural_to_single(kw, def_kw=''):
    try:
        return _PLURAL_TO_SINGLE[kw]
    except KeyError:
        return def_kw


def report(output, error=None, keyword='value', data=None):
    """ Report message in json, xml or plain text
        If error is set, only an status/error report is made.
        If no error and no data, only a status report is made.
        Else, a data report is made (optional 'keyword' for outer XML section).
    """
    if output == 'json':
        content = "application/json;charset=UTF-8"
        if error:
            info = {'status':False, 'error':error}
        elif data is None:
            info = {'status':True}
        else:
            if hasattr(data,'__iter__') and not keyword:
                info = data
            else:
                info = {keyword:data}
        response = JsonWriter().write(info)

    elif output == 'xml':
        content = "text/xml"
        xmlmaker = xml_factory()
        if error:
            status_str = xmlmaker.run('result', {'status':False, 'error':error})
        elif data is None:
            status_str = xmlmaker.run('result', {'status':True})
        else:
            status_str = xmlmaker.run(keyword, data)
        response = '<?xml version="1.0" encoding="UTF-8" ?>\n%s\n' % status_str

    else:
        content = "text/plain"
        if error:
            response = "error: %s\n" % error
        elif data is None:
            response = 'ok\n'
        else:
            if type(data) in (list, tuple):
                # Special handling for list/tuple (backward compatibility)
                data = [str(val) for val in data]
                response = '%s\n' % ' '.join(data)
            else:
                response = '%s\n' % str(data)

    cherrypy.response.headers['Content-Type'] = content
    cherrypy.response.headers['Pragma'] = 'no-cache'
    return response


class MainPage(object):
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
        self.wizard = sabnzbd.wizard.Wizard(web_dir, root+'wizard/', prim)


    @cherrypy.expose
    def index(self, **kwargs):
        if sabnzbd.OLD_QUEUE and not cfg.warned_old_queue():
            cfg.warned_old_queue.set(True)
            config.save_config()
            return panic_old_queue()

        if kwargs.get('skip_wizard') or config.get_servers():
            info, pnfo_list, bytespersec = build_header(self.__prim)

            if cfg.newzbin_username() and cfg.newzbin_password.get_stars():
                info['newzbinDetails'] = True

            info['script_list'] = ListScripts(default=True)
            info['script'] = cfg.dirscan_script()

            info['cat'] = 'Default'
            info['cat_list'] = ListCats(True)

            info['warning'] = ''
            if cfg.enable_unrar():
                if sabnzbd.newsunpack.RAR_PROBLEM and not cfg.ignore_wrong_unrar():
                    info['warning'] = T('warn-badUnrar')
                if not sabnzbd.newsunpack.RAR_COMMAND:
                    info['warning'] = T('warn-noUnpack')
            if not sabnzbd.newsunpack.PAR2_COMMAND:
                info['warning'] = T('warn-noRepair')

            template = Template(file=os.path.join(self.__web_dir, 'main.tmpl'),
                                filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
            return template.respond()
        else:
            # Redirect to the setup wizard
            raise cherrypy.HTTPRedirect('/wizard/')

    #@cherrypy.expose
    #def reset_lang(self, **kwargs):
    #    msg = check_session(kwargs)
    #    if msg: return msg
    #    reset_language(cfg.language())
    #    raise dcRaiser(self.__root, kwargs)


    def add_handler(self, kwargs):
        id = kwargs.get('id', '')
        if not id:
            id = kwargs.get('url', '')
        pp = kwargs.get('pp')
        script = kwargs.get('script')
        cat = kwargs.get('cat')
        priority =  kwargs.get('priority')
        redirect = kwargs.get('redirect')
        nzbname = kwargs.get('nzbname')

        RE_NEWZBIN_URL = re.compile(r'/browse/post/(\d+)')
        newzbin_url = RE_NEWZBIN_URL.search(id.lower())

        id = Strip(id)
        if id and (id.isdigit() or len(id)==5):
            sabnzbd.add_msgid(id, pp, script, cat, priority, nzbname)
        elif newzbin_url:
            sabnzbd.add_msgid(Strip(newzbin_url.group(1)), pp, script, cat, priority, nzbname)
        elif id:
            sabnzbd.add_url(id, pp, script, cat, priority, nzbname)
        if not redirect:
            redirect = self.__root
        raise cherrypy.HTTPRedirect(redirect)


    @cherrypy.expose
    def addID(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        raise self.add_handler(kwargs)


    @cherrypy.expose
    def addURL(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        raise self.add_handler(kwargs)


    @cherrypy.expose
    def addFile(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        nzbfile = kwargs.get('nzbfile')
        if nzbfile is not None and nzbfile.filename and nzbfile.value:
            sabnzbd.add_nzbfile(nzbfile, kwargs.get('pp'), kwargs.get('script'),
                                kwargs.get('cat'), kwargs.get('priority', NORMAL_PRIORITY))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def shutdown(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            yield msg
        else:
            yield "Initiating shutdown..."
            sabnzbd.halt()
            yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
            cherrypy.engine.exit()
            sabnzbd.SABSTOP = True

    @cherrypy.expose
    def pause(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        scheduler.plan_resume(0)
        downloader.pause_downloader()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def resume(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        scheduler.plan_resume(0)
        sabnzbd.unpause_all()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def rss(self, **kwargs):
        msg = check_apikey(kwargs, nokey=True)
        if msg: return msg

        if kwargs.get('mode') == 'history':
            return rss_history(cherrypy.url(), limit=kwargs.get('limit',50), search=kwargs.get('search'))
        elif kwargs.get('mode') == 'queue':
            return rss_qstatus()
        elif kwargs.get('mode') == 'warnings':
            return rss_warnings()

    @cherrypy.expose
    def tapi(self, **kwargs):
        """Handler for API over http, for template use
        """
        msg = check_session(kwargs)
        if msg: return msg
        return self.api_handler(kwargs)

    @cherrypy.expose
    def api(self, **kwargs):
        """Handler for API over http, with explicit authentication parameters
        """
        if kwargs.get('mode', '') not in ('version', 'auth'):
            msg = check_apikey(kwargs)
            if msg: return msg
        return self.api_handler(kwargs)


    def api_handler(self, kwargs):
        """ Actual API handler, not exposed to Web-ui
        """
        mode = kwargs.get('mode')
        output = kwargs.get('output')

        if mode == 'set_config':
            if kwargs.get('section') == 'servers':
                kwargs['keyword'] = handle_server_api(output, kwargs)
            else:
                res = config.set_config(kwargs)
                if not res:
                    return report(output, _MSG_NO_SUCH_CONFIG)
            config.save_config()

        if mode == 'del_config':
            if del_from_section(kwargs):
                return report(output)
            else:
                return report(output, _MSG_NOT_IMPLEMENTED)

        if mode in ('get_config', 'set_config'):
            res, data = config.get_dconfig(kwargs.get('section'), kwargs.get('keyword'))
            return report(output, keyword='config', data=data)

        if mode == 'qstatus':
            if output == 'json':
                # Compatibility Fix:
                # Old qstatus did not have a keyword, so do not use one now.
                keyword = ''
            else:
                keyword = 'queue'
            return report(output, keyword=keyword, data=qstatus_data())

        if mode == 'queue':
            name = kwargs.get('name')
            sort = kwargs.get('sort')
            dir = kwargs.get('dir')
            value = kwargs.get('value')
            value2 = kwargs.get('value2')
            start = kwargs.get('start')
            limit = kwargs.get('limit')

            if name == 'delete':
                if value.lower()=='all':
                    nzbqueue.remove_all_nzo()
                    return report(output)
                elif value:
                    items = value.split(',')
                    nzbqueue.remove_multiple_nzos(items)
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE)
            elif name == 'delete_nzf':
                # Value = nzo_id Value2 = nzf_id
                if value and value2:
                    nzbqueue.remove_nzf(value, value2)
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE2)
            elif name == 'rename':
                if value and value2:
                    nzbqueue.rename_nzo(value, special_fixer(value2))
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE2)
            elif name == 'change_complete_action':
                # http://localhost:8080/sabnzbd/api?mode=queue&name=change_complete_action&value=hibernate_pc
                sabnzbd.change_queue_complete_action(value)
                return report(output)
            elif name == 'purge':
                nzbqueue.remove_all_nzo()
                return report(output)
            elif name == 'pause':
                if value:
                    items = value.split(',')
                    nzbqueue.pause_multiple_nzo(items)
                return report(output)
            elif name == 'resume':
                if value:
                    items = value.split(',')
                    nzbqueue.resume_multiple_nzo(items)
                return report(output)
            elif name == 'priority':
                if value and value2:
                    try:
                        try:
                            priority = int(value2)
                        except:
                            return report(output, _MSG_INT_VALUE)
                        pos = nzbqueue.set_priority(value, priority)
                        # Returns the position in the queue, -1 is incorrect job-id
                        return report(output, keyword='position', data=pos)
                    except:
                        return report(output, _MSG_NO_VALUE2)
                else:
                    return report(output, _MSG_NO_VALUE2)
            elif name == 'sort':
                if sort:
                    nzbqueue.sort_queue(sort,dir)
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE2)

            elif output in ('xml', 'json'):
                if sort and sort != 'index':
                    reverse = dir.lower() == 'desc'
                    nzbqueue.sort_queue(sort,reverse)

                # &history=1 will show unprocessed items in the history
                history = bool(kwargs.get('history'))

                info, pnfo_list, bytespersec, verboseList, dictn = \
                    build_queue(history=history, start=start, limit=limit, output=output)
                info['categories'] = info.pop('cat_list')
                info['scripts'] = info.pop('script_list')
                return report(output, keyword='queue', data=remove_callable(info))
            elif output == 'rss':
                return rss_qstatus()

            else:
                return report(output, _MSG_NOT_IMPLEMENTED)

        if mode == 'options':
            return options_list(output)

        if mode == 'translate':
            return report(output, keyword='value', data=T(kwargs.get('value')))

        name = kwargs.get('name', '')
        pp = kwargs.get('pp')
        script = kwargs.get('script')
        cat = kwargs.get('cat')
        priority = kwargs.get('priority')
        value = kwargs.get('value')
        value2 = kwargs.get('value2')
        start = kwargs.get('start')
        limit = kwargs.get('limit')
        nzbname = kwargs.get('nzbname')

        if mode in ('addfile', 'retry'):
            # When uploading via flash it will send the nzb in a kw arg called Filedata
            if name is None or isinstance(name, str) or isinstance(name, unicode):
                name = kwargs.get('Filedata')
            # Normal upload will send the nzb in a kw arg called nzbfile
            if name is None or isinstance(name, str) or isinstance(name, unicode):
                name = kwargs.get('nzbfile')

            if mode == 'addfile':
                # Regular job creation
                if name is not None and name.filename and name.value:
                    sabnzbd.add_nzbfile(name, pp, script, cat, priority, nzbname)
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE)
            else:
                # Retry job from history
                if retry_job(value, name):
                    return report(output)
                else:
                    return report(output, _MSG_NO_ITEM)


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
                                fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True, nzbname=nzbname)
                    else:
                        return report(output, _MSG_NO_FILE)
                else:
                    return report(output, _MSG_NO_PATH)
                return report(output)
            else:
                return report(output, _MSG_NO_VALUE)


        if mode == 'switch':
            if value and value2:
                pos, prio = nzbqueue.switch(value, value2)
                # Returns the new position and new priority (if different)
                if output not in ('xml', 'json'):
                    return report(output, data=(pos, prio))
                else:
                    return report(output, keyword='result', data={'position':pos, 'priority':prio})
            else:
                return report(output, _MSG_NO_VALUE2)


        if mode == 'change_cat':
            if value and value2:
                nzo_id = value
                cat = value2
                if cat == 'None':
                    cat = None
                nzbqueue.change_cat(nzo_id, cat)
                return report(output)
            else:
                return report(output, _MSG_NO_VALUE)

        if mode == 'change_script':
            if value and value2:
                nzo_id = value
                script = value2
                if script.lower() == 'none':
                    script = None
                nzbqueue.change_script(nzo_id, script)
                return report(output)
            else:
                return report(output, _MSG_NO_VALUE)

        if mode == 'change_opts':
            if value and value2 and value2.isdigit():
                nzbqueue.change_opts(value, int(value2))
            return report(output)

        if mode == 'fullstatus':
            return report(output, _MSG_NOT_IMPLEMENTED + ' YET') #xml_full()

        if mode == 'history':
            if name == 'delete':
                if value.lower()=='all':
                    history_db = cherrypy.thread_data.history_db
                    history_db.remove_history()
                    return report(output)
                elif value:
                    jobs = value.split(',')
                    history_db = cherrypy.thread_data.history_db
                    history_db.remove_history(jobs)
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE)
            elif not name:
                search = kwargs.get('search')
                history, pnfo_list, bytespersec = build_header(True)
                history['total_size'], history['month_size'], history['week_size'] = get_history_size()
                history['slots'], fetched_items, history['noofslots'] = build_history(start=start, limit=limit, verbose=True, search=search)
                return report(output, keyword='history', data=remove_callable(history))
            else:
                return report(output, _MSG_NOT_IMPLEMENTED)

        if mode == 'get_files':
            if value:
                return report(output, keyword='files', data=build_file_list(value))
            else:
                return report(output, _MSG_NO_VALUE)

        if mode == 'addurl':
            if name:
                sabnzbd.add_url(name, pp, script, cat, priority, nzbname)
                return report(output)
            else:
                return report(output, _MSG_NO_VALUE)

        if mode == 'addid':
            RE_NEWZBIN_URL = re.compile(r'/browse/post/(\d+)')
            newzbin_url = RE_NEWZBIN_URL.search(name.lower())

            if name: name = name.strip()
            if name and (name.isdigit() or len(name)==5):
                sabnzbd.add_msgid(name, pp, script, cat, priority, nzbname)
                return report(output)
            elif newzbin_url:
                sabnzbd.add_msgid(newzbin_url.group(1), pp, script, cat, priority, nzbname)
                return report(output)
            elif name:
                sabnzbd.add_url(name, pp, script, cat, priority, nzbname)
                return report(output)
            else:
                return report(output, _MSG_NO_VALUE)

        if mode == 'pause':
            scheduler.plan_resume(0)
            downloader.pause_downloader()
            return report(output)

        if mode == 'resume':
            scheduler.plan_resume(0)
            sabnzbd.unpause_all()
            return report(output)

        if mode == 'shutdown':
            sabnzbd.halt()
            cherrypy.engine.exit()
            sabnzbd.SABSTOP = True
            return report(output)

        if mode == 'warnings':
            if name == 'clear':
                return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.clear())
            elif name == 'show':
                return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.content())
            elif name:
                return report(output, _MSG_NOT_IMPLEMENTED)
            return report(output, keyword="warnings", data=sabnzbd.GUIHANDLER.content())

        if mode == 'config':
            if name == 'speedlimit' or name == 'set_speedlimit': # http://localhost:8080/sabnzbd/api?mode=config&name=speedlimit&value=400
                if not value: value = '0'
                if value.isdigit():
                    try:
                        value = int(value)
                    except:
                        return report(output, _MSG_NO_VALUE)
                    downloader.limit_speed(value)
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE)
            elif name == 'get_speedlimit':
                return report(output, keyword='speedlimit', data=int(downloader.get_limit()))
            elif name == 'set_colorscheme':
                if value:
                    if self.__prim:
                        cfg.web_color.set(value)
                    else:
                        cfg.web_color2.set(value)
                    return report(output)
                else:
                    return report(output, _MSG_NO_VALUE)
            elif name == 'set_pause':
                scheduler.plan_resume(IntConv(value))
                return report(output)

            elif name == 'set_apikey':
                cfg.api_key.set(config.create_api_key())
                config.save_config()
                return report(output, keyword='apikey', data=cfg.api_key())

            elif name == 'test_server':

                result, msg = test_nntp_server_dict(kwargs)
                response = {'result': result, 'message': msg}

                if output:
                    return report(output, data=response)
                else:
                    return msg

            else:
                return report(output, _MSG_NOT_IMPLEMENTED)

        if mode == 'get_cats':
            return report(output, keyword="categories", data=ListCats())

        if mode == 'get_scripts':
            return report(output, keyword="scripts", data=ListScripts())

        if mode == 'version':
            return report(output, keyword='version', data=sabnzbd.__version__)

        if mode == 'auth':
            auth = 'None'
            if cfg.username() and cfg.password():
                auth = 'login'
            if not cfg.disable_key():
                auth = 'apikey'
            return report(output, keyword='auth', data=auth)

        if mode == 'newzbin':
            if name == 'get_bookmarks':
                Bookmarks.do.run()
                return report(output)
            return report(output, _MSG_NOT_IMPLEMENTED)

        if mode == 'restart':
            sabnzbd.halt()
            cherrypy.engine.restart()
            return report(output)

        if mode == 'restart-repair':
            sabnzbd.request_repair()
            sabnzbd.halt()
            cherrypy.engine.restart()
            return report(output)

        if mode == 'disconnect':
            downloader.disconnect()
            return report(output)

        if mode == 'osx_icon':
            sabnzbd.OSX_ICON = int(value != '0')
            return report(output)

        if mode == 'rescan':
            nzbqueue.scan_jobs()
            return report(output)

        return report(output, _MSG_NOT_IMPLEMENTED)

    @cherrypy.expose
    def scriptlog(self, **kwargs):
        """ Duplicate of scriptlog of History, needed for some skins """
        # No session key check, due to fixed URLs

        name = kwargs.get('name')
        if name:
            history_db = cherrypy.thread_data.history_db
            return ShowString(history_db.get_name(name), history_db.get_script_log(name))
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def retry(self, **kwargs):
        """ Duplicate of retry of History, needed for some skins """
        msg = check_session(kwargs)
        if msg: return msg

        url = kwargs.get('url', '')
        pp = kwargs.get('pp')
        cat = kwargs.get('cat')
        script = kwargs.get('script')

        url = url.strip()
        if url and (url.isdigit() or len(url)==5):
            sabnzbd.add_msgid(url, pp, script, cat)
        elif url:
            sabnzbd.add_url(url, pp, script, cat)
        if url:
            return ShowOK(url)
        else:
            raise dcRaiser(self.__root, kwargs)

#------------------------------------------------------------------------------
class NzoPage(object):
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
                break

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
                            filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()


    def nzo_details(self, info, pnfo_list, nzo_id):
        slot = {}
        n = 0
        for pnfo in pnfo_list:
            if pnfo[PNFO_NZO_ID_FIELD] == nzo_id:
                repair = pnfo[PNFO_REPAIR_FIELD]
                unpack = pnfo[PNFO_UNPACK_FIELD]
                delete = pnfo[PNFO_DELETE_FIELD]
                unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)
                script = pnfo[PNFO_SCRIPT_FIELD]
                if script is None:
                    script = 'None'
                cat = pnfo[PNFO_EXTRA_FIELD1]
                if not cat:
                    cat = 'None'
                filename = xml_name(pnfo[PNFO_FILENAME_FIELD])
                priority = pnfo[PNFO_PRIORITY_FIELD]

                slot['nzo_id'] =  str(nzo_id)
                slot['cat'] = cat
                slot['filename'] = filename
                slot['script'] = script
                slot['priority'] = str(priority)
                slot['unpackopts'] = str(unpackopts)
                info['index'] = n
                break
            n += 1

        info['slot'] = slot
        info['script_list'] = ListScripts()
        info['cat_list'] = ListCats()
        info['noofslots'] = len(pnfo_list)

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
                            'size': format_bytes(bytes),
                            'sizeleft':format_bytes(bytes_left),
                            'nzf_id':nzf_id,
                            'age':calc_age(date),
                            'checked':checked}
                    active.append(line)
                break

        info['active_files'] = active
        return info


    def save_details(self, nzo_id, args, kwargs):
        index = kwargs.get('index', None)
        name = kwargs.get('name',None)
        pp = kwargs.get('pp',None)
        script = kwargs.get('script',None)
        cat = kwargs.get('cat',None)
        priority = kwargs.get('priority',None)
        nzo = sabnzbd.nzbqueue.get_nzo(nzo_id)

        if index != None:
            nzbqueue.switch(nzo_id, index)
        if name != None:
            sabnzbd.nzbqueue.change_name(nzo_id, special_fixer(name))
        if cat != None:
            sabnzbd.nzbqueue.change_cat(nzo_id,cat)
        if script != None:
            sabnzbd.nzbqueue.change_script(nzo_id,script)
        if pp != None:
            sabnzbd.nzbqueue.change_opts(nzo_id,pp)
        if priority != None and nzo and nzo.priority != int(priority):
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

        if nzbqueue.get_nzo(nzo_id):
            url = cherrypy._urljoin(self.__root, nzo_id)
        else:
            url = cherrypy._urljoin(self.__root, '../queue')
        if url and not url.endswith('/'):
            url += '/'
        raise dcRaiser(url, kwargs)

#------------------------------------------------------------------------------
class QueuePage(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verboseList = []
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        start = kwargs.get('start')
        limit = kwargs.get('limit')
        dummy2 = kwargs.get('dummy2')

        info, pnfo_list, bytespersec, self.__verboseList, self.__dict__ = build_queue(self.__web_dir, self.__root, self.__verbose, self.__prim, self.__verboseList, self.__dict__, start=start, limit=limit, dummy2=dummy2)

        template = Template(file=os.path.join(self.__web_dir, 'queue.tmpl'),
                            filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()



    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid = kwargs.get('uid')
        if uid:
            nzbqueue.remove_nzo(uid, False)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def purge(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzbqueue.remove_all_nzo()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def removeNzf(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzo_id = kwargs.get('nzo_id')
        nzf_id = kwargs.get('nzf_id')
        if nzo_id and nzf_id:
            nzbqueue.remove_nzf(nzo_id, nzf_id)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def tog_verbose(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        self.__verbose = not self.__verbose
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def tog_uid_verbose(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid = kwargs.get('uid')
        if self.__verboseList.count(uid):
            self.__verboseList.remove(uid)
        else:
            self.__verboseList.append(uid)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_queue_complete_action(self, **kwargs):
        """
        Action or script to be performed once the queue has been completed
        Scripts are prefixed with 'script_'
        """
        msg = check_session(kwargs)
        if msg: return msg
        action = kwargs.get('action')
        sabnzbd.change_queue_complete_action(action)
        cfg.queue_complete.set(action)
        config.save_config()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def switch(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid1 = kwargs.get('uid1')
        uid2 = kwargs.get('uid2')
        if uid1 and uid2:
            nzbqueue.switch(uid1, uid2)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_opts(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzo_id = kwargs.get('nzo_id')
        pp = kwargs.get('pp', '')
        if nzo_id and pp and pp.isdigit():
            nzbqueue.change_opts(nzo_id, int(pp))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_script(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzo_id = kwargs.get('nzo_id')
        script = kwargs.get('script', '')
        if nzo_id and script:
            if script == 'None':
                script = None
            nzbqueue.change_script(nzo_id, script)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_cat(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzo_id = kwargs.get('nzo_id')
        cat = kwargs.get('cat', '')
        if nzo_id and cat:
            if cat == 'None':
                cat = None
            nzbqueue.change_cat(nzo_id, cat)
            item = config.get_config('categories', cat)
            if item:
                cat, pp, script, priority = cat_to_opts(cat)
            else:
                script = cfg.dirscan_script()
                pp = cfg.dirscan_pp()
                priority = cfg.dirscan_priority()

            nzbqueue.change_script(nzo_id, script)
            nzbqueue.change_opts(nzo_id, pp)
            nzbqueue.set_priority(nzo_id, priority)

        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def shutdown(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            yield msg
        else:
            yield "Initiating shutdown..."
            sabnzbd.halt()
            cherrypy.engine.exit()
            yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
            sabnzbd.SABSTOP = True

    @cherrypy.expose
    def pause(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        scheduler.plan_resume(0)
        downloader.pause_downloader()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def resume(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        scheduler.plan_resume(0)
        sabnzbd.unpause_all()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def pause_nzo(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid = kwargs.get('uid', '')
        nzbqueue.pause_multiple_nzo(uid.split(','))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def resume_nzo(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid = kwargs.get('uid', '')
        nzbqueue.resume_multiple_nzo(uid.split(','))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_priority(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzbqueue.set_priority(kwargs.get('nzo_id'), kwargs.get('priority'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_avg_age(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzbqueue.sort_queue('avg_age', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_name(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzbqueue.sort_queue('name', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_size(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzbqueue.sort_queue('size', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_speedlimit(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        downloader.limit_speed(IntConv(kwargs.get('value')))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_pause(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        scheduler.plan_resume(IntConv(kwargs.get('value')))
        raise dcRaiser(self.__root, kwargs)

class HistoryPage(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verbose_list = []
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        start = kwargs.get('start')
        limit = kwargs.get('limit')
        search = kwargs.get('search')

        history, pnfo_list, bytespersec = build_header(self.__prim)

        history['isverbose'] = self.__verbose

        if cfg.newzbin_username() and cfg.newzbin_password():
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
                            filter=FILTER, searchList=[history], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def purge(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        history_db = cherrypy.thread_data.history_db
        history_db.remove_history()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        job = kwargs.get('job')
        if job:
            history_db = cherrypy.thread_data.history_db
            jobs = job.split(',')
            for job in jobs:
                PostProcessor.do.delete(job)
                history_db.remove_history(job)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def retry_pp(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        retry_job(kwargs.get('job'), kwargs.get('nzbfile'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def purge_failed(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        history_db = cherrypy.thread_data.history_db
        history_db.remove_failed()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def reset(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        #sabnzbd.reset_byte_counter()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def tog_verbose(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        jobs = kwargs.get('jobs')
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
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def scriptlog(self, **kwargs):
        """ Duplicate of scriptlog of History, needed for some skins """
        # No session key check, due to fixed URLs

        name = kwargs.get('name')
        if name:
            history_db = cherrypy.thread_data.history_db
            return ShowString(history_db.get_name(name), history_db.get_script_log(name))
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def retry(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        url = kwargs.get('url', '').strip()
        pp = kwargs.get('pp')
        cat = kwargs.get('cat')
        script = kwargs.get('script')
        if url and (url.isdigit() or len(url)==5):
            sabnzbd.add_msgid(url, pp, script, cat)
        elif url:
            sabnzbd.add_url(url, pp, script, cat, nzbname=kwargs.get('nzbname'))
        if url:
            return ShowOK(url)
        else:
            raise dcRaiser(self.__root, kwargs)

def retry_job(job, new_nzb):
    """ Re enter failed job in the download queue """
    if job:
        history_db = cherrypy.thread_data.history_db
        path = history_db.get_path(job)
        if path:
            nzbqueue.repair_job(platform_encode(path), new_nzb)
            history_db.remove_history(job)
            return True
    return False

#------------------------------------------------------------------------------
class ConfigPage(object):
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
    def index(self, **kwargs):
        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['configfn'] = config.get_filename()

        new = {}
        for svr in config.get_servers():
            new[svr] = {}
        conf['servers'] = new

        template = Template(file=os.path.join(self.__web_dir, 'config.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def restart(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            yield msg
        else:
            yield T('restart1')
            sabnzbd.halt()
            yield T('restart2')
            cherrypy.engine.restart()

    @cherrypy.expose
    def repair(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            yield msg
        else:
            sabnzbd.request_repair()
            yield T('restart1')
            sabnzbd.halt()
            yield T('restart2')
            cherrypy.engine.restart()

    @cherrypy.expose
    def scan(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzbqueue.scan_jobs()
        raise dcRaiser(self.__root, kwargs)

#------------------------------------------------------------------------------
LIST_DIRPAGE = ( \
    'download_dir', 'download_free', 'complete_dir', 'cache_dir', 'admin_dir',
    'nzb_backup_dir', 'dirscan_dir', 'dirscan_speed', 'script_dir',
    'email_dir', 'permissions', 'log_dir'
    )

class ConfigDirectories(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        for kw in LIST_DIRPAGE:
            conf[kw] = config.get_config('misc', kw)()

        conf['my_home'] = sabnzbd.DIR_HOME
        conf['my_lcldata'] = sabnzbd.DIR_LCLDATA

        # Temporary fix, problem with build_header
        conf['restart_req'] = sabnzbd.RESTART_REQ

        template = Template(file=os.path.join(self.__web_dir, 'config_directories.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveDirectories(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        cfg.complete_dir.set_create()
        for kw in LIST_DIRPAGE:
            value = kwargs.get(kw)
            if value != None:
                value = platform_encode(value)
                msg = config.get_config('misc', kw).set(value)
                if msg:
                    return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


SWITCH_LIST = \
    ('par2_multicore', 'par_option', 'enable_unrar', 'enable_unzip', 'enable_filejoin',
     'enable_tsjoin', 'send_group', 'fail_on_crc', 'top_only',
     'dirscan_opts', 'enable_par_cleanup', 'auto_sort', 'check_new_rel', 'auto_disconnect',
     'safe_postproc', 'no_dupes', 'replace_spaces', 'replace_illegal', 'auto_browser',
     'ignore_samples', 'pause_on_post_processing', 'quick_check', 'dirscan_script', 'nice', 'ionice',
     'dirscan_priority', 'ssl_type', 'pre_script'
    )

#------------------------------------------------------------------------------
class ConfigSwitches(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['nt'] = sabnzbd.WIN32
        conf['have_nice'] = bool(sabnzbd.newsunpack.NICE_COMMAND)
        conf['have_ionice'] = bool(sabnzbd.newsunpack.IONICE_COMMAND)

        for kw in SWITCH_LIST:
            conf[kw] = config.get_config('misc', kw)()

        conf['script_list'] = ListScripts()

        template = Template(file=os.path.join(self.__web_dir, 'config_switches.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveSwitches(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        for kw in SWITCH_LIST:
            item = config.get_config('misc', kw)
            value = platform_encode(kwargs.get(kw))
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


#------------------------------------------------------------------------------
GENERAL_LIST = (
    'host', 'port', 'username', 'password', 'disable_api_key',
    'refresh_rate', 'rss_rate',
    'cache_limit',
    'enable_https', 'https_port', 'https_cert', 'https_key'
    )

class ConfigGeneral(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        def ListColors(web_dir):
            lst = []
            web_dir = os.path.join(sabnzbd.DIR_INTERFACES ,web_dir)
            dd = os.path.abspath(web_dir + '/templates/static/stylesheets/colorschemes')
            if (not dd) or (not os.access(dd, os.R_OK)):
                return lst
            for color in globber(dd):
                col= os.path.basename(color).replace('.css','')
                if col != "_svn" and col != ".svn":
                    lst.append(col)
            return lst

        def add_color(dir, color):
            if dir:
                if not color:
                    try:
                        color = DEF_SKIN_COLORS[dir.lower()]
                    except KeyError:
                        return dir
                return '%s - %s' % (dir, color)
            else:
                return ''

        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['configfn'] = config.get_filename()

        # Temporary fix, problem with build_header
        conf['restart_req'] = sabnzbd.RESTART_REQ

        if sabnzbd.newswrapper.HAVE_SSL:
            conf['have_ssl'] = 1
        else:
            conf['have_ssl'] = 0

        wlist = []
        wlist2 = ['None']
        interfaces = globber(sabnzbd.DIR_INTERFACES)
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
                        if rweb != 'Mobile':
                            wlist.append(add_color(rweb, col))
                        wlist2.append(add_color(rweb, col))
                else:
                    if rweb != 'Mobile':
                        wlist.append(rweb)
                    wlist2.append(rweb)
        conf['web_list'] = wlist
        conf['web_list2'] = wlist2

        # Obsolete template variables, must exist and have a value
        conf['web_colors'] = ['None']
        conf['web_color'] = 'None'
        conf['web_colors2'] = ['None']
        conf['web_color2'] = 'None'

        conf['web_dir']  = add_color(cfg.web_dir(), cfg.web_color())
        conf['web_dir2'] = add_color(cfg.web_dir2(), cfg.web_color2())

        conf['language'] = cfg.language()
        list = list_languages(sabnzbd.DIR_LANGUAGE)
        if len(list) < 2:
            list = []
        conf['lang_list'] = list

        conf['disable_api_key'] = cfg.disable_key()
        conf['host'] = cfg.cherryhost()
        conf['port'] = cfg.cherryport()
        conf['https_port'] = cfg.https_port()
        conf['https_cert'] = cfg.https_cert()
        conf['https_key'] = cfg.https_key()
        conf['enable_https'] = cfg.enable_https()
        conf['username'] = cfg.username()
        conf['password'] = cfg.password.get_stars()
        conf['bandwidth_limit'] = cfg.bandwidth_limit()
        conf['refresh_rate'] = cfg.refresh_rate()
        conf['rss_rate'] = cfg.rss_rate()
        conf['cache_limit'] = cfg.cache_limit()
        conf['cleanup_list'] = List2String(cfg.cleanup_list())

        template = Template(file=os.path.join(self.__web_dir, 'config_general.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveGeneral(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        # Special handling for cache_limitstr
        #kwargs['cache_limit'] = kwargs.get('cache_limitstr')

        # Handle general options
        for kw in GENERAL_LIST:
            item = config.get_config('misc', kw)
            value = platform_encode(kwargs.get(kw))
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        # Handle special options
        language = kwargs.get('language')
        if language and language != cfg.language():
            cfg.language.set(language)
            reset_language(language)

        cleanup_list = kwargs.get('cleanup_list')
        if cleanup_list and sabnzbd.WIN32:
            cleanup_list = cleanup_list.lower()
        cfg.cleanup_list.set(cleanup_list)

        web_dir = kwargs.get('web_dir')
        web_dir2 = kwargs.get('web_dir2')
        change_web_dir(web_dir)
        try:
            web_dir2, web_color2 = web_dir2.split(' - ')
        except:
            web_color2 = ''
        web_dir2_path = real_path(sabnzbd.DIR_INTERFACES, web_dir2)

        if web_dir2 == 'None':
            cfg.web_dir2.set('')
        elif os.path.exists(web_dir2_path):
            cfg.web_dir2.set(web_dir2)
        cfg.web_color2.set(web_color2)

        bandwidth_limit = kwargs.get('bandwidth_limit')
        if bandwidth_limit != None:
            bandwidth_limit = IntConv(bandwidth_limit)
            cfg.bandwidth_limit.set(bandwidth_limit)

        config.save_config()

        # Update CherryPy authentication
        set_auth(cherrypy.config)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def generateAPIKey(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        logging.debug('API Key Changed')
        cfg.api_key.set(config.create_api_key())
        config.save_config()
        raise dcRaiser(self.__root, kwargs)

def change_web_dir(web_dir):
    try:
        web_dir, web_color = web_dir.split(' - ')
    except:
        try:
            web_color = DEF_SKIN_COLORS[web_dir.lower()]
        except:
            web_color = ''

    web_dir_path = real_path(sabnzbd.DIR_INTERFACES, web_dir)

    if not os.path.exists(web_dir_path):
        return badParameterResponse('Cannot find web template: %s' % unicoder(web_dir_path))
    else:
        cfg.web_dir.set(web_dir)
        cfg.web_color.set(web_color)


#------------------------------------------------------------------------------

class ConfigServer(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        new = {}
        servers = config.get_servers()
        for svr in servers:
            new[svr] = servers[svr].get_dict(safe=True)
        conf['servers'] = new

        if sabnzbd.newswrapper.HAVE_SSL:
            conf['have_ssl'] = 1
        else:
            conf['have_ssl'] = 0

        template = Template(file=os.path.join(self.__web_dir, 'config_server.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()


    @cherrypy.expose
    def addServer(self, **kwargs):
        return handle_server(kwargs, self.__root)


    @cherrypy.expose
    def saveServer(self, **kwargs):
        return handle_server(kwargs, self.__root)

    @cherrypy.expose
    def testServer(self, **kwargs):
        return handle_server_test(kwargs, self.__root)


    @cherrypy.expose
    def delServer(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        kwargs['section'] = 'servers'
        kwargs['keyword'] = kwargs.get('server')
        del_from_section(kwargs)
        raise dcRaiser(self.__root, kwargs)

def handle_server(kwargs, root=None):
    """ Internal server handler """
    msg = check_session(kwargs)
    if msg: return msg

    host = kwargs.get('host', '').strip()
    if not host:
        return badParameterResponse(T('error-needServer'))

    port = kwargs.get('port', '').strip()
    if not port:
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

    server = '%s:%s' % (host, port)

    svr = None
    old_server = kwargs.get('server')
    if old_server:
        svr = config.get_config('servers', old_server)
    if not svr:
        svr = config.get_config('servers', server)

    if svr:
        for kw in ('fillserver', 'ssl', 'enable', 'optional'):
            if kw not in kwargs.keys():
                kwargs[kw] = None
        svr.set_dict(kwargs)
        svr.rename(server)
    else:
        old_server = None
        config.ConfigServer(server, kwargs)

    config.save_config()
    downloader.update_server(old_server, server)
    if root:
        raise dcRaiser(root, kwargs)

def handle_server_test(kwargs, root):
    result, msg = test_nntp_server_dict(kwargs)
    return msg


def handle_server_api(output, kwargs):
    """ Special handler for API-call 'set_config'
    """
    name = kwargs.get('keyword')
    if not name:
        name = kwargs.get('name')
    if not name:
        host = kwargs.get('host')
        port = kwargs.get('port', '119')
        if host:
            name = '%s:%s' % (host, port)
        else:
            return name

    server = config.get_config('servers', name)
    if server:
        server.set_dict(kwargs)
        old_name = name
        name = '%s:%s' % (server.host(), server.port())
        server.rename(name)
    else:
        config.ConfigServer(name, kwargs)
        old_name = None
    downloader.update_server(old_name, name)
    return name


#------------------------------------------------------------------------------

class ConfigRss(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['script_list'] = ListScripts(default=True)
        pick_script = conf['script_list'] != []

        conf['cat_list'] = ListCats(default=True)
        pick_cat = conf['cat_list'] != []

        rss = {}
        feeds = config.get_rss()
        for feed in feeds:
            rss[feed] = feeds[feed].get_dict()
            filters = feeds[feed].filters()
            rss[feed]['filters'] = filters
            rss[feed]['filtercount'] = len(filters)

            rss[feed]['pick_cat'] = pick_cat
            rss[feed]['pick_script'] = pick_script

        conf['rss'] = rss

        # Find a unique new Feed name
        unum = 1
        while 'Feed'+str(unum) in feeds:
            unum += 1
        conf['feed'] = 'Feed' + str(unum)

        template = Template(file=os.path.join(self.__web_dir, 'config_rss.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def upd_rss_feed(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        if kwargs.get('enable') is not None:
            del kwargs['enable']
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
        msg = check_session(kwargs)
        if msg: return msg
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            cfg = None
        if cfg:
            cfg.enable.set(not cfg.enable())
            config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add_rss_feed(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        feed= Strip(kwargs.get('feed'))
        uri = Strip(kwargs.get('uri'))
        try:
            cfg = config.get_rss()[feed]
        except KeyError:
            cfg = None
        if (not cfg) and uri:
            config.ConfigRSS(feed, kwargs)
            # Clear out any existing reference to this feed name
            # Otherwise first-run detection can fail
            sabnzbd.rss.clear_feed(feed)
            config.save_config()

        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def upd_rss_filter(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            raise dcRaiser(self.__root, kwargs)

        pp = kwargs.get('pp')
        if IsNone(pp): pp = ''
        script = ConvertSpecials(kwargs.get('script'))
        cat = ConvertSpecials(kwargs.get('cat'))

        cfg.filters.update(int(kwargs.get('index',0)), (cat, pp, script, kwargs.get('filter_type'), \
                           platform_encode(kwargs.get('filter_text'))))
        config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def pos_rss_filter(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        feed = kwargs.get('feed')
        current = kwargs.get('current', 0)
        new = kwargs.get('new', 0)

        try:
            cfg = config.get_rss()[feed]
        except KeyError:
            raise dcRaiser(self.__root, kwargs)

        if current != new:
            cfg.filters.move(int(current), int(new))
            config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def del_rss_feed(self, *args, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        kwargs['section'] = 'rss'
        kwargs['keyword'] = kwargs.get('feed')
        del_from_section(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def del_rss_filter(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            raise dcRaiser(self.__root, kwargs)

        cfg.filters.delete(int(kwargs.get('index', 0)))
        config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def download_rss_feed(self, *args, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        if 'feed' in kwargs:
            feed = kwargs['feed']
            msg = sabnzbd.rss.run_feed(feed, download=True, force=True)
            if msg:
                return badParameterResponse(msg)
            else:
                return ShowRssLog(feed, False)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def test_rss_feed(self, *args, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        if 'feed' in kwargs:
            feed = kwargs['feed']
            msg = sabnzbd.rss.run_feed(feed, download=False, ignoreFirst=True)
            if msg:
                return badParameterResponse(msg)
            else:
                return ShowRssLog(feed, True)
        raise dcRaiser(self.__root, kwargs)


    @cherrypy.expose
    def rss_download(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        feed = kwargs.get('feed')
        id = kwargs.get('id')
        cat = kwargs.get('cat')
        pp = kwargs.get('pp')
        script = kwargs.get('script')
        priority = kwargs.get('priority', NORMAL_PRIORITY)
        nzbname = kwargs.get('nzbname')
        if id and id.isdigit():
            sabnzbd.add_msgid(id, pp, script, cat, priority, nzbname)
        elif id:
            sabnzbd.add_url(id, pp, script, cat, priority, nzbname)
        # Need to pass the title instead
        sabnzbd.rss.flag_downloaded(feed, id)
        raise dcRaiser(self.__root, kwargs)


#------------------------------------------------------------------------------
_SCHED_ACTIONS = ('resume', 'pause', 'pause_all', 'shutdown', 'restart', 'speedlimit',
                  'pause_post', 'resume_post', 'scan_folder')

class ConfigScheduling(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        def get_days():
            days = {}
            days["*"] = T('daily')
            days["1"] = T('monday')
            days["2"] = T('tuesday')
            days["3"] = T('wednesday')
            days["4"] = T('thursday')
            days["5"] = T('friday')
            days["6"] = T('saturday')
            days["7"] = T('sunday')
            return days

        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        actions = []
        actions.extend(_SCHED_ACTIONS)
        days = get_days()
        conf['schedlines'] = []
        snum = 1
        conf['taskinfo'] = []
        for ev in scheduler.sort_schedules(forward=True):
            line = ev[3]
            conf['schedlines'].append(line)
            try:
                m, h, day, action = line.split(' ', 3)
            except:
                continue
            action = action.strip()
            if action in actions:
                action = T("sch-" + action)
            else:
                try:
                    act, server = action.split()
                except ValueError:
                    act = ''
                if act in ('enable_server', 'disable_server'):
                    action = T("sch-" + act) + ' ' + server
            item = (snum, h, '%02d' % int(m), days.get(day, '**'), action)
            conf['taskinfo'].append(item)
            snum += 1


        actions_lng = {}
        for action in actions:
            actions_lng[action] = T("sch-" + action)
        for server in config.get_servers():
            actions.append(server)
            actions_lng[server] = server
        conf['actions'] = actions
        conf['actions_lng'] = actions_lng

        template = Template(file=os.path.join(self.__web_dir, 'config_scheduling.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def addSchedule(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        minute = kwargs.get('minute')
        hour = kwargs.get('hour')
        dayofweek = kwargs.get('dayofweek')
        action = kwargs.get('action')
        arguments = kwargs.get('arguments')

        arguments = arguments.strip().lower()
        if arguments in ('on', 'enable'):
            arguments = '1'
        elif arguments in ('off','disable'):
            arguments = '0'

        if minute and hour  and dayofweek and action:
            if (action == 'speedlimit') and arguments.isdigit():
                pass
            elif action in _SCHED_ACTIONS:
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
                sched = cfg.schedules()
                sched.append('%s %s %s %s %s' %
                                 (minute, hour, dayofweek, action, arguments))
                cfg.schedules.set(sched)

        config.save_config()
        scheduler.restart(force=True)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def delSchedule(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        schedules = cfg.schedules()
        line = kwargs.get('line')
        if line and line in schedules:
            schedules.remove(line)
            cfg.schedules.set(schedules)
        config.save_config()
        scheduler.restart(force=True)
        raise dcRaiser(self.__root, kwargs)

#------------------------------------------------------------------------------
class ConfigNewzbin(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__bookmarks = []

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['username_newzbin'] = cfg.newzbin_username()
        conf['password_newzbin'] = cfg.newzbin_password.get_stars()
        conf['newzbin_bookmarks'] = int(cfg.newzbin_bookmarks())
        conf['newzbin_unbookmark'] = int(cfg.newzbin_unbookmark())
        conf['bookmark_rate'] = cfg.bookmark_rate()

        conf['bookmarks_list'] = self.__bookmarks

        conf['matrix_username'] = cfg.matrix_username()
        conf['matrix_apikey'] = cfg.matrix_apikey()

        template = Template(file=os.path.join(self.__web_dir, 'config_newzbin.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveNewzbin(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        cfg.newzbin_username.set(kwargs.get('username_newzbin'))
        cfg.newzbin_password.set(kwargs.get('password_newzbin'))
        cfg.newzbin_bookmarks.set(kwargs.get('newzbin_bookmarks'))
        cfg.newzbin_unbookmark.set(kwargs.get('newzbin_unbookmark'))
        cfg.bookmark_rate.set(kwargs.get('bookmark_rate'))

        cfg.matrix_username.set(kwargs.get('matrix_username'))
        cfg.matrix_apikey.set(kwargs.get('matrix_apikey'))

        config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def saveMatrix(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        cfg.matrix_username.set(kwargs.get('matrix_username'))
        cfg.matrix_apikey.set(kwargs.get('matrix_apikey'))

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


    @cherrypy.expose
    def getBookmarks(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        Bookmarks.do.run()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def showBookmarks(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        self.__bookmarks = Bookmarks.do.bookmarksList()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def hideBookmarks(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        self.__bookmarks = []
        raise dcRaiser(self.__root, kwargs)

#------------------------------------------------------------------------------

class ConfigCats(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        if cfg.newzbin_username() and cfg.newzbin_password():
            conf['newzbinDetails'] = True

        conf['script_list'] = ListScripts(default=True)

        categories = config.get_categories()
        conf['have_cats'] =  categories != {}
        conf['defdir'] = cfg.complete_dir.get_path()


        empty = { 'name':'', 'pp':'-1', 'script':'', 'dir':'', 'newzbin':'', 'priority':DEFAULT_PRIORITY }
        slotinfo = []
        slotinfo.append(empty)
        for cat in sorted(categories):
            slot = categories[cat].get_dict()
            slot['name'] = cat
            slotinfo.append(slot)
        conf['slotinfo'] = slotinfo

        template = Template(file=os.path.join(self.__web_dir, 'config_cat.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        kwargs['section'] = 'categories'
        kwargs['keyword'] = kwargs.get('name')
        del_from_section(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def save(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        newname = kwargs.get('newname', '').strip()
        name = kwargs.get('name')
        if newname:
            if name:
                config.delete('categories', name)
            name = newname.lower()
            if kwargs.get('dir'):
                kwargs['dir'] = platform_encode(kwargs['dir'])
            config.ConfigCat(name, kwargs)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def init_newzbin(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        config.define_categories(force=True)
        config.save_config()
        raise dcRaiser(self.__root, kwargs)


SORT_LIST = ( \
    'enable_tv_sorting', 'tv_sort_string', 'tv_categories',
    'enable_movie_sorting', 'movie_sort_string', 'movie_sort_extra', 'movie_extra_folder',
    'enable_date_sorting', 'date_sort_string', 'movie_categories', 'date_categories'
    )

#------------------------------------------------------------------------------
class ConfigSorting(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)
        conf['complete_dir'] = cfg.complete_dir.get_path()

        for kw in SORT_LIST:
            conf[kw] = config.get_config('misc', kw)()
        conf['cat_list'] = ListCats(True)
        #tvSortList = []

        template = Template(file=os.path.join(self.__web_dir, 'config_sorting.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveSorting(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        try:
            kwargs['movie_categories'] = kwargs['movie_cat']
        except:
            pass
        try:
            kwargs['date_categories'] = kwargs['date_cat']
        except:
            pass
        try:
            kwargs['tv_categories'] = kwargs['tv_cat']
        except:
            pass

        for kw in SORT_LIST:
            item = config.get_config('misc', kw)
            value = platform_encode(kwargs.get(kw))
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


#------------------------------------------------------------------------------

class ConnectionInfo(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__lastmail = None

    @cherrypy.expose
    def index(self, **kwargs):
        header, pnfo_list, bytespersec = build_header(self.__prim)

        header['logfile'] = sabnzbd.LOGFILE
        header['weblogfile'] = sabnzbd.WEBLOGFILE
        header['loglevel'] = str(cfg.log_level())

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
                        nzf_name = xml_name(nzf.filename)
                    except: #attribute error
                        nzf_name = xml_name(nzf.subject)
                    nzo_name = xml_name(nzo.final_name)

                busy.append((nw.thrdnum, art_name, nzf_name, nzo_name))

                if nw.connected:
                    connected += 1

            if server.warning and not (connected or server.errormsg):
                connected = unicoder(server.warning)

            if server.request and not server.info:
                connected = T('server-resolving')
            busy.sort()

            header['servers'].append((server.host, server.port, connected, busy, server.ssl,
                                      server.active, server.errormsg, server.fillserver, server.optional))

        wlist = []
        for w in sabnzbd.GUIHANDLER.content():
            w = w.replace('WARNING', Ta('warning')).replace('ERROR', Ta('error'))
            wlist.append(xml_name(w))
        header['warnings'] = wlist

        template = Template(file=os.path.join(self.__web_dir, 'connection_info.tmpl'),
                            filter=FILTER, searchList=[header], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def disconnect(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        downloader.disconnect()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def testmail(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        logging.info("Sending testmail")
        pack = {}
        pack['download'] = ['action 1', 'action 2']
        pack['unpack'] = ['action 1', 'action 2']

        self.__lastmail= emailer.endjob('I had a d\xe8ja vu', 123, 'unknown', True,
                                      os.path.normpath(os.path.join(cfg.COMPLETE_DIR.get_path(), '/unknown/I had a d\xe8ja vu')),
                                      str(123*MEBI), pack, 'my_script', 'Line 1\nLine 2\nLine 3\nd\xe8ja vu\n', 0)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def showlog(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        try:
            sabnzbd.LOGHANDLER.flush()
        except:
            pass
        return cherrypy.lib.static.serve_file(sabnzbd.LOGFILE, "application/x-download", "attachment")

    @cherrypy.expose
    def showweb(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        if sabnzbd.WEBLOGFILE:
            return cherrypy.lib.static.serve_file(sabnzbd.WEBLOGFILE, "application/x-download", "attachment")
        else:
            return "Web logging is off!"

    @cherrypy.expose
    def clearwarnings(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        sabnzbd.GUIHANDLER.clear()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_loglevel(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        cfg.log_level.set(kwargs.get('loglevel'))
        config.save_config()

        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def unblock_server(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        downloader.unblock(kwargs.get('server'))
        # Short sleep so that UI shows new server status
        time.sleep(1.0)
        raise dcRaiser(self.__root, kwargs)


def Protected():
    return badParameterResponse("Configuration is locked")

def badParameterResponse(msg):
    """Return a html page with error message and a 'back' button
    """
    return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
           <title>SABnzbd+ %s - %s/title>
</head>
<body>
           <h3>%s</h3>
           %s
           <br><br>
           <FORM><INPUT TYPE="BUTTON" VALUE="%s" ONCLICK="history.go(-1)"></FORM>
</body>
</html>
''' % (sabnzbd.__version__, T('error'), T('badParm'), unicoder(msg), T('button-back'))

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
           <FORM><INPUT TYPE="BUTTON" VALUE="%s" ONCLICK="history.go(-1)"></FORM>
           <h3>%s</h3>
           <code><pre>
           %s
           </pre></code><br/><br/>
</body>
</html>
''' % (name, T('button-back'), name, escape(msg))

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
           <FORM><INPUT TYPE="BUTTON" VALUE="%s" ONCLICK="history.go(-1)"></FORM>
           <h3>%s</h3>
           <code><pre>
           %s
           </pre></code><br/><br/>
</body>
</html>
''' % (xml_name(name), T('button-back'), xml_name(name), escape(unicoder(msg)))


def ShowOK(url):
    return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
           <title>%s</title>
</head>
<body>
           <FORM><INPUT TYPE="BUTTON" VALUE="%s" ONCLICK="history.go(-1)"></FORM>
           <br/><br/>
           %s
           <br/><br/>
</body>
</html>
''' % (escape(url), T('button-back'), T('msg-reAdded@1') % escape(url))


def _make_link(qfeed, job):
    # Return downlink for a job
    url = job.get('url', '')
    status = job.get('status', '')
    title = job.get('title', '')
    cat = job.get('cat')
    pp = job.get('pp')
    script = job.get('script')
    prio = job.get('prio')

    name = urllib.quote_plus(url)
    if 'nzbindex.nl/' in url or 'nzbindex.com/' in url or 'nzbclub.com/' in url:
        nzbname = ''
    else:
        nzbname = '&nzbname=%s' % urllib.quote(sanitize_foldername(latin1(title)))
    if cat:
        cat = '&cat=' + escape(cat)
    else:
        cat = ''
    if pp is None:
        pp = ''
    else:
        pp = '&pp=' + escape(str(pp))
    if script:
        script = '&script=' + escape(script)
    else:
        script = ''
    if prio:
        prio = '&priority=' + str(prio)
    else:
        prio = ''

    star = '&nbsp;*' * int(status.endswith('*'))

    if url.isdigit():
        title = '<a href="https://www.newzbin.com/browse/post/%s/" target="_blank">%s</a>' % (url, title)
    else:
        title = xml_name(title)

    return '<a href="rss_download?session=%s&feed=%s&id=%s%s%s%s%s%s">%s</a>&nbsp;&nbsp;&nbsp;%s%s<br/>' % \
           (cfg.api_key() ,qfeed, name, cat, pp, script, prio, nzbname, T('link-download'), title, star)


def ShowRssLog(feed, all):
    """Return a html page listing an RSS log and a 'back' button
    """
    jobs = sabnzbd.rss.show_result(feed)
    names = jobs.keys()
    # Sort in the order the jobs came from the feed
    names.sort(lambda x, y: jobs[x].get('order', 0) - jobs[y].get('order', 0))

    qfeed = escape(feed.replace('/','%2F').replace('?', '%3F'))

    doneStr = []
    for x in names:
        job = jobs[x]
        if job['status'][0] == 'D':
            doneStr.append('%s<br/>' % xml_name(job['title']))

    goodStr = []
    for x in names:
        job = jobs[x]
        if job['status'][0] == 'G':
            goodStr.append(_make_link(qfeed, job))

    badStr = []
    for x in names:
        job = jobs[x]
        if job['status'][0] == 'B':
            badStr.append(_make_link(qfeed, job))

    if all:
        return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
               <title>%s</title>
</head>
<body>
               <form>
               <input type="submit" onclick="this.form.action='.'; this.form.submit(); return false;" value="%s"/>
               </form>
               <h3>%s</h3>
               %s<br/><br/>
               <b>%s</b><br/>
               %s
               <br/>
               <b>%s</b><br/>
               %s
               <br/>
               <b>%s</b><br/>
               %s
               <br/>
</body>
</html>
''' % (escape(feed), T('button-back'), escape(feed), T('explain-rssStar'), T('rss-matched'), \
       ''.join(goodStr), T('rss-notMatched'), ''.join(badStr), T('rss-done'), ''.join(doneStr))
    else:
        return '''
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">
<html>
<head>
               <title>%s</title>
</head>
<body>
               <form>
               <input type="submit" onclick="this.form.action='.'; this.form.submit(); return false;" value="%s"/>
               </form>
               <h3>%s</h3>
               <b>%s</b><br/>
               %s
               <br/>
</body>
</html>
''' % (escape(feed), T('button-back'), escape(feed), T('rss-downloaded'), ''.join(doneStr))


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

    header = { 'T': T, 'Tspec': Tspec, 'version':sabnzbd.__version__, 'paused':downloader.paused(),
               'pause_int': scheduler.pause_int(), 'paused_all': sabnzbd.PAUSED_ALL,
               'uptime':uptime, 'color_scheme':color }
    speed_limit = downloader.get_limit()
    if speed_limit <= 0:
        speed_limit = ''

    header['helpuri'] = 'http://wiki.sabnzbd.org/'
    header['diskspace1'] = "%.2f" % diskfree(cfg.download_dir.get_path())
    header['diskspace2'] = "%.2f" % diskfree(cfg.complete_dir.get_path())
    header['diskspacetotal1'] = "%.2f" % disktotal(cfg.download_dir.get_path())
    header['diskspacetotal2'] = "%.2f" % disktotal(cfg.complete_dir.get_path())
    header['loadavg'] = loadavg()
    header['speedlimit'] = "%s" % speed_limit
    header['restart_req'] = sabnzbd.RESTART_REQ
    header['have_warnings'] = str(sabnzbd.GUIHANDLER.count())
    header['last_warning'] = sabnzbd.GUIHANDLER.last()
    header['active_lang'] = cfg.language()
    if prim:
        header['webdir'] = sabnzbd.WEB_DIR
    else:
        header['webdir'] = sabnzbd.WEB_DIR2

    header['finishaction'] = sabnzbd.QUEUECOMPLETE
    header['nt'] = sabnzbd.WIN32
    header['darwin'] = sabnzbd.DARWIN
    header['power_options'] = sabnzbd.WIN32 or sabnzbd.DARWIN or sabnzbd.LINUX_POWER

    header['session'] = cfg.api_key()

    bytespersec = BPSMeter.do.get_bps()
    qnfo = nzbqueue.queue_info()

    bytesleft = qnfo[QNFO_BYTES_LEFT_FIELD]
    bytes = qnfo[QNFO_BYTES_FIELD]

    header['kbpersec'] = "%.2f" % (bytespersec / KIBI)
    header['speed'] = to_units(bytespersec, spaces=1)
    header['mbleft']   = "%.2f" % (bytesleft / MEBI)
    header['mb']       = "%.2f" % (bytes / MEBI)
    header['sizeleft']   = format_bytes(bytesleft)
    header['size']       = format_bytes(bytes)

    status = ''
    if downloader.paused():
        status = 'Paused'
    elif bytespersec > 0:
        status = 'Downloading'
    else:
        status = 'Idle'
    header['status'] = "%s" % status

    anfo  = ArticleCache.do.cache_info()

    header['cache_art'] = str(anfo[ANFO_ARTICLE_SUM_FIELD])
    header['cache_size'] = format_bytes(anfo[ANFO_CACHE_SIZE_FIELD])
    header['cache_max'] = str(anfo[ANFO_CACHE_LIMIT_FIELD])

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
        header['eta'] = T('unknown')

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
    'email_account', 'email_pwd', 'email_dir', 'email_rss'
    )

class ConfigEmail(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['my_home'] = sabnzbd.DIR_HOME
        conf['my_lcldata'] = sabnzbd.DIR_LCLDATA

        for kw in LIST_EMAIL:
            conf[kw] = config.get_config('misc', kw).get_string()

        template = Template(file=os.path.join(self.__web_dir, 'config_email.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveEmail(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        for kw in LIST_EMAIL:
            msg = config.get_config('misc', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('error-badValue@2') % (kw, unicoder(msg)))

        config.save_config()
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

        stageLine = []
        for stage in history['stage_log']:
            stageLine.append("<tr><dt>Stage %s</dt>" % stage['name'])
            actions = []
            for action in stage['actions']:
                actions.append("<dd>%s</dd>" % (action))
            actions.sort()
            actions.reverse()
            for act in actions:
                stageLine.append(act)
            stageLine.append("</tr>")
        item.description = ''.join(stageLine)
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


def qstatus_data():
    """Build up the queue status as a nested object and output as a JSON object
    """

    qnfo = nzbqueue.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    jobs = []
    bytesleftprogess = 0
    bpsnow = BPSMeter.do.get_bps()
    for pnfo in pnfo_list:
        filename = pnfo[PNFO_FILENAME_FIELD]
        msgid = pnfo[PNFO_MSGID_FIELD]
        bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
        bytesleftprogess += pnfo[PNFO_BYTES_LEFT_FIELD]
        bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
        nzo_id = pnfo[PNFO_NZO_ID_FIELD]
        jobs.append( { "id" : nzo_id,
                        "mb":bytes,
                        "mbleft":bytesleft,
                        "filename":unicoder(filename),
                        "msgid":msgid,
                        "timeleft":calc_timeleft(bytesleftprogess, bpsnow) } )

    state = "IDLE"
    if downloader.paused():
        state = "PAUSED"
    elif qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI > 0:
        state = "DOWNLOADING"

    status = {
        "state" : state,
        "paused" : downloader.paused(),
        "pause_int" : scheduler.pause_int(),
        "kbpersec" : BPSMeter.do.get_bps() / KIBI,
        "speed" : to_units(BPSMeter.do.get_bps()),
        "mbleft" : qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
        "mb" : qnfo[QNFO_BYTES_FIELD] / MEBI,
        "noofslots" : len(pnfo_list),
        "have_warnings" : str(sabnzbd.GUIHANDLER.count()),
        "diskspace1" : diskfree(cfg.download_dir.get_path()),
        "diskspace2" : diskfree(cfg.complete_dir.get_path()),
        "timeleft" : calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsnow),
        "loadavg" : loadavg(),
        "jobs" : jobs
    }
    return status


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

                line = {'filename':fn,
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

                line = {'filename':fn,
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

                line = {'filename':fn, 'set':_set,
                        'mbleft':"%.2f" % (bytes_left / MEBI),
                        'mb':"%.2f" % (bytes / MEBI),
                        'bytes':"%.2f" % bytes,
                        'age':age, 'id':str(n), 'status':'queued'}
                jobs.append(line)
                n += 1

    return jobs


def get_history_size():
    history_db = cherrypy.thread_data.history_db
    bytes, month, week = history_db.get_history_size()
    return (format_bytes(bytes), format_bytes(month), format_bytes(week))

def build_history(start=None, limit=None, verbose=False, verbose_list=None, search=None):

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
        search_text = search_text.strip().replace('*','.*').replace(' ','.*') + '.*?'
        try:
            re_search = re.compile(search_text, re.I)
        except:
            logging.error(Ta('error-regex@1'), search_text)
            return False
        return re_search.search(text)

    # Grab any items that are active or queued in postproc
    queue = PostProcessor.do.get_queue()

    # Filter out any items that don't match the search
    if search:
        queue = [nzo for nzo in queue if matches_search(nzo.final_name, search)]

    # Multi-page support for postproc items
    if start > len(queue):
        # On a page where we shouldn't show postproc items
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
    # Remove the amount of postproc items from the db request for history items
    limit -= len(queue)

    # Aquire the db instance
    history_db = cherrypy.thread_data.history_db
    # Fetch history items
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

    # Reverse the queue to add items to the top (faster than insert)
    items.reverse()

    # Add the postproc items to the top of the history
    items = get_active_history(queue, items)

    # Unreverse the queue
    items.reverse()

    retry_folders = []
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
        path = platform_encode(item.get('path', ''))
        item['retry'] = int(bool(item.get('status') == 'Failed' and \
                                 path and \
                                 path not in retry_folders and \
                                 path.startswith(cfg.download_dir.get_path()) and \
                                 os.path.exists(path)) and \
                                 not bool(globber(os.path.join(path, JOB_ADMIN), 'SABnzbd_n*')) \
                                 )
        if item['retry']:
            retry_folders.append(path)

    return (items, fetched_items, total_items)


def json_list(section, lst):
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

    return { section : d }


class xml_factory(object):
    """
    Recursive xml string maker. Feed it a mixed tuple/dict/item object and will output into an xml string
    Current limitations:
        In Two tiered lists hardcoded name of "item": <cat_list><item> </item></cat_list>
        In Three tiered lists hardcoded name of "slot": <tier1><slot><tier2> </tier2></slot></tier1>
    """
    def __init__(self):
        self.__text = ''

    def _tuple(self, keyw, lst):
        text = []
        for item in lst:
            text.append(self.run(keyw, item))
        return ''.join(text)

    def _dict(self, keyw, lst):
        text = []
        for key in lst.keys():
            text.append(self.run(key, lst[key]))
        if keyw:
            return '<%s>%s</%s>\n' % (keyw, ''.join(text), keyw)
        else:
            return ''

    def _list(self, keyw, lst):
        text = []
        for cat in lst:
            if isinstance(cat, dict):
                text.append(self._dict(plural_to_single(keyw, 'slot'), cat))
            elif isinstance(cat, list):
                text.append(self._list(plural_to_single(keyw, 'list'), cat))
            elif isinstance(cat, tuple):
                text.append(self._tuple(plural_to_single(keyw, 'tuple'), cat))
            else:
                if not isinstance(cat, basestring):
                    cat = str(cat)
                name = plural_to_single(keyw, 'item')
                text.append('<%s>%s</%s>\n' % (name, xml_name(cat, encoding='utf-8'), name))
        if keyw:
            return '<%s>%s</%s>\n' % (keyw, ''.join(text), keyw)
        else:
            return ''

    def run(self, keyw, lst):
        if isinstance(lst, dict):
            text = self._dict(keyw, lst)
        elif isinstance(lst, list):
            text = self._list(keyw, lst)
        elif isinstance(lst, tuple):
            text = self._tuple(keyw, lst)
        elif keyw:
            text = '<%s>%s</%s>\n' % (keyw, xml_name(lst, encoding='utf-8'), keyw)
        else:
            text = ''
        return text


def build_queue(web_dir=None, root=None, verbose=False, prim=True, verboseList=None,
                dictionary=None, history=False, start=None, limit=None, dummy2=None, output=None):
    if output:
        converter = unicoder
    else:
        converter = xml_name

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

    if cfg.newzbin_username() and cfg.newzbin_password():
        info['newzbinDetails'] = True

    if cfg.refresh_rate() > 0:
        info['refresh_rate'] = str(cfg.refresh_rate())
    else:
        info['refresh_rate'] = ''

    datestart = datetime.datetime.now()

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
        slot['filename'] = converter(filename)
        slot['cat'] = cat
        slot['mbleft'] = "%.2f" % mbleft
        slot['mb'] = "%.2f" % mb
        slot['size'] = format_bytes(bytes)
        slot['sizeleft'] = format_bytes(bytesleft)
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
                    fn = converter(fn)

                    age = calc_age(date)

                    line = {'filename':fn,
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'age':age}
                    finished.append(line)

                for tup in active_files:
                    bytes_left, bytes, fn, date, nzf_id = tup
                    fn = converter(fn)

                    age = calc_age(date)

                    line = {'filename':fn,
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'nzf_id':nzf_id,
                            'age':age}
                    active.append(line)

                for tup in queued_files:
                    _set, bytes_left, bytes, fn, date = tup
                    fn = converter(fn)
                    _set = converter(_set)

                    age = calc_age(date)

                    line = {'filename':fn, 'set':_set,
                            'mbleft':"%.2f" % (bytes_left / MEBI),
                            'mb':"%.2f" % (bytes / MEBI),
                            'size': format_bytes(bytes),
                            'sizeleft': format_bytes(bytes_left),
                            'age':age}
                    queued.append(line)

            slot['finished'] = finished
            slot['active'] = active
            slot['queued'] = queued


        if (start <= n  and n < start + limit) or not limit:
            slotinfo.append(slot)
        n += 1

    if slotinfo:
        info['slots'] = slotinfo
    else:
        info['slots'] = ''
        verboseList = []

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

    return info, pnfo_list, bytespersec, verboseList, dictn



def rss_qstatus():
    """ Return a RSS feed with the queue status
    """
    qnfo = nzbqueue.queue_info()
    pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

    rss = RSS()
    rss.channel.title = "SABnzbd Queue"
    rss.channel.description = "Overview of current downloads"
    rss.channel.link = "http://%s:%s/sabnzbd/queue" % ( \
        cfg.cherryhost(), cfg.cherryport() )
    rss.channel.language = "en"

    item = Item()
    item.title = 'Total ETA: %s - Queued: %.2f MB - Speed: %.2f kB/s' % \
                 (
                  calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], BPSMeter.do.get_bps()),
                  qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI,
                  BPSMeter.do.get_bps() / KIBI
                 )
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
            cfg.cherryhost(), cfg.cherryport() )
        statusLine  = []
        statusLine.append('<tr>')
        #Total MB/MB left
        statusLine.append('<dt>Remain/Total: %.2f/%.2f MB</dt>' % (bytesleft, bytes))
        #ETA
        sum_bytesleft += pnfo[PNFO_BYTES_LEFT_FIELD]
        statusLine.append("<dt>ETA: %s </dt>" % calc_timeleft(sum_bytesleft, BPSMeter.do.get_bps()))
        statusLine.append("<dt>Age: %s</dt>" % calc_age(pnfo[PNFO_AVG_DATE_FIELD]))
        statusLine.append("</tr>")
        item.description = ''.join(statusLine)
        rss.addItem(item)

    rss.channel.lastBuildDate = std_time(time.time())
    rss.channel.pubDate = rss.channel.lastBuildDate
    rss.channel.ttl = "1"
    return rss.write()


def format_history_for_queue():
    ''' Retrieves the information on currently active history items, and formats them for displaying in the queue '''
    slotinfo = []
    history_items = get_active_history()

    for item in history_items:
        slot = {'nzo_id':item['nzo_id'],
                'msgid':item['report'], 'filename':xml_name(item['name']), 'loaded':False,
                'stages':item['stage_log'], 'status':item['status'], 'bytes':item['bytes'],
                'size':item['size']}
        slotinfo.append(slot)

    return slotinfo


def get_active_history(queue=None, items=None):
    # Get the currently in progress and active history queue.
    if items is None:
        items = []
    if queue is None:
        queue = PostProcessor.do.get_queue()

    for nzo in queue:
        t = build_history_info(nzo)
        item = {}
        item['completed'], item['name'], item['nzb_name'], item['category'], item['pp'], item['script'], item['report'], \
            item['url'], item['status'], item['nzo_id'], item['storage'], item['path'], item['script_log'], \
            item['script_line'], item['download_time'], item['postproc_time'], item['stage_log'], \
            item['downloaded'], item['completeness'], item['fail_message'], item['url_info'], item['bytes'] = t
        item['action_line'] = nzo.action_line
        item = unpack_history_info(item)

        item['loaded'] = nzo.pp_active
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


def options_list(output):
    return report(output, keyword='options', data=
        {
        'yenc' : sabnzbd.decoder.HAVE_YENC,
        'par2' : sabnzbd.newsunpack.PAR2_COMMAND,
        'par2c' : sabnzbd.newsunpack.PAR2C_COMMAND,
        'rar' : sabnzbd.newsunpack.RAR_COMMAND,
        'zip' : sabnzbd.newsunpack.ZIP_COMMAND,
        'nice' : sabnzbd.newsunpack.NICE_COMMAND,
        'ionice' : sabnzbd.newsunpack.IONICE_COMMAND,
        'ssl' : sabnzbd.newswrapper.HAVE_SSL
        })
