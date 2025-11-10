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
sabnzbd.validators.safe_dir_validator - Safe directory validation utilities
"""

from typing import Optional, Tuple

import sabnzbd
from sabnzbd.validators import ContextualValidator, ValidateResult


class SafeDirValidator(ContextualValidator):
    """Validate safe directory changes with queue state checks"""

    def validate(self, root: str, value: str, default: str) -> ValidateResult:
        """Allow only when queues are empty and not a network-path"""
        if not sabnzbd.__INITIALIZED__ or (
            self._postprocessor_empty() and self._nzbqueue_is_empty()
        ):
            # We allow it, but send a warning
            if self._is_network_path(self._real_path(root, value)):
                sabnzbd.misc.helpful_warning(
                    T('Network path "%s" should not be used here'), value
                )
            return self._validate_default_if_empty(value, default)
        else:
            return T("Queue not empty, cannot change folder."), None

    def _is_network_path(self, path: str) -> bool:
        """Check if path is a network path"""
        from sabnzbd.filesystem import is_network_path

        return is_network_path(path)

    def _real_path(self, root: str, value: str) -> str:
        """Get real path for validation"""
        from sabnzbd.filesystem import real_path

        return real_path(root, value)

    def _postprocessor_empty(self) -> bool:
        """Check if postprocessor queue is empty"""
        from sabnzbd import PostProcessor

        return PostProcessor.empty()

    def _nzbqueue_is_empty(self) -> bool:
        """Check if NZB queue is empty"""
        from sabnzbd import NzbQueue

        return NzbQueue.is_empty()

    def _validate_default_if_empty(self, value: str, default: str) -> ValidateResult:
        """If value is empty, return default"""
        if value:
            return None, value
        else:
            return None, default


# Convenience instance for common usage
safe_dir_validator = SafeDirValidator()


__all__ = [
    "SafeDirValidator",
    "safe_dir_validator",
]
