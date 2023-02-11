#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Generator, Set, Optional, Tuple

import sabnzbd
from sabnzbd.constants import SCAN_FILE_NAME, VALID_ARCHIVES, VALID_NZB_FILES
import sabnzbd.filesystem as filesystem
import sabnzbd.config as config
import sabnzbd.cfg as cfg

VALID_EXTENSIONS = set(VALID_NZB_FILES + VALID_ARCHIVES)


def compare_stat_tuple(tup1, tup2):
    """Test equality of two stat-tuples, content-related parts only"""
    if tup1.st_ino != tup2.st_ino:
        return False
    if tup1.st_size != tup2.st_size:
        return False
    if tup1.st_mtime != tup2.st_mtime:
        return False
    if tup1.st_ctime != tup2.st_ctime:
        return False
    return True


def clean_file_list(inp_list, files):
    """Remove elements of "inp_list" not found in "files" """
    for path in set(inp_list.keys()).difference(files):
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
            dirscan_dir, self.ignored, self.suspected = sabnzbd.filesystem.load_admin(SCAN_FILE_NAME)
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
        """We're notified of a dir change"""
        self.ignored = {}
        self.suspected = {}
        self.dirscan_dir = cfg.dirscan_dir.get_path()
        self.dirscan_speed = cfg.dirscan_speed()

    def newspeed(self):
        """We're notified of a scan speed change"""
        # If set to 0, use None so the wait() is forever
        self.dirscan_speed = cfg.dirscan_speed() or None
        with self.loop_condition:
            self.loop_condition.notify()

    def stop(self):
        """Stop the dir scanner"""
        self.shutdown = True
        with self.loop_condition:
            self.loop_condition.notify()

    def save(self):
        """Save dir scanner bookkeeping"""
        sabnzbd.filesystem.save_admin((self.dirscan_dir, self.ignored, self.suspected), SCAN_FILE_NAME)

    def run(self):
        """Start the scanner"""
        logging.info("Dirscanner starting up")
        self.shutdown = False

        while not self.shutdown:
            # Wait to be woken up or triggered
            with self.loop_condition:
                self.loop_condition.wait(self.dirscan_speed)
            if self.dirscan_speed and not self.shutdown:
                self.scan()

    def get_suspected_files(
        self, folder: str, catdir: Optional[str] = None
    ) -> Generator[Tuple[str, Optional[str], os.stat_result], None, None]:
        """Generator listing possible paths to NZB files"""

        if catdir is None:
            cats = config.get_categories()
        else:
            cats = {}

        try:
            with os.scandir(os.path.join(folder, catdir or "")) as it:
                for entry in it:
                    if self.shutdown:
                        break

                    path = entry.path

                    if path in self.ignored:
                        # We still need to know that an ignored file is still present when we clean up
                        yield path, catdir, None
                        continue

                    # If the entry is a catdir then recursion
                    if entry.is_dir():
                        if not catdir and entry.name.lower() in cats:
                            yield from self.get_suspected_files(folder, entry.name)
                        continue

                    if filesystem.get_ext(path) in VALID_EXTENSIONS:
                        try:
                            # https://docs.python.org/3/library/os.html#os.DirEntry.stat
                            # On Windows, the st_ino, st_dev and st_nlink attributes of the stat_result are always set
                            # to zero. Call os.stat() to get these attributes.
                            if sabnzbd.WIN32:
                                stat_tuple = os.stat(path)
                            else:
                                stat_tuple = entry.stat()
                        except OSError:
                            continue
                    else:
                        self.ignored[path] = 1
                        yield path, catdir, None
                        continue

                    if path in self.suspected:
                        if not compare_stat_tuple(self.suspected[path], stat_tuple):
                            # Suspected file attributes have changed
                            del self.suspected[path]

                    yield path, catdir, stat_tuple
        except OSError:
            if not self.error_reported and not catdir:
                logging.error(T("Cannot read Watched Folder %s"), filesystem.clip_path(folder))
                self.error_reported = True

    def when_stable_add_nzbfile(self, path: str, catdir: Optional[str], stat_tuple: os.stat_result):
        """Try and import the NZB but wait until the attributes are stable for 1 second, but give up after 3 sec"""

        logging.info("Trying to import %s", path)

        # Wait until the attributes are stable for 1 second, but give up after 3 sec
        # This indicates that the file is fully written to disk
        for n in range(3):
            with self.loop_condition:
                self.loop_condition.wait(1.0)
            if self.shutdown:
                return

            try:
                stat_tuple_tmp = os.stat(path)
            except OSError:
                continue
            if compare_stat_tuple(stat_tuple, stat_tuple_tmp):
                break
            stat_tuple = stat_tuple_tmp
        else:
            # Not stable
            return

        # Add the NZB's
        res, _ = sabnzbd.nzbparser.add_nzbfile(path, catdir=catdir, keep=False)
        if res < 0:
            # Retry later, for example when we can't read the file
            self.suspected[path] = stat_tuple
        elif res == 0:
            self.error_reported = False
        else:
            self.ignored[path] = 1

    def scan(self):
        """Do one scan of the watched folder"""

        def run_dir(folder):
            files: Set[str] = set()

            with ThreadPoolExecutor() as executor:
                for path, catdir, stat_tuple in self.get_suspected_files(folder):
                    if self.shutdown:
                        break

                    files.add(path)

                    if path in self.ignored or path in self.suspected:
                        continue

                    if stat_tuple.st_size > 0:
                        executor.submit(self.when_stable_add_nzbfile, path, catdir, stat_tuple)

            if not self.shutdown:
                # Remove files from the bookkeeping that are no longer on the disk
                clean_file_list(self.ignored, files)
                clean_file_list(self.suspected, files)

        if not self.busy:
            self.busy = True
            dirscan_dir = self.dirscan_dir
            if dirscan_dir and not sabnzbd.PAUSED_ALL:
                run_dir(dirscan_dir)
            self.busy = False
