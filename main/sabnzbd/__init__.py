#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#           2008 The ShyPike <shypike@users.sourceforge.net>
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

__version__ = "0.4.0X"
__configversion__ = 18
__queueversion__ = 6
__NAME__ = "sabnzbd"

import os
import logging
import datetime
import tempfile
import cPickle
import zipfile
import re
import random
import glob
from time import sleep

from threading import RLock, Lock, Condition, Thread

from sabnzbd.assembler import Assembler, PostProcessor
from sabnzbd.downloader import Downloader, BPSMeter
from sabnzbd.nzbqueue import NzbQueue, NZBQUEUE_LOCK
from sabnzbd.newzbin import Bookmarks, MSGIDGrabber
from sabnzbd.misc import URLGrabber, DirScanner, real_path, \
                         create_real_path, check_latest_version, from_units, SameFile, decodePassword
from sabnzbd.nzbstuff import NzbObject
from sabnzbd.utils.kronos import ThreadedScheduler
from sabnzbd.rss import RSSQueue
from sabnzbd.articlecache import ArticleCache
from sabnzbd.decorators import *
from sabnzbd.constants import *

START = datetime.datetime.now()

CFG = None

MY_NAME = None
MY_FULLNAME = None
NEW_VERSION = None
VERSION_CHECK = None
REPLACE_SPACES = None
DIR_HOME = None
DIR_APPDATA = None
DIR_LCLDATA = None
DIR_PROG = None
DIR_INTERFACES = None
FAIL_ON_CRC = False
CREATE_GROUP_FOLDERS = False
CREATE_CAT_FOLDERS = False
CREATE_CAT_SUB = False
NEWZBIN_BOOKMARKS = False
NEWZBIN_UNBOOKMARK = False
BOOKMARK_RATE = None
DO_FILE_JOIN = False
DO_UNZIP = False
DO_UNRAR = False
DO_SAVE = False
PAR_CLEANUP = False
AUTOSHUTDOWN = False
AUTOSHUTDOWN_GO = False # Set when downloader queue is empty and autoshutdown enabled
AUTODISCONNECT = False
WAITEXIT = False
SEND_GROUP = False

CLEANUP_LIST = []
IGNORE_SAMPLES = False

UMASK = None
BANDWITH_LIMIT = 0
DEBUG_DELAY = 0
AUTOBROWSER = None
DAEMON = None
CONFIGLOCK = None

USERNAME_NEWZBIN = None
PASSWORD_NEWZBIN = None

CACHE_DIR = None
NZB_BACKUP_DIR = None
DOWNLOAD_DIR = None
DOWNLOAD_FREE = None
COMPLETE_DIR = None
SCRIPT_DIR = None
LOGFILE = None
WEBLOGFILE = None
LOGHANDLER = None
GUIHANDLER = None
AMBI_LOCALHOST = False
SAFE_POSTPROC = False
DIRSCAN_SCRIPT = None

POSTPROCESSOR = None
ASSEMBLER = None
DIRSCANNER = None
MSGIDGRABBER = None
ARTICLECACHE = None
DOWNLOADER = None
NZBQ = None
BPSMETER = None
RSS = None
SCHED = None
BOOKMARKS = None

EMAIL_SERVER = None
EMAIL_TO = None
EMAIL_FROM = None
EMAIL_ACCOUNT = None
EMAIL_PWD = None
EMAIL_ENDJOB = False
EMAIL_FULL = False

URLGRABBERS = []

AUTO_SORT = None

ENABLE_TV_SORTING = False
TV_SORT = None
TV_SORT_SEASONS = True

WEB_COLOR = None
WEB_COLOR2 = None
WEB_DIR = None
WEB_DIR2 = None

__INITIALIZED__ = False

################################################################################
# Decorators                                                                   #
################################################################################
CV = Condition(NZBQUEUE_LOCK)
def synchronized_CV(func):
    def call_func(*params, **kparams):
        CV.acquire()
        try:
            return func(*params, **kparams)
        finally:
            CV.notifyAll()
            CV.release()
    return call_func

################################################################################
# Signal Handler                                                               #
################################################################################
def sig_handler(signum = None, frame = None):
    if type(signum) != type(None) and DAEMON and signum==5:
        # Ignore the "logoff" event when running as a Win32 daemon
        return True
    if type(signum) != type(None):
        logging.warning('[%s] Signal %s caught, saving and exiting...', __NAME__, signum)
    try:
        save_state()
    finally:
        os._exit(0)


################################################################################
# Directory Setup                                                              #
################################################################################
def dir_setup(config, cfg_name, def_loc, def_name):
    try:
        my_dir = config['misc'][cfg_name]
    except:
        logging.info('No %s defined, setting value to "%s"', cfg_name, def_name)
        my_dir = def_name
        config['misc'][cfg_name] = my_dir

    if my_dir:
        (dd, my_dir) = create_real_path(cfg_name, def_loc, my_dir)
        logging.debug("%s: %s", cfg_name, my_dir)
    return my_dir

################################################################################
# Check_setting_int                                                            #
################################################################################
def minimax(val, low, high):
    """ Return value forced within range """
    if val < low:
        return low
    if val > high:
        return high
    return val

################################################################################
# Check_setting_int                                                            #
################################################################################
def check_setting_int(config, cfg_name, item_name, def_val):
    try:
        my_val = int(config[cfg_name][item_name])
    except:
        my_val = def_val
        config[cfg_name][item_name] = my_val
    logging.debug("%s -> %s", item_name, my_val)
    return my_val

################################################################################
# Check_setting_float                                                          #
################################################################################
def check_setting_float(config, cfg_name, item_name, def_val):
    try:
        my_val = float(config[cfg_name][item_name])
    except:
        my_val = def_val
        config[cfg_name][item_name] = my_val

    logging.debug("%s -> %s", item_name, my_val)
    return my_val

################################################################################
# Check_setting_str                                                            #
################################################################################
def check_setting_str(config, cfg_name, item_name, def_val, log = True):
    try:
        my_val= config[cfg_name][item_name]
    except:
        my_val = def_val
        config[cfg_name][item_name] = my_val

    if log:
        logging.debug("%s -> %s", item_name, my_val)
    else:
        logging.debug("%s -> %s", item_name, '******')
    return my_val

################################################################################
# Initializing                                                                 #
################################################################################
INIT_LOCK = Lock()

@synchronized(INIT_LOCK)
def initialize(pause_downloader = False, clean_up = False, force_save= False):
    global __INITIALIZED__, FAIL_ON_CRC, CREATE_GROUP_FOLDERS,  DO_FILE_JOIN, \
           DO_UNZIP, DO_UNRAR, DO_SAVE, PAR_CLEANUP, CLEANUP_LIST, IGNORE_SAMPLES, \
           USERNAME_NEWZBIN, PASSWORD_NEWZBIN, POSTPROCESSOR, ASSEMBLER, \
           DIRSCANNER, MSGIDGRABBER, SCHED, NZBQ, DOWNLOADER, BOOKMARKS, \
           NZB_BACKUP_DIR, DOWNLOAD_DIR, DOWNLOAD_FREE, \
           LOGFILE, WEBLOGFILE, LOGHANDLER, GUIHANDLER, AMBI_LOCALHOST, AUTODISCONNECT, WAITEXIT, \
           SAFE_POSTPROC, DIRSCAN_SCRIPT, \
           COMPLETE_DIR, CACHE_DIR, UMASK, SEND_GROUP, CREATE_CAT_FOLDERS, SCRIPT_DIR, \
           CREATE_CAT_SUB, BPSMETER, BANDWITH_LIMIT, DEBUG_DELAY, AUTOBROWSER, ARTICLECACHE, \
           NEWZBIN_BOOKMARKS, NEWZBIN_UNBOOKMARK, BOOKMARK_RATE, \
           DAEMON, CONFIGLOCK, MY_NAME, MY_FULLNAME, NEW_VERSION, VERSION_CHECK, REPLACE_SPACES, \
           DIR_HOME, DIR_APPDATA, DIR_LCLDATA, DIR_PROG , DIR_INTERFACES, \
           EMAIL_SERVER, EMAIL_TO, EMAIL_FROM, EMAIL_ACCOUNT, EMAIL_PWD, \
           EMAIL_ENDJOB, EMAIL_FULL, TV_SORT, TV_SORT_SEASONS, ENABLE_TV_SORTING, AUTO_SORT, WEB_COLOR, WEB_COLOR2, WEB_DIR, WEB_DIR2

    if __INITIALIZED__:
        return False

    logging.info("Initializing SABnzbd v%s", __version__)

    ###########################
    ## CONFIG Initialization ##
    ###########################

    USERNAME_NEWZBIN = check_setting_str(CFG, 'newzbin', 'username', '')
    PASSWORD_NEWZBIN = decodePassword(check_setting_str(CFG, 'newzbin', 'password', '', False), 'web')

    VERSION_CHECK = bool(check_setting_int(CFG, 'misc', 'check_new_rel', 1))

    REPLACE_SPACES = bool(check_setting_int(CFG, 'misc', 'replace_spaces', 0))

    FAIL_ON_CRC = bool(check_setting_int(CFG, 'misc', 'fail_on_crc', 0))

    CREATE_GROUP_FOLDERS = bool(check_setting_int(CFG, 'misc', 'create_group_folders', 0))

    DO_FILE_JOIN = bool(check_setting_int(CFG, 'misc', 'enable_filejoin', 0))

    DO_UNZIP = bool(check_setting_int(CFG, 'misc', 'enable_unzip', 1))

    DO_UNRAR = bool(check_setting_int(CFG, 'misc', 'enable_unrar', 1))

    DO_SAVE = bool(check_setting_int(CFG, 'misc', 'enable_save', 1))

    AUTODISCONNECT = bool(check_setting_int(CFG, 'misc', 'auto_disconnect', 0))

    PAR_CLEANUP = bool(check_setting_int(CFG, 'misc', 'enable_par_cleanup', 1))

    CONFIGLOCK = bool(check_setting_int(CFG, 'misc', 'config_lock', 0))

    SAFE_POSTPROC = bool(check_setting_int(CFG, 'misc', 'safe_postproc', 0))

    CLEANUP_LIST = check_setting_str(CFG, 'misc', 'cleanup_list', '')
    if type(CLEANUP_LIST) != type([]):
        CLEANUP_LIST = []

    IGNORE_SAMPLES = bool(check_setting_int(CFG, 'misc', 'ignore_samples', 0))

    UMASK = check_setting_str(CFG, 'misc', 'permissions', '')
    try:
        if UMASK:
            int(UMASK, 8)
    except:
        logging.error("Permissions (%s) not correct, use OCTAL notation!", UMASK)

    SEND_GROUP = bool(check_setting_int(CFG, 'misc', 'send_group', 0))

    NEWZBIN_BOOKMARKS = bool(check_setting_int(CFG, 'newzbin', 'bookmarks', 0))

    NEWZBIN_UNBOOKMARK = bool(check_setting_int(CFG, 'newzbin', 'unbookmark', 0))

    BOOKMARK_RATE = check_setting_int(CFG, 'newzbin', 'bookmark_rate', 12)
    BOOKMARK_RATE = minimax(BOOKMARK_RATE, 1, 48)

    CREATE_CAT_FOLDERS = bool(check_setting_int(CFG, 'newzbin', 'create_category_folders', 0))

    logging.debug("CREATE_CAT_FOLDERS -> %s", CREATE_CAT_FOLDERS)

    DOWNLOAD_DIR = dir_setup(CFG, "download_dir", DIR_HOME, DEF_DOWNLOAD_DIR)
    if DOWNLOAD_DIR == "":
        return False

    DOWNLOAD_FREE = check_setting_str(CFG, 'misc', 'download_free', "0")
    DOWNLOAD_FREE = int(from_units(DOWNLOAD_FREE))
    logging.debug("DOWNLOAD_FREE %s", DOWNLOAD_FREE)

    COMPLETE_DIR = dir_setup(CFG, "complete_dir", DIR_HOME, DEF_COMPLETE_DIR)
    if COMPLETE_DIR == "":
        return False

    SCRIPT_DIR = dir_setup(CFG, 'script_dir', DIR_HOME, '')

    NZB_BACKUP_DIR = dir_setup(CFG, "nzb_backup_dir", DIR_LCLDATA, DEF_NZBBACK_DIR)

    if SameFile(DOWNLOAD_DIR, COMPLETE_DIR):
        logging.warning('DOWNLOAD_DIR and COMPLETE_DIR should not be the same!')

    CACHE_DIR = dir_setup(CFG, "cache_dir", DIR_LCLDATA, "cache")
    if CACHE_DIR == "":
        return False
    if clean_up:
        xlist= glob.glob(CACHE_DIR + '/*')
        for x in xlist:
            os.remove(x)

    try:
        defdir = CFG['misc']['dirscan_dir']
    except:
        defdir = DEF_NZB_DIR
    dirscan_dir = dir_setup(CFG, "dirscan_dir", DIR_HOME, defdir)

    dirscan_speed = check_setting_int(CFG, 'misc', 'dirscan_speed', DEF_SCANRATE)

    refresh_rate = check_setting_int(CFG, 'misc', 'refresh_rate', DEF_QRATE)

    rss_rate = check_setting_int(CFG, 'misc', 'rss_rate', 1)
    rss_rate = minimax(rss_rate, 1, 48)

    try:
        servers = CFG['servers']
    except:
        servers = ""
        CFG['servers'] = ''

    for server in servers:
        try:
            temp = servers[server]['ssl']
        except:
            servers[server]['ssl'] = 0
            CFG['servers'][server]['ssl'] = 0

    try:
        BANDWITH_LIMIT = check_setting_int(CFG, 'misc', 'bandwith_limit', 0)
    except:
        #BANDWITH_LIMIT = check_setting_float(CFG, 'misc', 'bandwith_limit', 0.0)
        BANDWITH_LIMIT = 0

    if BANDWITH_LIMIT < 1:
        BANDWITH_LIMIT = 0


    cache_limit = check_setting_str(CFG, 'misc', 'cache_limit', "0")
    cache_limit = int(from_units(cache_limit))
    logging.debug("Actual cache limit = %s", cache_limit)

    EMAIL_SERVER = check_setting_str(CFG, 'misc', 'email_server', '')
    EMAIL_TO     = check_setting_str(CFG, 'misc', 'email_to', '')
    EMAIL_FROM   = check_setting_str(CFG, 'misc', 'email_from', '')
    EMAIL_ACCOUNT= check_setting_str(CFG, 'misc', 'email_account', '')
    EMAIL_PWD    = decodePassword(check_setting_str(CFG, 'misc', 'email_pwd', '', False), 'email')
    EMAIL_ENDJOB = bool(check_setting_int(CFG, 'misc', 'email_endjob', 0))
    EMAIL_FULL   = bool(check_setting_int(CFG, 'misc', 'email_full', 0))

    try:
        schedlines = CFG['misc']['schedlines']
    except:
        CFG['misc']['schedlines'] = []
    schedlines = CFG['misc']['schedlines']

    dirscan_opts = check_setting_int(CFG, 'misc', 'dirscan_opts', 1)
    dirscan_repair, dirscan_unpack, dirscan_delete = pp_to_opts(dirscan_opts)
    DIRSCAN_SCRIPT = check_setting_str(CFG, 'misc', 'dirscan_script', '')
    
    top_only = bool(check_setting_int(CFG, 'misc', 'top_only', 1))

    AUTO_SORT = bool(check_setting_int(CFG, 'misc', 'auto_sort', 0))
    
    ENABLE_TV_SORTING = bool(check_setting_int(CFG, 'misc', 'enable_tv_sorting', 0)) #tv sorting on/off
    logging.debug("ENABLE_TV_SORTING -> %s", ENABLE_TV_SORTING)
    TV_SORT = check_setting_int(CFG, 'misc', 'tv_sort', 0) #tv sort level
    TV_SORT_SEASONS = bool(check_setting_int(CFG, 'misc', 'tv_sort_seasons', 1)) #sort into season folders
    
    WEB_COLOR  = check_setting_str(CFG, 'misc', 'web_color',  '')
    WEB_COLOR2 = check_setting_str(CFG, 'misc', 'web_color2', '')


    ############################
    ## Object initializiation ##
    ############################

    if NEWZBIN_BOOKMARKS:
        BOOKMARKS = Bookmarks(USERNAME_NEWZBIN, PASSWORD_NEWZBIN, dirscan_opts, DIRSCAN_SCRIPT)

    need_rsstask = init_RSS()
    init_SCHED(schedlines, need_rsstask, rss_rate, VERSION_CHECK, BOOKMARKS, BOOKMARK_RATE)

    if ARTICLECACHE:
        ARTICLECACHE.__init__(cache_limit)
    else:
        ARTICLECACHE = ArticleCache(cache_limit)

    if BPSMETER:
        BPSMETER.reset()
    else:
        bytes = load_data(BYTES_FILE_NAME, remove = False, do_pickle = False)
        try:
            bytes = int(bytes)
        except:
            bytes = 0

        BPSMETER = BPSMeter(bytes)

    if NZBQ:
        NZBQ.__init__(AUTO_SORT, top_only)
    else:
        NZBQ = NzbQueue(AUTO_SORT, top_only)

    if POSTPROCESSOR:
        POSTPROCESSOR.__init__(DOWNLOAD_DIR, COMPLETE_DIR, POSTPROCESSOR.queue)
    else:
        POSTPROCESSOR = PostProcessor(DOWNLOAD_DIR, COMPLETE_DIR)
        NZBQ.__init__stage2__()

    if ASSEMBLER:
        ASSEMBLER.__init__(DOWNLOAD_DIR, ASSEMBLER.queue)
    else:
        ASSEMBLER = Assembler(DOWNLOAD_DIR)

    if DOWNLOADER:
        DOWNLOADER.__init__(servers, DOWNLOADER.paused)
    else:
        DOWNLOADER = Downloader(servers)
        if pause_downloader:
            DOWNLOADER.paused = True

    if dirscan_dir:
        DIRSCANNER = DirScanner(dirscan_dir, dirscan_speed, dirscan_repair, dirscan_unpack,
                                dirscan_delete, DIRSCAN_SCRIPT)

    if USERNAME_NEWZBIN:
        MSGIDGRABBER = MSGIDGrabber(USERNAME_NEWZBIN, PASSWORD_NEWZBIN)

    __INITIALIZED__ = True
    return True

@synchronized(INIT_LOCK)
def start():
    if __INITIALIZED__:
        logging.debug('[%s] Starting postprocessor', __NAME__)
        POSTPROCESSOR.start()

        logging.debug('[%s] Starting assembler', __NAME__)
        ASSEMBLER.start()

        logging.debug('[%s] Starting downloader', __NAME__)
        DOWNLOADER.start()

        if SCHED:
            logging.debug('[%s] Starting scheduler', __NAME__)
            SCHED.start()

        if DIRSCANNER:
            logging.debug('[%s] Starting dirscanner', __NAME__)
            DIRSCANNER.start()

        if MSGIDGRABBER:
            logging.debug('[%s] Starting msgidgrabber', __NAME__)
            MSGIDGRABBER.start()

@synchronized(INIT_LOCK)
def halt():
    global __INITIALIZED__, SCHED, DIRSCANNER, RSS, MSGIDGRABBER, BOOKMARKS

    if __INITIALIZED__:
        logging.info('SABnzbd shutting down...')

        ## Stop Optional Objects ##

        if SCHED:
            logging.debug('Stopping scheduler')
            SCHED.stop()
            SCHED = None

        if BOOKMARKS:
            BOOKMARKS.save()
            BOOKMARKS = None

        for grabber in URLGRABBERS:
            logging.debug('Stopping grabber {%s}', grabber)
            try:
                grabber.join()
            except:
                logging.exception('[%s] Joining grabber {%s} failed', __NAME__, grabber)

        if MSGIDGRABBER:
            logging.debug('Stopping msgidgrabber')
            MSGIDGRABBER.stop()
            try:
                MSGIDGRABBER.join()
            except:
                pass
            MSGIDGRABBER = None

        if DIRSCANNER:
            logging.debug('Stopping dirscanner')
            DIRSCANNER.stop()
            try:
                DIRSCANNER.join()
            except:
                pass
            DIRSCANNER = None

        ## Stop Required Objects ##
        logging.debug('Stopping downloader')
        CV.acquire()
        try:
            DOWNLOADER.stop()
        finally:
            CV.notifyAll()
            CV.release()
        try:
            DOWNLOADER.join()
        except:
            pass

        logging.debug('Stopping assembler')
        ASSEMBLER.stop()
        try:
            ASSEMBLER.join()
        except:
            pass

        logging.debug('Stopping postprocessor')
        POSTPROCESSOR.stop()
        try:
            POSTPROCESSOR.join()
        except:
            pass

        ## Save State ##
        save_state()

        __INITIALIZED__ = False

################################################################################
## NZBQ Wrappers                                                              ##
################################################################################
def debug():
    try:
        return NZBQ.debug()
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def move_up_bulk(nzo_id, nzf_ids):
    try:
        NZBQ.move_up_bulk(nzo_id, nzf_ids)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def move_top_bulk(nzo_id, nzf_ids):
    try:
        NZBQ.move_top_bulk(nzo_id, nzf_ids)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def move_down_bulk(nzo_id, nzf_ids):
    try:
        NZBQ.move_down_bulk(nzo_id, nzf_ids)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def move_bottom_bulk(nzo_id, nzf_ids):
    try:
        NZBQ.move_bottom_bulk(nzo_id, nzf_ids)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def remove_nzo(nzo_id, add_to_history = True):
    try:
        NZBQ.remove(nzo_id, add_to_history)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def remove_all_nzo():
    try:
        NZBQ.remove_all()
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def remove_nzf(nzo_id, nzf_id):
    try:
        NZBQ.remove_nzf(nzo_id, nzf_id)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def sort_by_avg_age():
    try:
        NZBQ.sort_by_avg_age()
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def sort_by_name():
    try:
        NZBQ.sort_by_name()
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def change_opts(nzo_id, pp):
    try:
        NZBQ.change_opts(nzo_id, pp)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def change_script(nzo_id, script):
    try:
        NZBQ.change_script(nzo_id, script)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def get_article(host):
    try:
        return NZBQ.get_article(host)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def has_articles():
    try:
        return not NZBQ.is_empty()
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def has_articles_for(server):
    try:
        return NZBQ.has_articles_for(server)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def register_article(article):
    try:
        return NZBQ.register_article(article)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def switch(nzo_id1, nzo_id2):
    try:
        NZBQ.switch(nzo_id1, nzo_id2)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def history_info():
    try:
        return NZBQ.history_info()
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def queue_info(for_cli = False):
    try:
        return NZBQ.queue_info(for_cli = for_cli)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def purge_history(job=None):
    try:
        NZBQ.purge(job)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def cleanup_nzo(nzo):
    try:
        NZBQ.cleanup_nzo(nzo)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

def reset_try_lists(nzf = None, nzo = None):
    try:
        NZBQ.reset_try_lists(nzf, nzo)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

################################################################################
## ARTICLECACHE Wrappers                                                      ##
################################################################################
def cache_info():
    try:
        return ARTICLECACHE.cache_info()
    except:
        logging.exception("[%s] Error accessing ARTICLECACHE?", __NAME__)

def load_article(article):
    try:
        return ARTICLECACHE.load_article(article)
    except:
        logging.exception("[%s] Error accessing ARTICLECACHE?", __NAME__)

def save_article(article, data):
    try:
        return ARTICLECACHE.save_article(article, data)
    except:
        logging.exception("[%s] Error accessing ARTICLECACHE?", __NAME__)

def flush_articles():
    try:
        ARTICLECACHE.flush_articles()
    except:
        logging.exception("[%s] Error accessing ARTICLECACHE?", __NAME__)

def purge_articles(articles):
    try:
        ARTICLECACHE.purge_articles(articles)
    except:
        logging.exception("[%s] Error accessing ARTICLECACHE?", __NAME__)

################################################################################
## Misc Wrappers                                                              ##
################################################################################
def add_msgid(msgid, pp, script=None):
    logging.info('[%s] Fetching msgid %s from v3.newzbin.com',
                 __NAME__, msgid)
    msg = "fetching msgid %s from v3.newzbin.com" % msgid

    repair, unpack, delete = pp_to_opts(pp)

    future_nzo = NZBQ.generate_future(msg, repair, unpack, delete, script)

    MSGIDGRABBER.grab(msgid, future_nzo)


def add_url(url, pp, script=None):
    logging.info('[%s] Fetching %s', __NAME__, url)

    msg = "Trying to fetch .nzb from %s" % url

    repair, unpack, delete = pp_to_opts(pp)

    future_nzo = NZBQ.generate_future(msg, repair, unpack, delete, script)

    # Look for a grabber and reinitialize it
    for urlgrabber in URLGRABBERS:
        if not urlgrabber.isAlive():
            urlgrabber.__init__(url, future_nzo)
            urlgrabber.start()
            return

    urlgrabber = URLGrabber(url, future_nzo)
    urlgrabber.start()

    URLGRABBERS.append(urlgrabber)

def save_state():
    flush_articles()

    try:
        NZBQ.save()
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

    try:
        save_data(str(BPSMETER.get_sum()), BYTES_FILE_NAME, do_pickle = False)
    except:
        logging.exception("[%s] Error accessing BPSMETER?", __NAME__)

    if RSS:
        try:
            RSS.save()
        except:
            logging.exception("[%s] Error accessing RSS?", __NAME__)

    if BOOKMARKS:
        BOOKMARKS.save()


################################################################################
## NZB_LOCK Methods                                                           ##
################################################################################
NZB_LOCK = Lock()

@synchronized(NZB_LOCK)
def backup_nzb(filename, data):
    if NZB_BACKUP_DIR:
        try:
            path = os.path.join(NZB_BACKUP_DIR, filename)
            logging.info("[%s] Saving %s", __NAME__, path)
            _f = open(path, 'w')
            _f.write(data)
            _f.flush()
            _f.close()
        except:
            logging.exception("[%s] Saving %s failed", __NAME__, path)

################################################################################
## CV synchronized (notifys downloader)                                       ##
################################################################################
@synchronized_CV
def add_nzbfile(nzbfile, pp, script=None):
    repair, unpack, delete = pp_to_opts(pp)
    filename = nzbfile.filename

    if os.name != 'nt':
        # If windows client sends file to Unix server backslashed may
        # be included, so convert these
        filename = filename.replace('\\', '/')

    filename = os.path.basename(filename)

    root, ext = os.path.splitext(filename)

    logging.info('[%s] Adding %s', __NAME__, filename)

    if ext.lower() == '.zip':
        f = tempfile.TemporaryFile()
        f.write(nzbfile.value)
        f.flush()
        try:
            zf = zipfile.ZipFile(f)
            for name in zf.namelist():
                data = zf.read(name)
                name = os.path.basename(name)
                if data:
                    try:
                        nzo = NzbObject(name, repair, unpack, delete, script, data)
                    except:
                        nzo = None
                if nzo:
                    NZBQ.add(nzo)
        finally:
            f.close()
    else:
        try:
            nzo = NzbObject(filename, repair, unpack, delete, script, nzbfile.value)
        except:
            nzo = None
        if nzo:
            NZBQ.add(nzo)

@synchronized_CV
def add_nzo(nzo, position = -1):
    try:
        NZBQ.add(nzo, position)
    except NameError:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

@synchronized_CV
def insert_future_nzo(future_nzo, filename, data, cat_root = None, cat_tail = None):
    try:
        NZBQ.insert_future(future_nzo, filename, data, cat_root, cat_tail)
    except NameError:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

@synchronized_CV
def pause_downloader(save=True):
    try:
        DOWNLOADER.pause()
        if AUTODISCONNECT:
            DOWNLOADER.disconnect()
        if save:
            save_state()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

@synchronized_CV
def resume_downloader():
    try:
        DOWNLOADER.resume()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

@synchronized_CV
def delay_downloader():
    try:
        DOWNLOADER.delay()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

@synchronized_CV
def undelay_downloader():
    try:
        DOWNLOADER.undelay()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

@synchronized_CV
def limit_speed(value):
    try:
        DOWNLOADER.limit_speed(int(value))
        logging.info("[%s] Bandwidth limit set to %s", __NAME__, value)
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)
        


################################################################################
## Unsynchronized methods                                                     ##
################################################################################
def bps():
    try:
        return BPSMETER.bps
    except:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

def reset_bpsmeter():
    try:
        BPSMETER.reset()
    except:
        logging.exception("[%s] Error accessing BPSMETER?", __NAME__)

def update_bytes(bytes):
    try:
        BPSMETER.update(bytes)
    except:
        logging.exception("[%s] Error accessing BPSMETER?", __NAME__)

def get_bytes():
    try:
        return BPSMETER.get_sum()
    except:
        logging.exception("[%s] Error accessing BPSMETER?", __NAME__)
        return 0

def get_bps():
    try:
        return BPSMETER.get_bps()
    except:
        logging.exception("[%s] Error accessing BPSMETER?", __NAME__)
        return 0

def postprocess_nzo(nzo):
    try:
        POSTPROCESSOR.process(nzo)
    except:
        logging.exception("[%s] Error accessing POSTPROCESSOR?", __NAME__)

def assemble_nzf(nzf):
    try:
        ASSEMBLER.process(nzf)
    except:
        logging.exception("[%s] Error accessing ASSEMBLER?", __NAME__)

def disconnect():
    try:
        DOWNLOADER.disconnect()
    except:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

def paused():
    try:
        return DOWNLOADER.paused
    except:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

def delayed():
    try:
        return DOWNLOADER.delayed
    except:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

def getBookmarksNow():
    if BOOKMARKS:
        BOOKMARKS.run()

def getBookmarksList():
    if BOOKMARKS:
        return BOOKMARKS.bookmarksList()

def delete_bookmark(msgid):
    if BOOKMARKS and NEWZBIN_BOOKMARKS and NEWZBIN_UNBOOKMARK:
        BOOKMARKS.del_bookmark(msgid)
        
        
def system_shutdown():
    logging.info("[%s] Performing system shutdown", __NAME__)

    Thread(target=halt).start()

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
        
def shutdown_program():
    logging.info("[%s] Performing sabnzbd shutdown", __NAME__)
    Thread(target=halt).start()
    sleep(2.0)
    os._exit(0)
 
################################################################################
# Data IO                                                                      #
################################################################################
IO_LOCK = RLock()

@synchronized(IO_LOCK)
def get_new_id(prefix):
    try:
        fd, l = tempfile.mkstemp('', 'SABnzbd_%s_' % prefix, CACHE_DIR)
        os.close(fd)
        head, tail = os.path.split(l)
        return tail
    except:
        logging.exception("[%s] Failure in tempfile.mkstemp", __NAME__)

@synchronized(IO_LOCK)
def save_data(data, _id, do_pickle = True, doze= 0):
    path = os.path.join(CACHE_DIR, _id)
    logging.info("[%s] Saving data for %s in %s", __NAME__, _id, path)

    try:
        _f = open(path, 'wb')
        if do_pickle:
            cPickle.dump(data, _f, 2)
        else:
            _f.write(data)
        if doze:
            # Only for debugging decoder overflow
            sleep(doze)
        _f.flush()
        _f.close()
    except:
        logging.exception("[%s] Saving %s failed", __NAME__, path)

@synchronized(IO_LOCK)
def load_data(_id, remove = True, do_pickle = True):
    path = os.path.join(CACHE_DIR, _id)
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
        logging.exception("[%s] Loading %s failed", __NAME__, path)

    return data

@synchronized(IO_LOCK)
def remove_data(_id):
    path = os.path.join(CACHE_DIR, _id)
    try:
        os.remove(path)
        logging.info("[%s] %s removed", __NAME__, path)
    except:
        pass


def pp_to_opts(pp):
    repair, unpack, delete = (False, False, False)
    if pp > 0:
        repair = True
        if pp > 1:
            unpack = True
            if pp > 2:
                delete = True

    return (repair, unpack, delete)

PROPER_FILENAME_MATCHER = re.compile(r"[a-zA-Z0-9\-_\.+\(\)]")
def fix_filename(filename):
    cst = []
    for i in xrange(len(filename)):
        if PROPER_FILENAME_MATCHER.search(filename[i]):
            cst.append(filename[i])
        else:
            cst.append("_")
    filename = ''.join(cst)
    return filename


################################################################################
# SCHED                                                                        #
################################################################################
RSSTASK_MINUTE = random.randint(0, 59)

def init_SCHED(schedlines, need_rsstask = False, rss_rate = 1, need_versioncheck=True, \
               bookmarks=None, bookmark_rate=1):
    global SCHED

    if schedlines or need_rsstask or need_versioncheck:
        SCHED = ThreadedScheduler()

        for schedule in schedlines:
            arguments = []
            argument_list = None
            if schedule.count(' ') > 3:
                m, h, d, action_name, argument_list = schedule.split(' ', 4)
            else:
                m, h, d, action_name = schedule.split(' ', 3)
            if argument_list:
                arguments = argument_list.split()
            m = int(m)
            h = int(h)
            if d == '*':
                d = range(1, 8)
            else:
                d = [int(d)]

            if action_name == 'resume':
                action = resume_downloader
                arguments = []
            elif action_name == 'pause':
                action = pause_downloader
                arguments = []
            elif action_name == 'shutdown':
                action = shutdown_program
                arguments = []
            elif action_name == 'speedlimit':
                action = limit_speed
            else:
                logging.warning("[%s] Unknown action: %s", __NAME__, ACTION)
                
            logging.debug("[%s] scheduling action:%s arguments:%s",__NAME__, action, arguments)

            #(action, taskname, initialdelay, interval, processmethod, actionargs)
            SCHED.addDaytimeTask(action, '', d, None, (h, m),
                                 SCHED.PM_SEQUENTIAL, arguments)

        if need_rsstask:
            d = range(1, 8) # all days of the week
            interval = int((24*60) / rss_rate)
            ran_m = random.randint(0,interval-1)
            for n in range(0, 24*60, interval):
                at = n + ran_m
                h = int(at/60)
                m = at - h*60
                logging.debug("Scheduling RSS task %s %s:%s", d, h, m)
                SCHED.addDaytimeTask(RSS.run, '', d, None, (h, m), SCHED.PM_SEQUENTIAL, [])


        if need_versioncheck:
            # Check for new release, once per week on random time
            m = random.randint(0, 59)
            h = random.randint(0, 23)
            d = (random.randint(1, 7), )

            logging.debug("Scheduling VersionCheck day=%s time=%s:%s", d, h, m)
            SCHED.addDaytimeTask(check_latest_version, '', d, None, (h, m), SCHED.PM_SEQUENTIAL, [])


        if bookmarks:
            d = range(1, 8) # all days of the week
            interval = int((24*60) / bookmark_rate)
            ran_m = random.randint(0,interval-1)
            for n in range(0, 24*60, interval):
                at = n + ran_m
                h = int(at/60)
                m = at - h*60
                logging.debug("Scheduling Bookmark task %s %s:%s", d, h, m)
                SCHED.addDaytimeTask(bookmarks.run, '', d, None, (h, m), SCHED.PM_SEQUENTIAL, [])


################################################################################
# RSS                                                                          #
################################################################################
def init_RSS():
    global RSS

    need_rsstask = False

    if rss.HAVE_FEEDPARSER:
        tup = load_data(RSS_FILE_NAME, remove = False)

        uris = []
        uri_table = {}
        old_entries = {}
        if tup:
            uris, uri_table, old_entries = tup

        RSS = RSSQueue(uris, uri_table, old_entries)
        if uris:
            need_rsstask = True

    return need_rsstask

def add_rss_feed(uri, text_filter, re_filter, unpack_opts, match_multiple):
    if RSS:
        RSS.add_feed(uri, text_filter, re_filter, unpack_opts, match_multiple)

def del_rss_feed(uri_id):
    if RSS:
        RSS.del_feed(uri_id)

def del_rss_filter(uri_id, filter_id):
    if RSS:
        RSS.del_filter(uri_id, filter_id)

def get_rss_info():
    if RSS:
        return RSS.get_info()
