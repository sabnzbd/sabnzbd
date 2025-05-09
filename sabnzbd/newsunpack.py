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
sabnzbd.newsunpack
"""

import os
import sys
import re
import subprocess
import logging
import time
import io
import shutil
import functools
from typing import Tuple, List, BinaryIO, Optional, Dict, Any, Union, Set

import sabnzbd
from sabnzbd.encoding import correct_unknown_encoding, ubtou
import sabnzbd.utils.rarfile as rarfile
from sabnzbd.misc import (
    format_time_string,
    find_on_path,
    int_conv,
    get_all_passwords,
    calc_age,
    cmp,
    run_command,
    build_and_run_command,
    format_time_left,
    is_none,
)
from sabnzbd.filesystem import (
    make_script_path,
    real_path,
    globber,
    globber_full,
    renamer,
    clip_path,
    long_path,
    remove_file,
    listdir_full,
    setname_from_path,
    get_ext,
    TS_RE,
    build_filelists,
    get_filename,
    SEVENMULTI_RE,
    is_size,
    get_basename,
)
from sabnzbd.nzbstuff import NzbObject
import sabnzbd.cfg as cfg
from sabnzbd.constants import Status, JOB_ADMIN


# Regex globals
RAR_V3_RE = re.compile(r"\.(?P<ext>part\d*)$", re.I)
RAR_EXTRACTFROM_RE = re.compile(r"^Extracting\sfrom\s(.+)")
RAR_EXTRACTED_RE = re.compile(r"^(Extracting|Creating|...)\s+(.*?)\s+OK\s*$")
SEVENZIP_PATH_RE = re.compile("^Path = (.+)")
PAR2_TARGET_RE = re.compile(r'^(?:File|Target): "(.+)" -')
PAR2_BLOCK_FOUND_RE = re.compile(r'File: "([^"]+)" - found \d+ of \d+ data blocks from "([^"]+)"')
PAR2_IS_MATCH_FOR_RE = re.compile(r'File: "([^"]+)" - is a match for "([^"]+)"')
PAR2_FILENAME_RE = re.compile(r'"([^"]+)"')

# Constants
SEVENZIP_ID = b"7z\xbc\xaf'\x1c"
PAR2_COMMAND = None
MULTIPAR_COMMAND = None
RAR_COMMAND = None
NICE_COMMAND = None
SEVENZIP_COMMAND = None
IONICE_COMMAND = None
RAR_PROBLEM = False
PAR2_TURBO = True
RAR_VERSION = 0
SEVENZIP_VERSION = ""


def find_programs(curdir: str):
    """Find external programs"""

    def check(path: str, program: str) -> Optional[str]:
        p = os.path.abspath(os.path.join(path, program))
        if os.access(p, os.X_OK):
            return p
        else:
            return None

    if sabnzbd.MACOS:
        if sabnzbd.MACOSARM64:
            # M1 (ARM64) versions
            sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, "macos/par2/arm64/par2")
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, "macos/unrar/arm64/unrar")
        else:
            # Regular x64 versions
            sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, "macos/par2/par2")
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, "macos/unrar/unrar")
        # The 7zip binary is universal2
        sabnzbd.newsunpack.SEVENZIP_COMMAND = check(curdir, "macos/7zip/7zz")

    if sabnzbd.WINDOWS:
        sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, "win/par2/par2.exe")
        sabnzbd.newsunpack.RAR_COMMAND = check(curdir, "win/unrar/UnRAR.exe")
        sabnzbd.newsunpack.SEVENZIP_COMMAND = check(curdir, "win/7zip/7za.exe")
    else:
        if not sabnzbd.newsunpack.PAR2_COMMAND:
            sabnzbd.newsunpack.PAR2_COMMAND = find_on_path("par2")
        if not sabnzbd.newsunpack.RAR_COMMAND:
            sabnzbd.newsunpack.RAR_COMMAND = find_on_path(
                (
                    "unrar",
                    "rar",
                    "unrar3",
                    "rar3",
                )
            )
        sabnzbd.newsunpack.NICE_COMMAND = find_on_path("nice")
        sabnzbd.newsunpack.IONICE_COMMAND = find_on_path("ionice")

        # p7zip is the old Linux port of 7-Zip, now unmaintained.
        # Therefore the official filenames are different for Linux:
        #
        # 7zz  (7-Zip) - full version of 7-Zip that supports all formats.
        # 7zzs (7-Zip) - full version of 7-Zip that supports all formats (static linked).
        #
        # 7z   (p7zip) - older linux port that requires 7z.so shared library, supports all formats via 7z.so.
        # 7za  (p7zip) - older linux port that supports some main formats:
        #                  7z, xz, lzma, zip, bzip2, gzip, tar, cab, ppmd and split.

        if not sabnzbd.newsunpack.SEVENZIP_COMMAND:
            sabnzbd.newsunpack.SEVENZIP_COMMAND = find_on_path(
                (
                    "7zz",
                    "7zzs",
                    "7za",
                    "7z",
                )
            )

    if not (sabnzbd.WINDOWS or sabnzbd.MACOS):
        # Run check on rar version
        version, original = unrar_check(sabnzbd.newsunpack.RAR_COMMAND)
        sabnzbd.newsunpack.RAR_PROBLEM = not original or version < sabnzbd.constants.REC_RAR_VERSION
        sabnzbd.newsunpack.RAR_VERSION = version

        # Run check on 7zip
        sabnzbd.newsunpack.SEVENZIP_VERSION = sevenzip_check(sabnzbd.newsunpack.SEVENZIP_COMMAND)

        # Run check on par2-multicore
        sabnzbd.newsunpack.PAR2_TURBO = par2_turbo_check(sabnzbd.newsunpack.PAR2_COMMAND)

    # Set the path for rarfile
    rarfile.UNRAR_TOOL = sabnzbd.newsunpack.RAR_COMMAND


ENV_NZO_FIELDS = [
    "bytes",
    "bytes_downloaded",
    "bytes_tried",
    "cat",
    "correct_password",
    "duplicate",
    "duplicate_key",
    "encrypted",
    "fail_msg",
    "filename",
    "final_name",
    "group",
    "nzo_id",
    "oversized",
    "password",
    "pp",
    "priority",
    "repair",
    "script",
    "status",
    "unpack",
    "unwanted_ext",
    "url",
]


def external_processing(
    extern_proc: str, nzo: NzbObject, complete_dir: str, nicename: str, status: int
) -> Tuple[str, int]:
    """Run a user postproc script, return console output and exit value"""
    failure_url = nzo.nzo_info.get("failure", "")
    # Items can be bool or null, causing POpen to fail
    command = [
        str(extern_proc),
        str(complete_dir),
        str(nzo.filename),
        str(nicename),
        "",
        str(nzo.cat),
        str(nzo.group),
        str(status),
        str(failure_url),
    ]

    # Add path to original NZB
    nzb_paths = globber_full(nzo.admin_path, "*.gz")

    # Fields not in the NZO directly
    extra_env_fields = {
        "failure_url": failure_url,
        "complete_dir": complete_dir,
        "pp_status": status,
        "download_time": nzo.nzo_info.get("download_time", ""),
        "avg_bps": int(nzo.avg_bps_total / nzo.avg_bps_freq) if nzo.avg_bps_freq else 0,
        "age": calc_age(nzo.avg_date),
        "orig_nzb_gz": clip_path(nzb_paths[0]) if nzb_paths else "",
    }

    # Make sure that if we run a Python script it's output is unbuffered, so we can show it to the user
    if extern_proc.endswith(".py"):
        extra_env_fields["pythonunbuffered"] = True

    try:
        p = build_and_run_command(command, env=create_env(nzo, extra_env_fields))
        sabnzbd.PostProcessor.external_process = p

        # Follow the output, so we can abort it
        lines = []
        while 1:
            line = p.stdout.readline()
            if not line:
                break
            line = line.strip()
            lines.append(line)

            # Show current line in history
            nzo.set_action_line(T("Running script"), line)
    except Exception:
        logging.debug("Failed script %s, Traceback: ", extern_proc, exc_info=True)
        return "Cannot run script %s\r\n" % extern_proc, -1

    output = "\n".join(lines)
    ret = p.wait()
    return output, ret


def unpacker(
    nzo: NzbObject,
    workdir_complete: str,
    one_folder: bool,
    joinables: List[str] = [],
    rars: List[str] = [],
    sevens: List[str] = [],
    ts: List[str] = [],
    depth: int = 0,
) -> Tuple[Union[int, bool], List[str]]:
    """Do a recursive unpack from all archives in 'download_path' to 'workdir_complete'"""
    if depth > 2:
        # Prevent going to deep down the rabbit-hole
        nzo.set_unpack_info("Unpack", T("Unpack nesting too deep [%s]") % nzo.final_name)
        logging.info(T("Unpack nesting too deep [%s]"), nzo.final_name)
        return False, []
    depth += 1

    if depth == 1:
        # First time, ignore anything in workdir_complete
        xjoinables, xrars, xsevens, xts = build_filelists(nzo.download_path)
    else:
        xjoinables, xrars, xsevens, xts = build_filelists(nzo.download_path, workdir_complete, check_both=nzo.delete)

    force_rerun = False
    newfiles = []
    error = None
    new_joins = new_ts = None

    if cfg.enable_filejoin():
        new_joins = [jn for jn in xjoinables if jn not in joinables]
        if new_joins:
            logging.info("Filejoin starting on %s", nzo.download_path)
            error, newf = file_join(nzo, workdir_complete, new_joins)
            if newf:
                newfiles.extend(newf)
            logging.info("Filejoin finished on %s", nzo.download_path)

    if cfg.enable_unrar():
        new_rars = [rar for rar in xrars if rar not in rars]
        if new_rars:
            logging.info("Unrar starting on %s", nzo.download_path)
            error, newf = rar_unpack(nzo, workdir_complete, one_folder, new_rars)
            if newf:
                newfiles.extend(newf)
            logging.info("Unrar finished on %s", nzo.download_path)

    if cfg.enable_7zip() and SEVENZIP_COMMAND:
        new_sevens = [seven for seven in xsevens if seven not in sevens]
        if new_sevens:
            logging.info("7za starting on %s", nzo.download_path)
            error, newf = unseven(nzo, workdir_complete, one_folder, new_sevens)
            if newf:
                newfiles.extend(newf)
            logging.info("7za finished on %s", nzo.download_path)

    if cfg.enable_tsjoin():
        new_ts = [_ts for _ts in xts if _ts not in ts]
        if new_ts:
            logging.info("TS Joining starting on %s", nzo.download_path)
            error, newf = file_join(nzo, workdir_complete, new_ts)
            if newf:
                newfiles.extend(newf)
            logging.info("TS Joining finished on %s", nzo.download_path)

    # Refresh history and set output
    nzo.set_action_line()

    # Only re-run if something was unpacked and it was success
    rerun = error in (False, 0)

    # During a Retry we might miss files in the complete folder
    # that failed during recursive unpack in the first run
    if nzo.reuse and depth == 1 and any(build_filelists(workdir=None, workdir_complete=workdir_complete)):
        rerun = True

    # We can't recursive unpack on long paths on Windows
    # See: https://github.com/sabnzbd/sabnzbd/pull/771
    if sabnzbd.WINDOWS and len(workdir_complete) > 256:
        rerun = False

    # Double-check that we didn't miss any files in workdir
    # But only if dele=True, otherwise of course there will be files left
    if rerun and nzo.delete and depth == 1 and any(build_filelists(nzo.download_path)):
        force_rerun = True
        # Clear lists to force re-scan of files
        xjoinables, xrars, xsevens, xts = ([], [], [], [])

    if rerun and (cfg.enable_recursive() or new_ts or new_joins or force_rerun):
        z, y = unpacker(nzo, workdir_complete, one_folder, xjoinables, xrars, xsevens, xts, depth)
        if z:
            error = z
        if y:
            newfiles.extend(y)

    return error, newfiles


##############################################################################
# Filejoin Functions
##############################################################################
def match_ts(file: str) -> Tuple[str, int]:
    """Return True if file is a joinable TS file"""
    match = TS_RE.search(file)
    if not match:
        return "", 0

    num = int(match.group(1))
    try:
        setname = file[: match.start()]
        setname += ".ts"
    except Exception:
        setname = ""
    return setname, num


def clean_up_joinables(names: List[str]):
    """Remove joinable files and their .1 backups"""
    for name in names:
        if os.path.exists(name):
            try:
                remove_file(name)
            except Exception:
                pass
        name1 = name + ".1"
        if os.path.exists(name1):
            try:
                remove_file(name1)
            except Exception:
                pass


def get_seq_number(name: str) -> int:
    """Return sequence number if name as an int"""
    head, tail = os.path.splitext(name)
    if tail == ".ts":
        _, num = match_ts(name)
    else:
        num = tail[1:]
    if num.isdigit():
        return int(num)
    else:
        return 0


def file_join(nzo: NzbObject, workdir_complete: str, joinables: List[str]) -> Tuple[bool, List[str]]:
    """Join and joinable files in 'workdir' to 'workdir_complete' and
    when successful, delete originals
    """
    newfiles = []
    bufsize = 24 * 1024 * 1024

    # Create matching sets from the list of files
    joinable_sets = {}
    joinable_set = None
    for joinable in joinables:
        head, tail = os.path.splitext(joinable)
        if tail == ".ts":
            head, _ = match_ts(joinable)
        if head not in joinable_sets:
            joinable_sets[head] = []
        joinable_sets[head].append(joinable)
    logging.debug("joinable_sets: %s", joinable_sets)

    try:
        # Handle each set
        for joinable_set in joinable_sets:
            current = joinable_sets[joinable_set]
            joinable_sets[joinable_set].sort()

            # If par2 already did the work, just remove the files
            if os.path.exists(joinable_set):
                logging.debug("file_join(): Skipping %s, (probably) joined by par2", joinable_set)
                if nzo.delete:
                    clean_up_joinables(current)
                # done, go to next set
                continue

            # Only join when there is more than one file
            size = len(current)
            if size < 2:
                continue

            # Prepare joined file
            filename = joinable_set
            if workdir_complete:
                filename = filename.replace(nzo.download_path, workdir_complete)
            logging.debug("file_join(): Assembling %s", filename)

            # Join the segments
            with open(filename, "ab") as joined_file:
                n = get_seq_number(current[0])
                seq_error = n > 1
                for joinable in current:
                    if get_seq_number(joinable) != n:
                        seq_error = True
                    perc = (100.0 / size) * n
                    logging.debug("Processing %s", joinable)
                    nzo.set_action_line(T("Joining"), "%.0f%%" % perc)
                    with open(joinable, "rb") as f:
                        shutil.copyfileobj(f, joined_file, bufsize)
                    if nzo.delete:
                        remove_file(joinable)
                    n += 1

            # Remove any remaining .1 files
            clean_up_joinables(current)

            # Finish up
            newfiles.append(filename)

            setname = setname_from_path(joinable_set)
            if seq_error:
                msg = T("Incomplete sequence of joinable files")
                nzo.fail_msg = T("File join of %s failed") % setname
                nzo.set_unpack_info("Filejoin", T('[%s] Error "%s" while joining files') % (setname, msg))
                logging.error(T('Error "%s" while running file_join on %s'), msg, nzo.final_name)
                return True, []
            else:
                msg = T("[%s] Joined %s files") % (joinable_set, size)
                nzo.set_unpack_info("Filejoin", msg, setname)
    except Exception:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T("File join of %s failed") % msg
        nzo.set_unpack_info(
            "Filejoin", T('[%s] Error "%s" while joining files') % (setname_from_path(joinable_set), msg)
        )
        logging.error(T('Error "%s" while running file_join on %s'), msg, nzo.final_name)
        return True, []

    return False, newfiles


##############################################################################
# (Un)Rar Functions
##############################################################################
def rar_unpack(nzo: NzbObject, workdir_complete: str, one_folder: bool, rars: List[str]) -> Tuple[int, List[str]]:
    """Unpack multiple sets 'rars' of RAR files from 'download_path' to 'workdir_complete.
    When 'delete' is set, originals will be deleted.
    When 'one_folder' is set, all files will be in a single folder
    """
    fail = 0
    newfiles = extracted_files = []
    rar_sets = {}
    for rar in rars:
        rar_set = setname_from_path(rar)
        if RAR_V3_RE.search(rar_set):
            # Remove the ".partXX" part
            rar_set = get_basename(rar_set)
        if rar_set not in rar_sets:
            rar_sets[rar_set] = []
        rar_sets[rar_set].append(rar)

    logging.debug("Rar_sets: %s", rar_sets)

    for rar_set in rar_sets:
        # Run the RAR extractor
        rar_sets[rar_set].sort(key=functools.cmp_to_key(rar_sort))

        rarpath = rar_sets[rar_set][0]

        if workdir_complete and rarpath.startswith(nzo.download_path):
            extraction_path = workdir_complete
        else:
            extraction_path = os.path.split(rarpath)[0]

        # Is the direct-unpacker still running? We wait for it
        if nzo.direct_unpacker:
            wait_count = 0
            last_stats = nzo.direct_unpacker.get_formatted_stats()
            while nzo.direct_unpacker.is_alive():
                logging.debug("DirectUnpacker still alive for %s: %s", nzo.final_name, last_stats)

                # Bump the file-lock in case it's stuck
                with nzo.direct_unpacker.next_file_lock:
                    nzo.direct_unpacker.next_file_lock.notify()
                time.sleep(2)

                # Did something change? Might be stuck
                if last_stats == nzo.direct_unpacker.get_formatted_stats():
                    wait_count += 1
                    if wait_count > 60:
                        # We abort after 2 minutes of no changes
                        nzo.direct_unpacker.abort()
                else:
                    wait_count = 0
                last_stats = nzo.direct_unpacker.get_formatted_stats()

        # Did we already direct-unpack it? Not when recursive-unpacking
        if nzo.direct_unpacker and rar_set in nzo.direct_unpacker.success_sets:
            logging.info("Set %s completed by DirectUnpack", rar_set)
            fail = 0
            success = True
            rars, newfiles = nzo.direct_unpacker.success_sets.pop(rar_set)
        else:
            logging.info("Extracting rarfile %s (belonging to %s) to %s", rarpath, rar_set, extraction_path)
            try:
                fail, newfiles, rars = rar_extract(
                    rarpath, len(rar_sets[rar_set]), one_folder, nzo, rar_set, extraction_path
                )
                success = not fail
            except Exception:
                success = False
                fail = 1
                msg = sys.exc_info()[1]
                nzo.fail_msg = T("Unpacking failed, %s") % msg
                setname = nzo.final_name
                nzo.set_unpack_info("Unpack", T('[%s] Error "%s" while unpacking RAR files') % (setname, msg))

                logging.error(T('Error "%s" while running rar_unpack on %s'), msg, setname)
                logging.debug("Traceback: ", exc_info=True)

        if success:
            logging.debug("rar_unpack(): Rars: %s", rars)
            logging.debug("rar_unpack(): Newfiles: %s", newfiles)
            extracted_files.extend(newfiles)

        # Do not fail if this was a recursive unpack
        if fail and rarpath.startswith(workdir_complete):
            # Do not delete the files, leave it to user!
            logging.info("Ignoring failure to do recursive unpack of %s", rarpath)
            fail = 0
            success = True
            newfiles = []

        # Do not fail if this was maybe just some duplicate fileset
        # Multipar and par2tbb will detect and log them, par2cmdline will not
        if fail and rar_set.endswith((".1", ".2")):
            # Just in case, we leave the raw files
            logging.info("Ignoring failure of unpack for possible duplicate file %s", rarpath)
            fail = 0
            success = True
            newfiles = []

        # Delete the old files if we have to
        if success and nzo.delete and newfiles:
            for rar in rars:
                try:
                    remove_file(rar)
                except OSError:
                    if os.path.exists(rar):
                        logging.warning(T("Deleting %s failed!"), rar)

                brokenrar = "%s.1" % rar

                if os.path.exists(brokenrar):
                    logging.info("Deleting %s", brokenrar)
                    try:
                        remove_file(brokenrar)
                    except OSError:
                        if os.path.exists(brokenrar):
                            logging.warning(T("Deleting %s failed!"), brokenrar)

    return fail, extracted_files


def rar_extract(
    rarfile_path: str, numrars: int, one_folder: bool, nzo: NzbObject, setname: str, extraction_path: str
) -> Tuple[int, List[str], List[str]]:
    """Unpack single rar set 'rarfile' to 'extraction_path',
    with password tries
    Return fail==0(ok)/fail==1(error)/fail==2(wrong password)/fail==3(crc-error), new_files, rars
    """
    fail = 0
    new_files = []
    rars = []
    passwords = get_all_passwords(nzo)

    for password in passwords:
        if password:
            logging.debug('Trying unrar with password "%s"', password)
            msg = T('Trying unrar with password "%s"') % password
            nzo.set_unpack_info("Unpack", msg, setname)
        fail, new_files, rars = rar_extract_core(
            rarfile_path, numrars, one_folder, nzo, setname, extraction_path, password
        )
        if fail != 2:
            break

    return fail, new_files, rars


def rar_extract_core(
    rarfile_path: str, numrars: int, one_folder: bool, nzo: NzbObject, setname: str, extraction_path: str, password: str
) -> Tuple[int, List[str], List[str]]:
    """Unpack single rar set 'rarfile_path' to 'extraction_path'
    Return fail==0(ok)/fail==1(error)/fail==2(wrong password)/fail==3(crc-error), new_files, rars
    """
    start = time.time()

    logging.debug("rar_extract(): Extractionpath: %s", extraction_path)

    if password:
        password_command = "-p%s" % password
    else:
        password_command = "-p-"

    ############################################################################

    if one_folder or cfg.flat_unpack():
        action = "e"
    else:
        action = "x"
    if cfg.overwrite_files():
        overwrite = "-o+"  # Enable overwrite
        rename = "-o+"  # Dummy
    else:
        overwrite = "-o-"  # Disable overwrite
        rename = "-or"  # Auto renaming

    if sabnzbd.WINDOWS:
        # On Windows, UnRar uses a custom argument parser
        # See: https://github.com/sabnzbd/sabnzbd/issues/1043
        # The -scf forces the output to be UTF8
        command = [
            RAR_COMMAND,
            action,
            "-idp",
            "-scf",
            overwrite,
            rename,
            "-ai",
            password_command,
            rarfile_path,
            "%s\\" % long_path(extraction_path),
        ]

    elif RAR_PROBLEM:
        # Use only oldest options, specifically no "-or" or "-scf"
        command = [
            RAR_COMMAND,
            action,
            "-idp",
            overwrite,
            password_command,
            rarfile_path,
            "%s/" % extraction_path,
        ]
    else:
        # The -scf forces the output to be UTF8
        command = [
            RAR_COMMAND,
            action,
            "-idp",
            "-scf",
            overwrite,
            rename,
            "-ai",
            password_command,
            rarfile_path,
            "%s/" % extraction_path,
        ]

    if cfg.ignore_unrar_dates():
        command.insert(3, "-tsm-")
    if not RAR_PROBLEM and (unrar_parameters := cfg.unrar_parameters().strip().split()):
        for param in unrar_parameters:
            command.insert(-2, param)

    # Get list of all the volumes part of this set
    logging.debug("Analyzing rar file ... %s found", rarfile.is_rarfile(rarfile_path))
    p = build_and_run_command(command, windows_unrar_command=True)
    sabnzbd.PostProcessor.external_process = p

    nzo.set_action_line(T("Unpacking"), "00/%02d" % numrars)

    # Loop over the output from rar!
    curr = 0
    extracted = []
    rarfiles = []
    fail = 0
    requires_kill = False
    inrecovery = False
    lines = []

    while 1:
        line = p.stdout.readline()
        if not line:
            break

        # Skip empty lines
        line = line.strip()
        if not line:
            continue
        lines.append(line)

        if line.startswith("Extracting from"):
            filename = re.search(RAR_EXTRACTFROM_RE, line).group(1)
            if filename not in rarfiles:
                rarfiles.append(filename)
            curr += 1
            perc = (curr / numrars) * 100
            nzo.set_action_line(T("Unpacking"), "%02d/%02d %s" % (curr, numrars, add_time_left(perc, start)))

        elif line.find("recovery volumes found") > -1:
            inrecovery = True  # and thus start ignoring "Cannot find volume" for a while
            logging.debug("unrar recovery start: %s" % line)
        elif line.startswith("Reconstruct"):
            # end of reconstruction: 'Reconstructing... 100%' or 'Reconstructing... ' (both success), or 'Reconstruction impossible'
            inrecovery = False
            logging.debug("unrar recovery result: %s" % line)

        elif line.startswith("Cannot find volume") and not inrecovery:
            filename = os.path.basename(line[19:])
            msg = T("Unpacking failed, unable to find %s") % filename
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 1

        elif line.endswith("- CRC failed"):
            msg = T("Unpacking failed, CRC error")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 2  # Older unrar versions report a wrong password as a CRC error

        elif line.startswith("File too large"):
            msg = T("Unpacking failed, file too large for filesystem (FAT?)")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 1

        elif line.startswith("Write error"):
            msg = "%s %s" % (T("Unpacking failed, write error or disk is full?"), line[11:])
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 1

        elif line.startswith("There is not enough space on the disk"):
            msg = T("Unpacking failed, disk full")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 1
            # After this is a line that requires user input ([R]etry, [A]bort), which hangs, so we need a kill
            requires_kill = True

        elif line.startswith("Cannot create"):
            line2 = p.stdout.readline()
            if "must not exceed 260" in line2:
                msg = "%s: %s" % (T("Unpacking failed, path is too long"), line[13:])
            else:
                msg = "%s %s" % (T("Unpacking failed, write error or disk is full?"), line[13:])
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 1
            # Kill the process (can stay in endless loop on Windows Server)
            requires_kill = True

        elif line.startswith("ERROR: "):
            nzo.fail_msg = line
            nzo.set_unpack_info("Unpack", line, setname)
            fail = 1

        elif (
            "The specified password is incorrect" in line
            or "Incorrect password" in line
            or ("ncrypted file" in line and (("CRC failed" in line) or ("Checksum error" in line)))
        ):
            # unrar 3.x: "Encrypted file: CRC failed in oLKQfrcNVivzdzSG22a2xo7t001.part1.rar (password incorrect ?)"
            # unrar 4.x: "CRC failed in the encrypted file oLKQfrcNVivzdzSG22a2xo7t001.part1.rar. Corrupt file or wrong password."
            # unrar 5.x: "Checksum error in the encrypted file oLKQfrcNVivzdzSG22a2xo7t001.part1.rar. Corrupt file or wrong password."
            # unrar 5.01: "The specified password is incorrect."
            # unrar 5.80: "Incorrect password for oLKQfrcNVivzdzSG22a2xo7t001.part1.rar"
            msg = T("Unpacking failed, archive requires a password")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 2

        elif "is not RAR archive" in line:
            # Unrecognizable RAR file
            msg = T("Unusable RAR file")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 3

        elif "checksum error" in line or "Unexpected end of archive" in line:
            # Corrupt archive or passworded, we can't know
            # packed data checksum error in volume FILE
            msg = T("Corrupt RAR file")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 3

        elif m := re.search(RAR_EXTRACTED_RE, line):
            # In case of flat-unpack, UnRar still prints the whole path (?!)
            unpacked_file = m.group(2)
            if cfg.flat_unpack():
                unpacked_file = os.path.basename(unpacked_file)
            extracted.append(real_path(extraction_path, unpacked_file))

        if fail:
            if requires_kill:
                p.kill()
            else:
                p.wait()
            logging.debug("UNRAR output: \n%s", "\n".join(lines))
            return fail, [], []

    if p.stdout:
        p.stdout.close()
    p.wait()

    # Which files did we use to extract this?
    rarfiles = rar_volumelist(rarfile_path, password, rarfiles)

    logging.debug("UNRAR output: \n%s", "\n".join(lines))
    msg = T("Unpacked %s files/folders in %s") % (len(extracted), format_time_string(time.time() - start))
    nzo.set_unpack_info("Unpack", msg, setname)
    logging.info(msg)

    return 0, extracted, rarfiles


##############################################################################
# 7Zip Functions
##############################################################################
def unseven(nzo: NzbObject, workdir_complete: str, one_folder: bool, sevens: List[str]):
    """Unpack multiple sets '7z' of 7Zip files from 'download_path' to 'workdir_complete.
    When 'delete' is set, originals will be deleted.
    """
    unseven_failed = False
    new_files = []

    # Find multi-volume sets, because 7zip will not provide actual set members
    seven_sets = {}
    for seven in sevens:
        setname = setname_from_path(seven)
        if SEVENMULTI_RE.search(setname):
            # Remove the ".001" part
            setname = get_basename(setname)
        if setname not in seven_sets:
            seven_sets[setname] = []
        seven_sets[setname].append(seven)

    # Unpack each set
    for seven_set in seven_sets:
        logging.info("Starting extract on 7zip set/file: %s ", seven_set)
        nzo.set_action_line(T("Unpacking"), setname_from_path(seven_set))

        # Sort, so that x.001 is the first one
        seven_sets[seven_set].sort()
        seven_path = seven_sets[seven_set][0]

        if workdir_complete and seven_path.startswith(nzo.download_path):
            extraction_path = workdir_complete
        else:
            extraction_path = os.path.split(seven_path)[0]

        res, new_files_set = seven_extract(nzo, seven_path, seven_set, extraction_path, one_folder)
        if res:
            unseven_failed = True
        elif nzo.delete:
            for seven in seven_sets[seven_set]:
                try:
                    remove_file(seven)
                except Exception:
                    logging.warning(T("Deleting %s failed!"), seven)
        new_files.extend(new_files_set)

    return unseven_failed, new_files


def seven_extract(
    nzo: NzbObject, seven_path: str, seven_set: str, extraction_path: str, one_folder: bool
) -> Tuple[int, List[str]]:
    """Unpack single set 'sevenset' to 'extraction_path', with password tries
    Return fail==0(ok)/fail==1(error)/fail==2(wrong password), new_files, sevens
    """
    fail = 0
    new_files = []

    passwords = get_all_passwords(nzo)

    for password in passwords:
        if password:
            msg = T('Trying 7zip with password "%s"') % password
            logging.debug(msg)
            nzo.set_unpack_info("Unpack", msg, seven_set)
        fail, new_files = seven_extract_core(nzo, seven_path, extraction_path, seven_set, one_folder, password)
        if fail != 2:
            # anything else than a password problem (so: OK, or disk problem):
            break

    return fail, new_files


def seven_extract_core(
    nzo: NzbObject, seven_path: str, extraction_path: str, seven_set: str, one_folder: bool, password: str
) -> Tuple[int, List[str]]:
    """Unpack single 7Z set 'sevenset' to 'extraction_path'
    Return fail==0(ok)/fail==1(error)/fail==2(wrong password), new_files, message
    """
    start = time.time()
    if one_folder or cfg.flat_unpack():
        method = "e"  # Unpack without folders
    else:
        method = "x"  # Unpack with folders
    if sabnzbd.WINDOWS or sabnzbd.MACOS:
        case = "-ssc-"  # Case insensitive
    else:
        case = "-ssc"  # Case sensitive
    if cfg.overwrite_files():
        overwrite = "-aoa"
    else:
        overwrite = "-aou"
    if password:
        password = "-p%s" % password
    else:
        password = "-p"

    # For file-bookkeeping
    orig_dir_content = listdir_full(extraction_path)

    command = [SEVENZIP_COMMAND, method, "-y", overwrite, case, password, "-o%s" % extraction_path, seven_path]
    p = build_and_run_command(command)
    sabnzbd.PostProcessor.external_process = p
    output = p.stdout.read()
    logging.debug("7za output: %s", output)

    # ret contains the 7z/7za exit code: 0 = Normal, 1 = Warning, 2 = Fatal error, etc
    ret = p.wait()

    # What's new? Use symmetric difference
    new_files = list(set(orig_dir_content) ^ set(listdir_full(extraction_path)))

    # Anything else than 0 as RC: 7z unpack had a problem
    if ret > 0:
        # Let's try to find the cause:
        if "Data Error in encrypted file. Wrong password?" in output:
            msg = T("Unpacking failed, archive requires a password")
        elif "Disk full." in output or "No space left on device" in output:
            # note: the above does not work with 7z version 16.02, and does work with 7z 19.00 and higher
            ret = 1
            msg = T("Unpacking failed, write error or disk is full?")
        elif "ERROR: CRC Failed" in output:
            ret = 1
            msg = T("Unpacking failed, CRC error")
        else:
            # Default message
            msg = T("Unpacking failed, %s") % T("see logfile")
            logging.info("7za return code: %s", ret)
        nzo.fail_msg = msg
        nzo.status = Status.FAILED
    else:
        msg = T("Unpacked %s files/folders in %s") % (len(new_files), format_time_string(time.time() - start))
        nzo.set_unpack_info("Unpack", msg, seven_set)
        logging.info(msg)

    return ret, new_files


##############################################################################
# PAR2 Functions
##############################################################################
def par2_repair(nzo: NzbObject, setname: str) -> Tuple[bool, bool]:
    """Try to repair a set, return readd and correctness"""
    # Check which of the files exists
    for new_par in nzo.extrapars[setname]:
        test_parfile = os.path.join(nzo.download_path, new_par.filename)
        if os.path.exists(test_parfile):
            parfile_nzf = new_par
            break
    else:
        # No file was found, we assume this set already finished
        logging.info("No par2 files found on disk for set %s", setname)
        return False, True

    parfile = os.path.join(nzo.download_path, parfile_nzf.filename)
    old_dir_content = os.listdir(nzo.download_path)
    used_joinables = ()
    joinables = ()
    used_for_repair = ()
    result = readd = False

    # Need to copy now, gets pop-ed during repair
    setpars = nzo.extrapars[setname][:]

    # Start QuickCheck
    nzo.status = Status.QUICK_CHECK
    nzo.set_action_line(T("Repair"), T("Quick Checking"))
    qc_result = quick_check_set(setname, nzo)
    if qc_result:
        logging.info("Quick-check for %s is OK, skipping repair", setname)
        nzo.set_unpack_info("Repair", T("[%s] Quick Check OK") % setname)
        result = True

    if not result and cfg.enable_all_par():
        # Download all par2 files that haven't been downloaded yet
        readd = False
        for extrapar in nzo.extrapars[setname][:]:
            # Make sure we only get new par2 files
            if nzo.add_parfile(extrapar):
                readd = True
        if readd:
            return readd, result

    if not result:
        nzo.status = Status.REPAIRING
        result = False
        readd = False
        try:
            nzo.set_action_line(T("Repair"), T("Starting Repair"))
            logging.info('Scanning "%s"', parfile)

            joinables, _, _, _ = build_filelists(nzo.download_path, check_rar=False)

            finished, readd, used_joinables, used_for_repair = par2cmdline_verify(parfile, nzo, setname, joinables)

            if finished:
                result = True
                logging.info("Par verify finished ok on %s!", parfile)
            else:
                logging.info("Par verify failed on %s!", parfile)
                return readd, False
        except Exception:
            msg = sys.exc_info()[1]
            nzo.fail_msg = T("Repairing failed, %s") % msg
            logging.error(T("Error %s while running par2_repair on set %s"), msg, setname)
            logging.info("Traceback: ", exc_info=True)
            return readd, result

    try:
        if cfg.enable_par_cleanup():
            deletables = []
            new_dir_content = os.listdir(nzo.download_path)

            # If Multipar or par2cmdline repairs a broken part of a joinable, it doesn't list it as such.
            # So we need to manually add all joinables of the set to the list of used joinables.
            # We assume at least 1 of them was not broken, so we can use it as a base to find the rest.
            if used_joinables:
                for used_jn in used_joinables[:]:
                    for jn in joinables:
                        if get_filename(jn).startswith(setname_from_path(used_jn)) and jn not in used_joinables:
                            used_joinables.append(jn)

            # Remove extra files created during repair and par2 base files
            for path in new_dir_content:
                if get_ext(path) == ".1" and path not in old_dir_content:
                    deletables.append(os.path.join(nzo.download_path, path))
            deletables.append(os.path.join(nzo.download_path, setname + ".par2"))
            deletables.append(os.path.join(nzo.download_path, setname + ".PAR2"))
            deletables.append(parfile)

            # Add output of par2-repair to remove
            deletables.extend(used_joinables)
            deletables.extend([os.path.join(nzo.download_path, f) for f in used_for_repair])

            # Delete pars of the set
            deletables.extend([os.path.join(nzo.download_path, nzf.filename) for nzf in setpars])

            for filepath in deletables:
                if filepath in joinables:
                    joinables.remove(filepath)
                if os.path.exists(filepath):
                    try:
                        remove_file(filepath)
                    except OSError:
                        logging.warning(T("Deleting %s failed!"), filepath)
    except Exception:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T("Repairing failed, %s") % msg
        logging.error(T('Error "%s" while running par2_repair on set %s'), msg, setname, exc_info=True)

    return readd, result


def par2cmdline_verify(
    parfile: str, nzo: NzbObject, setname: str, joinables: List[str]
) -> Tuple[bool, bool, List[str], List[str]]:
    """Run par2 on par-set"""
    used_joinables = []
    used_for_repair = []
    # set the current nzo status to "Verifying...". Used in History
    nzo.status = Status.VERIFYING
    start = time.time()

    # Build command and add extra options
    command = [str(PAR2_COMMAND), "r", parfile]
    if options := cfg.par_option().strip().split():
        for option in options:
            command.insert(2, option)

    # Append the wildcard for this set
    parfolder = os.path.split(parfile)[0]
    if len(nzo.extrapars) == 1 or len(globber(parfolder, setname + "*")) < 2:
        # Support bizarre naming conventions
        wildcard = "*"
    else:
        # Normal case, everything is named after set
        wildcard = setname + "*"
    command.append(os.path.join(parfolder, wildcard))

    # We need to check for the bad par2cmdline that skips blocks
    # Or the one that complains about basepath
    par2text = run_command([command[0], "-h"])
    if "No data skipping" in par2text:
        logging.info("Detected par2cmdline version that skips blocks, adding -N parameter")
        command.insert(2, "-N")
    if "Set the basepath" in par2text:
        logging.info("Detected par2cmdline version that needs basepath, adding -B<path> parameter")
        command.insert(2, "-B")
        command.insert(3, parfolder)

    # Run the external command
    p = build_and_run_command(command)
    sabnzbd.PostProcessor.external_process = p

    # Set up our variables
    lines = []
    renames = {}
    reconstructed = []

    finished = False
    readd = False

    verifynum = 0
    verifytotal = 0
    verified = 0
    perc = 0

    in_verify = False
    in_extra_files = False
    in_verify_repaired = False

    # Loop over the output, whee
    while 1:
        line = p.stdout.readline()
        if not line:
            break

        # Skip empty lines
        line = line.strip()
        if not line:
            continue

        if not line.startswith(("Repairing:", "Scanning:", "Loading:", "Solving:", "Constructing:")):
            lines.append(line)

        if line.startswith(("Invalid option specified", "Invalid thread option", "Cannot specify recovery file count")):
            msg = T("[%s] PAR2 received incorrect options, check your Config->Switches settings") % setname
            nzo.set_unpack_info("Repair", msg)
            nzo.status = Status.FAILED
            logging.error(msg)

        elif line.startswith("All files are correct"):
            msg = T("[%s] Verified in %s, all files correct") % (setname, format_time_string(time.time() - start))
            nzo.set_unpack_info("Repair", msg)
            logging.info("Verified in %s, all files correct", format_time_string(time.time() - start))
            finished = True

        elif line.startswith("Repair is required"):
            msg = T("[%s] Verified in %s, repair is required") % (setname, format_time_string(time.time() - start))
            nzo.set_unpack_info("Repair", msg)
            logging.info("Verified in %s, repair is required", format_time_string(time.time() - start))
            start = time.time()
            verified = 1
            # Reset to use them again for verification of repair
            verifytotal = 0
            verifynum = 0

        elif line.startswith("Main packet not found") or "The recovery file does not exist" in line:
            # Initialparfile probably didn't decode properly or bad user parameters
            # We will try to get another par2 file, but 99% of time it's user parameters
            msg = T("Invalid par2 files or invalid PAR2 parameters, cannot verify or repair")
            logging.info(msg)
            logging.info("Extra pars = %s", nzo.extrapars[setname])

            # Look for the smallest par2file
            block_table = {}
            for nzf in nzo.extrapars[setname]:
                if not nzf.completed:
                    block_table[nzf.blocks] = nzf

            if block_table:
                nzf = block_table[min(block_table)]
                logging.info("Found new par2file %s", nzf.filename)

                # Move from extrapar list to files to be downloaded
                # and remove it from the extrapars list
                nzo.add_parfile(nzf)
                readd = True
            else:
                nzo.fail_msg = msg
                nzo.set_unpack_info("Repair", msg, setname)
                nzo.status = Status.FAILED

        elif line.startswith("You need"):
            # We need more blocks, but are they available?
            chunks = line.split()
            needed_blocks = int(chunks[2])

            # Check if we have enough blocks
            added_blocks = nzo.get_extra_blocks(setname, needed_blocks)
            if added_blocks:
                msg = T("Fetching %s blocks...") % str(added_blocks)
                nzo.set_action_line(T("Fetching"), msg)
                readd = True
            else:
                # Failed
                msg = T("Repair failed, not enough repair blocks (%s short)") % str(needed_blocks)
                nzo.fail_msg = msg
                nzo.set_unpack_info("Repair", msg, setname)
                nzo.status = Status.FAILED

        elif line.startswith("Repair is possible"):
            start = time.time()
            nzo.set_action_line(T("Repairing"), "%2d%%" % 0)

        elif line.startswith(("Repairing:", "Processing:")):
            # "Processing" is shown when it is only joining files without repairing
            chunks = line.split()
            new_perc = float(chunks[-1][:-1])
            # Only send updates for whole-percentage updates
            if new_perc - perc > 1:
                perc = new_perc
                nzo.set_action_line(T("Repairing"), "%2d%% %s" % (perc, add_time_left(perc, start)))
                nzo.status = Status.REPAIRING

        elif line.startswith("Repair complete"):
            msg = T("[%s] Repaired in %s") % (setname, format_time_string(time.time() - start))
            nzo.set_unpack_info("Repair", msg)
            logging.info("Repaired in %s", format_time_string(time.time() - start))
            finished = True

        elif verified and line.endswith(("are missing.", "exist but are damaged.")):
            # Files that will later be verified after repair
            chunks = line.split()
            verifytotal += int(chunks[0])

        elif line.startswith("Verifying repaired files"):
            in_verify_repaired = True

        elif in_verify_repaired and line.startswith("Target"):
            verifynum += 1
            if verifynum <= verifytotal:
                nzo.set_action_line(T("Verifying repair"), "%02d/%02d" % (verifynum, verifytotal))

        elif "Could not write" in line and "at offset 0:" in line:
            # If there are joinables, this error will only happen in case of 100% complete files
            # We can just skip the retry, because par2cmdline will fail in those cases
            # because it refuses to scan the ".001" file
            if joinables:
                finished = True
                used_joinables = []

        elif " cannot be renamed to " in line:
            msg = line.strip()
            nzo.fail_msg = msg
            nzo.set_unpack_info("Repair", msg, setname)
            nzo.status = Status.FAILED

        elif "There is not enough space on the disk" in line:
            # Oops, disk is full!
            msg = T("Repairing failed, %s") % T("Disk full")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Repair", msg, setname)
            nzo.status = Status.FAILED

        elif "No details available for recoverable file" in line:
            msg = line.strip()
            nzo.fail_msg = msg
            nzo.set_unpack_info("Repair", msg, setname)
            nzo.status = Status.FAILED

        elif line.startswith("Repair Failed."):
            # Unknown repair problem
            msg = T("Repairing failed, %s") % line
            nzo.fail_msg = msg
            nzo.set_unpack_info("Repair", msg, setname)
            nzo.status = Status.FAILED
            finished = False

        elif not verified:
            if line.startswith("Scanning:"):
                pass

            if in_extra_files:
                if "is a match for" in line or line.find("data blocks from") > 0:
                    # Baldy named ones
                    if m_rename := PAR2_IS_MATCH_FOR_RE.search(line):
                        old_name = m_rename.group(1)
                        new_name = m_rename.group(2)
                        logging.debug('PAR2 will rename "%s" to "%s"', old_name, new_name)
                        renames[new_name] = old_name

                    # Obfuscated and also damaged
                    if m_block := PAR2_BLOCK_FOUND_RE.search(line):
                        workdir = os.path.split(parfile)[0]
                        old_name = m_block.group(1)
                        new_name = m_block.group(2)
                        if joinables:
                            # Find out if a joinable file has been used for joining
                            for jn in joinables:
                                if get_filename(jn) == old_name:
                                    used_joinables.append(jn)
                                    break
                            # Special case of joined RAR files, the "of" and "from" must both be RAR files
                            # This prevents the joined rars files from being seen as an extra rar-set
                            if ".rar" in old_name.lower() and ".rar" in new_name.lower():
                                used_joinables.append(os.path.join(workdir, old_name))
                        else:
                            logging.debug('PAR2 will reconstruct "%s" from "%s"', new_name, old_name)
                            reconstructed.append(os.path.join(workdir, old_name))
                            renames[new_name] = old_name

                    if m_block or m_rename:
                        # Show progress
                        verifynum += 1
                        nzo.set_action_line(T("Checking extra files"), "%02d" % verifynum)

            elif not in_verify:
                # Total number to verify
                if m := re.match(r"There are (\d+) recoverable files", line):
                    verifytotal = int(m.group(1))

                if line.startswith("Verifying source files:"):
                    in_verify = True
                    nzo.status = Status.VERIFYING
            elif line.startswith("Scanning extra files:"):
                in_verify = False
                in_extra_files = True
                verifynum = 0
            else:
                # Target files for verification
                m = PAR2_TARGET_RE.match(line)
                if m:
                    verifynum += 1
                    nzo.set_action_line(T("Verifying"), "%02d/%02d" % (verifynum, verifytotal))

                    # Remove redundant extra files that are just duplicates of original ones
                    if "duplicate data blocks" in line:
                        used_for_repair.append(m.group(1))

    p.wait()

    # Also log what is shown to user in history
    if nzo.fail_msg:
        logging.info(nzo.fail_msg)

    logging.debug("par2cmdline output was:\n%s", "\n".join(lines))

    # If successful, add renamed files to the collection
    if finished and renames:
        nzo.renamed_file(renames)

    # If successful and files were reconstructed, remove incomplete original files
    if finished and reconstructed:
        # Use 'used_joinables' as a vehicle to get rid of the files
        used_joinables.extend(reconstructed)

    return finished, readd, used_joinables, used_for_repair


def create_env(nzo: Optional[NzbObject] = None, extra_env_fields: Dict[str, Any] = {}) -> Optional[Dict[str, Any]]:
    """Modify the environment for pp-scripts with extra information
    macOS: Return copy of environment without PYTHONPATH and PYTHONHOME
    other: return None
    """
    env = os.environ.copy()

    # Are we adding things?
    if nzo:
        # Add basic info
        for field in ENV_NZO_FIELDS:
            try:
                field_value = getattr(nzo, field)
                # Special filters for Python types
                if field_value is None:
                    env["SAB_" + field.upper()] = ""
                elif isinstance(field_value, bool):
                    env["SAB_" + field.upper()] = str(field_value * 1)
                else:
                    env["SAB_" + field.upper()] = str(field_value)
            except Exception:
                # Catch key errors
                pass

    # Always supply basic info
    extra_env_fields.update(
        {
            "program_dir": sabnzbd.DIR_PROG,
            "api_key": cfg.api_key(),
            "api_url": f"{sabnzbd.BROWSER_URL}/api",
            "par2_command": sabnzbd.newsunpack.PAR2_COMMAND,
            "rar_command": sabnzbd.newsunpack.RAR_COMMAND,
            "7zip_command": sabnzbd.newsunpack.SEVENZIP_COMMAND,
            "version": sabnzbd.__version__,
        }
    )

    # Add extra fields
    for field in extra_env_fields:
        try:
            if extra_env_fields[field] is not None:
                env["SAB_" + field.upper()] = str(extra_env_fields[field])
            else:
                env["SAB_" + field.upper()] = ""
        except Exception:
            # Catch key errors
            pass

    if sabnzbd.MACOS:
        if "PYTHONPATH" in env:
            del env["PYTHONPATH"]
        if "PYTHONHOME" in env:
            del env["PYTHONHOME"]

    return env


def rar_volumelist(rarfile_path: str, password: str, known_volumes: List[str]) -> List[str]:
    """List volumes that are part of this rarset
    and merge them with parsed paths list, removing duplicates.
    We assume RarFile is right and use parsed paths as backup.
    """
    # UnRar is required to read some RAR files
    # RarFile can fail in special cases
    try:
        zf = rarfile.RarFile(rarfile_path)

        # setpassword can fail due to bugs in RarFile
        if password:
            try:
                zf.setpassword(password)
            except Exception:
                pass
        zf_volumes = zf.volumelist()
    except Exception:
        zf_volumes = []

    # Remove duplicates
    zf_volumes_base = [os.path.basename(vol) for vol in zf_volumes]
    for known_volume in known_volumes:
        if os.path.basename(known_volume) not in zf_volumes_base:
            # Long-path notation just to be sure
            zf_volumes.append(long_path(known_volume))
    return zf_volumes


# Sort the various RAR filename formats properly :\
def rar_sort(a: str, b: str) -> int:
    """Define sort method for rar file names"""
    aext = a.split(".")[-1]
    bext = b.split(".")[-1]

    if aext == "rar" and bext == "rar":
        return cmp(a, b)
    elif aext == "rar":
        return -1
    elif bext == "rar":
        return 1
    else:
        return cmp(a, b)


def quick_check_set(setname: str, nzo: NzbObject) -> bool:
    """Check all on-the-fly crc32s of a set"""
    par2pack = nzo.par2packs.get(setname)
    if par2pack is None:
        return False

    # We use bitwise assignment (&=) so False always wins in case of failure
    # This way the renames always get saved!
    result = True
    nzf_list = nzo.finished_files
    renames = {}
    found_paths: Set[str] = set()

    # Files to ignore
    ignore_ext = cfg.quick_check_ext_ignore()

    for file in par2pack:
        par2info = par2pack[file]
        found = False
        file_to_ignore = get_ext(file).replace(".", "") in ignore_ext
        for nzf in nzf_list:
            # Do a simple filename based check
            if file == nzf.filename:
                found = True
                found_paths.add(nzf.filepath)
                if (
                    nzf.crc32 is not None
                    and nzf.crc32 == par2info.filehash
                    and is_size(nzf.filepath, par2info.filesize)
                ):
                    logging.debug("Quick-check of file %s OK", file)
                    result &= True
                elif file_to_ignore:
                    # We don't care about these files
                    logging.debug("Quick-check ignoring file %s", file)
                    result &= True
                else:
                    logging.info("Quick-check of file %s failed!", file)
                    result = False
                break

            # Now let's do obfuscation check
            if (
                nzf.filepath not in found_paths
                and nzf.crc32 is not None
                and nzf.crc32 == par2info.filehash
                and is_size(nzf.filepath, par2info.filesize)
            ):
                try:
                    logging.debug("Quick-check will rename %s to %s", nzf.filename, file)

                    # Note: file can and is allowed to be in a subdirectory.
                    # Subdirectories in par2 always contain "/", not "\" so we need to normalize
                    file = os.path.normpath(file)
                    renamer(
                        os.path.join(nzo.download_path, nzf.filename),
                        os.path.join(nzo.download_path, file),
                        create_local_directories=True,
                    )
                    renames[file] = nzf.filename
                    nzf.filename = file
                    result &= True
                    found = True
                    found_paths.add(nzf.filepath)
                    break
                except IOError:
                    # Renamed failed for some reason, probably already done
                    break

        if not found:
            if file_to_ignore:
                # We don't care about these files
                logging.debug("Quick-check ignoring missing file %s", file)
                continue

            logging.info("Cannot Quick-check missing file %s!", file)
            result = False

    # Save renames
    if renames:
        nzo.renamed_file(renames)

    return result


def unrar_check(rar: str) -> Tuple[int, bool]:
    """Return version number of unrar, where "5.01" returns 501
    Also return whether an original version is found
    (version, original)
    """
    version = 0
    original = False
    if rar:
        try:
            version = run_command([rar])
        except Exception:
            return version, original
        original = "Alexander Roshal" in version

        if m := re.search(r"RAR\s(\d+)\.(\d+)", version):
            version = int(m.group(1)) * 100 + int(m.group(2))
        else:
            version = 0
    return version, original


def sevenzip_check(sevenzip: str) -> str:
    """Return version of 7zip, currently as a string"""
    if sevenzip:
        try:
            seven_command_output = run_command([sevenzip])
            # Example: 7-Zip (z) 21.06 (x64) : Copyright (c) 1999-2021 Igor Pavlov : 2021-11-24
            #          7-Zip (a) 24.03 (x86) : Copyright (c) 1999-2024 Igor Pavlov : 2024-03-23
            return re.search(r"(\d+\.\d+).*Copyright", seven_command_output).group(1)
        except Exception:
            pass
    return ""


def par2_turbo_check(par2_path: str) -> bool:
    """Detect if we have the turbo par2 variant"""
    try:
        if "par2cmdline-turbo" in run_command([par2_path, "-V"]):
            return True
    except Exception:
        pass
    return False


def is_sfv_file(myfile: str) -> bool:
    """Checks if given file is a SFV file, and returns result as boolean"""
    # based on https://stackoverflow.com/a/7392391/5235502
    textchars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
    is_ascii_string = lambda input_bytes: not bool(input_bytes.translate(None, textchars))

    # first check if it's plain text (ASCII or Unicode)
    try:
        with open(myfile, "rb") as f:
            # get first 10000 bytes to check
            myblock = f.read(10000)
            if is_ascii_string(myblock):
                # ASCII, so store lines for further inspection
                try:
                    lines = ubtou(myblock).split("\n")
                except UnicodeDecodeError:
                    return False
            else:
                # non-ASCII, so not SFV
                return False
    except Exception:
        # the with-open() went wrong, so not an existing file, so certainly not a SFV file
        return False

    sfv_info_line_counter = 0
    for line in lines:
        line = line.strip()
        if re.search(r"^[^;].*\ +[A-Fa-f0-9]{8}$", line):
            # valid, useful SFV line: some text, then one or more space, and a 8-digit hex number
            sfv_info_line_counter += 1
            if sfv_info_line_counter >= 10:
                # with 10 valid, useful lines we're confident enough
                # (note: if we find less lines (even just 1 line), with no negatives, it is OK. See below)
                break
        elif not line or line.startswith(";"):
            # comment line or just spaces, so continue to next line
            continue
        else:
            # not a valid SFV line, so not a SFV file:
            return False
    # if we get here, no negatives were found, and at least 1 valid line is OK
    return sfv_info_line_counter >= 1


def sfv_check(sfvs: List[str], nzo: NzbObject) -> bool:
    """Verify files using SFV files"""
    # Update status
    nzo.status = Status.VERIFYING
    nzo.set_action_line(T("Trying SFV verification"), "...")

    # We use bitwise assignment (&=) so False always wins in case of failure
    # This way the renames always get saved!
    result = True
    nzf_list = nzo.finished_files
    renames = {}

    # Files to ignore
    ignore_ext = cfg.quick_check_ext_ignore()

    # We need the crc32 of all files
    calculated_crc32 = {}
    verifytotal = len(nzo.finished_files)
    verifynum = 0
    for nzf in nzf_list:
        if nzf.crc32 is not None:
            verifynum += 1
            nzo.set_action_line(T("Verifying"), "%02d/%02d" % (verifynum, verifytotal))
            calculated_crc32[nzf.filename] = b"%08x" % (nzf.crc32 & 0xFFFFFFFF)

    sfv_parse_results = {}
    nzo.set_action_line(T("Trying SFV verification"), "...")
    for sfv in sfvs:
        setname = setname_from_path(sfv)
        nzo.set_unpack_info("Repair", T("Trying SFV verification"), setname)

        # Parse the sfv and add to the already found results
        # Duplicates will be replaced
        sfv_parse_results.update(parse_sfv(sfv))

    for file in sfv_parse_results:
        found = False
        file_to_ignore = get_ext(file).replace(".", "") in ignore_ext
        for nzf in nzf_list:
            # Do a simple filename based check
            if file == nzf.filename:
                found = True
                if calculated_crc32.get(nzf.filename, "") == sfv_parse_results[file]:
                    logging.debug("SFV-check of file %s OK", file)
                    result &= True
                elif file_to_ignore:
                    # We don't care about these files
                    logging.debug("SFV-check ignoring file %s", file)
                    result &= True
                else:
                    logging.info("SFV-check of file %s failed!", file)
                    result = False
                break

            # Now lets do obfuscation check
            if calculated_crc32.get(nzf.filename, "") == sfv_parse_results[file]:
                try:
                    logging.debug("SFV-check will rename %s to %s", nzf.filename, file)
                    renamer(os.path.join(nzo.download_path, nzf.filename), os.path.join(nzo.download_path, file))
                    renames[file] = nzf.filename
                    nzf.filename = file
                    result &= True
                    found = True
                    break
                except IOError:
                    # Renamed failed for some reason, probably already done
                    break

        if not found:
            if file_to_ignore:
                # We don't care about these files
                logging.debug("SFV-check ignoring missing file %s", file)
                continue

            logging.info("Cannot SFV-check missing file %s!", file)
            result = False

    # Save renames
    if renames:
        nzo.renamed_file(renames)

    return result


def parse_sfv(sfv_filename):
    """Parse SFV file and return dictionary of crc32's and filenames"""
    results = {}
    with open(sfv_filename, mode="rb") as sfv_list:
        for sfv_item in sfv_list:
            sfv_item = sfv_item.strip()
            # Ignore comment-lines
            if sfv_item.startswith(b";"):
                continue
            # Parse out the filename and crc32
            filename, expected_crc32 = sfv_item.strip().rsplit(maxsplit=1)
            # We don't know what encoding is used when it was created
            results[correct_unknown_encoding(filename)] = expected_crc32.lower()
    return results


def add_time_left(perc: float, start_time: Optional[float] = None, time_used: Optional[float] = None) -> str:
    """Calculate time left based on current progress, if it is taking more than 10 seconds"""
    if not time_used:
        time_used = time.time() - start_time
    if time_used > 10:
        return " - %s %s" % (format_time_left(int((100 - perc) / (perc / time_used)), short_format=True), T("left"))
    return ""


def pre_queue(nzo: NzbObject, pp, cat):
    """Run pre-queue script (if any) and process results.
    pp and cat are supplied separate since they can change.
    """

    def fix(p):
        # If added via API, some items can still be "None" (as a string)
        if is_none(p):
            return ""
        return str(p)

    values = [1, nzo.final_name_with_password, pp, cat, nzo.script, nzo.priority, None]
    script_path = make_script_path(cfg.pre_script())
    if script_path:
        # Basic command-line parameters
        command = [
            script_path,
            nzo.final_name_with_password,
            pp,
            cat,
            nzo.script,
            nzo.priority,
            str(nzo.bytes),
            " ".join(nzo.groups),
        ]
        command = [fix(arg) for arg in command]

        # Fields not in the NZO directly
        show_analysis = sabnzbd.sorting.BasicAnalyzer(nzo.final_name)
        extra_env_fields = {
            "groups": " ".join(nzo.groups),
            "title": show_analysis.info.get("title", ""),
            "season": show_analysis.info.get("season_num", ""),
            "episode": show_analysis.info.get("episode_num", ""),
            "episode_name": show_analysis.info.get("ep_name", ""),
            "is_proper": show_analysis.is_proper(),
            "resolution": show_analysis.info.get("resolution", ""),
            "decade": show_analysis.info.get("decade", ""),
            "year": show_analysis.info.get("year", ""),
            "month": show_analysis.info.get("month", ""),
            "day": show_analysis.info.get("day", ""),
            "job_type": show_analysis.type,
        }

        try:
            p = build_and_run_command(command, env=create_env(nzo, extra_env_fields))
        except Exception:
            logging.debug("Failed script %s, Traceback: ", script_path, exc_info=True)
            return values

        output = p.stdout.read()
        ret = p.wait()
        logging.info("Pre-queue script returned %s and output=\n%s", ret, output)
        if ret == 0:
            split_output = output.splitlines()
            try:
                # Extract category line from pre-queue output
                pre_queue_category = split_output[3].strip(" '\"")
            except IndexError:
                pre_queue_category = None

            for index, line in enumerate(split_output):
                line = line.strip(" '\"")
                if index < len(values):
                    if line:
                        values[index] = line
                    elif pre_queue_category and index in (2, 4, 5):
                        # Preserve empty pp, script, and priority lines to prevent
                        # pre-existing values from overriding category-based settings
                        values[index] = ""

        accept = int_conv(values[0])
        if accept < 1:
            logging.info("Pre-Q refuses %s", nzo.final_name)
        elif accept == 2:
            logging.info("Pre-Q accepts&fails %s", nzo.final_name)
        else:
            logging.info("Pre-Q accepts %s", nzo.final_name)

    return values


def is_sevenfile(path: str) -> bool:
    """Return True if path has 7Zip-signature and 7Zip is detected"""
    with open(path, "rb") as sevenzip:
        if sevenzip.read(6) == SEVENZIP_ID:
            return bool(SEVENZIP_COMMAND)
    return False


class SevenZip:
    """Minimal emulation of ZipFile class for 7Zip"""

    def __init__(self, path: str):
        self.path = path
        # Check if it's actually a 7Zip-file
        if not is_sevenfile(self.path):
            raise TypeError("File is not a 7zip file")

    def namelist(self) -> List[str]:
        """Return list of names in 7Zip"""
        names = []
        command = [SEVENZIP_COMMAND, "l", "-p", "-y", "-slt", "-sccUTF-8", self.path]
        output = run_command(command)

        for line in output.split("\n"):
            if m := SEVENZIP_PATH_RE.search(line):
                names.append(m.group(1).strip("\r"))
        if names:
            # Remove name of archive itself
            del names[0]
        return names

    def open(self, name: str) -> BinaryIO:
        """Read named file from 7Zip and return data"""
        command = [SEVENZIP_COMMAND, "e", "-p", "-y", "-so", self.path, name]
        # Ignore diagnostic output, otherwise it will be appended to content
        with build_and_run_command(command, text_mode=False, stderr=subprocess.DEVNULL) as p:
            data = io.BytesIO(p.stdout.read())
            p.wait()
        return data

    def close(self):
        """Close file"""
        pass
