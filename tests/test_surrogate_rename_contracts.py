"""Regression coverage for the destinations actually selected by renamer (#2947)."""

import hashlib
import logging
import os
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

import pytest

import sabnzbd
from sabnzbd import deobfuscate_filenames, filesystem, newsunpack, postproc
from sabnzbd.constants import DEF_FOLDER_MAX
from sabnzbd.nzb import NzbObject
from sabnzbd.par2file import FilePar2Info
from tests.testhelper import FakeHistoryDB, make_mock_nzo


@pytest.mark.platform("linux")
@pytest.mark.parametrize("checker", ["quick", "sfv"])
def test_verification_tracks_actual_surrogate_rename(fake_fs, checker):
    source = "/download/obfuscated"
    requested = "weird\udc96.r00"
    expected = "weird_.1.r00"
    fake_fs.create_file(source, contents=b"payload")
    fake_fs.create_file("/download/weird_.r00", contents=b"existing")
    nzf = mock.Mock(filename="obfuscated", filepath=source, crc32=1234, setname="obfuscated", vol=1)
    nzo = make_mock_nzo(download_path="/download", finished_files=[nzf])
    if checker == "quick":
        nzo.par2packs = {"set": {requested: FilePar2Info(requested, b"", 7, 1234)}}
        assert newsunpack.quick_check_set("set", nzo)
    else:
        with mock.patch.object(newsunpack, "parse_sfv", return_value={requested: b"000004d2"}):
            assert newsunpack.sfv_check(["/download/set.sfv"], nzo)
    assert nzf.filename == expected
    assert Path("/download", nzf.filename).read_bytes() == b"payload"
    assert nzf.setname == "weird_.1"
    nzo.renamed_file.assert_called_once_with({expected: "obfuscated"})
    assert Path("/download/weird_.r00").read_bytes() == b"existing"


@pytest.mark.platform("linux")
def test_par2_object_tracks_actual_surrogate_rename(fake_fs):
    fake_fs.create_file("/download/obfuscated", contents=b"payload")
    fake_fs.create_file("/download/set_.par2", contents=b"existing")
    nzf = mock.Mock(filename="obfuscated")
    nzo = make_mock_nzo(download_path="/download", md5of16k={})
    with (
        mock.patch("sabnzbd.nzb.object.analyse_par2", return_value=("set\udc96", 0, 0)),
        mock.patch("sabnzbd.nzb.object.parse_par2_file", return_value=("id", {"file": "metadata"})),
    ):
        NzbObject.handle_par2(nzo, nzf, "/download/obfuscated")
    assert nzf.filename == "set_.1.par2"
    assert Path("/download", nzf.filename).read_bytes() == b"payload"
    nzo.renamed_file.assert_called_once_with("set_.1.par2", "obfuscated")
    assert Path("/download/set_.par2").read_bytes() == b"existing"


@pytest.mark.platform("linux")
class TestSurrogateRenameContracts:
    @pytest.mark.config({"folder_rename": True, "deobfuscate_final_filenames": False})
    def test_process_job_tracks_actual_final_folder(self, fake_fs):
        temporary = "/complete/_UNPACK_job"
        files = [temporary + "/one.txt", temporary + "/two.txt"]
        for file in files:
            fake_fs.create_file(file, contents="payload")
        fake_fs.create_file("/complete/job_/keep", contents="existing")
        nzo = make_mock_nzo(download_path="/incomplete/job", unpack=True, pp_active=True, md5sum="")
        sorter = mock.Mock(sorter_active=False)
        with (
            FakeHistoryDB(":memory:") as history_db,
            mock.patch.object(sabnzbd, "db_pool", create=True) as pool,
            mock.patch.object(sabnzbd, "NzbQueue", create=True),
            mock.patch.multiple(
                postproc,
                globber=mock.Mock(return_value=["__admin__", "archive.rar"]),
                listdir_full=mock.Mock(return_value=[]),
                parring=mock.Mock(return_value=(False, False)),
                wait_for_direct_unpacker=mock.DEFAULT,
                prepare_extraction_path=mock.Mock(return_value=(temporary, "/complete/job\udc96", sorter, False, None)),
                unpacker=mock.Mock(return_value=(0, files)),
                set_permissions=mock.DEFAULT,
                make_script_path=mock.Mock(return_value=None),
                notifier=mock.DEFAULT,
                history_updated=mock.DEFAULT,
            ),
        ):
            pool.connection.return_value = nullcontext(history_db)
            postproc.process_job(nzo)
            history_db.execute("SELECT storage, status FROM history")
            rows = history_db.cursor.fetchall()
        assert [tuple(row) for row in rows] == [("/complete/job_.1", sabnzbd.constants.Status.COMPLETED)]
        assert Path("/complete/job_.1/one.txt").read_text() == "payload"
        assert Path("/complete/job_/keep").read_text() == "existing"

    @pytest.mark.parametrize("copy_fallback", [False, True])
    @pytest.mark.parametrize("overwrite", [False, True])
    @pytest.mark.parametrize("collision", ["none", "file", "directory", "link"])
    @pytest.mark.config(lambda params: {"overwrite_files": params["overwrite"]})
    def test_move_uses_one_surrogate_target(self, fake_fs, copy_fallback, overwrite, collision):
        source = "/download/original.txt"
        fake_fs.create_file(source, contents="new")
        fake_fs.create_dir("/complete")
        existing = "/complete/weird_.txt"
        if collision == "file":
            fake_fs.create_file(existing, contents="existing")
        elif collision == "directory":
            fake_fs.create_file(existing + "/keep", contents="existing")
        elif collision == "link":
            os.symlink("/missing", existing)
        expected = existing if collision == "none" else "/complete/weird_.1.txt"
        # Force the cross-device/error route below the real target-selection code.
        with (
            mock.patch.object(filesystem.shutil, "move", side_effect=OSError("cross-device"))
            if copy_fallback
            else mock.patch.object(filesystem.shutil, "move", wraps=filesystem.shutil.move)
        ):
            result = filesystem.move_to_path(source, "/complete/weird\udc96.txt", root="/complete")
        assert result == (True, expected)
        assert Path(expected).read_text() == "new"
        assert not os.path.exists(source)
        if collision == "file":
            assert Path(existing).read_text() == "existing"
        elif collision == "directory":
            assert Path(existing, "keep").read_text() == "existing"
            assert os.listdir(existing) == ["keep"]
        elif collision == "link":
            assert os.readlink(existing) == "/missing"

    @pytest.mark.parametrize("copy_fallback", [False, True])
    @pytest.mark.parametrize("overwrite", [False, True])
    @pytest.mark.config(lambda params: {"overwrite_files": params["overwrite"]})
    def test_ordinary_move_overwrite_policy(self, fake_fs, copy_fallback, overwrite):
        fake_fs.create_file("/download/file.txt", contents="new")
        fake_fs.create_file("/complete/file.txt", contents="existing")
        expected = "/complete/file.txt" if overwrite else "/complete/file.1.txt"
        with (
            mock.patch.object(filesystem.shutil, "move", side_effect=OSError("cross-device"))
            if copy_fallback
            else mock.patch.object(filesystem.shutil, "move", wraps=filesystem.shutil.move)
        ):
            assert filesystem.move_to_path("/download/file.txt", "/complete/file.txt") == (True, expected)
        assert Path(expected).read_text() == "new"
        if not overwrite:
            assert Path("/complete/file.txt").read_text() == "existing"

    @pytest.mark.parametrize("copy_fallback", [False, True])
    def test_prepared_surrogate_collision_suffix_is_not_sanitized_again(self, fake_fs, copy_fallback):
        source = "/download/original.txt"
        fake_fs.create_file(source, contents="new")
        existing = "/complete/" + "x" * 27 + "_.txt"
        requested = "/complete/" + "x" * 27 + "\udc96.txt"
        fake_fs.create_file(existing, contents="existing")
        expected = "/complete/" + "x" * 27 + "_.1.txt"
        with (
            mock.patch.object(filesystem, "DEF_FILE_MAX", 32),
            (
                mock.patch.object(filesystem.shutil, "move", side_effect=OSError("cross-device"))
                if copy_fallback
                else mock.patch.object(filesystem.shutil, "move", wraps=filesystem.shutil.move)
            ),
        ):
            assert filesystem.move_to_path(source, requested) == (True, expected)
        assert Path(expected).read_text() == "new"
        assert Path(existing).read_text() == "existing"

    @pytest.mark.config({"overwrite_files": True})
    def test_prepared_target_checked_before_overwrite(self, fake_fs):
        fake_fs.create_file("/download/original.txt", contents="new")
        fake_fs.create_file("/outside/keep.txt", contents="existing")
        fake_fs.create_dir("/complete")
        os.symlink("/outside", "/complete/link")
        assert filesystem.move_to_path(
            "/download/original.txt", "/complete/link/weird\udc96.txt", root="/complete"
        ) == (False, None)
        assert Path("/outside/keep.txt").read_text() == "existing"
        assert Path("/download/original.txt").read_text() == "new"
        assert os.listdir("/outside") == ["keep.txt"]

    @pytest.mark.parametrize("folder_rename", [False, True])
    @pytest.mark.config(lambda params: {"folder_rename": params["folder_rename"], "marker_file": ""})
    def test_prepare_extraction_surrogate_parent_collisions(self, fake_fs, folder_rename):
        fake_fs.create_file("/complete/job_/keep", contents="existing")
        fake_fs.create_file("/complete/_UNPACK_job_.1/keep", contents="unpacking")
        nzo = make_mock_nzo(final_name="job\udc96")
        sorter = mock.Mock(sorter_active=False)
        with mock.patch.object(postproc, "get_complete_directory", return_value=("/complete", sorter, True)):
            temporary, final, _, one_folder, _ = postproc.prepare_extraction_path(nzo)
        expected_final = "/complete/job_.1.1" if folder_rename else "/complete/job_.1"
        expected_temporary = "/complete/_UNPACK_job_.1.1" if folder_rename else expected_final
        assert temporary == expected_temporary
        assert final == expected_final
        assert os.path.isdir(temporary)
        temporary.encode("utf-8")
        final.encode("utf-8")
        assert not one_folder
        assert Path("/complete/job_/keep").read_text() == "existing"
        assert Path("/complete/_UNPACK_job_.1/keep").read_text() == "unpacking"

    @pytest.mark.config({"folder_rename": True, "marker_file": ""})
    def test_prepare_extraction_failed_rename_uses_original(self, fake_fs):
        fake_fs.create_dir("/complete")
        sorter = mock.Mock(sorter_active=False)
        with (
            mock.patch.object(postproc, "get_complete_directory", return_value=("/complete", sorter, True)),
            mock.patch.object(filesystem.shutil, "move", side_effect=OSError("read-only")),
        ):
            temporary, final, _, _, _ = postproc.prepare_extraction_path(make_mock_nzo(final_name="job"))
        assert temporary == final == "/complete/job"
        assert os.path.isdir(temporary)

    @pytest.mark.config({"folder_rename": True, "marker_file": "", "max_foldername_length": 32})
    def test_prepare_extraction_retains_renamer_truncation(self, fake_fs):
        fake_fs.create_dir("/complete")
        sorter = mock.Mock(sorter_active=False)
        with mock.patch.object(postproc, "get_complete_directory", return_value=("/complete", sorter, True)):
            temporary, final, _, _, _ = postproc.prepare_extraction_path(make_mock_nzo(final_name="x" * 32))
        assert temporary == "/complete/_UNPACK_" + "x" * 24
        assert final == "/complete/" + "x" * 32
        assert os.path.isdir(temporary)

    @pytest.mark.config({"folder_rename": True, "marker_file": "", "max_foldername_length": 32})
    def test_prepare_extraction_avoids_truncated_surrogate_parent_collision(self, fake_fs):
        occupied = "/complete/_UNPACK_" + "x" * 24
        fake_fs.create_file(occupied + "/keep", contents="existing")
        sorter = mock.Mock(sorter_active=False)
        with mock.patch.object(postproc, "get_complete_directory", return_value=("/complete", sorter, True)):
            temporary, final, _, _, _ = postproc.prepare_extraction_path(make_mock_nzo(final_name="x" * 31 + "\udc96"))
        assert temporary == occupied + ".1"
        assert final == "/complete/" + "x" * 31 + "_.1"
        assert os.path.isdir(temporary)
        assert os.listdir(temporary) == []
        assert os.listdir(occupied) == ["keep"]
        assert Path(occupied, "keep").read_text() == "existing"

    @pytest.mark.parametrize("max_length", [32, DEF_FOLDER_MAX])
    @pytest.mark.parametrize("surrogate", [False, True])
    @pytest.mark.parametrize("collapse", [False, True])
    @pytest.mark.config(
        lambda params: {"folder_rename": True, "marker_file": "", "max_foldername_length": params["max_length"]}
    )
    def test_preparation_to_finalization_preserves_unique_folder(self, fake_fs, max_length, surrogate, collapse):
        name = "x" * (max_length - 1) + ("\udc96" if surrogate else "_")
        occupied = "/complete/" + "x" * (max_length - 1) + "_"
        fake_fs.create_file(occupied + "/keep", contents="existing")
        sorter = mock.Mock(sorter_active=False)
        with mock.patch.object(postproc, "get_complete_directory", return_value=("/complete", sorter, True)):
            temporary, final, _, _, _ = postproc.prepare_extraction_path(make_mock_nzo(final_name=name))
        source = temporary + ("/child" if collapse else "")
        files = [source + "/one.txt", source + "/two.txt"]
        for file in files:
            fake_fs.create_file(file, contents="payload")
        actual_root, actual_files = postproc.rename_and_collapse_folder(temporary, final, files)
        assert actual_root == final
        assert actual_files == [final + "/one.txt", final + "/two.txt"]
        assert [Path(file).read_text() for file in actual_files] == ["payload", "payload"]
        assert os.listdir(occupied) == ["keep"]
        assert Path(occupied, "keep").read_text() == "existing"
        assert not os.path.exists(temporary)

    @pytest.mark.parametrize("operation", ["exists", "isdir", "listdir"])
    def test_history_inspection_unicode_failure_is_logged(self, fake_fs, caplog, operation):
        fake_fs.create_dir("/complete/job")
        target = postproc.os if operation == "listdir" else postproc.os.path
        error = UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogate")
        with caplog.at_level(logging.DEBUG), mock.patch.object(target, operation, side_effect=error):
            assert postproc.one_file_or_folder("/complete/job") == "/complete/job"
        assert "Cannot inspect or repair history path" in caplog.text

    @pytest.mark.parametrize("collapse", [False, True])
    def test_collapse_returns_actual_folder_and_files(self, fake_fs, collapse, caplog):
        source = "/complete/_UNPACK_job" + ("/child" if collapse else "")
        fake_fs.create_file(source + "/one.txt", contents="one")
        fake_fs.create_file(source + "/two.txt", contents="two")
        fake_fs.create_file("/complete/job_/keep", contents="existing")
        final, files = postproc.rename_and_collapse_folder(
            "/complete/_UNPACK_job", "/complete/job\udc96", [source + "/one.txt", source + "/two.txt"]
        )
        assert final == "/complete/job_.1"
        assert files == [final + "/one.txt", final + "/two.txt"]
        assert [Path(file).read_text() for file in files] == ["one", "two"]
        assert Path("/complete/job_/keep").read_text() == "existing"
        assert not os.path.exists("/complete/_UNPACK_job")
        # Parallel pytest workers must be able to serialize captured log text.
        caplog.text.encode("utf-8")

    @pytest.mark.parametrize("nested", [False, True])
    @pytest.mark.parametrize("error", [OSError("read-only"), UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogate")])
    def test_history_repair_failure_keeps_safe_parent_and_logs(self, fake_fs, caplog, nested, error):
        parent = "/complete/job" + ("/safe" if nested else "")
        fake_fs.create_file(parent + "/weird\udc96.txt", contents="original")
        with caplog.at_level(logging.DEBUG), mock.patch.object(postproc, "renamer", side_effect=error):
            assert postproc.one_file_or_folder("/complete/job") == parent
        assert Path(parent + "/weird\udc96.txt").read_text() == "original"
        assert "Cannot inspect or repair history path" in caplog.text
        parent.encode("utf-8")

    def test_par2_recovery_tracks_actual_surrogate_destination(self, fake_fs):
        fake_fs.create_file("/download/obfuscated", contents=b"payload")
        fake_fs.create_file("/download/weird_.txt", contents=b"existing")
        digest = hashlib.md5(b"payload").digest()

        def parse(_filename, hashes):
            hashes[digest] = "weird\udc96.txt"

        with (
            mock.patch.object(deobfuscate_filenames, "is_par2_file", return_value=True),
            mock.patch.object(deobfuscate_filenames, "parse_par2_file", side_effect=parse),
        ):
            files = deobfuscate_filenames.decode_par2("/download/metadata.par2")
        assert files == ["/download/weird_.1.txt"]
        assert Path(files[0]).read_bytes() == b"payload"
        assert Path("/download/weird_.txt").read_bytes() == b"existing"
