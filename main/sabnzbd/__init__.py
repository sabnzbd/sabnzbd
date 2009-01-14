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
__NAME__ = "sabnzbd"

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

try:
    import ctypes
    KERNEL32 = ctypes.windll.LoadLibrary("Kernel32.dll")
except:
    KERNEL32 = None

try:
    # Try to import OSX library
    import Foundation
    import subprocess
    DARWIN = True
except:
    DARWIN = False

from threading import RLock, Lock, Condition, Thread

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

from sabnzbd.decorators import *
from sabnzbd.constants import *


START = datetime.datetime.now()

MY_NAME = None
MY_FULLNAME = None
NEW_VERSION = None
DIR_HOME = None
DIR_APPDATA = None
DIR_LCLDATA = None
DIR_PROG = None
DIR_INTERFACES = None

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
WEB_COLOR = None
WEB_COLOR2 = None
SABSTOP = False
RESTART_REQ = False

__INITIALIZED__ = False


################################################################################
# Signal Handler                                                               #
################################################################################
def sig_handler(signum = None, frame = None):
    global SABSTOP
    if os.name == 'nt' and type(signum) != type(None) and DAEMON and signum==5:
        # Ignore the "logoff" event when running as a Win32 daemon
        return True
    if type(signum) != type(None):
        logging.warning('[%s] Signal %s caught, saving and exiting...', __NAME__, signum)
    try:
        save_state()
    finally:
        SABSTOP = True
        os._exit(0)


################################################################################
# Initializing                                                                 #
################################################################################

INIT_LOCK = Lock()

@synchronized(INIT_LOCK)
def initialize(pause_downloader = False, clean_up = False, force_save= False, evalSched=False):
    global __INITIALIZED__, \
           LOGFILE, WEBLOGFILE, LOGHANDLER, GUIHANDLER, AMBI_LOCALHOST, WAITEXIT, \
           DEBUG_DELAY, \
           DAEMON, MY_NAME, MY_FULLNAME, NEW_VERSION, \
           DIR_HOME, DIR_APPDATA, DIR_LCLDATA, DIR_PROG , DIR_INTERFACES, \
           DARWIN, RESTART_REQ

    if __INITIALIZED__:
        return False

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

    ### Set cache limit
    articlecache.method.new_limit(cfg.CACHE_LIMIT.get_int(), cfg.DEBUG_DELAY.get())

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
        logging.debug('[%s] Starting postprocessor', __NAME__)
        postproc.start()

        logging.debug('[%s] Starting assembler', __NAME__)
        assembler.start()

        logging.debug('[%s] Starting downloader', __NAME__)
        downloader.start()

        scheduler.start()

        logging.debug('[%s] Starting dirscanner', __NAME__)
        dirscanner.start()

        newzbin.start_grabber()

        logging.debug('[%s] Starting urlgrabber', __NAME__)
        urlgrabber.start()


@synchronized(INIT_LOCK)
def halt():
    global __INITIALIZED__

    if __INITIALIZED__:
        logging.info('SABnzbd shutting down...')

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
        ### scheduler.stop()

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


def add_msgid(msgid, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY):

    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None


    if cfg.USERNAME_NEWZBIN.get() and cfg.PASSWORD_NEWZBIN.get():
        logging.info('[%s] Fetching msgid %s from www.newzbin.com',
                     __NAME__, msgid)
        msg = "fetching msgid %s from www.newzbin.com" % msgid

        future_nzo = nzbqueue.generate_future(msg, pp, script, cat=cat, url=msgid, priority=priority)

        newzbin.grab(msgid, future_nzo)
    else:
        logging.error('[%s] Error Fetching msgid %s from www.newzbin.com - Please make sure your Username and Password are set',
                             __NAME__, msgid)


def add_url(url, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY):
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None

    logging.info('[%s] Fetching %s', __NAME__, url)
    msg = "Trying to fetch NZB from %s" % url
    future_nzo = nzbqueue.generate_future(msg, pp, script, cat, url=url, priority=priority)
    urlgrabber.add(url, future_nzo)


def save_state():
    articlecache.method.flush_articles()
    nzbqueue.save()
    save_data(str(sabnzbd.bpsmeter.method.get_sum()), BYTES_FILE_NAME, do_pickle = False)
    rss.save()
    newzbin.bookmarks_save()
    dirscanner.save()
    postproc.save()


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

        logging.info("[%s] Backing up %s", __NAME__, backup_name)
        try:
            _f = gzip.GzipFile(backup_name, 'wb')
            _f.write(data)
            _f.flush()
            _f.close()
        except:
            logging.error("[%s] Saving %s to %s failed", __NAME__, backup_name, cfg.NZB_BACKUP_DIR.get_path())

        os.chdir(here)


################################################################################
## CV synchronized (notifies downloader)                                      ##
################################################################################
@synchronized_CV
def add_nzbfile(nzbfile, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY):
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None

    filename = codecs.name_fixer(nzbfile.filename)

    if os.name != 'nt':
        # If windows client sends file to Unix server backslashed may
        # be included, so convert these
        filename = filename.replace('\\', '/')

    filename = os.path.basename(filename)
    root, ext = os.path.splitext(filename)

    logging.info('[%s] Adding %s', __NAME__, filename)

    try:
        f, path = tempfile.mkstemp(suffix=ext, text=False)
        os.write(f, nzbfile.value)
        os.close(f)
    except:
        logging.error("[%s] Cannot create temp file for %s", __NAME__, filename)

    if ext.lower() in ('.zip', '.rar'):
        dirscanner.ProcessArchiveFile(filename, path, pp, script, cat, priority)
    else:
        dirscanner.ProcessSingleFile(filename, path, pp, script, cat, priority)


################################################################################
## Unsynchronized methods                                                     ##
################################################################################
def enable_server(server):
    try:
        config.get_config('servers', server).enable.set(1)
    except:
        logging.warning('[%s] Trying to set status of non-existing server %s', __NAME__, server)
        return
    config.save_config()
    downloader.update_server(server, server)


def disable_server(server):
    """ Disable server """
    try:
        config.get_config('servers', server).enable.set(0)
    except:
        logging.warning('[%s] Trying to set status of non-existing server %s', __NAME__, server)
        return
    config.save_config()
    downloader.update_server(server, server)


def system_shutdown():
    logging.info("[%s] Performing system shutdown", __NAME__)

    Thread(target=halt).start()
    while __INITIALIZED__:
        time.sleep(1.0)

    if os.name == 'nt':
        try:
            import win32security
            import win32api
            import ntsecuritycon

            flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES | ntsecuritycon.TOKEN_QUERY
            htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
            id = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_SHUTDOWN_NAME)
            newPrivileges = [(id, ntsecuritycon.SE_PRIVILEGE_ENABLED)]
            win32security.AdjustTokenPrivileges(htoken, 0, newPrivileges)
            win32api.InitiateSystemShutdown("", "", 30, 1, 0)
        finally:
            os._exit(0)

    elif DARWIN:
        Thread(target=halt).start()
        while __INITIALIZED__:
            time.sleep(1.0)
        try:
            subprocess.call(['osascript', '-e', 'tell app "System Events" to shut down'])
        finally:
            os._exit(0)


def system_hibernate():
    logging.info("[%s] Performing system hybernation", __NAME__)
    try:
        if os.name == 'nt':
            subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Hibernate")
            time.sleep(10)
    except:
        logging.error("[%s] Failed to hibernate system", __NAME__)


def system_standby():
    logging.info("[%s] Performing system standby", __NAME__)
    try:
        if os.name == 'nt':
            subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Standby")
        elif DARWIN:
            subprocess.call(['osascript', '-e','tell app "System Events" to sleep'])
        time.sleep(10)
    except:
        logging.error("[%s] Failed to standby system", __NAME__)


def shutdown_program():
    logging.info("[%s] Performing sabnzbd shutdown", __NAME__)
    Thread(target=halt).start()
    while __INITIALIZED__:
        time.sleep(1.0)
    os._exit(0)


def restart_program():
    """ Restart program (used by scheduler) """
    logging.info("[%s] Performing sabnzbd restart", __NAME__)
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
    logging.info('[%s] Spawning external command %s', __NAME__, command)
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
            logging.warning('Too little diskspace forcing PAUSE')
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
        logging.error("[%s] Failure in tempfile.mkstemp", __NAME__)
        logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)


@synchronized(IO_LOCK)
def save_data(data, _id, do_pickle = True, doze=0):
    path = os.path.join(cfg.CACHE_DIR.get_path(), _id)
    logging.info("[%s] Saving data for %s in %s", __NAME__, _id, path)

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
        logging.error("[%s] Saving %s failed", __NAME__, path)


@synchronized(IO_LOCK)
def load_data(_id, remove = True, do_pickle = True):
    path = os.path.join(cfg.CACHE_DIR.get_path(), _id)
    logging.info("[%s] Loading data for %s from %s", __NAME__, _id, path)

    if not os.path.exists(path):
        logging.info("[%s] %s missing", __NAME__, path)
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
        logging.error("[%s] Loading %s failed", __NAME__, path)

    return data


@synchronized(IO_LOCK)
def remove_data(_id):
    path = os.path.join(cfg.CACHE_DIR.get_path(), _id)
    try:
        os.remove(path)
        logging.info("[%s] %s removed", __NAME__, path)
    except:
        pass


def pp_to_opts(pp):
    """ Convert numeric processinf options to (repair, unpack, delete) """
    repair = unpack = delete = False
    try:
        pp = int(pp)
    except:
        pp = 0
    if pp > 0:
        repair = True
        if pp > 1:
            unpack = True
            if pp > 2:
                delete = True

    return (repair, unpack, delete)


def opts_to_pp(repair, unpack, delete):
    """ Convert (repair, unpack, delete) to numeric process options """
    if repair == None:
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
