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

import sys

import logging
import logging.handlers
import os
import cherrypy
import getopt
import sabnzbd
import signal
import re
import glob
import socket
import platform

from sabnzbd.utils.configobj import ConfigObj, ConfigObjError
from sabnzbd.__init__ import check_setting_str, check_setting_int, dir_setup
from sabnzbd.interface import *
from sabnzbd.constants import *
from sabnzbd.newsunpack import find_programs
from sabnzbd.misc import Get_User_ShellFolders, save_configfile, launch_a_browser, \
                         check_latest_version, Panic_Templ, Panic_Port, Panic_FWall, Panic, ExitSab

from threading import Thread

#------------------------------------------------------------------------------
signal.signal(signal.SIGINT, sabnzbd.sig_handler)
signal.signal(signal.SIGTERM, sabnzbd.sig_handler)

try:
    import win32api
    win32api.SetConsoleCtrlHandler(sabnzbd.sig_handler, True)
except ImportError:
    pass

#------------------------------------------------------------------------------
def hide_console(hide, path):
    if hasattr(sys, "frozen"):
        if hide:
            try:
                import linecache
                def fake_getline(filename, lineno, module_globals = None):
                    return ''
                linecache.getline = fake_getline

                del linecache, fake_getline

                import win32gui
                # Make sure we can find the window, give it a unique name
                win32api.SetConsoleTitle('___SABnzbd___')

                # Now hide it, based on the new name
                win32gui.ShowWindow(win32gui.FindWindow('ConsoleWindowClass','___SABnzbd___'), False)

            except ImportError:
                pass
        else:
            sabnzbd.WAITEXIT = True


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
    print "Usage: SABnzbd [-f <configfile>] <other options>"
    print
    print "Options marked [*] are stored in the config file"
    print
    print "Options:"
    print "  -f  --config-file <ini>  location of config file"
    print "  -s  --server <srv:port>  listen on server:port [*]"
    print "  -t  --templates <templ>  template directory [*]"
    print
    print "  -l  --logging <0..2>     set logging level (0= least, 2= most) [*]"
    print "  -w  --weblogging <0..1>  set cherrypy logging (0= off, 1= on) [*]"
    print
    print "  -b  --browser <0..1>     auto browser launch (0= off, 1= on) [*]"
    if os.name != 'nt':
        print "  -d  --daemon             fork daemon process"
        print "      --permissions        set the chmod mode (e.g. o=rwx,g=rwx) [*]"
    else:
        print "  -d  --daemon             Use when run as a service"
        print "      --console            Keep the console window open and wait on exit"
    print
    print "      --force              Discard web-port timeout (see Wiki!)"
    print "  -h  --help               print this message"
    print "  -v  --version            print version information"
    print "  -c  --clean              Remove queue, cache and logs"
    print "  -p  --pause              start in paused mode"

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
        ok = True
    elif os.name == 'nt':
        specials = Get_User_ShellFolders()
        try:
            sabnzbd.DIR_APPDATA = '%s\\%s' % (specials['AppData'], DEF_WORKDIR)
            sabnzbd.DIR_LCLDATA = '%s\\%s' % (specials['Local AppData'], DEF_WORKDIR)
            sabnzbd.DIR_HOME = specials['Personal']
            ok = True
        except:
            if vista:
                try:
                    root = os.environ['AppData']
                    user = os.environ['USERPROFILE']
                    sabnzbd.DIR_APPDATA = '%s\\%s' % (root.replace('\\Roaming', '\\Local'), DEF_WORKDIR)
                    sabnzbd.DIR_HOME    = '%s\\Documents' % user
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
    sabnzbd.MY_NAME = os.path.basename(sys.argv[0]).replace('.py','')
    sabnzbd.MY_FULLNAME = os.path.normpath(os.path.abspath(sys.argv[0]))

    print '\n%s-%s [%s]' % (sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_FULLNAME)

    LOGLEVELS = [ logging.WARNING, logging.INFO, logging.DEBUG ]

    try:
        opts, args = getopt.getopt(sys.argv[1:], "phdvncu:w:l:s:f:t:b:",
                     ['pause', 'help', 'daemon', 'nobrowser', 'clean', 'logging=', \
                      'weblogging=', 'umask=', 'server=', 'templates', 'permissions=', \
                      'browser=', 'config-file=', 'delay=', 'force', 'console'])
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
    delay = 0.0
    vista = False
    force_web = False
    hide = True

    sabnzbd.DIR_PROG = os.path.dirname(sabnzbd.MY_FULLNAME)

    for o, a in opts:
        if (o in ('-d', '--daemon')):
            if os.name == 'nt':
                hide = True
            else:
                fork = True
            sabnzbd.AUTOBROWSER = 0
            sabnzbd.DAEMON = True
        if o in ('-h', '--help'):
            print_help()
            ExitSab(0)
        if o in ('-f', '--config-file'):
            f = a
        if o in ('-t', '--templates'):
            web_dir = a
        if o in ('-s', '--server'):
            # Cannot use split, because IPV6 of "a:b:c:port" notation
            # Split on the last ':'
            mark = a.rfind(':')
            if mark < 0:
               cherryhost = a
            else:
               cherryhost = a[0 : mark]
               cherryport = a[mark+1 :]
            try:
                cherryport = int(cherryport)
            except:
                cherryport = None
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
        if o in ('--console'):
            hide = False

    hide_console(hide, sabnzbd.MY_FULLNAME)

    # Detect Vista or higher
    if platform.platform().find('Windows-32bit') >= 0 or \
       platform.platform().find('Windows-64bit') >= 0 :
        vista = True

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
    	    fp.write("__version__=%s\n[misc]\n[logging]\n[newzbin]\n[servers]\n" % sabnzbd.__configversion__)
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
        rollover_log = logging.handlers.RotatingFileHandler(\
                       sabnzbd.LOGFILE, 'a+',
                       check_setting_int(cfg, 'logging', 'max_log_size', 5242880),
                       check_setting_int(cfg, 'logging', 'log_backups', 5))

        rollover_log.setLevel(LOGLEVELS[logging_level])
        format = '%(asctime)s::%(levelname)s::%(message)s'
        rollover_log.setFormatter(logging.Formatter(format))
        sabnzbd.LOGHANDLER = rollover_log

        gui_log = guiHandler(MAX_WARNINGS)
        gui_log.setLevel(logging.WARNING)
        format_gui = '%(asctime)s\n%(levelname)s\n%(message)s'
        gui_log.setFormatter(logging.Formatter(format_gui))
        sabnzbd.GUIHANDLER = gui_log

        logger = logging.getLogger('')
        logger.setLevel(LOGLEVELS[logging_level])
        logger.addHandler(rollover_log)
        logger.addHandler(gui_log)


        logging.info("--------------------------------")

    except IOError:
        print "Error:"
        print "Can't write to logfile"
        ExitSab(2)

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

            console = logging.StreamHandler()
            console.setLevel(LOGLEVELS[logging_level])
            console.setFormatter(logging.Formatter(format))
            logger = logging.getLogger('')
            logger.setLevel(LOGLEVELS[logging_level])
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

    init_ok = sabnzbd.initialize(pause, clean_up)

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
        logging.info("par2 binary... NOT found!")

    if sabnzbd.newsunpack.RAR_COMMAND:
        logging.info("rar binary... found (%s)", sabnzbd.newsunpack.RAR_COMMAND)
    else:
        logging.info("rar binary... NOT found")

    if sabnzbd.newsunpack.ZIP_COMMAND:
        logging.info("unzip binary... found (%s)", sabnzbd.newsunpack.ZIP_COMMAND)
    else:
        logging.info("unzip binary... NOT found!")

    if os.name == 'nt':
        msg = "sendemail.exe"
    else:
        msg = "Perl interpreter"
    if sabnzbd.newsunpack.EMAIL_COMMAND:
        logging.info("%s... found (%s)", msg, sabnzbd.newsunpack.EMAIL_COMMAND)
    else:
        logging.warning("%s... NOT found, cannot EMail!", msg)

    if cherryhost == None:
        cherryhost = check_setting_str(cfg, 'misc','host', DEF_HOST)
    else:
        cfg['misc']['host'] = cherryhost

    if vista:
        logging.info("Windows Vista detected, will only use numerical IP")

    # Get IP address, but discard APIPA/IPV6
    # If only APIPA's or IPV6 are found, fall back to localhost
    hostip = 'localhost'
    info = socket.getaddrinfo(socket.gethostname(), None)
    for item in info:
        ip = item[4][0]
        if ip.find('169.254.') == 0:
            pass # Is an APIPA
        elif ip.find(':') >= 0:
            ipv6 = True
            sabnzbd.AMBI_LOCALHOST = True
            logging.warning("IPV6 has priority on this system, potential Firefox issue")
        elif ip.find('.') >= 0:
            hostip = ip
            break

    if cherryhost == '':
        if vista:
            # To protect Firefox users, use numeric IP
            cherryhost = hostip
            browserhost = hostip
        else:
            cherryhost = socket.gethostname()
            browserhost = cherryhost
    elif cherryhost == '0.0.0.0':
        # Just take the gamble for this
        cherryhost = ''
        browserhost = 'localhost'
    elif cherryhost.find('[') == 0:
        # IPV6
        browserhost = cherryhost
    elif cherryhost.replace('.', '').isdigit():
        # IPV4 numerical
        browserhost = cherryhost
    else:
        # If on Vista and/or APIPA, use numerical IP, to help FireFoxers
        if vista and not (cherryhost == 'localhost'):
            cherryhost = hostip
        browserhost = cherryhost

    if cherryport == None:
        if os.name == 'nt':
            defport = DEF_PORT_WIN
        else:
            defport = DEF_PORT_UNIX
        cherryport= check_setting_int(cfg, 'misc', 'port', defport)
    else:
        cfg['misc']['port'] = cherryport

    log_dir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, DEF_LOG_DIR)

    if not web_dir:
        try:
            web_dir = cfg['misc']['web_dir']
        except:
            web_dir = ''
    if not web_dir:
        web_dir = DEF_STDINTF
    cfg['misc']['web_dir'] = web_dir

    sabnzbd.DIR_INTERFACES = real_path(sabnzbd.DIR_PROG, DEF_INTERFACES)
    web_dir = real_path(sabnzbd.DIR_INTERFACES, web_dir)
    web_main = real_path(web_dir, DEF_MAIN_TMPL)
    logging.info("Web dir is %s", web_dir)

    sabnzbd.interface.USERNAME = check_setting_str(cfg, 'misc', 'username', '')

    sabnzbd.interface.PASSWORD = check_setting_str(cfg, 'misc', 'password', '', False)

    if not os.path.exists(web_main):
        logging.warning('Cannot find web template: %s, trying standard template', web_main)
        web_dir = real_path(sabnzbd.DIR_INTERFACES, DEF_STDINTF)
        web_main = real_path(web_dir, DEF_MAIN_TMPL)
        if not os.path.exists(web_main):
            logging.exception('Cannot find standard template: %s', web_main)
            Panic_Templ(web_main)
            ExitSab(1)

    web_dir = real_path(web_dir, "templates")

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

    cherrypy.root = BlahPage()
    cherrypy.root.sabnzbd = MainPage(web_dir)
    cherrypy.root.sabnzbd.queue = QueuePage(web_dir)
    cherrypy.root.sabnzbd.config = ConfigPage(web_dir)
    cherrypy.root.sabnzbd.config.general = ConfigGeneral(web_dir)
    cherrypy.root.sabnzbd.config.directories = ConfigDirectories(web_dir)
    cherrypy.root.sabnzbd.config.switches = ConfigSwitches(web_dir)
    cherrypy.root.sabnzbd.config.server = ConfigServer(web_dir)
    cherrypy.root.sabnzbd.config.scheduling = ConfigScheduling(web_dir)
    cherrypy.root.sabnzbd.config.rss = ConfigRss(web_dir)
    cherrypy.root.sabnzbd.config.email = ConfigEmail(web_dir)
    cherrypy.root.sabnzbd.config.newzbin = ConfigNewzbin(web_dir)
    cherrypy.root.sabnzbd.connections = ConnectionInfo(web_dir)
    cherrypy.root.sabnzbd.history = HistoryPage(web_dir)

    cherrypy.config.update(updateMap={'server.environment': 'production',
                                 'server.socketHost': cherryhost,
                                 'server.socketPort': cherryport,
                                 'server.logToScreen': cherrylogtoscreen,
                                 'server.logFile': sabnzbd.WEBLOGFILE,
                                 'sessionFilter.on': True,
                                 '/sabnzbd/shutdown': {'streamResponse': True},
                                 '/sabnzbd/default.css': {'staticFilter.on': True, 'staticFilter.file': os.path.join(web_dir, 'default.css')},
                                 '/sabnzbd/static': {'staticFilter.on': True, 'staticFilter.dir': os.path.join(web_dir, 'static')}
                           })
    logging.info('Starting web-interface on %s:%s', cherryhost, cherryport)
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

    # Now's the time to check for a new version
    if sabnzbd.VERSION_CHECK:
        check_latest_version()

    # Have to keep this running, otherwise logging will terminate
    while cherrypy.server.ready:
        time.sleep(3)

if __name__ == '__main__':
    main()
