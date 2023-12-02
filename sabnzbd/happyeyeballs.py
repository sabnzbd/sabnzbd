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

from sabnzbd import cfg as cfg
from sabnzbd.constants import DEF_TIMEOUT
from sabnzbd.decorators import cache_maintainer

# How long to delay between connection attempts? The RFC suggests 250ms, but this is
# quite long and might give us a slow host that just happened to be on top of the list.
# The absolute minium specified in RFC 8305 is 10ms, so we use that.
CONNECTION_ATTEMPT_DELAY = 0.01

# While providers are afraid to add IPv6 to their standard hostnames
# we map a number of well known hostnames to their IPv6 alternatives.
# WARNING: Only add if the SSL-certificate allows both hostnames!
IPV6_MAPPING = {
    "news.eweka.nl": "news6.eweka.nl",
    "news.xlned.com": "news6.xlned.com",
    "news.usenet.farm": "news6.usenet.farm",
    "news.easynews.com": "news6.easynews.com",
    "news.tweaknews.nl": "news6.tweaknews.nl",
    "news.tweaknews.eu": "news6.tweaknews.eu",
    "news.astraweb.com": "news6.astraweb.com",
    "news.pureusenet.nl": "news6.pureusenet.nl",
    "news.sunnyusenet.com": "news6.sunnyusenet.com",
    "news.newshosting.com": "news6.newshosting.com",
    "news.usenetserver.com": "news6.usenetserver.com",
    "news.frugalusenet.com": "news-v6.frugalusenet.com",
    "eunews.frugalusenet.com": "eunews-v6.frugalusenet.com",
}


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
@functools.cache
def happyeyeballs(host: str, port: int, timeout: int = DEF_TIMEOUT) -> Optional[AddrInfo]:
    """Return the fastest result of getaddrinfo() based on RFC 6555/8305 (Happy Eyeballs),
    including IPv6 addresses if desired. Returns None in case no addresses were returned
    by getaddrinfo or if no connection could be made to any of the addresses"""
    try:
        # Get address information, by default both IPV4 and IPV6
        check_hosts = [host]
        family = socket.AF_UNSPEC
        if not cfg.ipv6_servers():
            family = socket.AF_INET
        elif host in IPV6_MAPPING:
            # See if we can add a IPv6 alternative
            check_hosts.append(IPV6_MAPPING[host])
            logging.info("Added alternative IPv6 address: %s", IPV6_MAPPING[host])

        ipv4_addrinfo = []
        ipv6_addrinfo = []
        last_canonname = ""
        for check_host in check_hosts:
            try:
                for addrinfo in socket.getaddrinfo(
                    check_host, port, family, socket.SOCK_STREAM, flags=socket.AI_CANONNAME
                ):
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
            "Available addresses for %s (port=%d): %d IPv4 and %d IPv6",
            host,
            port,
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

        logging.info("Quickest IP address for %s (port=%d): %s (%s)", host, port, result.ipaddress, result.canonname)
        return result
    except Exception as e:
        logging.debug("Failed Happy Eyeballs lookup: %s", e)
        return None
