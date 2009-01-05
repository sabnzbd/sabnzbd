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

"""
sabnzbd.nzbqueue - nzb queue
"""

__NAME__ = "nzbqueue"

import sys
import os
import logging
import sabnzbd
import time
import datetime

from threading import Thread, RLock

from sabnzbd.trylist import TryList
from sabnzbd.nzbstuff import NzbObject
from sabnzbd.misc import Panic_Queue, ExitSab, sanitize_filename
from database import HistoryDB
from sabnzbd.decorators import *
from sabnzbd.constants import *
import sabnzbd.cfg as cfg
import sabnzbd.articlecache
import sabnzbd.downloader
import sabnzbd.assembler


def DeleteLog(name):
    if name:
        name = name.replace('.nzb', '.log')
        try:
            os.remove(os.path.join(os.path.dirname(sabnzbd.LOGFILE), name))
        except:
            pass

#-------------------------------------------------------------------------------

class NzbQueue(TryList):
    def __init__(self):
        TryList.__init__(self)

        self.__downloaded_items = []


        self.__top_only = cfg.TOP_ONLY.get()
        self.__top_nzo = None

        self.__nzo_list = []
        self.__nzo_table = {}

        self.__auto_sort = cfg.AUTO_SORT.get()

        nzo_ids = []

        data = sabnzbd.load_data(QUEUE_FILE_NAME, remove = False)

        if data:
            try:
                queue_vers, nzo_ids, self.__downloaded_items = data
                if not queue_vers == QUEUE_VERSION:
                    logging.error("[%s] Incompatible queuefile found, cannot proceed", __NAME__)
                    self.__downloaded_items = []
                    nzo_ids = []
                    Panic_Queue(os.path.join(cfg.CACHE_DIR.get_path(),QUEUE_FILE_NAME))
                    ExitSab(2)
            except ValueError:
                logging.error("[%s] Error loading %s, corrupt file " + \
                              "detected", __NAME__, os.path.join(cfg.CACHE_DIR.get_path(), QUEUE_FILE_NAME))

            for nzo_id in nzo_ids:
                nzo = sabnzbd.load_data(nzo_id, remove = False)
                if nzo:
                    self.add(nzo, save = False)

    @synchronized(NZBQUEUE_LOCK)
    def save(self):
        """ Save queue """
        logging.info("[%s] Saving queue", __NAME__)

        nzo_ids = []
        # Aggregate nzo_ids and save each nzo
        for nzo in self.__nzo_list:
            nzo_ids.append(nzo.nzo_id)
            sabnzbd.save_data(nzo, nzo.nzo_id)

        sabnzbd.save_data((QUEUE_VERSION, nzo_ids,
                           self.__downloaded_items), QUEUE_FILE_NAME)

    @synchronized(NZBQUEUE_LOCK)
    def generate_future(self, msg, pp=None, script=None, cat=None, url=None, priority=NORMAL_PRIORITY):
        """ Create and return a placeholder nzo object """
        future_nzo = NzbObject(msg, pp, 0, script, None, True, cat=cat, url=url, priority=priority, status="Fetching")
        self.add(future_nzo)
        return future_nzo

    @synchronized(NZBQUEUE_LOCK)
    def insert_future(self, future, filename, msgid, data, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY, nzo_info={}):
        """ Refresh a placeholder nzo with an actual nzo """
        nzo_id = future.nzo_id
        if nzo_id in self.__nzo_table:
            try:
                logging.info("[%s] Regenerating item: %s", __NAME__, nzo_id)
                r, u, d = future.get_repair_opts()
                if not r == None:
                    pp = sabnzbd.opts_to_pp(r, u, d)
                scr = future.get_script()
                if scr == None:
                    scr = script
                categ = future.get_cat()
                if categ == None:
                    categ = cat

                try:
                    future.__init__(filename, msgid, pp, scr, nzb=data, futuretype=False, cat=categ, priority=priority, nzo_info=nzo_info)
                    future.nzo_id = nzo_id
                    self.save()
                except ValueError:
                    self.remove(nzo_id, False)
                except TypeError:
                    self.remove(nzo_id, False)

                if self.__auto_sort:
                    self.sort_by_avg_age()

                self.reset_try_list()
            except:
                logging.error("[%s] Error while adding %s, removing", __NAME__, nzo_id)
                logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
                self.remove(nzo_id, False)
        else:
            logging.info("[%s] Item %s no longer in queue, omitting", __NAME__,
                         nzo_id)

    @synchronized(NZBQUEUE_LOCK)
    def change_opts(self, nzo_id, pp):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].set_opts(pp)

    @synchronized(NZBQUEUE_LOCK)
    def change_script(self, nzo_id, script):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].set_script(script)

    @synchronized(NZBQUEUE_LOCK)
    def change_cat(self, nzo_id, cat):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].set_cat(cat)

    @synchronized(NZBQUEUE_LOCK)
    def add(self, nzo, save=True):
        sabnzbd.QUEUECOMPLETEACTION_GO = False

        # Reset try_lists
        nzo.reset_try_list()
        self.reset_try_list()


        if not nzo.nzo_id:
            nzo.nzo_id = sabnzbd.get_new_id('nzo')

        if nzo.nzo_id:
            nzo.deleted = False
            priority = nzo.get_priority()
            self.__nzo_table[nzo.nzo_id] = nzo
            if priority == TOP_PRIORITY:
                #A top priority item (usually a completed download fetching pars)
                #is added to the top of the queue
                self.__nzo_list.insert(0, nzo)
            elif priority == LOW_PRIORITY:
                self.__nzo_list.append(nzo)
            else:
                #for high priority we need to add the item at the bottom 
                #of any other high priority items above the normal priority
                #for normal priority we need to add the item at the bottom 
                #of the normal priority items above the low priority
                if self.__nzo_list:
                    pos = 0
                    added = False
                    for position in self.__nzo_list:
                        if position.get_priority() < priority:
                            self.__nzo_list.insert(pos, nzo)
                            added=True
                            break
                        pos+=1
                    if not added:
                        #if there are no other items classed as a lower priority
                        #then it will be added to the bottom of the queue
                        self.__nzo_list.append(nzo)
                else:
                    #if the queue is empty then simple append the item to the bottom
                    self.__nzo_list.append(nzo)
            if save:
                self.save()

        if self.__auto_sort:
            self.sort_by_avg_age()

    @synchronized(NZBQUEUE_LOCK)
    def remove(self, nzo_id, add_to_history = True, unload=False, save=True, cleanup=True):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table.pop(nzo_id)
            nzo.deleted = True
            self.__nzo_list.remove(nzo)

            if add_to_history:
                # Create the history DB instance
                history_db = HistoryDB(os.path.join(sabnzbd.DIR_LCLDATA, DB_HISTORY_NAME))
                # Add the nzo to the database. Only the path, script and time taken is passed
                # Other information is obtained from the nzo
                history_db.add_history_db(nzo, '', '', 0, '', '')
                history_db.close()
                    
            elif cleanup:
                self.cleanup_nzo(nzo)

            sabnzbd.remove_data(nzo_id)
            if save:
                self.save()
                
        
    @synchronized(NZBQUEUE_LOCK)
    def remove_multiple(self, nzo_ids, add_to_history = True):
        for nzo_id in nzo_ids:
            self.remove(nzo_id, add_to_history = False, save = False)
        self.save()

    @synchronized(NZBQUEUE_LOCK)
    def remove_all(self):
        lst = []
        for nzo_id in self.__nzo_table:
            lst.append(nzo_id)
        for nzo_id in lst:
            nzo = self.__nzo_table.pop(nzo_id)
            nzo.deleted = True
            self.__nzo_list.remove(nzo)
            self.cleanup_nzo(nzo)
            sabnzbd.remove_data(nzo_id)
        del lst
        self.save()

    @synchronized(NZBQUEUE_LOCK)
    def remove_nzf(self, nzo_id, nzf_id):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzf = nzo.get_nzf_by_id(nzf_id)

            if nzf:
                post_done = nzo.remove_nzf(nzf)
                if post_done:
                    self.remove(nzo_id, add_to_history = False)
                    
                    
    @synchronized(NZBQUEUE_LOCK)
    def pause_multiple_nzo(self, nzo_ids):
        for nzo_id in nzo_ids:
            self.pause_nzo(nzo_id)
            
    @synchronized(NZBQUEUE_LOCK)
    def pause_nzo(self, nzo_id):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.pause_nzo()
            logging.debug("[%s] Paused nzo: %s", __NAME__, nzo_id)
            
    @synchronized(NZBQUEUE_LOCK)
    def resume_multiple_nzo(self, nzo_ids):
        for nzo_id in nzo_ids:
            self.resume_nzo(nzo_id)
            
    @synchronized(NZBQUEUE_LOCK)
    def resume_nzo(self, nzo_id):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.resume_nzo()
            logging.debug("[%s] Resumed nzo: %s", __NAME__, nzo_id)

    @synchronized(NZBQUEUE_LOCK)
    def switch(self, item_id_1, item_id_2):
        try:
            # Allow an index as second parameter, easier for some skins
            i = int(item_id_2)
            item_id_2 = self.__nzo_list[i].nzo_id
        except:
            pass
        #get the priorities of the two items
        nzo1 = self.__nzo_table[item_id_1]
        nzo1_priority = nzo1.get_priority()
        nzo2 = self.__nzo_table[item_id_2]
        nzo2_priority = nzo2.get_priority()
        try:
            #get the item id of the item below to use in priority changing
            item_id_3 = self.__nzo_list[i+1].nzo_id
            #if there is an item below the id1 and id2 then we need that too
            #to determine whether to change the priority
            nzo3 = self.__nzo_table[item_id_3]
            nzo3_priority = nzo3.get_priority()
            #if id1 is surrounded by items of a different priority then change it's pririty to match
            if nzo2_priority != nzo1_priority and nzo3_priority != nzo1_priority or nzo2_priority > nzo1_priority:
                nzo1.set_priority(nzo2_priority)
        except:
            nzo1.set_priority(nzo2_priority)
        item_id_pos1 = -1
        item_id_pos2 = -1
        for i in xrange(len(self.__nzo_list)):
            if item_id_1 == self.__nzo_list[i].nzo_id:
                item_id_pos1 = i
            elif item_id_2 == self.__nzo_list[i].nzo_id:
                item_id_pos2 = i
            if (item_id_pos1 > -1) and (item_id_pos2 > -1):
                item = self.__nzo_list[item_id_pos1]
                del self.__nzo_list[item_id_pos1]
                self.__nzo_list.insert(item_id_pos2, item)
                return item_id_pos2
        # If moving failed/no movement took place
        return -1

    @synchronized(NZBQUEUE_LOCK)
    def move_up_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_up_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def move_top_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_top_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def move_down_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_down_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def move_bottom_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_bottom_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_avg_age(self, reverse=False):
        logging.info("[%s] Sorting by average date...(reversed:%s)", __NAME__, reverse)
        self.__nzo_list = sort_queue(self.__nzo_list, _nzo_date_cmp, reverse)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_name(self, reverse=False):
        logging.info("[%s] Sorting by name...(reversed:%s)", __NAME__, reverse)
        self.__nzo_list = sort_queue(self.__nzo_list, _nzo_name_cmp, reverse)
        
    @synchronized(NZBQUEUE_LOCK)
    def sort_by_size(self, reverse=False):
        logging.info("[%s] Sorting by size...(reversed:%s)", __NAME__, reverse)
        self.__nzo_list = sort_queue(self.__nzo_list, _nzo_size_cmp, reverse)
        
    
    @synchronized(NZBQUEUE_LOCK)
    def sort_queue(self, field, reverse=False):
        if field.lower() == 'name':
            self.sort_by_name(reverse)
        elif field.lower() == 'size' or field.lower() == 'bytes':
            self.sort_by_size(reverse)
        elif field.lower() == 'avg_age':
            self.sort_by_avg_age(reverse)
        else:
            logging.debug("[%s] Sort: %s not recognised", __NAME__, field)
        

    @synchronized(NZBQUEUE_LOCK)
    def set_priority(self, nzo_id, priority):
        try:
            priority = int(priority)
            nzo = self.__nzo_table[nzo_id]
            nzo.set_priority(priority)
            nzo_id_pos1 = -1
            pos = -1
            
            for i in xrange(len(self.__nzo_list)):
                if nzo_id == self.__nzo_list[i].nzo_id:
                    nzo_id_pos1 = i
                    break
            if nzo_id_pos1 != -1:
                del self.__nzo_list[nzo_id_pos1]
                if priority == TOP_PRIORITY:
                    #A top priority item (usually a completed download fetching pars)
                    #is added to the top of the queue
                    self.__nzo_list.insert(0, nzo)
                    pos = 0
                elif priority == LOW_PRIORITY:
                    pos = len(self.__nzo_list)
                    self.__nzo_list.append(nzo)
                else:
                    # for high priority we need to add the item at the bottom 
                    #of any other high priority items above the normal priority
                    # for normal priority we need to add the item at the bottom 
                    #of the normal priority items above the low priority
                    if self.__nzo_list:
                        p = 0
                        added = False
                        for position in self.__nzo_list:
                            if position.get_priority() < priority:
                                self.__nzo_list.insert(p, nzo)
                                pos = p
                                added=True
                                break
                            p+=1
                        if not added:
                            #if there are no other items classed as a lower priority
                            #then it will be added to the bottom of the queue
                            pos = len(self.__nzo_list)
                            self.__nzo_list.append(nzo)
                    else:
                        #if the queue is empty then simple append the item to the bottom
                        self.__nzo_list.append(nzo)
                        pos = 0
            return pos
            
        except:
            return -1

    @synchronized(NZBQUEUE_LOCK)
    def set_priority_multiple(self, nzo_ids, priority):
        try:
            for nzo_id in nzo_ids:
                self.set_priority(nzo_id, priority)
        except:
            pass
        
    @synchronized(NZBQUEUE_LOCK)
    def set_original_dirname(self, nzo_id, name):
        try:
            if name:
                nzo = self.__nzo_table[nzo_id]
                name = sanitize_filename(name)
                nzo.set_original_dirname(name)
        except:
            pass
        
    @synchronized(NZBQUEUE_LOCK)
    def reset_try_lists(self, nzf = None, nzo = None):
        nzf.reset_try_list()
        nzo.reset_try_list()
        self.reset_try_list()

    @synchronized(NZBQUEUE_LOCK)
    def has_articles_for(self, server):
        if not self.__nzo_list:
            return False
        elif self.__top_only:
            for nzo in self.__nzo_list:
                if not nzo.get_status() == 'Paused' and not nzo.get_status() == 'Fetching':
                    return not nzo.server_in_try_list(server)
        else:
            return not self.server_in_try_list(server)

    @synchronized(NZBQUEUE_LOCK)
    def get_article(self, server):
        if self.__top_only:
            if self.__nzo_list:
                for nzo in self.__nzo_list:
                    if not nzo.get_status() == 'Paused':
                        article = nzo.get_article(server)
                        if article:
                            return article

        else:
            for nzo in self.__nzo_list:
                # Don't try to get an article if server is in try_list of nzo
                if not nzo.server_in_try_list(server):
                    article = nzo.get_article(server)
                    if article:
                        return article

            # No articles for this server, block server (until reset issued)
            self.add_to_try_list(server)

    @synchronized(NZBQUEUE_LOCK)
    def register_article(self, article):
        nzf = article.nzf
        nzo = nzf.nzo

        if nzo.deleted or nzf.deleted:
            logging.debug("[%s] Discarding article %s, no longer in queue",
                          __NAME__, article.article)
            return

        file_done, post_done, reset = nzo.remove_article(article)

        filename = nzf.get_filename()

        if reset:
            self.reset_try_list()

        if file_done:
            sabnzbd.save_data(nzo, nzo.nzo_id)

            _type = nzf.get_type()

            # Only start decoding if we have a filename and type
            if filename and _type:
                sabnzbd.assembler.process((nzo, nzf))

            else:
                logging.warning('[%s] %s -> Unknown encoding', __NAME__,
                                filename)

        if post_done:
            self.remove(nzo.nzo_id, add_to_history=False, cleanup=False)

            if not self.__nzo_list:
                # Close server connections
                if cfg.AUTODISCONNECT.get():
                    sabnzbd.downloader.disconnect()

                # Sets the end-of-queue back on if disabled
                # adding an nzb and re-adding for more blocks disables it
                if sabnzbd.QUEUECOMPLETEACTION:
                    sabnzbd.QUEUECOMPLETEACTION_GO = True
                    
            # Notify assembler to call postprocessor
            sabnzbd.assembler.process((nzo, None))


    @synchronized(NZBQUEUE_LOCK)
    def queue_info(self, for_cli = False):
        bytes_left = 0
        bytes = 0
        pnfo_list = []
        for nzo in self.__nzo_list:
            pnfo = nzo.gather_info(for_cli = for_cli)

            bytes += pnfo[PNFO_BYTES_FIELD]
            bytes_left += pnfo[PNFO_BYTES_LEFT_FIELD]
            pnfo_list.append(pnfo)

        return (bytes, bytes_left, pnfo_list)

    @synchronized(NZBQUEUE_LOCK)
    def is_empty(self):
        empty = True
        for nzo in self.__nzo_list:
            if not nzo.futuretype:
                empty = False
                break
        return empty
    
    @synchronized(NZBQUEUE_LOCK)
    def cleanup_nzo(self, nzo):
        nzo.purge_data()

        sabnzbd.articlecache.method.purge_articles(nzo.saved_articles)

        for hist_item in self.__downloaded_items:
            # refresh fields & delete nzo reference
            if hist_item.nzo and hist_item.nzo == nzo:
                hist_item.cleanup()
                logging.debug('[%s] %s cleaned up', __NAME__,
                              nzo.get_dirname())

    @synchronized(NZBQUEUE_LOCK)
    def debug(self):
        return (self.__downloaded_items[:], self.__nzo_list[:],
                self.__nzo_table.copy(), self.try_list[:])


    def get_urls(self):
        """ Return list of future-types needing URL """
        lst = []
        for nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            url = nzo.get_future()
            if nzo.futuretype and url.lower().startswith('http'):
                lst.append((url, nzo))
        return lst

    def get_msgids(self):
        """ Return list of future-types needing msgid """
        lst = []
        for nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            msgid = nzo.get_future()
            if nzo.futuretype and (msgid.isdigit() or len(msgid)==5):
                lst.append((msgid, nzo))
        return lst
        
    def __repr__(self):
        return "<NzbQueue>"

#-------------------------------------------------------------------------------

def _nzo_date_cmp(nzo1, nzo2):
    avg_date1 = nzo1.get_avg_date()
    avg_date2 = nzo2.get_avg_date()

    if avg_date1 == None and avg_date2 == None:
        return 0

    if avg_date1 == None:
        avg_date1 = datetime.datetime.now()
    elif avg_date2 == None:
        avg_date2 = datetime.datetime.now()

    return cmp(avg_date1, avg_date2)

def _nzo_name_cmp(nzo1, nzo2):
    return cmp(nzo1.get_filename(), nzo2.get_filename())

def _nzo_size_cmp(nzo1, nzo2):
    return cmp(nzo1.get_bytes(), nzo2.get_bytes())

def sort_queue(list, method, reverse):
    super_high_priority = [nzo for nzo in list if nzo.get_priority() == TOP_PRIORITY]
    high_priority = [nzo for nzo in list if nzo.get_priority() == HIGH_PRIORITY]
    normal_priority = [nzo for nzo in list if nzo.get_priority() == NORMAL_PRIORITY]
    low_priority = [nzo for nzo in list if nzo.get_priority() == LOW_PRIORITY]
    
    super_high_priority.sort(cmp=method, reverse=reverse)
    high_priority.sort(cmp=method, reverse=reverse)
    normal_priority.sort(cmp=method, reverse=reverse)
    low_priority.sort(cmp=method, reverse=reverse)
    
    new_list = super_high_priority
    new_list.extend(high_priority)
    new_list.extend(normal_priority)
    new_list.extend(low_priority)
    
    return new_list



#-------------------------------------------------------------------------------
# NZBQ Wrappers

__NZBQ = None  # Global pointer to NzbQueue instance

def init():
    global __NZBQ
    if __NZBQ:
        __NZBQ.__init__()
    else:
        __NZBQ = NzbQueue()

def start():
    global __NZBQ
    if __NZBQ: __NZBQ.start()


def stop():
    global __NZBQ
    if __NZBQ:
        __NZBQ.stop()
        try:
            __NZBQ.join()
        except:
            pass

def debug():
    global __NZBQ
    if __NZBQ: return __NZBQ.debug()

def move_up_bulk(nzo_id, nzf_ids):
    global __NZBQ
    if __NZBQ: __NZBQ.move_up_bulk(nzo_id, nzf_ids)

def move_top_bulk(nzo_id, nzf_ids):
    global __NZBQ
    if __NZBQ: __NZBQ.move_top_bulk(nzo_id, nzf_ids)

def move_down_bulk(nzo_id, nzf_ids):
    global __NZBQ
    if __NZBQ: __NZBQ.move_down_bulk(nzo_id, nzf_ids)

def move_bottom_bulk(nzo_id, nzf_ids):
    global __NZBQ
    if __NZBQ: __NZBQ.move_bottom_bulk(nzo_id, nzf_ids)

def remove_nzo(nzo_id, add_to_history = True, unload=False):
    global __NZBQ
    if __NZBQ: __NZBQ.remove(nzo_id, add_to_history, unload)
        
def remove_multiple_nzos(nzo_ids, add_to_history = True):
    global __NZBQ
    if __NZBQ: __NZBQ.remove_multiple(nzo_ids, add_to_history)

def remove_all_nzo():
    global __NZBQ
    if __NZBQ: __NZBQ.remove_all()

def remove_nzf(nzo_id, nzf_id):
    global __NZBQ
    if __NZBQ: __NZBQ.remove_nzf(nzo_id, nzf_id)

def sort_by_avg_age(reverse=False):
    global __NZBQ
    if __NZBQ: __NZBQ.sort_by_avg_age(reverse)

def sort_by_name(reverse=False):
    global __NZBQ
    if __NZBQ: __NZBQ.sort_by_name(reverse)

def sort_by_size(reverse=False):
    global __NZBQ
    if __NZBQ: __NZBQ.sort_by_size(reverse)

def change_opts(nzo_id, pp):
    global __NZBQ
    if __NZBQ: __NZBQ.change_opts(nzo_id, pp)

def change_script(nzo_id, script):
    global __NZBQ
    if __NZBQ: __NZBQ.change_script(nzo_id, script)

def change_cat(nzo_id, cat):
    global __NZBQ
    if __NZBQ: __NZBQ.change_cat(nzo_id, cat)

def get_article(host):
    global __NZBQ
    if __NZBQ: return __NZBQ.get_article(host)

def has_articles():
    global __NZBQ
    if __NZBQ: return not __NZBQ.is_empty()

def has_articles_for(server):
    global __NZBQ
    if __NZBQ: return __NZBQ.has_articles_for(server)

def register_article(article):
    global __NZBQ
    if __NZBQ: return __NZBQ.register_article(article)

def switch(nzo_id1, nzo_id2):
    global __NZBQ
    if __NZBQ:
        return __NZBQ.switch(nzo_id1, nzo_id2)
        
def rename_nzo(nzo_id, name):
    global __NZBQ
    if __NZBQ: __NZBQ.rename(nzo_id, name)

def history_info():
    global __NZBQ
    if __NZBQ: return __NZBQ.history_info()

def queue_info(for_cli = False):
    global __NZBQ
    if __NZBQ: return __NZBQ.queue_info(for_cli = for_cli)

#def purge_history(job=None):
#    global __NZBQ
#    if __NZBQ: __NZBQ.purge(job)
        
#def remove_multiple_history(jobs=None):
#    global __NZBQ
#    if __NZBQ: __NZBQ.remove_multiple_history(jobs)
        
def get_msgids():
    global __NZBQ
    if __NZBQ: return __NZBQ.get_msgids()

def get_urls():
    global __NZBQ
    if __NZBQ: return __NZBQ.get_urls()

def pause_multiple_nzo(jobs):
    global __NZBQ
    if __NZBQ: __NZBQ.pause_multiple_nzo(jobs)
        
def resume_multiple_nzo(jobs):
    global __NZBQ
    if __NZBQ: __NZBQ.resume_multiple_nzo(jobs)

def cleanup_nzo(nzo):
    global __NZBQ
    if __NZBQ: __NZBQ.cleanup_nzo(nzo)

def reset_try_lists(nzf = None, nzo = None):
    global __NZBQ
    if __NZBQ: __NZBQ.reset_try_lists(nzf, nzo)

def save():
    global __NZBQ
    if __NZBQ: __NZBQ.save()

def generate_future(msg, pp, script, cat, url, priority):
    global __NZBQ
    if __NZBQ: return __NZBQ.generate_future(msg, pp, script, cat, url, priority)


#-------------------------------------------------------------------------------
# Synchronized wrappers

@synchronized_CV
def add_nzo(nzo):
    global __NZBQ
    if __NZBQ: __NZBQ.add(nzo)

@synchronized_CV
def insert_future_nzo(future_nzo, filename, msgid, data, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY, nzo_info={}):
    global __NZBQ
    if __NZBQ: __NZBQ.insert_future(future_nzo, filename, msgid, data, pp=pp, script=script, cat=cat, priority=priority, nzo_info=nzo_info)
        
@synchronized_CV
def set_priority(nzo_id, priority):
    global __NZBQ
    if __NZBQ: 
        return __NZBQ.set_priority(nzo_id, priority)
        
@synchronized_CV
def set_priority_multiple(nzo_ids, priority):
    global __NZBQ
    if __NZBQ: __NZBQ.set_priority_multiple(nzo_ids, priority)
        
#@synchronized_CV
#def sort_queue(field, reverse=False):
#    global __NZBQ
#    if __NZBQ: __NZBQ.sort_queue(field, reverse)
