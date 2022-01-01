#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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
        assert testzip.namelist() == ["testfile.bin"]
        # Basic check that we can get data from the 7zip
        assert len(testzip.open(testzip.namelist()[0]).read()) == 102400

        # Test with a non-7zip file
        with pytest.raises(TypeError):
            newsunpack.SevenZip("tests/data/basic_rar5/testfile.rar")


@pytest.mark.usefixtures("clean_cache_dir")
class TestPar2Repair:
    def test_basic(self, caplog):
        # Create data-directory with all we have
        test_dir = os.path.join(SAB_CACHE_DIR, "par2repair_temp")
        test_dir_admin = os.path.join(test_dir, JOB_ADMIN)
        os.mkdir(test_dir)
        assert os.path.exists(test_dir)
        os.mkdir(test_dir_admin)
        assert os.path.exists(test_dir_admin)
        for file in glob.glob("tests/data/par2repair/*"):
            shutil.copy(file, test_dir)

        # Make sure all programs are found
        newsunpack.find_programs(".")

        # Needed to store the POpen-reference
        sabnzbd.PostProcessor = mock.Mock()

        # Simple NZF mock for the filename
        parfile = mock.Mock()
        parfile.filename = "par2test.par2"

        # Mock basic NZO structure
        nzo = mock.Mock()
        nzo.admin_path = test_dir_admin
        nzo.fail_msg = ""
        nzo.extrapars = {"test": [parfile]}
        nzo.md5packs = {"test": None}

        # We want to collect all updates
        nzo.set_action_line = mock.Mock()
        nzo.set_unpack_info = mock.Mock()

        # Log all
        caplog.set_level(logging.DEBUG)

        # Run repair
        readd, result = newsunpack.par2_repair(nzo=nzo, workdir=test_dir, setname="test")

        # Always cleanup, to be sure
        shutil.rmtree(test_dir)
        assert not os.path.exists(test_dir)

        # Verify process
        assert result
        nzo.set_unpack_info.assert_has_calls(
            [
                call("Repair", "[test] Verified in 0 seconds, repair is required"),
                call("Repair", "[test] Repaired in 0 seconds"),
            ]
        )

        if sabnzbd.WIN32:
            # Multipar output
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
                    call("Verifying", "Checking"),
                    call("Verifying", "01/03"),
                    call("Repairing", " 0%"),
                    call("Repairing", "100%"),
                    call("Verifying repair", "01/03"),
                    call("Verifying repair", "02/03"),
                    call("Verifying repair", "03/03"),
                ]
            )
        else:
            # par2cmdline output
            # Verify in chunks, as it outputs every single % during repair
            nzo.set_action_line.assert_has_calls(
                [
                    call("Repair", "Quick Checking"),
                    call("Repair", "Starting Repair"),
                    call("Verifying", "01/06"),
                    call("Verifying", "02/06"),
                    call("Verifying", "03/06"),
                    call("Verifying", "04/06"),
                    call("Verifying", "05/06"),
                    call("Checking extra files", "06"),
                    call("Checking extra files", "07"),
                ]
            )
            # Check at least for 0% and 100%
            nzo.set_action_line.assert_has_calls(
                [
                    call("Repairing", " 0%"),
                    call("Repairing", "100%"),
                ],
                any_order=True,
            )
            nzo.set_action_line.assert_has_calls(
                [
                    call("Verifying repair", "01/03"),
                    call("Verifying repair", "02/03"),
                    call("Verifying repair", "03/03"),
                ]
            )
