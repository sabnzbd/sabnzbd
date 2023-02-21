#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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
import stat
import sys
import os
import random
import shutil
from pathlib import Path
import tempfile

import pyfakefs.fake_filesystem_unittest as ffs
from pyfakefs.fake_filesystem import OSType

import sabnzbd.cfg
import sabnzbd.filesystem as filesystem
from sabnzbd.constants import DEF_FOLDER_MAX, DEF_FILE_MAX
from tests.testhelper import *

# Set the global uid for fake filesystems to a non-root user;
# by default this depends on the user running pytest.
global_uid = 1000
ffs.set_uid(global_uid)


class TestFileFolderNameSanitizer:
    def test_empty(self):
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_foldername(None) is None

    @set_platform("win32")
    def test_colon_handling_windows(self):
        assert filesystem.sanitize_filename("test:aftertest") == "test-aftertest"
        assert filesystem.sanitize_filename(":") == "-"
        assert filesystem.sanitize_filename("test:") == "test-"
        assert filesystem.sanitize_filename("test: ") == "test-"
        # They should act the same
        assert filesystem.sanitize_filename("test:aftertest") == filesystem.sanitize_foldername("test:aftertest")

    @set_platform("macos")
    def test_colon_handling_macos(self):
        assert filesystem.sanitize_filename("test:aftertest") == "aftertest"
        assert filesystem.sanitize_filename(":aftertest") == "aftertest"
        assert filesystem.sanitize_filename("::aftertest") == "aftertest"
        assert filesystem.sanitize_filename(":after:test") == "test"
        # Empty after sanitising with macos colon handling
        assert filesystem.sanitize_filename(":") == "unknown"
        assert filesystem.sanitize_filename("test:") == "unknown"
        assert filesystem.sanitize_filename("test: ") == "unknown"

    @set_platform("linux")
    def test_colon_handling_other(self):
        assert filesystem.sanitize_filename("test:aftertest") == "test:aftertest"
        assert filesystem.sanitize_filename(":") == ":"
        assert filesystem.sanitize_filename("test:") == "test:"
        assert filesystem.sanitize_filename("test: ") == "test:"

    @set_platform("win32")
    def test_win_devices_on_win(self):
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename("aux.txt") == "_aux.txt"
        assert filesystem.sanitize_filename("txt.aux") == "txt.aux"
        assert filesystem.sanitize_filename("$mft") == "Smft"
        assert filesystem.sanitize_filename("a$mft") == "a$mft"

    @set_platform("linux")
    def test_win_devices_not_win(self):
        # Linux and macOS are the same for this
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename("aux.txt") == "aux.txt"
        assert filesystem.sanitize_filename("txt.aux") == "txt.aux"
        assert filesystem.sanitize_filename("$mft") == "$mft"
        assert filesystem.sanitize_filename("a$mft") == "a$mft"

    @set_platform("win32")
    def test_file_illegal_chars_win32(self):
        assert filesystem.sanitize_filename("test" + filesystem.CH_ILLEGAL_WIN + "aftertest") == (
            "test" + filesystem.CH_LEGAL_WIN + "aftertest"
        )
        assert (
            filesystem.sanitize_filename("test" + chr(0) + chr(1) + chr(15) + chr(31) + "aftertest")
            == "test____aftertest"
        )

    @set_platform("win32")
    def test_folder_illegal_chars_win32(self):
        assert (
            filesystem.sanitize_foldername("test" + chr(0) + chr(9) + chr(13) + chr(31) + "aftertest")
            == "test____aftertest"
        )

    @set_platform("linux")
    def test_file_illegal_chars_linux(self):
        assert filesystem.sanitize_filename("test/aftertest") == "test+aftertest"
        assert filesystem.sanitize_filename("/test") == "+test"
        assert filesystem.sanitize_filename("test/") == "test+"
        assert filesystem.sanitize_filename(r"/test\/aftertest/") == r"+test\+aftertest+"
        assert filesystem.sanitize_filename("/") == "+"
        assert filesystem.sanitize_filename("///") == "+++"
        assert filesystem.sanitize_filename("../") == "..+"
        assert filesystem.sanitize_filename("../test") == "..+test"

    @set_platform("linux")
    def test_folder_illegal_chars_linux(self):
        assert filesystem.sanitize_foldername('test"aftertest') == "test'aftertest"
        assert filesystem.sanitize_foldername("test:") == "test-"
        assert filesystem.sanitize_foldername("test<>?*|aftertest") == "test<>?*|aftertest"

    def test_char_collections(self):
        assert len(filesystem.CH_ILLEGAL) == len(filesystem.CH_LEGAL)
        assert len(filesystem.CH_ILLEGAL_WIN) == len(filesystem.CH_LEGAL_WIN)

    @set_platform("linux")
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

    @set_platform("linux")
    @set_config({"sanitize_safe": True})
    def test_sanitize_safe_linux(self):
        # Set sanitize_safe to on, simulating Windows-style restrictions.
        assert filesystem.sanitize_filename("test" + filesystem.CH_ILLEGAL_WIN + "aftertest") == (
            "test" + filesystem.CH_LEGAL_WIN + "aftertest"
        )
        for index in range(0, len(filesystem.CH_ILLEGAL_WIN)):
            char_leg = filesystem.CH_LEGAL_WIN[index]
            char_ill = filesystem.CH_ILLEGAL_WIN[index]
            assert filesystem.sanitize_filename("test" + char_ill * 2 + "aftertest") == (
                "test" + char_leg * 2 + "aftertest"
            )
            # Illegal chars that also get caught by strip() never make it far
            # enough to be replaced by their legal equivalents if they appear
            # on either end of the filename.
            if char_ill.strip():
                assert filesystem.sanitize_filename("test" + char_ill * 2) == ("test" + char_leg * 2)
                assert filesystem.sanitize_filename(char_ill * 2 + "test") == (char_leg * 2 + "test")

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
        assert filesystem.sanitize_foldername("/test/this.") == "+test+this"
        assert filesystem.sanitize_foldername("/test./this.") == "+test.+this"
        assert filesystem.sanitize_foldername("/test. /this . ") == "+test. +this"

    def test_long_foldername(self):
        assert len(filesystem.sanitize_foldername("test" * 100)) == DEF_FOLDER_MAX
        assert len(filesystem.sanitize_foldername("a" * DEF_FOLDER_MAX)) == DEF_FOLDER_MAX
        assert len(filesystem.sanitize_foldername("a" * (DEF_FOLDER_MAX + 1))) == DEF_FOLDER_MAX

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

        # insert NON-ASCII chars, which should get removed because overall length is too long
        name = "aaaa" + 200 * chr(188) + 200 * chr(222) + "bbbb.ext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname == "aaaabbbb.ext"

        # Unicode / UTF8 ... total filename length might be too long for certain filesystems
        name = "BASE" + "你" * 200 + ".ext"
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname.startswith("BASE")
        assert sanitizedname.endswith(".ext")

        # Linux / POSIX: a hidden file (no extension), with size 200, so do not truncate at all
        name = "." + "a" * 200
        sanitizedname = filesystem.sanitize_filename(name)
        assert sanitizedname == name  # no change


class TestSanitizeFiles(ffs.TestCase):
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.os = OSType.WINDOWS
        # Disable randomisation of directory listings
        self.fs.shuffle_listdir_results = False

    def test_sanitize_files_input(self):
        assert [] == filesystem.sanitize_files(folder=None)
        assert [] == filesystem.sanitize_files(filelist=None)
        assert [] == filesystem.sanitize_files(folder=None, filelist=None)

    @set_platform("win32")
    @set_config({"sanitize_safe": True})
    def test_sanitize_files(self):
        # The very specific tests of sanitize_filename() are above
        # Here we just want to see that sanitize_files() works as expected
        input_list = [r"c:\test\con.man", r"c:\test\foo:bar"]
        output_list = [r"c:\test\_con.man", r"c:\test\foo-bar"]

        # Test both the "folder" and "filelist" based calls
        for kwargs in ({"folder": r"c:\test"}, {"filelist": input_list}):
            # Create source files
            for file in input_list:
                self.fs.create_file(file)

            assert output_list == filesystem.sanitize_files(**kwargs)

            # Make sure the old ones are gone
            for file in input_list:
                assert not os.path.exists(file)

            # Make sure the new ones are there
            for file in output_list:
                assert os.path.exists(file)
                os.remove(file)
                assert not os.path.exists(file)


class TestSameFile:
    def test_nothing_in_common_win_paths(self):
        assert 0 == filesystem.same_file("C:\\", "D:\\")
        assert 0 == filesystem.same_file("C:\\", "/home/test")

    def test_nothing_in_common_unix_paths(self):
        assert 0 == filesystem.same_file("/home/", "/data/test")
        assert 0 == filesystem.same_file("/test/home/test", "/home/")
        assert 0 == filesystem.same_file("/test/../home", "/test")
        assert 0 == filesystem.same_file("/test/./test", "/test")

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
    @set_platform("linux")
    def test_posix_fun(self):
        assert 1 == filesystem.same_file("/test", "/test")
        # IEEE 1003.1-2017 par. 4.13 for details
        assert 0 == filesystem.same_file("/test", "//test")
        assert 1 == filesystem.same_file("/test", "///test")
        assert 1 == filesystem.same_file("/test", "/test/")
        assert 1 == filesystem.same_file("/test", "/test//")
        assert 1 == filesystem.same_file("/test", "/test///")

    def test_same(self):
        assert 1 == filesystem.same_file("/home/123", "/home/123")
        assert 1 == filesystem.same_file("D:\\", "D:\\")
        assert 1 == filesystem.same_file("/test/../test", "/test")
        assert 1 == filesystem.same_file("test/../test", "test")
        assert 1 == filesystem.same_file("/test/./test", "/test/test")
        assert 1 == filesystem.same_file("./test", "test")

    def test_subfolder(self):
        assert 2 == filesystem.same_file("\\\\?\\C:\\", "\\\\?\\C:\\Users\\")
        assert 2 == filesystem.same_file("/home/test123", "/home/test123/sub")
        assert 2 == filesystem.same_file("/test", "/test/./test")
        assert 2 == filesystem.same_file("/home/../test", "/test/./test")

    @set_platform("win32")
    def test_capitalization(self):
        # Only matters on Windows/macOS
        assert 1 == filesystem.same_file("/HOME/123", "/home/123")
        assert 1 == filesystem.same_file("D:\\", "d:\\")
        assert 2 == filesystem.same_file("\\\\?\\c:\\", "\\\\?\\C:\\Users\\")

    @pytest.mark.skipif(sys.platform.startswith(("win", "darwin")), reason="Requires a case-sensitive filesystem")
    @set_platform("linux")
    def test_capitalization_linux(self):
        assert 2 == filesystem.same_file("/home/test123", "/home/test123/sub")
        assert 0 == filesystem.same_file("/test", "/Test")
        assert 0 == filesystem.same_file("tesT", "Test")
        assert 0 == filesystem.same_file("/test/../Home", "/home")


class TestClipLongPath:
    def test_empty(self):
        assert filesystem.clip_path(None) is None
        assert filesystem.long_path(None) is None

    @set_platform("win32")
    def test_clip_path_win(self):
        assert filesystem.clip_path(r"\\?\UNC\test") == r"\\test"
        assert filesystem.clip_path(r"\\?\F:\test") == r"F:\test"

    @set_platform("win32")
    def test_nothing_to_clip_win(self):
        assert filesystem.clip_path(r"\\test") == r"\\test"
        assert filesystem.clip_path(r"F:\test") == r"F:\test"
        assert filesystem.clip_path("/test/dir") == "/test/dir"

    @set_platform("linux")
    def test_clip_path_non_win(self):
        # Shouldn't have any effect on platforms other than Windows
        assert filesystem.clip_path(r"\\?\UNC\test") == r"\\?\UNC\test"
        assert filesystem.clip_path(r"\\?\F:\test") == r"\\?\F:\test"
        assert filesystem.clip_path(r"\\test") == r"\\test"
        assert filesystem.clip_path(r"F:\test") == r"F:\test"
        assert filesystem.clip_path("/test/dir") == "/test/dir"

    @set_platform("win32")
    def test_long_path_win(self):
        assert filesystem.long_path(r"\\test") == r"\\?\UNC\test"
        assert filesystem.long_path(r"F:\test") == r"\\?\F:\test"

    @set_platform("win32")
    def test_nothing_to_lenghten_win(self):
        assert filesystem.long_path(r"\\?\UNC\test") == r"\\?\UNC\test"
        assert filesystem.long_path(r"\\?\F:\test") == r"\\?\F:\test"

    @set_platform("linux")
    def test_long_path_non_win(self):
        # Shouldn't have any effect on platforms other than Windows
        assert filesystem.long_path(r"\\?\UNC\test") == r"\\?\UNC\test"
        assert filesystem.long_path(r"\\?\F:\test") == r"\\?\F:\test"
        assert filesystem.long_path(r"\\test") == r"\\test"
        assert filesystem.long_path(r"F:\test") == r"F:\test"
        assert filesystem.long_path("/test/dir") == "/test/dir"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
class TestCheckMountLinux(ffs.TestCase):
    # Our collection of fake directories
    test_dirs = ["/media/test/dir", "/mnt/TEST/DIR"]

    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True
        for test_dir in self.test_dirs:
            self.fs.create_dir(test_dir, perm_bits=755)
            # Sanity check the fake filesystem
            assert os.path.exists(test_dir) is True

    @set_platform("linux")
    def test_bare_mountpoint_linux(self):
        assert filesystem.check_mount("/media") is True
        assert filesystem.check_mount("/media/") is True
        assert filesystem.check_mount("/mnt") is True
        assert filesystem.check_mount("/mnt/") is True

    @set_platform("linux")
    def test_existing_dir_linux(self):
        assert filesystem.check_mount("/media/test") is True
        assert filesystem.check_mount("/media/test/dir/") is True
        assert filesystem.check_mount("/media/test/DIR/") is True
        assert filesystem.check_mount("/mnt/TEST") is True
        assert filesystem.check_mount("/mnt/TEST/dir/") is True
        assert filesystem.check_mount("/mnt/TEST/DIR/") is True

    @set_platform("linux")
    # Cut down a bit on the waiting time
    @set_config({"wait_ext_drive": 1})
    def test_dir_nonexistent_linux(self):
        # Filesystem is case-sensitive on this platform
        assert filesystem.check_mount("/media/TEST") is False  # Issue #1457
        assert filesystem.check_mount("/media/TesT/") is False
        assert filesystem.check_mount("/mnt/TeSt/DIR") is False
        assert filesystem.check_mount("/mnt/test/DiR/") is False

    @set_platform("linux")
    def test_dir_outsider_linux(self):
        # Outside of /media and /mnt
        assert filesystem.check_mount("/test/that/") is True
        # Root directory
        assert filesystem.check_mount("/") is True


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
class TestCheckMountMacOS(ffs.TestCase):
    # Our faked macos directory
    test_dir = "/Volumes/test/dir"

    def setUp(self):
        self.setUpPyfakefs()
        self.fs.os = OSType.MACOS
        self.fs.create_dir(self.test_dir, perm_bits=755)
        # Verify the fake filesystem does its thing
        assert os.path.exists(self.test_dir) is True

    @set_platform("macos")
    def test_bare_mountpoint_macos(self):
        assert filesystem.check_mount("/Volumes") is True
        assert filesystem.check_mount("/Volumes/") is True

    @set_platform("macos")
    def test_existing_dir_macos(self):
        assert filesystem.check_mount("/Volumes/test") is True
        assert filesystem.check_mount("/Volumes/test/dir/") is True
        # Filesystem is set case-insensitive for this platform
        assert filesystem.check_mount("/VOLUMES/test") is True
        assert filesystem.check_mount("/volumes/Test/dir/") is True

    @set_platform("macos")
    # Cut down a bit on the waiting time
    @set_config({"wait_ext_drive": 1})
    def test_dir_nonexistent_macos(self):
        # Within /Volumes
        assert filesystem.check_mount("/Volumes/nosuchdir") is False  # Issue #1457
        assert filesystem.check_mount("/Volumes/noSuchDir/") is False
        assert filesystem.check_mount("/Volumes/nosuchDIR/subdir") is False
        assert filesystem.check_mount("/Volumes/NOsuchdir/subdir/") is False

    @set_platform("macos")
    def test_dir_outsider_macos(self):
        # Outside of /Volumes
        assert filesystem.check_mount("/test/that/") is True
        # Root directory
        assert filesystem.check_mount("/") is True


class TestCheckMountWin(ffs.TestCase):
    # Our faked windows directory
    test_dir = r"F:\test\dir"

    def setUp(self):
        self.setUpPyfakefs()
        self.fs.os = OSType.WINDOWS
        self.fs.create_dir(self.test_dir)
        # Sanity check the fake filesystem
        assert os.path.exists(self.test_dir) is True

    @set_platform("win32")
    def test_existing_dir_win(self):
        assert filesystem.check_mount("F:\\test") is True
        assert filesystem.check_mount("F:\\test\\dir\\") is True
        # Filesystem and drive letters are case-insensitive on this platform
        assert filesystem.check_mount("f:\\Test") is True
        assert filesystem.check_mount("f:\\test\\DIR\\") is True

    @set_platform("win32")
    def test_bare_mountpoint_win(self):
        assert filesystem.check_mount("F:\\") is True
        assert filesystem.check_mount("Z:\\") is False

    @set_platform("win32")
    def test_dir_nonexistent_win(self):
        # The existence of the drive letter is what really matters
        assert filesystem.check_mount("F:\\NoSuchDir") is True
        assert filesystem.check_mount("F:\\NoSuchDir\\") is True
        assert filesystem.check_mount("F:\\NOsuchdir\\subdir") is True
        assert filesystem.check_mount("F:\\nosuchDIR\\subdir\\") is True

    @set_platform("win32")
    # Cut down a bit on the waiting time
    @set_config({"wait_ext_drive": 1})
    def test_dir_on_nonexistent_drive_win(self):
        # Non-existent drive-letter
        assert filesystem.check_mount("H:\\NoSuchDir") is False
        assert filesystem.check_mount("E:\\NoSuchDir\\") is False
        assert filesystem.check_mount("L:\\NOsuchdir\\subdir") is False
        assert filesystem.check_mount("L:\\nosuchDIR\\subdir\\") is False

    @set_platform("win32")
    def test_dir_outsider_win(self):
        # Outside the local filesystem
        assert filesystem.check_mount("//test/that/") is True


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
class TestListdirFull(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True

    def test_nonexistent_dir(self):
        assert filesystem.listdir_full("/foo/bar") == []

    def test_no_exceptions(self):
        test_files = (
            "/test/dir/file1.ext",
            "/test/dir/file2",
            "/test/dir/sub/sub/sub/dir/file3.ext",
        )
        for file in test_files:
            self.fs.create_file(file)
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

    def test_exception_appledouble(self):
        # Anything below a .AppleDouble directory should be omitted
        test_file = "/foo/bar/.AppleDouble/Oooooo.ps"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full("/foo") == []
        assert filesystem.listdir_full("/foo/bar") == []
        assert filesystem.listdir_full("/foo/bar/.AppleDouble") == []
        assert filesystem.listdir_full("/foo", recursive=False) == []
        assert filesystem.listdir_full("/foo/bar", recursive=False) == []
        assert filesystem.listdir_full("/foo/bar/.AppleDouble", recursive=False) == []

    def test_exception_dsstore(self):
        # Anything below a .DS_Store directory should be omitted
        for file in (
            "/some/FILE",
            "/some/.DS_Store/oh.NO",
            "/some/.DS_Store/subdir/The.End",
        ):
            self.fs.create_file(file)
            assert os.path.exists(file) is True
        assert filesystem.listdir_full("/some") == ["/some/FILE"]
        assert filesystem.listdir_full("/some/.DS_Store/") == []
        assert filesystem.listdir_full("/some/.DS_Store/subdir") == []
        assert filesystem.listdir_full("/some", recursive=False) == ["/some/FILE"]
        assert filesystem.listdir_full("/some/.DS_Store/", recursive=False) == []
        assert filesystem.listdir_full("/some/.DS_Store/subdir", recursive=False) == []

    def test_invalid_file_argument(self):
        # This is obviously not intended use; the function expects a directory
        # as its argument, not a file. Test anyway.
        test_file = "/dev/sleepy"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full(test_file) == []


class TestListdirFullWin(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.os = OSType.WINDOWS

    def test_nonexistent_dir(self):
        assert filesystem.listdir_full(r"F:\foo\bar") == []

    def test_no_exceptions(self):
        test_files = (
            r"f:\test\dir\file1.ext",
            r"f:\test\dir\file2",
            r"f:\test\dir\sub\sub\sub\dir\file3.ext",
        )
        for file in test_files:
            self.fs.create_file(file)
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

    def test_exception_appledouble(self):
        # Anything below a .AppleDouble directory should be omitted
        test_file = r"f:\foo\bar\.AppleDouble\Oooooo.ps"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full(r"f:\foo") == []
        assert filesystem.listdir_full(r"f:\foo\bar") == []
        assert filesystem.listdir_full(r"F:\foo\bar\.AppleDouble") == []
        assert filesystem.listdir_full(r"f:\foo", recursive=False) == []
        assert filesystem.listdir_full(r"f:\foo\bar", recursive=False) == []
        assert filesystem.listdir_full(r"F:\foo\bar\.AppleDouble", recursive=False) == []

    def test_exception_dsstore(self):
        # Anything below a .DS_Store directory should be omitted
        for file in (
            r"f:\some\FILE",
            r"f:\some\.DS_Store\oh.NO",
            r"f:\some\.DS_Store\subdir\The.End",
        ):
            self.fs.create_file(file)
            assert os.path.exists(file) is True
        assert filesystem.listdir_full(r"f:\some") == [r"f:\some\FILE"]
        assert filesystem.listdir_full(r"f:\some\.DS_Store") == []
        assert filesystem.listdir_full(r"f:\some\.DS_Store\subdir") == []
        assert filesystem.listdir_full(r"f:\some", recursive=True) == [r"f:\some\FILE"]
        assert filesystem.listdir_full(r"f:\some\.DS_Store", recursive=True) == []
        assert filesystem.listdir_full(r"f:\some\.DS_Store\subdir", recursive=True) == []

    def test_invalid_file_argument(self):
        # This is obviously not intended use; the function expects a directory
        # as its argument, not a file. Test anyway.
        test_file = r"f:\dev\sleepy"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.listdir_full(test_file) == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
class TestGetUniqueDirFilename(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True

    # Reduce the waiting time when the function calls check_mount()
    @set_config({"wait_ext_drive": 1})
    def test_nonexistent_dir(self):
        # Absolute path
        assert filesystem.get_unique_dir("/foo/bar", n=0, create_dir=False) == "/foo/bar"
        # Absolute path in a location that matters to check_mount
        assert filesystem.get_unique_dir("/mnt/foo/bar", n=0, create_dir=False) == "/mnt/foo/bar"
        # Relative path
        if self.fs.cwd != "/":
            os.chdir("/")
        assert filesystem.get_unique_dir("foo/bar", n=0, create_dir=False) == "foo/bar"

    def test_creating_dir(self):
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

    def test_nonexistent_file(self):
        assert filesystem.get_unique_filename("/dir/file.name") == "/dir/file.name"
        # Relative path
        assert filesystem.get_unique_filename("dir/file.name") == "dir/file.name"

    def test_existing_file(self):
        test_file = "/dir/file.name"
        max_obstruct = 11  # High enough for double digits
        self.fs.create_file(test_file)
        assert os.path.exists(test_file)
        # Create obstructions
        for n in range(1, max_obstruct):
            file_n = "/dir/file." + str(n) + ".name"
            self.fs.create_file(file_n)
            assert os.path.exists(file_n)
        assert filesystem.get_unique_filename(test_file) == "/dir/file." + str(max_obstruct) + ".name"

    def test_existing_file_without_extension(self):
        test_file = "/some/filename"
        # Create obstructions
        self.fs.create_file(test_file)
        assert os.path.exists(test_file)
        first_filename = filesystem.get_unique_filename(test_file)
        assert first_filename == "/some/filename.1"
        self.fs.create_file(first_filename)
        assert filesystem.get_unique_filename(test_file) == "/some/filename.2"


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows specific tests")
class TestGetUniqueDirFilenameWin(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.os = OSType.WINDOWS

    # Reduce the waiting time when the function calls check_mount()
    @set_config({"wait_ext_drive": 1})
    def test_nonexistent_dir(self):
        # Absolute path
        assert filesystem.get_unique_dir(r"C:\No\Such\Dir", n=0, create_dir=False).lower() == r"c:\no\such\dir"
        # Relative path
        assert filesystem.get_unique_dir(r"foo\bar", n=0, create_dir=False).lower() == r"foo\bar"

    def test_creating_dir(self):
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

    def test_nonexistent_file(self):
        assert filesystem.get_unique_filename(r"C:\DIR\file.name").lower() == r"c:\dir\file.name"
        # Relative path
        assert filesystem.get_unique_filename(r"DIR\file.name").lower() == r"dir\file.name"

    def test_existing_file(self):
        test_file = r"C:\dir\file.name"
        max_obstruct = 11  # High enough for double digits
        self.fs.create_file(test_file)
        assert os.path.exists(test_file)
        # Create obstructions
        for n in range(1, max_obstruct):
            file_n = r"C:\dir\file." + str(n) + ".name"
            self.fs.create_file(file_n)
            assert os.path.exists(file_n)
        assert filesystem.get_unique_filename(test_file).lower() == r"c:\dir\file." + str(max_obstruct) + ".name"

    def test_existing_file_without_extension(self):
        test_file = r"c:\some\filename"
        # Create obstructions
        self.fs.create_file(test_file)
        assert os.path.exists(test_file)
        assert filesystem.get_unique_filename(test_file).lower() == r"c:\some\filename.1"


class TestCreateAllDirsWin(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.os = OSType.WINDOWS

    @set_platform("win32")
    def test_create_all_dirs(self):
        self.directory = self.fs.create_dir(r"C:\Downloads")
        # Also test for no crash when folder already exists
        for folder in (r"C:\Downloads", r"C:\Downloads\Show\Test", r"C:\Downloads\Show\Test2", r"C:\Downloads\Show"):
            assert filesystem.create_all_dirs(folder) == folder
            assert os.path.exists(folder)


class PermissionCheckerHelper:
    @staticmethod
    def assert_dir_perms(path, expected_perms):
        assert stat.filemode(os.stat(path).st_mode) == "d" + stat.filemode(expected_perms)[1:]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
class TestCreateAllDirs(ffs.TestCase, PermissionCheckerHelper):
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True

    def test_basic_folder_creation(self):
        self.fs.create_dir("/test_base")
        # Also test for no crash when folder already exists
        for folder in ("/test_base", "/test_base/show/season 1/episode 1", "/test_base/show"):
            assert filesystem.create_all_dirs(folder) == folder
            assert os.path.exists(folder)

    @set_config({"permissions": "0777"})
    def test_permissions_777(self):
        self._permissions_runner("/test_base777")
        self._permissions_runner("/test_base777_nomask", apply_permissions=False)

    @set_config({"permissions": "0770"})
    def test_permissions_770(self):
        self._permissions_runner("/test_base770")
        self._permissions_runner("/test_base770_nomask", apply_permissions=False)

    @set_config({"permissions": "0600"})
    def test_permissions_600(self):
        self._permissions_runner("/test_base600")
        self._permissions_runner("/test_base600_nomask", apply_permissions=False)

    @set_config({"permissions": "0700"})
    def test_permissions_450(self):
        with pytest.raises(OSError):
            self._permissions_runner("/test_base450", perms_base="0450")

    def test_no_permissions(self):
        self._permissions_runner("/test_base_perm700", perms_base="0700")
        self._permissions_runner("/test_base_perm750", perms_base="0750")
        self._permissions_runner("/test_base_perm777", perms_base="0777")
        self._permissions_runner("/test_base_perm600", perms_base="0600")

    def _permissions_runner(self, test_base, perms_base="0700", apply_permissions=True):
        # Create base directory and set the base permissions
        perms_base_int = int(perms_base, 8)
        self.fs.create_dir(test_base, perms_base_int)
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


class TestSetPermissionsWin(ffs.TestCase):
    @set_platform("win32")
    def test_win32(self):
        # Should not do or return anything on Windows
        assert filesystem.set_permissions(r"F:\who\cares", recursive=False) is None


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
class TestSetPermissions(ffs.TestCase, PermissionCheckerHelper):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True
        self.fs.umask = int("0755", 8)  # rwxr-xr-x

    def _runner(self, perms_before_test):
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
        self.fs.create_dir(test_dir, perms_before_test)
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
                    self.fs.create_dir(basefolder, perms_before_test)
                except PermissionError:
                    ffs.set_uid(0)
                    self.fs.create_file(file, perms_before_test)
            assert os.path.exists(basefolder) is True
            self.assert_dir_perms(basefolder, perms_before_test)

            # Add a random one of the forbidden bits
            file_perms_before_test = perms_before_test | choice(
                (stat.S_ISUID, stat.S_ISGID, stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH)
            )

            # Then, create the file
            try:
                self.fs.create_file(file, file_perms_before_test)
            except PermissionError:
                ffs.set_uid(0)
                self.fs.create_file(file, file_perms_before_test)

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
        ffs.set_uid(0)
        self.fs.remove_object(test_dir)
        assert os.path.exists(test_dir) is False
        ffs.set_uid(global_uid)

    @set_platform("linux")
    def test_empty_permissions_setting(self):
        # World writable directory
        self._runner("0777")
        self._runner("0450")

    @set_platform("linux")
    @set_config({"permissions": "0760"})
    def test_dir0777_permissions0760_setting(self):
        # World-writable directory, permissions 760
        self._runner("0777")

    @set_platform("linux")
    @set_config({"permissions": "0617"})
    def test_dir0450_permissions0617_setting(self):
        # Insufficient base access
        self._runner("0450")

    @set_platform("linux")
    @set_config({"permissions": "2455"})
    def test_dir0444_permissions2455_setting(self):
        # Insufficient access, permissions with setgid (should be stripped)
        self._runner("0444")

    @set_platform("linux")
    @set_config({"permissions": "4755"})
    def test_dir1755_permissions4755_setting(self):
        # Sticky bit on directory, permissions with setuid (should be stripped)
        self._runner("1755")


class TestRenamer:
    # test filesystem.renamer() for different scenario's
    def test_renamer(self):
        # First of all, create a working directory (with a random name)
        dirname = os.path.join(SAB_DATA_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

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
        sameleveldirname = os.path.join(SAB_DATA_DIR, "othertestdir" + str(random.randint(10000, 99999)))
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
        except:
            pass
        assert os.path.isfile(filename)
        assert not os.path.isfile(newfilename)

        # Creation of subdirectory is allowed if create_local_directories=True
        Path(filename).touch()
        newfilename = os.path.join(dirname, "newsubdir", "newfile.txt")
        try:
            filesystem.renamer(filename, newfilename, create_local_directories=True)
        except:
            pass
        assert not os.path.isfile(filename)
        assert os.path.isfile(newfilename)

        # Creation of subdirectory plus deeper sudbdir is allowed if create_local_directories=True
        Path(filename).touch()
        newfilename = os.path.join(dirname, "newsubdir", "deepersubdir", "newfile.txt")
        try:
            filesystem.renamer(filename, newfilename, create_local_directories=True)
        except:
            pass
        assert not os.path.isfile(filename)
        assert os.path.isfile(newfilename)

        # ... escaping the directory plus subdir creation is not allowed
        Path(filename).touch()
        newfilename = os.path.join(dirname, "..", "newsubdir", "newfile.txt")
        try:
            filesystem.renamer(filename, newfilename, create_local_directories=True)
        except:
            pass
        assert os.path.isfile(filename)
        assert not os.path.isfile(newfilename)

        # Cleanup working directory
        shutil.rmtree(dirname)


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

    @set_config({"unwanted_extensions_mode": 0, "unwanted_extensions": test_extensions})
    def test_has_unwanted_extension_blacklist_mode(self):
        for filename, result in self.test_params:
            assert filesystem.has_unwanted_extension(filename) is result

    @set_config({"unwanted_extensions_mode": 1, "unwanted_extensions": test_extensions})
    def test_has_unwanted_extension_whitelist_mode(self):
        for filename, result in self.test_params:
            if filesystem.get_ext(filename):
                assert filesystem.has_unwanted_extension(filename) is not result
            else:
                # missing extension is never considered unwanted
                assert filesystem.has_unwanted_extension(filename) is False

    @set_config({"unwanted_extensions_mode": 0, "unwanted_extensions": ""})
    def test_has_unwanted_extension_empty_blacklist(self):
        for filename, result in self.test_params:
            assert filesystem.has_unwanted_extension(filename) is False

    @set_config({"unwanted_extensions_mode": 1, "unwanted_extensions": ""})
    def test_has_unwanted_extension_empty_whitelist(self):
        for filename, result in self.test_params:
            if filesystem.get_ext(filename):
                assert filesystem.has_unwanted_extension(filename) is True
            else:
                # missing extension is never considered unwanted
                assert filesystem.has_unwanted_extension(filename) is False


class TestDirectoryWriting:
    # very basic test of directory_is_writable()
    def test_directory_is_writable(self):
        # let's test on the tempdir provided by the OS:
        # on Windows, only basic writing testing will be done, and should succeed
        # on non-Windows, assuming tempdir is not on FAT, full test should happen, and succeed
        assert filesystem.directory_is_writable(tempfile.gettempdir())
