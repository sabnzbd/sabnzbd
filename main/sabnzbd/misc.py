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
sabnzbd.misc - misc classes
"""
__NAME__ = "sabnzbd.misc"

import os
import sys
import time
import logging
import Queue
import sabnzbd
import cherrypy
import urllib
import re
import zipfile
import gzip
import webbrowser
import tempfile
import shutil

try:
    # Try to import OSX library
    import Foundation
    HAVE_FOUNDATION = True
except:
    HAVE_FOUNDATION = False

from threading import *
from sabnzbd.decorators import *
from sabnzbd.nzbstuff import NzbObject
from sabnzbd.constants import *

RE_VERSION = re.compile('(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_UNITS = re.compile('(\d+\.*\d*)\s*([KMGTP]*)', re.I)
TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')
RE_SANITIZE = re.compile(r'[\\/><\?\*:|"]') # All forbidden file characters
RE_CAT = re.compile(r'^{{(\w+)}}(.+)') # Category prefix

PANIC_NONE  = 0
PANIC_PORT  = 1
PANIC_TEMPL = 2
PANIC_QUEUE = 3
PANIC_FWALL = 4
PANIC_OTHER = 5
PW_PREFIX = '!!!encoded!!!'


def Cat2Opts(cat, pp, script):
    """
        Derive options from category, if option not already defined.
        Specified options have priority over category-options
    """
    if not pp == None:
        try:
            pp = sabnzbd.CFG['categories'][cat.lower()]['pp']
            logging.debug('[%s] Job %s gets options %s', __NAME__, name, pp)
        except:
            pp = sabnzbd.DIRSCAN_PP

    if not script == None:
        try:
            script = sabnzbd.CFG['categories'][cat.lower()]['script']
            logging.debug('[%s] Job %s gets script %s', __NAME__, name, script)
        except:
            script = sabnzbd.DIRSCAN_SCRIPT

    return cat, pp, script


def Cat2OptsDef(fname, cat=None):
    """
        Get options associated with the category.
        Category options have priority over default options.
    """
    pp = sabnzbd.DIRSCAN_PP
    script = sabnzbd.DIRSCAN_SCRIPT
    name = fname

    if cat == None:
        m = RE_CAT.search(fname)
        if m and m.group(1) and m.group(2):
            cat = m.group(1).lower()
            name = m.group(2)
            logging.debug('[%s] Job %s has category %s', __NAME__, name, cat)

    if cat:
        try:
            pp = sabnzbd.CFG['categories'][cat.lower()]['pp']
            logging.debug('[%s] Job %s gets options %s', __NAME__, name, pp)
        except:
            pass

        try:
            script = sabnzbd.CFG['categories'][cat.lower()]['script']
            logging.debug('[%s] Job %s gets script %s', __NAME__, name, script)
        except:
            pass

    return cat, name, pp, script


def ProcessZipFile(filename, path, catdir=None):
    """ Analyse ZIP file and create job(s).
        Accepts ZIP files with ONLY nzb files in it.
    """
    cat, name, pp, script = Cat2OptsDef(filename, catdir)

    zf = zipfile.ZipFile(path)
    ok = True
    for name in zf.namelist():
        if not name.lower().endswith('.nzb'):
            ok = False
            break
    if ok:
        for name in zf.namelist():
            data = zf.read(name)
            name = os.path.basename(name)
            name = RE_SANITIZE.sub('_', name)
            if data:
                try:
                    nzo = NzbObject(name, pp, script, data, cat=cat)
                except:
                    nzo = None
                if nzo:
                    sabnzbd.add_nzo(nzo)
        zf.close()
        try:
            os.remove(path)
        except:
            logging.exception("[%s] Error removing %s", __NAME__, path)
            ok = False
    else:
        zf.close()

    return ok


def ProcessSingleFile(filename, path, catdir=None):
    """ Analyse file and create a job from it
        Supports NZB, NZB.GZ and GZ.NZB-in-disguise
    """
    try:
        f = open(path, 'rb')
        b1 = f.read(1)
        b2 = f.read(1)
        f.close()

        if (b1 == '\x1f' and b2 == '\x8b'):
            # gzip file or gzip in disguise
            name = filename.replace('.nzb.gz', '.nzb')
            f = gzip.GzipFile(path, 'rb')
        else:
            name = filename
            f = open(path, 'rb')
        data = f.read()
        f.close()
    except:
        logging.warning('[%s] Cannot read %s', __NAME__, path)
        return False

    cat, name, pp, script = Cat2OptsDef(name, catdir)

    try:
        nzo = NzbObject(name, pp, script, data, cat=cat)
    except:
        return False

    sabnzbd.add_nzo(nzo)
    try:
        os.remove(path)
    except:
        logging.error("[%s] Error removing %s", __NAME__, path)
        return False

    return True

#------------------------------------------------------------------------------
class DirScanner(Thread):
    """
    Thread that periodically scans a given directoty and picks up any
    valid NZB, NZB.GZ ZIP-with-only-NZB and even NZB.GZ named as .NZB
    Candidates which turned out wrong, will be remembered and skipped in
    subsequent scans.
    """
    def __init__(self, dirscan_dir, dirscan_speed):
        Thread.__init__(self)

        self.dirscan_dir = dirscan_dir
        self.dirscan_speed = dirscan_speed

        self.ignored = []  # Will hold all examined but bad candidates
        self.shutdown = False
        self.error_reported = False # Prevents mulitple reporting of missing watched folder

    def stop(self):
        logging.info('[%s] Dirscanner shutting down', __NAME__)
        self.shutdown = True

    def run(self):
        def run_dir(folder, catdir):
            try:
                files = os.listdir(folder)
            except:
                if not self.error_reported and not catdir:
                    logging.error("Cannot read Watched Folder %s", folder)
                    self.error_reported = True
                files = []

            for filename in files:
                path = os.path.join(folder, filename)
                if os.path.isdir(path) or path in self.ignored:
                    continue

                root, ext = os.path.splitext(path)
                ext = ext.lower()
                candidate = ext in ('.nzb', '.zip', '.gz')
                if candidate:
                    stat_tuple = os.stat(path)
                else:
                    self.ignored.append(path)

                if candidate and stat_tuple.st_size > 0:
                    logging.info('[%s] Trying to import %s', __NAME__, path)

                    # Wait until the attributes are stable for 1 second
                    while 1:
                        time.sleep(1.0)
                        stat_tuple_tmp = os.stat(path)
                        if stat_tuple == stat_tuple_tmp:
                            break
                        else:
                            stat_tuple = stat_tuple_tmp

                    # Handle ZIP files, but only when containing just NZB files
                    if ext == '.zip':
                        if not ProcessZipFile(filename, path, catdir):
                            self.ignored.append(path)
                        else:
                            self.error_reported = False

                    # Handle .nzb, .nzb.gz or gzip-disguised-as-nzb
                    elif ext == '.nzb' or filename.lower().endswith('.nzb.gz'):
                        if not ProcessSingleFile(filename, path, catdir):
                            self.ignored.append(path)
                        else:
                            self.error_reported = False
                    else:
                        self.ignored.append(path)

                if path in self.ignored:
                    logging.debug('[%s] Ignoring %s', __NAME__, path)


        logging.info('[%s] Dirscanner starting up', __NAME__)

        while not self.shutdown:
            # Use variable scan delay
            x = self.dirscan_speed
            while (x > 0) and not self.shutdown:
                time.sleep(1.0)
                x = x - 1

            run_dir(self.dirscan_dir, None)

            for dd in os.listdir(self.dirscan_dir):
                dpath = os.path.join(self.dirscan_dir, dd)
                if os.path.isdir(dpath) and dd.lower() in sabnzbd.CFG['categories']:
                    run_dir(dpath, dd.lower())


#------------------------------------------------------------------------------
class URLGrabber(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.queue = Queue.Queue()
        self.shutdown = False

    def add(self, url, future_nzo):
        """ Add an URL to the URLGrabber queue """
        self.queue.put((url, future_nzo))

    def stop(self):
        logging.info('[%s] URLGrabber shutting down', __NAME__)
        self.queue.put((None, None))
        self.shutdown = True

    def run(self):
        logging.info('[%s] URLGrabber starting up', __NAME__)

        while not self.shutdown:
            (url, future_nzo) = self.queue.get()
            if not url:
                continue

            try:
                logging.info('[%s] Grabbing URL %s', __NAME__, url)
                opener = urllib.FancyURLopener({})
                opener.prompt_user_passwd = None
                fn, header = opener.retrieve(url)

                filename, data = (None, None)
                f = open(fn, 'r')
                data = f.read()
                f.close()
                os.remove(fn)

                for tup in header.items():
                    for item in tup:
                        if "filename=" in item:
                            filename = item[item.index("filename=") + 9:]
                            break

                if data:
                    if not filename:
                         filename = os.path.basename(url)
                    pp = future_nzo.get_repair_opts()
                    script = future_nzo.get_script()
                    cat = future_nzo.get_cat()
                    cat, pp, script = Cat2Opts(cat, pp, script)
                    sabnzbd.insert_future_nzo(future_nzo, filename, data, pp=pp, script=script, cat=cat)
                else:
                    sabnzbd.remove_nzo(future_nzo.nzo_id, False)

            except:
                logging.exception("[%s] Error adding url %s", __NAME__, url)
                sabnzbd.remove_nzo(future_nzo.nzo_id, False)

            # Don't pound the website!
            time.sleep(1.0)


################################################################################
# Real_Path                                                                    #
################################################################################
def real_path(loc, path):
    if not ((os.name == 'nt' and path[0].isalpha() and path[1] == ':') or \
            (path[0] == '/' or path[0] == '\\')):
        path = loc + '/' + path
    return os.path.normpath(os.path.abspath(path))


################################################################################
# Create_Real_Path                                                             #
################################################################################
def create_real_path(name, loc, path):
    if path:
        my_dir = real_path(loc, path)
        if not os.path.exists(my_dir):
            logging.info('%s directory: %s does not exist, try to create it', name, my_dir)
            try:
                os.makedirs(my_dir)
            except:
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
    dict = {}

    # Open registry hive
    try:
        hive = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    except WindowsError:
        logging.error("Cannot connect to registry hive HKEY_CURRENT_USER.")
        return dict

    # Then open the registry key where Windows stores the Shell Folder locations
    try:
        key = _winreg.OpenKey(hive, "Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
    except WindowsError:
        logging.error("Cannot open registry key Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders.")
        _winreg.CloseKey(hive)
        return dict

    try:
        for i in range(0, _winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, i)
            try:
                dict[name] = value.encode('latin-1')
            except:
                try:
                    import win32api
                    dict[name] = win32api.GetShortPathName(value)
                except:
                    del dict[name]
            i += 1
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return dict
    except WindowsError:
        # On error, return empty dict.
        logging.error("Failed to read registry keys for special folders")
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return {}


################################################################################
# save_configfile
#
################################################################################
def save_configfile(cfg):
    """Save configuration to disk
    """
    try:
        cfg.write()
        f = open(cfg.filename)
        x = f.read()
        f.close()
        f = open(cfg.filename, "w")
        f.write(x)
        f.flush()
        f.close()
    except:
        Panic('Cannot write to configuration file "%s".' % cfg.filename, \
              'Make sure file is writable and in a writable folder.')
        ExitSab(2)

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
    if (not sabnzbd.AUTOBROWSER) or sabnzbd.DAEMON:
        return

    if os.name == 'nt':
        os_str = 'Press Startkey+R and type the line (example):'
    else:
        os_str = 'Open a Terminal window and type the line (example):'

    if panic == PANIC_PORT:
        newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_BAD_PORT % (b, a, os_str, sabnzbd.MY_FULLNAME, a, newport)
    elif panic == PANIC_TEMPL:
        msg = MSG_BAD_TEMPL % a
    elif panic == PANIC_QUEUE:
        msg = MSG_BAD_QUEUE % (a, os_str, sabnzbd.MY_FULLNAME)
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
    if (not sabnzbd.AUTOBROWSER) or sabnzbd.DAEMON:
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


################################################################################
# Check latest version
#
# Perform an online version check
# Formula
# - the online version is always: <major>.<minor>.<bugfix>
# - the local version is <major>.<minor>.<bugfix>[rc|beta]<cand>
#
# The <cand> value for the online version is assumned to be 99.
# The <cand> value for the local version is 1..98
# This is done to signal beta|rc users of availability of the final
# version (which is implicitly 99).
# People are NOT informed to upgrade to a higher beta|rc version, since these
# are not in the online version indicator.
#
################################################################################

def check_latest_version():
    try:
        fn = urllib.urlretrieve('http://sabnzbdplus.sourceforge.net/version/latest')[0]
        f = open(fn, 'r')
        data = f.read()
        f.close()
    except:
        return

    latest_label = data.split()[0]
    url = data.split()[1]
    m = RE_VERSION.search(latest_label)
    latest = int(m.group(1))*1000000 + int(m.group(2))*10000 + int(m.group(3))*100 + 99

    m = RE_VERSION.search(sabnzbd.__version__)
    current = int(m.group(1))*10000 + int(m.group(2))*10000 + int(m.group(3))*100
    try:
        current = current + int(m.group(5))
    except:
        current = current + 99

    logging.debug("Checked for a new release, cur= %s, latest= %s (on %s)", current, latest, url)

    if current < latest:
        sabnzbd.NEW_VERSION = "%s;%s" % (latest_label, url)


def from_units(val):
    """ Convert K/M/G/T/P notation to float
    """
    val = str(val).strip().upper()
    if val == "-1":
        return val
    m = RE_UNITS.search(val)
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


def to_units(val):
    """ Convert number to K/M/G/T/P notation
    """
    val = str(val).strip()
    if val == "-1":
        return val
    n= 0
    val = float(val)
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
        return os.path.samefile(a, b)
    else:
        a = os.path.normpath(os.path.abspath(a)).lower()
        b = os.path.normpath(os.path.abspath(b)).lower()
        return a == b

#------------------------------------------------------------------------------
def ExitSab(value):
    sys.stderr.flush()
    sys.stdout.flush()
    if sabnzbd.WAITEXIT and hasattr(sys, "frozen"):
        print
        raw_input("Press ENTER to close this window");
    sys.exit(value)


#------------------------------------------------------------------------------
def encode_for_xml(unicode_data, encoding='ascii'):
    """
    Encode unicode_data for use as XML or HTML, with characters outside
    of the encoding converted to XML numeric character references.
    """
    try:
        return unicode_data.encode(encoding, 'xmlcharrefreplace')
    except ValueError:
        # ValueError is raised if there are unencodable chars in the
        # data and the 'xmlcharrefreplace' error handler is not found.
        # Pre-2.3 Python doesn't support the 'xmlcharrefreplace' error
        # handler, so we'll emulate it.
        return _xmlcharref_encode(unicode_data, encoding)

def _xmlcharref_encode(unicode_data, encoding):
    """Emulate Python 2.3's 'xmlcharrefreplace' encoding error handler."""
    chars = []
    # Step through the unicode_data string one character at a time in
    # order to catch unencodable characters:
    for char in unicode_data:
        try:
            chars.append(char.encode(encoding, 'strict'))
        except UnicodeError:
            chars.append('&#%i;' % ord(char))
    return ''.join(chars)


#------------------------------------------------------------------------------
def encodePassword(pw):
    """ Encode password in hexadecimal if needed """
    enc = False
    if pw:
        encPW = PW_PREFIX
        for c in pw:
            cnum = ord(c)
            if c == '#' or cnum<33 or cnum>126:
                enc = True
            encPW += '%2x' % cnum
        if enc:
            return encPW
    return pw


def decodePassword(pw, name):
    """ Decode hexadecimal encoded password
        but only decode when prefixed
    """
    decPW = ''
    if pw.startswith(PW_PREFIX):
        for n in range(len(PW_PREFIX), len(pw), 2):
            try:
                ch = chr( int(pw[n] + pw[n+1],16) )
            except:
                logging.error('[%s] Incorrectly encoded password %s', __NAME__, name)
                return ''
            decPW += ch
        return decPW
    else:
        return pw

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

DIR_LOCK = RLock()

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
def create_dirs(dirpath):
    """ Create directory tree, obeying permissions """
    if not os.path.exists(dirpath):
        logging.info('[%s] Creating directories: %s', __NAME__, dirpath)
        try:
            if sabnzbd.UMASK and os.name != 'nt':
                os.makedirs(dirpath, int(sabnzbd.UMASK, 8) | 00700)
            else:
                os.makedirs(dirpath)
        except:
            logging.exception("[%s] Failed making (%s)",__NAME__,dirpath)
            return None

    return dirpath


@synchronized(DIR_LOCK)
def move_to_path(path, new_path, unique=True):
    """ Move a file to a new path, optionally give unique filename """
    if unique:
        new_path = get_unique_path(new_path, create_dir=False)
    if new_path:
        logging.debug("[%s] Moving. Old path:%s new path:%s unique?:%s",
                                                  __NAME__,path,new_path, unique)
        try:
            # First try cheap rename
            os.rename(path, new_path)
        except:
            # Cannot rename, try copying
            try:
                shutil.copyfile(path, new_path)
                os.remove(path)
            except:
                logging.error("[%s] Failed moving %s to %s", __NAME__, path, new_path)
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
