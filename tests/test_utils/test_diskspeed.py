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
tests.test_utils.test_diskspeed - Testing SABnzbd diskspeed
"""

from sabnzbd.utils.diskspeed import diskspeedmeasure
from tests.testhelper import *


class TestDiskSpeed:
    def test_disk_speed(self):
        speed = diskspeedmeasure(SAB_CACHE_DIR)
        assert speed
        assert isinstance(speed, float)

        # Make sure the test-file was cleaned up after the test
        assert not os.path.exists(os.path.join(SAB_CACHE_DIR, "outputTESTING.txt"))
