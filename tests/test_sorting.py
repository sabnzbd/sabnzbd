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
tests.test_sorting - Testing functions in sorting.py
"""

from sabnzbd import sorting
from tests.testhelper import *


class TestSorting:
    @pytest.mark.parametrize(
        "job_name, result",
        [
            ("Ubuntu.optimized.for.1080p.Screens-Canonical", "1080p"),
            ("Debian_for_240i_Scientific_Calculators-FTPMasters", "240i"),
            ("OpenBSD Streaming Edition 4320P", "4320p"),  # Lower-case result
            ("Surely.1080p.is.better.than.720p", "720p"),  # Last hit wins
            ("2160p.Campaign.Video", "2160p"),  # Resolution at the start
            ("Some.Linux.Iso.1234p", ""),  # Non-standard resolution
            ("No.Resolution.Anywhere", ""),
            ("not.keeping.its1080p.distance", ""),  # No separation
            ("not_keeping_1440idistance_either", ""),
            ("240 is a semiperfect and highly composite number", ""),  # Number only
            (480, ""),
            (None, ""),
            ("", ""),
        ],
    )
    def test_get_resolution(self, job_name, result):
        assert sorting.get_resolution(job_name) == result
