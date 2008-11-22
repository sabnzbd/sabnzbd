#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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
import re
import glob
import gzip
import subprocess
import time
from time import sleep

try:
    import ctypes
    KERNEL32 = ctypes.windll.LoadLibrary("Kernel32.dll")
except:
    KERNEL32 = None

try:
    # Try to import OSX library
    import Foundation
    DARWIN = True
except:
    DARWIN = False

from threading import RLock, Lock, Condition, Thread

from sabnzbd.assembler import Assembler
from sabnzbd.postproc import PostProcessor
from sabnzbd.downloader import Downloader, BPSMeter
from sabnzbd.nzbqueue import NzbQueue, NZBQUEUE_LOCK
import sabnzbd.newzbin as newzbin
from sabnzbd.misc import DirScanner, real_path, \
                         create_real_path, check_latest_version, from_units, SameFile, decodePassword, \
                         ProcessArchiveFile, ProcessSingleFile, save_configfile
from sabnzbd.urlgrabber import URLGrabber
from sabnzbd.nzbstuff import NzbObject
import sabnzbd.scheduler as scheduler
import sabnzbd.rss as rss
from sabnzbd.articlecache import ArticleCache
from sabnzbd.decorators import *
from sabnzbd.constants import *
import sabnzbd.newsunpack
from sabnzbd.codecs import name_fixer


START = datetime.datetime.now()

CFG = None

MY_NAME = None
MY_FULLNAME = None
NEW_VERSION = None
VERSION_CHECK = None
REPLACE_SPACES = None
REPLACE_ILLEGAL = None
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
DO_SAVE = True
AUTODISCONNECT = True
PAR_CLEANUP = False
PAR_OPTION = ''
NO_DUPES = False

QUEUECOMPLETE = None #stores the nice name of the action
QUEUECOMPLETEACTION = None #stores the name of the function to be called
QUEUECOMPLETEARG = None #stores an extra arguments that need to be passed
QUEUECOMPLETEACTION_GO = False # Booleen value whether to run an action or not at the queue end.

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
RSS_RATE = None

USERNAME_NEWZBIN = None
PASSWORD_NEWZBIN = None
USERNAME_MATRIX = None
PASSWORD_MATRIX = None

CACHE_DIR = None
NZB_BACKUP_DIR = None
DOWNLOAD_DIR = None
DOWNLOAD_FREE = None
COMPLETE_DIR = None
SCRIPT_DIR = None
EMAIL_DIR = None
LOGFILE = None
WEBLOGFILE = None
LOGHANDLER = None
GUIHANDLER = None
LOGLEVEL = None
AMBI_LOCALHOST = False
SAFE_POSTPROC = False
DIRSCAN_SCRIPT = None
DIRSCAN_DIR = None
DIRSCAN_PRIORITY = 0

POSTPROCESSOR = None
ASSEMBLER = None
DIRSCANNER = None

ARTICLECACHE = None
DOWNLOADER = None
NZBQ = None
BPSMETER = None

EMAIL_SERVER = None
EMAIL_TO = None
EMAIL_FROM = None
EMAIL_ACCOUNT = None
EMAIL_PWD = None
EMAIL_ENDJOB = 0
EMAIL_FULL = False

URLGRABBER = None

AUTO_SORT = None

WEB_COLOR = None
WEB_COLOR2 = None
WEB_DIR = None
WEB_DIR2 = None
pause_on_post_processing = False
QUICK_CHECK = True
LOGIN_PAGE = None


ENABLE_TV_SORTING = False
TV_SORT_STRING = None

ENABLE_MOVIE_SORTING = False
MOVIE_SORT_STRING = None
MOVIE_SORT_EXTRA = None
MOVIE_EXTRA_FOLDER = False
MOVIE_CATEGORIES = []

ENABLE_DATE_SORTING = False
DATE_SORT_STRING = None
DATE_CATEGORIES = []


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
    if os.name == 'nt' and type(signum) != type(None) and DAEMON and signum==5:
        # Ignore the "logoff" event when running as a Win32 daemon
        return True
    if type(signum) != type(None):
        logging.warning('[%s] Signal %s caught, saving and exiting...', __NAME__, signum)
    try:
        save_state()
    finally:
        os._exit(0)


def CheckSection(sec):
    """ Check if INI section exists, if not create it """
    try:
        CFG[sec]
        return True
    except:
        CFG[sec] = {}
        return False


################################################################################
# Directory Setup                                                              #
################################################################################
def dir_setup(config, cfg_name, def_loc, def_name, umask=None):
    try:
        my_dir = config['misc'][cfg_name]
    except:
        logging.info('No %s defined, setting value to "%s"', cfg_name, def_name)
        my_dir = def_name
        try:
            config['misc'][cfg_name] = my_dir
        except:
            config['misc'] = {}
            config['misc'][cfg_name] = my_dir

    if my_dir:
        (dd, my_dir) = create_real_path(cfg_name, def_loc, my_dir, umask)
        if not dd:
            my_dir = ""
        logging.debug("%s: %s", cfg_name, my_dir)
    return my_dir

################################################################################
# Check_setting_int                                                            #
################################################################################
def minimax(val, low, high):
    """ Return value forced within range """
    try:
        val = int(val)
    except:
        val = 0
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
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
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
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
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
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val

    if log:
        logging.debug("%s -> %s", item_name, my_val)
    else:
        logging.debug("%s -> %s", item_name, '******')
    return my_val

################################################################################
# Initializing                                                                 #
################################################################################
def init_newzbin():
    global USERNAME_NEWZBIN, PASSWORD_NEWZBIN, \
           USERNAME_MATRIX, PASSWORD_MATRIX, \
           NEWZBIN_BOOKMARKS, NEWZBIN_UNBOOKMARK, BOOKMARK_RATE

    USERNAME_NEWZBIN = check_setting_str(CFG, 'newzbin', 'username', '')
    PASSWORD_NEWZBIN = decodePassword(check_setting_str(CFG, 'newzbin', 'password', '', False), 'web')
    NEWZBIN_BOOKMARKS = bool(check_setting_int(CFG, 'newzbin', 'bookmarks', 0))
    NEWZBIN_UNBOOKMARK = bool(check_setting_int(CFG, 'newzbin', 'unbookmark', 0))

    BOOKMARK_RATE = check_setting_int(CFG, 'newzbin', 'bookmark_rate', 60)
    BOOKMARK_RATE = minimax(BOOKMARK_RATE, 15, 24*60)

    USERNAME_MATRIX = check_setting_str(CFG, 'nzbmatrix', 'username', '')
    PASSWORD_MATRIX = decodePassword(check_setting_str(CFG, 'nzbmatrix', 'password', '', False), 'web')


INIT_LOCK = Lock()

@synchronized(INIT_LOCK)
def initialize(pause_downloader = False, clean_up = False, force_save= False, evalSched=False):
    global __INITIALIZED__, FAIL_ON_CRC, CREATE_GROUP_FOLDERS,  DO_FILE_JOIN, AUTODISCONNECT, \
           DO_UNZIP, DO_UNRAR, DO_SAVE, PAR_CLEANUP, PAR_OPTION, NO_DUPES, CLEANUP_LIST, IGNORE_SAMPLES, \
           USERNAME_NEWZBIN, PASSWORD_NEWZBIN, POSTPROCESSOR, ASSEMBLER, \
           USERNAME_MATRIX, PASSWORD_MATRIX, \
           DIRSCANNER, URLGRABBER, NZBQ, DOWNLOADER, \
           NZB_BACKUP_DIR, DOWNLOAD_DIR, DOWNLOAD_FREE, \
           LOGFILE, WEBLOGFILE, LOGHANDLER, GUIHANDLER, LOGLEVEL, AMBI_LOCALHOST, WAITEXIT, \
           SAFE_POSTPROC, DIRSCAN_SCRIPT, DIRSCAN_DIR, DIRSCAN_PP, \
           COMPLETE_DIR, CACHE_DIR, UMASK, SEND_GROUP, CREATE_CAT_FOLDERS, SCRIPT_DIR, EMAIL_DIR, \
           CREATE_CAT_SUB, BPSMETER, BANDWITH_LIMIT, DEBUG_DELAY, AUTOBROWSER, ARTICLECACHE, \
           NEWZBIN_BOOKMARKS, NEWZBIN_UNBOOKMARK, BOOKMARK_RATE, \
           DAEMON, CONFIGLOCK, RSS_RATE, MY_NAME, MY_FULLNAME, NEW_VERSION, VERSION_CHECK, REPLACE_SPACES, REPLACE_ILLEGAL,\
           DIR_HOME, DIR_APPDATA, DIR_LCLDATA, DIR_PROG , DIR_INTERFACES, \
           EMAIL_SERVER, EMAIL_TO, EMAIL_FROM, EMAIL_ACCOUNT, EMAIL_PWD, \
           EMAIL_ENDJOB, EMAIL_FULL, TV_SORT_STRING, ENABLE_TV_SORTING, AUTO_SORT, WEB_COLOR, WEB_COLOR2, \
           WEB_DIR, WEB_DIR2, pause_on_post_processing, DARWIN, QUICK_CHECK, DIRSCAN_PRIORITY, \
           MOVIE_SORT_STRING, ENABLE_MOVIE_SORTING, MOVIE_SORT_EXTRA, ENABLE_DATE_SORTING, DATE_SORT_STRING, \
           MOVIE_EXTRA_FOLDER, MOVIE_CATEGORIES, DATE_CATEGORIES

    if __INITIALIZED__:
        return False

    ###########################
    ## CONFIG Initialization ##
    ###########################

    CheckSection('misc')
    CheckSection('logging')
    CheckSection('newzbin')
    CheckSection('nzbmatrix')
    CheckSection('servers')
    CheckSection('rss')
    catsDefined = CheckSection('categories')

    init_newzbin()

    VERSION_CHECK = bool(check_setting_int(CFG, 'misc', 'check_new_rel', 1))

    REPLACE_SPACES = bool(check_setting_int(CFG, 'misc', 'replace_spaces', 0))
    REPLACE_ILLEGAL = bool(check_setting_int(CFG, 'misc', 'replace_illegal', 1))

    FAIL_ON_CRC = bool(check_setting_int(CFG, 'misc', 'fail_on_crc', 0))

    CREATE_GROUP_FOLDERS = False #bool(check_setting_int(CFG, 'misc', 'create_group_folders', 0))

    DO_FILE_JOIN = bool(check_setting_int(CFG, 'misc', 'enable_filejoin', 0))

    DO_UNZIP = bool(check_setting_int(CFG, 'misc', 'enable_unzip', 1))

    DO_UNRAR = bool(check_setting_int(CFG, 'misc', 'enable_unrar', 1))

    DO_SAVE = True #bool(check_setting_int(CFG, 'misc', 'enable_save', 1))

    AUTODISCONNECT = bool(check_setting_int(CFG, 'misc', 'auto_disconnect', 1))

    PAR_CLEANUP = bool(check_setting_int(CFG, 'misc', 'enable_par_cleanup', 1))

    PAR_OPTION = check_setting_str(CFG, 'misc', 'par_option', '')
    if PAR_OPTION.lower() == 'none':
        PAR_OPTION = ""

    NO_DUPES = bool(check_setting_int(CFG, 'misc', 'no_dupes', 0))
    
    CONFIGLOCK = bool(check_setting_int(CFG, 'misc', 'config_lock', 0))

    SAFE_POSTPROC = bool(check_setting_int(CFG, 'misc', 'safe_postproc', 0))

    pause_on_post_processing = bool(check_setting_int(CFG, 'misc', 'pause_on_post_processing', 0))

    QUICK_CHECK = bool(check_setting_int(CFG, 'misc', 'quick_check', 1))

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

    CREATE_CAT_FOLDERS = False #bool(check_setting_int(CFG, 'newzbin', 'create_category_folders', 0))

    DOWNLOAD_DIR = dir_setup(CFG, "download_dir", DIR_HOME, DEF_DOWNLOAD_DIR)
    if DOWNLOAD_DIR == "":
        # Directory creation failed, retry with default
        CFG['misc']['download_dir'] = DEF_DOWNLOAD_DIR
        DOWNLOAD_DIR = dir_setup(CFG, "download_dir", DIR_HOME, DEF_DOWNLOAD_DIR)
        if DOWNLOAD_DIR == "":
            return False

    if DOWNLOAD_DIR.startswith('\\\\'):
        logging.error('[%s] UNC path "%s" not supported as download directory', __NAME__, DOWNLOAD_DIR)

    DOWNLOAD_FREE = check_setting_str(CFG, 'misc', 'download_free', "0")
    DOWNLOAD_FREE = int(from_units(DOWNLOAD_FREE))
    logging.debug("DOWNLOAD_FREE %s", DOWNLOAD_FREE)

    COMPLETE_DIR = dir_setup(CFG, "complete_dir", DIR_HOME, DEF_COMPLETE_DIR, UMASK)
    if COMPLETE_DIR == "":
        COMPLETE_DIR == DOWNLOAD_DIR

    SCRIPT_DIR = dir_setup(CFG, 'script_dir', DIR_HOME, '')
    
    EMAIL_DIR = dir_setup(CFG, 'email_dir', DIR_HOME, '')
    
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
        CFG['misc']['dirscan_dir'] = ''
        defdir = ''
    if defdir:
        DIRSCAN_DIR = dir_setup(CFG, "dirscan_dir", DIR_HOME, defdir)
        # If dirscan_dir cannot be created, set a proper value anyway.
        # Maybe it's a network path that's temporarily missing.
        if not DIRSCAN_DIR: DIRSCAN_DIR = real_path(DIR_HOME, defdir)
    else:
        DIRSCAN_DIR = ''


    dirscan_speed = check_setting_int(CFG, 'misc', 'dirscan_speed', DEF_SCANRATE)
    dirscan_speed = minimax(dirscan_speed, 1, 3600)

    refresh_rate = check_setting_int(CFG, 'misc', 'refresh_rate', DEF_QRATE)

    RSS_RATE = check_setting_int(CFG, 'misc', 'rss_rate', 60)
    RSS_RATE = minimax(RSS_RATE, 15, 24*60)

    try:
        BANDWITH_LIMIT = check_setting_int(CFG, 'misc', 'bandwith_limit', 0)
    except:
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
    EMAIL_ENDJOB = check_setting_int(CFG, 'misc', 'email_endjob', 0)
    EMAIL_FULL   = bool(check_setting_int(CFG, 'misc', 'email_full', 0))
    
    try:
        dummy = CFG['misc']['schedlines']
    except:
        CFG['misc']['schedlines'] = []

    DIRSCAN_PP = check_setting_int(CFG, 'misc', 'dirscan_opts', 3)
    DIRSCAN_SCRIPT = check_setting_str(CFG, 'misc', 'dirscan_script', '')
    DIRSCAN_PRIORITY = check_setting_int(CFG, 'misc', 'dirscan_priority', 0)

    top_only = bool(check_setting_int(CFG, 'misc', 'top_only', 1))

    AUTO_SORT = bool(check_setting_int(CFG, 'misc', 'auto_sort', 0))

    ENABLE_TV_SORTING = bool(check_setting_int(CFG, 'misc', 'enable_tv_sorting', 0)) #tv sorting on/off
    TV_SORT_STRING = check_setting_str(CFG, 'misc', 'tv_sort_string', '') #tv sort format

    ENABLE_MOVIE_SORTING = bool(check_setting_int(CFG, 'misc', 'enable_movie_sorting', 0))
    MOVIE_SORT_STRING = check_setting_str(CFG, 'misc', 'movie_sort_string', '') 
    MOVIE_SORT_EXTRA = check_setting_str(CFG, 'misc', 'movie_sort_extra', '-cd%1')
    MOVIE_EXTRA_FOLDER = bool(check_setting_int(CFG, 'misc', 'movie_extra_folder', 0))
    MOVIE_CATEGORIES = check_setting_str(CFG, 'misc', 'movie_categories', ['movies'])
    if type(MOVIE_CATEGORIES) != type([]):
        MOVIE_CATEGORIES = []
    
    ENABLE_DATE_SORTING = bool(check_setting_int(CFG, 'misc', 'enable_date_sorting', 0))
    DATE_SORT_STRING = check_setting_str(CFG, 'misc', 'date_sort_string', '')
    DATE_CATEGORIES = check_setting_str(CFG, 'misc', 'date_categories', ['tv'])
    if type(DATE_CATEGORIES) != type([]):
        DATE_CATEGORIES = []
    
    WEB_COLOR  = check_setting_str(CFG, 'misc', 'web_color',  '')
    WEB_COLOR2 = check_setting_str(CFG, 'misc', 'web_color2', '')

    if not catsDefined:
        newzbin.InitCats()

    ############################
    ## Object initializiation ##
    ############################

    newzbin.bookmarks_init()

    need_rsstask = rss.init()
    scheduler.init()

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
        DOWNLOADER.__init__(DOWNLOADER.paused)
    else:
        DOWNLOADER = Downloader()
        if pause_downloader:
            DOWNLOADER.paused = True

    if DIRSCANNER:
        DIRSCANNER.__init__(DIRSCAN_DIR, dirscan_speed)
    elif DIRSCAN_DIR:
        DIRSCANNER = DirScanner(DIRSCAN_DIR, dirscan_speed)

    newzbin.init_grabber()

    if URLGRABBER:
        URLGRABBER.__init__()
    else:
        URLGRABBER = URLGrabber()

    if evalSched:
        scheduler.analyse(pause_downloader)

    logging.info('All processes started')

    __INITIALIZED__ = True
    return True

@synchronized(INIT_LOCK)
def start():
    global __INITIALIZED__, ASSEMBLER, DOWNLOADER, DIRSCANNER, \
           URLGRABBER, DIRSCAN_DIR

    if __INITIALIZED__:
        logging.debug('[%s] Starting postprocessor', __NAME__)
        POSTPROCESSOR.start()

        logging.debug('[%s] Starting assembler', __NAME__)
        ASSEMBLER.start()

        logging.debug('[%s] Starting downloader', __NAME__)
        DOWNLOADER.start()

        scheduler.start()

        if DIRSCANNER and DIRSCAN_DIR:
            logging.debug('[%s] Starting dirscanner', __NAME__)
            DIRSCANNER.start()

        newzbin.start_grabber()

        if URLGRABBER:
            logging.debug('[%s] Starting urlgrabber', __NAME__)
            URLGRABBER.start()

@synchronized(INIT_LOCK)
def halt():
    global __INITIALIZED__, URLGRABBER, DIRSCANNER, \
           DOWNLOADER, ASSEMBLER, POSTPROCESSOR

    if __INITIALIZED__:
        logging.info('SABnzbd shutting down...')

        rss.stop()

        newzbin.bookmarks_save()

        if URLGRABBER:
            logging.debug('Stopping URLGrabber')
            URLGRABBER.stop()
            try:
                URLGRABBER.join()
            except:
                pass

        newzbin.stop_grabber()

        if DIRSCANNER:
            logging.debug('Stopping dirscanner')
            DIRSCANNER.stop()
            try:
                DIRSCANNER.join()
            except:
                pass

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

        ## Stop Optional Objects ##
        #Scheduler is stopped last so it doesn't break when halt() is launched by the scheduler
        scheduler.stop()

        logging.info('All processes stopped')

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

def remove_nzo(nzo_id, add_to_history = True, unload=False):
    try:
        NZBQ.remove(nzo_id, add_to_history, unload)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)
        
def remove_multiple_nzos(nzo_ids, add_to_history = True):
    try:
        NZBQ.remove_multiple(nzo_ids, add_to_history)
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

def sort_by_size():
    try:
        NZBQ.sort_by_size()
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

def change_cat(nzo_id, cat):
    try:
        NZBQ.change_cat(nzo_id, cat)
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
        
def rename_nzo(nzo_id, name):
    try:
        NZBQ.rename(nzo_id, name)
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
        
def remove_multiple_history(jobs=None):
    try:
        NZBQ.remove_multiple_history(jobs)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)
        
def pause_multiple_nzo(jobs):
    try:
        NZBQ.pause_multiple_nzo(jobs)
    except:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)
        
def resume_multiple_nzo(jobs):
    try:
        NZBQ.resume_multiple_nzo(jobs)
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
def add_msgid(msgid, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY):
    global USERNAME_NEWZBIN, PASSWORD_NEWZBIN

    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None


    if USERNAME_NEWZBIN and PASSWORD_NEWZBIN:
        logging.info('[%s] Fetching msgid %s from www.newzbin.com',
                     __NAME__, msgid)
        msg = "fetching msgid %s from www.newzbin.com" % msgid
    
        future_nzo = NZBQ.generate_future(msg, pp, script, cat=cat, url=msgid, priority=priority)
    
        newzbin.grab(msgid, future_nzo)
    else:
        logging.error('[%s] Error Fetching msgid %s from www.newzbin.com - Please make sure your Username and Password are set',
                             __NAME__, msgid)    


def add_url(url, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY):
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None

    if URLGRABBER:
        logging.info('[%s] Fetching %s', __NAME__, url)
        msg = "Trying to fetch NZB from %s" % url
        future_nzo = NZBQ.generate_future(msg, pp, script, cat, url=url, priority=priority)
        URLGRABBER.add(url, future_nzo)


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

    rss.save()

    newzbin.bookmarks_save()

    if DIRSCANNER:
        DIRSCANNER.save()
        
################################################################################
## NZB_LOCK Methods                                                           ##
################################################################################
NZB_LOCK = Lock()

@synchronized(NZB_LOCK)
def backup_nzb(filename, data, no_dupes):
    """ Backup NZB file,
        return True if OK, False if no_dupes and backup already exists
    """
    result = True
    if NZB_BACKUP_DIR:
        backup_name = filename + '.gz'

        # Need to go to the backup folder to
        # prevent the pathname being embedded in the GZ file
        here = os.getcwd()
        os.chdir(NZB_BACKUP_DIR)

        if no_dupes and os.path.exists(backup_name):
            result = False
        else:
            logging.info("[%s] Backing up %s", __NAME__, backup_name)
            try:
                _f = gzip.GzipFile(backup_name, 'wb')
                _f.write(data)
                _f.flush()
                _f.close()
            except:
                logging.error("[%s] Saving %s to %s failed", __NAME__, backup_name, NZB_BACKUP_DIR)

        os.chdir(here)

    return result


################################################################################
## CV synchronized (notifys downloader)                                       ##
################################################################################
@synchronized_CV
def add_nzbfile(nzbfile, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY):
    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None

    filename = name_fixer(nzbfile.filename)

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
        ProcessArchiveFile(filename, path, pp, script, cat, priority)
    else:
        ProcessSingleFile(filename, path, pp, script, cat, priority)


@synchronized_CV
def add_nzo(nzo):
    try:
        NZBQ.add(nzo)
    except NameError:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

@synchronized_CV
def insert_future_nzo(future_nzo, filename, data, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY):
    try:
        NZBQ.insert_future(future_nzo, filename, data, pp=pp, script=script, cat=cat, priority=priority)
    except NameError:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)
        
@synchronized_CV
def set_priority(nzo_id, priority):
    try:
        NZBQ.set_priority(nzo_id, priority)
    except NameError:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)
        
@synchronized_CV
def set_priority_multiple(nzo_ids, priority):
    try:
        NZBQ.set_priority_multiple(nzo_ids, priority)
    except NameError:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)
        
        
@synchronized_CV
def sort_queue(field, reverse=False):
    try:
        NZBQ.sort_queue(field, reverse)
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
def idle_downloader():
    try:
        DOWNLOADER.wait_postproc()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

@synchronized_CV
def unidle_downloader():
    try:
        DOWNLOADER.resume_postproc()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

@synchronized_CV
def limit_speed(value):
    global BANDWITH_LIMIT
    try:
        DOWNLOADER.limit_speed(int(value))
        BANDWITH_LIMIT = int(value)
        logging.info("[%s] Bandwidth limit set to %s", __NAME__, value)
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)



################################################################################
## Unsynchronized methods                                                     ##
################################################################################
def enable_server(server):
    """ Enable server """
    try:
        CFG['servers'][server]['enable'] = 1
    except:
        logging.warning('[%s] Trying to set status of non-existing server %s', __NAME__, server)
        return
    save_configfile(CFG)
    update_server(server, server)

def disable_server(server):
    """ Disable server """
    try:
        CFG['servers'][server]['enable'] = 0
    except:
        logging.warning('[%s] Trying to set status of non-existing server %s', __NAME__, server)
        return
    save_configfile(CFG)
    update_server(server, server)

def change_web_dir(web_dir):
    LOGIN_PAGE.change_web_dir(web_dir)
    
def change_web_dir2(web_dir):
    LOGIN_PAGE.change_web_dir2(web_dir)
    
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

def update_server(oldserver, newserver):
    global DOWNLOADER, CV
    try:
        CV.acquire()
        try:
            DOWNLOADER.init_server(oldserver, newserver)
        finally:
            CV.notifyAll()
            CV.release()
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


def system_shutdown():
    logging.info("[%s] Performing system shutdown", __NAME__)

    Thread(target=halt).start()
    while __INITIALIZED__:
        sleep(1.0)

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

def system_hibernate():
    logging.info("[%s] Performing system hybernation", __NAME__)
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Hibernate")
        os.sleep(10)
    except:
        logging.error("[%s] Failed to hibernate system", __NAME__)

def system_standby():
    logging.info("[%s] Performing system standby", __NAME__)
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Standby")
        os.sleep(10)
    except:
        logging.error("[%s] Failed to standby system", __NAME__)

def shutdown_program():
    logging.info("[%s] Performing sabnzbd shutdown", __NAME__)
    Thread(target=halt).start()
    while __INITIALIZED__:
        sleep(1.0)
    os._exit(0)

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
    command = os.path.join(SCRIPT_DIR, script)
    stup, need_shell, command, creationflags = sabnzbd.newsunpack.build_command(command)
    logging.info('[%s] Spawning external command %s', __NAME__, command)
    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

def keep_awake():
    """ If we still have work to do, keep Windows system awake
    """
    global KERNEL32, NZBQ, POSTPROCESSOR, DOWNLOADER
    if KERNEL32 and (DOWNLOADER and not DOWNLOADER.paused):
        if (POSTPROCESSOR and not POSTPROCESSOR.empty()) or (NZBQ and not NZBQ.is_empty()):
            # set ES_SYSTEM_REQUIRED
            KERNEL32.SetThreadExecutionState(ctypes.c_int(0x00000001))


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
        logging.error("[%s] Failure in tempfile.mkstemp", __NAME__)

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
        logging.error("[%s] Saving %s failed", __NAME__, path)

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
        logging.error("[%s] Loading %s failed", __NAME__, path)

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
