#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
from sabnzbd.nzb import Article, NzbFile, NzbObject
from tests.testhelper import *


class TestAssembler:
    @pytest.fixture
    def assembler(self, tmp_path):
        """Prepare a sabnzbd assembler, tmp_path is used because C libraries require a real filesystem."""

        try:
            sabnzbd.Downloader = SimpleNamespace(paused=False)
            sabnzbd.ArticleCache = SimpleNamespace()

            # Create a minimal NzbObject / NzbFile
            self.nzo = NzbObject("test.nzb")

            admin_path = str(tmp_path / "admin")

            with mock.patch.object(
                NzbObject,
                "admin_path",
                new_callable=mock.PropertyMock,
            ) as admin_path_mock:
                admin_path_mock.return_value = admin_path

                # Make sure the file can prepare a filepath
                self.nzo.download_path = str(tmp_path / "download")
                self.nzo.files = []
                self.nzo.first_articles = []

                # Ensure directories exist
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
                # Setup so that prepare_filepath() will return a path
                self.nzf.type = "yenc"
                self.nzf.filename_checked = True
                self.nzf.import_finished = True

                # Ensure filepath is created
                assert self.nzf.prepare_filepath() is not None

                # Clear the state for the test to manipulate
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
        return article, data

    def _make_request(
        self,
        nzf: NzbFile,
        articles: list[tuple[Article, bytearray]],
    ):
        data = []
        for article, raw in articles:
            nzf.decodetable.append(article)
            data.append(raw)
        expected = b"".join(data)
        nzf.bytes = len(expected)
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=data)

        for article, _ in articles:
            article.file_size = nzf.bytes

        return data, expected

    @staticmethod
    def _assert_expected_content(nzf: NzbFile, expected: bytes):
        with open(nzf.filepath, "rb") as f:
            content = f.read()
        assert content == expected
        assert len(nzf.decodetable) == nzf.assembler_next_index

    def test_assemble_direct_write(self, assembler):
        """All articles support direct_write; data should be written at offsets."""
        data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello"), can_direct_write=True),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), can_direct_write=True),
            ],
        )
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)
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
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_direct_append_direct_append(self, assembler):
        """
        Start in direct_write, but encounter an article that cannot be direct-written.
        Assembler should abort direct_write and switch to append mode.
        Then the cache writes the final piece.
        Finally, the assembler writes the previously missing piece.
        """
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
        # First two are written
        Assembler.assemble(self.nzo, self.nzf, file_done=False, force=False, direct_write=True)
        assert assembler.call_count == 2
        # Simulate the cache writing the 4th
        article = self.nzf.decodetable[3]
        article.decoded = True
        Assembler.assemble_article(article, bytearray(data[3]))
        assert assembler.call_count == 3
        # Final by assembler writing the 3rd
        article = self.nzf.decodetable[2]
        article.decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)
        assert assembler.call_count == 4
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_direct_write_aborted_to_append_second_attempt(self, assembler):
        """
        Start in direct_write, but encounter an article that cannot be direct-written.
        Assembler should abort direct_write and switch to append mode.
        """
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
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=data)
        Assembler.assemble(self.nzo, self.nzf, file_done=False, force=False, direct_write=True)
        # Second attempt should be direct via pwrite
        assert self.nzf.decodetable[2].on_disk is False
        self.nzf.decodetable[2].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_direct_write_second_attempt(self, assembler):
        """Verify that after an initial append-only assemble, a later assemble
        with direct_write enabled patches the remaining article via pwrite."""
        data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"hello"), can_direct_write=False),
                self._make_article(self.nzf, offset=5, data=bytearray(b"world"), decoded=False, can_direct_write=True),
            ],
        )
        Assembler.assemble(self.nzo, self.nzf, file_done=False, force=False, direct_write=False)
        # Second attempt should be direct via pwrite
        self.nzf.decodetable[1].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)
        self._assert_expected_content(self.nzf, expected)

    def test_assemble_append_only(self, assembler):
        """direct_write=False should use pure append mode."""
        data, expected = self._make_request(
            self.nzf,
            [
                self._make_article(self.nzf, offset=0, data=bytearray(b"abcd"), can_direct_write=False),
                self._make_article(self.nzf, offset=0, data=bytearray(b"efg"), can_direct_write=False),
            ],
        )
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=False)
        self._assert_expected_content(self.nzf, expected)
