#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
import re

import sabnzbd
from sabnzbd.constants import *
import sabnzbd.cfg
from sabnzbd.utils.sslinfo import ssl_method

try:
    from OpenSSL import SSL
    _ssl = SSL
    WantReadError = _ssl.WantReadError
    del SSL
    HAVE_SSL = True

except ImportError:
    _ssl = None
    HAVE_SSL = False

    # Dummy class so this exception is ignored by clients without ssl installed
    class WantReadError(Exception):

        def __init__(self, value):
            self.parameter = value

        def __str__(self):
            return repr(self.parameter)



import threading
_RLock = threading.RLock
del threading

import select


socket.setdefaulttimeout(DEF_TIMEOUT)


def force_bytes(p):
    """ Force string to 8bit bytes to compensate for bug in PyOpenSSL 0.14 """
    if isinstance(p, unicode) and p.encode('cp1252', 'replace') == p.encode('cp1252', 'ignore'):
        return p.encode('cp1252', 'replace')
    else:
        return p

# getaddrinfo() can be very slow. In some situations this can lead
# to delayed starts and timeouts on connections.
# Because of this, the results will be cached in the server object.


def _retrieve_info(server):
    """ Async attempt to run getaddrinfo() for specified server """
    info = GetServerParms(server.host, server.port)

    if info is None:
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
        return None


def con(sock, host, port, sslenabled, write_fds, nntp):
    assert isinstance(nntp, NNTP)
    try:
        sock.connect((host, port))
        sock.setblocking(0)
        if sslenabled and _ssl:
            while True:
                try:
                    sock.do_handshake()
                    break
                except WantReadError:
                    select.select([sock], [], [], 1.0)

        # Now it's safe to add the socket to the list of active sockets.
        # 'write_fds' is an attribute of the Downloader singleton.
        # This direct access is needed to prevent multi-threading sync problems.
        if write_fds is not None:
            write_fds[sock.fileno()] = nntp.nw

    except socket.error, e:
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

    except _ssl.Error, e:
        nntp.error(e)


def probablyipv4(ip):
    if ip.count('.') == 3 and re.sub('[0123456789.]', '', ip) == '':
        return True
    else:
        return False


def probablyipv6(ip):
    if ip.count(':') >= 2 and re.sub('[0123456789abcdefABCDEF:]', '', ip) == '':
        return True
    else:
        return False


class NNTP(object):

    def __init__(self, host, port, info, sslenabled, ssl_type, send_group, nw, user=None, password=None, block=False, write_fds=None):
        assert isinstance(nw, NewsWrapper)
        self.host = host
        self.port = port
        self.nw = nw
        self.blocking = block
        self.error_msg = None

        if not info:
            if block:
                info = GetServerParms(host, port)
            else:
                raise socket.error(errno.EADDRNOTAVAIL, "Address not available - Check for internet or DNS problems")

        af, socktype, proto, canonname, sa = info[0]

        # there will be a connect to host (or self.host, so let's force set 'af' to the correct value
        if probablyipv4(host):
            af = socket.AF_INET
        if probablyipv6(host):
            af = socket.AF_INET6

        if sslenabled and _ssl:
            ctx = _ssl.Context(ssl_method(ssl_type))
            self.sock = SSLConnection(ctx, socket.socket(af, socktype, proto))
        elif sslenabled and not _ssl:
            logging.error(T('Error importing OpenSSL module. Connecting with NON-SSL'))
            self.sock = socket.socket(af, socktype, proto)
        else:
            self.sock = socket.socket(af, socktype, proto)

        try:
            # Windows must do the connection in a separate thread due to non-blocking issues
            # If the server wants to be blocked (for testing) then use the linux route
            if not block:
                Thread(target=con, args=(self.sock, self.host, self.port, sslenabled, write_fds, self)).start()
            else:
                # if blocking (server test) only wait for 4 seconds during connect until timeout
                if block:
                    self.sock.settimeout(10)
                self.sock.connect((self.host, self.port))
                if not block:
                    self.sock.setblocking(0)
                if sslenabled and _ssl:
                    while True:
                        try:
                            self.sock.do_handshake()
                            break
                        except WantReadError:
                            select.select([self.sock], [], [], 1.0)

        except socket.error, e:
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

        except _ssl.Error, e:
            self.error(e)

    def error(self, error):
        if 'SSL23_GET_SERVER_HELLO' in str(error) or 'SSL3_GET_RECORD' in str(error):
            error = T('This server does not allow SSL on this port')
        msg = "Failed to connect: %s" % (str(error))
        msg = "%s %s@%s:%s" % (msg, self.nw.thrdnum, self.host, self.port)
        self.error_msg = msg
        if self.blocking:
            raise socket.error(errno.ECONNREFUSED, msg)
        else:
            logging.info(msg)
            self.nw.server.warning = msg


class NewsWrapper(object):

    def __init__(self, server, thrdnum, block=False):
        self.server = server
        self.thrdnum = thrdnum
        self.blocking = block

        self.timeout = None
        self.article = None
        self.data = ''
        self.lines = []

        self.nntp = None
        self.recv = None

        self.connected = False

        self.user_sent = False
        self.pass_sent = False

        self.group = None

        self.user_ok = False
        self.pass_ok = False
        self.force_login = False

    def init_connect(self, write_fds):
        self.nntp = NNTP(self.server.hostip, self.server.port, self.server.info, self.server.ssl,
                         self.server.ssl_type, self.server.send_group, self,
                         self.server.username, self.server.password, self.blocking, write_fds)
        self.recv = self.nntp.sock.recv

        self.timeout = time.time() + self.server.timeout

    def finish_connect(self, code):
        if not (self.server.username or self.server.password or self.force_login):
            self.connected = True
            self.user_sent = True
            self.user_ok = True
            self.pass_sent = True
            self.pass_ok = True

        if code in ('501', '502') and self.user_sent:
            # Change to a sensible text
            code = '481'
            self.lines[0] = T('Authentication failed, check username/password.')
            self.user_ok = True
            self.pass_sent = True

        if code == '480':
            self.force_login = True
            self.connected = False
            self.user_sent = False
            self.user_ok = False
            self.pass_sent = False
            self.pass_ok = False

        if code in ('400', '502'):
            raise NNTPPermanentError(self.lines[0])
        elif not self.user_sent:
            command = 'authinfo user %s\r\n' % force_bytes(self.server.username)
            self.nntp.sock.sendall(command)
            self.user_sent = True
        elif not self.user_ok:
            if code == '381':
                self.user_ok = True
            elif code == '281':
                # No login required
                self.user_ok = True
                self.pass_sent = True
                self.pass_ok = True
                self.connected = True

        if self.user_ok and not self.pass_sent:
            command = 'authinfo pass %s\r\n' % force_bytes(self.server.password)
            self.nntp.sock.sendall(command)
            self.pass_sent = True
        elif self.user_ok and not self.pass_ok:
            if code != '281':
                # Assume that login failed (code 481 or other)
                raise NNTPPermanentError(self.lines[0])
            else:
                self.connected = True

        self.timeout = time.time() + self.server.timeout

    def body(self, precheck):
        self.timeout = time.time() + self.server.timeout
        if precheck:
            if self.server.have_stat:
                command = 'STAT <%s>\r\n' % (self.article.article)
            else:
                command = 'HEAD <%s>\r\n' % (self.article.article)
        elif self.server.have_body:
            command = 'BODY <%s>\r\n' % (self.article.article)
        else:
            command = 'ARTICLE <%s>\r\n' % (self.article.article)
        self.nntp.sock.sendall(command)

    def send_group(self, group):
        self.timeout = time.time() + self.server.timeout
        command = 'GROUP %s\r\n' % (group)
        self.nntp.sock.sendall(command)

    def recv_chunk(self, block=False):
        """ Receive data, return #bytes, done, skip """
        self.timeout = time.time() + self.server.timeout
        while 1:
            try:
                chunk = self.recv(32768)
                break
            except WantReadError:
                # SSL connections will block until they are ready.
                # Either ignore the connection until it responds
                # Or wait in a loop until it responds
                if block:
                    # time.sleep(0.0001)
                    continue
                else:
                    return (0, False, True)

        self.data += chunk
        new_lines = self.data.split('\r\n')
        # See if incorrect newline-only was used
        # Do this as a special case to prevent using extra memory
        # for normal articles
        if len(new_lines) == 1 and '\r' not in self.data:
            new_lines = self.data.split('\n')

        self.data = new_lines.pop()
        self.lines.extend(new_lines)

        if self.lines and self.lines[-1] == '.':
            self.lines = self.lines[1:-1]
            return (len(chunk), True, False)
        else:
            return (len(chunk), False, False)

    def soft_reset(self):
        self.timeout = None
        self.article = None
        self.data = ''
        self.lines = []

    def hard_reset(self, wait=True, quit=True):
        if self.nntp:
            try:
                if quit:
                    self.nntp.sock.sendall('QUIT\r\n')
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
                    self.nntp.sock.sendall('QUIT\r\n')
                    time.sleep(0.1)
                self.nntp.sock.close()
            except:
                pass
        del self.nntp


class SSLConnection(object):

    def __init__(self, *args):
        self._ssl_conn = apply(_ssl.Connection, args)
        self._lock = _RLock()

    for f in ('get_context', 'pending', 'send', 'write', 'recv', 'read',
              'renegotiate', 'bind', 'listen', 'connect', 'accept',
              'setblocking', 'fileno', 'shutdown', 'close', 'get_cipher_list',
              'getpeername', 'getsockname', 'getsockopt', 'setsockopt',
              'makefile', 'get_app_data', 'set_app_data', 'state_string',
              'sock_shutdown', 'get_peer_certificate', 'want_read',
              'want_write', 'set_connect_state', 'set_accept_state',
              'connect_ex', 'sendall', 'do_handshake', 'settimeout'):
        exec """def %s(self, *args):
            self._lock.acquire()
            try:
                return apply(self._ssl_conn.%s, args)
            finally:
                self._lock.release()\n""" % (f, f)

