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
tests.test_utils.test_probablyip - Testing SABnzbd's probablyipX() functions
"""

from sabnzbd.misc import *


class TestProbablyIP:
    def test_probablyipv4(self):
        # Positive testing
        assert probablyipv4("1.2.3.4")
        assert probablyipv4("255.255.255.255")
        assert probablyipv4("0.0.0.0")
        # Negative testing
        assert not probablyipv4("400.500.600.700")
        assert not probablyipv4("blabla")
        assert not probablyipv4("2001::1")

    def test_probablyipv6(self):
        # Positive testing
        assert probablyipv6("2001::1")
        assert probablyipv6("[2001::1]")
        assert probablyipv6("fdd6:5a2d:3f20:0:14b0:d8f4:ccb9:fab6")
        # Negative testing
        assert not probablyipv6("blabla")
        assert not probablyipv6("1.2.3.4")
        assert not probablyipv6("[1.2.3.4]")
        assert not probablyipv6("2001:1")
        assert not probablyipv6("2001::[2001::1]")
