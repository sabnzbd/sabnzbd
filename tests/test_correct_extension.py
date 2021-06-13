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
Testing SABnzbd correct extension functionality module
"""

import os
from tests.testhelper import *
import sabnzbd.utils.correct_extension as correct_extension


class TestPuremagic:
    def test_puremagic_magic_file(self):
        import puremagic  # direct access only in this test function

        filename = "tests/data/par2file/basic_16k.par2"
        assert os.path.isfile(filename)
        result = puremagic.magic_file(filename)
        assert result[0].extension == ".par2"


class Test_Extension:
    def test_has_common_extension(self):
        assert correct_extension.has_common_extension("blabla/blabla.mkv")
        assert correct_extension.has_common_extension("blabla/blabla.srt")
        assert correct_extension.has_common_extension("djjddj/aaaaa.epub")
        assert not correct_extension.has_common_extension("98ads098f098fa.a0ds98f098asdf")

    '''
    def test_most_likely_extension(self):
        assert correct_extension.most_likely_extension("tests/data/test_extension/hello_world_mpthree.blabla") == "mp3"
    '''


class TestCorrect_Extension:
    def test_all_possible_extensions(self):

        filename = "tests/data/par2file/basic_16k.par2"
        assert os.path.isfile(filename)
        extension_list = correct_extension.all_possible_extensions(filename)
        assert ".par2" in extension_list

        filename = "tests/data/test_extension/hello_world_mpthree.blabla"
        assert os.path.isfile(filename)
        extension_list = correct_extension.all_possible_extensions(filename)
        assert ".mpga" in extension_list  # puremagic says it's mpga, not mp3 ...