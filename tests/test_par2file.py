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
Testing SABnzbd par2 parsing
"""

import hashlib
import logging
import os
from unittest import mock

import pytest

from sabnzbd.par2file import PAR_CREATOR_ID, PAR_PKT_ID, FilePar2Info, parse_par2_file, uncovered_blocks
from tests.testhelper import SAB_DATA_DIR

# TODO: Add testing for edge cases, such as non-unique md5of16k or broken par files


class TestPar2Parsing:
    @pytest.mark.parametrize("packet_length", [0, 4, 8, 12, 16, 20, 22, 24, 28, 32, 60, 2**20, 2**62, 2**64 - 4])
    def test_invalid_packet_length_does_not_consume_following_packets(self, tmp_path, packet_length):
        source_path = os.path.join(SAB_DATA_DIR, "par2file", "basic_16k.par2")
        with open(source_path, "rb") as source:
            valid_packets = source.read()

        malformed_path = tmp_path / "malformed.par2"
        # Too short, not a multiple of 4 or larger than the file: scanning resumes right after the header
        malformed_path.write_bytes(PAR_PKT_ID + packet_length.to_bytes(8, "little") + valid_packets)

        set_id, table = parse_par2_file(str(malformed_path), {})
        assert set_id == "69af2273e8fa0b4d811b56d02a9c4b59"
        assert list(table) == ["rss_feed_test.xml"]

    def test_minimum_length_creator_packet_is_accepted(self, tmp_path, caplog):
        source_path = os.path.join(SAB_DATA_DIR, "par2file", "basic_16k.par2")
        with open(source_path, "rb") as source:
            valid_packets = source.read()

        # A 64-byte Creator has no body, but its checksum still covers the set ID and packet type.
        creator_data = valid_packets[32:48] + PAR_CREATOR_ID
        creator_packet = PAR_PKT_ID + (64).to_bytes(8, "little") + hashlib.md5(creator_data).digest() + creator_data
        assert len(creator_packet) == 64
        creator_path = tmp_path / "creator_64.par2"
        creator_path.write_bytes(creator_packet + valid_packets)

        with caplog.at_level(logging.DEBUG):
            set_id, table = parse_par2_file(str(creator_path), {})

        assert set_id == "69af2273e8fa0b4d811b56d02a9c4b59"
        assert list(table) == ["rss_feed_test.xml"]
        assert "Par2-creator of creator_64.par2 is: " in (record.getMessage() for record in caplog.records)

    @staticmethod
    def _fixture_packets() -> dict[bytes, bytes]:
        """The packets of basic_16k.par2, by type"""
        with open(os.path.join(SAB_DATA_DIR, "par2file", "basic_16k.par2"), "rb") as source:
            data = source.read()
        packets = {}
        while data:
            length = int.from_bytes(data[8:16], "little")
            packets[data[48:64]] = data[:length]
            data = data[length:]
        return packets

    @pytest.mark.parametrize("chunk", [8, 2**16])
    @pytest.mark.parametrize("garbage", range(1, 17))
    def test_packets_are_found_after_garbage_of_any_length(self, tmp_path, chunk, garbage):
        shifted = tmp_path / "shifted.par2"
        shifted.write_bytes(b"\xff" * garbage + b"".join(self._fixture_packets().values()))

        with mock.patch("sabnzbd.par2file.PACKET_SEARCH_CHUNK", chunk):
            set_id, table = parse_par2_file(str(shifted), {})

        assert set_id == "69af2273e8fa0b4d811b56d02a9c4b59"
        assert list(table) == ["rss_feed_test.xml"]

    def test_a_damaged_packet_does_not_hide_the_packets_its_length_covers(self, tmp_path):
        valid_packets = b"".join(self._fixture_packets().values())
        # A header whose length takes in every packet after it, and whose checksum fails
        damaged = PAR_PKT_ID + (64 + len(valid_packets)).to_bytes(8, "little") + b"\0" * 48
        damaged_path = tmp_path / "damaged.par2"
        damaged_path.write_bytes(damaged + valid_packets)

        set_id, table = parse_par2_file(str(damaged_path), {})

        assert set_id == "69af2273e8fa0b4d811b56d02a9c4b59"
        assert list(table) == ["rss_feed_test.xml"]

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
                        blocksize=384000,
                        blockcount=1,
                    )
                },
            ) == parse_par2_file(os.path.join(SAB_DATA_DIR, "deobfuscate_filenames", "rename.par2"), {})
            assert "Par2-creator of rename.par2 is: QuickPar 0.9" in caplog.text
            caplog.clear()

            assert (
                "3ec589bd15a161194e2ec6b8189ec403",
                {
                    "frènch_german_demö.rar": FilePar2Info(
                        filename="frènch_german_demö.rar",
                        hash16k=b",F\x1f3\x83\xe7wa\xf4Q\xb0[\xd9\x9a\xc0\xa1",
                        filehash=13964116,
                        filesize=153,
                        blocksize=156,
                        blockcount=1,
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
                        blocksize=52,
                        blockcount=394,
                    ),
                    "我喜欢编程.part6.rar": FilePar2Info(
                        filename="我喜欢编程.part6.rar",
                        hash16k=b"\xb4\x86t\xf7B\x0bW+\xee-\xfd4z\x03\x05\xd2",
                        filehash=251711255,
                        filesize=1191,
                        blocksize=52,
                        blockcount=23,
                    ),
                    "我喜欢编程.part2.rar": FilePar2Info(
                        filename="我喜欢编程.part2.rar",
                        hash16k=b"\x1f\n\xc8\xf09@A&n\x17ah\xa4\x1dEi",
                        filehash=1866884676,
                        filesize=20480,
                        blocksize=52,
                        blockcount=394,
                    ),
                    "我喜欢编程.part1.rar": FilePar2Info(
                        filename="我喜欢编程.part1.rar",
                        hash16k=b"\x9b\x9cm\xd63\x15\x16\x923\xc9\xd7\x1c\x94\xd8\xd9#",
                        filehash=3178523720,
                        filesize=20480,
                        blocksize=52,
                        blockcount=394,
                    ),
                    "我喜欢编程.part5.rar": FilePar2Info(
                        filename="我喜欢编程.part5.rar",
                        hash16k=b"\x89fu\xd8\x10a\x01Ze\xcb\x04\x0b\ndjr",
                        filehash=4287933540,
                        filesize=20480,
                        blocksize=52,
                        blockcount=394,
                    ),
                    "我喜欢编程.part4.rar": FilePar2Info(
                        filename="我喜欢编程.part4.rar",
                        hash16k=b"8TA\x83\xeb\xc8\xbe\xf58\x95g\x87\n\xa2A\xa1",
                        filehash=3954002734,
                        filesize=20480,
                        blocksize=52,
                        blockcount=394,
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
                        blocksize=384000,
                        blockcount=1,
                    )
                },
            ) == parse_par2_file(os.path.join(SAB_DATA_DIR, "par2file", "basic_16k.par2"), md5of16k)
            assert md5of16k == {b"'ky\xd7\xd1\xd3wF\xed\x9c\xf7\x9b\x90\x93\x106": "rss_feed_test.xml"}
            assert "Par2-creator of basic_16k.par2 is: QuickPar 0.9" in caplog.text
            caplog.clear()

    def test_checksums_that_do_not_cover_the_file_leave_no_block_geometry(self, tmp_path):
        source_path = os.path.join(SAB_DATA_DIR, "par2file", "basic_16k.par2")
        with open(source_path, "rb") as source:
            packets = source.read()

        # One checksum entry more than the file has blocks
        start = packets.index(b"PAR 2.0\x00IFSC") - 48
        length = int.from_bytes(packets[start + 8 : start + 16], "little")
        data = packets[start + 32 : start + length] + b"\0" * 20
        ifsc = PAR_PKT_ID + (32 + len(data)).to_bytes(8, "little") + hashlib.md5(data).digest() + data
        extra_entry = tmp_path / "extra_entry.par2"
        extra_entry.write_bytes(packets[:start] + ifsc + packets[start + length :])

        _, table = parse_par2_file(str(extra_entry), {})
        assert table["rss_feed_test.xml"].blocksize == 0
        assert table["rss_feed_test.xml"].blockcount == 0


class TestUncoveredBlocks:
    """Tests for par2file.uncovered_blocks()."""

    BLOCKSIZE = 1000
    BLOCKCOUNT = 10
    FILESIZE = 9500  # The last block is short and par2 pads it

    def uncovered(self, ranges):
        return uncovered_blocks(ranges, self.BLOCKSIZE, self.BLOCKCOUNT, self.FILESIZE)

    def test_everything_covered(self):
        assert self.uncovered([(0, 9500)]) == 0

    def test_nothing_covered(self):
        assert self.uncovered([]) == self.BLOCKCOUNT

    def test_short_final_block_needs_only_the_bytes_the_file_has(self):
        """Block 9 spans 9000-10000 but the file ends at 9500."""
        assert self.uncovered([(0, 9500)]) == 0
        assert self.uncovered([(0, 9499)]) == 1

    def test_gap_inside_one_block(self):
        assert self.uncovered([(0, 5000), (5100, 9500)]) == 1

    def test_gap_straddling_a_boundary(self):
        assert self.uncovered([(0, 4900), (5100, 9500)]) == 2

    def test_abutting_ranges_merge(self):
        assert self.uncovered([(0, 4000), (4000, 9500)]) == 0

    def test_block_size_decides_the_damage(self):
        """The same lost bytes cost a different number of blocks per geometry."""
        arrived = [(0, 2500), (5000, 9500)]
        assert uncovered_blocks(arrived, 1000, 10, 9500) == 3
        assert uncovered_blocks(arrived, 5000, 2, 9500) == 1
