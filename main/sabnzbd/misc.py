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
sabnzbd.misc - misc classes
"""

import os
import sys
import logging
import urllib
import re
import webbrowser
import tempfile
import shutil
import threading
import subprocess
import socket
import time

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import *
import sabnzbd.nzbqueue
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.lang import T, Ta

if sabnzbd.FOUNDATION:
    import Foundation

RE_VERSION = re.compile('(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_UNITS = re.compile('(\d+\.*\d*)\s*([KMGTP]*)', re.I)
TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')

PANIC_NONE  = 0
PANIC_PORT  = 1
PANIC_TEMPL = 2
PANIC_QUEUE = 3
PANIC_FWALL = 4
PANIC_OTHER = 5
PANIC_XPORT = 6

def safe_lower(txt):
    if txt:
        return txt.lower()
    else:
        return ''


def cat_to_opts(cat, pp=None, script=None, priority=None):
    """
        Derive options from category, if option not already defined.
        Specified options have priority over category-options
    """
    if pp is None:
        try:
            pp = config.get_categories()[safe_lower(cat)].pp.get()
            # Get the default pp
            if pp == '':
                pp = cfg.DIRSCAN_PP.get()
            logging.debug('Job gets options %s', pp)
        except KeyError:
            pp = cfg.DIRSCAN_PP.get()

    if not script:
        try:
            script = config.get_categories()[safe_lower(cat)].script.get()
            # Get the default script
            if script == '' or safe_lower(script) == 'default':
                script = cfg.DIRSCAN_SCRIPT.get()
            logging.debug('Job gets script %s', script)
        except KeyError:
            script = cfg.DIRSCAN_SCRIPT.get()

    if priority is None or priority == DEFAULT_PRIORITY:
        try:
            priority = config.get_categories()[safe_lower(cat)].priority.get()
            # Get the default priority
            if priority == DEFAULT_PRIORITY:
                priority = cfg.DIRSCAN_PRIORITY.get()
            logging.debug('Job gets priority %s', script)
        except KeyError:
            priority = cfg.DIRSCAN_PRIORITY.get()

    return cat, pp, script, priority

################################################################################
# sanitize_filename                                                            #
################################################################################
if sabnzbd.WIN32:
    CH_ILLEGAL = r'\/<>?*:|"'
    CH_LEGAL   = r'++{}!@-#`'
else:
    CH_ILLEGAL = r'/'
    CH_LEGAL   = r'+'

def sanitize_filename(name):
    """ Return filename with illegal chars converted to legal ones
        and with the par2 extension always in lowercase
    """
    illegal = CH_ILLEGAL
    legal   = CH_LEGAL

    lst = []
    for ch in name.strip():
        if ch in illegal:
            ch = legal[illegal.find(ch)]
        lst.append(ch)
    name = ''.join(lst)

    if not name:
        name = 'unknown'

    name, ext = os.path.splitext(name)
    lowext = ext.lower()
    if lowext == '.par2' and lowext != ext:
        ext = lowext
    return name + ext


def sanitize_foldername(name):
    """ Return foldername with dodgy chars converted to safe ones
        Remove any leading and trailing dot and space characters
    """
    illegal = r'\/<>?*:|"'
    legal   = r'++{}!@-#`'

    repl = cfg.REPLACE_ILLEGAL.get()
    lst = []
    for ch in name.strip():
        if ch in illegal:
            if repl:
                ch = legal[illegal.find(ch)]
                lst.append(ch)
        else:
            lst.append(ch)
    name = ''.join(lst)

    name = name.strip('. ')
    if not name:
        name = 'unknown'

    return name


################################################################################
# DirPermissions                                                               #
################################################################################
def create_all_dirs(path, umask=False):
    """ Create all required path elements and set umask on all
        Return True if last elelent could be made or exists """
    result = True
    if sabnzbd.WIN32:
        try:
            os.makedirs(path)
        except:
            result = False
    else:
        list = []
        list.extend(path.split('/'))
        path = ''
        for d in list:
            if d:
                path += '/' + d
                if not os.path.exists(path):
                    try:
                        os.mkdir(path)
                        result = True
                    except:
                        result = False
                    if umask:
                        mask = cfg.UMASK.get()
                        if mask:
                            try:
                                os.chmod(path, int(mask, 8) | 0700)
                            except:
                                pass
    return result

################################################################################
# Real_Path                                                                    #
################################################################################
def real_path(loc, path):
    if not ((sabnzbd.WIN32 and len(path)>1 and path[0].isalpha() and path[1] == ':') or \
            (path and (path[0] == '/' or path[0] == '\\'))
           ):
        path = loc + '/' + path
    return os.path.normpath(os.path.abspath(path))


################################################################################
# Create_Real_Path                                                             #
################################################################################
def create_real_path(name, loc, path, umask=False):
    if path:
        my_dir = real_path(loc, path)
        if not os.path.exists(my_dir):
            logging.info('%s directory: %s does not exist, try to create it', name, my_dir)
            if not create_all_dirs(my_dir, umask):
                logging.error(Ta('error-createDir@1'), my_dir)
                return (False, my_dir)

        if os.access(my_dir, os.R_OK + os.W_OK):
            return (True, my_dir)
        else:
            logging.error(Ta('error-accessDir@2'), name, my_dir)
            return (False, my_dir)
    else:
        return (False, "")

################################################################################
# get_user_shellfolders
#
# Return a dictionary with Windows Special Folders
# Read info from the registry
################################################################################

def get_user_shellfolders():
    import _winreg
    values = {}

    # Open registry hive
    try:
        hive = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    except WindowsError:
        logging.error(Ta('error-regConnect'))
        return values

    # Then open the registry key where Windows stores the Shell Folder locations
    try:
        key = _winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
    except WindowsError:
        logging.error(Ta('error-regOpen@1'), r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
        _winreg.CloseKey(hive)
        return values

    try:
        for i in range(0, _winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, i)
            try:
                values[name] = value.encode('latin-1')
            except UnicodeDecodeError:
                try:
                    # If the path name cannot be converted to latin-1 (contains high ASCII value strings)
                    # then try and use the short name
                    import win32api
                    # Need to make sure the path actually exists, otherwise ignore
                    if os.path.exists(value):
                        values[name] = win32api.GetShortPathName(value)
                except:
                    # probably a pywintypes.error error such as folder does not exist
                    logging.error("Traceback: ", exc_info = True)
            i += 1
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return values
    except WindowsError:
        # On error, return empty dict.
        logging.error(Ta('error-regSpecial'))
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return {}


#------------------------------------------------------------------------------
def windows_variant():
    """ Determine Windows variant
        Return platform, vista_plus, x64
    """
    from win32api import GetVersionEx
    from win32con import VER_PLATFORM_WIN32_NT
    import _winreg

    vista_plus = x64 = False
    maj, min, buildno, plat, csd = GetVersionEx()

    if plat == VER_PLATFORM_WIN32_NT:
        vista_plus = maj > 5
        if vista_plus:
            # Must be done the hard way, because the Python runtime lies to us.
            # This does *not* work:
            #     return os.environ['PROCESSOR_ARCHITECTURE'] == 'AMD64'
            # because the Python runtime returns 'X86' even on an x64 system!
            key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
            for n in xrange(_winreg.QueryInfoKey(key)[1]):
                name, value, val_type = _winreg.EnumValue(key, n)
                if name == 'PROCESSOR_ARCHITECTURE':
                    x64 = value.upper() == u'AMD64'
                    break
            _winreg.CloseKey(key)

    return vista_plus, x64


################################################################################
# Launch a browser for various purposes
# including panic messages
#
################################################################################
MSG_BAD_NEWS = r'''
    <html>
    <head>
    <title>Problem with %s %s</title>
    </head>
    <body>
    <h1><font color="#0000FF">Welcome to %s %s</font></h1>
    <p align="center">&nbsp;</p>
    <p align="center"><font size="5">
    <blockquote>
        %s
    </blockquote>
    <br>Program did not start!<br>
    </body>
</html>
'''

MSG_BAD_FWALL = r'''
    SABnzbd is not compatible with some software firewalls.<br>
    %s<br>
    Sorry, but we cannot solve this incompatibility right now.<br>
    Please file a complaint at your firewall supplier.<br>
    <br>
'''

MSG_BAD_PORT = r'''
    SABnzbd needs a free tcp/ip port for its internal web server.<br>
    Port %s on %s was tried , but it is not available.<br>
    Some other software uses the port or SABnzbd is already running.<br>
    <br>
    Please restart SABnzbd with a different port number.<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>
    If you get this error message again, please try a different number.<br>
'''

MSG_ILL_PORT = r'''
    SABnzbd needs a free tcp/ip port for its internal web server.<br>
    Port %s on %s was tried , but the account SABnzbd has no permission to use it.<br>
    On Linux systems, normal users must use ports above 1023.<br>
    <br>
    Please restart SABnzbd with a different port number.<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>
    If you get this error message again, please try a different number.<br>
'''

MSG_BAD_QUEUE = r'''
    SABnzbd detected saved data from an other SABnzbd version<br>
    but cannot re-use the data of the other program.<br><br>
    You may want to finish your queue first with the other program.<br><br>
    After that, start this program with the "--clean" option.<br>
    This will erase the current queue and history!<br>
    SABnzbd read the file "%s".<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --clean<br>
    <br>
'''

MSG_BAD_TEMPL = r'''
    SABnzbd cannot find its web interface files in %s.<br>
    Please install the program again.<br>
    <br>
'''

MSG_OTHER = r'''
    SABnzbd detected a fatal error:<br>
    %s<br><br>
    %s<br>
'''

def panic_message(panic, a=None, b=None):
    """Create the panic message from templates
    """
    if (not cfg.AUTOBROWSER.get()) or sabnzbd.DAEMON:
        return

    if sabnzbd.WIN32:
        os_str = 'Press Startkey+R and type the line (example):'
        prog_path = '"%s"' % sabnzbd.MY_FULLNAME
    else:
        os_str = 'Open a Terminal window and type the line (example):'
        prog_path = sabnzbd.MY_FULLNAME

    if panic == PANIC_PORT:
        newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_BAD_PORT % (b, a, os_str, prog_path, a, newport)
    elif panic == PANIC_XPORT:
        if int(b) < 1023:
            newport = 1024
        else:
            newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_ILL_PORT % (b, a, os_str, prog_path, a, newport)
    elif panic == PANIC_TEMPL:
        msg = MSG_BAD_TEMPL % a
    elif panic == PANIC_QUEUE:
        msg = MSG_BAD_QUEUE % (a, os_str, prog_path)
    elif panic == PANIC_FWALL:
        if a:
            msg = MSG_BAD_FWALL % "It is likely that you are using ZoneAlarm on Vista.<br>"
        else:
            msg = MSG_BAD_FWALL % "<br>"
    else:
        msg = MSG_OTHER % (a, b)


    msg = MSG_BAD_NEWS % (sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_NAME, sabnzbd.__version__, msg)

    msgfile, url = tempfile.mkstemp(suffix='.html')
    os.write(msgfile, msg)
    os.close(msgfile)
    return url


def panic_fwall(vista):
    launch_a_browser(panic_message(PANIC_FWALL, vista))

def panic_port(host, port):
    launch_a_browser(panic_message(PANIC_PORT, host, port))

def panic_xport(host, port):
    launch_a_browser(panic_message(PANIC_XPORT, host, port))
    logging.error(Ta('error-portNoAccess@1'), port)

def panic_queue(name):
    launch_a_browser(panic_message(PANIC_QUEUE, name, 0))

def panic_tmpl(name):
    launch_a_browser(panic_message(PANIC_TEMPL, name, 0))

def panic(reason, remedy=""):
    print "\nFatal error:\n  %s\n%s" % (reason, remedy)
    launch_a_browser(panic_message(PANIC_OTHER, reason, remedy))


def launch_a_browser(url, force=False):
    """Launch a browser pointing to the URL
    """
    if not force and not cfg.AUTOBROWSER.get() or sabnzbd.DAEMON:
        return

    logging.info("Lauching browser with %s", url)
    try:
        webbrowser.open(url, 2, 1)
    except:
        # Python 2.4 does not support parameter new=2
        try:
            webbrowser.open(url, 1, 1)
        except:
            logging.warning(Ta('warn-noBrowser'))
            logging.debug("Traceback: ", exc_info = True)


def error_page_401(status, message, traceback, version):
    """ Custom handler for 401 error """
    return r'''
<html>
    <head>
    <title>Access denied</title>
    </head>
    <body>
    <br/><br/>
    <font color="#0000FF">Error %s: You need to provide a valid username and password.</font>
    </body>
</html>
''' % status



################################################################################
# Check latest version
#
# Perform an online version check
# Syntax of online version file:
#     <current-final-release>
#     <url-of-current-final-release>
#     <latest-alpha/beta-or-rc>
#     <url-of-latest-alpha/beta/rc-release>
# The latter two lines are only present when a alpha/beta/rc is available.
# Formula for the version numbers (line 1 and 3).
# - <major>.<minor>.<bugfix>[rc|beta|alpha]<cand>
#
# The <cand> value for a final version is assumned to be 99.
# The <cand> value for the beta/rc version is 1..98, with RC getting
# a boost of 80 and Beta of 40.
# This is done to signal alpha/beta/rc users of availability of the final
# version (which is implicitly 99).
# People will only be informed to upgrade to a higher alpha/beta/rc version, if
# they are already using an alpha/beta/rc.
# RC's are valued higher than Beta's, which are valued higher than Alpha's.
#
################################################################################

def convert_version(text):
    """ Convert version string to numerical value and a testversion indicator """
    version = 0
    test = True
    m = RE_VERSION.search(text)
    if m:
        version = int(m.group(1))*1000000 + int(m.group(2))*10000 + int(m.group(3))*100
        try:
            if m.group(4).lower() == 'rc':
                version = version + 80
            elif m.group(4).lower() == 'beta':
                version = version + 40
            version = version + int(m.group(5))
        except:
            version = version + 99
            test = False
    return version, test


def check_latest_version():
    """ Do an online check for the latest version """
    if not cfg.VERSION_CHECK.get():
        return

    current, testver = convert_version(sabnzbd.__version__)
    if not current:
        logging.debug("Unsupported release number (%s), will not check", sabnzbd.__version__)
        return

    try:
        fn = urllib.urlretrieve('http://sabnzbdplus.sourceforge.net/version/latest')[0]
        f = open(fn, 'r')
        data = f.read()
        f.close()
    except:
        return

    try:
        latest_label = data.split()[0]
    except:
        latest_label = ''
    try:
        url = data.split()[1]
    except:
        url = ''
    try:
        latest_testlabel = data.split()[2]
    except:
        latest_testlabel = ''
    try:
        url_beta = data.split()[3]
    except:
        url_beta = url


    latest, dummy = convert_version(latest_label)
    latest_test, dummy = convert_version(latest_testlabel)

    logging.debug("Checked for a new release, cur= %s, latest= %s (on %s)", current, latest, url)

    if testver and current < latest:
        sabnzbd.NEW_VERSION = "%s;%s" % (latest_label, url)
    elif current < latest:
        sabnzbd.NEW_VERSION = "%s;%s" % (latest_label, url)
    elif testver and current < latest_test:
        sabnzbd.NEW_VERSION = "%s;%s" % (latest_testlabel, url_beta)


def from_units(val):
    """ Convert K/M/G/T/P notation to float
    """
    val = str(val).strip().upper()
    if val == "-1":
        return val
    m = RE_UNITS.search(val)
    if m:
        if m.group(2):
            val = float(m.group(1))
            unit = m.group(2)
            n = 0
            while unit != TAB_UNITS[n]:
                val = val * 1024.0
                n = n+1
        else:
            val = m.group(1)
        try:
            return float(val)
        except:
            return 0.0
    else:
        return 0.0

def to_units(val, spaces=0):
    """ Convert number to K/M/G/T/P notation
        Add "spaces" if not ending in letter
    """
    val = str(val).strip()
    if val == "-1":
        return val
    n= 0
    try:
        val = float(val)
    except:
        return ''
    while (val > 1023.0) and (n < 5):
        val = val / 1024.0
        n= n+1
    unit = TAB_UNITS[n]
    if unit:
        return "%.2f %s" % (val, unit)
    else:
        return "%.0f%s" % (val, ' '*spaces)

#------------------------------------------------------------------------------
def same_file(a, b):
    """ Return True if both paths are identical """

    if "samefile" in os.path.__dict__:
        try:
            return os.path.samefile(a, b)
        except:
            return False
    else:
        try:
            a = os.path.normpath(os.path.abspath(a)).lower()
            b = os.path.normpath(os.path.abspath(b)).lower()
            return a == b
        except:
            return False

#------------------------------------------------------------------------------
def exit_sab(value):
    sys.stderr.flush()
    sys.stdout.flush()
    sys.exit(value)


#------------------------------------------------------------------------------
def notify(notificationName, message):
    """ Send a notification to the OS (OSX-only) """
    if sabnzbd.FOUNDATION:
        pool = Foundation.NSAutoreleasePool.alloc().init()
        nc = Foundation.NSDistributedNotificationCenter.defaultCenter()
        nc.postNotificationName_object_(notificationName, message)
        del pool


#------------------------------------------------------------------------------
def split_host(srv):
    """ Split host:port notation, allowing for IPV6 """
    # Cannot use split, because IPV6 of "a:b:c:port" notation
    # Split on the last ':'
    mark = srv.rfind(':')
    if mark < 0:
        host = srv
    else:
        host = srv[0 : mark]
        port = srv[mark+1 :]
    try:
        port = int(port)
    except:
        port = None
    return (host, port)


#------------------------------------------------------------------------------
# Locked directory operations

DIR_LOCK = threading.RLock()

@synchronized(DIR_LOCK)
def get_unique_path(dirpath, n=0, create_dir=True):
    """ Determine a unique folder or filename """
    path = dirpath
    if n: path = "%s.%s" % (dirpath, n)

    if not os.path.exists(path):
        if create_dir: create_dirs(path)
        return path
    else:
        return get_unique_path(dirpath, n=n+1, create_dir=create_dir)

@synchronized(DIR_LOCK)
def get_unique_filename(path, new_path, i=1):
    #path = existing path of the file, new_path = destination
    if os.path.exists(new_path):
        p, fn = os.path.split(path)
        name, ext = os.path.splitext(fn)
        uniq_name = "%s.%s%s" % (name,i,ext)
        uniq_path = new_path.replace(fn,uniq_name)
        if os.path.exists(uniq_path):
            path, uniq_path = get_unique_filename(path, new_path, i=i+1)
        else:
            try:
                os.rename(path, uniq_path)
                path = path.replace(fn, uniq_name)
            except:
                return path, new_path
        return path, uniq_path

    else:
        return path, new_path


@synchronized(DIR_LOCK)
def create_dirs(dirpath):
    """ Create directory tree, obeying permissions """
    if not os.path.exists(dirpath):
        logging.info('Creating directories: %s', dirpath)
        if not create_all_dirs(dirpath, True):
            logging.error(Ta('error-makeFile@1'), dirpath)
            logging.debug("Traceback: ", exc_info = True)
            return None
    return dirpath


@synchronized(DIR_LOCK)
def move_to_path(path, new_path, unique=True):
    """ Move a file to a new path, optionally give unique filename """
    if unique:
        new_path = get_unique_path(new_path, create_dir=False)
    if new_path:
        logging.debug("Moving. Old path:%s new path:%s unique?:%s",
                                                  path,new_path, unique)
        try:
            # First try cheap rename
            os.rename(path, new_path)
        except:
            # Cannot rename, try copying
            try:
                if not os.path.exists(os.path.dirname(new_path)):
                    create_dirs(os.path.dirname(new_path))
                shutil.copyfile(path, new_path)
                os.remove(path)
            except:
                logging.error(Ta('error-moveFile@2'), path, new_path)
                logging.debug("Traceback: ", exc_info = True)
    return new_path


@synchronized(DIR_LOCK)
def cleanup_empty_directories(path):
    path = os.path.normpath(path)
    while 1:
        repeat = False
        for root, dirs, files in os.walk(path, topdown=False):
            if not dirs and not files and root != path:
                try:
                    os.rmdir(root)
                    repeat = True
                except:
                    pass
        if not repeat:
            break


@synchronized(DIR_LOCK)
def get_filepath(path, nzo, filename):
    """ Create unique filepath """
    # This procedure is only used by the Assembler thread
    # It does no umask setting
    # It uses the dir_lock for the (rare) case that the
    # download_dir is equal to the complete_dir.
    dirname = nzo.get_dirname()
    created = nzo.get_dirname_created()

    dName = dirname
    if not created:
        for n in xrange(200):
            dName = dirname
            if n: dName += '.' + str(n)
            try:
                os.mkdir(os.path.join(path, dName))
                break
            except:
                pass
        nzo.set_dirname(dName, created = True)

    fPath = os.path.join(os.path.join(path, dName), filename)
    n = 0
    while True:
        fullPath = fPath
        if n: fullPath += '.' + str(n)
        if os.path.exists(fullPath):
            n = n + 1
        else:
            break

    return fullPath


def bad_fetch(nzo, url, retry=False, archive=False):
    """ Create History entry for failed URL Fetch """
    logging.error(Ta('error-urlGet@1'), url)

    pp = nzo.get_pp()
    if pp:
        pp = '&pp=%s' % urllib.quote(pp)
    else:
        pp = ''
    cat = nzo.get_cat()
    if cat:
        cat = '&cat=%s' % urllib.quote(cat)
    else:
        cat = ''
    script = nzo.get_script()
    if script:
        script = '&script=%s' % urllib.quote(script)
    else:
        script = ''

    nzo.set_status('Failed')


    if url:
        nzo.set_filename(url)
        nzo.set_original_dirname(url)

    if retry:
        nzbname = nzo.get_dirname_rename()
        if nzbname:
            nzbname = '&nzbname=%s' % urllib.quote(nzbname)
        text = T('his-retryURL1')+', <a href="./retry?session=%s&url=%s%s%s%s%s">' + T('his-retryURL2') + '</a>'
        parms = (cfg.API_KEY.get(), urllib.quote(url), pp, cat, script, nzbname)
        nzo.set_fail_msg(text % parms)
    else:
        if archive:
            msg = T('his-badArchive')
        elif not '://' in url:
            msg = T('his-cannotGetReport')
        else:
            msg = T('his-failedURL')
        nzo.set_fail_msg(msg)

    sabnzbd.nzbqueue.remove_nzo(nzo.nzo_id, add_to_history=True, unload=True)


def on_cleanup_list(filename, skip_nzb=False):
    """ Return True if a filename matches the clean-up list """

    if cfg.CLEANUP_LIST.get():
        ext = os.path.splitext(filename)[1].strip().strip('.')
        if sabnzbd.WIN32: ext = ext.lower()

        for k in cfg.CLEANUP_LIST.get():
            item = k.strip().strip('.')
            if item == ext and not (skip_nzb and item == 'nzb'):
                return True
    return False

def get_ext(filename):
    try:
        return os.path.splitext(filename)[1].lower()
    except:
        return ''

def get_filename(path):
    try:
        return os.path.split(path)[1]
    except:
        return ''

def loadavg():
    """ Return 1, 5 and 15 minute load average of host or "" if not supported
    """
    if sabnzbd.WIN32 or sabnzbd.DARWIN:
        return ""
    try:
        loadavgstr = open('/proc/loadavg', 'r').readline().strip()
    except:
        return ""

    data = loadavgstr.split()
    try:
        a1, a5, a15 = map(float, data[:3])
        return "%.2f, %.2f, %.2f" % (a1, a5, a15)
    except:
        return ""


def format_time_string(seconds, days=0):
    """ Return a formatted and translated time string """
    seconds = IntConv(seconds)
    completestr = []
    if days:
        completestr.append('%s %s' % (days, s_returner('day', days)))
    if (seconds/3600) >= 1:
        completestr.append('%s %s' % (seconds/3600, s_returner('hour', (seconds/3600))))
        seconds -= (seconds/3600)*3600
    if (seconds/60) >= 1:
        completestr.append('%s %s' % (seconds/60, s_returner('minute',(seconds/60))))
        seconds -= (seconds/60)*60
    if seconds > 0:
        completestr.append('%s %s' % (seconds, s_returner('second', seconds)))
    elif not completestr:
        completestr.append('0 %s' % s_returner('second', 0))

    p = ' '.join(completestr)
    if isinstance(p, unicode):
        return p.encode('latin-1')
    else:
        return p

def s_returner(item, value):
    if value == 1:
        return T(item)
    else:
        return T(item + 's')

def IntConv(value):
    """Safe conversion to int"""
    try:
        value = int(value)
    except:
        value = 0
    return value


#------------------------------------------------------------------------------
# Diskfree
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
            available, disk_size, total_free = win32api.GetDiskFreeSpaceEx(_dir)
            return available / GIGI
        except:
            return 0.0
    def disktotal(_dir):
        try:
            available, disk_size, total_free = win32api.GetDiskFreeSpaceEx(_dir)
            return disk_size / GIGI
        except:
            return 0.0


def create_https_certificates(ssl_cert, ssl_key):
    try:
        from OpenSSL import crypto
        from sabnzbd.utils.certgen import createKeyPair, createCertRequest, createCertificate,\
             TYPE_RSA, serial
    except:
        logging.warning(Ta('warn-pyopenssl'))
        return False

    # Create the CA Certificate
    cakey = createKeyPair(TYPE_RSA, 1024)
    careq = createCertRequest(cakey, CN='Certificate Authority')
    cacert = createCertificate(careq, (careq, cakey), serial, (0, 60*60*24*365*10)) # ten years

    fname = 'server'
    cname = 'SABnzbd'
    pkey = createKeyPair(TYPE_RSA, 1024)
    req = createCertRequest(pkey, CN=cname)
    cert = createCertificate(req, (cacert, cakey), serial, (0, 60*60*24*365*10)) # ten years

    # Save the key and certificate to disk
    try:
        open(ssl_key, 'w').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
        open(ssl_cert, 'w').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    except:
        logging.error(Ta('error-sslFiles'))
        logging.debug("Traceback: ", exc_info = True)
        return False

    return True


def find_on_path(targets):
    """ Search the PATH for a program and return full path """
    if sabnzbd.WIN32:
        paths = os.getenv('PATH').split(';')
    else:
        paths = os.getenv('PATH').split(':')

    if isinstance(targets, basestring):
        targets = ( targets, )

    for path in paths:
        for target in targets:
            target_path = os.path.abspath(os.path.join(path, target))
            if os.access(target_path, os.X_OK):
                return target_path
    return None


#------------------------------------------------------------------------------
_RE_IP4 = re.compile(r'inet\s+(addr:\s*){0,1}(\d+\.\d+\.\d+\.\d+)')
_RE_IP6 = re.compile(r'inet6\s+(addr:\s*){0,1}([0-9a-f:]+)', re.I)

def ip_extract():
    """ Return list of IP addresses of this system """
    ips = []
    program = find_on_path('ip')
    if program:
        program = [program, 'a']
    else:
        program = find_on_path('ifconfig')
        if program: program = [program]

    if sabnzbd.WIN32 or not program:
        try:
            info = socket.getaddrinfo(socket.gethostname(), None)
        except:
            # Hostname does not resolve, use localhost
            info = socket.getaddrinfo('localhost', None)
        for item in info:
            ips.append(item[4][0])
    else:
        p = subprocess.Popen(program, shell=False, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             startupinfo=None, creationflags=0)
        output = p.stdout.read()
        ret = p.wait()
        for line in output.split('\n'):
            m = _RE_IP4.search(line)
            if not (m and m.group(2)):
                m = _RE_IP6.search(line)
            if m and m.group(2):
                ips.append(m.group(2))
    return ips


#------------------------------------------------------------------------------
# Power management for Windows

def win_hibernate():
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Hibernate")
        time.sleep(10)
    except:
        logging.error(Ta('error-hibernate'))
        logging.debug("Traceback: ", exc_info = True)


def win_standby():
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Standby")
        time.sleep(10)
    except:
        logging.error(Ta('error-standby'))
        logging.debug("Traceback: ", exc_info = True)


def win_shutdown():
    try:
        import win32security
        import win32api
        import ntsecuritycon

        flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES | ntsecuritycon.TOKEN_QUERY
        htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
        id = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_SHUTDOWN_NAME)
        newPrivileges = [(id, ntsecuritycon.SE_PRIVILEGE_ENABLED)]
        win32security.AdjustTokenPrivileges(htoken, 0, newPrivileges)
        win32api.InitiateSystemShutdown("", "", 30, 1, 0)
    finally:
        os._exit(0)


#------------------------------------------------------------------------------
# Power management for OSX

def osx_shutdown():
    try:
        subprocess.call(['osascript', '-e', 'tell app "System Events" to shut down'])
    except:
        logging.error(Ta('error-shutdown'))
        logging.debug("Traceback: ", exc_info = True)
    os._exit(0)


def osx_standby():
    try:
        subprocess.call(['osascript', '-e','tell app "System Events" to sleep'])
        time.sleep(10)
    except:
        logging.error(Ta('error-standby'))
        logging.debug("Traceback: ", exc_info = True)


def osx_hibernate():
    osx_standby()


#------------------------------------------------------------------------------
# Power management for linux.
#
#    Requires DBus plus either HAL [1] or the more modern ConsoleKit [2] and
#    DeviceKit(-power) [3]. HAL will eventually be deprecated but older systems
#    might still use it.
#    [1] http://people.freedesktop.org/~hughsient/temp/dbus-interface.html
#    [2] http://www.freedesktop.org/software/ConsoleKit/doc/ConsoleKit.html
#    [3] http://hal.freedesktop.org/docs/DeviceKit-power/
#
#    Original code was contributed by Marcel de Vries <marceldevries@phannet.cc>
#

try:
    import dbus
    HAVE_DBUS = True
except ImportError:
    HAVE_DBUS = False


def _get_sessionproxy():
    name = 'org.freedesktop.PowerManagement'
    path = '/org/freedesktop/PowerManagement'
    interface = 'org.freedesktop.PowerManagement'
    try:
        bus = dbus.SessionBus()
        return bus.get_object(name, path), interface
    except dbus.exceptions.DBusException:
        return None, None

def _get_systemproxy(method):
    if method == 'ConsoleKit':
        name = 'org.freedesktop.ConsoleKit'
        path = '/org/freedesktop/ConsoleKit/Manager'
        interface = 'org.freedesktop.ConsoleKit.Manager'
        pinterface = None
    elif method == 'DeviceKit':
        name = 'org.freedesktop.DeviceKit.Power'
        path = '/org/freedesktop/DeviceKit/Power'
        interface = 'org.freedesktop.DeviceKit.Power'
        pinterface = 'org.freedesktop.DBus.Properties'
    try:
        bus = dbus.SystemBus()
        return bus.get_object(name, path), interface, pinterface
    except dbus.exceptions.DBusException:
        return None, None, None


def linux_shutdown():
    if not HAVE_DBUS: os._exit(0)

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanShutdown():
            proxy.Shutdown(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('ConsoleKit')
        if proxy and proxy.CanStop(dbus_interface=interface):
            proxy.Stop(dbus_interface=interface)
    os._exit(0)


def linux_hibernate():
    if not HAVE_DBUS: return

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanHibernate():
            proxy.Hibernate(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('DeviceKit')
        if proxy and proxy.Get(interface, 'can-hibernate', dbus_interface=pinterface):
            proxy.Hibernate(dbus_interface=interface)
    time.sleep(10)


def linux_standby():
    if not HAVE_DBUS: return

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanSuspend():
            proxy.Suspend(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('DeviceKit')
        if proxy.Get(interface, 'can-suspend', dbus_interface=pinterface):
            proxy.Suspend(dbus_interface=interface)
    time.sleep(10)
