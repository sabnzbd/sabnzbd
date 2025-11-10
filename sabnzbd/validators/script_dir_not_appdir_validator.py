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
sabnzbd.validators.script_dir_not_appdir_validator - Script directory validation utilities
"""

import os
from typing import Optional, Tuple

from sabnzbd.validators import ContextualValidator, ValidateResult


# Lazy imports to avoid circular dependencies
def _helpful_warning(message, *args):
    """Lazy import wrapper for helpful_warning"""
    from sabnzbd.misc import helpful_warning
    return helpful_warning(message, *args)


def _get_prog_dir():
    """Lazy import wrapper for DIR_PROG"""
    import sabnzbd
    return sabnzbd.DIR_PROG


class ScriptDirNotAppDirValidator(ContextualValidator):
    """Validate that script directory is not in application directory"""

    def validate(self, root: str, value: str, default: str) -> ValidateResult:
        """Warn users to not use the Program Files folder for their scripts"""
        # Need to add separator so /mnt/sabnzbd and /mnt/sabnzbd-data are not detected as equal
        if value and self._same_directory(_get_prog_dir(), os.path.join(root, value)):
            # Warn, but do not block
            _helpful_warning(
                T(
                    "Do not use a folder in the application folder as your Scripts Folder, it might be emptied during updates."
                )
            )
        return None, value

    def _same_directory(self, path1: str, path2: str) -> bool:
        """Check if two paths point to the same directory"""
        from sabnzbd.filesystem import same_directory

        return same_directory(path1, path2)


# Convenience instance for common usage
script_dir_not_appdir_validator = ScriptDirNotAppDirValidator()


__all__ = [
    "ScriptDirNotAppDirValidator",
    "script_dir_not_appdir_validator",
]
