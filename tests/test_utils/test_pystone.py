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
tests.test_utils.test_pystone - Testing SABnzbd pystone
"""

from sabnzbd.utils.pystone import pystones


class TestPystone:
    def test_pystone(self):
        """ Tests for performance with various loop sizes """
        loops = [10, 1000, 50000, 100000]
        for loop in loops:
            benchtime, stones = pystones(loop)
            assert benchtime > 0
            assert stones > 0
