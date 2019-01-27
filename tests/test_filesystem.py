#!/usr/bin/python3 -OO
# Copyright 2007-2019 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_misc - Testing functions in filesystem.py
"""

import sabnzbd.filesystem as filesystem

from tests.testhelper import *


class TestFileFolderNameSanitizer:

    def test_empty(self):
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_foldername(None) is None

    @set_platform('win32')
    def test_colon_handling_windows(self):
        assert filesystem.sanitize_filename('test:aftertest') == 'test3Aaftertest'

    @set_platform('darwin')
    def test_colon_handling_darwin(self):
        assert filesystem.sanitize_filename('test:aftertest') == 'aftertest'

    @set_platform('linux')
    def test_colon_handling_other(self):
        assert filesystem.sanitize_filename('test:aftertest') == 'test:aftertest'

    @set_platform('win32')
    def test_win_devices_on_win(self):
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename('aux.txt') == '_aux.txt'
        assert filesystem.sanitize_filename('txt.aux') == 'txt.aux'
        assert filesystem.sanitize_filename('$mft') == 'Smft'
        assert filesystem.sanitize_filename('a$mft') == 'a$mft'

    @set_platform('linux')
    def test_win_devices_not_win(self):
        # Linux and Darwin are the same for this
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename('aux.txt') == 'aux.txt'
        assert filesystem.sanitize_filename('txt.aux') == 'txt.aux'
        assert filesystem.sanitize_filename('$mft') == '$mft'
        assert filesystem.sanitize_filename('a$mft') == 'a$mft'


class TestFilesystemTest:
    @set_config({"fail_hopeless_jobs": True})
    def test_een(self):
        pass
