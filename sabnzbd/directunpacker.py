#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
import threading
import subprocess
import logging

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.misc import int_conv, clip_path, remove_all, globber, format_time_string, has_win_device
from sabnzbd.encoding import unicoder
from sabnzbd.newsunpack import build_command
from sabnzbd.postproc import prepare_extraction_path
from sabnzbd.utils.diskspeed import diskspeedmeasure

if sabnzbd.WIN32:
    # Load the POpen from the fixed unicode-subprocess
    from sabnzbd.utils.subprocess_fix import Popen
else:
    # Load the regular POpen
    from subprocess import Popen

MAX_ACTIVE_UNPACKERS = 10
ACTIVE_UNPACKERS = []
CONCURRENT_LOCK = threading.RLock()

RAR_NR = re.compile(r'(.*?)(\.part(\d*).rar|\.r(\d*))$', re.IGNORECASE)


class DirectUnpacker(threading.Thread):

    def __init__(self, nzo):
        threading.Thread.__init__(self)

        self.nzo = nzo
        self.active_instance = None
        self.killed = False
        self.next_file_lock = threading.Condition(threading.RLock())

        self.unpack_dir_info = None
        self.cur_setname = None
        self.cur_volume = 0
        self.total_volumes = {}

        self.success_sets = []
        self.next_sets = []

        nzo.direct_unpacker = self

    def stop(self):
        pass

    def save(self):
        pass

    def release_concurrent_lock(self):
        """ Let other unpackers go """
        try:
            CONCURRENT_LOCK.release()
        except:
            pass

    def reset_active(self):
        self.active_instance = None
        self.cur_setname = None
        self.cur_volume = 0
        # Release lock to be sure
        self.release_concurrent_lock()

    def check_requirements(self):
        if self.killed or not self.nzo.unpack or cfg.direct_unpack() < 1 or sabnzbd.newsunpack.RAR_PROBLEM:
            return False
        return True

    def set_volumes_for_nzo(self):
        """ Loop over all files to detect the names """
        none_counter = 0
        found_counter = 0
        for nzf in self.nzo.files + self.nzo.finished_files:
            nzf.setname, nzf.vol = analyze_rar_filename(nzf.filename)
            # We matched?
            if nzf.setname:
                found_counter += 1
                if nzf.setname not in self.total_volumes:
                    self.total_volumes[nzf.setname] = 0
                self.total_volumes[nzf.setname] += 1
            else:
                none_counter += 1

        # Too much not found? Obfuscated, ignore results
        if none_counter > found_counter:
            self.total_volumes = {}

    def add(self, nzf):
        """ Add jobs and start instance of DirectUnpack """
        if not cfg.direct_unpack_tested():
            test_disk_performance()

        # Stop if something is wrong
        if not self.check_requirements():
            return

        # Is this the first set?
        if not self.cur_setname:
            self.set_volumes_for_nzo()
            self.cur_setname = nzf.setname

        # Analyze updated filenames
        nzf.setname, nzf.vol = analyze_rar_filename(nzf.filename)

        # Are we doing this set?
        if self.cur_setname == nzf.setname:
            logging.debug('DirectUnpack queued %s for %s', nzf.filename, self.cur_setname)
            # Is this the first one of the first set?
            if not self.active_instance and not self.is_alive() and self.have_next_volume():
                # Too many runners already?
                if len(ACTIVE_UNPACKERS) >= MAX_ACTIVE_UNPACKERS:
                    logging.info('Too many DirectUnpackers currently to start %s', self.cur_setname)
                    return

                # Start the unrar command and the loop
                self.create_unrar_instance(nzf)
                self.start()
        elif not any(test_nzf.setname == nzf.setname for test_nzf in self.next_sets):
            # Need to store this for the future, only once per set!
            self.next_sets.append(nzf)

        # Wake up the thread to see if this is good to go
        with self.next_file_lock:
            self.next_file_lock.notify()

    def run(self):
        # Input and output
        linebuf = ''
        unrar_log = []

        # Need to read char-by-char because there's no newline after new-disk message
        while 1:
            if not self.active_instance:
                break

            char = self.active_instance.stdout.read(1)
            linebuf += char

            if not char:
                # End of program
                break

            # Error? Let PP-handle it
            if linebuf.endswith(('ERROR: ', 'Cannot create', 'in the encrypted file', 'CRC failed', \
                    'checksum failed', 'You need to start extraction from a previous volume',  \
                    'password is incorrect', 'Write error', 'checksum error', \
                    'start extraction from a previous volume')):
                logging.info('Error in DirectUnpack of %s', self.cur_setname)
                self.abort()

            # Did we reach the end?
            if linebuf.endswith('All OK'):
                # Add to success
                self.success_sets.append(self.cur_setname)
                logging.info('DirectUnpack completed for %s', self.cur_setname)

                # Make sure to release the lock
                self.release_concurrent_lock()

                # Are there more files left?
                if self.nzo.files:
                    with self.next_file_lock:
                        self.next_file_lock.wait()

                # Is there another set to do?
                if self.next_sets:
                    # Write current log
                    unrar_log.append(linebuf.strip())
                    linebuf = ''
                    logging.debug('DirectUnpack Unrar output %s', '\n'.join(unrar_log))
                    unrar_log = []

                    # Start new instance
                    nzf = self.next_sets.pop(0)
                    self.reset_active()
                    self.cur_setname = nzf.setname
                    # Wait for the 1st volume to appear
                    self.wait_for_next_volume()
                    self.create_unrar_instance(nzf)
                else:
                    break

            if linebuf.endswith('[C]ontinue, [Q]uit '):
                # Next one can go now
                self.release_concurrent_lock()

                # Wait for the next one..
                self.wait_for_next_volume()

                # Send "Enter" to proceed, only 1 at a time via lock
                CONCURRENT_LOCK.acquire()
                # Possible that the instance was deleted while locked
                if not self.killed:
                    # Next volume
                    self.cur_volume += 1
                    self.active_instance.stdin.write('\n')
                    self.nzo.set_action_line(T('Unpacking'), self.get_formatted_stats())
                    logging.info('DirectUnpacked volume %s for %s', self.cur_volume, self.cur_setname)

            if linebuf.endswith('\n'):
                unrar_log.append(linebuf.strip())
                linebuf = ''

        # Add last line
        unrar_log.append(linebuf.strip())
        logging.debug('DirectUnpack Unrar output %s', '\n'.join(unrar_log))

        # Save information if success
        if self.success_sets:
            msg = T('Unpacked %s files/folders in %s') % (len(globber(self.unpack_dir_info[0])), format_time_string(0))
            self.nzo.set_unpack_info('Unpack', '[%s] %s' % (unicoder(self.cur_setname), msg))

        # Make more space
        self.reset_active()
        ACTIVE_UNPACKERS.remove(self)

        # Make sure to release the lock
        self.release_concurrent_lock()

    def have_next_volume(self):
        """ Check if next volume of set is available, start
            from the end of the list where latest completed files are """
        for nzf_search in reversed(self.nzo.finished_files):
            if nzf_search.setname == self.cur_setname and nzf_search.vol == self.cur_volume+1:
                return True
        return False

    def wait_for_next_volume(self):
        """ Wait for the correct volume to appear
            But stop if it was killed or the NZB is done """
        while not self.have_next_volume() and not self.killed and self.nzo.files:
            with self.next_file_lock:
                self.next_file_lock.wait()

    def create_unrar_instance(self, rarfile_nzf):
        """ Start the unrar instance using the user's options """
        # Generate extraction path and save for post-proc
        if not self.unpack_dir_info:
            self.unpack_dir_info = prepare_extraction_path(self.nzo)
        extraction_path, _, _, one_folder, _ = self.unpack_dir_info

        # Set options
        if self.nzo.password:
            password_command = '-p%s' % self.nzo.password
        else:
            password_command = '-p-'

        if one_folder or cfg.flat_unpack():
            action = 'e'
        else:
            action = 'x'

        # Generate command
        rarfile_path = os.path.join(self.nzo.downpath, rarfile_nzf.filename)
        if sabnzbd.WIN32:
            if not has_win_device(rarfile_path):
                command = ['%s' % sabnzbd.newsunpack.RAR_COMMAND, action, '-vp', '-idp', '-o+', '-ai', password_command,
                           '%s' % clip_path(rarfile_path), clip_path(extraction_path)]
            else:
                # Need long-path notation in case of forbidden-names
                command = ['%s' % sabnzbd.newsunpack.RAR_COMMAND, action, '-vp', '-idp', '-o+', '-ai', password_command,
                           '%s' % clip_path(rarfile_path), '%s\\' % extraction_path]
        else:
            # Don't use "-ai" (not needed for non-Windows)
            command = ['%s' % sabnzbd.newsunpack.RAR_COMMAND, action, '-vp', '-idp', '-o+', password_command,
                       '%s' % rarfile_path, '%s/' % extraction_path]

        if cfg.ignore_unrar_dates():
            command.insert(3, '-tsm-')

        stup, need_shell, command, creationflags = build_command(command)
        logging.debug('Running unrar for DirectUnpack %s', command)

        # Aquire lock and go
        self.active_instance = Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    startupinfo=stup, creationflags=creationflags)
        # Add to runners
        ACTIVE_UNPACKERS.append(self)

        # Doing the first
        logging.info('DirectUnpacked volume %s for %s', self.cur_volume, self.cur_setname)

    def abort(self):
        """ Abort running instance and delete generated files """
        if not self.killed:
            logging.info('Aborting DirectUnpack for %s', self.cur_setname)
            self.killed = True

            # Abort Unrar
            if self.active_instance:
                self.active_instance.kill()
                # We need to wait for it to kill the process
                self.active_instance.wait()

            # Wake up the thread
            with self.next_file_lock:
                self.next_file_lock.notify()

            # No new sets
            self.next_sets = []
            self.success_sets = []

            # Remove files
            if self.unpack_dir_info:
                extraction_path, _, _, _, _ = self.unpack_dir_info
                remove_all(extraction_path, recursive=True)
                # Remove dir-info
                self.unpack_dir_info = None

            # Reset settings
            self.reset_active()

    def get_formatted_stats(self):
        """ Get percentage or number of rar's done """
        if self.cur_setname and self.cur_setname in self.total_volumes:
            # This won't work on obfuscated posts
            if self.total_volumes[self.cur_setname] > self.cur_volume and self.cur_volume:
                return '%.0f%%' % (100*float(self.cur_volume)/self.total_volumes[self.cur_setname])
        return self.cur_volume


def analyze_rar_filename(filename):
    """ Extract volume number and setname from rar-filenames
        Both ".part01.rar" and ".r01" """
    m = RAR_NR.search(filename)
    if m:
        if m.group(4):
            # Special since starts with ".rar", ".r00"
            return m.group(1), int_conv(m.group(4)) + 2
        return m.group(1), int_conv(m.group(3))
    else:
        # Detect if first of "rxx" set
        if filename.endswith('.rar') and '.part' not in filename:
            return os.path.splitext(filename)[0], 1
    return None, None


def abort_all():
    """ Abort all running DirectUnpackers """
    logging.info('Aborting all DirectUnpackers')
    for direct_unpacker in ACTIVE_UNPACKERS:
        direct_unpacker.abort()


def test_disk_performance():
    """ Test the incomplete-dir performance and enable
        Direct Unpack if good enough (> 60MB/s)
    """
    if diskspeedmeasure(sabnzbd.cfg.download_dir.get_path()) > 60:
        cfg.direct_unpack.set(True)
        logging.warning(T('Enabled Direct Unpack:') + ' ' + T('Jobs will start unpacking during the download, reduces post-processing time but requires capable hard drive. Only works for jobs that do not need repair.'))
    cfg.direct_unpack_tested.set(True)
