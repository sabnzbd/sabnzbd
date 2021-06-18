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
import sabnzbd.utils.file_extension as file_extension


class TestPuremagic:
    def test_puremagic_magic_file(self):
        import puremagic  # direct access only in this test function

        filename = "tests/data/par2file/basic_16k.par2"
        assert os.path.isfile(filename)
        result = puremagic.magic_file(filename)
        assert result[0].extension == ".par2"


class Test_File_Extension:
    def test_has_popular_extension(self):
        assert file_extension.has_popular_extension("blabla/blabla.mkv")
        assert file_extension.has_popular_extension("blabla/blabla.srt")
        assert file_extension.has_popular_extension("djjddj/aaaaa.epub")
        assert not file_extension.has_popular_extension("98ads098f098fa.a0ds98f098asdf")

    def test_what_is_most_likely_extension(self):
        filename = "tests/data/test_file_extension/apeeengeee"  # A PNG
        assert os.path.isfile(filename)
        assert file_extension.what_is_most_likely_extension(filename) == ".png"

        filename = "tests/data/test_file_extension/somepeedeef"  # Some PDF
        assert os.path.isfile(filename)
        assert file_extension.what_is_most_likely_extension(filename) == ".pdf"

        filename = "tests/data/test_file_extension/my_matroska"  # my Matroska MKV
        assert os.path.isfile(filename)
        assert file_extension.what_is_most_likely_extension(filename) == ".mkv"

        filename = "tests/data/test_file_extension/sometxtfile"  # some txt file
        assert os.path.isfile(filename)
        assert file_extension.what_is_most_likely_extension(filename) == ".txt"

        filename = "tests/data/test_file_extension/some_nzb_file"  # some txt file
        assert os.path.isfile(filename)
        assert file_extension.what_is_most_likely_extension(filename) == ".nzb"