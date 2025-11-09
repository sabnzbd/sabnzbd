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
sabnzbd.validators.email_validator - Email validation utilities
"""

from typing import Optional, Tuple, Union

import sabnzbd
from sabnzbd.validators import RE_EMAIL, StringValidator, ValidateResult


class EmailValidator(StringValidator):
    """Validate email addresses"""

    def validate(self, value: Union[str, list]) -> ValidateResult:
        """Validate email address(es)"""
        if (
            sabnzbd.cfg.email_endjob()
            or sabnzbd.cfg.email_full()
            or sabnzbd.cfg.email_rss()
        ):
            if isinstance(value, list):
                values = value
            else:
                values = [value]
            for addr in values:
                if not (addr and RE_EMAIL.match(addr)):
                    return T("%s is not a valid email address") % addr, None
        return None, value


# Convenience instance for common usage
email_validator = EmailValidator()


__all__ = [
    "EmailValidator",
    "email_validator",
]
