#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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

import sys
if sys.hexversion < 0x03050000:
    print("Sorry, requires Python 3.5 or above")
    print("You can read more at: https://sabnzbd.org/python3")
    sys.exit(1)

import logging
import logging.handlers
import traceback
import getopt
import signal
import socket
import platform
import subprocess
import ssl
import time
import re

try:
    import Cheetah
    if Cheetah.Version[0] != '3':
        raise ValueError
    import feedparser
    import configobj
    import cherrypy
    import portend
    import cryptography
    import chardet
except ValueError:
    print("Sorry, requires Python module Cheetah 3 or higher.")
    sys.exit(1)
except ImportError as e:
    print("Not all required Python modules are available, please check requirements.txt")
    print("Missing module:", e.name)
    print("You can read more at: https://sabnzbd.org/python3")
    print("If you still experience problems, remove all .pyc files in this folder and subfolders")
    sys.exit(1)

import sabnzbd
import sabnzbd.lang
import sabnzbd.interface
from sabnzbd.constants import *
import sabnzbd.newsunpack
from sabnzbd.misc import check_latest_version, exit_sab, \
    split_host, create_https_certificates, windows_variant, ip_extract, \
    set_serv_parms, get_serv_parms, get_from_url
from sabnzbd.filesystem import get_ext, real_path, long_path, globber_full, remove_file
from sabnzbd.panic import panic_tmpl, panic_port, panic_host, panic, launch_a_browser
import sabnzbd.scheduler as scheduler
import sabnzbd.config as config
import sabnzbd.cfg
import sabnzbd.downloader
import sabnzbd.notifier as notifier
import sabnzbd.zconfig

try:
    import win32api
    import win32serviceutil
    import win32evtlogutil
    import win32event
    import win32service
    import win32ts
    import pywintypes
    win32api.SetConsoleCtrlHandler(sabnzbd.sig_handler, True)
    from sabnzbd.utils.apireg import get_connection_info, set_connection_info, del_connection_info
except ImportError:
    if sabnzbd.WIN32:
        print("Sorry, requires Python module PyWin32.")
        sys.exit(1)

# Global for this module, signaling loglevel change
LOG_FLAG = False


def guard_loglevel():
    """ Callback function for guarding loglevel """
    global LOG_FLAG
    LOG_FLAG = True


class GUIHandler(logging.Handler):
    """ Logging handler collects the last warnings/errors/exceptions
        to be displayed in the web-gui
    """

    def __init__(self, size):
        """ Initializes the handler """
        logging.Handler.__init__(self)
        self.size = size
        self.store = []

    def emit(self, record):
        """ Emit a record by adding it to our private queue """
        if record.levelname == 'WARNING':
            sabnzbd.LAST_WARNING = record.msg % record.args
        else:
            sabnzbd.LAST_ERROR = record.msg % record.args

        if len(self.store) >= self.size:
            # Loose the oldest record
            self.store.pop(0)
        try:
            # Append traceback, if available
            warning = {'type': record.levelname, 'text': record.msg % record.args, 'time': int(time.time())}
            if record.exc_info:
                warning['text'] = '%s\n%s' % (warning['text'], traceback.format_exc())
            self.store.append(warning)
        except UnicodeDecodeError:
            # Catch elusive Unicode conversion problems
            pass

    def clear(self):
        self.store = []

    def count(self):
        return len(self.store)

    def content(self):
        """ Return an array with last records """
        return self.store


def print_help():
    print()
    print(("Usage: %s [-f <configfile>] <other options>" % sabnzbd.MY_NAME))
    print()
    print("Options marked [*] are stored in the config file")
    print()
    print("Options:")
    print("  -f  --config-file <ini>  Location of config file")
    print("  -s  --server <srv:port>  Listen on server:port [*]")
    print("  -t  --templates <templ>  Template directory [*]")
    print()
    print("  -l  --logging <-1..2>     Set logging level (-1=off, 0= least, 2= most) [*]")
    print("  -w  --weblogging         Enable cherrypy access logging")
    print()
    print("  -b  --browser <0..1>     Auto browser launch (0= off, 1= on) [*]")
    if sabnzbd.WIN32:
        print("  -d  --daemon             Use when run as a service")
    else:
        print("  -d  --daemon             Fork daemon process")
        print("      --pid <path>         Create a PID file in the given folder (full path)")
        print("      --pidfile <path>     Create a PID file with the given name (full path)")
    print()
    print("  -h  --help               Print this message")
    print("  -v  --version            Print version information")
    print("  -c  --clean              Remove queue, cache and logs")
    print("  -p  --pause              Start in paused mode")
    print("      --repair             Add orphaned jobs from the incomplete folder to the queue")
    print("      --repair-all         Try to reconstruct the queue from the incomplete folder")
    print("                           with full data reconstruction")
    print("      --https <port>       Port to use for HTTPS server")
    print("      --ipv6_hosting <0|1> Listen on IPv6 address [::1] [*]")
    print("      --no-login           Start with username and password reset")
    print("      --log-all            Log all article handling (for developers)")
    print("      --disable-file-log   Logging is only written to console")
    print("      --new                Run a new instance of SABnzbd")
    print()
    print("NZB (or related) file:")
    print("  NZB or compressed NZB file, with extension .nzb, .zip, .rar, .7z, .gz, or .bz2")
    print()


def print_version():
    print(("""
%s-%s

Copyright (C) 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
SABnzbd comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions. It is licensed under the
GNU GENERAL PUBLIC LICENSE Version 2 or (at your option) any later version.

""" % (sabnzbd.MY_NAME, sabnzbd.__version__)))


def daemonize():
    """ Daemonize the process, based on various StackOverflow answers """
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        print("fork() failed")
        sys.exit(1)

    os.chdir(sabnzbd.DIR_PROG)
    os.setsid()
    # Make sure I can read my own files and shut out others
    prev = os.umask(0)
    os.umask(prev and int('077', 8))

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        print("fork() failed")
        sys.exit(1)

    # Flush I/O buffers
    sys.stdout.flush()
    sys.stderr.flush()

    # Get log file  path and remove the log file if it got too large
    log_path = os.path.join(sabnzbd.cfg.log_dir.get_path(), DEF_LOG_ERRFILE)
    if os.path.exists(log_path) and os.path.getsize(log_path) > sabnzbd.cfg.log_size.get_int():
        remove_file(log_path)

    # Replace file descriptors for stdin, stdout, and stderr
    with open('/dev/null', 'rb', 0) as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(log_path, 'ab', 0) as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
    with open(log_path, 'ab', 0) as f:
        os.dup2(f.fileno(), sys.stderr.fileno())


def abort_and_show_error(browserhost, cherryport, err=''):
    """ Abort program because of CherryPy troubles """
    logging.error(T('Failed to start web-interface') + ' : ' + str(err))
    if not sabnzbd.DAEMON:
        if '49' in err:
            panic_host(browserhost, cherryport)
        else:
            panic_port(browserhost, cherryport)
    sabnzbd.halt()
    exit_sab(2)


def identify_web_template(key, defweb, wdir):
    """ Determine a correct web template set, return full template path """
    if wdir is None:
        try:
            wdir = fix_webname(key())
        except:
            wdir = ''
    if not wdir:
        wdir = defweb
    if key:
        key.set(wdir)
    if not wdir:
        # No default value defined, accept empty path
        return ''

    full_dir = real_path(sabnzbd.DIR_INTERFACES, wdir)
    full_main = real_path(full_dir, DEF_MAIN_TMPL)

    if not os.path.exists(full_main):
        logging.warning(T('Cannot find web template: %s, trying standard template'), full_main)
        full_dir = real_path(sabnzbd.DIR_INTERFACES, DEF_STDINTF)
        full_main = real_path(full_dir, DEF_MAIN_TMPL)
        if not os.path.exists(full_main):
            logging.exception('Cannot find standard template: %s', full_dir)
            panic_tmpl(full_dir)
            exit_sab(1)

    logging.info("Template location for %s is %s", defweb, full_dir)
    return real_path(full_dir, "templates")


def check_template_scheme(color, web_dir):
    """ Check existence of color-scheme """
    if color and os.path.exists(os.path.join(web_dir, 'static', 'stylesheets', 'colorschemes', color + '.css')):
        return color
    elif color and os.path.exists(os.path.join(web_dir, 'static', 'stylesheets', 'colorschemes', color)):
        return color
    else:
        return ''


def fix_webname(name):
    if name:
        xname = name.title()
    else:
        xname = ''
    if xname in ('Default', ):
        return 'Glitter'
    elif xname in ('Glitter', 'Plush'):
        return xname
    elif xname in ('Wizard', ):
        return name.lower()
    elif xname in ('Config',):
        return 'Glitter'
    else:
        return name


def get_user_profile_paths(vista_plus):
    """ Get the default data locations on Windows"""
    if sabnzbd.DAEMON:
        # In daemon mode, do not try to access the user profile
        # just assume that everything defaults to the program dir
        sabnzbd.DIR_APPDATA = sabnzbd.DIR_PROG
        sabnzbd.DIR_LCLDATA = sabnzbd.DIR_PROG
        sabnzbd.DIR_HOME = sabnzbd.DIR_PROG
        if sabnzbd.WIN32:
            # Ignore Win32 "logoff" signal
            # This should work, but it doesn't
            # Instead the signal_handler will ignore the "logoff" signal
            # signal.signal(5, signal.SIG_IGN)
            pass
        return
    elif sabnzbd.WIN32:
        try:
            from win32com.shell import shell, shellcon
            path = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, None, 0)
            sabnzbd.DIR_APPDATA = os.path.join(path, DEF_WORKDIR)
            path = shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)
            sabnzbd.DIR_LCLDATA = os.path.join(path, DEF_WORKDIR)
            sabnzbd.DIR_HOME = os.environ['USERPROFILE']
        except:
            try:
                if vista_plus:
                    root = os.environ['AppData']
                    user = os.environ['USERPROFILE']
                    sabnzbd.DIR_APPDATA = '%s\\%s' % (root.replace('\\Roaming', '\\Local'), DEF_WORKDIR)
                    sabnzbd.DIR_HOME = user
                else:
                    root = os.environ['USERPROFILE']
                    sabnzbd.DIR_APPDATA = '%s\\%s' % (root, DEF_WORKDIR)
                    sabnzbd.DIR_HOME = root
                sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
            except:
                pass

        # Long-path everything
        sabnzbd.DIR_APPDATA = long_path(sabnzbd.DIR_APPDATA)
        sabnzbd.DIR_LCLDATA = long_path(sabnzbd.DIR_LCLDATA)
        sabnzbd.DIR_HOME = long_path(sabnzbd.DIR_HOME)
        return

    elif sabnzbd.DARWIN:
        home = os.environ.get('HOME')
        if home:
            sabnzbd.DIR_APPDATA = '%s/Library/Application Support/SABnzbd' % home
            sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
            sabnzbd.DIR_HOME = home
            return
    else:
        # Unix/Linux
        home = os.environ.get('HOME')
        if home:
            sabnzbd.DIR_APPDATA = '%s/.%s' % (home, DEF_WORKDIR)
            sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
            sabnzbd.DIR_HOME = home
            return

    # Nothing worked
    panic("Cannot access the user profile.",
          "Please start with sabnzbd.ini file in another location")
    exit_sab(2)


def print_modules():
    """ Log all detected optional or external modules """
    if sabnzbd.decoder.SABYENC_ENABLED:
        # Yes, we have SABYenc, and it's the correct version, so it's enabled
        logging.info("SABYenc module (v%s)... found!", sabnzbd.decoder.SABYENC_VERSION)
    else:
        # Something wrong with SABYenc, so let's determine and print what:
        if sabnzbd.decoder.SABYENC_VERSION:
            # We have a VERSION, thus a SABYenc module, but it's not the correct version
            logging.error(T("SABYenc disabled: no correct version found! (Found v%s, expecting v%s)") % (sabnzbd.decoder.SABYENC_VERSION, sabnzbd.constants.SABYENC_VERSION_REQUIRED))
        else:
            # No SABYenc module at all
            logging.error(T("SABYenc module... NOT found! Expecting v%s - https://sabnzbd.org/sabyenc") % sabnzbd.constants.SABYENC_VERSION_REQUIRED)
        # Do not allow downloading
        sabnzbd.NO_DOWNLOADING = True

    logging.info('Cryptography module (v%s)... found!', cryptography.__version__)

    if sabnzbd.newsunpack.PAR2_COMMAND:
        logging.info("par2 binary... found (%s)", sabnzbd.newsunpack.PAR2_COMMAND)
    else:
        logging.error(T('par2 binary... NOT found!'))
        # Do not allow downloading
        sabnzbd.NO_DOWNLOADING = True

    if sabnzbd.newsunpack.MULTIPAR_COMMAND:
        logging.info("MultiPar binary... found (%s)", sabnzbd.newsunpack.MULTIPAR_COMMAND)
    elif sabnzbd.WIN32:
        logging.error('%s %s' % (T('MultiPar binary... NOT found!'), T('Verification and repair will not be possible.')))

    if sabnzbd.newsunpack.RAR_COMMAND:
        logging.info("UNRAR binary... found (%s)", sabnzbd.newsunpack.RAR_COMMAND)

        # Report problematic unrar
        if sabnzbd.newsunpack.RAR_PROBLEM and not sabnzbd.cfg.ignore_wrong_unrar():
            have_str = '%.2f' % (float(sabnzbd.newsunpack.RAR_VERSION) / 100)
            want_str = '%.2f' % (float(sabnzbd.constants.REC_RAR_VERSION) / 100)
            logging.warning(T('Your UNRAR version is %s, we recommend version %s or higher.<br />') % (have_str, want_str))
        elif not (sabnzbd.WIN32 or sabnzbd.DARWIN):
            logging.info('UNRAR binary version %.2f', (float(sabnzbd.newsunpack.RAR_VERSION) / 100))
    else:
        logging.error(T('unrar binary... NOT found'))
        # Do not allow downloading
        sabnzbd.NO_DOWNLOADING = True

    if sabnzbd.newsunpack.ZIP_COMMAND:
        logging.info("unzip binary... found (%s)", sabnzbd.newsunpack.ZIP_COMMAND)
    else:
        logging.info(T('unzip binary... NOT found!'))

    if sabnzbd.newsunpack.SEVEN_COMMAND:
        logging.info("7za binary... found (%s)", sabnzbd.newsunpack.SEVEN_COMMAND)
    else:
        logging.info(T('7za binary... NOT found!'))

    if not sabnzbd.WIN32:
        if sabnzbd.newsunpack.NICE_COMMAND:
            logging.info("nice binary... found (%s)", sabnzbd.newsunpack.NICE_COMMAND)
        else:
            logging.info("nice binary... NOT found!")
        if sabnzbd.newsunpack.IONICE_COMMAND:
            logging.info("ionice binary... found (%s)", sabnzbd.newsunpack.IONICE_COMMAND)
        else:
            logging.info("ionice binary... NOT found!")

    # Show fatal warning
    if sabnzbd.NO_DOWNLOADING:
        logging.error(T('Essential modules are missing, downloading cannot start.'))


def all_localhosts():
    """ Return all unique values of localhost in order of preference """
    ips = ['127.0.0.1']
    try:
        # Check whether IPv6 is available and enabled
        info = socket.getaddrinfo('::1', None)
        af, socktype, proto, _canonname, _sa = info[0]
        s = socket.socket(af, socktype, proto)
        s.close()
    except socket.error:
        return ips
    try:
        info = socket.getaddrinfo('localhost', None)
    except socket.error:
        # localhost does not resolve
        return ips
    ips = []
    for item in info:
        item = item[4][0]
        # Avoid problems on strange Linux settings
        if not isinstance(item, str):
            continue
        # Only return IPv6 when enabled
        if item not in ips and ('::1' not in item or sabnzbd.cfg.ipv6_hosting()):
            ips.append(item)
    return ips


def check_resolve(host):
    """ Return True if 'host' resolves """
    try:
        socket.getaddrinfo(host, None)
    except socket.error:
        # Does not resolve
        return False
    return True


def get_webhost(cherryhost, cherryport, https_port):
    """ Determine the webhost address and port,
        return (host, port, browserhost)
    """
    if cherryhost == '0.0.0.0' and not check_resolve('127.0.0.1'):
        cherryhost = ''
    elif cherryhost == '::' and not check_resolve('::1'):
        cherryhost = ''

    if cherryhost is None:
        cherryhost = sabnzbd.cfg.cherryhost()
    else:
        sabnzbd.cfg.cherryhost.set(cherryhost)

    # Get IP address, but discard APIPA/IPV6
    # If only APIPA's or IPV6 are found, fall back to localhost
    ipv4 = ipv6 = False
    localhost = hostip = 'localhost'
    try:
        info = socket.getaddrinfo(socket.gethostname(), None)
    except socket.error:
        # Hostname does not resolve
        try:
            # Valid user defined name?
            info = socket.getaddrinfo(cherryhost, None)
        except socket.error:
            if cherryhost not in ('localhost', '127.0.0.1', '::1'):
                cherryhost = '0.0.0.0'
            try:
                info = socket.getaddrinfo(localhost, None)
            except socket.error:
                info = socket.getaddrinfo('127.0.0.1', None)
                localhost = '127.0.0.1'
    for item in info:
        ip = str(item[4][0])
        if ip.startswith('169.254.'):
            pass  # Automatic Private IP Addressing (APIPA)
        elif ':' in ip:
            ipv6 = True
        elif '.' in ip and not ipv4:
            ipv4 = True
            hostip = ip

    # A blank host will use the local ip address
    if cherryhost == '':
        if ipv6 and ipv4:
            # To protect Firefox users, use numeric IP
            cherryhost = hostip
            browserhost = hostip
        else:
            cherryhost = socket.gethostname()
            browserhost = cherryhost

    # 0.0.0.0 will listen on all ipv4 interfaces (no ipv6 addresses)
    elif cherryhost == '0.0.0.0':
        # Just take the gamble for this
        cherryhost = '0.0.0.0'
        browserhost = localhost

    # :: will listen on all ipv6 interfaces (no ipv4 addresses)
    elif cherryhost in ('::', '[::]'):
        cherryhost = cherryhost.strip('[').strip(']')
        # Assume '::1' == 'localhost'
        browserhost = localhost

    # IPV6 address
    elif '[' in cherryhost or ':' in cherryhost:
        browserhost = cherryhost

    # IPV6 numeric address
    elif cherryhost.replace('.', '').isdigit():
        # IPV4 numerical
        browserhost = cherryhost

    elif cherryhost == localhost:
        cherryhost = localhost
        browserhost = localhost

    else:
        # If on Vista and/or APIPA, use numerical IP, to help FireFoxers
        if ipv6 and ipv4:
            cherryhost = hostip
        browserhost = cherryhost

    # Some systems don't like brackets in numerical ipv6
        if sabnzbd.DARWIN:
            cherryhost = cherryhost.strip('[]')
        else:
            try:
                socket.getaddrinfo(cherryhost, None)
            except socket.error:
                cherryhost = cherryhost.strip('[]')

    if ipv6 and ipv4 and \
       (browserhost not in ('localhost', '127.0.0.1', '[::1]', '::1')):
        sabnzbd.AMBI_LOCALHOST = True
        logging.info("IPV6 has priority on this system, potential Firefox issue")

    if ipv6 and ipv4 and cherryhost == '' and sabnzbd.WIN32:
        logging.warning(T('Please be aware the 0.0.0.0 hostname will need an IPv6 address for external access'))

    if cherryhost == 'localhost' and not sabnzbd.WIN32 and not sabnzbd.DARWIN:
        # On the Ubuntu family, localhost leads to problems for CherryPy
        ips = ip_extract()
        if '127.0.0.1' in ips and '::1' in ips:
            cherryhost = '127.0.0.1'
            if ips[0] != '127.0.0.1':
                browserhost = '127.0.0.1'

    # This is to please Chrome on OSX
    if cherryhost == 'localhost' and sabnzbd.DARWIN:
        cherryhost = '127.0.0.1'
        browserhost = 'localhost'

    if cherryport is None:
        cherryport = sabnzbd.cfg.cherryport.get_int()
    else:
        sabnzbd.cfg.cherryport.set(str(cherryport))

    if https_port is None:
        https_port = sabnzbd.cfg.https_port.get_int()
    else:
        sabnzbd.cfg.https_port.set(str(https_port))
        # if the https port was specified, assume they want HTTPS enabling also
        sabnzbd.cfg.enable_https.set(True)

    if cherryport == https_port and sabnzbd.cfg.enable_https():
        sabnzbd.cfg.enable_https.set(False)
        # Should have a translated message, but that's not available yet
        logging.error(T('HTTP and HTTPS ports cannot be the same'))

    return cherryhost, cherryport, browserhost, https_port


def attach_server(host, port, cert=None, key=None, chain=None):
    """ Define and attach server, optionally HTTPS """
    if sabnzbd.cfg.ipv6_hosting() or '::1' not in host:
        http_server = cherrypy._cpserver.Server()
        http_server.bind_addr = (host, port)
        if cert and key:
            http_server.ssl_module = 'builtin'
            http_server.ssl_certificate = cert
            http_server.ssl_private_key = key
            http_server.ssl_certificate_chain = chain
        http_server.subscribe()


def is_sabnzbd_running(url):
    """ Return True when there's already a SABnzbd instance running. """
    try:
        url = '%s&mode=version' % url
        # Do this without certificate verification, few installations will have that
        prev = sabnzbd.set_https_verification(False)
        ver = get_from_url(url)
        sabnzbd.set_https_verification(prev)
        return ver and (re.search(r'\d+\.\d+\.', ver) or ver.strip() == sabnzbd.__version__)
    except:
        return False


def find_free_port(host, currentport):
    """ Return a free port, 0 when nothing is free """
    n = 0
    while n < 10 and currentport <= 49151:
        try:
            portend.free(host, currentport, timeout=0.025)
            return currentport
        except:
            currentport += 5
            n += 1
    return 0


def check_for_sabnzbd(url, upload_nzbs, allow_browser=True):
    """ Check for a running instance of sabnzbd on this port
        allow_browser==True|None will launch the browser, False will not.
    """
    if allow_browser is None:
        allow_browser = True
    if is_sabnzbd_running(url):
        # Upload any specified nzb files to the running instance
        if upload_nzbs:
            from sabnzbd.utils.upload import upload_file
            prev = sabnzbd.set_https_verification(False)
            for f in upload_nzbs:
                upload_file(url, f)
            sabnzbd.set_https_verification(prev)
        else:
            # Launch the web browser and quit since sabnzbd is already running
            # Trim away everything after the final slash in the URL
            url = url[:url.rfind('/') + 1]
            launch_a_browser(url, force=allow_browser)
        exit_sab(0)
        return True
    return False


def evaluate_inipath(path):
    """ Derive INI file path from a partial path.
        Full file path: if file does not exist the name must contain a dot
        but not a leading dot.
        foldername is enough, the standard name will be appended.
    """
    path = os.path.normpath(os.path.abspath(path))
    inipath = os.path.join(path, DEF_INI_FILE)
    if os.path.isdir(path):
        return inipath
    elif os.path.isfile(path) or os.path.isfile(path + '.bak'):
        return path
    else:
        _dirpart, name = os.path.split(path)
        if name.find('.') < 1:
            return inipath
        else:
            return path


def commandline_handler():
    """ Split win32-service commands are true parameters
        Returns:
            service, sab_opts, serv_opts, upload_nzbs
    """
    service = ''
    sab_opts = []
    serv_opts = [os.path.normpath(os.path.abspath(sys.argv[0]))]
    upload_nzbs = []

    # OSX binary: get rid of the weird -psn_0_123456 parameter
    for arg in sys.argv:
        if arg.startswith('-psn_'):
            sys.argv.remove(arg)
            break

    # Ugly hack to remove the extra "SABnzbd*" parameter the Windows binary
    # gets when it's restarted
    if len(sys.argv) > 1 and \
       'sabnzbd' in sys.argv[1].lower() and \
       not sys.argv[1].startswith('-'):
        slice = 2
    else:
        slice = 1

    # Prepend options from env-variable to options
    info = os.environ.get('SABnzbd', '').split()
    info.extend(sys.argv[slice:])

    try:
        opts, args = getopt.getopt(info, "phdvncwl:s:f:t:b:2:",
                                   ['pause', 'help', 'daemon', 'nobrowser', 'clean', 'logging=',
                                    'weblogging', 'server=', 'templates', 'ipv6_hosting=',
                                    'template2', 'browser=', 'config-file=', 'force', 'disable-file-log',
                                    'version', 'https=', 'autorestarted', 'repair', 'repair-all',
                                    'log-all', 'no-login', 'pid=', 'new', 'console', 'pidfile=',
                                    # Below Win32 Service options
                                    'password=', 'username=', 'startup=', 'perfmonini=', 'perfmondll=',
                                    'interactive', 'wait=',
                                    ])
    except getopt.GetoptError:
        print_help()
        exit_sab(2)

    # Check for Win32 service commands
    if args and args[0] in ('install', 'update', 'remove', 'start', 'stop', 'restart', 'debug'):
        service = args[0]
        serv_opts.extend(args)

    if not service:
        # Get and remove any NZB file names
        for entry in args:
            if get_ext(entry) in VALID_NZB_FILES + VALID_ARCHIVES:
                upload_nzbs.append(os.path.abspath(entry))

    for opt, arg in opts:
        if opt in ('password', 'username', 'startup', 'perfmonini', 'perfmondll', 'interactive', 'wait'):
            # Service option, just collect
            if service:
                serv_opts.append(opt)
                if arg:
                    serv_opts.append(arg)
        else:
            if opt == '-f':
                arg = os.path.normpath(os.path.abspath(arg))
            sab_opts.append((opt, arg))

    return service, sab_opts, serv_opts, upload_nzbs


def get_f_option(opts):
    """ Return value of the -f option """
    for opt, arg in opts:
        if opt == '-f':
            return arg
    else:
        return None


def main():
    global LOG_FLAG
    import sabnzbd  # Due to ApplePython bug

    autobrowser = None
    autorestarted = False
    sabnzbd.MY_FULLNAME = sys.argv[0]
    sabnzbd.MY_NAME = os.path.basename(sabnzbd.MY_FULLNAME)
    fork = False
    pause = False
    inifile = None
    cherryhost = None
    cherryport = None
    https_port = None
    cherrypylogging = None
    clean_up = False
    logging_level = None
    no_file_log = False
    web_dir = None
    vista_plus = False
    win64 = False
    repair = 0
    no_login = False
    sabnzbd.RESTART_ARGS = [sys.argv[0]]
    pid_path = None
    pid_file = None
    new_instance = False
    osx_console = False
    ipv6_hosting = None

    _service, sab_opts, _serv_opts, upload_nzbs = commandline_handler()

    for opt, arg in sab_opts:
        if opt == '--servicecall':
            sabnzbd.MY_FULLNAME = arg
        elif opt in ('-d', '--daemon'):
            if not sabnzbd.WIN32:
                fork = True
            autobrowser = False
            sabnzbd.DAEMON = True
            sabnzbd.RESTART_ARGS.append(opt)
        elif opt in ('-f', '--config-file'):
            inifile = arg
            sabnzbd.RESTART_ARGS.append(opt)
            sabnzbd.RESTART_ARGS.append(arg)
        elif opt in ('-h', '--help'):
            print_help()
            exit_sab(0)
        elif opt in ('-t', '--templates'):
            web_dir = arg
        elif opt in ('-s', '--server'):
            (cherryhost, cherryport) = split_host(arg)
        elif opt in ('-n', '--nobrowser'):
            autobrowser = False
        elif opt in ('-b', '--browser'):
            try:
                autobrowser = bool(int(arg))
            except ValueError:
                autobrowser = True
        elif opt == '--autorestarted':
            autorestarted = True
        elif opt in ('-c', '--clean'):
            clean_up = True
        elif opt in ('-w', '--weblogging'):
            cherrypylogging = True
        elif opt in ('-l', '--logging'):
            try:
                logging_level = int(arg)
            except:
                logging_level = -2
            if logging_level < -1 or logging_level > 2:
                print_help()
                exit_sab(1)
        elif opt in ('-v', '--version'):
            print_version()
            exit_sab(0)
        elif opt in ('-p', '--pause'):
            pause = True
        elif opt == '--https':
            https_port = int(arg)
            sabnzbd.RESTART_ARGS.append(opt)
            sabnzbd.RESTART_ARGS.append(arg)
        elif opt == '--repair':
            repair = 1
            pause = True
        elif opt == '--repair-all':
            repair = 2
            pause = True
        elif opt == '--log-all':
            sabnzbd.LOG_ALL = True
        elif opt == '--disable-file-log':
            no_file_log = True
        elif opt == '--no-login':
            no_login = True
        elif opt == '--pid':
            pid_path = arg
            sabnzbd.RESTART_ARGS.append(opt)
            sabnzbd.RESTART_ARGS.append(arg)
        elif opt == '--pidfile':
            pid_file = arg
            sabnzbd.RESTART_ARGS.append(opt)
            sabnzbd.RESTART_ARGS.append(arg)
        elif opt == '--new':
            new_instance = True
        elif opt == '--ipv6_hosting':
            ipv6_hosting = arg

    sabnzbd.MY_FULLNAME = os.path.normpath(os.path.abspath(sabnzbd.MY_FULLNAME))
    sabnzbd.MY_NAME = os.path.basename(sabnzbd.MY_FULLNAME)
    sabnzbd.DIR_PROG = os.path.dirname(sabnzbd.MY_FULLNAME)
    sabnzbd.DIR_INTERFACES = real_path(sabnzbd.DIR_PROG, DEF_INTERFACES)
    sabnzbd.DIR_LANGUAGE = real_path(sabnzbd.DIR_PROG, DEF_LANGUAGE)
    org_dir = os.getcwd()

    # Need console logging for SABnzbd.py and SABnzbd-console.exe
    console_logging = (not hasattr(sys, "frozen")) or (sabnzbd.MY_NAME.lower().find('-console') > 0)
    console_logging = console_logging and not sabnzbd.DAEMON

    LOGLEVELS = (logging.FATAL, logging.WARNING, logging.INFO, logging.DEBUG)

    # Setup primary logging to prevent default console logging
    gui_log = GUIHandler(MAX_WARNINGS)
    gui_log.setLevel(logging.WARNING)
    format_gui = '%(asctime)s\n%(levelname)s\n%(message)s'
    gui_log.setFormatter(logging.Formatter(format_gui))
    sabnzbd.GUIHANDLER = gui_log

    # Create logger
    logger = logging.getLogger('')
    logger.setLevel(logging.WARNING)
    logger.addHandler(gui_log)

    # Detect Windows variant
    if sabnzbd.WIN32:
        vista_plus, win64 = windows_variant()
        sabnzbd.WIN64 = win64

    if inifile:
        # INI file given, simplest case
        inifile = evaluate_inipath(inifile)
    else:
        # No ini file given, need profile data
        get_user_profile_paths(vista_plus)
        # Find out where INI file is
        inifile = os.path.abspath(os.path.join(sabnzbd.DIR_LCLDATA, DEF_INI_FILE))

    # Long-path notation on Windows to be sure
    inifile = long_path(inifile)

    # If INI file at non-std location, then use INI location as $HOME
    if sabnzbd.DIR_LCLDATA != os.path.dirname(inifile):
        sabnzbd.DIR_HOME = os.path.dirname(inifile)

    # All system data dirs are relative to the place we found the INI file
    sabnzbd.DIR_LCLDATA = os.path.dirname(inifile)

    if not os.path.exists(inifile) and not os.path.exists(inifile + '.bak') and not os.path.exists(sabnzbd.DIR_LCLDATA):
        try:
            os.makedirs(sabnzbd.DIR_LCLDATA)
        except IOError:
            panic('Cannot create folder "%s".' % sabnzbd.DIR_LCLDATA, 'Check specified INI file location.')
            exit_sab(1)

    sabnzbd.cfg.set_root_folders(sabnzbd.DIR_HOME, sabnzbd.DIR_LCLDATA)

    res, msg = config.read_config(inifile)
    if not res:
        panic(msg, 'Specify a correct file or delete this file.')
        exit_sab(1)

    # Set root folders for HTTPS server file paths
    sabnzbd.cfg.set_root_folders2()

    if ipv6_hosting is not None:
        sabnzbd.cfg.ipv6_hosting.set(ipv6_hosting)

    # Determine web host address
    cherryhost, cherryport, browserhost, https_port = get_webhost(cherryhost, cherryport, https_port)
    enable_https = sabnzbd.cfg.enable_https()

    # When this is a daemon, just check and bail out if port in use
    if sabnzbd.DAEMON:
        if enable_https and https_port:
            try:
                portend.free(cherryhost, https_port, timeout=0.05)
            except IOError:
                abort_and_show_error(browserhost, cherryport)
            except:
                abort_and_show_error(browserhost, cherryport, '49')
        try:
            portend.free(cherryhost, cherryport, timeout=0.05)
        except IOError:
            abort_and_show_error(browserhost, cherryport)
        except:
            abort_and_show_error(browserhost, cherryport, '49')

    # Windows instance is reachable through registry
    url = None
    if sabnzbd.WIN32 and not new_instance:
        url = get_connection_info()
        if url and check_for_sabnzbd(url, upload_nzbs, autobrowser):
            exit_sab(0)

    # SSL
    if enable_https:
        port = https_port or cherryport
        try:
            portend.free(browserhost, port, timeout=0.05)
        except IOError as error:
            if str(error) == 'Port not bound.':
                pass
            else:
                if not url:
                    url = 'https://%s:%s%s/api?' % (browserhost, port, sabnzbd.cfg.url_base())
                if new_instance or not check_for_sabnzbd(url, upload_nzbs, autobrowser):
                    # Bail out if we have fixed our ports after first start-up
                    if sabnzbd.cfg.fixed_ports():
                        abort_and_show_error(browserhost, cherryport)
                    # Find free port to bind
                    newport = find_free_port(browserhost, port)
                    if newport > 0:
                        # Save the new port
                        if https_port:
                            https_port = newport
                            sabnzbd.cfg.https_port.set(newport)
                        else:
                            # In case HTTPS == HTTP port
                            cherryport = newport
                            sabnzbd.cfg.cherryport.set(newport)
        except:
            # Something else wrong, probably badly specified host
            abort_and_show_error(browserhost, cherryport, '49')

    # NonSSL check if there's no HTTPS or we only use 1 port
    if not (enable_https and not https_port):
        try:
            portend.free(browserhost, cherryport, timeout=0.05)
        except IOError as error:
            if str(error) == 'Port not bound.':
                pass
            else:
                if not url:
                    url = 'http://%s:%s%s/api?' % (browserhost, cherryport, sabnzbd.cfg.url_base())
                if new_instance or not check_for_sabnzbd(url, upload_nzbs, autobrowser):
                    # Bail out if we have fixed our ports after first start-up
                    if sabnzbd.cfg.fixed_ports():
                        abort_and_show_error(browserhost, cherryport)
                    # Find free port to bind
                    port = find_free_port(browserhost, cherryport)
                    if port > 0:
                        sabnzbd.cfg.cherryport.set(port)
                        cherryport = port
        except:
            # Something else wrong, probably badly specified host
            abort_and_show_error(browserhost, cherryport, '49')

    # We found a port, now we never check again
    sabnzbd.cfg.fixed_ports.set(True)

    # Logging-checks
    logdir = sabnzbd.cfg.log_dir.get_path()
    if fork and not logdir:
        print("Error: I refuse to fork without a log directory!")
        sys.exit(1)

    if clean_up:
        xlist = globber_full(logdir)
        for x in xlist:
            if RSS_FILE_NAME not in x:
                try:
                    os.remove(x)
                except:
                    pass

    # Prevent the logger from raising exceptions
    # primarily to reduce the fallout of Python issue 4749
    logging.raiseExceptions = 0

    # Log-related constants we always need
    if logging_level is None:
        logging_level = sabnzbd.cfg.log_level()
    else:
        sabnzbd.cfg.log_level.set(logging_level)
    sabnzbd.LOGFILE = os.path.join(logdir, DEF_LOG_FILE)
    logformat = '%(asctime)s::%(levelname)s::[%(module)s:%(lineno)d] %(message)s'
    logger.setLevel(LOGLEVELS[logging_level + 1])

    try:
        if not no_file_log:
            rollover_log = logging.handlers.RotatingFileHandler(
                sabnzbd.LOGFILE, 'a+',
                sabnzbd.cfg.log_size.get_int(),
                sabnzbd.cfg.log_backups())
            rollover_log.setFormatter(logging.Formatter(logformat))
            logger.addHandler(rollover_log)

    except IOError:
        print("Error:")
        print("Can't write to logfile")
        exit_sab(2)

    # Fork on non-Windows processes
    if fork and not sabnzbd.WIN32:
        daemonize()
    else:
        if console_logging:
            console = logging.StreamHandler()
            console.setLevel(LOGLEVELS[logging_level + 1])
            console.setFormatter(logging.Formatter(logformat))
            logger.addHandler(console)
        if no_file_log:
            logging.info('Console logging only')

    logging.info('--------------------------------')
    logging.info('%s-%s (rev=%s)', sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.__baseline__)
    logging.info('Full executable path = %s', sabnzbd.MY_FULLNAME)
    if sabnzbd.WIN32:
        suffix = ''
        if win64:
            suffix = '(win64)'
        try:
            logging.info('Platform = %s %s', platform.platform(), suffix)
        except:
            logging.info('Platform = %s <unknown>', suffix)
    else:
        logging.info('Platform = %s', os.name)
    logging.info('Python-version = %s', sys.version)
    logging.info('Arguments = %s', sabnzbd.CMDLINE)
    if sabnzbd.DOCKER:
        logging.info("Running inside a docker container")
    else:
        logging.info("Not inside a docker container")

    # Find encoding; relevant for external processing activities
    logging.info('Preferred encoding = %s', sabnzbd.encoding.CODEPAGE)

    # On Linux/FreeBSD/Unix "UTF-8" is strongly, strongly adviced:
    if not sabnzbd.WIN32 and not sabnzbd.DARWIN and not ('utf-8' in sabnzbd.encoding.CODEPAGE.lower()):
        logging.warning(T("SABnzbd was started with encoding %s, this should be UTF-8. Expect problems with Unicoded file and directory names in downloads.") % sabnzbd.encoding.CODEPAGE)

    # SSL Information
    logging.info("SSL version = %s", ssl.OPENSSL_VERSION)

    # Load (extra) certificates in the binary distributions
    if hasattr(sys, "frozen") and (sabnzbd.WIN32 or sabnzbd.DARWIN):
        # The certifi package brings the latest certificates on build
        # This will cause the create_default_context to load it automatically
        os.environ["SSL_CERT_FILE"] = os.path.join(sabnzbd.DIR_PROG, 'cacert.pem')
        logging.info('Loaded additional certificates from %s', os.environ["SSL_CERT_FILE"])

    # Extra startup info
    if sabnzbd.cfg.log_level() > 1:
        # List the number of certificates available (can take up to 1.5 seconds)
        ctx = ssl.create_default_context()
        logging.debug('Available certificates: %s', repr(ctx.cert_store_stats()))

        # Show IPv4/IPv6 address
        from sabnzbd.getipaddress import localipv4, publicipv4, ipv6

        mylocalipv4 = localipv4()
        if mylocalipv4:
            logging.debug('My local IPv4 address = %s', mylocalipv4)
        else:
            logging.debug('Could not determine my local IPv4 address')

        mypublicipv4 = publicipv4()
        if mypublicipv4:
            logging.debug('My public IPv4 address = %s', mypublicipv4)
        else:
            logging.debug('Could not determine my public IPv4 address')

        myipv6 = ipv6()
        if myipv6:
            logging.debug('My IPv6 address = %s', myipv6)
        else:
            logging.debug('Could not determine my IPv6 address')

        # Measure and log system performance measured by pystone and - if possible - CPU model
        from sabnzbd.utils.getperformance import getpystone, getcpu
        pystoneperf = getpystone()
        if pystoneperf:
            logging.debug('CPU Pystone available performance = %s', pystoneperf)
        else:
            logging.debug('CPU Pystone available performance could not be calculated')
        cpumodel = getcpu()  # Linux only
        if cpumodel:
            logging.debug('CPU model = %s', cpumodel)

    logging.info('Using INI file %s', inifile)

    if autobrowser is not None:
        sabnzbd.cfg.autobrowser.set(autobrowser)

    sabnzbd.initialize(pause, clean_up, evalSched=True, repair=repair)

    os.chdir(sabnzbd.DIR_PROG)

    sabnzbd.WEB_DIR = identify_web_template(sabnzbd.cfg.web_dir, DEF_STDINTF, fix_webname(web_dir))
    sabnzbd.WEB_DIR_CONFIG = identify_web_template(None, DEF_STDCONFIG, '')
    sabnzbd.WIZARD_DIR = os.path.join(sabnzbd.DIR_INTERFACES, 'wizard')

    sabnzbd.WEB_COLOR = check_template_scheme(sabnzbd.cfg.web_color(), sabnzbd.WEB_DIR)
    sabnzbd.cfg.web_color.set(sabnzbd.WEB_COLOR)

    # Handle the several tray icons
    if sabnzbd.cfg.win_menu() and not sabnzbd.DAEMON:
        if sabnzbd.WIN32:
            import sabnzbd.sabtray
            sabnzbd.WINTRAY = sabnzbd.sabtray.SABTrayThread()
        elif sabnzbd.LINUX_POWER and os.environ.get('DISPLAY'):
            try:
                import gi
                gi.require_version('Gtk', '3.0')
                from gi.repository import Gtk
                import sabnzbd.sabtraylinux
                sabnzbd.LINUXTRAY = sabnzbd.sabtraylinux.StatusIcon()
            except:
                logging.info("python3-gi not found, no SysTray.")

    # Find external programs
    sabnzbd.newsunpack.find_programs(sabnzbd.DIR_PROG)
    print_modules()

    # HTTPS certificate generation
    https_cert = sabnzbd.cfg.https_cert.get_path()
    https_key = sabnzbd.cfg.https_key.get_path()
    https_chain = sabnzbd.cfg.https_chain.get_path()
    if not (sabnzbd.cfg.https_chain() and os.path.exists(https_chain)):
        https_chain = None

    if enable_https:
        # If either the HTTPS certificate or key do not exist, make some self-signed ones.
        if not (https_cert and os.path.exists(https_cert)) or not (https_key and os.path.exists(https_key)):
            create_https_certificates(https_cert, https_key)

        if not (os.path.exists(https_cert) and os.path.exists(https_key)):
            logging.warning(T('Disabled HTTPS because of missing CERT and KEY files'))
            enable_https = False
            sabnzbd.cfg.enable_https.set(False)

        # So the cert and key files do exist, now let's check if they are valid:
        trialcontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            trialcontext.load_cert_chain(https_cert, https_key)
            logging.info("HTTPS keys are OK")
        except:
            logging.warning(T('Disabled HTTPS because of invalid CERT and KEY files'))
            logging.info("Traceback: ", exc_info=True)
            enable_https = False
            sabnzbd.cfg.enable_https.set(False)

    # Starting of the webserver
    # Determine if this system has multiple definitions for 'localhost'
    hosts = all_localhosts()
    multilocal = len(hosts) > 1 and cherryhost in ('localhost', '0.0.0.0')

    # For 0.0.0.0 CherryPy will always pick IPv4, so make sure the secondary localhost is IPv6
    if multilocal and cherryhost == '0.0.0.0' and hosts[1] == '127.0.0.1':
        hosts[1] = '::1'

    # The Windows binary requires numeric localhost as primary address
    if cherryhost == 'localhost':
        cherryhost = hosts[0]

    if enable_https:
        if https_port:
            # Extra HTTP port for primary localhost
            attach_server(cherryhost, cherryport)
            if multilocal:
                # Extra HTTP port for secondary localhost
                attach_server(hosts[1], cherryport)
                # Extra HTTPS port for secondary localhost
                attach_server(hosts[1], https_port, https_cert, https_key, https_chain)
            cherryport = https_port
        elif multilocal:
            # Extra HTTPS port for secondary localhost
            attach_server(hosts[1], cherryport, https_cert, https_key, https_chain)

        cherrypy.config.update({'server.ssl_module': 'builtin',
                                'server.ssl_certificate': https_cert,
                                'server.ssl_private_key': https_key,
                                'server.ssl_certificate_chain': https_chain})
    elif multilocal:
        # Extra HTTP port for secondary localhost
        attach_server(hosts[1], cherryport)

    if no_login:
        sabnzbd.cfg.username.set('')
        sabnzbd.cfg.password.set('')

    mime_gzip = ('text/*',
                 'application/javascript',
                 'application/x-javascript',
                 'application/json',
                 'application/xml',
                 'application/vnd.ms-fontobject',
                 'application/font*',
                 'image/svg+xml'
                 )
    cherrypy.config.update({'server.environment': 'production',
                            'server.socket_host': cherryhost,
                            'server.socket_port': cherryport,
                            'server.shutdown_timeout': 0,
                            'log.screen': False,
                            'engine.autoreload.on': False,
                            'tools.encode.on': True,
                            'tools.gzip.on': True,
                            'tools.gzip.mime_types': mime_gzip,
                            'request.show_tracebacks': True,
                            'error_page.401': sabnzbd.panic.error_page_401,
                            'error_page.404': sabnzbd.panic.error_page_404
                            })

    # Do we want CherryPy Logging? Cannot be done via the config
    if cherrypylogging:
        sabnzbd.WEBLOGFILE = os.path.join(logdir, DEF_LOG_CHERRY)
        cherrypy.log.screen = True
        cherrypy.log.access_log.propagate = True
        cherrypy.log.access_file = str(sabnzbd.WEBLOGFILE)
    else:
        cherrypy.log.access_log.propagate = False

    # Force mimetypes (OS might overwrite them)
    forced_mime_types = {'css': 'text/css', 'js': 'application/javascript'}

    static = {'tools.staticdir.on': True, 'tools.staticdir.dir': os.path.join(sabnzbd.WEB_DIR, 'static'), 'tools.staticdir.content_types': forced_mime_types}
    staticcfg = {'tools.staticdir.on': True, 'tools.staticdir.dir': os.path.join(sabnzbd.WEB_DIR_CONFIG, 'staticcfg'), 'tools.staticdir.content_types': forced_mime_types}
    wizard_static = {'tools.staticdir.on': True, 'tools.staticdir.dir': os.path.join(sabnzbd.WIZARD_DIR, 'static'), 'tools.staticdir.content_types': forced_mime_types}

    appconfig = {'/api': {
                            'tools.auth_basic.on': False,
                            'tools.response_headers.on': True,
                            'tools.response_headers.headers': [('Access-Control-Allow-Origin', '*')]
                         },
                 '/static': static,
                 '/wizard/static': wizard_static,
                 '/favicon.ico': {'tools.staticfile.on': True, 'tools.staticfile.filename': os.path.join(sabnzbd.WEB_DIR_CONFIG, 'staticcfg', 'ico', 'favicon.ico')},
                 '/staticcfg': staticcfg
                 }

    # Make available from both URLs
    main_page = sabnzbd.interface.MainPage()
    cherrypy.tree.mount(main_page, '/', config=appconfig)
    cherrypy.tree.mount(main_page, sabnzbd.cfg.url_base(), config=appconfig)

    # Set authentication for CherryPy
    sabnzbd.interface.set_auth(cherrypy.config)
    logging.info('Starting web-interface on %s:%s', cherryhost, cherryport)

    sabnzbd.cfg.log_level.callback(guard_loglevel)

    try:
        cherrypy.engine.start()
    except:
        logging.error(T('Failed to start web-interface: '), exc_info=True)
        abort_and_show_error(browserhost, cherryport)

    # Wait for server to become ready
    cherrypy.engine.wait(cherrypy.process.wspbus.states.STARTED)


    if sabnzbd.WIN32:
        if enable_https:
            mode = 's'
        else:
            mode = ''
        api_url = 'http%s://%s:%s%s/api?apikey=%s' % (mode, browserhost, cherryport, sabnzbd.cfg.url_base(), sabnzbd.cfg.api_key())

        # Write URL directly to registry
        set_connection_info(api_url)

    if pid_path or pid_file:
        sabnzbd.pid_file(pid_path, pid_file, cherryport)

    # Stop here in case of fatal errors
    if sabnzbd.NO_DOWNLOADING:
        return

    # Start all SABnzbd tasks
    logging.info('Starting %s-%s', sabnzbd.MY_NAME, sabnzbd.__version__)
    try:
        sabnzbd.start()
    except:
        logging.exception("Failed to start %s-%s", sabnzbd.MY_NAME, sabnzbd.__version__)
        sabnzbd.halt()

    # Upload any nzb/zip/rar/nzb.gz/nzb.bz2 files from file association
    if upload_nzbs:
        from sabnzbd.utils.upload import add_local
        for f in upload_nzbs:
            add_local(f)

    # Set URL for browser
    if enable_https:
        browser_url = "https://%s:%s%s" % (browserhost, cherryport, sabnzbd.cfg.url_base())
    else:
        browser_url = "http://%s:%s%s" % (browserhost, cherryport, sabnzbd.cfg.url_base())
    sabnzbd.BROWSER_URL = browser_url

    if not autorestarted:
        launch_a_browser(browser_url)
        notifier.send_notification('SABnzbd', T('SABnzbd %s started') % sabnzbd.__version__, 'startup')
        # Now's the time to check for a new version
        check_latest_version()
    autorestarted = False

    # ZeroConfig/Bonjour needs a ip. Lets try to find it.
    try:
        z_host = socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        z_host = cherryhost
    sabnzbd.zconfig.set_bonjour(z_host, cherryport)

    # Have to keep this running, otherwise logging will terminate
    timer = 0
    while not sabnzbd.SABSTOP:
        if sabnzbd.LAST_WARNING:
            msg = sabnzbd.LAST_WARNING
            sabnzbd.LAST_WARNING = None
            sabnzbd.notifier.send_notification(T('Warning'), msg, 'warning')
        if sabnzbd.LAST_ERROR:
            msg = sabnzbd.LAST_ERROR
            sabnzbd.LAST_ERROR = None
            sabnzbd.notifier.send_notification(T('Error'), msg, 'error')

        time.sleep(3)

        # Check for loglevel changes
        if LOG_FLAG:
            LOG_FLAG = False
            level = LOGLEVELS[sabnzbd.cfg.log_level() + 1]
            logger.setLevel(level)
            if console_logging:
                console.setLevel(level)

        # 30 sec polling tasks
        if timer > 9:
            timer = 0
            # Keep OS awake (if needed)
            sabnzbd.keep_awake()
            # Restart scheduler (if needed)
            scheduler.restart()
            # Save config (if needed)
            config.save_config()
            # Check the threads
            if not sabnzbd.check_all_tasks():
                autorestarted = True
                sabnzbd.TRIGGER_RESTART = True
        else:
            timer += 1

        # 3 sec polling tasks
        # Check for auto-restart request
        # Or special restart cases like Mac and WindowsService
        if sabnzbd.TRIGGER_RESTART:
            # Shutdown
            sabnzbd.shutdown_program()

            if sabnzbd.downloader.Downloader.do.paused:
                sabnzbd.RESTART_ARGS.append('-p')
            if autorestarted:
                sabnzbd.RESTART_ARGS.append('--autorestarted')
            sys.argv = sabnzbd.RESTART_ARGS

            os.chdir(org_dir)
            # If OSX frozen restart of app instead of embedded python
            if hasattr(sys, "frozen") and sabnzbd.DARWIN:
                # [[NSProcessInfo processInfo] processIdentifier]]
                # logging.info("%s" % (NSProcessInfo.processInfo().processIdentifier()))
                my_pid = os.getpid()
                my_name = sabnzbd.MY_FULLNAME.replace('/Contents/MacOS/SABnzbd', '')
                my_args = ' '.join(sys.argv[1:])
                cmd = 'kill -9 %s && open "%s" --args %s' % (my_pid, my_name, my_args)
                logging.info('Launching: ', cmd)
                os.system(cmd)
            elif sabnzbd.WIN_SERVICE:
                # Use external service handler to do the restart
                # Wait 5 seconds to clean up
                subprocess.Popen('timeout 5 & sc start SABnzbd', shell=True)
            else:
                cherrypy.engine._do_execv()

    config.save_config()

    if sabnzbd.WINTRAY:
        sabnzbd.WINTRAY.terminate = True
    if sabnzbd.WIN32:
        del_connection_info()

    # Send our final goodbyes!
    notifier.send_notification('SABnzbd', T('SABnzbd shutdown finished'), 'startup')
    logging.info('Leaving SABnzbd')
    sys.stderr.flush()
    sys.stdout.flush()
    sabnzbd.pid_file()

    if hasattr(sys, "frozen") and sabnzbd.DARWIN:
        try:
            AppHelper.stopEventLoop()
        except:
            # Failing AppHelper libary!
            os._exit(0)
    elif sabnzbd.WIN_SERVICE:
        # Do nothing, let service handle it
        pass
    else:
        os._exit(0)


##############################################################################
# Windows Service Support
##############################################################################


if sabnzbd.WIN32:
    import servicemanager

    class SABnzbd(win32serviceutil.ServiceFramework):
        """ Win32 Service Handler """
        _svc_name_ = 'SABnzbd'
        _svc_display_name_ = 'SABnzbd Binary Newsreader'
        _svc_deps_ = ["EventLog", "Tcpip"]
        _svc_description_ = 'Automated downloading from Usenet. ' \
                          'Set to "automatic" to start the service at system startup. ' \
                          'You may need to login with a real user account when you need ' \
                          'access to network shares.'

        # Only SABnzbd-console.exe can print to the console, so the service is installed
        # from there. But we run SABnzbd.exe so nothing is logged. Logging can cause the
        # Windows Service to stop because the output buffers are full.
        if hasattr(sys, "frozen"):
            _exe_name_ = "SABnzbd.exe"

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            sabnzbd.WIN_SERVICE = self

        def SvcDoRun(self):
            msg = 'SABnzbd-service %s' % sabnzbd.__version__
            self.Logger(servicemanager.PYS_SERVICE_STARTED, msg + ' has started')
            sys.argv = get_serv_parms(self._svc_name_)
            main()
            self.Logger(servicemanager.PYS_SERVICE_STOPPED, msg + ' has stopped')

        def SvcStop(self):
            sabnzbd.shutdown_program()
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)

        def Logger(self, state, msg):
            win32evtlogutil.ReportEvent(self._svc_display_name_,
                                        state, 0,
                                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                                        (self._svc_name_, msg))

        def ErrLogger(self, msg, text):
            win32evtlogutil.ReportEvent(self._svc_display_name_,
                                        servicemanager.PYS_SERVICE_STOPPED, 0,
                                        servicemanager.EVENTLOG_ERROR_TYPE,
                                        (self._svc_name_, msg), text)


SERVICE_MSG = """
You may need to set additional Service parameters!
Verify the settings in Windows Services (services.msc).

https://sabnzbd.org/wiki/advanced/sabnzbd-as-a-windows-service
"""


def handle_windows_service():
    """ Handle everything for Windows Service
        Returns True when any service commands were detected or
        when we have started as a service.
    """
    # Detect if running as Windows Service (only Vista and above!)
    # Adapted from https://stackoverflow.com/a/55248281/5235502
    if win32ts.ProcessIdToSessionId(win32api.GetCurrentProcessId()) == 0:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SABnzbd)
        servicemanager.StartServiceCtrlDispatcher()
        return True

    # Handle installation and other options
    service, sab_opts, serv_opts, _upload_nzbs = commandline_handler()

    if service:
        if service in ('install', 'update'):
            # In this case check for required parameters
            path = get_f_option(sab_opts)
            if not path:
                print(('The -f <path> parameter is required.\n' \
                      'Use: -f <path> %s' % service))
                return True

            # First run the service installed, because this will
            # set the service key in the Registry
            win32serviceutil.HandleCommandLine(SABnzbd, argv=serv_opts)

            # Add our own parameter to the Registry
            if set_serv_parms(SABnzbd._svc_name_, sab_opts):
                print(SERVICE_MSG)
            else:
                print('ERROR: Cannot set required registry info.')
        else:
            # Pass the other commands directly
            win32serviceutil.HandleCommandLine(SABnzbd)

    return bool(service)


##############################################################################
# Platform specific startup code
##############################################################################


if __name__ == '__main__':
    # We can only register these in the main thread
    signal.signal(signal.SIGINT, sabnzbd.sig_handler)
    signal.signal(signal.SIGTERM, sabnzbd.sig_handler)

    if sabnzbd.WIN32:
        if not handle_windows_service():
            main()

    elif sabnzbd.DARWIN and sabnzbd.FOUNDATION:

        # OSX binary runner
        from threading import Thread
        from PyObjCTools import AppHelper
        from AppKit import NSApplication
        from sabnzbd.osxmenu import SABnzbdDelegate

        # Need to run the main application in separate thread because the eventLoop
        # has to be in the main thread. The eventLoop is required for the menu.
        # This code is made with trial-and-error, please improve!
        class startApp(Thread):
            def run(self):
                logging.info('[osx] sabApp Starting - starting main thread')
                main()
                logging.info('[osx] sabApp Stopping - main thread quit ')
                AppHelper.stopEventLoop()


        sabApp = startApp()
        sabApp.start()

        # Initialize the menu
        shared_app = NSApplication.sharedApplication()
        sabnzbd_menu = SABnzbdDelegate.alloc().init()
        shared_app.setDelegate_(sabnzbd_menu)
        # Build the menu
        sabnzbd_menu.awakeFromNib()
        # Run the main eventloop
        AppHelper.runEventLoop()
    else:
        main()
