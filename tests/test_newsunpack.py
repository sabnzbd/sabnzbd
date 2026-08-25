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
tests.test_newsunpack - Tests of various functions in newspack
"""

import datetime
import glob
import io
import json
import logging
import os
import os.path
import shutil
import stat
import sys
import tarfile
from typing import Optional
from unittest import mock
from unittest.mock import call

import pytest

import sabnzbd
import sabnzbd.newsunpack as newsunpack
from sabnzbd.constants import JOB_ADMIN
from tests.testhelper import SAB_CACHE_DIR
from sabnzbd.misc import format_time_string, SABRarFile
from sabnzbd.filesystem import long_path, create_all_dirs, listdir_full, clip_path


class TestNewsUnpackFunctions:
    def test_is_sfv_file(self):
        assert newsunpack.is_sfv_file("tests/data/good_sfv_unicode.sfv")
        assert newsunpack.is_sfv_file("tests/data/one_line.sfv")
        assert not newsunpack.is_sfv_file("tests/data/only_comments.sfv")
        assert not newsunpack.is_sfv_file("tests/data/random.bin")

    def test_sfv_check_blocks_path_traversal(self, tmp_path):
        """A traversing SFV filename must not move a file out of the job directory"""
        download_path = str(tmp_path)
        obfuscated_name = "6f1ed002ab5595859014ebf0951522d9"
        obfuscated_path = os.path.join(download_path, obfuscated_name)
        with open(obfuscated_path, "wb") as test_file:
            test_file.write(b"payload")

        # SFV entry with matching crc32 but a traversing target name
        sfv_path = os.path.join(download_path, "check.sfv")
        with open(sfv_path, "w") as sfv_file:
            sfv_file.write("../escaped.bin deadbeef\n")

        nzf = mock.Mock(filename=obfuscated_name, filepath=obfuscated_path, crc32=0xDEADBEEF)
        nzo = mock.Mock(download_path=download_path, finished_files=[nzf])

        assert newsunpack.sfv_check([sfv_path], nzo) is False
        assert not os.path.exists(os.path.join(download_path, os.pardir, "escaped.bin"))
        assert os.path.exists(obfuscated_path)

    def test_is_sevenfile(self, monkeypatch):
        # False, because the command is not set. Force it explicitly: SEVENZIP_COMMAND
        # is a module global that another test in this class may have populated via
        # find_programs(), and under pytest-xdist tests share no ordering guarantee.
        monkeypatch.setattr(newsunpack, "SEVENZIP_COMMAND", None)
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
        newsunpack.find_programs(".")
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
    def _create_test_nzo(temp_dir, filename: str = "test.nzb", password: Optional[str] = None):
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
        nzo.password = password
        nzo.nzo_info = {}  # Empty nzo_info
        nzo.meta = {}  # Empty meta data
        nzo.correct_password = password

        return nzo

    @staticmethod
    def _run_rar_unpack(
        test_dir,
        rar_files,
        one_folder=False,
        custom_temp_test_dir=None,
        custom_temp_complete_dir=None,
        custom_nzo_settings=None,
        password=None,
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
        nzo = TestRarUnpack._create_test_nzo(temp_test_dir, password=password)

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

    @pytest.mark.parametrize(
        "test_dir, rar_files, expected_files, password",
        [
            (
                "tests/data/basic_rar3",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                None,
            ),
            # RAR3 does not support header encryption
            (
                "tests/data/basic_rar3_64",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
            ),
            (
                "tests/data/basic_rar4_16_header",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42e",
            ),
            # Long password triggers Rar3Sha1 slow path
            (
                "tests/data/basic_rar4_64_header",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
            ),
            # Password truncated to 127
            (
                "tests/data/basic_rar4_128_header",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "sgq6gxzcjupw6kmn3zk49dudy9iuwkuo4232zm3ygafo3me7wuj47grf3oap3sk6gfr7d7u6zobvjoxwo98xuuuqa78vqqmhxyxq7ego7modk49bhuw6cahfdqr7hyf",
            ),
            (
                "tests/data/basic_rar5",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                None,
            ),
            (
                "tests/data/basic_rar5_64_header_blake2",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
            ),
        ],
    )
    def test_basic_rar_unpack(self, test_dir, rar_files, expected_files, password):
        for rar_file in rar_files:
            with SABRarFile(os.path.join(test_dir, rar_file), part_only=True) as zf:
                zf.setpassword(password)
                assert zf.namelist()

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, password=password)
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

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
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

        error_code, extracted_files, complete_contents, download_contents, _nzo, actual_temp_complete_dir = (
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

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
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

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
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

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
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

        error_code, extracted_files, complete_contents, download_contents, _nzo, _temp_complete_dir = (
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

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
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


@pytest.mark.skipif(sys.version_info < (3, 12), reason="tarfile extraction filter requires Python 3.12 or later")
@pytest.mark.usefixtures("clean_cache_dir")
class TestTarUnpack:
    @staticmethod
    def _run_tar_unpack(
        test_dir,
        tar_files,
        one_folder=False,
        custom_temp_test_dir=None,
        custom_temp_complete_dir=None,
        custom_nzo_settings=None,
    ):
        """Run tar_unpack with test data"""
        # Base
        temp_test_dir_base = temp_test_dir = long_path(os.path.join(SAB_CACHE_DIR, "tar_unpack_temp"))
        temp_complete_dir_base = temp_complete_dir = long_path(os.path.join(SAB_CACHE_DIR, "tar_complete_temp"))

        # Extend if needed
        if custom_temp_test_dir:
            temp_test_dir = os.path.join(temp_test_dir, custom_temp_test_dir)
        if custom_temp_complete_dir:
            temp_complete_dir = os.path.join(temp_complete_dir, custom_temp_complete_dir)

        assert create_all_dirs(temp_test_dir), f"Failed to create {temp_test_dir}"
        assert create_all_dirs(temp_complete_dir), f"Failed to create {temp_complete_dir}"

        # Copy test files to temp directory
        copied_tars = []
        for tar_file in tar_files:
            src_path = os.path.join(test_dir, tar_file)
            if os.path.exists(src_path):
                dst_path = os.path.join(temp_test_dir, tar_file)
                shutil.copy(src_path, dst_path)
                copied_tars.append(dst_path)

        # Make sure all programs are found
        newsunpack.find_programs(".")

        # Mock PostProcessor that's needed for TAR extraction
        sabnzbd.PostProcessor = mock.Mock()

        # Create mock NZO
        nzo = TestRarUnpack._create_test_nzo(temp_test_dir)

        # Apply custom NZO settings if provided
        if custom_nzo_settings:
            for key, value in custom_nzo_settings.items():
                setattr(nzo, key, value)

        try:
            # Run the tar_unpack function
            error_code, extracted_files = newsunpack.tar_unpack(nzo, temp_complete_dir, one_folder, copied_tars)

            # Get directory contents with full paths
            complete_contents = listdir_full(temp_complete_dir) if os.path.exists(temp_complete_dir) else []
            download_contents = os.listdir(temp_test_dir) if os.path.exists(temp_test_dir) else []

            # Check nothing extracted is executable
            if not sabnzbd.WINDOWS:
                for file_path in complete_contents:
                    assert not os.access(file_path, os.X_OK), "%s is executable" % file_path
                    st = os.stat(file_path)
                    assert st.st_mode & 0o777 == 0o666 & ~sabnzbd.ORG_UMASK
                    assert st.st_uid == os.getuid(), "%s has wrong owner" % file_path
                    assert st.st_gid == os.getgid(), "%s has wrong group" % file_path

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
        assert error_code == 0, "TAR extraction should succeed"
        assert len(extracted_files) > 0, "Should have extracted files"
        assert len(complete_contents) > 0, "Should have files in complete directory"

        # Check file deletion behavior
        if should_delete_original and original_files:
            for original_file in original_files:
                tar_still_exists = any(original_file in f for f in download_contents)
                assert not tar_still_exists, f"Original TAR file {original_file} should be deleted after extraction"
        elif not should_delete_original and original_files:
            for original_file in original_files:
                tar_still_exists = any(original_file in f for f in download_contents)
                assert tar_still_exists, f"Original TAR file {original_file} should still exist when delete=False"

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

    def test_basic_tar_unpack(self):
        """Test basic TAR unpacking functionality"""
        test_dir = "tests/data/test_tar"
        tar_files = ["testfile.tar"]
        expected_files = {"My_Test_Download.bin"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_tar_unpack(test_dir, tar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=tar_files,
        )

    def test_path_traversal_tar_unpack(self, tmp_path):
        tar_path = tmp_path / "bad.tar"

        # Create a tar containing a path traversal entry
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("../evil.txt")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"evil"))

        tar_files = ["bad.tar"]

        error_code, extracted_files, _complete_contents, _download_contents, _nzo, _temp_complete_dir = (
            self._run_tar_unpack(str(tmp_path), tar_files)
        )

        assert error_code == 1, "TAR extraction should fail"
        assert not extracted_files

    def test_owner_permissions_sanitized_tar_unpack(self, tmp_path):
        tar_path = tmp_path / "owner.tar"

        # Create a tar containing a file owned by root with read, write, and execute permissions for everyone
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("file.txt")
            info.size = 4
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mode = 0o777
            tar.addfile(info, io.BytesIO(b"test"))

        tar_files = ["owner.tar"]
        expected_files = {"file.txt"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_tar_unpack(str(tmp_path), tar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=tar_files,
        )

    def test_one_folder_tar_unpack(self, tmp_path):
        tar_path = tmp_path / "flatten.tar"

        # Create a tar containing a file owned by root with read, write, and execute permissions for everyone
        with tarfile.open(tar_path, "w") as tar:
            for i in range(2):
                info = tarfile.TarInfo(os.path.join(str(i), "file.txt"))
                info.size = 4
                tar.addfile(info, io.BytesIO(b"test"))

        tar_files = ["flatten.tar"]
        expected_files = {"file.txt", "file.1.txt"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_tar_unpack(str(tmp_path), tar_files, True)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=tar_files,
        )


@pytest.mark.usefixtures("clean_cache_dir")
class TestExternalProcessingEnv:
    """Harness for the SAB_* environment variables passed to post-processing scripts.

    external_processing() builds the environment (via create_env) and runs a user script.
    These tests invoke a *real* receiving script that captures every SAB_* variable it sees
    and echoes them back as JSON, so any SAB_* variable can be asserted on. The round-trip
    proves the script decodes exactly the values SAB sent.

    SAB_FILES gets extra attention because its value is itself a JSON list of the new files:
    emojis, non-latin characters and characters that must be JSON-escaped (quotes,
    backslashes, tabs, newlines, control chars) all have to survive the round-trip intact.
    """

    # Receiving script: capture every SAB_* variable and echo it back. SAB_FILES is the only
    # variable SAB JSON-encodes, so it is the only one this script json-decodes; all other
    # values are passed through as plain strings. The script deliberately has no shebang,
    # so build_and_run_command() prepends the current interpreter (sys.executable) and it
    # runs under the same Python as the test suite. The captured mapping is re-emitted as
    # ASCII-safe JSON purely to ferry it back over stdout, independent of the console encoding.
    RECEIVING_SCRIPT = (
        "import os, json\n"
        "env = {k: v for k, v in os.environ.items() if k.startswith('SAB_')}\n"
        "if 'SAB_FILES' in env:\n"
        "    env['SAB_FILES'] = json.loads(env['SAB_FILES'])\n"
        "print(json.dumps(env))\n"
    )

    # Realistic defaults so every SAB_<field> derived from the NZO is a clean string unless
    # a test overrides it. Keys mirror newsunpack.ENV_NZO_FIELDS.
    NZO_DEFAULTS = {
        "bytes": 1024,
        "bytes_downloaded": 1024,
        "bytes_tried": 1024,
        "cat": "movies",
        "correct_password": "",
        "duplicate": False,
        "duplicate_key": "",
        "encrypted": 0,
        "fail_msg": "",
        "filename": "test.nzb",
        "final_name": "Test Job",
        "group": "alt.binaries.test",
        "nzo_id": "SABnzbd_nzo_abc123",
        "oversized": False,
        "password": "",
        "pp": 3,
        "priority": 0,
        "repair": True,
        "script": "recv.py",
        "status": "Completed",
        "unpack": True,
        "unwanted_ext": 0,
        "url": "",
    }

    @staticmethod
    def _write_receiving_script(directory: str) -> str:
        """Write the receiving script and give it the execute bit post-proc scripts need."""
        script_path = os.path.join(directory, "recv_sab_env.py")
        with open(script_path, "w", encoding="utf-8") as script_file:
            script_file.write(TestExternalProcessingEnv.RECEIVING_SCRIPT)
        os.chmod(
            script_path,
            os.stat(script_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )
        return script_path

    @classmethod
    def _make_nzo(cls, admin_dir: str, overrides: dict):
        """A mock NZO with clean string values for every field create_env reads."""
        nzo = mock.Mock()
        for field, value in {**cls.NZO_DEFAULTS, **overrides}.items():
            setattr(nzo, field, value)
        nzo.nzo_info = {}
        nzo.admin_path = admin_dir
        nzo.avg_bps_total = 0
        nzo.avg_bps_freq = 0
        nzo.avg_date = datetime.datetime(2026, 1, 1)
        return nzo

    def _run(self, filenames=None, status=0, nzo_overrides=None):
        """Invoke external_processing with a real script.

        Returns (sab_env, complete_dir, ret) where 'sab_env' is the dict of every SAB_*
        variable exactly as the receiving script saw it.
        """
        base = long_path(os.path.join(SAB_CACHE_DIR, "sab_env"))
        complete_dir = os.path.join(base, "complete")
        admin_dir = os.path.join(base, JOB_ADMIN)
        assert create_all_dirs(complete_dir), f"Failed to create {complete_dir}"
        assert create_all_dirs(admin_dir), f"Failed to create {admin_dir}"

        script_path = self._write_receiving_script(base)

        # Full paths as external_processing receives them
        newfiles = [os.path.join(complete_dir, name) for name in (filenames or [])]

        nzo = self._make_nzo(admin_dir, nzo_overrides or {})
        sabnzbd.PostProcessor = mock.Mock()
        output, ret = newsunpack.external_processing(script_path, nzo, complete_dir, status, newfiles)

        sab_env = json.loads(output)
        return sab_env, clip_path(complete_dir), ret

    def _run_files(self, filenames):
        """SAB_FILES convenience wrapper: returns (decoded_files, expected, ret).

        The receiving script already json-decodes SAB_FILES, so sab_env["SAB_FILES"] is the
        list the script parsed out of the environment variable.
        """
        sab_env, complete_dir, ret = self._run(filenames=filenames)
        decoded = sab_env["SAB_FILES"]
        expected = sorted(os.path.relpath(os.path.join(complete_dir, name), complete_dir) for name in filenames)
        return decoded, expected, ret

    @pytest.mark.parametrize(
        "filenames",
        [
            pytest.param(["movie.mkv", "sample.mkv", "readme.txt"], id="plain-ascii"),
            pytest.param(
                ['quote".mkv', "back\\slash.mkv", "tab\tchar.txt", "new\nline.txt", "control\x01.dat"],
                id="json-escaped",
            ),
            pytest.param(["clip_🎬.mkv", "party_🎉🎉.mkv", "flag_🏴‍☠️.txt"], id="emoji"),
            pytest.param(
                ["naïve.txt", "Пример.mkv", "测试文件.mkv", "日本語のファイル.txt", "ملف.txt", "Ω_Δ.dat"],
                id="non-latin",
            ),
            pytest.param(['Movie (2026) 🎬 — naïve 测试 "final".mkv'], id="mixed"),
        ],
    )
    def test_sab_files_round_trip(self, filenames):
        """The receiving script decodes SAB_FILES to exactly the filenames that went in."""
        decoded, expected, ret = self._run_files(filenames)
        assert ret == 0
        assert decoded == expected

    def test_sab_files_is_sorted(self):
        """Unsorted input arrives at the script as a sorted list."""
        decoded, expected, ret = self._run_files(["zebra.mkv", "apple.mkv", "Éclair.mkv", "mango.mkv"])
        assert ret == 0
        assert decoded == sorted(decoded)
        assert decoded == expected

    def test_sab_files_relative_paths(self):
        """Files in subdirectories are made relative to the complete dir, no absolute leak."""
        decoded, expected, ret = self._run_files([os.path.join("Season 1", "épisode 🎬.mkv"), "root.mkv"])
        assert ret == 0
        assert decoded == expected
        assert all(not os.path.isabs(path) for path in decoded)

    def test_sab_files_empty(self):
        """No new files; SAB_FILES is an empty JSON list."""
        decoded, expected, ret = self._run_files([])
        assert ret == 0
        assert decoded == []
        assert expected == []

    @pytest.mark.parametrize(
        "field, value, env_var",
        [
            pytest.param("cat", "tv 📺", "SAB_CAT", id="cat-emoji"),
            pytest.param("final_name", "Naïve.Show.测试.S01", "SAB_FINAL_NAME", id="final_name-non-latin"),
            pytest.param("nzo_id", "SABnzbd_nzo_xyz789", "SAB_NZO_ID", id="nzo_id"),
            pytest.param("group", 'alt."quoted".group', "SAB_GROUP", id="group-quotes"),
        ],
    )
    def test_sab_nzo_field_round_trip(self, field, value, env_var):
        """Any NZO-derived SAB_* variable arrives at the script unchanged."""
        sab_env, _complete_dir, ret = self._run(nzo_overrides={field: value})
        assert ret == 0
        assert sab_env[env_var] == value

    def test_sab_bool_field_is_normalised(self):
        """Boolean NZO fields are passed as '1'/'0' (create_env's str(value * 1))."""
        sab_env, _complete_dir, ret = self._run(nzo_overrides={"repair": True, "duplicate": False})
        assert ret == 0
        assert sab_env["SAB_REPAIR"] == "1"
        assert sab_env["SAB_DUPLICATE"] == "0"

    def test_sab_always_supplied_fields(self):
        """The always-present SAB_* variables reflect the arguments and SAB globals."""
        sab_env, complete_dir, ret = self._run(status=2)
        assert ret == 0
        assert sab_env["SAB_VERSION"] == sabnzbd.__version__
        assert sab_env["SAB_COMPLETE_DIR"] == complete_dir
        assert sab_env["SAB_PP_STATUS"] == "2"
