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
sabnzbd.validators.single_tag_validator - Indexer tag validation utilities
"""

from typing import List, Optional, Tuple

from sabnzbd.validators import ListValidator, ValidateResult


class SingleTagValidator(ListValidator):
    """Validate and process indexer tags to prevent splitting of compound tags"""

    def validate(self, value: List[str]) -> ValidateResult:
        """Don't split single indexer tags like "TV > HD" into ['TV', '>', 'HD']"""
        if len(value) == 3:
            if value[1] == ">":
                return None, [" ".join(value)]
        return None, value


# Convenience instance for common usage
single_tag_validator = SingleTagValidator()


__all__ = [
    "SingleTagValidator",
    "single_tag_validator",
]
