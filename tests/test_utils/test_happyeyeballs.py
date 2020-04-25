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
tests.test_utils.test_happyeyeballs - Testing SABnzbd happyeyeballs
"""

from sabnzbd.utils.happyeyeballs import happyeyeballs


class TestHappyEyeballs:
    """ Tests of happyeyeballs() against various websites/servers
        happyeyeballs() returns the quickest IP address (IPv4, or IPv6 if available end-to-end),
        or None (if not resolvable, or not reachable)
    """

    def test_google_http(self):
        ip = happyeyeballs("www.google.com")
        assert "." in ip or ":" in ip

    def test_google_https(self):
        ip = happyeyeballs("www.google.com", port=443, ssl=True)
        assert "." in ip or ":" in ip

    def test_not_resolvable(self):
        ip = happyeyeballs("not.resolvable.invalid")
        assert ip is None

    def test_ipv6_only(self):
        ip = happyeyeballs("ipv6.google.com")
        assert ip is None or ":" in ip

    def test_google_unreachable_port(self):
        ip = happyeyeballs("www.google.com", port=33333)
        assert ip is None

    def test_newszilla_nttp(self):
        ip = happyeyeballs("newszilla.xs4all.nl", port=119)
        assert "." in ip or ":" in ip
