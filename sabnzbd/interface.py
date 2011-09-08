#!/usr/bin/python -OO
# Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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
import time
import cherrypy
import logging
import re
import urllib
from xml.sax.saxutils import escape

from sabnzbd.utils.rsslib import RSS, Item
import sabnzbd
import sabnzbd.rss
import sabnzbd.scheduler as scheduler

from Cheetah.Template import Template
import sabnzbd.emailer as emailer
from sabnzbd.misc import real_path, to_units, \
     diskfree, sanitize_foldername, time_format, HAVE_AMPM, \
     cat_to_opts, int_conv, globber, remove_all
from sabnzbd.panic import panic_old_queue
from sabnzbd.newswrapper import GetServerParms
from sabnzbd.newzbin import Bookmarks
from sabnzbd.bpsmeter import BPSMeter
from sabnzbd.encoding import TRANS, xml_name, LatinFilter, unicoder, special_fixer, \
                             platform_encode, latin1, encode_for_xml
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.newsunpack
from sabnzbd.postproc import PostProcessor
from sabnzbd.downloader import Downloader
from sabnzbd.nzbqueue import NzbQueue
import sabnzbd.wizard
from sabnzbd.utils.servertests import test_nntp_server_dict

from sabnzbd.constants import *
from sabnzbd.lang import list_languages, set_language

from sabnzbd.api import list_scripts, list_cats, del_from_section, \
     api_handler, build_queue, rss_qstatus, \
     retry_job, build_header, build_history, del_job_files, \
     format_bytes, calc_age, std_time, report, del_hist_job, Ttemplate

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
        return badParameterResponse(T('Warning: LOCALHOST is ambiguous, use numerical IP-address.'))

    if GetServerParms(host, int_conv(port)):
        return ""
    else:
        return badParameterResponse(T('Server address "%s:%s" is not valid.') % (host, port))


def ConvertSpecials(p):
    """ Convert None to 'None' and 'Default' to ''
    """
    if p is None:
        p = 'None'
    elif p.lower() == T('Default').lower():
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

def rssRaiser(root, kwargs):
    return Raiser(root, feed=kwargs.get('feed'))

#------------------------------------------------------------------------------
def IsNone(value):
    """ Return True if either None, 'None' or '' """
    return value==None or value=="" or value.lower()=='none'


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
        conf.update({'tools.basic_auth.on' : True, 'tools.basic_auth.realm' : cfg.login_realm(),
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
        logging.warning(Ta('Missing Session key'))
        msg = T('Error: Session Key Required')
    elif key != cfg.api_key():
        logging.warning(Ta('Error: Session Key Incorrect'))
        msg = T('Error: Session Key Incorrect')
    return msg


#------------------------------------------------------------------------------
def check_apikey(kwargs, nokey=False):
    """ Check api key or nzbkey
        Return None when OK, otherwise an error message
    """
    output = kwargs.get('output')
    mode = kwargs.get('mode', '')
    callback = kwargs.get('callback')

    # Don't give a visible warning: these commands are used by some
    # external utilities to detect if username/password is required
    # The cfg item can suppress all visible warnings
    special = mode in ('get_scripts', 'qstatus') or not cfg.api_warnings.get()

    # For NZB upload calls, a separate key can be used
    nzbkey = kwargs.get('mode', '') in ('addid', 'addurl', 'addfile', 'addlocalfile')

    # First check APIKEY, if OK that's sufficient
    if not (cfg.disable_key() or nokey):
        key = kwargs.get('apikey')
        if not key:
            if not special:
                logging.warning(Ta('API Key missing, please enter the api key from Config->General into your 3rd party program:'))
            return report(output, 'API Key Required', callback=callback)
        elif nzbkey and key == cfg.nzb_key():
            return None
        elif key == cfg.api_key():
            return None
        else:
            logging.warning(Ta('API Key incorrect, Use the api key from Config->General in your 3rd party program:'))
            return report(output, 'API Key Incorrect', callback=callback)

    # No active APIKEY, check web credentials instead
    if cfg.username() and cfg.password():
        if kwargs.get('ma_username') == cfg.username() and kwargs.get('ma_password') == cfg.password():
            pass
        else:
            if not special:
                logging.warning(Ta('Authentication missing, please enter username/password from Config->General into your 3rd party program:'))
            return report(output, 'Missing authentication', callback=callback)
    return None


#------------------------------------------------------------------------------
class NoPage(object):
    def __init__(self):
        pass

    @cherrypy.expose
    def index(self, **kwargs):
        return badParameterResponse(T('Error: No secondary interface defined.'))



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

            info['script_list'] = list_scripts(default=True)
            info['script'] = 'Default'

            info['cat'] = 'Default'
            info['cat_list'] = list_cats(True)
            info['have_rss_defined'] = bool(config.get_rss())
            info['have_watched_dir'] = bool(cfg.dirscan_dir())

            info['warning'] = ''
            if cfg.enable_unrar():
                if sabnzbd.newsunpack.RAR_PROBLEM and not cfg.ignore_wrong_unrar():
                    info['warning'] = T('Your UNRAR version is not recommended, get it from http://www.rarlab.com/rar_add.htm<br />')
                if not sabnzbd.newsunpack.RAR_COMMAND:
                    info['warning'] = T('No UNRAR program found, unpacking RAR files is not possible<br />')
            if not sabnzbd.newsunpack.PAR2_COMMAND:
                info['warning'] = T('No PAR2 program found, repairs not possible<br />')

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
    #    set_language(cfg.language())
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
        Downloader.do.pause()
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
        return api_handler(kwargs)

    @cherrypy.expose
    def api(self, **kwargs):
        """Handler for API over http, with explicit authentication parameters
        """
        if kwargs.get('mode', '') not in ('version', 'auth'):
            msg = check_apikey(kwargs)
            if msg: return msg
        return api_handler(kwargs)

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

    @cherrypy.expose
    def retry_pp(self, **kwargs):
        # Duplicate of History/retry_pp to please the SMPL skin :(
        msg = check_session(kwargs)
        if msg: return msg
        retry_job(kwargs.get('job'), kwargs.get('nzbfile'))
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
                nzo = sabnzbd.nzbqueue.get_nzo(nzo_id)
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
                filename = xml_name(nzo.final_name_pw_clean)
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
        info['script_list'] = list_scripts()
        info['cat_list'] = list_cats()
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
        name = kwargs.get('name', None)
        pp = kwargs.get('pp', None)
        script = kwargs.get('script', None)
        cat = kwargs.get('cat', None)
        priority = kwargs.get('priority', None)
        nzo = sabnzbd.nzbqueue.get_nzo(nzo_id)

        if index != None:
            NzbQueue.do.switch(nzo_id, index)
        if name != None:
            NzbQueue.do.change_name(nzo_id, special_fixer(name))
        if cat != None:
            NzbQueue.do.change_cat(nzo_id,cat)
        if script != None:
            NzbQueue.do.change_script(nzo_id,script)
        if pp != None:
            NzbQueue.do.change_opts(nzo_id,pp)
        if priority != None and nzo and nzo.priority != int(priority):
            NzbQueue.do.set_priority(nzo_id, priority)

        raise dcRaiser(cherrypy._urljoin(self.__root, '../queue/'), {})

    def bulk_operation(self, nzo_id, kwargs):
        self.__cached_selection = kwargs
        if kwargs['action_key'] == 'Delete':
            for key in kwargs:
                if kwargs[key] == 'on':
                    NzbQueue.do.remove_nzf(nzo_id, key)

        elif kwargs['action_key'] == 'Top' or kwargs['action_key'] == 'Up' or \
             kwargs['action_key'] == 'Down' or kwargs['action_key'] == 'Bottom':
            nzf_ids = []
            for key in kwargs:
                if kwargs[key] == 'on':
                    nzf_ids.append(key)
            if kwargs['action_key'] == 'Top':
                NzbQueue.do.move_top_bulk(nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Up':
                NzbQueue.do.move_up_bulk(nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Down':
                NzbQueue.do.move_down_bulk(nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Bottom':
                NzbQueue.do.move_bottom_bulk(nzo_id, nzf_ids)

        if sabnzbd.nzbqueue.get_nzo(nzo_id):
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
        self.__verbose_list = []
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        start = kwargs.get('start')
        limit = kwargs.get('limit')
        dummy2 = kwargs.get('dummy2')

        info, pnfo_list, bytespersec, self.__verbose_list, self.__dict__ = build_queue(self.__web_dir, self.__root, self.__verbose,\
                                                                                       self.__prim, self.__verbose_list, self.__dict__, start=start, limit=limit, dummy2=dummy2, trans=True)

        template = Template(file=os.path.join(self.__web_dir, 'queue.tmpl'),
                            filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()



    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid = kwargs.get('uid')
        del_files = int_conv(kwargs.get('del_files'))
        if uid:
            NzbQueue.do.remove(uid, False, keep_basic=not del_files, del_files=del_files)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def purge(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        NzbQueue.do.remove_all()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def removeNzf(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzo_id = kwargs.get('nzo_id')
        nzf_id = kwargs.get('nzf_id')
        if nzo_id and nzf_id:
            NzbQueue.do.remove_nzf(nzo_id, nzf_id)
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
        if self.__verbose_list.count(uid):
            self.__verbose_list.remove(uid)
        else:
            self.__verbose_list.append(uid)
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
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def switch(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid1 = kwargs.get('uid1')
        uid2 = kwargs.get('uid2')
        if uid1 and uid2:
            NzbQueue.do.switch(uid1, uid2)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_opts(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        nzo_id = kwargs.get('nzo_id')
        pp = kwargs.get('pp', '')
        if nzo_id and pp and pp.isdigit():
            NzbQueue.do.change_opts(nzo_id, int(pp))
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
            NzbQueue.do.change_script(nzo_id, script)
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
            NzbQueue.do.change_cat(nzo_id, cat)
            cat, pp, script, priority = cat_to_opts(cat)
            NzbQueue.do.change_script(nzo_id, script)
            NzbQueue.do.change_opts(nzo_id, pp)
            NzbQueue.do.set_priority(nzo_id, priority)

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
        Downloader.do.pause()
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
        NzbQueue.do.pause_multiple_nzo(uid.split(','))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def resume_nzo(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        uid = kwargs.get('uid', '')
        NzbQueue.do.resume_multiple_nzo(uid.split(','))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_priority(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        sabnzbd.nzbqueue.set_priority(kwargs.get('nzo_id'), kwargs.get('priority'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_avg_age(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        sabnzbd.nzbqueue.sort_queue('avg_age', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_name(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        sabnzbd.nzbqueue.sort_queue('name', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_size(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        sabnzbd.nzbqueue.sort_queue('size', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_speedlimit(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        Downloader.do.limit_speed(int_conv(kwargs.get('value')))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_pause(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        scheduler.plan_resume(int_conv(kwargs.get('value')))
        raise dcRaiser(self.__root, kwargs)

class HistoryPage(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verbose_list = []
        self.__failed_only = False
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        start = kwargs.get('start')
        limit = kwargs.get('limit')
        search = kwargs.get('search')
        failed_only = kwargs.get('failed_only')
        if failed_only is None:
            failed_only = self.__failed_only

        history, pnfo_list, bytespersec = build_header(self.__prim)

        history['isverbose'] = self.__verbose
        history['failed_only'] = failed_only

        if cfg.newzbin_username() and cfg.newzbin_password():
            history['newzbinDetails'] = True

        #history_items, total_bytes, bytes_beginning = sabnzbd.history_info()
        #history['bytes_beginning'] = "%.2f" % (bytes_beginning / GIGI)

        grand, month, week, day = BPSMeter.do.get_sums()
        history['total_size'], history['month_size'], history['week_size'], history['day_size'] = \
               to_units(grand), to_units(month), to_units(week), to_units(day)

        history['lines'], history['fetched'], history['noofslots'] = build_history(limit=limit, start=start, verbose=self.__verbose, verbose_list=self.__verbose_list, search=search, failed_only=failed_only)

        if search:
            history['search'] = escape(search)
        else:
            history['search'] = ''

        history['start'] = int_conv(start)
        history['limit'] = int_conv(limit)
        history['finish'] = history['start'] + history['limit']
        if history['finish'] > history['noofslots']:
            history['finish'] = history['noofslots']
        if not history['finish']:
            history['finish'] = history['fetched']
        history['time_format'] = time_format

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
        del_files = int_conv(kwargs.get('del_files'))
        if job:
            jobs = job.split(',')
            for job in jobs:
                del_hist_job(job, del_files=del_files)
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
        del_files = bool(int_conv(kwargs.get('del_files')))
        history_db = cherrypy.thread_data.history_db
        if del_files:
            del_job_files(history_db.get_failed_paths())
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
    def tog_failed_only(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        self.__failed_only = not self.__failed_only
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

        conf['folders'] = sabnzbd.nzbqueue.scan_jobs(all=False, action=False)

        template = Template(file=os.path.join(self.__web_dir, 'config.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def restart(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            yield msg
        else:
            yield T('Initiating restart...<br />')
            sabnzbd.halt()
            yield T('&nbsp<br />SABnzbd shutdown finished.<br />Wait for about 5 second and then click the button below.<br /><br /><strong><a href="..">Refresh</a></strong><br />')
            cherrypy.engine.restart()

    @cherrypy.expose
    def repair(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            yield msg
        else:
            sabnzbd.request_repair()
            yield T('Initiating restart...<br />')
            sabnzbd.halt()
            yield T('&nbsp<br />SABnzbd shutdown finished.<br />Wait for about 5 second and then click the button below.<br /><br /><strong><a href="..">Refresh</a></strong><br />')
            cherrypy.engine.restart()

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        orphan_delete(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        orphan_add(kwargs)
        raise dcRaiser(self.__root, kwargs)

def orphan_delete(kwargs):
    path = kwargs.get('name')
    if path:
        path = os.path.join(cfg.download_dir.get_path(), path)
        remove_all(path, recursive=True)

def orphan_add(kwargs):
    path = kwargs.get('name')
    if path:
        path = os.path.join(cfg.download_dir.get_path(), path)
        sabnzbd.nzbqueue.repair_job(path, None)


#------------------------------------------------------------------------------
LIST_DIRPAGE = ( \
    'download_dir', 'download_free', 'complete_dir', 'cache_dir', 'admin_dir',
    'nzb_backup_dir', 'dirscan_dir', 'dirscan_speed', 'script_dir',
    'email_dir', 'permissions', 'log_dir', 'password_file'
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

        for kw in LIST_DIRPAGE:
            value = kwargs.get(kw)
            if value != None:
                value = platform_encode(value)
                if kw == 'complete_dir':
                    msg = config.get_config('misc', kw).set(value, create=True)
                else:
                    msg = config.get_config('misc', kw).set(value)
                if msg:
                    return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


SWITCH_LIST = \
            ('par2_multicore', 'par_option', 'enable_unrar', 'enable_unzip', 'enable_filejoin',
             'enable_tsjoin', 'send_group', 'fail_on_crc', 'top_only',
             'enable_par_cleanup', 'auto_sort', 'check_new_rel', 'auto_disconnect',
             'safe_postproc', 'no_dupes', 'replace_spaces', 'replace_dots', 'replace_illegal', 'auto_browser',
             'ignore_samples', 'pause_on_post_processing', 'quick_check', 'nice', 'ionice',
             'ssl_type', 'pre_script', 'pause_on_pwrar', 'ampm', 'sfv_check', 'folder_rename',
             'unpack_check'
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

        conf['script_list'] = list_scripts() or ['None']
        conf['have_ampm'] = HAVE_AMPM

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
    'refresh_rate', 'cache_limit',
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
            web_dir = os.path.join(sabnzbd.DIR_INTERFACES, web_dir)
            dd = os.path.abspath(web_dir + '/templates/static/stylesheets/colorschemes')
            if (not dd) or (not os.access(dd, os.R_OK)):
                return lst
            for color in globber(dd):
                col = os.path.basename(color).replace('.css','')
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
        list = list_languages()
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
        conf['cache_limit'] = cfg.cache_limit()
        conf['cleanup_list'] = cfg.cleanup_list.get_string()
        conf['nzb_key'] = cfg.nzb_key()

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
            set_language(language)
            sabnzbd.api.cache_skin_trans()

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
            bandwidth_limit = int_conv(bandwidth_limit)
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

    @cherrypy.expose
    def generateNzbKey(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        logging.debug('NZB Key Changed')
        cfg.nzb_key.set(config.create_api_key())
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
            t, m, w, d = BPSMeter.do.amounts(svr)
            if t:
                new[svr]['amounts'] = to_units(t), to_units(m), to_units(w), to_units(d)
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
        return handle_server(kwargs, self.__root, True)


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


#------------------------------------------------------------------------------
def unique_svr_name(server):
    """ Return a unique variant on given server name
    """
    num = 0
    svr = 1
    new_name = server
    while svr:
        if num:
            new_name = '%s@%d' % (server, num)
        else:
            new_name = '%s' % server
        svr = config.get_config('servers', new_name)
        num += 1
    return new_name


def handle_server(kwargs, root=None, new_svr=False):
    """ Internal server handler """
    msg = check_session(kwargs)
    if msg: return msg

    host = kwargs.get('host', '').strip()
    if not host:
        return badParameterResponse(T('Server address required'))

    port = kwargs.get('port', '').strip()
    if not port:
        if not kwargs.get('ssl', '').strip():
            port = '119'
        else:
            port = '563'
        kwargs['port'] = port

    if kwargs.get('connections', '').strip() == '':
        kwargs['connections'] = '1'

    if kwargs.get('enable') == '1':
        msg = check_server(host, port)
        if msg:
            return msg

    # Default server name is just the host name
    server = host

    svr = None
    old_server = kwargs.get('server')
    if old_server:
        svr = config.get_config('servers', old_server)
    if svr:
        server = old_server
    else:
        svr = config.get_config('servers', server)

    if new_svr:
        server = unique_svr_name(server)

    for kw in ('fillserver', 'ssl', 'enable', 'optional'):
        if kw not in kwargs.keys():
            kwargs[kw] = None
    if svr and not new_svr:
        svr.set_dict(kwargs)
    else:
        old_server = None
        config.ConfigServer(server, kwargs)

    config.save_config()
    Downloader.do.update_server(old_server, server)
    if root:
        raise dcRaiser(root, kwargs)


def handle_server_test(kwargs, root):
    result, msg = test_nntp_server_dict(kwargs)
    return msg

#------------------------------------------------------------------------------

class ConfigRss(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__refresh_readout = None # Set to URL when new readout is needed
        self.__refresh_download = False
        self.__refresh_force = False
        self.__refresh_ignore = False

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['script_list'] = list_scripts(default=True)
        pick_script = conf['script_list'] != []

        conf['cat_list'] = list_cats(default=True)
        pick_cat = conf['cat_list'] != []

        conf['rss_rate'] = cfg.rss_rate()

        rss = {}
        feeds = config.get_rss()
        for feed in feeds:
            rss[feed] = feeds[feed].get_dict()
            filters = feeds[feed].filters()
            rss[feed]['filters'] = filters
            rss[feed]['filtercount'] = len(filters)

            rss[feed]['pick_cat'] = pick_cat
            rss[feed]['pick_script'] = pick_script
            rss[feed]['link'] = urllib.quote_plus(feed)

        active_feed = kwargs.get('feed', '')
        conf['active_feed'] = active_feed
        conf['rss'] = rss

        if active_feed:
            readout = bool(self.__refresh_readout)
            logging.debug('RSS READOUT = %s', readout)
            if not readout:
                self.__refresh_download = False
                self.__refresh_force = False
                self.__refresh_ignore = False
            msg = sabnzbd.rss.run_feed(active_feed, download=self.__refresh_download, force=self.__refresh_force, \
                                 ignoreFirst=self.__refresh_ignore, readout=readout)
            if readout:
                sabnzbd.rss.save()
            self.__refresh_readout = None
            conf['error'] = msg

            conf['downloaded'], conf['matched'], conf['unmatched'] = GetRssLog(active_feed)


        # Find a unique new Feed name
        unum = 1
        txt = Ta('Feed') #: Used as default Feed name in Config->RSS
        while txt + str(unum) in feeds:
            unum += 1
        conf['feed'] = txt + str(unum)

        template = Template(file=os.path.join(self.__web_dir, 'config_rss.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def save_rss_rate(self, **kwargs):
        """ Save changed RSS automatic readout rate """
        msg = check_session(kwargs)
        if msg: return msg
        cfg.rss_rate.set(kwargs.get('rss_rate'))
        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def upd_rss_feed(self, **kwargs):
        """ Update Feed level attributes """
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

        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def toggle_rss_feed(self, **kwargs):
        """ Toggle automatic read-out flag of Feed """
        msg = check_session(kwargs)
        if msg: return msg
        try:
            item = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            item = None
        if cfg:
            item.enable.set(not item.enable())
            config.save_config()
        if kwargs.get('table'):
            raise dcRaiser(self.__root, kwargs)
        else:
            raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add_rss_feed(self, **kwargs):
        """ Add one new RSS feed definition """
        msg = check_session(kwargs)
        if msg: return msg
        feed= Strip(kwargs.get('feed')).strip('[]')
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
            self.__refresh_readout = feed
            self.__refresh_download = False
            self.__refresh_force = False
            self.__refresh_ignore = True
            raise rssRaiser(self.__root, kwargs)
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def upd_rss_filter(self, **kwargs):
        """ Save updated filter definition """
        msg = check_session(kwargs)
        if msg: return msg
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            raise rssRaiser(self.__root, kwargs)

        pp = kwargs.get('pp')
        if IsNone(pp): pp = ''
        script = ConvertSpecials(kwargs.get('script'))
        cat = ConvertSpecials(kwargs.get('cat'))
        prio = ConvertSpecials(kwargs.get('priority'))

        cfg.filters.update(int(kwargs.get('index', 0)), (cat, pp, script, kwargs.get('filter_type'), \
                                                         platform_encode(kwargs.get('filter_text')), prio ))

        # Move filter if requested
        index = int_conv(kwargs.get('index', ''))
        new_index = kwargs.get('new_index', '')
        if new_index and int_conv(new_index) != index:
            cfg.filters.move(int(index), int_conv(new_index))

        config.save_config()
        raise rssRaiser(self.__root, kwargs)


    @cherrypy.expose
    def del_rss_feed(self, *args, **kwargs):
        """ Remove complete RSS feed """
        msg = check_session(kwargs)
        if msg: return msg
        kwargs['section'] = 'rss'
        kwargs['keyword'] = kwargs.get('feed')
        del_from_section(kwargs)
        sabnzbd.rss.clear_feed(kwargs.get('feed'))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def del_rss_filter(self, **kwargs):
        """ Remove one RSS filter """
        msg = check_session(kwargs)
        if msg: return msg
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            raise rssRaiser(self.__root, kwargs)

        cfg.filters.delete(int(kwargs.get('index', 0)))
        config.save_config()
        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def download_rss_feed(self, *args, **kwargs):
        """ Force download of all matching jobs in a feed """
        msg = check_session(kwargs)
        if msg: return msg
        if 'feed' in kwargs:
            feed = kwargs['feed']
            self.__refresh_readout = feed
            self.__refresh_download = True
            self.__refresh_force = True
            self.__refresh_ignore = False
        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def clean_rss_jobs(self, *args, **kwargs):
        """ Remove processed RSS jobs from UI """
        msg = check_session(kwargs)
        if msg: return msg
        sabnzbd.rss.clear_downloaded(kwargs['feed'])
        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def test_rss_feed(self, *args, **kwargs):
        """ Read the feed content again and show results """
        msg = check_session(kwargs)
        if msg: return msg
        if 'feed' in kwargs:
            feed = kwargs['feed']
            self.__refresh_readout = feed
            self.__refresh_download = False
            self.__refresh_force = False
            self.__refresh_ignore = True
        raise rssRaiser(self.__root, kwargs)


    @cherrypy.expose
    def download(self, **kwargs):
        """ Download NZB from provider (Download button) """
        msg = check_session(kwargs)
        if msg: return msg
        feed = kwargs.get('feed')
        url = kwargs.get('url')
        nzbname = kwargs.get('nzbname')
        att = sabnzbd.rss.lookup_url(feed, url)
        if att:
            pp = att.get('pp')
            cat = att.get('cat')
            script = att.get('script')
            prio = att.get('prio')

            if url and url.isdigit():
                sabnzbd.add_msgid(url, pp, script, cat, prio, nzbname)
            elif url:
                sabnzbd.add_url(url, pp, script, cat, prio, nzbname)
            # Need to pass the title instead
            sabnzbd.rss.flag_downloaded(feed, url)
        raise rssRaiser(self.__root, kwargs)


    @cherrypy.expose
    def rss_now(self, *args, **kwargs):
        """ Run an automatic RSS run now """
        msg = check_session(kwargs)
        if msg: return msg
        scheduler.force_rss()
        raise rssRaiser(self.__root, kwargs)



#------------------------------------------------------------------------------
_SCHED_ACTIONS = ('resume', 'pause', 'pause_all', 'shutdown', 'restart', 'speedlimit',
                  'pause_post', 'resume_post', 'scan_folder', 'rss_scan')

class ConfigScheduling(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        def get_days():
            days = {}
            days["*"] = T('Daily')
            days["1"] = T('Monday')
            days["2"] = T('Tuesday')
            days["3"] = T('Wednesday')
            days["4"] = T('Thursday')
            days["5"] = T('Friday')
            days["6"] = T('Saturday')
            days["7"] = T('Sunday')
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
                action = Ttemplate("sch-" + action)
            else:
                try:
                    act, server = action.split()
                except ValueError:
                    act = ''
                if act in ('enable_server', 'disable_server'):
                    action = Ttemplate("sch-" + act) + ' ' + server
            item = (snum, h, '%02d' % int(m), days.get(day, '**'), action)
            conf['taskinfo'].append(item)
            snum += 1


        actions_lng = {}
        for action in actions:
            actions_lng[action] = Ttemplate("sch-" + action)
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
            elif action in config.get_servers():
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
        conf['matrix_del_bookmark'] = int(cfg.matrix_del_bookmark())

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
        cfg.matrix_del_bookmark.set(kwargs.get('matrix_del_bookmark'))

        config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def saveMatrix(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg

        cfg.matrix_username.set(kwargs.get('matrix_username'))
        cfg.matrix_apikey.set(kwargs.get('matrix_apikey'))
        cfg.matrix_del_bookmark.set(kwargs.get('matrix_del_bookmark'))

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

        conf['script_list'] = list_scripts(default=True)

        categories = config.get_categories()
        conf['have_cats'] =  len(categories) > 1
        conf['defdir'] = cfg.complete_dir.get_path()


        empty = { 'name':'', 'pp':'-1', 'script':'', 'dir':'', 'newzbin':'', 'priority':DEFAULT_PRIORITY }
        slotinfo = []
        for cat in sorted(categories.keys()):
            slot = categories[cat].get_dict()
            slot['name'] = cat
            slotinfo.append(slot)
        slotinfo.insert(1, empty)
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

        name = kwargs.get('name', '*')
        if name == '*':
            newname = name
        else:
            newname = kwargs.get('newname', '').strip(' []')
        if newname:
            if name:
                config.delete('categories', name)
            name = newname.lower()
            if kwargs.get('dir'):
                kwargs['dir'] = platform_encode(kwargs['dir'])
            folder = config.ConfigCat(name, kwargs).dir
            msg = folder.set(folder(), create=True)
            if msg:
                return badParameterResponse(msg)

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
        conf['cat_list'] = list_cats(False)

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

    @cherrypy.expose
    def index(self, **kwargs):
        header, pnfo_list, bytespersec = build_header(self.__prim)

        header['logfile'] = sabnzbd.LOGFILE
        header['weblogfile'] = sabnzbd.WEBLOGFILE
        header['loglevel'] = str(cfg.log_level())

        header['lastmail'] = None # Obsolete, keep for compatibility

        header['folders'] = sabnzbd.nzbqueue.scan_jobs(all=False, action=False)
        header['configfn'] = config.get_filename()


        header['servers'] = []

        for server in Downloader.do.servers[:]:
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
                connected = T('&nbsp;Resolving address')
            busy.sort()

            header['servers'].append((server.id, '', connected, busy, server.ssl,
                                      server.active, server.errormsg, server.fillserver, server.optional))

        wlist = []
        for w in sabnzbd.GUIHANDLER.content():
            w = w.replace('WARNING', Ta('WARNING:')).replace('ERROR', Ta('ERROR:'))
            wlist.insert(0, unicoder(w))
        header['warnings'] = wlist

        template = Template(file=os.path.join(self.__web_dir, 'connection_info.tmpl'),
                            filter=FILTER, searchList=[header], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def disconnect(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        Downloader.do.disconnect()
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
        Downloader.do.unblock(kwargs.get('server'))
        # Short sleep so that UI shows new server status
        time.sleep(1.0)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        orphan_delete(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        orphan_add(kwargs)
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
           <title>SABnzbd %s - %s</title>
</head>
<body>
<h3>%s</h3>
%s
<br><br>
<FORM><INPUT TYPE="BUTTON" VALUE="%s" ONCLICK="history.go(-1)"></FORM>
</body>
</html>
''' % (sabnzbd.__version__, T('ERROR:'), T('Incorrect parameter'), unicoder(msg), T('Back'))

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
''' % (name, T('Back'), name, escape(msg))

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
''' % (xml_name(name), T('Back'), xml_name(name), escape(unicoder(msg)))


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
''' % (escape(url), T('Back'), T('Job "%s" was re-added to the queue') % escape(url))



def GetRssLog(feed):
    def make_item(job):
        url = job.get('url', '')
        title = xml_name(job.get('title', ''))
        if url.isdigit():
            title = '<a href="https://www.newzbin.com/browse/post/%s/" target="_blank">%s</a>' % (url, title)
        else:
            title = title
        if sabnzbd.rss.special_rss_site(url):
            nzbname = ""
        else:
            nzbname = xml_name(sanitize_foldername(job.get('title', '')))
        return url, \
               title, \
               '*' * int(job.get('status', '').endswith('*')), \
               job.get('rule', 0), \
               nzbname

    jobs = sabnzbd.rss.show_result(feed)
    names = jobs.keys()
    # Sort in the order the jobs came from the feed
    names.sort(lambda x, y: jobs[x].get('order', 0) - jobs[y].get('order', 0))

    done = [xml_name(jobs[job]['title']) for job in names if jobs[job]['status'] == 'D']
    good = [make_item(jobs[job]) for job in names if jobs[job]['status'][0] == 'G']
    bad  = [make_item(jobs[job]) for job in names if jobs[job]['status'][0] == 'B']

    return done, good, bad

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
            goodStr.append('')

    badStr = []
    for x in names:
        job = jobs[x]
        if job['status'][0] == 'B':
            badStr.append('')

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
''' % (escape(feed), T('Back'), escape(feed), T('Jobs marked with a \'*\' will not be automatically downloaded.'), T('Matched'), \
       ''.join(goodStr), T('Not matched'), ''.join(badStr), T('Downloaded'), ''.join(doneStr))
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
''' % (escape(feed), T('Back'), escape(feed), T('Downloaded so far'), ''.join(doneStr))



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
        self.__lastmail = None

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock():
            return Protected()

        conf, pnfo_list, bytespersec = build_header(self.__prim)

        conf['my_home'] = sabnzbd.DIR_HOME
        conf['my_lcldata'] = sabnzbd.DIR_LCLDATA
        conf['lastmail'] = self.__lastmail


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
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)))

        config.save_config()
        self.__lastmail = None
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def testmail(self, **kwargs):
        msg = check_session(kwargs)
        if msg: return msg
        self.__lastmail = None
        logging.info("Sending testmail")
        pack = {}
        pack['download'] = ['action 1', 'action 2']
        pack['unpack'] = ['action 1', 'action 2']

        self.__lastmail = emailer.endjob('I had a d\xe8ja vu', 123, 'unknown', True,
                                         os.path.normpath(os.path.join(cfg.complete_dir.get_path(), '/unknown/I had a d\xe8ja vu')),
                                         str(123*MEBI), pack, 'my_script', 'Line 1\nLine 2\nLine 3\nd\xe8ja vu\n', 0)
        raise dcRaiser(self.__root, kwargs)


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
