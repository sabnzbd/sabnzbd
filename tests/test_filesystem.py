#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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

    @set_platform("win32")
    def test_colon_handling_windows(self):
        assert filesystem.sanitize_filename("test:aftertest") == "test-aftertest"
        # They should act the same
        assert filesystem.sanitize_filename("test:aftertest") == filesystem.sanitize_foldername("test:aftertest")
        # TODO: Add a lot more tests here!

    @set_platform("darwin")
    def test_colon_handling_darwin(self):
        assert filesystem.sanitize_filename("test:aftertest") == "aftertest"

    @set_platform("linux")
    def test_colon_handling_other(self):
        assert filesystem.sanitize_filename("test:aftertest") == "test:aftertest"

    @set_platform("win32")
    def test_win_devices_on_win(self):
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename("aux.txt") == "_aux.txt"
        assert filesystem.sanitize_filename("txt.aux") == "txt.aux"
        assert filesystem.sanitize_filename("$mft") == "Smft"
        assert filesystem.sanitize_filename("a$mft") == "a$mft"

    @set_platform("linux")
    def test_win_devices_not_win(self):
        # Linux and Darwin are the same for this
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename("aux.txt") == "aux.txt"
        assert filesystem.sanitize_filename("txt.aux") == "txt.aux"
        assert filesystem.sanitize_filename("$mft") == "$mft"
        assert filesystem.sanitize_filename("a$mft") == "a$mft"


class TestSameFile:
    def test_nothing_in_common(self):
        assert 0 == filesystem.same_file("C:\\", "D:\\")
        assert 0 == filesystem.same_file("C:\\", "/home/test")
        assert 0 == filesystem.same_file("/home/", "/data/test")
        assert 0 == filesystem.same_file("/test/home/test", "/home/")

    def test_same(self):
        assert 1 == filesystem.same_file("/home/123", "/home/123")
        assert 1 == filesystem.same_file("D:\\", "D:\\")

    def test_subfolder(self):
        assert 2 == filesystem.same_file("\\\\?\\C:\\", "\\\\?\\C:\\Users\\")
        assert 2 == filesystem.same_file("/home/test123", "/home/test123/sub")

    @set_platform("win32")
    def test_capitalization(self):
        # Only matters on Windows/macOS
        assert 1 == filesystem.same_file("/HOME/123", "/home/123")
        assert 1 == filesystem.same_file("D:\\", "d:\\")
        assert 2 == filesystem.same_file("\\\\?\\c:\\", "\\\\?\\C:\\Users\\")
        assert 2 == filesystem.same_file("/HOME/test123", "/home/test123/sub")
