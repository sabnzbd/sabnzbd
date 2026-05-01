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
tests.test_misc - Testing functions in encoding.py
"""

import unicodedata

import pytest

import sabnzbd.encoding as enc


class TestEncoding:
    def test_correct_unknown_encoding(self):
        # Windows encoding in bytes
        assert "frènch_german_demö" == enc.correct_unknown_encoding(b"fr\xe8nch_german_dem\xf6")
        # Windows encoding in string that's already UTF8
        assert "demotöwers" == enc.correct_unknown_encoding("demot\udcf6wers")

    def test_correct_unknown_encoding_nfc_normalization(self):
        """Verify that correct_unknown_encoding always returns NFC-normalized strings.

        This is the fix for GitHub issues #1633 and #2858: par2 file metadata may
        carry NFC filenames while macOS / some archivers produce NFD.
        Both must end up identical after passing through this function so that
        filename comparisons (e.g. quick_check_set) do not cause double-unpacking.
        """
        # NFD form: 'e' + combining-grave (U+0300), 'o' + combining-diaeresis (U+0308)
        nfd_bytes = "fre\u0300nch_german_demo\u0308".encode("utf-8")
        # NFC form: precomposed è (U+00E8) and ö (U+00F6)
        nfc_string = "frènch_german_demö"  # U+00E8 / U+00F6

        result_from_nfd = enc.correct_unknown_encoding(nfd_bytes)
        result_from_nfc = enc.correct_unknown_encoding(nfc_string.encode("utf-8"))

        # Both should produce the same NFC result
        assert result_from_nfd == nfc_string
        assert result_from_nfc == nfc_string
        # Confirm the output is actually NFC, not NFD
        assert unicodedata.is_normalized("NFC", result_from_nfd)
        assert unicodedata.is_normalized("NFC", result_from_nfc)
        # Confirm NFD input was different at the byte level before normalization
        assert nfd_bytes != nfc_string.encode("utf-8")

    def test_limit_encoded_length(self):
        # Test with empty string
        assert enc.limit_encoded_length("", 10) == "", "Empty string should return empty string"

        # Test with string shorter than the limit
        assert enc.limit_encoded_length("hello", 10) == "hello"

        # Test with string equal to the limit
        assert enc.limit_encoded_length("hello", 5) == "hello", "String equal to limit should return the same string"

        # Test with string longer than the limit
        assert enc.limit_encoded_length("hello world", 5) == "hello", "String longer than limit should be truncated"

        # Test with UTF-8 characters
        assert enc.limit_encoded_length("héllö wørld", 10) == "héllö w", "UTF-8 characters should be handled correctly"

        # Test with emojis (multibyte characters)
        assert enc.limit_encoded_length("😀😂🤣😃😄😅😆😉😊😋😎😍", 30) == "😀😂🤣😃😄😅😆"

        # Test with invalid UTF-8 (single surrogate)
        invalid_utf8 = b"\xed\xa0\x80".decode("latin-1")
        limited_string = enc.limit_encoded_length(invalid_utf8, 3)
        assert len(limited_string) == 1, "Invalid UTF-8 should be handled without raising an exception"

        # Test with mixed valid and invalid UTF-8
        mixed_string = "hello" + b"\xed\xa0\x80".decode("latin-1") + "world"
        limited_string = enc.limit_encoded_length(mixed_string, 8)
        assert "hello" in limited_string, "Valid part of mixed string should be present"
        assert len(limited_string) <= 8, "Length of mixed string should be limited"

        # Parametrized tests for various string and length combinations
        test_cases = [
            ("", 5, ""),
            ("short", 10, "short"),
            ("longstring", 4, "long"),
            ("üöä", 4, "üö"),  # Test for umlauts
            ("你好世界", 4, "你"),  # Test for CJK characters
        ]
        for input_string, max_len, expected in test_cases:
            assert enc.limit_encoded_length(input_string, max_len) == expected
