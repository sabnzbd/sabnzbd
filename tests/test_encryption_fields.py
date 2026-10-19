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
tests.test_encryption_fields - Encrypted-path =ybegin/=ypart field validation tests.
"""

import pytest

from sabnzbd.encryption import (
    YEncEncryptionCryptoError,
    extract_and_remove_yencryption,
)

_VALID_HDR = (
    b"=yencryption cipher=XChaCha20-Poly1305 salt=1a2b3c4d5e6f7890abcdef1234567890 "
    b"index=00000001 tag=0cd77ce245a654463f90b945b1d22d5b"
)


def _single(ybegin: bytes) -> bytes:
    return ybegin + b"\r\n" + _VALID_HDR + b"\r\n" b"DataLine1\r\n" b"=yend size=100\r\n"


def _multi(ybegin: bytes, ypart: bytes) -> bytes:
    return ybegin + b"\r\n" + ypart + b"\r\n" + _VALID_HDR + b"\r\n" b"DataLine1\r\n" b"=yend size=100 part=1\r\n"


def test_conflicting_duplicate_geometry_keywords_fail_closed():
    """GAP13-05 (SABnzbd): same-value duplicates of part/size/begin/end return the
    value; conflicting duplicates in either order raise YEncEncryptionCryptoError."""
    # Same-value duplicates return the value (multipart)
    params, _clean = extract_and_remove_yencryption(
        _multi(
            b"=ybegin part=1 part=1 total=2 line=128 size=200 size=200 name=test.bin",
            b"=ypart begin=1 begin=1 end=100 end=100",
        )
    )
    assert params["segment_index"] == 1
    assert params["segment_bytes"] == 100

    # Same-value duplicate on the single-part size path
    params, _clean = extract_and_remove_yencryption(_single(b"=ybegin line=128 size=100 size=100 name=test.bin"))
    assert params["segment_bytes"] == 100

    # Conflicting duplicates, both orders, for each geometry keyword
    conflicting_blocks = [
        # =ybegin part=
        _multi(b"=ybegin part=1 part=2 total=2 line=128 size=200 name=test.bin", b"=ypart begin=1 end=100"),
        _multi(b"=ybegin part=2 part=1 total=2 line=128 size=200 name=test.bin", b"=ypart begin=1 end=100"),
        # =ybegin size= (multipart whole-file size and single-part size)
        _multi(b"=ybegin part=1 total=2 line=128 size=200 size=201 name=test.bin", b"=ypart begin=1 end=100"),
        _multi(b"=ybegin part=1 total=2 line=128 size=201 size=200 name=test.bin", b"=ypart begin=1 end=100"),
        _single(b"=ybegin line=128 size=100 size=101 name=test.bin"),
        _single(b"=ybegin line=128 size=101 size=100 name=test.bin"),
        # =ypart begin=
        _multi(b"=ybegin part=1 total=2 line=128 size=200 name=test.bin", b"=ypart begin=1 begin=2 end=100"),
        _multi(b"=ybegin part=1 total=2 line=128 size=200 name=test.bin", b"=ypart begin=2 begin=1 end=100"),
        # =ypart end=
        _multi(b"=ybegin part=1 total=2 line=128 size=200 name=test.bin", b"=ypart begin=1 end=100 end=101"),
        _multi(b"=ybegin part=1 total=2 line=128 size=200 name=test.bin", b"=ypart begin=1 end=101 end=100"),
    ]
    for block in conflicting_blocks:
        with pytest.raises(YEncEncryptionCryptoError):
            extract_and_remove_yencryption(block)


def test_enumerated_fields_at_2_pow_32_raise_size_overflow():
    """GAP13-02 (SABnzbd): =ypart begin/end and =ybegin size at 2^32 raise
    SIZE_OVERFLOW; size=4294967295 does not."""
    overflow_blocks = [
        _multi(
            b"=ybegin part=1 total=2 line=128 size=200 name=test.bin",
            b"=ypart begin=4294967296 end=4294967296",
        ),
        _multi(b"=ybegin part=1 total=2 line=128 size=200 name=test.bin", b"=ypart begin=1 end=4294967296"),
        # end alone at 2^32: begin < 2^32 and segment_bytes (=7) < 2^32, so only the end bound catches it
        _multi(
            b"=ybegin part=1 total=2 line=128 size=200 name=test.bin",
            b"=ypart begin=4294967290 end=4294967296",
        ),
        _single(b"=ybegin line=128 size=4294967296 name=test.bin"),
        _multi(b"=ybegin part=1 total=2 line=128 size=4294967296 name=test.bin", b"=ypart begin=1 end=100"),
    ]
    for block in overflow_blocks:
        with pytest.raises(YEncEncryptionCryptoError, match="SIZE_OVERFLOW"):
            extract_and_remove_yencryption(block)

    # Largest permitted size does not raise SIZE_OVERFLOW
    params, _clean = extract_and_remove_yencryption(_single(b"=ybegin line=128 size=4294967295 name=test.bin"))
    assert params["segment_bytes"] == 4294967295


def test_ypart_begin_zero_raises():
    """SAB13-07: part_begin < 1 fails closed (Body §2.1, STD13-02 in SAB)."""
    with pytest.raises(YEncEncryptionCryptoError):
        extract_and_remove_yencryption(
            _multi(b"=ybegin part=1 total=2 line=128 size=200 name=test.bin", b"=ypart begin=0 end=100")
        )
