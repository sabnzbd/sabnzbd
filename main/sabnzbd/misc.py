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

try:
    # Try to import OSX library
    import Foundation
    HAVE_FOUNDATION = True
except:
    HAVE_FOUNDATION = False


import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import *
import nzbqueue
import sabnzbd.config as config
import sabnzbd.cfg as cfg

RE_VERSION = re.compile('(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_UNITS = re.compile('(\d+\.*\d*)\s*([KMGTP]*)', re.I)
TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')
RE_CAT = re.compile(r'^{{(\w+)}}(.+)') # Category prefix

PANIC_NONE  = 0
PANIC_PORT  = 1
PANIC_TEMPL = 2
PANIC_QUEUE = 3
PANIC_FWALL = 4
PANIC_OTHER = 5
PANIC_XPORT = 6

def Lower(txt):
    if txt:
        return txt.lower()
    else:
        return ''


def Cat2Opts(cat, pp, script):
    """
        Derive options from category, if option not already defined.
        Specified options have priority over category-options
    """
    if not pp:
        try:
            pp = config.get_categories()[Lower(cat)].pp.get()
            logging.debug('Job gets options %s', pp)
        except KeyError:
            pp = cfg.DIRSCAN_PP.get()

    if not script:
        try:
            script = config.get_categories()[Lower(cat)].script.get()
            logging.debug('Job gets script %s', script)
        except KeyError:
            script = cfg.DIRSCAN_SCRIPT.get()

    return cat, pp, script


def Cat2OptsDef(fname, cat=None):
    """
        Get options associated with the category.
        Category options have priority over default options.
    """
    pp = cfg.DIRSCAN_PP.get()
    script = cfg.DIRSCAN_SCRIPT.get()
    name = fname

    if cat == None:
        m = RE_CAT.search(fname)
        if m and m.group(1) and m.group(2):
            cat = m.group(1).lower()
            name = m.group(2)
            logging.debug('Job %s has category %s', name, cat)

    if cat:
        try:
            pp = config.get_categories()[cat.lower()].pp.get()
            logging.debug('Job %s gets options %s', name, pp)
        except:
            pass

        try:
            script = config.get_categories()[cat.lower()].script.get()
            logging.debug('Job %s gets script %s', name, script)
        except:
            pass

    return cat, name, pp, script




################################################################################
# sanitize_filename                                                            #
################################################################################
if os.name == 'nt':
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
        Remove any leading and trailing dot characters
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

    name = name.strip('.')
    if not name:
        name = 'unknown'

    return name


################################################################################
# DirPermissions                                                               #
################################################################################
def CreateAllDirs(path, umask=False):
    """ Create all required path elements and set umask on all
        Return True if last elelent could be made or exists """
    result = True
    if os.name == 'nt':
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
    if not ((os.name == 'nt' and len(path)>1 and path[0].isalpha() and path[1] == ':') or \
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
            if not CreateAllDirs(my_dir, umask):
                logging.error('Cannot create directory %s', my_dir)
                return (False, my_dir)

        if os.access(my_dir, os.R_OK + os.W_OK):
            return (True, my_dir)
        else:
            logging.error('%s directory: %s error accessing', name, my_dir)
            return (False, my_dir)
    else:
        return (False, "")

################################################################################
# Get_User_ShellFolders
#
# Return a dictionary with Windows Special Folders
# Read info from the registry
################################################################################

def Get_User_ShellFolders():
    import _winreg
    values = {}

    # Open registry hive
    try:
        hive = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    except WindowsError:
        logging.error("Cannot connect to registry hive HKEY_CURRENT_USER.")
        return values

    # Then open the registry key where Windows stores the Shell Folder locations
    try:
        key = _winreg.OpenKey(hive, "Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
    except WindowsError:
        logging.error("Cannot open registry key Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders.")
        _winreg.CloseKey(hive)
        return values

    try:
        for i in range(0, _winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, i)
            try:
                values[name] = value.encode('latin-1')
            except:
                try:
                    import win32api
                    values[name] = win32api.GetShortPathName(value)
                except:
                    del values[name]
            i += 1
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return values
    except WindowsError:
        # On error, return empty dict.
        logging.error("Failed to read registry keys for special folders")
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return {}


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

    if os.name == 'nt':
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


def Panic_FWall(vista):
    launch_a_browser(panic_message(PANIC_FWALL, vista))

def Panic_Port(host, port):
    launch_a_browser(panic_message(PANIC_PORT, host, port))

def Panic_XPort(host, port):
    launch_a_browser(panic_message(PANIC_XPORT, host, port))
    logging.error('You have no permisson to use port %s', port)

def Panic_Queue(name):
    launch_a_browser(panic_message(PANIC_QUEUE, name, 0))

def Panic_Templ(name):
    launch_a_browser(panic_message(PANIC_TEMPL, name, 0))

def Panic(reason, remedy=""):
    print "\nFatal error:\n  %s\n%s" % (reason, remedy)
    launch_a_browser(panic_message(PANIC_OTHER, reason, remedy))


def launch_a_browser(url):
    """Launch a browser pointing to the URL
    """
    if (not cfg.AUTOBROWSER.get()) or sabnzbd.DAEMON:
        return

    logging.info("Lauching browser with %s", url)
    try:
        webbrowser.open(url, 2, 1)
    except:
        # Python 2.4 does not support parameter new=2
        try:
            webbrowser.open(url, 1, 1)
        except:
            logging.warning("Cannot launch the browser, probably not found")
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
#     <latest-beta-or-rc>
#     <url-of-latest-beta/rc-release>
# The latter two lines are only present when a beta/rc is available.
# Formula for the version numbers (line 1 and 3).
# - <major>.<minor>.<bugfix>[rc|beta]<cand>
#
# The <cand> value for a final version is assumned to be 99.
# The <cand> value for the beta/rc version is 1..49, with RC getting
# a boost of 50.
# This is done to signal beta/rc users of availability of the final
# version (which is implicitly 99).
# People will only be informed to upgrade to a higher beta/rc version, if
# they are already using a beta/rc.
# RC's are valued higher than Beta's.
#
################################################################################

def ConvertVersion(text):
    """ Convert version string to numerical value and a testversion indicator """
    version = 0
    test = True
    m = RE_VERSION.search(text)
    if m:
        version = int(m.group(1))*1000000 + int(m.group(2))*10000 + int(m.group(3))*100
        try:
            if m.group(4).lower() == 'rc':
                version = version + 50
            version = version + int(m.group(5))
        except:
            version = version + 99
            test = False
    return version, test


def check_latest_version():
    """ Do an online check for the latest version """
    if not cfg.VERSION_CHECK.get():
        return

    current, testver = ConvertVersion(sabnzbd.__version__)
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


    latest, dummy = ConvertVersion(latest_label)
    latest_test, dummy = ConvertVersion(latest_testlabel)

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

def to_units(val):
    """ Convert number to K/M/G/T/P notation
    """
    val = str(val).strip()
    if val == "-1":
        return val
    n= 0
    try:
        val = float(val)
    except:
        val = 0.0
    while (val > 1023.0) and (n < 5):
        val = val / 1024.0
        n= n+1
    unit = TAB_UNITS[n]
    if unit:
        return "%.1f %s" % (val, unit)
    else:
        return "%.0f" % val

#------------------------------------------------------------------------------
def SameFile(a, b):
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
def ExitSab(value):
    sys.stderr.flush()
    sys.stdout.flush()
    sys.exit(value)


#------------------------------------------------------------------------------
def Notify(notificationName, message):
    """ Send a notification to the OS (OSX-only) """
    if HAVE_FOUNDATION:
        pool = Foundation.NSAutoreleasePool.alloc().init()
        nc = Foundation.NSDistributedNotificationCenter.defaultCenter()
        nc.postNotificationName_object_(notificationName, message)
        del pool


#------------------------------------------------------------------------------
def SplitHost(srv):
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
        if not CreateAllDirs(dirpath, True):
            logging.error("Failed making (%s)", dirpath)
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
                logging.error("Failed moving %s to %s", path, new_path)
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
def getFilepath(path, nzo, filename):
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


def BadFetch(nzo, url, retry=False, archive=False):
    """ Create History entry for failed URL Fetch """
    logging.error("Error getting url %s", url)

    pp = nzo.get_pp()
    if pp:
        pp = '&pp=%s' % pp
    else:
        pp = ''
    cat = nzo.get_cat()
    if cat:
        cat = '&cat=%s' % cat
    else:
        cat = ''
    script = nzo.get_script()
    if script:
        script = '&script=%s' % script
    else:
        script = ''

    nzo.set_status("Failed")


    if url:
        nzo.set_filename(url)
        nzo.set_original_dirname(url)

    if retry:
        nzo.set_fail_msg('URL Fetching failed, <a href="./retry?url=%s%s%s%s">Try again</a>' % \
                         (urllib.quote(url), pp, urllib.quote(cat), urllib.quote(script)))
    else:
        if archive:
            msg = 'Failed, Unusable archive file'
        elif not '://' in url:
            msg = 'Failed to fetch newzbin report'
        else:
            msg = 'Failed to add url'
        nzo.set_fail_msg(msg)

    sabnzbd.nzbqueue.remove_nzo(nzo.nzo_id, add_to_history=True, unload=True)


def OnCleanUpList(filename, skip_nzb=False):
    """ Return True if a filename matches the clean-up list """

    if cfg.CLEANUP_LIST.get():
        ext = os.path.splitext(filename)[1].strip().strip('.')
        if os.name == 'nt': ext = ext.lower()

        for k in cfg.CLEANUP_LIST.get():
            item = k.strip().strip('.')
            if item == ext and not (skip_nzb and item == 'nzb'):
                return True
    return False


def loadavg():
    """ Return 1, 5 and 15 minute load average of host or "" if not supported
    """
    if os.name == 'nt' or sabnzbd.DARWIN:
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

    try:
        seconds = int(seconds)
    except:
        seconds = 0

    completestr = ''
    if days:
        completestr += '%s day%s ' % (days, s_returner(days))
    if (seconds/3600) >= 1:
        completestr += '%s hour%s ' % (seconds/3600, s_returner((seconds/3600)))
        seconds -= (seconds/3600)*3600
    if (seconds/60) >= 1:
        completestr += '%s minute%s ' % (seconds/60, s_returner((seconds/60)))
        seconds -= (seconds/60)*60
    if seconds > 0:
        completestr += '%s second%s ' % (seconds, s_returner(seconds))

    return completestr.strip()


def s_returner(value):
    if value > 1:
        return 's'
    else:
        return ''


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
