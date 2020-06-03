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
tests.test_filesystem - Testing functions in filesystem.py
"""
import os
import stat
import pyfakefs.fake_filesystem_unittest as ffs

import sabnzbd.filesystem as filesystem
import sabnzbd.cfg

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

    @set_platform("darwin")
    def test_colon_handling_darwin(self):
        assert filesystem.sanitize_filename("test:aftertest") == "aftertest"
        assert filesystem.sanitize_filename(":aftertest") == "aftertest"
        assert filesystem.sanitize_filename("::aftertest") == "aftertest"
        assert filesystem.sanitize_filename(":after:test") == "test"
        # Empty after sanitising with darwin colon handling
        assert filesystem.sanitize_filename(":") == "unknown"
        assert filesystem.sanitize_filename("test:") == "unknown"
        assert filesystem.sanitize_filename("test: ") == "unknown"

    @set_platform("linux")
    @set_config({"sanitize_safe": False})
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
    @set_config({"sanitize_safe": False})
    def test_win_devices_not_win(self):
        # Linux and Darwin are the same for this
        assert filesystem.sanitize_filename(None) is None
        assert filesystem.sanitize_filename("aux.txt") == "aux.txt"
        assert filesystem.sanitize_filename("txt.aux") == "txt.aux"
        assert filesystem.sanitize_filename("$mft") == "$mft"
        assert filesystem.sanitize_filename("a$mft") == "a$mft"

    @set_platform("linux")
    @set_config({"sanitize_safe": False})
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
    @set_config({"sanitize_safe": False})
    def test_folder_illegal_chars_linux(self):
        assert filesystem.sanitize_foldername('test"aftertest') == "test'aftertest"
        assert filesystem.sanitize_foldername("test:") == "test-"
        assert filesystem.sanitize_foldername("test<>?*|aftertest") == "test<>?*|aftertest"

    def test_char_collections(self):
        assert len(filesystem.CH_ILLEGAL) == len(filesystem.CH_LEGAL)
        assert len(filesystem.CH_ILLEGAL_WIN) == len(filesystem.CH_LEGAL_WIN)

    @set_platform("linux")
    @set_config({"sanitize_safe": False})
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
        assert filesystem.sanitize_foldername("/test/this.") == "+test+this"
        assert filesystem.sanitize_foldername("/test./this.") == "+test.+this"

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


class TestSameFile:
    def test_nothing_in_common_win_paths(self):
        assert 0 == filesystem.same_file("C:\\", "D:\\")
        assert 0 == filesystem.same_file("C:\\", "/home/test")

    def test_nothing_in_common_unix_paths(self):
        assert 0 == filesystem.same_file("/home/", "/data/test")
        assert 0 == filesystem.same_file("/test/home/test", "/home/")
        assert 0 == filesystem.same_file("/test/../home", "/test")
        assert 0 == filesystem.same_file("/test/./test", "/test")

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Not for Windows")
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


class TestIsObfuscatedFilename:
    def test_obfuscated(self):
        # Files are considered obfuscated if they lack an extension
        assert filesystem.is_obfuscated_filename(".") is True
        assert filesystem.is_obfuscated_filename("..") is True
        assert filesystem.is_obfuscated_filename(".test") is True
        assert filesystem.is_obfuscated_filename("test.") is True
        assert filesystem.is_obfuscated_filename("test.ext.") is True
        assert filesystem.is_obfuscated_filename("t.....") is True
        assert filesystem.is_obfuscated_filename("a_" + ("test" * 666)) is True

    def test_not_obfuscated(self):
        assert filesystem.is_obfuscated_filename("test.ext") is False
        assert filesystem.is_obfuscated_filename(".test.ext") is False
        assert filesystem.is_obfuscated_filename("test..ext") is False
        assert filesystem.is_obfuscated_filename("test.ext") is False
        assert filesystem.is_obfuscated_filename("test .ext") is False
        assert filesystem.is_obfuscated_filename("test. ext") is False
        assert filesystem.is_obfuscated_filename("test . ext") is False
        assert filesystem.is_obfuscated_filename("a." + ("test" * 666)) is False


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


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Broken on Windows")
class TestCheckMountLinux(ffs.TestCase):
    # Our collection of fake directories
    test_dirs = ["/media/test/dir", "/mnt/TEST/DIR"]

    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True
        for dir in self.test_dirs:
            self.fs.create_dir(dir, perm_bits=755)
            # Sanity check the fake filesystem
            assert os.path.exists(dir) is True

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


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Broken on Windows")
class TestCheckMountDarwin(ffs.TestCase):
    # Our faked macos directory
    test_dir = "/Volumes/test/dir"

    def setUp(self):
        self.setUpPyfakefs()
        self.fs.is_macos = True
        self.fs.is_case_sensitive = False
        self.fs.path_separator = "/"
        self.fs.create_dir(self.test_dir, perm_bits=755)
        # Verify the fake filesystem does its thing
        assert os.path.exists(self.test_dir) is True

    @set_platform("darwin")
    def test_bare_mountpoint_darwin(self):
        assert filesystem.check_mount("/Volumes") is True
        assert filesystem.check_mount("/Volumes/") is True

    @set_platform("darwin")
    def test_existing_dir_darwin(self):
        assert filesystem.check_mount("/Volumes/test") is True
        assert filesystem.check_mount("/Volumes/test/dir/") is True
        # Filesystem is set case-insensitive for this platform
        assert filesystem.check_mount("/VOLUMES/test") is True
        assert filesystem.check_mount("/volumes/Test/dir/") is True

    @set_platform("darwin")
    # Cut down a bit on the waiting time
    @set_config({"wait_ext_drive": 1})
    def test_dir_nonexistent_darwin(self):
        # Within /Volumes
        assert filesystem.check_mount("/Volumes/nosuchdir") is False  # Issue #1457
        assert filesystem.check_mount("/Volumes/noSuchDir/") is False
        assert filesystem.check_mount("/Volumes/nosuchDIR/subdir") is False
        assert filesystem.check_mount("/Volumes/NOsuchdir/subdir/") is False

    @set_platform("darwin")
    def test_dir_outsider_darwin(self):
        # Outside of /Volumes
        assert filesystem.check_mount("/test/that/") is True
        # Root directory
        assert filesystem.check_mount("/") is True


class TestCheckMountWin(ffs.TestCase):
    # Our faked windows directory
    test_dir = r"F:\test\dir"

    def setUp(self):
        self.setUpPyfakefs()
        self.fs.is_windows_fs = True
        self.fs.is_case_sensitive = False
        self.fs.path_separator = "\\"
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
        # The existance of the drive letter is what really matters
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


class TestTrimWinPath:
    @set_platform("win32")
    def test_short_path(self):
        assert filesystem.trim_win_path(r"C:\short\path") == r"C:\short\path"

    @pytest.mark.xfail(sys.platform == "win32", reason="Bug in trim_win_path")
    @set_platform("win32")
    def test_long_path_short_segments(self):
        test_path = "C:\\" + "A" * 20 + "\\" + "B" * 20 + "\\" + "C" * 20  # Strlen 65
        # Current code causes the path to end up with strlen 70 rather than 69 on Windows
        assert filesystem.trim_win_path(test_path + "\\" + ("D" * 20)) == test_path + "\\" + "D" * 3


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Broken on Windows")
class TestRecursiveListdir(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True

    def test_nonexistent_dir(self):
        assert filesystem.recursive_listdir("/foo/bar") == []

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
        results_subdir = filesystem.recursive_listdir("/test/dir")
        assert len(results_subdir) == 3
        for entry in test_files:
            assert (entry in results_subdir) is True

        # List the same directory again, this time using its parent as the function argument.
        # Results should be identical, since there's nothing in /test but that one subdirectory
        results_parent = filesystem.recursive_listdir("/test")
        # Don't make assumptions about the sorting of the lists of results
        results_parent.sort()
        results_subdir.sort()
        assert results_parent == results_subdir

        # List that subsubsub-directory; no sorting required for a single result
        assert filesystem.recursive_listdir("/test/dir/sub/sub") == ["/test/dir/sub/sub/sub/dir/file3.ext"]

    def test_exception_appledouble(self):
        # Anything below a .AppleDouble directory should be omitted
        test_file = "/foo/bar/.AppleDouble/Oooooo.ps"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.recursive_listdir("/foo") == []
        assert filesystem.recursive_listdir("/foo/bar") == []
        assert filesystem.recursive_listdir("/foo/bar/.AppleDouble") == []

    def test_exception_dsstore(self):
        # Anything below a .DS_Store directory should be omitted
        for file in (
            "/some/FILE",
            "/some/.DS_Store/oh.NO",
            "/some/.DS_Store/subdir/The.End",
        ):
            self.fs.create_file(file)
            assert os.path.exists(file) is True
        assert filesystem.recursive_listdir("/some") == ["/some/FILE"]
        assert filesystem.recursive_listdir("/some/.DS_Store/") == []
        assert filesystem.recursive_listdir("/some/.DS_Store/subdir") == []

    def test_invalid_file_argument(self):
        # This is obviously not intended use; the function expects a directory
        # as its argument, not a file. Test anyway.
        test_file = "/dev/sleepy"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.recursive_listdir(test_file) == []


class TestRecursiveListdirWin(ffs.TestCase):
    # Basic fake filesystem setup stanza
    @set_platform("win32")
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.is_windows_fs = True
        self.fs.path_separator = "\\"
        self.fs.is_case_sensitive = False

    def test_nonexistent_dir(self):
        assert filesystem.recursive_listdir(r"F:\foo\bar") == []

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
        results_subdir = filesystem.recursive_listdir(r"f:\test\dir")
        assert len(results_subdir) == 3
        for entry in test_files:
            assert (entry in results_subdir) is True

        # List the same directory again, this time using its parent as the function argument.
        # Results should be identical, since there's nothing in /test but that one subdirectory
        results_parent = filesystem.recursive_listdir(r"f:\test")
        # Don't make assumptions about the sorting of the lists of results
        results_parent.sort()
        results_subdir.sort()
        assert results_parent == results_subdir

        # List that subsubsub-directory; no sorting required for a single result
        assert (
            filesystem.recursive_listdir(r"F:\test\dir\SUB\sub")[0].lower() == r"f:\test\dir\sub\sub\sub\dir\file3.ext"
        )

    def test_exception_appledouble(self):
        # Anything below a .AppleDouble directory should be omitted
        test_file = r"f:\foo\bar\.AppleDouble\Oooooo.ps"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.recursive_listdir(r"f:\foo") == []
        assert filesystem.recursive_listdir(r"f:\foo\bar") == []
        assert filesystem.recursive_listdir(r"F:\foo\bar\.AppleDouble") == []

    def test_exception_dsstore(self):
        # Anything below a .DS_Store directory should be omitted
        for file in (
            r"f:\some\FILE",
            r"f:\some\.DS_Store\oh.NO",
            r"f:\some\.DS_Store\subdir\The.End",
        ):
            self.fs.create_file(file)
            assert os.path.exists(file) is True
        assert filesystem.recursive_listdir(r"f:\some") == [r"f:\some\FILE"]
        assert filesystem.recursive_listdir(r"f:\some\.DS_Store") == []
        assert filesystem.recursive_listdir(r"f:\some\.DS_Store\subdir") == []

    def test_invalid_file_argument(self):
        # This is obviously not intended use; the function expects a directory
        # as its argument, not a file. Test anyway.
        test_file = r"f:\dev\sleepy"
        self.fs.create_file(test_file)
        assert os.path.exists(test_file) is True
        assert filesystem.recursive_listdir(test_file) == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Broken on Windows")
class TestGetUniquePathFilename(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True

    # Reduce the waiting time when the function calls check_mount()
    @set_config({"wait_ext_drive": 1})
    def test_nonexistent_dir(self):
        # Absolute path
        assert filesystem.get_unique_path("/foo/bar", n=0, create_dir=False) == "/foo/bar"
        # Absolute path in a location that matters to check_mount
        assert filesystem.get_unique_path("/mnt/foo/bar", n=0, create_dir=False) == "/mnt/foo/bar"
        # Relative path
        if self.fs.cwd != "/":
            os.chdir("/")
        assert filesystem.get_unique_path("foo/bar", n=0, create_dir=False) == "foo/bar"

    def test_creating_dir(self):
        # First call also creates the directory for us
        assert filesystem.get_unique_path("/foo/bar", n=0, create_dir=True) == "/foo/bar"
        # Verify creation of the path
        assert os.path.exists("/foo/bar") is True
        # Directories from previous loops get in the way
        for dir_n in range(1, 11):  # Go high enough for double digits
            assert filesystem.get_unique_path("/foo/bar", n=0, create_dir=True) == "/foo/bar." + str(dir_n)
            assert os.path.exists("/foo/bar." + str(dir_n)) is True
        # Explicitly set parameter n
        assert filesystem.get_unique_path("/foo/bar", n=666, create_dir=True) == "/foo/bar.666"
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
        assert filesystem.get_unique_filename(test_file) == "/some/filename.1"


class TestGetUniquePathFilenameWin(ffs.TestCase):
    # Basic fake filesystem setup stanza
    @set_platform("win32")
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.is_windows_fs = True
        self.fs.path_separator = "\\"
        self.fs.is_case_sensitive = False

    # Reduce the waiting time when the function calls check_mount()
    @set_config({"wait_ext_drive": 1})
    def test_nonexistent_dir(self):
        # Absolute path
        assert filesystem.get_unique_path(r"C:\No\Such\Dir", n=0, create_dir=False).lower() == r"c:\no\such\dir"
        # Relative path
        assert filesystem.get_unique_path(r"foo\bar", n=0, create_dir=False).lower() == r"foo\bar"

    def test_creating_dir(self):
        # First call also creates the directory for us
        assert filesystem.get_unique_path(r"C:\foo\BAR", n=0, create_dir=True).lower() == r"c:\foo\bar"
        # Verify creation of the path
        assert os.path.exists(r"c:\foo\bar") is True
        # Directories from previous loops get in the way
        for dir_n in range(1, 11):  # Go high enough for double digits
            assert filesystem.get_unique_path(r"c:\foo\bar", n=0, create_dir=True) == r"c:\foo\bar." + str(dir_n)
            assert os.path.exists(r"c:\foo\bar." + str(dir_n)) is True
        # Explicitly set parameter n
        assert filesystem.get_unique_path(r"c:\Foo\Bar", n=666, create_dir=True).lower() == r"c:\foo\bar.666"
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


class TestSetPermissionsWin(ffs.TestCase):
    @set_platform("win32")
    def test_win32(self):
        # Should not do or return anything on Windows
        assert filesystem.set_permissions(r"F:\who\cares", recursive=False) is None


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Broken on Windows")
class TestSetPermissions(ffs.TestCase):
    # Basic fake filesystem setup stanza
    def setUp(self):
        self.setUpPyfakefs()
        self.fs.path_separator = "/"
        self.fs.is_case_sensitive = True
        self.fs.umask = int("0755", 8)  # rwxr-xr-x

    def _runner(self, perms_test, perms_after):
        """
        Generic test runner for permissions testing. The umask is set per test
        via the relevant sab config option; the fileystem parameter in setUp().
        Note that the umask set in the environment before starting the program
        also affects the results if sabnzbd.cfg.umask isn't set.

        Arguments:
            str perms_test: permissions for test objects, chmod style "0755".
            str perms_after: expected permissions after completion of the test.
        """
        perms_test = int(perms_test, 8)
        if sabnzbd.cfg.umask():
            perms_after = int(perms_after, 8)
        else:
            perms_after = int("0777", 8) & (sabnzbd.ORG_UMASK ^ int("0777", 8))

        # Setup and verify fake dir
        test_dir = "/test"
        try:
            self.fs.create_dir(test_dir, perms_test)
        except PermissionError:
            ffs.set_uid(0)
            self.fs.create_dir(test_dir, perms_test)
        assert os.path.exists(test_dir) is True
        assert stat.filemode(os.stat(test_dir).st_mode) == "d" + stat.filemode(perms_test)[1:]

        # Setup and verify fake files
        for file in (
            "foobar",
            "file.ext",
            "sub/dir/.nzb",
            "another/sub/dir/WithSome.File",
        ):
            file = os.path.join(test_dir, file)
            try:
                self.fs.create_file(file, perms_test)
            except PermissionError:
                try:
                    ffs.set_uid(0)
                    self.fs.create_file(file, perms_test)
                except Exception:
                    # Skip creating files, if not even using root gets the job done.
                    break
            assert os.path.exists(file) is True
            assert stat.filemode(os.stat(file).st_mode)[1:] == stat.filemode(perms_test)[1:]

        # Set permissions, recursive by default
        filesystem.set_permissions(test_dir)

        # Check the results
        for root, dirs, files in os.walk(test_dir):
            for dir in [os.path.join(root, d) for d in dirs]:
                # Permissions on directories should now match perms_after
                assert stat.filemode(os.stat(dir).st_mode) == "d" + stat.filemode(perms_after)[1:]
            for file in [os.path.join(root, f) for f in files]:
                # Files also shouldn't have any executable or special bits set
                assert (
                    stat.filemode(os.stat(file).st_mode)[1:]
                    == stat.filemode(
                        perms_after & ~(stat.S_ISUID | stat.S_ISGID | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    )[1:]
                )

        # Cleanup
        ffs.set_uid(0)
        self.fs.remove_object(test_dir)
        assert os.path.exists(test_dir) is False
        ffs.set_uid(global_uid)

    @set_platform("linux")
    @set_config({"umask": ""})
    def test_dir0777_empty_umask_setting(self):
        # World writable directory
        self._runner("0777", "0700")

    @set_platform("linux")
    @set_config({"umask": ""})
    def test_dir0450_empty_umask_setting(self):
        # Insufficient access
        self._runner("0450", "0700")

    @set_platform("linux")
    @set_config({"umask": ""})
    def test_dir0000_empty_umask_setting(self):
        # Weird directory permissions
        self._runner("0000", "0700")

    @set_platform("linux")
    @set_config({"umask": "0760"})
    def test_dir0777_umask0760_setting(self):
        # World-writable directory, umask 760
        self._runner("0777", "0760")

    @set_platform("linux")
    @set_config({"umask": "0617"})
    def test_dir0450_umask0617_setting(self):
        # Insufficient access, weird umask
        self._runner("0450", "0717")

    @set_platform("linux")
    @set_config({"umask": "0000"})
    def test_dir0405_umask0000_setting(self):
        # Insufficient access on all fronts, weird umask
        self._runner("0405", "0700")

    @set_platform("linux")
    @set_config({"umask": "2455"})
    def test_dir0444_umask2455_setting(self):
        # Insufficient access, weird umask with setgid
        self._runner("0444", "2755")

    @set_platform("linux")
    @set_config({"umask": "4755"})
    def test_dir1755_umask4755_setting(self):
        # Sticky bit on directory, umask with setuid
        self._runner("1755", "4755")
