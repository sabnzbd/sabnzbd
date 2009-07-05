#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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
from time import time
import logging

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.lang import T

try:
    from OpenSSL import SSL
    _ssl = SSL
    del SSL
    HAVE_SSL = True

except ImportError:
    _ssl = None
    HAVE_SSL = False

import threading
_RLock = threading.RLock
del threading

import select
import os


socket.setdefaulttimeout(DEF_TIMEOUT)

def GetServerParms(host, port):
    # Make sure port is numeric (unicode input not supported)
    try:
        int(port)
    except:
        # Could do with a warning here
        port = 119
    try:
        # Standard IPV4
        return socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except:
        try:
            # Try IPV6 explicitly
            return socket.getaddrinfo(host, port, socket.AF_INET6,
                                      socket.SOCK_STREAM, socket.IPPROTO_IP, socket.AI_CANONNAME)
        except:
            # Nothing found!
            return None


def con(sock, host, port, sslenabled, nntp):
    try:
        sock.connect((host, port))
        sock.setblocking(0)
        if sslenabled and _ssl:
            while True:
                try:
                    sock.do_handshake()
                    break
                except _ssl.WantReadError:
                    select.select([sock], [], [], 1.0)
    except socket.error, e:
        try:
            if isinstance(e, tuple):
                (_errno, strerror) = e
            else:
                (_errno, strerror) = (errno.ETIMEDOUT, str(e))
                e = (_errno, strerror)
            #expected, do nothing
            if _errno == errno.EINPROGRESS:
                pass
        finally:
            nntp.error(e)

    except _ssl.Error, e:
        nntp.error(e)

class NNTP:
    def __init__(self, host, port, sslenabled, nntp, user=None, password=None, block=False):
        self.host = host
        self.port = port
        self.nntp = nntp
        self.blocking = block
        self.error_msg = None
        res= GetServerParms(self.host, self.port)
        if not res:
            raise socket.error(errno.EADDRNOTAVAIL, "Address not available - Check for internet or DNS problems")

        af, socktype, proto, canonname, sa = res[0]

        if sslenabled and _ssl:
            ctx = _ssl.Context(_ssl.SSLv23_METHOD)
            self.sock = SSLConnection(ctx, socket.socket(af, socktype, proto))
        elif sslenabled and not _ssl:
            logging.error(T('error-noSSL'))
            self.sock = socket.socket(af, socktype, proto)
        else:
            self.sock = socket.socket(af, socktype, proto)

        try:
            # Windows must do the connection in a seperate thread due to non-blocking issues
            # If the server wants to be blocked (for testing) then use the linux route
            if sabnzbd.WIN32 and not block:
                Thread(target=con, args=(self.sock, self.host, self.port, sslenabled, self)).start()
            else:
                self.sock.connect((self.host, self.port))
                if not block:
                    self.sock.setblocking(0)
                if sslenabled and _ssl:
                    while True:
                        try:
                            self.sock.do_handshake()
                            break
                        except _ssl.WantReadError:
                            select.select([self.sock], [], [], 1.0)

        except socket.error, e:
            try:
                (_errno, strerror) = e
                #expected, do nothing
                if _errno == errno.EINPROGRESS:
                    pass
            finally:
                self.error(e)

        except _ssl.Error, e:
            self.error(e)

    def error(self, error):
        if 'SSL23_GET_SERVER_HELLO' in str(error):
            error = 'This server does not allow SSL on this port'
        msg = "Failed to connect: %s" % (str(error))
        msg = "%s %s@%s:%s" % (msg, self.nntp.thrdnum, self.host, self.port)
        self.error_msg = msg
        if self.blocking:
            raise socket.error(errno.ECONNREFUSED, msg)
        else:
            logging.error(msg)

class NewsWrapper:
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

    def init_connect(self):
        self.nntp = NNTP(self.server.host, self.server.port, self.server.ssl, self,
                         self.server.username, self.server.password, self.blocking)
        self.recv = self.nntp.sock.recv

        self.timeout = time() + self.server.timeout

    def finish_connect(self):
        if not self.server.username or not self.server.password:
            self.connected = True
            self.user_sent = True
            self.user_ok = True
            self.pass_sent = True
            self.pass_ok = True

        if self.lines and self.lines[0][:3] == '400':
            raise NNTPPermanentError(self.lines[0])
        elif not self.user_sent:
            command = 'authinfo user %s\r\n' % (self.server.username)
            self.nntp.sock.sendall(command)
            self.user_sent = True
        elif not self.user_ok:
            if self.lines[0][:3] == '381':
                self.user_ok = True

        if self.user_ok and not self.pass_sent:
            command = 'authinfo pass %s\r\n' % (self.server.password)
            self.nntp.sock.sendall(command)
            self.pass_sent = True
        elif self.user_ok and not self.pass_ok:
            if self.lines[0][:3] != '281':
                # Assume that login failed (code 481 or other)
                raise NNTPPermanentError(self.lines[0])
            else:
                self.connected = True

        self.timeout = time() + self.server.timeout

    def body(self):
        self.timeout = time() + self.server.timeout
        command = 'BODY <%s>\r\n' % (self.article.article)
        self.nntp.sock.sendall(command)

    def send_group(self, group):
        self.timeout = time() + self.server.timeout
        command = 'GROUP %s\r\n' % (group)
        self.nntp.sock.sendall(command)

    def recv_chunk(self, block=False):
        self.timeout = time() + self.server.timeout
        while 1:
            try:
                chunk = self.recv(32768)
                break
            except _ssl.WantReadError:
                # SSL connections will block until they are ready.
                # Either ignore the connection until it responds
                # Or wait in a loop until it responds
                if block:
                    #time.sleep(0.0001)
                    continue
                else:
                    return (0, False, True)

        self.data += chunk
        new_lines = self.data.split('\r\n')

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

    def hard_reset(self, wait=True):
        if self.nntp:
            try:
                self.nntp.sock.sendall('QUIT\r\n')
                time.sleep(0.1)
                self.nntp.sock.close()
            except:
                pass

        self.__init__(self.server, self.thrdnum)

        # Wait before re-using this newswrapper
        if wait:
            # Reset due to error condition, use server timeout
            self.timeout = time() + self.server.timeout
        else:
            # Reset for internal reasons, just wait 5 sec
            self.timeout = time() + 5

    def terminate(self):
        """ Close connection and remove nntp object """
        if self.nntp:
            try:
                self.nntp.sock.sendall('QUIT\r\n')
                time.sleep(0.1)
                self.nntp.sock.close()
            except:
                pass
        del self.nntp


class SSLConnection:
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
              'connect_ex', 'sendall', 'do_handshake'):
        exec """def %s(self, *args):
            self._lock.acquire()
            try:
                return apply(self._ssl_conn.%s, args)
            finally:
                self._lock.release()\n""" % (f, f)
