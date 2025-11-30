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
from typing import Optional, NamedTuple
import rarfile

import sabctools
import sabnzbd
from sabnzbd.misc import get_all_passwords, match_str, SABRarFile
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
    ASSEMBLER_WRITE_THRESHOLD,
)
import sabnzbd.cfg as cfg
from sabnzbd.nzb import NzbFile, NzbObject, Article
import sabnzbd.par2file as par2file


class AssemblerTask(NamedTuple):
    nzo: Optional[NzbObject] = None
    nzf: Optional[NzbFile] = None
    file_done: bool = False
    force: bool = False
    direct_write: bool = False


class Assembler(Thread):
    def __init__(self):
        super().__init__()
        self.max_queue_size: int = cfg.assembler_max_queue_size()
        self.direct_write: bool = cfg.direct_write.get()
        self.assembler_write_trigger: int = 1
        self.queue: queue.Queue[AssemblerTask] = queue.Queue()
        self.queued_lock = threading.Lock()
        self.queued_nzf: set[NzbFile] = set()
        self.queued_nzf_forced: set[NzbFile] = set()

    def stop(self):
        self.queue.put(AssemblerTask())

    def new_limit(self, limit: int):
        """Called when cache limit changes"""
        # Set assembler_write_trigger to be the equivalent of ASSEMBLER_WRITE_THRESHOLD %
        # of the total cache, assuming an article size of 750 000 bytes
        self.assembler_write_trigger = int(limit * ASSEMBLER_WRITE_THRESHOLD / 100 / 750_000) + 1
        logging.debug("Assembler trigger = %d", self.assembler_write_trigger)

    def process(
        self,
        nzo: NzbObject = None,
        nzf: Optional[NzbFile] = None,
        file_done: bool = False,
        force: bool = False,
        article: Optional[Article] = None,
        articles_left: Optional[int] = None,
    ) -> None:
        if nzf is None:
            # post-proc
            self.queue.put(AssemblerTask(nzo))
        else:
            direct_write = self.direct_write and self.assembler_write_trigger > 1 and nzf.type == "yenc"
            if (
                # Always queue if done
                file_done
                # non-direct_write queue if not already queued and at trigger
                or (
                    not direct_write
                    and nzf not in self.queued_nzf
                    and (
                        (article.lowest_partnum and nzf.filename_checked and not nzf.import_finished)
                        or (articles_left and (articles_left % self.assembler_write_trigger) == 0)
                    )
                )
                # direct_write only if forced and not already force queued
                or (direct_write and force and nzf not in self.queued_nzf_forced)
            ):
                with self.queued_lock:
                    if force:
                        self.queued_nzf_forced.add(nzf)
                    self.queued_nzf.add(nzf)
                    self.queue.put(AssemblerTask(nzo, nzf, file_done, force, direct_write))

    def queue_level(self) -> float:
        return self.queue.qsize() / self.max_queue_size

    def run(self):
        while 1:
            # Set NzbObject and NzbFile objects to None so references
            # from this thread do not keep the objects alive (see #1628)
            nzo = nzf = None
            nzo, nzf, file_done, force, direct_write = self.queue.get()
            if not nzo:
                logging.debug("Shutting down assembler")
                break

            if nzf:
                # Check if enough disk space is free after each file is done
                if file_done and not sabnzbd.Downloader.paused:
                    self.diskspace_check(nzo, nzf)

                # Prepare filepath
                if filepath := nzf.prepare_filepath():
                    try:
                        logging.debug("Decoding part of %s", filepath)
                        self.assemble(nzo, nzf, file_done, force, direct_write)

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
                            self.queued_nzf.discard(nzf)
                            if force:
                                self.queued_nzf_forced.discard(nzf)
            else:
                sabnzbd.NzbQueue.remove(nzo.nzo_id, cleanup=False)
                sabnzbd.PostProcessor.process(nzo)

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
    def assemble(nzo: NzbObject, nzf: NzbFile, file_done: bool, force: bool, direct_write: bool) -> None:
        """Assemble a NZF from its table of articles
        1) Partial write: write what we have
        2) Nothing written before: write all
        """
        status_deleted = Status.DELETED
        load_article = sabnzbd.ArticleCache.load_article
        downloader = sabnzbd.Downloader
        decodetable = nzf.decodetable

        fd: Optional[int] = None
        skipped: bool = False  # have any articles been skipped

        try:
            # Resume assembly from where we got to previously
            for idx in range(nzf.assembler_next_index, len(decodetable)):
                article = decodetable[idx]

                # Break if deleted during writing
                if nzo.status is status_deleted:
                    break

                # When forced stop once reached an untried article unless paused
                if force and not article.tries and not downloader.paused:
                    break

                # Skip already written articles
                if article.on_disk:
                    if not skipped:
                        nzf.assembler_next_index += 1
                    continue

                # stop if next piece not yet decoded
                if not article.decoded:
                    # If the article was not decoded but the file
                    # is done, it is just a missing piece, so keep writing
                    if file_done:
                        if not skipped:
                            nzf.assembler_next_index += 1
                        continue
                    # We reach an article that was not decoded
                    if force:
                        skipped = True
                        continue
                    break

                # Could be empty in case nzo was deleted
                data = load_article(article)
                if not data:
                    if file_done:
                        continue
                    if force:
                        skipped = True
                        continue
                    else:
                        logging.info("No data found when trying to write %s", article)
                    break

                if fd is None:
                    fd, direct_write = Assembler.open(nzf, direct_write and article.can_direct_write, article.file_size)
                    if force and skipped and not direct_write:
                        # Abort a forced direct write if the article is not suitable for direct write; will write when file_done
                        if file_done:
                            os.lseek(fd, 0, os.SEEK_END)
                        else:
                            break
                elif direct_write and not article.can_direct_write:
                    # Opened for direct write but encountered an invalid article; revert to append mode
                    if force and skipped:
                        # Abort if skipped an article not yet decoded
                        break
                    if file_done:
                        os.lseek(fd, 0, os.SEEK_END)
                    direct_write = False

                if direct_write:
                    Assembler.write_at_offset(fd, nzf, article, data)
                else:
                    Assembler.write_append(fd, nzf, article, data)

                if not skipped:
                    nzf.assembler_next_index += 1
        finally:
            if fd is not None:
                os.close(fd)

        # Final steps
        if file_done:
            set_permissions(nzf.filepath)
            nzf.assembled = True

    def assemble_article(self, article: Article, data: bytearray) -> bool:
        """Write a single article to disk"""
        if not self.direct_write or not article.can_direct_write:
            return False
        nzf = article.nzf
        with nzf.file_lock:
            fd, direct_write = self.open(nzf, True, article.file_size)
            try:
                if not direct_write:
                    return False
                self.write_at_offset(fd, nzf, article, data)
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
    def write_at_offset(fd: int, nzf: NzbFile, article: Article, data: bytearray):
        """Write data at position in a file"""
        if sabnzbd.WINDOWS:
            # Not implemented on Windows so fallback to os.lseek and os.write
            # Must lock since it is possible to write from multiple threads (assembler + downloader)
            with nzf.file_lock:
                os.lseek(fd, article.data_begin, os.SEEK_SET)
                written = os.write(fd, data)
        else:
            written = os.pwrite(fd, data, article.data_begin)
        # In raw/non-buffered mode os.write may not write everything requested:
        # https://docs.python.org/3/library/io.html?highlight=write#io.RawIOBase.write
        if written < len(data):
            mv = memoryview(data)
            while written < len(data):
                if sabnzbd.WINDOWS:
                    with nzf.file_lock:
                        os.lseek(fd, article.data_begin + written, os.SEEK_SET)
                        written += os.write(fd, mv[written:])
                else:
                    written += os.pwrite(fd, mv[written:], article.data_begin + written)
        nzf.update_crc32(article.crc32, len(data))
        article.on_disk = True

    @staticmethod
    def write_append(fd: int, nzf: NzbFile, article: Article, data: bytearray):
        """
        Append data to the end of the file
        Assumes position is already at the end of the file.
        """
        written = os.write(fd, data)
        # In raw/non-buffered mode os.write may not write everything requested:
        # https://docs.python.org/3/library/io.html?highlight=write#io.RawIOBase.write
        if written < len(data):
            mv = memoryview(data)
            while written < len(data):
                written += os.write(fd, mv[written:])
        nzf.update_crc32(article.crc32, len(data))
        article.on_disk = True

    @staticmethod
    def open(nzf: NzbFile, direct_write: bool, file_size: int) -> tuple[int, bool]:
        """Open file for nzf"""
        with nzf.file_lock:
            if direct_write:
                flags = os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            else:
                flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0)
            fd = os.open(nzf.filepath, flags, 0o644)
            if direct_write:
                if file_size:
                    if os.fstat(fd).st_size == 0:
                        try:
                            sabctools.sparse(fd, file_size)
                        except OSError:
                            logging.debug("Sparse call failed for %s", nzf.filepath)
                            direct_write = False
                            os.lseek(fd, 0, os.SEEK_END)
                else:
                    direct_write = False
                    os.lseek(fd, 0, os.SEEK_END)
            return fd, direct_write


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
