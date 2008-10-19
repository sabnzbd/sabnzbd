#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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
import sys
import re
import subprocess
import logging
import glob
from time import time
try:
    import Foundation #OSX
    import platform
except:
    pass

import sabnzbd
from sabnzbd.nzbstuff import SplitFileName
from sabnzbd.codecs import TRANS, unicode2local
from sabnzbd.utils.rarfile import is_rarfile, RarFile

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
VOLPAR2_RE = re.compile(r'\.*vol[0-9]+\+[0-9]+\.par2', re.I)

PAR2_COMMAND = None
PAR2C_COMMAND = None
RAR_COMMAND = None
NICE_COMMAND = None
ZIP_COMMAND = None
IONICE_COMMAND = None

def find_programs(curdir):
    """Find external programs
    """
    if sabnzbd.DARWIN:
        if platform.machine() == 'i386':
            p = os.path.abspath(curdir + '/osx/par2/par2')
        else:
            p = os.path.abspath(curdir + '/osx/par2/par2universal')

        if os.access(p, os.X_OK):
            sabnzbd.newsunpack.PAR2_COMMAND = p
        p = os.path.abspath(curdir + '/osx/unrar/unrar')
        if os.access(p, os.X_OK):
            sabnzbd.newsunpack.RAR_COMMAND = p

    if os.name == 'nt':
        p = os.path.abspath(curdir + '/win/par2/par2.exe')
        if os.access(p, os.X_OK):
            sabnzbd.newsunpack.PAR2_COMMAND = p
        p = os.path.abspath(curdir + '/win/par2/par2-classic.exe')
        if os.access(p, os.X_OK):
            sabnzbd.newsunpack.PAR2C_COMMAND = p
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
        findionice = ('ionice',)
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

            if not sabnzbd.newsunpack.IONICE_COMMAND:
                for _ionice in findionice:
                    ionice_path = os.path.join(path, _ionice)
                    ionice_path = os.path.abspath(ionice_path)
                    if os.access(ionice_path, os.X_OK):
                        sabnzbd.newsunpack.IONICE_COMMAND = ionice_path
                        break

            if not sabnzbd.newsunpack.ZIP_COMMAND:
                for _zip in findzip:
                    zip_path = os.path.join(path, _zip)
                    zip_path = os.path.abspath(zip_path)
                    if os.access(zip_path, os.X_OK):
                        sabnzbd.newsunpack.ZIP_COMMAND = zip_path
                        break


#------------------------------------------------------------------------------
def external_processing(extern_proc, complete_dir, filename, nicename, cat, group, status):

    name, msgid = SplitFileName(filename)
    command = [str(extern_proc), str(complete_dir), str(filename), \
               str(nicename), str(msgid), str(cat), str(group), str(status)]

    stup, need_shell, command, creationflags = build_command(command)

    logging.info('[%s] Running external script %s(%s, %s, %s, %s, %s, %s, %s)', __NAME__, \
                 extern_proc, complete_dir, filename, nicename, msgid, cat, group, status)

    p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         startupinfo=stup, creationflags=creationflags)

    output = p.stdout.read()
    p.wait()
    return output


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
        msg = sys.exc_info()[1]
        nzo.set_unpackstr('=> Error "%s" while running file_join' % msg, actionname, 4)
        logging.error('[%s] Error "%s" while' + \
                      ' running file_join on %s',
                      __NAME__, msg, nzo.get_filename())
        return True

#------------------------------------------------------------------------------
# (Un)Rar Functions
#------------------------------------------------------------------------------

def rar_unpack(nzo, workdir, workdir_complete, delete, rars):
    actionname = '[RAR-INFO]'
    try:
        errors = False
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
            actionname = '[RAR-INFO] %s' % rar_set
            # Run the RAR extractor
            rar_sets[rar_set].sort(rar_sort)

            rarpath = rar_sets[rar_set][0]


            extraction_path = workdir
            if workdir_complete:
                extraction_path = workdir_complete

            logging.info("[%s] Extracting rarfile %s (belonging to %s) to %s",
                         __NAME__, rarpath, rar_set, extraction_path)

            newfiles, rars = RAR_Extract(rarpath, len(rar_sets[rar_set]),
                                         nzo, actionname, extraction_path)

            logging.debug('[%s] rar_unpack(): Rars: %s', __NAME__, rars)
            logging.debug('[%s] rar_unpack(): Newfiles: %s', __NAME__, newfiles)
            
            extracted_files.extend(newfiles)

            # Delete the old files if we have to
            if delete and newfiles:
                actionname = '[DEL-INFO] %s' % rar_set
                i = 0
                for rar in rars:
                    logging.info("[%s] Deleting %s", __NAME__, rar)
                    try:
                        os.remove(rar)
                        i += 1
                    except OSError:
                        logging.warning("[%s] Deleting %s failed!", __NAME__,
                                        rar)

                    brokenrar = '%s.1' % (rar)

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

            if not extracted_files:
                errors = True

        return errors, extracted_files
    except:
        msg = sys.exc_info()[1]
        nzo.set_unpackstr('=> Error "%s" while running rar_unpack' % msg, actionname, 2)
        logging.error('[%s] Error "%s" while' + \
                          ' running rar_unpack on %s',
                          __NAME__, msg, nzo.get_filename())
        return True, ''

def RAR_Extract(rarfile, numrars, nzo, actionname, extraction_path):
    start = time()

    logging.debug("[%s] RAR_Extract(): Extractionpath: %s", __NAME__,
                  extraction_path)

    try:
        zf = RarFile(rarfile)
        expected_files = zf.unamelist()
        zf.close()
    except:
        nzo.set_unpackstr('=> Archive probably encrypted', actionname, 2)
        logging.info('[%s] Archive %s probably encrypted, skipping', __NAME__, rarfile)
        return ((), ())


    ############################################################################

    command = ['%s' % RAR_COMMAND, 'x', '-idp', '-o-', '-p-',
               '%s' % rarfile, '%s/' % extraction_path]

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
            filename = TRANS((re.search(EXTRACTFROM_RE, line).group(1)))
            if filename not in rarfiles:
                rarfiles.append(filename)
            curr += 1
            nzo.set_unpackstr('=> Unpacking : %02d/%02d' % (curr, numrars),
                              actionname, 2)

        elif line.startswith('Cannot find volume'):
            filename = os.path.basename(TRANS(line[19:]))
            nzo.set_unpackstr('=> ERROR: unable to find "%s"' % filename,
                              actionname, 2)
            logging.warning('[%s] ERROR: unable to find "%s"', __NAME__,
                                                                       filename)
            fail = 1

        elif line.endswith('- CRC failed'):
            filename = TRANS(line[:-12].strip())
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
            filename = TRANS(line[31:-23].strip())
            nzo.set_unpackstr(\
                '=> ERROR: CRC failed in "%s" - password incorrect?' % filename,
                actionname, 2)
            logging.warning('[%s] ERROR: encrypted file: "%s"', __NAME__,
                                                                       filename)
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


    all_found = True
    for path in expected_files:
        path = unicode2local(path)
        fullpath = os.path.join(extraction_path, path)
        if path.endswith('/') or os.path.exists(fullpath):
            logging.debug("[%s] Checking existance of %s", __NAME__, fullpath)
        else:
            all_found = False
            logging.warning("[%s] Missing expected file: %s => unrar error?", __NAME__, path)

    if not all_found:
        nzo.set_unpackstr('=> At least one file failed to be unpacked, skipping', actionname, 2)
        return ((), ())

    msg = 'Unpacked %d files/folders in %.1fs' % (len(extracted), time() - start)
    nzo.set_unpackstr('=> ' + msg , actionname, 2)
    logging.info('[%s] %s', __NAME__, msg)

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
        msg = sys.exc_info()[1]
        nzo.set_unpackstr('=> Error "%s" while running unzip()' % msg, actionname, 3)
        logging.error('[%s] Error "%s" while' + \
                          ' running unzip() on %s',
                          __NAME__, msg, nzo.get_filename())
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

    parfile = os.path.join(workdir, parfile_nzf.get_filename())
    actionname = '[PAR-INFO] %s' % setname

    nzo.set_status("Quick check...")
    nzo.set_unpackstr('=> Quick checking', actionname, 1)
    if QuickCheck(setname, nzo):
        logging.info("[%s] Quick-check for %s is OK, skipping repair",
                     __NAME__, setname)
        nzo.set_unpackstr('=> Quick check OK', actionname, 1)
        readd = False
        result = True
        # Poor man's list of other pars, should not be needed
        # but sometimes too many are downloaded
        pars = ParsOfSet(workdir, setname)

    else:

        nzo.set_status("Repairing...")
        result = False
        readd = False
        try:
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
        except:
            msg = sys.exc_info()[1]
            nzo.set_unpackstr('=> Error %s while running par2_repair' % msg, actionname, 1)
            logging.error('[%s] Error %s while running par2_repair on set %s',
                          __NAME__, msg, setname)
            return readd, result

    try:
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
                        logging.warning("[%s] Deleting %s failed!", __NAME__, filepath)
            nzo.set_unpackstr("=> Deleted %d file(s)" % i, actionname, 1)
    except:
        msg = sys.exc_info()[1]
        nzo.set_unpackstr('=> Error "%s" while running par2_repair' % msg, actionname, 1)
        logging.error('[%s] Error "%s" while' + \
                          ' running par2_repair on set %s',
                           __NAME__, msg, setname)

    return readd, result


def PAR_Verify(parfile, parfile_nzf, nzo, actionname, joinables):

    #set the current nzo status to "Verifying...". Used in History
    nzo.set_status("Verifying...")
    start = time()

    odd = OddFiles(parfile)

    if sabnzbd.PAR_OPTION and not (odd and PAR2C_COMMAND):
        command = [str(PAR2_COMMAND), 'r', str(sabnzbd.PAR_OPTION.strip()), parfile]
    elif odd and PAR2C_COMMAND:
        command = [str(PAR2C_COMMAND), 'r', parfile]
    else:
        command = [str(PAR2_COMMAND), 'r', parfile]

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
        if IONICE_COMMAND:
            command.insert(0, "-n7")
            command.insert(0, "-c2")
            command.insert(0, IONICE_COMMAND)
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
    aext = a.lower().split('.')[-1]
    bext = b.lower().split('.')[-1]

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


def QuickCheck(set, nzo):
    """ Check all on-the-fly md5sums of a set """

    md5pack = nzo.get_md5pack(set)
    if md5pack == None:
        return False

    result = False
    nzf_list = nzo.get_files()
    for file in md5pack:
        if sabnzbd.misc.OnCleanUpList(file, False):
            result = True
            continue
        found = False
        for nzf in nzf_list:
            if file == nzf.get_filename():
                found = True
                if nzf.md5sum == md5pack[file]:
                    logging.debug('[%s] Quick-check of file %s OK', __NAME__, file)
                    result = True
                else:
                    logging.debug('[%s] Quick-check of file %s failed!', __NAME__, file)
                    return False # When any file fails, just stop
                break
        if not found:
            logging.debug('[%s] Cannot Quick-check missing file %s!', __NAME__, file)
            return False # Missing file is failure
    return result


def ParsOfSet(wdir, setname):
    """ Return list of par2 files matching the set """

    list = []
    size = len(setname)

    for file in os.listdir(wdir):
        if VOLPAR2_RE.search(file[size:]):
            list.append(file)
    return list


def OddFiles(parfile):
    """ Return True if any name in the job contains high ASCII """

    path, name = os.path.split(parfile)
    for name in os.listdir(path):
        try:
            name.encode('Latin-1')
        except:
            return True
    return False
