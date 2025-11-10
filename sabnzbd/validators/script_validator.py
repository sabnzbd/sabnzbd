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
sabnzbd.validators.script_validator - Script validation utilities
"""

from typing import Optional, Tuple

from sabnzbd.validators import StringValidator, ValidateResult


# Lazy imports to avoid circular dependencies
def _is_initialized():
    """Lazy import wrapper for __INITIALIZED__"""
    import sabnzbd
    return sabnzbd.__INITIALIZED__

def _is_none(value):
    """Lazy import wrapper for is_none"""
    from sabnzbd.misc import is_none

    return is_none(value)


def _is_valid_script(value):
    """Lazy import wrapper for is_valid_script"""
    from sabnzbd.filesystem import is_valid_script

    return is_valid_script(value)


class ScriptValidator(StringValidator):
    """Validate script names and paths"""

    def validate(self, value: str) -> ValidateResult:
        """Check if value is a valid script"""
        if not _is_initialized() or (value and _is_valid_script(value)):
            return None, value
        elif _is_none(value):
            return None, "None"
        return T("%s is not a valid script") % value, None


# Convenience instance for common usage
script_validator = ScriptValidator()


__all__ = [
    "ScriptValidator",
    "script_validator",
]
