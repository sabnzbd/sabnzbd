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
sabnzbd.newsunpack
"""

import os
import sys
import re
import subprocess
import logging
import time
import zlib
import shutil
import functools
from typing import Tuple

import sabnzbd
from sabnzbd.encoding import platform_btou, correct_unknown_encoding, ubtou
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
    get_filename,
)
from sabnzbd.nzbstuff import NzbObject, NzbFile
from sabnzbd.sorting import SeriesSorter
import sabnzbd.cfg as cfg
from sabnzbd.constants import Status

# Regex globals
RAR_RE = re.compile(r"\.(?P<ext>part\d*\.rar|rar|r\d\d|s\d\d|t\d\d|u\d\d|v\d\d|\d\d\d?\d)$", re.I)
RAR_RE_V3 = re.compile(r"\.(?P<ext>part\d*)$", re.I)

TARGET_RE = re.compile(r'^(?:File|Target): "(.+)" -')
EXTRACTFROM_RE = re.compile(r"^Extracting\sfrom\s(.+)")
EXTRACTED_RE = re.compile(r"^(Extracting|Creating|...)\s+(.*?)\s+OK\s*$")
SPLITFILE_RE = re.compile(r"\.(\d\d\d?\d$)", re.I)
ZIP_RE = re.compile(r"\.(zip$)", re.I)
SEVENZIP_RE = re.compile(r"\.7z$", re.I)
SEVENMULTI_RE = re.compile(r"\.7z\.\d+$", re.I)
TS_RE = re.compile(r"\.(\d+)\.(ts$)", re.I)

PAR2_COMMAND = None
MULTIPAR_COMMAND = None
RAR_COMMAND = None
NICE_COMMAND = None
ZIP_COMMAND = None
SEVEN_COMMAND = None
IONICE_COMMAND = None
RAR_PROBLEM = False
PAR2_MT = True
RAR_VERSION = 0


def find_programs(curdir):
    """Find external programs"""

    def check(path, program):
        p = os.path.abspath(os.path.join(path, program))
        if os.access(p, os.X_OK):
            return p
        else:
            return None

    if sabnzbd.DARWIN:
        sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, "osx/par2/par2-sl64")
        sabnzbd.newsunpack.RAR_COMMAND = check(curdir, "osx/unrar/unrar")
        sabnzbd.newsunpack.SEVEN_COMMAND = check(curdir, "osx/7zip/7za")

    if sabnzbd.WIN32:
        if sabnzbd.WIN64:
            # 64 bit versions
            sabnzbd.newsunpack.MULTIPAR_COMMAND = check(curdir, "win/multipar/par2j64.exe")
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, "win/unrar/x64/UnRAR.exe")
        else:
            # 32 bit versions
            sabnzbd.newsunpack.MULTIPAR_COMMAND = check(curdir, "win/multipar/par2j.exe")
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, "win/unrar/UnRAR.exe")
        sabnzbd.newsunpack.SEVEN_COMMAND = check(curdir, "win/7zip/7za.exe")
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
        if not sabnzbd.newsunpack.ZIP_COMMAND:
            sabnzbd.newsunpack.ZIP_COMMAND = find_on_path("unzip")
        if not sabnzbd.newsunpack.SEVEN_COMMAND:
            sabnzbd.newsunpack.SEVEN_COMMAND = find_on_path("7za")
        if not sabnzbd.newsunpack.SEVEN_COMMAND:
            sabnzbd.newsunpack.SEVEN_COMMAND = find_on_path("7z")

    if not (sabnzbd.WIN32 or sabnzbd.DARWIN):
        # Run check on rar version
        version, original = unrar_check(sabnzbd.newsunpack.RAR_COMMAND)
        sabnzbd.newsunpack.RAR_PROBLEM = not original or version < sabnzbd.constants.REC_RAR_VERSION
        sabnzbd.newsunpack.RAR_VERSION = version

        # Run check on par2-multicore
        sabnzbd.newsunpack.PAR2_MT = par2_mt_check(sabnzbd.newsunpack.PAR2_COMMAND)


ENV_NZO_FIELDS = [
    "bytes",
    "bytes_downloaded",
    "bytes_tried",
    "cat",
    "correct_password",
    "duplicate",
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


def external_processing(extern_proc, nzo: NzbObject, complete_dir, nicename, status):
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

    try:
        p = build_and_run_command(command, env=create_env(nzo, extra_env_fields))
        sabnzbd.PostProcessor.external_process = p

        # Follow the output, so we can abort it
        proc = p.stdout
        if p.stdin:
            p.stdin.close()

        lines = []
        while 1:
            line = platform_btou(proc.readline())
            if not line:
                break
            line = line.strip()
            lines.append(line)

            # Show current line in history
            nzo.set_action_line(T("Running script"), line)
    except:
        logging.debug("Failed script %s, Traceback: ", extern_proc, exc_info=True)
        return "Cannot run script %s\r\n" % extern_proc, -1

    output = "\n".join(lines)
    ret = p.wait()
    return output, ret


def unpack_magic(
    nzo: NzbObject, workdir, workdir_complete, dele, one_folder, joinables, zips, rars, sevens, ts, depth=0
):
    """Do a recursive unpack from all archives in 'workdir' to 'workdir_complete'"""
    if depth > 5:
        logging.warning(T("Unpack nesting too deep [%s]"), nzo.final_name)
        return False, []
    depth += 1

    if depth == 1:
        # First time, ignore anything in workdir_complete
        xjoinables, xzips, xrars, xsevens, xts = build_filelists(workdir)
    else:
        xjoinables, xzips, xrars, xsevens, xts = build_filelists(workdir, workdir_complete, check_both=dele)

    force_rerun = False
    newfiles = []
    error = None
    new_joins = new_ts = None

    if cfg.enable_filejoin():
        new_joins = [jn for jn in xjoinables if jn not in joinables]
        if new_joins:
            logging.info("Filejoin starting on %s", workdir)
            error, newf = file_join(nzo, workdir, workdir_complete, dele, new_joins)
            if newf:
                newfiles.extend(newf)
            logging.info("Filejoin finished on %s", workdir)

    if cfg.enable_unrar():
        new_rars = [rar for rar in xrars if rar not in rars]
        if new_rars:
            logging.info("Unrar starting on %s", workdir)
            error, newf = rar_unpack(nzo, workdir, workdir_complete, dele, one_folder, new_rars)
            if newf:
                newfiles.extend(newf)
            logging.info("Unrar finished on %s", workdir)

    if cfg.enable_7zip():
        new_sevens = [seven for seven in xsevens if seven not in sevens]
        if new_sevens:
            logging.info("7za starting on %s", workdir)
            error, newf = unseven(nzo, workdir, workdir_complete, dele, one_folder, new_sevens)
            if newf:
                newfiles.extend(newf)
            logging.info("7za finished on %s", workdir)

    if cfg.enable_unzip():
        new_zips = [zip for zip in xzips if zip not in zips]
        if new_zips:
            logging.info("Unzip starting on %s", workdir)
            if SEVEN_COMMAND:
                error, newf = unseven(nzo, workdir, workdir_complete, dele, one_folder, new_zips)
            else:
                error, newf = unzip(nzo, workdir, workdir_complete, dele, one_folder, new_zips)
            if newf:
                newfiles.extend(newf)
            logging.info("Unzip finished on %s", workdir)

    if cfg.enable_tsjoin():
        new_ts = [_ts for _ts in xts if _ts not in ts]
        if new_ts:
            logging.info("TS Joining starting on %s", workdir)
            error, newf = file_join(nzo, workdir, workdir_complete, dele, new_ts)
            if newf:
                newfiles.extend(newf)
            logging.info("TS Joining finished on %s", workdir)

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
    if sabnzbd.WIN32 and len(workdir_complete) > 256:
        rerun = False

    # Double-check that we didn't miss any files in workdir
    # But only if dele=True, otherwise of course there will be files left
    if rerun and dele and depth == 1 and any(build_filelists(workdir)):
        force_rerun = True
        # Clear lists to force re-scan of files
        xjoinables, xzips, xrars, xsevens, xts = ([], [], [], [], [])

    if rerun and (cfg.enable_recursive() or new_ts or new_joins or force_rerun):
        z, y = unpack_magic(
            nzo, workdir, workdir_complete, dele, one_folder, xjoinables, xzips, xrars, xsevens, xts, depth
        )
        if z:
            error = z
        if y:
            newfiles.extend(y)

    return error, newfiles


##############################################################################
# Filejoin Functions
##############################################################################
def match_ts(file):
    """Return True if file is a joinable TS file"""
    match = TS_RE.search(file)
    if not match:
        return False, "", 0

    num = int(match.group(1))
    try:
        set = file[: match.start()]
        set += ".ts"
    except:
        set = ""
    return match, set, num


def clean_up_joinables(names):
    """Remove joinable files and their .1 backups"""
    for name in names:
        if os.path.exists(name):
            try:
                remove_file(name)
            except:
                pass
        name1 = name + ".1"
        if os.path.exists(name1):
            try:
                remove_file(name1)
            except:
                pass


def get_seq_number(name):
    """Return sequence number if name as an int"""
    head, tail = os.path.splitext(name)
    if tail == ".ts":
        match, set, num = match_ts(name)
    else:
        num = tail[1:]
    if num.isdigit():
        return int(num)
    else:
        return 0


def file_join(nzo: NzbObject, workdir, workdir_complete, delete, joinables):
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
            head = match_ts(joinable)[1]
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
                if delete:
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
                filename = filename.replace(workdir, workdir_complete)
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
                    if delete:
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
    except:
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
def rar_unpack(nzo: NzbObject, workdir, workdir_complete, delete, one_folder, rars):
    """Unpack multiple sets 'rars' of RAR files from 'workdir' to 'workdir_complete.
    When 'delete' is set, originals will be deleted.
    When 'one_folder' is set, all files will be in a single folder
    """
    newfiles = extracted_files = []
    rar_sets = {}
    for rar in rars:
        rar_set = setname_from_path(rar)
        if RAR_RE_V3.search(rar_set):
            # Remove the ".partXX" part
            rar_set = os.path.splitext(rar_set)[0]
        if rar_set not in rar_sets:
            rar_sets[rar_set] = []
        rar_sets[rar_set].append(rar)

    logging.debug("Rar_sets: %s", rar_sets)

    for rar_set in rar_sets:
        # Run the RAR extractor
        rar_sets[rar_set].sort(key=functools.cmp_to_key(rar_sort))

        rarpath = rar_sets[rar_set][0]

        if workdir_complete and rarpath.startswith(workdir):
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
            fail = False
            success = True
            rars, newfiles = nzo.direct_unpacker.success_sets.pop(rar_set)
        else:
            logging.info("Extracting rarfile %s (belonging to %s) to %s", rarpath, rar_set, extraction_path)
            try:
                fail, newfiles, rars = rar_extract(
                    rarpath, len(rar_sets[rar_set]), one_folder, nzo, rar_set, extraction_path
                )
                success = not fail
            except:
                success = False
                fail = True
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
        if success and delete and newfiles:
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


def rar_extract(rarfile_path, numrars, one_folder, nzo: NzbObject, setname, extraction_path):
    """Unpack single rar set 'rarfile' to 'extraction_path',
    with password tries
    Return fail==0(ok)/fail==1(error)/fail==2(wrong password), new_files, rars
    """
    fail = 0
    new_files = None
    rars = []
    passwords = get_all_passwords(nzo)

    for password in passwords:
        if password:
            logging.debug('Trying unrar with password "%s"', password)
            msg = T('Trying unrar with password "%s"') % password
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
        fail, new_files, rars = rar_extract_core(
            rarfile_path, numrars, one_folder, nzo, setname, extraction_path, password
        )
        if fail != 2:
            break

    if fail == 2:
        logging.error("%s (%s)", T("Unpacking failed, archive requires a password"), get_filename(rarfile_path))
    return fail, new_files, rars


def rar_extract_core(rarfile_path, numrars, one_folder, nzo: NzbObject, setname, extraction_path, password):
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

    if sabnzbd.WIN32:
        # For Unrar to support long-path, we need to circumvent Python's list2cmdline
        # See: https://github.com/sabnzbd/sabnzbd/issues/1043
        # The -scf forces the output to be UTF8
        command = [
            "%s" % RAR_COMMAND,
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
        # Luckily platform_btou has a fallback for non-UTF-8
        command = [
            "%s" % RAR_COMMAND,
            action,
            "-idp",
            overwrite,
            password_command,
            "%s" % rarfile_path,
            "%s/" % extraction_path,
        ]
    else:
        # Don't use "-ai" (not needed for non-Windows)
        # The -scf forces the output to be UTF8
        command = [
            "%s" % RAR_COMMAND,
            action,
            "-idp",
            "-scf",
            overwrite,
            rename,
            password_command,
            "%s" % rarfile_path,
            "%s/" % extraction_path,
        ]

    if cfg.ignore_unrar_dates():
        command.insert(3, "-tsm-")

    # Get list of all the volumes part of this set
    logging.debug("Analyzing rar file ... %s found", rarfile.is_rarfile(rarfile_path))
    p = build_and_run_command(command, flatten_command=True)
    sabnzbd.PostProcessor.external_process = p

    proc = p.stdout
    if p.stdin:
        p.stdin.close()

    nzo.set_action_line(T("Unpacking"), "00/%02d" % numrars)

    # Loop over the output from rar!
    curr = 0
    extracted = []
    rarfiles = []
    fail = 0
    inrecovery = False
    lines = []

    while 1:
        line = platform_btou(proc.readline())
        if not line:
            break

        line = line.strip()
        lines.append(line)

        if line.startswith("Extracting from"):
            filename = re.search(EXTRACTFROM_RE, line).group(1)
            if filename not in rarfiles:
                rarfiles.append(filename)
            curr += 1
            nzo.set_action_line(T("Unpacking"), "%02d/%02d" % (curr, numrars))

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
            logging.warning(T('ERROR: unable to find "%s"'), filename)
            fail = 1

        elif line.endswith("- CRC failed"):
            msg = T("Unpacking failed, CRC error")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            logging.warning(T('ERROR: CRC failed in "%s"'), setname)
            fail = 2  # Older unrar versions report a wrong password as a CRC error

        elif line.startswith("File too large"):
            msg = T("Unpacking failed, file too large for filesystem (FAT?)")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            # ERROR: File too large for file system (bigfile-5000MB)
            logging.error(T("ERROR: File too large for filesystem (%s)"), setname)
            fail = 1

        elif line.startswith("Write error"):
            msg = T("Unpacking failed, write error or disk is full?")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname)
            logging.error(T("ERROR: write error (%s)"), line[11:])
            fail = 1

        elif line.startswith("Cannot create"):
            line2 = platform_btou(proc.readline())
            if "must not exceed 260" in line2:
                msg = "%s: %s" % (T("Unpacking failed, path is too long"), line[13:])
                nzo.fail_msg = msg
                logging.error(T("ERROR: path too long (%s)"), line[13:])
            else:
                msg = "%s: %s" % (T("Unpacking failed, write error or disk is full?"), line[13:])
                nzo.fail_msg = msg
                logging.error(T("ERROR: write error (%s)"), line[13:])
            nzo.set_unpack_info("Unpack", msg, setname)
            fail = 1
            # Kill the process (can stay in endless loop on Windows Server)
            p.kill()

        elif line.startswith("ERROR: "):
            msg = T("ERROR: %s") % line[7:]
            nzo.fail_msg = msg
            logging.warning(msg)
            nzo.set_unpack_info("Unpack", msg, setname)
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

        else:
            m = re.search(EXTRACTED_RE, line)
            if m:
                # In case of flat-unpack, UnRar still prints the whole path (?!)
                unpacked_file = m.group(2)
                if cfg.flat_unpack():
                    unpacked_file = os.path.basename(unpacked_file)
                extracted.append(real_path(extraction_path, unpacked_file))

        if fail:
            if proc:
                proc.close()
            p.wait()
            logging.debug("UNRAR output %s", "\n".join(lines))
            return fail, (), ()

    if proc:
        proc.close()
    p.wait()

    # Which files did we use to extract this?
    rarfiles = rar_volumelist(rarfile_path, password, rarfiles)

    logging.debug("UNRAR output %s", "\n".join(lines))
    nzo.fail_msg = ""
    msg = T("Unpacked %s files/folders in %s") % (str(len(extracted)), format_time_string(time.time() - start))
    nzo.set_unpack_info("Unpack", msg, setname)
    logging.info("%s", msg)

    return 0, extracted, rarfiles


##############################################################################
# (Un)Zip Functions
##############################################################################
def unzip(nzo: NzbObject, workdir, workdir_complete, delete, one_folder, zips):
    """Unpack multiple sets 'zips' of ZIP files from 'workdir' to 'workdir_complete.
    When 'delete' is ste, originals will be deleted.
    """

    try:
        i = 0
        unzip_failed = False
        tms = time.time()

        # For file-bookkeeping
        orig_dir_content = listdir_full(workdir_complete)

        for _zip in zips:
            logging.info("Starting extract on zipfile: %s ", _zip)
            nzo.set_action_line(T("Unpacking"), "%s" % setname_from_path(_zip))

            if workdir_complete and _zip.startswith(workdir):
                extraction_path = workdir_complete
            else:
                extraction_path = os.path.split(_zip)[0]

            if ZIP_Extract(_zip, extraction_path, one_folder):
                unzip_failed = True
            else:
                i += 1

        msg = T("%s files in %s") % (str(i), format_time_string(time.time() - tms))
        nzo.set_unpack_info("Unpack", msg)

        # What's new?
        new_files = list(set(orig_dir_content + listdir_full(workdir_complete)))

        # Delete the old files if we have to
        if delete and not unzip_failed:
            i = 0

            for _zip in zips:
                try:
                    remove_file(_zip)
                    i += 1
                except OSError:
                    logging.warning(T("Deleting %s failed!"), _zip)

                brokenzip = "%s.1" % _zip

                if os.path.exists(brokenzip):
                    try:
                        remove_file(brokenzip)
                        i += 1
                    except OSError:
                        logging.warning(T("Deleting %s failed!"), brokenzip)

        return unzip_failed, new_files
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T("Unpacking failed, %s") % msg
        logging.error(T('Error "%s" while running unzip() on %s'), msg, nzo.final_name)
        return True, []


def ZIP_Extract(zipfile, extraction_path, one_folder):
    """Unzip single zip set 'zipfile' to 'extraction_path'"""
    command = ["%s" % ZIP_COMMAND, "-o", "-Pnone", "%s" % clip_path(zipfile), "-d%s" % extraction_path]

    if one_folder or cfg.flat_unpack():
        command.insert(3, "-j")  # Unpack without folders

    p = build_and_run_command(command)
    output = platform_btou(p.stdout.read())
    ret = p.wait()
    logging.debug("unzip output: \n%s", output)
    return ret


##############################################################################
# 7Zip Functions
##############################################################################
def unseven(nzo: NzbObject, workdir, workdir_complete, delete, one_folder, sevens):
    """Unpack multiple sets '7z' of 7Zip files from 'workdir' to 'workdir_complete.
    When 'delete' is set, originals will be deleted.
    """
    i = 0
    unseven_failed = False
    new_files = []
    tms = time.time()

    # Find multi-volume sets, because 7zip will not provide actual set members
    sets = {}
    for seven in sevens:
        name, ext = os.path.splitext(seven)
        ext = ext.strip(".")
        if not ext.isdigit():
            name = seven
            ext = None
        if name not in sets:
            sets[name] = []
        if ext:
            sets[name].append(ext)

    # Unpack each set
    for seven in sets:
        extensions = sets[seven]
        logging.info("Starting extract on 7zip set/file: %s ", seven)
        nzo.set_action_line(T("Unpacking"), "%s" % setname_from_path(seven))

        if workdir_complete and seven.startswith(workdir):
            extraction_path = workdir_complete
        else:
            extraction_path = os.path.split(seven)[0]

        res, new_files_set, msg = seven_extract(nzo, seven, extensions, extraction_path, one_folder, delete)
        if res:
            unseven_failed = True
            nzo.set_unpack_info("Unpack", msg, setname_from_path(seven))
        else:
            i += 1
        new_files.extend(new_files_set)

    if not unseven_failed:
        msg = T("%s files in %s") % (str(i), format_time_string(time.time() - tms))
        nzo.set_unpack_info("Unpack", msg)

    return unseven_failed, new_files


def seven_extract(nzo: NzbObject, sevenset, extensions, extraction_path, one_folder, delete):
    """Unpack single set 'sevenset' to 'extraction_path', with password tries
    Return fail==0(ok)/fail==1(error)/fail==2(wrong password), new_files, sevens
    """
    # Before we start, make sure the 7z binary SEVEN_COMMAND is defined
    if not SEVEN_COMMAND:
        msg = T('No 7za binary found, cannot unpack "%s"') % os.path.basename(sevenset)
        logging.error(msg)
        return 1, [], msg

    fail = 0
    passwords = get_all_passwords(nzo)

    for password in passwords:
        if password:
            msg = T('Trying 7zip with password "%s"') % password
            logging.debug(msg)
            nzo.fail_msg = msg
            nzo.set_unpack_info("Unpack", msg, setname_from_path(sevenset))
        fail, new_files, msg = seven_extract_core(sevenset, extensions, extraction_path, one_folder, delete, password)
        if fail != 2:
            break

    nzo.fail_msg = ""
    if fail == 2:
        msg = "%s (%s)" % (T("Unpacking failed, archive requires a password"), os.path.basename(sevenset))
    if fail > 0:
        nzo.fail_msg = msg
        nzo.status = Status.FAILED
        logging.error(msg)
    return fail, new_files, msg


def seven_extract_core(sevenset, extensions, extraction_path, one_folder, delete, password):
    """Unpack single 7Z set 'sevenset' to 'extraction_path'
    Return fail==0(ok)/fail==1(error)/fail==2(wrong password), new_files, message
    """
    if one_folder:
        method = "e"  # Unpack without folders
    else:
        method = "x"  # Unpack with folders
    if sabnzbd.WIN32 or sabnzbd.DARWIN:
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

    if len(extensions) > 0:
        name = "%s.001" % sevenset
        parm = "-tsplit"
    else:
        name = sevenset
        parm = "-tzip" if sevenset.lower().endswith(".zip") else "-t7z"

    if not os.path.exists(name):
        return 1, [], T('7ZIP set "%s" is incomplete, cannot unpack') % setname_from_path(sevenset)

    # For file-bookkeeping
    orig_dir_content = listdir_full(extraction_path)

    command = [SEVEN_COMMAND, method, "-y", overwrite, parm, case, password, "-o%s" % extraction_path, name]
    p = build_and_run_command(command)
    sabnzbd.PostProcessor.external_process = p
    output = platform_btou(p.stdout.read())
    logging.debug("7za output: %s", output)

    ret = p.wait()

    # Return-code for CRC and Password is the same
    if ret == 2 and "ERROR: CRC Failed" in output:
        # We can output a more general error
        ret = 1
        msg = T('ERROR: CRC failed in "%s"') % setname_from_path(sevenset)
    else:
        # Default message
        msg = T("Could not unpack %s") % setname_from_path(sevenset)

    # What's new?
    new_files = list(set(orig_dir_content + listdir_full(extraction_path)))

    if ret == 0 and delete:
        if extensions:
            for ext in extensions:
                path = "%s.%s" % (sevenset, ext)
                try:
                    remove_file(path)
                except:
                    logging.warning(T("Deleting %s failed!"), path)
        else:
            try:
                remove_file(sevenset)
            except:
                logging.warning(T("Deleting %s failed!"), sevenset)

    # Always return an error message, even when return code is 0
    return ret, new_files, msg


##############################################################################
# PAR2 Functions
##############################################################################
def par2_repair(parfile_nzf: NzbFile, nzo: NzbObject, workdir, setname, single):
    """Try to repair a set, return readd or correctness"""
    # Check if file exists, otherwise see if another is done
    parfile_path = os.path.join(workdir, parfile_nzf.filename)
    if not os.path.exists(parfile_path) and nzo.extrapars[setname]:
        for new_par in nzo.extrapars[setname]:
            test_parfile = os.path.join(workdir, new_par.filename)
            if os.path.exists(test_parfile):
                parfile_nzf = new_par
                break
        else:
            # No file was found, we assume this set already finished
            return False, True

    parfile = os.path.join(workdir, parfile_nzf.filename)
    old_dir_content = os.listdir(workdir)
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
            if extrapar not in nzo.finished_files and extrapar not in nzo.files:
                nzo.add_parfile(extrapar)
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

            joinables, zips, rars, sevens, ts = build_filelists(workdir, check_rar=False)

            # Multipar on Windows, par2 on the other platforms
            if sabnzbd.WIN32:
                finished, readd, datafiles, used_joinables, used_for_repair = MultiPar_Verify(
                    parfile, nzo, setname, joinables, single=single
                )
            else:
                finished, readd, datafiles, used_joinables, used_for_repair = PAR_Verify(
                    parfile, nzo, setname, joinables, single=single
                )

            if finished:
                result = True
                logging.info("Par verify finished ok on %s!", parfile)

                # Remove this set so we don't try to check it again
                nzo.remove_parset(parfile_nzf.setname)
            else:
                logging.info("Par verify failed on %s!", parfile)

                if not readd:
                    # Failed to repair -> remove this set
                    nzo.remove_parset(parfile_nzf.setname)
                return readd, False
        except:
            msg = sys.exc_info()[1]
            nzo.fail_msg = T("Repairing failed, %s") % msg
            logging.error(T("Error %s while running par2_repair on set %s"), msg, setname)
            logging.info("Traceback: ", exc_info=True)
            return readd, result

    try:
        if cfg.enable_par_cleanup():
            deletables = []
            new_dir_content = os.listdir(workdir)

            # Remove extra files created during repair and par2 base files
            for path in new_dir_content:
                if os.path.splitext(path)[1] == ".1" and path not in old_dir_content:
                    deletables.append(os.path.join(workdir, path))
            deletables.append(os.path.join(workdir, setname + ".par2"))
            deletables.append(os.path.join(workdir, setname + ".PAR2"))
            deletables.append(parfile)

            # Add output of par2-repair to remove
            deletables.extend(used_joinables)
            deletables.extend([os.path.join(workdir, f) for f in used_for_repair])

            # Delete pars of the set
            deletables.extend([os.path.join(workdir, nzf.filename) for nzf in setpars])

            for filepath in deletables:
                if filepath in joinables:
                    joinables.remove(filepath)
                if os.path.exists(filepath):
                    try:
                        remove_file(filepath)
                    except OSError:
                        logging.warning(T("Deleting %s failed!"), filepath)
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T("Repairing failed, %s") % msg
        logging.error(T('Error "%s" while running par2_repair on set %s'), msg, setname, exc_info=True)

    return readd, result


_RE_BLOCK_FOUND = re.compile(r'File: "([^"]+)" - found \d+ of \d+ data blocks from "([^"]+)"')
_RE_IS_MATCH_FOR = re.compile(r'File: "([^"]+)" - is a match for "([^"]+)"')
_RE_LOADING_PAR2 = re.compile(r'Loading "([^"]+)"\.')
_RE_LOADED_PAR2 = re.compile(r"Loaded (\d+) new packets")


def PAR_Verify(parfile, nzo: NzbObject, setname, joinables, single=False):
    """Run par2 on par-set"""
    used_joinables = []
    used_for_repair = []
    # set the current nzo status to "Verifying...". Used in History
    nzo.status = Status.VERIFYING
    start = time.time()

    options = cfg.par_option().strip()
    command = [str(PAR2_COMMAND), "r", options, parfile]

    # Append the wildcard for this set
    parfolder = os.path.split(parfile)[0]
    if single or len(globber(parfolder, setname + "*")) < 2:
        # Support bizarre naming conventions
        wildcard = "*"
    else:
        # Normal case, everything is named after set
        wildcard = setname + "*"

    if sabnzbd.WIN32 or sabnzbd.DARWIN:
        command.append(os.path.join(parfolder, wildcard))
    else:
        # For Unix systems, remove folders, due to bug in some par2cmdline versions
        flist = [item for item in globber_full(parfolder, wildcard) if os.path.isfile(item)]
        command.extend(flist)

    # We need to check for the bad par2cmdline that skips blocks
    # Or the one that complains about basepath
    # Only if we're not doing multicore
    if not sabnzbd.WIN32 and not sabnzbd.DARWIN:
        par2text = run_command([command[0], "-h"])
        if "No data skipping" in par2text:
            logging.info("Detected par2cmdline version that skips blocks, adding -N parameter")
            command.insert(2, "-N")
        if "Set the basepath" in par2text:
            logging.info("Detected par2cmdline version that needs basepath, adding -B<path> parameter")
            command.insert(2, "-B")
            command.insert(3, parfolder)

    # par2multicore wants to see \\.\ paths on Windows
    # See: https://github.com/sabnzbd/sabnzbd/pull/771
    if sabnzbd.WIN32:
        command = [clip_path(x) if x.startswith("\\\\?\\") else x for x in command]

    # Run the external command
    p = build_and_run_command(command)
    sabnzbd.PostProcessor.external_process = p
    proc = p.stdout

    if p.stdin:
        p.stdin.close()

    # Set up our variables
    lines = []
    datafiles = []
    renames = {}
    reconstructed = []

    linebuf = ""
    finished = 0
    readd = False

    verifynum = 1
    verifytotal = 0
    verified = 0

    in_verify_repaired = False

    # Loop over the output, whee
    while 1:
        char = platform_btou(proc.read(1))
        if not char:
            break

        # Line not complete yet
        if char not in ("\n", "\r"):
            linebuf += char
            continue

        line = linebuf.strip()
        linebuf = ""

        # Skip empty lines
        if line == "":
            continue

        if "Repairing:" not in line:
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
            finished = 1

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

        elif line.startswith("Repairing:"):
            chunks = line.split()
            per = float(chunks[-1][:-1])
            nzo.set_action_line(T("Repairing"), "%2d%%" % per)
            nzo.status = Status.REPAIRING

        elif line.startswith("Repair complete"):
            msg = T("[%s] Repaired in %s") % (setname, format_time_string(time.time() - start))
            nzo.set_unpack_info("Repair", msg)
            logging.info("Repaired in %s", format_time_string(time.time() - start))
            finished = 1

        elif verified and line.endswith(("are missing.", "exist but are damaged.")):
            # Files that will later be verified after repair
            chunks = line.split()
            verifytotal += int(chunks[0])

        elif line.startswith("Verifying repaired files"):
            in_verify_repaired = True
            nzo.set_action_line(T("Verifying repair"), "%02d/%02d" % (verifynum, verifytotal))

        elif in_verify_repaired and line.startswith("Target"):
            verifynum += 1
            if verifynum <= verifytotal:
                nzo.set_action_line(T("Verifying repair"), "%02d/%02d" % (verifynum, verifytotal))

        elif line.startswith("File:") and line.find("data blocks from") > 0:
            m = _RE_BLOCK_FOUND.search(line)
            if m:
                workdir = os.path.split(parfile)[0]
                old_name = m.group(1)
                new_name = m.group(2)
                if joinables:
                    # Find out if a joinable file has been used for joining
                    for jn in joinables:
                        if line.find(os.path.split(jn)[1]) > 0:
                            used_joinables.append(jn)
                            break
                    # Special case of joined RAR files, the "of" and "from" must both be RAR files
                    # This prevents the joined rars files from being seen as an extra rar-set
                    if ".rar" in old_name.lower() and ".rar" in new_name.lower():
                        used_joinables.append(os.path.join(workdir, old_name))
                else:
                    logging.debug('PAR2 will reconstruct "%s" from "%s"', new_name, old_name)
                    reconstructed.append(os.path.join(workdir, old_name))

        elif "Could not write" in line and "at offset 0:" in line:
            # If there are joinables, this error will only happen in case of 100% complete files
            # We can just skip the retry, because par2cmdline will fail in those cases
            # becauses it refuses to scan the ".001" file
            if joinables:
                finished = 1
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

        # File: "oldname.rar" - is a match for "newname.rar".
        elif "is a match for" in line:
            m = _RE_IS_MATCH_FOR.search(line)
            if m:
                old_name = m.group(1)
                new_name = m.group(2)
                logging.debug('PAR2 will rename "%s" to "%s"', old_name, new_name)
                renames[new_name] = old_name

                # Show progress
                if verifytotal == 0 or verifynum < verifytotal:
                    verifynum += 1
                    nzo.set_action_line(T("Verifying"), "%02d/%02d" % (verifynum, verifytotal))

        elif "Scanning extra files" in line:
            # Obfuscated post most likely, so reset counter to show progress
            verifynum = 1

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
            finished = 0

        elif not verified:
            if line.startswith("Verifying source files"):
                nzo.set_action_line(T("Verifying"), "01/%02d" % verifytotal)
                nzo.status = Status.VERIFYING

            elif line.startswith("Scanning:"):
                pass

            # Target files
            m = TARGET_RE.match(line)
            if m:
                nzo.status = Status.VERIFYING
                verifynum += 1
                if verifytotal == 0 or verifynum < verifytotal:
                    nzo.set_action_line(T("Verifying"), "%02d/%02d" % (verifynum, verifytotal))
                else:
                    nzo.set_action_line(T("Checking extra files"), "%02d" % verifynum)

                # Remove redundant extra files that are just duplicates of original ones
                if "duplicate data blocks" in line:
                    used_for_repair.append(m.group(1))
                else:
                    datafiles.append(m.group(1))
                continue

            # Verify done
            m = re.match(r"There are (\d+) recoverable files", line)
            if m:
                verifytotal = int(m.group(1))

    p.wait()

    # Also log what is shown to user in history
    if nzo.fail_msg:
        logging.info(nzo.fail_msg)

    logging.debug("PAR2 output was\n%s", "\n".join(lines))

    # If successful, add renamed files to the collection
    if finished and renames:
        nzo.renamed_file(renames)

    # If successful and files were reconstructed, remove incomplete original files
    if finished and reconstructed:
        # Use 'used_joinables' as a vehicle to get rid of the files
        used_joinables.extend(reconstructed)

    return finished, readd, datafiles, used_joinables, used_for_repair


_RE_FILENAME = re.compile(r'"([^"]+)"')


def MultiPar_Verify(parfile, nzo: NzbObject, setname, joinables, single=False):
    """Run par2 on par-set"""
    parfolder = os.path.split(parfile)[0]
    used_joinables = []
    used_for_repair = []

    # set the current nzo status to "Verifying...". Used in History
    nzo.status = Status.VERIFYING
    start = time.time()

    # Caching of verification implemented by adding -vs/-vd
    # Force output of utf-8 by adding -uo
    # But not really required due to prospective-par2
    command = [str(MULTIPAR_COMMAND), "r", "-uo", "-vs2", "-vd%s" % parfolder, parfile]

    # Check if there are maybe par2cmdline/par2tbb commands supplied
    if "-t" in cfg.par_option() or "-p" in cfg.par_option():
        logging.info("Removing old par2cmdline/par2tbb options for MultiPar")
        cfg.par_option.set("")

    # Only add user-options if supplied
    options = cfg.par_option().strip()
    if options:
        # We wrongly instructed users to use /x parameter style instead of -x
        options = options.replace("/", "-", 1)
        command.insert(2, options)

    # Append the wildcard for this set
    if single or len(globber(parfolder, setname + "*")) < 2:
        # Support bizarre naming conventions
        wildcard = "*"
    else:
        # Normal case, everything is named after set
        wildcard = setname + "*"
    command.append(os.path.join(parfolder, wildcard))

    # Run MultiPar
    p = build_and_run_command(command)
    sabnzbd.PostProcessor.external_process = p
    proc = p.stdout
    if p.stdin:
        p.stdin.close()

    # Set up our variables
    lines = []
    datafiles = []
    renames = {}
    reconstructed = []

    linebuf = b""
    finished = 0
    readd = False

    verifynum = 0
    verifytotal = 0

    in_check = False
    in_verify = False
    in_repair = False
    in_verify_repaired = False
    misnamed_files = False
    old_name = None

    # Loop over the output, whee
    while 1:
        char = proc.read(1)
        if not char:
            break

        # Line not complete yet
        if char not in (b"\n", b"\r"):
            linebuf += char
            continue

        line = ubtou(linebuf).strip()
        linebuf = b""

        # Skip empty lines
        if line == "":
            continue

        # Save it all
        lines.append(line)

        # ----------------- Startup
        if line.startswith("invalid option"):
            # Option error
            msg = T("[%s] PAR2 received incorrect options, check your Config->Switches settings") % setname
            nzo.set_unpack_info("Repair", msg)
            nzo.status = Status.FAILED
            logging.error(msg)

        elif line.startswith("valid file is not found"):
            # Initialparfile probably didn't decode properly, or bad user parameters
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

        elif line.startswith("There is not enough space on the disk"):
            msg = T("Repairing failed, %s") % T("Disk full")
            nzo.fail_msg = msg
            nzo.set_unpack_info("Repair", msg, setname)
            nzo.status = Status.FAILED

        # ----------------- Start check/verify stage
        elif line.startswith("Recovery Set ID"):
            # Remove files were MultiPar stores verification result when repaired succesfull
            recovery_id = line.split()[-1]
            used_for_repair.append("2_%s.bin" % recovery_id)
            used_for_repair.append("2_%s.ini" % recovery_id)

        elif line.startswith("Input File total count"):
            # How many files will it try to find?
            verifytotal = int(line.split()[-1])

        # ----------------- Misnamed-detection stage
        # Misnamed files
        elif line.startswith("Searching misnamed file"):
            # We are in the misnamed files block
            misnamed_files = True
            verifynum = 0
        elif misnamed_files and "Found" in line:
            # First it reports the current filename
            m = _RE_FILENAME.search(line)
            if m:
                verifynum += 1
                nzo.set_action_line(T("Checking"), "%02d/%02d" % (verifynum, verifytotal))
                old_name = m.group(1)
        elif misnamed_files and "Misnamed" in line:
            # Then it finds the actual
            m = _RE_FILENAME.search(line)
            if m and old_name:
                new_name = m.group(1)
                logging.debug('MultiPar will rename "%s" to "%s"', old_name, new_name)
                renames[new_name] = old_name
                # New name is also part of data!
                datafiles.append(new_name)
                reconstructed.append(old_name)

        # ----------------- Checking stage
        # Checking input files
        elif line.startswith("Complete file count"):
            in_check = False
            verifynum = 0
            old_name = None
        elif line.startswith("Verifying Input File"):
            in_check = True
            nzo.status = Status.VERIFYING
        elif in_check:
            m = _RE_FILENAME.search(line)
            if m:
                # Only increase counter if it was really the detection line
                if line.startswith("= ") or "%" not in line:
                    verifynum += 1
                nzo.set_action_line(T("Checking"), "%02d/%02d" % (verifynum, verifytotal))
                old_name = m.group(1)

        # ----------------- Verify stage
        # Which files need extra verification?
        elif line.startswith("Damaged file count"):
            verifytotal = int(line.split()[-1])

        elif line.startswith("Missing file count"):
            verifytotal += int(line.split()[-1])

        # Actual verification
        elif line.startswith("Input File Slice found"):
            # End of verification AND end of misnamed file search
            in_verify = False
            misnamed_files = False
            old_name = None
        elif line.startswith("Finding available slice"):
            # The actual scanning of the files
            in_verify = True
            nzo.set_action_line(T("Verifying"), T("Checking"))
        elif in_verify:
            m = _RE_FILENAME.search(line)
            if m:
                # It prints the filename couple of times, so we save it to check
                # 'datafiles' will not contain all data-files in par-set, only the
                # ones that got scanned, but it's ouput is never used!
                nzo.status = Status.VERIFYING
                if line.split()[1] in ("Damaged", "Found"):
                    verifynum += 1
                    datafiles.append(m.group(1))

                    # Set old_name in case it was misnamed and found (not when we are joining)
                    old_name = None
                    if line.split()[1] == "Found" and not joinables:
                        old_name = m.group(1)

                    # Sometimes we don't know the total (filejoin)
                    if verifytotal <= 1:
                        nzo.set_action_line(T("Verifying"), "%02d" % verifynum)
                    else:
                        nzo.set_action_line(T("Verifying"), "%02d/%02d" % (verifynum, verifytotal))

                elif old_name and old_name != m.group(1):
                    # Hey we found another misnamed one!
                    new_name = m.group(1)
                    logging.debug('MultiPar will rename "%s" to "%s"', old_name, new_name)
                    renames[new_name] = old_name
                    # Put it back with it's new name!
                    datafiles.pop()
                    datafiles.append(new_name)
                    # Need to remove the old file after repair (Multipar keeps it)
                    used_for_repair.append(old_name)
                    # Need to reset it to avoid collision
                    old_name = None

                else:
                    # It's scanning extra files that don't belong to the set
                    # For damaged files it reports the filename twice, so only then start
                    verifynum += 1
                    if verifynum / 2 > verifytotal:
                        nzo.set_action_line(T("Checking extra files"), "%02d" % verifynum)

                if joinables:
                    # Find out if a joinable file has been used for joining
                    for jn in joinables:
                        if line.find(os.path.split(jn)[1]) > 0:
                            used_joinables.append(jn)
                            datafiles.append(m.group(1))
                            break

        elif line.startswith("Need"):
            # We need more blocks, but are they available?
            chunks = line.split()
            needed_blocks = int(chunks[1])

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

            # MultiPar can say 'PAR File(s) Incomplete' also when it needs more blocks
            # But the Need-more-blocks message is always last, so force failure
            finished = 0

        # Result of verification
        elif line.startswith("All Files Complete") or line.endswith("PAR File(s) Incomplete"):
            # Completed without damage!
            # 'PAR File(s) Incomplete' is reported for success
            # but when there are very similar filenames in the folder
            msg = T("[%s] Verified in %s, all files correct") % (setname, format_time_string(time.time() - start))
            nzo.set_unpack_info("Repair", msg)
            logging.info("Verified in %s, all files correct", format_time_string(time.time() - start))
            finished = 1

        elif line.startswith(("Ready to repair", "Ready to rejoin")):
            # Ready to repair!
            # Or we are re-joining a split file when there's no damage but takes time
            msg = T("[%s] Verified in %s, repair is required") % (setname, format_time_string(time.time() - start))
            nzo.set_unpack_info("Repair", msg)
            logging.info("Verified in %s, repair is required", format_time_string(time.time() - start))
            start = time.time()

            # Set message for user in case of joining
            if line.startswith("Ready to rejoin"):
                nzo.set_action_line(T("Joining"), "%2d" % len(used_joinables))
            else:
                # If we are repairing a joinable set, it won't actually
                # do the joining. So we can't remove those files!
                used_joinables = []

        # ----------------- Repair stage
        elif "Recovering slice" in line:
            # Before this it will calculate matrix, here is where it starts
            start = time.time()
            in_repair = True
            nzo.set_action_line(T("Repairing"), "%2d%%" % 0)

        elif in_repair and line.startswith("Verifying repair"):
            in_repair = False
            in_verify_repaired = True
            # How many will be checked?
            verifytotal = int(line.split()[-1])
            verifynum = 0

        elif in_repair:
            try:
                # Line with percentage of repair (nothing else)
                per = float(line[:-1])
                nzo.set_action_line(T("Repairing"), "%2d%%" % per)
                nzo.status = Status.REPAIRING
            except:
                # Checksum error
                if "checksum" in line:
                    # Failed due to checksum error of multipar
                    msg = T("Repairing failed, %s") % line
                    nzo.fail_msg = msg
                    nzo.set_unpack_info("Repair", msg, setname)
                    nzo.status = Status.FAILED
                else:
                    # Not sure, log error
                    logging.info("Traceback: ", exc_info=True)

        elif line.startswith("Repaired successfully"):
            msg = T("[%s] Repaired in %s") % (setname, format_time_string(time.time() - start))
            nzo.set_unpack_info("Repair", msg)
            logging.info("Repaired in %s", format_time_string(time.time() - start))
            finished = 1

        elif in_verify_repaired and line.startswith("Repaired :"):
            # Track verification of repaired files (can sometimes take a while)
            verifynum += 1
            nzo.set_action_line(T("Verifying repair"), "%02d/%02d" % (verifynum, verifytotal))

        elif line.startswith("Failed to repair") and not readd:
            # Unknown repair problem
            msg = T("Repairing failed, %s") % line
            nzo.fail_msg = msg
            nzo.set_unpack_info("Repair", msg, setname)
            nzo.status = Status.FAILED
            finished = 0

    p.wait()

    # Also log what is shown to user in history
    if nzo.fail_msg:
        logging.info(nzo.fail_msg)

    logging.debug("MultiPar output was\n%s", "\n".join(lines))

    # Add renamed files to the collection
    # MultiPar always(!!) renames automatically whatever it can in the 'Searching misnamed file:'-section
    # Even if the repair did not complete fully it will rename those!
    # But the ones in 'Finding available slices'-section will only be renamed after succesfull repair
    if renames:
        # If succes, we also remove the possibly previously renamed ones
        if finished:
            reconstructed.extend(list(renames.values()))

        # Adding to the collection
        nzo.renamed_file(renames)

        # Remove renamed original files
        workdir = os.path.split(parfile)[0]
        used_joinables.extend([os.path.join(workdir, name) for name in reconstructed])

    return finished, readd, datafiles, used_joinables, used_for_repair


def create_env(nzo=None, extra_env_fields={}):
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
            except:
                # Catch key errors
                pass

    # Always supply basic info
    extra_env_fields.update(
        {
            "program_dir": sabnzbd.DIR_PROG,
            "par2_command": sabnzbd.newsunpack.PAR2_COMMAND,
            "multipar_command": sabnzbd.newsunpack.MULTIPAR_COMMAND,
            "rar_command": sabnzbd.newsunpack.RAR_COMMAND,
            "zip_command": sabnzbd.newsunpack.ZIP_COMMAND,
            "7zip_command": sabnzbd.newsunpack.SEVEN_COMMAND,
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
        except:
            # Catch key errors
            pass

    if sabnzbd.DARWIN:
        if "PYTHONPATH" in env:
            del env["PYTHONPATH"]
        if "PYTHONHOME" in env:
            del env["PYTHONHOME"]
    elif not nzo:
        # No modification
        return None

    return env


def rar_volumelist(rarfile_path, password, known_volumes):
    """List volumes that are part of this rarset
    and merge them with parsed paths list, removing duplicates.
    We assume RarFile is right and use parsed paths as backup.
    """
    # UnRar is required to read some RAR files
    # RarFile can fail in special cases
    try:
        rarfile.UNRAR_TOOL = RAR_COMMAND
        zf = rarfile.RarFile(rarfile_path)

        # setpassword can fail due to bugs in RarFile
        if password:
            try:
                zf.setpassword(password)
            except:
                pass
        zf_volumes = zf.volumelist()
    except:
        zf_volumes = []

    # Remove duplicates
    zf_volumes_base = [os.path.basename(vol) for vol in zf_volumes]
    for known_volume in known_volumes:
        if os.path.basename(known_volume) not in zf_volumes_base:
            # Long-path notation just to be sure
            zf_volumes.append(long_path(known_volume))
    return zf_volumes


# Sort the various RAR filename formats properly :\
def rar_sort(a, b):
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


def build_filelists(workdir, workdir_complete=None, check_both=False, check_rar=True):
    """Build filelists, if workdir_complete has files, ignore workdir.
    Optionally scan both directories.
    Optionally test content to establish RAR-ness
    """
    sevens, joinables, zips, rars, ts, filelist = ([], [], [], [], [], [])

    if workdir_complete:
        filelist.extend(listdir_full(workdir_complete))

    if workdir and (not filelist or check_both):
        filelist.extend(listdir_full(workdir, recursive=False))

    for file in filelist:
        # Extra check for rar (takes CPU/disk)
        file_is_rar = False
        if check_rar:
            file_is_rar = rarfile.is_rarfile(file)

        # Run through all the checks
        if SEVENZIP_RE.search(file) or SEVENMULTI_RE.search(file):
            # 7zip
            sevens.append(file)
        elif SPLITFILE_RE.search(file) and not file_is_rar:
            # Joinables, optional with RAR check
            joinables.append(file)
        elif ZIP_RE.search(file):
            # ZIP files
            zips.append(file)
        elif RAR_RE.search(file):
            # RAR files
            rars.append(file)
        elif TS_RE.search(file):
            # TS split files
            ts.append(file)

    logging.debug("build_filelists(): joinables: %s", joinables)
    logging.debug("build_filelists(): zips: %s", zips)
    logging.debug("build_filelists(): rars: %s", rars)
    logging.debug("build_filelists(): 7zips: %s", sevens)
    logging.debug("build_filelists(): ts: %s", ts)

    return joinables, zips, rars, sevens, ts


def quick_check_set(set, nzo):
    """Check all on-the-fly md5sums of a set"""
    md5pack = nzo.md5packs.get(set)
    if md5pack is None:
        return False

    # We use bitwise assigment (&=) so False always wins in case of failure
    # This way the renames always get saved!
    result = True
    nzf_list = nzo.finished_files
    renames = {}

    # Files to ignore
    ignore_ext = cfg.quick_check_ext_ignore()

    for file in md5pack:
        found = False
        file_to_ignore = get_ext(file).replace(".", "") in ignore_ext
        for nzf in nzf_list:
            # Do a simple filename based check
            if file == nzf.filename:
                found = True
                if (nzf.md5sum is not None) and nzf.md5sum == md5pack[file]:
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

            # Now lets do obfuscation check
            if nzf.md5sum == md5pack[file]:
                try:
                    logging.debug("Quick-check will rename %s to %s", nzf.filename, file)

                    # Note: file can and is allowed to be in a subdirectory.
                    # Subdirectories in par2 always contain "/", not "\"
                    renamer(
                        os.path.join(nzo.download_path, nzf.filename),
                        os.path.join(nzo.download_path, file),
                        create_local_directories=True,
                    )
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
                logging.debug("Quick-check ignoring missing file %s", file)
                continue

            logging.info("Cannot Quick-check missing file %s!", file)
            result = False

    # Save renames
    if renames:
        nzo.renamed_file(renames)

    return result


def unrar_check(rar):
    """Return version number of unrar, where "5.01" returns 501
    Also return whether an original version is found
    (version, original)
    """
    version = 0
    original = ""
    if rar:
        try:
            version = run_command([rar])
        except:
            return version, original
        original = "Alexander Roshal" in version
        m = re.search(r"RAR\s(\d+)\.(\d+)", version)
        if m:
            version = int(m.group(1)) * 100 + int(m.group(2))
        else:
            version = 0
    return version, original


def par2_mt_check(par2_path):
    """Detect if we have multicore par2 variants"""
    try:
        par2_version = run_command([par2_path, "-h"])
        # Look for a threads option
        if "-t<" in par2_version:
            return True
    except:
        pass
    return False


def is_sfv_file(myfile):
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
    except:
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


def sfv_check(sfvs, nzo: NzbObject, workdir):
    """Verify files using SFV files"""
    # Update status
    nzo.status = Status.VERIFYING
    nzo.set_action_line(T("Trying SFV verification"), "...")

    # We use bitwise assigment (&=) so False always wins in case of failure
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
        verifynum += 1
        nzo.set_action_line(T("Verifying"), "%02d/%02d" % (verifynum, verifytotal))
        calculated_crc32[nzf.filename] = crc_calculate(os.path.join(workdir, nzf.filename))

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
                if nzf.filename in calculated_crc32 and calculated_crc32[nzf.filename] == sfv_parse_results[file]:
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
            if nzf.filename in calculated_crc32 and calculated_crc32[nzf.filename] == sfv_parse_results[file]:
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
                logging.debug("SVF-check ignoring missing file %s", file)
                continue

            logging.info("Cannot SFV-check missing file %s!", file)
            result = False

    # Save renames
    if renames:
        nzo.renamed_file(renames)

    return result


def parse_sfv(sfv_filename):
    """Parse SFV file and return dictonary of crc32's and filenames"""
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


def crc_calculate(path):
    """Calculate crc32 of the given file"""
    crc = 0
    with open(path, "rb") as fp:
        while 1:
            data = fp.read(4096)
            if not data:
                break
            crc = zlib.crc32(data, crc)
    return b"%08x" % (crc & 0xFFFFFFFF)


def analyse_show(name: str) -> Tuple[str, str, str, str, bool]:
    """Do a quick SeasonSort check and return basic facts"""
    job = SeriesSorter(None, name, None, None, force=True)
    if job.matched:
        job.get_values()
    return (
        job.info.get("title", ""),
        job.info.get("season_num", ""),
        job.info.get("episode_num", ""),
        job.info.get("ep_name", ""),
        job.is_proper(),
    )


def pre_queue(nzo: NzbObject, pp, cat):
    """Run pre-queue script (if any) and process results.
    pp and cat are supplied seperate since they can change.
    """

    def fix(p):
        # If added via API, some items can still be "None" (as a string)
        if not p or str(p).lower() == "none":
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
        command.extend(analyse_show(nzo.final_name_with_password)[:4])
        command = [fix(arg) for arg in command]

        # Fields not in the NZO directly
        extra_env_fields = {
            "groups": " ".join(nzo.groups),
            "show_name": command[8],
            "show_season": command[9],
            "show_episode": command[10],
            "show_episode_name": command[11],
        }

        try:
            p = build_and_run_command(command, env=create_env(nzo, extra_env_fields))
        except:
            logging.debug("Failed script %s, Traceback: ", script_path, exc_info=True)
            return values

        output = platform_btou(p.stdout.read())
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


def is_sevenfile(path):
    """Return True if path has proper extension and 7Zip is installed"""
    return SEVEN_COMMAND and os.path.splitext(path)[1].lower() == ".7z"


class SevenZip:
    """Minimal emulation of ZipFile class for 7Zip"""

    def __init__(self, path):
        self.path = path

    def namelist(self):
        """Return list of names in 7Zip"""
        names = []
        # Future extension: use '-sccUTF-8' to get names in UTF8 encoding
        command = [SEVEN_COMMAND, "l", "-p", "-y", "-slt", self.path]
        output = run_command(command)

        re_path = re.compile("^Path = (.+)")
        for line in output.split("\n"):
            m = re_path.search(line)
            if m:
                names.append(m.group(1).strip("\r"))
        if names:
            # Remove name of archive itself
            del names[0]
        return names

    def read(self, name):
        """Read named file from 7Zip and return data"""
        command = [SEVEN_COMMAND, "e", "-p", "-y", "-so", self.path, name]
        # Ignore diagnostic output, otherwise it will be appended to content
        return run_command(command, stderr=subprocess.DEVNULL)

    def close(self):
        """Close file"""
        pass
