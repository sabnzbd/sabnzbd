#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
tests.test_filesystem - Testing functions in filesystem.py
"""

import datetime
import errno
import io
import pickle
import stat
import sys
import os
import shutil
import time
import unicodedata
from pathlib import Path
import tempfile
from random import choice, randint
from unittest import mock

import pytest
from pyfakefs.helpers import set_uid

from tests.testhelper import SAB_DATA_DIR

import sabnzbd
import sabnzbd.cfg
from sabnzbd import cfg
import sabnzbd.filesystem as filesystem
from sabnzbd.constants import DEF_FOLDER_MAX, DEF_FILE_MAX, JOB_ADMIN

# Set the global uid for fake filesystems to a non-root user;
# by default this depends on the user running pytest.
global_uid = 1000
set_uid(global_uid)


class TestFileFolderNameSanitizer:
    def test_empty(self):
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_foldername(None) is None

    @pytest.mark.platform("win32")
    def test_colon_handling_windows(self):
        assert filesystem.sanitize_filename("test:aftertest") == "test_aftertest"
        assert filesystem.sanitize_filename(":") == "_"
        assert filesystem.sanitize_filename("test:") == "test_"
        assert filesystem.sanitize_filename("test: ") == "test_"
        # They should act the same
        assert filesystem.sanitize_filename("test:aftertest") == filesystem.sanitize_foldername("test:aftertest")

    @pytest.mark.platform("macos")
    def test_colon_handling_macos(self):
        assert filesystem.sanitize_filename("test:aftertest") == "test_aftertest"
        assert filesystem.sanitize_filename(":aftertest") == "_aftertest"
        assert filesystem.sanitize_filename("::aftertest") == "__aftertest"
        assert filesystem.sanitize_filename(":after:test") == "_after_test"
        # Empty after sanitising with macos colon handling
        assert filesystem.sanitize_filename(":") == "_"
        assert filesystem.sanitize_filename("test:") == "test_"
        assert filesystem.sanitize_filename("test: ") == "test_"

    @pytest.mark.platform("linux")
    def test_colon_handling_other(self):
        assert filesystem.sanitize_filename("test:aftertest") == "test:aftertest"
        assert filesystem.sanitize_filename(":") == ":"
        assert filesystem.sanitize_filename("test:") == "test:"
        assert filesystem.sanitize_filename("test: ") == "test:"

    @pytest.mark.platform("win32")
    def test_win_devices_on_win(self):
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename("aux.txt") == "_aux.txt"
        assert filesystem.sanitize_filename("txt.aux") == "txt.aux"
        assert filesystem.sanitize_filename("$mft") == "Smft"
        assert filesystem.sanitize_filename("a$mft") == "a$mft"

    @pytest.mark.platform("linux")
    def test_win_devices_not_win(self):
        # Linux and macOS are the same for this
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename("aux.txt") == "aux.txt"
        assert filesystem.sanitize_filename("txt.aux") == "txt.aux"
        assert filesystem.sanitize_filename("$mft") == "$mft"
        assert filesystem.sanitize_filename("a$mft") == "a$mft"

    @pytest.mark.platform("win32")
    def test_file_illegal_chars_win32(self):
        assert filesystem.sanitize_filename("test" + filesystem.CH_ILLEGAL_WIN + "aftertest") == (
            "test" + (len(filesystem.CH_ILLEGAL_WIN) * "_") + "aftertest"
        )
        assert (
            filesystem.sanitize_filename("test" + chr(0) + chr(1) + chr(15) + chr(31) + "aftertest")
            == "test____aftertest"
        )

    @pytest.mark.platform("win32")
    def test_folder_illegal_chars_win32(self):
        assert (
            filesystem.sanitize_foldername("test" + chr(0) + chr(9) + chr(13) + chr(31) + "aftertest")
            == "test____aftertest"
        )

    @pytest.mark.platform("linux")
    def test_file_illegal_chars_linux(self):
        assert filesystem.sanitize_filename("test/aftertest") == "test_aftertest"
        assert filesystem.sanitize_filename("/test") == "_test"
        assert filesystem.sanitize_filename("test/") == "test_"
        assert filesystem.sanitize_filename(r"/test\/aftertest/") == r"_test\_aftertest_"
        assert filesystem.sanitize_filename("/") == "_"
        assert filesystem.sanitize_filename("///") == "___"
        assert filesystem.sanitize_filename("../") == ".._"
        assert filesystem.sanitize_filename("../test") == ".._test"

    @pytest.mark.parametrize("platform", ["win32", "macos", "linux"])
    @pytest.mark.platform()
    def test_file_allow_subdirs(self, platform):
        """Par2 uses "/" to separate sub-directories, no matter which platform created the set"""
        assert filesystem.sanitize_filename("sub/test.rar", allow_subdirs=True) == os.path.join("sub", "test.rar")
        assert filesystem.sanitize_filename("sub/deeper/test.rar", allow_subdirs=True) == os.path.join(
            "sub", "deeper", "test.rar"
        )
        # No sub-directory at all, or nothing but separators
        assert filesystem.sanitize_filename("test.rar", allow_subdirs=True) == "test.rar"
        assert filesystem.sanitize_filename("a//b.rar", allow_subdirs=True) == os.path.join("a", "b.rar")
        assert filesystem.sanitize_filename("sub/./test.rar", allow_subdirs=True) == os.path.join("sub", "test.rar")
        # Every part is sanitized on its own, chr(0) is illegal on all platforms
        assert filesystem.sanitize_filename("sub" + chr(0) + "1/test" + chr(0) + "2.rar", allow_subdirs=True) == (
            os.path.join("sub_1", "test_2.rar")
        )

    @pytest.mark.parametrize(
        "hostile_name",
        [
            "/test.rar",
            "//test.rar",
            "../test.rar",
            "../../../../../../etc/shadow",
            "sub/../../test.rar",
            "sub/../../../sub/test.rar",
            "./../test.rar",
            "../..",
            "../",
            "/",
            "//",
            "/../",
            "...",
            "....",
        ],
    )
    @pytest.mark.parametrize("platform", ["win32", "macos", "linux"])
    @pytest.mark.platform()
    def test_file_allow_subdirs_cannot_escape(self, platform, hostile_name):
        """Whatever the par2 claims, the result has to stay inside the folder it is used in.
        Joining it onto any base directory must never point above that base."""
        result = filesystem.sanitize_filename(hostile_name, allow_subdirs=True)

        assert result, "an empty result would resolve to the base directory itself"
        assert not os.path.isabs(result)
        assert os.pardir not in result.split(os.sep)

        # The real test: it cannot climb out of whatever it gets joined to
        base = os.path.join(os.sep + "downloads", "incomplete", "job")
        resolved = os.path.normpath(os.path.join(base, result))
        assert resolved.startswith(base + os.sep), "%s escaped to %s" % (hostile_name, resolved)

    @pytest.mark.parametrize(
        "hostile_name",
        [
            JOB_ADMIN,
            JOB_ADMIN + "/__verified__",
            JOB_ADMIN.lower() + "/__verified__",
            "sub/" + JOB_ADMIN + "/__verified__",
            JOB_ADMIN + "/deeper/__verified__",
        ],
    )
    @pytest.mark.parametrize("platform", ["win32", "macos", "linux"])
    @pytest.mark.platform()
    def test_file_allow_subdirs_cannot_enter_admin(self, platform, hostile_name):
        """The admin folder is pickle-loaded, so a par2 name must never point into it"""
        result = filesystem.sanitize_filename(hostile_name, allow_subdirs=True)

        assert result, "an empty result would resolve to the base directory itself"
        assert JOB_ADMIN.lower() not in result.lower().split(os.sep)

    @pytest.mark.platform("linux")
    def test_folder_illegal_chars_linux(self):
        assert filesystem.sanitize_foldername('test"aftertest') == "test_aftertest"
        assert filesystem.sanitize_foldername("test:") == "test_"
        assert filesystem.sanitize_foldername("test<>?*|aftertest") == "test<>?*|aftertest"

    @pytest.mark.platform("linux")
    def test_legal_chars_linux(self):
        # Illegal on Windows but not on Linux, unless sanitize_safe is active.
        # Don't bother with '/' which is illegal in filenames on all platforms.
        char_ill = filesystem.CH_ILLEGAL_WIN.replace("/", "")
        assert filesystem.sanitize_filename("test" + char_ill + "aftertest") == ("test" + char_ill + "aftertest")
        for char in char_ill:
            # Try at start, middle, and end of a filename.
            assert filesystem.sanitize_filename("test" + char * 2 + "aftertest") == ("test" + char * 2 + "aftertest")
            assert filesystem.sanitize_filename("test" + char * 2) == ("test" + char * 2).strip()
            assert filesystem.sanitize_filename(char * 2 + "test") == (char * 2 + "test").strip()

    @pytest.mark.platform("linux")
    @pytest.mark.config({"sanitize_safe": True})
    def test_sanitize_safe_linux(self):
        # Set sanitize_safe to on, simulating Windows-style restrictions.
        assert filesystem.sanitize_filename("test" + filesystem.CH_ILLEGAL_WIN + "aftertest") == (
            "test" + (len(filesystem.CH_ILLEGAL_WIN) * "_") + "aftertest"
        )
        for index in range(0, len(filesystem.CH_ILLEGAL_WIN)):
            char_ill = filesystem.CH_ILLEGAL_WIN[index]
            assert filesystem.sanitize_filename("test" + char_ill * 2 + "aftertest") == ("test__aftertest")
            # Illegal chars that also get caught by strip() never make it far
            # enough to be replaced by their legal equivalents if they appear
            # on either end of the filename.
            if char_ill.strip():
                assert filesystem.sanitize_filename("test" + char_ill * 2) == "test__"
                assert filesystem.sanitize_filename(char_ill * 2 + "test") == "__test"

    def test_nfc_normalization_filename(self):
        """sanitize_filename must normalize Unicode to NFC (fixes issues #1633 and #2858).

        macOS decomposes Unicode to NFD when returning filenames from the filesystem.
        par2 files, yEnc headers, and NZBs typically carry NFC. Without normalization,
        visually identical filenames compare unequal, causing double-unpacking and
        inconsistent sort paths when %fn (disk) and %title (parsed) are combined.
        """
        # NFD: 'e' + U+0300 (combining grave), 'o' + U+0308 (combining diaeresis)
        nfd_name = "fre\u0300nch_german_demo\u0308.mkv"
        # NFC: precomposed è (U+00E8) and ö (U+00F6)
        nfc_name = "frènch_german_demö.mkv"

        assert nfd_name != nfc_name, "pre-condition: NFD and NFC byte representations differ"
        result = filesystem.sanitize_filename(nfd_name)
        assert result == nfc_name
        assert unicodedata.is_normalized("NFC", result)

        # NFC input must pass through unchanged (idempotent)
        assert filesystem.sanitize_filename(nfc_name) == nfc_name

    def test_nfc_normalization_foldername(self):
        """sanitize_foldername must normalize Unicode to NFC (fixes issues #1633 and #2858)."""
        nfd_folder = "Mo\u0308vie"  # NFD: 'o' + U+0308 (combining diaeresis)
        nfc_folder = "Möwie"  # NFC: precomposed ö (U+00F6)
        # Correct expected NFC for "Mo" + combining-diaeresis + "vie"
        nfc_folder = "M\u00f6vie"

        assert nfd_folder != nfc_folder, "pre-condition: NFD and NFC differ"
        result = filesystem.sanitize_foldername(nfd_folder)
        assert result == nfc_folder
        assert unicodedata.is_normalized("NFC", result)

        # NFC input must pass through unchanged (idempotent)
        assert filesystem.sanitize_foldername(nfc_folder) == nfc_folder

    def test_filename_dot(self):
        # All dots should survive in filenames
        assert filesystem.sanitize_filename(".test") == ".test"
        assert filesystem.sanitize_filename("..test") == "..test"
        assert filesystem.sanitize_filename("test.") == "test."
        assert filesystem.sanitize_filename("test..") == "test.."
        assert filesystem.sanitize_filename("test.aftertest") == "test.aftertest"
        assert filesystem.sanitize_filename("test..aftertest") == "test..aftertest"
        assert filesystem.sanitize_filename("test.aftertest.") == "test.aftertest."
        assert filesystem.sanitize_filename("test.aftertest..") == "test.aftertest.."

    def test_foldername_dot(self):
        # Dot should be removed from the end of directory names only
        assert filesystem.sanitize_foldername(".test") == ".test"
        assert filesystem.sanitize_foldername("..test") == "..test"
        assert filesystem.sanitize_foldername("test.") == "test"
        assert filesystem.sanitize_foldername("test..") == "test"
        assert filesystem.sanitize_foldername("test.aftertest") == "test.aftertest"
        assert filesystem.sanitize_foldername("test..aftertest") == "test..aftertest"
        assert filesystem.sanitize_foldername("test.aftertest.") == "test.aftertest"
        assert filesystem.sanitize_foldername("test.aftertest..") == "test.aftertest"
        assert filesystem.sanitize_foldername("test. aftertest. . . .") == "test. aftertest"
        assert filesystem.sanitize_foldername("/test/this.") == "_test_this"
        assert filesystem.sanitize_foldername("/test./this.") == "_test._this"
        assert filesystem.sanitize_foldername("/test. /this . ") == "_test. _this"

    def test_long_foldername(self):
        # Note: some filesystem can handle up to 255 UTF chars (which is more than 255 bytes) in the foldername,
        # but we stay on the safe side: max DEF_FILE_MAX bytes
        assert len(filesystem.sanitize_foldername("test" * 100)) == DEF_FOLDER_MAX
        assert len(filesystem.sanitize_foldername("a" * DEF_FOLDER_MAX)) == DEF_FOLDER_MAX
        assert len(filesystem.sanitize_foldername("a" * (DEF_FOLDER_MAX + 1))) == DEF_FOLDER_MAX

        # Adapted from filename tests

        # PART 1: Base cases: Nothing should happen:
        # normal filename
        name = "a" * 200
        sanitizedname = filesystem.sanitize_foldername(name)
        assert sanitizedname == name

        # Unicode / UTF8 is OK ... as total filename length is not too long
        name = "BASE" + "你" * 50 + "blabla"
        sanitizedname = filesystem.sanitize_foldername(name)
        assert sanitizedname == name

        # PART 2: base truncating
        name = "BASE" + "a" * 300
        sanitizedname = filesystem.sanitize_foldername(name)
        assert len(sanitizedname) <= DEF_FOLDER_MAX
        assert sanitizedname.startswith("BASEaaaaaaaaaaaaaaa")

        # PART 3: more exotic cases

        # insert NON-ASCII chars, which should stay in place because overall length is no problem
        name = "aaaa" + 10 * chr(188) + 10 * chr(222) + "bbbb"
        sanitizedname = filesystem.sanitize_foldername(name)
        assert sanitizedname == name

        # insert NON-ASCII chars
        name = "aaaa" + 200 * chr(188) + 200 * chr(222)
        sanitizedname = filesystem.sanitize_foldername(name)
        assert (
            sanitizedname
            == "aaaa¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼"
        )

        # Unicode / UTF8 ... total filename length might be too long for certain filesystems
        name = "BASE" + "你" * 200
        sanitizedname = filesystem.sanitize_foldername(name)
        assert sanitizedname.startswith("BASE")
        assert sanitizedname.endswith("你")

    def test_filename_empty_result(self):
        # Nothing remains after sanitizing the filename
        assert filesystem.sanitize_filename("\n") == "unknown"
        assert filesystem.sanitize_filename("\r\n") == "unknown"
        assert filesystem.sanitize_filename("\n\r") == "unknown"
        assert filesystem.sanitize_filename("\t\t\t") == "unknown"
        assert filesystem.sanitize_filename(" ") == "unknown"
        assert filesystem.sanitize_filename("  ") == "unknown"

    def test_foldername_empty_result(self):
        # Nothing remains after sanitizing the foldername
        assert filesystem.sanitize_foldername("\n") == "unknown"
        assert filesystem.sanitize_foldername("\r\n") == "unknown"
        assert filesystem.sanitize_foldername("\n\r") == "unknown"
        assert filesystem.sanitize_foldername("\t\t\t") == "unknown"
        assert filesystem.sanitize_foldername(" ") == "unknown"
        assert filesystem.sanitize_foldername("  ") == "unknown"
        assert filesystem.sanitize_foldername(" . .") == "unknown"

    def test_filename_too_long(self):
        # Note: some filesystem can handle up to 255 UTF chars (which is more than 255 bytes) in the filename,
        # but we stay on the safe side: max DEF_FILE_MAX bytes

        # PART 1: Base cases: Nothing should happen:

        # normal filename
        name = "a" * 200 + ".ext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname == name

        # Unicode / UTF8 is OK ... as total filename length is not too long
        name = "BASE" + "你" * 50 + "blabla.ext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname == name

        # filename with very long extension, but total filename is no problem, so no change
        name = "hello.ext" + "e" * 200
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname == name  # no change

        # PART 2: base truncating

        name = "BASE" + "a" * 300 + ".mylongext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert len(sanitizedname) <= DEF_FILE_MAX
        assert sanitizedname.startswith("BASEaaaaaaaaaaaaaaa")
        assert sanitizedname.endswith(".mylongext")

        # too long filename, so truncate keeping the start of name and ext should stay the same
        name = "BASE" + "a" * 200 + ".EXT" + "e" * 200
        sanitizedname = filesystem.sanitize_filename(name)
        assert len(sanitizedname) <= DEF_FILE_MAX
        newname, newext = os.path.splitext(sanitizedname)
        assert newname.startswith("BASEaaaaa")
        assert newext.startswith(".EXTeeeee")

        # PART 3: more exotic cases

        # insert NON-ASCII chars, which should stay in place because overall length is no problem
        name = "aaaa" + 10 * chr(188) + 10 * chr(222) + "bbbb.ext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname == name

        # insert NON-ASCII chars
        name = "aaaa" + 200 * chr(188) + 200 * chr(222) + "bbbb.ext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert (
            sanitizedname
            == "aaaa¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼¼.ext"
        )

        # Unicode / UTF8 ... total filename length might be too long for certain filesystems
        name = "BASE" + "你" * 200 + ".ext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname.startswith("BASE")
        assert sanitizedname.endswith(".ext")

        # Linux / POSIX: a hidden file (no extension), with size 200, so do not truncate at all
        name = "." + "a" * 200
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname == name  # no change


@pytest.mark.platform("win32")
@pytest.mark.fake_fs(
    {
        # Disable randomisation of directory listings
        "shuffle_listdir_results": False,
    }
)
class TestSanitizeFiles:
    def test_sanitize_files_input(self):
        assert [] == filesystem.sanitize_files(folder=None)
        assert [] == filesystem.sanitize_files(filelist=None)
        assert [] == filesystem.sanitize_files(folder=None, filelist=None)

    @pytest.mark.config({"sanitize_safe": True})
    def test_sanitize_files(self, fake_fs):
        # The very specific tests of sanitize_filename() are above
        # Here we just want to see that sanitize_files() works as expected
        input_list = [r"c:\test\con.man", r"c:\test\foo:bar"]
        output_list = [r"c:\test\_con.man", r"c:\test\foo_bar"]

        # Test both the "folder" and "filelist" based calls
        for kwargs in ({"folder": r"c:\test"}, {"filelist": input_list}):
            # Create source files
            for file in input_list:
                fake_fs.create_file(file)

            assert output_list == filesystem.sanitize_files(**kwargs)

            # Make sure the old ones are gone
            for file in input_list:
                assert not os.path.exists(file)

            # Make sure the new ones are there
            for file in output_list:
                assert os.path.exists(file)
                os.remove(file)
                assert not os.path.exists(file)


class TestSameDirectory:
    def test_nothing_in_common_win_paths(self):
        assert 0 == filesystem.same_directory("C:\\", "D:\\")
        assert 0 == filesystem.same_directory("C:\\", "/home/test")

    def test_nothing_in_common_unix_paths(self):
        assert 0 == filesystem.same_directory("/home/", "/data/test")
        assert 0 == filesystem.same_directory("/test/home/test", "/home/")
        assert 0 == filesystem.same_directory("/test/../home", "/test")
        assert 0 == filesystem.same_directory("/test/./test", "/test")

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
    @pytest.mark.platform("linux")
    def test_posix_fun(self):
        assert 1 == filesystem.same_directory("/test", "/test")
        # IEEE 1003.1-2017 par. 4.13 for details
        assert 0 == filesystem.same_directory("/test", "//test")
        assert 1 == filesystem.same_directory("/test", "///test")
        assert 1 == filesystem.same_directory("/test", "/test/")
        assert 1 == filesystem.same_directory("/test", "/test//")
        assert 1 == filesystem.same_directory("/test", "/test///")

    def test_same(self):
        assert 1 == filesystem.same_directory("/home/123", "/home/123")
        assert 1 == filesystem.same_directory("/test/../test", "/test")
        assert 1 == filesystem.same_directory("test/../test", "test")
        assert 1 == filesystem.same_directory("/test/./test", "/test/test")
        assert 1 == filesystem.same_directory("./test", "test")

    def test_subfolder(self):
        assert 2 == filesystem.same_directory("/home/test123", "/home/test123/sub")
        assert 2 == filesystem.same_directory("/test", "/test/./test")
        assert 2 == filesystem.same_directory("/home/../test", "/test/./test")

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Relies on os.sep so should only run on Windows")
    def test_windows(self):
        assert 1 == filesystem.same_directory("D:\\", "D:\\")
        assert 2 == filesystem.same_directory("\\\\?\\C:\\", "\\\\?\\C:\\Users\\")
        assert 1 == filesystem.same_directory("/HOME/123", "/home/123")
        assert 1 == filesystem.same_directory("D:\\", "d:\\")
        assert 2 == filesystem.same_directory("\\\\?\\c:\\", "\\\\?\\C:\\Users\\")

    def test_looks_likesubfolder_but_isnt(self):
        assert 0 == filesystem.same_directory("/mnt/sabnzbd", "/mnt/sabnzbd-data")

    @pytest.mark.skipif(sys.platform.startswith(("win", "darwin")), reason="Requires a case-sensitive filesystem")
    @pytest.mark.platform("linux")
    def test_capitalization_linux(self):
        assert 2 == filesystem.same_directory("/home/test123", "/home/test123/sub")
        assert 0 == filesystem.same_directory("/test", "/Test")
        assert 0 == filesystem.same_directory("tesT", "Test")
        assert 0 == filesystem.same_directory("/test/../Home", "/home")


class TestPointsIntoAdminDir:
    def test_by_name(self, tmp_path):
        base = str(tmp_path)
        assert filesystem.points_into_admin_dir(os.path.join(base, JOB_ADMIN), base)
        assert filesystem.points_into_admin_dir(os.path.join(base, JOB_ADMIN, "__verified__"), base)
        assert filesystem.points_into_admin_dir(os.path.join(base, "sub", JOB_ADMIN, "__verified__"), base)

    def test_regular_names_are_left_alone(self, tmp_path):
        base = str(tmp_path)
        assert not filesystem.points_into_admin_dir(os.path.join(base, "testfile.rar"), base)
        assert not filesystem.points_into_admin_dir(os.path.join(base, "sub", "testfile.rar"), base)
        # Only a full part counts, not a name that merely starts with it
        assert not filesystem.points_into_admin_dir(os.path.join(base, JOB_ADMIN + "-data", "testfile.rar"), base)

    def test_link_cannot_hide_it(self, tmp_path):
        """On Windows an NTFS 8.3 alias ("__ADMI~1") points at the admin folder under a
        different name, exactly like a link does here, so the name cannot be trusted"""
        base = str(tmp_path)
        admin_dir = os.path.join(base, JOB_ADMIN)
        os.mkdir(admin_dir)
        linkname = os.path.join(base, "notadmin")
        os.symlink(admin_dir, linkname)

        assert filesystem.points_into_admin_dir(linkname, base)
        assert filesystem.points_into_admin_dir(os.path.join(linkname, "__verified__"), base)

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="NTFS 8.3 aliases only exist on Windows")
    def test_ntfs_8dot3_alias_cannot_hide_it(self, tmp_path):
        """The real thing the link above stands in for: NTFS keeps an 8.3 alias for every
        long name, so "__ADMI~1" reaches the admin folder without ever spelling it out"""
        import win32api

        base = str(tmp_path)
        admin_dir = os.path.join(base, JOB_ADMIN)
        os.mkdir(admin_dir)

        # Ask the filesystem for the alias instead of assuming what it generated
        alias = os.path.basename(win32api.GetShortPathName(admin_dir))
        if alias.lower() == JOB_ADMIN.lower():
            pytest.skip("8.3 name creation is disabled on this volume")

        assert filesystem.points_into_admin_dir(os.path.join(base, alias), base)
        assert filesystem.points_into_admin_dir(os.path.join(base, alias, "__verified__"), base)

        # And the rename that the alias was meant to sneak through has to fail
        filename = os.path.join(base, "myfile.txt")
        Path(filename).touch()
        with pytest.raises(OSError):
            filesystem.renamer(filename, os.path.join(base, alias, "__verified__"), create_local_directories=True)
        assert os.path.isfile(filename)
        assert not os.listdir(admin_dir)


class TestFirstExistingPath:
    def test_existing_path(self, tmp_path):
        assert filesystem.first_existing_path(str(tmp_path)) == str(tmp_path)

    def test_walks_up_to_existing_parent(self, tmp_path):
        assert filesystem.first_existing_path(str(tmp_path / "not" / "created" / "yet")) == str(tmp_path)


class TestSameDevice:
    def test_same_path(self, tmp_path):
        assert filesystem.same_device(str(tmp_path), str(tmp_path)) is True

    def test_sibling_folders(self, tmp_path):
        download_dir = tmp_path / "download"
        complete_dir = tmp_path / "complete"
        download_dir.mkdir()
        complete_dir.mkdir()
        assert filesystem.same_device(str(download_dir), str(complete_dir)) is True

    def test_folders_not_created_yet(self, tmp_path):
        """Falls back on the first existing parent, so both resolve to tmp_path"""
        assert filesystem.same_device(str(tmp_path / "download"), str(tmp_path / "complete" / "sub")) is True

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Relies on /proc being its own filesystem")
    def test_separate_devices(self, tmp_path):
        assert filesystem.same_device(str(tmp_path), "/proc") is False

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only has drive letters")
    def test_different_drives_win(self):
        assert filesystem.same_device("C:\\downloads", "D:\\complete") is False

    def test_undeterminable_path(self, tmp_path):
        """Fall back on separate devices, so the caller keeps reserving space for a copy"""
        with mock.patch("os.stat", side_effect=OSError):
            assert filesystem.same_device(str(tmp_path / "a"), str(tmp_path / "b")) is False


class TestClipLongPath:
    def test_empty(self):
        assert filesystem.clip_path(None) is None
        assert filesystem.long_path(None) is None

    @pytest.mark.platform("win32")
    def test_clip_path_win(self):
        assert filesystem.clip_path(r"\\?\UNC\test") == r"\\test"
        assert filesystem.clip_path(r"\\?\F:\test") == r"F:\test"

    @pytest.mark.platform("win32")
    def test_nothing_to_clip_win(self):
        assert filesystem.clip_path(r"\\test") == r"\\test"
        assert filesystem.clip_path(r"F:\test") == r"F:\test"
        assert filesystem.clip_path("/test/dir") == "/test/dir"

    @pytest.mark.platform("linux")
    def test_clip_path_non_win(self):
        # Shouldn't have any effect on platforms other than Windows
        assert filesystem.clip_path(r"\\?\UNC\test") == r"\\?\UNC\test"
        assert filesystem.clip_path(r"\\?\F:\test") == r"\\?\F:\test"
        assert filesystem.clip_path(r"\\test") == r"\\test"
        assert filesystem.clip_path(r"F:\test") == r"F:\test"
        assert filesystem.clip_path("/test/dir") == "/test/dir"

    @pytest.mark.platform("win32")
    def test_long_path_win(self):
        assert filesystem.long_path(r"\\test") == r"\\?\UNC\test"
        assert filesystem.long_path(r"F:\test") == r"\\?\F:\test"

    @pytest.mark.platform("win32")
    def test_nothing_to_lenghten_win(self):
        assert filesystem.long_path(r"\\?\UNC\test") == r"\\?\UNC\test"
        assert filesystem.long_path(r"\\?\F:\test") == r"\\?\F:\test"

    @pytest.mark.platform("linux")
    def test_long_path_non_win(self):
        # Shouldn't have any effect on platforms other than Windows
        assert filesystem.long_path(r"\\?\UNC\test") == r"\\?\UNC\test"
        assert filesystem.long_path(r"\\?\F:\test") == r"\\?\F:\test"
        assert filesystem.long_path(r"\\test") == r"\\test"
        assert filesystem.long_path(r"F:\test") == r"F:\test"
        assert filesystem.long_path("/test/dir") == "/test/dir"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
@pytest.mark.platform("linux")
@pytest.mark.fake_fs(
    {
        "path_separator": "/",
        "is_case_sensitive": True,
        "create_dirs": ["/media/test/dir", "/mnt/TEST/DIR"],
    }
)
class TestCheckMountLinux:
    def test_bare_mountpoint_linux(self, fake_fs):
        assert filesystem.mount_is_available("/media") is True
        assert filesystem.mount_is_available("/media/") is True
        assert filesystem.mount_is_available("/mnt") is True
        assert filesystem.mount_is_available("/mnt/") is True

    def test_existing_dir_linux(self, fake_fs):
        assert filesystem.mount_is_available("/media/test") is True
        assert filesystem.mount_is_available("/media/test/dir/") is True
        assert filesystem.mount_is_available("/media/test/DIR/") is True
        assert filesystem.mount_is_available("/mnt/TEST") is True
        assert filesystem.mount_is_available("/mnt/TEST/dir/") is True
        assert filesystem.mount_is_available("/mnt/TEST/DIR/") is True

    def test_dir_nonexistent_linux(self, fake_fs, sleepless):
        # Filesystem is case-sensitive on this platform
        assert filesystem.mount_is_available("/media/TEST") is False  # Issue #1457
        assert filesystem.mount_is_available("/media/TesT/") is False
        assert filesystem.mount_is_available("/mnt/TeSt/DIR") is False
        assert filesystem.mount_is_available("/mnt/test/DiR/") is False

    def test_dir_outsider_linux(self, fake_fs):
        # Outside of /media and /mnt
        assert filesystem.mount_is_available("/test/that/") is True
        # Root directory
        assert filesystem.mount_is_available("/") is True


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
@pytest.mark.platform("macos")
@pytest.mark.fake_fs(
    {
        "create_dirs": ["/Volumes/test/dir"],
    }
)
class TestCheckMountMacOS:
    def test_bare_mountpoint_macos(self, fake_fs):
        assert filesystem.mount_is_available("/Volumes") is True
        assert filesystem.mount_is_available("/Volumes/") is True

    def test_existing_dir_macos(self, fake_fs):
        assert filesystem.mount_is_available("/Volumes/test") is True
        assert filesystem.mount_is_available("/Volumes/test/dir/") is True
        # Filesystem is set case-insensitive for this platform
        assert filesystem.mount_is_available("/VOLUMES/test") is True
        assert filesystem.mount_is_available("/volumes/Test/dir/") is True

    def test_dir_nonexistent_macos(self, fake_fs, sleepless):
        # Within /Volumes
        assert filesystem.mount_is_available("/Volumes/nosuchdir") is False  # Issue #1457
        assert filesystem.mount_is_available("/Volumes/noSuchDir/") is False
        assert filesystem.mount_is_available("/Volumes/nosuchDIR/subdir") is False
        assert filesystem.mount_is_available("/Volumes/NOsuchdir/subdir/") is False

    def test_dir_outsider_macos(self, fake_fs):
        # Outside of /Volumes
        assert filesystem.mount_is_available("/test/that/") is True
        # Root directory
        assert filesystem.mount_is_available("/") is True


@pytest.mark.platform("win32")
@pytest.mark.fake_fs(
    {
        "create_dirs": [r"F:\test\dir"],
    }
)
class TestCheckMountWin:
    def test_existing_dir_win(self, fake_fs):
        assert filesystem.mount_is_available("F:\\test") is True
        assert filesystem.mount_is_available("F:\\test\\dir\\") is True
        # Filesystem and drive letters are case-insensitive on this platform
        assert filesystem.mount_is_available("f:\\Test") is True
        assert filesystem.mount_is_available("f:\\test\\DIR\\") is True

    def test_bare_mountpoint_win(self, fake_fs, sleepless):
        assert filesystem.mount_is_available("F:\\") is True
        assert filesystem.mount_is_available("Z:\\") is False

    def test_dir_nonexistent_win(self, fake_fs):
        # The existence of the drive letter is what really matters
        assert filesystem.mount_is_available("F:\\NoSuchDir") is True
        assert filesystem.mount_is_available("F:\\NoSuchDir\\") is True
        assert filesystem.mount_is_available("F:\\NOsuchdir\\subdir") is True
        assert filesystem.mount_is_available("F:\\nosuchDIR\\subdir\\") is True

    def test_dir_on_nonexistent_drive_win(self, fake_fs, sleepless):
        # Non-existent drive-letter
        assert filesystem.mount_is_available("H:\\NoSuchDir") is False
        assert filesystem.mount_is_available("E:\\NoSuchDir\\") is False
        assert filesystem.mount_is_available("L:\\NOsuchdir\\subdir") is False
        assert filesystem.mount_is_available("L:\\nosuchDIR\\subdir\\") is False

    def test_dir_outsider_win(self, fake_fs):
        # Outside the local filesystem
        assert filesystem.mount_is_available("//test/that/") is True


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
@pytest.mark.fake_fs(
    {
        "path_separator": "/",
        "is_case_sensitive": True,
    }
)
class TestListdirFull:
    def test_nonexistent_dir(self):
        assert filesystem.listdir_full("/foo/bar") == []

    def test_no_exceptions(self, fake_fs):
        test_files = (
            "/test/dir/file1.ext",
            "/test/dir/file2",
            "/test/dir/sub/sub/sub/dir/file3.ext",
        )
        for file in test_files:
            fake_fs.create_file(file)
            assert os.path.exists(file) is True
        # List our fake directory structure
        results_subdir = filesystem.listdir_full("/test/dir")
        assert len(results_subdir) == 3
        for entry in test_files:
            assert (entry in results_subdir) is True

        # List the same directory again, this time using its parent as the function argument.
        # Results should be identical, since there's nothing in /test but that one subdirectory
        results_parent = filesystem.listdir_full("/test")
        # Don't make assumptions about the sorting of the lists of results
        results_parent.sort()
        results_subdir.sort()
        assert results_parent == results_subdir

        # List that subsubsub-directory; no sorting required for a single result
        assert filesystem.listdir_full("/test/dir/sub/sub") == ["/test/dir/sub/sub/sub/dir/file3.ext"]

        # Test non-recursive version
        assert filesystem.listdir_full(r"/test", recursive=False) == []
        assert filesystem.listdir_full(r"/test/dir/sub", recursive=False) == []
        assert len(filesystem.listdir_full(r"/test/dir", recursive=False)) == 2

    def test_exception_appledouble(self, fake_fs):
        # Anything below a .AppleDouble directory should be omitted
        test_file = "/foo/bar/.AppleDouble/Oooooo.ps"
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full("/foo") == []
        assert filesystem.listdir_full("/foo/bar") == []
        assert filesystem.listdir_full("/foo/bar/.AppleDouble") == []
        assert filesystem.listdir_full("/foo", recursive=False) == []
        assert filesystem.listdir_full("/foo/bar", recursive=False) == []
        assert filesystem.listdir_full("/foo/bar/.AppleDouble", recursive=False) == []

    def test_exception_dsstore(self, fake_fs):
        # Anything below a .DS_Store directory should be omitted
        for file in (
            "/some/FILE",
            "/some/.DS_Store/oh.NO",
            "/some/.DS_Store/subdir/The.End",
        ):
            fake_fs.create_file(file)
            assert os.path.exists(file) is True
        assert filesystem.listdir_full("/some") == ["/some/FILE"]
        assert filesystem.listdir_full("/some/.DS_Store/") == []
        assert filesystem.listdir_full("/some/.DS_Store/subdir") == []
        assert filesystem.listdir_full("/some", recursive=False) == ["/some/FILE"]
        assert filesystem.listdir_full("/some/.DS_Store/", recursive=False) == []
        assert filesystem.listdir_full("/some/.DS_Store/subdir", recursive=False) == []

    def test_exception_resource_files(self, fake_fs):
        for file in (
            "/rsc/base_file",
            "/rsc/._base_file",
            "/rsc/not._base_file",
        ):
            fake_fs.create_file(file)
            assert os.path.exists(file) is True
        assert sorted(filesystem.listdir_full("/rsc")) == ["/rsc/base_file", "/rsc/not._base_file"]

    def test_invalid_file_argument(self, fake_fs):
        # This is obviously not intended use; the function expects a directory
        # as its argument, not a file. Test anyway.
        test_file = "/dev/sleepy"
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full(test_file) == []


@pytest.mark.platform("win32")
class TestListdirFullWin:
    def test_nonexistent_dir(self):
        assert filesystem.listdir_full(r"F:\foo\bar") == []

    def test_no_exceptions(self, fake_fs):
        test_files = (
            r"f:\test\dir\file1.ext",
            r"f:\test\dir\file2",
            r"f:\test\dir\sub\sub\sub\dir\file3.ext",
        )
        for file in test_files:
            fake_fs.create_file(file)
            assert os.path.exists(file) is True
        # List our fake directory structure
        results_subdir = filesystem.listdir_full(r"f:\test\dir")
        assert len(results_subdir) == 3
        for entry in test_files:
            assert (entry in results_subdir) is True

        # List the same directory again, this time using its parent as the function argument.
        # Results should be identical, since there's nothing in /test but that one subdirectory
        results_parent = filesystem.listdir_full(r"f:\test")
        # Don't make assumptions about the sorting of the lists of results
        results_parent.sort()
        results_subdir.sort()
        assert results_parent == results_subdir

        # List that subsubsub-directory; no sorting required for a single result
        assert filesystem.listdir_full(r"F:\test\dir\SUB\sub")[0].lower() == r"f:\test\dir\sub\sub\sub\dir\file3.ext"

        # Test non-recursive version
        assert filesystem.listdir_full(r"f:\test", recursive=False) == []
        assert filesystem.listdir_full(r"F:\test\dir\SUB", recursive=False) == []
        assert len(filesystem.listdir_full(r"f:\test\dir", recursive=False)) == 2

    def test_exception_appledouble(self, fake_fs):
        # Anything below a .AppleDouble directory should be omitted
        test_file = r"f:\foo\bar\.AppleDouble\Oooooo.ps"
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full(r"f:\foo") == []
        assert filesystem.listdir_full(r"f:\foo\bar") == []
        assert filesystem.listdir_full(r"F:\foo\bar\.AppleDouble") == []
        assert filesystem.listdir_full(r"f:\foo", recursive=False) == []
        assert filesystem.listdir_full(r"f:\foo\bar", recursive=False) == []
        assert filesystem.listdir_full(r"F:\foo\bar\.AppleDouble", recursive=False) == []

    def test_exception_dsstore(self, fake_fs):
        # Anything below a .DS_Store directory should be omitted
        for file in (
            r"f:\some\FILE",
            r"f:\some\.DS_Store\oh.NO",
            r"f:\some\.DS_Store\subdir\The.End",
        ):
            fake_fs.create_file(file)
            assert os.path.exists(file) is True
        assert filesystem.listdir_full(r"f:\some") == [r"f:\some\FILE"]
        assert filesystem.listdir_full(r"f:\some\.DS_Store") == []
        assert filesystem.listdir_full(r"f:\some\.DS_Store\subdir") == []
        assert filesystem.listdir_full(r"f:\some", recursive=True) == [r"f:\some\FILE"]
        assert filesystem.listdir_full(r"f:\some\.DS_Store", recursive=True) == []
        assert filesystem.listdir_full(r"f:\some\.DS_Store\subdir", recursive=True) == []

    def test_exception_resource_files(self, fake_fs):
        for file in (
            r"f:\rsc\base_file",
            r"f:\rsc\._base_file",
            r"f:\rsc\not._base_file",
        ):
            fake_fs.create_file(file)
            assert os.path.exists(file) is True
        assert sorted(filesystem.listdir_full(r"f:\rsc")) == [r"f:\rsc\base_file", r"f:\rsc\not._base_file"]

    def test_invalid_file_argument(self, fake_fs):
        # This is obviously not intended use; the function expects a directory
        # as its argument, not a file. Test anyway.
        test_file = r"f:\dev\sleepy"
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full(test_file) == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
@pytest.mark.fake_fs(
    {
        "path_separator": "/",
        "is_case_sensitive": True,
    }
)
class TestGetUniqueDirFilename:
    # Reduce the waiting time when the function calls check_mount()
    @pytest.mark.config({"wait_ext_drive": 1})
    def test_nonexistent_dir(self, fake_fs, sleepless):
        # Absolute path
        assert filesystem.get_unique_dir("/foo/bar", n=0, create_dir=False) == "/foo/bar"
        # Absolute path in a location that matters to check_mount
        assert filesystem.get_unique_dir("/mnt/foo/bar", n=0, create_dir=False) == "/mnt/foo/bar"
        # Relative path
        if fake_fs.cwd != "/":
            os.chdir("/")
        assert filesystem.get_unique_dir("foo/bar", n=0, create_dir=False) == "foo/bar"

    def test_nonexistent_dir_without_permission(self, fake_fs):
        some_dir = "/foo/bar"
        fake_fs.create_dir(some_dir)

        # Remove write permission from the directory.
        os.chmod(some_dir, 0o500)

        assert filesystem.get_unique_dir(os.path.join(some_dir, "nonexistent"), create_dir=True) is False

    def test_creating_dir(self, fake_fs):
        # First call also creates the directory for us
        assert filesystem.get_unique_dir("/foo/bar", n=0, create_dir=True) == "/foo/bar"
        # Verify creation of the path
        assert os.path.exists("/foo/bar") is True
        # Directories from previous loops get in the way
        for dir_n in range(1, 11):  # Go high enough for double digits
            assert filesystem.get_unique_dir("/foo/bar", n=0, create_dir=True) == "/foo/bar." + str(dir_n)
            assert os.path.exists("/foo/bar." + str(dir_n)) is True
        # Explicitly set parameter n
        assert filesystem.get_unique_dir("/foo/bar", n=666, create_dir=True) == "/foo/bar.666"
        assert os.path.exists("/foo/bar.666") is True

    def test_nonexistent_file(self, fake_fs):
        assert filesystem.get_unique_filename("/dir/file.name") == "/dir/file.name"
        # Relative path
        assert filesystem.get_unique_filename("dir/file.name") == "dir/file.name"

    def test_existing_file(self, fake_fs):
        test_file = "/dir/file.name"
        max_obstruct = 11  # High enough for double digits
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file)
        # Create obstructions
        for n in range(1, max_obstruct):
            file_n = "/dir/file." + str(n) + ".name"
            fake_fs.create_file(file_n)
            assert os.path.exists(file_n)
        assert filesystem.get_unique_filename(test_file) == "/dir/file." + str(max_obstruct) + ".name"

    def test_existing_file_without_extension(self, fake_fs):
        test_file = "/some/filename"
        # Create obstructions
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file)
        first_filename = filesystem.get_unique_filename(test_file)
        assert first_filename == "/some/filename.1"
        fake_fs.create_file(first_filename)
        assert filesystem.get_unique_filename(test_file) == "/some/filename.2"


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows specific tests")
class TestGetUniqueDirFilenameWin:
    def test_nonexistent_dir(self, fake_fs, sleepless):
        # Absolute path
        assert filesystem.get_unique_dir(r"C:\No\Such\Dir", n=0, create_dir=False).lower() == r"c:\no\such\dir"
        # Relative path
        assert filesystem.get_unique_dir(r"foo\bar", n=0, create_dir=False).lower() == r"foo\bar"

    def test_creating_dir(self, fake_fs):
        # First call also creates the directory for us
        assert filesystem.get_unique_dir(r"C:\foo\BAR", n=0, create_dir=True).lower() == r"c:\foo\bar"
        # Verify creation of the path
        assert os.path.exists(r"c:\foo\bar") is True
        # Directories from previous loops get in the way
        for dir_n in range(1, 11):  # Go high enough for double digits
            assert filesystem.get_unique_dir(r"c:\foo\bar", n=0, create_dir=True) == r"c:\foo\bar." + str(dir_n)
            assert os.path.exists(r"c:\foo\bar." + str(dir_n)) is True
        # Explicitly set parameter n
        assert filesystem.get_unique_dir(r"c:\Foo\Bar", n=666, create_dir=True).lower() == r"c:\foo\bar.666"
        assert os.path.exists(r"c:\foo\bar.666") is True

    def test_nonexistent_file(self, fake_fs):
        assert filesystem.get_unique_filename(r"C:\DIR\file.name").lower() == r"c:\dir\file.name"
        # Relative path
        assert filesystem.get_unique_filename(r"DIR\file.name").lower() == r"dir\file.name"

    def test_existing_file(self, fake_fs):
        test_file = r"C:\dir\file.name"
        max_obstruct = 11  # High enough for double digits
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file)
        # Create obstructions
        for n in range(1, max_obstruct):
            file_n = r"C:\dir\file." + str(n) + ".name"
            fake_fs.create_file(file_n)
            assert os.path.exists(file_n)
        assert filesystem.get_unique_filename(test_file).lower() == r"c:\dir\file." + str(max_obstruct) + ".name"

    def test_existing_file_without_extension(self, fake_fs):
        test_file = r"c:\some\filename"
        # Create obstructions
        fake_fs.create_file(test_file)
        assert os.path.exists(test_file)
        assert filesystem.get_unique_filename(test_file).lower() == r"c:\some\filename.1"


@pytest.mark.platform("win32")
class TestCreateAllDirsWin:
    def test_create_all_dirs(self, fake_fs):
        self.directory = fake_fs.create_dir(r"C:\Downloads")
        # Also test for no crash when folder already exists
        for folder in (r"C:\Downloads", r"C:\Downloads\Show\Test", r"C:\Downloads\Show\Test2", r"C:\Downloads\Show"):
            assert filesystem.create_all_dirs(folder) == folder
            assert os.path.exists(folder)


class PermissionCheckerHelper:
    @staticmethod
    def assert_dir_perms(path, expected_perms):
        assert stat.filemode(os.stat(path).st_mode) == "d" + stat.filemode(expected_perms)[1:]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
@pytest.mark.fake_fs(
    {
        "path_separator": "/",
        "is_case_sensitive": True,
    }
)
class TestCreateAllDirs(PermissionCheckerHelper):
    def test_basic_folder_creation(self, fake_fs):
        fake_fs.create_dir("/test_base")
        # Also test for no crash when folder already exists
        for folder in ("/test_base", "/test_base/show/season 1/episode 1", "/test_base/show"):
            assert filesystem.create_all_dirs(folder) == folder
            assert os.path.exists(folder)

    @pytest.mark.config({"permissions": "0777"})
    def test_permissions_777(self, fake_fs):
        self._permissions_runner(fake_fs, "/test_base777")
        self._permissions_runner(fake_fs, "/test_base777_nomask", apply_permissions=False)

    @pytest.mark.config({"permissions": "0770"})
    def test_permissions_770(self, fake_fs):
        self._permissions_runner(fake_fs, "/test_base770")
        self._permissions_runner(fake_fs, "/test_base770_nomask", apply_permissions=False)

    @pytest.mark.config({"permissions": "0600"})
    def test_permissions_600(self, fake_fs):
        with pytest.raises(OSError):  # pyfakefs checks fake permissions now...
            self._permissions_runner(fake_fs, "/test_base600")
        self._permissions_runner(fake_fs, "/test_base600_nomask", apply_permissions=False)

    @pytest.mark.config({"permissions": "0450"})
    def test_permissions_450(self, fake_fs):
        with pytest.raises(OSError):
            self._permissions_runner(fake_fs, "/test_base450", perms_base="0450")

    def test_no_permissions(self, fake_fs):
        self._permissions_runner(fake_fs, "/test_base_perm700", perms_base="0700")
        self._permissions_runner(fake_fs, "/test_base_perm750", perms_base="0750")
        with pytest.raises(OSError):  # pyfakefs checks fake permissions now...
            self._permissions_runner(fake_fs, "/test_base_perm600", perms_base="0600")
        self._permissions_runner(fake_fs, "/test_base_perm777", perms_base="0777")

    def _permissions_runner(
        self,
        fs,
        test_base,
        perms_base="0700",
        apply_permissions=True,
    ):
        # Create base directory and set the base permissions
        perms_base_int = int(perms_base, 8)
        fs.create_dir(test_base, perms_base_int, apply_umask=False)
        assert os.path.exists(test_base) is True
        self.assert_dir_perms(test_base, perms_base_int)

        # Create directories with permissions
        new_dir = os.path.join(test_base, "se 1", "ep1")
        filesystem.create_all_dirs(new_dir, apply_permissions=apply_permissions)

        # If permissions needed to be set, verify the new folder has the
        # right permissions and verify the base didn't change
        if apply_permissions and cfg.permissions():
            perms_test_int = int(cfg.permissions(), 8)
        else:
            # Get the current permissions, since os.mkdir masks that out
            perms_test_int = int("0777", 8) & ~sabnzbd.ORG_UMASK
        self.assert_dir_perms(new_dir, perms_test_int)
        self.assert_dir_perms(test_base, perms_base_int)


@pytest.mark.platform("win32")
class TestSetPermissionsWin:
    def test_win32(self):
        # Should not do or return anything on Windows
        assert filesystem.set_permissions(r"F:\who\cares", recursive=False) is None


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
@pytest.mark.fake_fs(
    {
        "path_separator": "/",
        "is_case_sensitive": True,
        "umask": int("0022", 8),  # rwxr-xr-x
    }
)
class TestSetPermissions(PermissionCheckerHelper):
    def _runner(self, perms_before_test, fs):
        """
        Generic test runner for permissions testing. The permissions are set per test
        via the relevant sab config option; the filesystem parameter in setUp().
        Note that the umask set in the environment before starting the program
        also affects the results if sabnzbd.cfg.permissions isn't set.

        Arguments:
            str perms_test: permissions for test objects, chmod style "0755".
        """
        # We expect the cfg.permissions to be applied, or the original to be kept if none are set
        perms_before_test = int(perms_before_test, 8)
        if sabnzbd.cfg.permissions():
            perms_after_test = int(sabnzbd.cfg.permissions(), 8)
        else:
            perms_after_test = perms_before_test

        # Setup and verify fake dir
        test_dir = "/test"
        fs.create_dir(test_dir, perms_before_test, apply_umask=False)
        assert os.path.exists(test_dir) is True
        self.assert_dir_perms(test_dir, perms_before_test)

        # Setup and verify fake files
        for file in (
            "foobar",
            "file.ext",
            "sub/dir/.nzb",
            "another/sub/dir/WithSome.File",
        ):
            file = os.path.join(test_dir, file)
            basefolder = os.path.dirname(file)

            # Create the folder, so it has the expected permissions
            if not os.path.exists(basefolder):
                try:
                    fs.create_dir(basefolder, perms_before_test, apply_umask=False)
                except PermissionError:
                    set_uid(0)
                    fs.create_file(file, perms_before_test, apply_umask=False)
            assert os.path.exists(basefolder) is True
            self.assert_dir_perms(basefolder, perms_before_test)

            # Add a random one of the forbidden bits
            file_perms_before_test = perms_before_test | choice(
                (stat.S_ISUID, stat.S_ISGID, stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH)
            )

            # Then, create the file
            try:
                fs.create_file(file, file_perms_before_test, apply_umask=False)
            except PermissionError:
                set_uid(0)
                fs.create_file(file, file_perms_before_test, apply_umask=False)

            assert os.path.exists(file) is True
            assert stat.filemode(os.stat(file).st_mode)[1:] == stat.filemode(file_perms_before_test)[1:]

        # Set permissions, recursive by default
        filesystem.set_permissions(test_dir)

        # Check the results
        for root, dirs, files in os.walk(test_dir):
            for directory in [os.path.join(root, d) for d in dirs]:
                # Permissions on directories should now match perms_after
                self.assert_dir_perms(directory, perms_after_test)
            for file in [os.path.join(root, f) for f in files]:
                # Files also shouldn't have any executable or special bits set
                assert (
                    stat.filemode(os.stat(file).st_mode)[1:]
                    == stat.filemode(
                        perms_after_test & ~(stat.S_ISUID | stat.S_ISGID | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    )[1:]
                )

        # Cleanup
        set_uid(0)
        fs.remove_object(test_dir)
        assert os.path.exists(test_dir) is False
        set_uid(global_uid)

    @pytest.mark.platform("linux")
    def test_empty_permissions_setting(self, fake_fs):
        # World writable directory
        self._runner("0777", fake_fs)
        self._runner("0450", fake_fs)

    @pytest.mark.platform("linux")
    @pytest.mark.config({"permissions": "0760"})
    def test_dir0777_permissions0760_setting(self, fake_fs):
        # World-writable directory, permissions 760
        self._runner("0777", fake_fs)

    @pytest.mark.platform("linux")
    @pytest.mark.config({"permissions": "0617"})
    def test_dir0450_permissions0617_setting(self, fake_fs):
        # Insufficient base access
        self._runner("0450", fake_fs)

    @pytest.mark.platform("linux")
    @pytest.mark.config({"permissions": "2455"})
    def test_dir0444_permissions2455_setting(self, fake_fs):
        # Insufficient access, permissions with setgid (should be stripped)
        self._runner("0444", fake_fs)

    @pytest.mark.platform("linux")
    @pytest.mark.config({"permissions": "4755"})
    def test_dir1755_permissions4755_setting(self, fake_fs):
        # Sticky bit on directory, permissions with setuid (should be stripped)
        self._runner("1755", fake_fs)


class TestRenamer:
    # test filesystem.renamer() for different scenario's
    def test_renamer(self, fake_fs):
        # First of all, create a working directory (with a random name)
        dirname = os.path.join(SAB_DATA_DIR, "testdir" + str(randint(10000, 99999)))
        fake_fs.create_dir(dirname)

        # base case: rename file within directory
        filename = os.path.join(dirname, "myfile.txt")
        Path(filename).touch()  # create file
        newfilename = os.path.join(dirname, "newfile.txt")
        assert newfilename == filesystem.renamer(filename, newfilename)
        assert not os.path.isfile(filename)
        assert os.path.isfile(newfilename)

        # standard behaviour: renaming (moving) into an exiting other directory *is* allowed
        filename = os.path.join(dirname, "myfile.txt")
        Path(filename).touch()  # create file
        sameleveldirname = os.path.join(SAB_DATA_DIR, "othertestdir" + str(randint(10000, 99999)))
        os.mkdir(sameleveldirname)
        newfilename = os.path.join(sameleveldirname, "newfile.txt")
        assert newfilename == filesystem.renamer(filename, newfilename)
        assert not os.path.isfile(filename)
        assert os.path.isfile(newfilename)
        shutil.rmtree(sameleveldirname)

        # Default: renaming into a non-existing subdirectory not allowed
        Path(filename).touch()  # create file
        newfilename = os.path.join(dirname, "nonexistingsubdir", "newfile.txt")
        try:
            # Should fail
            filesystem.renamer(filename, newfilename)
        except Exception:
            pass
        assert os.path.isfile(filename)
        assert not os.path.isfile(newfilename)

        # Creation of subdirectory is allowed if create_local_directories=True
        Path(filename).touch()
        newfilename = os.path.join(dirname, "newsubdir", "newfile.txt")
        try:
            filesystem.renamer(filename, newfilename, create_local_directories=True)
        except Exception:
            pass
        assert not os.path.isfile(filename)
        assert os.path.isfile(newfilename)

        # Creation of subdirectory plus deeper sudbdir is allowed if create_local_directories=True
        Path(filename).touch()
        newfilename = os.path.join(dirname, "newsubdir", "deepersubdir", "newfile.txt")
        try:
            filesystem.renamer(filename, newfilename, create_local_directories=True)
        except Exception:
            pass
        assert not os.path.isfile(filename)
        assert os.path.isfile(newfilename)

        # ... escaping the directory plus subdir creation is not allowed
        Path(filename).touch()
        newfilename = os.path.join(dirname, "..", "newsubdir", "newfile.txt")
        try:
            filesystem.renamer(filename, newfilename, create_local_directories=True)
        except Exception:
            pass
        assert os.path.isfile(filename)
        assert not os.path.isfile(newfilename)

        # ... renaming into the admin folder is not allowed either
        admin_dir = os.path.join(dirname, JOB_ADMIN)
        os.mkdir(admin_dir)
        Path(filename).touch()
        newfilename = os.path.join(admin_dir, "__verified__")
        try:
            filesystem.renamer(filename, newfilename, create_local_directories=True)
        except Exception:
            pass
        assert os.path.isfile(filename)
        assert not os.path.isfile(newfilename)

        # ... nor is naming the admin folder itself: a move into an existing directory
        # keeps the old basename, so this would end up inside the admin folder as well
        Path(filename).touch()
        try:
            filesystem.renamer(filename, admin_dir, create_local_directories=True)
        except Exception:
            pass
        assert os.path.isfile(filename)
        assert not os.listdir(admin_dir)

        # ... and not under another name that resolves to it, such as a link. On Windows
        # an NTFS 8.3 alias ("__ADMI~1") reaches the admin folder the very same way.
        linkname = os.path.join(dirname, "notadmin")
        os.symlink(admin_dir, linkname)
        Path(filename).touch()
        try:
            filesystem.renamer(filename, os.path.join(linkname, "__verified__"), create_local_directories=True)
        except Exception:
            pass
        assert os.path.isfile(filename)
        assert not os.listdir(admin_dir)
        os.remove(linkname)

        # Cleanup working directory
        shutil.rmtree(dirname)


class TestRestrictedUnpickler:
    def test_round_trip(self, tmp_path):
        data = {"a": 1, "s": {1, 2}, "when": datetime.datetime(2024, 1, 1), "t": time.gmtime(0), "st": os.stat(".")}
        filesystem.save_data(data, "d", str(tmp_path))
        assert filesystem.load_data("d", str(tmp_path), remove=False) == data

    def test_rejects_code_execution_gadget(self):
        class Evil:
            def __reduce__(self):
                return (os.system, ("echo pwned",))

        with pytest.raises(pickle.UnpicklingError):
            filesystem.RestrictedUnpickler(io.BytesIO(pickle.dumps(Evil()))).load()

    def test_rejects_non_allowlisted_sabnzbd_class(self):
        # kronos.ForkedScheduler has a __del__ that runs os.kill; referenced by name, rejected pre-import
        def named_global(module, name):
            return (
                b"\x80\x04\x8c"
                + bytes([len(module)])
                + module.encode()
                + b"\x8c"
                + bytes([len(name)])
                + name.encode()
                + b"\x93."
            )

        with pytest.raises(pickle.UnpicklingError):
            filesystem.RestrictedUnpickler(io.BytesIO(named_global("sabnzbd.utils.kronos", "ForkedScheduler"))).load()

    def test_loads_legacy_3_0_rss_pickle(self):
        path = os.path.join(SAB_DATA_DIR, "test_3_0_0_data_format")
        data = filesystem.load_data("rss_data.sab", path, remove=False)
        assert isinstance(data, dict) and data
        feed_jobs = next(iter(data.values()))
        assert isinstance(feed_jobs, dict) and feed_jobs


class TestUnwantedExtensions:
    # Only test lowercase extensions without a leading dot: the unwanted_extensions
    # setting is sanitized accordingly in interface.saveSwitches() before saving.
    test_extensions = "iso, cmd, bat, sh, re:r[0-9]{2}, sab*"
    # Test parameters as (filename, result) tuples, with result given for blacklist mode
    test_params = [
        ("ubuntu.iso", True),
        ("par2.cmd", True),
        ("freedos.BAT", True),
        ("Debian.installer.SH", True),
        ("FREEBSD.ISO", True),
        ("par2.CmD", True),
        ("freedos.baT", True),
        ("Debian.Installer.sh", True),
        ("ubuntu.torrent", False),
        ("par2.cmd.notcmd", False),
        ("freedos.tab", False),
        (".SH.hs", False),
        ("regexp.r0611", False),
        ("regexp.007", False),
        ("regexp.A01", False),
        ("regexp.r9", False),
        ("regexp.r2d2", False),
        ("regexp.r2d", False),
        ("regexp.r00", True),
        ("regexp.R42", True),
        ("test.sabnzbd", True),
        ("pass.sab", True),
        ("fail.sb", False),
        ("No_Extension", False),
        ("r42", False),
        (480, False),
        (None, False),
        ("", False),
        ([], False),
    ]

    @pytest.mark.config({"unwanted_extensions_mode": 0, "unwanted_extensions": test_extensions})
    def test_has_unwanted_extension_blacklist_mode(self):
        for filename, result in self.test_params:
            assert filesystem.has_unwanted_extension(filename) is result

    @pytest.mark.config({"unwanted_extensions_mode": 1, "unwanted_extensions": test_extensions})
    def test_has_unwanted_extension_whitelist_mode(self):
        for filename, result in self.test_params:
            if filesystem.get_ext(filename):
                assert filesystem.has_unwanted_extension(filename) is not result
            else:
                # missing extension is never considered unwanted
                assert filesystem.has_unwanted_extension(filename) is False

    @pytest.mark.config({"unwanted_extensions_mode": 0, "unwanted_extensions": ""})
    def test_has_unwanted_extension_empty_blacklist(self):
        for filename, result in self.test_params:
            assert filesystem.has_unwanted_extension(filename) is False

    @pytest.mark.config({"unwanted_extensions_mode": 1, "unwanted_extensions": ""})
    def test_has_unwanted_extension_empty_whitelist(self):
        for filename, result in self.test_params:
            if filesystem.get_ext(filename):
                assert filesystem.has_unwanted_extension(filename) is True
            else:
                # missing extension is never considered unwanted
                assert filesystem.has_unwanted_extension(filename) is False


class TestOtherFileSystemFunctions:
    def test_directory_is_writable(self):
        # very basic test of directory_is_writable()
        # let's test on the tempdir provided by the OS:
        assert filesystem.directory_is_writable(tempfile.gettempdir())

    def test_filesystem_capabilities(self):
        # test the filesystem is capable of long and unicode filenames
        # any modern filesystem (ext3, ext4, ntfs, modern FAT) should succeed
        assert filesystem.check_filesystem_capabilities(tempfile.gettempdir())

    def test_directory_is_writable_with_file_survives_lost_test_file(self, monkeypatch):
        # Regression test: losing the temporary test file before cleanup (e.g. a
        # concurrent writability check removed it) must NOT be reported as "not
        # writable". This used to surface as a false "is not writable at all.
        # This blocks downloads." warning at startup.
        test_dir = tempfile.gettempdir()
        real_remove = os.remove
        leftover = os.path.join(test_dir, "sab_test.txt")

        def raise_enoent(path):
            raise FileNotFoundError("simulated race: test file already removed")

        monkeypatch.setattr(os, "remove", raise_enoent)
        try:
            assert filesystem.directory_is_writable_with_file(test_dir, "sab_test.txt") is True
        finally:
            # os.remove was patched out, so the test file was left behind
            if os.path.exists(leftover):
                real_remove(leftover)

    def test_directory_is_writable_with_file_reports_write_failure(self, monkeypatch):
        # A genuine failure to create/write the file must still return False
        def raise_permission(*args, **kwargs):
            raise PermissionError("simulated read-only filesystem")

        monkeypatch.setattr("builtins.open", raise_permission)
        assert filesystem.directory_is_writable_with_file(tempfile.gettempdir(), "sab_test.txt") is False

    @pytest.mark.parametrize(
        "name, ext_to_remove, output",
        [
            ("Test.nzb", (".nzb",), "Test"),
            ("Test.nzb.nzb.nzb.nzb.nzb", (".nzb",), "Test"),
            ("Test.not", (".nzb",), "Test.not"),
            ("No.par2.Test.par2.nzb", (".nzb", ".par2"), "No.par2.Test"),
        ],
    )
    def test_strip_extensions(self, name, ext_to_remove, output):
        assert filesystem.strip_extensions(name, ext_to_remove) == output

    @pytest.mark.parametrize(
        "file_name, clean_file_name",
        [
            ("my_awesome_nzb_file.pAr2.nZb", "my_awesome_nzb_file"),
            ("my_awesome_nzb_file.....pAr2.nZb", "my_awesome_nzb_file"),
            ("my_awesome_nzb_file....par2..", "my_awesome_nzb_file"),
            (" my_awesome_nzb_file  .pAr.nZb", "my_awesome_nzb_file"),
            ("with.extension.and.period.par2.", "with.extension.and.period"),
            ("nothing.in.here", "nothing.in.here"),
            ("  just.space  ", "just.space"),
            ("http://test.par2  ", "http://test.par2"),
        ],
    )
    def test_create_work_name(self, file_name, clean_file_name):
        # Only test stuff specific for create_work_name
        # The sanitizing is already tested in tests for sanitize_foldername
        assert filesystem.create_work_name(file_name) == clean_file_name


class TestOutOfSpace:
    """A full filesystem and an exhausted quota are the same thing to a user, and both
    are fixed by freeing space rather than by retrying the write."""

    @staticmethod
    def error(code, winerror=None):
        err = OSError(code, "test")
        if winerror is not None:
            err.winerror = winerror
        return err

    def test_a_full_filesystem(self):
        assert sabnzbd.filesystem.out_of_space(self.error(errno.ENOSPC)) is True

    def test_an_exhausted_quota(self):
        assert sabnzbd.filesystem.out_of_space(self.error(errno.EDQUOT)) is True

    @pytest.mark.parametrize("code", [errno.EACCES, errno.ENOENT, errno.EIO, errno.EROFS])
    def test_other_errors_are_not_out_of_space(self, code):
        """These need a person, not more free space, so they must not be reported as a
        full disk"""
        assert sabnzbd.filesystem.out_of_space(self.error(code)) is False

    @pytest.mark.parametrize("winerror", [39, 112, 1295])
    def test_the_windows_codes(self, winerror):
        """Windows says it several ways and only some map onto an errno"""
        original = sabnzbd.WINDOWS
        sabnzbd.WINDOWS = True
        try:
            assert sabnzbd.filesystem.out_of_space(self.error(errno.EINVAL, winerror)) is True
        finally:
            sabnzbd.WINDOWS = original

    def test_an_unrelated_windows_code(self):
        original = sabnzbd.WINDOWS
        sabnzbd.WINDOWS = True
        try:
            # 5 is ERROR_ACCESS_DENIED
            assert sabnzbd.filesystem.out_of_space(self.error(errno.EINVAL, 5)) is False
        finally:
            sabnzbd.WINDOWS = original
