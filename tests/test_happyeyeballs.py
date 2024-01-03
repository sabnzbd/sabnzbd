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
tests.test_happyeyeballs - Testing SABnzbd happyeyeballs
"""
import os
import sys
import socket

import pytest
from flaky import flaky

from sabnzbd.happyeyeballs import happyeyeballs


@flaky
class TestHappyEyeballs:
    """Tests of happyeyeballs() against various websites/servers
    happyeyeballs() returns the quickest IP address (IPv4, or IPv6 if available end-to-end),
    or None (if not resolvable, or not reachable)
    """

    def test_google_http(self):
        addrinfo = happyeyeballs("www.google.com", port=80)
        assert "." in addrinfo.ipaddress or ":" in addrinfo.ipaddress
        assert "google" in addrinfo.canonname

    def test_google_https(self):
        addrinfo = happyeyeballs("www.google.com", port=443)
        assert "." in addrinfo.ipaddress or ":" in addrinfo.ipaddress
        assert "google" in addrinfo.canonname

    def test_google_http_want_ipv4(self):
        addrinfo = happyeyeballs("www.google.com", port=80, family=socket.AF_INET)
        assert "." in addrinfo.ipaddress and not ":" in addrinfo.ipaddress
        assert "google" in addrinfo.canonname

    def test_google_http_want_ipv6(self):
        # TODO: timeout needed for IPv4-only CI environment?
        addrinfo = happyeyeballs("www.google.com", port=80, timeout=2, family=socket.AF_INET6)
        if addrinfo:
            assert not "." in addrinfo.ipaddress and ":" in addrinfo.ipaddress
            assert "google" in addrinfo.canonname

    def test_not_resolvable(self):
        assert happyeyeballs("not.resolvable.invalid", port=80) is None

    def test_ipv6_only(self):
        if addrinfo := happyeyeballs("ipv6.google.com", port=443, timeout=2):
            assert ":" in addrinfo.ipaddress
            assert "google" in addrinfo.canonname

    def test_google_unreachable_port(self):
        assert happyeyeballs("www.google.com", port=33333, timeout=1) is None

    @pytest.mark.xfail(reason="CI sometimes blocks this")
    def test_nntp(self):
        ip = happyeyeballs("news.newshosting.com", port=119).ipaddress
        assert "." in ip or ":" in ip
