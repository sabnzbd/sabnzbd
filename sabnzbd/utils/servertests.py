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

from sabnzbd.constants import DEF_TIMEOUT
from sabnzbd.newswrapper import NewsWrapper, NNTPPermanentError
from sabnzbd.downloader import Server, clues_login, clues_too_many
from sabnzbd.config import get_servers
from sabnzbd.misc import int_conv, match_str


def test_nntp_server_dict(kwargs):
    """Will connect (blocking) to the NNTP server and report back any errors"""
    host = kwargs.get("host", "").strip()
    port = int_conv(kwargs.get("port", 0))
    username = kwargs.get("username", "").strip()
    password = kwargs.get("password", "").strip()
    server = kwargs.get("server", "").strip()
    connections = int_conv(kwargs.get("connections", 0))
    timeout = int_conv(kwargs.get("timeout", DEF_TIMEOUT))
    ssl = int_conv(kwargs.get("ssl", 0))
    ssl_verify = int_conv(kwargs.get("ssl_verify", 1))
    ssl_ciphers = kwargs.get("ssl_ciphers", "").strip()

    if not host:
        return False, T("The hostname is not set.")

    if not connections:
        return False, T("There are no connections set. Please set at least one connection.")

    if not port:
        if ssl:
            port = 563
        else:
            port = 119

    if not timeout:
        # Lower value during new server testing
        timeout = 10

    if "*" in password and not password.strip("*"):
        # If the password is masked, try retrieving it from the config
        srv = get_servers().get(server)
        if srv:
            password = srv.password()
        else:
            return False, T("Password masked in ******, please re-enter")

    try:
        s = Server(
            server_id=-1,
            displayname="",
            host=host,
            port=port,
            timeout=timeout,
            threads=0,
            priority=0,
            use_ssl=ssl,
            ssl_verify=ssl_verify,
            ssl_ciphers=ssl_ciphers,
            send_group=False,
            username=username,
            password=password,
        )
    except:
        return False, T("Invalid server details")

    try:
        nw = NewsWrapper(server=s, thrdnum=-1, block=True)
        nw.init_connect()
        while not nw.connected:
            nw.reset_data_buffer()
            nw.recv_chunk()
            nw.finish_connect(nw.status_code)

    except socket.timeout:
        if port != 119 and not ssl:
            return False, T("Timed out: Try enabling SSL or connecting on a different port.")
        else:
            return False, T("Timed out")

    except socket.error as err:
        # Trying SSL on non-SSL port?
        if match_str(str(err), ("unknown protocol", "wrong version number")):
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
            nw.reset_data_buffer()
            nw.recv_chunk()
        except:
            # Some internal error, not always safe to close connection
            return False, str(sys.exc_info()[1])

    # Parse result
    return_status = ()
    if nw.status_code:
        if nw.status_code == 480:
            return_status = (False, T("Server requires username and password."))
        elif nw.status_code < 300 or nw.status_code in (411, 423, 430):
            # If no username/password set and we requested fake-article, it will return 430 Not Found
            return_status = (True, T("Connection Successful!"))
        elif nw.status_code == 502 or clues_login(nw.nntp_msg):
            return_status = (False, T("Authentication failed, check username/password."))
        elif clues_too_many(nw.nntp_msg):
            return_status = (False, T("Too many connections, please pause downloading or try again later"))

    # Fallback in case no data was received or unknown status
    if not return_status:
        return_status = (False, T("Could not determine connection result (%s)") % nw.nntp_msg)

    # Close the connection and return result
    nw.hard_reset(send_quit=True)
    return return_status
