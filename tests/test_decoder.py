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
tests.test_decoder- Testing functions in decoder.py
"""
import binascii
import os
import pytest

from random import randint
from unittest import mock

import sabnzbd.decoder as decoder
from sabnzbd.nzbstuff import Article


LINES_DATA = [os.urandom(45) for _ in range(32)]
VALID_UU_LINES = [binascii.b2a_uu(data).rstrip(b"\n") for data in LINES_DATA]

END_DATA = os.urandom(randint(1, 45))
VALID_UU_END = [
    binascii.b2a_uu(END_DATA).rstrip(b"\n"),
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
        begin_line: bytes = b"begin 644 My Favorite Open Source Movie.mkv",
    ):
        """Generate message parts. Part may be one of 'begin', 'middle', or 'end' for multipart
        messages, or 'single' for a singlepart message. All uu payload is taken from VALID_UU_*.

        Returns Article with a random id and lowest_partnum correctly set, socket-style raw
        data, and the expected result of uu decoding for the generated message.
        """
        article_id = "test@host" + os.urandom(8).hex() + ".sab"
        article = Article(article_id, randint(4321, 54321), None)
        article.lowest_partnum = True if part in ("begin", "single") else False
        # Mock an nzf so results from hashing and filename handling can be stored
        article.nzf = mock.Mock()

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

        if part in ("end", "single"):
            if insert_end:
                data.extend(VALID_UU_END)
                result.append(END_DATA)

        # Signal the end of the message with a dot on a line of its own
        data.append(b".")

        # Join the data with \r\n line endings, just like we get from socket reads
        data = b"\r\n".join(data)
        # Concatenate expected result
        result = b"".join(result)

        return article, data, result

    def test_no_data(self):
        with pytest.raises(decoder.BadUu):
            assert decoder.decode_uu(None, None)

    @pytest.mark.parametrize(
        "raw_data",
        [
            [b""],
            [b"\r\n\r\n"],
            [b"f", b"o", b"o", b"b", b"a", b"r", b"\r\n"],  # Plenty of list items, but (too) few actual lines
            [b"222 0 <artid@woteva>\r\nX-Too-Short: yup\r\n"],
        ],
    )
    def test_short_data(self, raw_data):
        with pytest.raises(decoder.BadUu):
            assert decoder.decode_uu(None, raw_data)

    @pytest.mark.parametrize(
        "raw_data",
        [
            [b"222 0 <foo@bar>\r\n\r\n"],  # Missing altogether
            [b"222 0 <foo@bar>\r\n\r\nbeing\r\n"],  # Typo in 'begin'
            [b"222 0 <foo@bar>\r\n\r\nx-header: begin 644 foobar\r\n"],  # Not at start of the line
            [b"666 0 <foo@bar>\r\nbegin\r\n"],  # No empty line + wrong response code
            [b"OMG 0 <foo@bar>\r\nbegin\r\n"],  # No empty line + invalid response code
            [b"222 0 <foo@bar>\r\nbegin\r\n"],  # No perms
            [b"222 0 <foo@bar>\r\nbegin ABC DEF\r\n"],  # Permissions not octal
            [b"222 0 <foo@bar>\r\nbegin 755\r\n"],  # No filename
            [b"222 0 <foo@bar>\r\nbegin 644 \t \t\r\n"],  # Filename empty after stripping
        ],
    )
    def test_missing_uu_begin(self, raw_data):
        article = Article("foo@bar", 1234, None)
        article.lowest_partnum = True
        filler = b"Some more\r\nrandom\r\nlines\r\nso the article\r\nlong\r\nenough\r\n"
        with pytest.raises(decoder.BadUu):
            assert decoder.decode_uu(article, raw_data.append(filler))

    @pytest.mark.parametrize("insert_empty_line", [True, False])
    @pytest.mark.parametrize("insert_excess_empty_lines", [True, False])
    @pytest.mark.parametrize("insert_headers", [True, False])
    @pytest.mark.parametrize("insert_end", [True, False])
    @pytest.mark.parametrize(
        "begin_line",
        [
            b"begin 644 nospace.bin",
            b"begin 444 filename with spaces.txt",
            b"BEGIN 644 foobar",
            b"begin 0755 shell.sh",
            None,
        ],
    )
    def test_singlepart(self, insert_empty_line, insert_excess_empty_lines, insert_headers, insert_end, begin_line):
        """Test variations of a sane single part nzf with proper uu-encoded data"""
        # Generate a singlepart message
        article, raw_data, expected_result = self._generate_msg_part(
            "single", insert_empty_line, insert_excess_empty_lines, insert_headers, insert_end, begin_line
        )
        assert decoder.decode_uu(article, [raw_data]) == expected_result
        assert article.nzf.filename_checked

    @pytest.mark.parametrize("insert_empty_line", [True, False])
    def test_multipart(self, insert_empty_line):
        """Test a simple multipart nzf"""

        # Generate and process a multipart msg
        decoded_data = expected_data = b""
        for part in ("begin", "middle", "middle", "end"):
            article, data, result = self._generate_msg_part(part, insert_empty_line, False, False, True, None)
            decoded_data += decoder.decode_uu(article, [data])
            expected_data += result

        # Verify results
        assert decoded_data == expected_data
        assert article.nzf.filename_checked

    @pytest.mark.parametrize(
        "bad_data",
        [
            b"MI^+0E\"C^364:CQ':]DW++^$F0J)6FDG/!`]0\\(4;EG$UY5RI,3JMBNX\\8+06\r\n$(WAIVBC^",  # Trailing junk
        ],
    )
    def test_broken_uu(self, bad_data):
        article = Article("foo@bar", 4321, None)
        article.lowest_partnum = False
        with pytest.raises(decoder.BadData):
            assert decoder.decode_uu(article, [b"222 0 <foo@bar>\r\n" + bad_data + b"\r\n"])
