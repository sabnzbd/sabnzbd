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
sabnzbd.misc - misc classes
"""

import os
import sys
import logging
import urllib
import re
import shutil
import threading
import subprocess
import socket
import time
import fnmatch
import stat
try:
    socket.ssl
    _HAVE_SSL = True
except:
    _HAVE_SSL = False
from urlparse import urlparse

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import DEFAULT_PRIORITY, FUTURE_Q_FOLDER, JOB_ADMIN, GIGI, MEBI
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.encoding import unicoder, special_fixer, gUTF

RE_VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_UNITS = re.compile(r'(\d+\.*\d*)\s*([KMGTP]{0,1})', re.I)
TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')

# Check if strings are defined for AM and PM
HAVE_AMPM = bool(time.strftime('%p', time.localtime()))


def time_format(fmt):
    """ Return time-format string adjusted for 12/24 hour clock setting """
    if cfg.ampm() and HAVE_AMPM:
        return fmt.replace('%H:%M:%S', '%I:%M:%S %p').replace('%H:%M', '%I:%M %p')
    else:
        return fmt


def safe_lower(txt):
    """ Return lowercased string. Return '' for None """
    if txt:
        return txt.lower()
    else:
        return ''


def globber(path, pattern=u'*'):
    """ Return matching base file/folder names in folder `path` """
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        return [f for f in os.listdir(path) if fnmatch.fnmatch(f, pattern)]
    else:
        return []


def globber_full(path, pattern=u'*'):
    """ Return matching full file/folder names in folder `path` """
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        try:
            return [os.path.join(path, f) for f in os.listdir(path) if fnmatch.fnmatch(f, pattern)]
        except UnicodeDecodeError:
            # This happens on Linux when names are incorrectly encoded, retry using a non-Unicode path
            path = path.encode('utf-8')
            return [os.path.join(path, f) for f in os.listdir(path) if fnmatch.fnmatch(f, pattern)]
    else:
        return []


def cat_to_opts(cat, pp=None, script=None, priority=None):
    """ Derive options from category, if options not already defined.
        Specified options have priority over category-options.
        If no valid category is given, special category '*' will supply default values
    """
    def_cat = config.get_categories('*')
    cat = safe_lower(cat)
    if cat in ('', 'none', 'default'):
        cat = '*'
    try:
        my_cat = config.get_categories()[cat]
    except KeyError:
        my_cat = def_cat

    if pp is None:
        pp = my_cat.pp()
        if pp == '':
            pp = def_cat.pp()

    if not script:
        script = my_cat.script()
        if safe_lower(script) in ('', 'default'):
            script = def_cat.script()

    if priority is None or priority == DEFAULT_PRIORITY:
        priority = my_cat.priority()
        if priority == DEFAULT_PRIORITY:
            priority = def_cat.priority()

    # logging.debug('Cat->Attrib cat=%s pp=%s script=%s prio=%s', cat, pp, script, priority)
    return cat, pp, script, priority


_wildcard_to_regex = {
    '\\': r'\\',
    '^': r'\^',
    '$': r'\$',
    '.': r'\.',
    '[': r'\[',
    ']': r'\]',
    '(': r'\(',
    ')': r'\)',
    '+': r'\+',
    '?': r'.',
    '|': r'\|',
    '{': r'\{',
    '}': r'\}',
    '*': r'.*'
}


def wildcard_to_re(text):
    """ Convert plain wildcard string (with '*' and '?') to regex. """
    return ''.join([_wildcard_to_regex.get(ch, ch) for ch in text])


def cat_convert(cat):
    """ Convert indexer's category/group-name to user categories.
        If no match found, but indexer-cat equals user-cat, then return user-cat
        If no match found, return None
    """
    newcat = cat
    found = False

    if cat and cat.lower() != 'none':
        cats = config.get_categories()
        for ucat in cats:
            try:
                indexer = cats[ucat].newzbin()
                if type(indexer) != type([]):
                    indexer = [indexer]
            except:
                indexer = []
            for name in indexer:
                if re.search('^%s$' % wildcard_to_re(name), cat, re.I):
                    if '.' not in name:
                        logging.debug('Convert index site category "%s" to user-cat "%s"', cat, ucat)
                    else:
                        logging.debug('Convert group "%s" to user-cat "%s"', cat, ucat)
                    newcat = ucat
                    found = True
                    break
            if found:
                break

        if not found:
            for ucat in cats:
                if cat.lower() == ucat.lower():
                    found = True
                    break

    if found:
        return newcat
    else:
        return None


##############################################################################
# sanitize_filename
##############################################################################
_DEVICES = ('con', 'prn', 'aux', 'nul',
            'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
            'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9')

def replace_win_devices(name):
    ''' Remove reserved Windows device names from a name.
        aux.txt ==> _aux.txt
        txt.aux ==> txt.aux
    '''
    if name:
        lname = name.lower()
        for dev in _DEVICES:
            if lname == dev or lname.startswith(dev + '.'):
                name = '_' + name
                break
    return name

if sabnzbd.WIN32:
    # the colon should be here too, but we'll handle that separately
    CH_ILLEGAL = r'\/<>?*|"'
    CH_LEGAL = r'++{}!@#`'
else:
    CH_ILLEGAL = r'/'
    CH_LEGAL = r'+'


def sanitize_filename(name):
    """ Return filename with illegal chars converted to legal ones
        and with the par2 extension always in lowercase
    """
    if not name:
        return name
    illegal = CH_ILLEGAL
    legal = CH_LEGAL

    if ':' in name:
        if sabnzbd.WIN32:
            # Compensate for the odd way par2 on Windows substitutes a colon character
            name = name.replace(':', '3A')
        elif sabnzbd.DARWIN:
            # Compensate for the foolish way par2 on OSX handles a colon character
            name = name[name.rfind(':') + 1:]

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


def sanitize_foldername(name, limit=True):
    """ Return foldername with dodgy chars converted to safe ones
        Remove any leading and trailing dot and space characters
    """
    if not name:
        return name

    FL_ILLEGAL = CH_ILLEGAL + ':\x92"'
    FL_LEGAL = CH_LEGAL + "-''"
    uFL_ILLEGAL = FL_ILLEGAL.decode('cp1252')
    uFL_LEGAL = FL_LEGAL.decode('cp1252')

    if isinstance(name, unicode):
        illegal = uFL_ILLEGAL
        legal = uFL_LEGAL
    else:
        illegal = FL_ILLEGAL
        legal = FL_LEGAL

    if cfg.sanitize_safe():
        # Remove all bad Windows chars too
        illegal += r'\/<>?*|":'
        legal += r'++{}!@#`;'

    repl = cfg.replace_illegal()
    lst = []
    for ch in name.strip():
        if ch in illegal:
            if repl:
                ch = legal[illegal.find(ch)]
                lst.append(ch)
        else:
            lst.append(ch)
    name = ''.join(lst)

    name = name.strip()
    if name != '.' and name != '..':
        name = name.rstrip('.')
    if not name:
        name = 'unknown'

    maxlen = cfg.folder_max_length()
    if limit and len(name) > maxlen:
        name = name[:maxlen]

    if sabnzbd.WIN32 or cfg.sanitize_safe():
        name = replace_win_devices(name)
    return name


def sanitize_and_trim_path(path):
    """ Remove illegal characters and trim element size """
    path = path.strip()
    new_path = ''
    if sabnzbd.WIN32:
        if path.startswith(u'\\\\?\\UNC\\'):
            new_path = u'\\\\?\\UNC\\'
            path = path[8:]
        elif path.startswith(u'\\\\?\\'):
            new_path = u'\\\\?\\'
            path = path[4:]

    path = path.replace('\\', '/')
    parts = path.split('/')
    if sabnzbd.WIN32 and len(parts[0]) == 2 and ':' in parts[0]:
        new_path += parts[0] + '/'
        parts.pop(0)
    elif path.startswith('//'):
        new_path = '//'
    elif path.startswith('/'):
        new_path = '/'
    for part in parts:
        new_path = os.path.join(new_path, sanitize_foldername(part))
    return os.path.abspath(os.path.normpath(new_path))


def flag_file(path, flag, create=False):
    """ Create verify flag file or return True if it already exists """
    path = os.path.join(path, JOB_ADMIN)
    path = os.path.join(path, flag)
    if create:
        try:
            f = open(path, 'w')
            f.write('ok\n')
            f.close()
            return True
        except IOError:
            return False
    else:
        return os.path.exists(path)


##############################################################################
# DirPermissions
##############################################################################
def create_all_dirs(path, umask=False):
    """ Create all required path elements and set umask on all
        Return True if last element could be made or exists
    """
    result = True
    if sabnzbd.WIN32:
        try:
            os.makedirs(path)
        except:
            result = False
    else:
        lst = []
        lst.extend(path.split('/'))
        path = ''
        for d in lst:
            if d:
                path += '/' + d
                if not os.path.exists(path):
                    try:
                        os.mkdir(path)
                        result = True
                    except:
                        result = False
                    if umask:
                        mask = cfg.umask()
                        if mask:
                            try:
                                os.chmod(path, int(mask, 8) | 0700)
                            except:
                                pass
    return result

##############################################################################
# Real_Path
##############################################################################
def real_path(loc, path):
    """ When 'path' is relative, return normalized join of 'loc' and 'path'
        When 'path' is absolute, return normalized path
        A path starting with ~ will be located in the user's Home folder
    """
    # The Windows part is a bit convoluted because
    # os.path.join() doesn't behave the same for all Python versions
    if path:
        path = path.strip()
    else:
        path = ''
    if path:
        if not sabnzbd.WIN32 and path.startswith('~/'):
            path = path.replace('~', os.environ.get('HOME', sabnzbd.DIR_HOME), 1)
        if sabnzbd.WIN32:
            path = path.replace('/', '\\')
            if len(path) > 1 and path[0].isalpha() and path[1] == ':':
                if len(path) == 2 or path[2] != '\\':
                    path = path.replace(':', ':\\', 1)
            elif path.startswith('\\\\'):
                pass
            elif path.startswith('\\'):
                if len(loc) > 1 and loc[0].isalpha() and loc[1] == ':':
                    path = loc[:2] + path
            else:
                path = os.path.join(loc, path)
        elif path[0] != '/':
            path = os.path.join(loc, path)
    else:
        path = loc

    return os.path.normpath(os.path.abspath(path))


##############################################################################
# Create_Real_Path
##############################################################################
def create_real_path(name, loc, path, umask=False, writable=True):
    """ When 'path' is relative, create join of 'loc' and 'path'
        When 'path' is absolute, create normalized path
        'name' is used for logging.
        Optional 'umask' will be applied.
        'writable' means that an existing folder should be writable
        Returns ('success', 'full path')
    """
    if path:
        my_dir = real_path(loc, path)
        if not os.path.exists(my_dir):
            logging.info('%s directory: %s does not exist, try to create it', name, my_dir)
            if not create_all_dirs(my_dir, umask):
                logging.error(T('Cannot create directory %s'), clip_path(my_dir))
                return (False, my_dir)

        checks = (os.W_OK + os.R_OK) if writable else os.R_OK
        if os.access(my_dir, checks):
            return (True, my_dir)
        else:
            logging.error(T('%s directory: %s error accessing'), name, clip_path(my_dir))
            return (False, my_dir)
    else:
        return (False, "")


def windows_variant():
    """ Determine Windows variant
        Return vista_plus, x64
    """
    from win32api import GetVersionEx
    from win32con import VER_PLATFORM_WIN32_NT
    import _winreg

    vista_plus = x64 = False
    maj, _minor, _buildno, plat, _csd = GetVersionEx()

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
                name, value, _val_type = _winreg.EnumValue(key, n)
                if name == 'PROCESSOR_ARCHITECTURE':
                    x64 = value.upper() == u'AMD64'
                    break
            _winreg.CloseKey(key)

    return vista_plus, x64


_SERVICE_KEY = 'SYSTEM\\CurrentControlSet\\services\\'
_SERVICE_PARM = 'CommandLine'


def get_serv_parms(service):
    """ Get the service command line parameters from Registry """
    import _winreg

    value = []
    try:
        key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        for n in xrange(_winreg.QueryInfoKey(key)[1]):
            name, value, _val_type = _winreg.EnumValue(key, n)
            if name == _SERVICE_PARM:
                break
        _winreg.CloseKey(key)
    except WindowsError:
        pass
    for n in xrange(len(value)):
        value[n] = value[n]
    return value


def set_serv_parms(service, args):
    """ Set the service command line parameters in Registry """
    import _winreg

    uargs = []
    for arg in args:
        uargs.append(unicoder(arg))

    try:
        key = _winreg.CreateKey(_winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        _winreg.SetValueEx(key, _SERVICE_PARM, None, _winreg.REG_MULTI_SZ, uargs)
        _winreg.CloseKey(key)
    except WindowsError:
        return False
    return True


def convert_version(text):
    """ Convert version string to numerical value and a testversion indicator """
    version = 0
    test = True
    m = RE_VERSION.search(text)
    if m:
        version = int(m.group(1)) * 1000000 + int(m.group(2)) * 10000 + int(m.group(3)) * 100
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
    """ Do an online check for the latest version

        Perform an online version check
        Syntax of online version file:
            <current-final-release>
            <url-of-current-final-release>
            <latest-alpha/beta-or-rc>
            <url-of-latest-alpha/beta/rc-release>
        The latter two lines are only present when an alpha/beta/rc is available.
        Formula for the version numbers (line 1 and 3).
            <major>.<minor>.<bugfix>[rc|beta|alpha]<cand>

        The <cand> value for a final version is assumned to be 99.
        The <cand> value for the beta/rc version is 1..98, with RC getting
        a boost of 80 and Beta of 40.
        This is done to signal alpha/beta/rc users of availability of the final
        version (which is implicitly 99).
        People will only be informed to upgrade to a higher alpha/beta/rc version, if
        they are already using an alpha/beta/rc.
        RC's are valued higher than Beta's, which are valued higher than Alpha's.
    """

    if not cfg.version_check():
        return

    current, testver = convert_version(sabnzbd.__version__)
    if not current:
        logging.debug("Unsupported release number (%s), will not check", sabnzbd.__version__)
        return

    # Using catch-all except's is poor coding practice.
    # However, the last thing you want is the app crashing due
    # to bad file content.

    try:
        fn = urllib.urlretrieve('https://raw.githubusercontent.com/sabnzbd/sabnzbd.github.io/master/latest.txt')[0]
        f = open(fn, 'r')
        data = f.read()
        f.close()
        os.remove(fn)
    except:
        logging.info('Cannot retrieve version information from GitHub.com')
        logging.debug('Traceback: ', exc_info=True)
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

    latest = convert_version(latest_label)[0]
    latest_test = convert_version(latest_testlabel)[0]

    logging.debug('Checked for a new release, cur= %s, latest= %s (on %s)', current, latest, url)

    if latest_test and cfg.version_check() > 1:
        # User always wants to see the latest test release
        latest = latest_test
        url = url_beta

    if testver and current < latest:
        # This is a test version, but user has't seen the
        # "Final" of this one yet, so show the Final
        sabnzbd.NEW_VERSION = '%s;%s' % (latest_label, url)
    elif current < latest:
        # This one is behind, show latest final
        sabnzbd.NEW_VERSION = '%s;%s' % (latest_label, url)
    elif testver and current < latest_test:
        # This is a test version beyond the latest Final, so show latest Alpha/Beta/RC
        sabnzbd.NEW_VERSION = '%s;%s' % (latest_testlabel, url_beta)


def from_units(val):
    """ Convert K/M/G/T/P notation to float """
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
                n = n + 1
        else:
            val = m.group(1)
        try:
            return float(val)
        except:
            return 0.0
    else:
        return 0.0


def to_units(val, spaces=0, dec_limit=2, postfix=''):
    """ Convert number to K/M/G/T/P notation
        Add "spaces" if not ending in letter
        dig_limit==1 show single decimal for M and higher
        dig_limit==2 show single decimal for G and higher
    """
    decimals = 0
    if val < 0:
        sign = '-'
    else:
        sign = ''
    val = str(abs(val)).strip()

    n = 0
    try:
        val = float(val)
    except:
        return ''
    while (val > 1023.0) and (n < 5):
        val = val / 1024.0
        n = n + 1
    unit = TAB_UNITS[n]
    if not unit:
        unit = ' ' * spaces
    if n > dec_limit:
        decimals = 1
    else:
        decimals = 0

    fmt = '%%s%%.%sf %%s%%s' % decimals
    return fmt % (sign, val, unit, postfix)


def same_file(a, b):
    """ Return 0 if A and B have nothing in common
        return 1 if A and B are actually the same path
        return 2 if B is a subfolder of A
    """
    a = os.path.normpath(os.path.abspath(a))
    b = os.path.normpath(os.path.abspath(b))
    if sabnzbd.WIN32 or sabnzbd.DARWIN:
        a = a.lower()
        b = b.lower()

    if b.startswith(a):
        return 2
    if "samefile" in os.path.__dict__:
        try:
            return int(os.path.samefile(a, b))
        except:
            return 0
    else:
        return int(a == b)


def exit_sab(value):
    """ Leave the program after flushing stderr/stdout """
    sys.stderr.flush()
    sys.stdout.flush()
    if getattr(sys, 'frozen', None) == 'macosx_app':
        sabnzbd.SABSTOP = True
        from PyObjCTools import AppHelper  # @UnresolvedImport
        AppHelper.stopEventLoop()
    sys.exit(value)


def split_host(srv):
    """ Split host:port notation, allowing for IPV6 """
    # Cannot use split, because IPV6 of "a:b:c:port" notation
    # Split on the last ':'
    mark = srv.rfind(':')
    if mark < 0:
        host = srv
    else:
        host = srv[0: mark]
        port = srv[mark + 1:]
    try:
        port = int(port)
    except:
        port = None
    return (host, port)


def check_mount(path):
    """ Return False if volume isn't mounted on Linux or OSX
        Retry 6 times with an interval of 1 sec.
    """
    if sabnzbd.DARWIN:
        m = re.search(r'^(/Volumes/[^/]+)/', path, re.I)
    elif sabnzbd.WIN32:
        m = re.search(r'^([a-z]:\\)', path, re.I)
    else:
        m = re.search(r'^(/(?:mnt|media)/[^/]+)/', path)

    if m:
        for n in xrange(cfg.wait_ext_drive() or 1):
            if os.path.exists(m.group(1)):
                return True
            logging.debug('Waiting for %s to come online', m.group(1))
            time.sleep(1)
    return not m


##############################################################################
# Locked directory operations
##############################################################################
DIR_LOCK = threading.RLock()


@synchronized(DIR_LOCK)
def get_unique_path(dirpath, n=0, create_dir=True):
    """ Determine a unique folder or filename """

    if not check_mount(dirpath):
        return dirpath

    path = dirpath
    if n:
        path = "%s.%s" % (dirpath, n)

    if not os.path.exists(path):
        if create_dir:
            return create_dirs(path)
        else:
            return path
    else:
        return get_unique_path(dirpath, n=n + 1, create_dir=create_dir)


@synchronized(DIR_LOCK)
def get_unique_filename(path):
    """ Check if path is unique. If not, add number like: "/path/name.NUM.ext". """
    num = 1
    while os.path.exists(path):
        path, fname = os.path.split(path)
        name, ext = os.path.splitext(fname)
        fname = "%s.%d%s" % (name, num, ext)
        num += 1
        path = os.path.join(path, fname)
    return path


@synchronized(DIR_LOCK)
def create_dirs(dirpath):
    """ Create directory tree, obeying permissions """
    if not os.path.exists(dirpath):
        logging.info('Creating directories: %s', dirpath)
        if not create_all_dirs(dirpath, True):
            logging.error(T('Failed making (%s)'), clip_path(dirpath))
            return None
    return dirpath


@synchronized(DIR_LOCK)
def move_to_path(path, new_path):
    """ Move a file to a new path, optionally give unique filename
        Return (ok, new_path)
    """
    ok = True
    overwrite = cfg.overwrite_files()
    new_path = os.path.abspath(new_path)
    if overwrite and os.path.exists(new_path):
        try:
            os.remove(new_path)
        except:
            overwrite = False
    if not overwrite:
        new_path = get_unique_filename(new_path)

    if new_path:
        logging.debug("Moving. Old path:%s new path:%s overwrite?:%s",
                                                  path, new_path, overwrite)
        try:
            # First try cheap rename
            renamer(path, new_path)
        except:
            # Cannot rename, try copying
            try:
                if not os.path.exists(os.path.dirname(new_path)):
                    create_dirs(os.path.dirname(new_path))
                shutil.copyfile(path, new_path)
                os.remove(path)
            except:
                if not (cfg.marker_file() and cfg.marker_file() in path):
                    logging.error(T('Failed moving %s to %s'), clip_path(path), clip_path(new_path))
                    logging.info("Traceback: ", exc_info=True)
                ok = False
    return ok, new_path


@synchronized(DIR_LOCK)
def cleanup_empty_directories(path):
    """ Remove all empty folders inside (and including) 'path' """
    path = os.path.normpath(path)
    while 1:
        repeat = False
        for root, dirs, files in os.walk(path, topdown=False):
            if not dirs and not files and root != path:
                try:
                    remove_dir(root)
                    repeat = True
                except:
                    pass
        if not repeat:
            break
    try:
        remove_dir(path)
    except:
        pass


@synchronized(DIR_LOCK)
def get_filepath(path, nzo, filename):
    """ Create unique filepath """
    # This procedure is only used by the Assembler thread
    # It does no umask setting
    # It uses the dir_lock for the (rare) case that the
    # download_dir is equal to the complete_dir.
    dirname = nzo.work_name
    created = nzo.created

    dName = dirname
    if not created:
        for n in xrange(200):
            dName = dirname
            if n:
                dName += '.' + str(n)
            try:
                os.mkdir(os.path.join(path, dName))
                break
            except:
                pass
        nzo.work_name = dName
        nzo.created = True

    fPath = os.path.join(os.path.join(path, dName), filename)
    fPath, ext = os.path.splitext(fPath)
    n = 0
    while True:
        if n:
            fullPath = "%s.%d%s" % (fPath, n, ext)
        else:
            fullPath = fPath + ext
        if os.path.exists(fullPath):
            n = n + 1
        else:
            break

    return fullPath


def trim_win_path(path):
    """ Make sure Windows path stays below 70 by trimming last part """
    if sabnzbd.WIN32 and len(path) > 69:
        path, folder = os.path.split(path)
        maxlen = 69 - len(path)
        if len(folder) > maxlen:
            folder = folder[:maxlen]
        path = os.path.join(path, folder).rstrip('. ')
    return path


def check_win_maxpath(folder):
    """ Return False if any file path in folder exceeds the Windows maximum """
    if sabnzbd.WIN32:
        for p in os.listdir(folder):
            if len(os.path.join(folder, p)) > 259:
                return False
    return True


def make_script_path(script):
    """ Return full script path, if any valid script exists, else None """
    s_path = None
    path = cfg.script_dir.get_path()
    if path and script:
        if script.lower() not in ('none', 'default'):
            s_path = os.path.join(path, script)
            if not os.path.exists(s_path):
                s_path = None
    return s_path


def get_admin_path(name, future):
    """ Return news-style full path to job-admin folder of names job
        or else the old cache path
    """
    if future:
        return os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)
    else:
        return os.path.join(os.path.join(cfg.download_dir.get_path(), name), JOB_ADMIN)


def on_cleanup_list(filename, skip_nzb=False):
    """ Return True if a filename matches the clean-up list """
    lst = cfg.cleanup_list()
    if lst:
        name, ext = os.path.splitext(filename)
        ext = ext.strip().lower()
        name = name.strip()
        for k in lst:
            item = k.strip().strip('.').lower()
            item = '.' + item
            if (item == ext or (ext == '' and item == name)) and not (skip_nzb and item == '.nzb'):
                return True
    return False


def get_ext(filename):
    """ Return lowercased file extension """
    try:
        return os.path.splitext(filename)[1].lower()
    except:
        return ''


def get_filename(path):
    """ Return path without the file extension """
    try:
        return os.path.split(path)[1]
    except:
        return ''


def memory_usage():
    try:
        # Probably only works on Linux because it uses /proc/<pid>/statm
        t = open('/proc/%d/statm' % os.getpid())
        v = t.read().split()
        t.close()
        virt = int(_PAGE_SIZE * int(v[0]) / MEBI)
        res = int(_PAGE_SIZE * int(v[1]) / MEBI)
        return "V=%sM R=%sM" % (virt, res)
    except IOError:
        pass
    except:
        logging.debug('Error retrieving memory usage')
        logging.info("Traceback: ", exc_info=True)
    else:
        return ''
try:
    _PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
except:
    _PAGE_SIZE = 0
_HAVE_STATM = _PAGE_SIZE and memory_usage()


def loadavg():
    """ Return 1, 5 and 15 minute load average of host or "" if not supported """
    p = ''
    if not sabnzbd.WIN32 and not sabnzbd.DARWIN:
        opt = cfg.show_sysload()
        if opt:
            try:
                p = '%.2f | %.2f | %.2f' % os.getloadavg()
            except:
                pass
            if opt > 1 and _HAVE_STATM:
                p = '%s | %s' % (p, memory_usage())
    return p


def format_time_string(seconds, days=0):
    """ Return a formatted and translated time string """

    def unit(single, n):
        if n == 1:
            return sabnzbd.api.Ttemplate(single)
        else:
            return sabnzbd.api.Ttemplate(single + 's')

    seconds = int_conv(seconds)
    completestr = []
    if days:
        completestr.append('%s %s' % (days, unit('day', days)))
    if (seconds / 3600) >= 1:
        completestr.append('%s %s' % (seconds / 3600, unit('hour', (seconds / 3600))))
        seconds -= (seconds / 3600) * 3600
    if (seconds / 60) >= 1:
        completestr.append('%s %s' % (seconds / 60, unit('minute', (seconds / 60))))
        seconds -= (seconds / 60) * 60
    if seconds > 0:
        completestr.append('%s %s' % (seconds, unit('second', seconds)))
    elif not completestr:
        completestr.append('0 %s' % unit('second', 0))

    return ' '.join(completestr)


def int_conv(value):
    """ Safe conversion to int (can handle None) """
    try:
        value = int(value)
    except:
        value = 0
    return value


##############################################################################
# Diskfree
##############################################################################
def find_dir(p):
    """ Return first folder level that exists in this path """
    x = 'x'
    while x and not os.path.exists(p):
        p, x = os.path.split(p)
    return p


if sabnzbd.WIN32:
    # windows diskfree
    try:
        # Careful here, because win32api test hasn't been done yet!
        import win32api
    except:
        pass

    def diskfree(_dir):
        """ Return amount of free diskspace in GBytes """
        _dir = find_dir(_dir)
        try:
            available, disk_size, total_free = win32api.GetDiskFreeSpaceEx(_dir)
            return available / GIGI
        except:
            return 0.0

    def disktotal(_dir):
        """ Return amount of free diskspace in GBytes """
        _dir = find_dir(_dir)
        try:
            available, disk_size, total_free = win32api.GetDiskFreeSpaceEx(_dir)
            return disk_size / GIGI
        except:
            return 0.0
else:
    try:
        os.statvfs
        # posix diskfree

        def diskfree(_dir):
            """ Return amount of free diskspace in GBytes """
            _dir = find_dir(_dir)
            try:
                s = os.statvfs(_dir)
                if s.f_bavail < 0:
                    return float(sys.maxint) * float(s.f_frsize) / GIGI
                else:
                    return float(s.f_bavail) * float(s.f_frsize) / GIGI
            except OSError:
                return 0.0

        def disktotal(_dir):
            """ Return amount of total diskspace in GBytes """
            _dir = find_dir(_dir)
            try:
                s = os.statvfs(_dir)
                if s.f_blocks < 0:
                    return float(sys.maxint) * float(s.f_frsize) / GIGI
                else:
                    return float(s.f_blocks) * float(s.f_frsize) / GIGI
            except OSError:
                return 0.0
    except ImportError:
        def diskfree(_dir):
            return 10.0

        def disktotal(_dir):
            return 20.0


def create_https_certificates(ssl_cert, ssl_key):
    """ Create self-signed HTTPS certificates and store in paths 'ssl_cert' and 'ssl_key' """
    try:
        from OpenSSL import crypto
        from sabnzbd.utils.certgen import createKeyPair, createCertRequest, createCertificate, \
             TYPE_RSA, serial
    except:
        logging.warning(T('pyopenssl module missing, please install for https access'))
        return False

    # Create the CA Certificate
    cakey = createKeyPair(TYPE_RSA, 1024)
    careq = createCertRequest(cakey, CN='Certificate Authority')
    cacert = createCertificate(careq, (careq, cakey), serial, (0, 60 * 60 * 24 * 365 * 10))  # ten years

    cname = 'SABnzbd'
    pkey = createKeyPair(TYPE_RSA, 1024)
    req = createCertRequest(pkey, CN=cname)
    cert = createCertificate(req, (cacert, cakey), serial, (0, 60 * 60 * 24 * 365 * 10))  # ten years

    # Save the key and certificate to disk
    try:
        open(ssl_key, 'w').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
        open(ssl_cert, 'w').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    except:
        logging.error(T('Error creating SSL key and certificate'))
        logging.info("Traceback: ", exc_info=True)
        return False

    return True


def find_on_path(targets):
    """ Search the PATH for a program and return full path """
    if sabnzbd.WIN32:
        paths = os.getenv('PATH').split(';')
    else:
        paths = os.getenv('PATH').split(':')

    if isinstance(targets, basestring):
        targets = (targets, )

    for path in paths:
        for target in targets:
            target_path = os.path.abspath(os.path.join(path, target))
            if os.path.isfile(target_path) and os.access(target_path, os.X_OK):
                return target_path
    return None


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
        if program:
            program = [program]

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
        p.wait()
        for line in output.split('\n'):
            m = _RE_IP4.search(line)
            if not (m and m.group(2)):
                m = _RE_IP6.search(line)
            if m and m.group(2):
                ips.append(m.group(2))
    return ips


def renamer(old, new):
    """ Rename file/folder with retries for Win32 """
    # Sanitize last part of new name
    path, name = os.path.split(new)
    # Use the more stringent folder rename to end up with a nicer name,
    # but do not trim size
    new = os.path.join(path, sanitize_foldername(name, False))

    logging.debug('Renaming "%s" to "%s"', old, new)
    if sabnzbd.WIN32:
        retries = 15
        while retries > 0:
            try:
                shutil.move(old, new)
                return
            except WindowsError, err:
                logging.debug('Error renaming "%s" to "%s" <%s>', old, new, err)
                if err[0] == 32:
                    logging.debug('Retry rename %s to %s', old, new)
                    retries -= 1
                else:
                    raise WindowsError(err)
            time.sleep(3)
        raise WindowsError(err)
    else:
        shutil.move(old, new)


def remove_dir(path):
    """ Remove directory with retries for Win32 """
    if sabnzbd.WIN32:
        retries = 15
        while retries > 0:
            try:
                os.rmdir(path)
                return
            except WindowsError, err:
                if err[0] == 32:
                    logging.debug('Retry delete %s', path)
                    retries -= 1
                else:
                    raise WindowsError(err)
            time.sleep(3)
        raise WindowsError(err)
    else:
        os.rmdir(path)


def remove_all(path, pattern='*', keep_folder=False, recursive=False):
    """ Remove folder and all its content (optionally recursive) """
    if os.path.exists(path):
        files = globber_full(path, pattern)
        if pattern == '*' and not sabnzbd.WIN32:
            files.extend(globber_full(path, '.*'))

        for f in files:
            if os.path.isfile(f):
                try:
                    os.remove(f)
                except:
                    logging.info('Cannot remove file %s', f)
            elif recursive:
                remove_all(f, pattern, False, True)
        if not keep_folder:
            try:
                os.rmdir(path)
            except:
                logging.info('Cannot remove folder %s', path)


def is_writable(path):
    """ Return True is file is writable (also when non-existent) """
    if os.path.isfile(path):
        return bool(os.stat(path).st_mode & stat.S_IWUSR)
    else:
        return True


def format_source_url(url):
    """ Format URL suitable for 'Source' stage """
    if _HAVE_SSL:
        prot = 'https'
    else:
        prot = 'http:'
    return url


def get_base_url(url):
    RE_URL = re.compile(r'://([^/]+)/')
    m = RE_URL.search(url)
    if m:
        return m.group(1)
    else:
        return ''


def match_str(text, matches):
    """ Return first matching element of list 'matches' in 'text', otherwise None """
    for match in matches:
        if match in text:
            return match
    return None


def starts_with_path(path, prefix):
    """ Return True if 'path' starts with 'prefix',
        considering case-sensitivity of the file system
    """
    if sabnzbd.WIN32:
        return clip_path(path).lower().startswith(prefix.lower())
    elif sabnzbd.DARWIN:
        return path.lower().startswith(prefix.lower())
    else:
        return path.startswith(prefix)


def set_chmod(path, permissions, report):
    """ Set 'permissions' on 'path', report any errors when 'report' is True """
    try:
        os.chmod(path, permissions)
    except:
        lpath = path.lower()
        if report and '.appledouble' not in lpath and '.ds_store' not in lpath:
            logging.error(T('Cannot change permissions of %s'), clip_path(path))
            logging.info("Traceback: ", exc_info=True)


def set_permissions(path, recursive=True):
    """ Give folder tree and its files their proper permissions """
    if not sabnzbd.WIN32:
        umask = cfg.umask()
        try:
            # Make sure that user R+W+X is on
            umask = int(umask, 8) | int('0700', 8)
            report = True
        except ValueError:
            # No or no valid permissions
            # Use the effective permissions of the session
            # Don't report errors (because the system might not support it)
            umask = int('0777', 8) & (sabnzbd.ORG_UMASK ^ int('0777', 8))
            report = False

        # Remove X bits for files
        umask_file = umask & int('7666', 8)

        if os.path.isdir(path):
            if recursive:
                # Parse the dir/file tree and set permissions
                for root, _dirs, files in os.walk(path):
                    set_chmod(root, umask, report)
                    for name in files:
                        set_chmod(os.path.join(root, name), umask_file, report)
            else:
                set_chmod(path, umask, report)
        else:
            set_chmod(path, umask_file, report)


def short_path(path, always=True):
    """ For Windows, return shortened ASCII path, for others same path
        When `always` is off, only return a short path when size is above 259
    """
    if sabnzbd.WIN32:
        import win32api
        path = os.path.normpath(path)
        if always or len(path) > 259:
            # First make the path "long"
            path = long_path(path)
            if os.path.exists(path):
                # Existing path can always be shortened
                path = win32api.GetShortPathName(path)
            else:
                # For new path, shorten only existing part (recursive)
                path1, name = os.path.split(path)
                path = os.path.join(short_path(path1, always), name)
        path = clip_path(path)
    return path


def clip_path(path):
    """ Remove \\?\ or \\?\UNC\ prefix from Windows path """
    if sabnzbd.WIN32 and path and '?' in path:
        path = path.replace(u'\\\\?\\UNC\\', u'\\\\').replace(u'\\\\?\\', u'')
    return path


def long_path(path):
    """ For Windows, convert to long style path; others, return same path """
    if sabnzbd.WIN32 and path and not path.startswith(u'\\\\?\\'):
        if path.startswith('\\\\'):
            # Special form for UNC paths
            path = path.replace(u'\\\\', u'\\\\?\\UNC\\', 1)
        else:
            # Normal form for local paths
            path = u'\\\\?\\' + path
    return path


def fix_unix_encoding(folder):
    """ Fix bad name encoding for Unix systems """
    if not sabnzbd.WIN32 and not sabnzbd.DARWIN and gUTF:
        for root, dirs, files in os.walk(folder.encode('utf-8')):
            for name in files:
                new_name = special_fixer(name).encode('utf-8')
                if name != new_name:
                    try:
                        shutil.move(os.path.join(root, name), os.path.join(root, new_name))
                    except:
                        logging.info('Cannot correct name of %s', os.path.join(root, name))


def get_urlbase(url):
    """ Return the base URL (like http://server.domain.com/) """
    parsed_uri = urlparse(url)
    return '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
