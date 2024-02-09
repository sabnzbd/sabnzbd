#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
tests.test_utils.test_check_dir - Testing SABnzbd checkdir util
"""

from sabnzbd.cfg import selftest_host
from sabnzbd.getipaddress import *
from sabnzbd.misc import is_ipv4_addr, is_ipv6_addr


class TestGetIpAddress:
    def test_addresslookup4(self):
        address = addresslookup4(selftest_host())
        assert address
        for item in address:
            assert isinstance(item[0], type(socket.AF_INET))

    def test_public_ipv4(self):
        if publicipv4 := public_ipv4():
            assert is_ipv4_addr(publicipv4)

    def test_local_ipv4(self):
        if localipv4 := local_ipv4():
            assert is_ipv4_addr(localipv4)

    def test_public_ipv6(self):
        if test_ipv6 := public_ipv6():
            # Not all systems have IPv6
            assert is_ipv6_addr(test_ipv6)
