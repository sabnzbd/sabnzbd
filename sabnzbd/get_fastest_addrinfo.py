#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.get_fastest_addrinfo - Concurrent IP address testing: find the fastest IPv4/IPv6 connection
"""

import socket
import threading
import time
import logging
import functools
from dataclasses import dataclass
from more_itertools import roundrobin
from typing import Tuple, Union, Optional

import sabnzbd.cfg as cfg
from sabnzbd.constants import DEF_NETWORKING_TIMEOUT
from sabnzbd.decorators import conditional_cache

# How often to check for connection results
CONNECTION_RESULT_CHECK = 0.1  # 100ms

# While providers are afraid to add IPv6 to their standard hostnames
# we map a number of well known hostnames to their IPv6 alternatives.
# WARNING: Only add if the SSL-certificate allows both hostnames!
IPV6_MAPPING = {
    "news.eweka.nl": "news6.eweka.nl",
    "news.xlned.com": "news6.xlned.com",
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
    port: int = 0
    connection_time: float = 0.0

    def __post_init__(self):
        # For easy access
        self.ipaddress = self.sockaddr[0]
        self.port = self.sockaddr[1]


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
def do_socket_connect(results_list: list, addrinfo: AddrInfo, timeout: int):
    """Connect to the ip, and add the result with timing info to the shared list"""
    try:
        start = time.time()
        s = socket.socket(addrinfo.family, addrinfo.type)
        s.settimeout(timeout)
        try:
            s.connect(addrinfo.sockaddr)
            addrinfo.connection_time = time.time() - start
            results_list.append(addrinfo)
            logging.debug(
                "Connected to %s (%s, port=%d) in %dms",
                addrinfo.ipaddress,
                addrinfo.canonname,
                addrinfo.port,
                1000 * addrinfo.connection_time,
            )
        except socket.error:
            logging.debug(
                "Failed to connect to %s (%s, port=%d) in %dms",
                addrinfo.ipaddress,
                addrinfo.canonname,
                addrinfo.port,
                1000 * (time.time() - start),
            )
        finally:
            s.close()
    except Exception:
        pass


@conditional_cache(cache_time=60)
def get_fastest_addrinfo(
    host: str,
    port: int,
    timeout: int = DEF_NETWORKING_TIMEOUT,
    family=socket.AF_UNSPEC,
) -> Optional[AddrInfo]:
    """Return the fastest result of getaddrinfo() by testing all IP addresses concurrently.
    Tests all available IP addresses simultaneously (alternating IPv4/6) in separate threads and returns the
    connection with the shortest response time after CONNECTION_CHECK interval.
    Returns None in case no addresses were returned by getaddrinfo or if no connection
    could be made to any of the addresses. If family is specified, only that family is tried"""
    try:
        # See if we can add an IPv6 alternative
        check_hosts = [host]
        if cfg.ipv6_staging() and host in IPV6_MAPPING:
            check_hosts.append(IPV6_MAPPING[host])
            logging.info("Added IPv6 alternative %s for host %s", IPV6_MAPPING[host], host)

        last_canonname = ""
        ipv4_addrinfo = []
        ipv6_addrinfo = []
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
            except Exception:
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

        if not ipv4_addrinfo and not ipv6_addrinfo:
            raise ConnectionError("No usable IP addresses found for %s" % ", ".join(check_hosts))

        # Try IPv6 and IPv4 alternating since there is delay in starting threads
        successful_connections = []
        threads = []
        for addrinfo in roundrobin(ipv6_addrinfo, ipv4_addrinfo):
            thread = threading.Thread(
                target=do_socket_connect,
                args=(successful_connections, addrinfo, timeout),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        # Wait for the first successful connection
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(CONNECTION_RESULT_CHECK)
            # Check if we have any successful connections
            if successful_connections:
                # Return the fastest connection
                fastest_addrinfo = min(successful_connections, key=lambda result: result.connection_time)
                logging.info(
                    "Fastest connection to %s (port=%d, %s): %s (%s) in %dms (out of %d results)",
                    host,
                    port,
                    family_type(family),
                    fastest_addrinfo.ipaddress,
                    fastest_addrinfo.canonname,
                    1000 * fastest_addrinfo.connection_time,
                    len(successful_connections),
                )
                return fastest_addrinfo

        # If no connections succeeded within timeout
        raise ConnectionError("No usable IP addresses found for %s" % ", ".join(check_hosts))

    except Exception as e:
        logging.debug("Failed IP address lookup: %s", e)
        return None
