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
tests.test_decoder- Testing functions in decoder.py
"""

import binascii
import os
import pytest
import threading
from collections import Counter
from datetime import datetime
from io import BytesIO
from typing import Optional

from random import randint
from unittest import mock

import sabctools
import sabnzbd.decoder as decoder
from sabnzbd.nzb import Article, NzbFile, NzbObject
from tests.testhelper import SAB_CACHE_DIR


def uu(data: bytes):
    """Uuencode data and insert a period if necessary"""
    line = binascii.b2a_uu(data).rstrip(b"\n")

    # Dot stuffing
    if line.startswith(b"."):
        return b"." + line

    return line


LINES_DATA = [os.urandom(45) for _ in range(32)]
VALID_UU_LINES = [uu(data) for data in LINES_DATA]

END_DATA = os.urandom(randint(1, 45))
VALID_UU_END = [
    uu(END_DATA),
    b"`",
    b"end",
]


class TestUuDecoder:
    def _generate_msg_part(
        self,
        part: str,
        insert_empty_line: bool = True,
        insert_excess_empty_lines: bool = False,
        insert_headers: bool = False,
        insert_end: bool = True,
        insert_dot_stuffing_line: bool = False,
        begin_line: bytes = b"begin 644 My Favorite Open Source Movie.mkv",
    ):
        """Generate message parts. Part may be one of 'begin', 'middle', or 'end' for multipart
        messages, or 'single' for a singlepart message. All uu payload is taken from VALID_UU_*.

        Returns Article with a random id and lowest_partnum correctly set, socket-style raw
        data, and the expected result of uu decoding for the generated message.
        """
        article_id = "test@host" + os.urandom(8).hex() + ".sab"
        # Mock an nzf so results from hashing and filename handling can be stored
        mock_nzf = mock.Mock()
        article = Article(article_id, randint(4321, 54321), mock_nzf)
        article.lowest_partnum = True if part in ("begin", "single") else False

        # Store the message data and the expected decoding result
        data = []
        result = []

        # Always start with the response code line
        data.append(b"222 0 <" + bytes(article_id, encoding="ascii") + b">")

        if insert_empty_line:
            # Only insert other headers if there's an empty line
            if insert_headers:
                data.extend([b"x-hoop: is uitgestelde teleurstelling", b"Another-Header: Sure"])

            # Insert the empty line between response code and body
            data.append(b"")

        if insert_excess_empty_lines:
            data.extend([b"", b""])

        # Insert uu data into the body
        if part in ("begin", "single"):
            data.append(begin_line)

        if part in ("begin", "middle", "single"):
            size = randint(4, len(VALID_UU_LINES) - 1)
            data.extend(VALID_UU_LINES[:size])
            result.extend(LINES_DATA[:size])

            if insert_dot_stuffing_line:
                data.append(uu(b"\0" * 14))
                result.append(b"\0" * 14)

        if part in ("end", "single"):
            if insert_end:
                data.extend(VALID_UU_END)
                result.append(END_DATA)

        # Signal the end of the message with a dot on a line of its own
        data.append(b".\r\n")

        # Join the data with \r\n line endings, just like we get from socket reads
        data = b"\r\n".join(data)
        # Concatenate expected result
        result = b"".join(result)

        return article, bytearray(data), result

    @staticmethod
    def _response(raw_data: bytes) -> sabctools.NNTPResponse:
        dec = sabctools.Decoder(len(raw_data))
        reader = BytesIO(raw_data)
        reader.readinto(dec)
        dec.process(len(raw_data))
        return next(dec)

    @pytest.mark.parametrize(
        "raw_data",
        [
            b"222 0 <foo@bar>\r\n.\r\n",
            b"222 0 <foo@bar>\r\n\r\n.\r\n",
            b"222 0 <foo@bar>\r\nfoobar\r\n.\r\n",  # Plenty of list items, but (too) few actual lines
            b"222 0 <foo@bar>\r\nX-Too-Short: yup\r\n.\r\n",
        ],
    )
    def test_short_data(self, raw_data):
        mock_nzf = mock.Mock()
        article = Article("foo@bar", 4321, mock_nzf)
        with pytest.raises(decoder.BadUu):
            assert decoder.decode_uu(article, self._response(raw_data))

    @pytest.mark.parametrize(
        "raw_data",
        [
            b"222 0 <foo@bar>\r\n\r\n",  # Missing altogether
            b"222 0 <foo@bar>\r\n\r\nbeing\r\n",  # Typo in 'begin'
            b"222 0 <foo@bar>\r\n\r\nx-header: begin 644 foobar\r\n",  # Not at start of the line
            b"666 0 <foo@bar>\r\nbegin\r\n",  # No empty line + wrong response code
            b"OMG 0 <foo@bar>\r\nbegin\r\n",  # No empty line + invalid response code
            b"222 0 <foo@bar>\r\nbegin\r\n",  # No perms
            b"222 0 <foo@bar>\r\nbegin ABC DEF\r\n",  # Permissions not octal
            b"222 0 <foo@bar>\r\nbegin 755\r\n",  # No filename
            b"222 0 <foo@bar>\r\nbegin 644 \t \t\r\n",  # Filename empty after stripping
        ],
    )
    def test_missing_uu_begin(self, raw_data):
        mock_nzf = mock.Mock()
        article = Article("foo@bar", 1234, mock_nzf)
        article.lowest_partnum = True
        filler = b"\r\n" * 4
        with pytest.raises(decoder.BadUu):
            raw_data = bytearray(raw_data)
            raw_data.extend(filler)
            raw_data.extend(b".\r\n")
            assert decoder.decode_uu(article, self._response(raw_data))

    @pytest.mark.parametrize("insert_empty_line", [True, False])
    @pytest.mark.parametrize("insert_excess_empty_lines", [True, False])
    @pytest.mark.parametrize("insert_headers", [True, False])
    @pytest.mark.parametrize("insert_end", [True, False])
    @pytest.mark.parametrize("insert_dot_stuffing_line", [True, False])
    @pytest.mark.parametrize(
        "begin_line",
        [
            b"begin 644 nospace.bin",
            b"begin 444 filename with spaces.txt",
            b"BEGIN 644 foobar",
            b"begin 0755 shell.sh",
        ],
    )
    def test_singlepart(
        self,
        insert_empty_line,
        insert_excess_empty_lines,
        insert_headers,
        insert_end,
        insert_dot_stuffing_line,
        begin_line,
    ):
        """Test variations of a sane single part nzf with proper uu-encoded data"""
        # Generate a singlepart message
        article, raw_data, expected_result = self._generate_msg_part(
            "single",
            insert_empty_line,
            insert_excess_empty_lines,
            insert_headers,
            insert_end,
            insert_dot_stuffing_line,
            begin_line,
        )
        assert decoder.decode_uu(article, self._response(raw_data)) == expected_result
        assert article.nzf.filename_checked

    @pytest.mark.parametrize("insert_empty_line", [True, False])
    def test_multipart(self, insert_empty_line):
        """Test a simple multipart nzf"""

        # Generate and process a multipart msg
        decoded_data = expected_data = b""
        for part in ("begin", "middle", "middle", "end"):
            article, data, result = self._generate_msg_part(part, insert_empty_line, False, False, True)
            decoded_data += decoder.decode_uu(article, self._response(data))
            expected_data += result

        # Verify results
        assert decoded_data == expected_data
        assert article.nzf.filename_checked

    @pytest.mark.parametrize(
        "bad_data",
        [
            VALID_UU_LINES[-1][:10] + bytes("ваше здоровье", encoding="utf8") + VALID_UU_LINES[-1][-10:],  # Non-ascii
        ],
        ids=["non_ascii"],
    )
    def test_broken_uu(self, bad_data):
        mock_nzf = mock.Mock()
        article = Article("foo@bar", 4321, mock_nzf)
        article.lowest_partnum = False
        filler = b"\r\n".join(VALID_UU_LINES[:4]) + b"\r\n"
        with pytest.raises(decoder.BadData):
            assert decoder.decode_uu(
                article, self._response(bytearray(b"222 0 <foo@bar>\r\n" + filler + bad_data + b"\r\n.\r\n"))
            )


class TestYencBlockCrcs:
    @staticmethod
    def _response(payload: bytes, begin: int, block_size: int) -> sabctools.NNTPResponse:
        encoded, crc = sabctools.yenc_encode(payload)
        raw_data = (
            b"222 0 <foo@bar>\r\n"
            + f"=ybegin part=1 line=128 size={begin + len(payload)} name=foo.bin\r\n".encode()
            + f"=ypart begin={begin + 1} end={begin + len(payload)}\r\n".encode()
            + encoded
            + f"\r\n=yend size={len(payload)} part=1 pcrc32={crc:08x}\r\n.\r\n".encode()
        )
        dec = sabctools.Decoder(len(raw_data))
        dec.expect(None, block_size=block_size)
        BytesIO(raw_data).readinto(dec)
        dec.process(len(raw_data))
        return next(dec)

    def test_the_pieces_are_kept_on_the_article(self):
        payload = bytes(range(256)) * 4
        article = Article("foo@bar", 1234, mock.Mock(lock=threading.RLock(), yenc_sizes=Counter(), overwritten=[]))
        decoder.decode_yenc(article, self._response(payload, 100, 256))
        assert article.block_size == 256
        assert list(article.block_crcs) == [
            binascii.crc32(payload[:156]),
            binascii.crc32(payload[156:412]),
            binascii.crc32(payload[412:668]),
            binascii.crc32(payload[668:924]),
            binascii.crc32(payload[924:]),
        ]

    def test_without_a_block_size_there_are_none(self):
        article = Article("foo@bar", 1234, mock.Mock(lock=threading.RLock(), yenc_sizes=Counter(), overwritten=[]))
        decoder.decode_yenc(article, self._response(b"\x01" * 100, 0, 0))
        assert article.block_size == 0
        assert article.block_crcs is None


@pytest.mark.usefixtures("clean_cache_dir")
@pytest.mark.config({"download_dir": SAB_CACHE_DIR})
class TestArticleOfAnotherFile:
    """A server can return another post's article under the Message-ID that was asked for,
    with a valid CRC of its own, see #3691"""

    PART = 1000
    PARTS = 10
    # The file the colliding article really belongs to
    OTHER_SIZE = 7333

    @pytest.fixture
    def nzf(self) -> NzbFile:
        nzo = NzbObject("test")
        raw_articles = [(f"part{index}@test", self.PART) for index in range(self.PARTS)]
        nzf = NzbFile(datetime.now(), "foo.bin", raw_articles, self.PART * self.PARTS, nzo)
        nzf.finish_import()
        return nzf

    @staticmethod
    def _response(
        article: Article, begin: int, file_size: int, length: int, sink: Optional[sabctools.FileWriter] = None
    ) -> sabctools.NNTPResponse:
        encoded, crc = sabctools.yenc_encode(os.urandom(length))
        raw_data = (
            b"222 0 <foo@bar>\r\n"
            + f"=ybegin part=1 line=128 size={file_size} name=foo.bin\r\n".encode()
            + f"=ypart begin={begin + 1} end={begin + length}\r\n".encode()
            + encoded
            + f"\r\n=yend size={length} part=1 pcrc32={crc:08x}\r\n.\r\n".encode()
        )
        dec = sabctools.Decoder(len(raw_data))
        dec.expect(article, sink)
        BytesIO(raw_data).readinto(dec)
        dec.process(len(raw_data))
        return next(dec)

    def _own(self, nzf: NzbFile, index: int, sink: Optional[sabctools.FileWriter] = None) -> sabctools.NNTPResponse:
        """The article the NZB asks for"""
        return self._response(nzf.decodetable[index], index * self.PART, self.PART * self.PARTS, self.PART, sink)

    def _other(self, nzf: NzbFile, index: int, begin: int, sink=None) -> sabctools.NNTPResponse:
        """Another file's article, under the same Message-ID"""
        return self._response(nzf.decodetable[index], begin, self.OTHER_SIZE, self.PART, sink)

    def test_article_of_another_file_is_rejected(self, nzf):
        for index in range(3):
            decoder.decode_yenc(nzf.decodetable[index], self._own(nzf, index))

        article = nzf.decodetable[3]
        with pytest.raises(decoder.BadData) as error:
            decoder.decode_yenc(article, self._other(nzf, 3, begin=5000))
        # Nothing to write, and nowhere to write it
        assert error.value.data is None
        assert article.data_begin is None
        assert article.crc32 is None

        # The right article is still accepted when another server has it
        decoder.decode_yenc(article, self._own(nzf, 3))
        assert article.data_begin == 3 * self.PART

    def test_another_file_first_does_not_condemn_the_file(self, nzf):
        # Nothing to compare the first article with, so it gets through
        decoder.decode_yenc(nzf.decodetable[0], self._other(nzf, 0, begin=5000))

        # The file's own articles must not be judged by it
        for index in range(1, 4):
            decoder.decode_yenc(nzf.decodetable[index], self._own(nzf, index))
            assert nzf.decodetable[index].data_begin == index * self.PART

        with pytest.raises(decoder.BadData):
            decoder.decode_yenc(nzf.decodetable[4], self._other(nzf, 4, begin=6000))

    def test_a_few_of_another_file_first_do_not_condemn_the_file(self, nzf):
        for index in range(2):
            decoder.decode_yenc(nzf.decodetable[index], self._other(nzf, index, begin=5000 + index * self.PART))

        # Two say otherwise, but that is too few to go on
        decoder.decode_yenc(nzf.decodetable[2], self._own(nzf, 2))
        assert nzf.decodetable[2].data_begin == 2 * self.PART

    def test_streamed_article_of_another_file_untrusts_what_it_overwrote(self, nzf, tmp_path):
        with sabctools.FileWriter(tmp_path / "foo.bin") as writer:
            for index in range(5):
                decoder.decode_yenc(nzf.decodetable[index], self._own(nzf, index, writer))
                nzf.decodetable[index].on_disk = True

            # Already on disk by the time its offset is known, across articles 2 and 3
            with pytest.raises(decoder.BadData):
                decoder.decode_yenc(nzf.decodetable[6], self._other(nzf, 6, begin=2500, sink=writer))

            # The rest of the file, including article 6 from a server that has the right one
            for index in range(5, self.PARTS):
                decoder.decode_yenc(nzf.decodetable[index], self._own(nzf, index, writer))

        # Their checksums no longer describe what is on disk, so par2 has to read it
        assert [article.crc32 is None for article in nzf.decodetable] == [False] * 2 + [True] * 2 + [False] * 6
        nzf.finalize_crc32()
        assert nzf.crc32 is None

    def test_article_decoded_after_it_was_overwritten_is_not_trusted(self, nzf, tmp_path):
        with sabctools.FileWriter(tmp_path / "foo.bin") as writer:
            responses = [self._own(nzf, index, writer) for index in range(5)]
            # Article 2 is on disk, but still waiting for its turn to be decoded
            for index in (0, 1, 3, 4):
                decoder.decode_yenc(nzf.decodetable[index], responses[index])
                nzf.decodetable[index].on_disk = True

            with pytest.raises(decoder.BadData):
                decoder.decode_yenc(nzf.decodetable[6], self._other(nzf, 6, begin=2500, sink=writer))
            decoder.decode_yenc(nzf.decodetable[2], responses[2])

        assert nzf.decodetable[2].data_begin == 2 * self.PART
        assert nzf.decodetable[2].crc32 is None

    def test_decode_tries_the_next_server(self, nzf):
        for index in range(3):
            decoder.decode_yenc(nzf.decodetable[index], self._own(nzf, index))

        article = nzf.decodetable[3]
        with (
            mock.patch("sabnzbd.decoder.search_new_server", return_value=True) as search_new_server,
            mock.patch("sabnzbd.ArticleCache", create=True) as article_cache,
            mock.patch("sabnzbd.NzbQueue", create=True) as nzb_queue,
        ):
            decoder.decode(article, self._other(nzf, 3, begin=5000))

        search_new_server.assert_called_once_with(article)
        article_cache.save_article.assert_not_called()
        nzb_queue.register_article.assert_not_called()

    def test_decode_without_another_server_keeps_nothing(self, nzf):
        for index in range(3):
            decoder.decode_yenc(nzf.decodetable[index], self._own(nzf, index))

        article = nzf.decodetable[3]
        with (
            mock.patch("sabnzbd.decoder.search_new_server", return_value=False),
            mock.patch("sabnzbd.ArticleCache", create=True) as article_cache,
            mock.patch("sabnzbd.NzbQueue", create=True) as nzb_queue,
        ):
            decoder.decode(article, self._other(nzf, 3, begin=5000))

        # A failed article, with nothing written for it, and no offset for par2 to place it at
        article_cache.save_article.assert_not_called()
        nzb_queue.register_article.assert_called_once_with(article, False)
        assert article.on_disk
        assert article.data_begin is None
