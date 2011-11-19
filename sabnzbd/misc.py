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
import glob
import stat

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import DEFAULT_PRIORITY, FUTURE_Q_FOLDER, JOB_ADMIN, GIGI, VERIFIED_FILE
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.encoding import unicoder, latin1

RE_VERSION = re.compile('(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_UNITS = re.compile('(\d+\.*\d*)\s*([KMGTP]{0,1})', re.I)
TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')

# Check if strings are defined for AM and PM
HAVE_AMPM = bool(time.strftime('%p', time.localtime()))

#------------------------------------------------------------------------------
def time_format(format):
    """ Return time-format string adjusted for 12/24 hour clock setting
    """
    if cfg.ampm() and HAVE_AMPM:
        return format.replace('%H:%M:%S', '%I:%M:%S %p').replace('%H:%M', '%I:%M %p')
    else:
        return format

#------------------------------------------------------------------------------
def safe_lower(txt):
    """ Return lowercased string. Return '' for None
    """
    if txt:
        return txt.lower()
    else:
        return ''

#------------------------------------------------------------------------------
def globber(path, pattern='*'):
    """ Do a glob.glob(), disabling the [] pattern in 'path' """
    return glob.glob(os.path.join(path, pattern).replace('[', '[[]'))


#------------------------------------------------------------------------------
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

    #logging.debug('Cat->Attrib cat=%s pp=%s script=%s prio=%s', cat, pp, script, priority)
    return cat, pp, script, priority


#------------------------------------------------------------------------------
_wildcard_to_regex = {
    '\\': r'\\',
    '^' : r'\^',
    '$' : r'\$',
    '.' : r'\.',
    '[' : r'\[',
    ']' : r'\]',
    '(' : r'\(',
    ')' : r'\)',
    '+' : r'\+',
    '?' : r'.' ,
    '|' : r'\|',
    '{' : r'\{',
    '}' : r'\}',
    '*' : r'.*'
}
def wildcard_to_re(text):
    """ Convert plain wildcard string (with '*' and '?') to regex.
    """
    return ''.join([_wildcard_to_regex.get(ch, ch) for ch in text])

#------------------------------------------------------------------------------
def cat_convert(cat):
    """ Convert newzbin/nzbs.org category/group-name to user categories.
        If no match found, but newzbin-cat equals user-cat, then return user-cat
        If no match found, return None
    """
    newcat = cat
    found = False

    if cat and cat.lower() != 'none':
        cats = config.get_categories()
        for ucat in cats:
            try:
                newzbin = cats[ucat].newzbin()
                if type(newzbin) != type([]):
                    newzbin = [newzbin]
            except:
                newzbin = []
            for name in newzbin:
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


################################################################################
# sanitize_filename                                                            #
################################################################################
if sabnzbd.WIN32:
    # the colon should be here too, but we'll handle that separately
    CH_ILLEGAL = r'\/<>?*|"'
    CH_LEGAL   = r'++{}!@#`'
else:
    CH_ILLEGAL = r'/'
    CH_LEGAL   = r'+'

def sanitize_filename(name):
    """ Return filename with illegal chars converted to legal ones
        and with the par2 extension always in lowercase
    """
    if not name:
        return name
    illegal = CH_ILLEGAL
    legal   = CH_LEGAL

    if ':' in name:
        if sabnzbd.WIN32:
            # Compensate for the odd way par2 on Windows substitutes a colon character
            name = name.replace(':', '3A')
        elif sabnzbd.DARWIN:
            # Compensate for the foolish way par2 on OSX handles a colon character
            name = name[name.rfind(':')+1:]

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

FL_ILLEGAL = CH_ILLEGAL + ':\x92"'
FL_LEGAL   = CH_LEGAL +   "-''"
uFL_ILLEGAL = FL_ILLEGAL.decode('latin-1')
uFL_LEGAL   = FL_LEGAL.decode('latin-1')

def sanitize_foldername(name):
    """ Return foldername with dodgy chars converted to safe ones
        Remove any leading and trailing dot and space characters
    """
    if not name:
        return name
    if isinstance(name, unicode):
        illegal = uFL_ILLEGAL
        legal   = uFL_LEGAL
    else:
        illegal = FL_ILLEGAL
        legal   = FL_LEGAL

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

    name = name.strip('. ')
    if not name:
        name = 'unknown'

    maxlen = cfg.folder_max_length()
    if len(name) > maxlen:
        name = name[:maxlen]

    return name


#------------------------------------------------------------------------------
def verified_flag_file(path, create=False):
    """ Create verify flag file or return True if it already exists """
    path = os.path.join(path, JOB_ADMIN)
    path = os.path.join(path, VERIFIED_FILE)
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
                        mask = cfg.umask()
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
    """ When 'path' is relative, return normalized join of 'loc' and 'path'
        When 'path' is absolute, return normalized path
        A path starting with ~ will be located in the user's Home folder
    """
    if path:
        path = path.strip()
    else:
        path = ''
    if path:
        if not sabnzbd.WIN32 and path.startswith('~/'):
            path = path.replace('~', sabnzbd.DIR_HOME, 1)
        if sabnzbd.WIN32:
            if path[0].isalpha() and len(path) > 1 and path[1] == ':':
                if len(path) == 2 or path[2] not in '\\/':
                    path = path.replace(':', ':\\', 1)
            else:
                path = os.path.join(loc, path)
        elif path[0] != '/':
            path = os.path.join(loc, path)
    else:
        path = loc

    return os.path.normpath(os.path.abspath(path))


################################################################################
# Create_Real_Path                                                             #
################################################################################
def create_real_path(name, loc, path, umask=False):
    """ When 'path' is relative, create join of 'loc' and 'path'
        When 'path' is absolute, create normalized path
        'name' is used for logging.
        Optional 'umask' will be applied.
        Returns ('success', 'full path')
    """
    if path:
        my_dir = real_path(loc, path)
        if not os.path.exists(my_dir):
            logging.info('%s directory: %s does not exist, try to create it', name, my_dir)
            if not create_all_dirs(my_dir, umask):
                logging.error(Ta('Cannot create directory %s'), my_dir)
                return (False, my_dir)

        if os.access(my_dir, os.R_OK + os.W_OK):
            return (True, my_dir)
        else:
            logging.error(Ta('%s directory: %s error accessing'), name, my_dir)
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
    """ Return a dictionary with Windows Special Folders
    """
    import _winreg
    values = {}

    # Open registry hive
    try:
        hive = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    except WindowsError:
        logging.error(Ta('Cannot connect to registry hive HKEY_CURRENT_USER.'))
        return values

    # Then open the registry key where Windows stores the Shell Folder locations
    try:
        key = _winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
    except WindowsError:
        logging.error(Ta('Cannot open registry key "%s".'), r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
        _winreg.CloseKey(hive)
        return values

    try:
        for i in range(0, _winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, i)
            try:
                values[name] = value.encode('latin-1')
            except UnicodeEncodeError:
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
                    values[name] = 'c:\\'
            i += 1
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return values
    except WindowsError:
        # On error, return empty dict.
        logging.error(Ta('Failed to read registry keys for special folders'))
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return {}


#------------------------------------------------------------------------------
def windows_variant():
    """ Determine Windows variant
        Return vista_plus, x64
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


#------------------------------------------------------------------------------

_SERVICE_KEY = 'SYSTEM\\CurrentControlSet\\services\\'
_SERVICE_PARM = 'CommandLine'

def get_serv_parms(service):
    """ Get the service command line parameters from Registry """
    import _winreg

    value = []
    try:
        key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        for n in xrange(_winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, n)
            if name == _SERVICE_PARM:
                break
        _winreg.CloseKey(key)
    except WindowsError:
        pass
    for n in xrange(len(value)):
        value[n] = latin1(value[n])
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
    if not cfg.version_check():
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
        os.remove(fn)
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

def to_units(val, spaces=0, dec_limit=2):
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

    format = '%%s%%.%sf %%s' % decimals
    return format % (sign, val, unit)

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
            a = os.path.normpath(os.path.abspath(a))
            b = os.path.normpath(os.path.abspath(b))
            if sabnzbd.WIN32 or sabnzbd.DARWIN:
                a = a.lower()
                b = b.lower()
            return a == b
        except:
            return False

#------------------------------------------------------------------------------
def exit_sab(value):
    """ Leave the program after flushing stderr/stdout
    """
    sys.stderr.flush()
    sys.stdout.flush()
    sys.exit(value)


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
def hostname():
    """ Return host's pretty name """
    if sabnzbd.WIN32:
        return os.environ.get('computername', 'unknown')
    try:
        return os.uname()[1]
    except:
        return 'unknown'


#------------------------------------------------------------------------------
def check_mount(path):
    """ Return False if volume isn't mounted on Linux or OSX
    """
    if sabnzbd.DARWIN:
        m = re.search(r'^(/Volumes/[^/]+)/', path, re.I)
    elif not sabnzbd.WIN32:
        m = re.search(r'^(/(?:mnt|media)/[^/]+)/', path)
    else:
        m = None
    return (not m) or os.path.exists(m.group(1))


#------------------------------------------------------------------------------
# Locked directory operations

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
        return get_unique_path(dirpath, n=n+1, create_dir=create_dir)

@synchronized(DIR_LOCK)
def get_unique_filename(path):
    """ Check if path is unique. If not, add number like: "/path/name.NUM.ext".
    """
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
            logging.error(Ta('Failed making (%s)'), dirpath)
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
            renamer(path, new_path)
        except:
            # Cannot rename, try copying
            try:
                if not os.path.exists(os.path.dirname(new_path)):
                    create_dirs(os.path.dirname(new_path))
                shutil.copyfile(path, new_path)
                os.remove(path)
            except:
                logging.error(Ta('Failed moving %s to %s'), path, new_path)
                logging.info("Traceback: ", exc_info = True)
    return new_path


@synchronized(DIR_LOCK)
def cleanup_empty_directories(path):
    """ Remove all empty folders inside (and including) 'path'
    """
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
            if n: dName += '.' + str(n)
            try:
                os.mkdir(os.path.join(path, dName))
                break
            except:
                pass
        nzo.work_name = dName
        nzo.created = True

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


def get_admin_path(newstyle, name, future):
    """ Return news-style full path to job-admin folder of names job
        or else the old cache path
    """
    if newstyle:
        if future:
            return os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)
        else:
            return os.path.join(os.path.join(cfg.download_dir.get_path(), name), JOB_ADMIN)
    else:
        return cfg.cache_dir.get_path()

def bad_fetch(nzo, url, msg='', retry=False, content=False):
    """ Create History entry for failed URL Fetch
        msg : message to be logged
        retry : make retry link in histort
        content : report in history that cause is a bad NZB file
    """
    msg = unicoder(msg)

    pp = nzo.pp
    if pp is None:
        pp = ''
    else:
        pp = '&pp=%s' % str(pp)
    cat = nzo.cat
    if cat:
        cat = '&cat=%s' % urllib.quote(cat)
    else:
        cat = ''
    script = nzo.script
    if script:
        script = '&script=%s' % urllib.quote(script)
    else:
        script = ''

    nzo.status = 'Failed'


    if url:
        nzo.filename = url
        nzo.final_name = url.strip()

    if content:
        # Bad content
        msg = T('Unusable NZB file')
    else:
        # Failed fetch
        msg = ' (' + msg + ')'

    if retry:
        nzbname = nzo.custom_name
        if nzbname:
            nzbname = '&nzbname=%s' % urllib.quote(nzbname)
        else:
            nzbname = ''
        text = T('URL Fetching failed; %s') + ', <a href="./retry?session=%s&url=%s%s%s%s%s">' + T('Try again') + '</a>'
        parms = (msg, cfg.api_key(), urllib.quote(url), pp, cat, script, nzbname)
        nzo.fail_msg = text % parms
    else:
        nzo.fail_msg = msg

    from sabnzbd.nzbqueue import NzbQueue
    assert isinstance(NzbQueue.do, NzbQueue)
    NzbQueue.do.remove(nzo.nzo_id, add_to_history=True)


def on_cleanup_list(filename, skip_nzb=False):
    """ Return True if a filename matches the clean-up list
    """
    lst = cfg.cleanup_list()
    if lst:
        ext = os.path.splitext(filename)[1].strip().strip('.').lower()
        for k in lst:
            item = k.strip().strip('.').lower()
            if item == ext and not (skip_nzb and item == 'nzb'):
                return True
    return False

def get_ext(filename):
    """ Return lowercased file extension
    """
    try:
        return os.path.splitext(filename)[1].lower()
    except:
        return ''

def get_filename(path):
    """ Return path without the file extension
    """
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
        return "%.2f | %.2f | %.2f" % os.getloadavg()
    except:
        return ""


def format_time_string(seconds, days=0):
    """ Return a formatted and translated time string """
    seconds = int_conv(seconds)
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
    """ Return a plural form of 'item', based on 'value' (english only)
    """
    if value == 1:
        return Tx(item)
    else:
        return Tx(item + 's')

def int_conv(value):
    """ Safe conversion to int (can handle None)
    """
    try:
        value = int(value)
    except:
        value = 0
    return value


#------------------------------------------------------------------------------
# Diskfree
if sabnzbd.WIN32:
    # windows diskfree
    import win32api
    def diskfree(_dir):
        """ Return amount of free diskspace in GBytes
        """
        try:
            available, disk_size, total_free = win32api.GetDiskFreeSpaceEx(_dir)
            return available / GIGI
        except:
            return 0.0
    def disktotal(_dir):
        """ Return amount of free diskspace in GBytes
        """
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
            """ Return amount of free diskspace in GBytes
            """
            try:
                s = os.statvfs(_dir)
                if s.f_bavail < 0:
                    return float(sys.maxint) * float(s.f_frsize) / GIGI
                else:
                    return float(s.f_bavail) * float(s.f_frsize) / GIGI
            except OSError:
                return 0.0
        def disktotal(_dir):
            """ Return amount of total diskspace in GBytes
            """
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
    """ Create self-signed HTTPS certificares and store in paths 'ssl_cert' and 'ssl_key'
    """
    try:
        from OpenSSL import crypto
        from sabnzbd.utils.certgen import createKeyPair, createCertRequest, createCertificate, \
             TYPE_RSA, serial
    except:
        logging.warning(Ta('pyopenssl module missing, please install for https access'))
        return False

    # Create the CA Certificate
    cakey = createKeyPair(TYPE_RSA, 1024)
    careq = createCertRequest(cakey, CN='Certificate Authority')
    cacert = createCertificate(careq, (careq, cakey), serial, (0, 60*60*24*365*10)) # ten years

    cname = 'SABnzbd'
    pkey = createKeyPair(TYPE_RSA, 1024)
    req = createCertRequest(pkey, CN=cname)
    cert = createCertificate(req, (cacert, cakey), serial, (0, 60*60*24*365*10)) # ten years

    # Save the key and certificate to disk
    try:
        open(ssl_key, 'w').write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
        open(ssl_cert, 'w').write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    except:
        logging.error(Ta('Error creating SSL key and certificate'))
        logging.info("Traceback: ", exc_info = True)
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
            if os.path.isfile(target_path) and os.access(target_path, os.X_OK):
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
        p.wait()
        for line in output.split('\n'):
            m = _RE_IP4.search(line)
            if not (m and m.group(2)):
                m = _RE_IP6.search(line)
            if m and m.group(2):
                ips.append(m.group(2))
    return ips


#------------------------------------------------------------------------------

def renamer(old, new):
    """ Rename file/folder with retries for Win32 """
    if sabnzbd.WIN32:
        retries = 15
        while retries > 0:
            try:
                os.rename(old, new)
                return
            except WindowsError, err:
                if err[0] == 32:
                    logging.debug('Retry rename %s to %s', old, new)
                    retries -= 1
                else:
                    raise WindowsError(err)
            time.sleep(3)
        raise WindowsError(err)
    else:
        os.rename(old, new)


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
    """ Remove folder and all its content (optionally recursive)
    """
    if os.path.exists(path):
        files = globber(path, pattern)
        if pattern == '*' and not sabnzbd.WIN32:
            files.extend(globber(path, '.*'))

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
