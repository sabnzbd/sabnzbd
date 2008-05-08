#!/usr/bin/python -OO
# Copyright 2004 Freddie <freddie@madcowdisease.org>
#           2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#           2007 The ShyPike <shypike@users.sourceforge.net>
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
__NAME__ = 'newsunpack'

import os
import re
import subprocess
import logging
from time import time
import sabnzbd
from sabnzbd.nzbstuff import SplitFileName

try:
    from win32con import SW_HIDE
    from win32process import STARTF_USESHOWWINDOW, IDLE_PRIORITY_CLASS
except ImportError:
    pass

RAR_RE = re.compile(r'\.(?P<ext>part\d*\.rar|rar|r\d\d|\d\d\d)$', re.I)
RAR_RE_V3 = re.compile(r'\.(?P<ext>part\d*)$', re.I)

LOADING_RE = re.compile(r'^Loading "(.+)"')
TARGET_RE = re.compile(r'^(?:File|Target): "(.+)" -')
EXTRACTFROM_RE = re.compile(r'^Extracting\sfrom\s(.+)')
SPLITFILE_RE = re.compile(r'\.(\d\d\d$)', re.I)
ZIP_RE = re.compile(r'\.(zip$)', re.I)

PAR2_COMMAND = None
RAR_COMMAND = None
NICE_COMMAND = None
ZIP_COMMAND = None

def find_programs(curdir):
    """Find external programs
    """
    if os.name == 'nt':
        p = os.path.abspath(curdir + '/win/par2/par2.exe')
        if os.access(p, os.X_OK):
            sabnzbd.newsunpack.PAR2_COMMAND = p
        p = os.path.abspath(curdir + '/win/unrar/UnRAR.exe')
        if os.access(p, os.X_OK):
            sabnzbd.newsunpack.RAR_COMMAND = p
        p = os.path.abspath(curdir + '/win/unzip/unzip.exe')
        if os.access(p, os.X_OK):
            sabnzbd.newsunpack.ZIP_COMMAND = p
    else:
        lookhere = os.getenv('PATH').split(':')
        findpar2 = ('par2',)
        findrar = ('rar', 'unrar', 'rar3', 'unrar3')
        findnice = ('nice',)
        findzip = ('unzip',)

        for path in lookhere:
            if not sabnzbd.newsunpack.PAR2_COMMAND:
                for par2 in findpar2:
                    par2_path = os.path.join(path, par2)
                    par2_path = os.path.abspath(par2_path)
                    if os.access(par2_path, os.X_OK):
                        sabnzbd.newsunpack.PAR2_COMMAND = par2_path
                        break

            if not sabnzbd.newsunpack.RAR_COMMAND:
                for _rar in findrar:
                    rar_path = os.path.join(path, _rar)
                    rar_path = os.path.abspath(rar_path)
                    if os.access(rar_path, os.X_OK):
                        sabnzbd.newsunpack.RAR_COMMAND = rar_path
                        break

            if not sabnzbd.newsunpack.NICE_COMMAND:
                for _nice in findnice:
                    nice_path = os.path.join(path, _nice)
                    nice_path = os.path.abspath(nice_path)
                    if os.access(nice_path, os.X_OK):
                        sabnzbd.newsunpack.NICE_COMMAND = nice_path
                        break

            if not sabnzbd.newsunpack.ZIP_COMMAND:
                for _zip in findzip:
                    zip_path = os.path.join(path, _zip)
                    zip_path = os.path.abspath(zip_path)
                    if os.access(zip_path, os.X_OK):
                        sabnzbd.newsunpack.ZIP_COMMAND = zip_path
                        break


#------------------------------------------------------------------------------
def external_processing(extern_proc, complete_dir, filename, nicename, cat):

    name, msgid = SplitFileName(filename)
    command = ['%s' % extern_proc, '%s' % complete_dir, '%s' % filename, \
               '%s' % nicename, '%s' % msgid, '%s' % cat]

    stup, need_shell, command, creationflags = build_command(command)

    logging.info('[%s] Running external script %s(%s, %s, %s, %s, %s)', __NAME__, \
                 extern_proc, complete_dir, filename, nicename, msgid, cat)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    output = p.stdout.read()
    p.wait()
    return output


#------------------------------------------------------------------------------

def unpack_magic(nzo, workdir, workdir_complete, dele, joinables, zips, rars):
    xjoinables, xzips, xrars = build_filelists(workdir, workdir_complete)

    rerun = False
    newfiles = []
    error = False

    if sabnzbd.DO_FILE_JOIN:
        do_filejoin = False
        for joinable in xjoinables:
            if joinable not in joinables:
                do_filejoin = True
                rerun = True
                break

        if do_filejoin:
            logging.info('[%s] Filejoin starting on %s', __NAME__, workdir)
            if file_join(nzo, workdir, workdir_complete, dele, xjoinables):
                error = True
            logging.info('[%s] Filejoin finished on %s', __NAME__, workdir)

    if sabnzbd.DO_UNRAR:
        do_unrar = False
        for rar in xrars:
            if rar not in rars:
                do_unrar = True
                rerun = True
                break

        if do_unrar:
            logging.info('[%s] Unrar starting on %s', __NAME__, workdir)
            error, newf = rar_unpack(nzo, workdir, workdir_complete, dele, xrars)
            if newf:
                newfiles.extend(newf)
            logging.info('[%s] Unrar finished on %s', __NAME__, workdir)

    if sabnzbd.DO_UNZIP:
        do_unzip = False
        for _zip in xzips:
            if _zip not in zips:
                do_unzip = True
                rerun = True
                break

        if do_unzip:
            logging.info('[%s] Unzip starting on %s', __NAME__, workdir)
            if unzip(nzo, workdir, workdir_complete, dele, xzips):
                error = True
            logging.info('[%s] Unzip finished on %s', __NAME__, workdir)

    if rerun:
            z, y = unpack_magic(nzo, workdir, workdir_complete, dele, xjoinables,
                             xzips, xrars)
            if z:
                error = z
            if y:
                newfiles.extend(y)

    return error, newfiles

#------------------------------------------------------------------------------
# Filejoin Functions
#------------------------------------------------------------------------------

def file_join(nzo, workdir, workdir_complete, delete, joinables):
    actionname = '[FJN-INFO]'
    try:
        joinable_sets = {}
        for joinable in joinables:
            head, tail = os.path.splitext(joinable)
            if head not in joinable_sets:
                joinable_sets[head] = []
            joinable_sets[head].append(joinable)

        logging.debug("[%s] joinable_sets: %s", __NAME__, joinable_sets)

        for joinable_set in joinable_sets:
            actionname = '[FJN-INFO] %s' % os.path.basename(joinable_set)

            expected_size = 0
            for i in xrange(len(joinable_sets[joinable_set])+1):
                expected_size += i
            logging.debug("[%s] FJN, expsize: %s", __NAME__, expected_size)

            real_size = 0
            for joinable in joinable_sets[joinable_set]:
                head, tail = os.path.splitext(joinable)
                real_size += int(tail[1:])
            logging.debug("[%s] FJN, realsize: %s", __NAME__, real_size)

            if real_size == expected_size:
                joinable_sets[joinable_set].sort()
                filename = joinable_set

                # Check if par2 repaired this joinable set
                if os.path.exists(filename):
                    logging.debug("file_join(): Skipping %s, (probably) joined by par2", filename)
                    nzo.set_unpackstr("=> Skipping, (probably) joined by par2", actionname, 4)
                    if delete:
                        i = 0
                        for joinable in joinable_sets[joinable_set]:
                            logging.debug("[%s] Deleting %s", __NAME__, joinable)
                            os.remove(joinable)
                            i += 1

                        actionname = '[DEL-INFO] %s' % os.path.basename(joinable_set)
                        nzo.set_unpackstr("=> Deleted %s file(s)" % i, actionname, 4)
                    continue

                if workdir_complete:
                    filename = filename.replace(workdir, workdir_complete)

                logging.debug("file_join(): Assembling %s", filename)

                joined_file = open(filename, 'ab')

                i = 0
                for joinable in joinable_sets[joinable_set]:
                    logging.debug("[%s] Processing %s", __NAME__, joinable)
                    nzo.set_unpackstr("=> Processing %s" % joinable, actionname, 4)
                    f = open(joinable, 'rb')
                    joined_file.write(f.read())
                    f.close()
                    i += 1
                    if delete:
                        logging.debug("[%s] Deleting %s", __NAME__, joinable)
                        os.remove(joinable)

                joined_file.flush()
                joined_file.close()
                nzo.set_unpackstr("=> Joined %s file(s)" % i, actionname, 4)
                if delete:
                    actionname = '[DEL-INFO] %s' % os.path.basename(joinable_set)
                    nzo.set_unpackstr("=> Deleted %s file(s)" % i, actionname, 4)
    except:
        nzo.set_unpackstr('=> Unknown error while running file_join, ' + \
                          'see logfile', actionname, 4)
        logging.error('[%s] Unknown error while' + \
                          ' running file_join on %s',
                          __NAME__, nzo.get_filename())
        return True

#------------------------------------------------------------------------------
# (Un)Rar Functions
#------------------------------------------------------------------------------

def rar_unpack(nzo, workdir, workdir_complete, delete, rars):
    actionname = '[RAR-INFO]'
    try:
        errors = False

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
            actionname = '[RAR-INFO] %s' % rar_set
            # Run the RAR extractor
            rarpath = rar_sets[rar_set][0]

            rar_sets[rar_set].sort(rar_sort)

            extraction_path = workdir
            if workdir_complete:
                extraction_path = workdir_complete

            logging.info("[%s] Extracting rarfile %s (belonging to %s) to %s",
                         __NAME__, rarpath, rar_set, extraction_path)

            newfiles, rars = RAR_Extract(rarpath, len(rar_sets[rar_set]),
                                         nzo, actionname, extraction_path)

            logging.debug('[%s] rar_unpack(): Rars: %s', __NAME__, rars)
            logging.debug('[%s] rar_unpack(): Newfiles: %s', __NAME__, newfiles)

            # Delete the old files if we have to
            if delete and newfiles:
                actionname = '[DEL-INFO] %s' % rar_set
                i = 0
                for rar in rars:
                    # Must translate to cp437 codepage due to a mismatch between
                    # the way Python and unrar interpret high-ASCII codes
                    if os.name == 'nt':
                        urar = rar.decode('cp437')
                    else:
                        urar = rar

                    logging.info("[%s] Deleting %s", __NAME__, urar)
                    try:
                        os.remove(urar)
                        i += 1
                    except OSError:
                        logging.warning("[%s] Deleting %s failed!", __NAME__,
                                        urar)

                    brokenrar = '%s.1' % (urar)

                    if os.path.exists(brokenrar):
                        logging.info("[%s] Deleting %s", __NAME__, brokenrar)
                        try:
                            os.remove(brokenrar)
                            i += 1
                        except OSError:
                            logging.warning("[%s] Deleting %s failed!",
                                            __NAME__, brokenrar)
                nzo.set_unpackstr("=> Deleted %d file(s)" % i, actionname,
                                  2)

            if not newfiles:
                errors = True

        return errors, newfiles
    except:
        nzo.set_unpackstr('=> Unknown error while running rar_unpack, ' + \
                          'see logfile', actionname, 2)
        logging.error('[%s] Unknown error while' + \
                          ' running rar_unpack on %s',
                          __NAME__, nzo.get_filename())
        return True, ''

def RAR_Extract(rarfile, numrars, nzo, actionname, extraction_path):
    start = time()

    logging.debug("[%s] RAR_Extract(): Extractionpath: %s", __NAME__,
                  extraction_path)

    ############################################################################
    command = ['%s' % RAR_COMMAND, 'vb', '-v', '%s' % rarfile]

    stup, need_shell, command, creationflags = build_command(command)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    output = p.stdout.read()

    p.wait()

    # List of all files we expect to extract from this archive
    expected_files = []
    for path in output.split(os.linesep):
        if path:
            path = os.path.join(extraction_path, path)
            if path not in expected_files:
                expected_files.append(path)
    ############################################################################

    command = ['%s' % RAR_COMMAND, 'x', '-idp', '-o-', '-p-',
               '%s' % rarfile, '%s' % extraction_path]

    stup, need_shell, command, creationflags = build_command(command)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    proc = p.stdout
    if p.stdin:
        p.stdin.close()

    nzo.set_unpackstr('=> Unpacking : 00/%02d' % (numrars),
                      actionname, 2)

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
            filename = (re.search(EXTRACTFROM_RE, line).group(1))
            if filename not in rarfiles:
                rarfiles.append(filename)
            curr += 1
            nzo.set_unpackstr('=> Unpacking : %02d/%02d' % (curr, numrars),
                              actionname, 2)

        elif line.startswith('Cannot find volume'):
            filename = os.path.basename(line[19:])
            nzo.set_unpackstr('=> ERROR: unable to find "%s"' % filename,
                              actionname, 2)
            logging.warning('[%s] ERROR: unable to find "%s"', __NAME__,
                                                                       filename)
            fail = 1

        elif line.endswith('- CRC failed'):
            filename = line[:-12].strip()
            nzo.set_unpackstr('=> ERROR: CRC failed in "%s"' % filename,
                              actionname, 2)
            logging.warning('[%s] ERROR: CRC failed in %s"', __NAME__, filename)
            fail = 1

        elif line.startswith('Write error'):
            nzo.set_unpackstr('=> ERROR: write error, disk full?',
                              actionname, 2)
            logging.warning('[%s] ERROR: write error', __NAME__)
            fail = 1

        elif line.startswith('ERROR: '):
            nzo.set_unpackstr('=> ERROR: %s' % (line[7:]),
                              actionname, 2)
            logging.warning('[%s] ERROR: %s', __NAME__, (line[7:]))
            fail = 1

        elif line.startswith('Encrypted file:  CRC failed'):
            filename = line[31:-23].strip()
            nzo.set_unpackstr(\
                '=> ERROR: CRC failed in "%s" - password incorrect?' % filename,
                actionname, 2)
            logging.warning('[%s] ERROR: encrypted file: "%s"', __NAME__,
                                                                       filename)
            fail = 1

        else:
            m = re.search(r'^(Extracting|...)\s+(.*?)\s+OK\s*$', line)
            if m:
                extracted.append(m.group(2))

        if fail:
            if proc:
                proc.close()
            p.wait()

            return ((), ())

    if proc:
        proc.close()
    p.wait()

    logging.debug("[%s] RAR_Extract(): expected_files: %s", __NAME__,
                                                                 expected_files)

    all_files_found = True
    for expected_path in expected_files:
        logging.debug("[%s] Checking existance of %s", __NAME__, expected_path)
        if not os.path.exists(expected_path):
            all_files_found = False
            logging.info("[%s] Missing expected file: %s => unrar error?",
                         __NAME__, expected_path)

    if not all_files_found:
        nzo.set_unpackstr('=> At least one file failed to be unpacked, skipping', actionname, 2)
        logging.info('[%s] At least one file failed to be unpacked in %s, skipping', __NAME__, rarfile)
        return ((), ())

    nzo.set_unpackstr('=> Unpacked %d file(s) in %.1fs' % \
                    (len(extracted), time() - start), actionname, 2)
    logging.info('[%s] Unpacked %d file(s) in %1.fs', __NAME__, len(extracted),
                 (time() - start))

    return (extracted, rarfiles)

#------------------------------------------------------------------------------
# (Un)Zip Functions
#------------------------------------------------------------------------------

def unzip(nzo, workdir, workdir_complete, delete, zips):
    actionname = '[ZIP-INFO]'
    try:
        i = 0
        unzip_failed = False
        tms = time()

        for _zip in zips:
            logging.info("[%s] Starting extract on zipfile: %s ", __NAME__,
                         _zip)
            nzo.set_unpackstr('=> Unzipping %s' % _zip, actionname, 3)

            extraction_path = workdir
            if workdir_complete:
                extraction_path = workdir_complete

            if ZIP_Extract(_zip, extraction_path):
                unzip_failed = True
            else:
                i += 1

        nzo.set_unpackstr("=> Unzipped %d file(s) in %1.fs" % (i, time() - tms),
                                                                  actionname, 3)

        # Delete the old files if we have to
        if delete and not unzip_failed:
            actionname = '[DEL-INFO]'
            i = 0

            for _zip in zips:
                logging.info("[%s] Deleting %s", __NAME__, _zip)
                try:
                    os.remove(_zip)
                    i += 1
                except OSError:
                    logging.warning("[%s] Deleting %s failed!", __NAME__, _zip)

                brokenzip = '%s.1' % (_zip)

                if os.path.exists(brokenzip):
                    logging.info("[%s] Deleting %s", __NAME__, brokenzip)
                    try:
                        os.remove(brokenzip)
                        i += 1
                    except OSError:
                        logging.warning("[%s] Deleting %s failed!", __NAME__,
                                        brokenzip)
            nzo.set_unpackstr("=> Deleted %d file(s)" % i, actionname, 3)

        return unzip_failed
    except:
        nzo.set_unpackstr('=> Unknown error while running unzip(): ' + \
                          'see logfile', actionname, 3)
        logging.error('[%s] Unknown error while' + \
                          ' running unzip() on %s',
                          __NAME__, nzo.get_filename())
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
    nzo.set_status("Repairing...")
    actionname = '[PAR-INFO] %s' % setname
    result = False
    readd = False
    try:
        parfile = os.path.join(workdir, parfile_nzf.get_filename())
        nzo.set_unpackstr('=> Scanning "%s"' % parfile, actionname, 1)

        joinables, zips, rars = build_filelists(workdir, None)

        old_dir_content = os.listdir(workdir)

        finished, readd, pars, datafiles = PAR_Verify(parfile, parfile_nzf, nzo,
                                                      actionname, joinables)

        if finished:
            result = True
            logging.info('[%s] Par verify finished ok on %s!', __NAME__,
                         parfile)

            # Remove this set so we don't try to check it again
            nzo.remove_parset(parfile_nzf.get_setname())
        else:
            logging.info('[%s] Par verify failed on %s!', __NAME__, parfile)

            if not readd:
                # Failed to repair -> remove this set
                nzo.remove_parset(parfile_nzf.get_setname())
            return readd, False

        if sabnzbd.PAR_CLEANUP:
            actionname = '[DEL-INFO] %s' % setname
            i = 0

            new_dir_content = os.listdir(workdir)

            for path in new_dir_content:
                if os.path.splitext(path)[1] == '.1' and path not in old_dir_content:
                    try:
                        path = os.path.join(workdir, path)

                        logging.info("[%s] Deleting %s", __NAME__, path)
                        os.remove(path)
                        i += 1
                    except:
                        logging.warning("[%s] Deleting %s failed!", __NAME__, path)

            path = os.path.join(workdir, setname + '.par2')
            path2 = os.path.join(workdir, setname + '.PAR2')

            if os.path.exists(path):
                try:
                    logging.info("[%s] Deleting %s", __NAME__, path)
                    os.remove(path)
                    i += 1
                except:
                    logging.warning("[%s] Deleting %s failed!", __NAME__, path)

            if os.path.exists(path2):
                try:
                    logging.info("[%s] Deleting %s", __NAME__, path2)
                    os.remove(path2)
                    i += 1
                except:
                    logging.warning("[%s] Deleting %s failed!", __NAME__, path2)

            try:
                logging.info("[%s] Deleting %s", __NAME__, parfile)
                os.remove(parfile)
                i += 1
            except OSError:
                logging.warning("[%s] Deleting %s failed", __NAME__, parfile)

            for filename in pars:
                filepath = os.path.join(workdir, filename)
                if os.path.exists(filepath):
                    logging.info("[%s] Deleting %s", __NAME__, filepath)
                    try:
                        os.remove(filepath)
                        i += 1
                    except OSError:
                        logging.warning("[%s] Deleting %s failed!", __NAME__,
                                        filepath)
            nzo.set_unpackstr("=> Deleted %d file(s)" % i, actionname, 1)
    except:
        nzo.set_unpackstr('=> Unknown error while running par2_repair, ' + \
                          'see logfile', actionname, 1)
        logging.error('[%s] Unknown error while' + \
                          ' running par2_repair on set %s',
                           __NAME__, setname)

    return readd, result


def PAR_Verify(parfile, parfile_nzf, nzo, actionname, joinables):
    
    #set the current nzo status to "Verifying...". Used in History
    nzo.set_status("Verifying...")
    start = time()
    command = ['%s' % PAR2_COMMAND, 'r', '%s' % parfile]

    for joinable in joinables:
        command.append(joinable)

    stup, need_shell, command, creationflags = build_command(command)

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

    lines = []
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
            nzo.set_unpackstr('=> Verified in %.1fs, all files correct' % \
                              (time() - start), actionname, 1)
            logging.info('[%s] Verified in %.1fs, all files correct', __NAME__,
                         time() - start)
            finished = 1

        elif line.startswith('Repair is required'):
            nzo.set_unpackstr('=> Verified in %.1fs, repair is required' % \
                              (time() - start), actionname, 1)
            logging.info('[%s] Verified in %.1fs, repair is required', __NAME__,
                          time() - start)
            start = time()
            verified = 1

        elif line.startswith('Main packet not found'):
            ## Initialparfile probaly didn't decode properly,
            logging.info("[%s] Main packet not found...", __NAME__)

            extrapars = parfile_nzf.get_extrapars()

            logging.info("[%s] %s", __NAME__, extrapars)

            ## Look for the smallest par2file
            block_table = {}
            for nzf in extrapars:
                block_table[int(nzf.get_blocks())] = nzf

            if block_table:
                nzf = block_table[min(block_table.keys())]

                logging.info("[%s] Found new par2file %s", __NAME__,
                             nzf.get_filename())

                nzo.add_parfile(nzf)
                ## mark for readd
                readd = True

        elif line.startswith('You need'):
            chunks = line.split()

            needed_blocks = int(chunks[2])

            logging.info('[%s] Need to fetch %s more blocks, checking blocks',
                         __NAME__, needed_blocks)

            avail_blocks = 0

            extrapars = parfile_nzf.get_extrapars()

            block_table = {}

            for nzf in extrapars:
                # Don't count extrapars that are completed already
                if nzf.completed():
                    continue

                blocks = int(nzf.get_blocks())

                avail_blocks += blocks

                if blocks not in block_table:
                    block_table[blocks] = []

                block_table[blocks].append(nzf)

            logging.info('[%s] %s blocks available', __NAME__, avail_blocks)


            force = False
            if (avail_blocks < needed_blocks) and (avail_blocks > 0):
                # Tell SAB that we always have enough blocks, so that
                # it will try to load all pars anyway
                nzo.set_unpackstr(\
                     '=> Not enough repair blocks, downloading all available (%d short)' % \
                     int(needed_blocks - avail_blocks), actionname, 1)
                nzo.set_status("Failed")
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

                logging.info('[%s] Added %s blocks to %s', __NAME__,
                             added_blocks, nzo.get_filename())

                if not force:
                    nzo.set_unpackstr('=> trying to fetch %s more blocks...' % \
                                      added_blocks, actionname, 1)
                    nzo.set_status("Fetching %s blocks..." % added_blocks)

            else:
                nzo.set_unpackstr(\
                     '=> Not enough repair blocks left (have: %s, need: %s)' % \
                     (avail_blocks, needed_blocks), actionname, 1)
                nzo.set_status("Failed")

        elif line.startswith('Repair is possible'):
            start = time()
            nzo.set_unpackstr('=> Repairing : %2d%%' % (0),
                              actionname, 1)

        elif line.startswith('Repairing:'):
            chunks = line.split()
            per = float(chunks[-1][:-1])
            nzo.set_unpackstr('=> Repairing : %2d%%' % (per),
                              actionname, 1)
            nzo.set_status("Repairing...")

        elif line.startswith('Repair complete'):
            nzo.set_unpackstr('=> Repaired in %.1fs' % (time() - start),
                              actionname, 1)
            logging.info('[%s] Repaired in %.1fs', __NAME__, time() - start)
            finished = 1

        # This has to go here, zorg
        elif not verified:
            if line.startswith('Verifying source files'):
                nzo.set_unpackstr('=> Verifying : 01/%02d' % verifytotal,
                                  actionname, 1)
                nzo.set_status("Verifying...")

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
                    nzo.set_unpackstr('=> Verifying : %02d/%02d' % \
                               (verifynum, verifytotal), actionname, 1)
                    nzo.set_status("Verifying...")
                datafiles.append(m.group(1))
                continue

            # Verify done
            m = re.match(r'There are (\d+) recoverable files', line)
            if m:
                verifytotal = int(m.group(1))

    p.wait()

    return (finished, readd, pars, datafiles)

#-------------------------------------------------------------------------------

def build_command(command):
    if os.name != "nt":
        if NICE_COMMAND:
            command.insert(0, NICE_COMMAND)
        need_shell = False
        stup = None
        creationflags = 0

    else:
        need_shell = False
        stup = subprocess.STARTUPINFO()
        stup.dwFlags = STARTF_USESHOWWINDOW
        stup.wShowWindow = SW_HIDE
        creationflags = IDLE_PRIORITY_CLASS

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
    aext = a.split('.')[-1]
    bext = b.split('.')[-1]

    if aext == bext:
        return cmp(a, b)
    elif aext == 'par2':
        return -1
    elif bext == 'par2':
        return 1

def build_filelists(workdir, workdir_complete):
    joinables, zips, rars = ([], [], [])

    filelist = []

    for root, dirs, files in os.walk(workdir):
        for _file in files:
            filelist.append(os.path.join(root, _file))

    if workdir_complete:
        for root, dirs, files in os.walk(workdir_complete):
            for _file in files:
                filelist.append(os.path.join(root, _file))

    joinables = [f for f in filelist if SPLITFILE_RE.search(f) and notrar(f)]

    zips = [f for f in filelist if ZIP_RE.search(f)]

    rars = [f for f in filelist if RAR_RE.search(f) and f not in joinables]

    logging.debug("[%s] build_filelists(): joinables: %s", __NAME__, joinables)
    logging.debug("[%s] build_filelists(): zips: %s", __NAME__, zips)
    logging.debug("[%s] build_filelists(): rars: %s", __NAME__, rars)

    return (joinables, zips, rars)

def notrar(f):
    logging.debug("[%s] notrar(): testing %s", __NAME__, f)
    try:
        _f = open(f, 'rb')
        header = _f.read(4)
        _f.close()
    except:
        logging.error("[%s] notrar(): reading %s failed", __NAME__, f)
        return False

    if header != 'Rar!':
        logging.debug("[%s] notrar(): joinable file %s", __NAME__, f)
        return True

    return False
