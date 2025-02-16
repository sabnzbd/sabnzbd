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
tests.test_utils.test_diskspeed - Testing SABnzbd diskspeed
"""

import os
import pytest
import tempfile
from sabnzbd.utils.diskspeed import diskspeedmeasure
from tests.testhelper import SAB_CACHE_DIR


@pytest.mark.usefixtures("clean_cache_dir")
class TestDiskSpeed:
    """test sabnzbd.utils.diskspeed"""

    def test_disk_speed(self):
        """Test the normal use case: writable directory"""
        speed = diskspeedmeasure(SAB_CACHE_DIR)
        assert speed > 0.0
        assert isinstance(speed, float)

        # Make sure the test-file was cleaned up after the test
        assert not os.path.exists(os.path.join(SAB_CACHE_DIR, "outputTESTING.txt"))

    def test_non_existing_dir(self):
        """testing a non-existing dir should result in 0"""
        speed = diskspeedmeasure("such_a_dir_does_not_exist")
        assert speed == 0

    def test_non_writable_dir(self):
        """testing a non-writable dir should result in 0.
        Only useful on Linux, and only if not-writable
        """
        non_writable_dir = "/usr"
        if os.path.isdir(non_writable_dir) and not os.access(non_writable_dir, os.W_OK):
            speed = diskspeedmeasure(non_writable_dir)
            assert speed == 0

    def test_file_not_dir_specified(self):
        """testing a file should result in 0"""
        with tempfile.NamedTemporaryFile() as temp_file:
            speed = diskspeedmeasure(temp_file.name)
        assert speed == 0
        assert not os.path.exists(temp_file.name)
