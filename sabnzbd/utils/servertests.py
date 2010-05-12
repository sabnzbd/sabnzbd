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
sabnzbd.utils.servertests - Debugging server connections. Currently only NNTP server tests are done.
"""

import socket
import sys

from sabnzbd.newswrapper import NewsWrapper
from sabnzbd.downloader import Server, clues_login, clues_too_many
from sabnzbd.config import get_servers
from sabnzbd.encoding import xml_name
from sabnzbd.interface import IntConv
from sabnzbd.lang import T

def test_nntp_server_dict(kwargs):
    # Grab the host/port/user/pass/connections/ssl
    host = kwargs.get('host', '').strip()
    if not host:
        return False, T('srv-noHost')
    username = kwargs.get('username', '').strip()
    password = kwargs.get('password', '').strip()
    connections = IntConv(kwargs.get('connections', 0))
    if not connections:
        return False, T('srv-noConnections')
    ssl = IntConv(kwargs.get('ssl', 0))
    port = IntConv(kwargs.get('port', 0))
    if not port:
        if ssl:
            port = 563
        else:
            port = 119


    return test_nntp_server(host, port, username=username, \
                        password=password, ssl=ssl)


def test_nntp_server(host, port, username=None, password=None, ssl=None):
    ''' Will connect (blocking) to the nttp server and report back any errors '''
    timeout = 4.0
    if '*' in password and not password.strip('*'):
        # If the password is masked, try retrieving it from the config
        servers = get_servers()
        got_pass = False
        for server in servers:
            if host in server:
                srv = servers[server]
                password = srv.password()
                got_pass = True
        if not got_pass:
            return False, T('srv-starredPass')
    try:
        s = Server(-1, host, port, timeout, 1, 0, ssl, username, password)
    except:
        return False, T('srv-invalidDetails')

    try:
        nw = NewsWrapper(s, -1, block=True)
        nw.init_connect()
        while not nw.connected:
            nw.lines = []
            nw.recv_chunk(block=True)
            nw.finish_connect('')

    except socket.timeout, e:
        if port != 119 and not ssl:
            return False, T('srv-timedoutSSL')
        else:
            return False, T('srv-timedout')
    except socket.error, e:
        return False, xml_name(str(e))

    except:
        return False, xml_name(str(sys.exc_info()[1]))


    if not username or not password:
        nw.nntp.sock.sendall('ARTICLE test\r\n')
        try:
            nw.lines = []
            nw.recv_chunk(block=True)
        except:
            return False, xml_name(str(sys.exc_info()[1]))

    # Could do with making a function for return codes to be used by downloader
    code = nw.lines[0][:3]

    if code == '480':
        return False, T('srv-noAuth')

    elif code == '100' or code.startswith('2') or code.startswith('4'):
        return True, T('srv-success')

    elif code == '502' or clues_login(nw.lines[0]):
        return False, T('srv-failedAuth')

    elif clues_too_many(nw.lines[0]):
        return False, T('srv-tooManyConnections')

    else:
        return False, T('srv-generalFail@1') % xml_name(nw.lines[0])

    # Close the connection
    nw.terminate(quit=True)
