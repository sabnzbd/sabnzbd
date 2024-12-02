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
sabnzbd.dirscanner - Scanner for Watched Folder
"""

import asyncio
import os
import logging
import threading
from typing import Generator, Set, Optional, Tuple

import sabnzbd
from sabnzbd.constants import SCAN_FILE_NAME, VALID_ARCHIVES, VALID_NZB_FILES, AddNzbFileResult
import sabnzbd.filesystem as filesystem
import sabnzbd.config as config
import sabnzbd.cfg as cfg

DIR_SCANNER_LOCK = threading.RLock()
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


async def clean_file_list(inp_list, files):
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

        # Create loop right away, so socks5 proxy doesn't break it
        self.loop = asyncio.new_event_loop()
        self.scanner_task: Optional[asyncio.Task] = None
        self.lock: Optional[asyncio.Lock] = None  # Prevents concurrent scans
        self.error_reported = False  # Prevents multiple reporting of missing watched folder
        self.dirscan_dir = cfg.dirscan_dir.get_path()
        self.dirscan_speed = cfg.dirscan_speed()
        cfg.dirscan_dir.callback(self.newdir)
        cfg.dirscan_speed.callback(self.newspeed)

        try:
            dirscan_dir, self.ignored, self.suspected = sabnzbd.filesystem.load_admin(SCAN_FILE_NAME)
            if dirscan_dir != self.dirscan_dir:
                self.ignored = {}
                self.suspected = {}
        except:
            self.ignored = {}  # Will hold all unusable files and the
            # successfully processed ones that cannot be deleted
            self.suspected = {}  # Will hold name/attributes of suspected candidates

    def newdir(self):
        """We're notified of a dir change"""
        self.ignored = {}
        self.suspected = {}
        self.dirscan_dir = cfg.dirscan_dir.get_path()

        self.start_scanner()

    def newspeed(self):
        """We're notified of a scan speed change"""
        self.dirscan_speed = cfg.dirscan_speed()

        self.start_scanner()

    def stop(self):
        """Stop the dir scanner"""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.shutdown(), self.loop)

    def save(self):
        """Save dir scanner bookkeeping"""
        sabnzbd.filesystem.save_admin((self.dirscan_dir, self.ignored, self.suspected), SCAN_FILE_NAME)

    def run(self):
        """Start the scanner"""
        logging.info("Dirscanner starting up")
        try:
            self.start_scanner()
            self.loop.run_forever()
        finally:
            self.loop.close()

    def start_scanner(self):
        """Start the scanner if it is not already running"""
        with DIR_SCANNER_LOCK:
            if not self.loop:
                logging.debug("Can not start scanner because loop not found")
                return

            if not self.scanner_task or self.scanner_task.done():
                self.scanner_task = asyncio.run_coroutine_threadsafe(self.scanner(), self.loop)

    def get_suspected_files(
        self, folder: str, catdir: Optional[str] = None
    ) -> Generator[Tuple[str, Optional[str], Optional[os.stat_result]], None, None]:
        """Generator listing possible paths to NZB files"""

        if catdir is None:
            cats = config.get_categories()
        else:
            cats = {}

        try:
            with os.scandir(os.path.join(folder, catdir or "")) as it:
                for entry in it:
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
                            if sabnzbd.WINDOWS:
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
        except:
            if not self.error_reported and not catdir:
                logging.error(T("Cannot read Watched Folder %s"), filesystem.clip_path(folder))
                logging.info("Traceback: ", exc_info=True)
                self.error_reported = True

    async def when_stable_add_nzbfile(self, path: str, catdir: Optional[str], stat_tuple: os.stat_result):
        """Try and import the NZB but wait until the attributes are stable for 1 second, but give up after 3 sec"""
        logging.info("Trying to import %s", path)

        # Wait until the attributes are stable for 1 second, but give up after 3 sec
        # This indicates that the file is fully written to disk
        for n in range(3):
            await asyncio.sleep(1.0)

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
        if res is AddNzbFileResult.RETRY or res is AddNzbFileResult.ERROR:
            # Retry later, for example when we can't read the file
            self.suspected[path] = stat_tuple
        elif res is AddNzbFileResult.OK:
            self.error_reported = False
        else:
            self.ignored[path] = 1

    def scan(self):
        """Schedule a scan of the watched folder"""
        if not self.loop:
            return

        if not (dirscan_dir := self.dirscan_dir):
            return

        asyncio.run_coroutine_threadsafe(self.scan_async(dirscan_dir), self.loop)

    async def scan_async(self, dirscan_dir: str):
        """Do one scan of the watched folder"""
        # On Python 3.8 we first need an event loop before we can create a asyncio.Lock
        if not self.lock:
            with DIR_SCANNER_LOCK:
                self.lock = asyncio.Lock()

        async with self.lock:
            if sabnzbd.PAUSED_ALL:
                return

            files: Set[str] = set()
            futures: Set[asyncio.Task] = set()

            for path, catdir, stat_tuple in self.get_suspected_files(dirscan_dir):
                files.add(path)

                if path in self.ignored or path in self.suspected:
                    continue

                if stat_tuple.st_size > 0:
                    futures.add(asyncio.create_task(self.when_stable_add_nzbfile(path, catdir, stat_tuple)))
                    await asyncio.sleep(0)

            # Remove files from the bookkeeping that are no longer on the disk
            # Wait for the paths found in this scan to finish
            await asyncio.gather(clean_file_list(self.ignored, files), clean_file_list(self.suspected, files), *futures)

    async def scanner(self):
        """Periodically scan the directory and add NZB files to the queue"""
        while True:
            if not (dirscan_speed := self.dirscan_speed):
                break

            if not (dirscan_dir := self.dirscan_dir):
                break

            await self.scan_async(dirscan_dir)

            await asyncio.sleep(dirscan_speed)

    async def shutdown(self):
        """Cancel all tasks and stop the loop"""
        loop = asyncio.get_event_loop()

        # Get all tasks except for this one
        tasks = filter(lambda task: task is not asyncio.current_task(), asyncio.all_tasks())

        # Cancel them all
        for task in tasks:
            task.cancel()

        # Wait for the tasks to be done
        await asyncio.gather(*tasks, return_exceptions=True)

        loop.stop()
