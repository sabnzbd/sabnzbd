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
sabnzbd.newswrapper
"""

import errno
import socket
from threading import Thread
from nntplib import NNTPPermanentError
import time
import logging
import ssl

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.encoding import utob
import sabnzbd.cfg
from sabnzbd.misc import nntp_to_msg, probablyipv4, probablyipv6

# Set pre-defined socket timeout
socket.setdefaulttimeout(DEF_TIMEOUT)

# getaddrinfo() can be very slow. In some situations this can lead
# to delayed starts and timeouts on connections.
# Because of this, the results will be cached in the server object.


def _retrieve_info(server):
    """ Async attempt to run getaddrinfo() for specified server """
    logging.debug('Retrieving server address information for %s', server.host)
    info = GetServerParms(server.host, server.port)
    if not info:
        server.bad_cons += server.threads
    else:
        server.bad_cons = 0
    (server.info, server.request) = (info, False)
    sabnzbd.downloader.Downloader.do.wakeup()


def request_server_info(server):
    """ Launch async request to resolve server address """
    if not server.request:
        server.request = True
        Thread(target=_retrieve_info, args=(server,)).start()


def GetServerParms(host, port):
    """ Return processed getaddrinfo() for server """
    try:
        int(port)
    except:
        port = 119
    opt = sabnzbd.cfg.ipv6_servers()
    ''' ... with the following meaning for 'opt':
    Control the use of IPv6 Usenet server addresses. Meaning:
    0 = don't use
    1 = use when available and reachable (DEFAULT)
    2 = force usage (when SABnzbd's detection fails)
    '''
    try:
        # Standard IPV4 or IPV6
        ips = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        if opt == 2 or (opt == 1 and sabnzbd.EXTERNAL_IPV6) or (opt == 1 and sabnzbd.cfg.load_balancing() == 2):
            # IPv6 forced by user, or IPv6 allowed and reachable, or IPv6 allowed and loadbalancing-with-IPv6 activated
            # So return all IP addresses, no matter IPv4 or IPv6:
            return ips
        else:
            # IPv6 unreachable or not allowed by user, so only return IPv4 address(es):
            return [ip for ip in ips if ':' not in ip[4][0]]
    except:
        if opt == 2 or (opt == 1 and sabnzbd.EXTERNAL_IPV6) or (opt == 1 and sabnzbd.cfg.load_balancing() == 2):
            try:
                # Try IPV6 explicitly
                return socket.getaddrinfo(host, port, socket.AF_INET6,
                                          socket.SOCK_STREAM, socket.IPPROTO_IP, socket.AI_CANONNAME)
            except:
                # Nothing found!
                pass
        return False


def con(sock, host, port, sslenabled, write_fds, nntp):
    try:
        sock.connect((host, port))
        sock.setblocking(0)
        if sslenabled:
            # Log SSL/TLS info
            logging.info("%s@%s: Connected using %s (%s)",
                                              nntp.nw.thrdnum, nntp.nw.server.host, sock.version(), sock.cipher()[0])
            nntp.nw.server.ssl_info = "%s (%s)" % (sock.version(), sock.cipher()[0])

        # Now it's safe to add the socket to the list of active sockets.
        # 'write_fds' is an attribute of the Downloader singleton.
        # This direct access is needed to prevent multi-threading sync problems.
        if write_fds is not None:
            write_fds[sock.fileno()] = nntp.nw

    except (ssl.SSLError, ssl.CertificateError) as e:
        nntp.error(e)

    except socket.error as e:
        try:
            # socket.error can either return a string or a tuple
            if isinstance(e, tuple):
                (_errno, strerror) = e
            else:
                # Are we safe to hardcode the ETIMEDOUT error?
                (_errno, strerror) = (errno.ETIMEDOUT, str(e))
                e = (_errno, strerror)
            # expected, do nothing
            if _errno == errno.EINPROGRESS:
                pass
        finally:
            nntp.error(e)


class NNTP:
    # Pre-define attributes to save memory
    __slots__ = ('host', 'port', 'nw', 'blocking', 'error_msg', 'sock')

    def __init__(self, host, port, info, sslenabled, nw, block=False, write_fds=None):
        self.host = host
        self.port = port
        self.nw = nw
        self.blocking = block
        self.error_msg = None

        if not info:
            raise socket.error(errno.EADDRNOTAVAIL, "Address not available - Check for internet or DNS problems")

        af, socktype, proto, canonname, sa = info[0]

        # there will be a connect to host (or self.host, so let's force set 'af' to the correct value
        if probablyipv4(host):
            af = socket.AF_INET
        if probablyipv6(host):
            af = socket.AF_INET6

        if sslenabled:
            # Use context or just wrapper
            if sabnzbd.CERTIFICATE_VALIDATION:
                # Setup the SSL socket
                ctx = ssl.create_default_context()

                if sabnzbd.cfg.require_modern_tls():
                    # We want a modern TLS (1.2 or higher), so we disallow older protocol versions (<= TLS 1.1)
                    ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

                # Only verify hostname when we're strict
                if nw.server.ssl_verify < 2:
                    ctx.check_hostname = False
                # Certificates optional
                if nw.server.ssl_verify == 0:
                    ctx.verify_mode = ssl.CERT_NONE

                # Did the user set a custom cipher-string?
                if nw.server.ssl_ciphers:
                    # At their own risk, socket will error out in case it was invalid
                    ctx.set_ciphers(nw.server.ssl_ciphers)

                self.sock = ctx.wrap_socket(socket.socket(af, socktype, proto), server_hostname=str(nw.server.host))
            else:
                # Use a regular wrapper, no certificate validation
                self.sock = ssl.wrap_socket(socket.socket(af, socktype, proto), ciphers=sabnzbd.cfg.ssl_ciphers())
        else:
            self.sock = socket.socket(af, socktype, proto)

        try:
            # Open the connection in a separate thread due to avoid blocking
            # For server-testing we do want blocking
            if not block:
                Thread(target=con, args=(self.sock, self.host, self.port, sslenabled, write_fds, self)).start()
            else:
                # if blocking (server test) only wait for 15 seconds during connect until timeout
                self.sock.settimeout(15)
                self.sock.connect((self.host, self.port))
                if sslenabled:
                    # Log SSL/TLS info
                    logging.info("%s@%s: Connected using %s (%s)",
                                              self.nw.thrdnum, self.nw.server.host, self.sock.version(), self.sock.cipher()[0])
                    self.nw.server.ssl_info = "%s (%s)" % (self.sock.version(), self.sock.cipher()[0])

        except (ssl.SSLError, ssl.CertificateError) as e:
            self.error(e)

        except socket.error as e:
            try:
                # socket.error can either return a string or a tuple
                if isinstance(e, tuple):
                    (_errno, strerror) = e
                else:
                    # Are we safe to hardcode the ETIMEDOUT error?
                    (_errno, strerror) = (errno.ETIMEDOUT, str(e))
                    e = (_errno, strerror)
                # expected, do nothing
                if _errno == errno.EINPROGRESS:
                    pass
            finally:
                self.error(e)

    def error(self, error):
        raw_error_str = str(error)
        if 'SSL23_GET_SERVER_HELLO' in str(error) or 'SSL3_GET_RECORD' in raw_error_str:
            error = T('This server does not allow SSL on this port')

        # Catch certificate errors
        if type(error) == ssl.CertificateError or 'CERTIFICATE_VERIFY_FAILED' in raw_error_str:
            # Log the raw message for debug purposes
            logging.info('Certificate error for host %s: %s', self.nw.server.host, raw_error_str)

            # Try to see if we should catch this message and provide better text
            if 'hostname' in raw_error_str:
                raw_error_str = T('Certificate hostname mismatch: the server hostname is not listed in the certificate. This is a server issue.')
            elif 'certificate verify failed' in raw_error_str:
                raw_error_str = T('Certificate not valid. This is most probably a server issue.')

            # Reformat error
            error = T('Server %s uses an untrusted certificate [%s]') % (self.nw.server.host, raw_error_str)
            error = '%s - %s: %s' % (error, T('Wiki'), 'https://sabnzbd.org/certificate-errors')

            # Prevent throwing a lot of errors or when testing server
            if error not in self.nw.server.warning and not self.blocking:
                logging.error(error)
            # Pass to server-test
            if self.blocking:
                raise ssl.CertificateError(error)

        # Blocking = server-test, pass directly to display code
        if self.blocking:
            raise socket.error(errno.ECONNREFUSED, str(error))
        else:
            msg = "Failed to connect: %s" % (str(error))
            msg = "%s %s@%s:%s" % (msg, self.nw.thrdnum, self.host, self.port)
            self.error_msg = msg
            logging.info(msg)
            self.nw.server.warning = msg


class NewsWrapper:
    # Pre-define attributes to save memory
    __slots__ = ('server', 'thrdnum', 'blocking', 'timeout', 'article', 'data', 'last_line',  'nntp',
                 'recv', 'connected', 'user_sent', 'pass_sent', 'group', 'user_ok', 'pass_ok', 'force_login')

    def __init__(self, server, thrdnum, block=False):
        self.server = server
        self.thrdnum = thrdnum
        self.blocking = block

        self.timeout = None
        self.article = None
        self.data = []
        self.last_line = ''

        self.nntp = None
        self.recv = None

        self.connected = False

        self.user_sent = False
        self.pass_sent = False

        self.group = None

        self.user_ok = False
        self.pass_ok = False
        self.force_login = False

    @property
    def status_code(self):
        """ Shorthand to get the code """
        try:
            return int(self.data[0][:3])
        except:
            return None

    def init_connect(self, write_fds):
        # Server-info is normally requested by initialization of
        # servers in Downloader, but not when testing servers
        if self.blocking and not self.server.info:
            self.server.info = GetServerParms(self.server.host, self.server.port)

        # Construct NNTP object and shorthands
        self.nntp = NNTP(self.server.hostip, self.server.port, self.server.info, self.server.ssl,
                         self, self.blocking, write_fds)
        self.recv = self.nntp.sock.recv
        self.timeout = time.time() + self.server.timeout

    def finish_connect(self, code):
        if not (self.server.username or self.server.password or self.force_login):
            self.connected = True
            self.user_sent = True
            self.user_ok = True
            self.pass_sent = True
            self.pass_ok = True

        if code == 501 and self.user_sent:
            # Change to a sensible text
            code = 481
            self.data[0] = "%d %s" % (code, T('Authentication failed, check username/password.'))
            self.user_ok = True
            self.pass_sent = True

        if code == 480:
            self.force_login = True
            self.connected = False
            self.user_sent = False
            self.user_ok = False
            self.pass_sent = False
            self.pass_ok = False

        if code in (400, 502):
            raise NNTPPermanentError(nntp_to_msg(self.data))
        elif not self.user_sent:
            command = utob('authinfo user %s\r\n' % self.server.username)
            self.nntp.sock.sendall(command)
            self.data = []
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
            command = utob('authinfo pass %s\r\n' % self.server.password)
            self.nntp.sock.sendall(command)
            self.data = []
            self.pass_sent = True
        elif self.user_ok and not self.pass_ok:
            if code != 281:
                # Assume that login failed (code 481 or other)
                raise NNTPPermanentError(nntp_to_msg(self.data))
            else:
                self.connected = True

        self.timeout = time.time() + self.server.timeout

    def body(self, precheck):
        self.timeout = time.time() + self.server.timeout
        if precheck:
            if self.server.have_stat:
                command = utob('STAT <%s>\r\n' % (self.article.article))
            else:
                command = utob('HEAD <%s>\r\n' % (self.article.article))
        elif self.server.have_body:
            command = utob('BODY <%s>\r\n' % (self.article.article))
        else:
            command = utob('ARTICLE <%s>\r\n' % (self.article.article))
        self.nntp.sock.sendall(command)
        self.data = []

    def send_group(self, group):
        self.timeout = time.time() + self.server.timeout
        command = utob('GROUP %s\r\n' % (group))
        self.nntp.sock.sendall(command)
        self.data = []

    def recv_chunk(self, block=False):
        """ Receive data, return #bytes, done, skip """
        self.timeout = time.time() + self.server.timeout
        while 1:
            try:
                if self.nntp.nw.server.ssl:
                    # SSL chunks come in 16K frames
                    # Setting higher limits results in slowdown
                    chunk = self.recv(16384)
                else:
                    # Get as many bytes as possible
                    chunk = self.recv(262144)
                break
            except ssl.SSLWantReadError as e:
                # SSL connections will block until they are ready.
                # Either ignore the connection until it responds
                # Or wait in a loop until it responds
                if block:
                    # time.sleep(0.0001)
                    continue
                else:
                    return 0, False, True

        # Append so we can do 1 join(), much faster than multiple!
        self.data.append(chunk)

        # Official end-of-article is ".\r\n" but sometimes it can get lost between 2 chunks
        chunk_len = len(chunk)
        if chunk[-5:] == b'\r\n.\r\n':
            return (chunk_len, True, False)
        elif chunk_len < 5 and len(self.data) > 1:
            # We need to make sure the end is not split over 2 chunks
            # This is faster than join()
            combine_chunk = self.data[-2][-5:] + chunk
            if combine_chunk[-5:] == b'\r\n.\r\n':
                return (chunk_len, True, False)

        # Still in middle of data, so continue!
        return (chunk_len, False, False)

    def soft_reset(self):
        self.timeout = None
        self.article = None
        self.clear_data()

    def clear_data(self):
        self.data = []
        self.last_line = ''

    def hard_reset(self, wait=True, quit=True):
        if self.nntp:
            try:
                if quit:
                    self.nntp.sock.sendall(b'QUIT\r\n')
                    time.sleep(0.1)
                self.nntp.sock.close()
            except:
                pass

        self.__init__(self.server, self.thrdnum)

        # Wait before re-using this newswrapper
        if wait:
            # Reset due to error condition, use server timeout
            self.timeout = time.time() + self.server.timeout
        else:
            # Reset for internal reasons, just wait 5 sec
            self.timeout = time.time() + 5

    def terminate(self, quit=False):
        """ Close connection and remove nntp object """
        if self.nntp:
            try:
                if quit:
                    self.nntp.sock.sendall(b'QUIT\r\n')
                    time.sleep(0.1)
                self.nntp.sock.close()
            except:
                pass
        del self.nntp
