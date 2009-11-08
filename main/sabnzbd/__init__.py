#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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

from sabnzbd.version import __version__, __baseline__
__configversion__ = 18
__queueversion__ = 8

import os
import logging
import datetime
import tempfile
import cPickle
import zipfile
import glob
import gzip
import subprocess
import time
import cherrypy
from threading import RLock, Lock, Condition, Thread
from sabnzbd.lang import T, Ta

#------------------------------------------------------------------------
# Determine platform flags

WIN32 = DARWIN = DARWIN_INTEL = POSIX = FOUNDATION = WIN64 = False
KERNEL32 = None

if os.name == 'nt':
    WIN32 = True
    try:
        import ctypes
        KERNEL32 = ctypes.windll.LoadLibrary("Kernel32.dll")
    except:
        pass
elif os.name == 'posix':
    POSIX = True
    import platform
    if platform.system().lower() == 'darwin':
        DARWIN = True
        try:
            import Foundation
            FOUNDATION = True
        except:
            pass
        if platform.machine() == 'i386':
            DARWIN_INTEL = True

#------------------------------------------------------------------------

import sabnzbd.nzbqueue as nzbqueue
import sabnzbd.postproc as postproc
import sabnzbd.downloader as downloader
import sabnzbd.assembler as assembler
import sabnzbd.newzbin as newzbin
import sabnzbd.misc as misc
import sabnzbd.dirscanner as dirscanner
import sabnzbd.urlgrabber as urlgrabber
import sabnzbd.scheduler as scheduler
import sabnzbd.rss as rss
import sabnzbd.email as email
import sabnzbd.articlecache as articlecache
import sabnzbd.newsunpack
import sabnzbd.codecs as codecs
import sabnzbd.config as config
import sabnzbd.bpsmeter
import sabnzbd.cfg as cfg
import sabnzbd.database
import sabnzbd.lang as lang
from sabnzbd.decorators import *
from sabnzbd.constants import *

LINUX_POWER = misc.HAVE_DBUS

START = datetime.datetime.now()

MY_NAME = None
MY_FULLNAME = None
NEW_VERSION = None
DIR_HOME = None
DIR_APPDATA = None
DIR_LCLDATA = None
DIR_PROG = None
DIR_INTERFACES = None
DIR_LANGUAGE = None

QUEUECOMPLETE = None #stores the nice name of the action
QUEUECOMPLETEACTION = None #stores the name of the function to be called
QUEUECOMPLETEARG = None #stores an extra arguments that need to be passed
QUEUECOMPLETEACTION_GO = False # Booleen value whether to run an action or not at the queue end.

DEBUG_DELAY = 0
DAEMON = None

LOGFILE = None
WEBLOGFILE = None
LOGHANDLER = None
GUIHANDLER = None
AMBI_LOCALHOST = False

WEB_DIR = None
WEB_DIR2 = None
WIZARD_DIR = None
WEB_COLOR = None
WEB_COLOR2 = None
SABSTOP = False
RESTART_REQ = False
OSX_ICON = 1
PAUSED_ALL = False

__INITIALIZED__ = False
__SHUTTING_DOWN__ = False


################################################################################
# Signal Handler                                                               #
################################################################################
def sig_handler(signum = None, frame = None):
    global SABSTOP
    if sabnzbd.WIN32 and type(signum) != type(None) and DAEMON and signum==5:
        # Ignore the "logoff" event when running as a Win32 daemon
        return True
    if type(signum) != type(None):
        logging.warning(Ta('warn-signal@1'), signum)
    try:
        save_state()
    finally:
        SABSTOP = True
        os._exit(0)


################################################################################
# Initializing                                                                 #
################################################################################

INIT_LOCK = Lock()

def connect_db(thread_index):
    # Create a connection and store it in the current thread
    cherrypy.thread_data.history_db = sabnzbd.database.get_history_handle()


@synchronized(INIT_LOCK)
def initialize(pause_downloader = False, clean_up = False, force_save= False, evalSched=False):
    global __INITIALIZED__, \
           LOGFILE, WEBLOGFILE, LOGHANDLER, GUIHANDLER, AMBI_LOCALHOST, WAITEXIT, \
           DEBUG_DELAY, \
           DAEMON, MY_NAME, MY_FULLNAME, NEW_VERSION, \
           DIR_HOME, DIR_APPDATA, DIR_LCLDATA, DIR_PROG , DIR_INTERFACES, \
           DARWIN, RESTART_REQ, OSX_ICON

    if __INITIALIZED__:
        return False

    __SHUTTING_DOWN__ = False

    ### Set global database connection for Web-UI threads
    cherrypy.engine.subscribe('start_thread', connect_db)

    ### Clean the cache folder, if requested
    if clean_up:
        xlist= glob.glob(cfg.CACHE_DIR.get_path() + '/*')
        for x in xlist:
            os.remove(x)

    ### If dirscan_dir cannot be created, set a proper value anyway.
    ### Maybe it's a network path that's temporarily missing.
    path = cfg.DIRSCAN_DIR.get_path()
    if not os.path.exists(path):
        sabnzbd.misc.create_real_path(cfg.DIRSCAN_DIR.ident(), '', path, False)

    ### Set call backs for Config items
    cfg.CACHE_LIMIT.callback(new_limit)
    cfg.CHERRYHOST.callback(guard_restart)
    cfg.CHERRYPORT.callback(guard_restart)
    cfg.WEB_DIR.callback(guard_restart)
    cfg.WEB_DIR2.callback(guard_restart)
    cfg.WEB_COLOR.callback(guard_restart)
    cfg.WEB_COLOR2.callback(guard_restart)
    cfg.LOG_DIR.callback(guard_restart)
    cfg.CACHE_DIR.callback(guard_restart)
    cfg.HTTPS_PORT.callback(guard_restart)
    cfg.HTTPS_CERT.callback(guard_restart)
    cfg.HTTPS_KEY.callback(guard_restart)
    cfg.ENABLE_HTTPS.callback(guard_restart)
    cfg.BANDWIDTH_LIMIT.callback(guard_speedlimit)
    cfg.TOP_ONLY.callback(guard_top_only)

    ### Set cache limit
    articlecache.method.new_limit(cfg.CACHE_LIMIT.get_int(), cfg.DEBUG_DELAY.get())

    ### Set language files
    lang.install_language(DIR_LANGUAGE, cfg.LANGUAGE.get())

    ###
    ### Initialize threads
    ###

    newzbin.bookmarks_init()
    rss.init()
    scheduler.init()

    bytes = load_data(BYTES_FILE_NAME, remove = False, do_pickle = False)
    try:
        bytes = int(bytes)
        sabnzbd.bpsmeter.method.bytes_sum = bytes
    except:
        sabnzbd.bpsmeter.method.reset()

    nzbqueue.init()

    postproc.init()

    assembler.init()

    downloader.init(pause_downloader)

    dirscanner.init()

    newzbin.init_grabber()

    urlgrabber.init()

    if evalSched:
        scheduler.analyse(pause_downloader)

    logging.info('All processes started')
    RESTART_REQ = False
    __INITIALIZED__ = True
    return True


@synchronized(INIT_LOCK)
def start():
    global __INITIALIZED__

    if __INITIALIZED__:
        logging.debug('Starting postprocessor')
        postproc.start()

        logging.debug('Starting assembler')
        assembler.start()

        logging.debug('Starting downloader')
        downloader.start()

        scheduler.start()

        logging.debug('Starting dirscanner')
        dirscanner.start()

        newzbin.start_grabber()

        logging.debug('Starting urlgrabber')
        urlgrabber.start()


@synchronized(INIT_LOCK)
def halt():
    global __INITIALIZED__

    if __INITIALIZED__:
        logging.info('SABnzbd shutting down...')
        __SHUTTING_DOWN__ = True

        rss.stop()

        newzbin.bookmarks_save()

        logging.debug('Stopping URLGrabber')
        urlgrabber.stop()

        logging.debug('Stopping Newzbin-Grabber')
        newzbin.stop_grabber()

        logging.debug('Stopping dirscanner')
        dirscanner.stop()

        ## Stop Required Objects ##
        logging.debug('Stopping downloader')
        downloader.stop()

        logging.debug('Stopping assembler')
        assembler.stop()

        logging.debug('Stopping postprocessor')
        postproc.stop()

        ## Save State ##
        save_state()

        # The Scheduler cannot be stopped when the stop was scheduled.
        # Since all warm-restarts have been removed, it's not longer
        # needed to stop the scheduler.
        # We must tell the scheduler to deactivate.
        scheduler.abort()

        logging.info('All processes stopped')

        __INITIALIZED__ = False



################################################################################
## Misc Wrappers                                                              ##
################################################################################

def new_limit():
    """ Callback for article cache changes """
    articlecache.method.new_limit(cfg.CACHE_LIMIT.get_int())

def guard_restart():
    """ Callback for config options requiring a restart """
    global RESTART_REQ
    sabnzbd.RESTART_REQ = True

def guard_speedlimit():
    """ Callback for change of bandwidth_limit, sets actual speed """
    downloader.limit_speed(cfg.BANDWIDTH_LIMIT.get_int())

def guard_top_only():
    """ Callback for change of top_only option """
    nzbqueue.set_top_only(cfg.TOP_ONLY.get())


def add_msgid(msgid, pp=None, script=None, cat=None, priority=None, nzbname=None):

    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None
    if priority == None: priority = NORMAL_PRIORITY


    if cfg.USERNAME_NEWZBIN.get() and cfg.PASSWORD_NEWZBIN.get():
        logging.info('Fetching msgid %s from www.newzbin.com', msgid)
        msg = T('fetchingNewzbin@1') % msgid

        future_nzo = nzbqueue.generate_future(msg, pp, script, cat=cat, url=msgid, priority=priority, nzbname=nzbname)

        newzbin.grab(msgid, future_nzo)
    else:
        logging.error(Ta('error-fetchNewzbin@1'), msgid)


def add_url(url, pp=None, script=None, cat=None, priority=None, nzbname=None):
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None
    if 'nzbindex.nl/' in url:
        nzbname = ''
    logging.info('Fetching %s', url)
    msg = T('fetchNZB@1') % url
    future_nzo = nzbqueue.generate_future(msg, pp, script, cat, url=url, priority=priority, nzbname=nzbname)
    urlgrabber.add(url, future_nzo)


def save_state():
    articlecache.method.flush_articles()
    nzbqueue.save()
    save_data(str(sabnzbd.bpsmeter.method.get_sum()), BYTES_FILE_NAME, do_pickle = False)
    rss.save()
    newzbin.bookmarks_save()
    dirscanner.save()
    postproc.save()

def pause_all():
    global PAUSED_ALL
    PAUSED_ALL = True
    logging.debug('PAUSED_ALL active')

def unpause_all():
    global PAUSED_ALL
    PAUSED_ALL = False
    sabnzbd.downloader.resume_downloader()
    logging.debug('PAUSED_ALL inactive')


################################################################################
## NZB_LOCK Methods                                                           ##
################################################################################
NZB_LOCK = Lock()

@synchronized(NZB_LOCK)
def backup_exists(filename):
    """ Return True if backup exists and no_dupes is set
    """
    path = cfg.NZB_BACKUP_DIR.get_path()
    return path and sabnzbd.cfg.NO_DUPES.get() and \
           os.path.exists(os.path.join(path, filename+'.gz'))

@synchronized(NZB_LOCK)
def backup_nzb(filename, data):
    """ Backup NZB file
    """
    if cfg.NZB_BACKUP_DIR.get_path():
        backup_name = filename + '.gz'

        # Need to go to the backup folder to
        # prevent the pathname being embedded in the GZ file
        here = os.getcwd()
        os.chdir(cfg.NZB_BACKUP_DIR.get_path())

        logging.info("Backing up %s", backup_name)
        try:
            _f = gzip.GzipFile(backup_name, 'wb')
            _f.write(data)
            _f.flush()
            _f.close()
        except:
            logging.error("Saving %s to %s failed", backup_name, cfg.NZB_BACKUP_DIR.get_path())
            logging.debug("Traceback: ", exc_info = True)

        os.chdir(here)


################################################################################
## CV synchronized (notifies downloader)                                      ##
################################################################################
@synchronized_CV
def add_nzbfile(nzbfile, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY, nzbname=None):
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None

    filename = codecs.name_fixer(nzbfile.filename)

    if not sabnzbd.WIN32:
        # If windows client sends file to Unix server backslashed may
        # be included, so convert these
        filename = filename.replace('\\', '/')

    filename = os.path.basename(filename)
    root, ext = os.path.splitext(filename)

    logging.info('Adding %s', filename)

    try:
        f, path = tempfile.mkstemp(suffix=ext, text=False)
        os.write(f, nzbfile.value)
        os.close(f)
    except:
        logging.error(Ta('error-tempFile@1'), filename)
        logging.debug("Traceback: ", exc_info = True)

    if ext.lower() in ('.zip', '.rar'):
        dirscanner.ProcessArchiveFile(filename, path, pp, script, cat, priority=priority)
    else:
        dirscanner.ProcessSingleFile(filename, path, pp, script, cat, priority=priority, nzbname=nzbname)


################################################################################
## Unsynchronized methods                                                     ##
################################################################################
def enable_server(server):
    try:
        config.get_config('servers', server).enable.set(1)
    except:
        logging.warning(Ta('warn-noServer@1'), server)
        return
    config.save_config()
    downloader.update_server(server, server)


def disable_server(server):
    """ Disable server """
    try:
        config.get_config('servers', server).enable.set(0)
    except:
        logging.warning(Ta('warn-noServer@1'), server)
        return
    config.save_config()
    downloader.update_server(server, server)


def system_shutdown():
    logging.info("Performing system shutdown")

    Thread(target=halt).start()
    while __INITIALIZED__:
        time.sleep(1.0)

    if sabnzbd.WIN32:
        misc.win_shutdown()
    elif DARWIN:
        misc.osx_shutdown()
    else:
        misc.linux_shutdown()


def system_hibernate():
    logging.info("Performing system hybernation")
    if sabnzbd.WIN32:
        misc.win_hibernate()
    elif DARWIN:
        misc.osx_shutdown()
    else:
        misc.linux_hibernate()


def system_standby():
    logging.info("Performing system standby")
    if sabnzbd.WIN32:
        misc.win_standby()
    elif DARWIN:
        misc.osx_standby()
    else:
        misc.linux_standby()


def shutdown_program():
    logging.info("Performing sabnzbd shutdown")
    Thread(target=halt).start()
    while __INITIALIZED__:
        time.sleep(1.0)
    os._exit(0)


def restart_program():
    """ Restart program (used by scheduler) """
    logging.info("Performing sabnzbd restart")
    sabnzbd.halt()
    while __INITIALIZED__:
        time.sleep(1.0)
    cherrypy.engine.restart()


def change_queue_complete_action(action):
    """
    Action or script to be performed once the queue has been completed
    Scripts are prefixed with 'script_'
    """
    global QUEUECOMPLETE, QUEUECOMPLETEACTION, QUEUECOMPLETEARG

    _action = None
    _argument = None
    if 'script_' in action:
        #all scripts are labeled script_xxx
        _action = run_script
        _argument = action.replace('script_', '')
    elif action == 'shutdown_pc':
        _action = system_shutdown
    elif action == 'hibernate_pc':
        _action = system_hibernate
    elif action == 'standby_pc':
        _action = system_standby
    elif action == 'shutdown_program':
        _action = shutdown_program

    #keep the name of the action for matching the current select in queue.tmpl
    QUEUECOMPLETE = action

    QUEUECOMPLETEACTION = _action
    QUEUECOMPLETEARG = _argument


def run_script(script):
    command = os.path.join(cfg.SCRIPT_DIR.get_path(), script)
    stup, need_shell, command, creationflags = sabnzbd.newsunpack.build_command(command)
    logging.info('Spawning external command %s', command)
    subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     startupinfo=stup, creationflags=creationflags)


def empty_queues():
    """ Return True if queues empty or non-existent """
    global __INITIALIZED__
    return (not __INITIALIZED__) or (postproc.empty() and not nzbqueue.has_articles())


def keep_awake():
    """ If we still have work to do, keep Windows system awake
    """
    global KERNEL32
    if KERNEL32 and not downloader.paused():
        if (not postproc.empty()) or nzbqueue.has_articles():
            # set ES_SYSTEM_REQUIRED
            KERNEL32.SetThreadExecutionState(ctypes.c_int(0x00000001))


def CheckFreeSpace():
    if cfg.DOWNLOAD_FREE.get() and not downloader.paused():
        if misc.diskfree(cfg.DOWNLOAD_DIR.get_path()) < cfg.DOWNLOAD_FREE.get_float() / GIGI:
            logging.warning(Ta('warn-noSpace'))
            # Pause downloader, but don't save, since the disk is almost full!
            downloader.pause_downloader(save=False)
            email.diskfull()


################################################################################
# Data IO                                                                      #
################################################################################
IO_LOCK = RLock()

@synchronized(IO_LOCK)
def get_new_id(prefix):
    try:
        fd, l = tempfile.mkstemp('', 'SABnzbd_%s_' % prefix, cfg.CACHE_DIR.get_path())
        os.close(fd)
        head, tail = os.path.split(l)
        return tail
    except:
        logging.error(Ta('error-failMkstemp'))
        logging.debug("Traceback: ", exc_info = True)


@synchronized(IO_LOCK)
def save_data(data, _id, do_pickle = True, doze=0):
    path = os.path.join(cfg.CACHE_DIR.get_path(), _id)
    logging.info("Saving data for %s in %s", _id, path)

    try:
        _f = open(path, 'wb')
        if do_pickle:
            cPickle.dump(data, _f, 2)
        else:
            _f.write(data)
        if doze:
            # Only for debugging decoder overflow
            time.sleep(doze)
        _f.flush()
        _f.close()
    except:
        logging.error(Ta('error-saveX@1'), path)
        logging.debug("Traceback: ", exc_info = True)


@synchronized(IO_LOCK)
def load_data(_id, remove = True, do_pickle = True):
    path = os.path.join(cfg.CACHE_DIR.get_path(), _id)
    logging.info("Loading data for %s from %s", _id, path)

    if not os.path.exists(path):
        logging.info("%s missing", path)
        return None

    data = None

    try:
        _f = open(path, 'rb')
        if do_pickle:
            data = cPickle.load(_f)
        else:
            data = _f.read()
        _f.close()

        if remove:
            remove_data(_id)
    except:
        logging.error(Ta('error-loading@1'), path)
        logging.debug("Traceback: ", exc_info = True)

    return data


@synchronized(IO_LOCK)
def remove_data(_id):
    path = os.path.join(cfg.CACHE_DIR.get_path(), _id)
    try:
        os.remove(path)
        logging.info("%s removed", path)
    except:
        pass


def pp_to_opts(pp):
    """ Convert numeric processinf options to (repair, unpack, delete) """
    # Convert the pp to an int
    pp = sabnzbd.interface.IntConv(pp)
    if pp == 0 : return (False, False, False)
    if pp == 1 : return (True, False, False)
    if pp == 2 : return (True, True, False)
    return (True, True, True)


def opts_to_pp(repair, unpack, delete):
    """ Convert (repair, unpack, delete) to numeric process options """
    if repair is None:
        return None
    pp = 0
    if repair: pp += 1
    if unpack: pp += 1
    if delete: pp += 1
    return pp


def SimpleRarExtract(rarfile, fn):
    """ Wrapper for call to newsunpack, required to avoid circular imports
    """
    return sabnzbd.newsunpack.SimpleRarExtract(rarfile, fn)


def check_all_tasks():
    """ Check every task and restart safe ones, else restart program
        Return True when everything is under control
    """
    if __SHUTTING_DOWN__ or not __INITIALIZED__:
        return True

    # Non-restartable threads, require program restart
    if not sabnzbd.postproc.alive():
        logging.info('Restarting because of crashed postprocessor')
        return False
    if not sabnzbd.downloader.alive():
        logging.info('Restarting because of crashed downloader')
        return False
    if not sabnzbd.assembler.alive():
        logging.info('Restarting because of crashed assembler')
        return False

    # Restartable threads
    if not sabnzbd.dirscanner.alive():
        logging.info('Restarting crashed dirscanner')
        sabnzbd.dirscanner.init()
    if not sabnzbd.urlgrabber.alive():
        logging.info('Restarting crashed urlgrabber')
        sabnzbd.urlgrabber.init()
    if not sabnzbd.newzbin.alive():
        logging.info('Restarting crashed newzbin')
        sabnzbd.newzbin.init_grabber()
    if not sabnzbd.scheduler.sched_check():
        logging.info('Restarting crashed scheduler')
        sabnzbd.scheduler.init()
    return True
