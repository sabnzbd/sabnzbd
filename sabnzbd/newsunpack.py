#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
import shutil

import sabnzbd
from sabnzbd.encoding import TRANS, UNTRANS, unicode2local, name_fixer, \
    reliable_unpack_names, unicoder, platform_encode, deunicode
from sabnzbd.utils.rarfile import RarFile, is_rarfile
from sabnzbd.misc import format_time_string, find_on_path, make_script_path, int_conv, \
    flag_file, real_path, globber, globber_full, short_path
from sabnzbd.tvsort import SeriesSorter
import sabnzbd.cfg as cfg
from sabnzbd.constants import Status, QCHECK_FILE, RENAMES_FILE
load_data = save_data = None

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
RAR_RE = re.compile(r'\.(?P<ext>part\d*\.rar|rar|r\d\d|s\d\d|t\d\d|u\d\d|v\d\d|\d\d\d)$', re.I)
RAR_RE_V3 = re.compile(r'\.(?P<ext>part\d*)$', re.I)

LOADING_RE = re.compile(r'^Loading "(.+)"')
TARGET_RE = re.compile(r'^(?:File|Target): "(.+)" -')
EXTRACTFROM_RE = re.compile(r'^Extracting\sfrom\s(.+)')
SPLITFILE_RE = re.compile(r'\.(\d\d\d$)', re.I)
ZIP_RE = re.compile(r'\.(zip$)', re.I)
SEVENZIP_RE = re.compile(r'\.7z$', re.I)
SEVENMULTI_RE = re.compile(r'\.7z\.\d+$', re.I)
VOLPAR2_RE = re.compile(r'\.*vol[0-9]+\+[0-9]+\.par2', re.I)
FULLVOLPAR2_RE = re.compile(r'(.*[^.])(\.*vol[0-9]+\+[0-9]+\.par2)', re.I)
TS_RE = re.compile(r'\.(\d+)\.(ts$)', re.I)

PAR2_COMMAND = None
PAR2C_COMMAND = None
RAR_COMMAND = None
NICE_COMMAND = None
ZIP_COMMAND = None
SEVEN_COMMAND = None
IONICE_COMMAND = None
RAR_PROBLEM = False
RAR_VERSION = 0


def find_programs(curdir):
    """ Find external programs """
    global load_data, save_data

    def check(path, program):
        p = os.path.abspath(os.path.join(path, program))
        if os.access(p, os.X_OK):
            return p
        else:
            return None

    # Another crazy Python import bug work-around
    load_data = sabnzbd.load_data
    save_data = sabnzbd.save_data

    if sabnzbd.DARWIN:
        sabnzbd.newsunpack.PAR2C_COMMAND = check(curdir, 'osx/par2/par2-classic')
        if sabnzbd.DARWIN_VERSION >= 6:
            # par2-sl from Macpar Deluxe 4.1 is only 10.6 and later
            if sabnzbd.DARWIN_64:
                sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, 'osx/par2/par2-sl64')
            else:
                sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, 'osx/par2/par2-sl')
        else:
            sabnzbd.newsunpack.PAR2_COMMAND = sabnzbd.newsunpack.PAR2C_COMMAND

        if sabnzbd.DARWIN_INTEL:
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, 'osx/unrar/unrar')
            sabnzbd.newsunpack.SEVEN_COMMAND = check(curdir, 'osx/7zip/7za')
        else:
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, 'osx/unrar/unrar-ppc')

    if sabnzbd.WIN32:
        if sabnzbd.WIN64 and cfg.allow_64bit_tools.get():
            sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, 'win/par2/x64/par2.exe')
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, 'win/unrar/x64/UnRAR.exe')
        if not sabnzbd.newsunpack.PAR2_COMMAND:
            sabnzbd.newsunpack.PAR2_COMMAND = check(curdir, 'win/par2/par2.exe')
        if not sabnzbd.newsunpack.RAR_COMMAND:
            sabnzbd.newsunpack.RAR_COMMAND = check(curdir, 'win/unrar/UnRAR.exe')
        sabnzbd.newsunpack.PAR2C_COMMAND = check(curdir, 'win/par2/par2-classic.exe')
        sabnzbd.newsunpack.ZIP_COMMAND = check(curdir, 'win/unzip/unzip.exe')
        sabnzbd.newsunpack.SEVEN_COMMAND = check(curdir, 'win/7zip/7za.exe')
    else:
        if not sabnzbd.newsunpack.PAR2_COMMAND:
            sabnzbd.newsunpack.PAR2_COMMAND = find_on_path('par2')
        if not sabnzbd.newsunpack.RAR_COMMAND:
            sabnzbd.newsunpack.RAR_COMMAND = find_on_path(('unrar', 'rar', 'unrar3', 'rar3',))
        sabnzbd.newsunpack.NICE_COMMAND = find_on_path('nice')
        sabnzbd.newsunpack.IONICE_COMMAND = find_on_path('ionice')
        if not sabnzbd.newsunpack.ZIP_COMMAND:
            sabnzbd.newsunpack.ZIP_COMMAND = find_on_path('unzip')
        if not sabnzbd.newsunpack.SEVEN_COMMAND:
            sabnzbd.newsunpack.SEVEN_COMMAND = find_on_path('7za')
        if not sabnzbd.newsunpack.SEVEN_COMMAND:
            sabnzbd.newsunpack.SEVEN_COMMAND = find_on_path('7z')

    if not sabnzbd.newsunpack.PAR2C_COMMAND:
        sabnzbd.newsunpack.PAR2C_COMMAND = sabnzbd.newsunpack.PAR2_COMMAND

    if not (sabnzbd.WIN32 or sabnzbd.DARWIN):
        version, original = unrar_check(sabnzbd.newsunpack.RAR_COMMAND)
        sabnzbd.newsunpack.RAR_PROBLEM = not original or version < 380
        sabnzbd.newsunpack.RAR_VERSION = version
        logging.info('UNRAR version %s', version)
        if sabnzbd.newsunpack.RAR_PROBLEM:
            logging.info('Problematic UNRAR')


def external_processing(extern_proc, complete_dir, filename, nicename, cat, group, status, failure_url):
    """ Run a user postproc script, return console output and exit value """
    command = [str(extern_proc), str(complete_dir), str(filename),
               str(nicename), '', str(cat), str(group), str(status)]

    if failure_url:
        command.extend(str(failure_url))

    if extern_proc.endswith('.py') and (sabnzbd.WIN32 or not os.access(extern_proc, os.X_OK)):
        command.insert(0, 'python')
    stup, need_shell, command, creationflags = build_command(command)
    env = fix_env()

    logging.info('Running external script %s(%s, %s, %s, %s, %s, %s, %s, %s)',
                 extern_proc, complete_dir, filename, nicename, '', cat, group, status, failure_url)

    try:
        p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            startupinfo=stup, env=env, creationflags=creationflags)
    except:
        logging.debug("Failed script %s, Traceback: ", extern_proc, exc_info=True)
        return "Cannot run script %s\r\n" % extern_proc, -1

    output = p.stdout.read()
    ret = p.wait()
    return output, ret


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


def unpack_magic(nzo, workdir, workdir_complete, dele, one_folder, joinables, zips, rars, sevens, ts, depth=0):
    """ Do a recursive unpack from all archives in 'workdir' to 'workdir_complete' """
    if depth > 5:
        logging.warning(T('Unpack nesting too deep [%s]'), nzo.final_name)
        return False, []
    depth += 1

    if depth == 1:
        # First time, ignore anything in workdir_complete
        xjoinables, xzips, xrars, xsevens, xts = build_filelists(workdir, None)
    else:
        xjoinables, xzips, xrars, xsevens, xts = build_filelists(workdir, workdir_complete)

    rerun = False
    newfiles = []
    error = 0
    new_joins = new_rars = new_zips = new_ts = None

    if cfg.enable_filejoin():
        new_joins = [jn for jn in xjoinables if jn not in joinables]
        if new_joins:
            logging.info('Filejoin starting on %s', workdir)
            error, newf = file_join(nzo, workdir, workdir_complete, dele, new_joins)
            if newf:
                newfiles.extend(newf)
            logging.info('Filejoin finished on %s', workdir)
            nzo.set_action_line()
            rerun = not error

    if cfg.enable_unrar():
        new_rars = [rar for rar in xrars if rar not in rars]
        if new_rars:
            logging.info('Unrar starting on %s', workdir)
            error, newf = rar_unpack(nzo, workdir, workdir_complete, dele, one_folder, new_rars)
            if newf:
                newfiles.extend(newf)
            logging.info('Unrar finished on %s', workdir)
            nzo.set_action_line()
            rerun = not error

    if cfg.enable_unzip():
        new_zips = [zip for zip in xzips if zip not in zips]
        if new_zips:
            logging.info('Unzip starting on %s', workdir)
            if unzip(nzo, workdir, workdir_complete, dele, one_folder, new_zips):
                error = 1
            logging.info('Unzip finished on %s', workdir)
            nzo.set_action_line()
            rerun = not error

    if cfg.enable_7zip():
        new_sevens = [seven for seven in xsevens if seven not in sevens]
        if new_sevens:
            logging.info('7za starting on %s', workdir)
            if unseven(nzo, workdir, workdir_complete, dele, one_folder, new_sevens):
                error = True
            logging.info('7za finished on %s', workdir)
            nzo.set_action_line()
            rerun = not error

    if cfg.enable_tsjoin():
        new_ts = [_ts for _ts in xts if _ts not in ts]
        if new_ts:
            logging.info('TS Joining starting on %s', workdir)
            error, newf = file_join(nzo, workdir, workdir_complete, dele, new_ts)
            if newf:
                newfiles.extend(newf)
            logging.info('TS Joining finished on %s', workdir)
            nzo.set_action_line()
            rerun = not error

    if rerun and (cfg.enable_recursive() or new_ts or new_joins):
        z, y = unpack_magic(nzo, workdir, workdir_complete, dele, one_folder,
                            xjoinables, xzips, xrars, xsevens, xts, depth)
        if z:
            error = z
        if y:
            newfiles.extend(y)

    return error, newfiles


##############################################################################
# Filejoin Functions
##############################################################################
def match_ts(file):
    """ Return True if file is a joinable TS file """
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


def clean_up_joinables(names):
    """ Remove joinable files and their .1 backups """
    for name in names:
        if os.path.exists(name):
            logging.debug("Deleting %s", name)
            try:
                os.remove(name)
            except:
                pass
        name1 = name + ".1"
        if os.path.exists(name1):
            logging.debug("Deleting %s", name1)
            try:
                os.remove(name1)
            except:
                pass


def get_seq_number(name):
    """ Return sequence number if name as an int """
    head, tail = os.path.splitext(name)
    if tail == '.ts':
        match, set, num = match_ts(name)
    else:
        num = tail[1:]
    if num.isdigit():
        return int(num)
    else:
        return 0


def file_join(nzo, workdir, workdir_complete, delete, joinables):
    """ Join and joinable files in 'workdir' to 'workdir_complete' and
        when successful, delete originals
    """
    newfiles = []
    bufsize = 24 * 1024 * 1024

    # Create matching sets from the list of files
    joinable_sets = {}
    joinable_set = None
    for joinable in joinables:
        head, tail = os.path.splitext(joinable)
        if tail == '.ts':
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
            joined_file = open(filename, 'ab')

            # Join the segments
            n = get_seq_number(current[0])
            seq_error = n > 1
            for joinable in current:
                if get_seq_number(joinable) != n:
                    seq_error = True
                perc = (100.0 / size) * n
                logging.debug("Processing %s", joinable)
                nzo.set_action_line(T('Joining'), '%.0f%%' % perc)
                f = open(joinable, 'rb')
                shutil.copyfileobj(f, joined_file, bufsize)
                f.close()
                if delete:
                    logging.debug("Deleting %s", joinable)
                    os.remove(joinable)
                n += 1

            # Remove any remaining .1 files
            clean_up_joinables(current)

            # Finish up
            joined_file.flush()
            joined_file.close()
            newfiles.append(filename)

            if seq_error:
                msg = T('Incomplete sequence of joinable files')
                nzo.fail_msg = T('File join of %s failed') % unicoder(joinable_set)
                nzo.set_unpack_info('Filejoin', T('[%s] Error "%s" while joining files') % (unicoder(joinable_set), msg))
                logging.error(T('Error "%s" while running file_join on %s'), msg, nzo.final_name)
            else:
                msg = T('[%s] Joined %s files') % (unicoder(joinable_set), size)
                nzo.set_unpack_info('Filejoin', msg, set=joinable_set)
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T('File join of %s failed') % msg
        nzo.set_unpack_info('Filejoin', T('[%s] Error "%s" while joining files') % (unicoder(joinable_set), msg))
        logging.error(T('Error "%s" while running file_join on %s'), msg, nzo.final_name)
        return True, []

    return False, newfiles


##############################################################################
# (Un)Rar Functions
##############################################################################
def rar_unpack(nzo, workdir, workdir_complete, delete, one_folder, rars):
    """ Unpack multiple sets 'rars' of RAR files from 'workdir' to 'workdir_complete.
        When 'delete' is set, originals will be deleted.
        When 'one_folder' is set, all files will be in a single folder
    """
    extracted_files = []
    success = False

    rar_sets = {}
    for rar in rars:
        rar_set = os.path.splitext(os.path.basename(rar))[0]
        if RAR_RE_V3.search(rar_set):
            rar_set = os.path.splitext(rar_set)[0]
        if rar_set not in rar_sets:
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
            fail, newfiles, rars = rar_extract(rarpath, len(rar_sets[rar_set]),
                                         one_folder, nzo, rar_set, extraction_path)
            success = not fail
        except:
            success = False
            fail = True
            msg = sys.exc_info()[1]
            nzo.set_fail = T('Unpacking failed, %s') % msg
            setname = nzo.final_name
            nzo.set_unpack_info('Unpack', T('[%s] Error "%s" while unpacking RAR files') % (unicoder(setname), msg))

            logging.error(T('Error "%s" while running rar_unpack on %s'), msg, setname)
            logging.debug("Traceback: ", exc_info=True)

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
                    logging.warning(T('Deleting %s failed!'), rar)

                brokenrar = '%s.1' % rar

                if os.path.exists(brokenrar):
                    logging.info("Deleting %s", brokenrar)
                    try:
                        os.remove(brokenrar)
                    except OSError:
                        logging.warning(T('Deleting %s failed!'), brokenrar)

    return fail, extracted_files


def rar_extract(rarfile, numrars, one_folder, nzo, setname, extraction_path):
    """ Unpack single rar set 'rarfile' to 'extraction_path',
        with password tries
        Return fail==0(ok)/fail==1(error)/fail==2(wrong password), new_files, rars
    """

    fail = 0
    new_files = None
    rars = []
    if nzo.password:
        logging.info('Got a password set by user: %s', nzo.password)
        passwords = [nzo.password.strip()]
    else:
        passwords = []
        # Append meta passwords, to prevent changing the original list
        passwords.extend(nzo.meta.get('password', []))
        if passwords:
            logging.info('Read %s passwords from meta data in NZB', len(passwords))
        pw_file = cfg.password_file.get_path()
        if pw_file:
            try:
                pwf = open(pw_file, 'r')
                lines = pwf.read().split('\n')
                # Remove empty lines and space-only passwords and remove surrounding spaces
                pws = [pw.strip('\r\n ') for pw in lines if pw.strip('\r\n ')]
                logging.debug('Read these passwords from file: %s', pws)
                passwords.extend(pws)
                pwf.close()
                logging.info('Read %s passwords from file %s', len(pws), pw_file)
            except IOError:
                logging.info('Failed to read the passwords file %s', pw_file)

    if nzo.password:
        # If an explicit password was set, add a retry without password, just in case.
        passwords.append('')
    elif not passwords or not nzo.encrypted:
        # If we're not sure about encryption, start with empty password
        # and make sure we have at least the empty password
        passwords.insert(0, '')

    for password in passwords:
        if password:
            logging.debug('Trying unrar with password "%s"', password)
            msg = T('Trying unrar with password "%s"') % unicoder(password)
            nzo.fail_msg = msg
            nzo.set_unpack_info('Unpack', msg)
        fail, new_files, rars = rar_extract_core(rarfile, numrars, one_folder, nzo, setname, extraction_path, password)
        if fail != 2:
            break

    if fail == 2:
        logging.error('%s (%s)', T('Unpacking failed, archive requires a password'), os.path.split(rarfile)[1])
    return fail, new_files, rars


def rar_extract_core(rarfile, numrars, one_folder, nzo, setname, extraction_path, password):
    """ Unpack single rar set 'rarfile' to 'extraction_path'
        Return fail==0(ok)/fail==1(error)/fail==2(wrong password)/fail==3(crc-error), new_files, rars
    """
    start = time()

    logging.debug("rar_extract(): Extractionpath: %s", extraction_path)

    try:
        zf = RarFile(rarfile)
        expected_files = zf.unamelist()
        zf.close()
    except:
        logging.info('Archive %s probably has full encryption', rarfile)
        expected_files = []

    if password:
        password = '-p%s' % password
    else:
        password = '-p-'

    ############################################################################

    if one_folder or cfg.flat_unpack():
        action = 'e'
    else:
        action = 'x'
    if cfg.overwrite_files():
        overwrite = '-o+'  # Enable overwrite
        rename = '-o+'    # Dummy
    else:
        overwrite = '-o-'  # Disable overwrite
        rename = '-or'    # Auto renaming
    if sabnzbd.WIN32:
        # Use all flags
        command = ['%s' % RAR_COMMAND, action, '-idp', overwrite, rename, '-ai', password,
                   '%s' % rarfile, '%s/' % extraction_path]
    elif RAR_PROBLEM:
        # Use only oldest options (specifically no "-or")
        command = ['%s' % RAR_COMMAND, action, '-idp', overwrite, password,
                   '%s' % rarfile, '%s/' % extraction_path]
    else:
        # Don't use "-ai" (not needed for non-Windows)
        command = ['%s' % RAR_COMMAND, action, '-idp', overwrite, rename, password,
                   '%s' % rarfile, '%s/' % extraction_path]

    if cfg.ignore_unrar_dates():
        command.insert(3, '-tsm-')

    stup, need_shell, command, creationflags = build_command(command)

    logging.debug("Running unrar %s", command)
    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    proc = p.stdout
    if p.stdin:
        p.stdin.close()

    nzo.set_action_line(T('Unpacking'), '00/%02d' % numrars)

    # Loop over the output from rar!
    curr = 0
    extracted = []
    rarfiles = []
    fail = 0
    inrecovery = False

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
            nzo.set_action_line(T('Unpacking'), '%02d/%02d' % (curr, numrars))

        elif line.find('recovery volumes found') > -1:
            inrecovery = True  # and thus start ignoring "Cannot find volume" for a while
            logging.debug("unrar recovery start: %s" % line)
        elif line.startswith('Reconstruct'):
            # end of reconstruction: 'Reconstructing... 100%' or 'Reconstructing... ' (both success), or 'Reconstruction impossible'
            inrecovery = False
            logging.debug("unrar recovery result: %s" % line)

        elif line.startswith('Cannot find volume') and not inrecovery:
            filename = os.path.basename(TRANS(line[19:]))
            nzo.fail_msg = T('Unpacking failed, unable to find %s') % unicoder(filename)
            msg = (u'[%s] ' + T('Unpacking failed, unable to find %s')) % (setname, filename)
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            logging.warning(T('ERROR: unable to find "%s"'), filename)
            fail = 1

        elif line.endswith('- CRC failed'):
            filename = TRANS(line[:-12].strip())
            nzo.fail_msg = T('Unpacking failed, CRC error')
            msg = (u'[%s] ' + T('ERROR: CRC failed in "%s"')) % (setname, filename)
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            logging.warning(T('ERROR: CRC failed in "%s"'), setname)
            fail = 2  # Older unrar versions report a wrong password as a CRC error

        elif line.startswith('Write error'):
            nzo.fail_msg = T('Unpacking failed, write error or disk is full?')
            msg = (u'[%s] ' + T('Unpacking failed, write error or disk is full?')) % setname
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            logging.error(T('ERROR: write error (%s)'), line[11:])
            fail = 1

        elif line.startswith('Cannot create'):
            line2 = proc.readline()
            if 'must not exceed 260' in line2:
                nzo.fail_msg = T('Unpacking failed, path is too long')
                msg = u'[%s] %s: %s' % (T('Unpacking failed, path is too long'), setname, unicoder(line[13:]))
                logging.error(T('ERROR: path too long (%s)'), unicoder(line[13:]))
            else:
                nzo.fail_msg = T('Unpacking failed, write error or disk is full?')
                msg = u'[%s] %s: %s' % (T('Unpacking failed, write error or disk is full?'), setname, unicoder(line[13:]))
                logging.error(T('ERROR: write error (%s)'), unicoder(line[13:]))
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            fail = 1

        elif line.startswith('ERROR: '):
            nzo.fail_msg = T('Unpacking failed, see log')
            logging.warning(T('ERROR: %s'), (unicoder(line[7:])))
            msg = (u'[%s] ' + T('ERROR: %s')) % (setname, line[7:])
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            fail = 1

        elif 'The specified password is incorrect' in line or \
             ('ncrypted file' in line and (('CRC failed' in line) or ('Checksum error' in line))):
            # unrar 3.x: "Encrypted file: CRC failed in oLKQfrcNVivzdzSG22a2xo7t001.part1.rar (password incorrect ?)"
            # unrar 4.x: "CRC failed in the encrypted file oLKQfrcNVivzdzSG22a2xo7t001.part1.rar. Corrupt file or wrong password."
            # unrar 5.x: "Checksum error in the encrypted file oLKQfrcNVivzdzSG22a2xo7t001.part1.rar. Corrupt file or wrong password."
            # unrar 5.01 : "The specified password is incorrect."
            m = re.search('encrypted file (.+)\. Corrupt file', line)
            if not m:
                # unrar 3.x syntax
                m = re.search(r'Encrypted file:  CRC failed in (.+) \(password', line)
            if m:
                filename = TRANS(m.group(1)).strip()
            else:
                filename = os.path.split(rarfile)[1]
            nzo.fail_msg = T('Unpacking failed, archive requires a password')
            msg = (u'[%s][%s] ' + T('Unpacking failed, archive requires a password')) % (setname, filename)
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            fail = 2

        elif 'is not RAR archive' in line:
            # Unrecognizable RAR file
            m = re.search('(.+) is not RAR archive', line)
            if m:
                filename = TRANS(m.group(1)).strip()
            else:
                filename = '???'
            nzo.fail_msg = T('Unusable RAR file')
            msg = ('[%s][%s] ' + T('Unusable RAR file')) % (setname, filename)
            nzo.set_unpack_info('Unpack', unicoder(msg), set=setname)
            fail = 3

        else:
            m = re.search(r'^(Extracting|Creating|...)\s+(.*?)\s+OK\s*$', line)
            if m:
                extracted.append(real_path(extraction_path, TRANS(m.group(2))))

        if fail:
            if proc:
                proc.close()
            p.wait()

            return fail, (), ()

    if proc:
        proc.close()
    p.wait()

    if cfg.unpack_check():
        if reliable_unpack_names() and not RAR_PROBLEM:
            missing = []
            # Loop through and check for the presence of all the files the archive contained
            for path in expected_files:
                if one_folder or cfg.flat_unpack():
                    path = os.path.split(path)[1]
                path = unicode2local(path)
                if '?' in path:
                    logging.info('Skipping check of file %s', path)
                    continue
                fullpath = os.path.join(extraction_path, path)
                logging.debug("Checking existence of %s", fullpath)
                if path.endswith('/'):
                    # Folder
                    continue
                if not os.path.exists(fullpath):
                    # There was a missing file, show a warning
                    missing.append(path)
                    logging.info(T('Missing expected file: %s => unrar error?'), path)

            if missing:
                nzo.fail_msg = T('Unpacking failed, an expected file was not unpacked')
                logging.debug("Expecting files: %s" % str(expected_files))
                msg = T('Unpacking failed, these file(s) are missing:') + ';' + u';'.join([unicoder(item) for item in missing])
                nzo.set_unpack_info('Unpack', msg, set=setname)
                return (1, (), ())
        else:
            logging.info('Skipping unrar file check due to unreliable file names or old unrar')

    nzo.fail_msg = ''
    msg = T('Unpacked %s files/folders in %s') % (str(len(extracted)), format_time_string(time() - start))
    nzo.set_unpack_info('Unpack', '[%s] %s' % (unicoder(setname), msg), set=setname)
    logging.info('%s', msg)

    return 0, extracted, rarfiles


##############################################################################
# (Un)Zip Functions
##############################################################################
def unzip(nzo, workdir, workdir_complete, delete, one_folder, zips):
    """ Unpack multiple sets 'zips' of ZIP files from 'workdir' to 'workdir_complete.
        When 'delete' is ste, originals will be deleted.
    """

    try:
        i = 0
        unzip_failed = False
        tms = time()

        for _zip in zips:
            logging.info("Starting extract on zipfile: %s ", _zip)
            nzo.set_action_line(T('Unpacking'), '%s' % unicoder(_zip))

            if workdir_complete and _zip.startswith(workdir):
                extraction_path = workdir_complete
            else:
                extraction_path = os.path.split(_zip)[0]

            if ZIP_Extract(_zip, extraction_path, one_folder):
                unzip_failed = True
            else:
                i += 1

        msg = T('%s files in %s') % (str(i), format_time_string(time() - tms))
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
                    logging.warning(T('Deleting %s failed!'), _zip)

                brokenzip = '%s.1' % _zip

                if os.path.exists(brokenzip):
                    logging.info("Deleting %s", brokenzip)
                    try:
                        os.remove(brokenzip)
                        i += 1
                    except OSError:
                        logging.warning(T('Deleting %s failed!'), brokenzip)

        return unzip_failed
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T('Unpacking failed, %s') % msg
        logging.error(T('Error "%s" while running unzip() on %s'), msg, nzo.final_name)
        return True


def ZIP_Extract(zipfile, extraction_path, one_folder):
    """ Unzip single zip set 'zipfile' to 'extraction_path' """
    if one_folder or cfg.flat_unpack():
        option = '-j'  # Unpack without folders
    else:
        option = '-qq'  # Dummy option
    command = ['%s' % ZIP_COMMAND, '-o', '-qq', option, '-Pnone', '%s' % zipfile,
               '-d%s' % extraction_path]

    stup, need_shell, command, creationflags = build_command(command)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    output = p.stdout.read()
    logging.debug('unzip output: %s', output)

    ret = p.wait()

    return ret


##############################################################################
# 7Zip Functions
##############################################################################
def unseven(nzo, workdir, workdir_complete, delete, one_folder, sevens):
    """ Unpack multiple sets '7z' of 7Zip files from 'workdir' to 'workdir_complete.
        When 'delete' is set, originals will be deleted.
    """
    i = 0
    unseven_failed = False
    tms = time()

    # Find multi-volume sets, because 7zip will not provide actual set members
    sets = {}
    for seven in sevens:
        name, ext = os.path.splitext(seven)
        ext = ext.strip('.')
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
        nzo.set_action_line(T('Unpacking'), '%s' % unicoder(seven))

        if workdir_complete and seven.startswith(workdir):
            extraction_path = workdir_complete
        else:
            extraction_path = os.path.split(seven)[0]

        res, msg = seven_extract(nzo, seven, extensions, extraction_path, one_folder, delete)
        if res:
            unseven_failed = True
            nzo.set_unpack_info('Unpack', msg)
        else:
            i += 1

    if not unseven_failed:
        msg = T('%s files in %s') % (str(i), format_time_string(time() - tms))
        nzo.set_unpack_info('Unpack', msg)

    return unseven_failed


def seven_extract(nzo, sevenset, extensions, extraction_path, one_folder, delete):
    """ Unpack single set 'sevenset' to 'extraction_path', with password tries
        Return fail==0(ok)/fail==1(error)/fail==2(wrong password), new_files, sevens
    """

    fail = 0
    if nzo.password:
        passwords = [nzo.password]
    else:
        passwords = []
        pw_file = cfg.password_file.get_path()
        if pw_file:
            try:
                pwf = open(pw_file, 'r')
                passwords = pwf.read().split('\n')
                # Remove empty lines and space-only passwords and remove surrounding spaces
                passwords = [pw.strip('\r\n ') for pw in passwords if pw.strip('\r\n ')]
                pwf.close()
                logging.info('Read the passwords file %s', pw_file)
            except IOError:
                logging.info('Failed to read the passwords file %s', pw_file)

    if nzo.password:
        # If an explicit password was set, add a retry without password, just in case.
        passwords.append('')
    elif not passwords or not nzo.encrypted:
        # If we're not sure about encryption, start with empty password
        # and make sure we have at least the empty password
        passwords.insert(0, '')

    for password in passwords:
        if password:
            logging.debug('Trying 7zip with password "%s"', password)
            msg = T('Trying 7zip with password "%s"') % unicoder(password)
            nzo.fail_msg = msg
            nzo.set_unpack_info('Unpack', msg)
        fail, msg = seven_extract_core(sevenset, extensions, extraction_path, one_folder, delete, password)
        if fail != 2:
            break

    nzo.fail_msg = ''
    if fail == 2:
        logging.error(u'%s (%s)', T('Unpacking failed, archive requires a password'), os.path.split(sevenset)[1])
    return fail, msg


def seven_extract_core(sevenset, extensions, extraction_path, one_folder, delete, password):
    """ Unpack single 7Z set 'sevenset' to 'extraction_path'
        Return fail==0(ok)/fail==1(error)/fail==2(wrong password), message
    """
    msg = None
    if one_folder:
        method = 'e'  # Unpack without folders
    else:
        method = 'x'  # Unpack with folders
    if sabnzbd.WIN32 or sabnzbd.DARWIN:
        case = '-ssc-'  # Case insensitive
    else:
        case = '-ssc'  # Case sensitive
    if password:
        password = '-p%s' % password
    else:
        password = '-p'

    if len(extensions) > 0:
        name = '%s.001' % sevenset
    else:
        name = sevenset

    if not os.path.exists(name):
        return 1, T('7ZIP set "%s" is incomplete, cannot unpack') % unicoder(sevenset)

    command = [SEVEN_COMMAND, method, '-y', '-aou', case, password,
               '-o%s' % extraction_path, name]

    stup, need_shell, command, creationflags = build_command(command)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    output = p.stdout.read()
    logging.debug('7za output: %s', output)

    ret = p.wait()

    if ret == 0 and delete:
        if extensions:
            for ext in extensions:
                path = '%s.%s' % (sevenset, ext)
                try:
                    os.remove(path)
                except:
                    logging.warning(T('Deleting %s failed!'), path)
        else:
            try:
                os.remove(sevenset)
            except:
                logging.warning(T('Deleting %s failed!'), sevenset)

    # Always return an error message, even when return code is 0
    return ret, T('Could not unpack %s') % unicoder(sevenset)


##############################################################################
# PAR2 Functions
##############################################################################
def par2_repair(parfile_nzf, nzo, workdir, setname, single):
    """ Try to repair a set, return readd or correctness """
    # set the current nzo status to "Repairing". Used in History

    parfile = os.path.join(workdir, parfile_nzf.filename)
    parfile = short_path(parfile)
    workdir = short_path(workdir)

    old_dir_content = os.listdir(workdir)
    used_joinables = ()
    joinables = ()
    used_par2 = ()
    setpars = pars_of_set(workdir, setname)
    result = readd = False

    nzo.status = Status.QUICK_CHECK
    nzo.set_action_line(T('Repair'), T('Quick Checking'))
    qc_result = QuickCheck(setname, nzo)
    if qc_result and cfg.quick_check():
        logging.info("Quick-check for %s is OK, skipping repair", setname)
        nzo.set_unpack_info('Repair', T('[%s] Quick Check OK') % unicoder(setname), set=setname)
        pars = setpars
        result = True

    if not result and cfg.enable_all_par():
        # Download all par2 files that haven't been downloaded yet
        readd = False
        for extrapar in parfile_nzf.extrapars[:]:
            if extrapar in nzo.files:
                nzo.add_parfile(extrapar)
                parfile_nzf.extrapars.remove(extrapar)
                readd = True
        if readd:
            return readd, result

    if not result:
        flag_file(workdir, QCHECK_FILE, True)
        nzo.status = Status.REPAIRING
        result = False
        readd = False
        try:
            nzo.set_action_line(T('Repair'), T('Starting Repair'))
            logging.info('Scanning "%s"', parfile)

            joinables, zips, rars, sevens, ts = build_filelists(workdir, None, check_rar=False)

            finished, readd, pars, datafiles, used_joinables, used_par2 = PAR_Verify(parfile, parfile_nzf, nzo,
                                                                                     setname, joinables, single=single)

            if finished:
                result = True
                logging.info('Par verify finished ok on %s!',
                             parfile)

                # Remove this set so we don't try to check it again
                nzo.remove_parset(parfile_nzf.setname)
            else:
                if qc_result:
                    logging.warning(T('Par verify failed on %s, while QuickCheck succeeded!'), parfile)
                else:
                    logging.info('Par verify failed on %s!', parfile)

                if not readd:
                    # Failed to repair -> remove this set
                    nzo.remove_parset(parfile_nzf.setname)
                return readd, False
        except:
            msg = sys.exc_info()[1]
            nzo.fail_msg = T('Repairing failed, %s') % msg
            logging.error(T('Error %s while running par2_repair on set %s'), msg, setname)
            logging.info("Traceback: ", exc_info=True)
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
                        logging.warning(T('Deleting %s failed!'), path)

            path = os.path.join(workdir, setname + '.par2')
            path2 = os.path.join(workdir, setname + '.PAR2')

            if os.path.exists(path):
                try:
                    logging.info("Deleting %s", path)
                    os.remove(path)
                except:
                    logging.warning(T('Deleting %s failed!'), path)

            if os.path.exists(path2):
                try:
                    logging.info("Deleting %s", path2)
                    os.remove(path2)
                except:
                    logging.warning(T('Deleting %s failed!'), path2)

            if os.path.exists(parfile):
                try:
                    logging.info("Deleting %s", parfile)
                    os.remove(parfile)
                except OSError:
                    logging.warning(T('Deleting %s failed!'), parfile)

            deletables = []
            for f in pars:
                if f in setpars:
                    deletables.append(os.path.join(workdir, f))
            deletables.extend(used_joinables)
            deletables.extend(used_par2)
            for filepath in deletables:
                if filepath in joinables:
                    joinables.remove(filepath)
                if os.path.exists(filepath):
                    logging.info("Deleting %s", filepath)
                    try:
                        os.remove(filepath)
                    except OSError:
                        logging.warning(T('Deleting %s failed!'), filepath)
    except:
        msg = sys.exc_info()[1]
        nzo.fail_msg = T('Repairing failed, %s') % msg
        logging.error(T('Error "%s" while running par2_repair on set %s'), msg, setname)

    return readd, result


_RE_BLOCK_FOUND = re.compile(r'File: "([^"]+)" - found \d+ of \d+ data blocks from "([^"]+)"')
_RE_IS_MATCH_FOR = re.compile(r'File: "([^"]+)" - is a match for "([^"]+)"')
_RE_LOADING_PAR2 = re.compile(r'Loading "([^"]+)"\.')
_RE_LOADED_PAR2 = re.compile(r'Loaded (\d+) new packets')


def PAR_Verify(parfile, parfile_nzf, nzo, setname, joinables, classic=False, single=False):
    """ Run par2 on par-set """
    import sabnzbd  # Python bug requires import here
    import sabnzbd.assembler
    if cfg.never_repair():
        cmd = 'v'
    else:
        cmd = 'r'
    retry_classic = False
    used_joinables = []
    used_par2 = []
    extra_par2_name = None
    # set the current nzo status to "Verifying...". Used in History
    nzo.status = Status.VERIFYING
    start = time()

    classic = classic or not cfg.par2_multicore()
    if sabnzbd.WIN32:
        # If filenames are UTF-8 then we must use par2-tbb, unless this is a retry with classic
        tbb = (sabnzbd.assembler.GetMD5Hashes(parfile, True)[1] and not classic) or not PAR2C_COMMAND
    else:
        tbb = False
    if tbb and cfg.par_option():
        command = [str(PAR2_COMMAND), cmd, str(cfg.par_option().strip()), parfile]
    else:
        if classic:
            command = [str(PAR2C_COMMAND), cmd, parfile]
        else:
            command = [str(PAR2_COMMAND), cmd, parfile]
    logging.debug('Par2-classic = %s', classic)

    # Append the wildcard for this set
    parfolder = os.path.split(parfile)[0]
    if single or len(globber(parfolder, setname + '*')) < 2:
        # Support bizarre naming conventions
        wildcard = '*'
    else:
        # Normal case, everything is named after set
        wildcard = setname + '*'

    if sabnzbd.WIN32 or sabnzbd.DARWIN:
        command.append(os.path.join(parfolder, wildcard))
    else:
        # For Unix systems, remove folders, due to bug in some par2cmdline versions
        flist = [item for item in globber_full(parfolder, wildcard) if os.path.isfile(item)]
        command.extend(flist)

    stup, need_shell, command, creationflags = build_command(command)
    logging.debug('Starting par2: %s', command)

    lines = []
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
        renames = {}

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

            if 'Repairing:' not in line:
                lines.append(line)

            if extra_par2_name and line.startswith('Loading:') and line.endswith('%'):
                continue
            if extra_par2_name and line.startswith('Loaded '):
                m = _RE_LOADED_PAR2.search(line)
                if m and int(m.group(1)) > 0:
                    used_par2.append(os.path.join(nzo.downpath, extra_par2_name))
                extra_par2_name = None
                continue
            extra_par2_name = None

            if line.startswith('Invalid option specified') or line.startswith('Cannot specify recovery file count'):
                msg = T('[%s] PAR2 received incorrect options, check your Config->Switches settings') % unicoder(setname)
                nzo.set_unpack_info('Repair', msg, set=setname)
                nzo.status = Status.FAILED

            elif line.startswith('All files are correct'):
                msg = T('[%s] Verified in %s, all files correct') % (unicoder(setname), format_time_string(time() - start))
                nzo.set_unpack_info('Repair', msg, set=setname)
                logging.info('Verified in %s, all files correct',
                             format_time_string(time() - start))
                finished = 1

            elif line.startswith('Repair is required'):
                msg = T('[%s] Verified in %s, repair is required') % (unicoder(setname), format_time_string(time() - start))
                nzo.set_unpack_info('Repair', msg, set=setname)
                logging.info('Verified in %s, repair is required',
                              format_time_string(time() - start))
                start = time()
                verified = 1

            elif line.startswith('Loading "'):
                # Found an extra par2 file. Only the next line will tell whether it's usable
                m = _RE_LOADING_PAR2.search(line)
                if m and m.group(1).lower().endswith('.par2'):
                    extra_par2_name = TRANS(m.group(1))

            elif line.startswith('Main packet not found') or 'The recovery file does not exist' in line:
                # Initialparfile probably didn't decode properly,
                logging.info(T('Main packet not found...'))

                extrapars = parfile_nzf.extrapars

                logging.info("Extra pars = %s", extrapars)

                # Look for the smallest par2file
                block_table = {}
                for nzf in extrapars:
                    if not nzf.completed:
                        block_table[int_conv(nzf.blocks)] = nzf

                if block_table:
                    nzf = block_table[min(block_table.keys())]

                    logging.info("Found new par2file %s", nzf.filename)

                    # Move from extrapar list to files to be downloaded
                    nzo.add_parfile(nzf)
                    extrapars.remove(nzf)
                    # Now set new par2 file as primary par2
                    nzo.partable[setname] = nzf
                    nzf.extrapars = extrapars
                    parfile_nzf = []
                    # mark for readd
                    readd = True
                else:
                    msg = T('Invalid par2 files, cannot verify or repair')
                    nzo.fail_msg = msg
                    msg = u'[%s] %s' % (unicoder(setname), msg)
                    nzo.set_unpack_info('Repair', msg, set=setname)
                    nzo.status = Status.FAILED

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

                    blocks = int_conv(nzf.blocks)

                    avail_blocks += blocks

                    if blocks not in block_table:
                        block_table[blocks] = []

                    block_table[blocks].append(nzf)

                logging.info('%s blocks available', avail_blocks)

                force = False
                if (avail_blocks < needed_blocks) and (avail_blocks > 0):
                    # Tell SAB that we always have enough blocks, so that
                    # it will try to load all pars anyway
                    msg = T('Repair failed, not enough repair blocks (%s short)') % str(int(needed_blocks - avail_blocks))
                    nzo.fail_msg = msg
                    msg = u'[%s] %s' % (unicoder(setname), msg)
                    nzo.set_unpack_info('Repair', msg, set=setname)
                    nzo.status = Status.FETCHING
                    needed_blocks = avail_blocks
                    force = True

                if avail_blocks >= needed_blocks:
                    added_blocks = 0
                    readd = True

                    while added_blocks < needed_blocks:
                        block_size = min(block_table.keys())
                        extrapar_list = block_table[block_size]

                        if extrapar_list:
                            new_nzf = extrapar_list.pop()
                            nzo.add_parfile(new_nzf)
                            if new_nzf in extrapars:
                                extrapars.remove(new_nzf)
                            added_blocks += block_size

                        else:
                            block_table.pop(block_size)

                    logging.info('Added %s blocks to %s',
                                 added_blocks, nzo.final_name)

                    if not force:
                        msg = T('Fetching %s blocks...') % str(added_blocks)
                        nzo.status = Status.FETCHING
                        nzo.set_action_line(T('Fetching'), msg)

                else:
                    msg = T('Repair failed, not enough repair blocks (%s short)') % str(needed_blocks)
                    nzo.fail_msg = msg
                    msg = u'[%s] %s' % (unicoder(setname), msg)
                    nzo.set_unpack_info('Repair', msg, set=setname)
                    nzo.status = Status.FAILED

            elif line.startswith('Repair is possible'):
                start = time()
                nzo.set_action_line(T('Repairing'), '%2d%%' % (0))

            elif line.startswith('Repairing:'):
                chunks = line.split()
                per = float(chunks[-1][:-1])
                nzo.set_action_line(T('Repairing'), '%2d%%' % per)
                nzo.status = Status.REPAIRING

            elif line.startswith('Repair complete'):
                msg = T('[%s] Repaired in %s') % (unicoder(setname), format_time_string(time() - start))
                nzo.set_unpack_info('Repair', msg, set=setname)
                logging.info('Repaired in %s', format_time_string(time() - start))
                finished = 1

            elif line.startswith('File:') and line.find('data blocks from') > 0:
                # Find out if a joinable file has been used for joining
                uline = unicoder(line)
                for jn in joinables:
                    if uline.find(os.path.split(jn)[1]) > 0:
                        used_joinables.append(jn)
                        break
                # Special case of joined RAR files, the "of" and "from" must both be RAR files
                # This prevents the joined rars files from being seen as an extra rar-set
                m = _RE_BLOCK_FOUND.search(line)
                if m and '.rar' in m.group(1).lower() and '.rar' in m.group(2).lower():
                    workdir = os.path.split(parfile)[0]
                    used_joinables.append(os.path.join(workdir, TRANS(m.group(1))))

            elif 'Could not write' in line and 'at offset 0:' in line and not classic:
                # Hit a bug in par2-tbb, retry with par2-classic
                retry_classic = sabnzbd.WIN32

            elif ' cannot be renamed to ' in line:
                if not classic and sabnzbd.WIN32:
                    # Hit a bug in par2-tbb, retry with par2-classic
                    retry_classic = True
                else:
                    msg = unicoder(line.strip())
                    nzo.fail_msg = msg
                    msg = u'[%s] %s' % (unicoder(setname), msg)
                    nzo.set_unpack_info('Repair', msg, set=setname)
                    nzo.status = Status.FAILED

            # File: "oldname.rar" - is a match for "newname.rar".
            elif 'is a match for' in line:
                m = _RE_IS_MATCH_FOR.search(line)
                if m:
                    old_name = TRANS(m.group(1))
                    new_name = TRANS(m.group(2))
                    logging.debug('PAR2 will rename "%s" to "%s"', old_name, new_name)
                    renames[new_name] = old_name

            elif 'No details available for recoverable file' in line:
                msg = unicoder(line.strip())
                nzo.fail_msg = msg
                msg = u'[%s] %s' % (unicoder(setname), msg)
                nzo.set_unpack_info('Repair', msg, set=setname)
                nzo.status = Status.FAILED

            elif not verified:
                if line.startswith('Verifying source files'):
                    nzo.set_action_line(T('Verifying'), '01/%02d' % verifytotal)
                    nzo.status = Status.VERIFYING

                elif line.startswith('Scanning:'):
                    pass

                else:
                    # Loading parity files
                    m = LOADING_RE.match(line)
                    if m:
                        pars.append(TRANS(m.group(1)))
                        continue

                # Target files
                m = TARGET_RE.match(line)
                if m:
                    if verifytotal == 0 or verifynum < verifytotal:
                        verifynum += 1
                        nzo.set_action_line(T('Verifying'), '%02d/%02d' % (verifynum, verifytotal))
                        nzo.status = Status.VERIFYING
                    datafiles.append(TRANS(m.group(1)))
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

    logging.debug('PAR2 output was\n%s', '\n'.join(lines))

    # If successful, add renamed files to the collection
    if finished and renames:
        previous = load_data(RENAMES_FILE, nzo.workpath, remove=False)
        for name in previous or {}:
            renames[name] = previous[name]
        save_data(renames, RENAMES_FILE, nzo.workpath)

    if retry_classic:
        logging.debug('Retry PAR2-joining with par2-classic')
        return PAR_Verify(parfile, parfile_nzf, nzo, setname, joinables, classic=True, single=single)
    else:
        return finished, readd, pars, datafiles, used_joinables, used_par2


def fix_env():
    """ OSX: Return copy of environment without PYTHONPATH and PYTHONHOME
        other: return None
    """
    if sabnzbd.DARWIN:
        env = os.environ.copy()
        if 'PYTHONPATH' in env:
            del env['PYTHONPATH']
        if 'PYTHONHOME' in env:
            del env['PYTHONHOME']
        return env
    else:
        return None


def build_command(command):
    """ Prepare list from running an external program """
    for n in xrange(len(command)):
        if isinstance(command[n], unicode):
            command[n] = deunicode(command[n])

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

    return stup, need_shell, command, creationflags


# Sort the various RAR filename formats properly :\
def rar_sort(a, b):
    """ Define sort method for rar file names """
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
    """ Define sort method for par2 file names """
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
    joinables, zips, rars, sevens, filelist = ([], [], [], [], [])

    if workdir_complete:
        for root, dirs, files in os.walk(workdir_complete):
            for _file in files:
                if '.AppleDouble' not in root and '.DS_Store' not in root:
                    filelist.append(os.path.join(root, _file))

    if workdir and not filelist:
        for root, dirs, files in os.walk(workdir):
            for _file in files:
                if '.AppleDouble' not in root and '.DS_Store' not in root:
                    filelist.append(os.path.join(root, _file))

    sevens = [f for f in filelist if SEVENZIP_RE.search(f)]
    sevens.extend([f for f in filelist if SEVENMULTI_RE.search(f)])

    if check_rar:
        joinables = [f for f in filelist if f not in sevens and SPLITFILE_RE.search(f) and not is_rarfile(f)]
    else:
        joinables = [f for f in filelist if f not in sevens and SPLITFILE_RE.search(f)]

    zips = [f for f in filelist if ZIP_RE.search(f)]

    rars = [f for f in filelist if RAR_RE.search(f)]

    ts = [f for f in filelist if TS_RE.search(f) and f not in joinables and f not in sevens]

    logging.debug("build_filelists(): joinables: %s", joinables)
    logging.debug("build_filelists(): zips: %s", zips)
    logging.debug("build_filelists(): rars: %s", rars)
    logging.debug("build_filelists(): 7zips: %s", sevens)
    logging.debug("build_filelists(): ts: %s", ts)

    return joinables, zips, rars, sevens, ts


def QuickCheck(set, nzo):
    """ Check all on-the-fly md5sums of a set """

    md5pack = nzo.md5packs.get(set)
    if md5pack is None:
        return False

    result = False
    nzf_list = nzo.finished_files

    for file in md5pack:
        if sabnzbd.misc.on_cleanup_list(file, False):
            result = True
            continue
        found = False
        for nzf in nzf_list:
            if file == nzf.filename:
                found = True
                if (nzf.md5sum is not None) and nzf.md5sum == md5pack[file]:
                    logging.debug('Quick-check of file %s OK', file)
                    result = True
                else:
                    logging.info('Quick-check of file %s failed!', file)
                    return False  # When any file fails, just stop
                break
        if not found:
            logging.info('Cannot Quick-check missing file %s!', file)
            return False  # Missing file is failure
    return result


def pars_of_set(wdir, setname):
    """ Return list of par2 files (pathless) matching the set """
    list = []
    for file in os.listdir(wdir):
        m = FULLVOLPAR2_RE.search(file)
        if m and m.group(1) == setname and m.group(2):
            list.append(file)
    return list


def add_s(i):
    """ Return an "s" when 'i' > 1 """
    if i > 1:
        return 's'
    else:
        return ''


def unrar_check(rar):
    """ Return version number of unrar, where "5.01" returns 501
        Also return whether an original version is found
        (version, original)
    """
    version = 0
    original = ''
    if rar:
        try:
            version = run_simple(rar)
        except:
            return version, original
        original = "Alexander Roshal" in version
        m = re.search(r"RAR\s(\d+)\.(\d+)", version)
        if m:
            version = int(m.group(1)) * 100 + int(m.group(2))
        else:
            version = 0
    return version, original


def sfv_check(sfv_path):
    """ Verify files using SFV file,
        input: full path of sfv, file are assumed to be relative to sfv
        returns: List of failing files or [] when all is OK
    """
    failed = []
    try:
        fp = open(sfv_path, 'r')
    except:
        logging.info('Cannot open SFV file %s', sfv_path)
        failed.append(unicoder(sfv_path))
        return failed
    root = os.path.split(sfv_path)[0]
    for line in fp:
        line = line.strip('\n\r ')
        if line and line[0] != ';':
            x = line.rfind(' ')
            if x > 0:
                filename = platform_encode(line[:x].strip())
                checksum = line[x:].strip()
                path = os.path.join(root, filename)
                if os.path.exists(path):
                    if crc_check(path, checksum):
                        logging.debug('File %s passed SFV check', path)
                    else:
                        logging.info('File %s did not pass SFV check', path)
                        failed.append(unicoder(filename))
                else:
                    logging.info('File %s missing in SFV check', path)
                    failed.append(unicoder(filename))
    fp.close()
    return failed


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


def analyse_show(name):
    """ Do a quick SeasonSort check and return basic facts """
    job = SeriesSorter(None, name, None, None)
    job.match(force=True)
    if job.is_match():
        job.get_values()
    info = job.show_info
    show_name = info.get('show_name', '').replace('.', ' ').replace('_', ' ')
    show_name = show_name.replace('  ', ' ')
    return show_name, \
           info.get('season_num', ''), \
           info.get('episode_num', ''), \
           info.get('ep_name', '')


def pre_queue(name, pp, cat, script, priority, size, groups):
    """ Run pre-queue script (if any) and process results """
    def fix(p):
        if not p or str(p).lower() == 'none':
            return ''
        else:
            return UNTRANS(str(p))

    values = [1, name, pp, cat, script, priority, None]
    script_path = make_script_path(cfg.pre_script())
    if script_path:
        command = [script_path, name, fix(pp), fix(cat), fix(script), fix(priority), str(size), ' '.join(groups)]
        command.extend(analyse_show(name))

        stup, need_shell, command, creationflags = build_command(command)
        env = fix_env()

        logging.info('Running pre-queue script %s', command)

        try:
            p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                startupinfo=stup, env=env, creationflags=creationflags)
        except:
            logging.debug("Failed script %s, Traceback: ", script_path, exc_info=True)
            return values

        output = p.stdout.read()
        ret = p.wait()
        logging.info('Pre-queue script returns %s and output=\n%s', ret, output)
        if ret == 0:
            n = 0
            for line in output.split('\n'):
                line = line.strip('\r\n \'"')
                if n < len(values) and line:
                    values[n] = TRANS(line)
                n += 1
        if int_conv(values[0]) < 1:
            logging.info('Pre-Q refuses %s', name)
        else:
            logging.info('Pre-Q accepts %s', name)

    return values


def list2cmdline(lst):
    """ convert list to a cmd.exe-compatible command string """
    nlst = []
    for arg in lst:
        if not arg:
            nlst.append('""')
        elif (' ' in arg) or ('\t' in arg) or ('&' in arg) or ('|' in arg) or (';' in arg) or (',' in arg):
            nlst.append('"%s"' % arg)
        else:
            nlst.append(arg)
    return ' '.join(nlst)


def get_from_url(url, timeout=None):
    """ Retrieve URL and return content
        `timeout` sets non-standard timeout
    """
    import urllib2
    try:
        if timeout:
            s = urllib2.urlopen(url, timeout=timeout)
        else:
            s = urllib2.urlopen(url)
        output = s.read()
    except:
        output = None
    return output


def is_sevenfile(path):
    """ Return True if path has proper extension and 7Zip is installed """
    return SEVEN_COMMAND and os.path.splitext(path)[1].lower() == '.7z'


class SevenZip(object):
    """ Minimal emulation of ZipFile class for 7Zip """

    def __init__(self, path):
        self.path = path

    def namelist(self):
        """ Return list of names in 7Zip """
        names = []
        # Future extension: use '-sccUTF-8' to get names in UTF8 encoding
        command = [SEVEN_COMMAND, 'l', '-p', '-y', '-slt', self.path]
        stup, need_shell, command, creationflags = build_command(command)

        p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             startupinfo=stup, creationflags=creationflags)

        output = p.stdout.read()
        ret = p.wait()
        re_path = re.compile('^Path = (.+)')
        for line in output.split('\n'):
            m = re_path.search(line)
            if m:
                names.append(m.group(1).strip('\r'))
        if names:
            # Remove name of archive itself
            del names[0]
        return names

    def read(self, name):
        """ Read named file from 7Zip and return data """
        command = [SEVEN_COMMAND, 'e', '-p', '-y', '-so', self.path, name]
        stup, need_shell, command, creationflags = build_command(command)

        # Ignore diagnostic output, otherwise it will be appended to content
        if sabnzbd.WIN32:
            stderr = open('nul', 'w')
        else:
            stderr = open('/dev/null', 'w')

        p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=stderr,
                             startupinfo=stup, creationflags=creationflags)

        output = p.stdout.read()
        ret = p.wait()
        stderr.close()
        return output

    def close(self):
        """ Close file """
        pass


def run_simple(cmd):
    """ Run simple external command and return output """
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    txt = p.stdout.read()
    p.wait()
    return txt
