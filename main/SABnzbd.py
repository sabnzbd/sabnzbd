#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#           2008 The ShyPike <shypike@users.sourceforge.net>
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
if sys.hexversion < 0x020403F0:
    print "Sorry, requires Python 2.4.3 or higher."
    exit(1)

import logging
import logging.handlers
import os
import getopt
import signal
import re
import glob
import socket
if os.name=='nt':
    import platform
    
try:
    import Cheetah
    if Cheetah.Version[0] != '2':
        raise ValueError
except:
    print "Sorry, requires Python module Cheetah 2.0rc7 or higher."
    exit(1)

import cherrypy

import sabnzbd
from sabnzbd.utils.configobj import ConfigObj, ConfigObjError
from sabnzbd.__init__ import check_setting_str, check_setting_int, dir_setup
from sabnzbd.interface import *
from sabnzbd.constants import *
from sabnzbd.newsunpack import find_programs
from sabnzbd.misc import Get_User_ShellFolders, save_configfile, launch_a_browser, from_units, \
                         check_latest_version, Panic_Templ, Panic_Port, Panic_FWall, Panic, ExitSab, \
                         decodePassword, Notify, SplitHost

from threading import Thread

cfg = {}

#------------------------------------------------------------------------------
signal.signal(signal.SIGINT, sabnzbd.sig_handler)
signal.signal(signal.SIGTERM, sabnzbd.sig_handler)

try:
    import win32api
    win32api.SetConsoleCtrlHandler(sabnzbd.sig_handler, True)
except ImportError:
    if os.name == 'nt':
        print "Sorry, requires Python module PyWin32."
        exit(1)


#------------------------------------------------------------------------------
class guiHandler(logging.Handler):
    """
    Logging handler collects the last warnings/errors/exceptions
    to be displayed in the web-gui
    """
    def __init__(self, size):
        """
        Initializes the handler
        """
        logging.Handler.__init__(self)
        self.size = size
        self.store = []

    def emit(self, record):
        """
        Emit a record by adding it to our private queue
        """
        if len(self.store) >= self.size:
            # Loose the oldest record
            self.store.pop(0)
        self.store.append(self.format(record))

    def clear(self):
        self.store = []

    def content(self):
        """
        Return an array with last records
        """
        return self.store


#------------------------------------------------------------------------------

def print_help():
    print
    print "Usage: %s [-f <configfile>] <other options>" % sabnzbd.MY_NAME
    print
    print "Options marked [*] are stored in the config file"
    print
    print "Options:"
    print "  -f  --config-file <ini>  Location of config file"
    print "  -s  --server <srv:port>  Listen on server:port [*]"
    print "  -t  --templates <templ>  Template directory [*]"
    print "  -2  --template2 <templ>  Secondary template dir [*]"
    print
    print "  -l  --logging <0..2>     Set logging level (0= least, 2= most) [*]"
    print "  -w  --weblogging <0..1>  Set cherrypy logging (0= off, 1= on) [*]"
    print
    print "  -b  --browser <0..1>     Auto browser launch (0= off, 1= on) [*]"
    if os.name != 'nt':
        print "  -d  --daemon             Fork daemon process"
        print "      --permissions        Set the chmod mode (e.g. o=rwx,g=rwx) [*]"
    else:
        print "  -d  --daemon             Use when run as a service"
    print
    print "      --force              Discard web-port timeout (see Wiki!)"
    print "  -h  --help               Print this message"
    print "  -v  --version            Print version information"
    print "  -c  --clean              Remove queue, cache and logs"
    print "  -p  --pause              Start in paused mode"

def print_version():
    print "%s-%s" % (sabnzbd.MY_NAME, sabnzbd.__version__)




def daemonize():
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        print "fork() failed"
        sys.exit(1)

    os.chdir("/")
    os.setsid()
    # Make sure I can read my own files and shut out others
    prev= os.umask(0)
    os.umask(prev and int('077',8))

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        print "fork() failed"
        sys.exit(1)

    dev_null = file('/dev/null', 'r')
    os.dup2(dev_null.fileno(), sys.stdin.fileno())


def Bail_Out(browserhost, cherryport):
    """Abort program because of CherryPy troubles
    """
    logging.exception("Failed to start web-interface")
    Panic_Port(browserhost, cherryport)
    sabnzbd.halt()
    ExitSab(2)

def Web_Template(key, defweb, wdir):
    """ Determine a correct web template set,
        return full template path
    """
    if wdir == None:
        try:
            wdir = cfg['misc'][key]
        except:
            wdir = ''
    if not wdir:
        wdir = defweb
    cfg['misc'][key] = wdir
    if not wdir:
        # No default value defined, accept empty path
        return ''

    full_dir = real_path(sabnzbd.DIR_INTERFACES, wdir)
    full_main = real_path(full_dir, DEF_MAIN_TMPL)
    logging.info("Web dir is %s", full_dir)

    if not os.path.exists(full_main):
        logging.warning('Cannot find web template: %s, trying standard template', full_main)
        full_dir = real_path(sabnzbd.DIR_INTERFACES, DEF_STDINTF)
        full_main = real_path(full_dir, DEF_MAIN_TMPL)
        if not os.path.exists(full_main):
            logging.exception('Cannot find standard template: %s', full_dir)
            Panic_Templ(full_dir)
            ExitSab(1)

    return real_path(full_dir, "templates")


def GetProfileInfo(vista):
    """ Get the default data locations
    """
    ok = False
    if sabnzbd.DAEMON:
        # In daemon mode, do not try to access the user profile
        # just assume that everything defaults to the program dir
        sabnzbd.DIR_APPDATA = sabnzbd.DIR_PROG
        sabnzbd.DIR_LCLDATA = sabnzbd.DIR_PROG
        sabnzbd.DIR_HOME = sabnzbd.DIR_PROG
        if os.name == 'nt':
            # Ignore Win23 "logoff" signal
            # This should work, but it doesn't
            # Instead the signal_handler will ignore the "logoff" signal
            signal.signal(5, signal.SIG_IGN)
        ok = True
    elif os.name == 'nt':
        specials = Get_User_ShellFolders()
        try:
            sabnzbd.DIR_APPDATA = '%s\\%s' % (specials['AppData'], DEF_WORKDIR)
            sabnzbd.DIR_LCLDATA = '%s\\%s' % (specials['Local AppData'], DEF_WORKDIR)
            sabnzbd.DIR_HOME = specials['Personal']
            ok = True
        except:
            try:
                if vista:
                    root = os.environ['AppData']
                    user = os.environ['USERPROFILE']
                    sabnzbd.DIR_APPDATA = '%s\\%s' % (root.replace('\\Roaming', '\\Local'), DEF_WORKDIR)
                    sabnzbd.DIR_HOME    = '%s\\Documents' % user
                else:
                    root = os.environ['USERPROFILE']
                    sabnzbd.DIR_APPDATA = '%s\\%s' % (root, DEF_WORKDIR)
                    sabnzbd.DIR_HOME = root

                try:
                    # Conversion to 8bit ASCII required for CherryPy
                    sabnzbd.DIR_APPDATA = sabnzbd.DIR_APPDATA.encode('latin-1')
                    sabnzbd.DIR_HOME = sabnzbd.DIR_HOME.encode('latin-1')
                    ok = True
                except:
                    # If unconvertible characters exist, use MSDOS name
                    try:
                        sabnzbd.DIR_APPDATA = win32api.GetShortPathName(sabnzbd.DIR_APPDATA)
                        sabnzbd.DIR_HOME = win32api.GetShortPathName(sabnzbd.DIR_HOME)
                        ok = True
                    except:
                        pass
                sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
            except:
                pass                        

    else:
        # Unix/Linux/OSX
    	sabnzbd.DIR_APPDATA = '%s/.%s' % (os.environ['HOME'], DEF_WORKDIR)
    	sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
    	sabnzbd.DIR_HOME = os.environ['HOME']
    	ok = True

    if not ok:
        Panic("Cannot access the user profile.",
              "Please start with sabnzbd.ini file in another location")
        ExitSab(2)



def main():
    global cfg

    sabnzbd.MY_FULLNAME = os.path.normpath(os.path.abspath(sys.argv[0]))
    sabnzbd.MY_NAME = os.path.basename(sabnzbd.MY_FULLNAME)
    sabnzbd.DIR_PROG = os.path.dirname(sabnzbd.MY_FULLNAME)
    sabnzbd.DIR_INTERFACES = real_path(sabnzbd.DIR_PROG, DEF_INTERFACES)

    # Need console logging for SABnzbd.py and SABnzbd-console.exe
    consoleLogging = (not hasattr(sys, "frozen")) or (sabnzbd.MY_NAME.lower().find('-console') > 0)

    LOGLEVELS = [ logging.WARNING, logging.INFO, logging.DEBUG ]

    # Setup primary logging to prevent default console logging
    gui_log = guiHandler(MAX_WARNINGS)
    gui_log.setLevel(logging.WARNING)
    format_gui = '%(asctime)s\n%(levelname)s\n%(message)s'
    gui_log.setFormatter(logging.Formatter(format_gui))
    sabnzbd.GUIHANDLER = gui_log

    # Create logger
    logger = logging.getLogger('')
    logger.setLevel(logging.WARNING)
    logger.addHandler(gui_log)


    try:
        opts, args = getopt.getopt(sys.argv[1:], "phdvncu:w:l:s:f:t:b:2:",
                     ['pause', 'help', 'daemon', 'nobrowser', 'clean', 'logging=', \
                      'weblogging=', 'umask=', 'server=', 'templates', 'permissions=', \
                      'template2', 'browser=', 'config-file=', 'delay=', 'force', 'version'])
    except getopt.GetoptError:
        print_help()
        ExitSab(2)

    fork = False
    pause = False
    f = None
    cherryhost = None
    cherryport = None
    cherrypylogging = None
    sabnzbd.AUTOBROWSER = None
    clean_up = False
    logging_level = None
    umask = None
    web_dir = None
    web_dir2 = None
    delay = 0.0
    vista = False
    vista64 = False
    force_web = False

    for o, a in opts:
        if (o in ('-d', '--daemon')):
            if os.name != 'nt':
                fork = True
            sabnzbd.AUTOBROWSER = 0
            sabnzbd.DAEMON = True
            consoleLogging = False
        if o in ('-h', '--help'):
            print_help()
            ExitSab(0)
        if o in ('-f', '--config-file'):
            f = a
        if o in ('-t', '--templates'):
            web_dir = a
        if o in ('-2', '--template2'):
            web_dir2 = a
        if o in ('-s', '--server'):
            (cherryhost, cherryport) = SplitHost(a)
        if o in ('-n', '--nobrowser'):
            sabnzbd.AUTOBROWSER = 0
        if o in ('-b', '--browser'):
            try:
                sabnzbd.AUTOBROWSER = int(a)
            except:
                sabnzbd.AUTOBROWSER = 1
        if o in ('-c', '--clean'):
            clean_up= True
        if o in ('-w', '--weblogging'):
            try:
                cherrypylogging = int(a)
            except:
                cherrypylogging = -1
            if cherrypylogging < 0 or cherrypylogging > 1:
                print_help()
                ExitSab(1)
        if o in ('-l', '--logging'):
            try:
                logging_level = int(a)
            except:
                logging_level = -1
            if logging_level < 0 or logging_level > 2:
                print_help()
                ExitSab(1)
        if o in ('--permissions'):
            umask = a
        if o in ('-v', '--version'):
            print_version()
            ExitSab(0)
        if o in ('-p', '--pause'):
            pause = True
        #if o in ('--delay'):
            # For debugging of memory leak only!!
            #try:
            #    delay = float(a)
            #except:
            #    pass
        if o in ('--force'):
            force_web = True


    # Detect Vista or higher
    if os.name == 'nt':
        if platform.platform().find('Windows-32bit') >= 0:
            vista = True
            vista64 = 'ProgramFiles(x86)' in os.environ

    if f:
        # INI file given, simplest case
        f = os.path.normpath(os.path.abspath(f))
    else:
        # No ini file given, need profile data
        GetProfileInfo(vista)
        # Find out where INI file is
        f = os.path.abspath(sabnzbd.DIR_PROG + '/' + DEF_INI_FILE)
        if not os.path.exists(f):
            f = os.path.abspath(sabnzbd.DIR_LCLDATA + '/' + DEF_INI_FILE)

    # If INI file at non-std location, then use program dir as $HOME
    if sabnzbd.DIR_LCLDATA != os.path.dirname(f):
        sabnzbd.DIR_HOME = os.path.dirname(f)

    # All system data dirs are relative to the place we found the INI file
    sabnzbd.DIR_LCLDATA = os.path.dirname(f)

    if not os.path.exists(f):
        # No file found, create default INI file
    	try:
    	    if not os.path.exists(sabnzbd.DIR_LCLDATA):
    	        os.makedirs(sabnzbd.DIR_LCLDATA)
    	    fp = open(f, "w")
    	    fp.write("__version__=%s\n[misc]\n[logging]\n" % sabnzbd.__configversion__)
    	    fp.close()
    	except:
    	    Panic('Cannot create file "%s".' % f, 'Check specified INI file location.')
            ExitSab(1)

    try:
        cfg = ConfigObj(f)
        try:
            my_version = cfg['__version__']
        except:
            my_version = sabnzbd.__configversion__
            cfg['__version__'] = my_version

    except ConfigObjError, strerror:
        Panic('"%s" is not a valid configuration file.' % f, \
              'Specify a correct file or delete this file.')
        ExitSab(1)

    if cherrypylogging == None:
        cherrypylogging = bool(check_setting_int(cfg, 'logging', 'enable_cherrypy_logging', 1))
    else:
        cfg['logging']['enable_cherrypy_logging'] = cherrypylogging

    if logging_level == None:
        logging_level = check_setting_int(cfg, 'logging', 'log_level', DEF_LOGLEVEL)
        if logging_level > 2:
            logging_level = 2
    else:
        cfg['logging']['log_level'] = logging_level

    my_logdir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, DEF_LOG_DIR)
    if fork and not my_logdir:
        print "Error:"
        print "I refuse to fork without a log directory!"
        sys.exit()

    logdir = ""

    logdir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, DEF_LOG_DIR)
    if clean_up:
        xlist= glob.glob(logdir + '/*')
        for x in xlist:
            if x.find(RSS_FILE_NAME) < 0:
                os.remove(x)

    try:
        sabnzbd.LOGFILE = os.path.join(logdir, DEF_LOG_FILE)
        logsize = check_setting_str(cfg, 'logging', 'max_log_size', '5M')
        logsize = int(from_units(logsize))
        rollover_log = logging.handlers.RotatingFileHandler(\
                       sabnzbd.LOGFILE, 'a+',
                       logsize,
                       check_setting_int(cfg, 'logging', 'log_backups', 5))

        rollover_log.setLevel(LOGLEVELS[logging_level])
        format = '%(asctime)s::%(levelname)s::%(message)s'
        rollover_log.setFormatter(logging.Formatter(format))
        sabnzbd.LOGHANDLER = rollover_log
        logger.addHandler(rollover_log)
        logger.setLevel(LOGLEVELS[logging_level])

    except IOError:
        print "Error:"
        print "Can't write to logfile"
        ExitSab(2)

    logging.info('--------------------------------')
    logging.info('\n%s-%s [%s]', sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_FULLNAME)


    if fork:
        try:
            sys.stderr.fileno
            sys.stdout.fileno
            my_logpath = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, DEF_LOG_DIR)
            ol_path = os.path.join(my_logpath, DEF_LOG_ERRFILE)
            out_log = file(ol_path, 'a+', 0)
            sys.stderr.flush()
            sys.stdout.flush()
            os.dup2(out_log.fileno(), sys.stderr.fileno())
            os.dup2(out_log.fileno(), sys.stdout.fileno())
        except AttributeError:
            pass

    else:
        try:
            sys.stderr.fileno
            sys.stdout.fileno

            if consoleLogging:
                console = logging.StreamHandler()
                console.setLevel(LOGLEVELS[logging_level])
                console.setFormatter(logging.Formatter(format))
                logger.addHandler(console)
        except AttributeError:
            pass

    logging.info('%s-%s', sabnzbd.MY_NAME, sabnzbd.__version__)

    if sabnzbd.AUTOBROWSER == None:
        sabnzbd.AUTOBROWSER = bool(check_setting_int(cfg, 'misc', 'auto_browser', 1))
    else:
        cfg['misc']['auto_browser'] = sabnzbd.AUTOBROWSER

    if umask == None:
        umask = check_setting_str(cfg, 'misc', 'permissions', '')
    if umask:
        cfg['misc']['permissions'] = umask

    sabnzbd.DEBUG_DELAY = delay
    sabnzbd.CFG = cfg

    init_ok = sabnzbd.initialize(pause, clean_up, evalSched=True)

    if not init_ok:
        logging.error('Initializing %s-%s failed, aborting',
                      sabnzbd.MY_NAME, sabnzbd.__version__)
        ExitSab(2)

    find_programs(sabnzbd.DIR_PROG)

    if sabnzbd.decoder.HAVE_YENC:
        logging.info("_yenc module... found!")
    else:
        logging.info("_yenc module... NOT found!")

    if sabnzbd.nzbstuff.HAVE_CELEMENTTREE:
        logging.info("celementtree module... found!")
    else:
        logging.info("celementtree module... NOT found!")

    if sabnzbd.newsunpack.PAR2_COMMAND:
        logging.info("par2 binary... found (%s)", sabnzbd.newsunpack.PAR2_COMMAND)
    else:
        logging.error("par2 binary... NOT found!")

    if sabnzbd.newsunpack.RAR_COMMAND:
        logging.info("rar binary... found (%s)", sabnzbd.newsunpack.RAR_COMMAND)
    else:
        logging.info("rar binary... NOT found")

    if sabnzbd.newsunpack.ZIP_COMMAND:
        logging.info("unzip binary... found (%s)", sabnzbd.newsunpack.ZIP_COMMAND)
    else:
        logging.info("unzip binary... NOT found!")

    if sabnzbd.newswrapper.HAVE_SSL:
        logging.info("pyOpenSSL... found (%s)", sabnzbd.newswrapper.HAVE_SSL)
    else:
        logging.info("pyOpenSSL... NOT found - try apt-get install python-pyopenssl (SSL is optional)")

    if cherryhost == None:
        cherryhost = check_setting_str(cfg, 'misc','host', DEF_HOST)
    else:
        cfg['misc']['host'] = cherryhost

    # Get IP address, but discard APIPA/IPV6
    # If only APIPA's or IPV6 are found, fall back to localhost
    ipv4 = ipv6 = False
    localhost = hostip = 'localhost'
    try:
        info = socket.getaddrinfo(socket.gethostname(), None)
    except:
        # Hostname does not resolve, use 0.0.0.0
        cherryhost = '0.0.0.0'
        info = socket.getaddrinfo(localhost, None)
    for item in info:
        ip = item[4][0]
        if ip.find('169.254.') == 0:
            pass # Is an APIPA
        elif ip.find(':') >= 0:
            ipv6 = True
        elif ip.find('.') >= 0:
            ipv4 = True
            hostip = ip
            break

    if ipv6 and ipv4:
        sabnzbd.AMBI_LOCALHOST = True
        logging.warning("IPV6 has priority on this system, potential Firefox issue")

    if cherryhost == '':
        if ipv6 and ipv4:
            # To protect Firefox users, use numeric IP
            cherryhost = hostip
            browserhost = hostip
        else:
            cherryhost = socket.gethostname()
            browserhost = cherryhost
    elif cherryhost == '0.0.0.0':
        # Just take the gamble for this
        cherryhost = ''
        browserhost = localhost
    elif cherryhost.find('[') >= 0 or cherryhost.find(':') >= 0:
        # IPV6
        browserhost = cherryhost
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
    if cherryhost.find('[') >= 0:
        try:
            info = socket.getaddrinfo(cherryhost, None)
        except:
            cherryhost = cherryhost.strip('[]')

    if cherryport == None:
        if os.name == 'nt':
            defport = DEF_PORT_WIN
        else:
            defport = DEF_PORT_UNIX
        cherryport= check_setting_int(cfg, 'misc', 'port', defport)
    else:
        cfg['misc']['port'] = cherryport

    log_dir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, DEF_LOG_DIR)

    web_dir  = Web_Template('web_dir',  DEF_STDINTF,  web_dir)
    web_dir2 = Web_Template('web_dir2', '', web_dir2)

    sabnzbd.WEB_DIR  = web_dir
    sabnzbd.WEB_DIR2 = web_dir2

    sabnzbd.interface.USERNAME = check_setting_str(cfg, 'misc', 'username', '')

    sabnzbd.interface.PASSWORD = decodePassword(check_setting_str(cfg, 'misc', 'password', '', False), 'web')

    if fork and os.name != 'nt':
        daemonize()

    # Save the INI file
    save_configfile(cfg)

    logging.info('Starting %s-%s', sabnzbd.MY_NAME, sabnzbd.__version__)
    try:
        sabnzbd.start()
    except:
        logging.exception("Failed to start %s-%s", sabnzbd.MY_NAME, sabnzbd.__version__)
        sabnzbd.halt()

    cherrylogtoscreen = False
    sabnzbd.WEBLOGFILE = None

    if cherrypylogging:
        if log_dir:
            sabnzbd.WEBLOGFILE = os.path.join(log_dir, DEF_LOG_CHERRY);
        if not fork:
            try:
                sys.stderr.fileno
                sys.stdout.fileno
                cherrylogtoscreen = True
            except:
                cherrylogtoscreen = False

    cherrypy.tree.mount(LoginPage(web_dir, '/sabnzbd/', web_dir2, '/sabnzbd/m/'), '/')

    cherrypy.config.update(updateMap={'server.environment': 'production',
                                 'server.socketHost': cherryhost,
                                 'server.socketPort': cherryport,
                                 'server.logToScreen': cherrylogtoscreen,
                                 'server.logFile': sabnzbd.WEBLOGFILE,
                                 'sessionFilter.on': True,
                                 '/sabnzbd': {'streamResponse': True},
                                 '/sabnzbd/static': {'staticFilter.on': True, 'staticFilter.dir': os.path.join(web_dir, 'static')},
                                 '/sabnzbd/m': {'streamResponse': True},
                                 '/sabnzbd/m/static': {'staticFilter.on': True, 'staticFilter.dir': os.path.join(web_dir2, 'static')}
                           })

    logging.info('Starting web-interface on %s:%s', cherryhost, cherryport)

    sabnzbd.LOGLEVEL = logging_level

    try:
        cherrypy.server.start(init_only=True)
        cherrypy.server.wait()
    except cherrypy.NotReady, error:
        if str(error) == 'Port not bound.':
            if not force_web:
                Panic_FWall(vista)
                sabnzbd.halt()
                ExitSab(2)
        else:
            Bail_Out(browserhost, cherryport)
    except:
        Bail_Out(browserhost, cherryport)

    launch_a_browser("http://%s:%s/sabnzbd" % (browserhost, cherryport))
    Notify("SAB_Launched", None)

    # Now's the time to check for a new version
    if sabnzbd.VERSION_CHECK:
        check_latest_version()

    # Have to keep this running, otherwise logging will terminate
    while cherrypy.server.ready:
        if sabnzbd.LOGLEVEL != logging_level:
            logging_level = sabnzbd.LOGLEVEL
            logger.setLevel(LOGLEVELS[logging_level])
        time.sleep(3)

    Notify("SAB_Shutdown", None)

if __name__ == '__main__':
    main()
