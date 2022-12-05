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
sabnzbd.utils.servertests - Debugging server connections. Currently only NNTP server tests are done.
"""

import socket
import sys

from sabnzbd.newswrapper import NewsWrapper, NNTPPermanentError
from sabnzbd.downloader import Server, clues_login, clues_too_many, nntp_to_msg
from sabnzbd.config import get_servers
from sabnzbd.misc import int_conv


def test_nntp_server_dict(kwargs):
    # Grab the host/port/user/pass/connections/ssl
    host = kwargs.get("host", "").strip()
    if not host:
        return False, T("The hostname is not set.")
    username = kwargs.get("username", "").strip()
    password = kwargs.get("password", "").strip()
    server = kwargs.get("server", "").strip()
    connections = int_conv(kwargs.get("connections", 0))
    if not connections:
        return False, T("There are no connections set. Please set at least one connection.")
    ssl = int_conv(kwargs.get("ssl", 0))
    ssl_verify = int_conv(kwargs.get("ssl_verify", 1))
    ssl_ciphers = kwargs.get("ssl_ciphers")
    port = int_conv(kwargs.get("port", 0))

    if not port:
        if ssl:
            port = 563
        else:
            port = 119

    return test_nntp_server(
        host,
        port,
        server,
        username=username,
        password=password,
        ssl=ssl,
        ssl_verify=ssl_verify,
        ssl_ciphers=ssl_ciphers,
    )


def test_nntp_server(host, port, server=None, username=None, password=None, ssl=None, ssl_verify=1, ssl_ciphers=None):
    """Will connect (blocking) to the nttp server and report back any errors"""
    timeout = 4.0
    if "*" in password and not password.strip("*"):
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
            return False, T("Password masked in ******, please re-enter")
    try:
        s = Server(-1, "", host, port, timeout, 0, 0, ssl, ssl_verify, ssl_ciphers, False, username, password)
    except:
        return False, T("Invalid server details")

    try:
        nw = NewsWrapper(s, -1, block=True)
        nw.init_connect()
        while not nw.connected:
            nw.clear_data()
            nw.recv_chunk(block=True)
            nw.finish_connect(nw.status_code)

    except socket.timeout:
        if port != 119 and not ssl:
            return False, T("Timed out: Try enabling SSL or connecting on a different port.")
        else:
            return False, T("Timed out")

    except socket.error as err:
        # Trying SSL on non-SSL port?
        if "unknown protocol" in str(err).lower() or "wrong version number" in str(err).lower():
            return False, T("Unknown SSL protocol: Try disabling SSL or connecting on a different port.")

        return False, str(err)

    except TypeError:
        return False, T("Invalid server address.")

    except IndexError:
        # No data was received in recv_chunk() call
        return False, T("Server quit during login sequence.")

    except NNTPPermanentError:
        # Handled by the code below
        pass

    except Exception as err:
        return False, str(err)

    if not username or not password:
        nw.nntp.sock.sendall(b"ARTICLE <test@home>\r\n")
        try:
            nw.clear_data()
            nw.recv_chunk(block=True)
        except:
            # Some internal error, not always safe to close connection
            return False, str(sys.exc_info()[1])

    if nw.status_code == 480:
        return_status = (False, T("Server requires username and password."))
    elif nw.status_code < 300 or nw.status_code in (411, 423, 430):
        # If no username/password set and we requested fake-article, it will return 430 Not Found
        return_status = (True, T("Connection Successful!"))
    elif nw.status_code == 502 or clues_login(nntp_to_msg(nw.data)):
        return_status = (False, T("Authentication failed, check username/password."))
    elif clues_too_many(nntp_to_msg(nw.data)):
        return_status = (False, T("Too many connections, please pause downloading or try again later"))
    else:
        return_status = (False, T("Could not determine connection result (%s)") % nntp_to_msg(nw.data))

    # Close the connection and return result
    nw.hard_reset(send_quit=True)
    return return_status
