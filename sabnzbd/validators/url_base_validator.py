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
sabnzbd.validators.url_base_validator - URL base path validation utilities
"""

from typing import Optional, Tuple

from sabnzbd.validators import StringValidator, ValidateResult


class UrlBaseValidator(StringValidator):
    """Validate and normalize URL base paths"""

    def validate(self, value: str) -> ValidateResult:
        """Strips the right slash and adds starting slash, if not present"""
        if value and isinstance(value, str):
            if not value.startswith("/"):
                value = "/" + value
            return None, value.rstrip("/")
        return None, value


# Convenience instance for common usage
url_base_validator = UrlBaseValidator()


__all__ = [
    "UrlBaseValidator",
    "url_base_validator",
]
