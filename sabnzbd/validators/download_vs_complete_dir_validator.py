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
sabnzbd.validators.download_vs_complete_dir_validator - Download vs complete directory validation utilities
"""

from typing import Optional, Tuple

import sabnzbd
from sabnzbd.constants import DEF_COMPLETE_DIR, DEF_DOWNLOAD_DIR
from sabnzbd.validators import ContextualValidator, ValidateResult


class DownloadVsCompleteDirValidator(ContextualValidator):
    """Validate that download and complete directories are not identical or nested"""

    def validate(self, root: str, value: str, default: str) -> ValidateResult:
        """Make sure download_dir and complete_dir are not identical
        or that download_dir is not a subfolder of complete_dir"""
        # Check what new value we are trying to set
        if default == DEF_COMPLETE_DIR:
            check_download_dir = self._get_download_dir_path()
            check_complete_dir = self._real_path(root, value)
        elif default == DEF_DOWNLOAD_DIR:
            check_download_dir = self._real_path(root, value)
            check_complete_dir = self._get_complete_dir_path()
        else:
            raise ValueError("Validator can only be used for download_dir/complete_dir")

        if self._same_directory(check_download_dir, check_complete_dir):
            return (
                T("The Completed Download Folder cannot be the same or a subfolder of the Temporary Download Folder"),
                None,
            )
        elif default == DEF_COMPLETE_DIR:
            # The complete_dir allows UNC
            return self._default_if_empty_validator(root, value, default)
        else:
            return self._safe_dir_validator(root, value, default)

    def _get_download_dir_path(self) -> str:
        """Get current download directory path"""
        return sabnzbd.cfg.download_dir.get_path()

    def _get_complete_dir_path(self) -> str:
        """Get current complete directory path"""
        return sabnzbd.cfg.complete_dir.get_path()

    def _real_path(self, root: str, value: str) -> str:
        """Get real path for validation"""
        from sabnzbd.filesystem import real_path

        return real_path(root, value)

    def _same_directory(self, path1: str, path2: str) -> bool:
        """Check if two paths point to the same directory"""
        from sabnzbd.filesystem import same_directory

        return same_directory(path1, path2)

    def _default_if_empty_validator(self, root: str, value: str, default: str) -> ValidateResult:
        """Use default if empty validator"""
        from sabnzbd.validators import default_if_empty_validator

        return default_if_empty_validator(root, value, default)

    def _safe_dir_validator(self, root: str, value: str, default: str) -> ValidateResult:
        """Use safe directory validator"""
        from sabnzbd.validators import safe_dir_validator

        return safe_dir_validator(root, value, default)


# Convenience instance for common usage
download_vs_complete_dir_validator = DownloadVsCompleteDirValidator()


__all__ = [
    "DownloadVsCompleteDirValidator",
    "download_vs_complete_dir_validator",
]
