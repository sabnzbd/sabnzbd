#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
from sabnzbd.nzbstuff import NzbObject
from sabnzbd.misc import exit_sab, cat_to_opts, remove_file, \
    get_admin_path, remove_all, globber_full, int_conv
from sabnzbd.panic import panic_queue
import sabnzbd.database as database
from sabnzbd.decorators import notify_downloader, synchronized, NZBQUEUE_LOCK
from sabnzbd.constants import QUEUE_FILE_NAME, QUEUE_VERSION, FUTURE_Q_FOLDER, \
    JOB_ADMIN, LOW_PRIORITY, NORMAL_PRIORITY, HIGH_PRIORITY, TOP_PRIORITY, \
    REPAIR_PRIORITY, STOP_PRIORITY, VERIFIED_FILE, \
    Status, IGNORED_FOLDERS, QNFO

import sabnzbd.cfg as cfg
from sabnzbd.articlecache import ArticleCache
import sabnzbd.downloader
from sabnzbd.assembler import Assembler, file_has_articles
import sabnzbd.notifier as notifier
from sabnzbd.encoding import platform_encode
from sabnzbd.bpsmeter import BPSMeter


class NzbQueue(object):
    """ Singleton NzbQueue """
    do = None

    def __init__(self):
        self.__top_only = cfg.top_only()
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

            # Process the data and check compatibility
            nzo_ids = self.check_compatibility(data)

        # First handle jobs in the queue file
        folders = []
        for nzo_id in nzo_ids:
            folder, _id = os.path.split(nzo_id)
            path = get_admin_path(folder, future=False)

            # Try as normal job
            nzo = sabnzbd.load_data(_id, path, remove=False)
            if not nzo:
                # Try as future job
                path = get_admin_path(folder, future=True)
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
                            remove_file(item)
                        except:
                            pass

    def check_compatibility(self, data):
        """ Do compatibility checks on the loaded data """
        nzo_ids = []
        if not data:
            # Warn about old queue
            if sabnzbd.OLD_QUEUE and cfg.warned_old_queue() < QUEUE_VERSION:
                logging.warning(T('Old queue detected, use Status->Repair to convert the queue'))
                cfg.warned_old_queue.set(QUEUE_VERSION)
                sabnzbd.config.save_config()
        else:
            # Try to process
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

        # We need to do a repair in case of old-style pickles
        if not cfg.converted_nzo_pickles():
            for nzo_id in nzo_ids:
                folder, _id = os.path.split(nzo_id)
                path = get_admin_path(folder, future=False)
                # This will update them but preserve queue-order
                if os.path.exists(os.path.join(path, _id)):
                    self.repair_job(os.path.dirname(path))
                continue

            # Remove any future-jobs, we can't save those
            for item in globber_full(os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)):
                remove_file(item)

            # Done converting
            cfg.converted_nzo_pickles.set(True)
            sabnzbd.config.save_config()
            nzo_ids = []
        return nzo_ids

    @synchronized(NZBQUEUE_LOCK)
    def scan_jobs(self, all=False, action=True):
        """ Scan "incomplete" for missing folders,
            'all' is True: Include active folders
            'action' is True, do the recovery action
            returns list of orphaned folders
        """
        result = []
        # Folders from the download queue
        if all:
            registered = []
        else:
            registered = [nzo.work_name for nzo in self.__nzo_list]

        # Retryable folders from History
        items = sabnzbd.api.build_history(output=True)[0]
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
        result = []

        # Retryable folders from History
        items = sabnzbd.api.build_history()[0]
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
            return all(verified[x] for x in verified)

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

    @notify_downloader
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
        # Must be a separate function from "send_back()", due to the required queue-lock
        try:
            old_id = nzo.nzo_id
            new_nzo = self.get_nzo(nzo_id)
            pos = self.__nzo_list.index(new_nzo)
            targetpos = self.__nzo_list.index(nzo)
            self.__nzo_list[targetpos] = new_nzo
            self.__nzo_list.pop(pos)
            # Reuse the old nzo_id
            new_nzo.nzo_id = old_id
            # Therefore: remove the new nzo_id
            del self.__nzo_table[nzo_id]
            # And attach the new nzo to the old nzo_id
            self.__nzo_table[old_id] = new_nzo
            logging.info('Replacing in queue %s by %s', nzo.final_name, new_nzo.final_name)
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
        for nzo in self.__nzo_list[:]:
            if not nzo.is_gone():
                nzo_ids.append(os.path.join(nzo.work_name, nzo.nzo_id))
                if save_nzo is None or nzo is save_nzo:
                    if not nzo.futuretype:
                        # Also includes save_data for NZO
                        nzo.save_to_disk()
                    else:
                        sabnzbd.save_data(nzo, nzo.nzo_id, nzo.workpath)

        sabnzbd.save_admin((QUEUE_VERSION, nzo_ids, []), QUEUE_FILE_NAME)

    def set_top_only(self, value):
        self.__top_only = value

    def generate_future(self, msg, pp=None, script=None, cat=None, url=None, priority=NORMAL_PRIORITY, nzbname=None):
        """ Create and return a placeholder nzo object """
        logging.debug('Creating placeholder NZO')
        future_nzo = NzbObject(msg, pp, script, None, True, cat=cat, url=url, priority=priority, nzbname=nzbname, status=Status.GRABBING)
        self.add(future_nzo)
        return future_nzo

    def change_opts(self, nzo_ids, pp):
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
            if nzo_id in self.__nzo_table:
                self.__nzo_table[nzo_id].set_pp(pp)
                result += 1
        return result

    def change_script(self, nzo_ids, script):
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
            if nzo_id in self.__nzo_table:
                self.__nzo_table[nzo_id].script = script
                logging.info('Set script=%s for job %s', script, self.__nzo_table[nzo_id].final_name)
                result += 1
        return result

    def change_cat(self, nzo_ids, cat, explicit_priority=None):
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
            if nzo_id in self.__nzo_table:
                nzo = self.__nzo_table[nzo_id]
                nzo.cat, pp, nzo.script, prio = cat_to_opts(cat)
                logging.info('Set cat=%s for job %s', cat, nzo.final_name)
                nzo.set_pp(pp)
                if explicit_priority is None:
                    self.set_priority(nzo_id, prio)
                # Abort any ongoing unpacking if the category changed
                nzo.abort_direct_unpacker()
                result += 1
        return result

    def change_name(self, nzo_id, name, password=None):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            logging.info('Renaming %s to %s', nzo.final_name, name)
            # Abort any ongoing unpacking if the name changed (dirs change)
            nzo.abort_direct_unpacker()
            if not nzo.futuretype:
                nzo.set_final_name_pw(name, password)
            else:
                # Reset url fetch wait time
                nzo.wait = None
            return True
        else:
            return False

    def get_nzo(self, nzo_id):
        if nzo_id in self.__nzo_table:
            return self.__nzo_table[nzo_id]
        else:
            return None

    @notify_downloader
    @synchronized(NZBQUEUE_LOCK)
    def add(self, nzo, save=True, quiet=False):
        if not nzo.nzo_id:
            nzo.nzo_id = sabnzbd.get_new_id('nzo', nzo.workpath, self.__nzo_table)

        # If no files are to be downloaded anymore, send to postproc
        if not nzo.files and not nzo.futuretype:
            self.end_job(nzo)
            return ''

        # Reset try_lists
        nzo.reset_try_list()

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
                notifier.send_notification(T('NZB added to queue'), nzo.filename, 'download', nzo.cat)

        if not quiet and cfg.auto_sort():
            self.sort_by_avg_age()
        return nzo.nzo_id

    @synchronized(NZBQUEUE_LOCK)
    def remove(self, nzo_id, add_to_history=True, save=True, cleanup=True, keep_basic=False, del_files=False):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table.pop(nzo_id)
            nzo.deleted = True
            if cleanup and not nzo.is_gone():
                nzo.status = Status.DELETED
            self.__nzo_list.remove(nzo)

            if add_to_history:
                # Create the history DB instance
                history_db = database.HistoryDB()
                # Add the nzo to the database. Only the path, script and time taken is passed
                # Other information is obtained from the nzo
                history_db.add_history_db(nzo, '', '', 0, '', '')
                history_db.close()
                sabnzbd.history_updated()

            elif cleanup:
                self.cleanup_nzo(nzo, keep_basic, del_files)

            sabnzbd.remove_data(nzo_id, nzo.workpath)
            logging.info('Removed job %s', nzo.final_name)
            if save:
                self.save(nzo)
        else:
            nzo_id = None
        return nzo_id

    def remove_multiple(self, nzo_ids, del_files=False):
        removed = []
        for nzo_id in nzo_ids:
            if self.remove(nzo_id, add_to_history=False, save=False, keep_basic=not del_files, del_files=del_files):
                removed.append(nzo_id)
        # Save with invalid nzo_id, to that only queue file is saved
        self.save('x')

        # Any files left? Otherwise let's disconnect
        if self.actives(grabs=False) == 0 and cfg.autodisconnect():
            # This was the last job, close server connections
            sabnzbd.downloader.Downloader.do.disconnect()

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

    def remove_nzf(self, nzo_id, nzf_id, force_delete=False):
        removed = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzf = nzo.get_nzf_by_id(nzf_id)

            if nzf:
                removed.append(nzf_id)
                nzo.abort_direct_unpacker()
                post_done = nzo.remove_nzf(nzf)
                if post_done:
                    if nzo.finished_files:
                        self.end_job(nzo)
                    else:
                        self.remove(nzo_id, add_to_history=False, keep_basic=False)
                elif force_delete:
                    # Force-remove all trace
                    nzo.bytes -= nzf.bytes
                    nzo.bytes_tried -= (nzf.bytes - nzf.bytes_left)
                    del nzo.files_table[nzf_id]
                    nzo.finished_files.remove(nzf)
            logging.info('Removed NZFs %s from job %s', removed, nzo.final_name)
        return removed

    def pause_multiple_nzo(self, nzo_ids):
        handled = []
        for nzo_id in nzo_ids:
            self.pause_nzo(nzo_id)
            handled.append(nzo_id)
        return handled

    def pause_nzo(self, nzo_id):
        handled = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.pause()
            logging.info("Paused nzo: %s", nzo_id)
            handled.append(nzo_id)
        return handled

    def resume_multiple_nzo(self, nzo_ids):
        handled = []
        for nzo_id in nzo_ids:
            self.resume_nzo(nzo_id)
            handled.append(nzo_id)
        return handled

    @notify_downloader
    def resume_nzo(self, nzo_id):
        handled = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.resume()
            nzo.reset_all_try_lists()
            logging.info("Resumed nzo: %s", nzo_id)
            handled.append(nzo_id)
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
                logging.info('Switching job [%s] %s => [%s] %s', item_id_pos1, item.final_name, item_id_pos2, self.__nzo_list[item_id_pos2].final_name)
                del self.__nzo_list[item_id_pos1]
                self.__nzo_list.insert(item_id_pos2, item)
                return (item_id_pos2, nzo1.priority)
        # If moving failed/no movement took place
        return (-1, nzo1.priority)

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
        logging.info("Sorting by average date... (reversed:%s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_date_cmp, reverse)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_name(self, reverse=False):
        logging.info("Sorting by name... (reversed:%s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_name_cmp, reverse)

    @synchronized(NZBQUEUE_LOCK)
    def sort_by_size(self, reverse=False):
        logging.info("Sorting by size... (reversed:%s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_size_cmp, reverse)

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

    @synchronized(NZBQUEUE_LOCK)
    def __set_priority(self, nzo_id, priority):
        """ Sets the priority on the nzo and places it in the queue at the appropriate position """
        try:
            priority = int_conv(priority)
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

            nzo.set_priority(priority)
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

            logging.info('Set priority=%s for job %s => position=%s ', priority, self.__nzo_table[nzo_id].final_name, pos)
            return pos

        except:
            return -1

    @notify_downloader
    def set_priority(self, nzo_ids, priority):
        try:
            n = -1
            for nzo_id in [item.strip() for item in nzo_ids.split(',')]:
                n = self.__set_priority(nzo_id, priority)
            return n
        except:
            return -1

    def reset_try_lists(self, nzf=None, nzo=None):
        if nzf:
            nzf.reset_try_list()
        if nzo:
            nzo.reset_try_list()

    def reset_all_try_lists(self):
        for nzo in self.__nzo_list:
            nzo.reset_all_try_lists()

    def has_forced_items(self):
        """ Check if the queue contains any Forced
            Priority items to download while paused
        """
        for nzo in self.__nzo_list:
            if nzo.priority == TOP_PRIORITY and nzo.status not in (Status.PAUSED, Status.GRABBING):
                return True
        return False

    def get_article(self, server, servers):
        """ Get next article for jobs in the queue
            Not locked for performance, since it only reads the queue
        """
        for nzo in self.__nzo_list:
            # Not when queue paused and not a forced item
            if nzo.status not in (Status.PAUSED, Status.GRABBING) or nzo.priority == TOP_PRIORITY:
                # Check if past propagation delay, or forced
                if not cfg.propagation_delay() or nzo.priority == TOP_PRIORITY or (nzo.avg_stamp + float(cfg.propagation_delay() * 60)) < time.time():
                    if not nzo.server_in_try_list(server):
                        article = nzo.get_article(server, servers)
                        if article:
                            return article
                    # Stop after first job that wasn't paused/propagating/etc
                    if self.__top_only:
                        return

    def register_article(self, article, found=True):
        """ Register the articles we tried
            Not locked for performance, since it only modifies individual NZOs
        """
        nzf = article.nzf
        nzo = nzf.nzo

        if nzf.deleted:
            logging.debug("Discarding article %s, no longer in queue", article.article)
            return

        file_done, post_done = nzo.remove_article(article, found)

        filename = nzf.filename

        if nzo.is_gone():
            logging.debug('Discarding article %s for deleted job', filename)
        else:
            if file_done:
                if nzo.next_save is None or time.time() > nzo.next_save:
                    nzo.save_to_disk()
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
                    elif filename.lower().endswith('.par2'):
                        # Broken par2 file, try to get another one
                        nzo.promote_par2(nzf)
                    else:
                        if file_has_articles(nzf):
                            logging.warning(T('%s -> Unknown encoding'), filename)
            if post_done:
                self.end_job(nzo)

    def end_job(self, nzo):
        """ Send NZO to the post-processing queue """
        logging.info('Ending job %s', nzo.final_name)

        # Notify assembler to call postprocessor
        if not nzo.deleted:
            nzo.deleted = True
            if nzo.precheck:
                nzo.save_to_disk()
                # Check result
                enough, _ratio = nzo.check_quality()
                if enough:
                    # Enough data present, do real download
                    self.cleanup_nzo(nzo, keep_basic=True)
                    self.send_back(nzo)
                    return
                else:
                    # Not enough data, let postprocessor show it as failed
                    pass
            Assembler.do.process((nzo, None))

    def actives(self, grabs=True):
        """ Return amount of non-paused jobs, optionally with 'grabbing' items
            Not locked for performance, only reads the queue
        """
        n = 0
        for nzo in self.__nzo_list:
            # Ignore any items that are paused
            if grabs and nzo.status == Status.GRABBING:
                n += 1
            elif nzo.status not in (Status.PAUSED, Status.GRABBING):
                n += 1
        return n

    def queue_info(self, search=None, start=0, limit=0):
        """ Return list of queued jobs,
            optionally filtered by 'search' and limited by start and limit.
            Not locked for performance, only reads the queue
        """
        if search:
            search = search.lower()
        bytes_left = 0
        bytes_total = 0
        bytes_left_previous_page = 0
        q_size = 0
        pnfo_list = []
        n = 0

        for nzo in self.__nzo_list:
            if nzo.status not in (Status.PAUSED, Status.CHECKING) or nzo.priority == TOP_PRIORITY:
                b_left = nzo.remaining
                bytes_total += nzo.bytes
                bytes_left += b_left
                q_size += 1
                # We need the number of bytes before the current page
                if n < start:
                    bytes_left_previous_page += b_left

            if (not search) or search in nzo.final_name_pw_clean.lower():
                if (not limit) or (start <= n < start + limit):
                    pnfo_list.append(nzo.gather_info())
                n += 1

        if not search:
            n = len(self.__nzo_list)
        return QNFO(bytes_total, bytes_left, bytes_left_previous_page, pnfo_list, q_size, n)

    def remaining(self):
        """ Return bytes left in the queue by non-paused items
            Not locked for performance, only reads the queue
        """
        bytes_left = 0
        for nzo in self.__nzo_list:
            if nzo.status != 'Paused':
                bytes_left += nzo.remaining
        return bytes_left

    def is_empty(self):
        empty = True
        for nzo in self.__nzo_list:
            if not nzo.futuretype and nzo.status != 'Paused':
                empty = False
                break
        return empty

    def cleanup_nzo(self, nzo, keep_basic=False, del_files=False):
        # Abort DirectUnpack and let it remove files
        nzo.abort_direct_unpacker()
        nzo.purge_data(keep_basic, del_files)
        ArticleCache.do.purge_articles(nzo.saved_articles)

    def stop_idle_jobs(self):
        """ Detect jobs that have zero files left and send them to post processing """
        empty = []
        for nzo in self.__nzo_list:
            if not nzo.futuretype and not nzo.files and nzo.status not in (Status.PAUSED, Status.GRABBING):
                empty.append(nzo)

            # Stall prevention by checking if all servers are in the trylist
            # This is a CPU-cheaper alternative to prevent stalling
            if len(nzo.try_list) == sabnzbd.downloader.Downloader.do.server_nr:
                # Maybe the NZF's need a reset too?
                for nzf in nzo.files:
                    if len(nzf.try_list) == sabnzbd.downloader.Downloader.do.server_nr:
                        # We do not want to reset all article trylists, they are good
                        nzf.reset_try_list()
                # Reset main trylist, minimal performance impact
                nzo.reset_try_list()

        for nzo in empty:
            self.end_job(nzo)

    def pause_on_prio(self, priority):
        for nzo in self.__nzo_list:
            if nzo.priority == priority:
                nzo.pause()

    @notify_downloader
    def resume_on_prio(self, priority):
        for nzo in self.__nzo_list:
            if nzo.priority == priority:
                # Don't use nzo.resume() to avoid resetting job warning flags
                nzo.status = Status.QUEUED

    def pause_on_cat(self, cat):
        for nzo in self.__nzo_list:
            if nzo.cat == cat:
                nzo.pause()

    @notify_downloader
    def resume_on_cat(self, cat):
        for nzo in self.__nzo_list:
            if nzo.cat == cat:
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
