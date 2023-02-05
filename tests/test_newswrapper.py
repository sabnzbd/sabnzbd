#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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
import logging
import os.path
import socket
import tempfile
import threading
import ssl
import time
from typing import Optional
import portend
from flaky import flaky

from tests.testhelper import *
from sabnzbd import misc
from sabnzbd import newswrapper

TEST_HOST = "127.0.0.1"
TEST_PORT = portend.find_available_local_port()
TEST_DATA = b"connection_test"


def socket_test_server(ssl_context: ssl.SSLContext):
    """Support function that starts a mini-server, as
    socket.create_server is not supported on Python 3.7"""
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
        nw.server.info = socket.getaddrinfo(TEST_HOST, TEST_PORT, 0, socket.SOCK_STREAM)
        nw.server.timeout = 10
        nw.server.ssl = True
        nw.server.ssl_context = None
        nw.server.ssl_verify = 0
        nw.server.ssl_ciphers = client_cipher

        # Do we expect failure to connect?
        if not can_connect:
            with pytest.raises(OSError):
                newswrapper.NNTP(nw, TEST_HOST)
        else:
            nntp = newswrapper.NNTP(nw, TEST_HOST)
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
