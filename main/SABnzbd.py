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
from sabnzbd.__init__ import check_setting_str, check_setting_int, dir_setup, real_path
from sabnzbd.interface import *
from sabnzbd.constants import *
from sabnzbd.misc import Get_User_ShellFolders

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
    print "Options:"
    print "  -f  --config-file= location of config file"
    if os.name != 'nt':
        print "  -d  --daemon       fork daemon process"
    print "  -p  --pause        start in paused mode"
    print "  -s  --server=      listen on server:port"
    print "  -n  --nobrowser    do not start a browser"
    print "  -c  --clean        clean the cache and logs"
    print "  -v  --version      print version information"
    print "  -h  --help         print this message"
    
def print_version():
    print "%s-%s" % (MY_NAME, sabnzbd.__version__)


def launch_a_browser(host, port):
    url= "http://%s:%s/sabnzbd" % (host, port)
    if os.name == 'nt':
        win32api.ShellExecute(0, "open", url, None, "", 5)
    else:
        os.system("%s %s &" %(sabnzbd.newsunpack.BROWSER_COMMAND, url))

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
    os.umask(0)
    
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
    print

    try:
        opts, args = getopt.getopt(sys.argv[1:], "phdvncs:f:",
                     ['pause', 'help', 'daemon', 'nobrowser', 'clean', 'server=', 'config-file='])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    fork = False
    pause = False
    f = None
    cherryhost = ''
    cherryport = 0
    nobrowser = False
    clean_up = False

    if os.name == 'nt':
        specials = Get_User_ShellFolders()
        sabnzbd.DIR_APPDATA = '%s\\sabnzbd' % specials['AppData']
        sabnzbd.DIR_LCLDATA = '%s\\sabnzbd' % specials['Local AppData']
        sabnzbd.DIR_HOME = specials['Personal']
    else:
    	  sabnzbd.DIR_APPDATA = '%s/.sabnzbd' % os.environ['HOME']
    	  sabnzbd.DIR_LCLDATA = sabnzbd.DIR_APPDATA
    	  sabnzbd.DIR_HOME = os.environ['HOME']

    sabnzbd.DIR_PROG= os.path.normpath(os.path.abspath('.'))

    f = sabnzbd.DIR_APPDATA + '/sabnzbd.ini'

    for o, a in opts:
        if (o in ('-d', '--daemon')) and os.name != 'nt':
            fork = True
        if o in ('-h', '--help'):
            print_help()
            sys.exit()
        if o in ('-f', '--config-file'):
            f = a
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
        if o in ('-v', '--version'):
            print_version()
            sys.exit()
        if o in ('-p', '--pause'):
            pause = True
            
    if not f:
        print_help()
        sys.exit()
    else:
        f = os.path.abspath(f)
        if not os.path.exists(f):
        	  try:
        	      if not os.path.exists(sabnzbd.DIR_APPDATA):
        	          os.makedirs(sabnzbd.DIR_APPDATA)
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
        if int(my_version) < sabnzbd.__configversion__:
            print "Error:"
            print "Configfile out of date, please update to latest version"
            sys.exit()

    except ConfigObjError, strerror:
        print "Error:"
        print "%s is not a valid configfile" % f
        sys.exit()
        
    my_logdir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, 'logs')
    if fork and not my_logdir:
        print "Error:"
        print "I refuse to fork without a log directory!"
        sys.exit()
        
    logdir = ""
    format = '%(asctime)s::%(levelname)s::%(message)s'
    
    
    logdir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, 'logs')
    if clean_up:
        xlist= glob.glob(logdir + '/*')
        for x in xlist:
            os.remove(x)

    try:
        rollover_log = logging.handlers.RotatingFileHandler(\
                       os.path.join(logdir, 'sabnzbd.log'), 'a+', 
                       check_setting_int(cfg, 'logging', 'max_log_size', 5242880), 
                       check_setting_int(cfg, 'logging', 'log_backups', 5))
                  
        rollover_log.setLevel(logging.DEBUG)
        rollover_log.setFormatter(logging.Formatter(format))
        logger = logging.getLogger('')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(rollover_log)
        logging.info("--------------------------------")
            
    except IOError:
        print "Error:"
        print "Can't write to logfile"
        sys.exit()
            
    if fork:
        try:
            sys.stderr.fileno
            sys.stdout.fileno
            my_logpath = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, 'logs')
            ol_path = os.path.join(my_logpath, 
                                   'sabnzbd.error.log')
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
            console.setLevel(logging.DEBUG)
            console.setFormatter(logging.Formatter(format))
            logger = logging.getLogger('')
            logger.setLevel(logging.DEBUG)
            logger.addHandler(console)
        except AttributeError:
            pass
                
    logging.info('%s-%s', MY_NAME, sabnzbd.__version__)
    
    sabnzbd.CFG = cfg
    
    init_ok = sabnzbd.initialize(pause, clean_up)
    
    if not init_ok:
        logging.error('Initializing %s-%s failed, aborting', 
                      MY_NAME, sabnzbd.__version__)
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

    if os.name != 'nt':
        if sabnzbd.newsunpack.BROWSER_COMMAND:
            logging.info("Browser binary: %s found!", sabnzbd.newsunpack.BROWSER_COMMAND)
        else:
            logging.info("Browser binary... NOT found!")
        
    if cherryhost == '':
        cherryhost = check_setting_str(cfg, 'misc','host', '')
    else:
        check_setting_str(cfg, 'misc','host', cherryhost)
        
    if cherryhost == '':
    	  cherryhost = 'localhost'

    if cherryport == 0:
        cherryport= check_setting_int(cfg, 'misc', 'port', 8080)
    else:
        check_setting_int(cfg, 'misc', 'port', cherryport)
        
    cherrypylogging = bool(check_setting_int(cfg, 'logging', 'enable_cherrypy_logging', 1))
    
    log_dir = dir_setup(cfg, 'log_dir', sabnzbd.DIR_LCLDATA, 'logs')

    try:
        web_dir = cfg['misc']['web_dir']
    except:
        web_dir = ''
    if not web_dir:
        web_dir = 'templates'
    cfg['misc']['web_dir'] = web_dir

    web_dir = real_path(sabnzbd.DIR_PROG, web_dir)
    logging.info("Web dir is %s", web_dir)
    
    sabnzbd.interface.USERNAME = check_setting_str(cfg, 'misc', 'username', '')
        
    sabnzbd.interface.PASSWORD = check_setting_str(cfg, 'misc', 'password', '')

    if not os.path.exists(web_dir + "/main.tmpl"):
        logging.error('Cannot find web template: %s/%s', web_dir, "main.tmpl")
        sys.exit(1)
    if not os.access(web_dir, os.R_OK):
        logging.error('Web directory: %s error accessing', web_dir)
        sys.exit(1)
        
    if fork and os.name != 'nt':
        daemonize()
        
    logging.info('Starting %s-%s', MY_NAME, sabnzbd.__version__)
    try:
        sabnzbd.start()
    except:
        logging.exception("Failed to start %s-%s", MY_NAME, sabnzbd.__version__)
        sabnzbd.halt()
    
    cherrylogtoscreen = False
    cherrylogfile = None
    
    if cherrypylogging:
        if log_dir: 
            cherrylogfile = os.path.join(log_dir, "cherrypy.log");
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
                                 'server.logFile': cherrylogfile,
                                 'sessionFilter.on': True,
                                 '/sabnzbd/shutdown': {'streamResponse': True},
                                 '/sabnzbd/default.css': {'staticFilter.on': True, 'staticFilter.file': os.path.join(web_dir, 'default.css')},
                                 '/sabnzbd/static': {'staticFilter.on': True, 'staticFilter.dir': os.path.join(web_dir, 'static')}
                           })
    logging.info('Starting web-interface on %s:%s', cherryhost, cherryport)
    try:
        cherrypy.server.start(init_only=True)
        cherrypy.server.wait()
        if not nobrowser:
            launch_a_browser(cherryhost, cherryport)
            
        # Have to keep this running, otherwise logging will terminate
        while cherrypy.server.ready:
            time.sleep(3)
    except:
        logging.exception("Failed to start web-interface")
        sabnzbd.halt()
        
if __name__ == '__main__':
    main()
