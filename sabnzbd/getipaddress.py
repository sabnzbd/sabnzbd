#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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

import socket
import multiprocessing.pool
import functools
import urllib.request
import urllib.error
import socks
import logging
import time
from typing import Callable

import sabnzbd
import sabnzbd.cfg
from sabnzbd.encoding import ubtou


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


def localipv4():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s_ipv4:
            # Option: use 100.64.1.1 (IANA-Reserved IPv4 Prefix for Shared Address Space)
            s_ipv4.connect(("10.255.255.255", 80))
            ipv4 = s_ipv4.getsockname()[0]
    except socket.error:
        ipv4 = None

    logging.debug("Local IPv4 address = %s", ipv4)
    return ipv4


def publicipv4():
    """Because of dual IPv4/IPv6 clients, finding the
    public ipv4 needs special attention, meaning forcing
    IPv4 connections, and not allowing IPv6 connections
    Function uses sabnzbd.cfg.selftest_host(), which must report our public IPv4 address over which we access it
    """
    start = time.time()
    try:
        # look up IPv4 addresses of selftest_host
        lookup_result_iv4 = addresslookup4(sabnzbd.cfg.selftest_host())

        # Make sure there is a result, abort otherwise
        if not lookup_result_iv4:
            raise Exception
    except Exception:
        # something very bad: no name resolving of selftest_host
        logging.debug("Failed to detect public IPv4 address: looking up %s failed", sabnzbd.cfg.selftest_host())
        return None

    public_ipv4 = None
    # we got one or more IPv4 address(es) for selftest_host, so let's connect and ask for our own public IPv4
    for item in lookup_result_iv4:
        # get next IPv4 address of sabnzbd.cfg.selftest_host()
        selftest_ipv4 = item[4][0]
        try:
            # put the selftest_host's IPv4 address into the URL
            req = urllib.request.Request("http://" + selftest_ipv4 + "/")
            # specify the User-Agent, because certain sites refuse connections with "python urllib2" as User-Agent:
            req.add_header("User-Agent", "SABnzbd/%s" % sabnzbd.__version__)
            # specify the Host, because we only provide the IPv4 address in the URL:
            req.add_header("Host", sabnzbd.cfg.selftest_host())
            # get the response, timeout 2 seconds, in case the website is not accessible
            public_ipv4 = ubtou(urllib.request.urlopen(req, timeout=2).read())
            # ... check the response is indeed an IPv4 address:
            # if we got anything else than a plain IPv4 address, this will raise an exception
            socket.inet_aton(public_ipv4)
            # if we get here without exception, we found our public IPv4, and we're done:
            break
        except (socket.error, urllib.error.URLError):
            # the connect OR the inet_aton raised an exception, so:
            public_ipv4 = None  # reset
            # continue the for loop to try next server IPv4 address
            pass

    if not public_ipv4:
        logging.debug("Failed to get public IPv4 address from %s", sabnzbd.cfg.selftest_host())
        return None

    logging.debug("Public IPv4 address = %s (in %.2f seconds)", public_ipv4, time.time() - start)
    return public_ipv4


def ipv6():
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s_ipv6:
            # IPv6 prefix for documentation purpose
            s_ipv6.connect(("2001:db8::8080", 80))
            ipv6_address = s_ipv6.getsockname()[0]
    except:
        ipv6_address = None

    logging.debug("IPv6 address = %s", ipv6_address)
    return ipv6_address
