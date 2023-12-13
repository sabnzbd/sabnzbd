#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team (sabnzbd.org)
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
tests.test_functional_sorting - Test downloads with season sorting and sequential files
"""
import os
from tests.testhelper import *
from flaky import flaky
import sabnzbd.config as config


# Use an ini file with a valid, old style series and movie sorting configuration
# that also serves to verify conversion to the new sorter settings is performed
INI_FILE = "sabnzbd.sorting.ini"


@flaky
@pytest.mark.usefixtures("run_sabnzbd")
class TestDownloadSorting(DownloadFlowBasics):
    def test_sorter_settings_conversion(self):
        """Read the ini file after the sabnzbd test instance completed startup
        and verify all defined sorters were converted to the new format"""
        return_status, return_msg = config._read_config(os.path.join(SAB_CACHE_DIR, DEF_INI_FILE), try_backup=False)
        assert return_status
        assert not return_msg
        assert config.CFG_OBJ["sorters"]
        assert len(config.CFG_OBJ["sorters"]) == 2  # The ini file only has Series and Movie sorting

    @pytest.mark.parametrize(
        "test_data_dir, result",
        [
            (
                "sea_sort_s01_4k_uhd-SABnzbd",
                ["Sea.Sort.S01E0" + str(n) + ".data" for n in (1, 2, 3, 5)],
            ),  # Data files with season and episode markers, one episode number intentionally missing
            (
                "sea_sort_s02_4k_uhd-SABnzbd",
                ["Sea.Sort.S02E0" + str(n) + ".data" for n in (4, 6, 7, 9)],
            ),  # Data files with episode markers only, one episode number intentionally missing
        ],
    )
    def test_download_season_sorting(self, test_data_dir, result):
        """Test season pack sorting"""
        self.download_nzb(os.path.join("sorting", test_data_dir), result, True)

    @pytest.mark.parametrize(
        "test_data_dir, result",
        [
            (
                "Long_live_CDs_2023_576i_mono-SABnzbd",
                ["Movie_DVD_" + str(n) + ".disc" for n in (1, 2, 3)],
            ),  # Data files with "CD n" sequence markers
            (
                "Its_all_about_parts_2023_576i_mono-SABnzbd",
                ["Movie_DVD_" + str(n) + ".disc" for n in (6, 7, 8)],
            ),  # Data file with "Part n" sequence markers
        ],
    )
    def test_download_sequential(self, test_data_dir, result):
        """Test sequential file handling"""
        self.download_nzb(os.path.join("sorting", test_data_dir), result, True)

    @pytest.mark.parametrize(
        "test_data_dir, result",
        [
            (
                "SINGLE_sort_s23e06_480i-SABnzbd",
                ["Single.Sort.S23E06.mov"],
            ),  # Single episode, no other files
            (
                "SINGLE_sort_s23e06_480i-SABnzbd",
                ["Single.Sort.S23E06.1.mov"],
            ),  # Repeat to verify a unique filename is applied
            pytest.param(
                "single-ep_sort_s06e66_4k_uhd-SABnzbd",
                ["Single-Ep.Sort.S06E66." + ext for ext in ("avi", "srt")],
                marks=pytest.mark.xfail(
                    sabnzbd.MACOS or sabnzbd.WIN32,
                    reason="Unreliable on macOS and Windows",
                ),
            ),  # Single episode with associated smaller file
            pytest.param(
                "single-ep_sort_s06e66_4k_uhd-SABnzbd",
                ["Single-Ep.Sort.S06E66.1." + ext for ext in ("avi", "srt")],
                marks=pytest.mark.xfail(
                    sabnzbd.MACOS or sabnzbd.WIN32,
                    reason="Unreliable on macOS and Windows",
                ),
            ),  # Repeat to verify unique filenames are applied
        ],
    )
    def test_download_sorting_single(self, test_data_dir, result):
        """Test single episode file handling"""
        self.download_nzb(os.path.join("sorting", test_data_dir), result, True)
