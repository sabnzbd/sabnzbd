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
tests.test_par2repair - par2 repair sessions
"""

import os
import sys
import zlib
from unittest import mock

import pytest
import sabctools

import sabnzbd.cfg as cfg
from sabnzbd.constants import GIGI, MEBI, PAR2_MINIMUM_MEMORY, PAR2_RESERVED_MEMORY
from sabnzbd.par2repair import RepairSession, _blocks_from_articles, article_backed_blocks, memory_limit
from tests.testhelper import make_mock_nzo

BLOCKSIZE = 64
CONTENT = bytes(range(256)) * 4


def piece_crcs(data: bytes, begin: int, blocksize: int) -> list[int]:
    """The CRC of each piece of data between multiples of blocksize, as the decoder splits it"""
    pieces = []
    position = begin
    while position < begin + len(data):
        end = min((position // blocksize + 1) * blocksize, begin + len(data))
        pieces.append(zlib.crc32(data[position - begin : end - begin]))
        position = end
    return pieces


def par2_checksums(size: int, content: bytes = CONTENT) -> list[int]:
    """The CRC32 par2 records for each block, the last one padded out with zeroes"""
    blocks = [content[start : start + BLOCKSIZE] for start in range(0, size, BLOCKSIZE)]
    blocks[-1] = blocks[-1][: size - (len(blocks) - 1) * BLOCKSIZE].ljust(BLOCKSIZE, b"\0")
    return [zlib.crc32(block) for block in blocks]


class FakeArticle:
    def __init__(self, data_begin, data_size, good=True, on_disk=True, content=CONTENT, split=True):
        self.data_begin = data_begin
        self.data_size = data_size
        self.decoded_size = data_size
        self.on_disk = on_disk
        self.crc32 = None
        self.block_size = self.block_crcs = None
        # crc32 is None when the decoded data did not match the yEnc trailer
        if good and data_begin is not None:
            data = content[data_begin : data_begin + data_size]
            self.crc32 = zlib.crc32(data)
            if split:
                self.block_size = BLOCKSIZE
                self.block_crcs = piece_crcs(data, data_begin, BLOCKSIZE)
        elif good:
            self.crc32 = 0


class FakeNzf:
    def __init__(self, articles, direct_written=True):
        self.decodetable = articles
        self.direct_written = direct_written
        self.crc32 = 0
        for article in articles:
            if article.crc32 is None or article.data_size is None:
                self.crc32 = None
                break
            self.crc32 = sabctools.crc32_combine(self.crc32, article.crc32, article.data_size)


@pytest.fixture
def datafile(tmp_path):
    def _make(size):
        path = tmp_path / "data.bin"
        path.write_bytes(CONTENT[:size])
        return str(path)

    return _make


def blocks_of(nzf, size, path):
    return _blocks_from_articles(nzf, BLOCKSIZE, -(-size // BLOCKSIZE), path, size, par2_checksums(size))


class TestBlocksFromArticles:
    def test_all_articles_good(self, datafile):
        # 4 articles of 160 bytes covering a 640 byte file, 10 blocks of 64
        articles = [FakeArticle(offset, 160) for offset in (0, 160, 320, 480)]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True] * 10

    def test_missing_article_needs_no_size_guess(self, datafile):
        """A missing article has no data_begin, and does not need one.

        Offsets are absolute, so a gap between two good articles is simply uncovered
        and every block overlapping it is left for par2 to check. Nothing has to be
        inferred about the length of what is missing.
        """
        articles = [
            FakeArticle(0, 160),
            FakeArticle(None, None, good=False),  # never arrived
            FakeArticle(320, 160),
            FakeArticle(480, 160),
        ]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))

        # Blocks 0-1 sit inside the first article, 5-9 inside the last two.
        # Blocks 2, 3 and 4 touch the hole at 160-320 and are not trusted.
        assert blocks == [True, True, False, False, False, True, True, True, True, True]

    def test_trailing_articles_missing(self, datafile):
        """Nothing after the last good article is trusted, however long the file is."""
        articles = [FakeArticle(0, 160), FakeArticle(160, 160), FakeArticle(None, None, good=False)]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True] * 5 + [False] * 5

    def test_article_present_but_checksum_failed(self, datafile):
        """A decoded article whose CRC did not match is bad, not unknown."""
        articles = [FakeArticle(0, 160), FakeArticle(160, 160, good=False), FakeArticle(320, 320)]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True, True, False, False, False, True, True, True, True, True]

    def test_article_not_on_disk(self, datafile):
        """Decoded and checksummed, but never written out, so nothing is known of it."""
        articles = [FakeArticle(0, 320), FakeArticle(320, 320, on_disk=False)]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True] * 5 + [None] * 5

    def test_good_article_without_an_offset(self, datafile):
        articles = [FakeArticle(0, 160), FakeArticle(None, None), FakeArticle(320, 320)]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True, True, None, None, None, True, True, True, True, True]

    def test_a_gap_not_wholly_lost_is_unknown(self, datafile):
        articles = [
            FakeArticle(0, 160),
            FakeArticle(None, None, good=False),
            FakeArticle(None, None),
            FakeArticle(480, 160),
        ]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True, True, None, None, None, None, None, None, True, True]

    def test_block_spanning_two_articles(self, datafile):
        """Consecutive articles are merged, so a block across the join still counts."""
        # 96-byte articles against 64-byte blocks: every boundary is straddled
        articles = [FakeArticle(offset, 96) for offset in range(0, 640, 96)]
        articles[-1] = FakeArticle(576, 64)
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True] * 10

    def test_short_final_block(self, datafile):
        """par2 pads the last block, so only the bytes the file has need covering."""
        # 600 bytes: 10 blocks, the last holding only 24 bytes
        articles = [FakeArticle(0, 600)]
        blocks = blocks_of(FakeNzf(articles), 600, datafile(600))
        assert blocks == [True] * 10

    def test_packed_file_is_skipped_entirely(self, datafile):
        """One packed article poisons the file: the assembler clears the flag and the
        whole file goes back to par2 for a full scan."""
        articles = [FakeArticle(offset, 160) for offset in (0, 160, 320, 480)]
        nzf = FakeNzf(articles, direct_written=False)
        assert blocks_of(nzf, 640, datafile(640)) is None

    def test_no_good_articles(self, datafile):
        articles = [FakeArticle(None, None, good=False)]
        assert blocks_of(FakeNzf(articles), 640, datafile(640)) == [False] * 10

    def test_an_article_of_another_version_is_not_trusted(self, datafile):
        """Its own yEnc check passes, but it is not what par2 describes"""
        other = bytes(reversed(CONTENT))
        articles = [FakeArticle(0, 160), FakeArticle(160, 160, content=other), FakeArticle(320, 320)]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True, True, None, None, None, True, True, True, True, True]

    def test_a_misplaced_article_is_not_trusted(self, datafile):
        """The yEnc headers put it over another article, so neither is taken for the
        blocks they share, and nothing vouches for where it should have been"""
        articles = [FakeArticle(0, 320), FakeArticle(320, 320), FakeArticle(None, None, good=False)]
        articles[1].data_begin = 0
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks[:5] == [None] * 5

    def test_an_article_whose_pieces_do_not_add_up_is_left_out_alone(self, datafile):
        articles = [FakeArticle(0, 160), FakeArticle(160, 160), FakeArticle(320, 320, good=False)]
        articles[1].block_crcs = articles[1].block_crcs[:-1]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [True, True, None, None, None] + [False] * 5

    def test_pieces_split_at_another_block_size_are_not_used(self, datafile):
        """A guess at the block size that turns out wrong costs nothing but the pieces"""
        articles = [FakeArticle(0, 320), FakeArticle(320, 320, good=False)]
        articles[0].block_size = BLOCKSIZE // 2
        articles[0].block_crcs = piece_crcs(CONTENT[:320], 0, BLOCKSIZE // 2)
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [None] * 5 + [False] * 5

    def test_whole_file_crc_proves_every_block(self, datafile):
        """Articles decoded before the par2 set was known carry no pieces, but when all
        of them arrived the whole-file CRC32 still proves every block"""
        articles = [FakeArticle(offset, 96, split=False) for offset in range(0, 576, 96)]
        articles.append(FakeArticle(576, 64, split=False))
        assert blocks_of(FakeNzf(articles), 640, datafile(640)) == [True] * 10

    def test_without_pieces_a_damaged_file_is_left_to_par2(self, datafile):
        articles = [FakeArticle(0, 320, split=False), FakeArticle(320, 320, good=False)]
        blocks = blocks_of(FakeNzf(articles), 640, datafile(640))
        assert blocks == [None] * 5 + [False] * 5

    def test_whole_file_crc_needs_the_articles_in_place(self, datafile):
        """The same articles in the same order, but one says it belongs elsewhere"""
        articles = [FakeArticle(offset, 160, split=False) for offset in (0, 160, 320, 480)]
        articles[3].data_begin = 470
        assert blocks_of(FakeNzf(articles), 640, datafile(640)) != [True] * 10

    def test_nothing_is_trusted_that_cannot_be_flushed(self, datafile):
        articles = [FakeArticle(0, 640)]
        with mock.patch("sabnzbd.par2repair.os.fsync", side_effect=OSError(5, "I/O error")):
            assert blocks_of(FakeNzf(articles), 640, datafile(640)) is None

    def test_the_file_is_flushed_before_it_is_trusted(self, datafile):
        articles = [FakeArticle(0, 640)]
        with mock.patch("sabnzbd.par2repair.os.fsync") as fsync:
            assert blocks_of(FakeNzf(articles), 640, datafile(640)) == [True] * 10
        fsync.assert_called_once()

    def test_without_par2_checksums_nothing_is_known(self, datafile):
        articles = [FakeArticle(0, 640)]
        assert _blocks_from_articles(FakeNzf(articles), BLOCKSIZE, 10, datafile(640), 640, None) is None

    def test_missing_file(self, tmp_path):
        articles = [FakeArticle(0, 640)]
        assert blocks_of(FakeNzf(articles), 640, str(tmp_path / "gone.bin")) is None


class FakeRepairer:
    def __init__(self, block_size, files):
        self.block_size = block_size
        self.files = files
        self.recoverable_file_count = len(files)

    def block_checksums(self, filename):
        for entry in self.files:
            if entry["name"] == filename:
                return par2_checksums(entry["size"])
        return None


class FakeNzo:
    def __init__(self, finished_files):
        self.finished_files = finished_files
        self.par2_rewritten = set()


class TestArticleBackedBlocks:
    @staticmethod
    def _setup(tmp_path, size=640):
        path = tmp_path / "alpha.bin"
        path.write_bytes(CONTENT[:size])
        nzf = FakeNzf([FakeArticle(0, size)])
        nzf.filename = "alpha.bin"
        repairer = FakeRepairer(
            BLOCKSIZE,
            [{"name": "alpha.bin", "target": str(path), "size": size, "blocks": size // BLOCKSIZE}],
        )
        return FakeNzo([nzf]), repairer

    def test_maps_files_by_name(self, tmp_path):
        nzo, repairer = self._setup(tmp_path)
        with (
            mock.patch.object(cfg.par2_quick_verify, "get", return_value=True),
            mock.patch.object(cfg.direct_write, "get", return_value=True),
        ):
            assert article_backed_blocks(nzo, repairer) == {"alpha.bin": [True] * 10}

    def test_maps_a_name_in_a_subdirectory_whichever_separator_it_has(self, tmp_path):
        nzo, repairer = self._setup(tmp_path)
        nzo.finished_files[0].filename = os.path.join("sub", "alpha.bin")
        repairer.files[0]["name"] = "sub/alpha.bin"
        with mock.patch.object(cfg.par2_quick_verify, "get", return_value=True):
            assert article_backed_blocks(nzo, repairer) == {"sub/alpha.bin": [True] * 10}

    def test_maps_a_name_the_set_records_in_a_code_page(self, tmp_path):
        nzo, repairer = self._setup(tmp_path)
        nzo.finished_files[0].filename = "café.bin"
        recorded = b"caf\xe9.bin".decode("utf-8", "surrogateescape")
        repairer.files[0]["name"] = recorded
        with mock.patch.object(cfg.par2_quick_verify, "get", return_value=True):
            assert article_backed_blocks(nzo, repairer) == {recorded: [True] * 10}

    def test_disabled_by_config(self, tmp_path):
        nzo, repairer = self._setup(tmp_path)
        with (
            mock.patch.object(cfg.par2_quick_verify, "get", return_value=False),
            mock.patch.object(cfg.direct_write, "get", return_value=True),
        ):
            assert article_backed_blocks(nzo, repairer) == {}

    def test_ignores_the_current_direct_write_setting(self, tmp_path):
        """What matters is how the file was written, not how the setting reads now.

        cfg.direct_write can be toggled at runtime and the assembler falls back per
        file, so at post-processing time it says nothing about an already-assembled
        file. The per-article direct_written flag is what decides.
        """
        nzo, repairer = self._setup(tmp_path)
        with (
            mock.patch.object(cfg.par2_quick_verify, "get", return_value=True),
            mock.patch.object(cfg.direct_write, "get", return_value=False),
        ):
            assert article_backed_blocks(nzo, repairer) == {"alpha.bin": [True] * 10}

    def test_a_file_a_repair_rewrote_is_not_vouched_for(self, tmp_path):
        nzo, repairer = self._setup(tmp_path)
        nzo.par2_rewritten.add(str(tmp_path / "alpha.bin"))
        with mock.patch.object(cfg.par2_quick_verify, "get", return_value=True):
            assert article_backed_blocks(nzo, repairer) == {}

    def test_packed_files_are_not_trusted(self, tmp_path):
        """A file the assembler packed sequentially is excluded even with the setting
        on: its article offsets do not describe where the bytes landed."""
        nzo, repairer = self._setup(tmp_path)
        nzo.finished_files[0].direct_written = False
        with (
            mock.patch.object(cfg.par2_quick_verify, "get", return_value=True),
            mock.patch.object(cfg.direct_write, "get", return_value=True),
        ):
            assert article_backed_blocks(nzo, repairer) == {}

    def test_skips_files_not_in_the_job(self, tmp_path):
        nzo, repairer = self._setup(tmp_path)
        nzo.finished_files = []
        with (
            mock.patch.object(cfg.par2_quick_verify, "get", return_value=True),
            mock.patch.object(cfg.direct_write, "get", return_value=True),
        ):
            assert article_backed_blocks(nzo, repairer) == {}

    def test_skips_targets_not_on_disk(self, tmp_path):
        nzo, repairer = self._setup(tmp_path)
        os.unlink(repairer.files[0]["target"])
        with (
            mock.patch.object(cfg.par2_quick_verify, "get", return_value=True),
            mock.patch.object(cfg.direct_write, "get", return_value=True),
        ):
            assert article_backed_blocks(nzo, repairer) == {}


class TestPar2MemoryLimit:
    """par2 defaults to half the host's physical memory. We give it a quarter of
    get_memory() instead, which is clamped by any cgroup limit."""

    def test_a_quarter_of_available_memory(self):
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(8192 * MEBI)):
            assert memory_limit() == int(2048 * MEBI)

    def test_the_article_cache_has_its_own_claim(self):
        """Both are taken out of the same memory, so the cache's share is not par2's."""
        with mock.patch.object(cfg.cache_limit, "get_int", return_value=int(7 * GIGI)):
            with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(8 * GIGI)):
                assert memory_limit() == int(8 * GIGI) - PAR2_RESERVED_MEMORY - int(7 * GIGI)

    def test_never_zero_on_a_tiny_budget(self):
        """Reserved headroom can exceed the whole budget; par2 reads 0 as "decide for
        yourself", which would throw away the clamp entirely."""
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(128 * MEBI)):
            assert memory_limit() == PAR2_MINIMUM_MEMORY

    def test_respects_a_cgroup_limit(self):
        # A 2GB container on a 32GB host
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(2 * GIGI)):
            assert memory_limit() == int(512 * MEBI)

    def test_falls_back_when_memory_is_unknown(self):
        # A conservative guess at the machine, and no clamp to apply
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=0):
            assert memory_limit() == int(128 * MEBI)

    def test_never_returns_zero(self):
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=1024):
            assert memory_limit() == PAR2_MINIMUM_MEMORY

    def test_capped_on_32bit(self):
        with mock.patch("sabnzbd.par2repair.get_memory", return_value=int(16384 * MEBI)):
            with mock.patch.object(sys, "maxsize", 2**31 - 1):
                assert memory_limit() == int(1024 * MEBI)
            # 64-bit gets the full quarter
            assert memory_limit() == int(4096 * MEBI)


class TestPar2Threads:
    """Left at 0, par2 counts the host's CPUs. get_cpus() knows about cgroup quotas."""

    def opened_with(self, tmp_path):
        """Open a session against a stubbed repairer and return the keyword arguments"""
        parfile = tmp_path / "test.par2"
        parfile.write_bytes(b"")
        session = RepairSession(mock.Mock(), "test", str(parfile))
        with mock.patch("sabnzbd.par2repair.sabctools.Par2Repairer") as repairer:
            session.open([])
        return repairer.call_args.kwargs

    def test_leaves_one_cpu_for_the_rest_of_sabnzbd(self, tmp_path):
        with mock.patch("sabnzbd.par2repair.get_cpus", return_value=4):
            assert self.opened_with(tmp_path)["threads"] == 3

    def test_a_single_cpu_still_gets_a_thread(self, tmp_path):
        with mock.patch("sabnzbd.par2repair.get_cpus", return_value=1):
            assert self.opened_with(tmp_path)["threads"] == 1

    def test_falls_back_to_par2_when_undetectable(self, tmp_path):
        """Zero hands the decision back to par2, which is better than guessing 1"""
        with mock.patch("sabnzbd.par2repair.get_cpus", return_value=0):
            assert self.opened_with(tmp_path)["threads"] == 0

    def test_file_threads_are_left_to_par2(self, tmp_path):
        """This one is about I/O concurrency, not CPU count - par2's 2 stands"""
        assert "file_threads" not in self.opened_with(tmp_path)


class TestPar2SetLoaded:
    @pytest.mark.parametrize(
        "creator, expected",
        [
            ("Created by par2cmdline-turbo version 1.1.1.", "(Created by par2cmdline-turbo version 1.1.1.)"),
            ("", "(creator unknown)"),
        ],
    )
    def test_logs_the_client_that_created_the_set(self, tmp_path, caplog, creator, expected):
        parfile = tmp_path / "test.par2"
        parfile.write_bytes(b"")
        session = RepairSession(make_mock_nzo(download_path=str(tmp_path)), "test", str(parfile))
        with mock.patch("sabnzbd.par2repair.sabctools.Par2Repairer") as repairer:
            repairer.return_value.load.return_value = sabctools.Par2Result.SUCCESS
            repairer.return_value.creator = creator
            with caplog.at_level("INFO"):
                session.open([])
        assert any(record.getMessage().endswith(expected) for record in caplog.records)


class TestPar2Repaired:
    @staticmethod
    def repair(tmp_path, caplog, in_place_files):
        session = RepairSession(make_mock_nzo(download_path=str(tmp_path)), "test", str(tmp_path / "test.par2"))
        session.repairer = mock.Mock(renames={}, in_place_files=in_place_files, files=[])
        session.repairer.repair.return_value = sabctools.Par2Result.SUCCESS
        with caplog.at_level("DEBUG"):
            assert session.repair() == sabctools.Par2Result.SUCCESS
        return [record.getMessage() for record in caplog.records if "in place" in record.getMessage()]

    def test_logs_the_files_repaired_in_place(self, tmp_path, caplog):
        assert self.repair(tmp_path, caplog, ["a.rar", "b.rar"]) == ["Repaired in place in test: a.rar, b.rar"]

    def test_says_nothing_when_none_were(self, tmp_path, caplog):
        assert self.repair(tmp_path, caplog, []) == []

    def test_remembers_the_files_it_rewrote(self, tmp_path, caplog):
        session = RepairSession(make_mock_nzo(download_path=str(tmp_path)), "test", str(tmp_path / "test.par2"))
        target = str(tmp_path / "a.rar")
        session.repairer = mock.Mock(renames={}, in_place_files=[], files=[{"target": target}])
        session.repairer.repair.return_value = sabctools.Par2Result.SUCCESS
        session.repair()
        assert session.nzo.par2_rewritten == {target}


class TestPar2FileSizes:
    @staticmethod
    def resize(tmp_path, size, wanted, data_end, downloaded=True):
        path = tmp_path / "test.rar"
        path.write_bytes(b"x" * size)
        nzf = mock.Mock(filename="test.rar", decodetable=[mock.Mock(on_disk=True, data_begin=0, data_size=data_end)])
        session = RepairSession(
            make_mock_nzo(download_path=str(tmp_path), finished_files=[nzf] if downloaded else []),
            "test",
            str(tmp_path / "test.par2"),
        )
        session.repairer = mock.Mock(files=[{"name": "test.rar", "target": str(path), "size": wanted}])
        session.truncate_to_par2_sizes()
        return os.path.getsize(path)

    def test_a_short_file_is_not_extended(self, tmp_path):
        assert self.resize(tmp_path, 100, 150, data_end=100) == 100

    def test_a_long_file_is_cut_back_to_its_data(self, tmp_path):
        assert self.resize(tmp_path, 150, 100, data_end=100) == 100

    def test_article_data_past_the_recorded_size_is_kept(self, tmp_path):
        assert self.resize(tmp_path, 150, 100, data_end=120) == 150

    def test_a_file_this_job_did_not_download_is_left_alone(self, tmp_path):
        assert self.resize(tmp_path, 150, 100, data_end=100, downloaded=False) == 150
