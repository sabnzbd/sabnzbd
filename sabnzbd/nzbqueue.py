#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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

import os
import logging
import time
import datetime

import sabnzbd
from sabnzbd.trylist import TryList
from sabnzbd.nzbstuff import NzbObject
from sabnzbd.misc import exit_sab, cat_to_opts, \
    get_admin_path, remove_all, globber, globber_full
from sabnzbd.panic import panic_queue
import sabnzbd.database as database
from sabnzbd.decorators import NZBQUEUE_LOCK, synchronized, synchronized_CV
from sabnzbd.constants import QUEUE_FILE_NAME, QUEUE_VERSION, FUTURE_Q_FOLDER, JOB_ADMIN, \
    LOW_PRIORITY, NORMAL_PRIORITY, HIGH_PRIORITY, TOP_PRIORITY, \
    REPAIR_PRIORITY, STOP_PRIORITY, VERIFIED_FILE, \
    PNFO_BYTES_FIELD, PNFO_BYTES_LEFT_FIELD, Status, QUEUE_FILE_TMPL, \
    IGNORED_FOLDERS
import sabnzbd.cfg as cfg
from sabnzbd.articlecache import ArticleCache
import sabnzbd.downloader
from sabnzbd.assembler import Assembler, file_has_articles
import sabnzbd.growler as growler
from sabnzbd.encoding import platform_encode
from sabnzbd.bpsmeter import BPSMeter


class NzbQueue(TryList):
    """ Singleton NzbQueue """
    do = None

    def __init__(self):
        TryList.__init__(self)

        self.__top_only = False  # cfg.top_only()
        self.__top_nzo = None

        self.__nzo_list = []
        self.__nzo_table = {}

        NzbQueue.do = self

    def read_queue(self, repair):
        """ Read queue from disk, supporting repair modes
            0 = no repairs
            1 = use existing queue, add missing "incomplete" folders
            2 = Discard all queue admin, reconstruct from "incomplete" folders
        """
        nzo_ids = []
        if repair < 2:
            # Read the queue from the saved files
            data = sabnzbd.load_admin(QUEUE_FILE_NAME)
            if not data:
                try:
                    # Try previous queue file
                    queue_vers, nzo_ids, dummy = sabnzbd.load_admin(QUEUE_FILE_TMPL % '9')
                except:
                    nzo_ids = []
                if nzo_ids:
                    logging.warning(T('Old queue detected, use Status->Repair to convert the queue'))
                    nzo_ids = []
            else:
                try:
                    queue_vers, nzo_ids, dummy = data
                    if not queue_vers == QUEUE_VERSION:
                        nzo_ids = []
                        logging.error(T('Incompatible queuefile found, cannot proceed'))
                        if not repair:
                            panic_queue(os.path.join(cfg.admin_dir.get_path(), QUEUE_FILE_NAME))
                            exit_sab(2)
                except ValueError:
                    nzo_ids = []
                    logging.error(T('Error loading %s, corrupt file detected'),
                                  os.path.join(cfg.admin_dir.get_path(), QUEUE_FILE_NAME))
                    if not repair:
                        return

        # First handle jobs in the queue file
        folders = []
        for nzo_id in nzo_ids:
            folder, _id = os.path.split(nzo_id)
            # Try as normal job
            path = get_admin_path(folder, False)
            nzo = sabnzbd.load_data(_id, path, remove=False)
            if not nzo:
                # Try as future job
                path = get_admin_path(folder, True)
                nzo = sabnzbd.load_data(_id, path)
            if nzo:
                self.add(nzo, save=False, quiet=True)
                folders.append(folder)

        # Scan for any folders in "incomplete" that are not yet in the queue
        if repair:
            self.scan_jobs(not folders)
            # Handle any lost future jobs
            for item in globber_full(os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)):
                path, nzo_id = os.path.split(item)
                if nzo_id not in self.__nzo_table:
                    if nzo_id.startswith('SABnzbd_nzo'):
                        nzo = sabnzbd.load_data(nzo_id, path, remove=True)
                        if nzo:
                            self.add(nzo, save=True)
                    else:
                        try:
                            os.remove(item)
                        except:
                            pass

    def scan_jobs(self, all=False, action=True):
        """ Scan "incomplete" for missing folders,
            'all' is True: Include active folders
            'action' is True, do the recovery action
            returns list of orphaned folders
        """
        from sabnzbd.api import build_history
        result = []
        # Folders from the download queue
        if all:
            registered = []
        else:
            registered = [nzo.work_name for nzo in self.__nzo_list]

        # Retryable folders from History
        items = build_history()[0]
        # Anything waiting or active or retryable is a known item
        registered.extend([platform_encode(os.path.basename(item['path']))
                           for item in items if item['retry'] or item['loaded'] or item['status'] == Status.QUEUED])

        # Repair unregistered folders
        for folder in globber_full(cfg.download_dir.get_path()):
            name = os.path.basename(folder)
            if os.path.isdir(folder) and name not in registered and name not in IGNORED_FOLDERS:
                if action:
                    logging.info('Repairing job %s', folder)
                    self.repair_job(folder)
                result.append(os.path.basename(folder))
            else:
                if action:
                    logging.info('Skipping repair for job %s', folder)
        return result

    def retry_all_jobs(self, history_db):
        """ Retry all retryable jobs in History """
        from sabnzbd.api import build_history
        result = []

        # Retryable folders from History
        items = build_history()[0]
        registered = [(platform_encode(os.path.basename(item['path'])),
                       item['nzo_id'])
                       for item in items if item['retry']]

        for job in registered:
            logging.info('Repairing job %s', job[0])
            result.append(self.repair_job(job[0]))
            history_db.remove_history(job[1])
        return bool(result)

    def repair_job(self, folder, new_nzb=None, password=None):
        """ Reconstruct admin for a single job folder, optionally with new NZB """
        def all_verified(path):
            """ Return True when all sets have been successfully verified """
            verified = sabnzbd.load_data(VERIFIED_FILE, path, remove=False) or {'x': False}
            return not bool([True for x in verified if not verified[x]])

        nzo_id = None
        name = os.path.basename(folder)
        path = os.path.join(folder, JOB_ADMIN)
        if hasattr(new_nzb, 'filename'):
            filename = new_nzb.filename
        else:
            filename = ''
        if not filename:
            if not all_verified(path):
                filename = globber_full(path, '*.gz')
            if len(filename) > 0:
                logging.debug('Repair job %s by reparsing stored NZB', name)
                nzo_id = sabnzbd.add_nzbfile(filename[0], pp=None, script=None, cat=None, priority=None, nzbname=name,
                                             reuse=True, password=password)[1]
            else:
                logging.debug('Repair job %s without stored NZB', name)
                nzo = NzbObject(name, pp=None, script=None, nzb='', cat=None, priority=None, nzbname=name, reuse=True)
                nzo.password = password
                self.add(nzo)
                nzo_id = nzo.nzo_id
        else:
            remove_all(path, '*.gz')
            logging.debug('Repair job %s with new NZB (%s)', name, filename)
            nzo_id = sabnzbd.add_nzbfile(new_nzb, pp=None, script=None, cat=None, priority=None, nzbname=name,
                                         reuse=True, password=password)[1]

        return nzo_id

    def send_back(self, nzo):
        """ Send back job to queue after successful pre-check """
        try:
            nzb_path = globber_full(nzo.workpath, '*.gz')[0]
        except:
            logging.debug('Failed to find NZB file after pre-check (%s)', nzo.nzo_id)
            return
        from sabnzbd.dirscanner import ProcessSingleFile
        res, nzo_ids = ProcessSingleFile(nzo.work_name + '.nzb', nzb_path, keep=True, reuse=True)
        if res == 0 and nzo_ids:
            nzo = self.replace_in_q(nzo, nzo_ids[0])
            # Reset reuse flag to make pause/abort on encryption possible
            nzo.reuse = False

    @synchronized(NZBQUEUE_LOCK)
    def replace_in_q(self, nzo, nzo_id):
        """ Replace nzo by new in at the same spot in the queue, destroy nzo """
        try:
            new_nzo = self.get_nzo(nzo_id)
            pos = self.__nzo_list.index(new_nzo)
            targetpos = self.__nzo_list.index(nzo)
            self.__nzo_list[targetpos] = new_nzo
            self.__nzo_list.pop(pos)
            del self.__nzo_table[nzo.nzo_id]
            del nzo
            return new_nzo
        except:
            logging.error(T('Failed to restart NZB after pre-check (%s)'), nzo.nzo_id)
            logging.info("Traceback: ", exc_info=True)
            return nzo

    @synchronized(NZBQUEUE_LOCK)
    def save(self, save_nzo=None):
        """ Save queue, all nzo's or just the specified one """
        logging.info("Saving queue")

        nzo_ids = []
        # Aggregate nzo_ids and save each nzo
        for nzo in self.__nzo_list:
            nzo_ids.append(os.path.join(nzo.work_name, nzo.nzo_id))
            if save_nzo is None or nzo is save_nzo:
                sabnzbd.save_data(nzo, nzo.nzo_id, nzo.workpath)
                if not nzo.futuretype:
                    nzo.save_to_disk()

        sabnzbd.save_admin((QUEUE_VERSION, nzo_ids, []), QUEUE_FILE_NAME)

    @synchronized(NZBQUEUE_LOCK)
    def set_top_only(self, value):
        self.__top_only = value

    @synchronized(NZBQUEUE_LOCK)
    def generate_future(self, msg, pp=None, script=None, cat=None, url=None, priority=NORMAL_PRIORITY, nzbname=None):
        """ Create and return a placeholder nzo object """
        future_nzo = NzbObject(msg, pp, script, None, True, cat=cat, url=url, priority=priority, nzbname=nzbname, status=Status.GRABBING)
        self.add(future_nzo)
        return future_nzo

    @synchronized(NZBQUEUE_LOCK)
    def insert_future(self, future, filename, data, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY, nzbname=None, nzo_info=None):
        """ Refresh a placeholder nzo with an actual nzo """
        assert isinstance(future, NzbObject)
        if nzo_info is None:
            nzo_info = {}
        nzo_id = future.nzo_id
        if nzo_id in self.__nzo_table:
            try:
                sabnzbd.remove_data(nzo_id, future.workpath)
                logging.info("Regenerating item: %s", nzo_id)
                r, u, d = future.repair_opts
                if r is not None:
                    pp = sabnzbd.opts_to_pp(r, u, d)
                scr = future.script
                if scr is None:
                    scr = script
                categ = future.cat
                if categ is None:
                    categ = cat
                categ, pp, script, priority = cat_to_opts(categ, pp, script, priority)

                # Remember old priority
                old_prio = future.priority

                try:
                    future.__init__(filename, pp, scr, nzb=data, futuretype=False, cat=categ, priority=priority, nzbname=nzbname, nzo_info=nzo_info)
                    future.nzo_id = nzo_id
                    self.save(future)
                except ValueError:
                    self.remove(nzo_id, False)
                except TypeError:
                    self.remove(nzo_id, False)

                # Make sure the priority is changed now that we know the category
                if old_prio != priority:
                    future.priority = None
                self.set_priority(future.nzo_id, priority)

                if cfg.auto_sort():
                    self.sort_by_avg_age()

                self.reset_try_list()
            except:
                logging.error(T('Error while adding %s, removing'), nzo_id)
                logging.info("Traceback: ", exc_info=True)
                self.remove(nzo_id, False)
        else:
            logging.info("Item %s no longer in queue, omitting",
                         nzo_id)

    @synchronized(NZBQUEUE_LOCK)
    def change_opts(self, nzo_ids, pp):
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
            if nzo_id in self.__nzo_table:
                self.__nzo_table[nzo_id].set_pp(pp)
                result += 1
        return result

    @synchronized(NZBQUEUE_LOCK)
    def change_script(self, nzo_ids, script):
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
            if nzo_id in self.__nzo_table:
                self.__nzo_table[nzo_id].script = script
                result += 1
        return result

    @synchronized(NZBQUEUE_LOCK)
    def change_cat(self, nzo_ids, cat, explicit_priority=None):
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
            if nzo_id in self.__nzo_table:
                nzo = self.__nzo_table[nzo_id]
                nzo.cat, pp, nzo.script, prio = cat_to_opts(cat)
                nzo.set_pp(pp)
                if explicit_priority is None:
                    self.set_priority(nzo_id, prio)
                result += 1
        return result

    @synchronized(NZBQUEUE_LOCK)
    def change_name(self, nzo_id, name, password=None):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            if not nzo.futuretype:
                nzo.set_final_name_pw(name, password)
            else:
                # Reset url fetch wait time
                nzo.wait = None
            return True
        else:
            return False

    @synchronized(NZBQUEUE_LOCK)
    def get_nzo(self, nzo_id):
        if nzo_id in self.__nzo_table:
            return self.__nzo_table[nzo_id]
        else:
            return None

    @synchronized(NZBQUEUE_LOCK)
    def add(self, nzo, save=True, quiet=False):
        assert isinstance(nzo, NzbObject)
        if not nzo.nzo_id:
            nzo.nzo_id = sabnzbd.get_new_id('nzo', nzo.workpath, self.__nzo_table)

        # If no files are to be downloaded anymore, send to postproc
        if not nzo.files and not nzo.futuretype:
            self.end_job(nzo)
            return ''

        # Reset try_lists
        nzo.reset_try_list()
        self.reset_try_list()

        if nzo.nzo_id:
            nzo.deleted = False
            priority = nzo.priority
            if sabnzbd.scheduler.analyse(False, priority):
                nzo.status = Status.PAUSED

            self.__nzo_table[nzo.nzo_id] = nzo
            if priority > HIGH_PRIORITY:
                # Top and repair priority items are added to the top of the queue
                self.__nzo_list.insert(0, nzo)
            elif priority == LOW_PRIORITY:
                self.__nzo_list.append(nzo)
            else:
                # for high priority we need to add the item at the bottom
                # of any other high priority items above the normal priority
                # for normal priority we need to add the item at the bottom
                # of the normal priority items above the low priority
                if self.__nzo_list:
                    pos = 0
                    added = False
                    for position in self.__nzo_list:
                        if position.priority < priority:
                            self.__nzo_list.insert(pos, nzo)
                            added = True
                            break
                        pos += 1
                    if not added:
                        # if there are no other items classed as a lower priority
                        # then it will be added to the bottom of the queue
                        self.__nzo_list.append(nzo)
                else:
                    # if the queue is empty then simple append the item to the bottom
                    self.__nzo_list.append(nzo)
            if save:
                self.save(nzo)

            if not (quiet or nzo.status in ('Fetching',)):
                growler.send_notification(T('NZB added to queue'), nzo.filename, 'download')

        if cfg.auto_sort():
            self.sort_by_avg_age()
        return nzo.nzo_id

    @synchronized(NZBQUEUE_LOCK)
    def remove(self, nzo_id, add_to_history=True, save=True, cleanup=True, keep_basic=False, del_files=False):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table.pop(nzo_id)
            nzo.deleted = True
            self.__nzo_list.remove(nzo)

            sabnzbd.remove_data(nzo_id, nzo.workpath)

            if add_to_history:
                # Create the history DB instance
                history_db = database.get_history_handle()
                # Add the nzo to the database. Only the path, script and time taken is passed
                # Other information is obtained from the nzo
                history_db.add_history_db(nzo, '', '', 0, '', '')
                history_db.close()

            elif cleanup:
                self.cleanup_nzo(nzo, keep_basic, del_files)

            if save:
                self.save(nzo)
        else:
            nzo_id = None
        return nzo_id

    @synchronized(NZBQUEUE_LOCK)
    def remove_multiple(self, nzo_ids, del_files=False):
        removed = []
        for nzo_id in nzo_ids:
            if self.remove(nzo_id, add_to_history=False, save=False, keep_basic=not del_files, del_files=del_files):
                removed.append(nzo_id)
        # Save with invalid nzo_id, to that only queue file is saved
        self.save('x')
        return removed

    @synchronized(NZBQUEUE_LOCK)
    def remove_all(self, search=None):
        if search:
            search = search.lower()
        removed = []
        for nzo_id in self.__nzo_table.keys():
            if (not search) or search in self.__nzo_table[nzo_id].final_name_pw_clean.lower():
                nzo = self.__nzo_table.pop(nzo_id)
                nzo.deleted = True
                self.__nzo_list.remove(nzo)
                sabnzbd.remove_data(nzo_id, nzo.workpath)
                self.cleanup_nzo(nzo)
                removed.append(nzo_id)
        self.save()
        return removed

    @synchronized(NZBQUEUE_LOCK)
    def remove_nzf(self, nzo_id, nzf_id):
        removed = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzf = nzo.get_nzf_by_id(nzf_id)

            if nzf:
                removed.append(nzf_id)
                post_done = nzo.remove_nzf(nzf)
                if post_done:
                    if nzo.finished_files:
                        self.end_job(nzo)
                    else:
                        self.remove(nzo_id, add_to_history=False, keep_basic=False)
        return removed

    @synchronized(NZBQUEUE_LOCK)
    def pause_multiple_nzo(self, nzo_ids):
        handled = []
        for nzo_id in nzo_ids:
            self.pause_nzo(nzo_id)
            handled.append(nzo_id)
        return handled

    @synchronized(NZBQUEUE_LOCK)
    def pause_nzo(self, nzo_id):
        handled = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.pause()
            logging.debug("Paused nzo: %s", nzo_id)
            handled.append(nzo_id)
        return handled

    @synchronized(NZBQUEUE_LOCK)
    def resume_multiple_nzo(self, nzo_ids):
        handled = []
        for nzo_id in nzo_ids:
            self.resume_nzo(nzo_id)
            handled.append(nzo_id)
        return handled

    @synchronized(NZBQUEUE_LOCK)
    def resume_nzo(self, nzo_id):
        handled = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.resume()
            nzo.reset_all_try_lists()
            logging.debug("Resumed nzo: %s", nzo_id)
            handled.append(nzo_id)
        self.reset_try_list()
        return handled

    @synchronized(NZBQUEUE_LOCK)
    def switch(self, item_id_1, item_id_2):
        try:
            # Allow an index as second parameter, easier for some skins
            i = int(item_id_2)
            item_id_2 = self.__nzo_list[i].nzo_id
        except:
            pass
        try:
            nzo1 = self.__nzo_table[item_id_1]
            nzo2 = self.__nzo_table[item_id_2]
        except KeyError:
            # One or both jobs missing
            return (-1, 0)

        if nzo1 == nzo2:
            return (-1, 0)

        # get the priorities of the two items
        nzo1_priority = nzo1.priority
        nzo2_priority = nzo2.priority
        try:
            # get the item id of the item below to use in priority changing
            item_id_3 = self.__nzo_list[i + 1].nzo_id
            # if there is an item below the id1 and id2 then we need that too
            # to determine whether to change the priority
            nzo3 = self.__nzo_table[item_id_3]
            nzo3_priority = nzo3.priority
            # if id1 is surrounded by items of a different priority then change it's pririty to match
            if nzo2_priority != nzo1_priority and nzo3_priority != nzo1_priority or nzo2_priority > nzo1_priority:
                nzo1.priority = nzo2_priority
        except:
            nzo1.priority = nzo2_priority
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
                return (item_id_pos2, nzo1.priority)
        # If moving failed/no movement took place
        return (-1, nzo1.priority)

    @synchronized(NZBQUEUE_LOCK)
    def get_position(self, nzb_id):
        for i in xrange(len(self.__nzo_list)):
            if nzb_id == self.__nzo_list[i].nzo_id:
                return i
        return -1

    @synchronized(NZBQUEUE_LOCK)
    def move_up_bulk(self, nzo_id, nzf_ids, size):
        if nzo_id in self.__nzo_table:
            for unused in range(size):
                self.__nzo_table[nzo_id].move_up_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def move_top_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_top_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def move_down_bulk(self, nzo_id, nzf_ids, size):
        if nzo_id in self.__nzo_table:
            for unused in range(size):
                self.__nzo_table[nzo_id].move_down_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def move_bottom_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_bottom_bulk(nzf_ids)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_avg_age(self, reverse=False):
        logging.info("Sorting by average date...(reversed:%s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_date_cmp, reverse)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_name(self, reverse=False):
        logging.info("Sorting by name...(reversed:%s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_name_cmp, reverse)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_size(self, reverse=False):
        logging.info("Sorting by size...(reversed:%s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_size_cmp, reverse)

    @synchronized(NZBQUEUE_LOCK)
    def sort_queue(self, field, reverse=None):
        if isinstance(reverse, basestring):
            if reverse.lower() == 'desc':
                reverse = True
            else:
                reverse = False
        if reverse is None:
            reverse = False
        if field.lower() == 'name':
            self.sort_by_name(reverse)
        elif field.lower() == 'size' or field.lower() == 'bytes':
            self.sort_by_size(reverse)
        elif field.lower() == 'avg_age':
            self.sort_by_avg_age(reverse)
        else:
            logging.debug("Sort: %s not recognized", field)

    def __set_priority(self, nzo_id, priority):
        """ Sets the priority on the nzo and places it in the queue at the appropriate position """
        try:
            priority = int(priority)
            nzo = self.__nzo_table[nzo_id]
            nzo_id_pos1 = -1
            pos = -1

            # If priority == STOP_PRIORITY, then send to queue
            if priority == STOP_PRIORITY:
                self.end_job(nzo)
                return

            # Get the current position in the queue
            for i in xrange(len(self.__nzo_list)):
                if nzo_id == self.__nzo_list[i].nzo_id:
                    nzo_id_pos1 = i
                    break

            # Don't change priority and order if priority is the same as asked
            if priority == self.__nzo_list[nzo_id_pos1].priority:
                return nzo_id_pos1

            nzo.priority = priority
            if sabnzbd.scheduler.analyse(False, priority) and \
               nzo.status in (Status.CHECKING, Status.DOWNLOADING, Status.QUEUED):
                nzo.status = Status.PAUSED
            elif nzo.status == Status.PAUSED:
                nzo.status = Status.QUEUED
            nzo.save_to_disk()

            if nzo_id_pos1 != -1:
                del self.__nzo_list[nzo_id_pos1]
                if priority == TOP_PRIORITY:
                    # A top priority item (usually a completed download fetching pars)
                    # is added to the top of the queue
                    self.__nzo_list.insert(0, nzo)
                    pos = 0
                elif priority == LOW_PRIORITY:
                    pos = len(self.__nzo_list)
                    self.__nzo_list.append(nzo)
                else:
                    # for high priority we need to add the item at the bottom
                    # of any other high priority items above the normal priority
                    # for normal priority we need to add the item at the bottom
                    # of the normal priority items above the low priority
                    if self.__nzo_list:
                        p = 0
                        added = False
                        for position in self.__nzo_list:
                            if position.priority < priority:
                                self.__nzo_list.insert(p, nzo)
                                pos = p
                                added = True
                                break
                            p += 1
                        if not added:
                            # if there are no other items classed as a lower priority
                            # then it will be added to the bottom of the queue
                            pos = len(self.__nzo_list)
                            self.__nzo_list.append(nzo)
                    else:
                        # if the queue is empty then simple append the item to the bottom
                        self.__nzo_list.append(nzo)
                        pos = 0
            return pos

        except:
            return -1

    @synchronized(NZBQUEUE_LOCK)
    def set_priority(self, nzo_ids, priority):
        try:
            n = -1
            for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
                n = self.__set_priority(nzo_id, priority)
            return n
        except:
            return -1

    @synchronized(NZBQUEUE_LOCK)
    def reset_try_lists(self, nzf=None, nzo=None):
        if nzf:
            nzf.reset_try_list()
        if nzo:
            nzo.reset_try_list()
        self.reset_try_list()

    @synchronized(NZBQUEUE_LOCK)
    def reset_all_try_lists(self):
        for nzo in self.__nzo_list:
            nzo.reset_all_try_lists()
        self.reset_try_list()

    @synchronized(NZBQUEUE_LOCK)
    def has_articles_for(self, server):
        """ Check whether there are any pending articles for the downloader """
        if not self.__nzo_list:
            return False
        if self.__top_only:
            for nzo in self.__nzo_list:
                # Ignore any items that are in a paused or grabbing state
                if nzo.status not in (Status.PAUSED, Status.GRABBING):
                    return not nzo.server_in_try_list(server)
        else:
            # Check if this server is allowed for any object, then return if we've tried this server.
            for nzo in self.__nzo_list:
                if nzo.status not in (Status.PAUSED, Status.GRABBING):
                    if nzo.server_allowed(server):
                        return not self.server_in_try_list(server)
            return False

    @synchronized(NZBQUEUE_LOCK)
    def has_forced_items(self):
        """ Check if the queue contains any Forced
            Priority items to download while paused
        """
        for nzo in self.__nzo_list:
            if nzo.priority == TOP_PRIORITY and nzo.status not in (Status.PAUSED, Status.GRABBING):
                return True
        return False

    @synchronized(NZBQUEUE_LOCK)
    def get_article(self, server, servers):
        if self.__top_only:
            if self.__nzo_list:
                for nzo in self.__nzo_list:
                    if nzo.status not in (Status.PAUSED, Status.GRABBING) and nzo.server_allowed(server):
                        article = nzo.get_article(server, servers)
                        if article:
                            return article

        else:
            for nzo in self.__nzo_list:
                # Don't try to get an article if server is in try_list of nzo
                if not nzo.server_in_try_list(server) and nzo.status not in (Status.PAUSED, Status.GRABBING) and nzo.server_allowed(server):
                    article = nzo.get_article(server, servers)
                    if article:
                        return article

            # No articles for this server, block server (until reset issued)
            self.add_to_try_list(server)

    @synchronized(NZBQUEUE_LOCK)
    def register_article(self, article, found=True):
        nzf = article.nzf
        nzo = nzf.nzo

        if nzf.deleted:
            logging.debug("Discarding article %s, no longer in queue", article.article)
            return

        file_done, post_done, reset = nzo.remove_article(article, found)

        filename = nzf.filename

        if reset:
            self.reset_try_list()

        if file_done:
            if nzo.next_save is None or time.time() > nzo.next_save:
                sabnzbd.save_data(nzo, nzo.nzo_id, nzo.workpath)
                BPSMeter.do.save()
                if nzo.save_timeout is None:
                    nzo.next_save = None
                else:
                    nzo.next_save = time.time() + nzo.save_timeout

            if not nzo.precheck:
                _type = nzf.type

                # Only start decoding if we have a filename and type
                if filename and _type:
                    Assembler.do.process((nzo, nzf))

                else:
                    if file_has_articles(nzf):
                        logging.warning(T('%s -> Unknown encoding'), filename)
        if post_done:
            self.end_job(nzo)

    def end_job(self, nzo):
        """ Send NZO to the post-processing queue """
        if self.actives(grabs=False) < 2 and cfg.autodisconnect():
            # This was the last job, close server connections
            if sabnzbd.downloader.Downloader.do:
                sabnzbd.downloader.Downloader.do.disconnect()

        # Notify assembler to call postprocessor
        if not nzo.deleted:
            nzo.deleted = True
            if nzo.precheck:
                nzo.save_to_disk()
                # Check result
                enough, _ratio = nzo.check_quality()
                if enough:
                    # Enough data present, do real download
                    _workdir = nzo.downpath
                    self.cleanup_nzo(nzo, keep_basic=True)
                    self.send_back(nzo)
                    return
                else:
                    # Not enough data, let postprocessor show it as failed
                    pass
            Assembler.do.process((nzo, None))

    @synchronized(NZBQUEUE_LOCK)
    def actives(self, grabs=True):
        """ Return amount of non-paused jobs, optionally with 'grabbing' items """
        n = 0
        for nzo in self.__nzo_list:
            # Ignore any items that are paused
            if grabs and nzo.status == Status.GRABBING:
                n += 1
            elif nzo.status not in (Status.PAUSED, Status.GRABBING):
                n += 1
        return n

    @synchronized(NZBQUEUE_LOCK)
    def queue_info(self, for_cli=False, max_jobs=0, search=None):
        """ Return list of queued jobs, optionally filtered by 'search' """
        if search:
            search = search.lower()
        bytes_left = 0
        bytes_total = 0
        q_size = 0
        pnfo_list = []
        n = 0
        for nzo in self.__nzo_list:
            if nzo.status != 'Paused':
                b, b_left = nzo.total_and_remaining()
                bytes_total += b
                bytes_left += b_left
                q_size += 1

            if (not search) or search in nzo.final_name_pw_clean.lower():
                if not max_jobs or n < max_jobs:
                    pnfo = nzo.gather_info(for_cli=for_cli)
                    pnfo_list.append(pnfo)
                n += 1

        return (bytes_total, bytes_left, pnfo_list, q_size, len(self.__nzo_list))

    @synchronized(NZBQUEUE_LOCK)
    def remaining(self):
        """ Return bytes left in the queue by non-paused items """
        bytes_left = 0
        for nzo in self.__nzo_list:
            if nzo.status != 'Paused':
                bytes_left += nzo.remaining()
        return bytes_left

    @synchronized(NZBQUEUE_LOCK)
    def is_empty(self):
        empty = True
        for nzo in self.__nzo_list:
            if not nzo.futuretype and nzo.status != 'Paused':
                empty = False
                break
        return empty

    @synchronized(NZBQUEUE_LOCK)
    def cleanup_nzo(self, nzo, keep_basic=False, del_files=False):
        nzo.purge_data(keep_basic, del_files)

        ArticleCache.do.purge_articles(nzo.saved_articles)

    @synchronized(NZBQUEUE_LOCK)
    def stop_idle_jobs(self):
        """ Detect jobs that have zero files left and send them to post processing """
        empty = []
        for nzo in self.__nzo_list:
            if not nzo.futuretype and not nzo.files and nzo.status not in (Status.PAUSED, Status.GRABBING):
                empty.append(nzo)
        for nzo in empty:
            self.end_job(nzo)

    @synchronized(NZBQUEUE_LOCK)
    def pause_on_prio(self, priority):
        for nzo in self.__nzo_list:
            if not nzo.futuretype and nzo.priority == priority:
                nzo.pause()

    @synchronized(NZBQUEUE_LOCK)
    def resume_on_prio(self, priority):
        for nzo in self.__nzo_list:
            if not nzo.futuretype and nzo.priority == priority:
                # Don't use nzo.resume() to avoid resetting job warning flags
                nzo.status = Status.QUEUED

    def get_urls(self):
        """ Return list of future-types needing URL """
        lst = []
        for nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            if nzo.futuretype:
                url = nzo.url
                if nzo.futuretype and url.lower().startswith('http'):
                    lst.append((url, nzo))
        return lst

    def __repr__(self):
        return "<NzbQueue>"


def _nzo_date_cmp(nzo1, nzo2):
    avg_date1 = nzo1.avg_date
    avg_date2 = nzo2.avg_date

    if avg_date1 is None and avg_date2 is None:
        return 0

    if avg_date1 is None:
        avg_date1 = datetime.datetime.now()
    elif avg_date2 is None:
        avg_date2 = datetime.datetime.now()

    return cmp(avg_date1, avg_date2)


def _nzo_name_cmp(nzo1, nzo2):
    return cmp(nzo1.final_name.lower(), nzo2.final_name.lower())


def _nzo_size_cmp(nzo1, nzo2):
    return cmp(nzo1.bytes, nzo2.bytes)


def sort_queue_function(nzo_list, method, reverse):
    ultra_high_priority = [nzo for nzo in nzo_list if nzo.priority == REPAIR_PRIORITY]
    super_high_priority = [nzo for nzo in nzo_list if nzo.priority == TOP_PRIORITY]
    high_priority = [nzo for nzo in nzo_list if nzo.priority == HIGH_PRIORITY]
    normal_priority = [nzo for nzo in nzo_list if nzo.priority == NORMAL_PRIORITY]
    low_priority = [nzo for nzo in nzo_list if nzo.priority == LOW_PRIORITY]

    ultra_high_priority.sort(cmp=method, reverse=reverse)
    super_high_priority.sort(cmp=method, reverse=reverse)
    high_priority.sort(cmp=method, reverse=reverse)
    normal_priority.sort(cmp=method, reverse=reverse)
    low_priority.sort(cmp=method, reverse=reverse)

    new_list = ultra_high_priority
    new_list.extend(super_high_priority)
    new_list.extend(high_priority)
    new_list.extend(normal_priority)
    new_list.extend(low_priority)

    # Make sure any left-over jobs enter the new list
    for item in nzo_list:
        if item not in new_list:
            new_list.append(item)

    return new_list


# Synchronized wrappers

@synchronized_CV
def add_nzo(nzo, quiet=False):
    return NzbQueue.do.add(nzo, quiet=quiet)


@synchronized_CV
def insert_future_nzo(future_nzo, filename, data, pp=None, script=None, cat=None, priority=NORMAL_PRIORITY, nzbname=None, nzo_info=None):
    if nzo_info is None:
        nzo_info = {}
    NzbQueue.do.insert_future(future_nzo, filename, data, pp=pp, script=script, cat=cat, priority=priority, nzbname=nzbname, nzo_info=nzo_info)


@synchronized_CV
def set_priority(nzo_ids, priority):
    return NzbQueue.do.set_priority(nzo_ids, priority)


@synchronized_CV
def get_nzo(nzo_id):
    return NzbQueue.do.get_nzo(nzo_id)


@synchronized_CV
def sort_queue(field, reverse=False):
    NzbQueue.do.sort_queue(field, reverse)


@synchronized_CV
@synchronized(NZBQUEUE_LOCK)
def repair_job(folder, new_nzb, password):
    return NzbQueue.do.repair_job(folder, new_nzb, password)


@synchronized_CV
@synchronized(NZBQUEUE_LOCK)
def scan_jobs(all=False, action=True):
    return NzbQueue.do.scan_jobs(all, action)
