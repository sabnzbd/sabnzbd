#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.par2repair - verify and repair par2 sets in-process
"""

import logging
import os
import time
from typing import Optional

import sabctools

import sabnzbd
from sabnzbd.constants import Status
from sabnzbd.filesystem import get_ext, globber, globber_full
from sabnzbd.misc import format_time_string
from sabnzbd.nzb.object import NzbObject


class RepairSession:
    """A par2 set being verified and repaired, and the repairer working on it."""

    def __init__(self, nzo: NzbObject, setname: str, parfile: str):
        self.nzo = nzo
        self.setname = setname
        self.parfile = parfile
        self.repairer: Optional[sabctools.Par2Repairer] = None

        # Absolute paths already handed to par2, so a re-add only loads what is new
        self.loaded_parfiles: set[str] = set()
        self.verified = False

        # Blocks par2 took from each file it scanned
        self.blocks_from: dict[str, int] = {}

        # Progress bookkeeping, reset per stage
        self.stage_start = time.time()
        self.last_percent = -1
        self.files_seen = 0
        self.file_count = 0

    def open(self) -> sabctools.Par2Result:
        """Create the repairer and read the par2 packets."""
        basepath = os.path.dirname(self.parfile)

        # Files par2 may scan to find renamed or obfuscated members of the set, leaving out
        # those another set of the job describes
        if len(self.nzo.extrapars) == 1 or len(globber(basepath, self.setname + "*")) < 2:
            candidates = globber_full(basepath, "*")
        else:
            candidates = globber_full(basepath, self.setname + "*")
        claimed = _other_sets_files(self.nzo, self.setname)
        extrafiles = [
            path
            for path in candidates
            if os.path.isfile(path) and get_ext(path) != ".par2" and os.path.normcase(path) not in claimed
        ]
        self.repairer = sabctools.Par2Repairer(
            self.parfile,
            extrafiles=extrafiles,
            basepath=basepath,
        )
        self.repairer.progress_callback = self._on_progress
        self.repairer.file_done_callback = self._on_file_done
        self.repairer.error_callback = self._on_error
        self.repairer.warning_callback = self._on_warning

        self.loaded_parfiles.add(os.path.abspath(self.parfile))

        self.stage_start = time.time()
        result = self.repairer.load(volumes=False)
        if result == sabctools.Par2Result.SUCCESS:
            try:
                self.add_parfiles(parfile_paths(self.nzo))
            except sabctools.Par2Error:
                logging.info("Could not load the other par2 files of %s", self.setname, exc_info=True)
            logging.info(
                "Loaded par2 set %s: %s recoverable files, %s source blocks, %s recovery blocks",
                self.setname,
                self.repairer.recoverable_file_count,
                self.repairer.source_block_count,
                self.repairer.recovery_block_count,
            )
        return result

    def add_parfiles(self, paths: list[str]) -> int:
        """Feed newly downloaded par2 files in without re-verifying.

        Returns the recovery block count afterwards.
        """
        fresh = []
        for path in paths:
            absolute = os.path.abspath(path)
            if absolute not in self.loaded_parfiles and os.path.exists(absolute):
                fresh.append(absolute)

        if not fresh:
            return self.repairer.recovery_block_count

        blocks = self.repairer.load_more(fresh)
        self.loaded_parfiles.update(fresh)
        logging.info(
            "Added %s par2 file(s) to set %s, now %s recovery blocks",
            len(fresh),
            self.setname,
            blocks,
        )
        return blocks

    def close(self):
        """Drop the repairer. Any in-flight verify or repair is asked to stop first."""
        if self.repairer is not None:
            self.repairer.cancel()
            self.repairer.progress_callback = None
            self.repairer.file_done_callback = None
            self.repairer = None

    def verify(self) -> sabctools.Par2Result:
        self.nzo.status = Status.VERIFYING
        self.stage_start = time.time()
        self.last_percent = -1
        self.files_seen = 0
        self.file_count = self.repairer.recoverable_file_count

        result = self.repairer.verify()
        self.verified = result in (
            sabctools.Par2Result.SUCCESS,
            sabctools.Par2Result.REPAIR_POSSIBLE,
            sabctools.Par2Result.REPAIR_NOT_POSSIBLE,
        )

        elapsed = format_time_string(time.time() - self.stage_start)
        if result == sabctools.Par2Result.SUCCESS:
            self.nzo.set_unpack_info("Repair", T("[%s] Verified in %s, all files correct") % (self.setname, elapsed))
            logging.info("Verified %s in %s, all files correct", self.setname, elapsed)
        else:
            self.nzo.set_unpack_info("Repair", T("[%s] Verified in %s, repair is required") % (self.setname, elapsed))
            logging.info(
                "Verified %s in %s, repair required: %s damaged, %s missing, %s renamed, %s of %s blocks missing",
                self.setname,
                elapsed,
                self.repairer.damaged_file_count,
                self.repairer.missing_file_count,
                self.repairer.renamed_file_count,
                self.repairer.missing_block_count,
                self.repairer.source_block_count,
            )
        return result

    def repair(self) -> sabctools.Par2Result:
        self.nzo.status = Status.REPAIRING
        self.stage_start = time.time()
        self.last_percent = -1
        self.file_count = self.repairer.recoverable_file_count
        self.nzo.set_action_line(T("Repairing"), "%2d%%" % 0)

        # repair() clears the renames
        renames = self.repairer.renames

        result = self.repairer.repair()

        if renames:
            # renamed_file() wants {new_name: old_name}, relative to the download folder
            base = self.nzo.download_path
            self.nzo.renamed_file(
                {os.path.relpath(new, base): os.path.relpath(old, base) for old, new in renames.items()}
            )

        if result == sabctools.Par2Result.SUCCESS:
            elapsed = format_time_string(time.time() - self.stage_start)
            self.nzo.set_unpack_info("Repair", T("[%s] Repaired in %s") % (self.setname, elapsed))
            logging.info("Repaired %s in %s", self.setname, elapsed)
        return result

    def files_used(self, joinables: list[str]) -> tuple[list[str], list[str]]:
        """The joinables par2 took blocks from, so par_cleanup can remove them, and the full paths
        of the extra files it took blocks from that are neither part of the finished set nor
        described by another set of the job. Must be called before repair().
        """
        by_name = {os.path.basename(path): path for path in joinables}
        kept = {os.path.normcase(entry["target"]) for entry in self.repairer.files}
        kept |= {os.path.normcase(path) for path in self.repairer.renames}
        kept |= {os.path.normcase(path) for path in joinables}
        kept |= _other_sets_files(self.nzo, self.setname)

        used_joinables = []
        used_extras = []
        for filename in self.blocks_from:
            if (path := by_name.get(os.path.basename(filename))) and path not in used_joinables:
                used_joinables.append(path)
            path = os.path.join(self.nzo.download_path, filename)
            if os.path.normcase(path) not in kept and path not in used_extras:
                used_extras.append(path)
        return used_joinables, used_extras

    def fail(self, result: sabctools.Par2Result):
        """Fail the job with the reason par2 gives for a non-success Par2Result, and drop this session"""
        error = self.last_error

        # Only a write par2 could not finish points at a full disk
        if error and error["code"] in (
            sabctools.Par2ErrorCode.FILE_CREATE_FAILED,
            sabctools.Par2ErrorCode.FILE_WRITE_FAILED,
        ):
            msg = T("Repairing failed, %s") % T("Disk full")
        elif result == sabctools.Par2Result.MEMORY_ERROR:
            msg = T("Repairing failed, %s") % T("Out of memory")
        elif error and error["message"]:
            msg = T("Repairing failed, %s") % error["message"]
        else:
            msg = T("Repairing failed, %s") % result.name

        self.nzo.fail_msg = msg
        self.nzo.set_unpack_info("Repair", msg, self.setname)
        self.nzo.status = Status.FAILED
        if error:
            logging.info(
                "Repair of %s failed: %s: %s%s",
                self.setname,
                result.name,
                error["message"],
                " (%s)" % error["filename"] if error["filename"] else "",
            )
        else:
            logging.info("Repair of %s failed: %s", self.setname, result.name)
        discard(self.nzo, self.setname)

    def fetch_blocks(self, needed: int) -> bool:
        """Queue par2 files holding at least needed more recovery blocks, False when the job has none left"""
        added = self.nzo.get_extra_blocks(self.setname, needed)
        if not added:
            return False
        self.nzo.set_action_line(T("Fetching"), T("Fetching %s blocks...") % str(added))
        self.nzo.status = Status.FETCHING
        return True

    @property
    def last_error(self) -> Optional["sabctools.Par2LastError"]:
        """Why the last call failed, or None where it did not."""
        return self.repairer.last_error if self.repairer else None

    def _on_error(self, code: sabctools.Par2ErrorCode, message: str, filename: str):
        """Called from par2's worker threads once per error, as it is found."""
        try:
            if filename:
                logging.info("par2 error in %s: %s: %s (%s)", self.setname, code.name, message, filename)
            else:
                logging.info("par2 error in %s: %s: %s", self.setname, code.name, message)
        except Exception:
            logging.debug("Failed to report a par2 error", exc_info=True)

    def _on_warning(self, code: sabctools.Par2WarningCode, message: str, filename: str):
        """Called from par2's worker threads once per warning, as it is found."""
        try:
            if filename:
                logging.info("par2 warning in %s: %s: %s (%s)", self.setname, code.name, message, filename)
            else:
                logging.info("par2 warning in %s: %s: %s", self.setname, code.name, message)
        except Exception:
            logging.debug("Failed to report a par2 warning", exc_info=True)

    def _on_file_done(self, filename: str, blocks_found: int, blocks_total: int):
        """One call per file par2 finishes scanning."""
        try:
            if blocks_found:
                self.blocks_from[filename] = blocks_found
        except Exception:
            logging.debug("Failed to record par2 block source", exc_info=True)

    def _on_progress(self, stage: str, filename: str, percent: int):
        """Called from par2's worker threads while par2 holds the repairer's lock"""
        try:
            if stage == "loading":
                return

            if filename:
                self.files_seen += 1
                self.last_percent = -1

            if stage == "verifying":
                if filename:
                    self.nzo.set_action_line(T("Verifying"), "%02d/%02d" % (self.files_seen, self.file_count))
            elif stage == "repairing":
                if percent > self.last_percent:
                    self.last_percent = percent
                    self.nzo.status = Status.REPAIRING
                    self.nzo.set_action_line(
                        T("Repairing"),
                        "%2d%% %s" % (percent, sabnzbd.newsunpack.add_time_left(percent, self.stage_start)),
                    )
            elif stage == "verifying_repair":
                if filename:
                    self.nzo.set_action_line(T("Verifying repair"), "%02d/%02d" % (self.files_seen, self.file_count))
        except Exception:
            logging.debug("Failed to report par2 progress", exc_info=True)


def _other_sets_files(nzo: NzbObject, setname: str) -> set[str]:
    """The files another par2 set of the job describes, as normalised full paths"""
    paths = set()
    for other, par2pack in nzo.par2packs.items():
        if other != setname and par2pack:
            for name in par2pack:
                paths.add(os.path.normcase(os.path.join(nzo.download_path, os.path.normpath(name))))
    return paths


def get_session(nzo: NzbObject, setname: str) -> Optional[RepairSession]:
    """Return the live session for this set, if there is one."""
    session = nzo.par2_sessions.get(setname)
    if session is not None and session.repairer is not None:
        return session
    if session is not None:
        discard(nzo, setname)
    return None


def create_session(nzo: NzbObject, setname: str, parfile: str) -> RepairSession:
    session = RepairSession(nzo, setname, parfile)
    nzo.par2_sessions[setname] = session
    return session


def discard(nzo: NzbObject, setname: Optional[str] = None):
    """Drop sessions for a job, or for one of its sets."""
    for name in [setname] if setname else list(nzo.par2_sessions):
        if session := nzo.par2_sessions.pop(name, None):
            session.close()


def cancel(nzo: NzbObject):
    """Ask any in-flight verify or repair for this job to stop."""
    for setname, session in list(nzo.par2_sessions.items()):
        if repairer := session.repairer:
            logging.info("Cancelling par2 repair of %s", setname)
            repairer.cancel()


def parfile_paths(nzo: NzbObject) -> list[str]:
    """Every par2 file for this job on disk that is not still being downloaded"""
    pending = {nzf.filename for nzf in nzo.files}
    for extrapars in nzo.extrapars.values():
        # A file a retry found complete on disk is assembled without its articles loaded
        pending.update(nzf.filename for nzf in extrapars if not (nzf.completed or nzf.assembled))
    return [
        path
        for path in globber_full(nzo.download_path)
        if get_ext(path) == ".par2" and os.path.basename(path) not in pending
    ]
