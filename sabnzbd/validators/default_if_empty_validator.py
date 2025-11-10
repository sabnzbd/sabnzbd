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
sabnzbd.validators.default_if_empty_validator - Default value substitution utilities
"""

from typing import Optional, Tuple

from sabnzbd.validators import StringValidator, ValidateResult


class DefaultIfEmptyValidator(StringValidator):
    """Validator that returns default value if input is empty"""

    def validate(self, value: str, default: str = "") -> ValidateResult:
        """If value is empty, return default"""
        if value:
            return None, value
        else:
            return None, default


# Convenience instance for common usage
# Note: This validator requires default parameter, so it's used differently
default_if_empty_validator = DefaultIfEmptyValidator()


__all__ = [
    "DefaultIfEmptyValidator",
    "default_if_empty_validator",
]
