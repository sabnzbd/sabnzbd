#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.nzb - NZB-related classes and functionality
"""

# Article-related classes
from sabnzbd.nzb.article import Article, ArticleSaver, TryList

# File-related classes
from sabnzbd.nzb.file import NzbFile, NzbFileSaver, SkippedNzbFile

# Object-related classes
from sabnzbd.nzb.object import (
    NzbObject,
    NzbObjectSaver,
    NzoAttributeSaver,
    NzbEmpty,
    NzbRejected,
    NzbPreQueueRejected,
    NzbRejectToHistory,
)

__all__ = [
    # Article
    "Article",
    "ArticleSaver",
    "TryList",
    # File
    "NzbFile",
    "NzbFileSaver",
    "SkippedNzbFile",
    # Object
    "NzbObject",
    "NzbObjectSaver",
    "NzoAttributeSaver",
    "NzbEmpty",
    "NzbRejected",
    "NzbPreQueueRejected",
    "NzbRejectToHistory",
]
