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

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.misc import int_conv, clip_path, remove_all
from sabnzbd.newsunpack import build_command
from sabnzbd.postproc import prepare_extraction_path


if sabnzbd.WIN32:
    # Load the POpen from the fixed unicode-subprocess
    from sabnzbd.utils.subprocess_fix import Popen
else:
    # Load the regular POpen
    from subprocess import Popen

RAR_NR = re.compile(r'(.*?)(\.part(\d*).rar|\.r(\d*))$')


class DirectUnpacker(threading.Thread):

    def __init__(self, nzo):
        threading.Thread.__init__(self)

        self.nzo = nzo
        self.active_instance = None
        self.killed = False
        self.next_file_lock = threading.Condition()

        self.unpack_dir_info = None
        self.cur_setname = None
        self.cur_volume = 0

        self.success_sets = []

        self.next_sets = []

        nzo.direct_unpacker = self

    def stop(self):
        pass

    def save(self):
        pass

    def reset_active(self):
        self.active_instance = None
        self.cur_setname = None
        self.cur_volume = 0

    def check_requirements(self):
        if self.killed or not cfg.direct_unpack():
            return False
        return True

    def add(self, nzf):
        # Stop if something is wrong
        if not self.check_requirements():
            return

        # Analyze the input
        filename = nzf.filename.lower()
        nzf.setname, nzf.vol = analyze_rar_filename(filename)

        # Do we have a set yet?
        if not self.cur_setname:
            self.cur_setname = nzf.setname

        # Are we doing this set?
        if self.cur_setname == nzf.setname:
            # Is this the first one?
            if not self.cur_volume and self.have_next_volume():
                # Start the unrar command and the loop
                self.cur_volume = 1
                self.create_unrar_instance(nzf)
                self.start()
            else:
                # Wake up the thread to see if this is good to go
                with self.next_file_lock:
                    self.next_file_lock.notify()
        else:
            # Need to store this for the future
            self.next_sets.append(nzf)

    def run(self):
        # Input and output
        proc_stdout = self.active_instance.stdout
        proc_stdin = self.active_instance.stdin
        linebuf = ''
        unrar_log = []

        # Need to read char-by-char because there's no newline after new-disk message
        while 1:
            char = proc_stdout.read(1)
            linebuf += char

            if not char:
                # End of program
                break

            # Error? Let PP-handle it
            if linebuf.endswith('Cannot create'):
                self.abort()

            # Did we reach the end?
            if linebuf.endswith('All OK'):
                # Add to success
                self.success_sets.append(self.cur_setname)

                 # Is there another set to do?
                if self.next_sets:
                    self.reset_active()
                    nzf = self.next_sets.pop(0)
                    self.cur_setname = nzf.setname
                    self.create_unrar_instance(nzf)
                else:
                    break

            if linebuf.endswith('[C]ontinue, [Q]uit '):
                # Wait for the volume to appear
                while not self.have_next_volume():
                    with self.next_file_lock:
                        self.next_file_lock.wait()

                # Send "Enter" to proceed
                proc_stdin.write('\n')

                # Next volume
                self.cur_volume += 1

            if linebuf.endswith('\n'):
                print linebuf
                unrar_log.append(linebuf.strip())
                linebuf = ''

        # Add last line
        unrar_log.append(linebuf.strip())

    def have_next_volume(self):
        """ Check if next volume of set is available, start
            from the end of the list where latest completed files are """
        for nzf_search in reversed(self.nzo.finished_files):
            if nzf_search.setname == self.cur_setname and nzf_search.vol == self.cur_volume+1:
                return True
        return False

    def create_unrar_instance(self, rarfile_nzf):
        password = None
        rarfile_path = os.path.join(self.nzo.downpath, rarfile_nzf.filename)

        # Generate extraction path and save for post-proc
        self.unpack_dir_info = prepare_extraction_path(self.nzo)
        extraction_path, _, _, one_folder, _ = self.unpack_dir_info

        # Set options
        if password:
            password_command = '-p%s' % password
        else:
            password_command = '-p-'

        if one_folder or cfg.flat_unpack():
            action = 'e'
        else:
            action = 'x'

        if sabnzbd.WIN32:
            command = ['%s' % sabnzbd.newsunpack.RAR_COMMAND, action, '-vp', '-idp', '-o+', '-ai', password_command,
                       '%s' % clip_path(rarfile_path), '%s\\' % extraction_path]

        if cfg.ignore_unrar_dates():
            command.insert(3, '-tsm-')

        stup, need_shell, command, creationflags = build_command(command)
        self.active_instance = Popen(command, shell=need_shell, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    startupinfo=stup, creationflags=creationflags)

    def abort(self):
        """ Abort running instance and delete generated files """
        if not self.killed:
            self.killed = True
            # Abort Unrar
            if self.active_instance:
                self.active_instance.kill()
                # We need to wait for it to kill the process
                self.active_instance.wait()
            # No new sets
            self.next_sets = []
            # Remove files
            extraction_path, _, _, _, _ = self.unpack_dir_info
            remove_all(extraction_path, recursive=True)
            # Remove dir-info
            self.unpack_dir_info = None
            # Reset settings
            self.reset_active()


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
