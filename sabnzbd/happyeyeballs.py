#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.happyeyeballs - Python implementation of RFC 6555 / Happy Eyeballs: find the quickest IPv4/IPv6 connection
"""

# Python implementation of RFC 6555 / Happy Eyeballs: find the quickest IPv4/IPv6 connection
# See https://tools.ietf.org/html/rfc6555
# Method: Start parallel sessions using threads, and only wait for the quickest successful socket connect
# See https://tools.ietf.org/html/rfc6555#section-4.1
# We do not implement caching, as this is handled by the SABnzbd calling code

import socket
import threading
import time
import logging
import queue
from typing import NamedTuple, Tuple, Union, Optional

from sabnzbd import cfg as cfg

IP4_DELAY = 0.1


# For typing and convenience!
class AddrInfo(NamedTuple):
    family: socket.AddressFamily
    type: socket.SocketKind
    proto: int
    canonname: str
    sockaddr: Union[Tuple[str, int], Tuple[str, int, int, int]]


# Called by each thread
def do_socket_connect(result_queue: queue.Queue, addrinfo: AddrInfo):
    """Connect to the ip, and put the result into the queue"""
    try:
        s = socket.socket(addrinfo.family, addrinfo.type)
        s.settimeout(3)

        # Delay IPv4 connects in case we need it
        if addrinfo.family == socket.AddressFamily.AF_INET:
            time.sleep(IP4_DELAY)

        try:
            s.connect(addrinfo.sockaddr)
        finally:
            s.close()
        result_queue.put((addrinfo, True))
    except:
        # We got an exception, so no successful connect on IP & port:
        result_queue.put((addrinfo, False))


def happyeyeballs(host: str, port: int) -> Optional[AddrInfo]:
    """Return the fastest result of getaddrinfo()
    based on RFC 6555 / Happy Eyeballs,
    including IPv6 addresses if desired"""
    try:
        # Time how long it took us
        start = time.time()

        # Get address information, by default IPV4 or IPV6
        family = socket.AF_UNSPEC
        if not cfg.ipv6_servers():
            # Only IPv4
            family = socket.AF_INET
        all_addrinfo = socket.getaddrinfo(host, port, family, socket.SOCK_STREAM, flags=socket.AI_CANONNAME)

        # Convert to AddrInfo
        all_addrinfo = [AddrInfo(*addrinfo) for addrinfo in all_addrinfo]

        # Fill queue used for threads giving back the results
        result_queue: queue.Queue[Tuple[AddrInfo, bool]] = queue.Queue()
        for addrinfo in all_addrinfo:
            threading.Thread(target=do_socket_connect, args=(result_queue, addrinfo), daemon=True).start()

        # start reading from the Queue for message from the threads:
        result = None
        for _ in range(len(all_addrinfo)):
            connect_result = result_queue.get()
            if connect_result[1]:
                result = connect_result[0]
                break

        logging.info("Quickest IP address for %s (port=%s) is %s", host, port, result.sockaddr[0])
        logging.debug("Happy Eyeballs lookup and port connect took %s ms", int(1000 * (time.time() - start)))
        return result
    except Exception as e:
        logging.debug("Failed Happy Eyeballs lookup: %s", e)
        return None
