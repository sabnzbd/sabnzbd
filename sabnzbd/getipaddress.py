#!/usr/bin/python -OO
# Copyright 2008-2016 The SABnzbd-Team <team@sabnzbd.org>
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


def localipv4():
    try:
        s_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_ipv4.connect(('1.2.3.4', 80))    # Option: use 100.64.1.1 (IANA-Reserved IPv4 Prefix for Shared Address Space)
        ipv4 = s_ipv4.getsockname()[0]
        s_ipv4.close()
    except:
        ipv4 = None
        pass
    return ipv4

def publicipv4():
    try:
        import urllib2
        req = urllib2.Request("http://" + sabnzbd.cfg.selftest_host(), headers={'User-Agent': 'SABnzbd+/%s' % sabnzbd.version.__version__}) 
        f = urllib2.urlopen(req, timeout=2)    # timeout 2 seconds, in case website is not accessible
        public_ipv4 = f.read()
        socket.inet_aton(public_ipv4)  # if we got anything else than a plain IPv4 address, this will raise an exception
    except:
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
