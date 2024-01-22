#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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

# Python implementation of RFC 6555/8305 (Happy Eyeballs): find the quickest IPv4/IPv6 connection
# See https://tools.ietf.org/html/rfc6555
# See https://tools.ietf.org/html/rfc8305

import socket
import threading
import time
import logging
import queue
import functools
from dataclasses import dataclass
from typing import Tuple, Union, Optional
from more_itertools import roundrobin

from sabnzbd.constants import DEF_TIMEOUT
from sabnzbd.decorators import cache_maintainer

# How long to delay between connection attempts? The RFC suggests 250ms, but this is
# quite long and might give us a slow host that just happened to be on top of the list.
# The absolute minium specified in RFC 8305 is 10ms, so we use that.
CONNECTION_ATTEMPT_DELAY = 0.01


# For typing and convenience!
@dataclass
class AddrInfo:
    family: socket.AddressFamily
    type: socket.SocketKind
    proto: int
    canonname: str
    sockaddr: Union[Tuple[str, int], Tuple[str, int, int, int]]
    ipaddress: str = ""

    def __post_init__(self):
        # For easy access
        self.ipaddress = self.sockaddr[0]


def family_type(family) -> str:
    """Human-readable socket type"""
    if family not in (socket.AF_INET, socket.AF_INET6, socket.AF_UNSPEC):
        raise ValueError("Invalid family")
    if family == socket.AF_INET:
        return "IPv4-only"
    elif family == socket.AF_INET6:
        return "IPv6-only"
    return "IPv4 or IPv6"


# Called by each thread
def do_socket_connect(result_queue: queue.Queue, addrinfo: AddrInfo, timeout: int):
    """Connect to the ip, and put the result into the queue"""
    try:
        start = time.time()
        s = socket.socket(addrinfo.family, addrinfo.type)
        s.settimeout(timeout)
        try:
            s.connect(addrinfo.sockaddr)
            result_queue.put(addrinfo)
            logging.debug(
                "Happy Eyeballs connected to %s (%s) in %dms",
                addrinfo.ipaddress,
                addrinfo.canonname,
                1000 * (time.time() - start),
            )
        except socket.error:
            logging.debug(
                "Happy Eyeballs failed to connect to %s (%s) in %dms",
                addrinfo.ipaddress,
                addrinfo.canonname,
                1000 * (time.time() - start),
            )
        finally:
            s.close()
    except:
        pass


@cache_maintainer(clear_time=10)
@functools.lru_cache(maxsize=None)
def happyeyeballs(host: str, port: int, timeout: int = DEF_TIMEOUT, family=socket.AF_UNSPEC) -> Optional[AddrInfo]:
    """Return the fastest result of getaddrinfo() based on RFC 6555/8305 (Happy Eyeballs),
    including IPv6 addresses if desired. Returns None in case no addresses were returned
    by getaddrinfo or if no connection could be made to any of the addresses.
    If family is specified, only that family is tried"""
    try:
        ipv4_addrinfo = []
        ipv6_addrinfo = []
        last_canonname = ""

        try:
            for addrinfo in socket.getaddrinfo(host, port, family, socket.SOCK_STREAM, flags=socket.AI_CANONNAME):
                # Convert to AddrInfo
                addrinfo = AddrInfo(*addrinfo)

                # The canonname is only reported once per alias
                if addrinfo.canonname:
                    last_canonname = addrinfo.canonname
                elif last_canonname:
                    addrinfo.canonname = last_canonname

                # Put it in the right list for further processing
                # But prevent adding duplicate items to the lists
                if addrinfo not in ipv6_addrinfo and addrinfo not in ipv4_addrinfo:
                    if addrinfo.family == socket.AddressFamily.AF_INET6:
                        ipv6_addrinfo.append(addrinfo)
                    else:
                        ipv4_addrinfo.append(addrinfo)
        except:
            # Did we fail on the first getaddrinfo already?
            # Otherwise, we failed on the IPv6 alternative address, and those failures can be ignored
            if not ipv4_addrinfo and not ipv6_addrinfo:
                raise

        logging.debug(
            "Available addresses for %s (port=%d, %s): %d IPv4 and %d IPv6",
            host,
            port,
            family_type(family),
            len(ipv4_addrinfo),
            len(ipv6_addrinfo),
        )

        # To optimize success, the RFC states to alternate between trying the
        # IPv6 and IPv4 results, starting with IPv6 since it is the preferred method.
        result_queue: queue.Queue[AddrInfo] = queue.Queue()
        addr_tried = 0
        result: Optional[AddrInfo] = None
        for addrinfo in roundrobin(ipv6_addrinfo, ipv4_addrinfo):
            threading.Thread(target=do_socket_connect, args=(result_queue, addrinfo, timeout), daemon=True).start()
            addr_tried += 1
            try:
                result = result_queue.get(timeout=CONNECTION_ATTEMPT_DELAY)
                break
            except queue.Empty:
                # Start a thread for the next address in the list if the previous
                # connection attempt did not complete in time or if it wasn't a success
                continue

        # If we had no results, we might just need to give it more time
        if not result:
            try:
                # Reduce waiting time by time already spent
                result = result_queue.get(timeout=timeout - addr_tried * CONNECTION_ATTEMPT_DELAY)
            except queue.Empty:
                raise ConnectionError("No addresses could be resolved")

        logging.info(
            "Quickest IP address for %s (port=%d, %s): %s (%s)",
            host,
            port,
            family_type(family),
            result.ipaddress,
            result.canonname,
        )
        return result
    except Exception as e:
        logging.debug("Failed Happy Eyeballs lookup: %s", e)
        return None
