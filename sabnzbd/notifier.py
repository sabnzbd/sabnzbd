#!/usr/bin/python -OO
# Copyright 2007-2019 The SABnzbd-Team <team@sabnzbd.org>
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
#

"""
sabnzbd.notifier - Send notifications to any notification services
"""

from __future__ import with_statement
import os.path
import logging
import urllib2
import httplib
import urllib
import subprocess
import json
from threading import Thread

import sabnzbd
import sabnzbd.cfg
from sabnzbd.encoding import unicoder
from sabnzbd.constants import NOTIFY_KEYS
from sabnzbd.misc import split_host, make_script_path
from sabnzbd.newsunpack import external_script

from gntp.core import GNTPRegister
from gntp.notifier import GrowlNotifier
import gntp.errors

try:
    import Growl
    # Detect classic Growl (older than 1.3)
    _HAVE_CLASSIC_GROWL = os.path.isfile('/Library/PreferencePanes/Growl.prefPane/Contents/MacOS/Growl')
except ImportError:
    _HAVE_CLASSIC_GROWL = False

try:
    import warnings
    # Make any warnings exceptions, so that pynotify is ignored
    # PyNotify will not work with Python 2.5 (due to next three lines)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        import pynotify
    _HAVE_NTFOSD = True

    # Check for working version, not all pynotify are the same
    if not hasattr(pynotify, 'init'):
         _HAVE_NTFOSD = False
except:
    _HAVE_NTFOSD = False


##############################################################################
# Define translatable message table
##############################################################################
TT = lambda x: x
NOTIFICATION = {
    'startup': TT('Startup/Shutdown'),        #: Notification
    'download': TT('Added NZB'),               #: Notification
    'pp': TT('Post-processing started'),  # : Notification
    'complete': TT('Job finished'),            #: Notification
    'failed': TT('Job failed'),              #: Notification
    'warning': TT('Warning'),                 #: Notification
    'error': TT('Error'),                   #: Notification
    'disk_full': TT('Disk full'),               #: Notification
    'queue_done': TT('Queue finished'),          #: Notification
    'new_login': TT('User logged in'),          #: Notification
    'other': TT('Other Messages')           #: Notification
}

##############################################################################
# Setup platform dependent Growl support
##############################################################################
_GROWL = None       # Instance of the Notifier after registration
_GROWL_REG = False  # Succesful registration
_GROWL_DATA = (None, None)    # Address and password


def get_icon():
    icon = os.path.join(os.path.join(sabnzbd.DIR_PROG, 'icons'), 'sabnzbd.ico')
    if not os.path.isfile(icon):
        icon = os.path.join(sabnzbd.DIR_PROG, 'sabnzbd.ico')
    if os.path.isfile(icon):
        fp = open(icon, 'rb')
        icon = fp.read()
        fp.close()
    else:
        icon = None
    return icon


def change_value():
    """ Signal that we should register with a new Growl server """
    global _GROWL_REG
    _GROWL_REG = False


def have_ntfosd():
    """ Return if any PyNotify support is present """
    return bool(_HAVE_NTFOSD)


def check_classes(gtype, section):
    """ Check if `gtype` is enabled in `section` """
    try:
        return sabnzbd.config.get_config(section, '%s_prio_%s' % (section, gtype))() > 0
    except TypeError:
        logging.debug('Incorrect Notify option %s:%s_prio_%s', section, section, gtype)
        return False


def get_prio(gtype, section):
    """ Check prio of `gtype` in `section` """
    try:
        return sabnzbd.config.get_config(section, '%s_prio_%s' % (section, gtype))()
    except TypeError:
        logging.debug('Incorrect Notify option %s:%s_prio_%s', section, section, gtype)
        return -1000


def check_cat(section, job_cat, keyword=None):
    """ Check if `job_cat` is enabled in `section`.
        * = All, if no other categories selected.
    """
    if not job_cat:
        return True
    try:
        if not keyword:
            keyword = section
        section_cats = sabnzbd.config.get_config(section, '%s_cats' % keyword)()
        return ['*'] == section_cats or job_cat in section_cats
    except TypeError:
        logging.debug('Incorrect Notify option %s:%s_cats', section, section)
        return True


def send_notification(title, msg, gtype, job_cat=None):
    """ Send Notification message """
    # Notification Center
    if sabnzbd.DARWIN and sabnzbd.cfg.ncenter_enable():
        if check_classes(gtype, 'ncenter') and check_cat('ncenter', job_cat):
            send_notification_center(title, msg, gtype)

    # Windows
    if sabnzbd.WIN32 and sabnzbd.cfg.acenter_enable():
        if check_classes(gtype, 'acenter') and check_cat('acenter', job_cat):
            send_windows(title, msg, gtype)

    # Growl
    if sabnzbd.cfg.growl_enable() and check_classes(gtype, 'growl') and check_cat('growl', job_cat):
        if _HAVE_CLASSIC_GROWL and not sabnzbd.cfg.growl_server():
            return send_local_growl(title, msg, gtype)
        else:
            Thread(target=send_growl, args=(title, msg, gtype)).start()

    # Prowl
    if sabnzbd.cfg.prowl_enable() and check_cat('prowl', job_cat):
        if sabnzbd.cfg.prowl_apikey():
            Thread(target=send_prowl, args=(title, msg, gtype)).start()

    # Pushover
    if sabnzbd.cfg.pushover_enable() and check_cat('pushover', job_cat):
        if sabnzbd.cfg.pushover_token():
            Thread(target=send_pushover, args=(title, msg, gtype)).start()

    # Pushbullet
    if sabnzbd.cfg.pushbullet_enable() and check_cat('pushbullet', job_cat):
        if sabnzbd.cfg.pushbullet_apikey() and check_classes(gtype, 'pushbullet'):
            Thread(target=send_pushbullet, args=(title, msg, gtype)).start()

    # Notification script.
    if sabnzbd.cfg.nscript_enable() and check_cat('nscript', job_cat):
        if sabnzbd.cfg.nscript_script():
            Thread(target=send_nscript, args=(title, msg, gtype)).start()

    # NTFOSD
    if have_ntfosd() and sabnzbd.cfg.ntfosd_enable():
        if check_classes(gtype, 'ntfosd') and check_cat('ntfosd', job_cat):
            send_notify_osd(title, msg)


def reset_growl():
    """ Reset Growl (after changing language) """
    global _GROWL, _GROWL_REG
    _GROWL = None
    _GROWL_REG = False


def register_growl(growl_server, growl_password):
    """ Register this app with Growl """
    error = None
    host, port = split_host(growl_server or '')

    sys_name = hostname(host)

    # Reduce logging of Growl in Debug/Info mode
    logging.getLogger('gntp').setLevel(logging.WARNING)

    # Clean up persistent data in GNTP to make re-registration work
    GNTPRegister.notifications = []
    GNTPRegister.headers = {}

    growler = GrowlNotifier(
        applicationName='SABnzbd%s' % sys_name,
        applicationIcon=get_icon(),
        notifications=[Tx(NOTIFICATION[key]) for key in NOTIFY_KEYS],
        hostname=host or 'localhost',
        port=port or 23053,
        password=growl_password or None
    )

    try:
        ret = growler.register()
        if ret is None or isinstance(ret, bool):
            logging.info('Registered with Growl')
            ret = growler
        else:
            error = 'Cannot register with Growl %s' % str(ret)
            logging.debug(error)
            del growler
            ret = None
    except (gntp.errors.NetworkError, gntp.errors.AuthError) as err:
        error = 'Cannot register with Growl %s' % str(err)
        logging.debug(error)
        del growler
        ret = None
    except:
        error = 'Unknown Growl registration error'
        logging.debug(error)
        logging.info("Traceback: ", exc_info=True)
        del growler
        ret = None

    return ret, error


def send_growl(title, msg, gtype, test=None):
    """ Send Growl message """
    global _GROWL, _GROWL_REG, _GROWL_DATA

    # support testing values from UI
    if test:
        growl_server = test.get('growl_server') or None
        growl_password = test.get('growl_password') or None
    else:
        growl_server = sabnzbd.cfg.growl_server()
        growl_password = sabnzbd.cfg.growl_password()

    for n in (0, 1):
        if not _GROWL_REG:
            _GROWL = None
        if (growl_server, growl_password) != _GROWL_DATA:
            reset_growl()
        if not _GROWL:
            _GROWL, error = register_growl(growl_server, growl_password)
        if _GROWL:
            _GROWL_REG = True
            if isinstance(msg, unicode):
                msg = msg.decode('utf-8')
            elif not isinstance(msg, str):
                msg = str(msg)
            logging.debug('Send to Growl: %s %s %s', gtype, title, msg)
            try:
                ret = _GROWL.notify(
                    noteType=Tx(NOTIFICATION.get(gtype, 'other')),
                    title=title,
                    description=unicoder(msg),
                )
                if ret is None or isinstance(ret, bool):
                    return None
                elif ret[0] == '401':
                    _GROWL = False
                else:
                    logging.debug('Growl error %s', ret)
                    return 'Growl error %s', ret
            except (gntp.errors.NetworkError, gntp.errors.AuthError) as err:
                error = 'Growl error %s' % err
                logging.debug(error)
                return error
            except:
                error = 'Growl error (unknown)'
                logging.debug(error)
                return error
        else:
            return error
    return None

##############################################################################
# Local OSX Growl support
##############################################################################
if _HAVE_CLASSIC_GROWL:
    _local_growl = None
    if os.path.isfile('sabnzbdplus.icns'):
        _OSX_ICON = Growl.Image.imageFromPath('sabnzbdplus.icns')
    elif os.path.isfile('osx/resources/sabnzbdplus.icns'):
        _OSX_ICON = Growl.Image.imageFromPath('osx/resources/sabnzbdplus.icns')
    else:
        _OSX_ICON = Growl.Image.imageWithIconForApplication('Terminal')

    def send_local_growl(title, msg, gtype):
        """ Send to local Growl server, OSX-only """
        global _local_growl
        if not _local_growl:
            notes = [Tx(NOTIFICATION[key]) for key in NOTIFY_KEYS]
            _local_growl = Growl.GrowlNotifier(
                applicationName='SABnzbd',
                applicationIcon=_OSX_ICON,
                notifications=notes,
                defaultNotifications=notes
            )
            _local_growl.register()
        _local_growl.notify(Tx(NOTIFICATION.get(gtype, 'other')), title, msg)
        return None


##############################################################################
# Ubuntu NotifyOSD Support
##############################################################################
_NTFOSD = False
def send_notify_osd(title, message):
    """ Send a message to NotifyOSD """
    global _NTFOSD
    if not _HAVE_NTFOSD:
        return T('Not available')  # : Function is not available on this OS

    error = 'NotifyOSD not working'
    icon = os.path.join(sabnzbd.DIR_PROG, 'sabnzbd.ico')
    _NTFOSD = _NTFOSD or pynotify.init('icon-summary-body')
    if _NTFOSD:
        logging.info('Send to NotifyOSD: %s / %s', title, message)
        try:
            note = pynotify.Notification(title, message, icon)
            note.show()
        except:
            # Apparently not implemented on this system
            logging.info(error)
            return error
        return None
    else:
        return error


def ncenter_path():
    """ Return path of Notification Center tool, if it exists """
    tool = os.path.normpath(os.path.join(sabnzbd.DIR_PROG, '../Resources/SABnzbd.app/Contents/MacOS/SABnzbd'))
    if os.path.exists(tool):
        return tool
    else:
        return None


def send_notification_center(title, msg, gtype):
    """ Send message to Mountain Lion's Notification Center """
    tool = ncenter_path()
    if tool:
        try:
            command = [tool, '-title', title, '-message', msg, '-group', Tx(NOTIFICATION.get(gtype, 'other'))]
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
            output = proc.stdout.read()
            proc.wait()
            if 'Notification delivered' in output or 'Removing previously' in output:
                output = ''
        except:
            logging.info('Cannot run notifier "%s"', tool)
            logging.debug("Traceback: ", exc_info=True)
            output = 'Notifier tool crashed'
    else:
        output = 'Notifier app not found'
    return output.strip('*\n ')


def hostname(host=True):
    """ Return host's pretty name """
    if sabnzbd.WIN32:
        sys_name = os.environ.get('computername', 'unknown')
    else:
        try:
            sys_name = os.uname()[1]
        except:
            sys_name = 'unknown'
    if host:
        return '@%s' % sys_name.lower()
    else:
        return ''


def send_prowl(title, msg, gtype, force=False, test=None):
    """ Send message to Prowl """

    if test:
        apikey = test.get('prowl_apikey')
    else:
        apikey = sabnzbd.cfg.prowl_apikey()
    if not apikey:
        return T('Cannot send, missing required data')

    title = Tx(NOTIFICATION.get(gtype, 'other'))
    title = urllib2.quote(title.encode('utf8'))
    msg = urllib2.quote(msg.encode('utf8'))
    prio = get_prio(gtype, 'prowl')

    if force:
        prio = 0

    if prio > -3:
        url = 'https://api.prowlapp.com/publicapi/add?apikey=%s&application=SABnzbd' \
              '&event=%s&description=%s&priority=%d' % (apikey, title, msg, prio)
        try:
            urllib2.urlopen(url)
            return ''
        except:
            logging.warning(T('Failed to send Prowl message'))
            logging.info("Traceback: ", exc_info=True)
            return T('Failed to send Prowl message')
    return ''


def send_pushover(title, msg, gtype, force=False, test=None):
    """ Send message to pushover """

    if test:
        apikey = test.get('pushover_token')
        userkey = test.get('pushover_userkey')
        device = test.get('pushover_device')
    else:
        apikey = sabnzbd.cfg.pushover_token()
        userkey = sabnzbd.cfg.pushover_userkey()
        device = sabnzbd.cfg.pushover_device()
        emergency_retry = sabnzbd.cfg.pushover_emergency_retry()
        emergency_expire = sabnzbd.cfg.pushover_emergency_expire()
    if not apikey or not userkey:
        return T('Cannot send, missing required data')

    title = Tx(NOTIFICATION.get(gtype, 'other'))
    prio = get_prio(gtype, 'pushover')

    if force:
        prio = 1

    if prio == 2:
        body = { "token": apikey,
                 "user": userkey,
                 "device": device,
                 "title": title,
                 "message": msg,
                 "priority": prio,
                 "retry": emergency_retry,
                 "expire": emergency_expire
        }
        return do_send_pushover(body)
    if -3 < prio < 2:
        body = { "token": apikey,
                 "user": userkey,
                 "device": device,
                 "title": title,
                 "message": msg,
                 "priority": prio,
        }
        return do_send_pushover(body)

def do_send_pushover(body):
    try:
        conn = httplib.HTTPSConnection("api.pushover.net:443")
        conn.request("POST", "/1/messages.json", urllib.urlencode(body),
                     {"Content-type": "application/x-www-form-urlencoded"})
        res = conn.getresponse()
        if res.status != 200:
            logging.error(T('Bad response from Pushover (%s): %s'), res.status, res.read())
            return T('Failed to send pushover message')
        else:
            return ''
    except:
        logging.warning(T('Failed to send pushover message'))
        logging.info("Traceback: ", exc_info=True)
        return T('Failed to send pushover message')

def send_pushbullet(title, msg, gtype, force=False, test=None):
    """ Send message to Pushbullet """

    if test:
        apikey = test.get('pushbullet_apikey')
        device = test.get('pushbullet_device')
    else:
        apikey = sabnzbd.cfg.pushbullet_apikey()
        device = sabnzbd.cfg.pushbullet_device()
    if not apikey:
        return T('Cannot send, missing required data')

    title = u'SABnzbd: ' + Tx(NOTIFICATION.get(gtype, 'other'))

    try:
        conn = httplib.HTTPSConnection('api.pushbullet.com:443')
        conn.request('POST', '/v2/pushes',
            json.dumps({
                'type': 'note',
                'device': device,
                'title': title,
                'body': msg}),
            headers={'Authorization': 'Bearer ' + apikey,
                     'Content-type': 'application/json'})
        res = conn.getresponse()
        if res.status != 200:
            logging.error(T('Bad response from Pushbullet (%s): %s'), res.status, res.read())
        else:
            logging.info('Successfully sent to Pushbullet')

    except:
        logging.warning(T('Failed to send pushbullet message'))
        logging.info('Traceback: ', exc_info=True)
        return T('Failed to send pushbullet message')
    return ''


def send_nscript(title, msg, gtype, force=False, test=None):
    """ Run user's notification script """
    if test:
        script = test.get('nscript_script')
        parameters = test.get('nscript_parameters')
    else:
        script = sabnzbd.cfg.nscript_script()
        parameters = sabnzbd.cfg.nscript_parameters()
    if not script:
        return T('Cannot send, missing required data')
    title = u'SABnzbd: ' + Tx(NOTIFICATION.get(gtype, 'other'))

    if force or check_classes(gtype, 'nscript'):
        script_path = make_script_path(script)
        if script_path:
            # retry calling the script up to 5 times
            for i in range(5):
                output, ret = external_script(script_path, gtype, title, msg, parameters)
                if ret:
                    continue
                else:
                    break
            if ret:
                logging.error(T('Script returned exit code %s and output "%s"') % (ret, output))
                return T('Script returned exit code %s and output "%s"') % (ret, output)
            else:
                logging.info('Successfully executed notification script ' + script_path)
        else:
            return T('Notification script "%s" does not exist') % script_path
    return ''


def send_windows(title, msg, gtype):
    if sabnzbd.WINTRAY and not sabnzbd.WINTRAY.terminate:
        try:
            sabnzbd.WINTRAY.sendnotification(title, msg)
        except:
            logging.info(T('Failed to send Windows notification'))
            logging.debug("Traceback: ", exc_info=True)
            return T('Failed to send Windows notification')
    return None

