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
import sys
import time
from typing import Optional

import sabctools

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.constants import GIGI, MEBI, PAR2_MINIMUM_MEMORY, PAR2_RESERVED_MEMORY, Status
from sabnzbd.encoding import correct_unknown_encoding
from sabnzbd.filesystem import get_ext, globber_full
from sabnzbd.misc import format_time_string, get_cpus, get_memory
from sabnzbd.nzb.object import NzbObject


def memory_limit() -> int:
    """Bytes par2 may use for its output buffers"""
    memory = get_memory()
    limit = (memory or int(512 * MEBI)) // 4
    if memory:
        limit = min(limit, max(0, memory - PAR2_RESERVED_MEMORY - cfg.cache_limit.get_int()))
    if sys.maxsize <= 2**32:
        limit = min(limit, int(GIGI))
    return max(limit, PAR2_MINIMUM_MEMORY)


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

    def open(self, extrafiles: list[str]) -> sabctools.Par2Result:
        """Create the repairer and read the par2 packets."""
        basepath = os.path.dirname(self.parfile)

        cpus = get_cpus()
        self.repairer = sabctools.Par2Repairer(
            self.parfile,
            extrafiles=extrafiles,
            basepath=basepath,
            memory_limit=memory_limit(),
            threads=max(1, cpus - 1) if cpus else 0,
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
                "Loaded par2 set %s: %s recoverable files, %s source blocks, %s recovery blocks (%s)",
                self.setname,
                self.repairer.recoverable_file_count,
                self.repairer.source_block_count,
                self.repairer.recovery_block_count,
                self.repairer.creator or "creator unknown",
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

    def truncate_to_par2_sizes(self):
        """Cut the files this job downloaded back to the size the par2 set records"""
        # A file in a subdirectory may be named with either separator
        by_name = {os.path.normpath(nzf.filename): nzf for nzf in self.nzo.finished_files}
        for entry in self.repairer.files:
            nzf = by_name.get(os.path.normpath(correct_unknown_encoding(entry["name"])))
            path = entry["target"]
            if not nzf or not os.path.isfile(path):
                continue
            size, wanted = os.path.getsize(path), entry["size"]
            if size <= wanted:
                continue
            # Only what lies past the data of every article can be cut off
            if any(
                article.on_disk
                and article.data_begin is not None
                and article.data_begin + (article.data_size or 0) > wanted
                for article in nzf.decodetable
            ):
                continue
            try:
                os.truncate(path, wanted)
            except OSError:
                logging.debug("Could not truncate %s", path, exc_info=True)
                continue
            logging.debug("Truncated %s from %s to %s bytes, the size the par2 set records", path, size, wanted)

    def apply_known_blocks(self):
        """Hand par2 the blocks the download already vouched for, if enabled"""
        try:
            known = article_backed_blocks(self.nzo, self.repairer)
            if not known:
                return
            self.repairer.set_known_blocks(known)
        except Exception:
            logging.info("Could not use article checksums for %s, verifying in full", self.setname, exc_info=True)
            return

        logging.info(
            "Quick verify: %s of %s files in set %s covered by verified articles",
            len(known),
            self.repairer.recoverable_file_count,
            self.setname,
        )

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
            logging.info(
                "Verified %s in %s, all files correct (%s file(s) taken from article checksums)",
                self.setname,
                elapsed,
                self.repairer.quick_verified_files,
            )
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
        targets = [entry["target"] for entry in self.repairer.files]

        result = self.repairer.repair()

        if renames:
            # renamed_file() wants {new_name: old_name} in bare filenames
            self.nzo.renamed_file({os.path.basename(new): os.path.basename(old) for old, new in renames.items()})

        if result == sabctools.Par2Result.SUCCESS:
            self.nzo.par2_rewritten.update(targets)
            elapsed = format_time_string(time.time() - self.stage_start)
            self.nzo.set_unpack_info("Repair", T("[%s] Repaired in %s") % (self.setname, elapsed))
            logging.info("Repaired %s in %s", self.setname, elapsed)
            if in_place := self.repairer.in_place_files:
                logging.debug("Repaired in place in %s: %s", self.setname, ", ".join(in_place))
        return result

    @property
    def last_error(self) -> Optional["sabctools.Par2LastError"]:
        """Why the last call failed, or None where it did not."""
        return self.repairer.last_error if self.repairer else None

    @property
    def block_shortfall(self) -> int:
        """How many more recovery blocks would make this repairable."""
        return max(0, self.repairer.missing_block_count - self.repairer.recovery_block_count)

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


def article_backed_blocks(nzo: NzbObject, repairer: sabctools.Par2Repairer) -> dict[str, list[Optional[bool]]]:
    """What the articles say of each par2 block of the direct-written files: present, missing or unknown"""
    if not cfg.par2_quick_verify():
        return {}

    blocksize = repairer.block_size
    if not blocksize:
        return {}

    # A file in a subdirectory may be named with either separator
    by_name = {os.path.normpath(nzf.filename): nzf for nzf in nzo.finished_files}
    known = {}
    for entry in repairer.files:
        if entry["target"] in nzo.par2_rewritten:
            continue
        if nzf := by_name.get(os.path.normpath(correct_unknown_encoding(entry["name"]))):
            checksums = repairer.block_checksums(entry["name"])
            if blocks := _blocks_from_articles(
                nzf, blocksize, entry["blocks"], entry["target"], entry["size"], checksums
            ):
                known[entry["name"]] = blocks
    return known


def _blocks_from_articles(
    nzf, blocksize: int, blockcount: int, target: str, size: int, checksums: Optional[list[int]]
) -> Optional[list[Optional[bool]]]:
    """Mark each block of one file present where the articles covering it prove it holds what
    par2 records for it, missing where it overlaps data known to be lost, and unknown otherwise"""
    if not nzf.direct_written or not checksums or len(checksums) != blockcount:
        return None

    try:
        filesize = os.path.getsize(target)
    except OSError:
        return None

    # crc32 is None when the article failed its yEnc check or never arrived
    good = []
    lost = []
    previous_end = 0
    since_good = []
    for article in nzf.decodetable:
        placed = article.data_begin is not None and article.data_size
        if article.crc32 is not None and article.on_disk and placed:
            if since_good and all(other.crc32 is None for other in since_good):
                lost.append((previous_end, article.data_begin))
            since_good = []
            previous_end = article.data_begin + article.data_size
            good.append(article)
            continue
        if article.crc32 is None and placed:
            lost.append((article.data_begin, article.data_begin + article.data_size))
        since_good.append(article)
    if since_good and all(other.crc32 is None for other in since_good):
        lost.append((previous_end, filesize))
    if not good and not lost:
        return None

    if filesize == size and _whole_file_matches(nzf, good, size, _par2_file_crc(checksums, blocksize, size)):
        blocks = [True] * blockcount
    else:
        pieces = _pieces_by_block(good, blocksize)
        blocks = []
        for block in range(blockcount):
            start = block * blocksize
            # par2 pads the final block
            end = min(start + blocksize, filesize)
            if start >= filesize:
                blocks.append(False)
            elif _block_matches(pieces.get(block, []), start, end, blocksize, checksums[block]):
                blocks.append(True)
            elif any(lost_start < end and lost_end > start for lost_start, lost_end in lost):
                blocks.append(False)
            else:
                blocks.append(None)

    # Nothing is taken on trust that is not yet on the disk
    if any(blocks):
        try:
            with open(target, "rb+") as handle:
                os.fsync(handle.fileno())
        except OSError:
            logging.info("Could not flush %s to disk, so par2 checks it in full", target, exc_info=True)
            return None

    return blocks


def _par2_file_crc(checksums: list[int], blocksize: int, size: int) -> int:
    """The CRC32 of a whole file from the CRC32 par2 records for each of its blocks"""
    crc = 0
    full, tail = divmod(size, blocksize)
    for checksum in checksums[:full]:
        crc = sabctools.crc32_combine(crc, checksum, blocksize)
    if tail:
        crc = sabctools.crc32_combine(crc, sabctools.crc32_zero_unpad(checksums[full], blocksize - tail), tail)
    return crc


def _whole_file_matches(nzf, good: list, size: int, par2_crc: int) -> bool:
    """Every article arrived intact, they lie end to end over the whole file, and together
    they hold what par2 records for it"""
    if nzf.crc32 is None or nzf.crc32 != par2_crc or len(good) != len(nzf.decodetable):
        return False
    # Articles lie end to end in decodetable order, the order nzf.crc32 is combined in
    position = 0
    for article in good:
        if article.data_begin != position or article.decoded_size != article.data_size:
            return False
        position += article.data_size
    return position == size


def _pieces_by_block(good: list, blocksize: int) -> dict[int, list[tuple[int, int, int]]]:
    """The (start, length, crc32) of each piece of the good articles, by the block it lies in"""
    pieces: dict[int, list[tuple[int, int, int]]] = {}
    for article in good:
        if article.block_size != blocksize or article.block_crcs is None or article.decoded_size != article.data_size:
            continue
        position = article.data_begin
        end = article.data_begin + article.data_size
        article_pieces = []
        for crc in article.block_crcs:
            piece_end = min((position // blocksize + 1) * blocksize, end)
            article_pieces.append((position // blocksize, (position, piece_end - position, crc)))
            position = piece_end
        # Pieces that do not add up to the article are not used
        if position == end:
            for block, piece in article_pieces:
                pieces.setdefault(block, []).append(piece)
    return pieces


def _block_matches(pieces: list[tuple[int, int, int]], start: int, end: int, blocksize: int, checksum: int) -> bool:
    """The pieces lie end to end over the block and together hold the CRC32 par2 records for it"""
    crc = 0
    position = start
    for piece_start, length, piece_crc in sorted(pieces):
        if piece_start != position:
            return False
        crc = sabctools.crc32_combine(crc, piece_crc, length)
        position += length
    if position != end:
        return False
    if end - start < blocksize:
        checksum = sabctools.crc32_zero_unpad(checksum, blocksize - (end - start))
    return crc == checksum


def parfile_paths(nzo: NzbObject) -> list[str]:
    """Every par2 file for this job on disk that is not still being downloaded"""
    pending = {nzf.filename for nzf in nzo.files}
    for extrapars in nzo.extrapars.values():
        pending.update(nzf.filename for nzf in extrapars if not nzf.completed)
    return [
        path
        for path in globber_full(nzo.download_path)
        if get_ext(path) == ".par2" and os.path.basename(path) not in pending
    ]


def joinable_matches(session: RepairSession, joinables: list[str]) -> list[str]:
    """Joinables par2 took data from, so par_cleanup can remove them"""
    if not joinables:
        return []

    by_name = {os.path.basename(path): path for path in joinables}
    used = []
    for filename in session.blocks_from:
        if path := by_name.get(os.path.basename(filename)):
            if path not in used:
                used.append(path)
    return used
