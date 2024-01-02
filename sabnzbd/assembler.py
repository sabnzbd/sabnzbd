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
sabnzbd.assembler - threaded assembly of files
"""

import os
import queue
import logging
import re
from threading import Thread
import ctypes
from typing import Tuple, Optional, List

import sabnzbd
from sabnzbd.misc import get_all_passwords, match_str
from sabnzbd.filesystem import (
    set_permissions,
    clip_path,
    has_win_device,
    diskspace,
    get_filename,
    has_unwanted_extension,
    get_basename,
)
from sabnzbd.constants import Status, GIGI, MAX_ASSEMBLER_QUEUE
import sabnzbd.cfg as cfg
from sabnzbd.nzbstuff import NzbObject, NzbFile
import sabnzbd.par2file as par2file
import sabnzbd.utils.rarfile as rarfile


class Assembler(Thread):
    def __init__(self):
        super().__init__()
        self.queue: queue.Queue[Tuple[Optional[NzbObject], Optional[NzbFile], Optional[bool]]] = queue.Queue()

    def stop(self):
        self.queue.put((None, None, None))

    def process(self, nzo: NzbObject, nzf: Optional[NzbFile] = None, file_done: Optional[bool] = None):
        self.queue.put((nzo, nzf, file_done))

    def queue_level(self) -> float:
        return self.queue.qsize() / MAX_ASSEMBLER_QUEUE

    def run(self):
        while 1:
            # Set NzbObject and NzbFile objects to None so references
            # from this thread do not keep the objects alive (see #1628)
            nzo = nzf = None
            nzo, nzf, file_done = self.queue.get()
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
                        self.assemble(nzo, nzf, file_done)

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

                        elif par2file.is_parfile(filepath):
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
                            if sabnzbd.WIN32:
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
                    except:
                        logging.error(T("Fatal error in Assembler"), exc_info=True)
                        break
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
    def assemble(nzo: NzbObject, nzf: NzbFile, file_done: bool):
        """Assemble a NZF from its table of articles
        1) Partial write: write what we have
        2) Nothing written before: write all
        """

        # We write large article-sized chunks, so we can safely skip the buffering of Python
        with open(nzf.filepath, "ab", buffering=0) as fout:
            for article in nzf.decodetable:
                # Break if deleted during writing
                if nzo.status is Status.DELETED:
                    break

                # Skip already written articles
                if article.on_disk:
                    continue

                # Write all decoded articles
                if article.decoded:
                    # Could be empty in case nzo was deleted
                    if data := sabnzbd.ArticleCache.load_article(article):
                        written = fout.write(data)

                        # In raw/non-buffered mode fout.write may not write everything requested:
                        # https://docs.python.org/3/library/io.html?highlight=write#io.RawIOBase.write
                        while written < len(data):
                            written += fout.write(data[written:])

                        nzf.update_crc32(article.crc32, len(data))
                        article.on_disk = True
                    else:
                        logging.info("No data found when trying to write %s", article)
                else:
                    # If the article was not decoded but the file
                    # is done, it is just a missing piece, so keep writing
                    if file_done:
                        continue
                    else:
                        # We reach an article that was not decoded
                        break

        # Final steps
        if file_done:
            set_permissions(nzf.filepath)
            nzf.assembled = True

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


RE_SUBS = re.compile(r"\W+sub|subs|subpack|subtitle|subtitles(?![a-z])", re.I)
SAFE_EXTS = (".mkv", ".mp4", ".avi", ".wmv", ".mpg", ".webm")


def is_cloaked(nzo: NzbObject, path: str, names: List[str]) -> bool:
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


def check_encrypted_and_unwanted_files(nzo: NzbObject, filepath: str) -> Tuple[bool, Optional[str]]:
    """Combines check for unwanted and encrypted files to save on CPU and IO"""
    encrypted = False
    unwanted = None

    if (cfg.unwanted_extensions() and cfg.action_on_unwanted_extensions()) or (
        nzo.encrypted == 0 and cfg.pause_on_pwrar()
    ):
        # These checks should not break the assembler
        try:
            # Rarfile freezes on Windows special names, so don't try those!
            if sabnzbd.WIN32 and has_win_device(filepath):
                return encrypted, unwanted

            # Is it even a rarfile?
            if rarfile.is_rarfile(filepath):
                # Open the rar
                zf = rarfile.RarFile(filepath, single_file_check=True)

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
                                except rarfile.Error:
                                    # On weird passwords the setpassword() will fail
                                    # but the actual testrar() will work
                                    pass
                                try:
                                    zf.testrar()
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
                                except:
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
