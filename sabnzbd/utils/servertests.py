#!/usr/bin/python -OO
# Copyright 2007-2018 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.utils.servertests - Debugging server connections. Currently only NNTP server tests are done.
"""

import socket
import sys
import select

from sabnzbd.newswrapper import NewsWrapper
from sabnzbd.downloader import Server, clues_login, clues_too_many, nntp_to_msg
from sabnzbd.config import get_servers
from sabnzbd.misc import int_conv


def test_nntp_server_dict(kwargs):
    # Grab the host/port/user/pass/connections/ssl
    host = kwargs.get('host', '').strip()
    if not host:
        return False, T('The hostname is not set.')
    username = kwargs.get('username', '').strip()
    password = kwargs.get('password', '').strip()
    server = kwargs.get('server', '').strip()
    connections = int_conv(kwargs.get('connections', 0))
    if not connections:
        return False, T('There are no connections set. Please set at least one connection.')
    ssl = int_conv(kwargs.get('ssl', 0))
    ssl_verify = int_conv(kwargs.get('ssl_verify', 1))
    port = int_conv(kwargs.get('port', 0))
    if not port:
        if ssl:
            port = 563
        else:
            port = 119

    return test_nntp_server(host, port, server, username=username,
                        password=password, ssl=ssl, ssl_verify=ssl_verify)


def test_nntp_server(host, port, server=None, username=None, password=None, ssl=None, ssl_verify=1):
    """ Will connect (blocking) to the nttp server and report back any errors """
    timeout = 4.0
    if '*' in password and not password.strip('*'):
        # If the password is masked, try retrieving it from the config
        if not server:
            servers = get_servers()
            got_pass = False
            for server in servers:
                if host in servers[server].host():
                    srv = servers[server]
                    password = srv.password()
                    got_pass = True
        else:
            srv = get_servers().get(server)
            if srv:
                password = srv.password()
                got_pass = True
        if not got_pass:
            return False, T('Password masked in ******, please re-enter')
    try:
        s = Server(-1, '', host, port, timeout, 0, 0, ssl, ssl_verify, None, False, username, password)
    except:
        return False, T('Invalid server details')

    try:
        nw = NewsWrapper(s, -1, block=True)
        nw.init_connect(None)
        while not nw.connected:
            nw.clear_data()
            nw.recv_chunk(block=True)
            #more ssl related: handle 1/n-1 splitting to prevent Rizzo/Duong-Beast
            read_sockets, _, _ = select.select([nw.nntp.sock], [], [], 0.1)
            if read_sockets:
                nw.recv_chunk(block=True)
            nw.finish_connect(nw.status_code)

    except socket.timeout as e:
        if port != 119 and not ssl:
            return False, T('Timed out: Try enabling SSL or connecting on a different port.')
        else:
            return False, T('Timed out')

    except socket.error as e:
        # Trying SSL on non-SSL port?
        if 'unknown protocol' in str(e).lower():
            return False, T('Unknown SSL protocol: Try disabling SSL or connecting on a different port.')

        return False, str(e)

    except TypeError as e:
        return False, T('Invalid server address.')

    except IndexError:
        # No data was received in recv_chunk() call
        return False, T('Server quit during login sequence.')

    except:
        return False, str(sys.exc_info()[1])

    if not username or not password:
        nw.nntp.sock.sendall(b'ARTICLE <test@home>\r\n')
        try:
            nw.clear_data()
            nw.recv_chunk(block=True)
        except:
            # Some internal error, not always safe to close connection
            return False, str(sys.exc_info()[1])

    # Close the connection
    nw.terminate(quit=True)

    if nw.status_code == 480:
        return False, T('Server requires username and password.')

    elif nw.status_code == 100 or str(nw.status_code).startswith(('2', '4')):
        return True, T('Connection Successful!')

    elif nw.status_code == 502 or clues_login(nntp_to_msg(nw.data)):
        return False, T('Authentication failed, check username/password.')

    elif clues_too_many(nw.lines[0]):
        return False, T('Too many connections, please pause downloading or try again later')

    else:
        return False, T('Could not determine connection result (%s)') % nntp_to_msg(nw.data)

