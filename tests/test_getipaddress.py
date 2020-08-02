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
tests.test_utils.test_check_dir - Testing SABnzbd checkdir util
"""

from sabnzbd.cfg import selftest_host
from sabnzbd.getipaddress import *
from sabnzbd.misc import probablyipv4, probablyipv6


class TestGetIpAddress:
    def test_addresslookup4(self):
        address = addresslookup4(selftest_host())
        assert address
        for item in address:
            assert isinstance(item[0], type(socket.AF_INET))

    def test_publicipv4(self):
        public_ipv4 = publicipv4()
        assert probablyipv4(public_ipv4)

    def test_localipv4(self):
        local_ipv4 = localipv4()
        assert probablyipv4(local_ipv4)

    def test_ipv6(self):
        test_ipv6 = ipv6()
        # Not all systems have IPv6
        if test_ipv6:
            assert probablyipv6(test_ipv6)
