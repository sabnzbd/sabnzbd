#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
import urllib
import json
import re
import hashlib
from random import randint
from xml.sax.saxutils import escape

from sabnzbd.utils.rsslib import RSS, Item
import sabnzbd
import sabnzbd.rss
import sabnzbd.scheduler as scheduler

from Cheetah.Template import Template
from sabnzbd.misc import real_path, to_units, from_units, \
    time_format, HAVE_AMPM, long_path, \
    cat_to_opts, int_conv, globber, globber_full, remove_all, get_base_url
from sabnzbd.panic import panic_old_queue
from sabnzbd.newswrapper import GetServerParms
from sabnzbd.rating import Rating
from sabnzbd.bpsmeter import BPSMeter
from sabnzbd.encoding import TRANS, xml_name, LatinFilter, unicoder, special_fixer, \
    platform_encode
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.notifier as notifier
import sabnzbd.newsunpack
from sabnzbd.downloader import Downloader
from sabnzbd.nzbqueue import NzbQueue
import sabnzbd.wizard
from sabnzbd.utils.servertests import test_nntp_server_dict
from sabnzbd.utils.sslinfo import ssl_protocols

from sabnzbd.constants import \
    REC_RAR_VERSION, NORMAL_PRIORITY, PNFO, \
    MEBI, DEF_SKIN_COLORS, DEF_STDINTF, DEF_STDCONFIG, DEF_MAIN_TMPL, \
    DEFAULT_PRIORITY

from sabnzbd.lang import list_languages, set_language

from sabnzbd.api import list_scripts, list_cats, del_from_section, \
    api_handler, build_queue, remove_callable, rss_qstatus, build_status, \
    retry_job, retry_all_jobs, build_queue_header, build_header, build_history, del_job_files, \
    format_bytes, calc_age, std_time, report, del_hist_job, Ttemplate, \
    _api_test_email, _api_test_notif

##############################################################################
# Global constants
##############################################################################
DIRECTIVES = {
    'directiveStartToken': '<!--#',
    'directiveEndToken': '#-->',
    'prioritizeSearchListOverSelf': True
}
FILTER = LatinFilter


def check_server(host, port, ajax):
    """ Check if server address resolves properly """

    if host.lower() == 'localhost' and sabnzbd.AMBI_LOCALHOST:
        return badParameterResponse(T('Warning: LOCALHOST is ambiguous, use numerical IP-address.'), ajax)

    if GetServerParms(host, int_conv(port)):
        return ""
    else:
        return badParameterResponse(T('Server address "%s:%s" is not valid.') % (host, port), ajax)


def check_access(access_type=4):
    """ Check if external address is allowed given `access_type`
        `access_type`: 1=nzb, 2=api, 3=full_api, 4=webui, 5=webui with login for external
    """
    referrer = cherrypy.request.remote.ip

    # CherryPy will report ::ffff:192.168.0.10 on dual-stack situation
    # It will always contain that ::ffff: prefix
    range_ok = (not cfg.local_ranges()) or bool([1 for r in cfg.local_ranges() if (referrer.startswith(r) or referrer.replace('::ffff:', '').startswith(r))])
    allowed = referrer in ('127.0.0.1', '::ffff:127.0.0.1', '::1') or range_ok or access_type <= cfg.inet_exposure()
    if not allowed:
        logging.debug('Refused connection to %s', referrer)
    return allowed


def ConvertSpecials(p):
    """ Convert None to 'None' and 'Default' to '' """
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


def IsNone(value):
    """ Return True if either None, 'None' or '' """
    return value is None or value == "" or value.lower() == 'none'


def Strip(txt):
    """ Return stripped string, can handle None """
    try:
        return txt.strip()
    except:
        return None


##############################################################################
# Web login support
##############################################################################
def get_users():
    users = {}
    users[cfg.username()] = cfg.password()
    return users

def encrypt_pwd(pwd):
    return pwd

# Create a more unique ID for each instance
COOKIE_SECRET = str(randint(1000,100000)*os.getpid())

def set_login_cookie(remove=False, remember_me=False):
    """ We try to set a cookie as unique as possible
        to the current user. Based on it's IP and the
        current process ID of the SAB instance and a random
        number, so cookies cannot be re-used
    """
    salt = randint(1,1000)
    cherrypy.response.cookie['login_cookie'] = hashlib.sha1(str(salt) + cherrypy.request.remote.ip + COOKIE_SECRET).hexdigest()
    cherrypy.response.cookie['login_cookie']['path'] = '/'
    cherrypy.response.cookie['login_salt'] = salt
    cherrypy.response.cookie['login_salt']['path'] = '/'

    # If we want to be remembered
    if remember_me:
        cherrypy.response.cookie['login_cookie']['max-age'] = 3600*24*14
        cherrypy.response.cookie['login_salt']['max-age'] = 3600*24*14

    # To remove
    if remove:
        cherrypy.response.cookie['login_cookie']['expires'] = 0
        cherrypy.response.cookie['login_salt']['expires'] = 0
    else:
        # Notify about new login
        notifier.send_notification(T('User logged in'), T('User logged in to the web interface'), 'new_login')

def check_login_cookie():
    # Do we have everything?
    if 'login_cookie' not in cherrypy.request.cookie or 'login_salt' not in cherrypy.request.cookie:
        return False

    return cherrypy.request.cookie['login_cookie'].value == hashlib.sha1(str(cherrypy.request.cookie['login_salt'].value) + cherrypy.request.remote.ip + COOKIE_SECRET).hexdigest()

def check_login():
    # Not when no authentication required or basic-auth is on
    if not cfg.html_login() or not cfg.username() or not cfg.password():
        return True

    # If we show login for external IP, by using access_type=6 we can check if IP match
    if cfg.inet_exposure() == 5 and check_access(access_type=6):
        return True

    # Check the cookie
    return check_login_cookie()

def set_auth(conf):
    """ Set the authentication for CherryPy """
    if cfg.username() and cfg.password() and not cfg.html_login():
        conf.update({'tools.basic_auth.on': True, 'tools.basic_auth.realm': cfg.login_realm(),
                     'tools.basic_auth.users': get_users, 'tools.basic_auth.encrypt': encrypt_pwd})
        conf.update({'/api': {'tools.basic_auth.on': False},
                     '/m/api': {'tools.basic_auth.on': False},
                     '/sabnzbd/api': {'tools.basic_auth.on': False},
                     '/sabnzbd/m/api': {'tools.basic_auth.on': False},
                     })
    else:
        conf.update({'tools.basic_auth.on': False})


def check_session(kwargs):
    """ Check session key """
    if not check_access():
        return u'Access denied'
    key = kwargs.get('session')
    if not key:
        key = kwargs.get('apikey')
    msg = None
    if not key:
        logging.warning(T('Missing Session key'))
        msg = T('Error: Session Key Required')
    elif key != cfg.api_key():
        logging.warning(T('Error: Session Key Incorrect'))
        msg = T('Error: Session Key Incorrect')
    return msg


def check_apikey(kwargs, nokey=False):
    """ Check api key or nzbkey
        Return None when OK, otherwise an error message
    """
    def log_warning(txt):
        txt = '%s %s>%s' % (txt, cherrypy.request.remote.ip, cherrypy.request.headers.get('User-Agent', '??'))
        logging.warning('%s', txt)

    output = kwargs.get('output')
    mode = kwargs.get('mode', '')
    name = kwargs.get('name', '')
    callback = kwargs.get('callback')

    # Don't give a visible warning: these commands are used by some
    # external utilities to detect if username/password is required
    # The cfg item can suppress all visible warnings
    special = mode in ('get_scripts', 'qstatus') or not cfg.api_warnings.get()

    # Lookup required access level
    req_access = sabnzbd.api.api_level(mode, name)

    if req_access == 1 and check_access(1):
        # NZB-only actions
        pass
    elif not check_access(req_access):
        return report(output, 'Access denied')

    # First check APIKEY, if OK that's sufficient
    if not (cfg.disable_key() or nokey):
        key = kwargs.get('apikey')
        if not key:
            key = kwargs.get('session')
        if not key:
            if not special:
                log_warning(T('API Key missing, please enter the api key from Config->General into your 3rd party program:'))
            return report(output, 'API Key Required', callback=callback)
        elif req_access == 1 and key == cfg.nzb_key():
            return None
        elif key == cfg.api_key():
            return None
        else:
            log_warning(T('API Key incorrect, Use the api key from Config->General in your 3rd party program:'))
            return report(output, 'API Key Incorrect', callback=callback)

    # No active APIKEY, check web credentials instead
    if cfg.username() and cfg.password():
        if check_login() or (kwargs.get('ma_username') == cfg.username() and kwargs.get('ma_password') == cfg.password()):
            pass
        else:
            if not special:
                log_warning(T('Authentication missing, please enter username/password from Config->General into your 3rd party program:'))
            return report(output, 'Missing authentication', callback=callback)
    return None


class NoPage(object):

    def __init__(self):
        pass

    @cherrypy.expose
    def index(self, **kwargs):
        return badParameterResponse(T('Error: No secondary interface defined.'))


##############################################################################
class MainPage(object):

    def __init__(self, web_dir, root, web_dir2=None, root2=None, web_dirc=None, prim=True, first=0):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

        if first >= 1 and web_dir2:
            # Setup addresses for secondary skin
            self.m = MainPage(web_dir2, root2, web_dirc=web_dirc, prim=False)
        if first == 2:
            # Setup addresses with /sabnzbd prefix for primary and secondary skin
            self.sabnzbd = MainPage(web_dir, '/sabnzbd/', web_dir2, '/sabnzbd/m/', web_dirc=web_dirc, prim=True, first=1)

        self.login = LoginPage(web_dirc, root + 'login/', prim)
        self.queue = QueuePage(web_dir, root + 'queue/', prim)
        self.history = HistoryPage(web_dir, root + 'history/', prim)
        self.status = Status(web_dir, root + 'status/', prim)
        self.config = ConfigPage(web_dirc, root + 'config/', prim)
        self.nzb = NzoPage(web_dir, root + 'nzb/', prim)
        self.wizard = sabnzbd.wizard.Wizard(web_dir, root + 'wizard/', prim)

    @cherrypy.expose
    def index(self, **kwargs):
        if not check_access():
            return Protected()

        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        if sabnzbd.OLD_QUEUE and not cfg.warned_old_queue():
            cfg.warned_old_queue.set(True)
            config.save_config()
            return panic_old_queue()

        if not cfg.notified_new_skin() and cfg.web_dir() != 'Glitter':
            logging.warning(T('Try our new skin Glitter! Fresh new design that is optimized for desktop and mobile devices. Go to Config -> General to change your skin.'))
        if not cfg.notified_new_skin():
            cfg.notified_new_skin.set(True)
            config.save_config()

        if kwargs.get('skip_wizard') or config.get_servers():
            info = build_header(self.__prim, self.__web_dir)

            info['script_list'] = list_scripts(default=True)
            info['script'] = 'Default'

            info['cat'] = 'Default'
            info['cat_list'] = list_cats(True)
            info['have_rss_defined'] = bool(config.get_rss())
            info['have_watched_dir'] = bool(cfg.dirscan_dir())

            # Have logout only with HTML and if inet=5, only when we are external
            info['have_logout'] = cfg.username() and cfg.password() and (cfg.html_login() and (cfg.inet_exposure() < 5 or (cfg.inet_exposure() == 5 and not check_access(access_type=6))))

            bytespersec_list = BPSMeter.do.get_bps_list()
            info['bytespersec_list'] = ','.join(bytespersec_list)

            info['warning'] = ''
            if cfg.enable_unrar():
                version = sabnzbd.newsunpack.RAR_VERSION
                if version and version < REC_RAR_VERSION and not cfg.ignore_wrong_unrar():
                    have_str = '%.2f' % (float(version) / 100)
                    want_str = '%.2f' % (float(REC_RAR_VERSION) / 100)
                    info['warning'] = T('Your UNRAR version is %s, we recommend version %s or higher.<br />') % \
                                         (have_str, want_str)
                if not sabnzbd.newsunpack.RAR_COMMAND:
                    info['warning'] = T('No UNRAR program found, unpacking RAR files is not possible<br />')
            if not sabnzbd.newsunpack.PAR2_COMMAND:
                info['warning'] = T('No PAR2 program found, repairs not possible<br />')

            # For Glitter we pre-load the JSON output
            if 'Glitter' in self.__web_dir:
                # Queue
                queue = build_queue(limit=cfg.queue_limit(), output='json')[0]
                queue['categories'] = info.pop('cat_list')
                queue['scripts'] = info.pop('script_list')

                # History
                history = {};
                grand, month, week, day = BPSMeter.do.get_sums()
                history['total_size'], history['month_size'], history['week_size'], history['day_size'] = \
                       to_units(grand), to_units(month), to_units(week), to_units(day)
                history['slots'], fetched_items, history['noofslots'] = build_history(limit=cfg.history_limit(), output='json')

                # Make sure the JSON works, otherwise leave empty
                try:
                    info['preload_queue'] = json.dumps({'queue': remove_callable(queue)});
                    info['preload_history'] = json.dumps({'history': history});
                except UnicodeDecodeError:
                    # We use the javascript recognized 'false'
                    info['preload_queue'] = 'false'
                    info['preload_history'] = 'false'

            template = Template(file=os.path.join(self.__web_dir, 'main.tmpl'),
                                filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
            return template.respond()
        else:
            # Redirect to the setup wizard
            raise cherrypy.HTTPRedirect('/sabnzbd/wizard/')

    #@cherrypy.expose
    # def reset_lang(self, **kwargs):
    #    msg = check_session(kwargs)
    #    if msg: return msg
    #    set_language(cfg.language())
    #    raise dcRaiser(self.__root, kwargs)

    def add_handler(self, kwargs):
        if not check_access():
            return Protected()
        url = kwargs.get('url', '')
        pp = kwargs.get('pp')
        script = kwargs.get('script')
        cat = kwargs.get('cat')
        priority = kwargs.get('priority')
        redirect = kwargs.get('redirect')
        nzbname = kwargs.get('nzbname')

        url = Strip(url)
        if url:
            sabnzbd.add_url(url, pp, script, cat, priority, nzbname)
        if not redirect:
            redirect = self.__root
        raise cherrypy.HTTPRedirect(redirect)

    @cherrypy.expose
    def addURL(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        raise self.add_handler(kwargs)

    @cherrypy.expose
    def addFile(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        nzbfile = kwargs.get('nzbfile')
        if nzbfile is not None and nzbfile.filename:
            if nzbfile.value or nzbfile.file:
                sabnzbd.add_nzbfile(nzbfile, kwargs.get('pp'), kwargs.get('script'),
                                    kwargs.get('cat'), kwargs.get('priority', NORMAL_PRIORITY))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def shutdown(self, **kwargs):
        msg = check_session(kwargs)

        # Check for PID 
        pid_in = kwargs.get('pid') 
        if pid_in and int(pid_in) != os.getpid(): 
            msg = "Incorrect PID for this instance, remove PID from URL to initiate shutdown." 

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
        if msg:
            return msg

        scheduler.plan_resume(0)
        Downloader.do.pause()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def resume(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        scheduler.plan_resume(0)
        sabnzbd.unpause_all()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def rss(self, **kwargs):
        msg = check_apikey(kwargs, nokey=True)
        if msg:
            return msg

        if kwargs.get('mode') == 'history':
            return rss_history(cherrypy.url(), limit=kwargs.get('limit', 50), search=kwargs.get('search'))
        elif kwargs.get('mode') == 'queue':
            return rss_qstatus()
        elif kwargs.get('mode') == 'warnings':
            return rss_warnings()

    @cherrypy.expose
    def tapi(self, **kwargs):
        """ Handler for API over http, for template use """
        msg = check_apikey(kwargs)
        if msg:
            return msg
        return api_handler(kwargs)

    @cherrypy.expose
    def api(self, **kwargs):
        """ Handler for API over http, with explicit authentication parameters """
        if not kwargs.get('tickleme') or not cfg.web_watchdog():
            if cfg.api_logging():
                logging.debug('API-call from %s [%s] %s', cherrypy.request.remote.ip,
                              cherrypy.request.headers.get('User-Agent', '??'), kwargs)
        mode = kwargs.get('mode', '')
        if isinstance(mode, list):
            mode = mode[0]
            kwargs['mode'] = mode
        name = kwargs.get('name', '')
        if isinstance(name, list):
            name = name[0]
            kwargs['name'] = name
        if mode not in ('version', 'auth'):
            msg = check_apikey(kwargs)
            if msg:
                return msg
        return api_handler(kwargs)

    @cherrypy.expose
    def scriptlog(self, **kwargs):
        """ Duplicate of scriptlog of History, needed for some skins """
        # No session key check, due to fixed URLs
        if not check_access():
            return Protected()

        name = kwargs.get('name')
        if name:
            history_db = sabnzbd.connect_db()
            return ShowString(history_db.get_name(name), history_db.get_script_log(name))
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def retry(self, **kwargs):
        """ Duplicate of retry of History, needed for some skins """
        msg = check_session(kwargs)
        if msg:
            return msg
        job = kwargs.get('job', '')
        url = kwargs.get('url', '').strip()
        pp = kwargs.get('pp')
        cat = kwargs.get('cat')
        script = kwargs.get('script')
        if url:
            sabnzbd.add_url(url, pp, script, cat, nzbname=kwargs.get('nzbname'))
        del_hist_job(job, del_files=True)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def retry_pp(self, **kwargs):
        # Duplicate of History/retry_pp to please the SMPL skin :(
        msg = check_session(kwargs)
        if msg:
            return msg
        retry_job(kwargs.get('job'), kwargs.get('nzbfile'), kwargs.get('password'))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def robots_txt(self):
        """ Keep web crawlers out """
        cherrypy.response.headers['Content-Type'] = 'text/plain'
        return 'User-agent: *\nDisallow: /\n'

##############################################################################
class LoginPage(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        # Base output var
        info = build_header(self.__prim, self.__web_dir)
        info['error'] = ''

        # Logout?
        if kwargs.get('logout'):
            set_login_cookie(remove=True)
            raise dcRaiser('.', kwargs)

        # Check if there's even a username/password set
        #if check_login():
        #    raise dcRaiser('../', kwargs)

        # Check login info
        if kwargs.get('username') == cfg.username() and kwargs.get('password') == cfg.password():
            # Save login cookie
            set_login_cookie(remember_me=kwargs.get('remember_me', False))
            # Redirect
            raise dcRaiser('../', kwargs)
        elif kwargs.get('username') or kwargs.get('password'):
            info['error'] = T('Authentication failed, check username/password.')

        # Show login
        template = Template(file=os.path.join(self.__web_dir, 'login', 'main.tmpl'),
                                filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()


##############################################################################
class NzoPage(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__cached_selection = {}  # None

    @cherrypy.expose
    def default(self, *args, **kwargs):
        # Allowed URL's
        # /nzb/SABnzbd_nzo_xxxxx/
        # /nzb/SABnzbd_nzo_xxxxx/details
        # /nzb/SABnzbd_nzo_xxxxx/files
        # /nzb/SABnzbd_nzo_xxxxx/bulk_operation
        # /nzb/SABnzbd_nzo_xxxxx/save
        if not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        nzo_id = None
        for a in args:
            if a.startswith('SABnzbd_nzo'):
                nzo_id = a
                break

        nzo = NzbQueue.do.get_nzo(nzo_id)
        if nzo_id and nzo:
            info = build_header(self.__prim, self.__web_dir)
            pnfo_list = [nzo.gather_info(full=True)]

            # /SABnzbd_nzo_xxxxx/bulk_operation
            if 'bulk_operation' in args:
                return self.bulk_operation(nzo_id, kwargs)

            # /SABnzbd_nzo_xxxxx/details
            elif 'details' in args:
                info = self.nzo_details(info, pnfo_list, nzo_id)

            # /SABnzbd_nzo_xxxxx/files
            elif 'files' in args:
                info = self.nzo_files(info, pnfo_list, nzo_id)

            # /SABnzbd_nzo_xxxxx/save
            elif 'save' in args:
                self.save_details(nzo_id, args, kwargs)
                return  # never reached

            # /SABnzbd_nzo_xxxxx/
            else:
                info = self.nzo_details(info, pnfo_list, nzo_id)
                info = self.nzo_files(info, pnfo_list, nzo_id)

            template = Template(file=os.path.join(self.__web_dir, 'nzo.tmpl'),
                                filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
            return template.respond()
        else:
            # Job no longer exists, go to main page
            raise dcRaiser(cherrypy.lib.httputil.urljoin(self.__root, '../queue/'), {})

    def nzo_details(self, info, pnfo_list, nzo_id):
        slot = {}
        n = 0
        for pnfo in pnfo_list:
            if pnfo.nzo_id == nzo_id:
                nzo = sabnzbd.nzbqueue.get_nzo(nzo_id)
                repair = pnfo.repair
                unpack = pnfo.unpack
                delete = pnfo.delete
                unpackopts = sabnzbd.opts_to_pp(repair, unpack, delete)
                script = pnfo.script
                if script is None:
                    script = 'None'
                cat = pnfo.category
                if not cat:
                    cat = 'None'
                filename_pw = xml_name(nzo.final_name_pw_clean)
                filename = xml_name(nzo.final_name)
                if nzo.password:
                    password = xml_name(nzo.password).replace('"', '&quot;')
                else:
                    password = ''
                priority = pnfo.priority

                slot['nzo_id'] = str(nzo_id)
                slot['cat'] = cat
                slot['filename'] = filename_pw
                slot['filename_clean'] = filename
                slot['password'] = password or ''
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
        nzo = NzbQueue.do.get_nzo(nzo_id)
        if nzo:
            pnfo = nzo.gather_info(full=True)
            info['nzo_id'] = pnfo.nzo_id
            info['filename'] = xml_name(pnfo.filename)

            for nzf in pnfo.active_files:
                checked = False
                if nzf.nzf_id in self.__cached_selection and \
                   self.__cached_selection[nzf.nzf_id] == 'on':
                    checked = True
                active.append({'filename': xml_name(nzf.filename if nzf.filename else nzf.subject),
                               'mbleft': "%.2f" % (nzf.bytes_left / MEBI),
                               'mb': "%.2f" % (nzf.bytes / MEBI),
                               'size': format_bytes(nzf.bytes),
                               'sizeleft': format_bytes(nzf.bytes_left),
                               'nzf_id': nzf.nzf_id,
                               'age': calc_age(nzf.date),
                               'checked': checked})

        info['active_files'] = active
        return info

    def save_details(self, nzo_id, args, kwargs):
        index = kwargs.get('index', None)
        name = kwargs.get('name', None)
        password = kwargs.get('password', None)
        if password == "":
            password = None
        pp = kwargs.get('pp', None)
        script = kwargs.get('script', None)
        cat = kwargs.get('cat', None)
        priority = kwargs.get('priority', None)
        nzo = sabnzbd.nzbqueue.get_nzo(nzo_id)

        if index is not None:
            NzbQueue.do.switch(nzo_id, index)
        if name is not None:
            NzbQueue.do.change_name(nzo_id, special_fixer(name), password)

        if cat is not None and nzo.cat is not cat and not (nzo.cat == '*' and cat == 'Default'):
            NzbQueue.do.change_cat(nzo_id, cat, priority)
            # Category changed, so make sure "Default" attributes aren't set again
            if script == 'Default':
                script = None
            if priority == 'Default':
                priority = None
            if pp == 'Default':
                pp = None

        if script is not None and nzo.script != script:
            NzbQueue.do.change_script(nzo_id, script)
        if pp is not None and nzo.pp != pp:
            NzbQueue.do.change_opts(nzo_id, pp)
        if priority is not None and nzo.priority != int(priority):
            NzbQueue.do.set_priority(nzo_id, priority)

        raise dcRaiser(cherrypy.lib.httputil.urljoin(self.__root, '../queue/'), {})

    def bulk_operation(self, nzo_id, kwargs):
        self.__cached_selection = kwargs
        if kwargs['action_key'] == 'Delete':
            for key in kwargs:
                if kwargs[key] == 'on':
                    NzbQueue.do.remove_nzf(nzo_id, key)

        elif kwargs['action_key'] in ('Top', 'Up', 'Down', 'Bottom'):
            nzf_ids = []
            for key in kwargs:
                if kwargs[key] == 'on':
                    nzf_ids.append(key)
            size = int_conv(kwargs.get('action_size', 1))
            if kwargs['action_key'] == 'Top':
                NzbQueue.do.move_top_bulk(nzo_id, nzf_ids)
            elif kwargs['action_key'] == 'Up':
                NzbQueue.do.move_up_bulk(nzo_id, nzf_ids, size)
            elif kwargs['action_key'] == 'Down':
                NzbQueue.do.move_down_bulk(nzo_id, nzf_ids, size)
            elif kwargs['action_key'] == 'Bottom':
                NzbQueue.do.move_bottom_bulk(nzo_id, nzf_ids)

        if sabnzbd.nzbqueue.get_nzo(nzo_id):
            url = cherrypy.lib.httputil.urljoin(self.__root, nzo_id)
        else:
            url = cherrypy.lib.httputil.urljoin(self.__root, '../queue')
        if url and not url.endswith('/'):
            url += '/'
        raise dcRaiser(url, kwargs)


##############################################################################
class QueuePage(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        start = int_conv(kwargs.get('start'))
        limit = int_conv(kwargs.get('limit'))
        search = kwargs.get('search')
        info, _pnfo_list, _bytespersec = build_queue(self.__web_dir, self.__root, self.__prim, self.__web_dir,
                                                     start=start, limit=limit, trans=True, search=search)

        template = Template(file=os.path.join(self.__web_dir, 'queue.tmpl'),
                            filter=FILTER, searchList=[info], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        uid = kwargs.get('uid')
        del_files = int_conv(kwargs.get('del_files'))
        if uid:
            NzbQueue.do.remove(uid, False, keep_basic=not del_files, del_files=del_files)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def purge(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        NzbQueue.do.remove_all(kwargs.get('search'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def removeNzf(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        nzo_id = kwargs.get('nzo_id')
        nzf_id = kwargs.get('nzf_id')
        if nzo_id and nzf_id:
            NzbQueue.do.remove_nzf(nzo_id, nzf_id)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_queue_complete_action(self, **kwargs):
        """ Action or script to be performed once the queue has been completed
            Scripts are prefixed with 'script_'
        """
        msg = check_session(kwargs)
        if msg:
            return msg
        action = kwargs.get('action')
        sabnzbd.change_queue_complete_action(action)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def switch(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        uid1 = kwargs.get('uid1')
        uid2 = kwargs.get('uid2')
        if uid1 and uid2:
            NzbQueue.do.switch(uid1, uid2)
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_opts(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        nzo_id = kwargs.get('nzo_id')
        pp = kwargs.get('pp', '')
        if nzo_id and pp and pp.isdigit():
            NzbQueue.do.change_opts(nzo_id, int(pp))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_script(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
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
        if msg:
            return msg
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
        if msg:
            return msg
        scheduler.plan_resume(0)
        Downloader.do.pause()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def resume(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        scheduler.plan_resume(0)
        sabnzbd.unpause_all()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def pause_nzo(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        uid = kwargs.get('uid', '')
        NzbQueue.do.pause_multiple_nzo(uid.split(','))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def resume_nzo(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        uid = kwargs.get('uid', '')
        NzbQueue.do.resume_multiple_nzo(uid.split(','))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_priority(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        sabnzbd.nzbqueue.set_priority(kwargs.get('nzo_id'), kwargs.get('priority'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_avg_age(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        sabnzbd.nzbqueue.sort_queue('avg_age', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_name(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        sabnzbd.nzbqueue.sort_queue('name', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def sort_by_size(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        sabnzbd.nzbqueue.sort_queue('size', kwargs.get('dir'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_speedlimit(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        Downloader.do.limit_speed(int_conv(kwargs.get('value')))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def set_pause(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        scheduler.plan_resume(int_conv(kwargs.get('value')))
        raise dcRaiser(self.__root, kwargs)


##############################################################################
class HistoryPage(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__verbose = False
        self.__verbose_list = []
        self.__failed_only = False
        self.__prim = prim
        self.__edit_rating = None

    @cherrypy.expose
    def index(self, **kwargs):
        if not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        start = int_conv(kwargs.get('start'))
        limit = int_conv(kwargs.get('limit'))
        search = kwargs.get('search')
        failed_only = kwargs.get('failed_only')
        if failed_only is None:
            failed_only = self.__failed_only

        history = build_header(self.__prim, self.__web_dir)

        history['isverbose'] = self.__verbose
        history['failed_only'] = failed_only

        history['rating_enable'] = bool(cfg.rating_enable())

        postfix = T('B')  # : Abbreviation for bytes, as in GB
        grand, month, week, day = BPSMeter.do.get_sums()
        history['total_size'], history['month_size'], history['week_size'], history['day_size'] = \
               to_units(grand, postfix=postfix), to_units(month, postfix=postfix), \
               to_units(week, postfix=postfix), to_units(day, postfix=postfix)

        history['lines'], history['fetched'], history['noofslots'] = build_history(limit=limit, start=start, verbose=self.__verbose, verbose_list=self.__verbose_list, search=search, failed_only=failed_only)

        for line in history['lines']:
            if self.__edit_rating is not None and line.get('nzo_id') == self.__edit_rating:
                line['edit_rating'] = True
            else:
                line['edit_rating'] = ''

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
        if msg:
            return msg
        history_db = sabnzbd.connect_db()
        history_db.remove_history()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
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
        if msg:
            return msg
        retry_job(kwargs.get('job'), kwargs.get('nzbfile'), kwargs.get('password'))
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def retry_all(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        retry_all_jobs()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def purge_failed(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        del_files = bool(int_conv(kwargs.get('del_files')))
        history_db = sabnzbd.connect_db()
        if del_files:
            del_job_files(history_db.get_failed_paths())
        history_db.remove_failed()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def reset(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        # sabnzbd.reset_byte_counter()
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def tog_verbose(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
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
        if msg:
            return msg
        self.__failed_only = not self.__failed_only
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def scriptlog(self, **kwargs):
        """ Duplicate of scriptlog of History, needed for some skins """
        # No session key check, due to fixed URLs
        if not check_access():
            return Protected()
        name = kwargs.get('name')
        if name:
            history_db = sabnzbd.connect_db()
            return ShowString(history_db.get_name(name), history_db.get_script_log(name))
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def retry(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        job = kwargs.get('job', '')
        url = kwargs.get('url', '').strip()
        pp = kwargs.get('pp')
        cat = kwargs.get('cat')
        script = kwargs.get('script')
        if url:
            sabnzbd.add_url(url, pp, script, cat, nzbname=kwargs.get('nzbname'))
        del_hist_job(job, del_files=True)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def show_edit_rating(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        self.__edit_rating = kwargs.get('job')
        raise queueRaiser(self.__root, kwargs)

    @cherrypy.expose
    def action_edit_rating(self, **kwargs):
        flag_map = {'spam': Rating.FLAG_SPAM, 'encrypted': Rating.FLAG_ENCRYPTED, 'expired': Rating.FLAG_EXPIRED}
        msg = check_session(kwargs)
        if msg:
            return msg
        try:
            if kwargs.get('send'):
                video = kwargs.get('video') if kwargs.get('video') != "-" else None
                audio = kwargs.get('audio') if kwargs.get('audio') != "-" else None
                flag = flag_map.get(kwargs.get('rating_flag'))
                detail = kwargs.get('expired_host') if kwargs.get('expired_host') != '<Host>' else None
                if cfg.rating_enable():
                    Rating.do.update_user_rating(kwargs.get('job'), video, audio, flag, detail)
        except:
            pass
        self.__edit_rating = None
        raise queueRaiser(self.__root, kwargs)


##############################################################################
class ConfigPage(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.folders = ConfigFolders(web_dir, root + 'folders/', prim)
        self.notify = ConfigNotify(web_dir, root + 'notify/', prim)
        self.general = ConfigGeneral(web_dir, root + 'general/', prim)
        self.rss = ConfigRss(web_dir, root + 'rss/', prim)
        self.scheduling = ConfigScheduling(web_dir, root + 'scheduling/', prim)
        self.server = ConfigServer(web_dir, root + 'server/', prim)
        self.switches = ConfigSwitches(web_dir, root + 'switches/', prim)
        self.categories = ConfigCats(web_dir, root + 'categories/', prim)
        self.sorting = ConfigSorting(web_dir, root + 'sorting/', prim)
        self.special = ConfigSpecial(web_dir, root + 'special/', prim)

    @cherrypy.expose
    def index(self, **kwargs):
        if not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)
        conf = build_header(self.__prim, self.__web_dir)

        conf['configfn'] = config.get_filename()
        conf['cmdline'] = sabnzbd.CMDLINE
        conf['build'] = sabnzbd.version.__baseline__[:7]

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
        if msg:
            return msg
        orphan_delete(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        orphan_add(kwargs)
        raise dcRaiser(self.__root, kwargs)


def orphan_delete(kwargs):
    path = kwargs.get('name')
    if path:
        path = platform_encode(path)
        path = os.path.join(long_path(cfg.download_dir.get_path()), path)
        remove_all(path, recursive=True)

def orphan_delete_all():
    paths = sabnzbd.nzbqueue.scan_jobs(all=False, action=False);
    for path in paths:
        kwargs = {'name': path}
        orphan_delete(kwargs)

def orphan_add(kwargs):
    path = kwargs.get('name')
    if path:
        path = platform_encode(path)
        path = os.path.join(long_path(cfg.download_dir.get_path()), path)
        sabnzbd.nzbqueue.repair_job(path, None, None)

def orphan_add_all():
    paths = sabnzbd.nzbqueue.scan_jobs(all=False, action=False);
    for path in paths:
        kwargs = {'name': path}
        orphan_add(kwargs)


##############################################################################
LIST_DIRPAGE = (
    'download_dir', 'download_free', 'complete_dir', 'admin_dir',
    'nzb_backup_dir', 'dirscan_dir', 'dirscan_speed', 'script_dir',
    'email_dir', 'permissions', 'log_dir', 'password_file'
)


class ConfigFolders(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        for kw in LIST_DIRPAGE:
            conf[kw] = config.get_config('misc', kw)()

        # Temporary fix, problem with build_header
        conf['restart_req'] = sabnzbd.RESTART_REQ

        template = Template(file=os.path.join(self.__web_dir, 'config_folders.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveDirectories(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        for kw in LIST_DIRPAGE:
            value = kwargs.get(kw)
            if value is not None:
                value = platform_encode(value)
                if kw in ('complete_dir', 'dirscan_dir'):
                    msg = config.get_config('misc', kw).set(value, create=True)
                else:
                    msg = config.get_config('misc', kw).set(value)
                if msg:
                    # return sabnzbd.api.report('json', error=msg)
                    return badParameterResponse(msg, kwargs.get('ajax'))

        sabnzbd.check_incomplete_vs_complete()
        config.save_config()
        if kwargs.get('ajax'):
            return sabnzbd.api.report('json')
        else:
            raise dcRaiser(self.__root, kwargs)


##############################################################################
SWITCH_LIST = \
    ('par2_multicore', 'par_option', 'enable_unrar', 'enable_unzip', 'enable_filejoin',
             'enable_tsjoin', 'overwrite_files', 'top_only',
             'auto_sort', 'propagation_delay', 'check_new_rel', 'auto_disconnect', 'flat_unpack',
             'safe_postproc', 'no_dupes', 'replace_spaces', 'replace_dots', 'replace_illegal', 'auto_browser',
             'ignore_samples', 'pause_on_post_processing', 'quick_check', 'nice', 'ionice',
             'pre_script', 'pause_on_pwrar', 'ampm', 'sfv_check', 'folder_rename',
             'unpack_check', 'quota_size', 'quota_day', 'quota_resume', 'quota_period',
             'pre_check', 'max_art_tries', 'max_art_opt', 'fail_hopeless', 'enable_7zip', 'enable_all_par',
             'enable_recursive', 'no_series_dupes', 'script_can_fail', 'new_nzb_on_failure',
             'unwanted_extensions', 'action_on_unwanted_extensions', 'enable_meta', 'sanitize_safe',
             'rating_enable', 'rating_api_key', 'rating_feedback', 'rating_filter_enable',
             'rating_filter_abort_audio', 'rating_filter_abort_video', 'rating_filter_abort_encrypted',
             'rating_filter_abort_encrypted_confirm', 'rating_filter_abort_spam', 'rating_filter_abort_spam_confirm',
             'rating_filter_abort_downvoted', 'rating_filter_abort_keywords',
             'rating_filter_pause_audio', 'rating_filter_pause_video', 'rating_filter_pause_encrypted',
             'rating_filter_pause_encrypted_confirm', 'rating_filter_pause_spam', 'rating_filter_pause_spam_confirm',
             'rating_filter_pause_downvoted', 'rating_filter_pause_keywords',
             'load_balancing'
     )


class ConfigSwitches(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        conf['have_multicore'] = sabnzbd.WIN32 or sabnzbd.DARWIN_INTEL
        conf['have_nice'] = bool(sabnzbd.newsunpack.NICE_COMMAND)
        conf['have_ionice'] = bool(sabnzbd.newsunpack.IONICE_COMMAND)
        conf['have_unrar'] = bool(sabnzbd.newsunpack.RAR_COMMAND)
        conf['have_unzip'] = bool(sabnzbd.newsunpack.ZIP_COMMAND)
        conf['have_7zip'] = bool(sabnzbd.newsunpack.SEVEN_COMMAND)
        conf['cleanup_list'] = cfg.cleanup_list.get_string()

        for kw in SWITCH_LIST:
            conf[kw] = config.get_config('misc', kw)()
        conf['unwanted_extensions'] = cfg.unwanted_extensions.get_string()

        conf['script_list'] = list_scripts() or ['None']
        conf['have_ampm'] = HAVE_AMPM

        template = Template(file=os.path.join(self.__web_dir, 'config_switches.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveSwitches(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        for kw in SWITCH_LIST:
            item = config.get_config('misc', kw)
            value = platform_encode(kwargs.get(kw))
            if kw == 'unwanted_extensions' and value:
                value = value.lower().replace('.', '')
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        cleanup_list = kwargs.get('cleanup_list')
        if cleanup_list and sabnzbd.WIN32:
            cleanup_list = cleanup_list.lower()
        cfg.cleanup_list.set(cleanup_list)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


##############################################################################
SPECIAL_BOOL_LIST = \
    ('start_paused', 'no_penalties', 'ignore_wrong_unrar', 'create_group_folders',
              'queue_complete_pers', 'api_warnings', 'allow_64bit_tools',
              'prospective_par_download', 'never_repair', 'allow_streaming', 'ignore_unrar_dates',
              'osx_menu', 'osx_speed', 'win_menu', 'use_pickle', 'allow_incomplete_nzb',
              'rss_filenames', 'ipv6_hosting', 'keep_awake', 'empty_postproc', 'html_login',
              'web_watchdog', 'wait_for_dfolder', 'warn_empty_nzb', 'enable_bonjour',
              'allow_duplicate_files', 'warn_dupl_jobs', 'backup_for_duplicates', 'enable_par_cleanup',
              'enable_https_verification', 'api_logging', 'fixed_ports'
     )
SPECIAL_VALUE_LIST = \
    ('size_limit', 'folder_max_length', 'fsys_type', 'movie_rename_limit', 'nomedia_marker',
              'req_completion_rate', 'wait_ext_drive', 'history_limit', 'show_sysload',
              'ipv6_servers', 'rating_host', 'selftest_host'
     )
SPECIAL_LIST_LIST = \
    ('rss_odd_titles', 'prio_sort_list'
     )


class ConfigSpecial(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        conf['nt'] = sabnzbd.WIN32

        conf['switches'] = [(kw, config.get_config('misc', kw)(), config.get_config('misc', kw).default()) for kw in SPECIAL_BOOL_LIST]
        conf['entries'] = [(kw, config.get_config('misc', kw)(), config.get_config('misc', kw).default()) for kw in SPECIAL_VALUE_LIST]
        conf['entries'].extend([(kw, config.get_config('misc', kw).get_string(), '') for kw in SPECIAL_LIST_LIST])

        template = Template(file=os.path.join(self.__web_dir, 'config_special.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveSpecial(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        for kw in SPECIAL_BOOL_LIST + SPECIAL_VALUE_LIST + SPECIAL_LIST_LIST:
            item = config.get_config('misc', kw)
            value = kwargs.get(kw)
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


##############################################################################
GENERAL_LIST = (
    'host', 'port', 'username', 'password', 'disable_api_key',
    'refresh_rate', 'cache_limit', 'local_ranges', 'inet_exposure',
    'enable_https', 'https_port', 'https_cert', 'https_key', 'https_chain'
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
                col = color.replace('.css', '')
                lst.append(col)
            return lst

        def add_color(skin_dir, color):
            if skin_dir:
                if not color:
                    try:
                        color = DEF_SKIN_COLORS[skin_dir.lower()]
                    except KeyError:
                        return skin_dir
                return '%s - %s' % (skin_dir, color)
            else:
                return ''

        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        conf['configfn'] = config.get_filename()

        # Temporary fix, problem with build_header
        conf['restart_req'] = sabnzbd.RESTART_REQ

        if sabnzbd.newswrapper.HAVE_SSL:
            conf['have_ssl'] = 1
        else:
            conf['have_ssl'] = 0

        wlist = []
        interfaces = globber_full(sabnzbd.DIR_INTERFACES)
        for k in interfaces:
            if k.endswith(DEF_STDINTF):
                interfaces.remove(k)
                interfaces.insert(0, k)
                break
        for k in interfaces:
            if k.endswith(DEF_STDCONFIG):
                interfaces.remove(k)
                break
        for web in interfaces:
            rweb = os.path.basename(web)
            if os.access(web + '/' + DEF_MAIN_TMPL, os.R_OK):
                cols = ListColors(rweb)
                if cols:
                    for col in cols:
                        wlist.append(add_color(rweb, col))
                else:
                    wlist.append(rweb)
        conf['web_list'] = wlist
        conf['web_dir'] = add_color(cfg.web_dir(), cfg.web_color())
        conf['web_dir2'] = add_color(cfg.web_dir2(), cfg.web_color2())

        conf['language'] = cfg.language()
        lang_list = list_languages()
        if len(lang_list) < 2:
            lang_list = []
        conf['lang_list'] = lang_list

        conf['disable_api_key'] = cfg.disable_key()
        conf['host'] = cfg.cherryhost()
        conf['port'] = cfg.cherryport()
        conf['https_port'] = cfg.https_port()
        conf['https_cert'] = cfg.https_cert()
        conf['https_key'] = cfg.https_key()
        conf['https_chain'] = cfg.https_chain()
        conf['enable_https'] = cfg.enable_https()
        conf['username'] = cfg.username()
        conf['password'] = cfg.password.get_stars()
        conf['html_login'] = cfg.html_login()
        conf['bandwidth_max'] = cfg.bandwidth_max()
        conf['bandwidth_perc'] = cfg.bandwidth_perc()
        conf['refresh_rate'] = cfg.refresh_rate()
        conf['cache_limit'] = cfg.cache_limit()
        conf['cleanup_list'] = cfg.cleanup_list.get_string()
        conf['nzb_key'] = cfg.nzb_key()
        conf['local_ranges'] = cfg.local_ranges.get_string()
        conf['inet_exposure'] = cfg.inet_exposure()
        conf['my_lcldata'] = cfg.admin_dir.get_path()
        conf['caller_url1'] = cherrypy.request.base + '/sabnzbd/'
        conf['caller_url2'] = cherrypy.request.base + '/sabnzbd/m/'

        template = Template(file=os.path.join(self.__web_dir, 'config_general.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveGeneral(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        # Special handling for cache_limitstr
        # kwargs['cache_limit'] = kwargs.get('cache_limitstr')

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
            sabnzbd.api.clear_trans_cache()

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

        bandwidth_max = kwargs.get('bandwidth_max')
        if bandwidth_max is not None:
            cfg.bandwidth_max.set(bandwidth_max)
        bandwidth_perc = kwargs.get('bandwidth_perc')
        if bandwidth_perc is not None:
            cfg.bandwidth_perc.set(bandwidth_perc)
        bandwidth_perc = cfg.bandwidth_perc()
        if bandwidth_perc and not bandwidth_max:
            logging.warning(T('You must set a maximum bandwidth before you can set a bandwidth limit'))

        config.save_config()

        # Update CherryPy authentication
        set_auth(cherrypy.config)
        if kwargs.get('ajax'):
            return sabnzbd.api.report('json', data={'success': True, 'restart_req': sabnzbd.RESTART_REQ})
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def generateAPIKey(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        logging.debug('API Key Changed')
        cfg.api_key.set(config.create_api_key())
        config.save_config()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def generateNzbKey(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

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


##############################################################################
class ConfigServer(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        new = []
        servers = config.get_servers()
        server_names = sorted(servers.keys(), key=lambda svr: '%d%02d%s' % (int(not servers[svr].enable()), servers[svr].priority(), servers[svr].displayname().lower()))
        for svr in server_names:
            new.append(servers[svr].get_dict(safe=True))
            t, m, w, d = BPSMeter.do.amounts(svr)
            if t:
                new[-1]['amounts'] = to_units(t), to_units(m), to_units(w), to_units(d)
        conf['servers'] = new
        conf['cats'] = list_cats(default=True)

        if sabnzbd.newswrapper.HAVE_SSL:
            conf['have_ssl'] = 1
            conf['ssl_protocols'] = ssl_protocols()
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
        if msg:
            return msg
        kwargs['section'] = 'servers'
        kwargs['keyword'] = kwargs.get('server')
        del_from_section(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def clrServer(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        server = kwargs.get('server')
        if server:
            BPSMeter.do.clear_server(server)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def toggleServer(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        server = kwargs.get('server')
        if server:
            svr = config.get_config('servers', server)
            if svr:
                svr.enable.set(not svr.enable())
                config.save_config()
                Downloader.do.update_server(server, server)
        raise dcRaiser(self.__root, kwargs)


def unique_svr_name(server):
    """ Return a unique variant on given server name """
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
    if msg:
        return msg

    ajax = kwargs.get('ajax')
    host = kwargs.get('host', '').strip()
    if not host:
        return badParameterResponse(T('Server address required'), ajax)

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
        msg = check_server(host, port, ajax)
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

    for kw in ('ssl', 'send_group', 'enable', 'optional'):
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
        if ajax:
            return sabnzbd.api.report('json')
        else:
            raise dcRaiser(root, kwargs)


def handle_server_test(kwargs, root):
    _result, msg = test_nntp_server_dict(kwargs)
    return msg


##############################################################################
class ConfigRss(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__refresh_readout = None  # Set to URL when new readout is needed
        self.__refresh_download = False
        self.__refresh_force = False
        self.__refresh_ignore = False
        self.__last_msg = ''

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

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
            rss[feed]['filter_states'] = [bool(sabnzbd.rss.convert_filter(f[4])) for f in filters]
            rss[feed]['filtercount'] = len(filters)

            rss[feed]['pick_cat'] = pick_cat
            rss[feed]['pick_script'] = pick_script
            rss[feed]['link'] = urllib.quote_plus(feed.encode('utf-8'))
            rss[feed]['baselink'] = get_base_url(rss[feed]['uri'])

        active_feed = kwargs.get('feed', '')
        conf['active_feed'] = active_feed
        conf['rss'] = rss
        conf['rss_next'] = time.strftime(time_format('%H:%M'), time.localtime(sabnzbd.rss.next_run())).decode(codepage)

        if active_feed:
            readout = bool(self.__refresh_readout)
            logging.debug('RSS READOUT = %s', readout)
            if not readout:
                self.__refresh_download = False
                self.__refresh_force = False
                self.__refresh_ignore = False
            msg = sabnzbd.rss.run_feed(active_feed, download=self.__refresh_download, force=self.__refresh_force,
                                 ignoreFirst=self.__refresh_ignore, readout=readout)
            if readout:
                sabnzbd.rss.save()
                self.__last_msg = msg
            else:
                msg = self.__last_msg
            self.__refresh_readout = None
            conf['error'] = msg

            conf['downloaded'], conf['matched'], conf['unmatched'] = GetRssLog(active_feed)
        else:
            self.__last_msg = ''

        # Find a unique new Feed name
        unum = 1
        txt = T('Feed')  # : Used as default Feed name in Config->RSS
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
        if msg:
            return msg
        cfg.rss_rate.set(kwargs.get('rss_rate'))
        config.save_config()
        scheduler.restart()
        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def upd_rss_feed(self, **kwargs):
        """ Update Feed level attributes,
            legacy version: ignores 'enable' parameter
        """
        msg = check_session(kwargs)
        if msg:
            return msg
        if kwargs.get('enable') is not None:
            del kwargs['enable']
        try:
            cf = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            cf = None
        uri = Strip(kwargs.get('uri'))
        if cf and uri:
            kwargs['uri'] = uri
            cf.set_dict(kwargs)
            config.save_config()

        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def save_rss_feed(self, **kwargs):
        """ Update Feed level attributes """
        msg = check_session(kwargs)
        if msg:
            return msg
        try:
            cf = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            cf = None
        if 'enable' not in kwargs:
            kwargs['enable'] = 0
        uri = Strip(kwargs.get('uri'))
        if cf and uri:
            kwargs['uri'] = uri
            cf.set_dict(kwargs)
            config.save_config()

        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def toggle_rss_feed(self, **kwargs):
        """ Toggle automatic read-out flag of Feed """
        msg = check_session(kwargs)
        if msg:
            return msg
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
        if msg:
            return msg
        feed = Strip(kwargs.get('feed')).strip('[]')
        uri = Strip(kwargs.get('uri'))
        if feed and uri:
            try:
                cfg = config.get_rss()[feed]
            except KeyError:
                cfg = None
            if (not cfg) and uri:
                kwargs['feed'] = feed
                kwargs['uri'] = uri
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
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def upd_rss_filter(self, **kwargs):
        """ Save updated filter definition """
        msg = check_session(kwargs)
        if msg:
            return msg
        try:
            cfg = config.get_rss()[kwargs.get('feed')]
        except KeyError:
            raise rssRaiser(self.__root, kwargs)

        pp = kwargs.get('pp')
        if IsNone(pp):
            pp = ''
        script = ConvertSpecials(kwargs.get('script'))
        cat = ConvertSpecials(kwargs.get('cat'))
        prio = ConvertSpecials(kwargs.get('priority'))
        filt = kwargs.get('filter_text')
        enabled = kwargs.get('enabled', '0')

        if filt:
            cfg.filters.update(int(kwargs.get('index', 0)), (cat, pp, script, kwargs.get('filter_type'),
                                                             platform_encode(filt), prio, enabled))

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
        if msg:
            return msg
        kwargs['section'] = 'rss'
        kwargs['keyword'] = kwargs.get('feed')
        del_from_section(kwargs)
        sabnzbd.rss.clear_feed(kwargs.get('feed'))
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def del_rss_filter(self, **kwargs):
        """ Remove one RSS filter """
        msg = check_session(kwargs)
        if msg:
            return msg
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
        if msg:
            return msg
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
        if msg:
            return msg
        sabnzbd.rss.clear_downloaded(kwargs['feed'])
        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def test_rss_feed(self, *args, **kwargs):
        """ Read the feed content again and show results """
        msg = check_session(kwargs)
        if msg:
            return msg
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
        if msg:
            return msg
        feed = kwargs.get('feed')
        url = kwargs.get('url')
        nzbname = kwargs.get('nzbname')
        att = sabnzbd.rss.lookup_url(feed, url)
        if att:
            pp = att.get('pp')
            cat = att.get('cat')
            script = att.get('script')
            prio = att.get('prio')

            if url:
                sabnzbd.add_url(url, pp, script, cat, prio, nzbname)
            # Need to pass the title instead
            sabnzbd.rss.flag_downloaded(feed, url)
        raise rssRaiser(self.__root, kwargs)

    @cherrypy.expose
    def rss_now(self, *args, **kwargs):
        """ Run an automatic RSS run now """
        msg = check_session(kwargs)
        if msg:
            return msg
        scheduler.force_rss()
        raise rssRaiser(self.__root, kwargs)


##############################################################################
_SCHED_ACTIONS = ('resume', 'pause', 'pause_all', 'shutdown', 'restart', 'speedlimit',
                  'pause_post', 'resume_post', 'scan_folder', 'rss_scan', 'remove_failed',
                  'remove_completed', 'pause_all_low', 'pause_all_normal', 'pause_all_high',
                  'resume_all_low', 'resume_all_normal', 'resume_all_high',
                  'enable_quota', 'disable_quota'
                  )


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

        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        actions = []
        actions.extend(_SCHED_ACTIONS)
        day_names = get_days()
        conf['schedlines'] = []
        snum = 1
        conf['taskinfo'] = []
        for ev in scheduler.sort_schedules(all_events=False):
            line = ev[3]
            conf['schedlines'].append(line)
            try:
                m, h, day_numbers, action = line.split(' ', 3)
            except:
                continue
            action = action.strip()
            try:
                action, value = action.split(' ', 1)
            except:
                value = ''
            value = value.strip()
            if value and not value.lower().strip('0123456789kmgtp%.'):
                if '%' not in value and from_units(value) < 1.0:
                    value = T('off')  # : "Off" value for speedlimit in scheduler
                else:
                    if '%' not in value and int_conv(value) > 1 and int_conv(value) < 101:
                        value += '%'
                    value = value.upper()
            if action in actions:
                action = Ttemplate("sch-" + action)
            else:
                if action in ('enable_server', 'disable_server'):
                    try:
                        value = '"%s"' % config.get_servers()[value].displayname()
                    except KeyError:
                        value = '"%s" <<< %s' % (value, T('Undefined server!'))
                    action = Ttemplate("sch-" + action)

            if day_numbers == "1234567":
                days_of_week = "Daily"
            elif day_numbers == "12345":
                days_of_week = "Weekdays"
            elif day_numbers == "67":
                days_of_week = "Weekends"
            else:
                days_of_week = ", ".join([day_names.get(i, "**") for i in day_numbers])
            item = (snum, '%02d' % int(h), '%02d' % int(m), days_of_week, '%s %s' % (action, value))

            conf['taskinfo'].append(item)
            snum += 1

        actions_lng = {}
        for action in actions:
            actions_lng[action] = Ttemplate("sch-" + action)

        actions_servers = {}
        servers = config.get_servers()
        for srv in servers:
            actions_servers[srv] = servers[srv].displayname()

        conf['actions_servers'] = actions_servers
        conf['actions'] = actions
        conf['actions_lng'] = actions_lng

        template = Template(file=os.path.join(self.__web_dir, 'config_scheduling.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def addSchedule(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        servers = config.get_servers()
        minute = kwargs.get('minute')
        hour = kwargs.get('hour')
        days_of_week = ''.join([str(x) for x in kwargs.get('daysofweek', '')])
        if not days_of_week:
            days_of_week = '1234567'
        action = kwargs.get('action')
        arguments = kwargs.get('arguments')

        arguments = arguments.strip().lower()
        if arguments in ('on', 'enable'):
            arguments = '1'
        elif arguments in ('off', 'disable'):
            arguments = '0'

        if minute and hour and days_of_week and action:
            if action == 'speedlimit':
                if not arguments or arguments.strip('0123456789kmgtp%.'):
                    arguments = 0
            elif action in _SCHED_ACTIONS:
                arguments = ''
            elif action in servers:
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
                             (minute, hour, days_of_week, action, arguments))
                cfg.schedules.set(sched)

        config.save_config()
        scheduler.restart(force=True)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def delSchedule(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        schedules = cfg.schedules()
        line = kwargs.get('line')
        if line and line in schedules:
            schedules.remove(line)
            cfg.schedules.set(schedules)
        config.save_config()
        scheduler.restart(force=True)
        raise dcRaiser(self.__root, kwargs)


##############################################################################
class ConfigCats(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        conf['script_list'] = list_scripts(default=True)

        categories = config.get_categories()
        conf['have_cats'] = len(categories) > 1
        conf['defdir'] = cfg.complete_dir.get_path()

        empty = {'name': '', 'pp': '-1', 'script': '', 'dir': '', 'newzbin': '', 'priority': DEFAULT_PRIORITY}
        slotinfo = []
        for cat in sorted(categories.keys()):
            slot = categories[cat].get_dict()
            slot['name'] = cat
            slot['newzbin'] = slot['newzbin'].replace('"', '&quot;')
            slotinfo.append(slot)
        slotinfo.insert(1, empty)
        conf['slotinfo'] = slotinfo

        template = Template(file=os.path.join(self.__web_dir, 'config_cat.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        kwargs['section'] = 'categories'
        kwargs['keyword'] = kwargs.get('name')
        del_from_section(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def save(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg

        name = kwargs.get('name', '*')
        if name == '*':
            newname = name
        else:
            newname = re.sub('"', '', kwargs.get('newname', ''))
        if newname:
            if name:
                config.delete('categories', name)
            name = newname.lower()
            if kwargs.get('dir'):
                kwargs['dir'] = platform_encode(kwargs['dir'])
            config.ConfigCat(name, kwargs)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


##############################################################################
SORT_LIST = (
    'enable_tv_sorting', 'tv_sort_string', 'tv_categories',
    'enable_movie_sorting', 'movie_sort_string', 'movie_sort_extra', 'movie_extra_folder',
    'enable_date_sorting', 'date_sort_string', 'movie_categories', 'date_categories'
)


class ConfigSorting(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)
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
        if msg:
            return msg

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
            value = kwargs.get(kw)
            msg = item.set(value)
            if msg:
                return badParameterResponse(msg)

        config.save_config()
        raise dcRaiser(self.__root, kwargs)


##############################################################################
LOG_API_RE = re.compile(r"(apikey|api)(=|:)[\w]+", re.I)
LOG_API_JSON_RE = re.compile(r"u'(apikey|api)': u'[\w]+'", re.I)
LOG_USER_RE = re.compile(r"(user|username)\s?=\s?[\w]+", re.I)
LOG_PASS_RE = re.compile(r"(password)\s?=\s?[\w]+", re.I)
LOG_INI_HIDE_RE = re.compile(r"(email_pwd|rating_api_key|pushover_token|pushover_userkey|pushbullet_apikey|prowl_apikey|growl_password|growl_server)\s?=\s?[\w]+", re.I)
LOG_HASH_RE = re.compile(r"([a-fA-F\d]{25})", re.I)

class Status(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim

    @cherrypy.expose
    def index(self, **kwargs):
        if not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        header = build_status(web_dir=self.__web_dir, prim=self.__prim, skip_dashboard=kwargs.get('skip_dashboard'))

        template = Template(file=os.path.join(self.__web_dir, 'status.tmpl'),
                            filter=FILTER, searchList=[header], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def reset_quota(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        BPSMeter.do.reset_quota(force=True)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def disconnect(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        Downloader.do.disconnect()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def refresh_conn(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        # No real action, just reload the page
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def showlog(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        try:
            sabnzbd.LOGHANDLER.flush()
        except:
            pass

        # Fetch the INI and the log-data and add a message at the top
        log_data  = '--------------------------------\n\n'
        log_data += 'The log includes a copy of your sabnzbd.ini with\nall usernames, passwords and API-keys removed.'
        log_data += '\n\n--------------------------------\n'
        log_data += open(sabnzbd.LOGFILE, "r").read()
        log_data += open(config.get_filename(), 'r').read()

        # We need to remove all passwords/usernames/api-keys
        log_data = LOG_API_RE.sub("apikey=<APIKEY>", log_data)
        log_data = LOG_API_JSON_RE.sub("'apikey':<APIKEY>'", log_data)
        log_data = LOG_USER_RE.sub("\g<1>=<USER>", log_data)
        log_data = LOG_PASS_RE.sub("password=<PASSWORD>", log_data)
        log_data = LOG_INI_HIDE_RE.sub(r"\1 = <REMOVED>", log_data)
        log_data = LOG_HASH_RE.sub("<HASH>", log_data)

        # Try to replace the username
        try:
            import getpass
            cur_user = getpass.getuser()
            if cur_user:
                log_data = log_data.replace(cur_user, '<USERNAME>')
        except:
            pass   
        # Set headers
        cherrypy.response.headers['Content-Type'] = 'application/x-download;charset=utf-8'
        cherrypy.response.headers['Content-Disposition'] = 'attachment;filename="sabnzbd.log"'
        return log_data

    @cherrypy.expose
    def showweb(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        if sabnzbd.WEBLOGFILE:
            return cherrypy.lib.static.serve_file(sabnzbd.WEBLOGFILE, "application/x-download", "attachment")
        else:
            return "Web logging is off!"

    @cherrypy.expose
    def clearwarnings(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        sabnzbd.GUIHANDLER.clear()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def change_loglevel(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        cfg.log_level.set(kwargs.get('loglevel'))
        config.save_config()

        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def unblock_server(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        Downloader.do.unblock(kwargs.get('server'))
        # Short sleep so that UI shows new server status
        time.sleep(1.0)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def delete(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        orphan_delete(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def delete_all(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        orphan_delete_all()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        orphan_add(kwargs)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def add_all(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        orphan_add_all()
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def dashrefresh(self, **kwargs):
        # This function is run when Refresh button on Dashboard is clicked
        # Put the time consuming dashboard functions here; they only get executed when the user clicks the Refresh button
        msg = check_session(kwargs)
        if msg:
            return msg

        from sabnzbd.utils.diskspeed import diskspeedmeasure
        sabnzbd.downloaddirspeed = round(diskspeedmeasure(sabnzbd.cfg.download_dir.get_path()), 1)
        time.sleep(1.0)
        sabnzbd.completedirspeed = round(diskspeedmeasure(sabnzbd.cfg.complete_dir.get_path()), 1)

        raise dcRaiser(self.__root, kwargs)  # Refresh screen


def Protected():
    cherrypy.response.status = 403
    return 'Access denied' 

def NeedLogin(url, kwargs):
    raise dcRaiser(url + 'login/', kwargs)

def badParameterResponse(msg, ajax=None):
    """ Return a html page with error message and a 'back' button """
    if ajax:
        return sabnzbd.api.report('json', error=msg)
    else:
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


def ShowString(name, string):
    """ Return a html page listing a file and a 'back' button """
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
           <code><pre>%s</pre></code>
</body>
</html>
''' % (xml_name(name), T('Back'), xml_name(name), escape(unicoder(msg)))


def GetRssLog(feed):
    def make_item(job):
        url = job.get('url', '')
        title = xml_name(job.get('title', ''))
        size = job.get('size')
        if size:
            size = to_units(size).replace(' ', '&nbsp;')
        else:
            size = '?'
        if sabnzbd.rss.special_rss_site(url):
            nzbname = ""
        else:
            nzbname = xml_name(job.get('title', ''))
        return url, \
               title, \
               '*' * int(job.get('status', '').endswith('*')), \
               job.get('rule', 0), \
               nzbname, \
               size

    jobs = sabnzbd.rss.show_result(feed)
    names = jobs.keys()
    # Sort in the order the jobs came from the feed
    names.sort(lambda x, y: jobs[x].get('order', 0) - jobs[y].get('order', 0))

    good = [make_item(jobs[job]) for job in names if jobs[job]['status'][0] == 'G']
    bad = [make_item(jobs[job]) for job in names if jobs[job]['status'][0] == 'B']

    # Sort in reverse order of time stamp for 'Done'
    dnames = [job for job in jobs.keys() if jobs[job]['status'] == 'D']
    dnames.sort(lambda x, y: int(jobs[y].get('time', 0) - jobs[x].get('time', 0)))
    done = [xml_name(jobs[job]['title']) for job in dnames]

    return done, good, bad


##############################################################################
LIST_EMAIL = (
    'email_endjob', 'email_full',
    'email_server', 'email_to', 'email_from',
    'email_account', 'email_pwd', 'email_dir', 'email_rss'
)
LIST_GROWL = ('growl_enable', 'growl_server', 'growl_password',
              'growl_prio_startup', 'growl_prio_download', 'growl_prio_pp', 'growl_prio_complete', 'growl_prio_failed',
              'growl_prio_disk_full', 'growl_prio_warning', 'growl_prio_error', 'growl_prio_queue_done', 'growl_prio_other',
              'growl_prio_new_login')
LIST_NCENTER = ('ncenter_enable',
                'ncenter_prio_startup', 'ncenter_prio_download', 'ncenter_prio_pp', 'ncenter_prio_complete', 'ncenter_prio_failed',
                'ncenter_prio_disk_full', 'ncenter_prio_warning', 'ncenter_prio_error', 'ncenter_prio_queue_done', 'ncenter_prio_other',
                'ncenter_prio_new_login')
LIST_ACENTER = ('acenter_enable',
                'acenter_prio_startup', 'acenter_prio_download', 'acenter_prio_pp', 'acenter_prio_complete', 'acenter_prio_failed',
                'acenter_prio_disk_full', 'acenter_prio_warning', 'acenter_prio_error', 'acenter_prio_queue_done', 'acenter_prio_other',
                'acenter_prio_new_login')
LIST_NTFOSD = ('ntfosd_enable',
               'ntfosd_prio_startup', 'ntfosd_prio_download', 'ntfosd_prio_pp', 'ntfosd_prio_complete', 'ntfosd_prio_failed',
               'ntfosd_prio_disk_full', 'ntfosd_prio_warning', 'ntfosd_prio_error', 'ntfosd_prio_queue_done', 'ntfosd_prio_other',
               'ntfosd_prio_new_login')
LIST_PROWL = ('prowl_enable', 'prowl_apikey',
              'prowl_prio_startup', 'prowl_prio_download', 'prowl_prio_pp', 'prowl_prio_complete', 'prowl_prio_failed',
              'prowl_prio_disk_full', 'prowl_prio_warning', 'prowl_prio_error', 'prowl_prio_queue_done', 'prowl_prio_other',
              'prowl_prio_new_login')
LIST_PUSHOVER = ('pushover_enable', 'pushover_token', 'pushover_userkey', 'pushover_device',
                 'pushover_prio_startup', 'pushover_prio_download', 'pushover_prio_pp', 'pushover_prio_complete', 'pushover_prio_failed',
                 'pushover_prio_disk_full', 'pushover_prio_warning', 'pushover_prio_error', 'pushover_prio_queue_done', 'pushover_prio_other',
                 'pushover_prio_new_login')
LIST_PUSHBULLET = ('pushbullet_enable', 'pushbullet_apikey', 'pushbullet_device',
                   'pushbullet_prio_startup', 'pushbullet_prio_download', 'pushbullet_prio_pp', 'pushbullet_prio_complete', 'pushbullet_prio_failed',
                   'pushbullet_prio_disk_full', 'pushbullet_prio_warning', 'pushbullet_prio_error', 'pushbullet_prio_queue_done', 'pushbullet_prio_other',
                   'pushbullet_prio_new_login')
LIST_NSCRIPT = ('nscript_enable', 'nscript_script', 'nscript_parameters',
                'nscript_prio_startup', 'nscript_prio_download', 'nscript_prio_pp', 'nscript_prio_complete', 'nscript_prio_failed',
                'nscript_prio_disk_full', 'nscript_prio_warning', 'nscript_prio_error', 'nscript_prio_queue_done', 'nscript_prio_other',
                'nscript_prio_new_login')


class ConfigNotify(object):

    def __init__(self, web_dir, root, prim):
        self.__root = root
        self.__web_dir = web_dir
        self.__prim = prim
        self.__lastmail = None

    @cherrypy.expose
    def index(self, **kwargs):
        if cfg.configlock() or not check_access():
            return Protected()
        if not check_login():
            raise NeedLogin(self.__root, kwargs)

        conf = build_header(self.__prim, self.__web_dir)

        conf['my_home'] = sabnzbd.DIR_HOME
        conf['lastmail'] = self.__lastmail
        conf['have_growl'] = True
        conf['have_ntfosd'] = sabnzbd.notifier.have_ntfosd()
        conf['have_ncenter'] = sabnzbd.DARWIN_VERSION > 7 and bool(sabnzbd.notifier.ncenter_path())
        conf['script_list'] = list_scripts(default=False, none=True)

        for kw in LIST_EMAIL:
            conf[kw] = config.get_config('misc', kw).get_string()
        for kw in LIST_GROWL:
            try:
                conf[kw] = config.get_config('growl', kw)()
            except:
                logging.debug('MISSING KW=%s', kw)
        for kw in LIST_PROWL:
            conf[kw] = config.get_config('prowl', kw)()
        for kw in LIST_PUSHOVER:
            conf[kw] = config.get_config('pushover', kw)()
        for kw in LIST_PUSHBULLET:
            conf[kw] = config.get_config('pushbullet', kw)()
        for kw in LIST_NCENTER:
            conf[kw] = config.get_config('ncenter', kw)()
        for kw in LIST_ACENTER:
            conf[kw] = config.get_config('acenter', kw)()
        for kw in LIST_NTFOSD:
            conf[kw] = config.get_config('ntfosd', kw)()
        for kw in LIST_NSCRIPT:
            conf[kw] = config.get_config('nscript', kw)()
        conf['notify_texts'] = sabnzbd.notifier.NOTIFICATION

        template = Template(file=os.path.join(self.__web_dir, 'config_notify.tmpl'),
                            filter=FILTER, searchList=[conf], compilerSettings=DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def saveEmail(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        ajax = kwargs.get('ajax')

        for kw in LIST_EMAIL:
            msg = config.get_config('misc', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_GROWL:
            msg = config.get_config('growl', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_NCENTER:
            msg = config.get_config('ncenter', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_ACENTER:
            msg = config.get_config('acenter', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_NTFOSD:
            msg = config.get_config('ntfosd', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_PROWL:
            msg = config.get_config('prowl', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_PUSHOVER:
            msg = config.get_config('pushover', kw).set(platform_encode(kwargs.get(kw)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_PUSHBULLET:
            msg = config.get_config('pushbullet', kw).set(platform_encode(kwargs.get(kw, 0)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)
        for kw in LIST_NSCRIPT:
            msg = config.get_config('nscript', kw).set(platform_encode(kwargs.get(kw, 0)))
            if msg:
                return badParameterResponse(T('Incorrect value for %s: %s') % (kw, unicoder(msg)), ajax)

        config.save_config()
        self.__lastmail = None
        if ajax:
            return sabnzbd.api.report('json')
        else:
            raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def testmail(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        self.__lastmail = _api_test_email(name=None, output=None, kwargs=None)
        raise dcRaiser(self.__root, kwargs)

    @cherrypy.expose
    def testnotification(self, **kwargs):
        msg = check_session(kwargs)
        if msg:
            return msg
        _api_test_notif(name=None, output=None, kwargs=None)
        raise dcRaiser(self.__root, kwargs)


def rss_history(url, limit=50, search=None):
    url = url.replace('rss', '')

    youngest = None

    rss = RSS()
    rss.channel.title = "SABnzbd History"
    rss.channel.description = "Overview of completed downloads"
    rss.channel.link = "http://sabnzbd.org/"
    rss.channel.language = "en"

    items, _fetched_items, _max_items = build_history(limit=limit, search=search)

    for history in items:
        item = Item()

        item.pubDate = std_time(history['completed'])
        item.title = history['name']

        if not youngest:
            youngest = history['completed']
        elif history['completed'] < youngest:
            youngest = history['completed']

        if history['url_info']:
            item.link = history['url_info']
        else:
            item.link = url
            item.guid = history['nzo_id']

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
    """ Return an RSS feed with last warnings/errors """
    rss = RSS()
    rss.channel.title = "SABnzbd Warnings"
    rss.channel.description = "Overview of warnings/errors"
    rss.channel.link = "http://sabnzbd.org/"
    rss.channel.language = "en"

    for warn in sabnzbd.GUIHANDLER.content():
        item = Item()
        item.title = warn
        rss.addItem(item)

    rss.channel.lastBuildDate = std_time(time.time())
    rss.channel.pubDate = rss.channel.lastBuildDate
    return rss.write()

