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
import sabnzbd.cfg as cfg
from sabnzbd.decorators import *
from sabnzbd.constants import *


START = datetime.datetime.now()

CFG = None

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

WAITEXIT = False

DEBUG_DELAY = 0
DAEMON = None

LOGFILE = None
WEBLOGFILE = None
LOGHANDLER = None
GUIHANDLER = None
LOGLEVEL = None
AMBI_LOCALHOST = False

POSTPROCESSOR = None
ASSEMBLER = None
DIRSCANNER = None

ARTICLECACHE = None
DOWNLOADER = None
NZBQ = None
BPSMETER = None

URLGRABBER = None

WEB_DIR = None
WEB_DIR2 = None
WEB_COLOR = None
WEB_COLOR2 = None
LOGIN_PAGE = None
SABSTOP = False

SSL_CA = ''
SSL_KEY = ''

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
        (dd, my_dir) = misc.create_real_path(cfg_name, def_loc, my_dir, umask)
        if not dd:
            my_dir = ""
        logging.debug("%s: %s", cfg_name, my_dir)
    return my_dir

################################################################################
# Check_setting_file                                                           #
################################################################################
def check_setting_file(config, cfg_name, def_loc):
    try:
        file = config['misc'][cfg_name]
    except:
        config['misc'][cfg_name] = file = ''

    if file:
        file = misc.real_path(def_loc, file)
        if not os.path.exists(file):
            file = ''
    return file

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

INIT_LOCK = Lock()

@synchronized(INIT_LOCK)
def initialize(pause_downloader = False, clean_up = False, force_save= False, evalSched=False):
    global __INITIALIZED__, \
           POSTPROCESSOR, ASSEMBLER, \
           DIRSCANNER, URLGRABBER, NZBQ, DOWNLOADER, \
           LOGFILE, WEBLOGFILE, LOGHANDLER, GUIHANDLER, LOGLEVEL, AMBI_LOCALHOST, WAITEXIT, \
           BPSMETER, DEBUG_DELAY, ARTICLECACHE, \
           DAEMON, MY_NAME, MY_FULLNAME, NEW_VERSION, \
           DIR_HOME, DIR_APPDATA, DIR_LCLDATA, DIR_PROG , DIR_INTERFACES, \
           DARWIN, \
           SSL_CA, SSL_KEY

    if __INITIALIZED__:
        return False

    ###########################
    ## CONFIG Initialization ##
    ###########################

    CheckSection('misc')
    CheckSection('logging')

    if clean_up:
        xlist= glob.glob(cfg.CACHE_DIR.get_path() + '/*')
        for x in xlist:
            os.remove(x)

    # If dirscan_dir cannot be created, set a proper value anyway.
    # Maybe it's a network path that's temporarily missing.
    path = cfg.DIRSCAN_DIR.get_path()
    if not os.path.exists(path):
        sabnzbd.misc.create_real_path(cfg.DIRSCAN_DIR.ident(), '', path, False)

    SSL_CA = check_setting_file(CFG, 'ssl_ca', DIR_LCLDATA)
    SSL_KEY = check_setting_file(CFG, 'ssl_key', DIR_LCLDATA)

    ############################
    ## Object initializiation ##
    ############################

    newzbin.bookmarks_init()

    need_rsstask = rss.init()
    scheduler.init()

    if ARTICLECACHE:
        ARTICLECACHE.__init__(cfg.CACHE_LIMIT.get_int())
    else:
        ARTICLECACHE = articlecache.ArticleCache(cfg.CACHE_LIMIT.get_int())

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
        NZBQ.__init__()
    else:
        NZBQ = NzbQueue()

    if POSTPROCESSOR:
        POSTPROCESSOR.__init__(POSTPROCESSOR.queue, POSTPROCESSOR.history_queue, restart=True)
    else:
        POSTPROCESSOR = PostProcessor()

    if ASSEMBLER:
        ASSEMBLER.__init__(cfg.DOWNLOAD_DIR.get_path(), ASSEMBLER.queue)
    else:
        ASSEMBLER = Assembler(cfg.DOWNLOAD_DIR.get_path())

    if DOWNLOADER:
        DOWNLOADER.__init__(DOWNLOADER.paused)
    else:
        DOWNLOADER = Downloader()
        if pause_downloader:
            DOWNLOADER.paused = True

    if DIRSCANNER:
        DIRSCANNER.__init__()
    elif cfg.DIRSCAN_DIR.get():
        DIRSCANNER = dirscanner.DirScanner()

    newzbin.init_grabber()

    if URLGRABBER:
        URLGRABBER.__init__()
    else:
        URLGRABBER = urlgrabber.URLGrabber()

    if evalSched:
        scheduler.analyse(pause_downloader)

    logging.info('All processes started')

    __INITIALIZED__ = True
    return True

@synchronized(INIT_LOCK)
def start():
    global __INITIALIZED__, ASSEMBLER, DOWNLOADER, DIRSCANNER, \
           URLGRABBER

    if __INITIALIZED__:
        logging.debug('[%s] Starting postprocessor', __NAME__)
        POSTPROCESSOR.start()

        logging.debug('[%s] Starting assembler', __NAME__)
        ASSEMBLER.start()

        logging.debug('[%s] Starting downloader', __NAME__)
        DOWNLOADER.start()

        scheduler.start()

        if DIRSCANNER and cfg.DIRSCAN_DIR.get():
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

    if pp and pp=="-1": pp = None
    if script and script.lower()=='default': script = None
    if cat and cat.lower()=='default': cat = None


    if cfg.USERNAME_NEWZBIN.get() and cfg.PASSWORD_NEWZBIN.get():
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
    if cfg.NZB_BACKUP_DIR.get_path():
        backup_name = filename + '.gz'

        # Need to go to the backup folder to
        # prevent the pathname being embedded in the GZ file
        here = os.getcwd()
        os.chdir(cfg.NZB_BACKUP_DIR.get_path())

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
                logging.error("[%s] Saving %s to %s failed", __NAME__, backup_name, cfg.NZB_BACKUP_DIR.get_path())

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


@synchronized_CV
def add_nzo(nzo):
    try:
        NZBQ.add(nzo)
    except NameError:
        logging.exception("[%s] Error accessing NZBQ?", __NAME__)

@synchronized_CV
def insert_future_nzo(future_nzo, filename, data, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY, nzo_info={}):
    try:
        NZBQ.insert_future(future_nzo, filename, data, pp=pp, script=script, cat=cat, priority=priority, nzo_info=nzo_info)
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
        if cfg.AUTODISCONNECT.get():
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
    try:
        DOWNLOADER.limit_speed(int(value))
        logging.info("[%s] Bandwidth limit set to %s", __NAME__, value)
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)

def get_limit():
    try:
        return DOWNLOADER.get_limit()
    except NameError:
        logging.exception("[%s] Error accessing DOWNLOADER?", __NAME__)
        return -1



################################################################################
## Unsynchronized methods                                                     ##
################################################################################
def get_history_queue():
    try:
        return POSTPROCESSOR.get_queue()
    except NameError:
        logging.exception("[%s] Error accessing POSTPROCESSOR?", __NAME__)
        
def enable_server(server):
    """ Enable server """
    try:
        config.get_config('servers', server).enable.set(1)
    except:
        logging.warning('[%s] Trying to set status of non-existing server %s', __NAME__, server)
        return
    config.save_config()
    update_server(server, server)

def disable_server(server):
    """ Disable server """
    try:
        config.get_config('servers', server).enable.set(0)
    except:
        logging.warning('[%s] Trying to set status of non-existing server %s', __NAME__, server)
        return
    config.save_config()
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
    command = os.path.join(cfg.SCRIPT_DIR.get_path(), script)
    stup, need_shell, command, creationflags = sabnzbd.newsunpack.build_command(command)
    logging.info('[%s] Spawning external command %s', __NAME__, command)
    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

def empty_queues():
    """ Return True if queues empty or non-existent """
    global NZBQ, POSTPROCESSOR
    if POSTPROCESSOR and NZBQ:
        return POSTPROCESSOR.empty() and NZBQ.is_empty()
    else:
        return True

def keep_awake():
    """ If we still have work to do, keep Windows system awake
    """
    global KERNEL32, NZBQ, POSTPROCESSOR, DOWNLOADER
    if KERNEL32 and (DOWNLOADER and not DOWNLOADER.paused):
        if (POSTPROCESSOR and not POSTPROCESSOR.empty()) or (NZBQ and not NZBQ.is_empty()):
            # set ES_SYSTEM_REQUIRED
            KERNEL32.SetThreadExecutionState(ctypes.c_int(0x00000001))



def CheckFreeSpace():
    if cfg.DOWNLOAD_FREE.get() and not paused():
        if misc.diskfree(cfg.DOWNLOAD_DIR.get_path()) < cfg.DOWNLOAD_FREE.get_float() / GIGI:
            logging.warning('Too little diskspace forcing PAUSE')
            # Pause downloader, but don't save, since the disk is almost full!
            pause_downloader(save=False)
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
def save_data(data, _id, do_pickle = True, doze= 0):
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
            sleep(doze)
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
