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
                    raw_article_db=[[None, 10]],
                    file_bytes=10,
                    nzo=self.nzo,
                )
                self.nzo.files.append(self.nzf)
                # Setup so that prepare_filepath() will return a path
                self.nzf.type = "yenc"
                self.nzf.filename_checked = True
                self.nzf.import_finished = True

                # Ensure filepath is created
                assert self.nzf.prepare_filepath() is not None

                with mock.patch.object(
                    Assembler, "write_at_offset", wraps=Assembler.write_at_offset
                ) as mocked_write_at_offset:
                    yield mocked_write_at_offset
        finally:
            # Reset values after test
            del sabnzbd.Downloader
            del sabnzbd.ArticleCache

    def _make_article(
        self, nzf: NzbFile, offset: int, size: int, decoded: bool = True, can_direct_write: bool = True
    ) -> Article:
        art = Article("msgid", size, nzf)
        art.decoded = decoded
        art.data_begin = offset
        art.data_size = size if can_direct_write else None
        art.file_size = nzf.bytes
        art.crc32 = 0x1234
        return art

    def test_assemble_direct_write(self, assembler):
        """All articles support direct_write; data should be written at offsets."""
        self.nzf.decodetable = [
            self._make_article(self.nzf, offset=0, size=5, can_direct_write=True),
            self._make_article(self.nzf, offset=5, size=5, can_direct_write=True),
        ]
        data = [b"hello", b"world"]
        expected = b"".join(data)
        self.nzf.bytes = len(expected)
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=data)
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)

        # File contents should match the two pieces written at their offsets
        with open(self.nzf.filepath, "rb") as f:
            content = f.read()
        assert content == expected

        # Both articles should be marked on_disk
        for article in self.nzf.decodetable:
            assert article.on_disk is True

        # File should be marked assembled
        assert self.nzf.assembled is True

    def test_assemble_direct_write_aborted_to_append(self, assembler):
        """
        Start in direct_write, but encounter an article that cannot be direct-written.
        Assembler should abort direct_write and switch to append mode.
        """
        mocked_write_at_offset = assembler
        # Only the first article supports direct_write
        self.nzf.decodetable = [
            self._make_article(self.nzf, offset=0, size=5, can_direct_write=True),
            self._make_article(self.nzf, offset=5, size=5, can_direct_write=False),
            self._make_article(self.nzf, offset=10, size=5, can_direct_write=True),
        ]
        data = [b"hello", b"world", b"12345"]
        expected = b"".join(data)
        self.nzf.bytes = len(expected)
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=data)

        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)

        # First write should be via pwrite (direct_write)
        # Second via append write
        # Third by pwrite because it was originally opened for direct write
        assert mocked_write_at_offset.call_count == 2

        with open(self.nzf.filepath, "rb") as f:
            content = f.read()
        assert content == expected

    def test_assemble_direct_write_aborted_to_append_second_attempt(self, assembler):
        """
        Start in direct_write, but encounter an article that cannot be direct-written.
        Assembler should abort direct_write and switch to append mode.
        """
        mocked_write_at_offset = assembler
        # Only the first article supports direct_write
        self.nzf.decodetable = [
            self._make_article(self.nzf, offset=0, size=5, can_direct_write=True),
            self._make_article(self.nzf, offset=5, size=5, can_direct_write=False),
            self._make_article(self.nzf, offset=10, size=5, decoded=False, can_direct_write=False),
        ]
        data = [b"hello", b"world", b"12345"]
        expected = b"".join(data)
        self.nzf.bytes = len(expected)
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=data)
        Assembler.assemble(self.nzo, self.nzf, file_done=False, force=False, direct_write=True)

        # Second attempt should be direct via pwrite
        assert self.nzf.decodetable[2].on_disk is False
        self.nzf.decodetable[2].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)

        # First write should be via pwrite (direct_write), second via append write
        assert mocked_write_at_offset.call_count == 1

        with open(self.nzf.filepath, "rb") as f:
            content = f.read()
        assert content == expected

    def test_assemble_direct_write_second_attempt(self, assembler):
        """Verify that after an initial append-only assemble, a later assemble
        with direct_write enabled patches the remaining article via pwrite."""
        mocked_write_at_offset = assembler
        self.nzf.decodetable = [
            self._make_article(self.nzf, offset=0, size=5, can_direct_write=False),
            self._make_article(self.nzf, offset=5, size=5, decoded=False, can_direct_write=True),
        ]
        data = [b"hello", b"world"]
        expected = b"".join(data)
        self.nzf.bytes = len(expected)
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=data)
        Assembler.assemble(self.nzo, self.nzf, file_done=False, force=False, direct_write=False)

        # Second attempt should be direct via pwrite
        self.nzf.decodetable[1].decoded = True
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=True)

        # First write should be via write (append), second via pwrite (direct)
        assert mocked_write_at_offset.call_count == 1

        with open(self.nzf.filepath, "rb") as f:
            content = f.read()
        assert content == expected

    def test_assemble_append_only(self, assembler):
        """direct_write=False should use pure append mode."""
        self.nzf.decodetable = [
            self._make_article(self.nzf, offset=0, size=4, can_direct_write=False),
            self._make_article(self.nzf, offset=0, size=3, can_direct_write=False),
        ]
        data = [b"abcd", b"efg"]
        expected = b"".join(data)
        self.nzf.bytes = len(expected)
        sabnzbd.ArticleCache.load_article = mock.Mock(side_effect=data)
        Assembler.assemble(self.nzo, self.nzf, file_done=True, force=False, direct_write=False)

        with open(self.nzf.filepath, "rb") as f:
            content = f.read()
        assert content == expected
