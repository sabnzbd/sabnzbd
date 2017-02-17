#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
import sabnzbd
import sabnzbd.cfg
import multiprocessing.pool
import functools


# decorator stuff:
def timeout(max_timeout):
    """Timeout decorator, parameter in seconds."""
    def timeout_decorator(item):
        """Wrap the original function."""
        @functools.wraps(item)
        def func_wrapper(*args, **kwargs):
            """Closure for function."""
            pool = multiprocessing.pool.ThreadPool(processes=1)
            async_result = pool.apply_async(item, args, kwargs)
            # raises a TimeoutError if execution exceeds max_timeout
            return async_result.get(max_timeout)
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


def localipv4():
    try:
        s_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_ipv4.connect(('1.2.3.4', 80))    # Option: use 100.64.1.1 (IANA-Reserved IPv4 Prefix for Shared Address Space)
        ipv4 = s_ipv4.getsockname()[0]
        s_ipv4.close()
    except:
        ipv4 = None
    return ipv4


def publicipv4():
    # Because of dual IPv4/IPv6 clients, finding the public ipv4 needs special attention,
    # meaning forcing IPv4 connections, and not allowing IPv6 connections
    try:
        import urllib2
        ipv4_found = False
        # we only want IPv4 resolving, so socket.AF_INET:
        result = addresslookup4(sabnzbd.cfg.selftest_host())
    except:
    # something very bad: no urllib2, no resolving of selftest_host, no network at all
        public_ipv4 = None
        return public_ipv4
    # we got one or more IPv4 address(es), so let's connect to them
    for item in result:
        selftest_ipv4 = item[4][0]     # get next IPv4 address of sabnzbd.cfg.selftest_host()
        try:
            # put the selftest_host's IPv4 address into the URL
            req = urllib2.Request("http://" + selftest_ipv4 + "/")
            # specify the User-Agent, because certain sites refuse connections with "python urllib2" as User-Agent:
            req.add_header('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__ )
            # specify the Host, because we only provide the IPv4 address in the URL:
            req.add_header('Host', sabnzbd.cfg.selftest_host())
            # get the response
            public_ipv4 = urllib2.urlopen(req, timeout=2).read()  # timeout 2 seconds, in case the website is not accessible
            # ... check the response is indeed an IPv4 address:
            socket.inet_aton(public_ipv4)  # if we got anything else than a plain IPv4 address, this will raise an exception
            # if we get here without exception, we're done:
            ipv4_found = True
            break
        except:
            # the connect OR the inet_aton raised an exception, so:
            # continue the for loop to try next server IPv4 address
            pass
    if not ipv4_found:
        public_ipv4 = None
    return public_ipv4


def ipv6():
    try:
        s_ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s_ipv6.connect(('2001:db8::8080', 80))    # IPv6 prefix for documentation purpose
        ipv6 = s_ipv6.getsockname()[0]
        s_ipv6.close()
    except:
        ipv6 = None
    return ipv6
