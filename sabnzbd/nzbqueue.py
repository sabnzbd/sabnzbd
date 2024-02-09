#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
import cherrypy._cpreqbody
from typing import List, Dict, Union, Tuple, Optional

import sabnzbd
from sabnzbd.nzbstuff import NzbObject, Article
from sabnzbd.misc import exit_sab, cat_to_opts, int_conv, caller_name, safe_lower, duplicate_warning
from sabnzbd.filesystem import get_admin_path, remove_all, globber_full, remove_file, is_valid_script
from sabnzbd.nzbparser import process_single_nzb
from sabnzbd.panic import panic_queue
from sabnzbd.decorators import NzbQueueLocker
from sabnzbd.constants import (
    QUEUE_FILE_NAME,
    QUEUE_VERSION,
    FUTURE_Q_FOLDER,
    JOB_ADMIN,
    LOW_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
    STOP_PRIORITY,
    VERIFIED_FILE,
    Status,
    IGNORED_FILES_AND_FOLDERS,
    DuplicateStatus,
)

import sabnzbd.cfg as cfg
from sabnzbd.downloader import Server
import sabnzbd.notifier as notifier


class NzbQueue:
    """Singleton NzbQueue"""

    def __init__(self):
        self.__top_only: bool = cfg.top_only()
        self.__nzo_list: List[NzbObject] = []
        self.__nzo_table: Dict[str, NzbObject] = {}

    def read_queue(self, repair: int):
        """Read queue from disk, supporting repair modes
        0 = no repairs
        1 = use existing queue, add missing "incomplete" folders
        2 = Discard all queue admin, reconstruct from "incomplete" folders
        """
        nzo_ids = []
        if repair < 2:
            # Try to process the queue file
            try:
                data = sabnzbd.filesystem.load_admin(QUEUE_FILE_NAME)
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
            nzo = sabnzbd.filesystem.load_data(_id, path, remove=False)
            if not nzo:
                # Try as future job
                path = get_admin_path(folder, future=True)
                nzo = sabnzbd.filesystem.load_data(_id, path)
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
                        nzo = sabnzbd.filesystem.load_data(nzo_id, path, remove=True)
                        if nzo:
                            self.add(nzo, save=True)
                    else:
                        try:
                            remove_file(item)
                        except:
                            pass

    @NzbQueueLocker
    def scan_jobs(self, all_jobs: bool = False, action: bool = True) -> List[str]:
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
            if os.path.isdir(folder) and name not in registered and name not in IGNORED_FILES_AND_FOLDERS:
                if action:
                    logging.info("Repairing job %s", folder)
                    self.repair_job(folder)
                result.append(os.path.basename(folder))
            else:
                if action:
                    logging.info("Skipping repair for job %s", folder)
        return result

    def repair_job(
        self, repair_folder: str, new_nzb: Optional[cherrypy._cpreqbody.Part] = None, password: Optional[str] = None
    ) -> Optional[str]:
        """Reconstruct admin for a single job folder, optionally with new NZB"""
        # Check if folder exists
        if not repair_folder or not os.path.exists(repair_folder):
            return None

        name = os.path.basename(repair_folder)
        admin_path = os.path.join(repair_folder, JOB_ADMIN)

        # If Retry was used and a new NZB was uploaded
        if getattr(new_nzb, "filename", None):
            remove_all(admin_path, "*.gz", keep_folder=True)
            logging.debug("Repair job %s with new NZB (%s)", name, new_nzb.filename)
            _, nzo_ids = sabnzbd.nzbparser.add_nzbfile(new_nzb, nzbname=name, reuse=repair_folder, password=password)
        else:
            # Was this file already post-processed?
            verified = sabnzbd.filesystem.load_data(VERIFIED_FILE, admin_path, remove=False)
            filenames = []
            if not verified or not all(verified[x] for x in verified):
                filenames = globber_full(admin_path, "*.gz")

            if filenames:
                logging.debug("Repair job %s by re-parsing stored NZB", name)
                _, nzo_ids = sabnzbd.nzbparser.add_nzbfile(
                    filenames[0], nzbname=name, reuse=repair_folder, password=password
                )
            else:
                try:
                    logging.debug("Repair job %s without stored NZB", name)
                    nzo = NzbObject(name, password=password, nzbname=name, reuse=repair_folder)
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
        """Send back job to queue after successful pre-check"""
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
        """Save queue, all nzo's or just the specified one"""
        logging.info("Saving queue")

        nzo_ids = []
        # Aggregate nzo_ids and save each nzo
        for nzo in self.__nzo_list[:]:
            if not nzo.removed_from_queue:
                nzo_ids.append(os.path.join(nzo.work_name, nzo.nzo_id))
                if save_nzo is None or nzo is save_nzo:
                    if not nzo.futuretype:
                        # Also includes save_data for NZO
                        nzo.save_to_disk()
                    else:
                        sabnzbd.filesystem.save_data(nzo, nzo.nzo_id, nzo.admin_path)

        sabnzbd.filesystem.save_admin((QUEUE_VERSION, nzo_ids, []), QUEUE_FILE_NAME)

    def set_top_only(self, value):
        self.__top_only = value

    def change_opts(self, nzo_ids: str, pp: int) -> int:
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
            if nzo_id in self.__nzo_table:
                self.__nzo_table[nzo_id].set_pp(pp)
                result += 1
        return result

    def change_script(self, nzo_ids: str, script: str) -> int:
        result = 0
        if (script is None) or is_valid_script(script):
            for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
                if nzo_id in self.__nzo_table:
                    self.__nzo_table[nzo_id].script = script
                    logging.info("Set script=%s for job %s", script, self.__nzo_table[nzo_id].final_name)
                    result += 1
        return result

    def change_cat(self, nzo_ids: str, cat: str) -> int:
        result = 0
        for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
            if nzo_id in self.__nzo_table:
                nzo = self.__nzo_table[nzo_id]
                nzo.cat, pp, nzo.script, prio = cat_to_opts(cat)
                logging.info("Set cat=%s for job %s", cat, nzo.final_name)
                nzo.set_pp(pp)
                self.set_priority(nzo_id, prio)
                # Abort any ongoing unpacking if the category changed
                nzo.abort_direct_unpacker()
                result += 1
        return result

    def change_name(self, nzo_id: str, name: str, password: str = None) -> bool:
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
    def add(self, nzo: NzbObject, save: bool = True, quiet: bool = False) -> str:
        # Can already be set for future jobs
        if not nzo.nzo_id:
            nzo.nzo_id = sabnzbd.filesystem.get_new_id("nzo", nzo.admin_path, self.__nzo_table)

        # If no files are to be downloaded anymore, send to postproc
        if not nzo.files and not nzo.futuretype:
            self.end_job(nzo)
            return nzo.nzo_id

        # Reset try_lists, markers and evaluate the scheduling settings
        nzo.reset_try_list()
        nzo.removed_from_queue = False
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
    def remove(self, nzo_id: str, cleanup: bool = True, delete_all_data: bool = True) -> Optional[NzbObject]:
        """Remove NZO from queue.
        It can be added to history directly.
        Or, we do some clean-up, sometimes leaving some data.
        """
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table.pop(nzo_id)
            logging.info("[%s] Removing job %s", caller_name(), nzo.final_name)

            # Set statuses
            nzo.removed_from_queue = True
            self.__nzo_list.remove(nzo)
            if cleanup:
                nzo.status = Status.DELETED
                nzo.purge_data(delete_all_data=delete_all_data)
            self.save(False)
            return nzo

    @NzbQueueLocker
    def remove_multiple(self, nzo_ids: List[str], delete_all_data=True) -> List[str]:
        """Remove multiple jobs from the queue. Also triggers duplicate handling
        and downloader-disconnect, so intended for external use only!"""
        removed = []
        for nzo_id in nzo_ids:
            if nzo := self.remove(nzo_id, delete_all_data=delete_all_data):
                removed.append(nzo_id)
                # Start an alternative, if available
                self.handle_duplicate_alternatives(nzo, success=False)

        # Any files left? Otherwise let's disconnect
        if not self.actives(grabs=False) and cfg.autodisconnect():
            # This was the last job, close server connections
            sabnzbd.Downloader.disconnect()

        return removed

    @NzbQueueLocker
    def remove_all(self, search: Optional[str] = None) -> List[str]:
        """Remove NZO's that match the search-pattern"""
        nzo_ids = []
        search = safe_lower(search)
        for nzo_id, nzo in self.__nzo_table.items():
            if not search or search in nzo.final_name.lower():
                nzo_ids.append(nzo_id)
        return self.remove_multiple(nzo_ids)

    def remove_nzfs(self, nzo_id: str, nzf_ids: List[str]) -> List[str]:
        removed = []
        if nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]

            for nzf_id in nzf_ids:
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
                    else:
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
    def move_nzf_up_bulk(self, nzo_id: str, nzf_ids: List[str], size: int):
        if nzo_id in self.__nzo_table:
            for _ in range(size):
                self.__nzo_table[nzo_id].move_up_bulk(nzf_ids)

    @NzbQueueLocker
    def move_nzf_top_bulk(self, nzo_id: str, nzf_ids: List[str]):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_top_bulk(nzf_ids)

    @NzbQueueLocker
    def move_nzf_down_bulk(self, nzo_id: str, nzf_ids: List[str], size: int):
        if nzo_id in self.__nzo_table:
            for _ in range(size):
                self.__nzo_table[nzo_id].move_down_bulk(nzf_ids)

    @NzbQueueLocker
    def move_nzf_bottom_bulk(self, nzo_id: str, nzf_ids: List[str]):
        if nzo_id in self.__nzo_table:
            self.__nzo_table[nzo_id].move_bottom_bulk(nzf_ids)

    @NzbQueueLocker
    def sort_queue(self, field: str, direction: Optional[str] = None):
        """Sort queue by field: "name", "size" or "avg_age" or by percentage remaining
        Direction is specified as "desc" or "asc"
        """
        field = field.lower()
        reverse = False
        if safe_lower(direction) == "desc":
            reverse = True

        if field == "name":
            logging.info("Sorting by name (reversed: %s)", reverse)
            sort_function = lambda nzo: nzo.final_name.lower()
        elif field == "size" or field == "bytes":
            logging.info("Sorting by size (reversed: %s)", reverse)
            sort_function = lambda nzo: nzo.bytes
        elif field == "avg_age":
            reverse = not reverse
            logging.info("Sorting by average date... (reversed: %s)", reverse)
            sort_function = lambda nzo: nzo.avg_date
        elif field == "remaining":
            if self.__nzo_list:
                logging.debug("Sorting by percentage downloaded...")
            sort_function = lambda nzo: nzo.remaining / nzo.bytes if nzo.bytes else 1
        else:
            logging.debug("Sort: %s not recognized", field)
            return

        # Apply sort by requested order, then restore priority ordering
        self.__nzo_list.sort(key=sort_function, reverse=reverse)
        self.__nzo_list.sort(key=lambda nzo: nzo.priority, reverse=True)

    def update_sort_order(self):
        """Resorts the queue if it is useful for the selected sort method"""
        auto_sort = cfg.auto_sort()
        if auto_sort and auto_sort.startswith("remaining"):
            self.sort_queue("remaining")

    @NzbQueueLocker
    def __set_priority(self, nzo_id: str, priority: Union[int, str]) -> Optional[int]:
        """Sets the priority on the nzo and places it in the queue at the appropriate position"""
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
    def set_priority(self, nzo_ids: str, priority: int) -> int:
        try:
            n = -1
            for nzo_id in [item.strip() for item in nzo_ids.split(",")]:
                n = self.__set_priority(nzo_id, priority)
            return n
        except:
            return -1

    @staticmethod
    def reset_try_lists(article: Article, remove_fetcher_from_trylist: bool = True):
        """Let article get new fetcher and reset trylists"""
        if remove_fetcher_from_trylist:
            article.remove_from_try_list(article.fetcher)
        article.fetcher = None
        article.tries = 0
        article.nzf.reset_try_list()
        article.nzf.nzo.reset_try_list()

    def has_forced_jobs(self) -> bool:
        """Check if the queue contains any Forced
        Priority jobs to download while paused
        """
        for nzo in self.__nzo_list:
            if nzo.priority == FORCE_PRIORITY and nzo.status not in (Status.PAUSED, Status.GRABBING):
                return True
            # Each time the priority of a job is changed the queue is sorted, so we can
            # assume that if we reach a job below Force priority we can continue
            if nzo.priority < FORCE_PRIORITY:
                return False
        return False

    def get_articles(self, server: Server, servers: List[Server], fetch_limit: int) -> List[Article]:
        """Get next article for jobs in the queue
        Not locked for performance, since it only reads the queue
        """
        for nzo in self.__nzo_list:
            # Not when queue paused, individually paused, or when waiting for propagation
            # Force items will always download
            if (
                not sabnzbd.Downloader.paused
                and nzo.status not in (Status.PAUSED, Status.GRABBING)
                and not nzo.propagation_delay_left
            ) or nzo.priority == FORCE_PRIORITY:
                if not nzo.server_in_try_list(server):
                    if articles := nzo.get_articles(server, servers, fetch_limit):
                        return articles
                # Stop after first job that wasn't paused/propagating/etc
                if self.__top_only:
                    return []
        return []

    def register_article(self, article: Article, success: bool = True):
        """Register the articles we tried
        Not locked for performance, since it only modifies individual NZOs
        """
        nzf = article.nzf
        nzo = nzf.nzo

        if nzo.pp_or_finished or nzf.deleted:
            logging.debug("Discarding article for file %s: deleted or already post-processing", nzf.filename)
            # If this file is needed later (par2 file added back to queue), it would be damaged because
            # we discard this article. So we reset it to be picked up again if needed.
            # But not reset all articles, as it could cause problems for articles still attached to a server.
            article.reset_try_list()
            nzf.reset_try_list()
            return

        articles_left, file_done, post_done = nzo.remove_article(article, success)

        # Write data if file is done or at trigger time
        # Skip if the file is already queued, since all available articles will then be written
        if (
            file_done
            or (article.lowest_partnum and nzf.filename_checked and not nzf.import_finished)
            or (articles_left and (articles_left % sabnzbd.ArticleCache.assembler_write_trigger) == 0)
        ):
            if not nzo.precheck:
                # Only start decoding if we have a filename and type
                # The type is only set if sabctools could decode the article
                if nzf.filename and nzf.type:
                    sabnzbd.Assembler.process(nzo, nzf, file_done)
                elif nzf.filename.lower().endswith(".par2"):
                    # Broken par2 file, try to get another one
                    nzo.promote_par2(nzf)

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

    @NzbQueueLocker
    def end_job(self, nzo: NzbObject):
        """Send NZO to the post-processing queue"""
        # Notify assembler to call postprocessor
        if not nzo.removed_from_queue:
            logging.info("[%s] Ending job %s", caller_name(), nzo.final_name)
            nzo.removed_from_queue = True
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

    def fail_to_history(self, nzo: NzbObject):
        """Fail to history, with all the steps in between"""
        if not nzo.nzo_id:
            self.add(nzo, quiet=True)
        self.remove(nzo.nzo_id, cleanup=False)
        sabnzbd.PostProcessor.process(nzo)

    def actives(self, grabs: bool = True) -> int:
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

    def queue_info(
        self,
        search: Optional[str] = None,
        categories: Optional[List[str]] = None,
        priorities: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        nzo_ids: Optional[List[str]] = None,
        start: int = 0,
        limit: int = 0,
    ) -> Tuple[int, int, int, List[NzbObject], int, int]:
        """Return list of queued jobs, optionally filtered and limited by start and limit.
        Not locked for performance, only reads the queue
        """
        if search:
            search = search.lower()
        bytes_left = 0
        bytes_total = 0
        bytes_left_previous_page = 0
        q_size = 0
        nzo_list = []
        nzos_matched = 0

        for nzo in self.__nzo_list:
            if nzo.status not in (Status.PAUSED, Status.CHECKING) or nzo.priority == FORCE_PRIORITY:
                b_left = nzo.remaining
                bytes_total += nzo.bytes
                bytes_left += b_left
                q_size += 1
                # We need the number of bytes before the current page
                if nzos_matched < start:
                    bytes_left_previous_page += b_left

            # Conditions split up for readability
            if search and search not in nzo.final_name.lower():
                continue
            if categories and nzo.cat not in categories:
                continue
            if priorities and nzo.priority not in priorities:
                continue
            if statuses and nzo.status not in statuses:
                # Propagation status is set only by the API-code, so has to be filtered specially
                if not (Status.PROPAGATING in statuses and nzo.propagation_delay_left):
                    continue
            if nzo_ids and nzo.nzo_id not in nzo_ids:
                continue

            if not limit or start <= nzos_matched < start + limit:
                nzo_list.append(nzo)
            nzos_matched += 1

        if not search and not nzo_ids:
            nzos_matched = len(self.__nzo_list)
        return bytes_total, bytes_left, bytes_left_previous_page, nzo_list, q_size, nzos_matched

    def remaining(self) -> int:
        """Return bytes left in the queue by non-paused items
        Not locked for performance, only reads the queue
        """
        bytes_left = 0
        for nzo in self.__nzo_list:
            if nzo.status != Status.PAUSED:
                bytes_left += nzo.remaining
        return bytes_left

    def is_empty(self) -> bool:
        for nzo in self.__nzo_list:
            if not nzo.futuretype and nzo.status != Status.PAUSED:
                return False
        return True

    def stop_idle_jobs(self):
        """Detect jobs that have zero files left and send them to post processing"""
        # Only check servers that are active
        active_servers = [server for server in sabnzbd.Downloader.servers[:] if server.active]
        nr_servers = len(active_servers)
        empty = []

        if nr_servers <= 0:
            logging.debug("Skipping stop_idle_jobs because no servers are active")
            return

        for nzo in self.__nzo_list:
            if not nzo.futuretype and not nzo.files and nzo.status not in (Status.PAUSED, Status.GRABBING):
                logging.info("Found idle job %s", nzo.final_name)
                empty.append(nzo)

            # Stall prevention by checking if all servers are in the trylist
            # This is a CPU-cheaper alternative to prevent stalling
            if len(nzo.try_list) >= nr_servers:
                # Maybe the NZF's need a reset too?
                for nzf in nzo.files:
                    if nzo.removed_from_queue:
                        break

                    if len(nzf.try_list) >= nr_servers:
                        # Check for articles where all active servers have already been tried
                        for article in nzf.articles[:]:
                            if article.all_servers_in_try_list(active_servers):
                                sabnzbd.NzbQueue.register_article(article, success=False)
                                nzo.increase_bad_articles_counter("missing_articles")

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

    def get_urls(self) -> List[Tuple[str, NzbObject]]:
        """Return list of future-types needing URL"""
        lst = []
        for nzo_id in self.__nzo_table:
            nzo = self.__nzo_table[nzo_id]
            if nzo.futuretype:
                url = nzo.url
                if nzo.futuretype and url.lower().startswith("http"):
                    lst.append((url, nzo))
        return lst

    @NzbQueueLocker
    def have_name_or_md5sum(self, name: str, md5sum: str) -> bool:
        """Check whether this name or md5sum is already
        in the queue or the post-processing queue"""
        lname = name.lower()
        for nzo in self.__nzo_list + sabnzbd.PostProcessor.get_queue():
            # Skip any jobs already marked as duplicate, to prevent double-triggers
            # URL's do not have an MD5!
            if not nzo.duplicate and (
                nzo.final_name.lower() == lname or (nzo.md5sum and md5sum and nzo.md5sum == md5sum)
            ):
                return True
        return False

    @NzbQueueLocker
    def have_duplicate_key(self, duplicate_key: str) -> bool:
        """Check whether this duplicate key is already
        in the queue or the post-processing queue"""
        for nzo in self.__nzo_list + sabnzbd.PostProcessor.get_queue():
            # Skip any jobs already marked as duplicate, to prevent double-triggers
            if not nzo.duplicate and nzo.duplicate_key == duplicate_key:
                return True
        return False

    @NzbQueueLocker
    def handle_duplicate_alternatives(self, finished_nzo: NzbObject, success: bool):
        """Remove matching duplicates if the first job succeeded,
        or start the next alternative if the job failed"""
        if not cfg.no_dupes() and not cfg.no_smart_dupes():
            return

        # Unfortunately we need a copy, since we might remove items from the list
        for nzo in self.__nzo_list[:]:
            if not nzo.duplicate or nzo.duplicate == DuplicateStatus.DUPLICATE_IGNORED:
                continue

            # URL's do not have an MD5!
            if (
                nzo.final_name.lower() == finished_nzo.final_name.lower()
                or (nzo.md5sum and finished_nzo.md5sum and nzo.md5sum == finished_nzo.md5sum)
            ) or (nzo.duplicate_key and finished_nzo.duplicate_key and nzo.duplicate_key == finished_nzo.duplicate_key):
                # Start the next alternative
                if not success:
                    # Don't just resume if only set to tag
                    if (nzo.duplicate == DuplicateStatus.DUPLICATE_ALTERNATIVE and cfg.no_dupes() != 4) or (
                        nzo.duplicate == DuplicateStatus.SMART_DUPLICATE_ALTERNATIVE and cfg.no_smart_dupes() != 4
                    ):
                        logging.info("Resuming duplicate alternative %s for ", nzo.final_name, finished_nzo.final_name)
                        nzo.resume()
                    nzo.duplicate = None
                    return

                # Take action on the alternatives to the duplicate
                #  1 = Discard
                #  2 = Pause
                #  3 = Fail (move to History)
                #  4 = Tag
                smart_duplicate = nzo.duplicate == DuplicateStatus.SMART_DUPLICATE_ALTERNATIVE
                if (not smart_duplicate and cfg.no_dupes() == 1) or (smart_duplicate and cfg.no_smart_dupes() == 1):
                    duplicate_warning(T('Ignoring duplicate NZB "%s"'), nzo.final_name)
                    self.remove(nzo.nzo_id)
                elif (not smart_duplicate and cfg.no_dupes() == 3) or (smart_duplicate and cfg.no_smart_dupes() == 3):
                    duplicate_warning(T('Failing duplicate NZB "%s"'), nzo.final_name)
                    nzo.fail_msg = T("Duplicate NZB")
                    self.fail_to_history(nzo)
                else:
                    # Action set to Pause or Tag, so only adjust the label on the first matching job
                    logging.info("Re-tagging duplicate alternative %s for %s", nzo.final_name, finished_nzo.final_name)
                    if nzo.duplicate == DuplicateStatus.DUPLICATE_ALTERNATIVE:
                        nzo.duplicate = DuplicateStatus.DUPLICATE
                    else:
                        nzo.duplicate = DuplicateStatus.SMART_DUPLICATE
                    return

    def __repr__(self):
        return "<NzbQueue>"
