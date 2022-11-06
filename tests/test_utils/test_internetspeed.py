#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_utils.test_internetspeed - Testing SABnzbd internetspeed
"""
import os
import pytest

from sabnzbd.utils.internetspeed import internetspeed, measure_speed_from_url, SIZE_URL_LIST


@pytest.mark.usefixtures("clean_cache_dir")
class TestInternetSpeed:
    """This class contains tests to measure internet speed
    with an active and inactive connection
    """

    def test_measurespeed_invalid_url(self):
        speed = measure_speed_from_url("www.fake-url-9999999.test")

        assert not speed

    def test_measurespeed_valid_url(self):
        speed = measure_speed_from_url(SIZE_URL_LIST[0][1])

        assert isinstance(speed, float)
        assert speed > 0

    def test_internet_speed(self):
        curr_speed_mbps = internetspeed()

        assert isinstance(curr_speed_mbps, float)
        assert curr_speed_mbps > 0

    def test_internet_speed_on_windows_with_curl(self):
        # on Windows 10 and 11, curl is always there
        if os.name == "ntNoNoNo":
            speed = internetspeed_with_curl()
            assert speed > 0.0
