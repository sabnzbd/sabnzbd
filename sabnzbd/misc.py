#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
import urllib.request, urllib.parse, urllib.error
import re
import shutil
import threading
import subprocess
import socket
import time
import datetime
import fnmatch
import stat
import inspect
import urllib2
from urlparse import urlparse

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import DEFAULT_PRIORITY, FUTURE_Q_FOLDER, JOB_ADMIN, \
     GIGI, MEBI, DEF_CACHE_LIMIT
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.encoding import unicoder, special_fixer, gUTF

TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')
RE_UNITS = re.compile(r'(\d+\.*\d*)\s*([KMGTP]{0,1})', re.I)
RE_VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_IP4 = re.compile(r'inet\s+(addr:\s*){0,1}(\d+\.\d+\.\d+\.\d+)')
RE_IP6 = re.compile(r'inet6\s+(addr:\s*){0,1}([0-9a-f:]+)', re.I)

# Check if strings are defined for AM and PM
HAVE_AMPM = bool(time.strftime('%p', time.localtime()))


def time_format(fmt):
    """ Return time-format string adjusted for 12/24 hour clock setting """
    if cfg.ampm() and HAVE_AMPM:
        return fmt.replace('%H:%M:%S', '%I:%M:%S %p').replace('%H:%M', '%I:%M %p')
    else:
        return fmt


def calc_age(date, trans=False):
    """ Calculate the age difference between now and date.
        Value is returned as either days, hours, or minutes.
        When 'trans' is True, time symbols will be translated.
    """
    if trans:
        d = T('d')  # : Single letter abbreviation of day
        h = T('h')  # : Single letter abbreviation of hour
        m = T('m')  # : Single letter abbreviation of minute
    else:
        d = 'd'
        h = 'h'
        m = 'm'
    try:
        now = datetime.datetime.now()
        # age = str(now - date).split(".")[0] #old calc_age

        # time difference
        dage = now - date
        seconds = dage.seconds
        # only one value should be returned
        # if it is less than 1 day then it returns in hours, unless it is less than one hour where it returns in minutes
        if dage.days:
            age = '%s%s' % (dage.days, d)
        elif seconds / 3600:
            age = '%s%s' % (seconds / 3600, h)
        else:
            age = '%s%s' % (seconds / 60, m)
    except:
        age = "-"

    return age


def monthrange(start, finish):
    """ Calculate months between 2 dates, used in the Config template """
    months = (finish.year - start.year) * 12 + finish.month + 1
    for i in range(start.month, months):
        year  = (i - 1) / 12 + start.year
        month = (i - 1) % 12 + 1
        yield datetime.date(year, month, 1)


def safe_lower(txt):
    """ Return lowercased string. Return '' for None """
    if txt:
        return txt.lower()
    else:
        return ''


def safe_fnmatch(f, pattern):
    """ fnmatch will fail if the pattern contains any of it's
        key characters, like [, ] or !.
    """
    try:
        return fnmatch.fnmatch(f, pattern)
    except re.error:
        return False


def globber(path, pattern='*'):
    """ Return matching base file/folder names in folder `path` """
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        return [f for f in os.listdir(path) if safe_fnmatch(f, pattern)]
    return []


def globber_full(path, pattern='*'):
    """ Return matching full file/folder names in folder `path` """
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        try:
            return [os.path.join(path, f) for f in os.listdir(path) if safe_fnmatch(f, pattern)]
        except UnicodeDecodeError:
            # This happens on Linux when names are incorrectly encoded, retry using a non-Unicode path
            path = path.encode('utf-8')
            return [os.path.join(path, f) for f in os.listdir(path) if safe_fnmatch(f, pattern)]
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

    if priority is None or priority == '' or priority == DEFAULT_PRIORITY:
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
        If no match found, but the indexer-cat starts with the user-cat, return user-cat
        If no match found, return None
    """
    if cat and cat.lower() != 'none':
        cats = config.get_ordered_categories()
        raw_cats = config.get_categories()
        for ucat in cats:
            try:
                # Ordered cat-list has tags only as string
                indexer = raw_cats[ucat['name']].newzbin()
                if not isinstance(indexer, list):
                    indexer = [indexer]
            except:
                indexer = []
            for name in indexer:
                if re.search('^%s$' % wildcard_to_re(name), cat, re.I):
                    if '.' in name:
                        logging.debug('Convert group "%s" to user-cat "%s"', cat, ucat['name'])
                    else:
                        logging.debug('Convert index site category "%s" to user-cat "%s"', cat, ucat['name'])
                    return ucat['name']

        # Try to find full match between user category and indexer category
        for ucat in cats:
            if cat.lower() == ucat['name'].lower():
                logging.debug('Convert index site category "%s" to user-cat "%s"', cat, ucat['name'])
                return ucat['name']

        # Try to find partial match between user category and indexer category
        for ucat in cats:
            if cat.lower().startswith(ucat['name'].lower()):
                logging.debug('Convert index site category "%s" to user-cat "%s"', cat, ucat['name'])
                return ucat['name']

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

    # Remove special NTFS filename
    if lname.startswith('$mft'):
        name = name.replace('$', 'S', 1)

    return name


def has_win_device(p):
    """ Return True if filename part contains forbidden name
        Before and after sanitizing
    """
    p = os.path.split(p)[1].lower()
    for dev in _DEVICES:
        if p == dev or p.startswith(dev + '.') or p.startswith('_' + dev + '.'):
            return True
    return False


if sabnzbd.WIN32:
    # the colon should be here too, but we'll handle that separately
    CH_ILLEGAL = '\/<>?*|"\t'
    CH_LEGAL = '++{}!@#`+'
else:
    CH_ILLEGAL = '/'
    CH_LEGAL = '+'


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

    if sabnzbd.WIN32 or cfg.sanitize_safe():
        name = replace_win_devices(name)

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

    if isinstance(name, str):
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

    if sabnzbd.WIN32 or cfg.sanitize_safe():
        name = replace_win_devices(name)

    maxlen = cfg.folder_max_length()
    if limit and len(name) > maxlen:
        name = name[:maxlen]

    # And finally, make sure it doesn't end in a dot
    if name != '.' and name != '..':
        name = name.rstrip('.')
    if not name:
        name = 'unknown'

    return name


def sanitize_and_trim_path(path):
    """ Remove illegal characters and trim element size """
    path = path.strip()
    new_path = ''
    if sabnzbd.WIN32:
        if path.startswith('\\\\?\\UNC\\'):
            new_path = '\\\\?\\UNC\\'
            path = path[8:]
        elif path.startswith('\\\\?\\'):
            new_path = '\\\\?\\'
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


def sanitize_files_in_folder(folder):
    """ Sanitize each file in the folder, return list of new names
    """
    lst = []
    for root, _, files in os.walk(folder):
        for file_ in files:
            path = os.path.join(root, file_)
            new_path = os.path.join(root, sanitize_filename(file_))
            if path != new_path:
                try:
                    os.rename(path, new_path)
                    path = new_path
                except:
                    logging.debug('Cannot rename %s to %s', path, new_path)
            lst.append(path)
    return lst


def is_obfuscated_filename(filename):
    """ Check if this file has an extension, if not, it's
        probably obfuscated and we don't use it
    """
    return (os.path.splitext(filename)[1] == '')


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
                                os.chmod(path, int(mask, 8) | 0o700)
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


def is_relative_path(p):
    """ Return True if path is relative """
    p = p.replace('\\', '/')
    if p and p[0] == '/':
        return False
    if sabnzbd.WIN32 and p and len(p) > 2:
        if p[0].isalpha() and p[1] == ':' and p[2] == '/':
            return False
    return True


def windows_variant():
    """ Determine Windows variant
        Return vista_plus, x64
    """
    from win32api import GetVersionEx
    from win32con import VER_PLATFORM_WIN32_NT
    import winreg

    vista_plus = x64 = False
    maj, _minor, _buildno, plat, _csd = GetVersionEx()

    if plat == VER_PLATFORM_WIN32_NT:
        vista_plus = maj > 5
        if vista_plus:
            # Must be done the hard way, because the Python runtime lies to us.
            # This does *not* work:
            #     return os.environ['PROCESSOR_ARCHITECTURE'] == 'AMD64'
            # because the Python runtime returns 'X86' even on an x64 system!
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
            for n in range(winreg.QueryInfoKey(key)[1]):
                name, value, _val_type = winreg.EnumValue(key, n)
                if name == 'PROCESSOR_ARCHITECTURE':
                    x64 = value.upper() == 'AMD64'
                    break
            winreg.CloseKey(key)

    return vista_plus, x64


_SERVICE_KEY = 'SYSTEM\\CurrentControlSet\\services\\'
_SERVICE_PARM = 'CommandLine'


def get_serv_parms(service):
    """ Get the service command line parameters from Registry """
    import winreg

    value = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        for n in range(winreg.QueryInfoKey(key)[1]):
            name, value, _val_type = winreg.EnumValue(key, n)
            if name == _SERVICE_PARM:
                break
        winreg.CloseKey(key)
    except WindowsError:
        pass
    for n in range(len(value)):
        value[n] = value[n]
    return value


def set_serv_parms(service, args):
    """ Set the service command line parameters in Registry """
    import winreg

    uargs = []
    for arg in args:
        uargs.append(unicoder(arg))

    try:
        key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        winreg.SetValueEx(key, _SERVICE_PARM, None, winreg.REG_MULTI_SZ, uargs)
        winreg.CloseKey(key)
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
        fn = urllib.request.urlretrieve('https://raw.githubusercontent.com/sabnzbd/sabnzbd.github.io/master/latest.txt')[0]
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

    logging.debug('Checked for a new release, cur= %s, latest= %s (on %s), latest_test= %s (on %s)',
                  current, latest, url, latest_test, url_beta)

    if latest_test and cfg.version_check() > 1:
        # User always wants to see the latest test release
        latest = latest_test
        latest_label = latest_testlabel
        url = url_beta

    if testver and current < latest:
        # This is a test version, but user has't seen the
        # "Final" of this one yet, so show the Final
        sabnzbd.NEW_VERSION = (latest_label, url)
    elif current < latest:
        # This one is behind, show latest final
        sabnzbd.NEW_VERSION = (latest_label, url)
    elif testver and current < latest_test:
        # This is a test version beyond the latest Final, so show latest Alpha/Beta/RC
        sabnzbd.NEW_VERSION = (latest_testlabel, url_beta)


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


def caller_name(skip=2):
    """Get a name of a caller in the format module.method
       Originally used: https://gist.github.com/techtonik/2151727
       Adapted for speed by using sys calls directly
    """
    # Only do the tracing on Debug (function is always called)
    if cfg.log_level() != 2:
        return 'N/A'

    parentframe = sys._getframe(skip)
    function_name = parentframe.f_code.co_name

    # Modulename not available in the binaries, we can use the filename instead
    if getattr(sys, 'frozen', None):
        module_name = inspect.getfile(parentframe)
    else:
        module_name = inspect.getmodule(parentframe).__name__

    # For decorated functions we have to go deeper
    if function_name in ('call_func', 'wrap') and skip == 2:
        return caller_name(4)

    return ".".join([module_name, function_name])


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
        from PyObjCTools import AppHelper
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


def get_from_url(url):
    """ Retrieve URL and return content """
    try:
        return urllib2.urlopen(url).read()
    except:
        return None


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
        for n in range(cfg.wait_ext_drive() or 1):
            if os.path.exists(m.group(1)):
                return True
            logging.debug('Waiting for %s to come online', m.group(1))
            time.sleep(1)
    return not m


def get_cache_limit():
    """ Depending on OS, calculate cache limit """
    # OSX/Windows use Default value
    if sabnzbd.WIN32 or sabnzbd.DARWIN:
        return DEF_CACHE_LIMIT

    # Calculate, if possible
    try:
        # Use 1/4th of available memory
        mem_bytes = (os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES'))/4
        # Not more than the maximum we think is reasonable
        if mem_bytes > from_units(DEF_CACHE_LIMIT):
            return DEF_CACHE_LIMIT
        elif mem_bytes > from_units('32M'):
            # We make sure it's at least a valid value
            return to_units(mem_bytes)
    except:
        pass
    # If failed, leave empty so user needs to decide
    return ''


##############################################################################
# Locked directory operations to avoid problems with simultaneous add/remove
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
    """ Check if path is unique.
        If not, add number like: "/path/name.NUM.ext".
    """
    num = 1
    new_path, fname = os.path.split(path)
    name, ext = os.path.splitext(fname)
    while os.path.exists(path):
        fname = "%s.%d%s" % (name, num, ext)
        num += 1
        path = os.path.join(new_path, fname)
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
            remove_file(new_path)
        except:
            overwrite = False
    if not overwrite:
        new_path = get_unique_filename(new_path)

    if new_path:
        logging.debug("Moving (overwrite: %s) %s => %s", overwrite, path, new_path)
        try:
            # First try cheap rename
            renamer(path, new_path)
        except:
            # Cannot rename, try copying
            logging.debug("File could not be renamed, trying copying: %s", path)
            try:
                if not os.path.exists(os.path.dirname(new_path)):
                    create_dirs(os.path.dirname(new_path))
                shutil.copyfile(path, new_path)
                remove_file(path)
            except:
                # Check if the old-file actually exists (possible delete-delays)
                if not os.path.exists(path):
                    logging.debug("File not moved, original path gone: %s", path)
                    return True, None
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
    dName = nzo.work_name
    if not nzo.created:
        for n in range(200):
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


@synchronized(DIR_LOCK)
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
            # First we try 3 times with os.rename
            if retries > 12:
                try:
                    os.rename(old, new)
                    return
                except:
                    retries -= 1
                    time.sleep(3)
                    continue

            # Now we try the back-up method
            logging.debug('Could not rename, trying move for %s to %s', old, new)
            try:
                shutil.move(old, new)
                return
            except WindowsError as err:
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


@synchronized(DIR_LOCK)
def remove_dir(path):
    """ Remove directory with retries for Win32 """
    if sabnzbd.WIN32:
        retries = 15
        while retries > 0:
            try:
                remove_dir(path)
                return
            except WindowsError as err:
                if err[0] == 32:
                    logging.debug('Retry delete %s', path)
                    retries -= 1
                else:
                    raise WindowsError(err)
            time.sleep(3)
        raise WindowsError(err)
    else:
        remove_dir(path)


@synchronized(DIR_LOCK)
def remove_all(path, pattern='*', keep_folder=False, recursive=False):
    """ Remove folder and all its content (optionally recursive) """
    if os.path.exists(path):
        files = globber_full(path, pattern)
        if pattern == '*' and not sabnzbd.WIN32:
            files.extend(globber_full(path, '.*'))

        for f in files:
            if os.path.isfile(f):
                try:
                    remove_file(f)
                except:
                    logging.info('Cannot remove file %s', f)
            elif recursive:
                remove_all(f, pattern, False, True)
        if not keep_folder:
            try:
                remove_dir(path)
            except:
                logging.info('Cannot remove folder %s', path)


def remove_file(path):
    """ Wrapper function so any file removal is logged """
    logging.debug('[%s] Deleting file %s', caller_name(), path)
    os.remove(path)


def remove_dir(dir):
    """ Wrapper function so any dir removal is logged """
    logging.debug('[%s] Deleting dir %s', caller_name(), dir)
    os.rmdir(dir)


def trim_win_path(path):
    """ Make sure Windows path stays below 70 by trimming last part """
    if sabnzbd.WIN32 and len(path) > 69:
        path, folder = os.path.split(path)
        maxlen = 69 - len(path)
        if len(folder) > maxlen:
            folder = folder[:maxlen]
        path = os.path.join(path, folder).rstrip('. ')
    return path


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

    def diskspace_base(_dir):
        """ Return amount of free and used diskspace in GBytes """
        _dir = find_dir(_dir)
        try:
            available, disk_size, total_free = win32api.GetDiskFreeSpaceEx(_dir)
            return disk_size / GIGI, available / GIGI
        except:
            return 0.0, 0.0

else:
    try:
        os.statvfs
        # posix diskfree
        def diskspace_base(_dir):
            """ Return amount of free and used diskspace in GBytes """
            _dir = find_dir(_dir)
            try:
                s = os.statvfs(_dir)
                if s.f_blocks < 0:
                    disk_size = float(sys.maxsize) * float(s.f_frsize)
                else:
                    disk_size = float(s.f_blocks) * float(s.f_frsize)
                if s.f_bavail < 0:
                    available = float(sys.maxsize) * float(s.f_frsize)
                else:
                    available = float(s.f_bavail) * float(s.f_frsize)
                return disk_size / GIGI, available / GIGI
            except:
                return 0.0, 0.0
    except ImportError:
        def diskspace_base(_dir):
            return 20.0, 10.0


# Store all results to speed things up
__DIRS_CHECKED = []
__DISKS_SAME = None
__LAST_DISK_RESULT = {'download_dir': [], 'complete_dir': []}
__LAST_DISK_CALL = 0

def diskspace(force=False):
    """ Wrapper to cache results """
    global __DIRS_CHECKED, __DISKS_SAME, __LAST_DISK_RESULT, __LAST_DISK_CALL

    # Reset everything when folders changed
    dirs_to_check = [cfg.download_dir.get_path(), cfg.complete_dir.get_path()]
    if __DIRS_CHECKED != dirs_to_check:
        __DIRS_CHECKED = dirs_to_check
        __DISKS_SAME = None
        __LAST_DISK_RESULT = {'download_dir': [], 'complete_dir': []}
        __LAST_DISK_CALL = 0

    # When forced, ignore any cache to avoid problems in UI
    if force:
        __LAST_DISK_CALL = 0

    # Check against cache
    if time.time() > __LAST_DISK_CALL + 10.0:
        # Same disk? Then copy-paste
        __LAST_DISK_RESULT['download_dir'] = diskspace_base(cfg.download_dir.get_path())
        __LAST_DISK_RESULT['complete_dir'] = __LAST_DISK_RESULT['download_dir'] if __DISKS_SAME else diskspace_base(cfg.complete_dir.get_path())
        __LAST_DISK_CALL = time.time()

    # Do we know if it's same disk?
    if __DISKS_SAME is None:
        __DISKS_SAME = (__LAST_DISK_RESULT['download_dir'] == __LAST_DISK_RESULT['complete_dir'])

    return __LAST_DISK_RESULT


##############################################################################
# Other support functions
##############################################################################
def create_https_certificates(ssl_cert, ssl_key):
    """ Create self-signed HTTPS certificates and store in paths 'ssl_cert' and 'ssl_key' """
    if not sabnzbd.HAVE_CRYPTOGRAPHY:
        logging.error(T('%s missing'), 'Python Cryptography')
        return False

    # Save the key and certificate to disk
    try:
        from sabnzbd.utils.certgen import generate_key, generate_local_cert
        private_key = generate_key(key_size=2048, output_file=ssl_key)
        generate_local_cert(private_key, days_valid=3560, output_file=ssl_cert, LN='SABnzbd', ON='SABnzbd', CN='localhost')
        logging.info('Self-signed certificates generated successfully')
    except:
        logging.error(T('Error creating SSL key and certificate'))
        logging.info("Traceback: ", exc_info=True)
        return False

    return True


def get_all_passwords(nzo):
    """ Get all passwords, from the NZB, meta and password file """
    if nzo.password:
        logging.info('Found a password that was set by the user: %s', nzo.password)
        passwords = [nzo.password.strip()]
    else:
        passwords = []

    meta_passwords = nzo.meta.get('password', [])
    pw = nzo.nzo_info.get('password')
    if pw:
        meta_passwords.append(pw)

    if meta_passwords:
        if nzo.password == meta_passwords[0]:
            # this nzo.password came from meta, so don't use it twice
            passwords.extend(meta_passwords[1:])
        else:
            passwords.extend(meta_passwords)
        logging.info('Read %s passwords from meta data in NZB: %s', len(meta_passwords), meta_passwords)

    pw_file = cfg.password_file.get_path()
    if pw_file:
        try:
            with open(pw_file, 'r') as pwf:
                lines = pwf.read().split('\n')
            # Remove empty lines and space-only passwords and remove surrounding spaces
            pws = [pw.strip('\r\n ') for pw in lines if pw.strip('\r\n ')]
            logging.debug('Read these passwords from file: %s', pws)
            passwords.extend(pws)
            logging.info('Read %s passwords from file %s', len(pws), pw_file)

            # Check size
            if len(pws) > 30:
                logging.warning(T('Your password file contains more than 30 passwords, testing all these passwords takes a lot of time. Try to only list useful passwords.'))
        except:
            logging.warning('Failed to read the passwords file %s', pw_file)

    if nzo.password:
        # If an explicit password was set, add a retry without password, just in case.
        passwords.append('')
    elif not passwords or nzo.encrypted < 1:
        # If we're not sure about encryption, start with empty password
        # and make sure we have at least the empty password
        passwords.insert(0, '')
    return passwords


def find_on_path(targets):
    """ Search the PATH for a program and return full path """
    if sabnzbd.WIN32:
        paths = os.getenv('PATH').split(';')
    else:
        paths = os.getenv('PATH').split(':')

    if isinstance(targets, str):
        targets = (targets, )

    for path in paths:
        for target in targets:
            target_path = os.path.abspath(os.path.join(path, target))
            if os.path.isfile(target_path) and os.access(target_path, os.X_OK):
                return target_path
    return None


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
            m = RE_IP4.search(line)
            if not (m and m.group(2)):
                m = RE_IP6.search(line)
            if m and m.group(2):
                ips.append(m.group(2))
    return ips


def is_writable(path):
    """ Return True is file is writable (also when non-existent) """
    if os.path.isfile(path):
        return bool(os.stat(path).st_mode & stat.S_IWUSR)
    else:
        return True


def get_base_url(url):
    """ Return only the true root domain for the favicon, so api.oznzb.com -> oznzb.com
        But also api.althub.co.za -> althub.co.za
    """
    url_host = urlparse(url).hostname
    if url_host:
        url_split = url_host.split(".")
        # Exception for localhost and IPv6 addresses
        if len(url_split) < 3:
            return url_host
        return ".".join(len(url_split[-2]) < 4 and url_split[-3:] or url_split[-2:])
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
        logging.debug('Applying permissions %s (octal) to %s', oct(permissions), path)
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


def clip_path(path):
    r""" Remove \\?\ or \\?\UNC\ prefix from Windows path """
    if sabnzbd.WIN32 and path and '?' in path:
        path = path.replace('\\\\?\\UNC\\', '\\\\', 1).replace('\\\\?\\', '', 1)
    return path


def long_path(path):
    """ For Windows, convert to long style path; others, return same path """
    if sabnzbd.WIN32 and path and not path.startswith('\\\\?\\'):
        if path.startswith('\\\\'):
            # Special form for UNC paths
            path = path.replace('\\\\', '\\\\?\\UNC\\', 1)
        else:
            # Normal form for local paths
            path = '\\\\?\\' + path
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


def nntp_to_msg(text):
    """ Format raw NNTP data for display """
    if isinstance(text, list):
        text = text[0]
    lines = text.split('\r\n')
    return lines[0]
