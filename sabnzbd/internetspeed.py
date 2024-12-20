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
sabnzbd.internetspeed - Measure internet bandwidth using sabctools routines
"""

import sys
import logging
import socket
import ssl
import time
import threading
from typing import Dict

import sabctools
import sabnzbd
from sabnzbd.constants import DEF_NETWORKING_SHORT_TIMEOUT
from sabnzbd.happyeyeballs import happyeyeballs, family_type

TEST_HOSTNAME = "sabnzbd.org"
TEST_PORT = 443
TEST_FILE = "/tests/internetspeed/100MB.bin"
TEST_FILE_SIZE = 100 * 1024 * 1024
TEST_REQUEST = f"GET {TEST_FILE} HTTP/1.1\nHost: {TEST_HOSTNAME}\nUser-Agent: SABnzbd/{sabnzbd.__version__}\n\n"
BUFFER_SIZE = 5 * 1024 * 1024  # Each connection will allocate its own buffer, so mind the memory usage!

NR_CONNECTIONS = 5
TIME_LIMIT = 3


def internetspeed_worker(secure_sock: ssl.SSLSocket, socket_speed: Dict[ssl.SSLSocket, float]):
    """Worker to perform the requests in parallel"""
    secure_sock.sendall(TEST_REQUEST.encode())
    empty_buffer = memoryview(sabctools.bytearray_malloc(BUFFER_SIZE))

    start_time = time.perf_counter()
    diff_time = 0
    data_received = 0

    while diff_time < TIME_LIMIT:
        if data_received < TEST_FILE_SIZE:
            try:
                if new_bytes := sabctools.unlocked_ssl_recv_into(secure_sock, empty_buffer):
                    # Update the speed after every loop
                    diff_time = time.perf_counter() - start_time
                    data_received += new_bytes
                    socket_speed[secure_sock] = data_received / diff_time
                else:
                    break
            except ssl.SSLWantReadError:
                time.sleep(0)
        else:
            break

    try:
        secure_sock.close()
    except socket.error:
        # In case socket was closed unexpectedly already
        pass


def internetspeed_interal(family: int = socket.AF_UNSPEC) -> float:
    """Measure internet speed from a test-download using our optimized SSL-code"""
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    socket_speed = {}

    # Allow those pesky virus-scanners to inject their scanning certificates
    # This is enabled by default because it's just a speedtest anyway
    if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
        context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    try:
        if not (addrinfo := happyeyeballs(TEST_HOSTNAME, TEST_PORT, DEF_NETWORKING_SHORT_TIMEOUT, family)):
            # no addrinfo from happyeyeballs, so no connection was possible
            return 0.0  # no speed at all

        for _ in range(NR_CONNECTIONS):
            sock = socket.socket(addrinfo.family, addrinfo.type)
            sock.settimeout(DEF_NETWORKING_SHORT_TIMEOUT)
            sock.connect(addrinfo.sockaddr)
            secure_sock = context.wrap_socket(sock, server_hostname=TEST_HOSTNAME)
            secure_sock.setblocking(False)
            socket_speed[secure_sock] = 0

        for secure_sock in socket_speed:
            threading.Thread(
                target=internetspeed_worker,
                args=(secure_sock, socket_speed),
                daemon=True,
            ).start()
    except Exception:
        logging.info("Internet Bandwidth connection failure", exc_info=True)
        return 0.0

    # We let the workers finish
    time.sleep(TIME_LIMIT + 0.5)

    speed = sum(socket_speed.values()) / 1024 / 1024
    logging.debug(
        "Internet Bandwidth (%s) = %.2f MB/s - %.2f Mbps",
        family_type(family),
        speed,
        speed * 8.05,
    )
    return speed


def internetspeed() -> float:
    # Internet bandwidth
    if not sabnzbd.cfg.ipv6_staging():
        # no special IPv6 wishes, so straight Internet speed test (ipv4 / ipv6 agnostic)
        return round(internetspeed_interal(), 2)
    else:
        internetspeed_ipv4 = round(internetspeed_interal(family=socket.AF_INET), 1)
        internetspeed_ipv6 = round(internetspeed_interal(family=socket.AF_INET6), 1)
        if internetspeed_ipv4 > 0 and internetspeed_ipv6 > 0:
            # both working, so let's see if it's about the same speed (good), there is a big difference (bad)
            if 0.5 > (internetspeed_ipv4 / internetspeed_ipv6) > 2:
                sabnzbd.misc.helpful_warning(
                    T(
                        "Internet Bandwidth of IPv4 significantly different from IPv6: %f MB/s versus %f MB/s",
                        internetspeed_ipv4,
                        internetspeed_ipv6,
                    )
                )

        return max(internetspeed_ipv4, internetspeed_ipv6)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    internetspeed()
