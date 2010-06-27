#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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
from time import time
import binascii

import sabnzbd
from sabnzbd.encoding import TRANS, UNTRANS, unicode2local,name_fixer, reliable_unpack_names, unicoder
from sabnzbd.utils.rarfile import RarFile, is_rarfile
from sabnzbd.misc import format_time_string, find_on_path, make_script_path
from sabnzbd.tvsort import SeriesSorter
import sabnzbd.cfg as cfg
from sabnzbd.lang import T, Ta

if sabnzbd.WIN32:
    try:
        import win32api
        from win32con import SW_HIDE
        from win32process import STARTF_USESHOWWINDOW, IDLE_PRIORITY_CLASS
    except ImportError:
        pass
else:
    # Define dummy WindowsError for non-Windows
    class WindowsError(Exception):
        def __init__(self, value):
            self.parameter = value
        def __str__(self):
            return repr(self.parameter)

# Regex globals
RAR_RE = re.compile(r'\.(?P<ext>part\d*\.rar|rar|s\d\d|r\d\d|\d\d\d)$', re.I)
RAR_RE_V3 = re.compile(r'\.(?P<ext>part\d*)$', re.I)

LOADING_RE = re.compile(r'^Loading "(.+)"')
TARGET_RE = re.compile(r'^(?:File|Target): "(.+)" -')
EXTRACTFROM_RE = re.compile(r'^Extracting\sfrom\s(.+)')
SPLITFILE_RE = re.compile(r'\.(\d\d\d$)', re.I)
ZIP_RE = re.compile(r'\.(zip$)', re.I)
VOLPAR2_RE = re.compile(r'\.*vol[0-9]+\+[0-9]+\.par2', re.I)
FULLVOLPAR2_RE = re.compile(r'(.*[^.])(\.*vol[0-9]+\+[0-9]+\.par2)', re.I)
TS_RE = re.compile(r'\.(\d+)\.(ts$)', re.I)

PAR2_COMMAND = None
PAR2C_COMMAND = None
RAR_COMMAND = None
NICE_COMMAND = None
ZIP_COMMAND = None
IONICE_COMMAND = None
RAR_PROBLEM = False

def find_programs(curdir):
    """Find external programs
    """
    def check(path, program):
        p = os.path.abspath(os.path.join(path, program))
        if os.access(p, os.X_OK):
            return p
        else:
            return None

    if sabnzbd.DARWIN:
        try:
            os_version = subprocess.Popen("sw_vers -productVersion", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).stdout.read()
            #par2-sl from Macpar Deluxe 4.1 is only 10.6 and later
            if int(os_version.split('.')[1]) >= 6:
                sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, 'osx/par2/par2-sl')
            else:
                sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, 'osx/par2/par2-classic')
        except:
            sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, 'osx/par2/par2-classic')

        sabnzbd.newsunpack.RAR_COMMAND =  check(curdir, 'osx/unrar/unrar')

    if sabnzbd.WIN32:
        if sabnzbd.WIN64:
            sabnzbd.newsunpack.PAR2_COMMAND =  check(curdir, 'win/par2/x64/par2.exe')
            sabnzbd.newsunpack.RAR_COMMAND =   check(curdir, 'win/unrar/x64/UnRAR.exe')
        if not sabnzbd.newsunpack.PAR2_COMMAND:
            sabnzbd.newsunpack.PAR2_COMMAND =  check(curdir, 'win/par2/par2.exe')
        if not sabnzbd.newsunpack.RAR_COMMAND:
            sabnzbd.newsunpack.RAR_COMMAND =   check(curdir, 'win/unrar/UnRAR.exe')
        sabnzbd.newsunpack.PAR2C_COMMAND = check(curdir, 'win/par2/par2-classic.exe')
        sabnzbd.newsunpack.ZIP_COMMAND =   check(curdir, 'win/unzip/unzip.exe')
    else:
        if not sabnzbd.newsunpack.PAR2_COMMAND:
            sabnzbd.newsunpack.PAR2_COMMAND = find_on_path('par2')
        if not sabnzbd.newsunpack.RAR_COMMAND:
            sabnzbd.newsunpack.RAR_COMMAND = find_on_path(('unrar', 'rar', 'unrar3', 'rar3',))
        sabnzbd.newsunpack.NICE_COMMAND = find_on_path('nice')
        sabnzbd.newsunpack.IONICE_COMMAND = find_on_path('ionice')
        sabnzbd.newsunpack.ZIP_COMMAND = find_on_path('unzip')

    if not (sabnzbd.WIN32 or sabnzbd.DARWIN):
        sabnzbd.newsunpack.RAR_PROBLEM = not unrar_check(sabnzbd.newsunpack.RAR_COMMAND)

#------------------------------------------------------------------------------
def external_processing(extern_proc, complete_dir, filename, msgid, nicename, cat, group, status):

    command = [str(extern_proc), str(complete_dir), str(filename), \
               str(nicename), str(msgid), str(cat), str(group), str(status)]

    stup, need_shell, command, creationflags = build_command(command)
    env = fix_env()

    logging.info('Running external script %s(%s, %s, %s, %s, %s, %s, %s)', \
                 extern_proc, complete_dir, filename, nicename, msgid, cat, group, status)

    try:
        p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            startupinfo=stup, env=env, creationflags=creationflags)
    except:
        logging.debug("Failed script %s, Traceback: ", extern_proc, exc_info = True)
        return "Cannot run script %s\r\n" % extern_proc, -1

    output = p.stdout.read()
    ret = p.wait()
    return output, ret


#------------------------------------------------------------------------------
def SimpleRarExtract(rarfile, name):
    """ Extract single file from rar archive, returns (retcode, data) """
    command = [sabnzbd.newsunpack.RAR_COMMAND, "p", "-inul", rarfile, name]

    stup, need_shell, command, creationflags = build_command(command)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    output = p.stdout.read()
    ret = p.wait()
    return ret, output

#------------------------------------------------------------------------------
def unpack_magic(nzo, workdir, workdir_complete, dele, joinables, zips, rars, ts, depth=0):
    if depth > 5:
        logging.warning('Unpack nesting too deep [%s]', nzo.final_name)
        return False, []
    depth += 1

    xjoinables, xzips, xrars, xts = build_filelists(workdir, workdir_complete)

    rerun = False
    newfiles = []
    error = False

    if cfg.enable_filejoin():
        new_joins = [jn for jn in xjoinables if jn not in joinables]
        if new_joins:
            rerun = True
            logging.info('Filejoin starting on %s', workdir)
            error, newf = file_join(nzo, workdir, workdir_complete, dele, new_joins)
            if newf:
                newfiles.extend(newf)
            logging.info('Filejoin finished on %s', workdir)
            nzo.set_action_line()

    if cfg.enable_unrar():
        new_rars = [rar for rar in xrars if rar not in rars]
        if new_rars:
            rerun = True
            logging.info('Unrar starting on %s', workdir)
            error, newf = rar_unpack(nzo, workdir, workdir_complete, dele, new_rars)
            if newf:
                newfiles.extend(newf)
            logging.info('Unrar finished on %s', workdir)
            nzo.set_action_line()

    if cfg.enable_unzip():
        new_zips = [zip for zip in xzips if zip not in zips]
        if new_zips:
            logging.info('Unzip starting on %s', workdir)
            if unzip(nzo, workdir, workdir_complete, dele, new_zips):
                error = True
            logging.info('Unzip finished on %s', workdir)
            nzo.set_action_line()

    if cfg.enable_tsjoin():
        new_ts = [_ts for _ts in xts if _ts not in ts]
        if new_ts:
            rerun = True
            logging.info('TS Joining starting on %s', workdir)
            error, newf = file_join(nzo, workdir, workdir_complete, dele, new_ts)
            if newf:
                newfiles.extend(newf)
            logging.info('TS Joining finished on %s', workdir)
            nzo.set_action_line()


    if rerun:
        z, y = unpack_magic(nzo, workdir, workdir_complete, dele, xjoinables,
                            xzips, xrars, xts, depth)
        if z:
            error = z
        if y:
            newfiles.extend(y)

    return error, newfiles

#------------------------------------------------------------------------------
# Filejoin Functions
#------------------------------------------------------------------------------

def match_ts(file):
    match = TS_RE.search(file)
    if not match:
        return False, '', 0

    num = int(match.group(1))
    try:
        set = file[:match.start()]
        set += '.ts'
    except:
        set = ''
    return match, set, num

def file_join(nzo, workdir, workdir_complete, delete, joinables):
    newfiles = []
    try:
        joinable_sets = {}
        set = match = num = None
        for joinable in joinables:
            head, tail = os.path.splitext(joinable)
            if tail == '.ts':
                match, set, num = match_ts(joinable)
            if not set:
                set = head

            if set not in joinable_sets:
                joinable_sets[set] = []
            joinable_sets[set].append(joinable)

        logging.debug("joinable_sets: %s", joinable_sets)

        for joinable_set in joinable_sets:
            try:
                expected_size = 0
                # Make sure there are no missing files in the file sequence
                # Add 1 to the value before adding to take into account .000
                for i in xrange(len(joinable_sets[joinable_set])+1):
                    expected_size += i
                logging.debug("FJN, expsize: %s", expected_size)

                # Add together the values of .001 (+1 for .000)
                # To work out the actual size
                real_size = 0
                for joinable in joinable_sets[joinable_set]:
                    head, tail = os.path.splitext(joinable)
                    if tail == '.ts':
                        match, set, num = match_ts(joinable)
                        real_size += num+1
                    else:
                        real_size += int(tail[1:])
                logging.debug("FJN, realsize: %s", real_size)

                if real_size != expected_size:
                    msg = T('error-joinMismatch')
                    nzo.fail_msg = T('error-joinFail@1') % msg
                    nzo.set_unpack_info('Filejoin', T('error-joinFail@2') % (unicoder(joinable_set), msg))
                    logging.error(Ta('error-fileJoin@2'), msg, nzo.final_name)
                else:
                    joinable_sets[joinable_set].sort()
                    filename = joinable_set

                    # Check if par2 repaired this joinable set
                    if os.path.exists(filename):
                        logging.debug("file_join(): Skipping %s, (probably) joined by par2", filename)
                        if delete:
                            i = 0
                            for joinable in joinable_sets[joinable_set]:
                                if os.path.exists(joinable):
                                    logging.debug("Deleting %s", joinable)
                                    try:
                                        os.remove(joinable)
                                    except:
                                        pass
                                path1 = joinable + ".1"
                                if os.path.exists(path1):
                                    logging.debug("Deleting %s", path1)
                                    try:
                                        os.remove(path1)
                                    except:
                                        pass
                                i += 1
                        continue

                    if workdir_complete:
                        filename = filename.replace(workdir, workdir_complete)

                    logging.debug("file_join(): Assembling %s", filename)

                    joined_file = open(filename, 'ab')

                    i = 0
                    for joinable in joinable_sets[joinable_set]:
                        join_num = len(joinable_sets[joinable_set])
                        perc = (100.0/join_num)*(i)
                        logging.debug("Processing %s", joinable)
                        nzo.set_action_line(T('msg-joining'), '%.0f%%' % perc)
                        f = open(joinable, 'rb')
                        joined_file.write(f.read())
                        f.close()
                        i += 1
                        if delete:
                            logging.debug("Deleting %s", joinable)
                            os.remove(joinable)

                    joined_file.flush()
                    joined_file.close()
                    msg = T('msg-joinOK@2') % (unicoder(joinable_set), i)
                    nzo.set_unpack_info('Filejoin', msg, set=joinable_set)
                    newfiles.append(joinable_set)
            except:
                msg = sys.exc_info()[1]
                nzo.fail_msg = T('error-joinFail@1') % msg
                nzo.set_unpack_info('Filejoin', T('error-joinFail@2') % (unicoder(joinable_set), msg))
                logging.error(Ta('error-fileJoin@2'), msg, nzo.final_name)
                return True, []

        return False, newfiles
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T('error-joinFail@1') % msg
        nzo.set_unpack_info('Filejoin', T('error-joinFail@2') % (unicoder(joinable_set), msg))
        logging.error(Ta('error-fileJoin@2'), msg, nzo.final_name)
        return True, []


#------------------------------------------------------------------------------
# (Un)Rar Functions
#------------------------------------------------------------------------------

def rar_unpack(nzo, workdir, workdir_complete, delete, rars):
    extracted_files = []

    rar_sets = {}
    for rar in rars:
        rar_set = os.path.splitext(os.path.basename(rar))[0]
        if RAR_RE_V3.search(rar_set):
            rar_set = os.path.splitext(rar_set)[0]
        if not rar_set in rar_sets:
            rar_sets[rar_set] = []
        rar_sets[rar_set].append(rar)

    logging.debug('Rar_sets: %s', rar_sets)

    for rar_set in rar_sets:
        # Run the RAR extractor
        rar_sets[rar_set].sort(rar_sort)

        rarpath = rar_sets[rar_set][0]

        if workdir_complete and rarpath.startswith(workdir):
            extraction_path = workdir_complete
        else:
            extraction_path = os.path.split(rarpath)[0]

        logging.info("Extracting rarfile %s (belonging to %s) to %s",
                     rarpath, rar_set, extraction_path)

        try:
            newfiles, rars = RAR_Extract(rarpath, len(rar_sets[rar_set]),
                                         nzo, rar_set, extraction_path)
            success = newfiles and rars
        except:
            success = False
            msg = sys.exc_info()[1]
            nzo.set_fail = T('error-unpackFail@1') % msg
            setname = nzo.final_name
            nzo.set_unpack_info('Unpack', T('error-unpackFail@2') % (unicoder(setname), msg))

            logging.error(Ta('error-fileUnrar@2'), msg, setname)

        if success:
            logging.debug('rar_unpack(): Rars: %s', rars)
            logging.debug('rar_unpack(): Newfiles: %s', newfiles)
            extracted_files.extend(newfiles)

        # Delete the old files if we have to
        if success and delete and newfiles:
            for rar in rars:
                logging.info("Deleting %s", rar)
                try:
                    os.remove(rar)
                except OSError:
                    logging.warning(Ta('warn-delFailed@1'), rar)

                brokenrar = '%s.1' % (rar)

                if os.path.exists(brokenrar):
                    logging.info("Deleting %s", brokenrar)
                    try:
                        os.remove(brokenrar)
                    except OSError:
                        logging.warning(Ta('warn-delFailed@1'), brokenrar)

    return not success, extracted_files


def RAR_Extract(rarfile, numrars, nzo, setname, extraction_path):
    start = time()

    logging.debug("RAR_Extract(): Extractionpath: %s",
                  extraction_path)

    try:
        zf = RarFile(rarfile)
        expected_files = zf.unamelist()
        zf.close()
    except:
        nzo.fail_msg = T('error-badArchive')
        nzo.set_unpack_info('Unpack', u'[%s] %s' % (unicoder(setname), T('error-badArchive')), set=setname)

        logging.info('Archive %s probably encrypted, skipping', rarfile)
        return ((), ())

    if nzo.password:
        password = '-p%s' % nzo.password
    else:
        password = '-p-'

    ############################################################################

    if sabnzbd.WIN32:
        # Use all flags
        command = ['%s' % RAR_COMMAND, 'x', '-idp', '-o-', '-or', '-ai', password,
                   '%s' % rarfile, '%s/' % extraction_path]
    elif RAR_PROBLEM:
        # Use only oldest options (specifically no "-or")
        command = ['%s' % RAR_COMMAND, 'x', '-idp', '-o-', password,
                   '%s' % rarfile, '%s/' % extraction_path]
    else:
        # Don't use "-ai" (not needed for non-Windows)
        command = ['%s' % RAR_COMMAND, 'x', '-idp', '-o-', '-or', password,
                   '%s' % rarfile, '%s/' % extraction_path]

    stup, need_shell, command, creationflags = build_command(command)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    proc = p.stdout
    if p.stdin:
        p.stdin.close()

    nzo.set_action_line(T('msg-unpacking'), '00/%02d' % (numrars))

    # Loop over the output from rar!
    curr = 0
    extracted = []
    rarfiles = []
    fail = 0

    while 1:
        line = proc.readline()
        if not line:
            break

        line = line.strip()

        if line.startswith('Extracting from'):
            filename = TRANS((re.search(EXTRACTFROM_RE, line).group(1)))
            if filename not in rarfiles:
                rarfiles.append(filename)
            curr += 1
            nzo.set_action_line(T('msg-unpacking'), '%02d/%02d' % (curr, numrars))

        elif line.startswith('Cannot find volume'):
            filename = os.path.basename(TRANS(line[19:]))
            nzo.fail_msg = T('error-unpackFailed@1') % unicoder(filename)
            msg = ('[%s] '+Ta('error-unpackFailed@1')) % (setname, filename)
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            logging.warning(Ta('warn-cannotFind@1'), filename)
            fail = 1

        elif line.endswith('- CRC failed'):
            filename = TRANS(line[:-12].strip())
            nzo.fail_msg = T('error-unpackCRC')
            msg = ('[%s] '+Ta('warn-crcFailed@1')) % (setname, filename)
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            logging.warning(Ta('warn-crcFailed@1'), setname)
            fail = 1

        elif line.startswith('Write error'):
            nzo.fail_msg = T('error-unpackFull')
            msg = ('[%s] ' + Ta('error-unpackFull')) % setname
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            logging.warning(Ta('warn-writeError@1'), line[11:])
            fail = 1

        elif line.startswith('ERROR: '):
            nzo.fail_msg = T('error-unpackFailLog')
            logging.warning(Ta('warn-error@1'), (line[7:]))
            msg = ('[%s] '+Ta('warn-error@1')) % (setname, line[7:])
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            fail = 1

        elif line.startswith('Encrypted file:  CRC failed'):
            filename = TRANS(line[31:-23].strip())
            nzo.fail_msg = T('error-unpackPassword')
            msg = ('[%s][%s] '+Ta('error-unpackPassword')) % (setname, filename)
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            logging.error('%s (%s)', Ta('error-unpackPassword'), filename)
            fail = 1

        else:
            m = re.search(r'^(Extracting|Creating|...)\s+(.*?)\s+OK\s*$', line)
            if m:
                extracted.append(TRANS(m.group(2)))

        if fail:
            if proc:
                proc.close()
            p.wait()

            return ((), ())

    if proc:
        proc.close()
    p.wait()


    if cfg.unpack_check():
        if reliable_unpack_names() and not RAR_PROBLEM:
            all_found = True
            # Loop through and check for the presence of all the files the archive contained
            for path in expected_files:
                path = unicode2local(path)
                fullpath = os.path.join(extraction_path, path)
                logging.debug("Checking existance of %s", fullpath)
                if path.endswith('/'):
                    # Folder
                    continue
                if not os.path.exists(fullpath):
                    # There was a missing file, show a warning
                    all_found = False
                    logging.warning(Ta('warn-MissExpectedFile@1'), path)

            if not all_found:
                nzo.fail_msg = T('error-unpackMissing')
                logging.debug("Expecting files: %s" % expected_files)
                nzo.set_unpack_info('Unpack', T('error-unpackMissing'), set=setname)
                return ((), ())
        else:
            logging.info('Skipping unrar file check due to unreliable file names or old unrar')

    msg = T('msg-unpackDone@2') % (str(len(extracted)), format_time_string(time() - start))
    nzo.set_unpack_info('Unpack', '[%s] %s' % (unicoder(setname), msg), set=setname)
    logging.info('%s', msg)

    return (extracted, rarfiles)

#------------------------------------------------------------------------------
# (Un)Zip Functions
#------------------------------------------------------------------------------

def unzip(nzo, workdir, workdir_complete, delete, zips):
    try:
        i = 0
        unzip_failed = False
        tms = time()

        for _zip in zips:
            logging.info("Starting extract on zipfile: %s ", _zip)
            nzo.set_action_line(T('msg-unpacking'), '%s' % unicoder(_zip))

            if workdir_complete and _zip.startswith(workdir):
                extraction_path = workdir_complete
            else:
                extraction_path = os.path.split(_zip)[0]

            if ZIP_Extract(_zip, extraction_path):
                unzip_failed = True
            else:
                i += 1

        msg = T('msg-unzipDone@2') % (str(i), format_time_string(time() - tms))
        nzo.set_unpack_info('Unpack', msg)

        # Delete the old files if we have to
        if delete and not unzip_failed:
            i = 0

            for _zip in zips:
                logging.info("Deleting %s", _zip)
                try:
                    os.remove(_zip)
                    i += 1
                except OSError:
                    logging.warning(Ta('warn-delFailed@1'), _zip)

                brokenzip = '%s.1' % (_zip)

                if os.path.exists(brokenzip):
                    logging.info("Deleting %s", brokenzip)
                    try:
                        os.remove(brokenzip)
                        i += 1
                    except OSError:
                        logging.warning(Ta('warn-delFailed@1'), brokenzip)

        return unzip_failed
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T('error-unpackFail@1') % msg
        logging.error(Ta('error-fileUnzip@2'), msg, nzo.final_name)
        return True

def ZIP_Extract(zipfile, extraction_path):
    command = ['%s' % ZIP_COMMAND, '-o', '-qq', '-Pnone', '%s' % zipfile,
               '-d%s' % extraction_path]

    stup, need_shell, command, creationflags = build_command(command)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    output = p.stdout.read()

    ret = p.wait()

    return ret

#------------------------------------------------------------------------------
# PAR2 Functions
#------------------------------------------------------------------------------

def par2_repair(parfile_nzf, nzo, workdir, setname):
    """ Try to repair a set, return readd or correctness """
    #set the current nzo status to "Repairing". Used in History

    parfile = os.path.join(workdir, parfile_nzf.filename)

    old_dir_content = os.listdir(workdir)
    used_joinables = joinables = []
    setpars = pars_of_set(workdir, setname)
    result = readd = False

    if cfg.quick_check():
        nzo.status = 'QuickCheck'
        nzo.set_action_line(T('msg-repair'), T('msg-QuickChecking'))
        result = QuickCheck(setname, nzo)
        if result:
            logging.info("Quick-check for %s is OK, skipping repair", setname)
            nzo.set_unpack_info('Repair', T('msg-QuickOK@1') % unicoder(setname), set=setname)
            pars = setpars

    if not result:
        nzo.status = 'Repairing'
        result = False
        readd = False
        try:
            nzo.set_action_line(T('msg-repair'), T('msg-startRepair'))
            logging.info('Scanning "%s"', parfile)

            joinables, zips, rars, ts = build_filelists(workdir, None, check_rar=False)

            finished, readd, pars, datafiles, used_joinables = PAR_Verify(parfile, parfile_nzf, nzo,
                                                                          setname, joinables)

            if finished:
                result = True
                logging.info('Par verify finished ok on %s!',
                             parfile)

                # Remove this set so we don't try to check it again
                nzo.remove_parset(parfile_nzf.setname)
            else:
                logging.info('Par verify failed on %s!', parfile)

                if not readd:
                    # Failed to repair -> remove this set
                    nzo.remove_parset(parfile_nzf.setname)
                return readd, False
        except:
            msg = sys.exc_info()[1]
            nzo.fail_msg = T('error-repairFailed@1') % msg
            logging.error(Ta('error-filePar2@2'), msg, setname)
            logging.debug("Traceback: ", exc_info = True)
            return readd, result

    try:
        if cfg.enable_par_cleanup():
            new_dir_content = os.listdir(workdir)

            for path in new_dir_content:
                if os.path.splitext(path)[1] == '.1' and path not in old_dir_content:
                    try:
                        path = os.path.join(workdir, path)

                        logging.info("Deleting %s", path)
                        os.remove(path)
                    except:
                        logging.warning(Ta('warn-delFailed@1'), path)

            path = os.path.join(workdir, setname + '.par2')
            path2 = os.path.join(workdir, setname + '.PAR2')

            if os.path.exists(path):
                try:
                    logging.info("Deleting %s", path)
                    os.remove(path)
                except:
                    logging.warning(Ta('warn-delFailed@1'), path)

            if os.path.exists(path2):
                try:
                    logging.info("Deleting %s", path2)
                    os.remove(path2)
                except:
                    logging.warning(Ta('warn-delFailed@1'), path2)

            if os.path.exists(parfile):
                try:
                    logging.info("Deleting %s", parfile)
                    os.remove(parfile)
                except OSError:
                    logging.warning(Ta('warn-delFailed@1'), parfile)

            deletables = []
            for f in pars:
                if f in setpars:
                    deletables.append(os.path.join(workdir, f))
            deletables.extend(used_joinables)
            for filepath in deletables:
                if filepath in joinables:
                    joinables.remove(filepath)
                if os.path.exists(filepath):
                    logging.info("Deleting %s", filepath)
                    try:
                        os.remove(filepath)
                    except OSError:
                        logging.warning(Ta('warn-delFailed@1'), filepath)
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T('error-repairFailed@1') % msg
        logging.error(Ta('error-repairBad@2'), msg, setname)

    return readd, result


def PAR_Verify(parfile, parfile_nzf, nzo, setname, joinables, classic=False):

    retry_classic = False
    used_joinables = []
    #set the current nzo status to "Verifying...". Used in History
    nzo.status = 'Verifying'
    start = time()

    classic = classic or not cfg.par2_multicore()
    logging.debug('Par2-classic = %s', classic)

    if (is_new_partype(nzo, setname) and not classic) or not PAR2C_COMMAND:
        if cfg.par_option():
            command = [str(PAR2_COMMAND), 'r', str(cfg.par_option().strip()), parfile]
        else:
            command = [str(PAR2_COMMAND), 'r', parfile]
        classic = not PAR2C_COMMAND
    else:
        command = [str(PAR2C_COMMAND), 'r', parfile]
        classic = True

    for joinable in joinables:
        if setname in joinable:
            command.append(joinable)

    stup, need_shell, command, creationflags = build_command(command)

    try:
        p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             startupinfo=stup, creationflags=creationflags)

        proc = p.stdout

        if p.stdin:
            p.stdin.close()

        # Set up our variables
        pars = []
        datafiles = []

        linebuf = ''
        finished = 0
        readd = False

        verifynum = 1
        verifytotal = 0
        verified = 0

        # Loop over the output, whee
        while 1:
            char = proc.read(1)
            if not char:
                break

            # Line not complete yet
            if char not in ('\n', '\r'):
                linebuf += char
                continue

            line = linebuf.strip()
            linebuf = ''

            # Skip empty lines
            if line == '':
                continue

            # And off we go
            if line.startswith('All files are correct'):
                msg = T('msg-verifyOK@2') % (unicoder(setname), format_time_string(time() - start))
                nzo.set_unpack_info('Repair', msg, set=setname)
                logging.info('Verified in %s, all files correct',
                             format_time_string(time() - start))
                finished = 1

            elif line.startswith('Repair is required'):
                msg = T('msg-repairNeeded@2') % (unicoder(setname), format_time_string(time() - start))
                nzo.set_unpack_info('Repair', msg, set=setname)
                logging.info('Verified in %s, repair is required',
                              format_time_string(time() - start))
                start = time()
                verified = 1

            elif line.startswith('Main packet not found'):
                ## Initialparfile probaly didn't decode properly,
                logging.info(Ta('error-noMainPacket'))

                extrapars = parfile_nzf.extrapars

                logging.info("%s", extrapars)

                ## Look for the smallest par2file
                block_table = {}
                for nzf in extrapars:
                    block_table[int(nzf.blocks)] = nzf

                if block_table:
                    nzf = block_table[min(block_table.keys())]

                    logging.info("Found new par2file %s", nzf.filename)

                    nzo.add_parfile(nzf)
                    ## mark for readd
                    readd = True

            elif line.startswith('You need'):
                chunks = line.split()

                needed_blocks = int(chunks[2])

                logging.info('Need to fetch %s more blocks, checking blocks', needed_blocks)

                avail_blocks = 0

                extrapars = parfile_nzf.extrapars

                block_table = {}

                for nzf in extrapars:
                    # Don't count extrapars that are completed already
                    if nzf.completed:
                        continue

                    blocks = int(nzf.blocks)

                    avail_blocks += blocks

                    if blocks not in block_table:
                        block_table[blocks] = []

                    block_table[blocks].append(nzf)

                logging.info('%s blocks available', avail_blocks)


                force = False
                if (avail_blocks < needed_blocks) and (avail_blocks > 0):
                    # Tell SAB that we always have enough blocks, so that
                    # it will try to load all pars anyway
                    msg = T('error-repairBlocks@1') % str(int(needed_blocks - avail_blocks))
                    nzo.fail_msg = msg
                    msg = u'[%s] %s' % (unicoder(setname), msg)
                    nzo.set_unpack_info('Repair', msg, set=setname)
                    nzo.status = 'Failed'
                    needed_blocks = avail_blocks
                    force = True

                if avail_blocks >= needed_blocks:
                    added_blocks = 0
                    readd = True

                    while added_blocks < needed_blocks:
                        block_size = min(block_table.keys())
                        extrapar_list = block_table[block_size]

                        if extrapar_list:
                            nzo.add_parfile(extrapar_list.pop())
                            added_blocks += block_size

                        else:
                            block_table.pop(block_size)

                    logging.info('Added %s blocks to %s',
                                 added_blocks, nzo.final_name)

                    if not force:
                        msg = T('msg-fetchBlocks@1') % str(added_blocks)
                        nzo.status = 'Fetching'
                        nzo.set_action_line(T('msg-fetching'), msg)

                else:
                    msg = T('error-repairBlocks@1') % str(needed_blocks)
                    nzo.fail_msg = msg
                    msg = u'[%s] %s' % (unicoder(setname), msg)
                    nzo.set_unpack_info('Repair', msg, set=setname)
                    nzo.status = 'Failed'


            elif line.startswith('Repair is possible'):
                start = time()
                nzo.set_action_line(T('msg-repairing'), '%2d%%' % (0))

            elif line.startswith('Repairing:'):
                chunks = line.split()
                per = float(chunks[-1][:-1])
                nzo.set_action_line(T('msg-repairing'), '%2d%%' % (per))
                nzo.status = 'Repairing'

            elif line.startswith('Repair complete'):
                msg = T('msg-repairDone@2') % (unicoder(setname), format_time_string(time() - start))
                nzo.set_unpack_info('Repair', msg, set=setname)
                logging.info('Repaired in %s', format_time_string(time() - start))
                finished = 1

            elif line.startswith('File:') and line.find('data blocks from') > 0:
                # Find out if a joinable file has been used for joining
                for jn in joinables:
                    if line.find(os.path.split(jn)[1]) > 0:
                        used_joinables.append(jn)
                        break

            elif 'Could not write' in line and 'at offset 0:' in line and not classic:
                # Hit a bug in par2-tbb, retry with par2-classic
                retry_classic = True

            elif not verified:
                if line.startswith('Verifying source files'):
                    nzo.set_action_line(T('msg-verifying'), '01/%02d' % verifytotal)
                    nzo.status = 'Verifying'

                elif line.startswith('Scanning:'):
                    pass

                else:
                    # Loading parity files
                    m = LOADING_RE.match(line)
                    if m:
                        pars.append(m.group(1))
                        continue

                # Target files
                m = TARGET_RE.match(line)
                if m:
                    if verifytotal == 0 or verifynum < verifytotal:
                        verifynum += 1
                        nzo.set_action_line(T('msg-verifying'), '%02d/%02d' % (verifynum, verifytotal))
                        nzo.status = 'Verifying'
                    datafiles.append(m.group(1))
                    continue

                # Verify done
                m = re.match(r'There are (\d+) recoverable files', line)
                if m:
                    verifytotal = int(m.group(1))

        p.wait()
    except WindowsError, err:
        if err[0] == '87' and not classic:
            # Hit a bug in par2-tbb, retry with par2-classic
            retry_classic = True
        else:
            raise WindowsError(err)

    if retry_classic:
        logging.debug('Retry PAR2-joining with par2-classic')
        return PAR_Verify(parfile, parfile_nzf, nzo, setname, joinables, classic=True)
    else:
        return (finished, readd, pars, datafiles, used_joinables)

#-------------------------------------------------------------------------------

def fix_env():
    """ OSX: Return copy of environment without PYTHONPATH and PYTHONHOME
        other: return None
    """
    if sabnzbd.DARWIN:
        env = os.environ.copy()
        if 'PYTHONPATH' in env: del env['PYTHONPATH']
        if 'PYTHONHOME' in env: del env['PYTHONHOME']
        return env
    else:
        return None


def build_command(command):
    if not sabnzbd.WIN32:
        if IONICE_COMMAND and cfg.ionice().strip():
            lst = cfg.ionice().split()
            lst.reverse()
            for arg in lst:
                command.insert(0, arg)
            command.insert(0, IONICE_COMMAND)
        if NICE_COMMAND and cfg.nice().strip():
            lst = cfg.nice().split()
            lst.reverse()
            for arg in lst:
                command.insert(0, arg)
            command.insert(0, NICE_COMMAND)
        need_shell = False
        stup = None
        creationflags = 0

    else:
        need_shell = os.path.splitext(command[0])[1].lower() not in ('.exe', '.com')
        stup = subprocess.STARTUPINFO()
        stup.dwFlags = STARTF_USESHOWWINDOW
        stup.wShowWindow = SW_HIDE
        creationflags = IDLE_PRIORITY_CLASS

        # Work-around for bug in Python's Popen function,
        # scripts with spaces in the path don't work.
        if need_shell and ' ' in command[0]:
            command[0] = win32api.GetShortPathName(command[0])
        if need_shell:
            command = list2cmdline(command)

    return (stup, need_shell, command, creationflags)

# Sort the various RAR filename formats properly :\
def rar_sort(a, b):
    aext = a.split('.')[-1]
    bext = b.split('.')[-1]

    if aext == 'rar' and bext == 'rar':
        return cmp(a, b)
    elif aext == 'rar':
        return -1
    elif bext == 'rar':
        return 1
    else:
        return cmp(a, b)

# Sort the various PAR filename formats properly :\
def par_sort(a, b):
    aext = a.lower().split('.')[-1]
    bext = b.lower().split('.')[-1]

    if aext == bext:
        return cmp(a, b)
    elif aext == 'par2':
        return -1
    elif bext == 'par2':
        return 1


def build_filelists(workdir, workdir_complete, check_rar=True):
    """ Build filelists, if workdir_complete has files, ignore workdir.
        Optionally test content to establish RAR-ness
    """
    joinables, zips, rars, filelist = ([], [], [], [])

    if workdir_complete:
        for root, dirs, files in os.walk(workdir_complete):
            for _file in files:
                filelist.append(os.path.join(root, _file))

    if workdir and not filelist:
        for root, dirs, files in os.walk(workdir):
            for _file in files:
                filelist.append(os.path.join(root, _file))

    if check_rar:
        joinables = [f for f in filelist if SPLITFILE_RE.search(f) and not is_rarfile(f)]
    else:
        joinables = [f for f in filelist if SPLITFILE_RE.search(f)]

    zips = [f for f in filelist if ZIP_RE.search(f)]

    rars = [f for f in filelist if RAR_RE.search(f) and is_rarfile(f)]

    ts = [f for f in filelist if TS_RE.search(f) and f not in joinables]

    logging.debug("build_filelists(): joinables: %s", joinables)
    logging.debug("build_filelists(): zips: %s", zips)
    logging.debug("build_filelists(): rars: %s", rars)
    logging.debug("build_filelists(): ts: %s", ts)

    return (joinables, zips, rars, ts)


def QuickCheck(set, nzo):
    """ Check all on-the-fly md5sums of a set """

    md5pack = nzo.md5packs.get(set)
    if md5pack is None:
        return False

    result = False
    nzf_list = nzo.finished_files
    for file in md5pack:
        file = name_fixer(file)
        if sabnzbd.misc.on_cleanup_list(file, False):
            result = True
            continue
        found = False
        for nzf in nzf_list:
            if file == name_fixer(nzf.filename):
                found = True
                if nzf.md5sum == md5pack[file]:
                    logging.debug('Quick-check of file %s OK', file)
                    result = True
                else:
                    logging.debug('Quick-check of file %s failed!', file)
                    return False # When any file fails, just stop
                break
        if not found:
            logging.debug('Cannot Quick-check missing file %s!', file)
            return False # Missing file is failure
    return result


def pars_of_set(wdir, setname):
    """ Return list of par2 files (pathless) matching the set """
    list = []
    for file in os.listdir(wdir):
        m = FULLVOLPAR2_RE.search(file)
        if m and m.group(1) == setname and m.group(2):
            list.append(file)
    return list


def is_new_partype(nzo, setname):
    """ Determine the PAR2 program type, based on the filename encoding """
    pack = nzo.md5packs.get(setname)
    if not pack:
        return True
    for name in pack.keys():
        try:
            name.decode('utf-8')
        except UnicodeDecodeError:
            # Now we know it's not pure ASCII or UTF-8
            return False
    return True


def add_s(i):
    if i > 1:
        return 's'
    else:
        return ''


def unrar_check(rar):
    """ Return True if correct version of unrar is found """
    if rar:
        try:
            version = subprocess.Popen(rar, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).stdout.read()
        except:
            return False
        m = re.search("RAR\s(\d+)\.(\d+)\s+.*Alexander Roshal", version)
        if m:
            return (int(m.group(1)), int(m.group(2))) >= (3, 80)
    return False


#-------------------------------------------------------------------------------
def sfv_check(sfv_path):
    """ Verify files using SFV file,
        input: full path of sfv, file are assumed to be relative to sfv
        returns: True when all files verified OK
    """
    try:
        fp = open(sfv_path, 'r')
    except:
        logging.info('Cannot open SFV file %s', sfv_path)
        return False
    root = os.path.split(sfv_path)[0]
    status = True
    for line in fp:
        line = line.strip('\n\r ')
        if line[0] != ';':
            x = line.rfind(' ')
            filename = line[:x].strip()
            checksum = line[x:].strip()
            path = os.path.join(root, filename)
            if os.path.exists(path):
                if crc_check(path, checksum):
                    logging.debug('File %s passed SFV check', path)
                else:
                    logging.warning('File %s did not pass SFV check', path)
                    status = False
            else:
                logging.warning('File %s mssing in SFV check', path)
    fp.close()
    return status


def crc_check(path, target_crc):
    """ Return True if file matches CRC """
    try:
        fp = open(path, 'rb')
    except:
        return False
    crc = binascii.crc32('')
    while 1:
        data = fp.read(4096)
        if not data:
            break
        crc = binascii.crc32(data, crc)
    fp.close()
    crc = '%08x' % (crc & 0xffffffff,)
    return crc.lower() == target_crc.lower()


#-------------------------------------------------------------------------------

def analyse_show(name):
    """ Do a quick SeasonSort check and return basic facts """
    job = SeriesSorter(name, None, None, force=True)
    if job.is_match():
        job.get_values()
    info = job.show_info
    return info.get('show_name', ''), \
           info.get('season_num', ''), \
           info.get('episode_num', ''), \
           info.get('ep_name', '')


def pre_queue(name, pp, cat, script, priority, size, groups):
    """ Run pre-queue script (if any) and process results
    """
    def fix(p):
        if not p or str(p).lower() == 'none':
            return ''
        else:
            return UNTRANS(str(p))

    values = [1, name, pp, cat, script, priority, None]
    script_path = make_script_path(cfg.pre_script())
    if script_path:
        name = os.path.splitext(name)[0]
        command = [script_path, name, fix(pp), fix(cat), fix(script), fix(priority), str(size), ' '.join(groups)]
        command.extend(analyse_show(name))

        stup, need_shell, command, creationflags = build_command(command)
        env = fix_env()

        logging.info('Running pre-queue script %s(' + '%s, '*(len(command)-1) + ')', *command)

        try:
            p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                startupinfo=stup, env=env, creationflags=creationflags)
        except:
            logging.debug("Failed script %s, Traceback: ", pre_script, exc_info = True)
            return values

        output = p.stdout.read()
        ret = p.wait()
        if ret == 0:
            n = 0
            for line in output.split('\n'):
                line = line.strip('\r\n \'"')
                if n < len(values) and line:
                    try:
                        values[n] = int(line)
                    except:
                        values[n] = TRANS(line)
                n += 1
        if values[0]:
            logging.info('Pre-Q accepts %s', name)
        else:
            logging.info('Pre-Q refuses %s', name)

    return values


#------------------------------------------------------------------------------
def list2cmdline(lst):
    """ convert list to a cmd.exe-compatible command string """
    nlst = []
    for arg in lst:
        if (' ' in arg) or ('\t' in arg) or ('&' in arg) or ('|' in arg):
            nlst.append('"%s"' % arg)
        else:
            nlst.append(arg)
    return ' '.join(nlst)
