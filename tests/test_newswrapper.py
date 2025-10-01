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
tests.test_newswrapper - Tests of various functions in newswrapper
"""
import errno
import ipaddress
import logging
import os.path
import socket
import sys
import tempfile
import threading
import ssl
import time
import warnings
from enum import Enum
from typing import Optional, Tuple
import portend
from flaky import flaky

from tests.testhelper import *
from sabnzbd import misc
from sabnzbd import newswrapper
from sabnzbd.get_addrinfo import AddrInfo

TEST_HOST = "127.0.0.1"
TEST_PORT = portend.find_available_local_port()
TEST_DATA = b"connection_test"


class IPProtocolVersion(Enum):
    IPV4 = 4
    IPV6 = 6


def socket_test_server(ssl_context: ssl.SSLContext):
    """Support function that starts a mini-server"""
    # Allow reuse of the address, because our CI is too fast for the socket closing
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((TEST_HOST, TEST_PORT))
        server_socket.listen(1)
        server_socket.settimeout(1.0)
        conn, _ = server_socket.accept()
        with ssl_context.wrap_socket(sock=conn, server_side=True) as wrapped_socket:
            wrapped_socket.write(TEST_DATA)
    except Exception as e:
        # Skip SSL errors
        logging.info("Error in server: %s", e)
        pass
    finally:
        # Make sure to close the socket
        server_socket.close()


def get_local_ip(protocol_version: IPProtocolVersion) -> Optional[str]:
    """
    Find the ip address that would be used to send traffic towards internet. Uses the UDP Socket trick: connect is not
    sending any traffic but already prefills what would be the sender ip address.
    """
    s: Optional[socket.socket] = None
    address_to_connect_to: Optional[Tuple[str, int]] = None
    if protocol_version == IPProtocolVersion.IPV4:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Google DNS IPv4
        address_to_connect_to = ("8.8.8.8", 80)
    elif protocol_version == IPProtocolVersion.IPV6:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        # Google DNS IPv6
        address_to_connect_to = ("2001:4860:4860::8888", 80)
    else:
        raise ValueError(f"Unknown protocol version: {protocol_version}")

    assert s is not None, "Socket has not been assigned!"
    assert address_to_connect_to is not None, "Address to connect to has not been assigned!"

    try:
        s.connect(address_to_connect_to)
        local_ip = s.getsockname()[0]
    except OSError as e:
        # If the network is unreachable, it's probably that we don't have an IP for this Protocol
        # On Linux, we would get ENETUNREACH where on Mac OS we would get EHOSTUNREACH
        if e.errno == errno.ENETUNREACH or e.errno == errno.EHOSTUNREACH:
            return None
        else:
            raise
    finally:
        s.close()
    return local_ip


@flaky
class TestNewsWrapper:
    cert_file = os.path.join(tempfile.mkdtemp(), "test.cert")
    key_file = os.path.join(tempfile.mkdtemp(), "test.key")

    @pytest.mark.parametrize(
        "server_tls, expected_client_tls, client_cipher, can_connect",
        [
            (None, "TLSv1.3", None, True),  # Default, highest
            (ssl.TLSVersion.TLSv1_2, "TLSv1.2", None, True),  # Server with just TLSv1.2
            (ssl.TLSVersion.SSLv3, None, None, False),  # No connection for old TLS/SSL
            (ssl.TLSVersion.TLSv1, None, None, False),
            (ssl.TLSVersion.TLSv1_1, None, None, False),
            (None, None, "RC4-MD5", False),  # No connection for old cipher
            (None, "TLSv1.2", "AES256-SHA", True),  # Forced to TLSv1.2 if ciphers set
            (None, None, "TLS_AES_128_CCM_SHA256", False),  # Cannot force use of TLSv1.3 cipher
        ],
    )
    def test_newswrapper(
        self,
        server_tls: Optional[ssl.TLSVersion],
        expected_client_tls: Optional[str],
        client_cipher: Optional[str],
        can_connect: bool,
    ):
        # We need at least some certificates for the server to work
        if not os.path.exists(self.cert_file) or not os.path.exists(self.key_file):
            misc.create_https_certificates(self.cert_file, self.key_file)

        # Create the server context
        server_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        server_context.load_cert_chain(self.cert_file, self.key_file)
        server_context.set_ciphers("HIGH")

        # Set the options
        if server_tls:
            # Ignore DeprecationWarning about old SSL/TLS settings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                server_context.maximum_version = server_tls

        server_thread = threading.Thread(target=socket_test_server, args=(server_context,), daemon=True)
        server_thread.start()

        # Create the NNTP, mocking the required values
        # We disable certificate validation, as we use self-signed certificates
        nw = mock.Mock()
        nw.blocking = True
        nw.thrdnum = 1
        nw.server = mock.Mock()
        nw.server.host = TEST_HOST
        nw.server.port = TEST_PORT
        nw.server.info = AddrInfo(*socket.getaddrinfo(TEST_HOST, TEST_PORT, 0, socket.SOCK_STREAM)[0])
        nw.server.timeout = 10
        nw.server.ssl = True
        nw.server.ssl_context = None
        nw.server.ssl_verify = 0
        nw.server.ssl_ciphers = client_cipher

        # Do we expect failure to connect?
        if not can_connect:
            with pytest.raises(OSError):
                newswrapper.NNTP(nw, nw.server.info)
        else:
            nntp = newswrapper.NNTP(nw, nw.server.info)
            assert nntp.sock.recv(len(TEST_DATA)) == TEST_DATA

            # Assert SSL data
            assert nntp.sock.version() == expected_client_tls

            if client_cipher:
                assert nntp.sock.cipher()[0] == client_cipher

        # Wait for server to close
        server_thread.join(timeout=1.5)
        if server_thread.is_alive():
            raise RuntimeError("Test server was not stopped")
        time.sleep(1.0)

    @pytest.mark.parametrize(
        "local_ip, ip_protocol",
        [
            (get_local_ip(protocol_version=IPProtocolVersion.IPV4), IPProtocolVersion.IPV4),
            (get_local_ip(protocol_version=IPProtocolVersion.IPV6), IPProtocolVersion.IPV6),
            (None, None),
        ],
    )
    def test_socket_binding_outgoing_ip(
        self, local_ip: Optional[str], ip_protocol: Optional[IPProtocolVersion], monkeypatch
    ):
        """Test to make sure that the binding of outgoing interface works as expected."""
        if local_ip is None and ip_protocol is not None:
            pytest.skip(f"No available ip for this protocol: {ip_protocol}")
        elif ip_protocol is not None:
            # We want to make sure the local ip is matching the version of the expected IP Protocol
            assert ipaddress.ip_address(local_ip).version == ip_protocol.value

        nw = mock.Mock()

        nw.blocking = True
        nw.thrdnum = 1
        nw.server = mock.Mock()
        nw.server.host = TEST_HOST
        nw.server.port = TEST_PORT
        nw.server.info = AddrInfo(*socket.getaddrinfo(TEST_HOST, TEST_PORT, 0, socket.SOCK_STREAM)[0])
        nw.server.timeout = 10
        nw.server.ssl = True
        nw.server.ssl_context = None
        nw.server.ssl_verify = 0
        nw.server.ssl_ciphers = None

        sabnzbd.cfg.outgoing_nttp_ip.set(local_ip)

        # We mock the connect as it's being called in the Init, we want to have a "functional" newswrapper.NNTP instance
        def mock_connect(self):
            pass

        monkeypatch.setattr("sabnzbd.newswrapper.NNTP.connect", mock_connect)
        nntp = newswrapper.NNTP(nw, nw.server.info)
        monkeypatch.undo()

        # The connection has crashed but the socket should have been bound to the provided ip in the configuration
        with pytest.raises(OSError) as excinfo:
            nntp.connect()

        if sys.platform == "win32":
            # On Windows, the error code for this is WSAECONNREFUSED (10061)
            assert excinfo.value.errno == errno.WSAECONNREFUSED
        else:
            # On Linux and macOS, the error code is ECONNREFUSED
            assert excinfo.value.errno == errno.ECONNREFUSED

        current_ip, _ = nntp.sock.getsockname()
        if local_ip is not None:
            assert current_ip == local_ip
        else:
            assert current_ip is not None
        nntp.close(send_quit=False)
