#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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

        if sabnzbd.WIN32 and cfg.enable_multipar():
            # Multipar output status updates
            nzo.set_action_line.assert_has_calls(
                [
                    call("Repair", "Quick Checking"),
                    call("Repair", "Starting Repair"),
                    call("Checking", "01/06"),
                    call("Checking", "02/06"),
                    call("Checking", "03/06"),
                    call("Checking", "04/06"),
                    call("Checking", "05/06"),
                    call("Checking", "06/06"),
                    # We only know total of missing files, so not how many will be found
                    call("Checking extra files", "01/05"),
                    call("Checking extra files", "02/05"),
                    call("Verifying", "01/03"),
                    call("Verifying", "02/03"),
                    call("Verifying", "03/03"),
                    call("Repairing", " 0%"),
                    call("Repairing", "100% "),
                    call("Verifying repair", "01/03"),
                    call("Verifying repair", "02/03"),
                    call("Verifying repair", "03/03"),
                ]
            )
        else:
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

        if sabnzbd.WIN32 and cfg.enable_multipar():
            # Multipar output status updates, which is limited because Multipar doesn't say much..
            nzo.set_action_line.assert_has_calls(
                [
                    call("Repair", "Quick Checking"),
                    call("Repair", "Starting Repair"),
                    call("Checking", "01/01"),
                    call("Verifying", "01"),
                    call("Verifying", "02"),
                    call("Verifying", "03"),
                    call("Verifying", "04"),
                    call("Verifying", "05"),
                    call("Verifying", "06"),
                    call("Verifying", "07"),
                    call("Verifying", "08"),
                    call("Verifying", "09"),
                    call("Verifying", "10"),
                    call("Verifying", "11"),
                    call("Joining", "11"),
                    call("Verifying repair", "01/01"),
                ]
            )
        else:
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

        if sabnzbd.WIN32 and cfg.enable_multipar():
            # Multipar output status updates, which is limited because Multipar doesn't say much..
            nzo.set_action_line.assert_has_calls(
                [
                    call("Repair", "Quick Checking"),
                    call("Repair", "Starting Repair"),
                    call("Checking", "01/01"),
                    call("Verifying", "01"),
                    call("Verifying", "02"),
                    call("Verifying", "03"),
                    call("Verifying", "04"),
                    call("Verifying", "05"),
                    call("Verifying", "06"),
                    call("Verifying", "07"),
                    call("Verifying", "08"),
                    call("Verifying", "09"),
                    call("Repairing", " 0%"),
                    call("Repairing", "100% "),
                    call("Verifying repair", "01/01"),
                ]
            )
        else:
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
