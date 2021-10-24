#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_newsunpack - Tests of various functions in newspack
"""
from sabnzbd.newsunpack import *


class TestNewsUnpack:
    def test_is_sfv_file(self):
        assert is_sfv_file("tests/data/good_sfv_unicode.sfv")
        assert is_sfv_file("tests/data/one_line.sfv")
        assert not is_sfv_file("tests/data/only_comments.sfv")
        assert not is_sfv_file("tests/data/random.bin")
