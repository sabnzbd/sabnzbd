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
tests.test_internetspeed - Testing SABnzbd internetspeed
"""
import pytest

from sabnzbd.internetspeed import internetspeed


@pytest.mark.usefixtures("clean_cache_dir")
class TestInternetSpeed:
    def test_internet_speed(self):
        curr_speed_mbps = internetspeed()

        assert isinstance(curr_speed_mbps, float)
        assert curr_speed_mbps > 0
