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
sabnzbd.directunpacker
"""

import os
import re
import subprocess
import time
import threading
import logging
from typing import Optional, Dict, List, Tuple

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.misc import int_conv, format_time_string, build_and_run_command
from sabnzbd.filesystem import long_path, remove_all, real_path, remove_file
from sabnzbd.nzbstuff import NzbObject, NzbFile
from sabnzbd.encoding import platform_btou
from sabnzbd.decorators import synchronized
from sabnzbd.newsunpack import RAR_EXTRACTFROM_RE, RAR_EXTRACTED_RE, rar_volumelist, add_time_left
from sabnzbd.postproc import prepare_extraction_path
from sabnzbd.utils.rarfile import RarFile
from sabnzbd.utils.diskspeed import diskspeedmeasure

# Need a lock to make sure start and stop is handled correctly
# Otherwise we could stop while the thread was still starting
START_STOP_LOCK = threading.RLock()

ACTIVE_UNPACKERS = []

RAR_NR = re.compile(r"(.*?)(\.part(\d*).rar|\.r(\d*))$", re.IGNORECASE)


class DirectUnpacker(threading.Thread):
    def __init__(self, nzo: NzbObject):
        super().__init__()

        self.nzo: NzbObject = nzo
        self.active_instance: Optional[subprocess.Popen] = None
        self.killed: bool = False
        self.next_file_lock = threading.Condition(threading.RLock())

        self.unpack_dir_info = None
        self.rarfile_nzf: Optional[NzbFile] = None
        self.cur_setname: Optional[str] = None
        self.cur_volume: int = 0
        self.total_volumes: Dict[str, int] = {}
        self.unpack_time: float = 0.0

        self.success_sets: Dict[str, Tuple[List[str], List[str]]] = {}
        self.next_sets: List[NzbFile] = []

        self.duplicate_lines: int = 0

        nzo.direct_unpacker = self

    def stop(self):
        pass

    def save(self):
        pass

    def reset_active(self):
        # make sure the process and file handlers are closed nicely:
        try:
            if self.active_instance:
                self.active_instance.stdout.close()
                self.active_instance.stdin.close()
                self.active_instance.wait(timeout=2)
        except:
            logging.debug("Exception in reset_active()", exc_info=True)
            pass

        self.active_instance = None
        self.cur_setname = None
        self.cur_volume = 0
        self.rarfile_nzf = None

    def check_requirements(self):
        if (
            not cfg.enable_unrar()
            or not cfg.direct_unpack()
            or self.killed
            or self.nzo.first_articles
            or not self.nzo.unpack
            or self.nzo.bad_articles
            or sabnzbd.newsunpack.RAR_PROBLEM
        ):
            return False
        return True

    def set_volumes_for_nzo(self):
        """Loop over all files to detect the names"""
        logging.debug("Parsing setname and volume information for %s" % self.nzo.final_name)
        none_counter = 0
        found_counter = 0
        for nzf in self.nzo.files + self.nzo.finished_files:
            nzf.setname, nzf.vol = analyze_rar_filename(nzf.filename)
            # We matched?
            if nzf.setname:
                found_counter += 1
                if nzf.setname not in self.total_volumes:
                    self.total_volumes[nzf.setname] = 0
                self.total_volumes[nzf.setname] = max(self.total_volumes[nzf.setname], nzf.vol)
            else:
                none_counter += 1

        # Too much not found? Obfuscated, ignore results
        if none_counter > found_counter:
            self.total_volumes = {}

    @synchronized(START_STOP_LOCK)
    def add(self, nzf: NzbFile):
        """Add jobs and start instance of DirectUnpack"""
        if not cfg.direct_unpack_tested():
            test_disk_performance()

        # Stop if something is wrong or we shouldn't start yet
        if not self.check_requirements():
            return

        # Is this the first set?
        if not self.cur_setname:
            self.set_volumes_for_nzo()
            self.cur_setname = nzf.setname

        # Analyze updated filenames
        nzf.setname, nzf.vol = analyze_rar_filename(nzf.filename)

        # Are we doing this set?
        if self.cur_setname and self.cur_setname == nzf.setname:
            logging.debug("DirectUnpack queued %s for %s", nzf.filename, self.cur_setname)
            # Is this the first one of the first set?
            if not self.active_instance and not self.is_alive() and self.have_next_volume():
                # Too many runners already?
                if len(ACTIVE_UNPACKERS) >= cfg.direct_unpack_threads():
                    logging.info("Too many DirectUnpackers currently to start %s", self.cur_setname)
                    return

                # Start the unrar command and the loop
                self.create_unrar_instance()
                self.start()
        elif not any(test_nzf.setname == nzf.setname for test_nzf in self.next_sets):
            # Need to store this for the future, only once per set!
            self.next_sets.append(nzf)

        # Wake up the thread to see if this is good to go
        with self.next_file_lock:
            self.next_file_lock.notify()

    def run(self):
        # Input and output
        linebuf = b""
        last_volume_linebuf = b""
        unrar_log = []
        rarfiles = []
        extracted = []
        start_time = time.time()

        # Need to read char-by-char because there's no newline after new-disk message
        while 1:
            # We need to lock, so we don't crash if unpacker is deleted while we read
            with START_STOP_LOCK:
                if not self.active_instance or not self.active_instance.stdout:
                    break
                char = self.active_instance.stdout.read(1)

            if not char:
                # End of program
                break
            linebuf += char

            # Continue if it's not a space or end of line
            if char not in (b" ", b"\n"):
                continue

            # Handle whole lines
            if char == b"\n":
                # When reaching end-of-line, we can safely convert and add to the log
                linebuf_encoded = platform_btou(linebuf.strip())
                unrar_log.append(linebuf_encoded)
                linebuf = b""

                # Error? Let PP-handle this job
                if any(
                    error_text in linebuf_encoded
                    for error_text in (
                        "ERROR: ",
                        "Cannot create",
                        "in the encrypted file",
                        "CRC failed",
                        "checksum failed",
                        "You need to start extraction from a previous volume",
                        "password is incorrect",
                        "Incorrect password",
                        "Write error",
                        "checksum error",
                        "Cannot open",
                        "start extraction from a previous volume",
                        "Unexpected end of archive",
                    )
                ):
                    logging.info("Error in DirectUnpack of %s: %s", self.cur_setname, linebuf_encoded)
                    self.abort()

                elif linebuf_encoded.startswith("All OK"):
                    # Did we reach the end?
                    # Stop timer and finish
                    self.unpack_time += time.time() - start_time
                    ACTIVE_UNPACKERS.remove(self)

                    # Take note of the correct password
                    if self.nzo.password and not self.nzo.correct_password:
                        self.nzo.correct_password = self.nzo.password

                    # Add to success
                    rarfile_path = os.path.join(self.nzo.download_path, self.rarfile_nzf.filename)
                    self.success_sets[self.cur_setname] = (
                        rar_volumelist(rarfile_path, self.nzo.correct_password, rarfiles),
                        extracted,
                    )
                    logging.info("DirectUnpack completed for %s", self.cur_setname)
                    self.nzo.set_action_line(T("Direct Unpack"), T("Completed"))

                    # List success in history-info
                    msg = T("Unpacked %s files/folders in %s") % (len(extracted), format_time_string(self.unpack_time))
                    msg = "%s - %s" % (T("Direct Unpack"), msg)
                    self.nzo.set_unpack_info("Unpack", msg, self.cur_setname)

                    # Write current log and clear
                    logging.debug("DirectUnpack Unrar output %s", "\n".join(unrar_log))
                    unrar_log = []
                    rarfiles = []
                    extracted = []

                    # Are there more files left?
                    while self.nzo.files and not self.next_sets:
                        with self.next_file_lock:
                            self.next_file_lock.wait()

                    # Is there another set to do?
                    if self.next_sets:
                        # Start new instance
                        nzf = self.next_sets.pop(0)
                        self.reset_active()
                        self.cur_setname = nzf.setname
                        # Wait for the 1st volume to appear
                        self.wait_for_next_volume()
                        self.create_unrar_instance()
                        start_time = time.time()
                    else:
                        self.killed = True
                        break

                elif linebuf_encoded.startswith("Extracting from"):
                    # List files we used
                    filename = re.search(RAR_EXTRACTFROM_RE, linebuf_encoded).group(1)
                    if filename not in rarfiles:
                        rarfiles.append(filename)
                else:
                    # List files we extracted
                    m = re.search(RAR_EXTRACTED_RE, linebuf_encoded)
                    if m:
                        # In case of flat-unpack, UnRar still prints the whole path (?!)
                        unpacked_file = m.group(2)
                        if cfg.flat_unpack():
                            unpacked_file = os.path.basename(unpacked_file)
                        extracted.append(real_path(self.unpack_dir_info[0], unpacked_file))

            if linebuf.endswith(b"[C]ontinue, [Q]uit "):
                # Stop timer
                self.unpack_time += time.time() - start_time

                # Wait for the next one..
                self.wait_for_next_volume()

                # Possible that the instance was deleted while locked
                if not self.killed:
                    # Sometimes the assembler is still working on the file, resulting in "Unexpected end of archive".
                    # So we delay a tiny bit before we continue. This is not the cleanest solution, but it works.
                    time.sleep(0.1)

                    # If unrar stopped or is killed somehow, writing will cause a crash
                    try:
                        # Give unrar some time to do its thing
                        self.active_instance.stdin.write(b"C\n")
                        start_time = time.time()
                        time.sleep(0.1)
                    except IOError:
                        self.abort()
                        break

                    # Did we unpack a new volume? Sometimes UnRar hangs on 1 volume
                    if not last_volume_linebuf or last_volume_linebuf != linebuf:
                        # Next volume
                        self.cur_volume += 1
                        self.nzo.set_action_line(T("Direct Unpack"), self.get_formatted_stats(include_time_left=True))
                        logging.info("DirectUnpacked volume %s for %s", self.cur_volume, self.cur_setname)

                    # If lines did not change and we don't have the next volume, this download is missing files!
                    # In rare occasions we can get stuck forever with repeating lines
                    if last_volume_linebuf == linebuf:
                        if not self.have_next_volume() or self.duplicate_lines > 10:
                            logging.info("DirectUnpack failed due to missing files %s", self.cur_setname)
                            self.abort()
                        else:
                            logging.debug('Duplicate output line detected: "%s"', platform_btou(last_volume_linebuf))
                            self.duplicate_lines += 1
                    else:
                        self.duplicate_lines = 0
                    last_volume_linebuf = linebuf

        # Add last line and write any new output
        if linebuf:
            unrar_log.append(platform_btou(linebuf.strip()))
        if unrar_log:
            logging.debug("DirectUnpack Unrar output %s", "\n".join(unrar_log))

        # Make more space
        self.reset_active()
        if self in ACTIVE_UNPACKERS:
            ACTIVE_UNPACKERS.remove(self)

        # Set the thread to killed so it never gets restarted by accident
        self.killed = True

    def have_next_volume(self):
        """Check if next volume of set is available, start
        from the end of the list where latest completed files are
        Make sure that files are 100% written to disk by checking md5sum
        """
        for nzf_search in reversed(self.nzo.finished_files):
            if nzf_search.setname == self.cur_setname and nzf_search.vol == (self.cur_volume + 1) and nzf_search.md5sum:
                return nzf_search
        return False

    def wait_for_next_volume(self):
        """Wait for the correct volume to appear but stop if it was killed
        or the NZB is in post-processing and no new files will be downloaded.
        """
        while not self.have_next_volume() and not self.killed and not self.nzo.pp_active:
            with self.next_file_lock:
                self.next_file_lock.wait()

    @synchronized(START_STOP_LOCK)
    def create_unrar_instance(self):
        """Start the unrar instance using the user's options"""
        # Generate extraction path and save for post-proc
        if not self.unpack_dir_info:
            try:
                self.unpack_dir_info = prepare_extraction_path(self.nzo)
            except:
                # Prevent fatal crash if directory creation fails
                self.abort()
                return

        # Get the information
        extraction_path, _, _, one_folder, _ = self.unpack_dir_info

        # Set options
        if self.nzo.correct_password:
            password_command = "-p%s" % self.nzo.correct_password
        elif self.nzo.password:
            password_command = "-p%s" % self.nzo.password
        else:
            password_command = "-p-"

        if one_folder or cfg.flat_unpack():
            action = "e"
        else:
            action = "x"

        # The first NZF
        self.rarfile_nzf = self.have_next_volume()

        # Ignore if maybe this set is not there anymore
        # This can happen due to race/timing issues when creating the sets
        if not self.rarfile_nzf:
            return

        # Generate command
        rarfile_path = os.path.join(self.nzo.download_path, self.rarfile_nzf.filename)
        if sabnzbd.WIN32:
            # On Windows, UnRar uses a custom argument parser
            # See: https://github.com/sabnzbd/sabnzbd/issues/1043
            # The -scf forces the output to be UTF8
            command = [
                sabnzbd.newsunpack.RAR_COMMAND,
                action,
                "-vp",
                "-idp",
                "-scf",
                "-o+",
                "-ai",
                password_command,
                rarfile_path,
                "%s\\" % long_path(extraction_path),
            ]
        else:
            # The -scf forces the output to be UTF8
            command = [
                sabnzbd.newsunpack.RAR_COMMAND,
                action,
                "-vp",
                "-idp",
                "-scf",
                "-o+",
                "-ai",
                password_command,
                rarfile_path,
                "%s/" % extraction_path,
            ]

        if cfg.ignore_unrar_dates():
            command.insert(3, "-tsm-")

        # Let's start from the first one!
        self.cur_volume = 1

        # Need to disable buffer to have direct feedback
        self.active_instance = build_and_run_command(command, windows_unrar_command=True, bufsize=0)

        # Add to runners
        ACTIVE_UNPACKERS.append(self)

        # Doing the first
        logging.info("DirectUnpacked volume %s for %s", self.cur_volume, self.cur_setname)

    @synchronized(START_STOP_LOCK)
    def abort(self):
        """Abort running instance and delete generated files"""
        if not self.killed and self.cur_setname:
            logging.info("Aborting DirectUnpack for %s", self.cur_setname)
            self.killed = True

            # Save reference to the first rarfile
            rarfile_nzf = self.rarfile_nzf

            # Abort Unrar
            if self.active_instance:
                # First we try to abort gracefully
                try:
                    self.active_instance.stdin.write(b"Q\n")
                    time.sleep(0.2)
                except IOError:
                    pass

                # Now force kill and give it a bit of time
                try:
                    self.active_instance.kill()
                    time.sleep(0.2)
                except AttributeError:
                    # Already killed by the Quit command
                    pass

            # Wake up the thread
            with self.next_file_lock:
                self.next_file_lock.notify()

            # No new sets
            self.next_sets = []
            self.success_sets = {}

            # Remove files
            if self.unpack_dir_info:
                extraction_path, _, _, one_folder, _ = self.unpack_dir_info
                # In case of flat-unpack we need to remove the files manually
                if one_folder:
                    # RarFile can fail for mysterious reasons
                    try:
                        rar_contents = RarFile(
                            os.path.join(self.nzo.download_path, rarfile_nzf.filename), single_file_check=True
                        ).filelist()
                        for rm_file in rar_contents:
                            # Flat-unpack, so remove foldername from RarFile output
                            f = os.path.join(extraction_path, os.path.basename(rm_file))
                            remove_file(f)
                    except:
                        # The user will have to remove it themselves
                        logging.info(
                            "Failed to clean Direct Unpack after aborting %s", rarfile_nzf.filename, exc_info=True
                        )
                else:
                    # We can just remove the whole path
                    remove_all(extraction_path, recursive=True)
                # Remove dir-info
                self.unpack_dir_info = None

            # Reset settings
            self.reset_active()

    def get_formatted_stats(self, include_time_left: bool = False) -> str:
        """Get percentage or number of rar's done"""
        if self.cur_setname and self.cur_setname in self.total_volumes:
            # This won't work on obfuscated posts
            if self.total_volumes[self.cur_setname] >= self.cur_volume and self.cur_volume:
                formatted_stats = "%02d/%02d" % (self.cur_volume, self.total_volumes[self.cur_setname])
                if include_time_left:
                    formatted_stats += add_time_left(
                        (self.cur_volume / self.total_volumes[self.cur_setname]) * 100, time_used=self.unpack_time
                    )
                return formatted_stats
        return str(self.cur_volume)


def analyze_rar_filename(filename):
    """Extract volume number and setname from rar-filenames
    Both ".part01.rar" and ".r01"
    """
    m = RAR_NR.search(filename)
    if m:
        if m.group(4):
            # Special since starts with ".rar", ".r00"
            return m.group(1), int_conv(m.group(4)) + 2
        return m.group(1), int_conv(m.group(3))
    else:
        # Detect if first of "rxx" set
        if filename.endswith(".rar"):
            return os.path.splitext(filename)[0], 1
    return None, None


def abort_all():
    """Abort all running DirectUnpackers"""
    logging.info("Aborting all DirectUnpackers")
    for direct_unpacker in ACTIVE_UNPACKERS:
        direct_unpacker.abort()


def test_disk_performance():
    """Test the incomplete-dir performance and enable
    Direct Unpack if good enough (> 40MB/s)
    """
    if diskspeedmeasure(sabnzbd.cfg.download_dir.get_path()) > 40:
        cfg.direct_unpack.set(True)
        logging.warning(
            T("Direct Unpack was automatically enabled.")
            + " "
            + T(
                "Jobs will start unpacking during the downloading to reduce post-processing time. Only works for jobs that do not need repair."
            )
        )
    else:
        logging.info("Direct Unpack was not enabled, incomplete folder disk speed below 40MB/s")
    cfg.direct_unpack_tested.set(True)
    sabnzbd.config.save_config()
