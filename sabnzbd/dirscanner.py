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
sabnzbd.dirscanner - Scanner for Watched Folder
"""

import os
import time
import logging
import threading

import sabnzbd
from sabnzbd.constants import SCAN_FILE_NAME, VALID_ARCHIVES, VALID_NZB_FILES
import sabnzbd.filesystem as filesystem
import sabnzbd.config as config
import sabnzbd.cfg as cfg


def compare_stat_tuple(tup1, tup2):
    """ Test equality of two stat-tuples, content-related parts only """
    if tup1.st_ino != tup2.st_ino:
        return False
    if tup1.st_size != tup2.st_size:
        return False
    if tup1.st_mtime != tup2.st_mtime:
        return False
    if tup1.st_ctime != tup2.st_ctime:
        return False
    return True


def clean_file_list(inp_list, folder, files):
    """ Remove elements of "inp_list" not found in "files" """
    for path in sorted(inp_list):
        fld, name = os.path.split(path)
        if fld == folder:
            present = False
            for name in files:
                if os.path.join(folder, name) == path:
                    present = True
                    break
            if not present:
                del inp_list[path]


class DirScanner(threading.Thread):
    """Thread that periodically scans a given directory and picks up any
    valid NZB, NZB.GZ ZIP-with-only-NZB and even NZB.GZ named as .NZB
    Candidates which turned out wrong, will be remembered and skipped in
    subsequent scans, unless changed.
    """

    def __init__(self):
        super().__init__()

        self.newdir()
        try:
            dirscan_dir, self.ignored, self.suspected = sabnzbd.load_admin(SCAN_FILE_NAME)
            if dirscan_dir != self.dirscan_dir:
                self.ignored = {}
                self.suspected = {}
        except:
            self.ignored = {}  # Will hold all unusable files and the
            # successfully processed ones that cannot be deleted
            self.suspected = {}  # Will hold name/attributes of suspected candidates

        self.loop_condition = threading.Condition(threading.Lock())
        self.shutdown = False
        self.error_reported = False  # Prevents multiple reporting of missing watched folder
        self.dirscan_dir = cfg.dirscan_dir.get_path()
        self.dirscan_speed = cfg.dirscan_speed() or None  # If set to 0, use None so the wait() is forever
        self.busy = False
        cfg.dirscan_dir.callback(self.newdir)
        cfg.dirscan_speed.callback(self.newspeed)

    def newdir(self):
        """ We're notified of a dir change """
        self.ignored = {}
        self.suspected = {}
        self.dirscan_dir = cfg.dirscan_dir.get_path()
        self.dirscan_speed = cfg.dirscan_speed()

    def newspeed(self):
        """ We're notified of a scan speed change """
        # If set to 0, use None so the wait() is forever
        self.dirscan_speed = cfg.dirscan_speed() or None
        with self.loop_condition:
            self.loop_condition.notify()

    def stop(self):
        """ Stop the dir scanner """
        self.shutdown = True
        with self.loop_condition:
            self.loop_condition.notify()

    def save(self):
        """ Save dir scanner bookkeeping """
        sabnzbd.save_admin((self.dirscan_dir, self.ignored, self.suspected), SCAN_FILE_NAME)

    def run(self):
        """ Start the scanner """
        logging.info("Dirscanner starting up")
        self.shutdown = False

        while not self.shutdown:
            # Wait to be woken up or triggered
            with self.loop_condition:
                self.loop_condition.wait(self.dirscan_speed)
            if self.dirscan_speed and not self.shutdown:
                self.scan()

    def scan(self):
        """ Do one scan of the watched folder """

        def run_dir(folder, catdir):
            try:
                files = os.listdir(folder)
            except OSError:
                if not self.error_reported and not catdir:
                    logging.error(T("Cannot read Watched Folder %s"), filesystem.clip_path(folder))
                    self.error_reported = True
                files = []

            for filename in files:
                if self.shutdown:
                    break
                path = os.path.join(folder, filename)
                if os.path.isdir(path) or path in self.ignored or filename[0] == ".":
                    continue

                if filesystem.get_ext(path) in VALID_NZB_FILES + VALID_ARCHIVES:
                    try:
                        stat_tuple = os.stat(path)
                    except OSError:
                        continue
                else:
                    self.ignored[path] = 1
                    continue

                if path in self.suspected:
                    if compare_stat_tuple(self.suspected[path], stat_tuple):
                        # Suspected file still has the same attributes
                        continue
                    else:
                        del self.suspected[path]

                if stat_tuple.st_size > 0:
                    logging.info("Trying to import %s", path)

                    # Wait until the attributes are stable for 1 second, but give up after 3 sec
                    # This indicates that the file is fully written to disk
                    for n in range(3):
                        time.sleep(1.0)
                        try:
                            stat_tuple_tmp = os.stat(path)
                        except OSError:
                            continue
                        if compare_stat_tuple(stat_tuple, stat_tuple_tmp):
                            break
                        stat_tuple = stat_tuple_tmp
                    else:
                        # Not stable
                        continue

                    # Add the NZB's
                    res, _ = sabnzbd.add_nzbfile(path, catdir=catdir, keep=False)
                    if res < 0:
                        # Retry later, for example when we can't read the file
                        self.suspected[path] = stat_tuple
                    elif res == 0:
                        self.error_reported = False
                    else:
                        self.ignored[path] = 1

            # Remove files from the bookkeeping that are no longer on the disk
            clean_file_list(self.ignored, folder, files)
            clean_file_list(self.suspected, folder, files)

        if not self.busy:
            self.busy = True
            dirscan_dir = self.dirscan_dir
            if dirscan_dir and not sabnzbd.PAUSED_ALL:
                run_dir(dirscan_dir, None)

                try:
                    dirscan_list = os.listdir(dirscan_dir)
                except OSError:
                    if not self.error_reported:
                        logging.error(T("Cannot read Watched Folder %s"), filesystem.clip_path(dirscan_dir))
                        self.error_reported = True
                    dirscan_list = []

                cats = config.get_categories()
                for dd in dirscan_list:
                    dpath = os.path.join(dirscan_dir, dd)
                    if os.path.isdir(dpath) and dd.lower() in cats:
                        run_dir(dpath, dd.lower())
            self.busy = False
