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
tests.test_bitmap - Tests of Bitmap methods
"""

from sabnzbd.bitmap import Bitmap


class TestBitmap:
    def test_bitmap(self):
        bm = Bitmap(150)
        bm[7] = True
        bm[100] = True
        assert len(bm.to_bytes()) == 19
        assert bm[7] is True
        assert bm[100] is True
        assert bm.count() == 2
        assert bm.size == 150
