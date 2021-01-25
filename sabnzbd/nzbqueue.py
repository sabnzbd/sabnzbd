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

"""
sabnzbd.nzbqueue - nzb queue
"""

import os
import logging
import time
import datetime
import functools
from typing import List, Dict, Union, Tuple, Optional

import sabnzbd
from sabnzbd.nzbstuff import NzbObject, Article
from sabnzbd.misc import exit_sab, cat_to_opts, int_conv, caller_name, cmp, safe_lower
from sabnzbd.filesystem import get_admin_path, remove_all, globber_full, remove_file, is_valid_script
from sabnzbd.nzbparser import process_single_nzb
from sabnzbd.panic import panic_queue
from sabnzbd.decorators import NzbQueueLocker
from sabnzbd.constants import (
    QUEUE_FILE_NAME,
    QUEUE_VERSION,
    FUTURE_Q_FOLDER,
    JOB_ADMIN,
    DEFAULT_PRIORITY,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
    REPAIR_PRIORITY,
    STOP_PRIORITY,
    VERIFIED_FILE,
    Status,
    IGNORED_FOLDERS,
    QNFO,
    DIRECT_WRITE_TRIGGER,
)

import sabnzbd.cfg as cfg
from sabnzbd.downloader import Server
from sabnzbd.assembler import file_has_articles
import sabnzbd.notifier as notifier


class NzbQueue:
    """ Singleton NzbQueue """

    def __init__(self):
        self.__top_only: bool = cfg.top_only()
        self.__nzo_list: List[NzbObject] = []
        self.__nzo_table: Dict[str, NzbObject] = {}

    def read_queue(self, repair):
        """Read queue from disk, supporting repair modes
        0 = no repairs
        1 = use existing queue, add missing "incomplete" folders
        2 = Discard all queue admin, reconstruct from "incomplete" folders
        """
        nzo_ids = []
        if repair < 2:
            # Try to process the queue file
            try:
                data = sabnzbd.load_admin(QUEUE_FILE_NAME)
                if data:
                    queue_vers, nzo_ids, _ = data
                    if not queue_vers == QUEUE_VERSION:
                        nzo_ids = []
                        logging.error(T("Incompatible queuefile found, cannot proceed"))
                        if not repair:
                            panic_queue(os.path.join(cfg.admin_dir.get_path(), QUEUE_FILE_NAME))
                            exit_sab(2)
            except:
                nzo_ids = []
                logging.error(
                    T("Error loading %s, corrupt file detected"),
                    os.path.join(cfg.admin_dir.get_path(), QUEUE_FILE_NAME),
                )

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
            logging.info("Starting queue repair")
            self.scan_jobs(not folders)
            # Handle any lost future jobs
            for item in globber_full(os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)):
                path, nzo_id = os.path.split(item)
                if nzo_id not in self.__nzo_table:
                    if nzo_id.startswith("SABnzbd_nzo"):
                        nzo = sabnzbd.load_data(nzo_id, path, remove=True)
                        if nzo:
                            self.add(nzo, save=True)
                    else:
                        try:
                            remove_file(item)
                        except:
                            pass

    @NzbQueueLocker
    def scan_jobs(self, all_jobs=False, action=True):
        """Scan "incomplete" for missing folders,
        'all' is True: Include active folders
        'action' is True, do the recovery action
        returns list of orphaned folders
        """
        result = []
        # Folders from the download queue
        if all_jobs:
            registered = []
        else:
            registered = [nzo.work_name for nzo in self.__nzo_list]

        # Retryable folders from History
        items = sabnzbd.api.build_history()[0]
        # Anything waiting or active or retryable is a known item
        registered.extend(
            [
                os.path.basename(item["path"])
                for item in items
                if item["retry"] or item["loaded"] or item["status"] == Status.QUEUED
            ]
        )

        # Repair unregistered folders
        for folder in globber_full(cfg.download_dir.get_path()):
            name = os.path.basename(folder)
            if os.path.isdir(folder) and name not in registered and name not in IGNORED_FOLDERS:
                if action:
                    logging.info("Repairing job %s", folder)
                    self.repair_job(folder)
                result.append(os.path.basename(folder))
            else:
                if action:
                    logging.info("Skipping repair for job %s", folder)
        return result

    def repair_job(self, repair_folder, new_nzb=None, password=None):
        """ Reconstruct admin for a single job folder, optionally with new NZB """
        # Check if folder exists
        if not repair_folder or not os.path.exists(repair_folder):
            return None

        name = os.path.basename(repair_folder)
        admin_path = os.path.join(repair_folder, JOB_ADMIN)

        # If Retry was used and a new NZB was uploaded
        if getattr(new_nzb, "filename", None):
            remove_all(admin_path, "*.gz", keep_folder=True)
            logging.debug("Repair job %s with new NZB (%s)", name, new_nzb.filename)
            _, nzo_ids = sabnzbd.add_nzbfile(new_nzb, nzbname=name, reuse=repair_folder, password=password)
        else:
            # Was this file already post-processed?
            verified = sabnzbd.load_data(VERIFIED_FILE, admin_path, remove=False)
            filenames = []
            if not verified or not all(verified[x] for x in verified):
                filenames = globber_full(admin_path, "*.gz")

            if filenames:
                logging.debug("Repair job %s by re-parsing stored NZB", name)
                _, nzo_ids = sabnzbd.add_nzbfile(filenames[0], nzbname=name, reuse=repair_folder, password=password)
            else:
                try:
                    logging.debug("Repair job %s without stored NZB", name)
                    nzo = NzbObject(name, nzbname=name, reuse=repair_folder)
                    nzo.password = password
                    self.add(nzo)
                    nzo_ids = [nzo.nzo_id]
                except:
                    # NzoObject can throw exceptions if duplicate or unwanted etc
                    logging.info("Skipping %s due to exception", name, exc_info=True)
                    nzo_ids = []

        # Return None if we could not add anything
        if nzo_ids:
            return nzo_ids[0]
        return None

    @NzbQueueLocker
    def send_back(self, old_nzo: NzbObject):
        """ Send back job to queue after successful pre-check """
        try:
            nzb_path = globber_full(old_nzo.admin_path, "*.gz")[0]
        except:
            logging.info("Failed to find NZB file after pre-check (%s)", old_nzo.nzo_id)
            return

        # Store old position and create new NZO
        old_position = self.__nzo_list.index(old_nzo)
        res, nzo_ids = process_single_nzb(
            old_nzo.filename, nzb_path, keep=True, reuse=old_nzo.download_path, nzo_id=old_nzo.nzo_id
        )
        if res == 0 and nzo_ids:
            # Swap to old position
            new_nzo = self.get_nzo(nzo_ids[0])
            self.__nzo_list.remove(new_nzo)
            self.__nzo_list.insert(old_position, new_nzo)
            # Reset reuse flag to make pause/abort on encryption possible
            self.__nzo_table[nzo_ids[0]].reuse = None

    @NzbQueueLocker
    def save(self, save_nzo: Union[NzbObject, None, bool] = None):
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
                        sabnzbd.save_data(nzo, nzo.nzo_id, nzo.admin_path)

        sabnzbd.save_admin((QUEUE_VERSION, nzo_ids, []), QUEUE_FILE_NAME)

    def set_top_only(self, value):
        self.__top_only = value

    def generate_future(self, msg, pp=None, script=None, cat=None, url=None, priority=DEFAULT_PRIORITY, nzbname=None):
        """ Create and return a placeholder nzo object """
        logging.debug("Creating placeholder NZO")
        future_nzo = NzbObject(
            filename=msg,
            pp=pp,
            script=script,
            futuretype=True,
            cat=cat,
            url=url,
            priority=priority,
            nzbname=nzbname,
            status=Status.GRABBING,
        )
        self.add(future_nzo)
        return future_nzo

    def change_opts(self, nzo_ids: str, pp: int) -> int:
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
            if nzo_id in self.__nzo_table:
                self.__nzo_table[nzo_id].set_pp(pp)
                result += 1
        return result

    def change_script(self, nzo_ids: str, script: str) -> int:
        result = 0
        if is_valid_script(script):
            for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
                if nzo_id in self.__nzo_table:
                    self.__nzo_table[nzo_id].script = script
                    logging.info("Set script=%s for job %s", script, self.__nzo_table[nzo_id].final_name)
                    result += 1
        return result

    def change_cat(self, nzo_ids: str, cat: str, explicit_priority=None):
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
            if nzo_id in self.__nzo_table:
                nzo = self.__nzo_table[nzo_id]
                nzo.cat, pp, nzo.script, prio = cat_to_opts(cat)
                logging.info("Set cat=%s for job %s", cat, nzo.final_name)
                nzo.set_pp(pp)
                if explicit_priority is None:
                    self.set_priority(nzo_id, prio)
                # Abort any ongoing unpacking if the category changed
                nzo.abort_direct_unpacker()
                result += 1
        return result

    def change_name(self, nzo_id: str, name: str, password: str = None):
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            logging.info("Renaming %s to %s", nzo.final_name, name)
            # Abort any ongoing unpacking if the name changed (dirs change)
            nzo.abort_direct_unpacker()
            if not nzo.futuretype:
                nzo.set_final_name_and_scan_password(name, password)
            else:
                # Reset url fetch wait time
                nzo.url_wait = None
                nzo.url_tries = 0
            return True
        else:
            return False

    def get_nzo(self, nzo_id) -> Optional[NzbObject]:
        if nzo_id in self.__nzo_table:
            return self.__nzo_table[nzo_id]
        else:
            return None

    @NzbQueueLocker
    def add(self, nzo: NzbObject, save=True, quiet=False) -> str:
        if not nzo.nzo_id:
            nzo.nzo_id = sabnzbd.get_new_id("nzo", nzo.admin_path, self.__nzo_table)

        # If no files are to be downloaded anymore, send to postproc
        if not nzo.files and not nzo.futuretype:
            self.end_job(nzo)
            return nzo.nzo_id

        # Reset try_lists, markers and evaluate the scheduling settings
        nzo.reset_try_list()
        nzo.deleted = False
        priority = nzo.priority
        if sabnzbd.Scheduler.analyse(False, priority):
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

        if not (quiet or nzo.status == Status.FETCHING):
            notifier.send_notification(T("NZB added to queue"), nzo.filename, "download", nzo.cat)

        if not quiet and cfg.auto_sort():
            try:
                field, direction = cfg.auto_sort().split()
                self.sort_queue(field, direction)
            except ValueError:
                pass
        return nzo.nzo_id

    @NzbQueueLocker
    def remove(self, nzo_id: str, cleanup=True, delete_all_data=True):
        """Remove NZO from queue.
        It can be added to history directly.
        Or, we do some clean-up, sometimes leaving some data.
        """
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table.pop(nzo_id)
            logging.info("[%s] Removing job %s", caller_name(), nzo.final_name)

            # Set statuses
            nzo.deleted = True
            if cleanup and not nzo.is_gone():
                nzo.status = Status.DELETED
            self.__nzo_list.remove(nzo)

            if cleanup:
                nzo.purge_data(delete_all_data=delete_all_data)
            self.save(False)
            return nzo_id
        return None

    @NzbQueueLocker
    def remove_multiple(self, nzo_ids: List[str], delete_all_data=True) -> List[str]:
        removed = []
        for nzo_id in nzo_ids:
            if self.remove(nzo_id, delete_all_data=delete_all_data):
                removed.append(nzo_id)

        # Any files left? Otherwise let's disconnect
        if self.actives(grabs=False) == 0 and cfg.autodisconnect():
            # This was the last job, close server connections
            sabnzbd.Downloader.disconnect()

        return removed

    @NzbQueueLocker
    def remove_all(self, search: str = "") -> List[str]:
        """ Remove NZO's that match the search-pattern """
        nzo_ids = []
        search = safe_lower(search)
        for nzo_id, nzo in self.__nzo_table.items():
            if not search or search in nzo.final_name.lower():
                nzo_ids.append(nzo_id)
        return self.remove_multiple(nzo_ids)

    def remove_nzf(self, nzo_id: str, nzf_id: str, force_delete=False) -> List[str]:
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
                        self.remove(nzo_id)
                elif force_delete:
                    # Force-remove all trace and update counters
                    nzo.bytes -= nzf.bytes
                    nzo.bytes_tried -= nzf.bytes - nzf.bytes_left
                    if nzf.is_par2 or sabnzbd.par2file.is_parfile(nzf.filename):
                        nzo.bytes_par2 -= nzf.bytes
                    del nzo.files_table[nzf_id]
                    nzo.finished_files.remove(nzf)
            logging.info("Removed NZFs %s from job %s", removed, nzo.final_name)
        return removed

    def pause_multiple_nzo(self, nzo_ids: List[str]) -> List[str]:
        handled = []
        for nzo_id in nzo_ids:
            self.pause_nzo(nzo_id)
            handled.append(nzo_id)
        return handled

    def pause_nzo(self, nzo_id: str) -> List[str]:
        handled = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.pause()
            logging.info("Paused nzo: %s", nzo_id)
            handled.append(nzo_id)
        return handled

    def resume_multiple_nzo(self, nzo_ids: List[str]) -> List[str]:
        handled = []
        for nzo_id in nzo_ids:
            self.resume_nzo(nzo_id)
            handled.append(nzo_id)
        return handled

    @NzbQueueLocker
    def resume_nzo(self, nzo_id: str) -> List[str]:
        handled = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            nzo.resume()
            logging.info("Resumed nzo: %s", nzo_id)
            handled.append(nzo_id)
        return handled

    @NzbQueueLocker
    def switch(self, item_id_1: str, item_id_2: str) -> Tuple[int, int]:
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
            return -1, 0

        if nzo1 == nzo2:
            return -1, 0

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
        for i in range(len(self.__nzo_list)):
            if item_id_1 == self.__nzo_list[i].nzo_id:
                item_id_pos1 = i
            elif item_id_2 == self.__nzo_list[i].nzo_id:
                item_id_pos2 = i
            if (item_id_pos1 > -1) and (item_id_pos2 > -1):
                item = self.__nzo_list[item_id_pos1]
                logging.info(
                    "Switching job [%s] %s => [%s] %s",
                    item_id_pos1,
                    item.final_name,
                    item_id_pos2,
                    self.__nzo_list[item_id_pos2].final_name,
                )
                del self.__nzo_list[item_id_pos1]
                self.__nzo_list.insert(item_id_pos2, item)
                return item_id_pos2, nzo1.priority
        # If moving failed/no movement took place
        return -1, nzo1.priority

    @NzbQueueLocker
    def move_up_bulk(self, nzo_id, nzf_ids, size):
        if nzo_id in self.__nzo_table:
            for unused in range(size):
                self.__nzo_table[nzo_id].move_up_bulk(nzf_ids)

    @NzbQueueLocker
    def move_top_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_top_bulk(nzf_ids)

    @NzbQueueLocker
    def move_down_bulk(self, nzo_id, nzf_ids, size):
        if nzo_id in self.__nzo_table:
            for unused in range(size):
                self.__nzo_table[nzo_id].move_down_bulk(nzf_ids)

    @NzbQueueLocker
    def move_bottom_bulk(self, nzo_id, nzf_ids):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_bottom_bulk(nzf_ids)

    @NzbQueueLocker
    def sort_by_avg_age(self, reverse=False):
        logging.info("Sorting by average date... (reversed: %s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_date_cmp, reverse)

    @NzbQueueLocker
    def sort_by_name(self, reverse=False):
        logging.info("Sorting by name... (reversed: %s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_name_cmp, reverse)

    @NzbQueueLocker
    def sort_by_size(self, reverse=False):
        logging.info("Sorting by size... (reversed: %s)", reverse)
        self.__nzo_list = sort_queue_function(self.__nzo_list, _nzo_size_cmp, reverse)

    def sort_queue(self, field, reverse=None):
        """Sort queue by field: "name", "size" or "avg_age"
        Direction is specified as "desc"/True or "asc"/False
        """
        if isinstance(reverse, str):
            if reverse.lower() == "desc":
                reverse = True
            else:
                reverse = False
        if reverse is None:
            reverse = False
        if field.lower() == "name":
            self.sort_by_name(reverse)
        elif field.lower() == "size" or field.lower() == "bytes":
            self.sort_by_size(reverse)
        elif field.lower() == "avg_age":
            self.sort_by_avg_age(not reverse)
        else:
            logging.debug("Sort: %s not recognized", field)

    @NzbQueueLocker
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
            for i in range(len(self.__nzo_list)):
                if nzo_id == self.__nzo_list[i].nzo_id:
                    nzo_id_pos1 = i
                    break

            # Don't change priority and order if priority is the same as asked
            if priority == self.__nzo_list[nzo_id_pos1].priority:
                return nzo_id_pos1

            nzo.set_priority(priority)
            if sabnzbd.Scheduler.analyse(False, priority) and nzo.status in (
                Status.CHECKING,
                Status.DOWNLOADING,
                Status.QUEUED,
            ):
                nzo.status = Status.PAUSED
            elif nzo.status == Status.PAUSED:
                nzo.status = Status.QUEUED
            nzo.save_to_disk()

            if nzo_id_pos1 != -1:
                del self.__nzo_list[nzo_id_pos1]
                if priority == FORCE_PRIORITY:
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

            logging.info(
                "Set priority=%s for job %s => position=%s ", priority, self.__nzo_table[nzo_id].final_name, pos
            )
            return pos

        except:
            return -1

    @NzbQueueLocker
    def set_priority(self, nzo_ids, priority):
        try:
            n = -1
            for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
                n = self.__set_priority(nzo_id, priority)
            return n
        except:
            return -1

    @staticmethod
    def reset_try_lists(article: Article, article_reset=True):
        """ Let article get new fetcher and reset trylists """
        article.fetcher = None
        if article_reset:
            article.reset_try_list()
        article.nzf.reset_try_list()
        article.nzf.nzo.reset_try_list()

    def has_forced_items(self):
        """Check if the queue contains any Forced
        Priority items to download while paused
        """
        for nzo in self.__nzo_list:
            if nzo.priority == FORCE_PRIORITY and nzo.status not in (Status.PAUSED, Status.GRABBING):
                return True
        return False

    def get_article(self, server: Server, servers: List[Server]) -> Optional[Article]:
        """Get next article for jobs in the queue
        Not locked for performance, since it only reads the queue
        """
        # Pre-calculate propagation delay
        propagation_delay = float(cfg.propagation_delay() * 60)
        for nzo in self.__nzo_list:
            # Not when queue paused and not a forced item
            if nzo.status not in (Status.PAUSED, Status.GRABBING) or nzo.priority == FORCE_PRIORITY:
                # Check if past propagation delay, or forced
                if (
                    not propagation_delay
                    or nzo.priority == FORCE_PRIORITY
                    or (nzo.avg_stamp + propagation_delay) < time.time()
                ):
                    if not nzo.server_in_try_list(server):
                        article = nzo.get_article(server, servers)
                        if article:
                            return article
                    # Stop after first job that wasn't paused/propagating/etc
                    if self.__top_only:
                        return

    def register_article(self, article: Article, success: bool = True):
        """Register the articles we tried
        Not locked for performance, since it only modifies individual NZOs
        """
        nzf = article.nzf
        nzo = nzf.nzo

        if nzf.deleted:
            logging.debug("Discarding article %s, no longer in queue", article.article)
            return

        articles_left, file_done, post_done = nzo.remove_article(article, success)

        if nzo.is_gone():
            logging.debug("Discarding article for file %s, no longer in queue", nzf.filename)
        else:
            # Write data if file is done or at trigger time
            if file_done or (articles_left and (articles_left % DIRECT_WRITE_TRIGGER) == 0):
                if not nzo.precheck:
                    # Only start decoding if we have a filename and type
                    # The type is only set if sabyenc could decode the article
                    if nzf.filename and nzf.type:
                        sabnzbd.Assembler.process(nzo, nzf, file_done)
                    elif nzf.filename.lower().endswith(".par2"):
                        # Broken par2 file, try to get another one
                        nzo.promote_par2(nzf)
                    else:
                        if file_has_articles(nzf):
                            logging.warning(T("%s -> Unknown encoding"), nzf.filename)

            # Save bookkeeping in case of crash
            if file_done and (nzo.next_save is None or time.time() > nzo.next_save):
                nzo.save_to_disk()
                sabnzbd.BPSMeter.save()
                if nzo.save_timeout is None:
                    nzo.next_save = None
                else:
                    nzo.next_save = time.time() + nzo.save_timeout

            # Remove post from Queue
            if post_done:
                nzo.set_download_report()
                self.end_job(nzo)

    def end_job(self, nzo: NzbObject):
        """ Send NZO to the post-processing queue """
        # Notify assembler to call postprocessor
        if not nzo.deleted:
            logging.info("[%s] Ending job %s", caller_name(), nzo.final_name)
            nzo.deleted = True
            if nzo.precheck:
                nzo.save_to_disk()
                # Check result
                enough, _ = nzo.check_availability_ratio()
                if enough:
                    # Enough data present, do real download
                    self.send_back(nzo)
                    return
                else:
                    # Not enough data, let postprocessor show it as failed
                    pass
            sabnzbd.Assembler.process(nzo)

    def actives(self, grabs=True) -> int:
        """Return amount of non-paused jobs, optionally with 'grabbing' items
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

    def queue_info(self, search=None, nzo_ids=None, start=0, limit=0):
        """Return list of queued jobs,
        optionally filtered by 'search' and 'nzo_ids', and limited by start and limit.
        Not locked for performance, only reads the queue
        """
        if search:
            search = search.lower()
        if nzo_ids:
            nzo_ids = nzo_ids.split(",")
        bytes_left = 0
        bytes_total = 0
        bytes_left_previous_page = 0
        q_size = 0
        pnfo_list = []
        n = 0

        for nzo in self.__nzo_list:
            if nzo.status not in (Status.PAUSED, Status.CHECKING) or nzo.priority == FORCE_PRIORITY:
                b_left = nzo.remaining
                bytes_total += nzo.bytes
                bytes_left += b_left
                q_size += 1
                # We need the number of bytes before the current page
                if n < start:
                    bytes_left_previous_page += b_left

            if (not search) or search in nzo.final_name.lower():
                if (not nzo_ids) or nzo.nzo_id in nzo_ids:
                    if (not limit) or (start <= n < start + limit):
                        pnfo_list.append(nzo.gather_info())
                    n += 1

        if not search and not nzo_ids:
            n = len(self.__nzo_list)
        return QNFO(bytes_total, bytes_left, bytes_left_previous_page, pnfo_list, q_size, n)

    def remaining(self):
        """Return bytes left in the queue by non-paused items
        Not locked for performance, only reads the queue
        """
        bytes_left = 0
        for nzo in self.__nzo_list:
            if nzo.status != Status.PAUSED:
                bytes_left += nzo.remaining
        return bytes_left

    def is_empty(self):
        empty = True
        for nzo in self.__nzo_list:
            if not nzo.futuretype and nzo.status != Status.PAUSED:
                empty = False
                break
        return empty

    def stop_idle_jobs(self):
        """ Detect jobs that have zero files left and send them to post processing """
        empty = []
        for nzo in self.__nzo_list:
            if not nzo.futuretype and not nzo.files and nzo.status not in (Status.PAUSED, Status.GRABBING):
                logging.info("Found idle job %s", nzo.final_name)
                empty.append(nzo)

            # Stall prevention by checking if all servers are in the trylist
            # This is a CPU-cheaper alternative to prevent stalling
            if len(nzo.try_list) == sabnzbd.Downloader.server_nr:
                # Maybe the NZF's need a reset too?
                for nzf in nzo.files:
                    if len(nzf.try_list) == sabnzbd.Downloader.server_nr:
                        # We do not want to reset all article trylists, they are good
                        logging.info("Resetting bad trylist for file %s in job %s", nzf.filename, nzo.final_name)
                        nzf.reset_try_list()

                # Reset main trylist, minimal performance impact
                logging.info("Resetting bad trylist for job %s", nzo.final_name)
                nzo.reset_try_list()

        for nzo in empty:
            self.end_job(nzo)

    def pause_on_prio(self, priority: int):
        for nzo in self.__nzo_list:
            if nzo.priority == priority:
                nzo.pause()

    @NzbQueueLocker
    def resume_on_prio(self, priority: int):
        for nzo in self.__nzo_list:
            if nzo.priority == priority:
                # Don't use nzo.resume() to avoid resetting job warning flags
                nzo.status = Status.QUEUED

    def pause_on_cat(self, cat: str):
        for nzo in self.__nzo_list:
            if nzo.cat == cat:
                nzo.pause()

    @NzbQueueLocker
    def resume_on_cat(self, cat: str):
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
                if nzo.futuretype and url.lower().startswith("http"):
                    lst.append((url, nzo))
        return lst

    def __repr__(self):
        return "<NzbQueue>"


def _nzo_date_cmp(nzo1: NzbObject, nzo2: NzbObject):
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


def sort_queue_function(nzo_list: List[NzbObject], method, reverse: bool) -> List[NzbObject]:
    ultra_high_priority = [nzo for nzo in nzo_list if nzo.priority == REPAIR_PRIORITY]
    super_high_priority = [nzo for nzo in nzo_list if nzo.priority == FORCE_PRIORITY]
    high_priority = [nzo for nzo in nzo_list if nzo.priority == HIGH_PRIORITY]
    normal_priority = [nzo for nzo in nzo_list if nzo.priority == NORMAL_PRIORITY]
    low_priority = [nzo for nzo in nzo_list if nzo.priority == LOW_PRIORITY]

    ultra_high_priority.sort(key=functools.cmp_to_key(method), reverse=reverse)
    super_high_priority.sort(key=functools.cmp_to_key(method), reverse=reverse)
    high_priority.sort(key=functools.cmp_to_key(method), reverse=reverse)
    normal_priority.sort(key=functools.cmp_to_key(method), reverse=reverse)
    low_priority.sort(key=functools.cmp_to_key(method), reverse=reverse)

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
