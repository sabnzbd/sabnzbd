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
sabnzbd.assembler - threaded assembly/decoding of files
"""

import os
import queue
import logging
import re
from threading import Thread
from time import sleep
import hashlib
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
)
from sabnzbd.constants import Status, GIGI, MAX_ASSEMBLER_QUEUE
import sabnzbd.cfg as cfg
from sabnzbd.nzbstuff import NzbObject, NzbFile
import sabnzbd.downloader
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

    def queue_full(self):
        return self.queue.qsize() >= MAX_ASSEMBLER_QUEUE

    def run(self):
        while 1:
            # Set NzbObject and NzbFile objects to None so references
            # from this thread do not keep the objects alive (see #1628)
            nzo = nzf = None
            nzo, nzf, file_done = self.queue.get()
            if not nzo:
                logging.info("Shutting down")
                break

            if nzf:
                # Check if enough disk space is free after each file is done
                # If not enough space left, pause downloader and send email
                if file_done and not sabnzbd.Downloader.paused:
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
                            required_space = (complete_free + nzo.bytes_downloaded) / GIGI
                        else:
                            # Continue downloading until 95% complete before checking
                            if nzo.bytes_tried > (nzo.bytes - nzo.bytes_par2) * 0.95:
                                required_space = (complete_free + nzo.bytes) / GIGI

                        if required_space and freespace["complete_dir"][1] < required_space:
                            full_dir = "complete_dir"

                    if full_dir:
                        logging.warning(T("Too little diskspace forcing PAUSE"))
                        # Pause downloader, but don't save, since the disk is almost full!
                        sabnzbd.Downloader.pause()
                        if cfg.fulldisk_autoresume():
                            sabnzbd.Scheduler.plan_diskspace_resume(full_dir, required_space)
                        sabnzbd.emailer.diskfull_mail()

                # Prepare filepath
                filepath = nzf.prepare_filepath()

                if filepath:
                    logging.debug("Decoding part of %s", filepath)
                    try:
                        self.assemble(nzf, file_done)
                    except IOError as err:
                        # If job was deleted or in active post-processing, ignore error
                        if not nzo.deleted and not nzo.is_gone() and not nzo.pp_active:
                            # 28 == disk full => pause downloader
                            if err.errno == 28:
                                logging.error(T("Disk full! Forcing Pause"))
                            else:
                                logging.error(T("Disk error on creating file %s"), clip_path(filepath))
                            # Log traceback
                            logging.info("Traceback: ", exc_info=True)
                            # Pause without saving
                            sabnzbd.Downloader.pause()
                        continue
                    except:
                        logging.error(T("Fatal error in Assembler"), exc_info=True)
                        break

                    # Continue after partly written data
                    if not file_done:
                        continue

                    # Clean-up admin data
                    logging.info("Decoding finished %s", filepath)
                    nzf.remove_admin()

                    # Do rar-related processing
                    if rarfile.is_rarfile(filepath):
                        # Encryption and unwanted extension detection
                        rar_encrypted, unwanted_file = check_encrypted_and_unwanted_files(nzo, filepath)
                        if rar_encrypted:
                            if cfg.pause_on_pwrar() == 1:
                                logging.warning(
                                    T(
                                        'Paused job "%s" because of encrypted RAR file (if supplied, all passwords were tried)'
                                    ),
                                    nzo.final_name,
                                )
                                nzo.pause()
                            else:
                                logging.warning(
                                    T(
                                        'Aborted job "%s" because of encrypted RAR file (if supplied, all passwords were tried)'
                                    ),
                                    nzo.final_name,
                                )
                                nzo.fail_msg = T("Aborted, encryption detected")
                                sabnzbd.NzbQueue.end_job(nzo)

                        if unwanted_file:
                            # Don't repeat the warning after a user override of an unwanted extension pause
                            if nzo.unwanted_ext == 0:
                                logging.warning(
                                    T('In "%s" unwanted extension in RAR file. Unwanted file is %s '),
                                    nzo.final_name,
                                    unwanted_file,
                                )
                            logging.debug(T("Unwanted extension is in rar file %s"), filepath)
                            if cfg.action_on_unwanted_extensions() == 1 and nzo.unwanted_ext == 0:
                                logging.debug("Unwanted extension ... pausing")
                                nzo.unwanted_ext = 1
                                nzo.pause()
                            if cfg.action_on_unwanted_extensions() == 2:
                                logging.debug("Unwanted extension ... aborting")
                                nzo.fail_msg = T("Aborted, unwanted extension detected")
                                sabnzbd.NzbQueue.end_job(nzo)

                        # Add to direct unpack
                        nzo.add_to_direct_unpacker(nzf)

                    elif par2file.is_parfile(filepath):
                        # Parse par2 files, cloaked or not
                        nzo.handle_par2(nzf, filepath)

                    filter_output, reason = nzo_filtered_by_rating(nzo)
                    if filter_output == 1:
                        logging.warning(
                            T('Paused job "%s" because of rating (%s)'),
                            nzo.final_name,
                            reason,
                        )
                        nzo.pause()
                    elif filter_output == 2:
                        logging.warning(
                            T('Aborted job "%s" because of rating (%s)'),
                            nzo.final_name,
                            reason,
                        )
                        nzo.fail_msg = T("Aborted, rating filter matched (%s)") % reason
                        sabnzbd.NzbQueue.end_job(nzo)

            else:
                sabnzbd.NzbQueue.remove(nzo.nzo_id, cleanup=False)
                sabnzbd.PostProcessor.process(nzo)

    @staticmethod
    def assemble(nzf: NzbFile, file_done: bool):
        """Assemble a NZF from its table of articles
        1) Partial write: write what we have
        2) Nothing written before: write all
        """
        # New hash-object needed?
        if not nzf.md5:
            nzf.md5 = hashlib.md5()

        with open(nzf.filepath, "ab") as fout:
            for article in nzf.decodetable:
                # Break if deleted during writing
                if nzf.nzo.status is Status.DELETED:
                    break

                # Skip already written articles
                if article.on_disk:
                    continue

                # Write all decoded articles
                if article.decoded:
                    data = sabnzbd.ArticleCache.load_article(article)
                    # Could be empty in case nzo was deleted
                    if data:
                        fout.write(data)
                        nzf.md5.update(data)
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
            nzf.md5sum = nzf.md5.digest()


RE_SUBS = re.compile(r"\W+sub|subs|subpack|subtitle|subtitles(?![a-z])", re.I)
SAFE_EXTS = (".mkv", ".mp4", ".avi", ".wmv", ".mpg", ".webm")


def is_cloaked(nzo: NzbObject, path: str, names: List[str]) -> bool:
    """Return True if this is likely to be a cloaked encrypted post"""
    fname = os.path.splitext(get_filename(path.lower()))[0]
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
                rarfile.UNRAR_TOOL = sabnzbd.newsunpack.RAR_COMMAND
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
        except:
            logging.info("Error during inspection of RAR-file %s", filepath)
            logging.debug("Traceback: ", exc_info=True)

    return encrypted, unwanted


def nzo_filtered_by_rating(nzo: NzbObject) -> Tuple[int, str]:
    if cfg.rating_enable() and cfg.rating_filter_enable() and (nzo.rating_filtered < 2):
        rating = sabnzbd.Rating.get_rating_by_nzo(nzo.nzo_id)
        if rating is not None:
            nzo.rating_filtered = 1
            reason = rating_filtered(rating, nzo.filename.lower(), True)
            if reason is not None:
                return 2, reason
            reason = rating_filtered(rating, nzo.filename.lower(), False)
            if reason is not None:
                return 1, reason
    return 0, ""


def rating_filtered(rating, filename, abort):
    def check_keyword(keyword):
        clean_keyword = keyword.strip().lower()
        return (len(clean_keyword) > 0) and (clean_keyword in filename)

    audio = cfg.rating_filter_abort_audio() if abort else cfg.rating_filter_pause_audio()
    video = cfg.rating_filter_abort_video() if abort else cfg.rating_filter_pause_video()
    spam = cfg.rating_filter_abort_spam() if abort else cfg.rating_filter_pause_spam()
    spam_confirm = cfg.rating_filter_abort_spam_confirm() if abort else cfg.rating_filter_pause_spam_confirm()
    encrypted = cfg.rating_filter_abort_encrypted() if abort else cfg.rating_filter_pause_encrypted()
    encrypted_confirm = (
        cfg.rating_filter_abort_encrypted_confirm() if abort else cfg.rating_filter_pause_encrypted_confirm()
    )
    downvoted = cfg.rating_filter_abort_downvoted() if abort else cfg.rating_filter_pause_downvoted()
    keywords = cfg.rating_filter_abort_keywords() if abort else cfg.rating_filter_pause_keywords()
    if (video > 0) and (rating.avg_video > 0) and (rating.avg_video <= video):
        return T("video")
    if (audio > 0) and (rating.avg_audio > 0) and (rating.avg_audio <= audio):
        return T("audio")
    if (spam and ((rating.avg_spam_cnt > 0) or rating.avg_encrypted_confirm)) or (
        spam_confirm and rating.avg_spam_confirm
    ):
        return T("spam")
    if (encrypted and ((rating.avg_encrypted_cnt > 0) or rating.avg_encrypted_confirm)) or (
        encrypted_confirm and rating.avg_encrypted_confirm
    ):
        return T("passworded")
    if downvoted and (rating.avg_vote_up < rating.avg_vote_down):
        return T("downvoted")
    if any(check_keyword(k) for k in keywords.split(",")):
        return T("keywords")
    return None
