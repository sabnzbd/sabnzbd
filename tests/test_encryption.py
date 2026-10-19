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
tests.test_encryption - Unit and integration tests for SABnzbd decryption adapter.
"""

import itertools
import json
from pathlib import Path
import re
import socket
import threading
import time
from unittest import mock
import pytest

import sabnzbd
from sabnzbd.downloader import Server, Downloader
from sabnzbd.get_addrinfo import AddrInfo
from sabnzbd.encryption import (
    DecryptionAdapter,
    YEncEncryptionCryptoError,
    parse_yencryption_line,
    extract_and_remove_yencryption,
    extract_bootstrap_from_line1,
    build_aad,
    BOOTSTRAP_PREFIX_LEN,
    ff1_decrypt,
    byte_to_numeral,
    numeral_to_byte,
)
from tests.encryption_helpers import ff1_encrypt
from sabnzbd.nzb import Article
from sabnzbd.newswrapper import NewsWrapper


def _mock_response():
    """A response mock with the same status and byte-count types as sabctools."""
    import sabctools

    response = mock.MagicMock(spec=sabctools.NNTPResponse)
    response.status_code = 222
    response.bytes_decoded = 0
    response.sink_failed = False
    return response


def _encrypted_wire(
    password: str,
    plaintext: bytes,
    name: str = "test.bin",
    salt: bytes = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890"),
    segment_index: int = 1,
    multipart: bool = False,
    line_ending: bytes = b"\r\n",
    tamper_tag: bool = False,
):
    """Build a complete encrypted wire article body (centralized builder).

    Returns (wire_body, adapter, master_key, nonce, ct, tag, body_crc, aad).
    The body is framed with `line_ending` and carries the given name/segment_index.
    With tamper_tag=True the =yencryption tag is corrupted so authentication fails.
    """
    import nacl.bindings as nb
    import sabctools

    adapter = DecryptionAdapter(password=password)
    master_key = adapter.get_master_key(salt)
    nonce = adapter.derive_body_nonce(master_key, segment_index)

    part_number, part_begin = (1, 1)  # ypart fields are filled from multipart geometry below
    aad = build_aad(name.encode("ascii"), part_number, part_begin, len(plaintext))
    enc = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, master_key)
    ct = enc[:-16]
    tag = enc[-16:]
    if tamper_tag:
        tag = bytes([tag[0] ^ 0xFF]) + tag[1:]

    body_encoded, body_crc = sabctools.yenc_encode(ct)

    if multipart:
        line1_pt = f"=ybegin part=1 total=1 line=128 size={len(plaintext)} name={name}".encode("ascii")
        line2_pt = f"=ypart begin=1 end={len(plaintext)}".encode("ascii")
        line3_pt = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag.hex()}".encode(
            "ascii"
        )
        line_last_pt = f"=yend size={len(plaintext)} part=1 pcrc32={body_crc:08x}".encode("ascii")
        plain_lines = [line1_pt, line2_pt, line3_pt, body_encoded, line_last_pt]
        line_indices = [1, 2, 3, None, 5]
    else:
        line1_pt = f"=ybegin line=128 size={len(plaintext)} name={name}".encode("ascii")
        line2_pt = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag.hex()}".encode(
            "ascii"
        )
        line_last_pt = f"=yend size={len(plaintext)} crc32={body_crc:08x}".encode("ascii")
        plain_lines = [line1_pt, line2_pt, body_encoded, line_last_pt]
        line_indices = [1, 2, None, 4]

    n_lines = len(plain_lines)
    wire_lines: list[bytes] = []
    for idx, (pt, line_idx) in enumerate(zip(plain_lines, line_indices)):
        if line_idx is None:
            wire_lines.append(pt)  # data line: untouched
        elif line_idx == 1:
            k, t = adapter.derive_control_keys(master_key, segment_index, 1)
            wire_lines.append(salt + segment_index.to_bytes(4, "big") + ff1_encrypt(k, t, pt))
        else:
            k, t = adapter.derive_control_keys(master_key, segment_index, line_idx)
            wire_lines.append(ff1_encrypt(k, t, pt))

    return (
        line_ending.join(wire_lines) + line_ending,
        adapter,
        master_key,
        nonce,
        ct,
        tag,
        body_crc,
        aad,
        n_lines,
    )


def fixture_bytes(vec, name):
    """Return bytes from a ``*_bytes`` fixture field (array of ints 0-255)."""
    return bytes(vec[name + "_bytes"])


def fixture_bytes_list(vec, name):
    return [bytes(item) for item in vec[name + "_bytes"]]


def _get_test_vector_dir() -> Path:
    vector_dir = Path(__file__).resolve().parent / "data" / "test-vectors"
    if not vector_dir.exists():
        pytest.fail(f"Test vectors not found at {vector_dir}")
    return vector_dir


class MockArticleNNTPServer:
    """Minimal NNTP server providing custom responses for BODY and ARTICLE commands."""

    def __init__(self, body_bytes: bytes, host: str = "127.0.0.1", line_ending: bytes = b"\r\n", split_at=None):
        self.host: str = host
        self.port: int = 0
        self.server_socket = None
        self.connections = []
        self._stop = threading.Event()
        self._thread = None
        self.body_bytes: bytes = body_bytes
        self.line_ending: bytes = line_ending
        # When set, every response is delivered in explicit TCP chunks split at these
        # byte offsets, with a pause between chunks so the client really observes
        # separate TCP segments (used to test CRLF split across chunk boundaries).
        self.split_at = split_at
        self.have_body: bool = True  # Flip to False to make BODY respond 500
        self.commands: list[bytes] = []  # Every command line received, in order

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(5)
        self.server_socket.settimeout(0.5)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self.server_socket.accept()
                self.connections.append(conn)
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except OSError:
                pass

    def _handle_client(self, conn):
        def send_response(resp: bytes):
            if self.split_at is None:
                conn.sendall(resp)
                return
            # Deliver in explicit chunks at the requested split offsets, pausing
            # between chunks so the client's recv() sees separate TCP segments.
            bounds = [0, *sorted({s for s in self.split_at if 0 < s < len(resp)}), len(resp)]
            for start, end in itertools.pairwise(bounds):
                conn.sendall(resp[start:end])
                if end < len(resp):
                    time.sleep(0.05)

        try:
            conn.sendall(b"200 Welcome\r\n")
            while not self._stop.is_set():
                conn.settimeout(0.5)
                try:
                    data = conn.recv(1024)
                    if not data:
                        break
                    if data.startswith(b"QUIT"):
                        conn.sendall(b"205 Goodbye" + self.line_ending)
                        break
                    elif data.startswith(b"BODY"):
                        self.commands.append(data)
                        if self.have_body:
                            resp = b"222 0 <art@e2e>" + self.line_ending + self.body_bytes + b"." + self.line_ending
                            send_response(resp)
                        else:
                            conn.sendall(b"500 command not supported" + self.line_ending)
                    elif data.startswith(b"ARTICLE"):
                        self.commands.append(data)
                        resp = (
                            b"220 0 <art@e2e>"
                            + self.line_ending
                            + b"Path: not-for-mail"
                            + self.line_ending
                            + b"From: poster@test"
                            + self.line_ending
                            + b"Newsgroups: alt.binaries.test"
                            + self.line_ending
                            + b"Subject: enc"
                            + self.line_ending
                            + b"Message-ID: <art@e2e>"
                            + self.line_ending
                            + self.line_ending
                            + self.body_bytes
                            + b"."
                            + self.line_ending
                        )
                        send_response(resp)
                    elif data.startswith(b"authinfo user"):
                        conn.sendall(b"381 More auth required" + self.line_ending)
                    elif data.startswith(b"authinfo pass"):
                        conn.sendall(b"281 Auth accepted" + self.line_ending)
                except TimeoutError:
                    continue
        except Exception:
            pass
        finally:
            conn.close()

    def stop(self):
        self._stop.set()
        for conn in self.connections:
            try:
                conn.close()
            except Exception:
                pass
        if self.server_socket:
            self.server_socket.close()
        if self._thread:
            self._thread.join(timeout=2)


class TestDecryptionAdapterContracts:
    """Adapter contract tests: Argon2id derivation, key caching, AEAD decryption, and FF1 control-line restoration."""

    def test_sab_adapter_contracts(self):
        """Argon2id key derivation, caching, body AEAD, and control line restoration against the standards vectors."""
        vector_dir = _get_test_vector_dir()

        # 1. Verify Argon2id key derivation against argon2id.json
        with open(vector_dir / "argon2id.json", "r", encoding="utf-8") as f:
            argon_data = json.load(f)

        for vec in argon_data["vectors"]:
            password = vec["password"]
            salt = fixture_bytes(vec, "salt")
            expected_key = fixture_bytes(vec, "expected_key")

            adapter = DecryptionAdapter(password=password)
            derived = adapter.get_master_key(salt)
            assert derived == expected_key, f"Key mismatch for {vec['id']}"

        # 2. Verify key caching (Argon2id called only once for identical salt)
        adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")

        import argon2.low_level as argon2_ll

        with mock.patch("argon2.low_level.hash_secret_raw", wraps=argon2_ll.hash_secret_raw) as mock_kdf:
            k1 = adapter.get_master_key(salt)
            k2 = adapter.get_master_key(salt)
            assert k1 == k2
            assert mock_kdf.call_count == 1, "Expected Argon2id KDF to be called exactly once due to caching"

        # 3. Verify body AEAD decryption against body_encryption.json
        with open(vector_dir / "body_encryption.json", "r", encoding="utf-8") as f:
            body_data = json.load(f)

        for vec in body_data["vectors"]:
            if vec["id"] == "body-vec-05-empty-payload":
                # Per Q-D, zero-length encrypted payloads are not exercised; the
                # vector stays in the JSON unexercised.
                continue
            password = vec["password"]
            salt = fixture_bytes(vec, "salt")
            segment_index = vec["segment_index"]
            expected_ct = fixture_bytes(vec, "expected_ciphertext")
            expected_tag = fixture_bytes(vec, "expected_tag")
            expected_pt = fixture_bytes(vec, "plaintext")
            aad_obj = vec["aad"]
            aad = fixture_bytes(aad_obj, "expected_aad")
            assert aad == build_aad(
                fixture_bytes(aad_obj, "name_bytes"),
                aad_obj["part_number"],
                aad_obj["part_begin"],
                aad_obj["segment_bytes"],
            ), f"AAD serialization mismatch for {vec['id']}"

            adapter = DecryptionAdapter(password=password)
            pt = adapter.decrypt_body(expected_ct, expected_tag, salt, segment_index, aad=aad)
            assert pt == expected_pt, f"Plaintext mismatch for {vec['id']}"

            # Empty AAD MUST fail authentication (Body Standard v1.2 Section 2.1)
            adapter_empty = DecryptionAdapter(password=password)
            with pytest.raises(ValueError, match="Poly1305 authentication failed"):
                adapter_empty.decrypt_body(expected_ct, expected_tag, salt, segment_index, aad=b"")

        # 4. Zero-Output Guarantee on authentication failure
        adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        good_vec = body_data["vectors"][0]
        ct = fixture_bytes(good_vec, "expected_ciphertext")
        tag = fixture_bytes(good_vec, "expected_tag")
        good_aad = fixture_bytes(good_vec["aad"], "expected_aad")

        # Corrupted tag
        bad_tag = bytes([tag[0] ^ 0xFF]) + tag[1:]
        with pytest.raises(ValueError, match="Poly1305 authentication failed"):
            adapter.decrypt_body(ct, bad_tag, salt, segment_index=1, aad=good_aad)

        # Corrupted ciphertext
        bad_ct = bytes([ct[0] ^ 0xFF]) + ct[1:]
        with pytest.raises(ValueError, match="Poly1305 authentication failed"):
            adapter.decrypt_body(bad_ct, tag, salt, segment_index=1, aad=good_aad)

        # Wrong segment_index
        with pytest.raises(ValueError, match="Poly1305 authentication failed"):
            adapter.decrypt_body(ct, tag, salt, segment_index=2, aad=good_aad)

        # Wrong password
        wrong_adapter = DecryptionAdapter(password="conformance-fixture-wrong-password")
        with pytest.raises(ValueError, match="Poly1305 authentication failed"):
            wrong_adapter.decrypt_body(ct, tag, salt, segment_index=1, aad=good_aad)

        # 5. Verify Control Line Decryption against control_line_encryption.json
        with open(vector_dir / "control_line_encryption.json", "r", encoding="utf-8") as f:
            control_data = json.load(f)

        for vec in control_data["vectors"]:
            if "total_physical_lines" in vec:
                # Full article test vector
                password = vec["password"]
                segment_index = vec["segment_index"]
                expected_lines = [line.encode("ascii") for line in vec["input_lines"]]
                wire_lines = fixture_bytes_list(vec, "expected_wire_lines")
                wire_block = b"\r\n".join(wire_lines) + b"\r\n"

                adapter = DecryptionAdapter(password=password)
                restored_block, extracted_salt, extracted_idx = adapter.restore_control_lines(wire_block)
                assert extracted_salt == fixture_bytes(vec, "salt")
                assert extracted_idx == segment_index
                expected_block = b"\r\n".join(expected_lines) + b"\r\n"
                assert restored_block == expected_block, f"Full article restoration mismatch for {vec['id']}"
            else:
                # Single line vector
                password = vec["password"]
                salt = fixture_bytes(vec, "salt")
                segment_index = vec["segment_index"]
                line_index = vec["line_index"]
                is_line_1 = vec["is_line_1"]
                expected_pt_line = vec["plaintext_line"].encode("ascii")
                wire_bytes = fixture_bytes(vec, "expected_wire")

                adapter = DecryptionAdapter(password=password)
                master_key = adapter.get_master_key(salt)
                enc_key, tweak = adapter.derive_control_keys(master_key, segment_index, line_index)

                if is_line_1:
                    line_salt = wire_bytes[:16]
                    line_idx = int.from_bytes(wire_bytes[16:20], "big")
                    assert line_salt == salt
                    assert line_idx == segment_index
                    ct = wire_bytes[20:]
                else:
                    ct = wire_bytes

                pt_line = adapter.decrypt_control_line(ct, enc_key, tweak)
                assert pt_line == expected_pt_line, f"Control line mismatch for {vec['id']}"

    def test_combined_layout_vectors_restore_and_decrypt(self):
        """control-vec-07/09/10 carry =yencryption at line 2 in the standards repo; they are valid combined articles.

        Restoration must succeed, the =yencryption line must be verified against Line 1, and the restored yEnc
        block must equal the vector's plaintext lines. Vectors 11 and 12 stay covered by the same check.
        """
        vector_dir = _get_test_vector_dir()
        with open(vector_dir / "control_line_encryption.json", "r", encoding="utf-8") as f:
            control_data = json.load(f)

        checked = set()
        for vec in control_data["vectors"]:
            if "total_physical_lines" not in vec or not vec["id"].startswith(
                ("control-vec-07-", "control-vec-09-", "control-vec-10-", "control-vec-11-", "control-vec-12-")
            ):
                continue
            checked.add("-".join(vec["id"].split("-")[:3]))

            expected_lines = [line.encode("ascii") for line in vec["input_lines"]]
            # =yencryption sits at line 2 (line 3 when =ypart is present) in the standards vectors
            enc_index = next(i for i, line in enumerate(expected_lines) if line.startswith(b"=yencryption"))
            assert enc_index in (1, 2), vec["id"]

            wire_block = b"\r\n".join(fixture_bytes_list(vec, "expected_wire_lines")) + b"\r\n"
            adapter = DecryptionAdapter(password=vec["password"])
            restored_block, extracted_salt, extracted_idx = adapter.restore_control_lines(wire_block)

            assert extracted_salt == fixture_bytes(vec, "salt"), vec["id"]
            assert extracted_idx == vec["segment_index"], vec["id"]
            assert restored_block == b"\r\n".join(expected_lines) + b"\r\n", vec["id"]

            yenc_params, clean_block = extract_and_remove_yencryption(restored_block)
            assert yenc_params["salt"] == extracted_salt, vec["id"]
            assert yenc_params["segment_index"] == extracted_idx, vec["id"]
            assert b"=yencryption" not in clean_block, vec["id"]
            without_enc = expected_lines[:enc_index] + expected_lines[enc_index + 1 :]
            assert clean_block == b"\r\n".join(without_enc) + b"\r\n", vec["id"]

        assert checked == {"control-vec-07", "control-vec-09", "control-vec-10", "control-vec-11", "control-vec-12"}

    def test_nonce_and_tweak_vectors(self):
        """Verify HMAC-SHA256 body nonce and control tweak derivations against nonce_tweak.json."""
        vector_dir = _get_test_vector_dir()
        with open(vector_dir / "nonce_tweak.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")

        # 1. Body nonce vectors (24 bytes via 19-byte HMAC message)
        for vec in data["body_nonce_vectors"]:
            key = fixture_bytes(vec, "key")
            segment_index = vec["segment_index"]
            nonce = adapter.derive_body_nonce(key, segment_index)
            assert nonce == fixture_bytes(vec, "expected_nonce"), f"Nonce mismatch for {vec['id']}"

        # 2. Control tweak vectors (32-byte encKey and 8-byte tweak)
        for vec in data["control_tweak_vectors"]:
            master_key = fixture_bytes(vec, "master_key")
            segment_index = vec["segment_index"]
            line_index = vec["line_index"]
            enc_key, tweak = adapter.derive_control_keys(master_key, segment_index, line_index)
            assert enc_key == fixture_bytes(vec, "enc_key"), f"Enc key mismatch for {vec['id']}"
            assert tweak == fixture_bytes(vec, "expected_tweak"), f"Tweak mismatch for {vec['id']}"

    def test_numeral_bijection_and_parser(self):
        """Test byte_to_numeral, numeral_to_byte, and parse_yencryption_line."""
        # 1. Numeral bijection
        for b in range(1, 256):
            if b in (0x0A, 0x0D):
                with pytest.raises(ValueError):
                    byte_to_numeral(b)
            else:
                num = byte_to_numeral(b)
                assert 0 <= num <= 252
                assert numeral_to_byte(num) == b

        with pytest.raises(ValueError):
            byte_to_numeral(0x00)

        # 2. Parser
        line = "=yencryption cipher=XChaCha20-Poly1305 salt=1a2b3c4d5e6f7890abcdef1234567890 index=00000001 tag=0cd77ce245a654463f90b945b1d22d5b"
        parsed = parse_yencryption_line(line)
        assert parsed is not None

        assert parsed["salt"] == bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        assert parsed["segment_index"] == 1
        assert parsed["tag"] == bytes.fromhex("0cd77ce245a654463f90b945b1d22d5b")

        # Invalid lines
        assert parse_yencryption_line("not an encryption line") is None
        assert parse_yencryption_line("=yencryption cipher=AES salt=123 tag=456") is None

    def test_extract_bootstrap_from_line1(self):
        """Test 20-byte bootstrap extraction: 22B minimum length, forbidden bytes, and zero index."""
        assert BOOTSTRAP_PREFIX_LEN == 20
        valid_prefix = b"A" * 16 + (42).to_bytes(4, "big")
        valid_line = valid_prefix + b"xy"
        salt, idx = extract_bootstrap_from_line1(valid_line)
        assert salt == b"A" * 16
        assert idx == 42

        # < 22 bytes fails
        with pytest.raises(ValueError, match="Line 1 truncated"):
            extract_bootstrap_from_line1(valid_prefix + b"x")

        # Forbidden bytes in salt
        for forbidden in (0x00, 0x0A, 0x0D):
            bad_salt = bytearray(b"A" * 16)
            bad_salt[5] = forbidden
            with pytest.raises(ValueError, match="Forbidden byte"):
                extract_bootstrap_from_line1(bytes(bad_salt) + (1).to_bytes(4, "big") + b"xx")

        # Zero index fails
        with pytest.raises(ValueError, match="ZERO_SEGMENT_INDEX"):
            extract_bootstrap_from_line1(b"A" * 16 + (0).to_bytes(4, "big") + b"xx")


class TestDirectWriteGatingAndFailover:
    """Test suite verifying direct-write gating and authentication error routing."""

    def test_direct_write_gated_differentiation(self):
        """article_sink gates encrypted releases and preserves archive-password direct-write."""
        wrapper = mock.MagicMock(spec=NewsWrapper)
        mock_monitor = mock.MagicMock(allow_direct_decode=True)
        mock_writer = mock.MagicMock()
        mock_assembler = mock.MagicMock()
        mock_assembler.get_writer.return_value = mock_writer

        article_enc = mock.MagicMock(spec=Article)
        article_enc.nzf.nzo.yenc_encrypted = True
        article_enc.nzf.type = "yenc"
        article_enc.lowest_partnum = False
        article_enc.nzf.prepare_filepath.return_value = True

        with (
            mock.patch.object(sabnzbd.cfg, "direct_decode", return_value=True),
            mock.patch.object(sabnzbd.cfg, "direct_write", return_value=True),
            mock.patch.object(sabnzbd, "WriteMonitor", mock_monitor, create=True),
        ):
            assert NewsWrapper.article_sink(wrapper, article_enc) is None

        article_archive = mock.MagicMock(spec=Article)
        article_archive.nzf.nzo.yenc_encrypted = False
        article_archive.nzf.nzo.password = "fixture-archive-value"
        article_archive.nzf.type = "yenc"
        article_archive.lowest_partnum = False
        article_archive.nzf.prepare_filepath.return_value = True

        with (
            mock.patch.object(sabnzbd.cfg, "direct_decode", return_value=True),
            mock.patch.object(sabnzbd.cfg, "direct_write", return_value=True),
            mock.patch.object(sabnzbd, "WriteMonitor", mock_monitor, create=True),
            mock.patch.object(sabnzbd, "Assembler", mock_assembler, create=True),
        ):
            assert NewsWrapper.article_sink(wrapper, article_archive) == mock_writer

    def test_downloader_decode_candidate_dispatch(self):
        """Downloader.decode forwards candidate encrypted responses to decoder instead of discarding."""
        from sabnzbd.downloader import Downloader

        # Case 1: Candidate encrypted article (bytes_decoded == 0, lines and encryption provenance present)
        art_cand = mock.MagicMock(spec=Article)
        art_cand.fetcher.id = 1
        art_cand.nzf.nzo.password = "fixture-archive-value"
        art_cand.nzf.nzo.yenc_encrypted = True
        art_cand.nzf.nzo.precheck = False

        resp_cand = _mock_response()
        resp_cand.bytes_decoded = 0
        resp_cand.lines = ["encrypted_line_1", "encrypted_line_2"]

        mock_bps = mock.MagicMock()
        with (
            mock.patch.object(sabnzbd, "BPSMeter", mock_bps, create=True),
            mock.patch.object(sabnzbd.decoder, "decode") as mock_decoder_decode,
        ):
            Downloader.decode(art_cand, resp_cand)
            assert mock_decoder_decode.called, "Expected candidate encrypted article to be forwarded to decoder.decode"
            assert not art_cand.search_new_server.called
            assert not art_cand.nzf.nzo.increase_bad_articles_counter.called

        # Case 2: Broken archive-password article is not transport encrypted
        art_broken = mock.MagicMock(spec=Article)
        art_broken.fetcher.id = 1
        art_broken.nzf.nzo.password = "fixture-archive-value"
        art_broken.nzf.nzo.yenc_encrypted = False
        art_broken.nzf.nzo.precheck = False
        art_broken.search_new_server.return_value = False

        resp_broken = _mock_response()
        resp_broken.bytes_decoded = 0
        resp_broken.lines = ["some_line"]

        mock_queue = mock.MagicMock()
        with (
            mock.patch.object(sabnzbd, "BPSMeter", mock_bps, create=True),
            mock.patch.object(sabnzbd.decoder, "decode") as mock_decoder_decode,
            mock.patch.object(sabnzbd, "NzbQueue", mock_queue, create=True),
        ):
            Downloader.decode(art_broken, resp_broken)
            assert not mock_decoder_decode.called, "Broken article must not be forwarded to decoder.decode"
            assert art_broken.search_new_server.called
            assert art_broken.nzf.nzo.increase_bad_articles_counter.called

    def test_modified_tag_native_response_triggers_server_search(self):
        """A real encrypted wire response with a modified tag fails Poly1305 and is routed
        to search_new_server with zero bytes stored (real modified-tag native response)."""
        import sabnzbd.decoder as decoder

        password = "conformance-fixture-tamper-password"
        plaintext = b"Modified tag native response test payload!"

        enc_body, _adapter, _mk, _nonce, _ct, _tag, _crc, _aad, _n = _encrypted_wire(
            password=password,
            plaintext=plaintext,
            name="test.bin",
            tamper_tag=True,
        )
        wire_lines = enc_body.split(b"\r\n")

        article = mock.MagicMock(spec=Article)
        article.article = "tag_tamper@news"
        article.nzf.nzo.password = password
        article.nzf.nzo.yenc_encrypted = True
        article.nzf.nzo.precheck = False
        article.nzf.filename_checked = True
        article.lowest_partnum = False
        article.on_disk = False
        article.search_new_server.return_value = True

        # Native 222 BODY response carrying the modified-tag encrypted article
        resp = _mock_response()
        resp.sink_failed = False
        resp.status_code = 222
        resp.bytes_decoded = 0
        resp.lines = [line.decode("latin-1") for line in wire_lines if line]

        mock_cache = mock.MagicMock()
        mock_queue = mock.MagicMock()
        with (
            mock.patch.object(sabnzbd, "ArticleCache", mock_cache, create=True),
            mock.patch.object(sabnzbd, "NzbQueue", mock_queue, create=True),
        ):
            decoder.decode(article, resp)
            # search_new_server should have been called via article.search_new_server()
            assert article.search_new_server.called, "search_new_server should be called on auth failure"
            # Zero-output guarantee: cache save must NOT be called
            assert not mock_cache.save_article.called, "save_article must not be called on authentication failure"
            assert not article.on_disk, "article.on_disk must remain False on auth failure"

    def test_wire_restore_and_authenticated_decode(self):
        """Full wire response: encrypted control lines + =yencryption + ciphertext body -> authenticated decode."""
        import nacl.bindings as nb
        import sabctools
        import sabnzbd.decoder as decoder
        from sabnzbd.encryption import build_aad

        # 1. Single-part article test
        password = "public-conformance-vector-key-2026"
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        segment_index = 1
        plaintext = b"Synthetic fixture payload for SABnzbd wire decryption testing!"

        adapter = DecryptionAdapter(password=password)
        master_key = adapter.get_master_key(salt)
        nonce = adapter.derive_body_nonce(master_key, segment_index)

        aad_single = build_aad(b"test.bin", 1, 1, len(plaintext))
        enc = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad_single, nonce, master_key)
        ct = enc[:-16]
        tag = enc[-16:]

        body_encoded, body_crc = sabctools.yenc_encode(ct)

        line1_pt = f"=ybegin line=128 size={len(ct)} name=test.bin".encode("ascii")
        line2_pt = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag.hex()}".encode(
            "ascii"
        )
        line3_pt = body_encoded
        line4_pt = f"=yend size={len(ct)} crc32={body_crc:08x}".encode("ascii")

        k1, t1 = adapter.derive_control_keys(master_key, segment_index, 1)
        wire1 = salt + (segment_index).to_bytes(4, "big") + ff1_encrypt(k1, t1, line1_pt)

        k2, t2 = adapter.derive_control_keys(master_key, segment_index, 2)
        wire2 = ff1_encrypt(k2, t2, line2_pt)

        wire3 = line3_pt

        k4, t4 = adapter.derive_control_keys(master_key, segment_index, 4)
        wire4 = ff1_encrypt(k4, t4, line4_pt)

        article = mock.MagicMock(spec=Article)
        article.article = "wire_single@news"
        article.nzf.nzo.password = password
        article.nzf.filename_checked = False
        article.lowest_partnum = True

        resp = _mock_response()
        resp.sink_failed = False
        resp.bytes_decoded = 0
        resp.lines = [
            wire1.decode("latin-1"),
            wire2.decode("latin-1"),
            wire3.decode("latin-1"),
            wire4.decode("latin-1"),
        ]

        decoded = decoder.decode_yenc(article, resp)
        assert decoded == bytearray(plaintext)
        assert article.decoded_size == len(plaintext)
        assert article.file_size == len(ct)
        # Ciphertext CRC never persisted on encrypted paths
        assert article.crc32 is None
        assert article.nzf.nzo.verify_nzf_filename.called

        # 2. Multipart article test
        aad_multi = build_aad(b"multi.bin", 1, 1, len(plaintext))
        enc_m = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad_multi, nonce, master_key)
        ct_m = enc_m[:-16]
        tag_m = enc_m[-16:]
        body_encoded_m, body_crc_m = sabctools.yenc_encode(ct_m)

        line1_m_pt = f"=ybegin part=1 total=2 line=128 size={len(ct_m) * 2} name=multi.bin".encode("ascii")
        line2_m_pt = f"=ypart begin=1 end={len(ct_m)}".encode("ascii")
        line3_m_pt = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag_m.hex()}".encode(
            "ascii"
        )
        line4_m_pt = body_encoded_m
        line5_m_pt = f"=yend size={len(ct_m)} part=1 pcrc32={body_crc_m:08x}".encode("ascii")

        wire_m_1 = salt + (segment_index).to_bytes(4, "big") + ff1_encrypt(k1, t1, line1_m_pt)
        wire_m_2 = ff1_encrypt(k2, t2, line2_m_pt)
        k3, t3 = adapter.derive_control_keys(master_key, segment_index, 3)
        wire_m_3 = ff1_encrypt(k3, t3, line3_m_pt)
        wire_m_4 = line4_m_pt
        k5, t5 = adapter.derive_control_keys(master_key, segment_index, 5)
        wire_m_5 = ff1_encrypt(k5, t5, line5_m_pt)

        article_m = mock.MagicMock(spec=Article)
        article_m.article = "wire_multi@news"
        article_m.bytes = len(plaintext)
        article_m.nzf.nzo.password = password
        article_m.nzf.filename_checked = True
        article_m.lowest_partnum = False

        resp_m = _mock_response()
        resp_m.sink_failed = False
        resp_m.bytes_decoded = 0
        resp_m.lines = [
            wire_m_1.decode("latin-1"),
            wire_m_2.decode("latin-1"),
            wire_m_3.decode("latin-1"),
            wire_m_4.decode("latin-1"),
            wire_m_5.decode("latin-1"),
        ]

        decoded_m = decoder.decode_yenc(article_m, resp_m)
        assert decoded_m == bytearray(plaintext)
        assert article_m.decoded_size == len(plaintext)
        assert article_m.file_size == len(ct_m) * 2
        assert article_m.data_begin == 0
        assert article_m.data_size == len(ct_m)
        # Ciphertext CRC never persisted on encrypted paths
        assert article_m.crc32 is None

        # 3. Wire CRC failure (corrupted pcrc32 in =yend)
        bad_crc = (body_crc_m ^ 0xFFFFFFFF) & 0xFFFFFFFF
        bad_line5_pt = f"=yend size={len(ct_m)} part=1 pcrc32={bad_crc:08x}".encode("ascii")
        bad_wire_5 = ff1_encrypt(k5, t5, bad_line5_pt)

        resp_bad_crc = _mock_response()
        resp_bad_crc.sink_failed = False
        resp_bad_crc.bytes_decoded = 0
        resp_bad_crc.lines = [
            wire_m_1.decode("latin-1"),
            wire_m_2.decode("latin-1"),
            wire_m_3.decode("latin-1"),
            wire_m_4.decode("latin-1"),
            bad_wire_5.decode("latin-1"),
        ]
        with pytest.raises(ValueError, match="Wire CRC error"):
            decoder.decode_yenc(article_m, resp_bad_crc)

        # 4. Poly1305 authentication failure (tampered tag)
        bad_tag = bytes([tag_m[0] ^ 0xFF]) + tag_m[1:]
        bad_line3_pt = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={bad_tag.hex()}".encode(
            "ascii"
        )
        bad_wire_3 = ff1_encrypt(k3, t3, bad_line3_pt)

        resp_bad_tag = _mock_response()
        resp_bad_tag.sink_failed = False
        resp_bad_tag.bytes_decoded = 0
        resp_bad_tag.lines = [
            wire_m_1.decode("latin-1"),
            wire_m_2.decode("latin-1"),
            bad_wire_3.decode("latin-1"),
            wire_m_4.decode("latin-1"),
            wire_m_5.decode("latin-1"),
        ]
        with pytest.raises(ValueError, match="Poly1305 authentication failed"):
            decoder.decode_yenc(article_m, resp_bad_tag)

    def test_encrypted_multipart_yend_whole_file_crc32_is_ignored(self):
        """Receivers ignore whole-file crc32= on an encrypted multipart article (Body Std v1.2 §5/§9, Q-1).

        Producers never emit crc32= alongside pcrc32= on multipart; a receiver must
        still decode (validating pcrc32=) and never persist the ciphertext CRC.
        """
        import sabnzbd.decoder as decoder

        password = "public-conformance-vector-key-2026"
        plaintext = b"Synthetic fixture payload for SABnzbd wire decryption testing!"
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        segment_index = 1

        # Build the multipart article directly with both pcrc32= (correct) and
        # crc32= (arbitrary whole-file value) on the =yend plaintext line.
        import nacl.bindings as nb
        import sabctools

        adapter = DecryptionAdapter(password=password)
        master_key = adapter.get_master_key(salt)
        nonce = adapter.derive_body_nonce(master_key, segment_index)
        aad_m = build_aad(b"multi.bin", 1, 1, len(plaintext))
        enc_m = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad_m, nonce, master_key)
        ct_m, tag_m = enc_m[:-16], enc_m[-16:]
        body_encoded_m, body_crc_m = sabctools.yenc_encode(ct_m)

        line1_pt = f"=ybegin part=1 total=2 line=128 size={len(ct_m) * 2} name=multi.bin".encode("ascii")
        line2_pt = f"=ypart begin=1 end={len(ct_m)}".encode("ascii")
        line3_pt = (
            f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag_m.hex()}"
        ).encode("ascii")
        line5_pt = f"=yend size={len(ct_m)} part=1 pcrc32={body_crc_m:08x} crc32=deadbeef".encode("ascii")
        k1, t1 = adapter.derive_control_keys(master_key, segment_index, 1)
        k2, t2 = adapter.derive_control_keys(master_key, segment_index, 2)
        k3, t3 = adapter.derive_control_keys(master_key, segment_index, 3)
        k5, t5 = adapter.derive_control_keys(master_key, segment_index, 5)
        wire = [
            (salt + segment_index.to_bytes(4, "big") + ff1_encrypt(k1, t1, line1_pt)).decode("latin-1"),
            ff1_encrypt(k2, t2, line2_pt).decode("latin-1"),
            ff1_encrypt(k3, t3, line3_pt).decode("latin-1"),
            body_encoded_m.decode("latin-1"),
            ff1_encrypt(k5, t5, line5_pt).decode("latin-1"),
        ]

        article = mock.MagicMock(spec=Article)
        article.article = "wire_multi_crc32@news"
        article.bytes = len(plaintext)
        article.nzf.nzo.password = password
        article.nzf.filename_checked = True
        article.lowest_partnum = False
        resp = _mock_response()
        resp.sink_failed = False
        resp.bytes_decoded = 0
        resp.lines = wire

        decoded = decoder.decode_yenc(article, resp)
        assert decoded == bytearray(plaintext)
        assert article.crc32 is None

    def test_single_part_wire_crc_corruption_fails_closed(self):
        """Single-part wire CRC corruption (crc32= in =yend) fails before AEAD (Body Std v1.2 §5/§9)."""
        import sabnzbd.decoder as decoder

        password = "public-conformance-vector-key-2026"
        plaintext = b"Synthetic fixture payload for SABnzbd wire decryption testing!"
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        segment_index = 1

        import nacl.bindings as nb
        import sabctools

        adapter = DecryptionAdapter(password=password)
        master_key = adapter.get_master_key(salt)
        nonce = adapter.derive_body_nonce(master_key, segment_index)
        aad = build_aad(b"test.bin", 1, 1, len(plaintext))
        enc = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, master_key)
        ct, tag = enc[:-16], enc[-16:]
        body_encoded, body_crc = sabctools.yenc_encode(ct)

        bad_crc = (body_crc ^ 0xFFFFFFFF) & 0xFFFFFFFF
        line1_pt = f"=ybegin line=128 size={len(ct)} name=test.bin".encode("ascii")
        line2_pt = (
            f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag.hex()}"
        ).encode("ascii")
        line4_pt = f"=yend size={len(ct)} crc32={bad_crc:08x}".encode("ascii")
        k1, t1 = adapter.derive_control_keys(master_key, segment_index, 1)
        k2, t2 = adapter.derive_control_keys(master_key, segment_index, 2)
        k4, t4 = adapter.derive_control_keys(master_key, segment_index, 4)
        wire = [
            (salt + segment_index.to_bytes(4, "big") + ff1_encrypt(k1, t1, line1_pt)).decode("latin-1"),
            ff1_encrypt(k2, t2, line2_pt).decode("latin-1"),
            body_encoded.decode("latin-1"),
            ff1_encrypt(k4, t4, line4_pt).decode("latin-1"),
        ]

        article = mock.MagicMock(spec=Article)
        article.article = "wire_single_bad_crc@news"
        article.nzf.nzo.password = password
        article.nzf.filename_checked = False
        article.lowest_partnum = True
        resp = _mock_response()
        resp.sink_failed = False
        resp.bytes_decoded = 0
        resp.lines = wire

        with pytest.raises(ValueError, match="Wire CRC error"):
            decoder.decode_yenc(article, resp)

    def test_extract_and_remove_yencryption(self):
        """Verify strict header placement, extraction, duplicate/misplaced rejection, and stripping."""
        valid_hdr = b"=yencryption cipher=XChaCha20-Poly1305 salt=1a2b3c4d5e6f7890abcdef1234567890 index=00000001 tag=0cd77ce245a654463f90b945b1d22d5b"

        # 1. Valid single-part article (header at line 2)
        single = (
            b"=ybegin line=128 size=100 name=test.bin\r\n" + valid_hdr + b"\r\n" b"DataLine1\r\n" b"=yend size=100\r\n"
        )
        params, clean = extract_and_remove_yencryption(single)

        assert params["salt"] == bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        assert params["segment_index"] == 1
        assert params["tag"] == bytes.fromhex("0cd77ce245a654463f90b945b1d22d5b")
        assert clean == (b"=ybegin line=128 size=100 name=test.bin\r\n" b"DataLine1\r\n" b"=yend size=100\r\n")

        # 2. Valid multipart article (header at line 3, following =ypart)
        multi = (
            b"=ybegin part=1 total=2 line=128 size=200 name=test.bin\r\n"
            b"=ypart begin=1 end=100\r\n" + valid_hdr + b"\r\n"
            b"DataLine1\r\n"
            b"=yend size=100 part=1\r\n"
        )
        m_params, m_clean = extract_and_remove_yencryption(multi)

        assert m_params["segment_index"] == 1
        assert m_clean == (
            b"=ybegin part=1 total=2 line=128 size=200 name=test.bin\r\n"
            b"=ypart begin=1 end=100\r\n"
            b"DataLine1\r\n"
            b"=yend size=100 part=1\r\n"
        )

        # 3. Missing =yencryption line
        missing = b"=ybegin line=128 size=100 name=test.bin\r\n" b"DataLine1\r\n" b"=yend size=100\r\n"
        with pytest.raises(ValueError, match="does not start with =yencryption"):
            extract_and_remove_yencryption(missing)

        # 4. Duplicate =yencryption line
        dup = (
            b"=ybegin line=128 size=100 name=test.bin\r\n" + valid_hdr + b"\r\n"
            b"DataLine1\r\n" + valid_hdr + b"\r\n"
            b"=yend size=100\r\n"
        )
        with pytest.raises(ValueError, match="Duplicate or misplaced =yencryption"):
            extract_and_remove_yencryption(dup)

        # 5. Misplaced =yencryption (at line 3 in single-part)
        misplaced_single = (
            b"=ybegin line=128 size=100 name=test.bin\r\n" b"DataLine1\r\n" + valid_hdr + b"\r\n" b"=yend size=100\r\n"
        )
        with pytest.raises(ValueError, match="does not start with =yencryption"):
            extract_and_remove_yencryption(misplaced_single)

        # 6. Misplaced =yencryption (at line 2 instead of line 3 in multipart)
        misplaced_multi = (
            b"=ybegin part=1 total=2 line=128 size=200 name=test.bin\r\n" + valid_hdr + b"\r\n"
            b"=ypart begin=1 end=100\r\n"
            b"DataLine1\r\n"
            b"=yend size=100 part=1\r\n"
        )
        with pytest.raises(ValueError, match="does not start with =ypart"):
            extract_and_remove_yencryption(misplaced_multi)

        # 7. Line 1 not =ybegin
        not_begin = b"not_ybegin\r\n" + valid_hdr + b"\r\n" b"=yend size=100\r\n"
        with pytest.raises(ValueError, match="Line 1 does not start with =ybegin"):
            extract_and_remove_yencryption(not_begin)

    def test_malformed_inputs_matrix(self):
        """Verify that all malformed header and control line test vectors fail closed with ValueError."""
        vector_dir = _get_test_vector_dir()
        with open(vector_dir / "malformed_inputs.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        with open(vector_dir / "control_line_encryption.json", "r", encoding="utf-8") as cf:
            control_data = json.load(cf)

        for vec in data["vectors"]:
            cat = vec["category"]
            vec_id = vec["id"]

            if cat == "header_syntax":
                # Strict v1.2 grammar: parse must fail closed (None or ValueError with
                # canonical error token). SABnzbd collapses all grammar violations into
                # a single ValueError tier mapped to PROVIDER_FAILOVER; the vector's
                # expected_error token must appear whenever the failure raises.
                if not vec["input_line"].startswith("=yencryption"):
                    assert parse_yencryption_line(vec["input_line"]) is None, f"Expected None for {vec_id}"
                else:
                    try:
                        parsed = parse_yencryption_line(vec["input_line"])
                        assert parsed is None, f"Expected rejection for {vec_id}"
                    except ValueError as parse_error:
                        # All grammar violations land in the single PROVIDER_FAILOVER
                        # ValueError tier; the vector token classifies the root cause
                        # but SABnzbd surfaces a canonical grammar/length token instead.
                        assert vec["expected_error"] in str(parse_error) or str(parse_error).startswith(
                            ("INVALID_LENGTH", "INVALID_WHITESPACE")
                        ), f"{vec_id}: unexpected rejection for: {parse_error}"
                # Must fail extract_and_remove_yencryption when in header position
                dummy = (
                    b"=ybegin line=128 size=10 name=test\r\n"
                    + vec["input_line"].encode("ascii", errors="replace")
                    + b"\r\n=yend size=10\r\n"
                )
                with pytest.raises(ValueError):
                    extract_and_remove_yencryption(dummy)

            elif cat == "control_syntax":
                adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")
                if "tampered_salt_bytes" in vec:
                    # Line 1 with forbidden bytes in salt
                    raw_salt = fixture_bytes(vec, "tampered_salt")
                    line1 = raw_salt + b"=ybegin line=128 size=18"
                    with pytest.raises(ValueError, match="Forbidden byte"):
                        extract_bootstrap_from_line1(line1)[0]
                    wire = raw_salt + b"=" * 20 + b"\r\n"
                    with pytest.raises(ValueError):
                        adapter.restore_control_lines(wire)
                elif vec_id == "control-syntax-04-line-too-short":
                    short_bytes = fixture_bytes(vec, "line")
                    with pytest.raises(ValueError, match="Line too short"):
                        ff1_decrypt(b"0" * 32, b"0" * 8, short_bytes)
                    with pytest.raises(ValueError, match="Line too short"):
                        ff1_encrypt(b"0" * 32, b"0" * 8, short_bytes)
                elif vec_id == "control-syntax-05-line1-truncated":
                    wire = fixture_bytes(vec, "line1") + b"\r\n"
                    with pytest.raises(ValueError, match="Line 1 truncated"):
                        adapter.restore_control_lines(wire)
                elif vec_id == "control-syntax-06-zero-segment-index":
                    wire = fixture_bytes(vec, "line1") + b"\r\n"
                    with pytest.raises(ValueError, match="ZERO_SEGMENT_INDEX"):
                        adapter.restore_control_lines(wire)
                elif vec_id in (
                    "control-syntax-08-forbidden-index-10",
                    "control-syntax-09-forbidden-index-13",
                    "control-syntax-10-forbidden-index-266",
                    "control-syntax-11-forbidden-index-269",
                ):
                    wire = fixture_bytes(vec, "line1") + b"\r\n"
                    with pytest.raises(ValueError, match="FORBIDDEN_SEGMENT_INDEX_BYTE"):
                        adapter.restore_control_lines(wire)
                elif vec_id == "control-syntax-07-wrong-password":
                    # Valid wire line 1 from control_line_encryption.json
                    wire_line1 = fixture_bytes(control_data["vectors"][0], "expected_wire") + b"\r\n"
                    wrong_adapter = DecryptionAdapter(password=vec["wrong_password"])
                    with pytest.raises(ValueError, match="Control line decrypt failure"):
                        wrong_adapter.restore_control_lines(wire_line1)
                else:
                    pytest.fail(f"Unhandled control_syntax vector {vec_id}")

            elif cat == "placement":
                # placement vectors: checks already in encryption.py (Control Std v1.2 §5).
                # placement-01/02 carry a target line_index; 03/04 carry only framing
                # flags, so synthesize the contradictory article from those flags.
                adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")
                salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
                seg = 1
                master_key = adapter.get_master_key(salt)
                hdr = (
                    b"=yencryption cipher=XChaCha20-Poly1305 salt="
                    + salt.hex().encode("ascii")
                    + f" index={seg:08x} tag={'00' * 16}".encode("ascii")
                )
                if vec_id in (
                    "placement-03-ypart-without-part-param",
                    "placement-04-yencryption-line2-with-part-param",
                ):
                    # Contradictory framing at the extract seam (encryption.py: INVALID_MULTIPART_FRAMING /
                    # MISPLACED_ENCRYPTION_HEADER). has_part_on_ybegin / is_ypart_on_line2 drive the block.
                    ybegin = (
                        b"=ybegin part=1 total=2 line=128 size=200 name=test.bin"
                        if vec["has_part_on_ybegin"]
                        else b"=ybegin line=128 size=100 name=test.bin"
                    )
                    line2 = b"=ypart begin=1 end=100" if vec["is_ypart_on_line2"] else hdr
                    if vec["is_ypart_on_line2"]:
                        block = ybegin + b"\r\n" + line2 + b"\r\n" + hdr + b"\r\nDATA\r\n=yend size=100 part=1\r\n"
                    else:
                        block = ybegin + b"\r\n" + line2 + b"\r\nDATA\r\n=yend size=100\r\n"
                    with pytest.raises(YEncEncryptionCryptoError, match=vec["expected_error"]):
                        extract_and_remove_yencryption(block)
                    # Same contradiction at the control-restore seam (restore_control_lines raises
                    # the same tokens): encrypt the lines per the flags and restore.
                    k1, t1 = adapter.derive_control_keys(master_key, seg, 1)
                    k2, t2 = adapter.derive_control_keys(master_key, seg, 2)
                    wire1 = salt + seg.to_bytes(4, "big") + ff1_encrypt(k1, t1, ybegin)
                    wire2 = ff1_encrypt(k2, t2, line2)
                    if vec["is_ypart_on_line2"]:
                        k3, t3 = adapter.derive_control_keys(master_key, seg, 3)
                        wire3 = ff1_encrypt(k3, t3, hdr)
                        k5, t5 = adapter.derive_control_keys(master_key, seg, 5)
                        wire5 = ff1_encrypt(k5, t5, b"=yend size=100 part=1")
                        wire_block = b"\r\n".join([wire1, wire2, wire3, b"DATA", wire5]) + b"\r\n"
                    else:
                        k4, t4 = adapter.derive_control_keys(master_key, seg, 4)
                        wire4 = ff1_encrypt(k4, t4, b"=yend size=100")
                        wire_block = b"\r\n".join([wire1, wire2, b"DATA", wire4]) + b"\r\n"
                    with pytest.raises(YEncEncryptionCryptoError, match=vec["expected_error"]):
                        adapter.restore_control_lines(wire_block)
                else:
                    # placement-01: single-part header must be on line 2 (not line_index=3)
                    # placement-02: multipart header must immediately follow =ypart (not line_index=4)
                    if vec["multipart"]:
                        block = (
                            b"=ybegin part=1 total=2 line=128 size=200 name=test.bin\r\n"
                            b"=ypart begin=1 end=100\r\n"
                            b"DATA\r\n" + hdr + b"\r\n=yend size=100 part=1\r\n"
                        )
                    else:
                        block = (
                            b"=ybegin line=128 size=100 name=test.bin\r\n" b"DATA\r\n" + hdr + b"\r\n=yend size=100\r\n"
                        )
                    # Chosen seam: extract_and_remove_yencryption (simplest honest fix).
                    # Diagnostic strings are informative, not normative (R4-STANDARDS-BOUNDARY),
                    # so assert only the production error type, not the vector's token
                    # or a substituted production string.
                    with pytest.raises(YEncEncryptionCryptoError):
                        extract_and_remove_yencryption(block)

            elif cat == "salt_mismatch":
                # malformed-dual-01/02: dual-bootstrap comparison in decoder.decode_yenc.
                import sabnzbd.decoder as decoder

                password = "public-conformance-vector-key-2026"
                line1_salt = fixture_bytes(vec, "line1_salt")
                header_salt = fixture_bytes(vec, "header_salt")
                line1_index = vec["line1_index"]
                header_index = vec["header_index"]
                dual_adapter = DecryptionAdapter(password=password)
                # Keys are derived from the Line 1 salt/index (what restore sees first).
                dual_key = dual_adapter.get_master_key(line1_salt)
                k1, t1 = dual_adapter.derive_control_keys(dual_key, line1_index, 1)
                k2, t2 = dual_adapter.derive_control_keys(dual_key, line1_index, 2)
                k4, t4 = dual_adapter.derive_control_keys(dual_key, line1_index, 4)
                line1_pt = b"=ybegin line=128 size=100 name=test.bin"
                line2_pt = (
                    f"=yencryption cipher=XChaCha20-Poly1305 salt={header_salt.hex()} "
                    f"index={header_index:08x} tag={'0' * 32}"
                ).encode("ascii")
                wire = [
                    (line1_salt + line1_index.to_bytes(4, "big") + ff1_encrypt(k1, t1, line1_pt)).decode("latin-1"),
                    ff1_encrypt(k2, t2, line2_pt).decode("latin-1"),
                    "data",
                    ff1_encrypt(k4, t4, b"=yend size=100").decode("latin-1"),
                ]
                article = mock.MagicMock(spec=Article)
                article.article = f"{vec_id}@test"
                article.nzf.nzo.password = password
                article.nzf.nzo.yenc_encrypted = True
                resp = _mock_response()
                resp.sink_failed = False
                resp.bytes_decoded = 0
                resp.lines = wire
                expected_msg = "Salt mismatch" if vec_id.endswith("dual-salt-mismatch") else "Dual index mismatch"
                with pytest.raises(YEncEncryptionCryptoError, match=expected_msg):
                    decoder.decode_yenc(article, resp)

            elif cat == "metadata_validation":
                # metadata-01..03 are NZB-ingest checks (Body Std v1.2 §8) covered by
                # TestNzbParserMetadataValidationVectors in test_nzbparser.py, which
                # drives actual NZB inputs through nzbfile_parser; nothing to assert
                # at this seam without re-implementing ingest.
                continue
            elif cat == "framing":
                # metadata-04: body-only article (=yencryption line, no Line 1 bootstrap)
                # presented to a combined-only receiver fails control-line restoration.
                assert vec_id == "metadata-04-body-only-vs-combined-only", vec_id
                body_only = (
                    b"=ybegin line=128 size=10 name=test.bin\r\n"
                    b"=yencryption cipher=XChaCha20-Poly1305 salt=1a2b3c4d5e6f7890abcdef1234567890 "
                    b"index=00000001 tag=0cd77ce245a654463f90b945b1d22d5b\r\n"
                    b"DATA\r\n=yend size=10\r\n"
                )
                # Actual token probed at the restore_control_lines seam: the vector's
                # CONTROL_LINE_DECRYPT_FAILURE is not a literal production string;
                # restore fails because Line 1 lacks the bootstrap and does not
                # restore to =ybegin.
                with pytest.raises(
                    YEncEncryptionCryptoError,
                    match=re.escape("Control line decrypt failure: line 1 does not start with =ybegin"),
                ):
                    DecryptionAdapter(password="public-conformance-vector-key-2026").restore_control_lines(body_only)

            elif cat == "auth_failure":
                # Covered by test_zero_output_matrix (AEAD authentication failures).
                continue

            else:
                pytest.fail(f"Unhandled malformed vector category {cat!r} for {vec_id}")

    def test_zero_output_matrix(self):
        """Verify that all auth_failure test vectors fail authentication and produce zero plaintext output."""
        vector_dir = _get_test_vector_dir()
        with open(vector_dir / "malformed_inputs.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        for vec in data["vectors"]:
            if vec["category"] != "auth_failure":
                continue

            pwd = vec["password"]
            salt = fixture_bytes(vec, "salt")
            ct = bytes(vec.get("tampered_ciphertext_bytes") or vec.get("ciphertext_bytes"))
            tag = bytes(vec.get("tampered_tag_bytes") or vec.get("tag_bytes"))
            seg_idx = vec["segment_index"]

            adapter = DecryptionAdapter(password=pwd)

            aad = fixture_bytes(vec, "aad") if "aad_bytes" in vec else b""
            with pytest.raises(ValueError, match="Poly1305 authentication failed"):
                adapter.decrypt_body(ct, tag, salt, seg_idx, aad=aad)

    def test_downloader_encrypted_e2e(self, caplog):
        """Dual-server failover: corrupted server 1 fails auth and fails over to server 2 which succeeds."""
        password = "conformance-fixture-multi-server-password"
        plaintext = b"Dual server failover end-to-end integration test payload!"

        valid_body, _adapter, master_key, nonce, _ct, tag, _crc, _aad, _n = _encrypted_wire(
            password=password,
            plaintext=plaintext,
            name="test.bin",
        )
        bad_body, _, _, _, _, _, _, _, _ = _encrypted_wire(
            password=password,
            plaintext=plaintext,
            name="test.bin",
            tamper_tag=True,
        )

        srv1 = MockArticleNNTPServer(bad_body)
        srv1.start()
        srv2 = MockArticleNNTPServer(valid_body)
        srv2.start()

        try:
            s1 = _make_server(srv1, "srv1", "Primary Bad Server", priority=0, pipelining=1)

            s2 = _make_server(srv2, "srv2", "Backup Good Server", priority=1, pipelining=1)

            mock_downloader = _mock_downloader([s1, s2])

            mock_bps, mock_cache, mock_queue = _mock_services()
            art, mock_nzo = _enc_article("art@e2e", password)

            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                # 1. Connect NW1 to Server 1 (tampered article)
                nw1 = _connect_wrapper(s1)

                # Request article from Server 1
                art.fetcher = s1
                nw1.queue_article(art)
                nw1.write()
                nw1.read()

                # Server 1 must fail auth and failover to Server 2
                assert s1 in art.try_list
                assert mock_bps.register_server_article_failed.called
                assert not mock_cache.save_article.called
                assert not mock_nzo.increase_bad_articles_counter.called

                # 2. Connect NW2 to Server 2 (valid article)
                nw2 = _connect_wrapper(s2)

                # Request article from Server 2
                art.fetcher = s2
                nw2.queue_article(art)
                nw2.write()
                nw2.read()

                # Server 2 must succeed and save byte-identical plaintext
                assert mock_cache.save_article.called
                _saved_art, saved_data = mock_cache.save_article.call_args[0]
                assert bytes(saved_data) == plaintext

            # Log safety checks: no secrets leaked to logs
            log_text = caplog.text
            assert password not in log_text, "Password must not appear in logs"
            assert master_key.hex() not in log_text, "Master key must not appear in logs"
            assert nonce.hex() not in log_text, "Nonce must not appear in logs"
            assert tag.hex() not in log_text, "Tag must not appear in logs"
            assert plaintext.decode("ascii") not in log_text, "Plaintext must not appear in logs"
            assert "Encrypted article art@e2e rejected (Poly1305 authentication failed: " in log_text
            assert "Authentication failed" not in log_text

        finally:
            srv1.stop()
            srv2.stop()

    def test_body_unsupported_fails_closed_without_article_fallback(self, caplog):
        """BODY 500 on an encrypted article is provider failover; ARTICLE is never requested."""
        password = "conformance-fixture-fallback-password"
        plaintext = b"ARTICLE fallback end-to-end test payload!"

        enc_body, _adapter, _mk, _nonce, _ct, _tag, _crc, _aad, _n = _encrypted_wire(
            password=password,
            plaintext=plaintext,
            name="test.bin",
        )

        srv = MockArticleNNTPServer(enc_body)
        srv.have_body = False  # BODY will answer 500
        srv.start()

        try:
            s1 = _make_server(srv, "srv_a", "Article Fallback Server", priority=0, pipelining=1)

            mock_downloader = _mock_downloader([s1])

            mock_bps, mock_cache, mock_queue = _mock_services()
            art, _mock_nzo = _enc_article("art@e2e", password)

            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                nw1 = _connect_wrapper(s1)

                # BODY -> 500: the article fails over (never cached), and no ARTICLE is sent
                art.fetcher = s1
                nw1.queue_article(art)
                nw1.write()
                nw1.read()
                assert not mock_cache.save_article.called
                assert _registered_success(mock_queue) is False

                # Retry on the same server still uses BODY
                art.fetcher = s1
                nw1.queue_article(art)
                nw1.write()
                nw1.read()
                assert not mock_cache.save_article.called
                assert srv.commands
                assert all(cmd.startswith(b"BODY") for cmd in srv.commands)

        finally:
            srv.stop()

    def test_non_body_status_logs_real_reason_not_authentication(self, caplog):
        """A 430 answer on an encrypted article logs the real reason; it is not an authentication failure."""
        import logging
        import sabctools
        import sabnzbd.decoder as decoder

        article = mock.MagicMock(spec=Article)
        article.article = "missing@f1"
        article.nzf.nzo.yenc_encrypted = True
        article.nzf.nzo.precheck = False
        article.nzf.nzo.password = "fixture-f1-430-value"
        article.search_new_server.return_value = True

        response = _mock_response()
        response.status_code = 430
        response.format = sabctools.EncodingFormat.YENC
        response.bytes_decoded = 0
        response.lines = None
        response.sink_failed = False

        caplog.set_level(logging.INFO)
        decoder.decode(article, response)

        assert "answered with status 430" in caplog.text
        assert "Authentication failed" not in caplog.text
        assert article.search_new_server.called

    def test_salt_mismatch_logs_reason_without_salt_hex_at_info(self, caplog):
        """A salt mismatch logs the reason at INFO, with no salt bytes."""
        import logging
        import sabctools
        import sabnzbd.decoder as decoder

        salt_line1 = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        salt_yenc = bytes.fromhex("ffeeddccbbaa99887766554433221100")
        yenc_line = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt_yenc.hex()} index=00000001 tag={'ab' * 16}"
        assert len(yenc_line) == 128
        block = b"=ybegin line=128 size=3 name=salt.bin\r\n" + yenc_line.encode("ascii") + b"\r\n=yend size=3\r\n"

        article = mock.MagicMock(spec=Article)
        article.article = "salt@f1"
        article.nzf.nzo.yenc_encrypted = True
        article.nzf.nzo.precheck = False
        article.nzf.nzo.password = "fixture-f1-salt-value"
        article.search_new_server.return_value = True

        response = _mock_response()
        response.status_code = 222
        response.format = sabctools.EncodingFormat.YENC
        response.bytes_decoded = 0
        response.lines = ["=ybegin line=128 size=3 name=salt.bin"]
        response.sink_failed = False

        caplog.set_level(logging.INFO)
        with mock.patch.object(
            DecryptionAdapter, "restore_control_lines", autospec=True, return_value=(block, salt_line1, 1)
        ):
            decoder.decode(article, response)

        assert (
            "Encrypted article salt@f1 rejected (Salt mismatch between control line 1 and =yencryption), "
            "trying next server"
        ) in caplog.text
        assert salt_line1.hex() not in caplog.text
        assert salt_yenc.hex() not in caplog.text
        assert article.search_new_server.called

    def test_malformed_yencryption_error_carries_no_salt_or_tag(self):
        """A malformed =yencryption line is reported without echoing its salt or tag."""
        salt = "1a2b3c4d5e6f7890abcdef1234567890"
        bad_line = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt} index=00000001"
        block = b"=ybegin line=128 size=3 name=bad.bin\r\n" + bad_line.encode("ascii") + b"\r\n=yend size=3\r\n"

        with pytest.raises(YEncEncryptionCryptoError, match="Malformed =yencryption") as info:
            extract_and_remove_yencryption(block)
        assert salt not in str(info.value)
        assert "index=" not in str(info.value)

    @pytest.mark.parametrize("framing", ["bare-lf", "split-terminator", "split-body"])
    def test_encrypted_response_framing_over_real_socket(self, framing):
        """Bare LF and CRLF split across TCP chunks deliver authenticated plaintext."""
        password = "conformance-fixture-framing-password"
        plaintext = b"Framing end-to-end test payload!"
        line_ending = b"\n" if framing == "bare-lf" else b"\r\n"
        enc_body, *_ = _encrypted_wire(password, plaintext, line_ending=line_ending)
        split_at = None
        if framing != "bare-lf":
            resp = b"222 0 <art@e2e>\r\n" + enc_body + b".\r\n"
            boundary = resp.rfind(b"\r\n")
            if framing == "split-body":
                terminator = resp.rfind(b"\r\n.")
                boundary = resp.rfind(b"\r\n", 0, terminator - 1)
            assert boundary >= 0 and resp[boundary : boundary + 2] == b"\r\n"
            split_at = [boundary + 1]
        srv = MockArticleNNTPServer(enc_body, line_ending=line_ending, split_at=split_at)
        srv.start()

        try:
            s1 = _make_server(srv, "srv_lf", "Bare LF Server", priority=0, pipelining=1)

            mock_downloader = _mock_downloader([s1])

            mock_bps, mock_cache, mock_queue = _mock_services()
            art, _mock_nzo = _enc_article("art@e2e", password)

            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                nw1 = _connect_wrapper(s1)

                art.fetcher = s1
                nw1.queue_article(art)
                nw1.write()
                nw1.read()
                if split_at:
                    nw1.read()

                mock_cache.save_article.assert_called_once()
                _saved_art, saved_data = mock_cache.save_article.call_args[0]
                assert bytes(saved_data) == plaintext
        finally:
            srv.stop()


def _make_server(srv, server_id, displayname, priority=0, pipelining=1):
    """Real Server config bound to a running mock NNTP server."""
    server = Server(
        server_id=server_id,
        displayname=displayname,
        host=srv.host,
        port=srv.port,
        timeout=5,
        threads=0,
        priority=priority,
        use_ssl=False,
        ssl_verify=0,
        ssl_ciphers="",
        pipelining_requests=pipelining,
    )
    server.addrinfo = AddrInfo(*socket.getaddrinfo(srv.host, srv.port, socket.AF_INET, socket.SOCK_STREAM)[0])
    server.active = True
    return server


def _mock_downloader(servers):
    """Mock Downloader whose finish_connect/decode delegate to the real class."""
    downloader = mock.MagicMock(spec=Downloader)
    downloader.servers = list(servers)
    downloader.reset_nw = lambda nw, *args, **kwargs: None
    downloader.finish_connect_nw = lambda nw, resp: Downloader.finish_connect_nw(downloader, nw, resp)
    downloader.decode = lambda article, resp: Downloader.decode(article, resp)
    downloader.modify_socket = lambda nw, event: None
    downloader.remove_socket = lambda nw: None
    downloader.no_active_jobs = lambda: False
    downloader.shutdown = False
    downloader.paused_for_postproc = False
    downloader.force_disconnect = False
    return downloader


def _mock_services():
    """The (bps, cache, queue) service mocks patched over sabnzbd globals."""
    return mock.MagicMock(), mock.MagicMock(), mock.MagicMock()


def _enc_article(msgid, password):
    """Real Article on a mocked encrypted NZO/NZF; returns (article, mock_nzo)."""
    mock_nzo = mock.MagicMock()
    mock_nzo.password = password
    mock_nzo.yenc_encrypted = True
    mock_nzo.precheck = False
    mock_nzo.removed_from_queue = False
    mock_nzo.status = "active"
    mock_nzo.priority = 0
    mock_nzo.update_download_stats = mock.MagicMock()
    mock_nzf = mock.MagicMock()
    mock_nzf.nzo = mock_nzo
    mock_nzf.filename_checked = True
    mock_nzf.type = "yenc"
    art = Article(msgid, 100, mock_nzf)
    art.lowest_partnum = False
    art.on_disk = False
    art.tries = 0
    return art, mock_nzo


def _make_article(msgid, password, encrypted):
    """Real Article on a mocked NZO/NZF for mixed plain/encrypted pipelining."""
    art, nzo = _enc_article(msgid, password if encrypted else None)
    nzo.yenc_encrypted = encrypted
    return art


def _connect_wrapper_no_read(server):
    """NewsWrapper connected (blocking socket); welcome not yet read."""
    nw = NewsWrapper(server, thrdnum=1)
    server.idle_threads.add(nw)
    nw.init_connect()
    for _ in range(50):
        if nw.connected:
            break
        time.sleep(0.05)
    return nw


def _connect_wrapper(server):
    """NewsWrapper connected (blocking socket) to server, welcome ready."""
    nw = _connect_wrapper_no_read(server)
    nw.nntp.sock.setblocking(True)
    nw.nntp.sock.settimeout(2)
    nw.read()
    assert nw.ready
    return nw


def _patched_services(downloader, bps, cache, queue, write_monitor=None):
    """ExitStack patching Downloader/BPSMeter/ArticleCache/NzbQueue (+ WriteMonitor if given)."""
    import contextlib

    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.object(sabnzbd, "Downloader", downloader, create=True))
    stack.enter_context(mock.patch.object(sabnzbd, "BPSMeter", bps, create=True))
    stack.enter_context(mock.patch.object(sabnzbd, "ArticleCache", cache, create=True))
    stack.enter_context(mock.patch.object(sabnzbd, "NzbQueue", queue, create=True))
    if write_monitor is not None:
        stack.enter_context(mock.patch.object(sabnzbd, "WriteMonitor", write_monitor, create=True))
    return stack


def _transport_server_and_article(enc_body: bytes, password: str, split_at=None):
    """Real NewsWrapper + real sabctools Decoder against a mock NNTP server.

    Returns (server, server_config, article, mocks) wired exactly like the framing
    tests above: blocking sockets, mocked Downloader services.
    """
    srv = MockArticleNNTPServer(enc_body, split_at=split_at)
    srv.start()
    s1 = _make_server(srv, "srv_raw", "Raw Capture Server", pipelining=2)
    mock_downloader = _mock_downloader([s1])
    mock_bps, mock_cache, mock_queue = _mock_services()
    art, _nzo = _enc_article("art@e2e", password)
    return srv, s1, art, mock_downloader, mock_bps, mock_cache, mock_queue


def _connect_and_fetch(nw, s1, art):
    """Blocking connect, welcome read, then queue/write/read one article."""
    nw.nntp.sock.setblocking(True)
    nw.nntp.sock.settimeout(2)
    nw.read()
    assert nw.ready
    art.fetcher = s1
    nw.queue_article(art)
    nw.write()
    nw.read()


class _PipelinedNNTPServer(MockArticleNNTPServer):
    """MockArticleNNTPServer that answers each command line separately, so two
    pipelined BODY commands produce two responses in the wire stream."""

    def _handle_client(self, conn):
        try:
            conn.sendall(b"200 Welcome\r\n")
            while not self._stop.is_set():
                conn.settimeout(0.5)
                try:
                    data = conn.recv(1024)
                except TimeoutError:
                    continue
                if not data:
                    break
                if data.startswith(b"QUIT"):
                    break
                for command in data.split(b"\r\n"):
                    if command.startswith(b"BODY"):
                        self.commands.append(command)
                        conn.sendall(b"222 0 <art@e2e>\r\n" + self.body_bytes + b".\r\n")
        except Exception:
            pass
        finally:
            conn.close()


class _MixedPipelinedNNTPServer:
    """NNTP server that answers each pipelined BODY command with the per-Message-ID body."""

    def __init__(self, bodies: dict, coalesce=False, plain_bytes_early=0):
        self.host = "127.0.0.1"
        self.port = 0
        self.server_socket = None
        self._stop = threading.Event()
        self._thread = None
        self.bodies = bodies  # msgid (without <>) -> response body bytes
        self.coalesce = coalesce
        self.plain_bytes_early = plain_bytes_early
        self.commands = []

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(5)
        self.server_socket.settimeout(0.5)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except OSError:
                pass

    def _handle_client(self, conn):
        responses = []
        try:
            conn.sendall(b"200 Welcome\r\n")
            while not self._stop.is_set():
                conn.settimeout(0.5)
                try:
                    data = conn.recv(4096)
                except TimeoutError:
                    continue
                if not data:
                    break
                if data.startswith(b"QUIT"):
                    break
                for command in data.split(b"\r\n"):
                    if command.startswith(b"BODY"):
                        self.commands.append(command)
                        msgid = command[len(b"BODY <") : -1].decode()
                        body = self.bodies[msgid]
                        response = b"222 0 <%s>\r\n" % msgid.encode() + body + b".\r\n"
                        if self.coalesce:
                            if not responses and self.plain_bytes_early:
                                conn.sendall(response[: self.plain_bytes_early])
                                response = response[self.plain_bytes_early :]
                            responses.append(response)
                            if len(responses) == 2:
                                conn.sendall(b"".join(responses))
                                responses.clear()
                        else:
                            conn.sendall(response)
                    elif command.startswith(b"authinfo"):
                        conn.sendall(b"281 Auth accepted\r\n")
        except Exception:
            pass
        finally:
            conn.close()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass


class TestRawTransportCapture:
    """Valid encrypted wire with an ordinary-yEnc-looking Line 1 salt must survive
    sabctools' native autodetection through the real NewsWrapper transport."""

    @pytest.mark.parametrize("chunked", [False, True])
    def test_forced_prefix_salt_single_part_decodes_through_real_transport(self, chunked):
        """Salt b'=ybegin ABCDEFGH' makes native sabctools consume the article as ordinary
        yEnc (no raw lines). The raw bytes must be preserved at the transport seam so the
        restoration/authentication pipeline still sees the valid article."""
        password = "conformance-fixture-forced-prefix"
        plaintext = b"prefix salt validation"
        enc_body, *_ = _encrypted_wire(password=password, plaintext=plaintext, salt=b"=ybegin ABCDEFGH")
        split_at = [len(enc_body) // 2] if chunked else None
        srv, s1, art, mock_downloader, mock_bps, mock_cache, mock_queue = _transport_server_and_article(
            enc_body, password, split_at=split_at
        )

        try:
            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                nw1 = _connect_wrapper_no_read(s1)
                _connect_and_fetch(nw1, s1, art)
                if split_at:
                    nw1.read()

                mock_cache.save_article.assert_called_once()
                _saved_art, saved_data = mock_cache.save_article.call_args[0]
                assert bytes(saved_data) == plaintext
        finally:
            srv.stop()

    def test_forced_prefix_salt_multipart_decodes_through_real_transport(self):
        """Multipart article with the forced prefix salt through real transport."""
        password = "conformance-fixture-forced-prefix-multi"
        plaintext = b"prefix salt multipart validation"
        enc_body, *_ = _encrypted_wire(password=password, plaintext=plaintext, salt=b"=ybegin ABCDEFGH", multipart=True)
        srv, s1, art, mock_downloader, mock_bps, mock_cache, mock_queue = _transport_server_and_article(
            enc_body, password
        )

        try:
            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                nw1 = _connect_wrapper_no_read(s1)
                _connect_and_fetch(nw1, s1, art)

                mock_cache.save_article.assert_called_once()
                _saved_art, saved_data = mock_cache.save_article.call_args[0]
                assert bytes(saved_data) == plaintext
        finally:
            srv.stop()

    def test_pipelined_encrypted_articles_both_decode_through_real_transport(self):
        """Two pipelined encrypted articles answered in one read: both raw captures are
        sliced at their own response boundaries and both decode to plaintext."""
        password = "conformance-fixture-pipelined"
        plaintext = b"pipelined plaintext payload!"
        enc_body, *_ = _encrypted_wire(password=password, plaintext=plaintext)
        srv = _PipelinedNNTPServer(enc_body)
        srv.start()
        s1 = _make_server(srv, "srv_pipe", "Pipelined Server", priority=0, pipelining=2)

        mock_downloader = _mock_downloader([s1])

        mock_bps, mock_cache, mock_queue = _mock_services()
        art1, _mock_nzo = _enc_article("art1@e2e", password)
        art2 = Article("art2@e2e", 100, art1.nzf)
        art2.lowest_partnum = False
        art2.on_disk = False
        art2.tries = 0
        arts = [art1, art2]

        try:
            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                nw1 = _connect_wrapper(s1)

                # Pipeline two requests: the second command goes out once the first
                # response is read (concurrency semaphore), then both decode.
                for art in arts:
                    art.fetcher = s1
                    nw1.queue_article(art)
                    nw1.write()
                for _ in range(6):
                    nw1.read()
                    nw1.write()
                    if mock_cache.save_article.call_count >= 2:
                        break

                assert mock_cache.save_article.call_count == 2
                for call in mock_cache.save_article.call_args_list:
                    assert bytes(call.args[1]) == plaintext
        finally:
            srv.stop()

    @pytest.mark.parametrize(
        ("partial_read", "coalesce", "bare_lf"),
        [
            pytest.param(0, False, False, id="existing-0"),
            pytest.param(32, False, False, id="existing-32"),
            pytest.param(60, False, False, id="existing-60"),
            pytest.param(0, True, True, id="coalesced-lf"),
            pytest.param(0, True, False, id="coalesced-crlf"),
            pytest.param(10, True, True, id="status-split-lf"),
            pytest.param(100, True, True, id="body-split-lf"),
            pytest.param(len(b"222 0 <plain@e2e>\r"), True, True, id="crlf-arming-split"),
        ],
    )
    def test_mixed_pipelined_plain_and_encrypted_articles_both_decode(self, partial_read, coalesce, bare_lf):
        """A large plain article pipelined ahead of an encrypted article on one connection
        must not release the encrypted article's journal bound: both decode to plaintext.

        With a partial read before the encrypted request is queued, the journal starts
        mid-response; partial_read=0 is the control where both responses arrive after
        arming. Splits inside the status line (0/32) and inside the yEnc body (60) are
        both exercised; all bytes stay below the journal bound to isolate alignment."""
        import sabctools

        password = "conformance-fixture-mixed-pipelined"
        plain_data = b"0123456789" * 100  # ~1 KB plain article
        encoded, crc = sabctools.yenc_encode(plain_data)
        plain_body = (
            b"=ybegin line=128 size=%d name=plain.bin\r\n" % len(plain_data)
            + encoded
            + b"\r\n=yend size=%d crc32=%08x\r\n" % (len(plain_data), crc)
        )
        plaintext = b"mixed pipelined encrypted payload!"
        enc_body, *_ = _encrypted_wire(password=password, plaintext=plaintext, salt=b"=ybegin ABCDEFGH")
        if bare_lf:
            enc_body = enc_body.replace(b"\r\n", b"\n")

        srv = _MixedPipelinedNNTPServer(
            {
                "plain@e2e": plain_body,
                "enc@e2e": enc_body,
            },
            coalesce=coalesce,
            plain_bytes_early=partial_read,
        )
        srv.start()
        s1 = _make_server(srv, "srv_mixed", "Mixed Server", priority=0, pipelining=2)

        mock_downloader = _mock_downloader([s1])

        mock_bps, mock_cache, mock_queue = _mock_services()

        plain_art = _make_article("plain@e2e", password, False)
        enc_art = _make_article("enc@e2e", password, True)
        plain_art.bytes = len(plain_data)
        enc_art.bytes = len(plaintext)

        try:
            with _patched_services(
                mock_downloader,
                mock_bps,
                mock_cache,
                mock_queue,
                write_monitor=mock.MagicMock(allow_direct_decode=False),
            ):
                nw1 = _connect_wrapper(s1)

                # Pipeline the large plain article first, then the encrypted one; both
                # responses arrive in one read while the journal is armed for the
                # encrypted article only.
                for art in (plain_art, enc_art):
                    art.fetcher = s1
                    nw1.queue_article(art)
                    nw1.write()
                    if partial_read and art is plain_art:
                        nw1.read(nbytes=partial_read)
                for _ in range(8):
                    nw1.read()
                    nw1.write()
                    if mock_queue.register_article.call_count >= 2:
                        break

                assert mock_cache.save_article.call_count == 2
                saved = {call.args[0].article: bytes(call.args[1]) for call in mock_cache.save_article.call_args_list}
                assert saved["plain@e2e"] == plain_data
                assert saved["enc@e2e"] == plaintext
        finally:
            srv.stop()

    def test_rearm_after_full_release_with_next_ordinary_response_partly_received(self):
        """An encrypted article armed after a full release (journal cleared) while the
        next ordinary response has already partly arrived: the new journal start offset
        keeps that ordinary response's absent prefix out of take(), and both the
        ordinary article and the later encrypted article still save exact plaintext."""
        import sabctools

        password = "conformance-fixture-rearm"
        plain_data = b"0123456789" * 100  # ~1 KB plain article
        encoded, crc = sabctools.yenc_encode(plain_data)
        plain_body = (
            b"=ybegin line=128 size=%d name=plain.bin\r\n" % len(plain_data)
            + encoded
            + b"\r\n=yend size=%d crc32=%08x\r\n" % (len(plain_data), crc)
        )
        plaintext = b"rearm release encrypted payload!"
        enc_body, *_ = _encrypted_wire(password=password, plaintext=plaintext, salt=b"=ybegin ABCDEFGH")

        srv = _MixedPipelinedNNTPServer(
            {
                "plain@e2e": plain_body,
                "plain2@e2e": plain_body,
                "enc@e2e": enc_body,
            }
        )
        srv.start()
        s1 = _make_server(srv, "srv_rearm", "Rearm Server", priority=0, pipelining=2)

        mock_downloader = _mock_downloader([s1])

        mock_bps, mock_cache, mock_queue = _mock_services()

        plain_art = _make_article("plain@e2e", password, False)
        plain2_art = _make_article("plain2@e2e", password, False)
        enc_art = _make_article("enc@e2e", password, True)
        plain_art.bytes = len(plain_data)
        plain2_art.bytes = len(plain_data)
        enc_art.bytes = len(plaintext)

        try:
            with _patched_services(
                mock_downloader,
                mock_bps,
                mock_cache,
                mock_queue,
                write_monitor=mock.MagicMock(allow_direct_decode=False),
            ):
                nw1 = _connect_wrapper(s1)

                # Stage 1: only the ordinary article is requested, and the journal is
                # never armed for it (no journaling of ordinary traffic). Its response
                # completes and its bound-free stream slice is consumed; the journal
                # then sits fully released (inactive) with no stored bytes.
                plain_art.fetcher = s1
                nw1.queue_article(plain_art)
                nw1.write()
                for _ in range(8):
                    nw1.read()
                    nw1.write()
                    if mock_queue.register_article.call_count >= 1:
                        break
                assert not nw1.raw_capture.active

                # Stage 2: the next ordinary article is pipelined and its response
                # begins arriving BEFORE the encrypted article is armed: a partial
                # read takes some of that response's bytes while the journal is
                # inactive (its storage was already cleared by the full release).
                plain2_art.fetcher = s1
                nw1.queue_article(plain2_art)
                nw1.write()
                nw1.read(nbytes=20)

                # Stage 3: now the encrypted article is armed and requested; its
                # response follows the partly-received ordinary one. take() must skip
                # the absent prefix of the ordinary response and still slice the
                # encrypted response exactly.
                enc_art.fetcher = s1
                nw1.queue_article(enc_art)
                nw1.write()
                for _ in range(8):
                    nw1.read()
                    nw1.write()
                    if any(call.args[0].article == "enc@e2e" for call in mock_cache.save_article.call_args_list):
                        break

                assert mock_queue.register_article.call_count >= 2
                assert mock_cache.save_article.call_count == 3
                saved = {call.args[0].article: bytes(call.args[1]) for call in mock_cache.save_article.call_args_list}
                assert saved["plain@e2e"] == plain_data
                assert saved["plain2@e2e"] == plain_data
                assert saved["enc@e2e"] == plaintext
        finally:
            srv.stop()

    @pytest.mark.parametrize("nbytes", [0, 900])
    def test_ordinary_only_reads_keep_bytes_and_full_buffer(self, nbytes):
        """No encrypted request: bare LF stays untouched and read limits stay upstream-exact."""
        server = mock.MagicMock(timeout=10, ssl=False)
        server.pipelining_requests = 1
        nw = NewsWrapper(server, thrdnum=1)
        dec = _FakeDecoder(1024)
        nw.decoder = dec
        nw.nntp = mock.MagicMock()
        nw.nntp.nw = nw
        raw = b"ordinary\nbare LF\r"

        def recv_into(buffer, nbytes):
            assert buffer is dec
            buffer[: len(raw)] = raw
            return len(raw)

        nw.nntp.sock.recv_into.side_effect = recv_into
        with mock.patch.object(sabnzbd, "Downloader", create=True):
            count, _ = nw.read(nbytes=nbytes)
        nw.nntp.sock.recv_into.assert_called_once_with(dec, nbytes=nbytes)
        assert count == len(raw)
        assert bytes(dec[:count]) == raw
        assert dec.processed == [len(raw)]
        assert not nw.raw_capture.active

    def test_plain_substitution_through_transport_still_fails_closed(self):
        """An ordinary yEnc article served to a declared-encrypted job through real
        transport must still release no plaintext (raw reconstruction fails closed)."""
        import sabctools

        password = "conformance-fixture-plain-sub"
        plain_data = b"plain unencrypted substitution!"
        encoded, crc = sabctools.yenc_encode(plain_data)
        plain_body = (
            b"=ybegin line=128 size=%d name=plain.bin\r\n" % len(plain_data)
            + encoded
            + b"\r\n=yend size=%d crc32=%08x\r\n" % (len(plain_data), crc)
        )
        srv, s1, art, mock_downloader, mock_bps, mock_cache, mock_queue = _transport_server_and_article(
            plain_body, password
        )

        try:
            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                nw1 = NewsWrapper(s1, thrdnum=1)
                s1.idle_threads.add(nw1)
                nw1.init_connect()
                for _ in range(50):
                    if nw1.connected:
                        break
                    time.sleep(0.05)
                _connect_and_fetch(nw1, s1, art)

                assert not mock_cache.save_article.called
                assert not art.on_disk
        finally:
            srv.stop()

    def test_capture_released_on_hard_reset(self):
        """Raw capture storage is released when the connection is reset."""

        server = mock.MagicMock()
        server.timeout = 10
        server.ssl = False
        server.pipelining_requests = 1

        nw = NewsWrapper(server, thrdnum=1)
        nw.decoder = _FakeDecoder(1024)
        nw.nntp = mock.MagicMock()
        nw.nntp.nw = nw
        nw.raw_capture.arm(mock.MagicMock(spec=Article, bytes=100))
        nw.raw_capture.add(b"x" * 100)

        with (mock.patch.object(sabnzbd, "Downloader", create=True) as mock_dl,):
            mock_dl.remove_socket = lambda nw: None
            nw.hard_reset(wait=False)

        assert nw.raw_capture.retained == 0

    def test_stale_cr_flag_cleared_by_reset_after_partial_read(self):
        """A read ending in bare '\\r' leaves the split-CRLF flag set; hard_reset rebuilds the
        wrapper, so a later CRLF split must not see the stale flag (which would turn '\\n'
        into '\\r\\r\\n' if it survived on the fresh connection)."""
        server = mock.MagicMock(timeout=10, ssl=False)
        server.pipelining_requests = 1
        nw = NewsWrapper(server, thrdnum=1)
        nw.decoder = _FakeDecoder(1024)
        nw.nntp = mock.MagicMock()
        nw.nntp.nw = nw
        art = mock.MagicMock(spec=Article)
        art.bytes = 1000
        art.nzf.nzo.yenc_encrypted = True
        art.nzf.nzo.precheck = False
        art.nzf.nzo.removed_from_queue = False
        nw.raw_capture.arm(art)

        nw.nntp.sock.recv_into.side_effect = lambda buf, nbytes: (buf.__setitem__(slice(0, 1), b"\r") or 1)
        with mock.patch.object(sabnzbd, "Downloader", create=True) as mock_dl:
            mock_dl.remove_socket = lambda nw: None
            nw.read()
            assert nw._prev_chunk_ended_with_cr
            nw.hard_reset(wait=False)
        assert not nw._prev_chunk_ended_with_cr

    def test_stale_cr_flag_cleared_by_init_connect(self):
        """init_connect recreates the decoder for a new connection; the split-CRLF flag
        must not carry over."""
        server = mock.MagicMock(timeout=10, ssl=False, addrinfo=("127.0.0.1", 119))
        server.pipelining_requests = 1
        nw = NewsWrapper(server, thrdnum=1)
        nw.decoder = _FakeDecoder(1024)
        nw._prev_chunk_ended_with_cr = True
        with mock.patch("sabnzbd.newswrapper.NNTP"):
            nw.init_connect()
        assert not nw._prev_chunk_ended_with_cr

    def test_raw_capture_bound_trips_fail_closed(self):
        """The enforced article bound drops the journal instead of growing it; take()
        then yields no capture and encrypted articles fail closed (never wrong output)."""
        from sabnzbd.newswrapper import _RawBodyCapture

        cap = _RawBodyCapture()
        cap._bound = 200  # direct bound for the unit test; production arms via arm()
        cap.add(b"a" * 100)
        assert cap.retained == 100
        # Bound trip: journal dropped, accounting continues
        cap.add(b"b" * 150)
        assert cap.retained == 0
        assert cap._dropped
        # Later slices are also unavailable (journal gone), never garbage
        assert cap.take(10) is None

    def test_raw_capture_arm_release_bookkeeping(self):
        """arm/release balance the bound; the last release clears storage."""
        from sabnzbd.newswrapper import _RawBodyCapture

        art = mock.MagicMock(spec=Article)
        art.bytes = 1000
        cap = _RawBodyCapture()
        assert not cap.active
        cap.arm(art)
        assert cap.active
        cap.add(b"data")
        cap.release(art)
        assert not cap.active
        assert cap.retained == 0

    def test_plain_article_release_does_not_destroy_encrypted_bound(self):
        """A plain article's discard/response release (even with a huge declared size)
        must not decrement another in-flight encrypted article's journal bound on a
        shared connection (release sites use the arming condition, precheck excluded)."""

        server = mock.MagicMock()
        server.timeout = 10
        server.pipelining_requests = 1

        nw = NewsWrapper(server, thrdnum=1)
        nw.decoder = _FakeDecoder(1024)
        nw.nntp = mock.MagicMock()
        nw.nntp.nw = nw

        enc_art = mock.MagicMock(spec=Article)
        enc_art.bytes = 1000
        enc_art.nzf.nzo.yenc_encrypted = True
        enc_art.nzf.nzo.precheck = False
        enc_art.nzf.nzo.removed_from_queue = False
        enc_art.nzf.nzo.allow_new_fetcher = mock.MagicMock()

        nw.raw_capture.arm(enc_art)
        nw.raw_capture.add(b"x" * 500)

        # Plain article on the same connection: its response slice is consumed from the
        # FIFO to stay aligned, but its release must not touch the encrypted bound.
        plain_art = mock.MagicMock(spec=Article)
        plain_art.bytes = 1_000_000
        plain_art.nzf.nzo.yenc_encrypted = False
        plain_art.nzf.nzo.precheck = False
        plain_art.nzf.nzo.removed_from_queue = False

        response = _mock_response()
        response.bytes_read = 100
        response.status_code = 222
        nw._with_raw_lines(plain_art, response)
        assert nw.raw_capture.active  # bound survived the plain release
        assert nw.raw_capture.retained == 400

        # discard() of the plain article also must not retire the encrypted bound
        nw.discard(plain_art, count_article_try=False)
        assert nw.raw_capture.active

        nw.raw_capture.release(enc_art)
        assert not nw.raw_capture.active

    def test_precheck_article_release_does_not_destroy_encrypted_bound(self):
        """A precheck encrypted article (which never armed) must not release the bound of
        an in-flight non-precheck encrypted article's journal."""
        server = mock.MagicMock()
        server.timeout = 10
        server.pipelining_requests = 1

        nw = NewsWrapper(server, thrdnum=1)
        nw.decoder = _FakeDecoder(1024)
        nw.nntp = mock.MagicMock()
        nw.nntp.nw = nw

        enc_art = mock.MagicMock(spec=Article)
        enc_art.bytes = 1000
        enc_art.nzf.nzo.yenc_encrypted = True
        enc_art.nzf.nzo.precheck = False
        enc_art.nzf.nzo.removed_from_queue = False

        nw.raw_capture.arm(enc_art)
        nw.raw_capture.add(b"y" * 300)

        precheck_art = mock.MagicMock(spec=Article)
        precheck_art.bytes = 999_999
        precheck_art.nzf.nzo.yenc_encrypted = True
        precheck_art.nzf.nzo.precheck = True
        precheck_art.nzf.nzo.removed_from_queue = False

        response = _mock_response()
        response.bytes_read = 100
        response.status_code = 222
        nw._with_raw_lines(precheck_art, response)
        nw.discard(precheck_art, count_article_try=False)
        assert nw.raw_capture.active
        assert nw.raw_capture.retained == 200

        nw.raw_capture.release(enc_art)
        assert not nw.raw_capture.active

    def test_never_armed_encrypted_discard_preserves_in_flight_journal(self):
        """release() retires only an article's own armed contribution: discarding a
        never-armed encrypted article of the same declared size must leave a
        co-pipelined in-flight encrypted article's bound and journaled bytes
        intact, and its slice must still be available. A second release of the
        already-released in-flight article is likewise a no-op (double release)."""
        server = mock.MagicMock()
        server.timeout = 10
        server.pipelining_requests = 1

        nw = NewsWrapper(server, thrdnum=1)
        nw.decoder = _FakeDecoder(1024)
        nw.nntp = mock.MagicMock()
        nw.nntp.nw = nw

        enc_art = mock.MagicMock(spec=Article)
        enc_art.bytes = 1000
        enc_art.nzf.nzo.yenc_encrypted = True
        enc_art.nzf.nzo.precheck = False
        enc_art.nzf.nzo.removed_from_queue = False

        nw.raw_capture.arm(enc_art)
        journaled = b"z" * 500
        nw.raw_capture.add(journaled)

        never_armed = mock.MagicMock(spec=Article)
        never_armed.bytes = 1000
        never_armed.nzf.nzo.yenc_encrypted = True
        never_armed.nzf.nzo.precheck = False
        never_armed.nzf.nzo.removed_from_queue = False

        # discard() of the never-armed encrypted article must not retire A's bound.
        nw.discard(never_armed, count_article_try=False)
        assert nw.raw_capture.active, "never-armed discard stole the in-flight bound"
        assert nw.raw_capture.retained == 500, "never-armed discard destroyed journaled bytes"
        # A's journaled bytes are still A's: the FIFO slice is intact.
        assert nw.raw_capture.take(500) == journaled

        # Response-completion release works once; a second release (e.g. a
        # following discard of the same article) must not clear the journal.
        nw.raw_capture.release(enc_art)
        assert not nw.raw_capture.active
        nw.raw_capture.release(enc_art)
        assert not nw.raw_capture.active

    def test_raw_capture_slices_pipelined_responses_exactly(self):
        """take() returns each response's exact bytes in FIFO order across pipelining."""
        from sabnzbd.newswrapper import _RawBodyCapture

        cap = _RawBodyCapture()
        cap._bound = 4096
        r1 = b"222 0 <a>\r\nLINE1\r\nLINE2\r\n.\r\n"
        r2 = b"430 No Such Article\r\n"
        cap.add(r1[:20])
        cap.add(r1[20:] + r2)

        assert cap.take(len(r1)) == r1
        assert cap.take(len(r2)) == r2
        assert cap.retained == 0
        assert cap.take(5) is None

    def test_raw_capture_take_spans_chunks_and_preserves_remainder(self):
        """take(n) returns up to n bytes in order across chunks, preserving the rest."""
        from sabnzbd.newswrapper import _RawBodyCapture

        cap = _RawBodyCapture()
        cap._bound = 4096
        assert cap.take(0) is None
        assert cap.take(5) is None  # journaled nothing yet: fails closed, stream untouched
        for chunk in (b"abc", b"defg", b"hi", b"jklm"):
            cap.add(chunk)
        # Take less than the head chunk, exactly to a boundary, across chunks, and the tail.
        assert cap.take(2) == b"ab"
        assert cap.take(1) == b"c"
        assert cap.take(4) == b"defg"
        assert cap.take(5) == b"hijkl"
        assert cap.retained == 1
        # Asking for more than retained fails closed and leaves the remainder intact.
        assert cap.take(2) is None
        assert cap.retained == 1
        assert cap.take(1) == b"m"
        assert cap.retained == 0
        assert cap.take(1) is None


def _registered_success(queue_mock) -> bool:
    """The success flag of the last NzbQueue.register_article call, positional or keyword."""
    call = queue_mock.register_article.call_args
    return call.kwargs["success"] if "success" in call.kwargs else call.args[1]


class TestBodyCommandForEncryptedArticles:
    """Encrypted articles are fetched with BODY so no ARTICLE header scan (or trial decryption) happens."""

    @staticmethod
    def _queued_command(have_body: bool, yenc_encrypted) -> bytes:
        from sabnzbd.newswrapper import NewsWrapper as _NW

        wrapper = mock.MagicMock(spec=_NW)
        wrapper.server = mock.Mock(have_body=have_body, timeout=5)
        article = mock.MagicMock(spec=Article)
        article.article = "cmd@test"
        article.nzf.nzo.precheck = False
        article.nzf.nzo.yenc_encrypted = yenc_encrypted
        _NW.queue_article(wrapper, article)
        return wrapper.queue_command.call_args[0][0]

    @pytest.mark.parametrize(
        ("have_body", "yenc_encrypted", "expected"),
        [
            (True, True, b"BODY <cmd@test>\r\n"),
            (False, True, b"BODY <cmd@test>\r\n"),  # encrypted: BODY even after the server refused BODY earlier
            (True, False, b"BODY <cmd@test>\r\n"),  # plain regression: unchanged
            (False, False, b"ARTICLE <cmd@test>\r\n"),  # plain regression: unchanged
        ],
    )
    def test_command_selection(self, have_body, yenc_encrypted, expected):
        assert self._queued_command(have_body, yenc_encrypted) == expected

    def test_220_response_on_encrypted_release_fails_closed_without_kdf(self):
        """An ARTICLE-style 220 with long header lines is rejected before any body scan or KDF call."""
        import io
        import sabctools
        import sabnzbd.decoder as decoder

        body_wire, *_ = _encrypted_wire(password="fixture-sb2-value", plaintext=b"never released")
        headers = b"Path: " + b"x" * 200 + b"\r\nSubject: " + b"y" * 200 + b"\r\n\r\n"
        wire = b"220 0 <a@t>\r\n" + headers + body_wire + b".\r\n"
        dec = sabctools.Decoder(len(wire))
        reader = io.BytesIO(wire)
        reader.readinto(dec)
        dec.process(len(wire))
        response = next(dec)
        assert response.status_code == 220

        article = mock.MagicMock(spec=Article)
        article.article = "a@t"
        article.nzf.nzo.yenc_encrypted = True
        article.nzf.nzo.password = "fixture-sb2-value"

        original = DecryptionAdapter.get_master_key
        with mock.patch.object(DecryptionAdapter, "get_master_key", autospec=True, side_effect=original) as kdf:
            with pytest.raises(YEncEncryptionCryptoError, match="not BODY"):
                decoder.decode_yenc(article, response)
            assert kdf.call_count == 0


class TestKeyCacheAndHeaderBounding:
    """Regression tests for key cache thread-safety and header bounding."""

    def test_adapter_key_cache_thread_safety(self):
        """DecryptionAdapter._key_cache thread-safety under concurrent access."""
        import concurrent.futures
        from sabnzbd.encryption import DecryptionAdapter

        adapter = DecryptionAdapter(password="conformance-fixture-concurrent-password")
        salt = bytes.fromhex("11223344556677889900aabbccddeeff")
        results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(adapter.get_master_key, salt) for _ in range(16)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        assert len(results) == 16
        # All threads must receive the identical derived key
        assert all(r == results[0] for r in results)
        assert len(results[0]) == 32
        # Exactly one entry in key cache
        assert salt in adapter._key_cache

    def test_restore_control_lines_header_bounded(self):
        """restore_control_lines decrypts only fixed header/footer positions (no data-line touch)."""
        from sabnzbd.encryption import DecryptionAdapter

        adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")
        salt = b"\x01" * 16
        master_key = adapter.get_master_key(salt)
        seg_idx = 1

        # Single-part: line 1 =ybegin, line 2 =yencryption, line 3 = data line, line 4 = =yend
        k1, t1 = adapter.derive_control_keys(master_key, seg_idx, 1)
        k2, t2 = adapter.derive_control_keys(master_key, seg_idx, 2)
        k4, t4 = adapter.derive_control_keys(master_key, seg_idx, 4)

        ct1 = ff1_encrypt(k1, t1, b"=ybegin line=128 size=50 name=test.bin")
        wire_line1 = salt + seg_idx.to_bytes(4, "big") + ct1 + b"\r\n"

        line2_pt = (
            f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={seg_idx:08x} tag={'00' * 16}"
        ).encode("ascii")
        assert len(line2_pt) == 128
        ct2 = ff1_encrypt(k2, t2, line2_pt)
        wire_line2 = ct2 + b"\r\n"

        data_line = b"PAYLOAD DATA LINE NOT CONTROL LINE\r\n"

        ct4 = ff1_encrypt(k4, t4, b"=yend size=50 crc32=12345678")
        wire_footer = ct4 + b"\r\n"

        wire_block = wire_line1 + wire_line2 + data_line + wire_footer

        orig_decrypt = adapter.decrypt_control_line
        decrypt_calls = []

        def tracked_decrypt(ct, enc_key, tweak):
            decrypt_calls.append(ct)
            return orig_decrypt(ct, enc_key, tweak)

        adapter.decrypt_control_line = tracked_decrypt
        restored, out_salt, out_idx = adapter.restore_control_lines(wire_block)

        # Header has 2 lines, footer is line 4 -> decrypt_control_line must be called exactly 3 times
        assert len(decrypt_calls) == 3, f"expected 3 header/footer decryptions, got {len(decrypt_calls)}"
        assert line2_pt in restored
        assert b"PAYLOAD DATA LINE" in restored
        assert out_salt == salt
        assert out_idx == seg_idx

    def test_restore_control_lines_trailing_blank_line_after_yend(self):
        """Trailing blank lines after =yend are ignored before footer line-index accounting.

        Control Lines Std v1.2 section 5: N is the index of the last non-empty physical
        line; a blank physical line after the encrypted =yend footer must not be treated
        as the footer (lineIndex N) — the footer keeps the tweak of its real position and
        the blank is outside the block (not carried into the restored block).
        """
        from sabnzbd.encryption import DecryptionAdapter

        adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")
        salt = b"\x02" * 16
        master_key = adapter.get_master_key(salt)
        seg_idx = 1

        # Single-part: line 1 =ybegin, line 2 =yencryption, line 3 = data, line 4 = =yend
        k1, t1 = adapter.derive_control_keys(master_key, seg_idx, 1)
        k2, t2 = adapter.derive_control_keys(master_key, seg_idx, 2)
        k4, t4 = adapter.derive_control_keys(master_key, seg_idx, 4)

        wire_line1 = (
            salt + seg_idx.to_bytes(4, "big") + ff1_encrypt(k1, t1, b"=ybegin line=128 size=50 name=test.bin") + b"\r\n"
        )
        line2_pt = (
            f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={seg_idx:08x} tag={'00' * 16}"
        ).encode("ascii")
        wire_line2 = ff1_encrypt(k2, t2, line2_pt) + b"\r\n"
        data_line = b"PAYLOAD DATA LINE NOT CONTROL LINE\r\n"
        wire_footer = ff1_encrypt(k4, t4, b"=yend size=50 crc32=12345678") + b"\r\n"

        # A blank physical line after =yend (joined as an extra CRLF) is the regression case;
        # also pin multiple trailing empties and a bare-LF empty tail.
        for empty_tail in (b"\r\n", b"\r\n\r\n", b"\n"):
            restored, out_salt, out_idx = adapter.restore_control_lines(
                wire_line1 + wire_line2 + data_line + wire_footer + empty_tail
            )
            assert out_salt == salt
            assert out_idx == seg_idx
            assert line2_pt in restored
            assert restored.endswith(b"=yend size=50 crc32=12345678\r\n")
            # Compare against the no-tail restoration, not a slice of the returned block.
            expected, _s, _i = adapter.restore_control_lines(wire_line1 + wire_line2 + data_line + wire_footer)
            assert restored == expected

    @pytest.mark.parametrize("blank_block", [b"\r\n", b"\n"])
    def test_restore_control_lines_only_blank_lines_fails_closed(self, blank_block):
        """A block of only blank lines raises YEncEncryptionCryptoError, not IndexError.

        The trailing-blank pop can empty raw_lines; restore_control_lines must fail
        closed (PROVIDER_FAILOVER) instead of indexing the now-empty list.
        """
        from sabnzbd.encryption import DecryptionAdapter

        adapter = DecryptionAdapter(password="public-conformance-vector-key-2026")
        with pytest.raises(YEncEncryptionCryptoError, match="Empty encrypted article block"):
            adapter.restore_control_lines(blank_block)

    def test_decoder_adapter_cached_on_nzo(self):
        """_get_decryption_adapter caches DecryptionAdapter on nzo to eliminate churn."""
        import sabnzbd.decoder as decoder

        mock_nzo = mock.MagicMock()
        mock_nzo.lock = threading.RLock()
        mock_nzo._decryption_adapter = None
        mock_nzo.password = "conformance-fixture-shared-password"

        mock_nzf = mock.MagicMock()
        mock_nzf.nzo = mock_nzo

        art1 = mock.MagicMock(spec=Article)
        art1.nzf = mock_nzf
        art1.password = None

        art2 = mock.MagicMock(spec=Article)
        art2.nzf = mock_nzf
        art2.password = None

        adapter1 = decoder._get_decryption_adapter(art1, "conformance-fixture-shared-password")
        adapter2 = decoder._get_decryption_adapter(art2, "conformance-fixture-shared-password")

        assert isinstance(adapter1, DecryptionAdapter)
        assert adapter1 is adapter2
        assert mock_nzo._decryption_adapter is adapter1


class TestDotUnstuffing:
    """Dot-stuffing transport boundary (RFC 3977 §3.1.1) for encrypted Line 1."""

    def test_dot_stuffed_line1_unstuffed_through_decode_path(self):
        """Regression: a dot-stuffed Line 1 (leading '..' on the wire) decodes with the exact original salt/index."""
        import nacl.bindings as nb
        import sabctools
        import sabnzbd.decoder as decoder

        password = "conformance-fixture-dot-stuff"
        # Line 1 plaintext content starts with a 0x2E salt byte -> producer dot-stuffs -> '..' on wire
        salt = b"\x2e" + b"\x11" * 15
        segment_index = 1
        plaintext = b"Dot stuffed bootstrap regression payload!"

        adapter = DecryptionAdapter(password=password)
        master_key = adapter.get_master_key(salt)
        nonce = adapter.derive_body_nonce(master_key, segment_index)

        aad = build_aad(b"dot.bin", 1, 1, len(plaintext))
        enc = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, master_key)
        ct = enc[:-16]
        tag = enc[-16:]
        body_encoded, body_crc = sabctools.yenc_encode(ct)

        line1_pt = f"=ybegin line=128 size={len(ct)} name=dot.bin".encode("ascii")
        line2_pt = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag.hex()}".encode(
            "ascii"
        )
        line4_pt = f"=yend size={len(ct)} crc32={body_crc:08x}".encode("ascii")

        k1, t1 = adapter.derive_control_keys(master_key, segment_index, 1)
        k2, t2 = adapter.derive_control_keys(master_key, segment_index, 2)
        k4, t4 = adapter.derive_control_keys(master_key, segment_index, 4)

        wire1 = salt + segment_index.to_bytes(4, "big") + ff1_encrypt(k1, t1, line1_pt)
        wire2 = ff1_encrypt(k2, t2, line2_pt)
        wire4 = ff1_encrypt(k4, t4, line4_pt)

        # Producer dot-stuffs Line 1 (its content byte 0 is 0x2E) -> '..' on the wire
        assert wire1[0:1] == b"."
        stuffed_wire1 = b"." + wire1

        article = mock.MagicMock(spec=Article)
        article.article = "dot@stuff"
        article.nzf.nzo.password = password
        article.nzf.nzo.yenc_encrypted = True

        resp = _mock_response()
        resp.sink_failed = False
        resp.bytes_decoded = 0
        resp.lines = [
            stuffed_wire1.decode("latin-1"),
            wire2.decode("latin-1"),
            body_encoded.decode("latin-1"),
            wire4.decode("latin-1"),
        ]

        decoded = decoder.decode_yenc(article, resp)
        assert decoded == bytearray(plaintext), "dot-stuffed Line 1 must decode to exact plaintext"


class TestUnauthenticatedPlainArticle:
    """Zero-Output Rule: plain article under a declared-encrypted release is rejected."""

    def _plain_response(self):
        import sabctools

        resp = _mock_response()
        resp.sink_failed = False
        resp.format = sabctools.EncodingFormat.YENC
        resp.data = bytearray(b"plain unencrypted content")
        resp.file_size = 100
        resp.part_begin = 0
        resp.part_size = len(resp.data)
        resp.bytes_decoded = len(resp.data)
        resp.file_name = "plain.bin"
        resp.crc = 0x12345678
        resp.lines = None
        return resp

    def _enc_article(self, nzo_yenc_encrypted=True):
        article = mock.MagicMock(spec=Article)
        article.article = "plain-sub@news"
        article.nzf.nzo.yenc_encrypted = nzo_yenc_encrypted
        article.nzf.nzo.precheck = False
        article.lowest_partnum = False
        return article

    def test_plain_article_rejected_when_release_declared_encrypted(self):
        """yenc_encrypted release + plain yEnc response raises UNAUTHENTICATED_ARTICLE and preserves metadata."""
        import sabnzbd.decoder as decoder

        nzf = mock.Mock()
        nzf.nzo.yenc_encrypted = True
        article = Article("plain-sub@news", 5, nzf)
        original = (article.file_size, article.data_begin, article.data_size, article.decoded_size, article.crc32)
        response = self._plain_response()

        with pytest.raises(ValueError, match="UNAUTHENTICATED_ARTICLE"):
            decoder.decode_yenc(article, response)
        assert (
            article.file_size,
            article.data_begin,
            article.data_size,
            article.decoded_size,
            article.crc32,
        ) == original

    def test_decode_routes_to_search_new_server_and_second_server_serves_authenticated_plaintext(self):
        """(2) decode() routes through search_new_server; second server's encrypted article decodes to authenticated plaintext only."""
        import nacl.bindings as nb
        import sabctools
        import sabnzbd.decoder as decoder

        password = "conformance-fixture-plain-sub-password"
        salt = bytes.fromhex("2a2b3c4d5e6f7890abcdef1234567890")
        segment_index = 1
        plaintext = b"Authenticated plaintext from the good server!"

        adapter = DecryptionAdapter(password=password)
        master_key = adapter.get_master_key(salt)
        nonce = adapter.derive_body_nonce(master_key, segment_index)
        aad = build_aad(b"good.bin", 1, 1, len(plaintext))
        enc = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, master_key)
        ct = enc[:-16]
        tag = enc[-16:]
        body_encoded, body_crc = sabctools.yenc_encode(ct)

        line1_pt = f"=ybegin line=128 size={len(ct)} name=good.bin".encode("ascii")
        line2_pt = f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={segment_index:08x} tag={tag.hex()}".encode(
            "ascii"
        )
        line4_pt = f"=yend size={len(ct)} crc32={body_crc:08x}".encode("ascii")

        k1, t1 = adapter.derive_control_keys(master_key, segment_index, 1)
        k2, t2 = adapter.derive_control_keys(master_key, segment_index, 2)
        k4, t4 = adapter.derive_control_keys(master_key, segment_index, 4)
        wire1 = salt + segment_index.to_bytes(4, "big") + ff1_encrypt(k1, t1, line1_pt)
        wire2 = ff1_encrypt(k2, t2, line2_pt)
        wire4 = ff1_encrypt(k4, t4, line4_pt)

        good_resp = _mock_response()
        good_resp.sink_failed = False
        good_resp.bytes_decoded = 0
        good_resp.lines = [
            wire1.decode("latin-1"),
            wire2.decode("latin-1"),
            body_encoded.decode("latin-1"),
            wire4.decode("latin-1"),
        ]

        article = self._enc_article()
        article.article = "art@e2e"
        article.nzf.nzo.password = password
        article.on_disk = False
        article.search_new_server.return_value = True

        plain_resp = self._plain_response()

        # decode_yenc on server 1's plain response raises retriable ValueError
        with pytest.raises(ValueError, match="UNAUTHENTICATED_ARTICLE"):
            decoder.decode_yenc(article, plain_resp)

        # decode() routes it to search_new_server (retriable tier), zero bytes stored
        mock_cache = mock.MagicMock()
        mock_queue = mock.MagicMock()
        with (
            mock.patch.object(sabnzbd, "ArticleCache", mock_cache, create=True),
            mock.patch.object(sabnzbd, "NzbQueue", mock_queue, create=True),
        ):
            # Server 1: plain article -> failover
            decoder.decode(article, plain_resp)
            assert article.search_new_server.called
            assert not mock_cache.save_article.called

            # Server 2: real encrypted article -> authenticated plaintext cached, server 1's bytes never appear
            mock_cache.reset_mock()
            decoded = decoder.decode_yenc(article, good_resp)
            assert bytes(decoded) == plaintext
            assert b"plain unencrypted content" not in bytes(decoded)

    def test_exhausted_servers_increments_bad_articles_with_zero_bytes_stored(self):
        """(3) Exhausted servers: bad_articles incremented, zero bytes stored."""
        import sabnzbd.decoder as decoder

        article = self._enc_article()
        article.article = "exhausted@e2e"
        article.search_new_server.return_value = False
        article.on_disk = False

        plain_resp = self._plain_response()

        mock_cache = mock.MagicMock()
        mock_queue = mock.MagicMock()
        with (
            mock.patch.object(sabnzbd, "ArticleCache", mock_cache, create=True),
            mock.patch.object(sabnzbd, "NzbQueue", mock_queue, create=True),
        ):
            # Servers exhausted: search_new_server returns False -> decode() cleanly registers
            # failure via NzbQueue.register_article(article, False) without crashing;
            # bad_articles already incremented and zero bytes were stored.
            decoder.decode(article, plain_resp)
            assert article.nzf.nzo.increase_bad_articles_counter.called
            assert not mock_cache.save_article.called
            mock_queue.register_article.assert_called_once_with(article, False)

    def test_uu_response_on_encrypted_job_routes_to_server_search_with_zero_cached_bytes(self):
        """A valid UU-encoded article on a declared-encrypted job is an unencrypted
        substitution: decode() must reject it before decode_uu and route to
        search_new_server with zero bytes cached (Zero-Output Rule)."""
        import sabctools
        import io
        import sabnzbd.decoder as decoder

        # Real native UU response produced through sabctools' transport state machine
        def uu_line(data: bytes) -> bytes:
            n = len(data)
            out = bytearray()
            out.append((n & 0x3F) + 32 if n else ord("`"))
            for i in range(0, n, 3):
                chunk = data[i : i + 3]
                while len(chunk) < 3:
                    chunk += b"\0"
                b1, b2, b3 = chunk
                out += bytes(
                    [
                        32 + ((b1 >> 2) & 0x3F),
                        32 + (((b1 << 4) | (b2 >> 4)) & 0x3F),
                        32 + (((b2 << 2) | (b3 >> 6)) & 0x3F),
                        32 + (b3 & 0x3F),
                    ]
                )
            return bytes(out) + b"\r\n"

        payload = b"valid uu payload"
        wire = b"222 0 <x>\r\n" b"begin 644 test.bin\r\n" + uu_line(payload) + b"`\r\n" b"end\r\n" b".\r\n"
        dec = sabctools.Decoder(len(wire))
        dec.expect(None)
        reader = io.BytesIO(wire)
        reader.readinto(dec)
        dec.process(len(wire))
        uu_resp = next(dec)
        assert uu_resp.format is sabctools.EncodingFormat.UU
        assert uu_resp.bytes_decoded == len(payload)

        article = self._enc_article()
        article.article = "uu-sub@news"
        article.nzf.nzo.password = "fixture-meta-value"
        article.lowest_partnum = False
        article.on_disk = False
        article.search_new_server.return_value = True

        mock_cache = mock.MagicMock()
        mock_queue = mock.MagicMock()
        with (
            mock.patch.object(sabnzbd, "ArticleCache", mock_cache, create=True),
            mock.patch.object(sabnzbd, "NzbQueue", mock_queue, create=True),
        ):
            decoder.decode(article, uu_resp)
            # Routed to server search, never handed to decode_uu, zero cached bytes
            assert article.search_new_server.called
            assert not mock_cache.save_article.called
            assert not article.on_disk


class TestStructuralNoPasswordEncryptedWire:
    """Encrypted wire with no resolvable password raises structural error, never on_disk."""

    def test_encrypted_wire_no_password_raises_structural(self):
        import sabctools
        import sabnzbd.decoder as decoder
        from sabnzbd.encryption import YEncEncryptionStructuralError

        article = mock.MagicMock(spec=Article)
        article.article = "nopass@enc"
        article.nzf.nzo.password = None
        article.nzf.nzo.yenc_encrypted = True
        article.nzf.nzo.precheck = False
        article.search_new_server.return_value = True
        article.on_disk = False

        resp = _mock_response()
        resp.sink_failed = False
        resp.format = sabctools.EncodingFormat.YENC
        resp.bytes_decoded = 0
        resp.lines = ["=ybegin line=128 size=50 name=test.bin", "AAAABBBBCCCCDDDDEEEE", "=yend size=50"]
        resp.data = None
        resp.crc = None

        with pytest.raises(YEncEncryptionStructuralError, match="MISSING_PASSWORD"):
            decoder.decode_yenc(article, resp)


class TestHeaderRegionFailClosed:
    """Fail-closed header-region FF1 error; byte-exact reconstruction (no lstrip masking)."""

    def _wire_block(self, adapter, salt, seg_idx, corrupt_line2=False):
        master_key = adapter.get_master_key(salt)
        k1, t1 = adapter.derive_control_keys(master_key, seg_idx, 1)
        k2, t2 = adapter.derive_control_keys(master_key, seg_idx, 2)
        k4, t4 = adapter.derive_control_keys(master_key, seg_idx, 4)

        ct1 = ff1_encrypt(k1, t1, b"=ybegin line=128 size=50 name=test.bin")
        wire_line1 = salt + seg_idx.to_bytes(4, "big") + ct1 + b"\r\n"

        if corrupt_line2:
            # Corrupt ciphertext so FF1 decryption raises (invalid Alphabet byte 0x00)
            wire_line2 = b"\x00" * 40 + b"\r\n"
        else:
            ct2 = ff1_encrypt(
                k2,
                t2,
                b"=yencryption cipher=XChaCha20-Poly1305 salt="
                + salt.hex().encode("ascii")
                + b" index=00000001 tag="
                + b"00" * 16,
            )
            wire_line2 = ct2 + b"\r\n"

        data_line = b"PAYLOAD DATA LINE\r\n"
        ct4 = ff1_encrypt(k4, t4, b"=yend size=50 crc32=12345678")
        wire_footer = ct4 + b"\r\n"
        return wire_line1 + wire_line2 + data_line + wire_footer

    def test_ff1_error_on_header_line_raises_provider_failover(self):
        """FF1 error on the fixed =yencryption position fails closed (never accepted as valid)."""
        adapter = DecryptionAdapter(password="conformance-fixture-test-password")
        salt = b"\x07" * 16
        wire_block = self._wire_block(adapter, salt, 1, corrupt_line2=True)

        with pytest.raises(ValueError):
            adapter.restore_control_lines(wire_block)

    def test_corrupt_header_line_never_appended_as_data_line(self):
        """The raw wire line of a failed header decryption is never accepted as data:
        extract_and_remove_yencryption fails closed on the restored block."""
        from sabnzbd.encryption import extract_and_remove_yencryption

        adapter = DecryptionAdapter(password="conformance-fixture-test-password")
        salt = b"\x08" * 16
        wire_block = self._wire_block(adapter, salt, 1, corrupt_line2=True)

        # The corrupted position either fails restoration outright or restores to a
        # non-=yencryption value; in both cases the block can never proceed to body
        # decryption (no =yencryption params are available).
        with pytest.raises(ValueError):
            restored, _s, _i = adapter.restore_control_lines(wire_block)
            extract_and_remove_yencryption(restored)


def _single_part_wire_lines(password: str, plaintext: bytes, name: bytes, segment_index: int = 1) -> list[str]:
    """Wire lines of a combined-mode single-part article with an arbitrary =ybegin name (Control Std v1.2 §5)."""
    import nacl.bindings as nb
    import sabctools

    salt = bytes.fromhex("9a8b7c6d5e4f30211f0e1d2c3b4a5968")
    adapter = DecryptionAdapter(password=password)
    master_key = adapter.get_master_key(salt)
    nonce = adapter.derive_body_nonce(master_key, segment_index)
    aad = build_aad(name, 1, 1, len(plaintext))
    enc = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, master_key)
    body_encoded, body_crc = sabctools.yenc_encode(enc[:-16])
    tag = enc[-16:]
    plain_lines = [
        b"=ybegin line=128 size=%d name=%s" % (len(plaintext), name),
        b"=yencryption cipher=XChaCha20-Poly1305 salt=%s index=%08x tag=%s"
        % (salt.hex().encode("ascii"), segment_index, tag.hex().encode("ascii")),
        None,  # data line, passed through untouched
        b"=yend size=%d crc32=%08x" % (len(plaintext), body_crc),
    ]
    wire: list[str] = []
    for line_index, pt in enumerate(plain_lines, start=1):
        if pt is None:
            wire.append(body_encoded.decode("latin-1"))
            continue
        if line_index == 1:
            k, t = adapter.derive_control_keys(master_key, segment_index, 1)
            wire.append((salt + segment_index.to_bytes(4, "big") + ff1_encrypt(k, t, pt)).decode("latin-1"))
        else:
            k, t = adapter.derive_control_keys(master_key, segment_index, line_index)
            wire.append(ff1_encrypt(k, t, pt).decode("latin-1"))
    return wire


class _FakeDecoder(bytearray):
    def __init__(self, size):
        super().__init__(size)
        self.processed = []
        self.pending = ()
        self.expected = 0

    def process(self, n):
        self.processed.append(n)

    def __iter__(self):
        return iter([])


class TestHeaderGeometryParsing:
    """Header-geometry parsing rules: keywords before name= decide multipart; missing
    AAD keywords (part=/begin=/end=/size=) fail closed instead of defaulting."""

    def test_single_part_name_containing_part_keyword_decodes(self):
        """Only keywords before name= decide multipart (Control Std v1.2 §5 step 4; Body Std §2.1)."""
        import sabnzbd.decoder as decoder

        plaintext = b"single-part payload whose name contains a part= keyword"
        wire = _single_part_wire_lines("conformance-fixture-conv-password", plaintext, b"my part=2.bin")
        article = mock.MagicMock(spec=Article)
        article.article = "conv_single_part@news"
        article.nzf.nzo.password = "conformance-fixture-conv-password"
        article.nzf.filename_checked = False
        article.lowest_partnum = True

        resp = _mock_response()
        resp.sink_failed = False
        resp.bytes_decoded = 0
        resp.lines = wire

        decoded = decoder.decode_yenc(article, resp)
        assert decoded == bytearray(plaintext)
        assert article.decoded_size == len(plaintext)

    def test_restore_marks_name_part_keyword_as_single_part(self):
        """At the restore seam: =yencryption stays at line 2 and the AAD uses single-part geometry."""
        from sabnzbd.encryption import extract_and_remove_yencryption

        plaintext = b"geometry check"
        adapter = DecryptionAdapter(password="conformance-fixture-conv-password")
        wire = (
            "\r\n".join(_single_part_wire_lines("conformance-fixture-conv-password", plaintext, b"my part=2.bin"))
            + "\r\n"
        )
        restored, _salt, _idx = adapter.restore_control_lines(wire.encode("latin-1"))
        assert restored.split(b"\r\n")[1].startswith(b"=yencryption")
        params, _clean = extract_and_remove_yencryption(restored)
        assert params["aad"] == build_aad(b"my part=2.bin", 1, 1, len(plaintext))

    def test_yencryption_extract_reports_real_file_name(self):
        """The real =ybegin name must reach filename detection.

        The sub-decoder only sees the neutralized name=x placeholder, so
        decode_yenc must take the name from the restored block, decoded the same
        way sabctools decodes name= for ordinary yEnc; otherwise an obfuscated
        NZB subject can never be renamed from the yEnc header (what ordinary
        yEnc still does via response.file_name)."""
        from sabnzbd.encryption import extract_and_remove_yencryption

        valid_hdr = b"=yencryption cipher=XChaCha20-Poly1305 salt=1a2b3c4d5e6f7890abcdef1234567890 index=00000001 tag=0cd77ce245a654463f90b945b1d22d5b"
        block = b"=ybegin line=128 size=10 name=Ubuntu.24.04.iso\r\n" + valid_hdr + b"\r\nDATA\r\n=yend size=10\r\n"
        params, clean = extract_and_remove_yencryption(block)
        assert params["file_name"] == "Ubuntu.24.04.iso"
        # The AAD still uses the raw name bytes (Body Std v1.2 §2.1)
        assert params["aad"] == build_aad(b"Ubuntu.24.04.iso", 1, 1, 10)
        # The =yencryption line was removed; the =ybegin line keeps the real name
        # (neutralization to name=x happens later, only for the sub-decoder feed)
        assert clean.startswith(b"=ybegin line=128 size=10 name=Ubuntu.24.04.iso\r\n")

        # Non-UTF-8 names decode like sabctools' latin-1 fallback for ordinary yEnc
        block_l1 = b"=ybegin line=128 size=10 name=caf\xe9.bin\r\n" + valid_hdr + b"\r\nDATA\r\n=yend size=10\r\n"
        params_l1, _ = extract_and_remove_yencryption(block_l1)
        assert params_l1["file_name"] == "café.bin"

        # A name containing " part=" still works and keeps the whole value
        block_part = b"=ybegin line=128 size=10 name=my part=2.bin\r\n" + valid_hdr + b"\r\nDATA\r\n=yend size=10\r\n"
        params_part, _ = extract_and_remove_yencryption(block_part)
        assert params_part["file_name"] == "my part=2.bin"

    def test_multipart_with_part_keyword_in_name_uses_header_part_number(self):
        """A multipart =ybegin takes part= from the header keywords, never from the name value."""
        from sabnzbd.encryption import extract_and_remove_yencryption

        valid_hdr = b"=yencryption cipher=XChaCha20-Poly1305 salt=1a2b3c4d5e6f7890abcdef1234567890 index=00000001 tag=0cd77ce245a654463f90b945b1d22d5b"
        block = (
            b"=ybegin part=3 total=5 line=128 size=20 name=x part=9.bin\r\n"
            b"=ypart begin=11 end=20\r\n" + valid_hdr + b"\r\nDATA\r\n=yend size=10 part=3\r\n"
        )
        params, _clean = extract_and_remove_yencryption(block)
        assert params["aad"] == build_aad(b"x part=9.bin", 3, 11, 10)

    @pytest.mark.parametrize(
        "ybegin_line, ypart_line",
        [
            (b"=ybegin part=1 total=1 line=128 size=10 name=f.bin", b"=ypart end=10"),
            (b"=ybegin part=1 total=1 line=128 size=10 name=f.bin", b"=ypart begin=1"),
            (b"=ybegin part=1 total=1 line=128 size=10 name=f.bin", b"=ypart begin=x end=10"),
            (b"=ybegin line=128 name=f.bin", None),
        ],
    )
    def test_missing_aad_geometry_fails_closed(self, ybegin_line, ypart_line):
        """A missing or malformed keyword the AAD needs is PROVIDER_FAILOVER, not a silent
        default (Body Std v1.2 §2.1: =ypart begin=/end=, =ybegin size=)."""
        from sabnzbd.encryption import extract_and_remove_yencryption

        valid_hdr = b"=yencryption cipher=XChaCha20-Poly1305 salt=1a2b3c4d5e6f7890abcdef1234567890 index=00000001 tag=0cd77ce245a654463f90b945b1d22d5b"
        block = ybegin_line + b"\r\n"
        if ypart_line is not None:
            block += ypart_line + b"\r\n"
        block += valid_hdr + b"\r\nDATA\r\n=yend size=10\r\n"
        with pytest.raises(YEncEncryptionCryptoError):
            extract_and_remove_yencryption(block)

    def test_restore_fails_closed_on_missing_yencryption_before_data(self):
        """The fixed =yencryption position is never silently treated as data (Control Std v1.2 §5 step 4b)."""
        adapter = DecryptionAdapter(password="conformance-fixture-conv-password")
        wire = "\r\n".join(_single_part_wire_lines("conformance-fixture-conv-password", b"abc", b"f.bin")) + "\r\n"
        lines = wire.split("\r\n")
        # Swap line 2 (=yencryption) for the footer position's data: restoration must raise, not pass through.
        broken = "\r\n".join([lines[0], lines[2], lines[1], lines[3]]).encode("latin-1") + b"\r\n"
        with pytest.raises(YEncEncryptionCryptoError):
            adapter.restore_control_lines(broken)

    def test_bare_lf_expansion_never_exceeds_buffer(self):
        """Reads on encrypted jobs leave room for bare-LF to CRLF expansion, so no article is lost."""
        server = mock.MagicMock()
        server.timeout = 10
        server.ssl = False
        server.pipelining_requests = 1

        buf_size = 64
        stream = b"\n" * (buf_size * 3)

        def run(encrypted):
            nw = NewsWrapper(server, thrdnum=1)
            dec = _FakeDecoder(buf_size)
            nw.decoder = dec
            nw.nntp = mock.MagicMock()
            nw.nntp.nw = nw
            position = 0
            seen = bytearray()

            def fake_recv_into(buf, nbytes=0):
                # Like socket.recv_into: fill at most nbytes (default: the whole buffer)
                nonlocal position
                count = min(nbytes or len(buf), len(buf), len(stream) - position)
                memoryview(buf)[:count] = stream[position : position + count]
                position += count
                return count

            def fake_process(count):
                seen.extend(dec[:count])

            dec.process = fake_process
            nw.nntp.sock.recv_into = fake_recv_into

            article = mock.MagicMock()
            article.nzf.nzo.yenc_encrypted = encrypted
            with (
                mock.patch.object(NewsWrapper, "article", new_callable=mock.PropertyMock) as mock_art_prop,
                mock.patch.object(sabnzbd, "Downloader", create=True),
            ):
                mock_art_prop.return_value = article
                while position < len(stream):
                    nw.read()
            return bytes(seen)

        # Unencrypted release: the ordinary path never rewrites the bytes
        assert run(False) == stream

        # Encrypted release: every bare LF becomes CRLF and no read overflows the buffer
        assert run(True) == stream.replace(b"\n", b"\r\n")


def test_encrypted_article_filename_detected_from_ybegin_name():
    """End to end: decode_yenc must pass the real =ybegin name to
    verify_nzf_filename, like the ordinary yEnc path does with
    response.file_name. The sub-decoder's response carries the neutralized
    name=x placeholder, so it can never be used for filename detection."""
    import sabnzbd.decoder as decoder

    password = "conformance-fixture-e2e-password"
    plaintext = b"payload for filename detection"
    article = mock.MagicMock(spec=Article)
    article.article = "filename@news"
    article.nzf.filename = "1a2b3c4d5e6f0123456789abcdef0123.01"  # obfuscated NZB subject
    article.nzf.filename_checked = False
    article.nzf.nzo.password = password
    article.lowest_partnum = True

    resp = _mock_response()
    resp.sink_failed = False
    resp.bytes_decoded = 0
    resp.lines = _single_part_wire_lines(password, plaintext, b"Ubuntu.24.04.iso")

    decoded = decoder.decode_yenc(article, resp)
    assert decoded == bytearray(plaintext)
    verify_args = article.nzf.nzo.verify_nzf_filename.call_args[0]
    assert verify_args[1] == "Ubuntu.24.04.iso", verify_args


def test_key_cache_replaces_on_new_salt():
    """The single-entry key cache keeps only the most recent salt's key (DoS bound)."""
    adapter = DecryptionAdapter(password="conformance-fixture-test-password")
    first_salt = bytes([1]) * 16
    first_key = adapter.get_master_key(first_salt)
    assert adapter._key_cache == {first_salt: first_key}

    second_salt = bytes([2]) * 16
    second_key = adapter.get_master_key(second_salt)
    assert adapter._key_cache == {second_salt: second_key}
    assert first_salt not in adapter._key_cache


@pytest.mark.parametrize("defect", ["missing_name", "empty_name", "missing_crc"])
def test_encrypted_missing_name_or_crc_fails_closed(defect):
    import sabnzbd.decoder as decoder

    password = "conformance-fixture-metadata-password"
    lines = _single_part_wire_lines(password, b"hello", b"valid.bin")
    first = lines[0].encode("latin-1")
    salt = first[:16]
    adapter = DecryptionAdapter(password=password)
    key = adapter.get_master_key(salt)
    index = 4 if defect == "missing_crc" else 1
    enc_key, tweak = adapter.derive_control_keys(key, 1, index)
    content = lines[index - 1].encode("latin-1")
    plain = adapter.decrypt_control_line(content[20:] if index == 1 else content, enc_key, tweak)
    if defect == "missing_crc":
        plain = plain.split(b" crc32=")[0]
    else:
        plain = plain.split(b" name=")[0] + (b" name=" if defect == "empty_name" else b"")
    encrypted = ff1_encrypt(enc_key, tweak, plain)
    lines[index - 1] = ((first[:20] + encrypted) if index == 1 else encrypted).decode("latin-1")
    article = mock.MagicMock(spec=Article)
    article.article = "metadata-defects@test"
    article.nzf.nzo.yenc_encrypted = True
    article.nzf.nzo.password = password
    response = _mock_response()
    response.sink_failed = False
    response.bytes_decoded = 0
    response.status_code = 222
    response.lines = lines
    with pytest.raises(YEncEncryptionCryptoError):
        decoder.decode_yenc(article, response)


class TestDeclaredGeometryLengthMismatch:
    """The AEAD tag authenticates the DECLARED geometry (=ybegin size / =ypart range
    in the AAD), not the plaintext itself. A corrupted or truncated-then-reCRC'd article
    could carry plaintext whose actual length differs from the declaration. sabctools'
    sub-decoder does not validate actual-vs-declared (part_size mirrors the declared
    keywords), so decode_yenc must reject the mismatch before any cache write.
    """

    @staticmethod
    def _wire_lines(plaintext: bytes, declared_bytes: int, salt, seg, master_key, multipart: bool):
        """Build encrypted wire lines whose AAD/tag use the DECLARED geometry, while the
        actual plaintext length may differ from it. Returns (lines, adapter)."""
        import nacl.bindings as nb
        import sabctools

        adapter = DecryptionAdapter(password="fixture-meta-value")
        nonce = adapter.derive_body_nonce(master_key, seg)
        aad = build_aad(b"test.bin", 1, 1, declared_bytes)
        enc = nb.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, master_key)
        ct, tag = enc[:-16], enc[-16:]
        body, crc = sabctools.yenc_encode(ct)

        if multipart:
            lines_pt = [
                f"=ybegin part=1 total=2 line=128 size={declared_bytes * 2} name=test.bin".encode(),
                f"=ypart begin=1 end={declared_bytes}".encode(),
                f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={seg:08x} tag={tag.hex()}".encode(),
                body,
                f"=yend size={declared_bytes * 2} part=1 pcrc32={crc:08x}".encode(),
            ]
            line_indices = [1, 2, 3, None, 5]
        else:
            lines_pt = [
                f"=ybegin line=128 size={declared_bytes} name=test.bin".encode(),
                f"=yencryption cipher=XChaCha20-Poly1305 salt={salt.hex()} index={seg:08x} tag={tag.hex()}".encode(),
                body,
                f"=yend size={declared_bytes} crc32={crc:08x}".encode(),
            ]
            line_indices = [1, 2, None, 4]

        lines = []
        for pt, li in zip(lines_pt, line_indices):
            if li is None:
                lines.append(pt.decode("latin-1"))
            elif li == 1:
                k, t = adapter.derive_control_keys(master_key, seg, 1)
                lines.append((salt + seg.to_bytes(4, "big") + ff1_encrypt(k, t, pt)).decode("latin-1"))
            else:
                k, t = adapter.derive_control_keys(master_key, seg, li)
                lines.append(ff1_encrypt(k, t, pt).decode("latin-1"))
        return lines, adapter

    @pytest.mark.parametrize(
        ("plaintext", "declared_bytes", "multipart", "should_fail"),
        [
            (b"actual payload!!", 26, False, True),  # single-part shorter
            (b"x" * 30, 26, False, True),  # single-part longer
            (b"actual payload!!", 26, True, True),  # multipart range mismatch
            (b"exact ten ok", 12, False, False),  # matching length decodes
        ],
    )
    def test_declared_geometry_vs_actual_length(self, plaintext, declared_bytes, multipart, should_fail):
        import sabnzbd.decoder as decoder

        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        adapter = DecryptionAdapter(password="fixture-meta-value")
        master_key = adapter.get_master_key(salt)
        lines, _ = self._wire_lines(plaintext, declared_bytes, salt, 1, master_key, multipart=multipart)

        article = mock.MagicMock(spec=Article)
        article.article = "length-check@test"
        article.nzf.nzo.password = "fixture-meta-value"
        article.nzf.filename_checked = True
        article.lowest_partnum = False
        original = (article.file_size, article.data_begin, article.data_size, article.decoded_size, article.crc32)

        resp = _mock_response()
        resp.lines = lines

        if should_fail:
            with pytest.raises(YEncEncryptionCryptoError, match="LENGTH_MISMATCH"):
                decoder.decode_yenc(article, resp)
            # Rejection must happen before article metadata mutation
            assert (
                article.file_size,
                article.data_begin,
                article.data_size,
                article.decoded_size,
                article.crc32,
            ) == original
        else:
            decoded = decoder.decode_yenc(article, resp)
            assert decoded == bytearray(plaintext)


class TestFF1ControlLineLengthLimit:
    """Cap each expensive FF1 control-line operation to 8192 ciphertext bytes.

    Control Lines Standard v1.2 §9 allows local receiver safety limits. FF1 over
    the 253-byte radix is quadratic in line length, so oversized control lines
    must be rejected before numeral conversion or FF1 rounds.
    """

    def test_ff1_decrypt_boundary_8192_and_8193(self, monkeypatch):
        """Deterministically assert 8192 bytes reaches FF1 primitive and 8193 reaches neither numeral conversion nor FF1."""
        import sabnzbd.encryption as enc

        key = b"\x01" * 32
        tweak = b"\x02" * 8

        b2n_calls = 0
        orig_b2n = enc.byte_to_numeral

        def spy_b2n(b: int) -> int:
            nonlocal b2n_calls
            b2n_calls += 1
            return orig_b2n(b)

        primitive_calls = []

        def mock_ff1_numerals(k: bytes, t: bytes, numerals: list[int], radix: int = 253) -> list[int]:
            primitive_calls.append((len(numerals), radix))
            return [0] * len(numerals)

        monkeypatch.setattr(enc, "byte_to_numeral", spy_b2n)
        monkeypatch.setattr(enc, "ff1_decrypt_numerals", mock_ff1_numerals)

        # 8192 bytes reaches numeral conversion and FF1 primitive
        ct_8192 = b"x" * 8192
        res_8192 = enc.ff1_decrypt(key, tweak, ct_8192)
        assert len(res_8192) == 8192
        assert b2n_calls == 8192
        assert len(primitive_calls) == 1
        assert primitive_calls[0] == (8192, 253)

        # Reset counters
        b2n_calls = 0
        primitive_calls.clear()

        # 8193 bytes raises YEncEncryptionCryptoError and reaches NEITHER
        ct_8193 = b"x" * 8193
        with pytest.raises(enc.YEncEncryptionCryptoError, match="Control line ciphertext too large"):
            enc.ff1_decrypt(key, tweak, ct_8193)

        assert b2n_calls == 0, "byte_to_numeral must not be called when ciphertext exceeds 8192 bytes"
        assert len(primitive_calls) == 0, "ff1_decrypt_numerals must not be called when ciphertext exceeds 8192 bytes"

    @pytest.mark.parametrize(
        ("position", "multipart"),
        [
            ("first_line", False),
            ("single_part_header", False),
            ("multipart_header_ypart", True),
            ("multipart_header_yencryption", True),
            ("footer", False),
        ],
    )
    def test_restore_control_lines_positions_boundary(self, position, multipart, monkeypatch):
        """Exercise first line, single/multipart header positions and footer through restoration with valid framing.

        Deterministically asserts that 8192 bytes ciphertext reaches FF1 primitive and 8193 bytes
        raises YEncEncryptionCryptoError without reaching numeral conversion or FF1.
        First-line content limit is 8212 bytes (20B bootstrap + 8192B ciphertext); terminators and
        bootstrap do not count toward the 8192-byte limit.
        """
        import sabnzbd.encryption as enc

        adapter = enc.DecryptionAdapter(password="conformance-fixture-test-password")
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        seg = 1
        master_key = adapter.get_master_key(salt)

        k1, t1 = adapter.derive_control_keys(master_key, seg, 1)
        k2, t2 = adapter.derive_control_keys(master_key, seg, 2)
        k3, t3 = adapter.derive_control_keys(master_key, seg, 3)

        if multipart:
            k_footer, t_footer = adapter.derive_control_keys(master_key, seg, 5)
            std_lines = {
                "line1": ff1_encrypt(k1, t1, b"=ybegin part=1 total=2 line=128 size=200 name=test.bin"),
                "line2": ff1_encrypt(k2, t2, b"=ypart begin=1 end=100"),
                "line3": ff1_encrypt(
                    k3,
                    t3,
                    b"=yencryption cipher=XChaCha20-Poly1305 salt="
                    + salt.hex().encode("ascii")
                    + f" index={seg:08x} tag={'00'*16}".encode("ascii"),
                ),
                "data": b"DATA LINE NOT TOUCHED",
                "footer": ff1_encrypt(k_footer, t_footer, b"=yend size=200 part=1 pcrc32=12345678"),
            }
        else:
            k_footer, t_footer = adapter.derive_control_keys(master_key, seg, 4)
            std_lines = {
                "line1": ff1_encrypt(k1, t1, b"=ybegin line=128 size=100 name=test.bin"),
                "line2": ff1_encrypt(
                    k2,
                    t2,
                    b"=yencryption cipher=XChaCha20-Poly1305 salt="
                    + salt.hex().encode("ascii")
                    + f" index={seg:08x} tag={'00'*16}".encode("ascii"),
                ),
                "data": b"DATA LINE NOT TOUCHED",
                "footer": ff1_encrypt(k_footer, t_footer, b"=yend size=100 crc32=12345678"),
            }

        def build_wire(ct_len: int) -> bytes:
            payload = b"x" * ct_len
            if position == "first_line":
                l1 = salt + seg.to_bytes(4, "big") + payload
                l2 = std_lines["line2"]
                l3 = std_lines["line3"] if multipart else std_lines["data"]
                l4 = std_lines["data"] if multipart else std_lines["footer"]
                lines = [l1, l2, l3, l4] + ([std_lines["footer"]] if multipart else [])
            elif position == "single_part_header":
                l1 = salt + seg.to_bytes(4, "big") + std_lines["line1"]
                lines = [l1, payload, std_lines["data"], std_lines["footer"]]
            elif position == "multipart_header_ypart":
                l1 = salt + seg.to_bytes(4, "big") + std_lines["line1"]
                lines = [l1, payload, std_lines["line3"], std_lines["data"], std_lines["footer"]]
            elif position == "multipart_header_yencryption":
                l1 = salt + seg.to_bytes(4, "big") + std_lines["line1"]
                lines = [l1, std_lines["line2"], payload, std_lines["data"], std_lines["footer"]]
            elif position == "footer":
                l1 = salt + seg.to_bytes(4, "big") + std_lines["line1"]
                if multipart:
                    lines = [l1, std_lines["line2"], std_lines["line3"], std_lines["data"], payload]
                else:
                    lines = [l1, std_lines["line2"], std_lines["data"], payload]
            else:
                raise ValueError(f"Unknown position: {position}")

            return b"\r\n".join(lines) + b"\r\n"

        ff1_primitive_calls = []
        orig_ff1_numerals = enc.ff1_decrypt_numerals

        def mock_ff1_numerals(k: bytes, t: bytes, numerals: list[int], radix: int = 253) -> list[int]:
            if len(numerals) == 8192:
                ff1_primitive_calls.append(len(numerals))
                if position == "first_line":
                    prefix = (
                        b"=ybegin part=1 total=2 line=128 size=200 name=test.bin"
                        if multipart
                        else b"=ybegin line=128 size=100 name=test.bin"
                    )
                elif position in ("single_part_header", "multipart_header_yencryption"):
                    prefix = (
                        b"=yencryption cipher=XChaCha20-Poly1305 salt="
                        + salt.hex().encode("ascii")
                        + f" index={seg:08x} tag={'00'*16}".encode("ascii")
                    )
                elif position == "multipart_header_ypart":
                    prefix = b"=ypart begin=1 end=100"
                elif position == "footer":
                    prefix = b"=yend size=200 part=1 pcrc32=12345678" if multipart else b"=yend size=100 crc32=12345678"
                else:
                    prefix = b"=yline"
                prefix_nums = [enc.byte_to_numeral(b) for b in prefix]
                pad = [enc.byte_to_numeral(ord(" "))] * (len(numerals) - len(prefix_nums))
                return prefix_nums + pad
            return orig_ff1_numerals(k, t, numerals, radix)

        monkeypatch.setattr(enc, "ff1_decrypt_numerals", mock_ff1_numerals)

        # 1. 8192 bytes reaches FF1 primitive
        wire_8192 = build_wire(8192)
        _restored, out_salt, out_idx = adapter.restore_control_lines(wire_8192)
        assert out_salt == salt
        assert out_idx == seg
        assert 8192 in ff1_primitive_calls

        # 2. 8193 bytes raises YEncEncryptionCryptoError and reaches neither conversion nor primitive
        wire_8193 = build_wire(8193)
        with pytest.raises(enc.YEncEncryptionCryptoError, match="Control line ciphertext too large"):
            adapter.restore_control_lines(wire_8193)

        assert 8193 not in ff1_primitive_calls, "8193 bytes must not reach ff1_decrypt_numerals"

    def test_first_line_total_content_limit_8212_bytes(self, monkeypatch):
        """First line content limit is exactly 8212 bytes (20B bootstrap + 8192B ciphertext).

        Bootstrap prefix and CRLF terminators do not count toward the 8192-byte limit.
        """
        import sabnzbd.encryption as enc

        adapter = enc.DecryptionAdapter(password="conformance-fixture-test-password")
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        seg = 1
        master_key = adapter.get_master_key(salt)

        k2, t2 = adapter.derive_control_keys(master_key, seg, 2)
        k4, t4 = adapter.derive_control_keys(master_key, seg, 4)

        wire_line2 = (
            ff1_encrypt(
                k2,
                t2,
                b"=yencryption cipher=XChaCha20-Poly1305 salt="
                + salt.hex().encode("ascii")
                + f" index={seg:08x} tag={'00'*16}".encode("ascii"),
            )
            + b"\r\n"
        )
        wire_data = b"DATA LINE\r\n"
        wire_footer = ff1_encrypt(k4, t4, b"=yend size=100 crc32=12345678") + b"\r\n"

        primitive_called_lengths = []
        orig_ff1_numerals = enc.ff1_decrypt_numerals

        def mock_ff1_numerals(k: bytes, t: bytes, numerals: list[int], radix: int = 253) -> list[int]:
            primitive_called_lengths.append(len(numerals))
            if len(numerals) == 8192:
                prefix = b"=ybegin line=128 size=100 name=test.bin"
                prefix_nums = [enc.byte_to_numeral(b) for b in prefix]
                pad = [enc.byte_to_numeral(ord(" "))] * (len(numerals) - len(prefix_nums))
                return prefix_nums + pad
            return orig_ff1_numerals(k, t, numerals, radix)

        b2n_calls = 0
        orig_b2n = enc.byte_to_numeral

        def spy_b2n(b: int) -> int:
            nonlocal b2n_calls
            b2n_calls += 1
            return orig_b2n(b)

        # 8212 content bytes (20B bootstrap + 8192B ciphertext) + 2B CRLF = 8214 bytes line
        ct_8192 = b"x" * 8192
        line1_content_8212 = salt + seg.to_bytes(4, "big") + ct_8192
        assert len(line1_content_8212) == 8212
        wire_8212 = line1_content_8212 + b"\r\n" + wire_line2 + wire_data + wire_footer

        monkeypatch.setattr(enc, "ff1_decrypt_numerals", mock_ff1_numerals)
        monkeypatch.setattr(enc, "byte_to_numeral", spy_b2n)

        _restored, out_salt, out_idx = adapter.restore_control_lines(wire_8212)
        assert 8192 in primitive_called_lengths
        assert b2n_calls >= 8192
        assert out_salt == salt
        assert out_idx == seg

        # 8213 content bytes (20B bootstrap + 8193B ciphertext) + 2B CRLF = 8215 bytes line
        primitive_called_lengths.clear()
        b2n_calls = 0

        ct_8193 = b"x" * 8193
        line1_content_8213 = salt + seg.to_bytes(4, "big") + ct_8193
        assert len(line1_content_8213) == 8213
        wire_8213 = line1_content_8213 + b"\r\n" + wire_line2 + wire_data + wire_footer

        with pytest.raises(enc.YEncEncryptionCryptoError, match="Control line ciphertext too large: 8193 bytes"):
            adapter.restore_control_lines(wire_8213)

        assert b2n_calls == 0, "No numeral conversion for 8193-byte line"
        assert len(primitive_called_lengths) == 0, "No FF1 primitive call for 8193-byte line"

    def test_oversized_control_line_decoder_retry_seam(self):
        """Oversized control line (>8192 bytes) raises YEncEncryptionCryptoError, is treated as provider
        corruption by decoder.decode(), triggers server retry, and releases no cache or disk output."""
        import sabnzbd.decoder as decoder

        password = "conformance-fixture-failover-password"
        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        segment_index = 1
        plaintext = b"Authenticated plaintext from good backup server!"

        # Server 1 response: oversized Line 1 ciphertext (8193 bytes)
        line1_oversized = salt + segment_index.to_bytes(4, "big") + (b"x" * 8193)
        oversized_resp = _mock_response()
        oversized_resp.sink_failed = False
        oversized_resp.status_code = 222
        oversized_resp.bytes_decoded = 0
        oversized_resp.lines = [
            line1_oversized.decode("latin-1"),
            "line2",
            "body",
            "line4",
        ]

        # Server 2 response: valid encrypted article
        good_body, _ad, _mk, _nonce, _ct, _tag, _crc, _aad, _n = _encrypted_wire(
            password=password,
            plaintext=plaintext,
            name="test.bin",
            salt=salt,
            segment_index=segment_index,
        )
        good_resp = _mock_response()
        good_resp.sink_failed = False
        good_resp.status_code = 222
        good_resp.bytes_decoded = 0
        good_resp.lines = [line.decode("latin-1") for line in good_body.split(b"\r\n") if line]

        # Mock article
        article = mock.MagicMock(spec=Article)
        article.article = "oversized-art@test"
        article.nzf.nzo.password = password
        article.nzf.nzo.yenc_encrypted = True
        article.nzf.nzo.precheck = False
        article.nzf.filename_checked = True
        article.lowest_partnum = False
        article.on_disk = False
        article.search_new_server.return_value = True

        # 1. Assert decode_yenc directly raises YEncEncryptionCryptoError on oversized response
        with pytest.raises(YEncEncryptionCryptoError, match="Control line ciphertext too large"):
            decoder.decode_yenc(article, oversized_resp)

        # 2. Assert decode() treats it as provider corruption (retries backup, zero output)
        mock_cache = mock.MagicMock()
        mock_queue = mock.MagicMock()
        with (
            mock.patch.object(sabnzbd, "ArticleCache", mock_cache, create=True),
            mock.patch.object(sabnzbd, "NzbQueue", mock_queue, create=True),
        ):
            # Attempt 1 (bad server with oversized control line):
            decoder.decode(article, oversized_resp)

            # Assert treated as provider corruption: retries backup server
            assert article.search_new_server.called, "Must trigger search_new_server for provider failover"
            # Assert zero output released from rejected attempt
            assert not mock_cache.save_article.called, "No cache output must be released from rejected attempt"
            assert not article.on_disk, "No disk output must be released from rejected attempt"

            # Attempt 2 (backup server succeeds with authenticated plaintext)
            mock_cache.reset_mock()
            article.search_new_server.reset_mock()

            decoder.decode(article, good_resp)
            assert mock_cache.save_article.called, "Backup server must save authenticated plaintext"
            _saved_art, saved_data = mock_cache.save_article.call_args[0]
            assert bytes(saved_data) == plaintext

    def test_oversized_control_line_downloader_dual_server_failover(self, caplog):
        """Dual-server failover: Server 1 delivers an oversized control line, is rejected as provider
        corruption, retries backup Server 2, and releases no cache or disk output from the rejected attempt."""
        password = "conformance-fixture-oversized-password"
        plaintext = b"Authenticated payload from backup server after oversized rejection!"

        valid_body, _adapter, _master_key, _nonce, _ct, _tag, _crc, _aad, _n = _encrypted_wire(
            password=password,
            plaintext=plaintext,
            name="test.bin",
        )

        salt = bytes.fromhex("1a2b3c4d5e6f7890abcdef1234567890")
        seg_idx = 1
        oversized_wire = (
            salt + seg_idx.to_bytes(4, "big") + (b"x" * 8193) + b"\r\n" + b"xx\r\n" + b"data\r\n" + b"yy\r\n"
        )

        srv1 = MockArticleNNTPServer(oversized_wire)
        srv1.start()
        srv2 = MockArticleNNTPServer(valid_body)
        srv2.start()

        try:
            s1 = _make_server(srv1, "srv_oversized", "Primary Bad Server", priority=0, pipelining=1)

            s2 = _make_server(srv2, "srv_good", "Backup Good Server", priority=1, pipelining=1)

            mock_downloader = _mock_downloader([s1, s2])

            mock_bps, mock_cache, mock_queue = _mock_services()
            art, mock_nzo = _enc_article("art@oversized", password)

            with _patched_services(mock_downloader, mock_bps, mock_cache, mock_queue):
                # 1. Connect NW1 to Server 1 (oversized article)
                nw1 = _connect_wrapper(s1)

                # Request article from Server 1
                art.fetcher = s1
                nw1.queue_article(art)
                nw1.write()
                nw1.read()

                # Server 1 must fail with provider failover
                assert s1 in art.try_list
                assert mock_bps.register_server_article_failed.called
                assert not mock_cache.save_article.called, "Zero-output: cache save must not be called"
                assert not art.on_disk, "Zero-output: article must not be marked on_disk"
                assert not mock_nzo.increase_bad_articles_counter.called

                # 2. Connect NW2 to Server 2 (valid article)
                nw2 = _connect_wrapper(s2)

                # Request article from Server 2
                art.fetcher = s2
                nw2.queue_article(art)
                nw2.write()
                nw2.read()

                # Server 2 must succeed and save authenticated plaintext
                assert mock_cache.save_article.called
                _saved_art, saved_data = mock_cache.save_article.call_args[0]
                assert bytes(saved_data) == plaintext

            log_text = caplog.text
            assert "Control line ciphertext too large" in log_text

        finally:
            srv1.stop()
            srv2.stop()
