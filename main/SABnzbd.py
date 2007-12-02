#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#                The ShyPike <shypike@users.sourceforge.net>
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

if hasattr(sys, "frozen"):
    try:
        import linecache
        def fake_getline(filename, lineno, module_globals = None):
            return ''
        linecache.getline = fake_getline
        
        del linecache, fake_getline
        
        import win32gui
        win32gui.ShowWindow(win32gui.GetForegroundWindow(), False)
    except ImportError:
        pass
        
import logging
import logging.handlers
import os
import cherrypy
import getopt
import sabnzbd
import signal
import re
import glob

from sabnzbd.utils.configobj import ConfigObj, ConfigObjError
from sabnzbd.__init__ import check_setting_str, check_setting_int, dir_setup
from sabnzbd.interface import *
from sabnzbd.constants import *
from sabnzbd.misc import Get_User_ShellFolders, save_configfile, launch_a_browser

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
            
def print_help():
    print "Usage: %s [-f <configfile>]" % __file__
    print
    print "Options marked [*] are stored in the config file"
    print
    print "Options:"
    print "  -f  --config-file <ini>  location of config file"
    print "  -h  --help               print this message"
    print "  -v  --version            print version information"
    print "  -s  --server <srv:port>  listen on server:port [*]"
    print "  -t  --templates <templ>  template directory [*]"
    print "  -l  --logging <0..2>     set logging level (0= least, 2= most) [*]"
    print "  -w  --weblogging <0..1>  set cherrypy logging (0= off, 1= on) [*]"
    if os.name != 'nt':
        print "      --permissions        set the chmod mode (e.g. o=rwx,g=rwx) [*]"
        print "  -d  --daemon             fork daemon process"
    print "  -c  --clean              clean queue, cache and logs"
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
    
def main():
    sabnzbd.MY_NAME = os.path.basename(sys.argv[0]).replace('.py','')
    sabnzbd.MY_FULLNAME = os.path.normpath(os.path.abspath(sys.argv[0]))
    
    print '\n%s-%s' % (sabnzbd.MY_FULLNAME, sabnzbd.__version__)

    LOGLEVELS = [ logging.WARNING, logging.INFO, logging.DEBUG ]

    try:
        opts, args = getopt.getopt(sys.argv[1:], "phdvncu:w:l:s:f:t:",
                     ['pause', 'help', 'daemon', 'nobrowser', 'clean', 'logging=', \
                      'weblogging=', 'umask=', 'server=', 'templates', 'permissions=', \
                      'config-file=', 'delay='])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    fork = False
    pause = False
    f = None
    cherryhost = ''
    cherryport = 0
    cherrypylogging = None
    nobrowser = False
    clean_up = False
    logging_level = None
    umask = None
    web_dir = None
    delay = 0.0

    if os.name == 'nt':
        specials = Get_User_ShellFolders()
        sabnzbd.DIR_APPDATA = '%s\\%s' % (specials['AppData'], DEF_WORKDIR)
        sabnzbd.DIR_LCLDATA = '%s\\%s' % (specials['Local AppData'], DEF_WORKDIR)
        sabnzbd.DIR_HOME = specials['Personal']
    else:
    	  sabnzbd.DIR_APPDATA = '%s/.%s' % (os.environ['HOME'], DEF_WORKDIR)
    	  sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
    	  sabnzbd.DIR_HOME = os.environ['HOME']

    sabnzbd.DIR_PROG= os.path.normpath(os.path.abspath('.'))

    f = sabnzbd.DIR_LCLDATA + '/' + DEF_INI_FILE

    for o, a in opts:
        if (o in ('-d', '--daemon')) and os.name != 'nt':
            fork = True
            nobrowser = True
        if o in ('-h', '--help'):
            print_help()
            sys.exit()
        if o in ('-f', '--config-file'):
            f = a
        if o in ('-t', '--templates'):
            web_dir = a
        if o in ('-s', '--server'):
            try:
                (cherryhost, cherryport) = a.split(":", 1)
            except:
                cherryhost= ""
            try:
                cherryport = int(cherryport)
            except:
                cherryport = 0
        if o in ('-n', '--nobrowser'):
            nobrowser= True
        if o in ('-c', '--clean'):
            clean_up= True
        if o in ('-w', '--weblogging'):
            try:
                cherrypylogging = int(a)
            except:
                cherrypylogging = -1
            if cherrypylogging < 0 or cherrypylogging > 1:
                print_help()
                sys.exit()
        if o in ('-l', '--logging'):
            try:
                logging_level = int(a)
            except:
                logging_level = -1
            if logging_level < 0 or logging_level > 2:
                print_help()
                sys.exit()
        if o in ('--permissions'):
            umask = a
        if o in ('-v', '--version'):
            print_version()
            sys.exit()
        if o in ('-p', '--pause'):
            pause = True
        if o in ('--delay'):
            # For debugging of memory leak only!!
            try:
                delay = float(a)
            except:
                pass
            
    if not f:
        print_help()
        sys.exit()
    else:
        f = os.path.abspath(f)
        if not os.path.exists(f):
        	  try:
        	      if not os.path.exists(sabnzbd.DIR_LCLDATA):
        	          os.makedirs(sabnzbd.DIR_LCLDATA)
        	      fp = open(f, "w")
        	      fp.write("__version__=%s\n[misc]\n[logging]\n[newzbin]\n[servers]\n" % sabnzbd.__configversion__)
        	      fp.close()
        	  except:
        	      print "Error:"
        	      print "Cannot create file %s" % f
        	      sys.exit()

    try:
        cfg = ConfigObj(f)
        try:
            my_version = cfg['__version__']
        except:
            my_version = sabnzbd.__configversion__
            cfg['__version__'] = my_version

    except ConfigObjError, strerror:
        print "Error:"
        print "%s is not a valid configfile" % f
        sys.exit()

    if cherrypylogging == None:
        cherrypylogging = bool(check_setting_int(cfg, 'logging', 'enable_cherrypy_logging', 0))
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
    format = '%(asctime)s::%(levelname)s::%(message)s'
    
    
    logdir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, DEF_LOG_DIR)
    if clean_up:
        xlist= glob.glob(logdir + '/*')
        for x in xlist:
            os.remove(x)

    try:
        sabnzbd.LOGFILE = os.path.join(logdir, DEF_LOG_FILE)
        rollover_log = logging.handlers.RotatingFileHandler(\
                       sabnzbd.LOGFILE, 'a+', 
                       check_setting_int(cfg, 'logging', 'max_log_size', 5242880), 
                       check_setting_int(cfg, 'logging', 'log_backups', 5))
                  
        rollover_log.setLevel(LOGLEVELS[logging_level])
        rollover_log.setFormatter(logging.Formatter(format))
        logger = logging.getLogger('')
        logger.setLevel(LOGLEVELS[logging_level])
        logger.addHandler(rollover_log)
        sabnzbd.LOGHANDLER = rollover_log
        logging.info("--------------------------------")
            
    except IOError:
        print "Error:"
        print "Can't write to logfile"
        sys.exit()
            
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
    
    if umask == None:
        umask = check_setting_str(cfg, 'misc', 'permissions', '')
    if umask:
        cfg['misc']['permissions'] = umask

    sabnzbd.DEBUG_DELAY = delay
    sabnzbd.NO_BROWSER = nobrowser
    sabnzbd.CFG = cfg
    
    init_ok = sabnzbd.initialize(pause, clean_up)
    
    if not init_ok:
        logging.error('Initializing %s-%s failed, aborting', 
                      sabnzbd.MY_NAME, sabnzbd.__version__)
        sys.exit(2)

    if sabnzbd.decoder.HAVE_YENC:
        logging.info("_yenc module... found!")
    else:
        logging.info("_yenc module... NOT found!")
        
    if sabnzbd.nzbstuff.HAVE_CELEMENTTREE:
        logging.info("celementtree module... found!")
    else:
        logging.info("celementtree module... NOT found!")
        
    if sabnzbd.newsunpack.PAR2_COMMAND:
        logging.info("par2 binary... found!")
    else:
        logging.info("par2 binary... NOT found!")
        
    if sabnzbd.newsunpack.RAR_COMMAND:
        logging.info("rar binary... found!")
    else:
        logging.info("rar binary... NOT found")
        
    if sabnzbd.newsunpack.ZIP_COMMAND:
        logging.info("unzip binary... found!")
    else:
        logging.info("unzip binary... NOT found!")

    if sabnzbd.newsunpack.EMAIL_COMMAND:
        logging.info("sendemail binary... found!")
    else:
        logging.info("sendemail binary... NOT found!")

    if cherryhost == '':
        cherryhost = check_setting_str(cfg, 'misc','host', DEF_HOST)
    else:
        check_setting_str(cfg, 'misc','host', cherryhost)
        
    if cherryhost == '':
    	  cherryhost = DEF_HOST
    cfg['misc']['host'] = cherryhost

    if cherryport == 0:
        cherryport= check_setting_int(cfg, 'misc', 'port', DEF_PORT)
    else:
        check_setting_int(cfg, 'misc', 'port', cherryport)

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
        web_dir = real_path(sabnzbd.DEF_INTERFACES, DEF_STDINTF)
        web_main = real_path(web_dir, DEF_MAIN_TMPL)
        if not os.path.exists(web_main):
            logging.exception('Cannot find standard template: %s', web_main)
            launch_a_browser(cherryhost, cherryport, PANIC_TEMPL)
            sys.exit(1)

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
        launch_a_browser(cherryhost, cherryport)
            
        # Have to keep this running, otherwise logging will terminate
        while cherrypy.server.ready:
            time.sleep(3)
    except:
        logging.exception("Failed to start web-interface")
        launch_a_browser(cherryhost, cherryport, PANIC_PORT)
        sabnzbd.halt()
        
if __name__ == '__main__':
    main()
