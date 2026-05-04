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

from types import SimpleNamespace
from zlib import crc32

from sabnzbd.assembler import Assembler
from sabnzbd.constants import GIGI
from sabnzbd.filesystem import Diskspace
from sabnzbd.nzb import Article, NzbFile, NzbObject
from tests.testhelper import *


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

    def test_assemble_direct_write(self, assembler):
        """Pure direct write mode"""
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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
        data, expected = self._make_request(
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


class TestDiskspaceCheck:
    """Tests for Assembler.diskspace_check"""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        self.nzo = mock.Mock()
        self.nzo.bytes = int(2 * GIGI)
        self.nzo.bytes_tried = 0
        self.nzo.bytes_par2 = 0

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
                mock.patch("sabnzbd.assembler.cfg") as self.mock_cfg,
            ):
                # Defaults: plenty of space, no direct_unpack, autoresume on
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
        """Pause when complete_dir is full and download is >95% done"""
        self.nzo.bytes_tried = int(self.nzo.bytes * 0.96)
        self.nzo.bytes_par2 = 0
        self._set_diskspace(download_free_gb=50.0, complete_free_gb=1.0)

        Assembler.diskspace_check(self.nzo, self.nzf)

        expected_required = (2 * GIGI + self.nzo.bytes) / GIGI  # (complete_free + nzo.bytes)
        self.mock_downloader.pause.assert_called_once()
        self.mock_scheduler.plan_diskspace_resume.assert_called_once_with("/complete", expected_required)

    def test_complete_dir_no_check_below_95_percent(self):
        """No complete_dir check when download is below 95% and not direct_unpack"""
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
