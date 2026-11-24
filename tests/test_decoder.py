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
import threading
import pytest
from io import BytesIO

from random import randint
from unittest import mock

import sabctools
import sabnzbd
import sabnzbd.decoder as decoder
from sabnzbd.nzb import Article


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
        article = Article("foo@bar", 1234, mock.Mock())
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
        article = Article("foo@bar", 1234, mock.Mock())
        decoder.decode_yenc(article, self._response(b"\x01" * 100, 0, 0))
        assert article.block_size == 0
        assert article.block_crcs is None


class TestYencKeptBytes:
    @pytest.mark.parametrize("streamed", [True, False])
    @pytest.mark.parametrize("end", [8, 5])
    def test_an_article_describes_only_the_bytes_kept(self, tmp_path, streamed, end):
        """A body longer than its range is cut by the decoder. The article's size and data
        are then the bytes that go to the file, on either write path, and it keeps no CRC,
        as the one reported covers the whole body."""
        payload = b"abcdefgh"
        encoded, crc = sabctools.yenc_encode(payload)
        raw_data = (
            b"222 0 <foo@bar>\r\n"
            + b"=ybegin part=1 line=128 size=1000 name=foo.bin\r\n"
            + f"=ypart begin=1 end={end}\r\n".encode()
            + encoded
            + f"\r\n=yend size={len(payload)} part=1 pcrc32={crc:08x}\r\n.\r\n".encode()
        )
        writer = sabctools.FileWriter(str(tmp_path / "foo.bin")) if streamed else None
        dec = sabctools.Decoder(len(raw_data))
        dec.expect(None, writer)
        BytesIO(raw_data).readinto(dec)
        dec.process(len(raw_data))
        response = next(dec)
        if writer:
            writer.close()
        nzf = mock.Mock(file_size=1000, filename_checked=True, file_lock=threading.RLock())
        article = Article("foo@bar", 1234, nzf)

        data = decoder.decode_yenc(article, response)

        kept = payload[:end]
        assert response.crc == crc
        assert article.decoded_size == article.data_size == end
        assert article.crc32 == (crc if end == len(payload) else None)
        if streamed:
            assert data is None
            assert open(tmp_path / "foo.bin", "rb").read() == kept
        else:
            assert data == kept


class TestYencFileSize:
    @staticmethod
    def _response(payload: bytes, size: int, crc_ok: bool = True) -> sabctools.NNTPResponse:
        encoded, crc = sabctools.yenc_encode(payload)
        if not crc_ok:
            crc ^= 0xFFFFFFFF
        raw_data = (
            b"222 0 <foo@bar>\r\n"
            + f"=ybegin part=1 line=128 size={size} name=foo.bin\r\n".encode()
            + f"=ypart begin=1 end={len(payload)}\r\n".encode()
            + encoded
            + f"\r\n=yend size={len(payload)} part=1 pcrc32={crc:08x}\r\n.\r\n".encode()
        )
        dec = sabctools.Decoder(len(raw_data))
        dec.expect(None)
        BytesIO(raw_data).readinto(dec)
        dec.process(len(raw_data))
        return next(dec)

    @pytest.mark.parametrize("par2_size, expected", [(None, 1000), (600, 600)])
    def test_size_from_a_crc_failure_is_not_kept(self, par2_size, expected):
        payload = b"\x01" * 100
        nzf = mock.Mock(file_size=None, filename_checked=True, file_lock=threading.RLock())
        nzf.nzo.par2_file_size.return_value = par2_size
        with pytest.raises(decoder.BadData):
            decoder.decode_yenc(Article("foo@bar", 1234, nzf), self._response(payload, 5000, crc_ok=False))
        assert nzf.file_size is None
        decoder.decode_yenc(Article("foo@bar", 1234, nzf), self._response(payload, 1000))
        assert nzf.file_size == expected


class TestDecodeOnDisk:
    """Only an article that streamed to its file is on disk, a failed one is fetched again on a retry"""

    @pytest.fixture
    def decode(self, monkeypatch, tmp_path):
        queue = mock.Mock()
        monkeypatch.setattr(sabnzbd, "NzbQueue", queue, raising=False)
        monkeypatch.setattr(sabnzbd, "ArticleCache", mock.Mock(), raising=False)
        monkeypatch.setattr(decoder, "search_new_server", mock.Mock(return_value=False))

        def decode(crc_ok: bool = True, close_writer: bool = False) -> Article:
            payload = b"\x01" * 100
            encoded, crc = sabctools.yenc_encode(payload)
            if not crc_ok:
                crc ^= 0xFFFFFFFF
            raw_data = (
                b"222 0 <foo@bar>\r\n=ybegin part=1 line=128 size=100 name=foo.bin\r\n=ypart begin=1 end=100\r\n"
                + encoded
                + f"\r\n=yend size=100 part=1 pcrc32={crc:08x}\r\n.\r\n".encode()
            )
            writer = sabctools.FileWriter(str(tmp_path / "foo.bin"))
            if close_writer:
                writer.close()
            dec = sabctools.Decoder(len(raw_data))
            dec.expect(None, writer, max_end=100)
            BytesIO(raw_data).readinto(dec)
            dec.process(len(raw_data))
            writer.close()

            article = Article("foo@bar", 1234, mock.Mock(file_size=100, filename_checked=True))
            article.nzf.nzo.precheck = False
            decoder.decode(article, next(dec))
            queue.register_article.assert_called_once_with(article, crc_ok and not close_writer)
            return article

        return decode

    def test_streamed(self, decode):
        assert decode().on_disk is True

    def test_streamed_crc_error(self, decode):
        assert decode(crc_ok=False).on_disk is False

    def test_sink_failed(self, decode):
        assert decode(close_writer=True).on_disk is False
