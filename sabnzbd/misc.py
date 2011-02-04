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
import webbrowser
import tempfile
import shutil
import threading
import subprocess
import socket
import time
import glob

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import DEFAULT_PRIORITY, FUTURE_Q_FOLDER, JOB_ADMIN, GIGI
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.encoding import unicoder, latin1

if sabnzbd.FOUNDATION:
    import Foundation

RE_VERSION = re.compile('(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_UNITS = re.compile('(\d+\.*\d*)\s*([KMGTP]{0,1})', re.I)
TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')

PANIC_NONE  = 0
PANIC_PORT  = 1
PANIC_TEMPL = 2
PANIC_QUEUE = 3
PANIC_FWALL = 4
PANIC_OTHER = 5
PANIC_XPORT = 6
PANIC_SQLITE = 7
PANIC_HOST = 8

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
        logging.debug('Job gets options %s', pp)

    if not script:
        script = my_cat.script()
        if safe_lower(script) in ('', 'default'):
            script = def_cat.script()
        logging.debug('Job gets script %s', script)

    if priority is None or priority == DEFAULT_PRIORITY:
        priority = my_cat.priority()
        if priority == DEFAULT_PRIORITY:
            priority = def_cat.priority()
        logging.debug('Job gets priority %s', priority)

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

FL_ILLEGAL = CH_ILLEGAL + ':\x92'
FL_LEGAL   = CH_LEGAL + ";'"
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
        if path.startswith('~'):
            path = path.replace('~', sabnzbd.DIR_HOME+'/', 1)
        if sabnzbd.WIN32:
            if path[0] not in '/\\' and not (len(path) > 1 and path[0].isalpha() and path[1] == ':'):
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
# Launch a browser for various purposes
# including panic messages
#
################################################################################
def MSG_BAD_NEWS():
    return r'''
    <html>
    <head>
    <title>''' + Ta('Problem with') + ''' %s %s</title>
    </head>
    <body>
    <h1><font color="#0000FF"> %s %s</font></h1>
    <p align="center">&nbsp;</p>
    <p align="center"><font size="5">
    <blockquote>
        %s
    </blockquote>
    <br>%s<br>
    </body>
</html>
'''

def MSG_BAD_FWALL():
    return Ta(r'''
    SABnzbd is not compatible with some software firewalls.<br>
    %s<br>
    Sorry, but we cannot solve this incompatibility right now.<br>
    Please file a complaint at your firewall supplier.<br>
    <br>
''')

def MSG_BAD_PORT():
    return Ta(r'''
    SABnzbd needs a free tcp/ip port for its internal web server.<br>
    Port %s on %s was tried , but it is not available.<br>
    Some other software uses the port or SABnzbd is already running.<br>
    <br>
    Please restart SABnzbd with a different port number.''') + \
    '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>''' + \
    Ta(r'If you get this error message again, please try a different number.<br>')

def MSG_ILL_PORT():
    return Ta(r'''
    SABnzbd needs a free tcp/ip port for its internal web server.<br>
    Port %s on %s was tried , but the account used for SABnzbd has no permission to use it.<br>
    On OSX and Linux systems, normal users must use ports above 1023.<br>
    <br>
    Please restart SABnzbd with a different port number.''') + \
    '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>''' + \
    Ta(r'If you get this error message again, please try a different number.<br>')

def MSG_BAD_HOST():
    return Ta(r'''
    SABnzbd needs a valid host address for its internal web server.<br>
    You have specified an invalid address.<br>
    Safe values are <b>localhost</b> and <b>0.0.0.0</b><br>
    <br>
    Please restart SABnzbd with a proper host address.''') + \
    '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>
'''

def MSG_BAD_QUEUE():
    return Ta(r'''
    SABnzbd detected saved data from an other SABnzbd version<br>
    but cannot re-use the data of the other program.<br><br>
    You may want to finish your queue first with the other program.<br><br>
    After that, start this program with the "--clean" option.<br>
    This will erase the current queue and history!<br>
    SABnzbd read the file "%s".''') + \
    '''<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --clean<br>
    <br>
'''

def MSG_BAD_TEMPL():
    return Ta(r'''
    SABnzbd cannot find its web interface files in %s.<br>
    Please install the program again.<br>
    <br>
''')

def MSG_OTHER():
    return Ta('SABnzbd detected a fatal error:') + '<br>%s<br><br>%s<br>'

def MSG_OLD_QUEUE():
    return Ta(r'''
    SABnzbd detected a Queue and History from an older (0.4.x) release.<br><br>
    Both queue and history will be ignored and may get lost!<br><br>
    You may choose to stop SABnzbd and finish the queue with the older program.<br><br>
    Click OK to proceed to SABnzbd''') + \
    ('''<br><br><FORM><input type="button" onclick="this.form.action='/.'; this.form.submit(); return false;" value="%s"/></FORM>''' % Ta('OK'))

def MSG_SQLITE():
    return Ta(r'''
    SABnzbd detected that the file sqlite3.dll is missing.<br><br>
    Some poorly designed virus-scanners remove this file.<br>
    Please check your virus-scanner, try to re-install SABnzbd and complain to your virus-scanner vendor.<br>
    <br>
''')

def panic_message(panic, a=None, b=None):
    """Create the panic message from templates
    """
    if sabnzbd.WIN32:
        os_str = Ta('Press Startkey+R and type the line (example):')
        prog_path = '"%s"' % sabnzbd.MY_FULLNAME
    else:
        os_str = Ta('Open a Terminal window and type the line (example):')
        prog_path = sabnzbd.MY_FULLNAME

    if panic == PANIC_PORT:
        newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_BAD_PORT() % (b, a, os_str, prog_path, a, newport)
    elif panic == PANIC_XPORT:
        if int(b) < 1023:
            newport = 1024
        else:
            newport = int(b) + 1
        newport = "%s" % newport
        msg = MSG_ILL_PORT() % (b, a, os_str, prog_path, a, newport)
    elif panic == PANIC_TEMPL:
        msg = MSG_BAD_TEMPL() % a
    elif panic == PANIC_QUEUE:
        msg = MSG_BAD_QUEUE() % (a, os_str, prog_path)
    elif panic == PANIC_FWALL:
        if a:
            msg = MSG_BAD_FWALL() % Ta('It is likely that you are using ZoneAlarm on Vista.<br>')
        else:
            msg = MSG_BAD_FWALL() % "<br>"
    elif panic == PANIC_SQLITE:
        msg = MSG_SQLITE()
    elif panic == PANIC_HOST:
        msg = MSG_BAD_HOST() % (os_str, prog_path, 'localhost', b)
    else:
        msg = MSG_OTHER() % (a, b)

    msg = MSG_BAD_NEWS() % (sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_NAME, sabnzbd.__version__,
                          msg, Ta('Program did not start!'))

    if sabnzbd.WIN_SERVICE:
        sabnzbd.WIN_SERVICE.ErrLogger('Panic exit', msg)

    if (not cfg.autobrowser()) or sabnzbd.DAEMON:
        return

    msgfile, url = tempfile.mkstemp(suffix='.html')
    os.write(msgfile, msg)
    os.close(msgfile)
    return url


def panic_fwall(vista):
    launch_a_browser(panic_message(PANIC_FWALL, vista))

def panic_port(host, port):
    launch_a_browser(panic_message(PANIC_PORT, host, port))

def panic_host(host, port):
    launch_a_browser(panic_message(PANIC_HOST, host, port))

def panic_xport(host, port):
    launch_a_browser(panic_message(PANIC_XPORT, host, port))
    logging.error(Ta('You have no permisson to use port %s'), port)

def panic_queue(name):
    launch_a_browser(panic_message(PANIC_QUEUE, name, 0))

def panic_tmpl(name):
    launch_a_browser(panic_message(PANIC_TEMPL, name, 0))

def panic_sqlite(name):
    launch_a_browser(panic_message(PANIC_SQLITE, name, 0))

def panic_old_queue():
    msg = MSG_OLD_QUEUE
    return MSG_BAD_NEWS % (sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_NAME, sabnzbd.__version__, msg, '')

def panic(reason, remedy=""):
    print "\n%s:\n  %s\n%s" % (Ta('Fatal error'), reason, remedy)
    launch_a_browser(panic_message(PANIC_OTHER, reason, remedy))


def launch_a_browser(url, force=False):
    """Launch a browser pointing to the URL
    """
    if not force and not cfg.autobrowser() or sabnzbd.DAEMON:
        return

    logging.info("Lauching browser with %s", url)
    try:
        webbrowser.open(url, 2, 1)
    except:
        # Python 2.4 does not support parameter new=2
        try:
            webbrowser.open(url, 1, 1)
        except:
            logging.warning(Ta('Cannot launch the browser, probably not found'))
            logging.info("Traceback: ", exc_info = True)


def error_page_401(status, message, traceback, version):
    """ Custom handler for 401 error """
    title = T('Access denied')
    body = T('Error %s: You need to provide a valid username and password.') % status
    return r'''
<html>
    <head>
    <title>%s</title>
    </head>
    <body>
    <br/><br/>
    <font color="#0000FF">%s</font>
    </body>
</html>
''' % (title, body)



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
    val = str(val).strip()
    if val == "-1":
        return val
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

    format = '%%.%sf %%s' % decimals
    return format % (val, unit)

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
    """ Leave the program after flushing stderr/stdout
    """
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
def check_mount(path):
    """ Return False if volume isn't mounted on Linux or OSX
    """
    if sabnzbd.DARWIN:
        m = re.search(r'^(/Volumes/[^/]+)/', path, re.I)
    elif not sabnzbd.WIN32:
        m = re.search(r'^(/mnt/[^/]+)/', path)
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
            logging.info("Traceback: ", exc_info = True)
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
        ext = os.path.splitext(filename)[1].strip().strip('.')
        if sabnzbd.WIN32:
            ext = ext.lower()

        for k in lst:
            item = k.strip().strip('.')
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
try:
    os.statvfs
    import statvfs
    # posix diskfree
    def diskfree(_dir):
        """ Return amount of free diskspace in GBytes
        """
        try:
            s = os.statvfs(_dir)
            return (s[statvfs.F_BAVAIL] * s[statvfs.F_FRSIZE]) / GIGI
        except OSError:
            return 0.0
    def disktotal(_dir):
        """ Return amount of total diskspace in GBytes
        """
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
# Power management for Windows

def win_hibernate():
    """ Hibernate Windows system, returns after wakeup
    """
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Hibernate")
        time.sleep(10)
    except:
        logging.error(Ta('Failed to hibernate system'))
        logging.info("Traceback: ", exc_info = True)


def win_standby():
    """ Standby Windows system, returns after wakeup
    """
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Standby")
        time.sleep(10)
    except:
        logging.error(Ta('Failed to standby system'))
        logging.info("Traceback: ", exc_info = True)


def win_shutdown():
    """ Shutdown Windows system, never returns
    """
    try:
        import win32security
        import win32api
        import ntsecuritycon

        flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES | ntsecuritycon.TOKEN_QUERY
        htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
        id_ = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_SHUTDOWN_NAME)
        newPrivileges = [(id_, ntsecuritycon.SE_PRIVILEGE_ENABLED)]
        win32security.AdjustTokenPrivileges(htoken, 0, newPrivileges)
        win32api.InitiateSystemShutdown("", "", 30, 1, 0)
    finally:
        os._exit(0)


#------------------------------------------------------------------------------
# Power management for OSX

def osx_shutdown():
    """ Shutdown OSX system, never returns
    """
    try:
        subprocess.call(['osascript', '-e', 'tell app "System Events" to shut down'])
    except:
        logging.error(Ta('Error while shutting down system'))
        logging.info("Traceback: ", exc_info = True)
    os._exit(0)


def osx_standby():
    """ Make OSX system sleep, returns after wakeup
    """
    try:
        subprocess.call(['osascript', '-e','tell app "System Events" to sleep'])
        time.sleep(10)
    except:
        logging.error(Ta('Failed to standby system'))
        logging.info("Traceback: ", exc_info = True)


def osx_hibernate():
    """ Make OSX system sleep, returns after wakeup
    """
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
    """ Make Linux system shutdown, never returns
    """
    if not HAVE_DBUS: os._exit(0)

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanShutdown():
            proxy.Shutdown(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('ConsoleKit')
        if proxy and proxy.CanStop(dbus_interface=interface):
            try:
                proxy.Stop(dbus_interface=interface)
            except dbus.exceptions.DBusException, msg:
                logging.info('Received a DBus exception %s', latin1(msg))
    os._exit(0)


def linux_hibernate():
    """ Make Linux system go into hibernate, returns after wakeup
    """
    if not HAVE_DBUS: return

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanHibernate():
            proxy.Hibernate(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('DeviceKit')
        if proxy and proxy.Get(interface, 'can-hibernate', dbus_interface=pinterface):
            try:
                proxy.Hibernate(dbus_interface=interface)
            except dbus.exceptions.DBusException, msg:
                logging.info('Received a DBus exception %s', latin1(msg))
    time.sleep(10)


def linux_standby():
    """ Make Linux system go into standby, returns after wakeup
    """
    if not HAVE_DBUS: return

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanSuspend():
            proxy.Suspend(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('DeviceKit')
        if proxy.Get(interface, 'can-suspend', dbus_interface=pinterface):
            try:
                proxy.Suspend(dbus_interface=interface)
            except dbus.exceptions.DBusException, msg:
                logging.info('Received a DBus exception %s', latin1(msg))
    time.sleep(10)


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


def remove_all(path, pattern='*'):
    """ Remove folder and all its content
    """
    if os.path.exists(path):
        for f in globber(path, pattern):
            os.remove(f)
        try:
            os.rmdir(path)
        except:
            pass


def clean_folder(path, pattern='*'):
    """ Remove all files in root of folder, remove folder if empty afterwards """
    for file in globber(path, pattern):
        try:
            os.remove(file)
        except:
            pass
    try:
        os.rmdir(path)
    except:
        pass
