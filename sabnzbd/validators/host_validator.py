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
sabnzbd.validators.host_validator - Host and IP address validation utilities
"""

import ipaddress
import socket
from typing import Optional, Tuple

from sabnzbd.validators import StringValidator, ValidateResult


class HostValidator(StringValidator):
    """Validate host names and IP addresses"""

    def validate(self, value: str) -> ValidateResult:
        """Check if host is valid: an IP address, or a name/FQDN that resolves to an IP address"""
        # Easy: value is a plain IPv4 or IPv6 address
        try:
            ipaddress.ip_address(value)
            return None, value
        except Exception:
            pass

        # We don't want a plain number. As socket.getaddrinfo("100", ...) allows that, we have to pre-check
        if value.isdigit():
            return T("Invalid hostname: %s") % value, None

        # Not a plain IPv4 nor IPv6 address, so let's check if it's a name that resolves to IPv4
        try:
            socket.getaddrinfo(value, None, socket.AF_INET)
            return None, value
        except Exception:
            pass

        # ... and if not: does it resolve to IPv6 ... ?
        try:
            socket.getaddrinfo(value, None, socket.AF_INET6)
            return None, value
        except Exception:
            pass

        # If we get here, it is not valid host, so return None
        return T("Invalid hostname: %s") % value, None


# Convenience instance for common usage
host_validator = HostValidator()


__all__ = [
    "HostValidator",
    "host_validator",
]
