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
from sabnzbd.nzbstuff import NzbObject, SplitFileName
from sabnzbd.misc import Panic_Queue, ExitSab

from sabnzbd.decorators import *
from sabnzbd.constants import *

def DeleteLog(name):
    if name:
        name = name.replace('.nzb', '.log')
        try:
            os.remove(os.path.join(os.path.dirname(sabnzbd.LOGFILE), name))
        except:
            pass

#-------------------------------------------------------------------------------

class HistoryItem:
    def __init__(self, nzo):
        self.nzo = nzo
        self.filename = nzo.get_filename()
        self.bytes_downloaded = nzo.get_bytes_downloaded()
        self.completed = time.time()
        self.unpackstrht = None
        self.status = nzo.get_status()

    def cleanup(self):
        if self.nzo:
            self.bytes_downloaded = self.nzo.get_bytes_downloaded()
            self.unpackstrht = self.nzo.get_unpackstrht()
            self.status = self.nzo.get_status()
            self.completed = time.time()
            self.nzo = None

#-------------------------------------------------------------------------------

NZBQUEUE_LOCK = RLock()
class NzbQueue(TryList):
    def __init__(self, auto_sort = False, top_only = False):
        TryList.__init__(self)

        self.__downloaded_items = []


        self.__top_only = top_only
        self.__top_nzo = None

        self.__nzo_list = []
        self.__nzo_table = {}

        self.__auto_sort = auto_sort

        nzo_ids = []

        data = sabnzbd.load_data(QUEUE_FILE_NAME, remove = False)

        if data:
            try:
                queue_vers, nzo_ids, self.__downloaded_items = data
                if not queue_vers == QUEUE_VERSION:
                    logging.error("[%s] Incompatible queuefile found, cannot proceed", __NAME__)
                    self.__downloaded_items = []
                    nzo_ids = []
                    Panic_Queue(os.path.join(sabnzbd.CACHE_DIR,QUEUE_FILE_NAME))
                    ExitSab(2)
            except ValueError:
                logging.error("[%s] Error loading %s, corrupt file " + \
                              "detected", __NAME__, os.path.join(sabnzbd.CACHE_DIR,QUEUE_FILE_NAME))

            for nzo_id in nzo_ids:
                nzo = sabnzbd.load_data(nzo_id, remove = False)
                if nzo:
                    self.add(nzo, save = False)

    def __init__stage2__(self):
        for hist_item in self.__downloaded_items:
            if hist_item.nzo:
                sabnzbd.postprocess_nzo(hist_item.nzo)

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
    def generate_future(self, msg, pp=None, script=None, cat=None, url=None):
        """ Create and return a placeholder nzo object """
        future_nzo = NzbObject(msg, pp, script, None, True, cat=cat, url=url)
        self.add(future_nzo)
        return future_nzo

    @synchronized(NZBQUEUE_LOCK)
    def insert_future(self, future, filename, data, pp=None, script=None, cat=None):
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
                try:
                    future.__init__(filename, pp, scr, nzb=data, futuretype=False, cat=cat)
                    future.nzo_id = nzo_id
                    self.save()
                except:
                    self.remove(nzo_id, False)

                if self.__auto_sort:
                    self.sort_by_avg_age()

                self.reset_try_list()
            except:
                logging.error("[%s] Error while adding %s, removing", __NAME__, nzo_id)
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
    def add(self, nzo, pos = -1, save=True):
        sabnzbd.QUEUECOMPLETEACTION_GO = False

        # Reset try_lists
        nzo.reset_try_list()
        self.reset_try_list()


        if not nzo.nzo_id:
            nzo.nzo_id = sabnzbd.get_new_id('nzo')

        if nzo.nzo_id:
            nzo.deleted = False
            self.__nzo_table[nzo.nzo_id] = nzo
            if pos > -1:
                self.__nzo_list.insert(pos, nzo)
            else:
                self.__nzo_list.append(nzo)
            if save:
                self.save()

        if pos != 0 and self.__auto_sort:
            self.sort_by_avg_age()

    @synchronized(NZBQUEUE_LOCK)
    def remove(self, nzo_id, add_to_history = True, unload=False):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table.pop(nzo_id)
            nzo.deleted = True
            self.__nzo_list.remove(nzo)

            if add_to_history:
                # Make sure item is only represented once in history
                should_add = True
                for hist_item in self.__downloaded_items:
                    if hist_item.nzo and hist_item.nzo.nzo_id == nzo.nzo_id:
                        should_add = False
                        break
                if should_add:
                    hist = HistoryItem(nzo)
                    self.__downloaded_items.append(hist)
                    if unload: hist.cleanup()
            else:
                self.cleanup_nzo(nzo)

            sabnzbd.remove_data(nzo_id)
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
    def switch(self, item_id_1, item_id_2):
        try:
            # Allow an index as second parameter, easier for some skins
            i = int(item_id_2)
            item_id_2 = self.__nzo_list[i].nzo_id
        except:
            pass
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
                break

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
    def sort_by_avg_age(self):
        logging.info("[%s] Sorting by average date...", __NAME__)
        self.__nzo_list.sort(cmp=_nzo_date_cmp)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_name(self):
        logging.info("[%s] Sorting by name...", __NAME__)
        self.__nzo_list.sort(cmp=_nzo_name_cmp)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_size(self):
        logging.info("[%s] Sorting by size...", __NAME__)
        self.__nzo_list.sort(cmp=_nzo_size_cmp)


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
            return not self.__nzo_list[0].server_in_try_list(server)
        else:
            return not self.server_in_try_list(server)

    @synchronized(NZBQUEUE_LOCK)
    def get_article(self, server):
        if self.__top_only:
            if self.__nzo_list:
                article = self.__nzo_list[0].get_article(server)
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
        if filename:
            root, ext = os.path.splitext(filename)
            if ext in sabnzbd.CLEANUP_LIST:
                logging.info("[%s] Skipping %s", __NAME__, nzf)
                file_done, reset = (False, True)
                post_done = post_done or nzo.remove_nzf(nzf)

        if reset:
            self.reset_try_list()

        if file_done:
            if sabnzbd.DO_SAVE:
                sabnzbd.save_data(nzo, nzo.nzo_id)

            _type = nzf.get_type()

            # Only start decoding if we have a filename and type
            if filename and _type:
                sabnzbd.assemble_nzf((nzo, nzf))

            else:
                logging.warning('[%s] %s -> Unknown encoding', __NAME__,
                                filename)

        if post_done:
            self.remove(nzo.nzo_id, True)

            if not self.__nzo_list:
                # Close server connections
                sabnzbd.disconnect()

                # Sets the end-of-queue back on if disabled
                # adding an nzb and re-adding for more blocks disables it
                if sabnzbd.QUEUECOMPLETEACTION:
                    sabnzbd.QUEUECOMPLETEACTION_GO = True
                    
            # Notify assembler to call postprocessor
            sabnzbd.assemble_nzf((nzo, None))

    @synchronized(NZBQUEUE_LOCK)
    def purge(self, job=None):
        """ Remove all history items, except the active ones """
        if job == None:
            keep = []
            for hist_item in self.__downloaded_items:
                if hist_item.nzo:
                    keep.append(hist_item)
                else:
                    DeleteLog(hist_item.filename)
            self.__downloaded_items = []
            for hist_item in keep:
                self.__downloaded_items.append(hist_item)
            del keep
        else:
            n = 0
            found = False
            for hist_item in self.__downloaded_items:
                if (not hist_item.nzo) and (str(int(hist_item.completed*1000)) == job):
                    found = True
                    break
                n = n+1
            if found:
                logging.debug("[%s] Delete History item %s", __NAME__, job)
                hist_item = self.__downloaded_items.pop(n)
                DeleteLog(hist_item.filename)

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
    def history_info(self):
        history_info = {}
        bytes_downloaded = 0
        for hist_item in self.__downloaded_items:
            completed = hist_item.completed
            filename = hist_item.filename
            bytes = hist_item.bytes_downloaded
            bytes_downloaded += bytes

            if completed not in history_info:
                history_info[completed] = []

            if hist_item.nzo:
                unpackstrht = hist_item.nzo.get_unpackstrht()
                status = hist_item.nzo.get_status()
                loaded = True
            else:
                unpackstrht = hist_item.unpackstrht
                try:
                    status = hist_item.status
                except:
                    status = ""
                loaded = False

            ident = str(int(hist_item.completed*1000))
            history_info[completed].append((filename, unpackstrht, loaded, bytes, ident, status))
        return (history_info, bytes_downloaded, sabnzbd.get_bytes())

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

        sabnzbd.purge_articles(nzo.saved_articles)

        for hist_item in self.__downloaded_items:
            # refresh fields & delete nzo reference
            if hist_item.nzo and hist_item.nzo == nzo:
                hist_item.cleanup()
                logging.debug('[%s] %s cleaned up', __NAME__,
                              nzo.get_filename())

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
    fn1, msgid1 = SplitFileName(nzo1.get_filename())
    fn2, msgid2 = SplitFileName(nzo2.get_filename())
    return cmp(fn1, fn2)

def _nzo_size_cmp(nzo1, nzo2):
    return cmp(nzo1.get_bytes(), nzo2.get_bytes())
