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
    ORG_UMASK = os.umask(18)
    os.umask(ORG_UMASK)
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

from sabnzbd.nzbqueue import NzbQueue
from sabnzbd.postproc import PostProcessor
from sabnzbd.downloader import Downloader
from sabnzbd.assembler import Assembler
from sabnzbd.newzbin import Bookmarks, MSGIDGrabber
import sabnzbd.misc as misc
import sabnzbd.powersup as powersup
from sabnzbd.dirscanner import DirScanner,  ProcessArchiveFile, ProcessSingleFile
from sabnzbd.urlgrabber import URLGrabber
import sabnzbd.scheduler as scheduler
import sabnzbd.rss as rss
import sabnzbd.emailer as emailer
from sabnzbd.articlecache import ArticleCache
import sabnzbd.newsunpack
import sabnzbd.encoding as encoding
import sabnzbd.config as config
from sabnzbd.bpsmeter import BPSMeter
import sabnzbd.cfg as cfg
import sabnzbd.database
import sabnzbd.lang as lang
import sabnzbd.api
from sabnzbd.decorators import *
from sabnzbd.constants import *

LINUX_POWER = powersup.HAVE_DBUS

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
DIR_PID = None

QUEUECOMPLETE = None #stores the nice name of the action
QUEUECOMPLETEACTION = None #stores the name of the function to be called
QUEUECOMPLETEARG = None #stores an extra arguments that need to be passed

DAEMON = None

LOGFILE = None
WEBLOGFILE = None
LOGHANDLER = None
GUIHANDLER = None
LOG_ALL = False
AMBI_LOCALHOST = False
WIN_SERVICE = None      # Instance of our Win32 Service Class
BROWSER_URL = None
CMDLINE = ''  # Rendering of original command line arguments

WEB_DIR = None
WEB_DIR2 = None
WIZARD_DIR = None
WEB_COLOR = None
WEB_COLOR2 = None
SABSTOP = False
RESTART_REQ = False
OSX_ICON = 1
PAUSED_ALL = False
OLD_QUEUE = False
SCHED_RESTART = False # Set when restarted through scheduler

__INITIALIZED__ = False
__SHUTTING_DOWN__ = False



################################################################################
# Table to map 0.5.x style language code to new style
LANG_MAP = {
    'de-de' : 'de',
    'dk-da' : 'da', # Should have been "da-dk"
    'fr-fr' : 'fr',
    'nl-du' : 'nl', # Should have been "du-nl"
    'no-no' : 'nb', # Norsk Bokmal
    'sv-se' : 'sv',
    'us-en' : 'en'  # Should have been "en-us"
}


################################################################################
# Signal Handler                                                               #
################################################################################
def sig_handler(signum = None, frame = None):
    global SABSTOP
    if sabnzbd.WIN32 and type(signum) != type(None) and DAEMON and signum==5:
        # Ignore the "logoff" event when running as a Win32 daemon
        return True
    if type(signum) != type(None):
        logging.warning(Ta('Signal %s caught, saving and exiting...'), signum)
    try:
        save_state(flag=True)
    finally:
        if sabnzbd.WIN32:
            from util.apireg import del_connection_info
            del_connection_info()
        else:
            pid_file()
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
def initialize(pause_downloader = False, clean_up = False, evalSched=False, repair=0):
    global __INITIALIZED__, __SHUTTING_DOWN__,\
           LOGFILE, WEBLOGFILE, LOGHANDLER, GUIHANDLER, AMBI_LOCALHOST, WAITEXIT, \
           DAEMON, MY_NAME, MY_FULLNAME, NEW_VERSION, \
           DIR_HOME, DIR_APPDATA, DIR_LCLDATA, DIR_PROG , DIR_INTERFACES, \
           DARWIN, RESTART_REQ, OSX_ICON, OLD_QUEUE

    if __INITIALIZED__:
        return False

    __SHUTTING_DOWN__ = False

    ### Set global database connection for Web-UI threads
    cherrypy.engine.subscribe('start_thread', connect_db)

    ### Clean-up, if requested
    if clean_up:
        # Old cache folder
        misc.remove_all(cfg.cache_dir.get_path(), '*.sab')
        misc.remove_all(cfg.cache_dir.get_path(), 'SABnzbd_*')
        # New admin folder
        misc.remove_all(cfg.admin_dir.get_path(), '*.sab')

    ### If dirscan_dir cannot be created, set a proper value anyway.
    ### Maybe it's a network path that's temporarily missing.
    path = cfg.dirscan_dir.get_path()
    if not os.path.exists(path):
        sabnzbd.misc.create_real_path(cfg.dirscan_dir.ident(), '', path, False)

    ### Set call backs for Config items
    cfg.cache_limit.callback(new_limit)
    cfg.cherryhost.callback(guard_restart)
    cfg.cherryport.callback(guard_restart)
    cfg.web_dir.callback(guard_restart)
    cfg.web_dir2.callback(guard_restart)
    cfg.web_color.callback(guard_restart)
    cfg.web_color2.callback(guard_restart)
    cfg.log_dir.callback(guard_restart)
    cfg.cache_dir.callback(guard_restart)
    cfg.https_port.callback(guard_restart)
    cfg.https_cert.callback(guard_restart)
    cfg.https_key.callback(guard_restart)
    cfg.enable_https.callback(guard_restart)
    cfg.bandwidth_limit.callback(guard_speedlimit)
    cfg.top_only.callback(guard_top_only)
    cfg.pause_on_post_processing.callback(guard_pause_on_pp)

    ### Set cache limit
    ArticleCache.do.new_limit(cfg.cache_limit.get_int())

    ### Handle language upgrade from 0.5.x to 0.6.x
    cfg.language.set(LANG_MAP.get(cfg.language(), cfg.language()))

    ### Set language files
    lang.set_locale_info('SABnzbd', DIR_LANGUAGE)
    lang.set_language(cfg.language())
    sabnzbd.api.cache_skin_trans()

    ### Check for old queue (when a new queue is not present)
    if not os.path.exists(os.path.join(cfg.cache_dir.get_path(), QUEUE_FILE_NAME)):
        OLD_QUEUE = bool(misc.globber(cfg.cache_dir.get_path(), QUEUE_FILE_TMPL % '?'))

    sabnzbd.change_queue_complete_action(cfg.queue_complete(), new=False)

    if check_repair_request():
        repair = 2
        pause_downloader = True
    else:
        # Check crash detection file
        #if load_admin(TERM_FLAG_FILE, remove=True):
            # Repair mode 2 is a bit over an over-reaction!
        pass # repair = 2

    # Set crash detection file
    #save_admin(1, TERM_FLAG_FILE)

    ###
    ### Initialize threads
    ###

    Bookmarks()
    rss.init()

    BPSMeter.do.read()

    PostProcessor()

    NzbQueue()
    NzbQueue.do.read_queue(repair)

    Assembler()

    Downloader(pause_downloader)

    DirScanner()

    MSGIDGrabber()

    URLGrabber()

    scheduler.init()

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
        PostProcessor.do.start()

        logging.debug('Starting assembler')
        Assembler.do.start()

        logging.debug('Starting downloader')
        Downloader.do.start()

        scheduler.start()

        logging.debug('Starting dirscanner')
        DirScanner.do.start()

        MSGIDGrabber.do.start()

        logging.debug('Starting urlgrabber')
        URLGrabber.do.start()


@synchronized(INIT_LOCK)
def halt():
    global __INITIALIZED__, __SHUTTING_DOWN__

    if __INITIALIZED__:
        logging.info('SABnzbd shutting down...')
        __SHUTTING_DOWN__ = True

        rss.stop()

        Bookmarks.do.save()

        logging.debug('Stopping URLGrabber')
        URLGrabber.do.stop()
        try:
            URLGrabber.do.join()
        except:
            pass

        logging.debug('Stopping Newzbin-Grabber')
        MSGIDGrabber.do.stop()
        try:
            MSGIDGrabber.do.join()
        except:
            pass

        logging.debug('Stopping dirscanner')
        DirScanner.do.stop()
        try:
            DirScanner.do.join()
        except:
            pass


        ## Stop Required Objects ##
        logging.debug('Stopping downloader')
        sabnzbd.downloader.stop()

        logging.debug('Stopping assembler')
        Assembler.do.stop()
        try:
            Assembler.do.join()
        except:
            pass

        logging.debug('Stopping postprocessor')
        PostProcessor.do.stop()
        try:
            PostProcessor.do.join()
        except:
            pass

        ## Save State ##
        try:
            save_state(flag=True)
        except:
            logging.error('Fatal error at saving state', exc_info=True)


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
    ArticleCache.do.new_limit(cfg.cache_limit.get_int())

def guard_restart():
    """ Callback for config options requiring a restart """
    global RESTART_REQ
    sabnzbd.RESTART_REQ = True

def guard_speedlimit():
    """ Callback for change of bandwidth_limit, sets actual speed """
    Downloader.do.limit_speed(cfg.bandwidth_limit())

def guard_top_only():
    """ Callback for change of top_only option """
    NzbQueue.do.set_top_only(cfg.top_only())

def guard_pause_on_pp():
    """ Callback for change of pause-download-on-pp """
    if cfg.pause_on_post_processing():
        pass # Not safe to idle downloader, because we don't know
             # if post-processing is active now
    else:
        Downloader.do.resume_from_postproc()

def add_msgid(msgid, pp=None, script=None, cat=None, priority=None, nzbname=None):
    """ Add NZB based on newzbin report number, attributes optional
    """
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None

    if cfg.newzbin_username() and cfg.newzbin_password():
        logging.info('Fetching msgid %s from www.newzbin.com', msgid)
        msg = T('fetching msgid %s from www.newzbin.com') % msgid

        future_nzo = NzbQueue.do.generate_future(msg, pp, script, cat=cat, url=msgid, priority=priority, nzbname=nzbname)

        MSGIDGrabber.do.grab(msgid, future_nzo)
    else:
        logging.error(Ta('Error Fetching msgid %s from www.newzbin.com - Please make sure your Username and Password are set'), msgid)


def add_url(url, pp=None, script=None, cat=None, priority=None, nzbname=None):
    """ Add NZB based on a URL, attributes optional
    """
    if 'http' not in url:
        return
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None
    logging.info('Fetching %s', url)
    msg = T('Trying to fetch NZB from %s') % url
    future_nzo = NzbQueue.do.generate_future(msg, pp, script, cat, url=url, priority=priority, nzbname=nzbname)
    URLGrabber.do.add(url, future_nzo)


def save_state(flag=False):
    """ Save all internal bookkeeping to disk """
    ArticleCache.do.flush_articles()
    NzbQueue.do.save()
    BPSMeter.do.save()
    rss.save()
    Bookmarks.do.save()
    DirScanner.do.save()
    PostProcessor.do.save()
    #if flag:
    #    # Remove crash detector
    #    load_admin(TERM_FLAG_FILE, remove=True)

def pause_all():
    """ Pause all activities than cause disk access
    """
    global PAUSED_ALL
    PAUSED_ALL = True
    Downloader.do.pause()
    logging.debug('PAUSED_ALL active')

def unpause_all():
    """ Resume all activcities
    """
    global PAUSED_ALL
    PAUSED_ALL = False
    Downloader.do.resume()
    logging.debug('PAUSED_ALL inactive')


################################################################################
## NZB_LOCK Methods                                                           ##
################################################################################
NZB_LOCK = Lock()

@synchronized(NZB_LOCK)
def backup_exists(filename):
    """ Return True if backup exists and no_dupes is set
    """
    path = cfg.nzb_backup_dir.get_path()
    return path and sabnzbd.cfg.no_dupes() and \
           os.path.exists(os.path.join(path, filename+'.gz'))

def backup_nzb(filename, data):
    """ Backup NZB file
    """
    path = cfg.nzb_backup_dir.get_path()
    if path:
        save_compressed(path, filename, data)


@synchronized(NZB_LOCK)
def save_compressed(folder, filename, data):
    """ Save compressed NZB file in folder
    """
    # Need to go to the save folder to
    # prevent the pathname being embedded in the GZ file
    here = os.getcwd()
    os.chdir(folder)

    if filename.endswith('.nzb'):
        filename += '.gz'
    else:
        filename += '.nzb.gz'
    logging.info("Backing up %s", os.path.join(folder, filename))
    try:
        f = gzip.GzipFile(filename, 'wb')
        f.write(data)
        f.flush()
        f.close()
    except:
        logging.error("Saving %s failed", os.path.join(folder, filename))
        logging.info("Traceback: ", exc_info = True)

    os.chdir(here)


################################################################################
## CV synchronized (notifies downloader)                                      ##
################################################################################
@synchronized_CV
def add_nzbfile(nzbfile, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY, nzbname=None, reuse=False):
    """ Add disk-based NZB file, optional attributes,
        'reuse' flag will suppress duplicate detection
    """
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None

    if isinstance(nzbfile, str):
        # File coming from queue repair
        filename = nzbfile
        keep = True
    else:
        # File coming from API/TAPI
        # Consider reception of Latin-1 names for non-Windows platforms
        # When an OSX/Unix server receives a file from Windows platform
        filename = encoding.special_fixer(nzbfile.filename)
        keep = False

    if not sabnzbd.WIN32:
        # If windows client sends file to Unix server backslashed may
        # be included, so convert these
        filename = filename.replace('\\', '/')

    filename = os.path.basename(filename)
    root, ext = os.path.splitext(filename)

    logging.info('Adding %s', filename)

    if isinstance(nzbfile, str):
        path = nzbfile
    else:
        try:
            f, path = tempfile.mkstemp(suffix=ext, text=False)
            os.write(f, nzbfile.value)
            os.close(f)
        except:
            logging.error(Ta('Cannot create temp file for %s'), filename)
            logging.info("Traceback: ", exc_info = True)

    if ext.lower() in ('.zip', '.rar'):
        ProcessArchiveFile(filename, path, pp, script, cat, priority=priority)
    else:
        ProcessSingleFile(filename, path, pp, script, cat, priority=priority, nzbname=nzbname, keep=keep, reuse=reuse)


################################################################################
## Unsynchronized methods                                                     ##
################################################################################
def enable_server(server):
    """ Enable server (scheduler only)
    """
    try:
        config.get_config('servers', server).enable.set(1)
    except:
        logging.warning(Ta('Trying to set status of non-existing server %s'), server)
        return
    config.save_config()
    Downloader.do.update_server(server, server)


def disable_server(server):
    """ Disable server (scheduler only)
    """
    try:
        config.get_config('servers', server).enable.set(0)
    except:
        logging.warning(Ta('Trying to set status of non-existing server %s'), server)
        return
    config.save_config()
    Downloader.do.update_server(server, server)


def system_shutdown():
    """ Shutdown system after halting download and saving bookkeeping
    """
    logging.info("Performing system shutdown")

    Thread(target=halt).start()
    while __INITIALIZED__:
        time.sleep(1.0)

    if sabnzbd.WIN32:
        powersup.win_shutdown()
    elif DARWIN:
        powersup.osx_shutdown()
    else:
        powersup.linux_shutdown()


def system_hibernate():
    """ Hibernate system """
    logging.info("Performing system hybernation")
    if sabnzbd.WIN32:
        powersup.win_hibernate()
    elif DARWIN:
        powersup.osx_hibernate()
    else:
        powersup.linux_hibernate()


def system_standby():
    """ Standby system """
    logging.info("Performing system standby")
    if sabnzbd.WIN32:
        powersup.win_standby()
    elif DARWIN:
        powersup.osx_standby()
    else:
        powersup.linux_standby()


def shutdown_program():
    """ Stop program after halting and saving """
    logging.info("Performing sabnzbd shutdown")
    Thread(target=halt).start()
    while __INITIALIZED__:
        time.sleep(1.0)
    os._exit(0)


def restart_program():
    """ Restart program (used by scheduler) """
    global SCHED_RESTART
    logging.info("Scheduled restart request")
    # Just set the stop flag, because stopping CherryPy from
    # the scheduler is not reliable
    cherrypy.engine.execv = SCHED_RESTART = True


def change_queue_complete_action(action, new=True):
    """
    Action or script to be performed once the queue has been completed
    Scripts are prefixed with 'script_'
    When "new" is False, check wether non-script actions are acceptable
    """
    global QUEUECOMPLETE, QUEUECOMPLETEACTION, QUEUECOMPLETEARG

    _action = None
    _argument = None
    if 'script_' in action:
        #all scripts are labeled script_xxx
        _action = run_script
        _argument = action.replace('script_', '')
    elif new or cfg.queue_complete_pers.get():
        if action == 'shutdown_pc':
            _action = system_shutdown
        elif action == 'hibernate_pc':
            _action = system_hibernate
        elif action == 'standby_pc':
            _action = system_standby
        elif action == 'shutdown_program':
            _action = shutdown_program
        else:
            action = None
    else:
        action = None

    if new:
        cfg.queue_complete.set(action or '')
        config.save_config()

    #keep the name of the action for matching the current select in queue.tmpl
    QUEUECOMPLETE = action

    QUEUECOMPLETEACTION = _action
    QUEUECOMPLETEARG = _argument


def run_script(script):
    """ Run a user script (queue complete only) """
    command = [os.path.join(cfg.script_dir.get_path(), script)]
    stup, need_shell, command, creationflags = sabnzbd.newsunpack.build_command(command)
    logging.info('Spawning external command %s', command)
    subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     startupinfo=stup, creationflags=creationflags)


def empty_queues():
    """ Return True if queues empty or non-existent """
    global __INITIALIZED__
    return (not __INITIALIZED__) or (PostProcessor.do.empty() and NzbQueue.do.is_empty())


def keep_awake():
    """ If we still have work to do, keep Windows system awake
    """
    global KERNEL32
    if KERNEL32 and not sabnzbd.downloader.Downloader.do.paused:
        if (not PostProcessor.do.empty()) or not NzbQueue.do.is_empty():
            # set ES_SYSTEM_REQUIRED
            KERNEL32.SetThreadExecutionState(ctypes.c_int(0x00000001))


def CheckFreeSpace():
    """ Check if enough disk space is free, if not pause downloader and send email
    """
    if cfg.download_free() and not sabnzbd.downloader.Downloader.do.paused:
        if misc.diskfree(cfg.download_dir.get_path()) < cfg.download_free.get_float() / GIGI:
            logging.warning(Ta('Too little diskspace forcing PAUSE'))
            # Pause downloader, but don't save, since the disk is almost full!
            Downloader.do.pause(save=False)
            emailer.diskfull()


################################################################################
# Data IO                                                                      #
################################################################################
IO_LOCK = RLock()

@synchronized(IO_LOCK)
def get_new_id(prefix, folder, check_list=None):
    """ Return unique prefixed admin identifier within folder
        optionally making sure that id is not in the check_list.
    """
    for n in xrange(10000):
        try:
            if not os.path.exists(folder):
                os.makedirs(folder)
            fd, path = tempfile.mkstemp('', 'SABnzbd_%s_' % prefix, folder)
            os.close(fd)
            head, tail = os.path.split(path)
            if not check_list or tail not in check_list:
                return tail
        except:
            logging.error(Ta('Failure in tempfile.mkstemp'))
            logging.info("Traceback: ", exc_info = True)
    # Cannot create unique id, crash the process
    raise IOError


@synchronized(IO_LOCK)
def save_data(data, _id, path, do_pickle = True, silent=False):
    """ Save data to a diskfile """
    if not silent:
        logging.debug("Saving data for %s in %s", _id, path)
    path = os.path.join(path, _id)

    try:
        _f = open(path, 'wb')
        if do_pickle:
            pickler = cPickle.Pickler(_f, 2)
            pickler.dump(data)
            _f.flush()
            _f.close()
            pickler.clear_memo()
            del pickler
        else:
            _f.write(data)
            _f.flush()
            _f.close()
    except:
        logging.error(Ta('Saving %s failed'), path)
        logging.info("Traceback: ", exc_info = True)


@synchronized(IO_LOCK)
def load_data(_id, path, remove=True, do_pickle=True, silent=False):
    """ Read data from disk file """
    path = os.path.join(path, _id)

    if not os.path.exists(path):
        logging.info("%s missing", path)
        return None

    if not silent:
        logging.debug("Loading data for %s from %s", _id, path)

    try:
        _f = open(path, 'rb')
        if do_pickle:
            data = cPickle.load(_f)
        else:
            data = _f.read()
        _f.close()

        if remove:
            os.remove(path)
    except:
        logging.error(Ta('Loading %s failed'), path)
        logging.info("Traceback: ", exc_info = True)
        return None

    return data


@synchronized(IO_LOCK)
def remove_data(_id, path):
    """ Remove admin file """
    path = os.path.join(path, _id)
    try:
        if os.path.exists(path):
            os.remove(path)
            logging.info("%s removed", path)
    except:
        logging.info("Failed to remove %s", path)
        logging.info("Traceback: ", exc_info = True)



@synchronized(IO_LOCK)
def save_admin(data, _id, do_pickle=True):
    """ Save data in admin folder in specified format """
    path = os.path.join(cfg.admin_dir.get_path(), _id)
    logging.info("Saving data for %s in %s", _id, path)

    try:
        _f = open(path, 'wb')
        if do_pickle:
            pickler = cPickle.Pickler(_f, 2)
            pickler.dump(data)
            _f.flush()
            _f.close()
            pickler.clear_memo()
            del pickler
        else:
            _f.write(data)
            _f.flush()
            _f.close()
    except:
        logging.error(Ta('Saving %s failed'), path)
        logging.info("Traceback: ", exc_info = True)


@synchronized(IO_LOCK)
def load_admin(_id, remove=False, do_pickle=True):
    """ Read data in admin folder in specified format """
    path = os.path.join(cfg.admin_dir.get_path(), _id)
    logging.info("Loading data for %s from %s", _id, path)

    if not os.path.exists(path):
        logging.info("%s missing, trying old cache", path)
        path = os.path.join(cfg.cache_dir.get_path(), _id)
        if not os.path.exists(path):
            logging.info("%s missing", path)
            return None
        remove = True

    try:
        f = open(path, 'rb')
        if do_pickle:
            data = cPickle.load(f)
        else:
            data = f.read()
        f.close()

        if remove:
            os.remove(path)
    except:
        logging.error(Ta('Loading %s failed'), path)
        logging.info("Traceback: ", exc_info = True)
        return None

    return data



def pp_to_opts(pp):
    """ Convert numeric processinf options to (repair, unpack, delete) """
    # Convert the pp to an int
    pp = sabnzbd.interface.int_conv(pp)
    if pp == 0 : return (False, False, False)
    if pp == 1 : return (True, False, False)
    if pp == 2 : return (True, True, False)
    return (True, True, True)


def opts_to_pp(repair, unpack, delete):
    """ Convert (repair, unpack, delete) to numeric process options """
    if repair is None:
        return None
    pp = 0
    if repair: pp = 1
    if unpack: pp = 2
    if delete: pp = 3
    return pp


def request_repair():
    """ Request a full repair on next restart """
    path = os.path.join(cfg.admin_dir.get_path(), REPAIR_REQUEST)
    try:
        f = open(path, 'w')
        f.write('\n')
        f.close()
    except:
        pass

def check_repair_request():
    """ Return True if repair request found, remove afterwards """
    path = os.path.join(cfg.admin_dir.get_path(), REPAIR_REQUEST)
    if os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass
        return True
    return False


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
    if not sabnzbd.PostProcessor.do.isAlive():
        logging.info('Restarting because of crashed postprocessor')
        return False
    if not Downloader.do.isAlive():
        logging.info('Restarting because of crashed downloader')
        return False
    if not Assembler.do.isAlive():
        logging.info('Restarting because of crashed assembler')
        return False

    # Kick the downloader, in case it missed the semaphore
    Downloader.do.wakeup()

    # Make sure the right servers are active
    Downloader.do.check_timers()

    # Restartable threads
    if not DirScanner.do.isAlive():
        logging.info('Restarting crashed dirscanner')
        DirScanner.do.__init__()
    if not URLGrabber.do.isAlive():
        logging.info('Restarting crashed urlgrabber')
        URLGrabber.do.__init__()
    if not MSGIDGrabber.do.isAlive():
        logging.info('Restarting crashed newzbin')
        MSGIDGrabber.do.__init__()
    if not sabnzbd.scheduler.sched_check():
        logging.info('Restarting crashed scheduler')
        sabnzbd.scheduler.init()
        sabnzbd.downloader.Downloader.do.unblock_all()

    # Check one-shot pause
    sabnzbd.scheduler.pause_check()

    return True


def pid_file(pid_path=None, port=0):
    """ Create or remove pid file
    """
    global DIR_PID
    if not sabnzbd.WIN32 and pid_path and pid_path.startswith('/'):
        DIR_PID = os.path.join(pid_path, 'sabnzbd-%s.pid' % port)

    if DIR_PID:
        try:
            if port:
                f = open(DIR_PID, 'w')
                f.write('%d\n' % os.getpid())
                f.close()
            else:
                os.remove(DIR_PID)
        except:
            logging.warning('Cannot access PID file %s', DIR_PID)



# Required wrapper because nzbstuff.py cannot import downloader.py
def active_primaries():
    return sabnzbd.downloader.Downloader.do.active_primaries()


def proxy_postproc(nzo):
    sabnzbd.postproc.PostProcessor.do.process(nzo)

def proxy_pre_queue(name, pp, cat, script, priority, size, groups):
    return sabnzbd.newsunpack.pre_queue(name, pp, cat, script, priority, size, groups)

def proxy_get_history_size():
    history_db = sabnzbd.database.get_history_handle()
    return history_db.get_history_size()

def proxy_build_history():
    """ Proxy to let nzbqueue call api """
    return sabnzbd.api.build_history()

def proxy_rm_bookmark(url):
    """ Proxy to urlgrabber rm_bookmark """
    return sabnzbd.urlgrabber.URLGrabber.do.rm_bookmark(url)
