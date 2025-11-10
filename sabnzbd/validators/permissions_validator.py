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
sabnzbd.validators.permissions_validator - Octal permissions validation utilities
"""

from typing import Optional, Tuple

from sabnzbd.validators import StringValidator, ValidateResult


# Lazy import to avoid circular dependencies
def _helpful_warning(message, *args):
    """Lazy import wrapper for helpful_warning"""
    from sabnzbd.misc import helpful_warning

    return helpful_warning(message, *args)


class PermissionsValidator(StringValidator):
    """Validate octal file permissions"""

    def validate(self, value: str) -> ValidateResult:
        """Check if value is valid octal permissions"""
        # Empty value is allowed
        if not value:
            return None, value

        # Octal verification
        try:
            oct_value = int(value, 8)
            # Block setting it to 0
            if not oct_value:
                raise ValueError
        except ValueError:
            return T("%s is not a correct octal value") % value, None

        # Check if we at least have user-permissions
        if oct_value < int("700", 8):
            _helpful_warning(
                T("Permissions setting of %s might deny SABnzbd access to the files and folders it creates."),
                value,
            )
        return None, value


# Convenience instance for common usage
permissions_validator = PermissionsValidator()


__all__ = [
    "PermissionsValidator",
    "permissions_validator",
]
