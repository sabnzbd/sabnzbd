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

__version__ = "0.2.7"
__configversion__ = 17
__queueversion__ = 5
__NAME__ = "sabnzbd"

import os
import logging
import datetime
import tempfile
import cPickle
import zipfile
import re
import random

from threading import RLock, Lock, Condition, Thread

from sabnzbd.assembler import Assembler, PostProcessor
from sabnzbd.downloader import Downloader, BPSMeter
from sabnzbd.nzbqueue import NzbQueue, NZBQUEUE_LOCK
from sabnzbd.misc import MSGIDGrabber, URLGrabber, DirScanner
from sabnzbd.nzbstuff import NzbObject
from sabnzbd.utils.kronos import ThreadedScheduler
from sabnzbd.rss import RSSQueue
from sabnzbd.articlecache import ArticleCache
from sabnzbd.decorators import *
from sabnzbd.constants import *

import sabnzbd.nzbgrab

START = datetime.datetime.now()

NZB_QUOTA = None

CFG = None

FAIL_ON_CRC = False
CREATE_GROUP_FOLDERS = False
CREATE_CAT_FOLDERS = False
CREATE_CAT_SUB = False
DO_FILE_JOIN = False
DO_UNZIP = False
DO_UNRAR = False
DO_SAVE = False
PAR_CLEANUP = False
AUTOSHUTDOWN = False
SEND_GROUP = False

CLEANUP_LIST = []

UMASK = 0755
BANDWITH_LIMIT = 0.0

USERNAME_NEWZBIN = None
PASSWORD_NEWZBIN = None

CACHE_DIR = None
NZB_BACKUP_DIR = None
DOWNLOAD_DIR = None
DOWNLOAD_FREE = None
COMPLETE_DIR = None

POSTPROCESSOR = None
ASSEMBLER = None
DIRSCANNER = None
ARTICLECACHE = None
DOWNLOADER = None
NZBQ = None
BPSMETER = None
RSS = None
SCHED = None

EMAIL_SERVER = None
EMAIL_TO = None
EMAIL_FROM = None
EMAIL_ACCOUNT = None
EMAIL_PWD = None
EMAIL_ENDJOB = False
EMAIL_FULL = False

URLGRABBERS = []
MSGIDGRABBERS = []

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
    if type(signum) != type(None):
        logging.info('[%s] Signal %s caught, saving and exiting...', __NAME__, 
                     signum)
    try:
        save_state()
    finally:
        os._exit(0)
        
################################################################################
# Initializing                                                                 #
################################################################################
INIT_LOCK = Lock()

@synchronized(INIT_LOCK)
def initialize(pause_downloader = False):
    global __INITIALIZED__, FAIL_ON_CRC, CREATE_GROUP_FOLDERS,  DO_FILE_JOIN, \
           DO_UNZIP, DO_UNRAR, DO_SAVE, PAR_CLEANUP, CLEANUP_LIST, \
           USERNAME_NEWZBIN, PASSWORD_NEWZBIN, POSTPROCESSOR, ASSEMBLER, \
           DIRSCANNER, SCHED, NZBQ, DOWNLOADER, NZB_BACKUP_DIR, DOWNLOAD_DIR, DOWNLOAD_FREE, \
           COMPLETE_DIR, CACHE_DIR, UMASK, SEND_GROUP, CREATE_CAT_FOLDERS, \
           CREATE_CAT_SUB, BPSMETER, BANDWITH_LIMIT, ARTICLECACHE, \
           EMAIL_SERVER, EMAIL_TO, EMAIL_FROM, EMAIL_ACCOUNT, EMAIL_PWD, \
           EMAIL_ENDJOB, EMAIL_FULL
           
    if __INITIALIZED__:
        return False
        
    logging.info("Initializing SABnzbd+ v%s", __version__)
    
    ###########################
    ## CONFIG Initialization ##
    ###########################
    
    USERNAME_NEWZBIN = CFG['newzbin']['username']
    PASSWORD_NEWZBIN = CFG['newzbin']['password']
    
    FAIL_ON_CRC = bool(int(CFG['misc']['fail_on_crc']))
    logging.debug("FAIL_ON_CRC -> %s", FAIL_ON_CRC)
    
    CREATE_GROUP_FOLDERS = bool(int(CFG['misc']['create_group_folders']))
    logging.debug("CREATE_GROUP_FOLDERS -> %s", CREATE_GROUP_FOLDERS)
    
    DO_FILE_JOIN = bool(int(CFG['misc']['enable_filejoin']))
    logging.debug("DO_FILE_JOIN -> %s", DO_FILE_JOIN)
    
    DO_UNZIP = bool(int(CFG['misc']['enable_unzip']))
    logging.debug("DO_UNZIP -> %s", DO_UNZIP)
    
    DO_UNRAR = bool(int(CFG['misc']['enable_unrar']))
    logging.debug("DO_UNRAR -> %s", DO_UNRAR)
    
    DO_SAVE = bool(int(CFG['misc']['enable_save']))
    logging.debug("DO_SAVE -> %s", DO_SAVE)
    
    PAR_CLEANUP = bool(int(CFG['misc']['enable_par_cleanup']))
    logging.debug("PAR_CLEANUP -> %s", PAR_CLEANUP)
    
    CLEANUP_LIST = CFG['misc']['cleanup_list']
    if type(CLEANUP_LIST) != type([]):
        CLEANUP_LIST = []
    logging.debug("CLEANUP_LIST -> %s", CLEANUP_LIST)
    
    UMASK = int(CFG['misc']['umask'], 8)
    logging.debug("UMASK -> %s", UMASK)
    
    SEND_GROUP = bool(int(CFG['misc']['send_group']))
    logging.debug("SEND_GROUP -> %s", SEND_GROUP)
    
    CREATE_CAT_FOLDERS = int(CFG['newzbin']['create_category_folders'])
    
    if CREATE_CAT_FOLDERS > 1:
        CREATE_CAT_SUB = True
    CREATE_CAT_FOLDERS = bool(CREATE_CAT_FOLDERS)
    
    logging.debug("CREATE_CAT_FOLDERS -> %s", CREATE_CAT_FOLDERS)
    logging.debug("CREATE_CAT_SUB -> %s", CREATE_CAT_SUB)
    
    if not CFG['misc']['download_dir']:
        logging.error('No DOWNLOAD_DIR defined!')
        return False
    
    try:
        DOWNLOAD_FREE = int(CFG['misc']['download_free'])
    except:
        logging.error('No DOWNLOAD_FREE defined!')
        DOWNLOAD_FREE = 0
    logging.debug("DOWNLOAD_FREE -> %s", DOWNLOAD_FREE)
    
    DOWNLOAD_DIR = os.path.abspath(CFG['misc']['download_dir'])
    if not os.path.exists(DOWNLOAD_DIR):
        logging.error('Download directory: %s does not exist', DOWNLOAD_DIR)
        return False
    if not os.access(DOWNLOAD_DIR, os.R_OK + os.W_OK):
        logging.error('Download directory: %s error accessing',
                      DOWNLOAD_DIR)
        return False
    logging.info("DOWNLOAD_DIR: %s", DOWNLOAD_DIR)
    
    COMPLETE_DIR = CFG['misc']['complete_dir']
    if COMPLETE_DIR:
        COMPLETE_DIR = os.path.abspath(COMPLETE_DIR)
        if not os.path.exists(COMPLETE_DIR):
            logging.error('Directory: %s does not exist', COMPLETE_DIR)
            return False
        if not os.access(COMPLETE_DIR, os.R_OK + os.W_OK):
            logging.error('Directory: %s error accessing', COMPLETE_DIR)
            return False
    logging.info("COMPLETE_DIR: %s", COMPLETE_DIR)
    
    NZB_BACKUP_DIR = CFG['misc']['nzb_backup_dir']
    if NZB_BACKUP_DIR:
        NZB_BACKUP_DIR = os.path.abspath(NZB_BACKUP_DIR)
        if not os.path.exists(NZB_BACKUP_DIR):
            logging.error('Directory: %s does not exist', NZB_BACKUP_DIR)
            return False
        if not os.access(NZB_BACKUP_DIR, os.R_OK + os.W_OK):
            logging.error('Directory: %s error accessing', NZB_BACKUP_DIR)
            return False
    logging.info("NZB_BACKUP_DIR: %s", NZB_BACKUP_DIR)
    
    if "samefile" in os.path.__dict__:
        if os.path.samefile(DOWNLOAD_DIR, COMPLETE_DIR):
            logging.error('DOWNLOAD_DIR and COMPLETE_DIR cannot be the same!')
            return True
            
    if not CFG['misc']['cache_dir']:
        logging.error('No cache_dir defined!')
        return False
        
    CACHE_DIR = os.path.abspath(CFG['misc']['cache_dir'])
    if not os.path.exists(CACHE_DIR):
        logging.error('Cache directory directory: %s does not exist', CACHE_DIR)
        return False
    if not os.access(CACHE_DIR, os.R_OK + os.W_OK):
        logging.error('Cache directory directory: %s error accessing', CACHE_DIR)
        return False
    logging.info("CACHE_DIR: %s", CACHE_DIR)
    
    dirscan_dir = CFG['misc']['dirscan_dir']
    if dirscan_dir:
        dirscan_dir = os.path.abspath(dirscan_dir)
        if not os.path.exists(dirscan_dir):
            logging.error('Directory: %s does not exist', dirscan_dir)
            return False
        if not os.access(dirscan_dir, os.R_OK + os.W_OK):
            logging.error('Directory: %s error accessing', dirscan_dir)
            return False
    logging.info("dirscan_dir: %s", dirscan_dir)
            
    try:
        dirscan_speed = float(CFG['misc']['dirscan_speed'])
    except:
        CFG['misc']['dirscan_speed'] = "1.0"
        dirscan_speed = 1.0
    logging.info("dirscan_speed: %s", dirscan_speed)

    try:
        refresh_rate = int(CFG['misc']['refresh_rate'])
    except:
        refresh_rate = 0
    logging.info("refresh_rate: %s", refresh_rate)
    if refresh_rate == 0:
        CFG['misc']['refresh_rate'] = ""
 
    try:
    	  rss_rate = int(CFG['misc']['rss_rate'])
    except:
    	  rss_rate = 1
    if rss_rate > 4:
        rss_rate = 4
    if rss_rate < 1:
        rss_rate = 1
    CFG['misc']['rss_rate'] = rss_rate
    logging.info("rss_rate: %s", rss_rate)
    
    extern_proc = CFG['misc']['extern_proc']
    if extern_proc:
        extern_proc= os.path.abspath(extern_proc)
        if os.path.exists(extern_proc):
            logging.info("extern_proc: %s", extern_proc)
        else:
            logging.error('External postproc script: %s does not exist', extern_proc)
            return False

    servers = CFG['servers']
     
    try:
        BANDWITH_LIMIT = float(CFG['misc']['bandwith_limit'])
    except:
        CFG['misc']['bandwith_limit'] = "0.0"
        BANDWITH_LIMIT = 0.0
        
    logging.info("BANDWITH_LIMIT: %s", BANDWITH_LIMIT)
    
    try:
        cache_limit = int(CFG['misc']['cache_limit'])
    except:
        CFG['misc']['cache_limit'] = "0"
        cache_limit = 0

    try:
    	  EMAIL_SERVER = CFG['misc']['email_server']
    except:
    	  EMAIL_SERVER = ""
    logging.info("Email_server: %s", EMAIL_SERVER)
    
    try:
    	  EMAIL_TO = CFG['misc']['email_to']
    except:
    	  EMAIL_TO = ""
    logging.info("Email_to: %s", EMAIL_TO)

    try:
    	  EMAIL_FROM = CFG['misc']['email_from']
    except:
    	  EMAIL_FROM = ""
    logging.info("Email_from: %s", EMAIL_FROM)

    try:
    	  EMAIL_ACCOUNT = CFG['misc']['email_account']
    except:
    	  EMAIL_ACCOUNT = ""
    	  
    try:
    	  EMAIL_PWD = CFG['misc']['email_pwd']
    except:
    	  EMAIL_PWD = ""

    try:
    	  EMAIL_ENDJOB = bool(int(CFG['misc']['email_endjob']))
    except:
    	  EMAIL_ENDJOB = False
    logging.debug("EMAIL_ENDJOB -> %s", EMAIL_ENDJOB)

    try:
    	  EMAIL_FULL = bool(int(CFG['misc']['email_full']))
    except:
    	  EMAIL_FULL = False
    logging.debug("EMAIL_FULL -> %s", EMAIL_FULL)

    if not CFG['misc']['schedlines']:
        CFG['misc']['schedlines'] = []
        
    schedlines = CFG['misc']['schedlines']
    logging.info("schedlines: %s", schedlines)
    
    dirscan_opts = int(CFG['misc']['dirscan_opts'])
    dirscan_repair, dirscan_unpack, dirscan_delete, dirscan_script = pp_to_opts(dirscan_opts)
    logging.info("dirscan_opts: %s", dirscan_opts)
    
    top_only = bool(int(CFG['misc']['top_only']))
    logging.info("top_only: %s", top_only)
    
    auto_sort = bool(int(CFG['misc']['auto_sort']))
    logging.info("auto_sort: %s", auto_sort)
    
    ############################
    ## Object initializiation ##
    ############################
    
    need_rsstask = init_RSS()
    init_SCHED(schedlines, need_rsstask, rss_rate)
    
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
        NZBQ.__init__(auto_sort, top_only)
    else:
        NZBQ = NzbQueue(auto_sort, top_only)
        
    if POSTPROCESSOR:
        POSTPROCESSOR.__init__(DOWNLOAD_DIR, COMPLETE_DIR, extern_proc, POSTPROCESSOR.queue)
    else:
        POSTPROCESSOR = PostProcessor(DOWNLOAD_DIR, COMPLETE_DIR, extern_proc)
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
                                dirscan_delete, dirscan_script)
                                
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

@synchronized(INIT_LOCK)
def halt():
    global __INITIALIZED__, SCHED, DIRSCANNER, RSS
    
    if __INITIALIZED__:
        logging.info('SABnzbd shutting down...')
        
        ## Stop Optional Objects ##
        
        if SCHED:
            logging.debug('Stopping scheduler')
            SCHED.stop()
            SCHED = None
            
        for grabber in URLGRABBERS:
            logging.debug('Stopping grabber {%s}', grabber)
            try:
                grabber.join()
            except:
                logging.exception('[%s] Joining grabber {%s} failed', __NAME__, grabber)
                
        for grabber in MSGIDGRABBERS:
            logging.debug('Stopping grabber {%s}', grabber)
            try:
                grabber.join()
            except:
                logging.exception('[%s] Joining grabber {%s} failed', __NAME__, grabber)
                
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
        
def change_opts(nzo_id, pp):
    try:
        NZBQ.change_opts(nzo_id, pp)
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
        
def purge_history():
    try:
        NZBQ.purge()
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
def add_msgid(msgid, pp):
    logging.info('[%s] Fetching msgid %s from v3.newzbin.com',
                 __NAME__, msgid)
    msg = "fetching msgid %s from v3.newzbin.com" % msgid
    
    repair, unpack, delete, script = pp_to_opts(pp)
    
    future_nzo = NZBQ.generate_future(msg, repair, unpack, delete, script)
    
    # Look for a grabber and reinitialize it
    for grabber in MSGIDGRABBERS:
        if not grabber.isAlive():
            grabber.__init__(USERNAME_NEWZBIN, PASSWORD_NEWZBIN, msgid, future_nzo)
            grabber.start()
            return
            
    grabber = MSGIDGrabber(USERNAME_NEWZBIN, PASSWORD_NEWZBIN, msgid, future_nzo)
    grabber.start()
    
def add_url(url, pp):
    logging.info('[%s] Fetching %s', __NAME__, url)
    
    msg = "Trying to fetch .nzb from %s" % url
    
    repair, unpack, delete, script = pp_to_opts(pp)
    
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
def add_nzbfile(nzbfile, pp):
    repair, unpack, delete, script = pp_to_opts(pp)
    
    filename = os.path.basename(nzbfile.filename)
    
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
                    NZBQ.add(NzbObject(name, repair, unpack, delete, script, data))
        finally:
            f.close()
    else:
        try:
            NZBQ.add(NzbObject(filename, repair, unpack, delete, script, nzbfile.value))
        except NameError:
            logging.exception("[%s] Error accessing NZBQ?", __NAME__)
        
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
def pause_downloader():
    try:
        DOWNLOADER.pause()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)
        
@synchronized_CV
def resume_downloader():
    try:
        DOWNLOADER.resume()
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
def save_data(data, _id, do_pickle = True):
    path = os.path.join(CACHE_DIR, _id)
    logging.info("[%s] Saving data for %s in %s", __NAME__, _id, path)
    
    try:
        _f = open(path, 'wb')
        if do_pickle:
            cPickle.dump(data, _f, 2)
        else:
            _f.write(data)
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
        
################################################################################
# Misc                                                                         #
################################################################################
#def check_for_latest_version():
#    try:
#        import urllib
#        
#        fn = urllib.urlretrieve('http://sabnzbd.sourceforge.net/sa')[0]
#        
#        f = open(fn, 'r')
#        data = f.read()
#        f.close()
#        
#        latest = data.split()[0]
#        
#        return (latest, latest == __version__)
#        
#    except:
#        return None
        
def pp_to_opts(pp):
    repair, unpack, delete, script = (False, False, False, False)
    if pp > 3:
    	  script= True
    	  pp= pp-3

    if pp > 0:
        repair = True
        if pp > 1:
            unpack = True
            if pp > 2:
                delete = True
                	  
    return (repair, unpack, delete, script)
    
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
    
def search_new_server(servers, article):
    article.add_to_try_list(article.fetcher)
    
    new_server_found = False
    fill_server_found = False
    
    for server in self.servers:
        if server not in article.try_list:
            if server.fillserver:
                fill_server_found = True
            else:
                new_server_found = True
                break
                
    # Only found one (or more) fill server(s)
    if not new_server_found and fill_server_found:
        article.allow_fill_server = True
        new_server_found = True
        
    if new_server_found:
        article.fetcher = None
        
        ## Allow all servers to iterate over this nzo and nzf again ##
        nzf.reset_try_list()
        nzo.reset_try_list()
        reset_try_list()
        
        logging.warning('[%s] %s => found at least one untested server',
                        __NAME__, article)
                        
    else:
        logging.warning('[%s] %s => missing from all servers, discarding',
                        __NAME__, article)
                        
################################################################################
# SCHED                                                                        #
################################################################################
RSSTASK_MINUTE = random.randint(0, 59)

def init_SCHED(schedlines, need_rsstask = False, rss_rate = 1):
    global SCHED
    
    if schedlines or need_rsstask:
        SCHED = ThreadedScheduler()
        
        for schedule in schedlines:
            m, h, d, action_name = schedule.split()
            m = int(m)
            h = int(h)
            if d == '*':
                d = range(1, 8)
            else:
                d = [int(d)]
                
            if action_name == 'resume':
                action = resume_downloader
            elif action_name == 'pause':
                action = pause_downloader
            else:
                logging.info("[%s] Unknown action: %s", __NAME__, ACTION) 
                
            SCHED.addDaytimeTask(action, '', d, None, (h, m), 
                                 SCHED.PM_SEQUENTIAL, [])
                                 
        if need_rsstask:
            d = range(1, 8)
            
            ran_m = int(RSSTASK_MINUTE  / rss_rate)
            logging.debug("[%s] RSSTASK_MINUTE: %s", __NAME__, ran_m)
            
            for h in range(24):
            	  for m in range(rss_rate):
                    SCHED.addDaytimeTask(RSS.run, '', d, None, (h, 15*m + ran_m), 
                                         SCHED.PM_SEQUENTIAL, [])
################################################################################
# RSS                                                                          #
################################################################################
def init_RSS():
    global RSS
    
    need_rsstask = False
    
    if sabnzbd.rss.HAVE_FEEDPARSER:
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
