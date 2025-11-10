#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
import ctypes.util
import time
import ssl

import cherrypy
import platform
import concurrent.futures
import sys
from threading import Lock, Condition

##############################################################################
# Determine platform flags
##############################################################################

WINDOWS = MACOS = MACOSARM64 = FOUNDATION = False
KERNEL32 = LIBC = MACOSLIBC = PLATFORM = None

if os.name == "nt":
    WINDOWS = True

    if platform.uname().machine not in ["AMD64", "ARM64"]:
        print("SABnzbd only supports 64-bit Windows")
        sys.exit(1)

    from sabnzbd.utils.apireg import del_connection_info

    try:
        KERNEL32 = ctypes.windll.LoadLibrary("Kernel32.dll")
    except Exception:
        pass
elif os.name == "posix":
    ORG_UMASK = os.umask(18)
    os.umask(ORG_UMASK)

    # See if we have the GNU glibc malloc_trim() memory release function
    try:
        LIBC = ctypes.CDLL("libc.so.6")
        LIBC.malloc_trim(0)  # try the malloc_trim() call, which is a GNU extension
    except Exception:
        # No malloc_trim(), probably because no glibc
        LIBC = None
        pass

    # Parse macOS version numbers
    if platform.system().lower() == "darwin":
        MACOS = True
        MACOSARM64 = platform.uname().machine == "arm64"
        MACOSLIBC = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)  # the MacOS C library
        try:
            import Foundation
            import sabnzbd.utils.sleepless as sleepless

            FOUNDATION = True
        except Exception:
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
import sabnzbd.articlecache
import sabnzbd.bpsmeter
import sabnzbd.scheduler as scheduler
import sabnzbd.notifier as notifier
import sabnzbd.sorting
from sabnzbd.decorators import synchronized
import sabnzbd.utils.ssdp
import sabnzbd.utils.checkdir
import sabnzbd.utils.ssdp


# Storage for the threads, variables are filled during initialization
ArticleCache: sabnzbd.articlecache.ArticleCache
Assembler: sabnzbd.assembler.Assembler
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

DAEMON = None
LINUX_POWER = powersup.HAVE_DBUS

LOGFILE = None
WEBLOGFILE = None
GUIHANDLER = None
LOG_ALL = False
WIN_SERVICE = None  # Instance of our Win32 Service Class
BROWSER_URL = None

NO_DOWNLOADING = False  # When essentials are missing (SABCTools/par2/unrar)

WEB_DIR = None
WEB_DIR_CONFIG = None
WIZARD_DIR = None
WEB_COLOR = None
SABSTOP = False
RESTART_REQ = False
PAUSED_ALL = False
TRIGGER_RESTART = False  # To trigger restart for Scheduler, WinService and Mac
WINTRAY = None  # Thread for the Windows SysTray icon
MACOSTRAY = None  # Thread for the macOS tray icon
WEBUI_READY = False
LAST_HISTORY_UPDATE = 1
RESTORE_DATA = None

# Condition used to handle the main loop in SABnzbd.py
SABSTOP_CONDITION = Condition(Lock())

# General threadpool
THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# Performance measure for dashboard
PYSTONE_SCORE = 0
DOWNLOAD_DIR_SPEED = 0
COMPLETE_DIR_SPEED = 0
INTERNET_BANDWIDTH = 0

# Record of HTTPS config files at startup
CONFIG_BACKUP_HTTPS_OK = []

# Rendering of original command line arguments in Config
CMDLINE = " ".join(['"%s"' % arg for arg in sys.argv])

__INITIALIZED__ = False
__SHUTTING_DOWN__ = False


##############################################################################
# Signal Handler
##############################################################################
def sig_handler(signum=None, frame=None):
    if sabnzbd.WINDOWS and signum is not None and DAEMON and signum == 5:
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

    sys.setswitchinterval(cfg.switchinterval())

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
        filesystem.wait_for_download_folder()

    # Create the folders, now that we waited for them to be available
    cfg.download_dir.set_create(True)
    cfg.download_dir.create_path()
    cfg.complete_dir.set_create(True)
    cfg.complete_dir.create_path()

    # Set call backs for Config items
    from sabnzbd.config_callbacks import ConfigCallbacks

    cfg.cache_limit.callback(lambda: ConfigCallbacks.new_limit(cfg.cache_limit))
    cfg.web_host.callback(ConfigCallbacks.guard_restart)
    cfg.web_port.callback(ConfigCallbacks.guard_restart)
    cfg.web_dir.callback(ConfigCallbacks.guard_restart)
    cfg.web_color.callback(ConfigCallbacks.guard_restart)
    cfg.url_base.callback(trigger_restart)
    cfg.username.callback(ConfigCallbacks.guard_restart)
    cfg.password.callback(ConfigCallbacks.guard_restart)
    cfg.log_dir.callback(ConfigCallbacks.guard_restart)
    cfg.https_port.callback(ConfigCallbacks.guard_restart)
    cfg.https_cert.callback(ConfigCallbacks.guard_restart)
    cfg.https_key.callback(ConfigCallbacks.guard_restart)
    cfg.enable_https.callback(ConfigCallbacks.guard_restart)
    cfg.socks5_proxy_url.callback(ConfigCallbacks.guard_restart)
    cfg.top_only.callback(lambda: ConfigCallbacks.guard_top_only(cfg.top_only))
    cfg.pause_on_post_processing.callback(
        lambda: ConfigCallbacks.guard_pause_on_pp(cfg.pause_on_post_processing)
    )
    cfg.quota_size.callback(ConfigCallbacks.guard_quota_size)
    cfg.quota_day.callback(ConfigCallbacks.guard_quota_dp)
    cfg.quota_period.callback(ConfigCallbacks.guard_quota_dp)
    cfg.language.callback(lambda: ConfigCallbacks.guard_language(cfg.language))
    cfg.enable_https_verification.callback(
        lambda: ConfigCallbacks.guard_https_ver(cfg.enable_https_verification)
    )
    ConfigCallbacks.guard_https_ver(cfg.enable_https_verification)

    # Set language files
    lang.set_locale_info("SABnzbd", DIR_LANGUAGE)
    lang.set_language(cfg.language())
    sabnzbd.api.clear_trans_cache()

    # Set end-of-queue action
    misc.change_queue_complete_action(cfg.queue_complete(), new=False)

    # Do any config conversions
    from sabnzbd.config_migrations import ConfigConverter

    ConfigConverter.run_all_conversions(
        cfg.config_conversion_version,
        cfg.auto_sort,
        cfg.sorters_converted,
        cfg.no_series_dupes,
        cfg.no_smart_dupes,
        cfg.history_retention,
        cfg.host_whitelist,
        cfg.cache_limit,
        cfg.par_option,
    )

    # Do repair if requested
    if misc.check_repair_request():
        repair = 2
        pause_downloader = True

    # Initialize threads
    sabnzbd.ArticleCache = sabnzbd.articlecache.ArticleCache()
    sabnzbd.BPSMeter = sabnzbd.bpsmeter.BPSMeter()
    sabnzbd.NzbQueue = sabnzbd.nzbqueue.NzbQueue()
    sabnzbd.Downloader = sabnzbd.downloader.Downloader(sabnzbd.BPSMeter.read() or pause_downloader)
    sabnzbd.Assembler = sabnzbd.assembler.Assembler()
    sabnzbd.PostProcessor = sabnzbd.postproc.PostProcessor()
    sabnzbd.DirScanner = sabnzbd.dirscanner.DirScanner()
    sabnzbd.URLGrabber = sabnzbd.urlgrabber.URLGrabber()
    sabnzbd.RSSReader = sabnzbd.rss.RSSReader()
    sabnzbd.Scheduler = sabnzbd.scheduler.Scheduler()

    # Run startup tasks
    sabnzbd.NzbQueue.read_queue(repair)
    sabnzbd.Scheduler.analyse(pause_downloader)
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

        logging.debug("Starting scheduler")
        sabnzbd.Scheduler.start()

        logging.debug("Starting dirscanner")
        sabnzbd.DirScanner.start()

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
        if sabnzbd.WINDOWS:
            del_connection_info()

        sabnzbd.zconfig.remove_server()
        sabnzbd.utils.ssdp.stop_ssdp()

        sabnzbd.directunpacker.abort_all()

        sabnzbd.THREAD_POOL.shutdown(wait=False)

        logging.debug("Stopping RSSReader")
        sabnzbd.RSSReader.stop()

        logging.debug("Stopping URLGrabber")
        sabnzbd.URLGrabber.stop()
        try:
            sabnzbd.URLGrabber.join(timeout=3)
        except Exception:
            pass

        logging.debug("Stopping dirscanner")
        sabnzbd.DirScanner.stop()
        try:
            sabnzbd.DirScanner.join(timeout=3)
        except Exception:
            pass

        logging.debug("Stopping downloader")
        sabnzbd.Downloader.stop()
        try:
            sabnzbd.Downloader.join(timeout=3)
        except Exception:
            pass

        logging.debug("Stopping assembler")
        sabnzbd.Assembler.stop()
        try:
            sabnzbd.Assembler.join(timeout=3)
        except Exception:
            pass

        logging.debug("Stopping postprocessor")
        sabnzbd.PostProcessor.stop()
        try:
            sabnzbd.PostProcessor.join(timeout=3)
        except Exception:
            pass

        # Save State
        try:
            save_state()
        except Exception:
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
    """Trigger the main loop to wake up"""
    with sabnzbd.SABSTOP_CONDITION:
        sabnzbd.SABSTOP_CONDITION.notify()


def shutdown_program():
    """Stop program after halting and saving"""
    if not sabnzbd.SABSTOP:
        logging.info("[%s] Performing SABnzbd shutdown", misc.caller_name())
        sabnzbd.halt()
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True
        notify_shutdown_loop()


def trigger_restart(timeout=None):
    """Trigger a restart by setting a flag an shutting down CP"""
    # Sometimes we need to wait a bit to send good-bye to the browser
    if timeout:
        time.sleep(timeout)

    # Set the flag and wake up the main loop
    sabnzbd.TRIGGER_RESTART = True
    notify_shutdown_loop()


def save_state():
    """Save all internal bookkeeping to disk"""
    config.save_config()
    sabnzbd.ArticleCache.flush_articles()
    sabnzbd.NzbQueue.save()
    sabnzbd.BPSMeter.save()
    sabnzbd.DirScanner.save()
    sabnzbd.PostProcessor.save()
    sabnzbd.RSSReader.save()


def delayed_startup_actions():
    """Checks and logging that are not required for main function"""

    # See if we can get version from git when running an unknown revision
    if sabnzbd.__baseline__ == "unknown":
        try:
            sabnzbd.__baseline__ = sabnzbd.misc.run_command(
                ["git", "rev-parse", "--short", "HEAD"], cwd=sabnzbd.DIR_PROG
            ).strip()
        except Exception:
            pass

    logging.info("Commit = %s", sabnzbd.__baseline__)
    logging.info("Python-version = %s", sys.version)
    logging.info("CPU architecture = %s", platform.uname().machine)
    logging.info("Platform = %s", misc.get_platform_description())
    logging.info(
        "JSON-module = %s %s", sabnzbd.api.json.__name__, sabnzbd.api.json.__version__
    )
    logging.info("Preferred encoding = %s", sabnzbd.encoding.CODEPAGE)
    logging.info("SSL version = %s", ssl.OPENSSL_VERSION)

    # On Linux/FreeBSD/Unix "UTF-8" is strongly, strongly advised:
    if (
        not sabnzbd.WINDOWS
        and not sabnzbd.MACOS
        and not ("utf-8" in sabnzbd.encoding.CODEPAGE.lower())
    ):
        misc.helpful_warning(
            T(
                "SABnzbd was started with encoding %s, this should be UTF-8. Expect problems with Unicoded file and directory names in downloads."
            ),
            sabnzbd.encoding.CODEPAGE,
        )

    # Verify umask, we need at least 700
    if not sabnzbd.WINDOWS and sabnzbd.ORG_UMASK > int("077", 8):
        misc.helpful_warning(
            T("Current umask (%o) might deny SABnzbd access to the files and folders it creates."),
            sabnzbd.ORG_UMASK,
        )

    # List the number of certificates available (can take up to 1.5 seconds)
    if cfg.log_level() > 1:
        logging.debug("Available certificates = %s", repr(ssl.create_default_context().cert_store_stats()))

    # First we do a dircheck
    complete_dir = sabnzbd.cfg.complete_dir.get_path()
    if sabnzbd.utils.checkdir.isFAT(complete_dir):
        misc.helpful_warning(
            T("Completed Download Folder %s is on FAT file system, limiting maximum file size to 4GB") % complete_dir
        )
    else:
        logging.debug("Completed Download Folder %s is not on FAT", complete_dir)

    if filesystem.directory_is_writable(sabnzbd.cfg.download_dir.get_path()):
        filesystem.check_filesystem_capabilities(sabnzbd.cfg.download_dir.get_path())
    if filesystem.directory_is_writable(sabnzbd.cfg.complete_dir.get_path()):
        filesystem.check_filesystem_capabilities(sabnzbd.cfg.complete_dir.get_path())

    # Do an extra purge of the history on startup to ensure timely removal on systems that
    # aren't on 24/7 and typically don't benefit from the daily scheduled call at midnight
    database.scheduled_history_purge()

    # Start SSDP and Bonjour if SABnzbd isn't listening on localhost only
    if sabnzbd.cfg.enable_broadcast() and not misc.is_localhost(cfg.web_host()):
        # Try to find a LAN IP address for SSDP/Bonjour
        if misc.is_lan_addr(cfg.web_host()):
            # A specific listening address was configured, use that
            external_host = cfg.web_host()
        else:
            # Fall back to the IPv4 address of the LAN interface
            external_host = sabnzbd.getipaddress.local_ipv4()
        logging.debug("Using %s as host address for Bonjour and SSDP", external_host)

        # Only broadcast to local network addresses. If local ranges have been defined, further
        # restrict broadcasts to those specific ranges in order to avoid broadcasting to the "wrong"
        # private network when the system is connected to multiple such networks (e.g. a corporate
        # VPN in addition to a standard household LAN).
        if misc.is_lan_addr(external_host) and (
            (not sabnzbd.cfg.local_ranges())
            or any(misc.ip_in_subnet(external_host, r) for r in sabnzbd.cfg.local_ranges())
        ):
            # Start Bonjour and SSDP
            sabnzbd.zconfig.set_bonjour(external_host, cfg.web_port())

            # Set URL for browser for external hosts
            ssdp_url = "%s://%s:%s%s" % (
                ("https" if cfg.enable_https() else "http"),
                external_host,
                cfg.web_port(),
                sabnzbd.cfg.url_base(),
            )
            sabnzbd.utils.ssdp.start_ssdp(
                external_host,
                "SABnzbd",
                ssdp_url,
                "SABnzbd %s" % sabnzbd.__version__,
                "SABnzbd Team",
                "https://sabnzbd.org/",
                "SABnzbd %s" % sabnzbd.__version__,
                ssdp_broadcast_interval=sabnzbd.cfg.ssdp_broadcast_interval(),
            )


def check_all_tasks():
    """Check every task and restart safe ones, else restart program
    Return True when everything is under control
    """
    if __SHUTTING_DOWN__ or not __INITIALIZED__:
        return True

    # Non-restartable threads, require program restart
    if not sabnzbd.PostProcessor.is_alive():
        logging.warning(T("Restarting because of crashed postprocessor"))
        return False
    if not sabnzbd.Downloader.is_alive():
        logging.warning(T("Restarting because of crashed downloader"))
        return False
    if not sabnzbd.Assembler.is_alive():
        logging.warning(T("Restarting because of crashed assembler"))
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
    if not sabnzbd.Scheduler.is_alive():
        logging.info("Restarting crashed scheduler")
        sabnzbd.Scheduler.restart()
        sabnzbd.Downloader.unblock_all()

    # Check one-shot pause
    sabnzbd.Scheduler.pause_check()

    # Check (and terminate) idle jobs
    sabnzbd.NzbQueue.stop_idle_jobs()

    # Check that the queue is sorted correctly
    sabnzbd.NzbQueue.update_sort_order()

    return True


def pid_file(pid_path=None, pid_file=None, port=0):
    """Create or remove pid file"""
    if not sabnzbd.WINDOWS:
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
        except Exception:
            logging.warning(T("Cannot access PID file %s"), sabnzbd.DIR_PID)
