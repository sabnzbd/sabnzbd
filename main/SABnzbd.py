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
if not cherrypy.__version__.startswith("3.1."):
    print "Sorry, requires Python module Cherrypy 3.1.x"
    exit(1)

try:
    from sqlite3 import version as sqlite3_version
except:
    try:
        from pysqlite2.sqlite3 import version as sqlite3_version
    except:
        print "Sorry, requires Python module sqlite3 (pysqlite2 in python2.4)"
        if os.name != 'nt':
            print "Try: apt-get install python-pysqlite2"
        exit(1)

import sabnzbd
from sabnzbd.utils.configobj import ConfigObj, ConfigObjError
from sabnzbd.interface import *
from sabnzbd.constants import *
from sabnzbd.newsunpack import find_programs
from sabnzbd.misc import Get_User_ShellFolders, launch_a_browser, from_units, \
                         check_latest_version, Panic_Templ, Panic_Port, Panic_FWall, Panic, ExitSab, \
                         Notify, SplitHost, ConvertVersion
import sabnzbd.scheduler as scheduler
import sabnzbd.config as config
import sabnzbd.cfg
from threading import Thread

LOG_FLAG = False  # Global for this module, signalling loglevel change


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


def guard_loglevel():
    """ Callback function for guarding loglevel """
    global LOG_FLAG
    LOG_FLAG = True


#------------------------------------------------------------------------------
class FilterCP3(logging.Filter):
    ### Filter out all CherryPy3 logging that we receive,
    ### because we have the root logger
    def __init__(self):
        pass
    def filter(self, record):
        return record.module != '_cplogging'

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

    def count(self):
        return len(self.store)

    def last(self):
        if self.store:
            return self.store[len(self.store)-1]
        else:
            return ""

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
    else:
        print "  -d  --daemon             Use when run as a service"
    print
    print "      --force              Discard web-port timeout (see Wiki!)"
    print "  -h  --help               Print this message"
    print "  -v  --version            Print version information"
    print "  -c  --clean              Remove queue, cache and logs"
    print "  -p  --pause              Start in paused mode"
    print "      --https              Webserver uses HTTPS only"

def print_version():
    print """
%s-%s

Copyright (C) 2008-2009, The SABnzbd-Team <team@sabnzbd.org>
SABnzbd comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions. It is licensed under the
GNU GENERAL PUBLIC LICENSE Version 2 or (at your option) any later version.

""" % (sabnzbd.MY_NAME, sabnzbd.__version__)


def daemonize():
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        print "fork() failed"
        sys.exit(1)

    os.chdir(sabnzbd.DIR_PROG)
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
    logging.error("Failed to start web-interface")
    Panic_Port(browserhost, cherryport)
    sabnzbd.halt()
    ExitSab(2)

def Web_Template(key, defweb, wdir):
    """ Determine a correct web template set,
        return full template path
    """
    if wdir == None:
        try:
            wdir = key.get()
        except:
            wdir = ''
    if not wdir:
        wdir = defweb
    key.set(wdir)
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


def CheckColor(color, web_dir):
    """ Check existence of color-scheme """
    if color and os.path.exists(os.path.join(web_dir,'static/stylesheets/colorschemes/'+color+'.css')):
        return color
    else:
        return ''

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
            #signal.signal(5, signal.SIG_IGN)
            pass
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

    elif sabnzbd.DARWIN:
        sabnzbd.DIR_APPDATA = '%s/Library/Application Support/SABnzbd' % (os.environ['HOME'])
        sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
        sabnzbd.DIR_HOME = os.environ['HOME']
        ok = True

    else:
        # Unix/Linux
        sabnzbd.DIR_APPDATA = '%s/.%s' % (os.environ['HOME'], DEF_WORKDIR)
        sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
        sabnzbd.DIR_HOME = os.environ['HOME']
        ok = True

    if not ok:
        Panic("Cannot access the user profile.",
              "Please start with sabnzbd.ini file in another location")
        ExitSab(2)



def main():
    global LOG_FLAG

    AUTOBROWSER = None
    testlog = False # Allow log options for test-releases

    sabnzbd.MY_FULLNAME = os.path.normpath(os.path.abspath(sys.argv[0]))
    sabnzbd.MY_NAME = os.path.basename(sabnzbd.MY_FULLNAME)
    sabnzbd.DIR_PROG = os.path.dirname(sabnzbd.MY_FULLNAME)
    sabnzbd.DIR_INTERFACES = real_path(sabnzbd.DIR_PROG, DEF_INTERFACES)

    # Need console logging for SABnzbd.py and SABnzbd-console.exe
    consoleLogging = (not hasattr(sys, "frozen")) or (sabnzbd.MY_NAME.lower().find('-console') > 0)

    LOGLEVELS = (logging.WARNING, logging.INFO, logging.DEBUG)

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
        opts, args = getopt.getopt(sys.argv[1:], "phdvncw:l:s:f:t:b:2:",
                     ['pause', 'help', 'daemon', 'nobrowser', 'clean', 'logging=',
                      'weblogging=', 'server=', 'templates',
                      'template2', 'browser=', 'config-file=', 'delay=', 'force',
                      'version', 'https', 'testlog'])
    except getopt.GetoptError:
        print_help()
        ExitSab(2)

    fork = False
    pause = False
    f = None
    cherryhost = None
    cherryport = None
    cherrypylogging = None
    clean_up = False
    logging_level = None
    web_dir = None
    web_dir2 = None
    delay = 0.0
    vista = False
    vista64 = False
    force_web = False
    https = False

    for o, a in opts:
        if (o in ('-d', '--daemon')):
            if os.name != 'nt':
                fork = True
            AUTOBROWSER = False
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
            AUTOBROWSER = False
        if o in ('-b', '--browser'):
            try:
                AUTOBROWSER = bool(int(a))
            except:
                AUTOBROWSER = True
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
        if o in ('-v', '--version'):
            print_version()
            ExitSab(0)
        if o in ('-p', '--pause'):
            pause = True
        if o in ('--delay'):
            # For debugging of memory leak only!!
            try:
                delay = float(a)
            except:
                pass
        if o in ('--force'):
            force_web = True
        if o in ('--https'):
            https = True
        if o in ('--testlog'):
            testlog = True


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

    if not os.path.exists(f) and not os.path.exists(sabnzbd.DIR_LCLDATA):
        try:
            os.makedirs(sabnzbd.DIR_LCLDATA)
        except IOError:
            Panic('Cannot create folder "%s".' % sabnzbd.DIR_LCLDATA, 'Check specified INI file location.')
            ExitSab(1)

    sabnzbd.cfg.set_root_folders(sabnzbd.DIR_HOME, sabnzbd.DIR_LCLDATA, sabnzbd.DIR_PROG, sabnzbd.DIR_INTERFACES)

    if not config.read_config(f):
        Panic('"%s" is not a valid configuration file.' % f, \
              'Specify a correct file or delete this file.')
        ExitSab(1)


    if cherrypylogging == None:
        cherrypylogging = sabnzbd.cfg.LOG_WEB.get()
    else:
        sabnzbd.cfg.LOG_WEB.set(cherrypylogging)

    if logging_level == None:
        logging_level = sabnzbd.cfg.LOG_LEVEL.get()
    else:
        sabnzbd.cfg.LOG_LEVEL.set(logging_level)

    ver, testRelease = ConvertVersion(sabnzbd.__version__)
    if testRelease and not testlog:
        logging_level = 2
        cherrypylogging = True

    logdir = sabnzbd.cfg.LOG_DIR.get_path()
    if fork and not logdir:
        print "Error:"
        print "I refuse to fork without a log directory!"
        sys.exit(1)

    if clean_up:
        xlist= glob.glob(logdir + '/*')
        for x in xlist:
            if x.find(RSS_FILE_NAME) < 0:
                os.remove(x)

    try:
        sabnzbd.LOGFILE = os.path.join(logdir, DEF_LOG_FILE)
        logsize = sabnzbd.cfg.LOG_SIZE.get_int()
        rollover_log = logging.handlers.RotatingFileHandler(\
                       sabnzbd.LOGFILE, 'a+',
                       logsize,
                       sabnzbd.cfg.LOG_BACKUPS.get())

        format = '%(asctime)s::%(levelname)s::[%(module)s:%(lineno)d] %(message)s'
        rollover_log.setFormatter(logging.Formatter(format))
        rollover_log.addFilter(FilterCP3())
        sabnzbd.LOGHANDLER = rollover_log
        logger.addHandler(rollover_log)
        logger.setLevel(LOGLEVELS[logging_level])

    except IOError:
        print "Error:"
        print "Can't write to logfile"
        ExitSab(2)

    if fork:
        try:
            x= sys.stderr.fileno
            x= sys.stdout.fileno
            ol_path = os.path.join(logdir, DEF_LOG_ERRFILE)
            out_log = file(ol_path, 'a+', 0)
            sys.stderr.flush()
            sys.stdout.flush()
            os.dup2(out_log.fileno(), sys.stderr.fileno())
            os.dup2(out_log.fileno(), sys.stdout.fileno())
        except AttributeError:
            pass

    else:
        try:
            x= sys.stderr.fileno
            x= sys.stdout.fileno

            if consoleLogging:
                console = logging.StreamHandler()
                console.addFilter(FilterCP3())
                console.setLevel(LOGLEVELS[logging_level])
                console.setFormatter(logging.Formatter(format))
                logger.addHandler(console)
        except AttributeError:
            pass

    logging.info('--------------------------------')
    logging.info('%s-%s (rev=%s)', sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.__baseline__)
    if os.name == 'nt':
        suffix = ''
        if vista: suffix = ' (=Vista)'
        if vista64: suffix = ' (=Vista64)'
        logging.info('Platform=%s%s Class=%s', platform.platform(), suffix, os.name)
    else:
        logging.info('Platform = %s', os.name)
    logging.info('Python-version = %s', sys.version)

    if testRelease:
        logging.info('Test release, setting maximum logging levels')

    if AUTOBROWSER != None:
        sabnzbd.cfg.AUTOBROWSER.set(AUTOBROWSER)
    else:
        AUTOBROWSER = sabnzbd.cfg.AUTOBROWSER.get()

    sabnzbd.cfg.DEBUG_DELAY.set(delay)

    init_ok = sabnzbd.initialize(pause, clean_up, evalSched=True)

    if not init_ok:
        logging.error('Initializing %s-%s failed, aborting',
                      sabnzbd.MY_NAME, sabnzbd.__version__)
        ExitSab(2)

    find_programs(sabnzbd.DIR_PROG)

    if sabnzbd.decoder.HAVE_YENC:
        logging.info("_yenc module... found!")
    else:
        if hasattr(sys, "frozen"):
            logging.warning("_yenc module... NOT found!")
        else:
            logging.info("_yenc module... NOT found!")

    if sabnzbd.newsunpack.PAR2_COMMAND:
        logging.info("par2 binary... found (%s)", sabnzbd.newsunpack.PAR2_COMMAND)
    else:
        logging.error("par2 binary... NOT found!")

    if sabnzbd.newsunpack.PAR2C_COMMAND:
        logging.info("par2-classic binary... found (%s)", sabnzbd.newsunpack.PAR2C_COMMAND)

    if sabnzbd.newsunpack.RAR_COMMAND:
        logging.info("unrar binary... found (%s)", sabnzbd.newsunpack.RAR_COMMAND)
    else:
        logging.warning("unrar binary... NOT found")

    if sabnzbd.newsunpack.ZIP_COMMAND:
        logging.info("unzip binary... found (%s)", sabnzbd.newsunpack.ZIP_COMMAND)
    else:
        logging.warning("unzip binary... NOT found!")

    if os.name != 'nt':
        if sabnzbd.newsunpack.NICE_COMMAND:
            logging.info("nice binary... found (%s)", sabnzbd.newsunpack.NICE_COMMAND)
        else:
            logging.info("nice binary... NOT found!")
        if sabnzbd.newsunpack.IONICE_COMMAND:
            logging.info("ionice binary... found (%s)", sabnzbd.newsunpack.IONICE_COMMAND)
        else:
            logging.info("ionice binary... NOT found!")

    if sabnzbd.newswrapper.HAVE_SSL:
        logging.info("pyOpenSSL... found (%s)", sabnzbd.newswrapper.HAVE_SSL)
    else:
        logging.info("pyOpenSSL... NOT found - try apt-get install python-pyopenssl (SSL is optional)")

    if cherryhost == None:
        cherryhost = sabnzbd.cfg.CHERRYHOST.get()
    else:
        sabnzbd.cfg.CHERRYHOST.set(cherryhost)

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
        cherryhost = '0.0.0.0'
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

    if ipv6 and ipv4 and \
        (browserhost not in ('localhost', '127.0.0.1', '[::1]', '::1')):
        sabnzbd.AMBI_LOCALHOST = True
        logging.info("IPV6 has priority on this system, potential Firefox issue")

    if ipv6 and ipv4 and cherryhost == '' and os.name == 'nt':
        logging.warning("Please be aware the 0.0.0.0 hostname will need an IPv6 address for external access")

    if cherryport == None:
        cherryport= sabnzbd.cfg.CHERRYPORT.get_int()
    else:
        sabnzbd.cfg.CHERRYPORT.set(str(cherryport))

    os.chdir(sabnzbd.DIR_PROG)

    web_dir  = Web_Template(sabnzbd.cfg.WEB_DIR,  DEF_STDINTF,  web_dir)
    web_dir2 = Web_Template(sabnzbd.cfg.WEB_DIR2, '', web_dir2)

    sabnzbd.WEB_DIR  = web_dir
    sabnzbd.WEB_DIR2 = web_dir2

    sabnzbd.WEB_COLOR = CheckColor(sabnzbd.cfg.WEB_COLOR.get(),  web_dir)
    sabnzbd.cfg.WEB_COLOR.set(sabnzbd.WEB_COLOR)
    sabnzbd.WEB_COLOR2 = CheckColor(sabnzbd.cfg.WEB_COLOR2.get(),  web_dir2)
    sabnzbd.cfg.WEB_COLOR2.set(sabnzbd.WEB_COLOR2)

    if fork and os.name != 'nt':
        daemonize()

    # Save the INI file
    config.save_config(force=True)

    logging.info('Starting %s-%s', sabnzbd.MY_NAME, sabnzbd.__version__)
    try:
        sabnzbd.start()
    except:
        logging.exception("Failed to start %s-%s", sabnzbd.MY_NAME, sabnzbd.__version__)
        sabnzbd.halt()

    cherrylogtoscreen = False
    sabnzbd.WEBLOGFILE = None
    access_file = None

    if cherrypylogging:
        if logdir:
            sabnzbd.WEBLOGFILE = os.path.join(logdir, DEF_LOG_CHERRY)
            access_file = os.path.join(logdir, DEF_LOG_CHERRY_ACCESS)
        if not fork:
            try:
                x= sys.stderr.fileno
                x= sys.stdout.fileno
                cherrylogtoscreen = True
            except:
                cherrylogtoscreen = False

    cherrypy.config.update({'server.environment': 'production',
                            'server.socket_host': cherryhost,
                            'server.socket_port': cherryport,
                            'server.logToScreen': cherrylogtoscreen,
                            'log.error_file' : sabnzbd.WEBLOGFILE,
                            'log.access_file' : access_file,
                            'engine.autoreload_frequency' : 100,
                            'engine.autoreload_on' : False,
                            'tools.encode.on' : True,
                            'tools.gzip.on' : True,
                            'tools.sessions.on' : True,
                            'request.show_tracebacks': True,
                            'checker.check_localhost' : bool(consoleLogging),
                            'error_page.401': sabnzbd.misc.error_page_401
                           })

    ssl_ca = sabnzbd.cfg.SSL_CA.get_path()
    ssl_key = sabnzbd.cfg.SSL_KEY.get_path()
    if not (ssl_ca and os.path.exists(ssl_ca) and ssl_key and os.path.exists(ssl_key)):
        ssl_ca = None

    if https and not (ssl_ca and ssl_key):
        logging.warning('Disabled HTTPS because of missing CA and KEY files')
        https = False

    if https:
        cherrypy.config.update({'server.ssl_certificate' : ssl_ca,
                                 'server.ssl_private_key' : ssl_key})


    appconfig = {'/sabnzbd/api' : {'tools.basic_auth.on' : False},
                 '/sabnzbd/shutdown': {'streamResponse': True},
                 '/sabnzbd/static': {'tools.staticdir.on': True, 'tools.staticdir.dir': os.path.join(web_dir, 'static')}
                }

    if web_dir2:
        appconfig['/sabnzbd/m/api'] = {'tools.basic_auth.on' : False}
        appconfig['/sabnzbd/m/shutdown'] = {'streamResponse': True}
        appconfig['/sabnzbd/m/static'] = {'tools.staticdir.on': True, 'tools.staticdir.dir': os.path.join(web_dir2, 'static')}

    if sabnzbd.cfg.USERNAME.get() and sabnzbd.cfg.PASSWORD.get():
        appconfig['/sabnzbd'] = {'tools.basic_auth.on' : True, 'tools.basic_auth.realm' : 'SABnzbd',
                                'tools.basic_auth.users' : sabnzbd.interface.get_users, 'tools.basic_auth.encrypt' : sabnzbd.interface.encrypt_pwd}


    login_page = LoginPage(web_dir, '/sabnzbd/', web_dir2, '/sabnzbd/m/')
    cherrypy.tree.mount(login_page, '/', config=appconfig)

    logging.info('Starting web-interface on %s:%s', cherryhost, cherryport)

    sabnzbd.cfg.LOG_LEVEL.callback(guard_loglevel)

    try:
        # Use internal cherrypy check first to prevent ugly tracebacks
        cherrypy.process.servers.check_port(cherryhost, cherryport)
        cherrypy.engine.start()
    except IOError, error:
        if str(error) == 'Port not bound.':
            if not force_web:
                Panic_FWall(vista)
                sabnzbd.halt()
                ExitSab(2)
        else:
            Bail_Out(browserhost, cherryport)
    except:
        Bail_Out(browserhost, cherryport)

    # Wait for server to become ready
    cherrypy.engine.wait(cherrypy.process.wspbus.states.STARTED)

    if https:
        launch_a_browser("https://%s:%s/sabnzbd" % (browserhost, cherryport))
    else:
        launch_a_browser("http://%s:%s/sabnzbd" % (browserhost, cherryport))

    Notify("SAB_Launched", None)

    # Now's the time to check for a new version
    check_latest_version()

    # Have to keep this running, otherwise logging will terminate
    timer = 0
    while not sabnzbd.SABSTOP:
        ### 3 sec polling tasks
        # Check for auto-restart request
        if cherrypy.engine.execv:
            cherrypy.engine._do_execv()

        # Check for loglevel changes, ignore for non-final releases
        if LOG_FLAG and (testlog or not testRelease):
            LOG_FLAG = False
            level = LOGLEVELS[sabnzbd.cfg.LOG_LEVEL.get()]
            logger.setLevel(level)
            if consoleLogging:
                console.setLevel(level)

        ### 30 sec polling tasks
        if timer > 9:
            timer = 0
            # Keep Windows awake (if needed)
            sabnzbd.keep_awake()
            # Restart scheduler (if needed)
            scheduler.restart()
            # Save config (if needed)
            config.save_config()
        else:
            timer += 1

        time.sleep(3)

    config.save_config()

    Notify("SAB_Shutdown", None)
    logging.info('Leaving SABnzbd')
    sys.stderr.flush()
    sys.stdout.flush()
    os._exit(0)


#####################################################################
#
# Platform specific startup code
#

if not sabnzbd.DARWIN:

    # Windows & Unix/Linux

    if __name__ == '__main__':
        main()

else:

    # OSX

    if __name__ == '__main__':
        try:
            from email import header
            import cherrypy.filters.cachefilter
            import cherrypy.filters.logdebuginfofilter
            import cherrypy.filters.baseurlfilter
            import cherrypy.filters.virtualhostfilter
            import cherrypy.filters.decodingfilter
            import cherrypy.filters.sessionauthenticatefilter
            import cherrypy.filters.sessionfilter
            import cherrypy.filters.staticfilter
            import cherrypy.filters.nsgmlsfilter
            import cherrypy.filters.tidyfilter
            import cherrypy.filters.xmlrpcfilter
            import cherrypy.filters.responseheadersfilter
            import cherrypy.filters.encodingfilter
            import Cheetah.DummyTransaction
            import objc
            from Foundation import *
            from AppKit import *
            from PyObjCTools import NibClassBuilder, AppHelper

            NibClassBuilder.extractClasses("MainMenu")

            class SABnzbdDelegate(NibClassBuilder.AutoBaseClass):
                def applicationShouldTerminate_(self, sender):
                    logging.info('[osx] application terminating')
                    sabApp.stop()
                    return NSTerminateNow

            class startApp(Thread):
                def __init__(self):
                    logging.info('[osx] sabApp Starting - starting main thread')
                    Thread.__init__(self)
                def run(self):
                    main()
                    logging.info('[osx] sabApp Stopping - main thread quit ')
                    AppHelper.stopEventLoop()
                def stop(self):
                    logging.info('[osx] sabApp Quit - stopping main thread ')
                    cherrypy.server.stop()
                    sabnzbd.halt()
                    logging.info('[osx] sabApp Quit - main thread stopped')

            sabApp = startApp()
            sabApp.start()
            AppHelper.runEventLoop()
        except:
            main()
