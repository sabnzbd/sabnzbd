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
sabnzbd.getipaddress
"""

import functools
import logging
import socket
import time
import urllib.error
import urllib.request
from typing import Callable

import socks

import sabnzbd
import sabnzbd.cfg
from sabnzbd.encoding import ubtou
from sabnzbd.happyeyeballs import happyeyeballs, family_type


def timeout(max_timeout: float):
    """Timeout decorator, parameter in seconds."""

    def timeout_decorator(item: Callable) -> Callable:
        """Wrap the original function."""

        @functools.wraps(item)
        def func_wrapper(*args, **kwargs):
            """Closure for function."""
            # Raises a TimeoutError if execution exceeds max_timeout
            # Raises a RuntimeError is SABnzbd is already shutting down when called
            try:
                return sabnzbd.THREAD_POOL.submit(item, *args, **kwargs).result(max_timeout)
            except (TimeoutError, RuntimeError):
                return None

        return func_wrapper

    return timeout_decorator


@timeout(3.0)
def addresslookup(myhost):
    return socket.getaddrinfo(myhost, 80)


@timeout(3.0)
def addresslookup4(myhost):
    return socket.getaddrinfo(myhost, 80, socket.AF_INET)


@timeout(3.0)
def addresslookup6(myhost):
    return socket.getaddrinfo(myhost, 80, socket.AF_INET6)


def active_socks5_proxy():
    """Return the active proxy"""
    if socket.socket == socks.socksocket:
        return "%s:%s" % socks.socksocket.default_proxy[1:3]
    return None


def dnslookup():
    """Perform a basic DNS lookup"""
    start = time.time()
    try:
        addresslookup(sabnzbd.cfg.selftest_host())
        result = True
    except:
        result = False
    logging.debug("DNS Lookup = %s (in %.2f seconds)", result, time.time() - start)
    return result


def local_ipv4():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s_ipv4:
            # Option: use 100.64.1.1 (IANA-Reserved IPv4 Prefix for Shared Address Space)
            s_ipv4.connect(("10.255.255.255", 80))
            ipv4 = s_ipv4.getsockname()[0]
    except socket.error:
        ipv4 = None

    logging.debug("Local IPv4 address = %s", ipv4)
    return ipv4


def public_ip(family=socket.AF_UNSPEC):
    """
    Reports the client's public IP address (IPv4 or IPv6, if specified by family), as reported by selftest host
    """
    start = time.time()
    if resolvehostaddress := happyeyeballs(sabnzbd.cfg.selftest_host(), port=443, family=family):
        resolvehostip = resolvehostaddress.ipaddress
    else:
        logging.debug("Error resolving my IP address: resolvehost not found")
        return None

    if sabnzbd.misc.is_ipv4_addr(resolvehostip):
        resolveurl = f"http://{resolvehostip}/?ipv4test"
    elif sabnzbd.misc.is_ipv6_addr(resolvehostip):
        resolveurl = f"http://[{resolvehostip}]/?ipv6test"  # including square brackets
    else:
        logging.debug("Error resolving my IP address: got no valid IPv4 nor IPv6 address")
        return None

    try:
        req = urllib.request.Request(resolveurl)
        req.add_header("Host", sabnzbd.cfg.selftest_host())
        req.add_header("User-Agent", "SABnzbd/%s" % sabnzbd.__version__)
        with urllib.request.urlopen(req, timeout=2) as open_req:
            client_ip = ubtou(open_req.read().strip())

        # Make sure it's a valid IPv4 or IPv6 address
        if not sabnzbd.misc.is_ipv4_addr(client_ip) and not sabnzbd.misc.is_ipv6_addr(client_ip):
            raise ValueError
    except urllib.error.URLError:
        logging.debug("Failed to get public address from %s (%s)", sabnzbd.cfg.selftest_host(), family_type(family))
        return None

    logging.debug("Public address %s = %s (in %.2f seconds)", family_type(family), client_ip, time.time() - start)
    return client_ip


def public_ipv4():
    return public_ip(family=socket.AF_INET)


def local_ipv6():
    """
    return IPv6 address on local LAN interface. So a first check if there is IPv6 connectivity
    """
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s_ipv6:
            # IPv6 prefix for documentation purpose
            s_ipv6.connect(("2001:db8::8080", 80))
            ipv6_address = s_ipv6.getsockname()[0]
    except:
        ipv6_address = None

    logging.debug("IPv6 address = %s", ipv6_address)
    return ipv6_address


def public_ipv6():
    if local_ipv6():
        return public_ip(family=socket.AF_INET6)
