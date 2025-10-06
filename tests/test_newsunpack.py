#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
tests.test_newsunpack - Tests of various functions in newspack
"""
import glob
import logging
import os.path
import shutil
from unittest.mock import call


from tests.testhelper import *

import sabnzbd
import sabnzbd.newsunpack as newsunpack
from sabnzbd.constants import JOB_ADMIN
from sabnzbd.misc import format_time_string
from sabnzbd.filesystem import long_path, create_all_dirs, listdir_full


class TestNewsUnpackFunctions:
    def test_is_sfv_file(self):
        assert newsunpack.is_sfv_file("tests/data/good_sfv_unicode.sfv")
        assert newsunpack.is_sfv_file("tests/data/one_line.sfv")
        assert not newsunpack.is_sfv_file("tests/data/only_comments.sfv")
        assert not newsunpack.is_sfv_file("tests/data/random.bin")

    def test_is_sevenfile(self):
        # False, because the command is not set
        assert not newsunpack.SEVENZIP_COMMAND
        assert not newsunpack.is_sevenfile("tests/data/test_7zip/testfile.7z")

        # Set the command to get some real results
        newsunpack.find_programs(".")
        assert newsunpack.SEVENZIP_COMMAND
        assert not newsunpack.is_sevenfile("tests/data/only_comments.sfv")
        assert not newsunpack.is_sevenfile("tests/data/random.bin")
        assert not newsunpack.is_sevenfile("tests/data/par2file/basic_16k.par2")
        assert newsunpack.is_sevenfile("tests/data/test_7zip/testfile.7z")

    def test_sevenzip(self):
        testzip = newsunpack.SevenZip("tests/data/test_7zip/testfile.7z")
        assert testzip.namelist() == ["My_Test_Download.bin"]
        # Basic check that we can get data from the 7zip
        assert len(testzip.open(testzip.namelist()[0]).read()) == 102400

        # Test with a non-7zip file
        with pytest.raises(TypeError):
            newsunpack.SevenZip("tests/data/basic_rar5/testfile.rar")


@pytest.mark.usefixtures("clean_cache_dir")
class TestPar2Repair:
    @staticmethod
    def _run_par2repair(test_dir, caplog, break_file=None, remove_file=None):
        # Create data-directory with copy of our test-files
        temp_test_dir = os.path.join(SAB_CACHE_DIR, "par2repair_temp")
        test_dir_admin = os.path.join(temp_test_dir, JOB_ADMIN)
        os.mkdir(temp_test_dir)
        assert os.path.exists(temp_test_dir)
        os.mkdir(test_dir_admin)
        assert os.path.exists(test_dir_admin)

        # Copy all test files
        for file in glob.glob(test_dir + "/*"):
            shutil.copy(file, temp_test_dir)

        # Break a specific file, if requested
        if break_file:
            with open(os.path.join(temp_test_dir, break_file), "wb") as bf:
                bf.seek(10)
                bf.write(b"booh")

        # Remove a specific file, if requested
        if remove_file:
            os.unlink(os.path.join(temp_test_dir, remove_file))

        # Make sure all programs are found
        newsunpack.find_programs(".")

        # Needed to store the POpen-reference
        sabnzbd.PostProcessor = mock.Mock()

        # Mock basic NZO structure
        nzo = mock.Mock()
        nzo.download_path = temp_test_dir
        nzo.admin_path = test_dir_admin
        nzo.fail_msg = ""
        nzo.extrapars = {"test": []}
        nzo.par2packs = {"test": None}

        for file in glob.glob(test_dir + "/*.par2"):
            # Simple NZF mock for the filename
            parfile = mock.Mock()
            parfile.filename = os.path.basename(file)
            nzo.extrapars["test"].append(parfile)

        # We want to collect all updates
        nzo.set_action_line = mock.Mock()
        nzo.set_unpack_info = mock.Mock()
        nzo.renamed_file = mock.Mock()

        # Run repair
        with caplog.at_level(logging.DEBUG):
            readd, result = newsunpack.par2_repair(nzo=nzo, setname="test")

        # Verify we only have the rar-files left
        dir_contents = os.listdir(temp_test_dir)
        dir_contents.sort()

        # Always cleanup, to be sure
        shutil.rmtree(temp_test_dir)
        assert not os.path.exists(temp_test_dir)

        # Verify result
        assert result
        assert not readd

        # Verify history updates
        # Try with multiple values, as it can take longer sometimes
        for text in ("[test] Verified in %s, repair is required", "[test] Repaired in %s"):
            for i in range(10):
                try:
                    nzo.set_unpack_info.assert_has_calls([call("Repair", text % format_time_string(i))])
                    break
                except AssertionError:
                    pass
            else:
                # It never succeeded
                raise AssertionError("Failed to match: %s" % text)

        # Check externally
        return nzo, dir_contents

    def test_basic(self, caplog):
        # Run code
        nzo, dir_contents = self._run_par2repair("tests/data/par2repair/basic", caplog)

        assert dir_contents == [
            "__ADMIN__",
            "notarealfile.rar",
            "par2test.part1.rar",
            "par2test.part2.rar",
            "par2test.part3.rar",
            "par2test.part4.rar",
            "par2test.part5.rar",
            "par2test.part6.rar",
        ]

        # Verify renames
        nzo.renamed_file.assert_has_calls(
            [
                call(
                    {
                        "par2test.part3.rar": "foorbar.rar",
                        "par2test.part4.rar": "stillrarbutnotagoodname.txt",
                        "par2test.part1.rar": "par2test.part1.11.rar",
                    }
                )
            ]
        )

        # par2cmdline output status updates
        # Verify output in chunks, as it outputs every single % during repair
        nzo.set_action_line.assert_has_calls(
            [
                call("Repair", "Quick Checking"),
                call("Repair", "Starting Repair"),
                call("Verifying", "01/06"),
                call("Verifying", "02/06"),
                call("Verifying", "03/06"),
                call("Verifying", "04/06"),
                call("Verifying", "05/06"),
                call("Verifying", "06/06"),
                call("Checking extra files", "01"),
                call("Checking extra files", "02"),
                call("Checking extra files", "03"),
                call("Repairing", " 0%"),
            ]
        )
        nzo.set_action_line.assert_has_calls(
            [
                call("Repairing", "100% "),
                call("Verifying repair", "01/03"),
                call("Verifying repair", "02/03"),
                call("Verifying repair", "03/03"),
            ]
        )

    def test_filejoin(self, caplog):
        # Run code
        nzo, dir_contents = self._run_par2repair("tests/data/par2repair/filejoin", caplog)

        # All joinable files will be removed
        assert dir_contents == ["__ADMIN__", "par2test.bin"]

        # There are no renames in case of filejoin by par2repair!
        nzo.renamed_file.assert_not_called()

        # par2cmdline output status updates
        # Verify output in chunks, as it outputs every single % during repair
        nzo.set_action_line.assert_has_calls(
            [
                call("Repair", "Quick Checking"),
                call("Repair", "Starting Repair"),
                call("Verifying", "01/01"),
                call("Checking extra files", "01"),
                call("Checking extra files", "02"),
                call("Checking extra files", "03"),
                call("Checking extra files", "04"),
                call("Checking extra files", "05"),
                call("Checking extra files", "06"),
                call("Checking extra files", "07"),
                call("Checking extra files", "08"),
                call("Checking extra files", "09"),
                call("Checking extra files", "10"),
                call("Checking extra files", "11"),
                call("Repairing", " 0%"),
            ]
        )
        nzo.set_action_line.assert_has_calls(
            [
                call("Repairing", "100% "),
                call("Verifying repair", "01/01"),
            ]
        )

    def test_broken_filejoin(self, caplog):
        # Run code
        nzo, dir_contents = self._run_par2repair(
            "tests/data/par2repair/filejoin", caplog, break_file="par2test.bin.005", remove_file="par2test.bin.010"
        )

        # There are no renames in case of filejoin by par2repair!
        nzo.renamed_file.assert_not_called()

        # All joinable files should be removed
        assert dir_contents == ["__ADMIN__", "par2test.bin"]

        # Verify output in chunks, as it outputs every single % during repair
        nzo.set_action_line.assert_has_calls(
            [
                call("Repair", "Quick Checking"),
                call("Repair", "Starting Repair"),
                call("Verifying", "01/01"),
                call("Checking extra files", "01"),
                call("Checking extra files", "02"),
                call("Checking extra files", "03"),
                call("Checking extra files", "04"),
                call("Checking extra files", "05"),
                call("Checking extra files", "06"),
                call("Checking extra files", "07"),
                call("Checking extra files", "08"),
                call("Checking extra files", "09"),
                call("Repairing", " 0%"),
            ]
        )
        nzo.set_action_line.assert_has_calls(
            [
                call("Repairing", "100% "),
                call("Verifying repair", "01/01"),
            ]
        )


@pytest.mark.usefixtures("clean_cache_dir")
class TestRarUnpack:
    @staticmethod
    def _create_test_nzo(temp_dir, filename="test.nzb"):
        """Create a mock NZO object for testing"""
        nzo = mock.Mock()
        nzo.download_path = temp_dir
        nzo.admin_path = os.path.join(temp_dir, JOB_ADMIN)
        nzo.fail_msg = ""
        nzo.final_name = filename
        nzo.delete = True  # Enable deletion of extracted files
        nzo.direct_unpacker = None  # No direct unpacker
        nzo.set_unpack_info = mock.Mock()
        nzo.set_action_line = mock.Mock()

        # Mock password-related attributes
        nzo.password = ""  # No password by default
        nzo.nzo_info = {}  # Empty nzo_info
        nzo.meta = {}  # Empty meta data
        nzo.correct_password = ""  # No correct password found yet

        return nzo

    @staticmethod
    def _run_rar_unpack(
        test_dir,
        rar_files,
        one_folder=False,
        custom_temp_test_dir=None,
        custom_temp_complete_dir=None,
        custom_nzo_settings=None,
    ):
        """Run rar_unpack with test data"""
        # Base
        temp_test_dir_base = temp_test_dir = long_path(os.path.join(SAB_CACHE_DIR, "rar_unpack_temp"))
        temp_complete_dir_base = temp_complete_dir = long_path(os.path.join(SAB_CACHE_DIR, "rar_complete_temp"))

        # Extend if needed
        if custom_temp_test_dir:
            temp_test_dir = os.path.join(temp_test_dir, custom_temp_test_dir)
        if custom_temp_complete_dir:
            temp_complete_dir = os.path.join(temp_complete_dir, custom_temp_complete_dir)

        assert create_all_dirs(temp_test_dir), f"Failed to create {temp_test_dir}"
        assert create_all_dirs(temp_complete_dir), f"Failed to create {temp_complete_dir}"

        # Copy test files to temp directory
        copied_rars = []
        for rar_file in rar_files:
            src_path = os.path.join(test_dir, rar_file)
            if os.path.exists(src_path):
                dst_path = os.path.join(temp_test_dir, rar_file)
                shutil.copy(src_path, dst_path)
                copied_rars.append(dst_path)

        # Make sure all programs are found
        newsunpack.find_programs(".")

        # Mock PostProcessor that's needed for RAR extraction
        sabnzbd.PostProcessor = mock.Mock()

        # Create mock NZO
        nzo = TestRarUnpack._create_test_nzo(temp_test_dir)

        # Apply custom NZO settings if provided
        if custom_nzo_settings:
            for key, value in custom_nzo_settings.items():
                setattr(nzo, key, value)

        try:
            # Run the rar_unpack function
            error_code, extracted_files = newsunpack.rar_unpack(nzo, temp_complete_dir, one_folder, copied_rars)

            # Get directory contents with full paths
            complete_contents = listdir_full(temp_complete_dir) if os.path.exists(temp_complete_dir) else []
            download_contents = os.listdir(temp_test_dir) if os.path.exists(temp_test_dir) else []

            return error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir

        finally:
            # Cleanup
            shutil.rmtree(temp_test_dir_base)
            shutil.rmtree(temp_complete_dir_base)

    def _assert_successful_extraction(
        self,
        error_code,
        extracted_files,
        complete_contents,
        download_contents,
        temp_complete_dir,
        expected_files,
        should_delete_original=True,
        original_files=None,
    ):
        """Helper method to assert common successful extraction conditions"""
        # Check that extraction was successful
        assert error_code == 0, "RAR extraction should succeed"
        assert len(extracted_files) > 0, "Should have extracted files"
        assert len(complete_contents) > 0, "Should have files in complete directory"

        # Check file deletion behavior
        if should_delete_original and original_files:
            for original_file in original_files:
                rar_still_exists = any(original_file in f for f in download_contents)
                assert not rar_still_exists, f"Original RAR file {original_file} should be deleted after extraction"
        elif not should_delete_original and original_files:
            for original_file in original_files:
                rar_still_exists = any(original_file in f for f in download_contents)
                assert rar_still_exists, f"Original RAR file {original_file} should still exist when delete=False"

        # Verify full paths, but since extracted_files also includes the in-between folders we use issubset
        complete_contents_set = set(complete_contents)
        extracted_files_set = set(extracted_files)
        assert complete_contents_set.issubset(
            extracted_files_set
        ), f"{complete_contents_set} should be in {extracted_files_set}"

        # Verify the expected files are present using full paths
        expected_full_paths = {os.path.join(temp_complete_dir, filename) for filename in expected_files}
        assert expected_full_paths.issubset(
            extracted_files_set
        ), f"{expected_full_paths} should be in {extracted_files_set}"

    def test_basic_rar_unpack(self):
        """Test basic RAR unpacking functionality"""
        test_dir = "tests/data/basic_rar5"
        rar_files = ["testfile.rar"]
        expected_files = {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"}

        error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_no_delete(self):
        """Test RAR unpacking without deleting the original files"""
        test_dir = "tests/data/basic_rar5"
        rar_files = ["testfile.rar"]
        expected_files = {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"}
        custom_nzo_settings = {"delete": False}

        error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, custom_nzo_settings=custom_nzo_settings)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=False,
            original_files=rar_files,
        )

    def test_rar_unpack_long_path(self):
        """Test RAR unpacking with very long paths (>260 characters) for both download and complete directories"""

        # Create very long paths that exceed 260 characters on all platforms
        # This tests handling of long paths universally, not just on Windows

        # Build long nested directory structure to guarantee >260 character paths
        long_dir_name = "very_long_directory_name_" + "x" * 100  # 82 characters
        nested_path_parts = [long_dir_name] * 4  # 4 levels of 82-char names = 328

        temp_test_dir = os.path.join(*nested_path_parts)
        temp_complete_dir = os.path.join(*nested_path_parts)

        assert len(temp_test_dir) > 260, "Should have test directory > 260 characters"
        assert len(temp_complete_dir) > 0, "Should have complete directory > 260 characters"

        test_dir = "tests/data/basic_rar5"
        rar_files = ["testfile.rar"]
        expected_files = {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"}

        error_code, extracted_files, complete_contents, download_contents, nzo, actual_temp_complete_dir = (
            self._run_rar_unpack(
                test_dir, rar_files, custom_temp_test_dir=temp_test_dir, custom_temp_complete_dir=temp_complete_dir
            )
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            actual_temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_rar_long_path_inside(self):
        """Test  RAR unpacking functionality for file with long paths inside"""

        # Test with the basic rar5 test file
        test_dir = "tests/data/rar_long_path_inside"
        rar_files = ["long_path_in_rar.rar"]
        expected_files = {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"}

        # The long nested directory structure inside the rar is build the same as test_rar_unpack_long_path
        long_dir_name = "very_long_directory_name_" + "x" * 100  # 82 characters
        nested_path_parts = [long_dir_name] * 4  # 4 levels of 82-char names = 328
        expected_files = {os.path.join(*nested_path_parts, expected_file) for expected_file in expected_files}

        error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_multipart_unicode(self):
        """Test multi-part RAR unpacking with unicode filenames"""

        # Test with unicode multi-part RAR files
        test_dir = "tests/data/unicode_rar"
        rar_files = [
            "我喜欢编程.part1.rar",
            "我喜欢编程.part2.rar",
            "我喜欢编程.part3.rar",
            "我喜欢编程.part4.rar",
            "我喜欢编程.part5.rar",
            "我喜欢编程.part6.rar",
        ]
        expected_files = {"我喜欢编程_My_Test_Download.bin"}

        error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_passworded(self):
        """Test RAR unpacking with password-protected file"""

        # Test with password-protected RAR file
        test_dir = "tests/data/test_passworded{{secret}}"
        rar_files = ["passworded-file.rar"]
        expected_files = {"testfile.bin", "My_Test_Download.bin"}

        # Set NZO with the correct password
        custom_nzo_settings = {
            "password": "secret",  # The password is "secret"
            "nzo_info": {"password": "secret"},  # Also set in nzo_info
            "meta": {"password": ["secret"]},  # And in meta for get_all_passwords
        }

        error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, custom_nzo_settings=custom_nzo_settings)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_wrong_password(self):
        """Test RAR unpacking with wrong password fails appropriately"""

        # Test with password-protected RAR file but wrong password
        test_dir = "tests/data/test_passworded{{secret}}"
        rar_files = ["passworded-file.rar"]

        # Set NZO with the wrong password
        custom_nzo_settings = {
            "password": "wrongpassword",  # Wrong password
            "nzo_info": {"password": "wrongpassword"},
            "meta": {"password": ["wrongpassword"]},
        }

        error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, custom_nzo_settings=custom_nzo_settings)
        )

        # Check that extraction failed with wrong password (error_code 2 = wrong password)
        assert error_code == 2, "Password-protected RAR extraction should fail with wrong password (error_code 2)"
        assert len(extracted_files) == 0, "Should have no extracted files with wrong password"
        assert len(complete_contents) == 0, "Should have no files in complete directory with wrong password"

        # Verify that the original RAR file still exists (extraction failed)
        rar_still_exists = any("passworded-file.rar" in f for f in download_contents)
        assert rar_still_exists, "Original RAR file should still exist when extraction fails"

    def test_rar_unpack_invalid_windows_filenames(self):
        """Test RAR unpacking with Windows-invalid filenames (allowed to fail on Windows)

        This test contains a RAR file with filenames that are invalid on Windows
        (e.g., files named CON, AUX, PRN, etc. or containing invalid characters).
        On Windows, this extraction may fail, which is acceptable behavior.
        """
        # Test with RAR containing Windows-invalid filenames
        test_dir = "tests/data/rar_invalid_windows"
        rar_files = ["rar_invalid_on_windows.rar"]

        # Check for expected corrected filenames, Unrar corrects it on Windows
        if sabnzbd.WINDOWS:
            expected_files = {"blabla __ bla _ bla __ __ bla ___ CON.bin"}
        else:
            expected_files = {'blabla :: bla " bla << || bla ??? CON.bin'}

        error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )
