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
tests.test_articlecache - Testing functions in articlecache.py
"""

from unittest import mock

import pytest

import sabnzbd
from sabnzbd.articlecache import ArticleCache
from sabnzbd.constants import ASSEMBLER_DELAY_FILL, MEBI

LIMIT = 100 * MEBI


class TestNonContiguousFlush:
    @pytest.fixture
    def cache(self):
        cache = ArticleCache()
        cache.change_direct_write(True)
        cache.new_limit(LIMIT)
        with mock.patch.object(sabnzbd, "Downloader", create=True) as downloader:
            downloader.no_active_jobs.return_value = False
            yield cache

    def test_not_before_the_downloader_is_held_back(self, cache):
        cache._ArticleCache__cache_size = int(LIMIT * ASSEMBLER_DELAY_FILL)
        assert not cache.should_flush()

    def test_once_the_downloader_is_held_back(self, cache):
        cache._ArticleCache__cache_size = int(LIMIT * ASSEMBLER_DELAY_FILL) + 1
        assert cache.should_flush()
