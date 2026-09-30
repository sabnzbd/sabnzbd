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
tests.test_utils.test_check_dir - Testing SABnzbd checkdir util
"""

import socket
import urllib.parse
import urllib.request

import pytest
from werkzeug import Request, Response

import sabnzbd.cfg as cfg
import sabnzbd.getipaddress as getipaddress
from sabnzbd.get_addrinfo import AddrInfo
from sabnzbd.getipaddress import addresslookup4, dnslookup, public_ipv4, local_ipv4, public_ipv6
from sabnzbd.misc import is_ipv4_addr

SELFTEST_HOST = "localhost"

# What the local server reports as the public IP addresses (documentation prefixes)
LOCAL_PUBLIC_IPV4 = "192.0.2.1"
LOCAL_PUBLIC_IPV6 = "2001:db8::1"


def _selftest_handler(request: Request) -> Response:
    """Answer like the selftest host: the public IP of the client, only when addressed by the selftest hostname"""
    if request.headers.get("Host") != SELFTEST_HOST:
        return Response(status=404)
    if request.query_string == b"ipv4test":
        return Response(LOCAL_PUBLIC_IPV4)
    if request.query_string == b"ipv6test":
        return Response(LOCAL_PUBLIC_IPV6)
    return Response(status=404)


@pytest.fixture
def selftest_server(httpserver, monkeypatch):
    """Local webserver taking the place of the selftest host, so the tests never touch the real one"""
    httpserver.expect_request("/").respond_with_handler(_selftest_handler)
    monkeypatch.setattr(cfg.selftest_host, "get", lambda: SELFTEST_HOST)

    def local_addrinfo(host, port, timeout, family):
        # Report an address of the requested family, the request is redirected to the local server below
        ip = "::1" if family == socket.AF_INET6 else "127.0.0.1"
        return AddrInfo(family, socket.SOCK_STREAM, 0, host, (ip, httpserver.port))

    real_urlopen = urllib.request.urlopen

    def local_urlopen(req, *args, **kwargs):
        # Send the request to the local server, but keep the path, query and headers
        req.full_url = urllib.parse.urlunparse(
            urllib.parse.urlparse(req.full_url)._replace(netloc=f"{httpserver.host}:{httpserver.port}")
        )
        return real_urlopen(req, *args, **kwargs)

    monkeypatch.setattr(getipaddress, "get_fastest_addrinfo", local_addrinfo)
    monkeypatch.setattr(urllib.request, "urlopen", local_urlopen)
    return httpserver


class TestGetIpAddress:
    def test_addresslookup4(self):
        address = addresslookup4(SELFTEST_HOST)
        assert address
        for item in address:
            assert isinstance(item[0], type(socket.AF_INET))

    def test_dnslookup(self, selftest_server):
        assert dnslookup()

    def test_public_ipv4(self, selftest_server):
        assert public_ipv4() == LOCAL_PUBLIC_IPV4

    def test_local_ipv4(self):
        if localipv4 := local_ipv4():
            assert is_ipv4_addr(localipv4)

    def test_public_ipv6(self, selftest_server):
        # Not all systems have IPv6
        if test_ipv6 := public_ipv6():
            assert test_ipv6 == LOCAL_PUBLIC_IPV6
