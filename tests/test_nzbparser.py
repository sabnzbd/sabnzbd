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
tests.test_nzbparser - Tests of basic NZB parsing
"""

import gzip
import logging
import os
import zipfile
from types import SimpleNamespace
from unittest import mock
import pytest
import sabnzbd
from sabnzbd.constants import AddNzbFileResult
from tests.testhelper import SAB_CACHE_DIR, SAB_DATA_DIR, create_and_read_nzb_fp
import sabnzbd.nzbparser as nzbparser
from sabnzbd.nzb import NzbObject
from sabnzbd.nzbqueue import NzbQueue
from sabnzbd.filesystem import save_compressed


def _write_nzb_gz(cache_dir: str, name: str, xml_content: str) -> str:
    path = os.path.join(cache_dir, f"{name}.nzb.gz")
    with gzip.open(path, "wb") as f:
        f.write(xml_content.encode("utf-8"))
    return path


def _make_nzb(meta_entries: list[tuple[str, str]]) -> str:
    metas = "\n".join(f'  <meta type="{t}">{v}</meta>' for t, v in meta_entries)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
 <head>
{metas}
 </head>
 <file poster="p@test.com" date="1600000000" subject="test.bin">
  <segments><segment bytes="1000" number="1">s1@test</segment></segments>
 </file>
</nzb>"""


@pytest.mark.usefixtures("clean_cache_dir")
class TestNzbParser:
    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_nzbparser(self):
        nzo = NzbObject("test_basic")
        # Create test file
        metadata = {"category": "test", "password": "testpass"}
        nzb_fp = create_and_read_nzb_fp("..", metadata=metadata)

        # Create folder and save compressed NZB like SABnzbd would do
        save_compressed(SAB_CACHE_DIR, "test", nzb_fp)
        nzb_file = os.path.join(SAB_CACHE_DIR, "test.nzb.gz")
        assert os.path.exists(nzb_file)

        # Files we expect
        test_dir = os.path.normpath(os.path.join(SAB_DATA_DIR, ".."))
        expected_files = [fl for fl in os.listdir(test_dir) if os.path.isfile(os.path.join(test_dir, fl))]
        expected_files.sort()
        assert expected_files

        # Parse the file
        nzbparser.nzbfile_parser(nzb_file, nzo)

        # Compare filenames
        resulting_files = [nzf.filename for nzf in nzo.files]
        resulting_files.sort()
        assert resulting_files == expected_files

        # Compare sizes
        expected_sizes = [os.path.getsize(os.path.join(test_dir, fl)) for fl in expected_files]
        expected_sizes.sort()
        resulting_sizes = [nzf.bytes for nzf in nzo.files]
        resulting_sizes.sort()
        assert resulting_sizes == expected_sizes

        # Check meta-data
        for field in metadata:
            assert [metadata[field]] == nzo.meta[field]

    @pytest.mark.xfail(reason="These tests should be added")
    def test_nzbparser_bad_stuff(self):
        # TODO: Add tests for:
        #  Duplicate parts
        #  Strange articles sizes
        #  Correct parsing of dates
        assert False

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_nzb_password_and_encryption_flag_parsing(self):
        archive_xml = """<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
 <head><meta type="password">fixture-archive-value</meta></head>
 <file poster="p@test.com" date="1600000000" subject="&quot;archive.rar&quot; yEnc (1/1)">
  <segments><segment bytes="1000" number="1">archive@test</segment></segments>
 </file>
</nzb>"""
        encrypted_xml = """<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
 <head>
  <meta type="password">fixture-encrypted-value</meta>
  <meta type="yenc_encrypted">true</meta>
 </head>
 <file poster="p@test.com" date="1600000000" subject="opaque">
  <segments><segment bytes="1000" number="1">encrypted@test</segment></segments>
 </file>
</nzb>"""
        explicit_xml = """<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
 <head><meta type="yenc_encrypted">true</meta></head>
 <file poster="p@test.com" date="1600000000" subject="opaque">
  <segments><segment bytes="1000" number="1">explicit@test</segment></segments>
 </file>
</nzb>"""

        archive_nzo = NzbObject("archive")
        nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "archive", archive_xml), archive_nzo)
        archive_nzo.files[0].finish_import()
        assert archive_nzo.meta["password"] == ["fixture-archive-value"]
        assert archive_nzo.yenc_encrypted is False

        encrypted_nzo = NzbObject("encrypted")
        nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "encrypted", encrypted_xml), encrypted_nzo)
        encrypted_nzo.files[0].finish_import()
        assert encrypted_nzo.meta["password"] == ["fixture-encrypted-value"]
        assert encrypted_nzo.yenc_encrypted is True

        # Explicit yenc_encrypted without password meta is a structural error at ingest
        from sabnzbd.encryption import YEncEncryptionStructuralError

        explicit_nzo = NzbObject("explicit")
        with pytest.raises(YEncEncryptionStructuralError, match="MISSING_PASSWORD"):
            nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "explicit", explicit_xml), explicit_nzo)

        empty_pw_xml = """<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
 <head><meta type="yenc_encrypted">true</meta><meta type="password"></meta></head>
 <file poster="p@test.com" date="1600000000" subject="opaque">
  <segments><segment bytes="1000" number="1">empty_pw@test</segment></segments>
 </file>
</nzb>"""
        empty_pw_nzo = NzbObject("empty_pw")
        with pytest.raises(YEncEncryptionStructuralError, match="MISSING_PASSWORD"):
            nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "empty_pw", empty_pw_xml), empty_pw_nzo)

        ws_pw_xml = """<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
 <head><meta type="yenc_encrypted">true</meta><meta type="password">   </meta></head>
 <file poster="p@test.com" date="1600000000" subject="opaque">
  <segments><segment bytes="1000" number="1">ws_pw@test</segment></segments>
 </file>
</nzb>"""
        ws_pw_nzo = NzbObject("ws_pw")
        with pytest.raises(YEncEncryptionStructuralError, match="MISSING_PASSWORD"):
            nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "ws_pw", ws_pw_xml), ws_pw_nzo)

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_encrypted_ingest_version_cipher_and_order_validation(self):
        """Validate supplied version/cipher/mode during ingest before NNTP, independent of meta tag order."""
        from sabnzbd.encryption import YEncEncryptionStructuralError

        # 1. Supported version and cipher present, standard ordering
        xml_ok = _make_nzb(
            [
                ("yenc_encrypted", "true"),
                ("yenc_version", "1.2"),
                ("yenc_cipher", "XChaCha20-Poly1305"),
                ("password", "fixture-nzb-meta-value"),
            ]
        )
        nzo_ok = NzbObject("ok")
        nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "ok", xml_ok), nzo_ok)
        assert nzo_ok.yenc_encrypted is True
        assert nzo_ok.meta["password"] == ["fixture-nzb-meta-value"]

        # 2. Version and cipher absent -> succeeds (defaults apply)
        xml_absent = _make_nzb(
            [
                ("password", "fixture-nzb-meta-absent"),
                ("yenc_encrypted", "true"),
            ]
        )
        nzo_absent = NzbObject("absent")
        nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "absent", xml_absent), nzo_absent)
        assert nzo_absent.yenc_encrypted is True
        assert nzo_absent.meta["password"] == ["fixture-nzb-meta-absent"]

        # 3. Independent of metadata ordering (reversed order)
        xml_reversed = _make_nzb(
            [
                ("password", "fixture-reversed-value"),
                ("yenc_cipher", "XChaCha20-Poly1305"),
                ("yenc_version", "1.2"),
                ("yenc_mode", "combined"),
                ("yenc_encrypted", "true"),
            ]
        )
        nzo_rev = NzbObject("reversed")
        nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "reversed", xml_reversed), nzo_rev)
        assert nzo_rev.yenc_encrypted is True
        assert nzo_rev.meta["password"] == ["fixture-reversed-value"]

        # 4. Unsupported version -> raises YEncEncryptionStructuralError
        xml_bad_ver = _make_nzb(
            [
                ("yenc_encrypted", "true"),
                ("yenc_version", "2.0"),
                ("password", "fixture-nzb-meta-value"),
            ]
        )
        with pytest.raises(YEncEncryptionStructuralError, match="UNSUPPORTED_VERSION"):
            nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, "bad_ver", xml_bad_ver), NzbObject("bad_ver"))

        # 5. Unsupported cipher -> raises YEncEncryptionStructuralError
        xml_bad_cipher = _make_nzb(
            [
                ("yenc_encrypted", "true"),
                ("yenc_cipher", "AES-256-GCM"),
                ("password", "fixture-nzb-meta-value"),
            ]
        )
        with pytest.raises(YEncEncryptionStructuralError, match="UNSUPPORTED_CIPHER"):
            nzbparser.nzbfile_parser(
                _write_nzb_gz(SAB_CACHE_DIR, "bad_cipher", xml_bad_cipher), NzbObject("bad_cipher")
            )

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_yenc_mode_meta_is_ignored(self):
        """No mode metadata exists (Body Std v1.2 §8, Control Std v1.2 §5): a yenc_mode tag has no effect."""
        for mode in ("combined", "body-only", "anything"):
            xml = f"""<?xml version="1.0" encoding="utf-8"?>
<nzb xmlns="http://www.newzbin.com/DTD/nzb/nzb-1.1.dtd">
 <head>
  <meta type="yenc_encrypted">true</meta>
  <meta type="yenc_mode">{mode}</meta>
  <meta type="password">fixture-nzb-meta-value</meta>
 </head>
 <file poster="p@test.com" date="1600000000" subject="test.bin">
  <segments><segment bytes="1000" number="1">mode_{mode}@test</segment></segments>
 </file>
</nzb>"""
            nzo = NzbObject(f"mode_{mode}")
            nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, f"mode_{mode}", xml), nzo)
            assert nzo.yenc_encrypted is True, mode
            assert nzo.meta["password"] == ["fixture-nzb-meta-value"], mode

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_yenc_meta_values_are_trimmed_and_ascii_case_insensitive(self):
        """Body Std v1.2 §8: values are trimmed before matching; the stored password is not trimmed."""
        from sabnzbd.encryption import YEncEncryptionStructuralError

        accepted = [
            [("yenc_encrypted", "TRUE"), ("password", "fixture-meta-one")],
            [("yenc_encrypted", " true "), ("password", "fixture-meta-two")],
            [
                ("yenc_encrypted", "true"),
                ("yenc_version", " 1.2 "),
                ("yenc_cipher", "xchacha20-poly1305"),
                ("password", "  padded fixture  "),
            ],
        ]
        for idx, entries in enumerate(accepted):
            nzo = NzbObject(f"accepted_{idx}")
            nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, f"accepted_{idx}", _make_nzb(entries)), nzo)
            assert nzo.yenc_encrypted is True, idx
        assert nzo.meta["password"] == ["  padded fixture  "]

        rejected = [
            ([("yenc_encrypted", "true"), ("yenc_version", "1.3"), ("password", "fixture-meta-value")], "UNSUPPORTED_VERSION"),
            ([("yenc_encrypted", "true"), ("yenc_cipher", "AES"), ("password", "fixture-meta-value")], "UNSUPPORTED_CIPHER"),
        ]
        for idx, (entries, token) in enumerate(rejected):
            with pytest.raises(YEncEncryptionStructuralError, match=token):
                nzbparser.nzbfile_parser(
                    _write_nzb_gz(SAB_CACHE_DIR, f"rejected_{idx}", _make_nzb(entries)), NzbObject(f"rejected_{idx}")
                )

        # Any other yenc_encrypted value means a plain NZB (Body Std v1.2 §8)
        plain = NzbObject("plain_yes")
        nzbparser.nzbfile_parser(
            _write_nzb_gz(SAB_CACHE_DIR, "plain_yes", _make_nzb([("yenc_encrypted", "yes")])), plain
        )
        assert plain.yenc_encrypted is False

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_empty_yenc_version_and_cipher_meta_are_rejected_for_encrypted_nzbs(self):
        """Body Std v1.2 §8: a present-but-empty yenc_version/yenc_cipher counts as a non-matching value,
        not as an absent entry; it must fail closed as METADATA_VALIDATION during real ingestion.
        Covers self-closing (<meta .../>) and explicit-empty (<meta ...></meta>) XML forms, plus a
        valid-nonempty-plus-empty duplicate of the same tag."""
        from sabnzbd.encryption import YEncEncryptionStructuralError

        # Both empty XML forms of both tags (self-closing and explicit empty), plus whitespace-only
        empty_declarations = [
            (
                [("yenc_encrypted", "true"), ("yenc_version", ""), ("password", "fixture-meta-value")],
                "UNSUPPORTED_VERSION",
                "ver_self_closing",
            ),
            (
                [("yenc_encrypted", "true"), ("yenc_version", ""), ("password", "fixture-meta-value")],
                "UNSUPPORTED_VERSION",
                "ver_explicit_empty",
            ),
            (
                [("yenc_encrypted", "true"), ("yenc_cipher", ""), ("password", "fixture-meta-value")],
                "UNSUPPORTED_CIPHER",
                "cipher_self_closing",
            ),
            (
                [("yenc_encrypted", "true"), ("yenc_cipher", ""), ("password", "fixture-meta-value")],
                "UNSUPPORTED_CIPHER",
                "cipher_explicit_empty",
            ),
            (
                [("yenc_encrypted", "true"), ("yenc_version", " "), ("password", "fixture-meta-value")],
                "UNSUPPORTED_VERSION",
                "ver_whitespace_only",
            ),
            (
                [("yenc_encrypted", "true"), ("yenc_cipher", " "), ("password", "fixture-meta-value")],
                "UNSUPPORTED_CIPHER",
                "cipher_whitespace_only",
            ),
        ]
        for entries, token, name in empty_declarations:
            xml = _make_nzb(entries)
            if name.endswith("_self_closing"):
                tag = "yenc_version" if "ver" in name else "yenc_cipher"
                xml = xml.replace(f'<meta type="{tag}"></meta>', f'<meta type="{tag}"/>')
            with pytest.raises(YEncEncryptionStructuralError, match=token):
                nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, name, xml), NzbObject(name))

        # Valid value plus an empty duplicate of the same tag: the empty entry must survive
        # collection and trip the existing validation gate
        for tag, token in (("yenc_version", "UNSUPPORTED_VERSION"), ("yenc_cipher", "UNSUPPORTED_CIPHER")):
            xml = _make_nzb(
                [
                    ("yenc_encrypted", "true"),
                    (tag, "1.2" if tag == "yenc_version" else "XChaCha20-Poly1305"),
                    (tag, ""),
                    ("password", "fixture-meta-value"),
                ]
            )
            with pytest.raises(YEncEncryptionStructuralError, match=token):
                nzbparser.nzbfile_parser(_write_nzb_gz(SAB_CACHE_DIR, f"dup_{tag}", xml), NzbObject(f"dup_{tag}"))

        # Unencrypted ordinary controls: empty/absent version and cipher meta have no effect
        # on a plain NZB and empty arbitrary metadata still stays discarded
        plain_nzo = NzbObject("plain_empty_meta")
        nzbparser.nzbfile_parser(
            _write_nzb_gz(
                SAB_CACHE_DIR,
                "plain_empty_meta",
                _make_nzb([("yenc_version", ""), ("yenc_cipher", ""), ("category", "movies")]),
            ),
            plain_nzo,
        )
        assert plain_nzo.yenc_encrypted is False
        assert plain_nzo.meta["category"] == ["movies"]

        # Arbitrary empty metadata stays discarded
        plain_arbitrary = NzbObject("plain_arbitrary")
        nzbparser.nzbfile_parser(
            _write_nzb_gz(
                SAB_CACHE_DIR,
                "plain_arbitrary",
                _make_nzb([("arbitrary_field", ""), ("category", "movies")]),
            ),
            plain_arbitrary,
        )
        assert "arbitrary_field" not in plain_arbitrary.meta
        assert plain_arbitrary.meta["category"] == ["movies"]

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_empty_yenc_version_and_cipher_meta_ingest_lifecycle(self, monkeypatch, tmp_path, caplog):
        """Through the real process_single_nzb ingestion path: empty self-closing or explicit-empty
        version/cipher declarations are logged as ERROR, the job is not added to the queue, and no
        article scheduling or provider query happens."""

        monkeypatch.setattr(sabnzbd.cfg.admin_dir, "get_path", lambda: str(tmp_path / "admin"))
        monkeypatch.setattr(sabnzbd.cfg.download_dir, "get_path", lambda: str(tmp_path / "downloads"))
        os.makedirs(str(tmp_path / "admin"), exist_ok=True)
        os.makedirs(str(tmp_path / "downloads"), exist_ok=True)

        sabnzbd.config.ConfigCat("*", {})
        sabnzbd.Scheduler = mock.Mock()
        sabnzbd.Scheduler.analyse = mock.Mock(return_value=False)
        sabnzbd.ArticleCache = mock.Mock()
        sabnzbd.Assembler = mock.Mock()
        sabnzbd.BPSMeter = mock.Mock()
        sabnzbd.Downloader = SimpleNamespace(paused=False, servers=[])
        sabnzbd.Downloader.highest_server = lambda server: True
        queue = NzbQueue()
        sabnzbd.NzbQueue = queue
        sabnzbd.PostProcessor = mock.Mock()
        try:
            cases = [
                ("ver_self_closing", '<meta type="yenc_version"/>', "UNSUPPORTED_VERSION"),
                ("cipher_self_closing", '<meta type="yenc_cipher"/>', "UNSUPPORTED_CIPHER"),
            ]
            for name, self_closing_meta, match_token in cases:
                xml = _make_nzb([("yenc_encrypted", "true"), ("password", "fixture-meta-value")])
                xml = xml.replace(
                    '  <meta type="password">fixture-meta-value</meta>',
                    f'  <meta type="password">fixture-meta-value</meta>\n  {self_closing_meta}',
                )
                nzb_path = _write_nzb_gz(SAB_CACHE_DIR, f"ingest_{name}", xml)

                caplog.set_level(logging.DEBUG)
                caplog.clear()
                with mock.patch.object(NzbQueue, "get_articles", wraps=queue.get_articles) as get_articles_mock:
                    result, nzo_ids = nzbparser.process_single_nzb(f"{name}.nzb.gz", path=nzb_path, keep=True)
                    assert result == AddNzbFileResult.ERROR
                    assert nzo_ids == []
                    assert get_articles_mock.call_count == 0
                assert any(record.levelno == logging.ERROR for record in caplog.records)
                assert "Structural yEnc-encryption failure" in caplog.text
                assert match_token in caplog.text
                assert queue.is_empty()

            # Explicit-empty form through real ingestion as well
            xml = _make_nzb([("yenc_encrypted", "true"), ("password", "fixture-meta-value"), ("yenc_cipher", "")])
            nzb_path = _write_nzb_gz(SAB_CACHE_DIR, "ingest_cipher_explicit_empty", xml)
            caplog.set_level(logging.DEBUG)
            caplog.clear()
            with mock.patch.object(NzbQueue, "get_articles", wraps=queue.get_articles) as get_articles_mock:
                result, nzo_ids = nzbparser.process_single_nzb("cipher_explicit_empty.nzb.gz", path=nzb_path, keep=True)
                assert result == AddNzbFileResult.ERROR
                assert nzo_ids == []
                assert get_articles_mock.call_count == 0
            assert any(record.levelno == logging.ERROR for record in caplog.records)
            assert "Structural yEnc-encryption failure" in caplog.text
            assert "UNSUPPORTED_CIPHER" in caplog.text
            assert queue.is_empty()

            # Valid-plus-empty duplicate through real ingestion
            xml_dup = _make_nzb(
                [
                    ("yenc_encrypted", "true"),
                    ("password", "fixture-meta-value"),
                    ("yenc_version", "1.2"),
                    ("yenc_version", ""),
                ]
            )
            nzb_path = _write_nzb_gz(SAB_CACHE_DIR, "ingest_ver_dup_empty", xml_dup)
            caplog.set_level(logging.DEBUG)
            caplog.clear()
            with mock.patch.object(NzbQueue, "get_articles", wraps=queue.get_articles) as get_articles_mock:
                result, nzo_ids = nzbparser.process_single_nzb("ver_dup_empty.nzb.gz", path=nzb_path, keep=True)
                assert result == AddNzbFileResult.ERROR
                assert nzo_ids == []
                assert get_articles_mock.call_count == 0
            assert any(record.levelno == logging.ERROR for record in caplog.records)
            assert "Structural yEnc-encryption failure" in caplog.text
            assert "UNSUPPORTED_VERSION" in caplog.text
            assert queue.is_empty()

            # Valid encrypted NZB with absent optional fields: ingests successfully
            absent_xml = _make_nzb([("yenc_encrypted", "true"), ("password", "fixture-meta-value")])
            absent_path = _write_nzb_gz(SAB_CACHE_DIR, "ingest_absent", absent_xml)
            result, nzo_ids = nzbparser.process_single_nzb("absent.nzb.gz", path=absent_path, keep=True)
            assert result == AddNzbFileResult.OK
            assert len(nzo_ids) == 1
            assert not queue.is_empty()
            nzo = queue.get_nzo(nzo_ids[0])
            assert nzo is not None
            assert nzo.yenc_encrypted is True
            queue.remove(nzo_ids[0], delete_all_data=True)

            # Ordinary control: a valid unencrypted NZB still ingests normally
            ordinary_path = _write_nzb_gz(
                SAB_CACHE_DIR,
                "ingest_ordinary",
                _make_nzb([("yenc_version", ""), ("yenc_cipher", ""), ("category", "movies")]),
            )
            result, nzo_ids = nzbparser.process_single_nzb("ordinary.nzb.gz", path=ordinary_path, keep=True)
            assert result == AddNzbFileResult.OK
            assert len(nzo_ids) == 1
            assert not queue.is_empty()
        finally:
            for attr in (
                "NzbQueue",
                "Downloader",
                "BPSMeter",
                "Assembler",
                "ArticleCache",
                "Scheduler",
                "PostProcessor",
            ):
                delattr(sabnzbd, attr)

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_encrypted_structural_failure_in_zip_archive_returns_error(self, monkeypatch, tmp_path):
        """SAB13-01: a structurally invalid encrypted NZB inside a zip archive maps to
        AddNzbFileResult.ERROR (not NO_FILES_FOUND) and leaves no job folder."""
        monkeypatch.setattr(sabnzbd.cfg.admin_dir, "get_path", lambda: str(tmp_path / "admin"))
        monkeypatch.setattr(sabnzbd.cfg.download_dir, "get_path", lambda: str(tmp_path / "downloads"))
        os.makedirs(str(tmp_path / "admin"), exist_ok=True)
        downloads_dir = tmp_path / "downloads"
        os.makedirs(str(downloads_dir), exist_ok=True)

        sabnzbd.config.ConfigCat("*", {})
        sabnzbd.Scheduler = mock.Mock()
        sabnzbd.Scheduler.analyse = mock.Mock(return_value=False)
        sabnzbd.ArticleCache = mock.Mock()
        sabnzbd.Assembler = mock.Mock()
        sabnzbd.BPSMeter = mock.Mock()
        sabnzbd.Downloader = SimpleNamespace(paused=False, servers=[])
        sabnzbd.Downloader.highest_server = lambda server: True
        queue = NzbQueue()
        sabnzbd.NzbQueue = queue
        sabnzbd.PostProcessor = mock.Mock()
        try:
            nzb_xml = _make_nzb([("yenc_encrypted", "true")])
            zip_path = str(tmp_path / "archive.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("inner.nzb", nzb_xml)

            result, nzo_ids = nzbparser.process_nzb_archive_file("archive.zip", path=zip_path, keep=True)
            assert result == AddNzbFileResult.ERROR
            assert nzo_ids == []
            assert queue.is_empty()
            # No job folder left in the downloads dir
            assert os.listdir(str(downloads_dir)) == []
        finally:
            for attr in (
                "NzbQueue",
                "Downloader",
                "BPSMeter",
                "Assembler",
                "ArticleCache",
                "Scheduler",
                "PostProcessor",
            ):
                delattr(sabnzbd, attr)


@pytest.mark.usefixtures("clean_cache_dir")
class TestNzbParserMetadataValidationVectors:
    """Vendored malformed_inputs.json metadata_validation vectors (metadata-01..03),
    each driven through the real nzbparser NZB-ingest seam (Body Std v1.2 §8,
    Control Std v1.2 §5: the METADATA_VALIDATION tier is structural and
    non-retriable, with zero output).

    The vectors carry no article bytes; each one is defined by its NZB head
    metadata (provenance/password), which differs per vector and is expressed
    here per vector id. Ordinary-NZB parsing is the control: with no transport
    decryption requested, the same head blocks stay plain (Body Std v1.2 §8)."""

    @staticmethod
    def _metadata_vector(vec_id: str) -> dict:
        vector_path = os.path.join(os.path.dirname(__file__), "data", "test-vectors", "malformed_inputs.json")
        import json

        with open(vector_path, encoding="utf-8") as fh:
            vectors = {vec["id"]: vec for vec in json.load(fh)["vectors"]}
        # A missing vendored vector fails here rather than silently skipping the assertion.
        vec = vectors[vec_id]
        assert vec["category"] == "metadata_validation", vec_id
        assert vec["expected_rejection_stage"] == "METADATA_VALIDATION", vec_id
        assert vec["provider_failover_permitted"] is False, vec_id
        assert vec["zero_output_required"] is True, vec_id
        return vec

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_metadata_01_missing_provenance_vector_ingest_is_plain(self):
        """metadata-01 (MISSING_ENCRYPTION_PROVENANCE): an NZB with a password but no
        yenc_encrypted provenance marker makes no transport claim. Body Std v1.2 §8:
        the marker is the sole provenance gate, so the job ingests as ordinary
        unencrypted yEnc and the password stays an archive password; no decryption
        is requested, so there is nothing to refuse at ingest. Vector ids are also
        exercised by the sibling test below for the positive-provenance control."""
        vec = self._metadata_vector("metadata-01-missing-provenance")
        assert vec["expected_error"] == "MISSING_ENCRYPTION_PROVENANCE"

        nzo = NzbObject("metadata_01")
        nzbparser.nzbfile_parser(
            _write_nzb_gz(SAB_CACHE_DIR, "metadata_01", _make_nzb([("password", "fixture-archive-value")])),
            nzo,
        )
        assert nzo.yenc_encrypted is False
        assert nzo.meta["password"] == ["fixture-archive-value"]

        # Positive control from the same matrix row family: with the provenance
        # marker present and a password, the identical ingest is encrypted, so the
        # plain outcome above is caused by the missing marker alone.
        encrypted = NzbObject("metadata_01_control")
        nzbparser.nzbfile_parser(
            _write_nzb_gz(
                SAB_CACHE_DIR,
                "metadata_01_control",
                _make_nzb([("yenc_encrypted", "true"), ("password", "fixture-archive-value")]),
            ),
            encrypted,
        )
        assert encrypted.yenc_encrypted is True

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_metadata_02_false_provenance_vector_ingest_is_plain(self):
        """metadata-02 (INVALID_ENCRYPTION_PROVENANCE): yenc_encrypted set to a value
        other than "true" (here "false") is not transport provenance. Body Std v1.2 §8:
        any value other than "true" (trimmed, ASCII case-insensitive) is treated as a
        standard unencrypted NZB, so this ingests plain with an archive password."""
        vec = self._metadata_vector("metadata-02-false-provenance")
        assert vec["expected_error"] == "INVALID_ENCRYPTION_PROVENANCE"

        nzo = NzbObject("metadata_02")
        nzbparser.nzbfile_parser(
            _write_nzb_gz(
                SAB_CACHE_DIR,
                "metadata_02",
                _make_nzb([("yenc_encrypted", "false"), ("password", "fixture-archive-value")]),
            ),
            nzo,
        )
        assert nzo.yenc_encrypted is False
        assert nzo.meta["password"] == ["fixture-archive-value"]

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_metadata_03_missing_password_vector_ingest_rejected(self):
        """metadata-03 (MISSING_PASSWORD): yenc_encrypted=true with no password meta
        (and no other password source on the job) must be refused at ingest as a
        structural METADATA_VALIDATION failure, before any article fetch."""
        from sabnzbd.encryption import YEncEncryptionStructuralError

        vec = self._metadata_vector("metadata-03-missing-password")
        assert vec["expected_error"] == "MISSING_PASSWORD"

        nzo = NzbObject("metadata_03")
        with pytest.raises(YEncEncryptionStructuralError, match="MISSING_PASSWORD"):
            nzbparser.nzbfile_parser(
                _write_nzb_gz(
                    SAB_CACHE_DIR,
                    "metadata_03",
                    _make_nzb([("yenc_encrypted", "true")]),
                ),
                nzo,
            )

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_metadata_03_missing_password_vector_ingest_lifecycle(self, monkeypatch, tmp_path, caplog):
        """metadata-03 through the real process_single_nzb ingestion path: the job is
        logged as an ERROR, is not added to the queue, and no article scheduling or
        provider query happens (structural refusal before NNTP)."""
        monkeypatch.setattr(sabnzbd.cfg.admin_dir, "get_path", lambda: str(tmp_path / "admin"))
        monkeypatch.setattr(sabnzbd.cfg.download_dir, "get_path", lambda: str(tmp_path / "downloads"))
        os.makedirs(str(tmp_path / "admin"), exist_ok=True)
        os.makedirs(str(tmp_path / "downloads"), exist_ok=True)

        sabnzbd.config.ConfigCat("*", {})
        sabnzbd.Scheduler = mock.Mock()
        sabnzbd.Scheduler.analyse = mock.Mock(return_value=False)
        sabnzbd.ArticleCache = mock.Mock()
        sabnzbd.Assembler = mock.Mock()
        sabnzbd.BPSMeter = mock.Mock()
        sabnzbd.Downloader = SimpleNamespace(paused=False, servers=[])
        sabnzbd.Downloader.highest_server = lambda server: True
        queue = NzbQueue()
        sabnzbd.NzbQueue = queue
        sabnzbd.PostProcessor = mock.Mock()
        try:
            nzb_path = _write_nzb_gz(
                SAB_CACHE_DIR,
                "metadata_03_ingest",
                _make_nzb([("yenc_encrypted", "true")]),
            )
            caplog.set_level(logging.DEBUG)
            caplog.clear()
            with mock.patch.object(NzbQueue, "get_articles", wraps=queue.get_articles) as get_articles_mock:
                result, nzo_ids = nzbparser.process_single_nzb("metadata_03_ingest.nzb.gz", path=nzb_path, keep=True)
                assert result == AddNzbFileResult.ERROR
                assert nzo_ids == []
                assert get_articles_mock.call_count == 0
            assert any(record.levelno == logging.ERROR for record in caplog.records)
            assert "Structural yEnc-encryption failure" in caplog.text
            assert "MISSING_PASSWORD" in caplog.text
            assert queue.is_empty()
        finally:
            for attr in (
                "NzbQueue",
                "Downloader",
                "BPSMeter",
                "Assembler",
                "ArticleCache",
                "Scheduler",
                "PostProcessor",
            ):
                delattr(sabnzbd, attr)
