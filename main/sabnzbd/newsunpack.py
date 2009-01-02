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
from sabnzbd.misc import format_time_string
import sabnzbd.cfg as cfg

try:
    from win32con import SW_HIDE
    from win32process import STARTF_USESHOWWINDOW, IDLE_PRIORITY_CLASS
except ImportError:
    pass

# Define option handlers



RAR_RE = re.compile(r'\.(?P<ext>part\d*\.rar|rar|r\d\d|\d\d\d)$', re.I)
RAR_RE_V3 = re.compile(r'\.(?P<ext>part\d*)$', re.I)

LOADING_RE = re.compile(r'^Loading "(.+)"')
TARGET_RE = re.compile(r'^(?:File|Target): "(.+)" -')
EXTRACTFROM_RE = re.compile(r'^Extracting\sfrom\s(.+)')
SPLITFILE_RE = re.compile(r'\.(\d\d\d$)', re.I)
ZIP_RE = re.compile(r'\.(zip$)', re.I)
VOLPAR2_RE = re.compile(r'\.*vol[0-9]+\+[0-9]+\.par2', re.I)
TS_RE = re.compile(r'\.(\d+)\.(ts$)', re.I)

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

    try:
        p = subprocess.Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            startupinfo=stup, creationflags=creationflags)
    except WindowsError:
        return "Cannot run script %s\r\n" % extern_proc

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

def unpack_magic(nzo, workdir, workdir_complete, dele, joinables, zips, rars, ts):
    xjoinables, xzips, xrars, xts = build_filelists(workdir, workdir_complete)

    rerun = False
    newfiles = []
    error = False

    if cfg.enable_filejoin.get():
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
            nzo.set_action_line('', '')

    if cfg.enable_unrar.get():
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
            nzo.set_action_line('', '')

    if cfg.enable_unzip.get():
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
            nzo.set_action_line('', '')
            
    if cfg.enable_tsjoin.get():
        do_tsjoin = False
        for _ts in xts:
            if _ts not in ts:
                do_tsjoin = True
                rerun = True
                break

        if do_tsjoin:
            logging.info('[%s] TS Joining starting on %s', __NAME__, workdir)
            error, newf = file_join(nzo, workdir, workdir_complete, dele, xts)
            if newf:
                newfiles.extend(newf)
            logging.info('[%s] TS Joining finished on %s', __NAME__, workdir)
            nzo.set_action_line('', '')


    if rerun:
        z, y = unpack_magic(nzo, workdir, workdir_complete, dele, xjoinables,
                            xzips, xrars, xts)
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

        logging.debug("[%s] joinable_sets: %s", __NAME__, joinable_sets)

        for joinable_set in joinable_sets:
            try:
                expected_size = 0
                for i in xrange(len(joinable_sets[joinable_set])+1):
                    expected_size += i
                logging.debug("[%s] FJN, expsize: %s", __NAME__, expected_size)
    
                real_size = 0
                for joinable in joinable_sets[joinable_set]:
                    head, tail = os.path.splitext(joinable)
                    if tail == '.ts':
                        match, set, num = match_ts(joinable)
                        real_size += num
                    else:
                        real_size += int(tail[1:])
                logging.debug("[%s] FJN, realsize: %s", __NAME__, real_size)
    
                if real_size == expected_size:
                    joinable_sets[joinable_set].sort()
                    filename = joinable_set
    
                    # Check if par2 repaired this joinable set
                    if os.path.exists(filename):
                        logging.debug("file_join(): Skipping %s, (probably) joined by par2", filename)
                        if delete:
                            i = 0
                            for joinable in joinable_sets[joinable_set]:
                                if os.path.exists(joinable):
                                    logging.debug("[%s] Deleting %s", __NAME__, joinable)
                                    try:
                                        os.remove(joinable)
                                    except:
                                        pass
                                path1 = joinable + ".1"
                                if os.path.exists(path1):
                                    logging.debug("[%s] Deleting %s", __NAME__, path1)
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
                        logging.debug("[%s] Processing %s", __NAME__, joinable)
                        nzo.set_action_line('Joining', '%.0f%%' % perc)
                        f = open(joinable, 'rb')
                        joined_file.write(f.read())
                        f.close()
                        i += 1
                        if delete:
                            logging.debug("[%s] Deleting %s", __NAME__, joinable)
                            os.remove(joinable)
    
                    joined_file.flush()
                    joined_file.close()
                    nzo.set_unpack_info('filejoin', '[%s] Joined %s file%s' % (joinable_set, i, add_s(i)), set=joinable_set)
                    newfiles.append(joinable_set)
            except:
                msg = sys.exc_info()[1]
                nzo.set_fail_msg('File join failed, %s' % msg)
                nzo.set_unpack_info('filejoin', '[%s] Error "%s" while running file_join ' % (joinable_set, msg))
                logging.error('[%s] Error "%s" while' + \
                              ' running file_join on %s',
                              __NAME__, msg, nzo.get_filename())
                return True, []
                
        return False, newfiles
    except:
        msg = sys.exc_info()[1]
        nzo.set_fail_msg('File join failed, %s' % msg)
        nzo.set_unpack_info('filejoin', 'Error "%s" while running file_join ' % (msg))
        logging.error('[%s] Error "%s" while' + \
                      ' running file_join on %s',
                      __NAME__, msg, nzo.get_filename())
        return True, []
    

#------------------------------------------------------------------------------
# (Un)Rar Functions
#------------------------------------------------------------------------------

def rar_unpack(nzo, workdir, workdir_complete, delete, rars):
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
            # Run the RAR extractor
            rar_sets[rar_set].sort(rar_sort)

            rarpath = rar_sets[rar_set][0]


            extraction_path = workdir
            if workdir_complete:
                extraction_path = workdir_complete

            logging.info("[%s] Extracting rarfile %s (belonging to %s) to %s",
                         __NAME__, rarpath, rar_set, extraction_path)

            newfiles, rars = RAR_Extract(rarpath, len(rar_sets[rar_set]),
                                         nzo, rar_set, extraction_path)

            logging.debug('[%s] rar_unpack(): Rars: %s', __NAME__, rars)
            logging.debug('[%s] rar_unpack(): Newfiles: %s', __NAME__, newfiles)
            
            extracted_files.extend(newfiles)

            # Delete the old files if we have to
            if delete and newfiles:
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

            if not extracted_files:
                errors = True

        return errors, extracted_files
    except:
        msg = sys.exc_info()[1]
        nzo.set_fail_msg('Unpacking failed, %s' % msg)
        setname = nzo.get_filename()
        nzo.set_unpack_info('unpack', '[%s] Error "%s" while running rar_unpack' % (setname, msg))

        logging.error('[%s] Error "%s" while' + \
                          ' running rar_unpack on %s',
                          __NAME__, msg, setname)
        return True, ''

def RAR_Extract(rarfile, numrars, nzo, setname, extraction_path):
    start = time()

    logging.debug("[%s] RAR_Extract(): Extractionpath: %s", __NAME__,
                  extraction_path)

    try:
        zf = RarFile(rarfile)
        expected_files = zf.unamelist()
        zf.close()
    except:
        nzo.set_fail_msg('Failed opening main archive (encrypted or damaged)')
        nzo.set_unpack_info('unpack', '[%s] Failed opening main archive (encrypted or damaged)' % (setname), set=setname)

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

    nzo.set_action_line('Unpacking', '00/%02d' % (numrars))

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
            nzo.set_action_line('Unpacking', '%02d/%02d' % (curr, numrars))

        elif line.startswith('Cannot find volume'):
            filename = os.path.basename(TRANS(line[19:]))
            nzo.set_fail_msg('Unpacking failed, unable to find %s' % filename)
            nzo.set_unpack_info('unpack', '[%s] Error, unable to find "%s"' % (setname, filename), set=setname)
            logging.warning('[%s] ERROR: unable to find "%s"', __NAME__,
                                                                       filename)
            fail = 1

        elif line.endswith('- CRC failed'):
            filename = TRANS(line[:-12].strip())
            nzo.set_fail_msg('Unpacking failed, CRC error')
            nzo.set_unpack_info('unpack', '[%s] Error, CRC failed in "%s"' % (setname, filename), set=setname)
            logging.warning('[%s] ERROR: CRC failed in %s"', __NAME__, filename)
            fail = 1

        elif line.startswith('Write error'):
            nzo.set_fail_msg('Unpacking failed, write error or disk is full?')
            nzo.set_unpack_info('unpack', '[%s] Error writing to disk, disk full?' % (setname), set=setname)
            logging.warning('[%s] ERROR: write error (%s)', __NAME__, line[11:])
            fail = 1

        elif line.startswith('ERROR: '):
            nzo.set_fail_msg('Unpacking failed, see log')
            logging.warning('[%s] ERROR: %s', __NAME__, (line[7:]))
            nzo.set_unpack_info('unpack', '[%s] Error, %s' % (setname, line[7:]), set=setname)
            fail = 1

        elif line.startswith('Encrypted file:  CRC failed'):
            filename = TRANS(line[31:-23].strip())
            nzo.set_fail_msg('Unpacking failed, archive requires a password')
            nzo.set_unpack_info('unpack', '[%s][%s] Error, password required' % (setname, filename), set=setname)
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
        nzo.set_fail_msg('Unpacking failed, an expected file was not unpacked')
        nzo.set_unpack_info('unpack', 'ERROR: An expected file was not unpacked', set=setname)
        return ((), ())

    msg = 'Unpacked %d file%s/folder%s in %s' % (len(extracted), add_s(len(extracted)), add_s(len(extracted)), format_time_string(time() - start))
    nzo.set_unpack_info('unpack', '[%s] %s' % (setname, msg), set=setname)
    logging.info('[%s] %s', __NAME__, msg)

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
            logging.info("[%s] Starting extract on zipfile: %s ", __NAME__,
                         _zip)
            nzo.set_action_line('Unpacking', '%s' % _zip)

            extraction_path = workdir
            if workdir_complete:
                extraction_path = workdir_complete

            if ZIP_Extract(_zip, extraction_path):
                unzip_failed = True
            else:
                i += 1

        nzo.set_unpack_info('unpack', 'Unzipped %d file%s in %s' % (i,add_s(i), format_time_string(time() - tms)))

        # Delete the old files if we have to
        if delete and not unzip_failed:
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

        return unzip_failed
    except:
        msg = sys.exc_info()[1]
        nzo.set_fail_msg('Unpacking failed, %s' % msg)
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

    old_dir_content = os.listdir(workdir)

    nzo.set_status("Quick check...")
    nzo.set_action_line('Repair', 'Quick Checking')
    if QuickCheck(setname, nzo):
        logging.info("[%s] Quick-check for %s is OK, skipping repair",
                     __NAME__, setname)
        nzo.set_unpack_info('repair', '[%s] Quick Check OK' % setname, set=setname)
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
            nzo.set_action_line('Repair', 'Starting Repair')
            logging.info('[%s] Scanning "%s"' % (__NAME__, parfile))

            joinables, zips, rars, ts = build_filelists(workdir, None)

            finished, readd, pars, datafiles = PAR_Verify(parfile, parfile_nzf, nzo,
                                                          setname, joinables)

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
            nzo.set_fail_msg('Reparing failed, %s' % msg)
            logging.error('[%s] Error %s while running par2_repair on set %s',
                          __NAME__, msg, setname)
            return readd, result

    try:
        if cfg.enable_par_cleanup.get():
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
    except:
        msg = sys.exc_info()[1]
        nzo.set_fail_msg('Repairing failed, %s' % msg)
        logging.error('[%s] Error "%s" while' + \
                          ' running par2_repair on set %s',
                           __NAME__, msg, setname)

    return readd, result


def PAR_Verify(parfile, parfile_nzf, nzo, setname, joinables):

    #set the current nzo status to "Verifying...". Used in History
    nzo.set_status("Verifying...")
    start = time()

    odd = OddFiles(parfile)

    if cfg.par_option.get() and not (odd and PAR2C_COMMAND):
        command = [str(PAR2_COMMAND), 'r', str(cfg.par_option.get().strip()), parfile]
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
            nzo.set_unpack_info('repair', '[%s] Verified in %s, all files correct' % (setname, format_time_string(time() - start)), set=setname)
            logging.info('[%s] Verified in %s, all files correct', __NAME__,
                         format_time_string(time() - start))
            finished = 1

        elif line.startswith('Repair is required'):
            nzo.set_unpack_info('repair', '[%s] Verified in %s, repair is required' % (setname, format_time_string(time() - start)), set=setname)
            logging.info('[%s] Verified in %s, repair is required', __NAME__,
                          format_time_string(time() - start))
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
                nzo.set_fail_msg('Repair failed, not enough repair blocks (%d short)' % int(needed_blocks - avail_blocks))
                nzo.set_unpack_info('repair', '[%s] Repair failed, not enough repair blocks (%d short)' % (setname, int(needed_blocks - avail_blocks)), set=setname)
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
                    nzo.set_status("Fetching %s blocks..." % added_blocks)
                    nzo.set_action_line('Fetching', '%s blocks...' % added_blocks)

            else:
                nzo.set_fail_msg('Repair failed, not enough repair blocks (have: %s, need: %s)' % (avail_blocks, needed_blocks))
                nzo.set_unpack_info('repair', '[%s] Repair failed, not enough repair blocks, have: %s, need: %s' % (setname, avail_blocks, needed_blocks), set=setname)
                nzo.set_status("Failed")
                

        elif line.startswith('Repair is possible'):
            start = time()
            nzo.set_action_line('Repairing', '%2d%%' % (0))

        elif line.startswith('Repairing:'):
            chunks = line.split()
            per = float(chunks[-1][:-1])
            nzo.set_action_line('Repairing', '%2d%%' % (per))
            nzo.set_status("Repairing...")

        elif line.startswith('Repair complete'):
            nzo.set_unpack_info('repair', '[%s] Repaired in %s' % (setname, format_time_string(time() - start)), set=setname)
            logging.info('[%s] Repaired in %s', __NAME__, format_time_string(time() - start))
            finished = 1

        # This has to go here, zorg
        elif not verified:
            if line.startswith('Verifying source files'):
                nzo.set_action_line('Verifying', '01/%02d' % verifytotal)
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
                    nzo.set_action_line('Verifying', '%02d/%02d' % (verifynum, verifytotal))
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
        if IONICE_COMMAND and cfg.ionice.get().strip():
            lst = cfg.ionice.get().split()
            lst.reverse()
            for arg in lst:
                command.insert(0, arg)
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
    
    ts = [f for f in filelist if TS_RE.search(f) and f not in joinables]

    logging.debug("[%s] build_filelists(): joinables: %s", __NAME__, joinables)
    logging.debug("[%s] build_filelists(): zips: %s", __NAME__, zips)
    logging.debug("[%s] build_filelists(): rars: %s", __NAME__, rars)
    logging.debug("[%s] build_filelists(): ts: %s", __NAME__, ts)

    return (joinables, zips, rars, ts)

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

def add_s(i):
    if i > 1:
        return 's'
    else:
        return ''