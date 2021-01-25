#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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

import os
import logging
import datetime
import tempfile
import pickle
import gzip
import time
import socket
import cherrypy
import sys
import ssl
from threading import Lock, Thread, Condition
from typing import Any, AnyStr

##############################################################################
# Determine platform flags
##############################################################################
WIN32 = DARWIN = FOUNDATION = WIN64 = DOCKER = False
KERNEL32 = None

if os.name == "nt":
    WIN32 = True
    from sabnzbd.utils.apireg import del_connection_info

    try:
        import ctypes

        KERNEL32 = ctypes.windll.LoadLibrary("Kernel32.dll")
    except:
        pass
elif os.name == "posix":
    ORG_UMASK = os.umask(18)
    os.umask(ORG_UMASK)

    # Check if running in a Docker container
    try:
        with open("/proc/1/cgroup", "rt") as ifh:
            DOCKER = ":/docker/" in ifh.read()
    except:
        pass

    import platform

    if platform.system().lower() == "darwin":
        DARWIN = True
        # 12 = Sierra, 11 = ElCaptain, 10 = Yosemite, 9 = Mavericks, 8 = MountainLion
        DARWIN_VERSION = int(platform.mac_ver()[0].split(".")[1])
        try:
            import Foundation
            import sabnzbd.utils.sleepless as sleepless

            FOUNDATION = True
        except:
            pass

# Imported to be referenced from other files directly
from sabnzbd.version import __version__, __baseline__

# Now we can import safely
import sabnzbd.misc as misc
import sabnzbd.filesystem as filesystem
import sabnzbd.powersup as powersup
import sabnzbd.rss as rss
import sabnzbd.emailer as emailer
import sabnzbd.encoding as encoding
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.database
import sabnzbd.lang as lang
import sabnzbd.nzbparser as nzbparser
import sabnzbd.nzbstuff
import sabnzbd.getipaddress
import sabnzbd.newsunpack
import sabnzbd.par2file
import sabnzbd.api
import sabnzbd.interface
import sabnzbd.zconfig
import sabnzbd.directunpacker as directunpacker
import sabnzbd.dirscanner
import sabnzbd.urlgrabber
import sabnzbd.nzbqueue
import sabnzbd.postproc
import sabnzbd.downloader
import sabnzbd.decoder
import sabnzbd.assembler
import sabnzbd.rating
import sabnzbd.articlecache
import sabnzbd.bpsmeter
import sabnzbd.scheduler as scheduler
import sabnzbd.notifier as notifier
from sabnzbd.decorators import synchronized
from sabnzbd.constants import (
    DEFAULT_PRIORITY,
    VALID_ARCHIVES,
    REPAIR_REQUEST,
    QUEUE_FILE_NAME,
    QUEUE_VERSION,
    QUEUE_FILE_TMPL,
)
import sabnzbd.utils.ssdp

# Storage for the threads, variables are filled during initialization
ArticleCache: sabnzbd.articlecache.ArticleCache
Rating: sabnzbd.rating.Rating
Assembler: sabnzbd.assembler.Assembler
Decoder: sabnzbd.decoder.Decoder
Downloader: sabnzbd.downloader.Downloader
PostProcessor: sabnzbd.postproc.PostProcessor
NzbQueue: sabnzbd.nzbqueue.NzbQueue
URLGrabber: sabnzbd.urlgrabber.URLGrabber
DirScanner: sabnzbd.dirscanner.DirScanner
BPSMeter: sabnzbd.bpsmeter.BPSMeter
RSSReader: sabnzbd.rss.RSSReader
Scheduler: sabnzbd.scheduler.Scheduler

# Regular constants
START = datetime.datetime.now()
MY_NAME = None
MY_FULLNAME = None
RESTART_ARGS = []
NEW_VERSION = (None, None)
DIR_HOME = None
DIR_LCLDATA = None
DIR_PROG = None
DIR_INTERFACES = None
DIR_LANGUAGE = None
DIR_PID = None

QUEUECOMPLETE = None  # stores the nice name of the action
QUEUECOMPLETEACTION = None  # stores the name of the function to be called
QUEUECOMPLETEARG = None  # stores an extra arguments that need to be passed

DAEMON = None
LINUX_POWER = powersup.HAVE_DBUS

LOGFILE = None
WEBLOGFILE = None
LOGHANDLER = None
GUIHANDLER = None
LOG_ALL = False
AMBI_LOCALHOST = False
WIN_SERVICE = None  # Instance of our Win32 Service Class
BROWSER_URL = None

CERTIFICATE_VALIDATION = True
NO_DOWNLOADING = False  # When essentials are missing (SABYenc/par2/unrar)

WEB_DIR = None
WEB_DIR_CONFIG = None
WIZARD_DIR = None
WEB_COLOR = None
SABSTOP = False
RESTART_REQ = False
PAUSED_ALL = False
TRIGGER_RESTART = False  # To trigger restart for Scheduler, WinService and Mac
WINTRAY = None  # Thread for the Windows SysTray icon
WEBUI_READY = False
EXTERNAL_IPV6 = False
LAST_HISTORY_UPDATE = 1

# Condition used to handle the main loop in SABnzbd.py
SABSTOP_CONDITION = Condition(Lock())

# Performance measure for dashboard
PYSTONE_SCORE = 0
DOWNLOAD_DIR_SPEED = 0
COMPLETE_DIR_SPEED = 0
INTERNET_BANDWIDTH = 0


# Rendering of original command line arguments in Config
CMDLINE = " ".join(['"%s"' % arg for arg in sys.argv])

__INITIALIZED__ = False
__SHUTTING_DOWN__ = False


##############################################################################
# Signal Handler
##############################################################################
def sig_handler(signum=None, frame=None):
    if sabnzbd.WIN32 and signum is not None and DAEMON and signum == 5:
        # Ignore the "logoff" event when running as a Win32 daemon
        return True
    if signum is not None:
        logging.warning(T("Signal %s caught, saving and exiting..."), signum)
        sabnzbd.shutdown_program()


##############################################################################
# Initializing
##############################################################################
INIT_LOCK = Lock()


def get_db_connection(thread_index=0):
    # Create a connection and store it in the current thread
    if not (hasattr(cherrypy.thread_data, "history_db") and cherrypy.thread_data.history_db):
        cherrypy.thread_data.history_db = sabnzbd.database.HistoryDB()
    return cherrypy.thread_data.history_db


@synchronized(INIT_LOCK)
def initialize(pause_downloader=False, clean_up=False, repair=0):
    if sabnzbd.__INITIALIZED__:
        return False

    sabnzbd.__SHUTTING_DOWN__ = False

    # Set global database connection for Web-UI threads
    cherrypy.engine.subscribe("start_thread", get_db_connection)

    # Paused?
    pause_downloader = pause_downloader or cfg.start_paused()

    # Clean-up, if requested
    if clean_up:
        # New admin folder
        filesystem.remove_all(cfg.admin_dir.get_path(), "*.sab")

    # Optionally wait for "incomplete" to become online
    if cfg.wait_for_dfolder():
        wait_for_download_folder()
    else:
        cfg.download_dir.set(cfg.download_dir(), create=True)
    cfg.download_dir.set_create(True)

    # Set access rights for "incomplete" base folder
    filesystem.set_permissions(cfg.download_dir.get_path(), recursive=False)

    # If dirscan_dir cannot be created, set a proper value anyway.
    # Maybe it's a network path that's temporarily missing.
    path = cfg.dirscan_dir.get_path()
    if not os.path.exists(path):
        filesystem.create_real_path(cfg.dirscan_dir.ident(), "", path, False)

    # Set call backs for Config items
    cfg.cache_limit.callback(new_limit)
    cfg.cherryhost.callback(guard_restart)
    cfg.cherryport.callback(guard_restart)
    cfg.web_dir.callback(guard_restart)
    cfg.web_color.callback(guard_restart)
    cfg.username.callback(guard_restart)
    cfg.password.callback(guard_restart)
    cfg.log_dir.callback(guard_restart)
    cfg.https_port.callback(guard_restart)
    cfg.https_cert.callback(guard_restart)
    cfg.https_key.callback(guard_restart)
    cfg.enable_https.callback(guard_restart)
    cfg.top_only.callback(guard_top_only)
    cfg.pause_on_post_processing.callback(guard_pause_on_pp)
    cfg.quota_size.callback(guard_quota_size)
    cfg.quota_day.callback(guard_quota_dp)
    cfg.quota_period.callback(guard_quota_dp)
    cfg.language.callback(guard_language)
    cfg.enable_https_verification.callback(guard_https_ver)
    guard_https_ver()

    check_incomplete_vs_complete()

    # Set language files
    lang.set_locale_info("SABnzbd", DIR_LANGUAGE)
    lang.set_language(cfg.language())
    sabnzbd.api.clear_trans_cache()

    # Set end-of-queue action
    sabnzbd.change_queue_complete_action(cfg.queue_complete(), new=False)

    # Convert auto-sort
    if cfg.auto_sort() == "0":
        cfg.auto_sort.set("")
    elif cfg.auto_sort() == "1":
        cfg.auto_sort.set("avg_age asc")

    # Add hostname to the whitelist
    if not cfg.host_whitelist():
        cfg.host_whitelist.set(socket.gethostname())

    # Do repair if requested
    if check_repair_request():
        repair = 2
        pause_downloader = True

    # Initialize threads
    sabnzbd.ArticleCache = sabnzbd.articlecache.ArticleCache()
    sabnzbd.BPSMeter = sabnzbd.bpsmeter.BPSMeter()
    sabnzbd.NzbQueue = sabnzbd.nzbqueue.NzbQueue()
    sabnzbd.Downloader = sabnzbd.downloader.Downloader(sabnzbd.BPSMeter.read() or pause_downloader)
    sabnzbd.Decoder = sabnzbd.decoder.Decoder()
    sabnzbd.Assembler = sabnzbd.assembler.Assembler()
    sabnzbd.PostProcessor = sabnzbd.postproc.PostProcessor()
    sabnzbd.DirScanner = sabnzbd.dirscanner.DirScanner()
    sabnzbd.Rating = sabnzbd.rating.Rating()
    sabnzbd.URLGrabber = sabnzbd.urlgrabber.URLGrabber()
    sabnzbd.RSSReader = sabnzbd.rss.RSSReader()
    sabnzbd.Scheduler = sabnzbd.scheduler.Scheduler()

    # Run startup tasks
    sabnzbd.NzbQueue.read_queue(repair)
    sabnzbd.Scheduler.analyse(pause_downloader)

    # Set cache limit for new users
    if not cfg.cache_limit():
        cfg.cache_limit.set(misc.get_cache_limit())
    sabnzbd.ArticleCache.new_limit(cfg.cache_limit.get_int())

    logging.info("All processes started")
    sabnzbd.RESTART_REQ = False
    sabnzbd.__INITIALIZED__ = True


@synchronized(INIT_LOCK)
def start():
    if sabnzbd.__INITIALIZED__:
        logging.debug("Starting postprocessor")
        sabnzbd.PostProcessor.start()

        logging.debug("Starting assembler")
        sabnzbd.Assembler.start()

        logging.debug("Starting downloader")
        sabnzbd.Downloader.start()

        logging.debug("Starting decoders")
        sabnzbd.Decoder.start()

        logging.debug("Starting scheduler")
        sabnzbd.Scheduler.start()

        logging.debug("Starting dirscanner")
        sabnzbd.DirScanner.start()

        logging.debug("Starting rating")
        sabnzbd.Rating.start()

        logging.debug("Starting urlgrabber")
        sabnzbd.URLGrabber.start()


@synchronized(INIT_LOCK)
def halt():
    if sabnzbd.__INITIALIZED__:
        logging.info("SABnzbd shutting down...")
        sabnzbd.__SHUTTING_DOWN__ = True

        # Stop the windows tray icon
        if sabnzbd.WINTRAY:
            sabnzbd.WINTRAY.stop()

        # Remove registry information
        if sabnzbd.WIN32:
            del_connection_info()

        sabnzbd.zconfig.remove_server()
        sabnzbd.utils.ssdp.stop_ssdp()

        sabnzbd.directunpacker.abort_all()

        logging.debug("Stopping RSSReader")
        sabnzbd.RSSReader.stop()

        logging.debug("Stopping URLGrabber")
        sabnzbd.URLGrabber.stop()
        try:
            sabnzbd.URLGrabber.join()
        except:
            pass

        logging.debug("Stopping rating")
        sabnzbd.Rating.stop()
        try:
            sabnzbd.Rating.join()
        except:
            pass

        logging.debug("Stopping dirscanner")
        sabnzbd.DirScanner.stop()
        try:
            sabnzbd.DirScanner.join()
        except:
            pass

        logging.debug("Stopping downloader")
        sabnzbd.Downloader.stop()
        try:
            sabnzbd.Downloader.join()
        except:
            pass

        # Decoder handles join gracefully
        logging.debug("Stopping decoders")
        sabnzbd.Decoder.stop()
        sabnzbd.Decoder.join()

        logging.debug("Stopping assembler")
        sabnzbd.Assembler.stop()
        try:
            sabnzbd.Assembler.join()
        except:
            pass

        logging.debug("Stopping postprocessor")
        sabnzbd.PostProcessor.stop()
        try:
            sabnzbd.PostProcessor.join()
        except:
            pass

        # Save State
        try:
            save_state()
        except:
            logging.error(T("Fatal error at saving state"), exc_info=True)

        # The Scheduler cannot be stopped when the stop was scheduled.
        # Since all warm-restarts have been removed, it's not longer
        # needed to stop the scheduler.
        # We must tell the scheduler to deactivate.
        logging.debug("Terminating scheduler")
        sabnzbd.Scheduler.abort()

        logging.info("All processes stopped")

        sabnzbd.__INITIALIZED__ = False


def notify_shutdown_loop():
    """ Trigger the main loop to wake up"""
    with sabnzbd.SABSTOP_CONDITION:
        sabnzbd.SABSTOP_CONDITION.notify()


def shutdown_program():
    """ Stop program after halting and saving """
    if not sabnzbd.SABSTOP:
        logging.info("[%s] Performing SABnzbd shutdown", misc.caller_name())
        sabnzbd.halt()
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True
        notify_shutdown_loop()


def trigger_restart(timeout=None):
    """ Trigger a restart by setting a flag an shutting down CP """
    # Sometimes we need to wait a bit to send good-bye to the browser
    if timeout:
        time.sleep(timeout)

    # Set the flag and wake up the main loop
    sabnzbd.TRIGGER_RESTART = True
    notify_shutdown_loop()


##############################################################################
# Misc Wrappers
##############################################################################
def new_limit():
    """ Callback for article cache changes """
    sabnzbd.ArticleCache.new_limit(cfg.cache_limit.get_int())


def guard_restart():
    """ Callback for config options requiring a restart """
    sabnzbd.RESTART_REQ = True


def guard_top_only():
    """ Callback for change of top_only option """
    sabnzbd.NzbQueue.set_top_only(cfg.top_only())


def guard_pause_on_pp():
    """ Callback for change of pause-download-on-pp """
    if cfg.pause_on_post_processing():
        pass  # Not safe to idle downloader, because we don't know
        # if post-processing is active now
    else:
        sabnzbd.Downloader.resume_from_postproc()


def guard_quota_size():
    """ Callback for change of quota_size """
    sabnzbd.BPSMeter.change_quota()


def guard_quota_dp():
    """ Callback for change of quota_day or quota_period """
    sabnzbd.Scheduler.restart()


def guard_language():
    """ Callback for change of the interface language """
    sabnzbd.lang.set_language(cfg.language())
    sabnzbd.api.clear_trans_cache()


def set_https_verification(value):
    """Set HTTPS-verification state while returning current setting
    False = disable verification
    """
    prev = ssl._create_default_https_context == ssl.create_default_context
    if value:
        ssl._create_default_https_context = ssl.create_default_context
    else:
        ssl._create_default_https_context = ssl._create_unverified_context
    return prev


def guard_https_ver():
    """ Callback for change of https verification """
    set_https_verification(cfg.enable_https_verification())


def add_url(url, pp=None, script=None, cat=None, priority=None, nzbname=None, password=None):
    """ Add NZB based on a URL, attributes optional """
    if "http" not in url:
        return
    if not pp or pp == "-1":
        pp = None
    if script and script.lower() == "default":
        script = None
    if cat and cat.lower() == "default":
        cat = None
    logging.info("Fetching %s", url)

    # Add feed name if it came from RSS
    msg = T("Trying to fetch NZB from %s") % url
    if nzbname:
        msg = "%s - %s" % (nzbname, msg)

    # Generate the placeholder
    future_nzo = sabnzbd.NzbQueue.generate_future(msg, pp, script, cat, url=url, priority=priority, nzbname=nzbname)

    # Set password
    if not future_nzo.password:
        future_nzo.password = password

    # Get it!
    sabnzbd.URLGrabber.add(url, future_nzo)
    return future_nzo.nzo_id


def save_state():
    """ Save all internal bookkeeping to disk """
    config.save_config()
    sabnzbd.ArticleCache.flush_articles()
    sabnzbd.NzbQueue.save()
    sabnzbd.BPSMeter.save()
    sabnzbd.Rating.save()
    sabnzbd.DirScanner.save()
    sabnzbd.PostProcessor.save()
    sabnzbd.RSSReader.save()


def pause_all():
    """ Pause all activities than cause disk access """
    sabnzbd.PAUSED_ALL = True
    sabnzbd.Downloader.pause()
    logging.debug("PAUSED_ALL active")


def unpause_all():
    """ Resume all activities """
    sabnzbd.PAUSED_ALL = False
    sabnzbd.Downloader.resume()
    logging.debug("PAUSED_ALL inactive")


##############################################################################
# NZB Saving Methods
##############################################################################


def backup_exists(filename: str) -> bool:
    """ Return True if backup exists and no_dupes is set """
    path = cfg.nzb_backup_dir.get_path()
    return path and os.path.exists(os.path.join(path, filename + ".gz"))


def backup_nzb(filename: str, data: AnyStr):
    """ Backup NZB file """
    path = cfg.nzb_backup_dir.get_path()
    if path:
        save_compressed(path, filename, data)


def save_compressed(folder: str, filename: str, data: AnyStr):
    """ Save compressed NZB file in folder """
    if filename.endswith(".nzb"):
        filename += ".gz"
    else:
        filename += ".nzb.gz"
    logging.info("Backing up %s", os.path.join(folder, filename))
    try:
        # Have to get around the path being put inside the tgz
        with open(os.path.join(folder, filename), "wb") as tgz_file:
            f = gzip.GzipFile(filename, fileobj=tgz_file, mode="wb")
            f.write(encoding.utob(data))
            f.flush()
            f.close()
    except:
        logging.error(T("Saving %s failed"), os.path.join(folder, filename))
        logging.info("Traceback: ", exc_info=True)


##############################################################################
# Unsynchronized methods
##############################################################################


def add_nzbfile(
    nzbfile,
    pp=None,
    script=None,
    cat=None,
    catdir=None,
    priority=DEFAULT_PRIORITY,
    nzbname=None,
    nzo_info=None,
    url=None,
    keep=None,
    reuse=None,
    password=None,
    nzo_id=None,
):
    """Add file, either a single NZB-file or an archive.
    All other parameters are passed to the NZO-creation.
    """
    if pp == "-1":
        pp = None
    if script and (script.lower() == "default" or not filesystem.is_valid_script(script)):
        script = None
    if cat and cat.lower() == "default":
        cat = None

    if isinstance(nzbfile, str):
        # File coming from queue repair or local file-path
        path = nzbfile
        filename = os.path.basename(path)
        keep_default = True
        if not sabnzbd.WIN32:
            # If windows client sends file to Unix server backslashes may
            # be included, so convert these
            path = path.replace("\\", "/")
        logging.info("Attempting to add %s [%s]", filename, path)
    else:
        # File from file-upload object
        # CherryPy mangles unicode-filenames: https://github.com/cherrypy/cherrypy/issues/1766
        filename = encoding.correct_unknown_encoding(nzbfile.filename)
        logging.info("Attempting to add %s", filename)
        keep_default = False
        try:
            # We have to create a copy, because we can't re-use the CherryPy temp-file
            # Just to be sure we add the extension to detect file type later on
            nzb_temp_file, path = tempfile.mkstemp(suffix=filesystem.get_ext(filename))
            os.write(nzb_temp_file, nzbfile.file.read())
            os.close(nzb_temp_file)
        except OSError:
            logging.error(T("Cannot create temp file for %s"), filename)
            logging.info("Traceback: ", exc_info=True)
            return None

    # Externally defined if we should keep the file?
    if keep is None:
        keep = keep_default

    if filesystem.get_ext(filename) in VALID_ARCHIVES:
        return nzbparser.process_nzb_archive_file(
            filename,
            path=path,
            pp=pp,
            script=script,
            cat=cat,
            catdir=catdir,
            priority=priority,
            nzbname=nzbname,
            keep=keep,
            reuse=reuse,
            nzo_info=nzo_info,
            url=url,
            password=password,
            nzo_id=nzo_id,
        )
    else:
        return nzbparser.process_single_nzb(
            filename,
            path=path,
            pp=pp,
            script=script,
            cat=cat,
            catdir=catdir,
            priority=priority,
            nzbname=nzbname,
            keep=keep,
            reuse=reuse,
            nzo_info=nzo_info,
            url=url,
            password=password,
            nzo_id=nzo_id,
        )


def enable_server(server):
    """ Enable server (scheduler only) """
    try:
        config.get_config("servers", server).enable.set(1)
    except:
        logging.warning(T("Trying to set status of non-existing server %s"), server)
        return
    config.save_config()
    sabnzbd.Downloader.update_server(server, server)


def disable_server(server):
    """ Disable server (scheduler only) """
    try:
        config.get_config("servers", server).enable.set(0)
    except:
        logging.warning(T("Trying to set status of non-existing server %s"), server)
        return
    config.save_config()
    sabnzbd.Downloader.update_server(server, server)


def system_shutdown():
    """ Shutdown system after halting download and saving bookkeeping """
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


def restart_program():
    """ Restart program (used by scheduler) """
    logging.info("Scheduled restart request")
    # Just set the stop flag, because stopping CherryPy from
    # the scheduler is not reliable
    sabnzbd.TRIGGER_RESTART = True


def change_queue_complete_action(action, new=True):
    """Action or script to be performed once the queue has been completed
    Scripts are prefixed with 'script_'
    When "new" is False, check whether non-script actions are acceptable
    """
    _action = None
    _argument = None
    if action.startswith("script_") and filesystem.is_valid_script(action.replace("script_", "", 1)):
        # all scripts are labeled script_xxx
        _action = run_script
        _argument = action.replace("script_", "", 1)
    elif new or cfg.queue_complete_pers():
        if action == "shutdown_pc":
            _action = system_shutdown
        elif action == "hibernate_pc":
            _action = system_hibernate
        elif action == "standby_pc":
            _action = system_standby
        elif action == "shutdown_program":
            _action = shutdown_program
        else:
            action = None
    else:
        action = None

    if new:
        cfg.queue_complete.set(action or "")
        config.save_config()

    # keep the name of the action for matching the current select in queue.tmpl
    sabnzbd.QUEUECOMPLETE = action
    sabnzbd.QUEUECOMPLETEACTION = _action
    sabnzbd.QUEUECOMPLETEARG = _argument


def run_script(script):
    """ Run a user script (queue complete only) """
    script_path = filesystem.make_script_path(script)
    if script_path:
        try:
            script_output = misc.run_command([script_path])
            logging.info("Output of queue-complete script %s: \n%s", script, script_output)
        except:
            logging.info("Failed queue-complete script %s, Traceback: ", script, exc_info=True)


def keep_awake():
    """ If we still have work to do, keep Windows/macOS system awake """
    if KERNEL32 or FOUNDATION:
        if sabnzbd.cfg.keep_awake():
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            if (not sabnzbd.Downloader.is_paused() and not sabnzbd.NzbQueue.is_empty()) or (
                not sabnzbd.PostProcessor.paused and not sabnzbd.PostProcessor.empty()
            ):
                if KERNEL32:
                    # Set ES_SYSTEM_REQUIRED until the next call
                    KERNEL32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                else:
                    sleepless.keep_awake("SABnzbd is busy downloading and/or post-processing")
            else:
                if KERNEL32:
                    # Allow the regular state again
                    KERNEL32.SetThreadExecutionState(ES_CONTINUOUS)
                else:
                    sleepless.allow_sleep()


################################################################################
# Data IO                                                                      #
################################################################################


def get_new_id(prefix, folder, check_list=None):
    """Return unique prefixed admin identifier within folder
    optionally making sure that id is not in the check_list.
    """
    for n in range(100):
        try:
            if not os.path.exists(folder):
                os.makedirs(folder)
            fd, path = tempfile.mkstemp("", "SABnzbd_%s_" % prefix, folder)
            os.close(fd)
            head, tail = os.path.split(path)
            if not check_list or tail not in check_list:
                return tail
        except:
            logging.error(T("Failure in tempfile.mkstemp"))
            logging.info("Traceback: ", exc_info=True)
            break
    # Cannot create unique id, crash the process
    raise IOError


def save_data(data, _id, path, do_pickle=True, silent=False):
    """ Save data to a diskfile """
    if not silent:
        logging.debug("[%s] Saving data for %s in %s", misc.caller_name(), _id, path)
    path = os.path.join(path, _id)

    # We try 3 times, to avoid any dict or access problems
    for t in range(3):
        try:
            with open(path, "wb") as data_file:
                if do_pickle:
                    pickle.dump(data, data_file, protocol=pickle.HIGHEST_PROTOCOL)
                else:
                    data_file.write(data)
            break
        except:
            if silent:
                # This can happen, probably a removed folder
                pass
            elif t == 2:
                logging.error(T("Saving %s failed"), path)
                logging.info("Traceback: ", exc_info=True)
            else:
                # Wait a tiny bit before trying again
                time.sleep(0.1)


def load_data(data_id, path, remove=True, do_pickle=True, silent=False):
    """ Read data from disk file """
    path = os.path.join(path, data_id)

    if not os.path.exists(path):
        logging.info("[%s] %s missing", misc.caller_name(), path)
        return None

    if not silent:
        logging.debug("[%s] Loading data for %s from %s", misc.caller_name(), data_id, path)

    try:
        with open(path, "rb") as data_file:
            if do_pickle:
                try:
                    data = pickle.load(data_file, encoding=sabnzbd.encoding.CODEPAGE)
                except UnicodeDecodeError:
                    # Could be Python 2 data that we can load using old encoding
                    data = pickle.load(data_file, encoding="latin1")
            else:
                data = data_file.read()

        if remove:
            filesystem.remove_file(path)
    except:
        logging.error(T("Loading %s failed"), path)
        logging.info("Traceback: ", exc_info=True)
        return None

    return data


def remove_data(_id: str, path: str):
    """ Remove admin file """
    path = os.path.join(path, _id)
    try:
        if os.path.exists(path):
            filesystem.remove_file(path)
    except:
        logging.debug("Failed to remove %s", path)


def save_admin(data: Any, data_id: str):
    """ Save data in admin folder in specified format """
    logging.debug("[%s] Saving data for %s", misc.caller_name(), data_id)
    save_data(data, data_id, cfg.admin_dir.get_path())


def load_admin(data_id: str, remove=False, silent=False) -> Any:
    """ Read data in admin folder in specified format """
    logging.debug("[%s] Loading data for %s", misc.caller_name(), data_id)
    return load_data(data_id, cfg.admin_dir.get_path(), remove=remove, silent=silent)


def request_repair():
    """ Request a full repair on next restart """
    path = os.path.join(cfg.admin_dir.get_path(), REPAIR_REQUEST)
    try:
        with open(path, "w") as f:
            f.write("\n")
    except:
        pass


def check_repair_request():
    """ Return True if repair request found, remove afterwards """
    path = os.path.join(cfg.admin_dir.get_path(), REPAIR_REQUEST)
    if os.path.exists(path):
        try:
            filesystem.remove_file(path)
        except:
            pass
        return True
    return False


def check_all_tasks():
    """Check every task and restart safe ones, else restart program
    Return True when everything is under control
    """
    if __SHUTTING_DOWN__ or not __INITIALIZED__:
        return True

    # Non-restartable threads, require program restart
    if not sabnzbd.PostProcessor.is_alive():
        logging.info("Restarting because of crashed postprocessor")
        return False
    if not sabnzbd.Downloader.is_alive():
        logging.info("Restarting because of crashed downloader")
        return False
    if not sabnzbd.Decoder.is_alive():
        logging.info("Restarting because of crashed decoder")
        return False
    if not sabnzbd.Assembler.is_alive():
        logging.info("Restarting because of crashed assembler")
        return False

    # Kick the downloader, in case it missed the semaphore
    sabnzbd.Downloader.wakeup()

    # Make sure the right servers are active
    sabnzbd.Downloader.check_timers()

    # Restartable threads
    if not sabnzbd.DirScanner.is_alive():
        logging.info("Restarting crashed dirscanner")
        sabnzbd.DirScanner.__init__()
    if not sabnzbd.URLGrabber.is_alive():
        logging.info("Restarting crashed urlgrabber")
        sabnzbd.URLGrabber.__init__()
    if not sabnzbd.Rating.is_alive():
        logging.info("Restarting crashed rating")
        sabnzbd.Rating.__init__()
    if not sabnzbd.Scheduler.is_alive():
        logging.info("Restarting crashed scheduler")
        sabnzbd.Scheduler.restart()
        sabnzbd.Downloader.unblock_all()

    # Check one-shot pause
    sabnzbd.Scheduler.pause_check()

    # Check (and terminate) idle jobs
    sabnzbd.NzbQueue.stop_idle_jobs()

    return True


def pid_file(pid_path=None, pid_file=None, port=0):
    """ Create or remove pid file """
    if not sabnzbd.WIN32:
        if pid_path and pid_path.startswith("/"):
            sabnzbd.DIR_PID = os.path.join(pid_path, "sabnzbd-%d.pid" % port)
        elif pid_file and pid_file.startswith("/"):
            sabnzbd.DIR_PID = pid_file

    if sabnzbd.DIR_PID:
        try:
            if port:
                with open(sabnzbd.DIR_PID, "w") as f:
                    f.write("%d\n" % os.getpid())
            else:
                filesystem.remove_file(sabnzbd.DIR_PID)
        except:
            logging.warning(T("Cannot access PID file %s"), sabnzbd.DIR_PID)


def check_incomplete_vs_complete():
    """Make sure download_dir and complete_dir are not identical
    or that download_dir is not a subfolder of complete_dir"""
    complete = cfg.complete_dir.get_path()
    if filesystem.same_file(cfg.download_dir.get_path(), complete):
        if filesystem.real_path("X", cfg.download_dir()) == filesystem.long_path(cfg.download_dir()):
            # Abs path, so set download_dir as an abs path inside the complete_dir
            cfg.download_dir.set(os.path.join(complete, "incomplete"))
        else:
            cfg.download_dir.set("incomplete")
        return False
    return True


def wait_for_download_folder():
    """ Wait for download folder to become available """
    while not cfg.download_dir.test_path():
        logging.debug('Waiting for "incomplete" folder')
        time.sleep(2.0)


def test_ipv6():
    """ Check if external IPv6 addresses are reachable """
    if not cfg.selftest_host():
        # User disabled the test, assume active IPv6
        return True
    try:
        info = sabnzbd.getipaddress.addresslookup6(cfg.selftest_host())
    except:
        logging.debug(
            "Test IPv6: Disabling IPv6, because it looks like it's not available. Reason: %s", sys.exc_info()[0]
        )
        return False

    try:
        af, socktype, proto, canonname, sa = info[0]
        with socket.socket(af, socktype, proto) as sock:
            sock.settimeout(2)  # 2 second timeout
            sock.connect(sa[0:2])
        logging.debug("Test IPv6: IPv6 test successful. Enabling IPv6")
        return True
    except socket.error:
        logging.debug("Test IPv6: Cannot reach IPv6 test host. Disabling IPv6")
        return False
    except:
        logging.debug("Test IPv6: Problem during IPv6 connect. Disabling IPv6. Reason: %s", sys.exc_info()[0])
        return False


def test_cert_checking():
    """ Test quality of certificate validation """
    # User disabled the test, assume proper SSL certificates
    if not cfg.selftest_host():
        return True

    # Try a connection to our test-host
    try:
        ctx = ssl.create_default_context()
        base_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_sock = ctx.wrap_socket(base_sock, server_hostname=cfg.selftest_host())
        ssl_sock.settimeout(2.0)
        ssl_sock.connect((cfg.selftest_host(), 443))
        ssl_sock.close()
        return True
    except (socket.gaierror, socket.timeout):
        # Non-SSL related error.
        # We now assume that certificates work instead of forcing
        # lower quality just because some (temporary) internet problem
        logging.info("Could not determine system certificate validation quality due to connection problems")
        return True
    except:
        # Seems something is still wrong
        sabnzbd.set_https_verification(False)
    return False


def history_updated():
    """ To make sure we always have a fresh history """
    sabnzbd.LAST_HISTORY_UPDATE += 1
    # Never go over the limit
    if sabnzbd.LAST_HISTORY_UPDATE + 1 >= sys.maxsize:
        sabnzbd.LAST_HISTORY_UPDATE = 1
