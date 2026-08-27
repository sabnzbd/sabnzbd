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
tests.test_interface - Testing functions in interface.py
"""

import asyncio
import inspect
import logging
import logging.config
from typing import Optional
import pytest
from unittest.mock import Mock, patch
from starlette.requests import Request
from starlette.datastructures import Headers, Address, QueryParams
import uvicorn
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from uvicorn.lifespan import on as lifespan_on
from uvicorn.protocols.http import h11_impl, httptools_impl
from uvicorn.server import ServerState

import sabnzbd
import sabnzbd.cfg as cfg
import sabnzbd.security as security
from sabnzbd import interface
from tests.test_security import api_request, config_save_middleware, mock_request, page_post, store_session
from sabnzbd.misc import is_local_addr, is_loopback_addr, xff_trusted_networks


def resolve_client(remote_ip: str, xff_header: str | None = None, remote_port: int = 12345) -> Address:
    """Pass a connection through uvicorn's ProxyHeadersMiddleware, configured
    exactly like SABnzbd.py does, and return the resulting effective client."""
    captured = {}

    async def asgi_app(scope, receive, send):
        captured["client"] = scope.get("client")

    middleware = ProxyHeadersMiddleware(asgi_app, trusted_hosts=xff_trusted_networks())
    headers = []
    if xff_header:
        headers.append((b"x-forwarded-for", xff_header.encode("latin1")))
    scope = {"type": "http", "client": (remote_ip, remote_port), "headers": headers}
    asyncio.run(middleware(scope, None, None))
    return Address(*captured["client"])


class TestInterfaceFunctions:
    @pytest.mark.parametrize(
        "remote_ip, local_ranges, xff_header, result_with_xff",
        [
            ("10.11.12.13", None, None, True),
            ("10.11.12.13", None, "127.0.0.1", True),
            ("10.11.12.13", None, "127.1.2.3", True),
            ("10.11.12.13", None, "127.0.0.1:8080", True),  # Port stripped from XFF, leaving loopback
            ("10.11.12.13", None, "::1", True),
            ("10.11.12.13", None, "[::1]", True),
            ("10.11.12.13", None, "[::1]:8080", True),  # Port stripped from XFF, leaving loopback
            ("10.11.12.13", None, "localhost", False),  # Hostname in XFF
            ("10.11.12.13", None, "example.org", False),  # Hostname in XFF
            ("10.11.12.13", None, "192.168.1.1", True),
            ("10.11.12.13", None, "10.11.12.99", True),
            ("10.11.12.13", None, "8.7.6.5", False),  # XFF IP isn't local
            ("10.11.12.13", None, "192.168.1.1, 10.11.12.13", True),
            ("10.11.12.13", None, "192.168.1.1, 10.11.12.13, 9.8.7.6", False),  # Last XFF IP isn't local
            ("10.11.12.13", None, "192.168.1.1, 10.11.12.13, ::1", True),
            ("10.11.12.13", None, "192.168.1.1, 10.11.12.13, sabrules.example.org", False),  # Hostname in XFF
            ("10.11.12.13", "192.168.1.0/24", None, False),  # Remote IP not part of local ranges
            ("10.11.12.13", "192.168.1.0/24", "192.168.1.23", False),
            ("10.11.12.13", "192.168.1.0/24", "192.168.1.23, 10.11.12.1", False),
            ("10.11.12.13", "192.168.1.0/24, 10.0.0.0/8", "192.168.1.23", True),
            ("10.11.12.13", "192.168.2.0/24, 10.0.0.0/8", "192.168.1.23", False),
            ("10.11.12.13", "192.168.1.0/24, 10.0.0.0/24", "192.168.1.23", False),
            ("10.11.12.13", "10.11.12.0/24", "192.168.1.23", False),
            ("10.11.12.13", "2001:ffff::/64", None, False),
            ("10.11.12.13", "2001:ffff::/64, 192.168.1.0/24", None, False),
            ("13.12.11.10", None, None, False),  # Public remote IP doesn't have access, XFF ignored altogether
            ("13.12.11.10", None, "127.0.0.1", False),
            ("13.12.11.10", None, "127.1.2.3", False),
            ("13.12.11.10", None, "::1", False),
            ("13.12.11.10", None, "[::1]", False),
            ("13.12.11.10", None, "localhost", False),
            ("13.12.11.10", None, "192.168.1.1", False),
            ("13.12.11.10", None, "192.168.1.1, 13.12.11.10", False),
            ("13.12.11.10", None, "192.168.1.1, 13.12.11.10, ::1", False),
            ("13.12.11.10", None, "2001::/16", False),
            ("13.12.11.10", None, "2001::/16, 13.12.11.10", False),
            ("13.12.11.10", None, "2001::/16, 13.0.0.0/9", False),
            ("13.12.11.10", "13.12.11.10", None, True),  # Local ranges include a public IP
            ("13.12.11.10", "13.12.11.10, 192.168.255.0/24", None, True),
            ("13.12.11.10", "13.12.11.10", "192.168.1.1", False),  # XFF not in local ranges
            ("13.12.11.10", "13.12.11.10, 192.168.255.0/24", "192.168.1.1", False),
            ("13.12.11.10", "13.12.11.10", "192.168.1.1, 9.8.7.6", False),
            ("13.12.11.10", "13.12.11.10, 192.168.255.0/24", "192.168.1.1, 9.8.7.6", False),
            ("13.12.11.10", "13.0.0.0/12", None, True),
            ("13.12.11.10", "13.0.0.0/12, 192.168.255.0/24", None, True),
            ("13.12.11.10", "13.0.0.0/12", "192.168.1.1", False),  # XFF not in local ranges
            ("13.12.11.10", "13.0.0.0/12, 192.168.255.0/24", "192.168.1.1", False),
            ("13.12.11.10", "13.0.0.0/12", "192.168.1.1, 9.8.7.6", False),
            ("13.12.11.10", "13.0.0.0/12, 192.168.255.0/24", "192.168.1.1, 9.8.7.6", False),
            ("127.6.6.6", None, None, True),
            ("127.6.6.6", None, "127.0.0.1", True),
            ("127.6.6.6", None, "127.1.2.3", True),
            ("127.6.6.6", None, "127.0.0.1:8080", True),  # Port stripped from XFF, leaving loopback
            ("127.6.6.6", None, "::1", True),
            ("127.6.6.6", None, "[::1]", True),
            ("127.6.6.6", None, "[::1]:8080", True),  # Port stripped from XFF, leaving loopback
            ("127.6.6.6", None, "localhost", False),  # Hostname in XFF
            ("127.6.6.6", None, "example.org", False),  # Hostname in XFF
            ("127.6.6.6", None, "192.168.1.1", True),
            ("127.6.6.6", None, "10.11.12.99", True),
            ("127.6.6.6", None, "8.7.6.5", False),  # XFF IP isn't local
            ("127.6.6.6", None, "192.168.1.1, 127.6.6.6", True),
            ("127.6.6.6", None, "192.168.1.1, 127.6.6.6, 9.8.7.6", False),  # Last XFF IP isn't local
            ("127.6.6.6", None, "192.168.1.1, 127.6.6.6, ::1", True),
            ("127.6.6.6", None, "192.168.1.1, 127.6.6.6, sabrules.example.org", False),  # Hostname in XFF
            ("127.6.6.6", "192.168.1.0/24", None, True),  # Remote IP is loopback, local ranges be damned
            ("127.6.6.6", "192.168.1.0/24", "192.168.1.23", True),
            ("127.6.6.6", "192.168.1.0/24", "192.168.1.23, 127.0.0.1", True),
            ("127.6.6.6", "192.168.1.0/24, 127.0.0.0/8", "192.168.1.23", True),
            ("127.6.6.6", "192.168.2.0/24, 127.0.0.0/8", "192.168.1.23", False),  # Access denied by XFF
            ("127.6.6.6", "192.168.2.0/24, 127.0.0.0/8", "5.6.7.8", False),  # Idem
            ("127.6.6.6", "192.168.1.0/24, 127.0.0.0/8", "192.168.1.23, 5.6.7.8", False),  # Idem
            ("127.6.6.6", "192.168.1.0/24, 10.0.0.0/24", "::1", True),
            ("127.6.6.6", "127.6.6.0/24", "192.168.1.23", False),  # Access denied by XFF
            ("127.6.6.6", "2001:ffff::/32", None, True),
            ("127.6.6.6", "2001:ffff::/32, 192.168.1.0/24", None, True),
            ("127.6.6.6", "2001:ffff::/32", "2001:ffff:a:b:c:d:e:f", True),
            ("127.6.6.6", "2001:ffff::/32, 192.168.1.0/24", "2001:ffff:a:b:c:d:e:f, 192.168.1.1", True),
            ("127.6.6.6", "2001:ffff::/32", "666:ffff:a:b:c:d:e:f", False),  # Access denied by XFF
            ("127.6.6.6", "2001:ffff::/32, 192.168.1.0/24", "666:ffff:a:b:c:d:e:f, 192.168.1.1", False),  # Idem
            ("DEAD:BEEF:2023:007::1", None, None, False),  # Back to ignoring XFF altogether
            ("DEAD:BEEF:2023:007::1", None, "127.0.0.1", False),  # XFF is loopback
            ("DEAD:BEEF:2023:007::1", None, "127.1.2.3", False),
            ("DEAD:BEEF:2023:007::1", None, "::1", False),
            ("DEAD:BEEF:2023:007::1", None, "[::1]", False),
            ("DEAD:BEEF:2023:007::1", None, "localhost", False),  # Hostname in XFF
            ("DEAD:BEEF:2023:007::1", None, "192.168.1.1", False),
            ("DEAD:BEEF:2023:007::1", None, "192.168.1.1, DEAD:BEEF:2023:0007::1", False),
            ("DEAD:BEEF:2023:007::1", None, "192.168.1.1, DEAD:BEEF:2023:0007::1, ::1", False),
            ("DEAD:BEEF:2023:007::1", None, "2001::/16", False),
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", None, True),  # Local ranges include a public IPv6
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "127.0.0.1", True),  # XFF is loopback
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "127.1.2.3", True),
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "::1", True),
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "[::1]", True),
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "localhost", False),  # Hostname in XFF
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "192.168.1.1", False),
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "192.168.1.1, DEAD:BEEF:2023:0007::1", False),
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "192.168.1.1, DEAD:BEEF:2023:0007::1, ::1", False),
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "DEAD::/16", False),  # Netmask in XFF
            ("DEAD:BEEF:2023:007::1", "dead:beef::/32", "DEAD:BEEF:2023:7::42", True),  # XFF in local ranges
        ],
    )
    @pytest.mark.parametrize("access_type", [1, 2, 3, 4, 5, 6])
    @pytest.mark.parametrize("inet_exposure", [0, 1, 2, 3, 4, 5])
    @pytest.mark.parametrize("verify_xff_header", [False, True])
    @pytest.mark.config(
        lambda params: {
            "local_ranges": params["local_ranges"],
            "inet_exposure": params["inet_exposure"],
            "verify_xff_header": params["verify_xff_header"],
        }
    )
    def test_check_access(
        self,
        access_type,
        inet_exposure,
        local_ranges,
        remote_ip,
        xff_header,
        verify_xff_header,
        result_with_xff,
        monkeypatch,
    ):
        def _func():
            # With verify_xff_header enabled, SABnzbd.py runs uvicorn with
            # proxy_headers=True, so the XFF chain is resolved into the
            # effective client before check_access ever sees the request.
            # With it disabled the header is ignored entirely.
            if verify_xff_header:
                client = resolve_client(remote_ip=remote_ip, xff_header=xff_header)
                result = result_with_xff
            else:
                client = Address(remote_ip, 12345)
                # Without XFF, only the remote IP and the local ranges setting matter
                result = is_loopback_addr(remote_ip) or is_local_addr(remote_ip)

            request = mock_request(remote_ip=client.host, remote_port=client.port)

            if access_type <= inet_exposure:
                assert security.check_access(request, access_type) is True
            else:
                assert security.check_access(request, access_type) is result

        _func()

    @pytest.mark.config({"api_key": "the_real_api_key", "nzb_key": "the_real_nzb_key", "api_warnings": True})
    @pytest.mark.parametrize(
        "params, expected",
        [
            ({"mode": "version"}, None),
            ({"mode": "auth"}, None),
            # The NZB-key is valid for nzb-level calls only
            ({"mode": "addfile", "apikey": "the_real_nzb_key"}, None),
            ({"mode": "queue", "apikey": "the_real_nzb_key"}, interface._MSG_APIKEY_INCORRECT),
            ({"mode": "queue", "apikey": "the_real_api_key"}, None),
            ({"mode": "queue"}, interface._MSG_APIKEY_REQUIRED),
            ({"mode": "queue", "apikey": "wrong"}, interface._MSG_APIKEY_INCORRECT),
        ],
    )
    def test_apikey_on_the_api_route(self, params, expected):
        request = mock_request(params=params)
        response = interface.check_apikey(request)
        assert (response.body.decode() if response else None) == expected

    @pytest.mark.parametrize(
        "local_ranges, xff_ips, expected_result",
        [
            ([], ["4.3.2.1"], "4.3.2.1"),  # Standard situation, single non-local XFF IP
            ([], ["42:1b5::beef"], "42:1b5::beef"),
            ([], ["10.10.10.10"], "10.10.10.10"),  # Only local XFF IPs, first entry wins
            ([], ["::1"], "::1"),
            ([], ["127.0.0.1"], "127.0.0.1"),
            ([], ["10.10.10.10", "192.168.0.1"], "10.10.10.10"),  # Only local XFF IPs, first entry wins
            ([], ["10.10.10.10", "192.168.0.1", "192.168.1.2"], "10.10.10.10"),  # Only local XFF IPs, first entry wins
            ([], ["4.3.2.1", "10.10.10.10"], "4.3.2.1"),  # First non-local entry wins
            ([], ["4.3.2.1", "192.168.0.1", "10.10.10.10"], "4.3.2.1"),
            ([], ["127.0.0.1", "4.3.2.1", "192.168.0.1", "10.10.10.10"], "4.3.2.1"),
            ([], ["4.3.2.1", "192.168.0.1", "10.10.10.10", "127.0.0.1"], "4.3.2.1"),
            ([], ["666::1", "4.3.2.1", "10.10.10.10"], "4.3.2.1"),
            ([], ["4.3.2.1", "666::1", "192.168.0.1", "10.10.10.10"], "666::1"),
            ([], ["127.0.0.1", "4.3.2.1", "666::1", "10.10.10.10"], "666::1"),
            ([], ["4.3.2.1", "192.168.0.1", "10.10.10.10", "127.0.0.1", "666::1"], "666::1"),
            ([], ["10.10.10.10", "4.3.2.1"], "4.3.2.1"),
            ([], ["192.168.0.1", "4.3.2.1", "10.10.10.10"], "4.3.2.1"),
            ([], ["127.0.0.1", "192.168.0.1", "4.3.2.1", "10.10.10.10"], "4.3.2.1"),
            ([], ["192.168.0.1", "4.3.2.1", "10.10.10.10", "127.0.0.1"], "4.3.2.1"),
            (["4.3.2.0/24"], ["4.3.2.1"], "4.3.2.1"),  # Only local IPs due to local_ranges, first entry wins
            (["666::/48"], ["666::1"], "666::1"),
            (["192.168.0.0/16", "4.3.2.0/24"], ["4.3.2.1"], "4.3.2.1"),
            (["666::/48", "192.168.0.0/16", "4.3.2.0/24"], ["4.3.2.1"], "4.3.2.1"),
            (["666::/48", "192.168.0.0/16", "4.3.2.0/24"], ["666::1"], "666::1"),
            (["192.168.0.0/16", "4.3.2.0/24"], ["10.10.10.10"], "10.10.10.10"),  # 10.x wins, outside local_ranges
            (["192.168.0.0/16", "4.3.2.0/24"], ["4.3.2.1", "10.10.10.10"], "10.10.10.10"),
            (["192.168.0.0/16", "4.3.2.0/24"], ["10.10.10.10", "4.3.2.1"], "10.10.10.10"),
            (["666::/48", "192.168.0.0/16", "4.3.2.0/24"], ["10.10.10.10"], "10.10.10.10"),
            (["666::/48", "192.168.0.0/16", "4.3.2.0/24"], ["4.3.2.1", "10.10.10.10"], "10.10.10.10"),
            (["666::/48", "192.168.0.0/16", "4.3.2.0/24"], ["10.10.10.10", "4.3.2.1"], "10.10.10.10"),
            (["8.8.8.8", "4.3.2.1"], ["4.3.2.1", "192.168.0.1", "10.10.10.10"], "10.10.10.10"),
            (["8.8.8.8", "4.3.2.1"], ["192.168.0.1", "4.3.2.1", "10.10.10.10"], "10.10.10.10"),
            (["8.8.8.8", "4.3.2.1"], ["192.168.0.1", "10.10.10.10", "4.3.2.1"], "10.10.10.10"),
            (["8.8.8.8"], ["192.168.0.1", "10.10.10.10", "4.3.2.1"], "4.3.2.1"),  # All XFF IPs non-local, last wins
            (["8.8.8.8"], ["4.3.2.1", "10.10.10.10", "192.168.0.1"], "192.168.0.1"),
            (["8.8.8.8"], ["4.3.2.1", "192.168.0.1", "10.10.10.10"], "10.10.10.10"),
            (["8.8.8.8"], ["127.0.0.1", "4.3.2.1", "10.10.10.10", "192.168.0.1"], "192.168.0.1"),
            (["666::/48"], ["192.168.0.1", "10.10.10.10", "4.3.2.1"], "4.3.2.1"),
            (["666::/48"], ["4.3.2.1", "10.10.10.10", "192.168.0.1"], "192.168.0.1"),
            (["666::/48"], ["4.3.2.1", "192.168.0.1", "10.10.10.10"], "10.10.10.10"),
            (["666::/48"], ["127.0.0.1", "4.3.2.1", "10.10.10.10", "192.168.0.1"], "192.168.0.1"),
            (["8.8.8.8"], ["4.3.2.1", "192.168.0.1", "10.10.10.10", "127.0.0.1"], "10.10.10.10"),  # Loopback as last
            (["666::/48"], ["4.3.2.1", "192.168.0.1", "10.10.10.10", "127.0.0.1"], "10.10.10.10"),
            (["8.8.8.8"], ["4.3.2.1", "192.168.0.1", "10.10.10.10", "::1"], "10.10.10.10"),
            (["666::/48"], ["4.3.2.1", "192.168.0.1", "10.10.10.10", "::1"], "10.10.10.10"),
            ([], ["4.3.2.1:56789"], "4.3.2.1"),  # Port stripped from XFF entry
        ],
    )
    @pytest.mark.config(
        lambda params: {
            "local_ranges": params["local_ranges"],
        }
    )
    def test_effective_client_from_xff(self, local_ranges, xff_ips, expected_result):
        def _func():
            # The effective client IP (used for access
            # checks) is selected by uvicorn's ProxyHeadersMiddleware: the last
            # XFF entry that is not a trusted (local) proxy, or the first entry
            # when the whole chain is trusted. Connect from loopback, which is
            # always a trusted peer.
            assert xff_ips
            client = resolve_client(remote_ip="127.0.0.1", xff_header=", ".join(xff_ips))
            assert client.host == expected_result

        _func()

    @pytest.mark.parametrize("access_type", [1, 2, 3, 4, 5, 6])
    @pytest.mark.parametrize("inet_exposure", [0, 2, 4])
    @pytest.mark.config(lambda params: {"inet_exposure": params["inet_exposure"], "api_warnings": True})
    def test_check_access_without_client(self, access_type, inet_exposure):
        # request.client can be None on unix sockets and with some test clients
        request = mock_request()
        request.client = None

        assert security.check_access(request, access_type, warn_user=True) is (access_type <= inet_exposure)
        # The logging helpers must not raise either
        interface.log_warning_and_ip(request, "txt")

    @pytest.mark.parametrize(
        "local_ranges, expected_networks, unexpected_networks",
        [
            # Without local_ranges: loopback plus all private address space
            (None, ["127.0.0.0/8", "::1", "10.0.0.0/8", "192.168.0.0/16", "::ffff:10.0.0.0/104"], []),
            # With local_ranges: loopback plus the configured ranges only
            (
                "192.168.1.0/24",
                ["127.0.0.0/8", "::1", "192.168.1.0/24", "::ffff:192.168.1.0/120"],
                ["10.0.0.0/8", "172.16.0.0/12"],
            ),
        ],
    )
    @pytest.mark.config(lambda params: {"local_ranges": params["local_ranges"]})
    def test_xff_trusted_networks(self, local_ranges, expected_networks, unexpected_networks):
        def _func():
            networks = xff_trusted_networks()
            for network in expected_networks:
                assert network in networks
            for network in unexpected_networks:
                assert network not in networks

        _func()


async def empty_app(scope, receive, send):
    """Minimal ASGI app, replying to anything that does reach it"""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def is_client_error(record: logging.LogRecord) -> bool:
    """Was this record logged by uvicorn because of client behavior?"""
    return record.getMessage().startswith(interface.UvicornNoiseFilter.CLIENT_ERRORS)


def feed_raw_request(protocol_class, data: bytes):
    """Hand raw bytes to a real uvicorn HTTP protocol, so it logs whatever it
    makes of them, just like it would for an actual connection."""

    async def _run():
        # log_config=None: the logging setup under test is applied by the fixture
        config = uvicorn.Config(app=empty_app, log_config=None)
        config.load()
        protocol = protocol_class(config=config, server_state=ServerState(), app_state={})
        transport = Mock()
        transport.get_extra_info = lambda name, default=None: ("127.0.0.1", 12345) if name == "peername" else default
        protocol.connection_made(transport)
        protocol.data_received(data)

    asyncio.run(_run())


class TestUvicornLogging:
    @pytest.fixture(autouse=True)
    def uvicorn_logging(self):
        """Apply the logging configuration that SABnzbd hands to uvicorn and
        restore the previous state afterwards, so other tests are unaffected."""
        loggers = [logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")]
        saved = [(logger.level, logger.propagate, logger.handlers[:], logger.filters[:]) for logger in loggers]
        logging.config.dictConfig(interface.uvicorn_logging_config())
        yield
        for logger, (level, propagate, handlers, filters) in zip(loggers, saved):
            logger.setLevel(level)
            logger.propagate = propagate
            logger.handlers = handlers
            logger.filters = filters

    @pytest.mark.parametrize("protocol_class", [h11_impl.H11Protocol, httptools_impl.HttpToolsProtocol])
    @pytest.mark.parametrize(
        "raw_request",
        [
            # Not HTTP at all, as sent by port scanners and misdirected clients
            b"\x16\x03\x01\x00\xf4\x01\x00\x00\xf0\x03\x03",
            # Valid HTTP, but asking for an upgrade we do not support
            b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: upgrade\r\nUpgrade: h2c\r\n\r\n",
        ],
    )
    def test_client_errors_are_not_warnings(self, protocol_class, raw_request, caplog):
        # A handler that only wants INFO and up, just like the console and logfile
        # handlers when debug logging is off, must not see the message at all
        caplog.set_level(logging.INFO)
        feed_raw_request(protocol_class, raw_request)
        assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
        assert not [record for record in caplog.records if is_client_error(record)]

    @pytest.mark.parametrize("protocol_class", [h11_impl.H11Protocol, httptools_impl.HttpToolsProtocol])
    def test_client_errors_are_kept_for_debug_logging(self, protocol_class, caplog):
        caplog.set_level(logging.DEBUG)
        feed_raw_request(protocol_class, b"\x16\x03\x01\x00\xf4\x01\x00\x00\xf0\x03\x03")
        assert [
            record
            for record in caplog.records
            if record.levelname == "DEBUG" and record.getMessage() == "Invalid HTTP request received."
        ]

    def test_lifecycle_messages_are_not_logged(self, caplog):
        # Starting and stopping is already logged by SABnzbd itself
        caplog.set_level(logging.INFO)
        logging.getLogger("uvicorn.error").info("Application startup complete.")
        assert not caplog.records

    def test_lifecycle_messages_are_kept_for_debug_logging(self, caplog):
        caplog.set_level(logging.DEBUG)
        logging.getLogger("uvicorn.error").info("Application startup complete.")
        assert [record for record in caplog.records if record.levelname == "DEBUG"]

    def test_failures_reported_by_sabnzbd_are_not_logged_twice(self, caplog):
        # SABnzbd logs its own error, including the reason, when the
        # web-interface fails to start, so this summary adds nothing
        caplog.set_level(logging.INFO)
        logging.getLogger("uvicorn.error").error("Application startup failed. Exiting.")
        assert not caplog.records

    def test_reason_for_a_failed_start_still_propagates(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("uvicorn.error").error("Exception in 'lifespan' protocol")
        assert [record for record in caplog.records if record.levelno == logging.ERROR]

    def test_real_warnings_still_propagate(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("uvicorn.error").warning("Exceeded concurrency limit.")
        logging.getLogger("uvicorn.error").error("Exception in ASGI application")
        assert [record for record in caplog.records if record.levelno == logging.WARNING]
        assert [record for record in caplog.records if record.levelno == logging.ERROR]

    def test_filtered_messages_still_used_by_uvicorn(self):
        """Guard against uvicorn rewording the messages we filter on"""
        uvicorn_source = "".join(inspect.getsource(module) for module in (h11_impl, httptools_impl, lifespan_on))
        for message in interface.UvicornNoiseFilter.CLIENT_ERRORS + interface.UvicornNoiseFilter.REPORTED_FAILURES:
            assert message in uvicorn_source


class TestClientAddressInfo:
    """The client address goes into log lines as host:port, so an IPv6 address has to
    be bracketed: ::ffff:127.0.0.1:55170 gives no clue where the address stops."""

    @pytest.mark.config({"verify_xff_header": False})
    @pytest.mark.parametrize(
        "remote_ip, expected",
        [
            ("127.0.0.1", "127.0.0.1:55170"),
            ("10.11.12.13", "10.11.12.13:55170"),
            ("::1", "[::1]:55170"),
            # Dual-stack listener reporting an IPv4 client
            ("::ffff:127.0.0.1", "[::ffff:127.0.0.1]:55170"),
            ("2001:470:1:332::152", "[2001:470:1:332::152]:55170"),
            # Unknown client, request.client was None
            ("", ":55170"),
        ],
    )
    def test_brackets_ipv6(self, remote_ip, expected):
        request = mock_request(remote_ip=remote_ip, remote_port=55170)
        assert security.client_address_info(request) == expected

    @pytest.mark.config({"verify_xff_header": True})
    def test_includes_forwarded_chain(self):
        request = mock_request(remote_ip="::1", remote_port=55170, headers={"X-Forwarded-For": "8.7.6.5, ::1"})
        assert security.client_address_info(request) == "[::1]:55170 (X-Forwarded-For: 8.7.6.5, ::1)"

    @pytest.mark.config({"verify_xff_header": False})
    def test_omits_forwarded_chain_when_not_verified(self):
        """Without verify_xff_header the header is not trusted, so it is not reported"""
        request = mock_request(remote_ip="::1", remote_port=55170, headers={"X-Forwarded-For": "8.7.6.5"})
        assert security.client_address_info(request) == "[::1]:55170"


class TestUseSecureCookies:
    """The Secure attribute must follow the connection the request actually arrived on,
    including TLS terminated by a trusted reverse proxy in front of SABnzbd."""

    @staticmethod
    def make_request(scheme: str, host: str | None = "sab.example.com", server=("127.0.0.1", 8080)) -> Request:
        headers = [(b"host", host.encode())] if host is not None else []
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "scheme": scheme,
                "headers": headers,
                "client": ("127.0.0.1", 12345),
                "server": server,
            }
        )

    @pytest.mark.config({"enable_https": False})
    @pytest.mark.parametrize(
        "scheme, host, server, expected",
        [
            ("http", "sab.example.com", ("127.0.0.1", 8080), False),
            ("https", "sab.example.com", ("127.0.0.1", 8080), True),
            # No Host header: the scheme must still decide the flag
            ("https", None, ("127.0.0.1", 8080), True),
            # An IPv6 listen address leaves the URL unparseable, the scheme is unaffected
            ("https", None, ("::ffff:127.0.0.1", 8080), True),
            ("https", "1234:5678::1:8080", ("::1", 8080), True),
            # Neither a Host header nor an address: the URL is relative and has no
            # scheme at all, which must not silently drop the Secure attribute
            ("https", None, None, True),
            ("http", None, None, False),
        ],
    )
    def test_follows_request_scheme(self, scheme, host, server, expected):
        assert security.use_secure_cookies(self.make_request(scheme, host, server)) is expected

    @pytest.mark.config({"enable_https": True})
    def test_https_enabled_always_secure(self):
        """Serving https ourselves is enough, whatever the request looks like"""
        assert security.use_secure_cookies(self.make_request("http")) is True

    @pytest.mark.config({"enable_https": False})
    def test_scheme_from_trusted_proxy(self):
        """X-Forwarded-Proto from a trusted proxy is resolved into the scope by
        uvicorn, so a proxy terminating TLS still gets the Secure attribute."""

        captured = {}

        async def asgi_app(scope, receive, send):
            captured["secure"] = security.use_secure_cookies(Request(scope))

        def run(remote_ip: str):
            middleware = ProxyHeadersMiddleware(asgi_app, trusted_hosts=xff_trusted_networks())
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/",
                "query_string": b"",
                "scheme": "http",
                "client": (remote_ip, 12345),
                "server": ("127.0.0.1", 8080),
                "headers": [(b"host", b"sab.example.com"), (b"x-forwarded-proto", b"https")],
            }
            asyncio.run(middleware(scope, None, None))
            return captured["secure"]

        # Trusted proxy: the forwarded scheme is honoured
        assert run("127.0.0.1") is True
        # Untrusted peer: the header must be ignored, so no Secure on a plain connection
        assert run("8.7.6.5") is False


class TestStaleTokenIsNotAWarning:

    def _levels(self, caplog, run) -> set:
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=""):
            run()
        return {record.levelname for record in caplog.records}

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0, "api_warnings": True})
    def test_api_call_with_a_stale_token_is_only_info(self, session_store, caplog):
        request = mock_request(security.anonymous_session_tag(), params={"mode": "queue", "name": ""}, csrf="f0" * 32)
        levels = self._levels(caplog, lambda: interface.check_apikey(request))
        assert "WARNING" not in levels
        assert "INFO" in levels

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0, "api_warnings": True})
    def test_api_call_with_no_token_still_warns(self, session_store, caplog):
        request = api_request(security.anonymous_session_tag(), with_token=False)
        levels = self._levels(caplog, lambda: interface.check_apikey(request))
        assert "WARNING" in levels

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0, "api_warnings": True})
    def test_page_post_with_a_stale_token_is_only_info(self, session_store, caplog):
        request = page_post(security.anonymous_session_tag(), csrf="f0" * 32)
        levels = self._levels(caplog, lambda: config_save_middleware().denied_response(request))
        assert "WARNING" not in levels
        assert "INFO" in levels

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0, "api_warnings": True})
    def test_cross_site_page_post_still_warns(self, session_store, caplog):
        levels = self._levels(caplog, lambda: config_save_middleware().denied_response(page_post()))
        assert "WARNING" in levels


class TestApiCsrf:
    """A cookie-authorized API call must echo its session's CSRF token in a header"""

    def _status(self, request) -> Optional[int]:
        response = interface.check_apikey(request)
        return response.status_code if response else None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_cookie_with_token_authorizes(self, session_store):
        assert self._status(api_request(security.anonymous_session_tag())) is None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_cookie_without_token_is_forbidden(self, session_store):
        """403, not 401: a reload cannot conjure up a header the client never sends"""
        assert self._status(api_request(security.anonymous_session_tag(), with_token=False)) == 403

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_stale_token_asks_for_a_reload(self, session_store):
        """401, because a reload does fix this one"""
        request = mock_request(security.anonymous_session_tag(), params={"mode": "queue", "name": ""}, csrf="f0" * 32)
        assert self._status(request) == 401

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_apikey_still_works_alongside_a_cookie(self, session_store):
        """The cookie check must fall through to the key, never reject on its own"""
        request = mock_request(
            security.anonymous_session_tag(),
            params={"mode": "queue", "name": "", "apikey": cfg.api_key()},
        )
        assert self._status(request) is None
        # ...and with no cookie at all, which is how 3rd-party clients call it
        assert self._status(mock_request(params={"mode": "queue", "name": "", "apikey": cfg.api_key()})) is None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_no_mode_is_exempt(self, session_store):
        """There is no carve-out list, including showlog"""
        assert self._status(api_request(security.anonymous_session_tag(), mode="showlog", with_token=False)) == 403
        assert self._status(api_request(security.anonymous_session_tag(), mode="showlog")) is None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_token_outside_the_header_is_not_accepted(self, session_store):
        """This route merges the query string into its params; page routes still take the field"""
        tag = security.anonymous_session_tag()
        token = security.csrf_token_for(tag)

        as_parameter = mock_request(tag, params={"mode": "queue", "name": "", security.CSRF_FIELD: token})
        assert self._status(as_parameter) == 403
        # The same token in the header is what the frontend sends, and it is accepted
        assert self._status(api_request(tag)) is None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_keyless_and_cookieless_still_reports_missing_key(self, session_store):
        assert self._status(mock_request(params={"mode": "queue", "name": ""})) == 403

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_apikey_is_compared_in_constant_time(self, session_store):
        key = cfg.api_key()
        assert self._status(mock_request(params={"mode": "queue", "name": "", "apikey": key})) is None
        # A prefix of the real key is no better than any other wrong key
        for wrong in (key[:-1], key[:1], "", "x" * len(key)):
            request = mock_request(params={"mode": "queue", "name": "", "apikey": wrong})
            assert self._status(request) == 403

    @pytest.mark.parametrize("credentials", [("", ""), ("user", "pass")])
    @pytest.mark.config(
        lambda params: {
            "username": params["credentials"][0],
            "password": params["credentials"][1],
            "inet_exposure": 0,
            "api_warnings": True,
        }
    )
    def test_apikey_does_not_open_the_page_routes(self, session_store, credentials):
        """Refused the same way whether or not credentials are configured, and never with a redirect to the login form"""
        request = page_post()
        request.state.params = {"apikey": cfg.api_key()}
        request.query_params = QueryParams("")

        response = config_save_middleware().denied_response(request)
        assert response is not None
        assert response.status_code == 403
        assert b"only accepted on /api" in response.body

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_stray_apikey_does_not_break_a_valid_session(self, session_store):
        store_session(session_store, "login-token")
        request = page_post("login-token", csrf=security.csrf_token_for("login-token"))
        request.state.params = {security.CSRF_FIELD: security.csrf_token_for("login-token")}
        request.query_params = QueryParams("apikey=" + cfg.api_key())
        assert config_save_middleware().denied_response(request) is None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_version_and_auth_skip_the_check(self, session_store):
        for mode in ("version", "auth"):
            assert self._status(mock_request(params={"mode": mode, "name": ""})) is None


class TestLogRoute:

    def _route(self):
        return next(route for route in interface.INTERFACE_ROUTES if getattr(route, "path", None) == "/log")

    def test_registered_as_a_guarded_post_route(self):
        assert sorted(self._route().methods) == ["POST"]

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_behind_the_login_check(self, session_store):
        """Driven through the route as registered, so weakening the decorator fails here"""
        route = self._route()
        captured = {}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                captured["headers"] = Headers(raw=message["headers"])

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/log",
            "query_string": b"",
            "headers": [(b"host", b"127.0.0.1:8080")],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8080),
            "scheme": "http",
        }
        asyncio.run(route.app(scope, receive, send))
        # Redirected to the login form, and the handler never ran to stream any of the log
        assert captured["status"] == 302
        assert captured["headers"]["location"].endswith("/login")


# The kinds of session cookie a page POST can arrive with, resolved once the test's
# credentials are in place
COOKIE_NONE = "none"
COOKIE_ANONYMOUS = "anonymous"
COOKIE_LOGIN = "login"
COOKIE_FORGED = "forged"


def cookie_of_kind(kind: str, store) -> Optional[str]:
    if kind == COOKIE_NONE:
        return None
    if kind == COOKIE_ANONYMOUS:
        return security.anonymous_session_tag()
    if kind == COOKIE_FORGED:
        return "f0" * 32
    store_session(store, "login-token")
    return "login-token"


# The CSRF token a page POST can arrive with, relative to the cookie it sends
TOKEN_NONE = "none"
TOKEN_MATCHING = "matching"
TOKEN_WRONG = "wrong"


def token_of_kind(kind: str, cookie_value: Optional[str]) -> Optional[str]:
    if kind == TOKEN_NONE:
        return None
    if kind == TOKEN_WRONG:
        return "f0" * 32
    return security.csrf_token_for(cookie_value or "")


class TestPagePostCsrf:

    @pytest.mark.parametrize(
        "credentials, inet_exposure, cookie, token, allowed",
        [
            # No credentials at all: check_login always passes, so this guard is all there is
            (("", ""), 0, COOKIE_NONE, TOKEN_NONE, False),
            (("", ""), 0, COOKIE_ANONYMOUS, TOKEN_MATCHING, True),
            (("", ""), 0, COOKIE_ANONYMOUS, TOKEN_NONE, False),
            (("", ""), 0, COOKIE_ANONYMOUS, TOKEN_WRONG, False),
            (("", ""), 0, COOKIE_FORGED, TOKEN_MATCHING, False),
            (("", ""), 5, COOKIE_NONE, TOKEN_NONE, False),
            # A token with no cookie must not pass: csrf_token_for("") is computable by anyone
            (("", ""), 0, COOKIE_NONE, TOKEN_MATCHING, False),
            # Credentials with the login enforced
            (("user", "pass"), 0, COOKIE_NONE, TOKEN_NONE, False),
            (("user", "pass"), 0, COOKIE_LOGIN, TOKEN_MATCHING, True),
            (("user", "pass"), 0, COOKIE_LOGIN, TOKEN_NONE, False),
            # inet_exposure 5: the login is waived, so check_login passes with no cookie
            (("user", "pass"), 5, COOKIE_NONE, TOKEN_NONE, False),
            (("user", "pass"), 5, COOKIE_FORGED, TOKEN_MATCHING, False),
            (("user", "pass"), 5, COOKIE_ANONYMOUS, TOKEN_MATCHING, True),
            (("user", "pass"), 5, COOKIE_ANONYMOUS, TOKEN_NONE, False),
            # ...without locking out a local client who does hold a real login session
            (("user", "pass"), 5, COOKIE_LOGIN, TOKEN_MATCHING, True),
        ],
    )
    @pytest.mark.config(
        lambda params: {
            "username": params["credentials"][0],
            "password": params["credentials"][1],
            "inet_exposure": params["inet_exposure"],
        }
    )
    def test_config_save_post(self, session_store, credentials, inet_exposure, cookie, token, allowed):
        cookie_value = cookie_of_kind(cookie, session_store)
        request = page_post(cookie_value, csrf=token_of_kind(token, cookie_value))
        response = config_save_middleware().denied_response(request)
        assert (response is None) is allowed

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_token_accepted_as_form_field(self, session_store):
        """A form that navigates cannot set a header, so the body is accepted too"""
        tag = security.anonymous_session_tag()
        allowed = page_post(tag, csrf_field=security.csrf_token_for(tag))
        assert config_save_middleware().denied_response(allowed) is None
        denied = page_post(tag, csrf_field="f0" * 32)
        assert config_save_middleware().denied_response(denied) is not None

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 5})
    def test_token_is_bound_to_its_own_session(self, session_store):
        cookie_of_kind(COOKIE_LOGIN, session_store)
        anonymous_tag = security.anonymous_session_tag()

        login_with_anonymous_token = page_post("login-token", csrf=security.csrf_token_for(anonymous_tag))
        assert config_save_middleware().denied_response(login_with_anonymous_token) is not None

        anonymous_with_login_token = page_post(anonymous_tag, csrf=security.csrf_token_for("login-token"))
        assert config_save_middleware().denied_response(anonymous_with_login_token) is not None

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 5})
    def test_external_client_still_needs_login(self, session_store):
        """The waiver is local-only: an external POST gets no help from the anonymous tag"""
        tag = security.anonymous_session_tag()
        request = page_post(tag, remote_ip="9.8.7.6", csrf=security.csrf_token_for(tag))
        assert config_save_middleware().denied_response(request) is not None

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_session_is_looked_up_once_per_request(self, session_store):
        store_session(session_store, "login-token")
        request = page_post("login-token", csrf=security.csrf_token_for("login-token"))

        with patch.object(sabnzbd.SessionStore, "get", wraps=sabnzbd.SessionStore.get) as get_session:
            assert config_save_middleware().denied_response(request) is None
        assert get_session.call_count == 1

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_get_is_not_guarded(self, session_store):
        """A first visit has no token yet, so rendering a page must not require one"""
        assert config_save_middleware().denied_response(mock_request()) is None


def run_page_request(cookie: Optional[str] = None, remote_ip: str = "127.0.0.1") -> tuple[list[str], str]:
    """Drive a page route's SecurityMiddleware over a real ASGI scope, returning the Set-Cookie values it injected and the CSRF token it published"""

    rendered_token = ""

    async def asgi_app(scope, receive, send):
        # Stand in for a page handler: build_header reads the token off request.state here
        nonlocal rendered_token
        rendered_token = scope.get("state", {}).get("csrf_token", "")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = interface.SecurityMiddleware(asgi_app, check_for_login=True, check_api_key=False, access_type=4)

    headers = [(b"host", b"127.0.0.1:8080")]
    if cookie:
        headers.append((b"cookie", ("%s=%s" % (security.SESSION_COOKIE_USER, cookie)).encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/config/general",
        "query_string": b"",
        "headers": headers,
        "client": (remote_ip, 12345),
        "server": ("127.0.0.1", 8080),
        "scheme": "http",
        # secured_expose always wraps SecurityMiddleware in ParamsMiddleware
        "state": {"params": QueryParams("")},
    }
    captured: list[str] = []

    async def send(message):
        if message["type"] == "http.response.start":
            captured.extend(Headers(raw=message["headers"]).getlist("set-cookie"))

    asyncio.run(middleware(scope, None, send))
    return captured, rendered_token


def issued_session_cookies(cookie: Optional[str] = None, remote_ip: str = "127.0.0.1") -> list[str]:
    return run_page_request(cookie=cookie, remote_ip=remote_ip)[0]


class TestAnonymousSessionIssuing:

    def _issued(self, **kwargs) -> bool:
        return any(value.startswith(security.SESSION_COOKIE_USER + "=") for value in issued_session_cookies(**kwargs))

    @pytest.mark.config({"username": "", "password": ""})
    def test_issued_without_credentials(self, session_store):
        assert self._issued() is True

    @pytest.mark.config({"username": "", "password": ""})
    def test_not_reissued_when_tag_already_held(self, session_store):
        assert self._issued(cookie=security.anonymous_session_tag()) is False

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 5})
    def test_issued_when_login_waived_for_local_client(self, session_store):
        assert self._issued() is True

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 5})
    def test_login_session_not_overwritten(self, session_store):
        store_session(session_store, "login-token")
        assert self._issued(cookie="login-token") is False


def session_cookie_value(set_cookie_headers: list[str], fallback: Optional[str]) -> str:
    """The session cookie the client is left holding after a response"""
    for value in set_cookie_headers:
        if value.startswith(security.SESSION_COOKIE_USER + "="):
            return value.split("=", 1)[1].split(";", 1)[0]
    return fallback or ""


class TestRenderedTokenMatchesCookie:

    def _assert_token_matches(self, cookie: Optional[str]):
        set_cookies, rendered_token = run_page_request(cookie=cookie)
        held = session_cookie_value(set_cookies, cookie)
        assert rendered_token == security.csrf_token_for(held)
        assert rendered_token, "a page rendered no usable token at all"

    @pytest.mark.config({"username": "", "password": ""})
    def test_first_load_with_no_cookie(self, session_store):
        self._assert_token_matches(None)

    @pytest.mark.config({"username": "", "password": ""})
    def test_load_with_stale_cookie(self, session_store):
        # A tag from before a restart rotated the key: a fresh cookie is issued
        self._assert_token_matches("f0" * 32)

    @pytest.mark.config({"username": "", "password": ""})
    def test_steady_state_anonymous(self, session_store):
        self._assert_token_matches(security.anonymous_session_tag())

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_login_session(self, session_store):
        store_session(session_store, "login-token")
        self._assert_token_matches("login-token")

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 5})
    def test_login_session_while_login_waived(self, session_store):
        store_session(session_store, "login-token")
        self._assert_token_matches("login-token")

    @pytest.mark.config({"username": "", "password": ""})
    def test_rendered_token_authorizes_the_next_post(self, session_store):
        set_cookies, rendered_token = run_page_request()
        held = session_cookie_value(set_cookies, None)
        request = page_post(held, csrf=rendered_token)
        assert config_save_middleware().denied_response(request) is None
