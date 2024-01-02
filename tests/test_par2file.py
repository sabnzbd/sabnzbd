#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
Testing SABnzbd par2 parsing
"""

from sabnzbd.par2file import *
from tests.testhelper import *

# TODO: Add testing for edge cases, such as non-unique md5of16k or broken par files


class TestPar2Parsing:
    def test_parse_par2_file(self, caplog):
        # To capture the par2-creator, we need to capture the logging
        with caplog.at_level(logging.DEBUG):
            # These files are all <16k so the MD5 of the whole file is the same as the 16k one
            assert (
                "7e926efb97172cbcff9a5b32a6a4df55",
                {
                    "random.bin": FilePar2Info(
                        filename="random.bin",
                        hash16k=b"\xbf\xe0\xe4\x10\xa2#\xf5\xbeN\x7f2\xe5\x9e\xdd\t\x03",
                        filehash=787459617,
                        filesize=5120,
                    )
                },
            ) == parse_par2_file(os.path.join(SAB_DATA_DIR, "deobfuscate_filenames", "rename.par2"), {})
            assert "Par2-creator of rename.par2 is: QuickPar 0.9" in caplog.text
            caplog.clear()

            assert (
                "6f9d1d2e7466f09f1db010084bb4ca89",
                {
                    "frènch_german_demö.rar": FilePar2Info(
                        filename="frènch_german_demö.rar",
                        hash16k=b"C\t\x1d\xbd\xdf\x8c\xb5w \xcco\xbf~L)\xc2",
                        filehash=1320056373,
                        filesize=132,
                    )
                },
            ) == parse_par2_file(
                os.path.join(SAB_DATA_DIR, "test_win_unicode", "frènch_german_demö.rar.vol0+1.par2"), {}
            )
            assert "Par2-creator of frènch_german_demö.rar.vol0+1.par2 is: QuickPar 0.9" in caplog.text
            caplog.clear()

            assert (
                "a96d3f9c00d63653d8e2cc171e8c5384",
                {
                    "我喜欢编程.part3.rar": FilePar2Info(
                        filename="我喜欢编程.part3.rar",
                        hash16k=b"\xe0\xab\xe9\x96\xfa\xdc\xba\x07?\xb1\xd4w\t2\xe5\x96",
                        filehash=2849562011,
                        filesize=20480,
                    ),
                    "我喜欢编程.part6.rar": FilePar2Info(
                        filename="我喜欢编程.part6.rar",
                        hash16k=b"\xb4\x86t\xf7B\x0bW+\xee-\xfd4z\x03\x05\xd2",
                        filehash=251711255,
                        filesize=1191,
                    ),
                    "我喜欢编程.part2.rar": FilePar2Info(
                        filename="我喜欢编程.part2.rar",
                        hash16k=b"\x1f\n\xc8\xf09@A&n\x17ah\xa4\x1dEi",
                        filehash=1866884676,
                        filesize=20480,
                    ),
                    "我喜欢编程.part1.rar": FilePar2Info(
                        filename="我喜欢编程.part1.rar",
                        hash16k=b"\x9b\x9cm\xd63\x15\x16\x923\xc9\xd7\x1c\x94\xd8\xd9#",
                        filehash=3178523720,
                        filesize=20480,
                    ),
                    "我喜欢编程.part5.rar": FilePar2Info(
                        filename="我喜欢编程.part5.rar",
                        hash16k=b"\x89fu\xd8\x10a\x01Ze\xcb\x04\x0b\ndjr",
                        filehash=4287933540,
                        filesize=20480,
                    ),
                    "我喜欢编程.part4.rar": FilePar2Info(
                        filename="我喜欢编程.part4.rar",
                        hash16k=b"8TA\x83\xeb\xc8\xbe\xf58\x95g\x87\n\xa2A\xa1",
                        filehash=3954002734,
                        filesize=20480,
                    ),
                },
            ) == parse_par2_file(os.path.join(SAB_DATA_DIR, "unicode_rar", "我喜欢编程.par2"), {})
            assert "Par2-creator of 我喜欢编程.par2 is: Created by par2cmdline version 0.8.1" in caplog.text
            caplog.clear()

    def test_parse_par2_file_16k(self, caplog):
        # Capture logging of the par2-creator
        with caplog.at_level(logging.DEBUG):
            # This file is 18k, so it's md5 of the first 16k is actually different
            md5of16k = {}
            assert (
                "69af2273e8fa0b4d811b56d02a9c4b59",
                {
                    "rss_feed_test.xml": FilePar2Info(
                        filename="rss_feed_test.xml",
                        hash16k=b"'ky\xd7\xd1\xd3wF\xed\x9c\xf7\x9b\x90\x93\x106",
                        filehash=1157097199,
                        filesize=17803,
                    )
                },
            ) == parse_par2_file(os.path.join(SAB_DATA_DIR, "par2file", "basic_16k.par2"), md5of16k)
            assert md5of16k == {b"'ky\xd7\xd1\xd3wF\xed\x9c\xf7\x9b\x90\x93\x106": "rss_feed_test.xml"}
            assert "Par2-creator of basic_16k.par2 is: QuickPar 0.9" in caplog.text
            caplog.clear()
