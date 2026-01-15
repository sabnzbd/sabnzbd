#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.assembler - threaded assembly of files
"""

import os
import queue
import logging
import re
import threading
from threading import Thread
import ctypes
from typing import Optional, NamedTuple, Union
import rarfile
import time

import sabctools
import sabnzbd
from sabnzbd.misc import get_all_passwords, match_str, SABRarFile, to_units
from sabnzbd.filesystem import (
    set_permissions,
    clip_path,
    has_win_device,
    diskspace,
    get_filename,
    has_unwanted_extension,
    get_basename,
)
from sabnzbd.constants import (
    Status,
    GIGI,
    ASSEMBLER_WRITE_THRESHOLD_FACTOR_APPEND,
    ASSEMBLER_WRITE_THRESHOLD_FACTOR_DIRECT_WRITE,
    ASSEMBLER_MAX_WRITE_THRESHOLD_DIRECT_WRITE,
    SOFT_ASSEMBLER_QUEUE_LIMIT,
    ASSEMBLER_DELAY_FACTOR_DIRECT_WRITE,
    ARTICLE_CACHE_NON_CONTIGUOUS_FLUSH_PERCENTAGE,
    ASSEMBLER_WRITE_INTERVAL,
)
import sabnzbd.cfg as cfg
from sabnzbd.nzb import NzbFile, NzbObject, Article
import sabnzbd.par2file as par2file


class AssemblerTask(NamedTuple):
    nzo: Optional[NzbObject] = None
    nzf: Optional[NzbFile] = None
    file_done: bool = False
    allow_non_contiguous: bool = False
    direct_write: bool = False


class Assembler(Thread):
    def __init__(self):
        super().__init__()
        self.max_queue_size: int = cfg.assembler_max_queue_size()
        self.direct_write: bool = cfg.direct_write()
        self.cache_limit: int = 0
        # Contiguous bytes required to trigger append writes
        self.append_trigger: int = 1
        # Total bytes required to trigger direct-write assembles
        self.direct_write_trigger: int = 1
        self.delay_trigger: int = 1
        self.queue: queue.Queue[AssemblerTask] = queue.Queue()
        self.queued_lock = threading.Lock()
        self.queued_nzf: set[str] = set()
        self.queued_nzf_non_contiguous: set[str] = set()
        self.queued_next_time: dict[str, float] = dict()
        self.ready_bytes_lock = threading.Lock()
        self.ready_bytes: dict[str, int] = dict()

    def stop(self):
        self.queue.put(AssemblerTask())

    def new_limit(self, limit: int):
        """Called when cache limit changes"""
        self.cache_limit = limit
        self.append_trigger = max(1, int(limit * ASSEMBLER_WRITE_THRESHOLD_FACTOR_APPEND))
        self.direct_write_trigger = max(
            1,
            min(
                max(1, int(limit * ASSEMBLER_WRITE_THRESHOLD_FACTOR_DIRECT_WRITE)),
                ASSEMBLER_MAX_WRITE_THRESHOLD_DIRECT_WRITE,
            ),
        )
        self.calculate_delay_trigger()
        self.change_direct_write(cfg.direct_write())
        logging.debug(
            "Assembler trigger append=%s, direct=%s, delay=%s",
            to_units(self.append_trigger),
            to_units(self.direct_write_trigger),
            to_units(self.delay_trigger),
        )

    def change_direct_write(self, direct_write: bool) -> None:
        self.direct_write = direct_write and self.direct_write_trigger > 1
        self.calculate_delay_trigger()

    def calculate_delay_trigger(self):
        """Point at which downloader should start being delayed, recalculated when cache limit or direct write changes"""
        self.delay_trigger = int(
            max(
                (
                    750_000 * self.max_queue_size * ASSEMBLER_DELAY_FACTOR_DIRECT_WRITE
                    if self.direct_write
                    else 750_000 * self.max_queue_size
                ),
                (
                    self.cache_limit * ARTICLE_CACHE_NON_CONTIGUOUS_FLUSH_PERCENTAGE
                    if self.direct_write
                    else min(self.append_trigger * self.max_queue_size, int(self.cache_limit * 0.5))
                ),
            )
        )

    def is_busy(self) -> bool:
        """Returns True if the assembler thread has at least one NzbFile it is assembling"""
        return bool(self.queued_nzf or self.queued_nzf_non_contiguous)

    def total_ready_bytes(self) -> int:
        with self.ready_bytes_lock:
            return sum(self.ready_bytes.values())

    def update_ready_bytes(self, nzf: NzbFile, delta: int) -> int:
        with self.ready_bytes_lock:
            cur = self.ready_bytes.get(nzf.nzf_id, 0) + delta
            if cur <= 0:
                self.ready_bytes.pop(nzf.nzf_id, None)
            else:
                self.ready_bytes[nzf.nzf_id] = cur
            return cur

    def clear_ready_bytes(self, *nzfs: NzbFile) -> None:
        with self.ready_bytes_lock:
            for nzf in nzfs:
                self.ready_bytes.pop(nzf.nzf_id, None)
                self.queued_next_time.pop(nzf.nzf_id, None)

    def process(
        self,
        nzo: NzbObject = None,
        nzf: Optional[NzbFile] = None,
        file_done: bool = False,
        allow_non_contiguous: bool = False,
        article: Optional[Article] = None,
        override_trigger: bool = False,
    ) -> None:
        if nzf is None:
            # post-proc
            self.queue.put(AssemblerTask(nzo))
            return

        # Track bytes pending being written for this nzf
        ready_bytes = 0
        if self.should_track_ready_bytes(article, allow_non_contiguous, override_trigger):
            ready_bytes = self.update_ready_bytes(nzf, article.decoded_size)

        article_has_first_part = bool(article and article.lowest_partnum)
        if article_has_first_part:
            self.queued_next_time[nzf.nzf_id] = time.monotonic() + ASSEMBLER_WRITE_INTERVAL

        if not self.should_queue_nzf(
            nzf,
            article_has_first_part=article_has_first_part,
            filename_checked=nzf.filename_checked,
            import_finished=nzf.import_finished,
            file_done=file_done,
            allow_non_contiguous=allow_non_contiguous,
            override_trigger=override_trigger,
            ready_bytes=ready_bytes,
        ):
            return

        with self.queued_lock:
            # Recheck not already in the normal queue under lock, but always enqueue when file_done
            if not file_done and nzf.nzf_id in self.queued_nzf:
                return
            if allow_non_contiguous:
                if not file_done and nzf.nzf_id in self.queued_nzf_non_contiguous:
                    return
                self.queued_nzf_non_contiguous.add(nzf.nzf_id)
            else:
                self.queued_nzf.add(nzf.nzf_id)
            self.queued_next_time[nzf.nzf_id] = time.monotonic() + ASSEMBLER_WRITE_INTERVAL
        can_direct_write = self.direct_write and nzf.type == "yenc"
        self.queue.put(AssemblerTask(nzo, nzf, file_done, allow_non_contiguous, can_direct_write))

    def should_queue_nzf(
        self,
        nzf: NzbFile,
        *,
        article_has_first_part: bool,
        filename_checked: bool,
        import_finished: bool,
        file_done: bool,
        allow_non_contiguous: bool,
        override_trigger: bool,
        ready_bytes: int,
    ) -> bool:
        # Always queue if done
        if file_done:
            return True
        if nzf.nzf_id in self.queued_nzf:
            return False
        # Always write
        if (override_trigger or article_has_first_part) and filename_checked and not import_finished:
            return True
        next_ready = (
            (next_index := nzf.assembler_next_index) >= 0
            and next_index < len(nzf.decodetable)
            and (next_article := nzf.decodetable[next_index])
            and (next_article.decoded or next_article.on_disk)
        )
        # Trigger every 5 seconds if next article is decoded or on_disk
        if next_ready and time.monotonic() > self.queued_next_time.get(nzf.nzf_id, 0):
            return True
        # Append
        if not self.direct_write or nzf.type != "yenc":
            return nzf.contiguous_ready_bytes() >= self.append_trigger
        # Direct Write
        if allow_non_contiguous:
            return True
        # Direct Write ready bytes trigger if next is also ready
        if next_ready and ready_bytes >= self.direct_write_trigger:
            return True
        return False

    @staticmethod
    def should_track_ready_bytes(
        article: Optional[Article], allow_non_contiguous: bool, override_trigger: bool
    ) -> bool:
        """"""
        return article and not allow_non_contiguous and not override_trigger and article.decoded_size

    def delay(self) -> float:
        """Calculate how long if at all the downloader thread should sleep to allow the assembler to catch up"""
        ready_total = self.total_ready_bytes()
        # Below trigger: no delay possible
        if ready_total <= self.delay_trigger:
            return 0
        pressure = (ready_total - self.delay_trigger) / max(1.0, self.cache_limit - self.delay_trigger)
        if pressure <= SOFT_ASSEMBLER_QUEUE_LIMIT:
            return 0
        # 50-100%: 0-0.25 seconds, capped at 0.15
        sleep = min((pressure - SOFT_ASSEMBLER_QUEUE_LIMIT) / 2, 0.15)
        return max(0.001, sleep)

    def run(self):
        while 1:
            # Set NzbObject and NzbFile objects to None so references
            # from this thread do not keep the objects alive (see #1628)
            nzo = nzf = None
            nzo, nzf, file_done, allow_non_contiguous, direct_write = self.queue.get()
            if not nzo:
                logging.debug("Shutting down assembler")
                break

            if nzf:
                # Check if enough disk space is free after each file is done
                if file_done and not sabnzbd.Downloader.paused:
                    self.diskspace_check(nzo, nzf)

                try:
                    # Prepare filepath
                    if not (filepath := nzf.prepare_filepath()):
                        continue

                    try:
                        logging.debug("Decoding part of %s", filepath)
                        self.assemble(nzo, nzf, file_done, allow_non_contiguous, direct_write)

                        # Continue after partly written data
                        if not file_done:
                            continue

                        # Clean-up admin data
                        logging.info("Decoding finished %s", filepath)
                        nzf.remove_admin()

                        # Do rar-related processing
                        if rarfile.is_rarfile(filepath):
                            # Check for encrypted files, unwanted extensions and add to direct unpack
                            self.check_encrypted_and_unwanted(nzo, nzf)
                            nzo.add_to_direct_unpacker(nzf)

                        elif par2file.is_par2_file(filepath):
                            # Parse par2 files, cloaked or not
                            nzo.handle_par2(nzf, filepath)

                    except IOError as err:
                        # If job was deleted/finished or in active post-processing, ignore error
                        if not nzo.pp_or_finished:
                            # 28 == disk full => pause downloader
                            if err.errno == 28:
                                logging.error(T("Disk full! Forcing Pause"))
                            else:
                                logging.error(T("Disk error on creating file %s"), clip_path(filepath))
                            # Log traceback
                            if sabnzbd.WINDOWS:
                                logging.info(
                                    "Winerror: %s - %s",
                                    err.winerror,
                                    hex(ctypes.windll.ntdll.RtlGetLastNtStatus() + 2**32),
                                )
                            logging.info("Traceback: ", exc_info=True)
                            # Pause without saving
                            sabnzbd.Downloader.pause()
                        else:
                            logging.debug("Ignoring error %s for %s, already finished or in post-proc", err, filepath)
                    except Exception:
                        logging.error(T("Fatal error in Assembler"), exc_info=True)
                        break
                finally:
                    with self.queued_lock:
                        if allow_non_contiguous:
                            self.queued_nzf_non_contiguous.discard(nzf.nzf_id)
                        else:
                            self.queued_nzf.discard(nzf.nzf_id)
            else:
                sabnzbd.NzbQueue.remove(nzo.nzo_id, cleanup=False)
                sabnzbd.PostProcessor.process(nzo)
                self.clear_ready_bytes(*nzo.files)

    @staticmethod
    def diskspace_check(nzo: NzbObject, nzf: NzbFile):
        """Check diskspace requirements.
        If not enough space left, pause downloader and send email"""
        freespace = diskspace(force=True)
        full_dir = None
        required_space = (cfg.download_free.get_float() + nzf.bytes) / GIGI
        if freespace["download_dir"][1] < required_space:
            full_dir = "download_dir"

        # Enough space in download_dir, check complete_dir
        complete_free = cfg.complete_free.get_float()
        if complete_free > 0 and not full_dir:
            required_space = 0
            if cfg.direct_unpack():
                # We unpack while we download, so we should check every time
                # if the unpack maybe already filled up the drive
                required_space = complete_free / GIGI
            elif nzo.bytes_tried > (nzo.bytes - nzo.bytes_par2) * 0.95:
                # Since only at 100% unpack is started, continue
                # downloading until 95% complete before checking
                required_space = (complete_free + nzo.bytes) / GIGI

            if required_space and freespace["complete_dir"][1] < required_space:
                full_dir = "complete_dir"

        if full_dir:
            logging.warning(T("Too little diskspace forcing PAUSE"))
            # Pause downloader, but don't save, since the disk is almost full!
            sabnzbd.Downloader.pause()
            if cfg.fulldisk_autoresume():
                sabnzbd.Scheduler.plan_diskspace_resume(full_dir, required_space)
            sabnzbd.notifier.send_notification("SABnzbd", T("Too little diskspace forcing PAUSE"), "disk_full")
            sabnzbd.emailer.diskfull_mail()

    @staticmethod
    def assemble(nzo: NzbObject, nzf: NzbFile, file_done: bool, allow_non_contiguous: bool, direct_write: bool) -> None:
        """Assemble a NZF from its table of articles
        1) Partial write: write what we have
        2) Nothing written before: write all
        """
        load_article = sabnzbd.ArticleCache.load_article
        downloader = sabnzbd.Downloader
        decodetable = nzf.decodetable

        fd: Optional[int] = None
        skipped: bool = False  # have any articles been skipped
        offset: int = 0  # sequential offset for append writes

        try:
            # Resume assembly from where we got to previously
            for idx in range(nzf.assembler_next_index, len(decodetable)):
                article = decodetable[idx]

                # Break if deleted during writing
                if nzo.status is Status.DELETED:
                    break

                # allow_non_contiguous is when the cache forces the assembler to write all articles, even if it leaves gaps.
                # In most cases we can stop at the first article that has not been tried, because they are requested in order.
                # However, if we are paused then always consider the whole decodetable to ensure everything possible is written.
                if allow_non_contiguous and not article.tries and not downloader.paused:
                    break

                # Skip already written articles
                if article.on_disk:
                    if fd is not None and article.decoded_size is not None:
                        # Move the file descriptor forward past this article
                        offset += article.decoded_size
                    if not skipped:
                        with nzf.lock:
                            nzf.assembler_next_index = idx + 1
                    continue

                # stop if next piece not yet decoded
                if not article.decoded:
                    # If the article was not decoded but the file
                    # is done, it is just a missing piece, so keep writing
                    if file_done:
                        continue
                    # We reach an article that was not decoded
                    if allow_non_contiguous:
                        skipped = True
                        continue
                    break

                # Could be empty in case nzo was deleted
                data = load_article(article)
                if not data:
                    if file_done:
                        continue
                    if allow_non_contiguous:
                        skipped = True
                        continue
                    else:
                        logging.info("No data found when trying to write %s", article)
                    break

                # If required open the file
                if fd is None:
                    fd, offset, direct_write = Assembler.open(
                        nzf, direct_write and article.can_direct_write, article.file_size
                    )
                    if not direct_write and allow_non_contiguous:
                        # Can only be allow_non_contiguous if we wanted direct_write, file_done will always be queued separately
                        break

                if direct_write and article.can_direct_write:
                    offset += Assembler.write(fd, idx, nzf, article, data)
                else:
                    if direct_write and skipped and not file_done:
                        # If we have already skipped an article then need to abort, unless this is the final assemble
                        break
                    offset += Assembler.write(fd, idx, nzf, article, data, offset)

        finally:
            if fd is not None:
                os.close(fd)

        # Final steps
        if file_done:
            sabnzbd.Assembler.clear_ready_bytes(nzf)
            set_permissions(nzf.filepath)
            nzf.assembled = True

    @staticmethod
    def assemble_article(article: Article, data: bytearray) -> bool:
        """Write a single article to disk"""
        if not article.can_direct_write:
            return False
        nzf = article.nzf
        with nzf.file_lock:
            fd, _, direct_write = Assembler.open(nzf, True, article.file_size)
            try:
                if not direct_write:
                    cfg.direct_write.set(False)
                    return False
                with nzf.lock:
                    # Is this the next article to keep writing sequentially
                    idx = nzf.assembler_next_index
                    if idx >= len(nzf.decodetable) or article != nzf.decodetable[idx]:
                        idx = None
                Assembler.write(fd, idx, nzf, article, data)
            except FileNotFoundError:
                # nzo has probably been deleted, ArticleCache tries the fallback and handles it
                return False
            finally:
                os.close(fd)
        return True

    @staticmethod
    def check_encrypted_and_unwanted(nzo: NzbObject, nzf: NzbFile):
        """Encryption and unwanted extension detection"""
        rar_encrypted, unwanted_file = check_encrypted_and_unwanted_files(nzo, nzf.filepath)
        if rar_encrypted:
            if cfg.pause_on_pwrar() == 1:
                logging.warning(
                    T('Paused job "%s" because of encrypted RAR file (if supplied, all passwords were tried)'),
                    nzo.final_name,
                )
                nzo.pause()
            else:
                logging.warning(
                    T('Aborted job "%s" because of encrypted RAR file (if supplied, all passwords were tried)'),
                    nzo.final_name,
                )
                nzo.fail_msg = T("Aborted, encryption detected")
                sabnzbd.NzbQueue.end_job(nzo)

        if unwanted_file:
            # Don't repeat the warning after a user override of an unwanted extension pause
            if nzo.unwanted_ext == 0:
                logging.warning(
                    T('In "%s" unwanted extension in RAR file. Unwanted file is %s '),
                    nzf.nzo.final_name,
                    unwanted_file,
                )
            logging.debug(T("Unwanted extension is in rar file %s"), nzf.filename)
            if cfg.action_on_unwanted_extensions() == 1 and nzo.unwanted_ext == 0:
                logging.debug("Unwanted extension ... pausing")
                nzo.unwanted_ext = 1
                nzo.pause()
            if cfg.action_on_unwanted_extensions() == 2:
                logging.debug("Unwanted extension ... aborting")
                nzo.fail_msg = T("Aborted, unwanted extension detected")
                sabnzbd.NzbQueue.end_job(nzo)

    @staticmethod
    def write(
        fd: int, nzf_index: Optional[int], nzf: NzbFile, article: Article, data: bytearray, offset: Optional[int] = None
    ) -> int:
        """Write data at position in a file"""
        pos = article.data_begin if offset is None else offset
        written = Assembler._write(fd, nzf, data, pos)
        # In raw/non-buffered mode os.write may not write everything requested:
        # https://docs.python.org/3/library/io.html?highlight=write#io.RawIOBase.write
        if written < len(data) and (mv := memoryview(data)):
            while written < len(data):
                written += Assembler._write(fd, nzf, mv[written:], pos + written)

        nzf.update_crc32(article.crc32, len(data))
        article.on_disk = True
        sabnzbd.Assembler.update_ready_bytes(nzf, -len(data))
        if nzf_index is not None:
            with nzf.lock:
                # assembler_next_index is the lowest index that has not yet been written sequentially from the start of the file.
                # If this was the next required index to remain sequential, it can be incremented which allows the assmebler to
                # resume without rechecking articles that are already known to be on disk.
                if nzf.assembler_next_index == nzf_index:
                    nzf.assembler_next_index += 1
        return written

    @staticmethod
    def _write(fd: int, nzf: NzbFile, data: Union[bytearray, memoryview], offset: int) -> int:
        if sabnzbd.WINDOWS:
            # pwrite is not implemented on Windows so fallback to os.lseek and os.write
            # Must lock since it is possible to write from multiple threads (assembler + downloader)
            with nzf.file_lock:
                os.lseek(fd, offset, os.SEEK_SET)
                return os.write(fd, data)
        else:
            return os.pwrite(fd, data, offset)

    @staticmethod
    def open(nzf: NzbFile, direct_write: bool, file_size: int) -> tuple[int, int, bool]:
        """Open file for nzf

         Use direct_write if requested, with a fallback to setting the current file position for append mode
        :returns (file_descriptor, current_offset, can_direct_write)
        """
        with nzf.file_lock:
            # Get the current umask without changing it, to create a file with the same permissions as `with open(...)`
            os.umask(os.umask(0))
            fd = os.open(nzf.filepath, os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o666)
            offset = nzf.contiguous_offset()
            os.lseek(fd, offset, os.SEEK_SET)
            if direct_write:
                if not file_size:
                    direct_write = False
                if os.fstat(fd).st_size == 0:
                    try:
                        sabctools.sparse(fd, file_size)
                    except OSError:
                        logging.debug("Sparse call failed for %s", nzf.filepath)
                        cfg.direct_write.set(False)
                        direct_write = False
            return fd, offset, direct_write


RE_SUBS = re.compile(r"\W+sub|subs|subpack|subtitle|subtitles(?![a-z])", re.I)
SAFE_EXTS = (".mkv", ".mp4", ".avi", ".wmv", ".mpg", ".webm")


def is_cloaked(nzo: NzbObject, path: str, names: list[str]) -> bool:
    """Return True if this is likely to be a cloaked encrypted post"""
    fname = get_basename(get_filename(path.lower()))
    for name in names:
        name = get_filename(name.lower())
        name, ext = os.path.splitext(name)
        if (
            ext == ".rar"
            and fname.startswith(name)
            and (len(fname) - len(name)) < 8
            and len(names) < 3
            and not RE_SUBS.search(fname)
        ):
            # Only warn once
            if nzo.encrypted == 0:
                logging.warning(
                    T('Job "%s" is probably encrypted due to RAR with same name inside this RAR'), nzo.final_name
                )
                nzo.encrypted = 1
            return True
        elif "password" in name and ext not in SAFE_EXTS:
            # Only warn once
            if nzo.encrypted == 0:
                logging.warning(T('Job "%s" is probably encrypted: "password" in filename "%s"'), nzo.final_name, name)
                nzo.encrypted = 1
            return True
    return False


def check_encrypted_and_unwanted_files(nzo: NzbObject, filepath: str) -> tuple[bool, Optional[str]]:
    """Combines check for unwanted and encrypted files to save on CPU and IO"""
    encrypted = False
    unwanted = None

    if (cfg.unwanted_extensions() and cfg.action_on_unwanted_extensions()) or (
        nzo.encrypted == 0 and cfg.pause_on_pwrar()
    ):
        # These checks should not break the assembler
        try:
            # Rarfile freezes on Windows special names, so don't try those!
            if sabnzbd.WINDOWS and has_win_device(filepath):
                return encrypted, unwanted

            # Is it even a rarfile?
            if rarfile.is_rarfile(filepath):
                # Open the rar
                zf = SABRarFile(filepath, part_only=True)

                # Check for encryption
                if (
                    nzo.encrypted == 0
                    and cfg.pause_on_pwrar()
                    and (zf.needs_password() or is_cloaked(nzo, filepath, zf.namelist()))
                ):
                    # Load all passwords
                    passwords = get_all_passwords(nzo)

                    # Cloaked job?
                    if is_cloaked(nzo, filepath, zf.namelist()):
                        encrypted = True
                    elif not passwords:
                        # Only error when no password was set
                        nzo.encrypted = 1
                        encrypted = True
                    else:
                        # Lets test if any of the password work
                        password_hit = False

                        for password in passwords:
                            if password:
                                logging.info('Trying password "%s" on job "%s"', password, nzo.final_name)
                                try:
                                    zf.setpassword(password)
                                    zf.trigger_parse()
                                    password_hit = password
                                    break
                                except rarfile.RarWrongPassword:
                                    # This one really didn't work
                                    pass
                                except rarfile.RarCRCError as e:
                                    # CRC errors can be thrown for wrong password or
                                    # missing the next volume (with correct password)
                                    if match_str(str(e), ("cannot find volume", "unexpected end of archive")):
                                        # We assume this one worked!
                                        password_hit = password
                                        break
                                    # This one didn't work
                                    pass
                                except Exception:
                                    # All the other errors we skip, they might be fixable in post-proc.
                                    # For example starting from the wrong volume, or damaged files
                                    # This will cause the check to be performed again for the next rar, might
                                    # be disk-intensive! Could be removed later and just accept the password.
                                    return encrypted, unwanted

                        # Did any work?
                        if password_hit:
                            # Record the successful password
                            nzo.correct_password = password_hit
                            # Don't check other files
                            logging.info('Password "%s" matches for job "%s"', password_hit, nzo.final_name)
                            nzo.encrypted = -1
                            encrypted = False
                        else:
                            # Encrypted and none of them worked
                            nzo.encrypted = 1
                            encrypted = True

                # Check for unwanted extensions
                if cfg.unwanted_extensions() and cfg.action_on_unwanted_extensions():
                    for somefile in zf.namelist():
                        logging.debug("File contains: %s", somefile)
                        if has_unwanted_extension(somefile):
                            logging.debug("Unwanted file %s", somefile)
                            unwanted = somefile
                zf.close()
                del zf
        except rarfile.Error as e:
            logging.info("Error during inspection of RAR-file %s: %s", filepath, e)

    return encrypted, unwanted
