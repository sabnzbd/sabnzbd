#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.newswrapper
"""

import errno
import socket
from threading import Thread
from nntplib import NNTPPermanentError
import time
import logging
import ssl
from typing import List, Optional, Tuple, AnyStr

import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DEF_TIMEOUT
from sabnzbd.encoding import utob
from sabnzbd.misc import nntp_to_msg, is_ipv4_addr, is_ipv6_addr, get_server_addrinfo

# Set pre-defined socket timeout
socket.setdefaulttimeout(DEF_TIMEOUT)


class NewsWrapper:
    # Pre-define attributes to save memory
    __slots__ = (
        "server",
        "thrdnum",
        "blocking",
        "timeout",
        "article",
        "data",
        "nntp",
        "connected",
        "user_sent",
        "pass_sent",
        "group",
        "user_ok",
        "pass_ok",
        "force_login",
        "status_code",
    )

    def __init__(self, server, thrdnum, block=False):
        self.server: sabnzbd.downloader.Server = server
        self.thrdnum: int = thrdnum
        self.blocking: bool = block

        self.timeout: Optional[float] = None
        self.article: Optional[sabnzbd.nzbstuff.Article] = None
        self.data: List[AnyStr] = []

        self.nntp: Optional[NNTP] = None

        self.connected: bool = False
        self.user_sent: bool = False
        self.pass_sent: bool = False
        self.user_ok: bool = False
        self.pass_ok: bool = False
        self.force_login: bool = False
        self.group: Optional[str] = None
        self.status_code: Optional[int] = None

    def init_connect(self):
        """Setup the connection in NNTP object"""
        # Server-info is normally requested by initialization of
        # servers in Downloader, but not when testing servers
        if self.blocking and not self.server.info:
            self.server.info = get_server_addrinfo(self.server.host, self.server.port)

        # Construct NNTP object
        self.nntp = NNTP(self, self.server.hostip)
        self.timeout = time.time() + self.server.timeout

    def finish_connect(self, code: int):
        """Perform login options"""
        if not (self.server.username or self.server.password or self.force_login):
            self.connected = True
            self.user_sent = True
            self.user_ok = True
            self.pass_sent = True
            self.pass_ok = True

        if code == 501 and self.user_sent:
            # Change to a sensible text
            code = 481
            self.data[0] = "%d %s" % (code, T("Authentication failed, check username/password."))
            self.status_code = code
            self.user_ok = True
            self.pass_sent = True

        if code == 480:
            self.force_login = True
            self.connected = False
            self.user_sent = False
            self.user_ok = False
            self.pass_sent = False
            self.pass_ok = False

        if code in (400, 500, 502):
            raise NNTPPermanentError(nntp_to_msg(self.data))
        elif not self.user_sent:
            command = utob("authinfo user %s\r\n" % self.server.username)
            self.nntp.sock.sendall(command)
            self.clear_data()
            self.user_sent = True
        elif not self.user_ok:
            if code == 381:
                self.user_ok = True
            elif code == 281:
                # No login required
                self.user_ok = True
                self.pass_sent = True
                self.pass_ok = True
                self.connected = True

        if self.user_ok and not self.pass_sent:
            command = utob("authinfo pass %s\r\n" % self.server.password)
            self.nntp.sock.sendall(command)
            self.clear_data()
            self.pass_sent = True
        elif self.user_ok and not self.pass_ok:
            if code != 281:
                # Assume that login failed (code 481 or other)
                raise NNTPPermanentError(nntp_to_msg(self.data))
            else:
                self.connected = True

        self.timeout = time.time() + self.server.timeout

    def body(self):
        """Request the body of the article"""
        self.timeout = time.time() + self.server.timeout
        if self.article.nzf.nzo.precheck:
            if self.server.have_stat:
                command = utob("STAT <%s>\r\n" % self.article.article)
            else:
                command = utob("HEAD <%s>\r\n" % self.article.article)
        elif self.server.have_body:
            command = utob("BODY <%s>\r\n" % self.article.article)
        else:
            command = utob("ARTICLE <%s>\r\n" % self.article.article)
        self.nntp.sock.sendall(command)
        self.clear_data()

    def send_group(self, group: str):
        """Send the NNTP GROUP command"""
        self.timeout = time.time() + self.server.timeout
        command = utob("GROUP %s\r\n" % group)
        self.nntp.sock.sendall(command)
        self.clear_data()

    def recv_chunk(self, block: bool = False) -> Tuple[int, bool, bool]:
        """Receive data, return #bytes, done, skip"""
        self.timeout = time.time() + self.server.timeout
        while 1:
            try:
                if self.nntp.nw.server.ssl:
                    # SSL chunks come in 16K frames
                    # Setting higher limits results in slowdown
                    chunk = self.nntp.sock.recv(16384)
                else:
                    # Get as many bytes as possible
                    chunk = self.nntp.sock.recv(262144)
                break
            except ssl.SSLWantReadError:
                # SSL connections will block until they are ready.
                # Either ignore the connection until it responds
                # Or wait in a loop until it responds
                if block:
                    # time.sleep(0.0001)
                    continue
                else:
                    return 0, False, True

        if not self.data:
            try:
                self.status_code = int(chunk[:3])
            except:
                self.status_code = None

        # Append so we can do 1 join(), much faster than multiple!
        self.data.append(chunk)

        # Official end-of-article is ".\r\n" but sometimes it can get lost between 2 chunks
        chunk_len = len(chunk)
        if chunk[-5:] == b"\r\n.\r\n":
            return chunk_len, True, False
        elif chunk_len < 5 and len(self.data) > 1:
            # We need to make sure the end is not split over 2 chunks
            # This is faster than join()
            combine_chunk = self.data[-2][-5:] + chunk
            if combine_chunk[-5:] == b"\r\n.\r\n":
                return chunk_len, True, False

        # Still in middle of data, so continue!
        return chunk_len, False, False

    def soft_reset(self):
        """Reset for the next article"""
        self.timeout = None
        self.article = None
        self.clear_data()

    def clear_data(self):
        """Clear the stored raw data"""
        self.data = []
        self.status_code = None

    def hard_reset(self, wait: bool = True, send_quit: bool = True):
        """Destroy and restart"""
        if self.nntp:
            try:
                if send_quit:
                    self.nntp.sock.sendall(b"QUIT\r\n")
                    time.sleep(0.01)
                self.nntp.sock.close()
            except:
                pass
            self.nntp = None

        # Reset all variables (including the NNTP connection)
        self.__init__(self.server, self.thrdnum)

        # Wait before re-using this newswrapper
        if wait:
            # Reset due to error condition, use server timeout
            self.timeout = time.time() + self.server.timeout
        else:
            # Reset for internal reasons, just wait 5 sec
            self.timeout = time.time() + 5

    def __repr__(self):
        return "<NewsWrapper: server=%s:%s, thread=%s, connected=%s>" % (
            self.server.host,
            self.server.port,
            self.thrdnum,
            self.connected,
        )


class NNTP:
    # Pre-define attributes to save memory
    __slots__ = ("nw", "host", "error_msg", "sock", "fileno")

    def __init__(self, nw: NewsWrapper, host):
        self.nw: NewsWrapper = nw
        self.host: str = host  # Store the fastest ip
        self.error_msg: Optional[str] = None

        if not self.nw.server.info:
            raise socket.error(errno.EADDRNOTAVAIL, "Address not available - Check for internet or DNS problems")

        af, socktype, proto, _, _ = self.nw.server.info[0]

        # there will be a connect to host (or self.host, so let's force set 'af' to the correct value
        if is_ipv4_addr(self.host):
            af = socket.AF_INET
        if is_ipv6_addr(self.host):
            af = socket.AF_INET6

        # Create SSL-context if it is needed and not created yet
        if self.nw.server.ssl and not self.nw.server.ssl_context:
            # Setup the SSL socket
            self.nw.server.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

            # Only verify hostname when we're strict
            if self.nw.server.ssl_verify < 2:
                self.nw.server.ssl_context.check_hostname = False
                # Certificates optional
                if self.nw.server.ssl_verify == 0:
                    self.nw.server.ssl_context.verify_mode = ssl.CERT_NONE

            # Did the user set a custom cipher-string?
            if self.nw.server.ssl_ciphers:
                # At their own risk, socket will error out in case it was invalid
                self.nw.server.ssl_context.set_ciphers(self.nw.server.ssl_ciphers)
                # Python does not allow setting ciphers on TLSv1.3, so have to force TLSv1.2 as the maximum
                self.nw.server.ssl_context.maximum_version = ssl.TLSVersion.TLSv1_2
            else:
                # Support at least TLSv1.2+ ciphers, as some essential ones are removed by default in Python 3.10
                self.nw.server.ssl_context.set_ciphers("HIGH")

            if sabnzbd.cfg.allow_old_ssl_tls():
                # Allow anything that the system has
                self.nw.server.ssl_context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
            else:
                # We want a modern TLS (1.2 or higher), so we disallow older protocol versions (<= TLS 1.1)
                self.nw.server.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

            # Disable any verification if the setup is bad
            if not sabnzbd.CERTIFICATE_VALIDATION:
                self.nw.server.ssl_context.check_hostname = False
                self.nw.server.ssl_context.verify_mode = ssl.CERT_NONE

        # Create socket and store fileno of the socket
        self.sock = socket.socket(af, socktype, proto)
        self.fileno: int = self.sock.fileno()

        # Open the connection in a separate thread due to avoid blocking
        # For server-testing we do want blocking
        if not self.nw.blocking:
            Thread(target=self.connect).start()
        else:
            self.connect()

    def connect(self):
        """Start of connection, can be performed a-sync"""
        try:
            # Wait only 15 seconds during server test
            if self.nw.blocking:
                self.sock.settimeout(15)

            # Connect
            self.sock.connect((self.host, self.nw.server.port))

            # Secured or unsecured?
            if self.nw.server.ssl:
                # Wrap socket and log SSL/TLS diagnostic info
                self.sock = self.nw.server.ssl_context.wrap_socket(self.sock, server_hostname=self.nw.server.host)
                logging.info(
                    "%s@%s: Connected using %s (%s)",
                    self.nw.thrdnum,
                    self.nw.server.host,
                    self.sock.version(),
                    self.sock.cipher()[0],
                )
                self.nw.server.ssl_info = "%s (%s)" % (self.sock.version(), self.sock.cipher()[0])

            # Set blocking mode
            self.sock.setblocking(self.nw.blocking)

            # Now it's safe to add the socket to the list of active sockets
            # Skip this step during server test
            if not self.nw.blocking:
                sabnzbd.Downloader.add_socket(self.fileno, self.nw)
        except OSError as e:
            self.error(e)

    def error(self, error: OSError):
        raw_error_str = str(error)
        if "SSL23_GET_SERVER_HELLO" in str(error) or "SSL3_GET_RECORD" in raw_error_str:
            error = T("This server does not allow SSL on this port")

        # Catch certificate errors
        if type(error) == ssl.CertificateError or "CERTIFICATE_VERIFY_FAILED" in raw_error_str:
            # Log the raw message for debug purposes
            logging.info("Certificate error for host %s: %s", self.nw.server.host, raw_error_str)

            # Try to see if we should catch this message and provide better text
            if "hostname" in raw_error_str:
                raw_error_str = T(
                    "Certificate hostname mismatch: the server hostname is not listed in the certificate. This is a server issue."
                )
            elif "certificate verify failed" in raw_error_str:
                raw_error_str = T("Certificate not valid. This is most probably a server issue.")

            # Reformat error and overwrite str-representation
            error_str = T("Server %s uses an untrusted certificate [%s]") % (self.nw.server.host, raw_error_str)
            error_str = "%s - %s: %s" % (error_str, T("Wiki"), "https://sabnzbd.org/certificate-errors")
            error.strerror = error_str

            # Prevent throwing a lot of errors or when testing server
            if error_str not in self.nw.server.warning and not self.nw.blocking:
                logging.error(error_str)

            # Pass to server-test
            if self.nw.blocking:
                raise error

        # Blocking = server-test, pass directly to display code
        if self.nw.blocking:
            raise socket.error(errno.ECONNREFUSED, str(error))
        else:
            msg = "Failed to connect: %s" % (str(error))
            msg = "%s %s@%s:%s" % (msg, self.nw.thrdnum, self.host, self.nw.server.port)
            self.error_msg = msg
            self.nw.server.next_busy_threads_check = 0
            logging.info(msg)
            self.nw.server.warning = msg

    def __repr__(self):
        return "<NNTP: %s:%s>" % (self.host, self.nw.server.port)
