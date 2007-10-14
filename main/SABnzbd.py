#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
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

from sabnzbd.utils.configobj import ConfigObj, ConfigObjError

from sabnzbd.interface import *

from sabnzbd.constants import *

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
    print "Usage: SABnzbd.py [-f <configfile>]"
    print
    print "Options:"
    print "  -f   location of config file"
    print "  -d   fork daemon process"
    print "  -p   start paused"
    print "  -v   print version information"
    print "  -h   print this message"
    
def print_version():
    print "SABnzbd-%s" % sabnzbd.__version__
    
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
    try:
        opts, args = getopt.getopt(sys.argv[1:], "phdvf:")
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
        
    fork = False
    pause = False
    f = None
    
    if os.name == 'nt':
        f = './SABnzbd.ini'
        
    for o, a in opts:
        if o == '-d' and os.name != 'nt':
            fork = True
        if o == '-h':
            print_help()
            sys.exit()
        if o == '-f':
            f = a
        if o == '-v':
            print_version()
            sys.exit()
        if o == '-p':
            pause = True
            
    if not f:
        print_help()
        sys.exit()
    else:
        f = os.path.abspath(f)
        if not os.path.exists(f):
            print "Error:"
            print "%s does not exist" % f
            sys.exit()
    try:
        cfg = ConfigObj(f)
        if int(cfg['__version__']) < sabnzbd.__configversion__:
            print "Error:"
            print "Configfile out of date, please update to latest version"
            sys.exit()
            
    except ConfigObjError, strerror:
        print "Error:"
        print "%s is not a valid configfile" % f
        sys.exit()
        
    if fork and not cfg['misc']['log_dir']:
        print "Error:"
        print "I refuse to fork without a log directory!"
        sys.exit()
        
    logdir = ""
    format = '%(asctime)s::%(levelname)s::%(message)s'
    
    if cfg['misc']['log_dir']:
        logdir = os.path.abspath(cfg['misc']['log_dir'])
        try:
            rollover_log = logging.handlers.RotatingFileHandler(\
                        os.path.join(logdir, 'SABnzbd.log'), 'a+', 
                        int(cfg['logging']['max_log_size']), 
                        int(cfg['logging']['log_backups']))
                        
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
            ol_path = os.path.join(cfg['misc']['log_dir'], 
                                   'SABnzbd.error.log')
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
                
    logging.info('SABnzbd v%s', sabnzbd.__version__)
    
    sabnzbd.CFG = cfg
    
    init_ok = sabnzbd.initialize(pause)
    
    if not init_ok:
        logging.error('Initializing SABnzbd v%s failed, aborting', 
                      sabnzbd.__version__)
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
        
        
    cherryhost = cfg['misc']['host']
    cherryport = int(cfg['misc']['port'])
    cherrypylogging = bool(int(cfg['logging']['enable_cherrypy_logging']))
    
    log_dir = os.path.abspath(cfg['misc']['log_dir'])
    web_dir = os.path.abspath(cfg['misc']['web_dir'])
    
    sabnzbd.interface.USERNAME = cfg['misc']['username']
    sabnzbd.interface.PASSWORD = cfg['misc']['password']
    
    if not os.path.exists(web_dir):
        logging.error('Web directory: %s does not exist', web_dir)
        sys.exit(1)
    if not os.access(web_dir, os.R_OK):
        logging.error('Web directory: %s error accessing', web_dir)
        sys.exit(1)
        
    if fork and os.name != 'nt':
        daemonize()
        
    logging.info('Starting SABnzbd v%s', sabnzbd.__version__)
    try:
        sabnzbd.start()
    except:
        logging.exception("Failed to start SABnzbd v%s", sabnzbd.__version__)
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
    logging.info('Starting web-interface')
    try:
        cherrypy.server.start()
    except:
        logging.exception("Failed to start web-interface")
        sabnzbd.halt()
        
if __name__ == '__main__':
    main()
