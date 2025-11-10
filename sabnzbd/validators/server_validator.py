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
sabnzbd.validators.server_validator - Email server address validation utilities
"""

from typing import Optional, Tuple

import sabnzbd
from sabnzbd.validators import StringValidator, ValidateResult


class ServerValidator(StringValidator):
    """Validate email server addresses with conditional requirements"""

    def validate(self, value: str) -> ValidateResult:
        """Check if server non-empty when email notifications are enabled"""
        if value == "" and (self._email_endjob() or self._email_full() or self._email_rss()):
            return T("Server address required"), None
        else:
            return None, value

    def _email_endjob(self) -> bool:
        """Get email_endjob setting"""
        return sabnzbd.cfg.email_endjob()

    def _email_full(self) -> bool:
        """Get email_full setting"""
        return sabnzbd.cfg.email_full()

    def _email_rss(self) -> bool:
        """Get email_rss setting"""
        return sabnzbd.cfg.email_rss()


# Convenience instance for common usage
server_validator = ServerValidator()


__all__ = [
    "ServerValidator",
    "server_validator",
]
