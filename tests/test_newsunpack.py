#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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

import pytest

from sabnzbd.newsunpack import *


class TestNewsUnpack:
    @pytest.mark.parametrize(
        "test_input, expected_output",
        [
            (["cmd1", 9, "cmd3"], '"cmd1" "9" "cmd3"'),  # sending all commands as valid string
            (["", "cmd1", "5"], '"" "cmd1" "5"'),  # sending blank string
            (["cmd1", None, "cmd3", "tail -f"], '"cmd1" "" "cmd3" "tail -f"'),  # sending None in command
            (["cmd1", 0, "ps ux"], '"cmd1" "" "ps ux"'),  # sending 0
        ],
    )
    def test_list_to_cmd(self, test_input, expected_output):
        """ Test to convert list to a cmd.exe-compatible command string """

        res = list2cmdline(test_input)
        # Make sure the output is cmd.exe-compatible
        assert res == expected_output

    def test_is_sfv_file(self):
        assert is_sfv_file("tests/data/good_sfv_unicode.sfv")
        assert is_sfv_file("tests/data/one_line.sfv")
        assert not is_sfv_file("tests/data/only_comments.sfv")
        assert not is_sfv_file("tests/data/random.bin")
