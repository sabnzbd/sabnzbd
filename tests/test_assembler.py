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
tests.test_assembler - Testing functions in assembler.py
"""

import os
import threading
from types import SimpleNamespace
from typing import NamedTuple, Optional
from unittest import mock
from zlib import crc32

import pytest

import sabnzbd
from sabnzbd.assembler import Assembler
from sabnzbd.constants import ASSEMBLER_MAX_OPEN_WRITERS, GIGI
from sabnzbd.filesystem import Diskspace
from sabnzbd.misc import pp_to_opts
from sabnzbd.nzb import Article, NzbFile, NzbObject


class TestAssembler:
    @pytest.fixture
    def assembler(self, tmp_path):
        """Prepare a sabnzbd assembler, tmp_path is used because C libraries require a real filesystem."""

        try:
            sabnzbd.Downloader = SimpleNamespace(paused=False)
            sabnzbd.ArticleCache = SimpleNamespace()
            sabnzbd.Assembler = Assembler()

            # Create a minimal NzbObject / NzbFile
            self.nzo = NzbObject("test.nzb")

            admin_path = str(tmp_path / "admin")

            with mock.patch.object(
                NzbObject,
                "admin_path",
                new_callable=mock.PropertyMock,
            ) as admin_path_mock:
                admin_path_mock.return_value = admin_path
                self.nzo.download_path = str(tmp_path / "download")
                os.mkdir(self.nzo.download_path)
                os.mkdir(self.nzo.admin_path)

                # NzbFile requires some constructor args; use dummy but valid values
                self.nzf = NzbFile(
                    date=self.nzo.avg_date,
                    subject="test-file",
                    raw_article_db=[[None, None]],
                    file_bytes=0,
                    nzo=self.nzo,
                )
                self.nzo.files.append(self.nzf)
                self.nzf.type = "yenc"  # for writes from article cache
                assert self.nzf.prepare_filepath() is not None
                # Clear the state after prepare_filepath
                self.nzf.articles.clear()
                self.nzf.decodetable.clear()

                with mock.patch.object(Assembler, "write", wraps=Assembler.write) as mocked_assembler_write:
                    yield mocked_assembler_write

                # All articles should be marked on_disk
                for article in self.nzf.decodetable:
                    assert article.on_disk is True

                # File should be marked assembled
                assert self.nzf.assembled is True
        finally:
            # Reset values after test
            del sabnzbd.Downloader
            del sabnzbd.ArticleCache
            del sabnzbd.Assembler

    def _make_article(
        self, nzf: NzbFile, offset: int, data: bytearray, decoded: bool = True, can_direct_write: bool = True
    ) -> tuple[Article, bytearray]:
        article = Article("msgid", len(data), nzf)
        article.decoded = decoded
        article.data_begin = offset
        article.data_size = len(data) if can_direct_write else None
        article.file_size = nzf.bytes
        article.decoded_size = len(data)
        article.crc32 = crc32(data)
        article.tries = 1  # force aborts if never tried
        return article, data

    def _make_request(
        self,
        nzf: NzbFile,
        articles: list[tuple[Article, bytearray]],
    ):
        article_data = {}
        for article, raw in articles:
            nzf.decodetable.append(article)
            article_data[article] = raw
        expected = b"".join(article_data.values())
        nzf.bytes = len(expected)
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=lambda article: article_data.get(article))

        for article, _ in articles:
            article.file_size = nzf.bytes

        return article_data.values(), expected

    @staticmethod
    def _assert_expected_content(nzf: NzbFile, expected: bytes):
        with open(nzf.filepath, "rb") as f:
            content = f.read()
        assert content == expected
        assert nzf.assembler_next_index == len(nzf.decodetable)
        assert nzf.contiguous_offset() == nzf.decodetable[0].file_size
        # crc32 is finalized in post-processing, not during assembly. Once combined in decodetable
        # order it must match the file regardless of the order articles were written to disk
        nzf.finalize_crc32()
        assert nzf.crc32 == crc32(expected)

    def test_assemble_direct_write(self, assembler):
        """Pure direct write mode"""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello"), can_direct_write=True),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), can_direct_write=True),
            ],
        )
        assert self.nzf.contiguous_offset() == 0
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_direct_write_aborted_to_append(self, assembler):
        """
        Start in direct_write, but encounter an article that cannot be direct-written.
        Assembler should abort direct_write and switch to append mode.
        """
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello"), can_direct_write=True),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), can_direct_write=False),
                self._make_article(self.nzf, offset=10, data=bytearray(b"12345"), can_direct_write=True),
            ],
        )
        # [0] direct_write, [1] append, [2] append
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_direct_append_direct_append(self, assembler):
        """Out-of-order direct write via cache, append fills the gap."""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello"), can_direct_write=True),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), can_direct_write=False),
                self._make_article(
                    self.nzf, offset=10, data=bytearray(b"12345"), decoded=False, can_direct_write=False
                ),
                self._make_article(
                    self.nzf, offset=15, data=bytearray(b"abcde"), decoded=False, can_direct_write=True
                ),  # Cache direct
            ],
        )
        # [0] direct_write, [1] append
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=False, direct_write=True)
        assert assembler.call_count == 2
        assert self.nzf.contiguous_offset() == 10
        # [3] direct_write
        article = self.nzf.decodetable[3]
        article.decoded = True
        Assembler.assemble_article(article, sabnzbd.ArticleCache.load_article(article))
        assert assembler.call_count == 3
        assert self.nzf.contiguous_offset() == 10  # was not a sequential write
        # [3] append
        article = self.nzf.decodetable[2]
        article.decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        assert assembler.call_count == 4
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_direct_write_aborted_to_append_second_attempt(self, assembler):
        """Second attempt after initial partial assemble, including revert to append mode."""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello"), can_direct_write=True),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), can_direct_write=False),
                self._make_article(
                    self.nzf, offset=10, data=bytearray(b"12345"), decoded=False, can_direct_write=False
                ),
            ],
        )
        # [0] direct_write, [1] append
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=False, direct_write=True)
        assert self.nzf.decodetable[2].on_disk is False
        self.nzf.decodetable[2].decoded = True
        # [2] append
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_append_direct_second_attempt(self, assembler):
        """Second attempt after initial partial assemble"""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello"), can_direct_write=False),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), decoded=False, can_direct_write=True),
            ],
        )
        # [0] append
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=False, direct_write=False)
        self.nzf.decodetable[1].decoded = True
        # [1] append
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_append_only(self, assembler):
        """Pure append mode"""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"abcd"), can_direct_write=False),
                self._make_article(self.nzf, offset=0, data=bytearray(b"efg"), can_direct_write=False),
            ],
        )
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=False)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_append_second_attempt(self, assembler):
        """Pure append mode, second attempt"""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"abcd"), can_direct_write=False),
                self._make_article(self.nzf, offset=0, data=bytearray(b"efg"), decoded=False, can_direct_write=False),
            ],
        )
        # [0] append
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=False, direct_write=False)
        assert self.nzf.assembled is False
        self.nzf.decodetable[1].decoded = True
        # [1] append
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=False)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_append_first_not_decoded(self, assembler):
        """Pure append mode, second attempt"""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"abcd"), decoded=False, can_direct_write=False),
                self._make_article(self.nzf, offset=0, data=bytearray(b"efg"), can_direct_write=False),
            ],
        )
        # Nothing written
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=False, direct_write=False)
        assert not os.path.exists(self.nzf.filepath)
        self.nzf.decodetable[0].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=False)
        self._assert_expected_content(self.nzf, expected)

    def test_force_append(self, assembler):
        """Force in direct_write mode, then fill in gaps in append mode"""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello")),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), decoded=False, can_direct_write=False),
                self._make_article(self.nzf, offset=10, data=bytearray(b"12345")),
                self._make_article(self.nzf, offset=15, data=bytearray(b"abcd"), decoded=False, can_direct_write=False),
                self._make_article(self.nzf, offset=19, data=bytearray(b"efg")),
            ],
        )
        # [0] direct, [2] direct, [4], direct
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=True, direct_write=True)
        assert assembler.call_count == 3
        assert self.nzf.assembled is False
        # [1] append, [3], append
        self.nzf.decodetable[1].decoded = True
        self.nzf.decodetable[3].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=False)
        assert assembler.call_count == 5
        self._assert_expected_content(self.nzf, expected)

    def test_force_force_direct(self, assembler):
        """Force the first, then force the last, then direct the gap"""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello")),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), decoded=False),
                self._make_article(self.nzf, offset=10, data=bytearray(b"12345"), decoded=False),
            ],
        )
        # [0] direct
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=False, direct_write=True)
        assert assembler.call_count == 1
        assert self.nzf.assembler_next_index == 1
        # Client restart
        self.nzf.assembler_next_index = 0
        # force: [2] direct
        self.nzf.decodetable[2].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=True, direct_write=True)
        assert assembler.call_count == 2
        assert self.nzf.assembler_next_index == 1
        # [1] direct
        self.nzf.decodetable[1].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        assert assembler.call_count == 3
        self._assert_expected_content(self.nzf, expected)

    def test_crc32_correct_when_gap_filled_out_of_order(self, assembler):
        """Pausing flushes the cache non-contiguously, so later articles are written before an earlier gap article.
        The finalized crc32 must still match the file, which is combined in decodetable order."""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello")),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), decoded=False),
                self._make_article(self.nzf, offset=10, data=bytearray(b"12345")),
            ],
        )
        # Forced flush writes [0] and [2], skipping the not-yet-decoded gap [1]
        Assembler.assemble(self.nzo, self.nzf, file_done=False, allow_non_contiguous=True, direct_write=True)
        assert self.nzf.crc32 is None  # not finalized until file_done
        # Gap article arrives last and the file completes
        self.nzf.decodetable[1].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_finalize_crc32_none_when_article_missing(self, assembler):
        """A file with a missing article crc cannot be verified, so crc32 is None."""
        _data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello")),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world")),
            ],
        )
        Assembler.assemble(self.nzo, self.nzf, file_done=True, allow_non_contiguous=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)
        # A missing per-article crc (e.g. article never decoded) makes the whole-file crc unverifiable
        self.nzf.decodetable[1].crc32 = None
        self.nzf.finalize_crc32()
        assert self.nzf.crc32 is None


class TestDiskspaceCheck:
    """Tests for Assembler.diskspace_check"""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        self.nzo = mock.Mock()
        self.nzo.bytes = int(2 * GIGI)
        self.nzo.bytes_tried = 0
        self.nzo.bytes_par2 = 0
        self.nzo.unpack = True

        self.nzf = mock.Mock()
        self.nzf.bytes = int(0.5 * GIGI)

        self.mock_downloader = mock.Mock()
        self.mock_scheduler = mock.Mock()
        self.mock_notifier = mock.Mock()
        self.mock_emailer = mock.Mock()

        try:
            sabnzbd.Downloader = self.mock_downloader
            sabnzbd.Scheduler = self.mock_scheduler
            sabnzbd.notifier = self.mock_notifier
            sabnzbd.emailer = self.mock_emailer

            with (
                mock.patch("sabnzbd.assembler.diskspace") as self.mock_diskspace,
                mock.patch("sabnzbd.assembler.get_complete_directory") as self.mock_get_complete_dir,
                mock.patch("sabnzbd.assembler.same_device", return_value=False) as self.mock_same_device,
                mock.patch("sabnzbd.assembler.cfg") as self.mock_cfg,
            ):
                # Defaults: plenty of space, no direct_unpack, autoresume on, separate devices
                self.mock_get_complete_dir.return_value = ("/complete", None, True)
                self.mock_cfg.download_free.get_float.return_value = 1 * GIGI
                self.mock_cfg.complete_free.get_float.return_value = 2 * GIGI
                self.mock_cfg.direct_unpack.return_value = False
                self.mock_cfg.fulldisk_autoresume.return_value = True
                self.mock_cfg.download_dir.get_path.return_value = "/download"
                yield
        finally:
            del sabnzbd.Downloader
            del sabnzbd.Scheduler
            del sabnzbd.notifier
            del sabnzbd.emailer

    def _set_diskspace(self, download_free_gb: float, complete_free_gb: float, complete_path: str = "/complete"):
        self.mock_diskspace.return_value = (
            Diskspace(path="/download", free=download_free_gb),
            Diskspace(path=complete_path, free=complete_free_gb),
        )

    def test_download_dir_full(self):
        """Pause when download_dir has insufficient space"""
        # download_free=1GiB, nzf.bytes=0.5GiB => required = 1.5 GiB, free = 1.0 GiB
        self._set_diskspace(download_free_gb=1.0, complete_free_gb=50.0)
        Assembler.diskspace_check(self.nzo, self.nzf)

        expected_required = (1 * GIGI + self.nzf.bytes) / GIGI
        self.mock_downloader.pause.assert_called_once()
        self.mock_scheduler.plan_diskspace_resume.assert_called_once_with("/download", expected_required)

    def test_complete_dir_full_direct_unpack(self):
        """Pause when complete_dir is full during direct_unpack"""
        self._set_diskspace(download_free_gb=50.0, complete_free_gb=1.0)
        self.mock_cfg.direct_unpack.return_value = True

        Assembler.diskspace_check(self.nzo, self.nzf)

        expected_required = (2 * GIGI) / GIGI
        self.mock_downloader.pause.assert_called_once()
        self.mock_scheduler.plan_diskspace_resume.assert_called_once_with("/complete", expected_required)

    def test_complete_dir_full_near_completion(self):
        """Pause when complete_dir is full and download is >90% done"""
        self.nzo.bytes_tried = int(self.nzo.bytes * 0.96)
        self.nzo.bytes_par2 = 0
        self._set_diskspace(download_free_gb=50.0, complete_free_gb=1.0)

        Assembler.diskspace_check(self.nzo, self.nzf)

        expected_required = (2 * GIGI + self.nzo.bytes) / GIGI  # (complete_free + nzo.bytes)
        self.mock_downloader.pause.assert_called_once()
        self.mock_scheduler.plan_diskspace_resume.assert_called_once_with("/complete", expected_required)

    def test_complete_dir_no_check_below_90_percent(self):
        """No complete_dir check when download is below 90% and not direct_unpack"""
        self.nzo.bytes_tried = int(self.nzo.bytes * 0.50)
        self._set_diskspace(download_free_gb=50.0, complete_free_gb=0.1)

        Assembler.diskspace_check(self.nzo, self.nzf)

        self.mock_downloader.pause.assert_not_called()
        self.mock_scheduler.plan_diskspace_resume.assert_not_called()

    def test_complete_dir_custom_path(self):
        """full_dir is the actual path when complete_dir differs from default"""
        custom_path = "/custom/complete"
        self.mock_get_complete_dir.return_value = (custom_path, None, True)
        self._set_diskspace(download_free_gb=50.0, complete_free_gb=1.0, complete_path=custom_path)
        self.mock_cfg.direct_unpack.return_value = True

        Assembler.diskspace_check(self.nzo, self.nzf)

        self.mock_downloader.pause.assert_called_once()
        self.mock_scheduler.plan_diskspace_resume.assert_called_once_with(custom_path, mock.ANY)

    def test_enough_space(self):
        """No action when both dirs have sufficient space"""
        self._set_diskspace(download_free_gb=50.0, complete_free_gb=50.0)

        Assembler.diskspace_check(self.nzo, self.nzf)

        self.mock_downloader.pause.assert_not_called()
        self.mock_scheduler.plan_diskspace_resume.assert_not_called()
        self.mock_notifier.send_notification.assert_not_called()
        self.mock_emailer.diskfull_mail.assert_not_called()

    def test_autoresume_disabled(self):
        """plan_diskspace_resume not called when fulldisk_autoresume is off"""
        self._set_diskspace(download_free_gb=1.0, complete_free_gb=50.0)
        self.mock_cfg.fulldisk_autoresume.return_value = False

        Assembler.diskspace_check(self.nzo, self.nzf)

        self.mock_downloader.pause.assert_called_once()
        self.mock_scheduler.plan_diskspace_resume.assert_not_called()

    def test_download_dir_full_notifications(self):
        """Verify notifications and email are sent on disk full"""
        self._set_diskspace(download_free_gb=1.0, complete_free_gb=50.0)

        Assembler.diskspace_check(self.nzo, self.nzf)

        self.mock_notifier.send_notification.assert_called_once()
        self.mock_emailer.diskfull_mail.assert_called_once()


class DiskspaceCheckResult(NamedTuple):
    paused: bool
    full_dir: Optional[str]
    required_space: Optional[float]


class TestDiskspaceCheckScenarios:
    """Assembler.diskspace_check across post-processing options and single/multi-device layouts."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        self.mock_downloader = mock.Mock()
        self.mock_scheduler = mock.Mock()

        try:
            sabnzbd.Downloader = self.mock_downloader
            sabnzbd.Scheduler = self.mock_scheduler
            sabnzbd.notifier = mock.Mock()
            sabnzbd.emailer = mock.Mock()

            with (
                mock.patch("sabnzbd.assembler.diskspace") as self.mock_diskspace,
                mock.patch("sabnzbd.assembler.get_complete_directory") as self.mock_get_complete_dir,
                mock.patch("sabnzbd.assembler.same_device") as self.mock_same_device,
                mock.patch("sabnzbd.assembler.cfg") as self.mock_cfg,
            ):
                self.mock_get_complete_dir.return_value = ("/complete", None, True)
                self.mock_cfg.fulldisk_autoresume.return_value = True
                self.mock_cfg.download_dir.get_path.return_value = "/download"
                yield
        finally:
            del sabnzbd.Downloader
            del sabnzbd.Scheduler
            del sabnzbd.notifier
            del sabnzbd.emailer

    def _run_check(
        self,
        job_gb: float,
        progress: float,
        pp: int,
        same_device: bool,
        disk_free_gb: float = 120.0,
        complete_disk_free_gb: Optional[float] = None,
        complete_free_gb: float = 5.0,
        download_free_gb: float = 1.0,
        par2_gb: float = 0.0,
        direct_unpack: bool = False,
        file_gb: float = 0.05,
    ) -> DiskspaceCheckResult:
        """Run one check against a modeled disk layout.

        disk_free_gb is the free space on the download device *before* the job started; the bytes
        downloaded so far are subtracted from it. On a single-device layout the complete dir sees
        that same reduced figure, because the partially downloaded job is already occupying it."""
        nzo = mock.Mock()
        nzo.bytes = int(job_gb * GIGI)
        nzo.bytes_par2 = int(par2_gb * GIGI)
        nzo.bytes_tried = int((nzo.bytes - nzo.bytes_par2) * progress)
        nzo.repair, nzo.unpack, nzo.delete = pp_to_opts(pp)

        nzf = mock.Mock()
        nzf.bytes = int(file_gb * GIGI)

        download_dir_free = disk_free_gb - nzo.bytes_tried / GIGI
        if same_device:
            complete_dir_free = download_dir_free
        else:
            complete_dir_free = disk_free_gb if complete_disk_free_gb is None else complete_disk_free_gb

        self.mock_diskspace.return_value = (
            Diskspace(path="/download", free=download_dir_free),
            Diskspace(path="/download" if same_device else "/complete", free=complete_dir_free),
        )
        self.mock_same_device.return_value = same_device
        self.mock_cfg.download_free.get_float.return_value = download_free_gb * GIGI
        self.mock_cfg.complete_free.get_float.return_value = complete_free_gb * GIGI
        self.mock_cfg.direct_unpack.return_value = direct_unpack

        Assembler.diskspace_check(nzo, nzf)

        paused = self.mock_downloader.pause.called
        resume_call = self.mock_scheduler.plan_diskspace_resume.call_args
        return DiskspaceCheckResult(
            paused=paused,
            full_dir=resume_call.args[0] if resume_call else None,
            required_space=resume_call.args[1] if resume_call else None,
        )

    @pytest.mark.parametrize("pp", [0, 1, 2, 3])
    @pytest.mark.parametrize("same_device", [True, False])
    def test_job_size_required_only_when_unpacking_or_crossing_devices(self, pp, same_device):
        """Room for the whole job is needed when it gets unpacked (pp 2 and 3) or when the move to
        complete_dir crosses devices. A Download-only or Repair-only job on one device does not."""
        result = self._run_check(
            job_gb=61.0,
            progress=0.95,
            pp=pp,
            same_device=same_device,
            disk_free_gb=118.0,
            complete_disk_free_gb=60.0,
        )

        if pp >= 2 or not same_device:
            assert result.paused is True
            assert result.required_space == pytest.approx(5.0 + 61.0)
        else:
            assert result.paused is False

    def test_reported_issue_scenario(self):
        """#3531: 61GB job, 118GB free at the start, 5GB complete_free and all unpacking off.
        Used to pause at ~90% because the bytes already downloaded were deducted from
        complete_dir.free while the requirement still asked for the whole job on top of them."""
        result = self._run_check(job_gb=61.0, progress=0.91, pp=0, same_device=True, disk_free_gb=118.0)

        assert result.paused is False
        # Free space is below the old requirement, but well above the reserve it now has to meet
        assert 5.0 < self.mock_diskspace.return_value[1].free < 5.0 + 61.0

    @pytest.mark.parametrize(
        "scenario, expect_full_dir, expect_required",
        [
            pytest.param(
                # Moving to another device really does copy the whole job, so it is still required
                {"job_gb": 61.0, "progress": 0.91, "pp": 0, "same_device": False, "complete_disk_free_gb": 60.0},
                "/complete",
                66.0,
                id="download_only_separate_devices",
            ),
            pytest.param(
                # Unpacking writes a second copy alongside the archives, also on one device
                {"job_gb": 61.0, "progress": 0.95, "pp": 2, "same_device": True, "disk_free_gb": 118.0},
                "/download",
                66.0,
                id="unpack_single_device",
            ),
            pytest.param(
                {"job_gb": 40.0, "progress": 1.0, "pp": 0, "same_device": True, "disk_free_gb": 80.0},
                None,
                None,
                id="download_only_single_device_fully_downloaded",
            ),
            pytest.param(
                {"job_gb": 61.0, "progress": 0.99, "pp": 2, "same_device": False, "complete_disk_free_gb": 70.0},
                None,
                None,
                id="separate_device_complete_dir_large_enough",
            ),
            pytest.param(
                # 40GB of articles plus the 5GB threshold would fit in the 52GB available, but the
                # par2 blocks are counted too even though they are usually never downloaded
                {
                    "job_gb": 50.0,
                    "par2_gb": 10.0,
                    "progress": 0.95,
                    "pp": 1,
                    "same_device": False,
                    "complete_disk_free_gb": 52.0,
                },
                "/complete",
                55.0,
                id="par2_bytes_included_in_requirement",
            ),
            pytest.param(
                # cfg.direct_unpack is global, but DirectUnpacker also requires nzo.unpack, so a
                # pp=0 job never direct unpacks and must not take the direct_unpack branch
                {
                    "job_gb": 61.0,
                    "progress": 0.95,
                    "pp": 0,
                    "same_device": False,
                    "complete_disk_free_gb": 8.0,
                    "direct_unpack": True,
                },
                "/complete",
                66.0,
                id="direct_unpack_ignored_for_download_only_job",
            ),
            pytest.param(
                # A job that does direct unpack is checked against the reserve alone, from the
                # start of the download rather than at 90%
                {
                    "job_gb": 61.0,
                    "progress": 0.10,
                    "pp": 2,
                    "same_device": False,
                    "complete_disk_free_gb": 4.0,
                    "direct_unpack": True,
                },
                "/complete",
                5.0,
                id="direct_unpack_checks_reserve_only",
            ),
            pytest.param(
                # complete_free defaults to empty (0), but the check still applies because the job
                # size alone makes required_space non-zero
                {
                    "job_gb": 61.0,
                    "progress": 0.95,
                    "pp": 0,
                    "same_device": False,
                    "complete_free_gb": 0.0,
                    "complete_disk_free_gb": 60.0,
                },
                "/complete",
                61.0,
                id="complete_free_unset_separate_devices",
            ),
            pytest.param(
                # Nothing left to require, so the complete_dir check is skipped entirely
                {
                    "job_gb": 61.0,
                    "progress": 0.95,
                    "pp": 0,
                    "same_device": True,
                    "complete_free_gb": 0.0,
                    "disk_free_gb": 60.0,
                },
                None,
                None,
                id="complete_free_unset_single_device",
            ),
            pytest.param(
                # Both dirs are short: download_dir wins and the required_space handed to the
                # scheduler is the much smaller download_dir figure
                {
                    "job_gb": 61.0,
                    "progress": 0.95,
                    "pp": 2,
                    "same_device": False,
                    "disk_free_gb": 58.0,
                    "complete_disk_free_gb": 1.0,
                    "download_free_gb": 1.0,
                    "file_gb": 0.05,
                },
                "/download",
                1.05,
                id="download_dir_full_takes_precedence",
            ),
        ],
    )
    def test_diskspace_scenarios(self, scenario, expect_full_dir, expect_required):
        result = self._run_check(**scenario)

        assert result.paused is (expect_full_dir is not None)
        assert result.full_dir == expect_full_dir
        if expect_required is None:
            assert result.required_space is None
        else:
            assert result.required_space == pytest.approx(expect_required)


class TestWriterCache:
    """Handles are cached so an article does not cost an open and a close, which is the
    dominant syscall cost of a write at the rates this is built for. The risks are all
    about lifetime: a leaked handle, or one closed while a thread is still writing."""

    @pytest.fixture
    def assembler(self):
        try:
            sabnzbd.Assembler = Assembler()
            yield sabnzbd.Assembler
        finally:
            sabnzbd.Assembler.close_all_writers()
            del sabnzbd.Assembler

    @staticmethod
    def make_nzf(tmp_path, name):
        nzf = mock.Mock()
        nzf.nzf_id = name
        nzf.filepath = str(tmp_path / name)
        nzf.writer = None
        return nzf

    def test_the_same_handle_is_reused(self, assembler, tmp_path):
        nzf = self.make_nzf(tmp_path, "reused")
        first = assembler.get_writer(nzf)
        assert assembler.get_writer(nzf) is first
        assert nzf.writer is first

    def test_each_file_gets_its_own_handle(self, assembler, tmp_path):
        one = self.make_nzf(tmp_path, "one")
        two = self.make_nzf(tmp_path, "two")
        assert assembler.get_writer(one) is not assembler.get_writer(two)

    def test_close_writer_releases_it(self, assembler, tmp_path):
        nzf = self.make_nzf(tmp_path, "closed")
        writer = assembler.get_writer(nzf)
        assembler.close_writer(nzf)
        assert nzf.writer is None
        assert writer.closed is True
        assert nzf.nzf_id not in assembler.open_writers

    def test_close_writer_is_safe_without_one(self, assembler, tmp_path):
        assembler.close_writer(self.make_nzf(tmp_path, "never_opened"))

    def test_a_finished_file_gives_its_handle_back(self, assembler, tmp_path):
        """clear_ready_bytes runs as a file completes, just before post-processing
        reads, renames or deletes it"""
        nzf = self.make_nzf(tmp_path, "finished")
        writer = assembler.get_writer(nzf)
        assembler.clear_ready_bytes(nzf)
        assert nzf.writer is None
        assert writer.closed is True

    def test_the_cache_is_bounded(self, assembler, tmp_path):
        """Handles are shared with every socket the downloader holds, so the cache
        cannot be allowed to grow with the queue"""
        files = [self.make_nzf(tmp_path, "file%d" % index) for index in range(ASSEMBLER_MAX_OPEN_WRITERS + 10)]
        for nzf in files:
            assembler.get_writer(nzf)

        assert len(assembler.open_writers) == ASSEMBLER_MAX_OPEN_WRITERS
        # Oldest evicted, newest kept
        assert files[0].writer is None
        assert files[-1].writer is not None

    def test_eviction_drops_rather_than_closes(self, assembler, tmp_path):
        """A thread may be inside a write on the handle being evicted. Closing it would
        turn that write into an error; dropping the reference lets it close once the
        write returns."""
        victim = self.make_nzf(tmp_path, "victim")
        held = assembler.get_writer(victim)  # a caller still holding it, mid-write

        for index in range(ASSEMBLER_MAX_OPEN_WRITERS + 1):
            assembler.get_writer(self.make_nzf(tmp_path, "filler%d" % index))

        assert victim.writer is None, "should have been evicted"
        assert held.closed is False, "evicting must not close a handle in use"
        # And it still works for whoever is holding it
        assert held.write(b"still valid", 0) == 11

    def test_use_keeps_a_handle_from_being_evicted(self, assembler, tmp_path):
        """Least recently used, so a file being actively written is not the one dropped"""
        busy = self.make_nzf(tmp_path, "busy")
        assembler.get_writer(busy)

        for index in range(ASSEMBLER_MAX_OPEN_WRITERS - 1):
            assembler.get_writer(self.make_nzf(tmp_path, "other%d" % index))
            assembler.get_writer(busy)

        assembler.get_writer(self.make_nzf(tmp_path, "one_too_many"))
        assert busy.writer is not None

    def test_close_all_writers(self, assembler, tmp_path):
        files = [self.make_nzf(tmp_path, "shutdown%d" % index) for index in range(5)]
        writers = [assembler.get_writer(nzf) for nzf in files]
        assembler.close_all_writers()

        assert not assembler.open_writers
        assert all(nzf.writer is None for nzf in files)
        assert all(writer.closed for writer in writers)

    def test_concurrent_get_writer_returns_one_handle(self, assembler, tmp_path):
        """Receive threads and the assembler thread both reach for the same file"""
        nzf = self.make_nzf(tmp_path, "contended")
        seen = []
        barrier = threading.Barrier(8)

        def fetch():
            barrier.wait()
            seen.append(assembler.get_writer(nzf))

        threads = [threading.Thread(target=fetch) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len({id(writer) for writer in seen}) == 1
