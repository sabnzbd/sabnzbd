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
tests.test_newsunpack - Tests of various functions in newspack
"""

import datetime
import glob
import io
import json
import logging
import os
import os.path
import shutil
import stat
import sys
import tarfile
import threading
from typing import Optional
from unittest import mock
from unittest.mock import call

import pytest
import sabctools

import sabnzbd
import sabnzbd.newsunpack as newsunpack
import sabnzbd.par2repair as par2repair
from sabnzbd.constants import JOB_ADMIN, Status
from sabnzbd.par2file import FilePar2Info
from tests.testhelper import SAB_CACHE_DIR, make_mock_nzo
from sabnzbd.misc import format_time_string, SABRarFile
from sabnzbd.filesystem import long_path, build_filelists, create_all_dirs, listdir_full, clip_path


@pytest.fixture(autouse=True)
def _isolate_newsunpack_globals(monkeypatch):
    """Snapshot the module globals that these tests mutate so they can't leak into other
    tests/modules on the same pytest-xdist worker"""
    for name in (
        "NICE_COMMAND",
        "IONICE_COMMAND",
        "RAR_COMMAND",
        "SEVENZIP_COMMAND",
    ):
        monkeypatch.setattr(newsunpack, name, getattr(newsunpack, name))
    # PostProcessor is unset by default; raising=False lets monkeypatch delete it on teardown
    monkeypatch.setattr(sabnzbd, "PostProcessor", getattr(sabnzbd, "PostProcessor", None), raising=False)
    yield


class TestNewsUnpackFunctions:
    def test_is_sfv_file(self):
        assert newsunpack.is_sfv_file("tests/data/good_sfv_unicode.sfv")
        assert newsunpack.is_sfv_file("tests/data/one_line.sfv")
        assert not newsunpack.is_sfv_file("tests/data/only_comments.sfv")
        assert not newsunpack.is_sfv_file("tests/data/random.bin")

    def test_file_join_refuses_a_link_as_target(self, tmp_path):
        """A dangling link left behind by another extractor is not a free name, so joining
        must not write the result through it"""
        base = str(tmp_path)
        download_path = os.path.join(base, "job")
        workdir_complete = os.path.join(base, "complete")
        os.mkdir(download_path)
        os.mkdir(workdir_complete)
        outside = os.path.join(base, "outside.bin")

        joinables = []
        for num in (1, 2):
            joinable = os.path.join(download_path, "victim.%03d" % num)
            with open(joinable, "wb") as part:
                part.write(b"part%d" % num)
            joinables.append(joinable)
        # The link sits where the joined file is written, not next to the parts
        os.symlink(os.path.join("..", "outside.bin"), os.path.join(workdir_complete, "victim"))

        nzo = make_mock_nzo(download_path=download_path)

        failed, newfiles = newsunpack.file_join(nzo, workdir_complete, joinables)

        assert not os.path.exists(outside), "written through the link to %s" % outside
        assert failed
        assert not newfiles

    def test_file_join_refuses_a_link_in_a_parent(self, tmp_path):
        """A linked directory on the way to the joined name redirects the append"""
        base = str(tmp_path)
        download_path = os.path.join(base, "job")
        workdir_complete = os.path.join(base, "complete")
        outside = os.path.join(base, "outside")
        os.makedirs(os.path.join(download_path, "sub"))
        os.makedirs(workdir_complete)
        os.makedirs(outside)
        os.symlink(outside, os.path.join(workdir_complete, "sub"))

        joinables = []
        for num in (1, 2):
            joinable = os.path.join(download_path, "sub", "victim.%03d" % num)
            with open(joinable, "wb") as part:
                part.write(b"part%d" % num)
            joinables.append(joinable)

        nzo = make_mock_nzo(download_path=download_path)

        failed, newfiles = newsunpack.file_join(nzo, workdir_complete, joinables)

        assert not os.listdir(outside), "joined through the link into %s" % outside
        assert failed
        assert not newfiles

    def test_sfv_check_blocks_path_traversal(self, tmp_path):
        """A traversing SFV filename must not move a file out of the job directory"""
        download_path = str(tmp_path)
        obfuscated_name = "6f1ed002ab5595859014ebf0951522d9"
        obfuscated_path = os.path.join(download_path, obfuscated_name)
        with open(obfuscated_path, "wb") as test_file:
            test_file.write(b"payload")

        # SFV entry with matching crc32 but a traversing target name
        sfv_path = os.path.join(download_path, "check.sfv")
        with open(sfv_path, "w") as sfv_file:
            sfv_file.write("../escaped.bin deadbeef\n")

        nzf = mock.Mock(filename=obfuscated_name, filepath=obfuscated_path, crc32=0xDEADBEEF)
        nzo = make_mock_nzo(download_path=download_path, finished_files=[nzf])

        assert newsunpack.sfv_check([sfv_path], nzo) is False
        assert not os.path.exists(os.path.join(download_path, os.pardir, "escaped.bin"))
        assert os.path.exists(obfuscated_path)

    def test_is_sevenfile(self, monkeypatch):
        # False, because the command is not set. Force it explicitly: SEVENZIP_COMMAND
        # is a module global that another test in this class may have populated via
        # find_programs(), and under pytest-xdist tests share no ordering guarantee.
        monkeypatch.setattr(newsunpack, "SEVENZIP_COMMAND", None)
        assert not newsunpack.SEVENZIP_COMMAND
        assert not newsunpack.is_sevenfile("tests/data/test_7zip/testfile.7z")

        # Set the command to get some real results
        newsunpack.find_programs(".")
        assert newsunpack.SEVENZIP_COMMAND
        assert not newsunpack.is_sevenfile("tests/data/only_comments.sfv")
        assert not newsunpack.is_sevenfile("tests/data/random.bin")
        assert not newsunpack.is_sevenfile("tests/data/par2file/basic_16k.par2")
        assert newsunpack.is_sevenfile("tests/data/test_7zip/testfile.7z")

    def test_sevenzip(self):
        # Make the test self-sufficient: SEVENZIP_COMMAND is a module global and
        # under pytest-xdist this test may land on a worker where no earlier test
        # called find_programs(), leaving it None (SevenZip would then wrongly raise
        # "File is not a 7zip file"). find_programs() is idempotent.
        newsunpack.find_programs(".")
        testzip = newsunpack.SevenZip("tests/data/test_7zip/testfile.7z")
        assert testzip.namelist() == ["My_Test_Download.bin"]
        # Basic check that we can get data from the 7zip
        assert len(testzip.open(testzip.namelist()[0]).read()) == 102400

        # Test with a non-7zip file
        with pytest.raises(TypeError):
            newsunpack.SevenZip("tests/data/basic_rar5/testfile.rar")


class TestPar2MultipleSets:
    @staticmethod
    def _make_nzo(tmp_path):
        for name in ("a.bin", "b.bin", "dupe.bin", "A.par2", "B.par2"):
            (tmp_path / name).write_bytes(b"x")
        info = FilePar2Info("", b"", 1)
        return make_mock_nzo(
            download_path=str(tmp_path),
            extrapars={"A": [], "B": []},
            par2packs={"A": {"a.bin": info}, "B": {"b.bin": info}},
        )

    def test_another_sets_files_are_not_scanned_as_extras(self, tmp_path):
        nzo = self._make_nzo(tmp_path)
        extras = newsunpack._par2_extra_files(str(tmp_path / "A.par2"), nzo, "A")
        assert sorted(os.path.basename(path) for path in extras) == ["a.bin", "dupe.bin"]

    def test_another_sets_files_are_not_deleted_as_consumed(self, tmp_path):
        nzo = self._make_nzo(tmp_path)
        session = mock.Mock()
        session.repairer.files = [{"name": "a.bin", "target": str(tmp_path / "a.bin")}]
        session.repairer.renames = {}
        session.blocks_from = {str(tmp_path / "a.bin"): 1, str(tmp_path / "b.bin"): 1, str(tmp_path / "dupe.bin"): 1}
        assert newsunpack._consumed_extra_files(session, nzo, "A", []) == [str(tmp_path / "dupe.bin")]

    def test_an_extra_file_named_like_a_target_elsewhere_is_still_consumed(self, tmp_path):
        nzo = self._make_nzo(tmp_path)
        os.mkdir(tmp_path / "sub")
        session = mock.Mock()
        session.repairer.files = [{"name": "sub/c.bin", "target": str(tmp_path / "sub" / "c.bin")}]
        session.repairer.renames = {}
        session.blocks_from = {str(tmp_path / "c.bin"): 1}
        assert newsunpack._consumed_extra_files(session, nzo, "A", []) == [str(tmp_path / "c.bin")]


class TestPar2RepairFailures:
    def test_running_out_of_memory_fails_without_fetching_another_par2(self, tmp_path):
        nzo = make_mock_nzo(download_path=str(tmp_path), extrapars={"test": []})
        session = mock.Mock(last_error=None)
        session.open.return_value = sabctools.Par2Result.MEMORY_ERROR
        with (
            mock.patch.object(par2repair, "get_session", return_value=None),
            mock.patch.object(par2repair, "create_session", return_value=session),
        ):
            result = newsunpack.par2_verify_and_repair(str(tmp_path / "test.par2"), nzo, "test", [])
        assert result == (False, False, [], [])
        assert "Out of memory" in nzo.fail_msg
        nzo.add_parfile.assert_not_called()

    def test_extra_par2_files_that_will_not_load_say_why(self, tmp_path):
        nzo = make_mock_nzo(download_path=str(tmp_path), extrapars={"test": []})
        session = mock.Mock()
        session.add_parfiles.side_effect = sabctools.Par2Error("could not read vol01")
        with mock.patch.object(par2repair, "get_session", return_value=session):
            result = newsunpack.par2_verify_and_repair(str(tmp_path / "test.par2"), nzo, "test", [])
        assert result == (False, False, [], [])
        assert "could not read vol01" in nzo.fail_msg
        assert nzo.status == Status.FAILED

    @pytest.mark.parametrize(
        "result, verified",
        [
            (sabctools.Par2Result.SUCCESS, True),
            (sabctools.Par2Result.REPAIR_POSSIBLE, True),
            (sabctools.Par2Result.REPAIR_NOT_POSSIBLE, True),
            (sabctools.Par2Result.FILE_IO_ERROR, False),
            (sabctools.Par2Result.MEMORY_ERROR, False),
        ],
    )
    def test_only_a_verify_that_ran_to_its_end_counts(self, tmp_path, result, verified):
        session = par2repair.RepairSession(make_mock_nzo(download_path=str(tmp_path)), "test", str(tmp_path / "t.par2"))
        session.repairer = mock.Mock()
        session.repairer.verify.return_value = result
        session.verify()
        assert session.verified is verified


@pytest.mark.usefixtures("clean_cache_dir")
class TestPar2Repair:
    @staticmethod
    def _run_par2repair(test_dir, caplog, break_file=None, remove_file=None):
        # Create data-directory with copy of our test-files
        temp_test_dir = os.path.join(SAB_CACHE_DIR, "par2repair_temp")
        test_dir_admin = os.path.join(temp_test_dir, JOB_ADMIN)
        os.mkdir(temp_test_dir)
        assert os.path.exists(temp_test_dir)
        os.mkdir(test_dir_admin)
        assert os.path.exists(test_dir_admin)

        # Copy all test files
        for file in glob.glob(test_dir + "/*"):
            shutil.copy(file, temp_test_dir)

        # Break a specific file, if requested
        if break_file:
            with open(os.path.join(temp_test_dir, break_file), "wb") as bf:
                bf.seek(10)
                bf.write(b"booh")

        # Remove a specific file, if requested
        if remove_file:
            os.unlink(os.path.join(temp_test_dir, remove_file))

        # Make sure all programs are found
        newsunpack.find_programs(".")

        # Needed to store the POpen-reference
        sabnzbd.PostProcessor = mock.Mock()

        # Mock basic NZO structure
        nzo = make_mock_nzo(
            download_path=temp_test_dir,
            admin_path=test_dir_admin,
            extrapars={"test": []},
            par2packs={"test": None},
            par2_sessions={},
        )

        for file in glob.glob(test_dir + "/*.par2"):
            # Simple NZF mock for the filename
            parfile = mock.Mock()
            parfile.filename = os.path.basename(file)
            nzo.extrapars["test"].append(parfile)

        # Run repair
        with caplog.at_level(logging.DEBUG):
            readd, result = newsunpack.par2_repair(nzo=nzo, setname="test")

        # Verify we only have the rar-files left
        dir_contents = os.listdir(temp_test_dir)
        dir_contents.sort()

        # Always cleanup, to be sure
        shutil.rmtree(temp_test_dir)
        assert not os.path.exists(temp_test_dir)

        # Verify result
        assert result
        assert not readd

        # Verify history updates
        # Try with multiple values, as it can take longer sometimes
        for text in ("[test] Verified in %s, repair is required", "[test] Repaired in %s"):
            for i in range(10):
                try:
                    nzo.set_unpack_info.assert_has_calls([call("Repair", text % format_time_string(i))])
                    break
                except AssertionError:
                    pass
            else:
                # It never succeeded
                raise AssertionError("Failed to match: %s" % text)

        # Check externally
        return nzo, dir_contents

    def test_basic(self, caplog):
        # Run code
        nzo, dir_contents = self._run_par2repair("tests/data/par2repair/basic", caplog)

        assert dir_contents == [
            "__ADMIN__",
            "notarealfile.rar",
            "par2test.part1.rar",
            "par2test.part2.rar",
            "par2test.part3.rar",
            "par2test.part4.rar",
            "par2test.part5.rar",
            "par2test.part6.rar",
        ]

        # The two badly named files par2 did match are renamed to their real names
        nzo.renamed_file.assert_has_calls(
            [
                call(
                    {
                        "par2test.part3.rar": "foorbar.rar",
                        "par2test.part4.rar": "stillrarbutnotagoodname.txt",
                    }
                )
            ]
        )

        # Progress reporting
        actions = [c.args for c in nzo.set_action_line.call_args_list]
        assert ("Repair", "Quick Checking") in actions
        assert ("Repair", "Starting Repair") in actions
        assert ("Verifying", "01/06") in actions
        assert ("Verifying", "06/06") in actions
        assert ("Repairing", "%2d%%" % 0) in actions
        assert any(a[0] == "Verifying repair" for a in actions)

    def test_filejoin(self, caplog):
        # Run code
        nzo, dir_contents = self._run_par2repair("tests/data/par2repair/filejoin", caplog)

        # All joinable files will be removed
        assert dir_contents == ["__ADMIN__", "par2test.bin"]

        # There are no renames in case of filejoin by par2repair!
        nzo.renamed_file.assert_not_called()

        # Progress reporting
        actions = [c.args for c in nzo.set_action_line.call_args_list]
        assert ("Repair", "Quick Checking") in actions
        assert ("Repair", "Starting Repair") in actions
        assert ("Verifying", "01/01") in actions
        assert ("Repairing", "%2d%%" % 0) in actions
        assert any(a[0] == "Verifying repair" for a in actions)

    def test_broken_filejoin(self, caplog):
        # Run code
        nzo, dir_contents = self._run_par2repair(
            "tests/data/par2repair/filejoin", caplog, break_file="par2test.bin.005", remove_file="par2test.bin.010"
        )

        # There are no renames in case of filejoin by par2repair!
        nzo.renamed_file.assert_not_called()

        # All joinable files should be removed
        assert dir_contents == ["__ADMIN__", "par2test.bin"]

        # Progress reporting
        actions = [c.args for c in nzo.set_action_line.call_args_list]
        assert ("Repair", "Quick Checking") in actions
        assert ("Repair", "Starting Repair") in actions
        assert ("Verifying", "01/01") in actions
        assert ("Repairing", "%2d%%" % 0) in actions
        assert any(a[0] == "Verifying repair" for a in actions)


class TestPar2RepairParfile:
    def test_a_par2_file_still_downloading_is_not_picked_first(self, tmp_path):
        pending = mock.Mock(filename="set.vol000+001.par2", completed=False)
        done = mock.Mock(filename="set.par2", completed=True)
        for nzf in (pending, done):
            (tmp_path / nzf.filename).write_bytes(b"")
        nzo = make_mock_nzo(download_path=str(tmp_path), extrapars={"set": [pending, done]})

        with (
            mock.patch.object(newsunpack, "quick_check_set", return_value=False),
            mock.patch.object(newsunpack, "build_filelists", return_value=([], [], [], [], [])),
            mock.patch.object(newsunpack, "par2_verify_and_repair", return_value=(False, False, [], [])) as repair,
        ):
            newsunpack.par2_repair(nzo, "set")

        assert repair.call_args.args[0] == str(tmp_path / "set.par2")


@pytest.mark.usefixtures("clean_cache_dir")
class TestPar2RepairResume:
    """The 'not enough recovery blocks, go and fetch more' path.

    The repairer is kept alive on the NzbObject between the two attempts, so the second
    one only loads the new par2 files and repairs - it must not verify again.
    """

    TEST_DIR = "tests/data/par2repair/basic"

    def _stage(self, with_volumes: bool):
        temp_test_dir = os.path.join(SAB_CACHE_DIR, "par2repair_resume")
        os.makedirs(os.path.join(temp_test_dir, JOB_ADMIN), exist_ok=True)
        for file in glob.glob(self.TEST_DIR + "/*"):
            name = os.path.basename(file)
            # Withhold everything carrying recovery blocks for the first attempt
            if not with_volumes and name.endswith(".par2") and name != "par2test.par2":
                continue
            shutil.copy(file, temp_test_dir)
        return temp_test_dir

    def _make_nzo(self, temp_test_dir):
        nzo = mock.Mock()
        nzo.download_path = temp_test_dir
        nzo.admin_path = os.path.join(temp_test_dir, JOB_ADMIN)
        nzo.fail_msg = ""
        nzo.extrapars = {"par2test": []}
        nzo.par2packs = {"par2test": None}
        nzo.par2_sessions = {}
        nzo.files = []
        nzo.get_extra_blocks.return_value = 5
        return nzo

    def test_resume_reuses_the_verification(self, caplog):
        temp_test_dir = self._stage(with_volumes=False)
        nzo = self._make_nzo(temp_test_dir)
        parfile = os.path.join(temp_test_dir, "par2test.par2")

        try:
            with caplog.at_level(logging.DEBUG):
                finished, readd, _, _ = newsunpack.par2_verify_and_repair(parfile, nzo, "par2test", [])

            # Nothing to repair with yet, so more blocks are requested
            assert not finished
            assert readd
            nzo.get_extra_blocks.assert_called()

            # The session survives, carrying the verification with it
            session = nzo.par2_sessions["par2test"]
            assert session.verified
            assert session.repairer.recovery_block_count == 0

            # The remaining par2 files arrive on disk, not in extrapars
            self._stage(with_volumes=True)
            assert not nzo.extrapars["par2test"]

            stages = []
            session.repairer.progress_callback = lambda stage, filename, percent: stages.append(stage)

            with caplog.at_level(logging.DEBUG):
                finished, readd, _, _ = newsunpack.par2_verify_and_repair(parfile, nzo, "par2test", [])

            assert finished
            assert not readd
            # The expensive part must not have been repeated
            assert "verifying" not in stages
            assert "repairing" in stages
            # And the session is released once the set is done
            assert not nzo.par2_sessions
        finally:
            shutil.rmtree(temp_test_dir, ignore_errors=True)

    def test_par2_files_still_downloading_are_read_once_complete(self, caplog):
        temp_test_dir = self._stage(with_volumes=False)
        nzo = self._make_nzo(temp_test_dir)
        parfile = os.path.join(temp_test_dir, "par2test.par2")

        # Preallocated volumes holding only their first article so far
        pending = []
        for file in glob.glob(self.TEST_DIR + "/par2test.vol*.par2"):
            with open(file, "rb") as f:
                data = f.read()
            with open(os.path.join(temp_test_dir, os.path.basename(file)), "wb") as f:
                f.write(data[: len(data) // 2] + bytes(len(data) - len(data) // 2))
            nzf = mock.Mock(filename=os.path.basename(file), completed=False)
            pending.append(nzf)
        nzo.extrapars["par2test"] = pending

        try:
            finished, readd, _, _ = newsunpack.par2_verify_and_repair(parfile, nzo, "par2test", [])
            assert not finished
            assert readd
            assert nzo.par2_sessions["par2test"].repairer.recovery_block_count == 0

            self._stage(with_volumes=True)
            for nzf in pending:
                nzf.completed = True

            finished, readd, _, _ = newsunpack.par2_verify_and_repair(parfile, nzo, "par2test", [])
            assert finished
            assert not readd
        finally:
            shutil.rmtree(temp_test_dir, ignore_errors=True)

    def test_resume_from_a_different_parfile_of_the_same_set(self, caplog):
        """par2_repair picks its parfile from extrapars, which shrinks as par2 files
        finish downloading, so a resumed attempt often starts from a different member
        of the set. That must reuse the session rather than verifying all over again.

        Asserted by counting sessions: a discarded session is replaced by a new one,
        which would quietly redo the verification.
        """
        temp_test_dir = self._stage(with_volumes=False)
        nzo = self._make_nzo(temp_test_dir)

        try:
            with mock.patch.object(par2repair, "create_session", wraps=par2repair.create_session) as create_session:
                with caplog.at_level(logging.DEBUG):
                    finished, readd, _, _ = newsunpack.par2_verify_and_repair(
                        os.path.join(temp_test_dir, "par2test.par2"), nzo, "par2test", []
                    )
                assert not finished and readd
                assert create_session.call_count == 1
                assert nzo.par2_sessions["par2test"].verified

                self._stage(with_volumes=True)

                # Resume naming a volume file rather than the one we started from
                with caplog.at_level(logging.DEBUG):
                    finished, readd, _, _ = newsunpack.par2_verify_and_repair(
                        os.path.join(temp_test_dir, "par2test.vol1+2.par2"), nzo, "par2test", []
                    )

                assert finished
                # Still one session: the first was reused, not thrown away
                assert create_session.call_count == 1
        finally:
            shutil.rmtree(temp_test_dir, ignore_errors=True)

    def _stage_unsolvable(self):
        """Blocks 0 and 2 lost, which recovery blocks 0 and 21845 cannot rebuild together but 21846 can"""
        temp_test_dir = os.path.join(SAB_CACHE_DIR, "par2repair_unsolvable")
        os.makedirs(os.path.join(temp_test_dir, JOB_ADMIN), exist_ok=True)
        for file in glob.glob("tests/data/par2repair/unsolvable/*"):
            if not file.endswith("vol21846+1.par2"):
                shutil.copy(file, temp_test_dir)

        datafile = os.path.join(temp_test_dir, "unsolvable.bin")
        with open(datafile, "rb") as f:
            original = f.read()
        with open(datafile, "wb") as f:
            f.write(bytes(64) + original[64:128] + bytes(64))

        nzo = self._make_nzo(temp_test_dir)
        nzo.extrapars = {"unsolvable": []}
        nzo.par2packs = {"unsolvable": None}
        return temp_test_dir, nzo, datafile, original

    def test_recovery_blocks_that_cannot_rebuild_the_missing_ones_fetch_a_spare(self):
        temp_test_dir, nzo, datafile, original = self._stage_unsolvable()
        parfile = os.path.join(temp_test_dir, "unsolvable.par2")

        try:
            finished, readd, _, _ = newsunpack.par2_verify_and_repair(parfile, nzo, "unsolvable", [])
            assert not finished
            assert readd
            nzo.get_extra_blocks.assert_called_with("unsolvable", 1)
            assert not nzo.par2_sessions["unsolvable"].verified

            shutil.copy("tests/data/par2repair/unsolvable/unsolvable.vol21846+1.par2", temp_test_dir)

            finished, readd, _, _ = newsunpack.par2_verify_and_repair(parfile, nzo, "unsolvable", [])
            assert finished
            assert not readd
            with open(datafile, "rb") as f:
                assert f.read() == original
        finally:
            shutil.rmtree(temp_test_dir, ignore_errors=True)

    def test_recovery_blocks_that_cannot_rebuild_the_missing_ones_fail_without_a_spare(self):
        temp_test_dir, nzo, _, _ = self._stage_unsolvable()
        nzo.get_extra_blocks.return_value = 0

        try:
            finished, readd, _, _ = newsunpack.par2_verify_and_repair(
                os.path.join(temp_test_dir, "unsolvable.par2"), nzo, "unsolvable", []
            )
            assert not finished
            assert not readd
            assert nzo.status == Status.FAILED
            assert not nzo.par2_sessions
        finally:
            shutil.rmtree(temp_test_dir, ignore_errors=True)


@pytest.mark.usefixtures("clean_cache_dir")
class TestRarUnpack:
    @staticmethod
    def _create_test_nzo(temp_dir, filename: str = "test.nzb", password: Optional[str] = None):
        """Create a mock NZO object for testing"""
        return make_mock_nzo(
            download_path=temp_dir,
            final_name=filename,
            delete=True,  # Enable deletion of extracted files
            password=password,
            correct_password=password,
        )

    @staticmethod
    def _run_rar_unpack(
        test_dir,
        rar_files,
        one_folder=False,
        custom_temp_test_dir=None,
        custom_temp_complete_dir=None,
        custom_nzo_settings=None,
        password=None,
    ):
        """Run rar_unpack with test data"""
        # Base
        temp_test_dir_base = temp_test_dir = long_path(os.path.join(SAB_CACHE_DIR, "rar_unpack_temp"))
        temp_complete_dir_base = temp_complete_dir = long_path(os.path.join(SAB_CACHE_DIR, "rar_complete_temp"))

        # Extend if needed
        if custom_temp_test_dir:
            temp_test_dir = os.path.join(temp_test_dir, custom_temp_test_dir)
        if custom_temp_complete_dir:
            temp_complete_dir = os.path.join(temp_complete_dir, custom_temp_complete_dir)

        assert create_all_dirs(temp_test_dir), f"Failed to create {temp_test_dir}"
        assert create_all_dirs(temp_complete_dir), f"Failed to create {temp_complete_dir}"

        # Copy test files to temp directory
        copied_rars = []
        for rar_file in rar_files:
            src_path = os.path.join(test_dir, rar_file)
            if os.path.exists(src_path):
                dst_path = os.path.join(temp_test_dir, rar_file)
                shutil.copy(src_path, dst_path)
                copied_rars.append(dst_path)

        # Make sure all programs are found
        newsunpack.find_programs(".")

        # Mock PostProcessor that's needed for RAR extraction
        sabnzbd.PostProcessor = mock.Mock()

        # Create mock NZO
        nzo = TestRarUnpack._create_test_nzo(temp_test_dir, password=password)

        # Apply custom NZO settings if provided
        if custom_nzo_settings:
            for key, value in custom_nzo_settings.items():
                setattr(nzo, key, value)

        try:
            # Run the rar_unpack function
            error_code, extracted_files = newsunpack.rar_unpack(nzo, temp_complete_dir, one_folder, copied_rars)

            # Get directory contents with full paths
            complete_contents = listdir_full(temp_complete_dir) if os.path.exists(temp_complete_dir) else []
            download_contents = os.listdir(temp_test_dir) if os.path.exists(temp_test_dir) else []

            return error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir

        finally:
            # Cleanup
            shutil.rmtree(temp_test_dir_base)
            shutil.rmtree(temp_complete_dir_base)

    def _assert_successful_extraction(
        self,
        error_code,
        extracted_files,
        complete_contents,
        download_contents,
        temp_complete_dir,
        expected_files,
        should_delete_original=True,
        original_files=None,
    ):
        """Helper method to assert common successful extraction conditions"""
        # Check that extraction was successful
        assert error_code == 0, "RAR extraction should succeed"
        assert len(extracted_files) > 0, "Should have extracted files"
        assert len(complete_contents) > 0, "Should have files in complete directory"

        # Check file deletion behavior
        if should_delete_original and original_files:
            for original_file in original_files:
                rar_still_exists = any(original_file in f for f in download_contents)
                assert not rar_still_exists, f"Original RAR file {original_file} should be deleted after extraction"
        elif not should_delete_original and original_files:
            for original_file in original_files:
                rar_still_exists = any(original_file in f for f in download_contents)
                assert rar_still_exists, f"Original RAR file {original_file} should still exist when delete=False"

        # Verify full paths, but since extracted_files also includes the in-between folders we use issubset
        complete_contents_set = set(complete_contents)
        extracted_files_set = set(extracted_files)
        assert complete_contents_set.issubset(
            extracted_files_set
        ), f"{complete_contents_set} should be in {extracted_files_set}"

        # Verify the expected files are present using full paths
        expected_full_paths = {os.path.join(temp_complete_dir, filename) for filename in expected_files}
        assert expected_full_paths.issubset(
            extracted_files_set
        ), f"{expected_full_paths} should be in {extracted_files_set}"

    @pytest.mark.parametrize(
        "test_dir, rar_files, expected_files, password",
        [
            (
                "tests/data/basic_rar3",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                None,
            ),
            # RAR3 does not support header encryption
            (
                "tests/data/basic_rar3_64",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
            ),
            (
                "tests/data/basic_rar4_16_header",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42e",
            ),
            # Long password triggers Rar3Sha1 slow path
            (
                "tests/data/basic_rar4_64_header",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
            ),
            # Password truncated to 127
            (
                "tests/data/basic_rar4_128_header",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "sgq6gxzcjupw6kmn3zk49dudy9iuwkuo4232zm3ygafo3me7wuj47grf3oap3sk6gfr7d7u6zobvjoxwo98xuuuqa78vqqmhxyxq7ego7modk49bhuw6cahfdqr7hyf",
            ),
            (
                "tests/data/basic_rar5",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                None,
            ),
            (
                "tests/data/basic_rar5_64_header_blake2",
                ["testfile.rar"],
                {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"},
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
            ),
        ],
    )
    def test_basic_rar_unpack(self, test_dir, rar_files, expected_files, password):
        for rar_file in rar_files:
            with SABRarFile(os.path.join(test_dir, rar_file), part_only=True) as zf:
                zf.setpassword(password)
                assert zf.namelist()

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, password=password)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_no_delete(self):
        """Test RAR unpacking without deleting the original files"""
        test_dir = "tests/data/basic_rar5"
        rar_files = ["testfile.rar"]
        expected_files = {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"}
        custom_nzo_settings = {"delete": False}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, custom_nzo_settings=custom_nzo_settings)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=False,
            original_files=rar_files,
        )

    def test_rar_unpack_long_path(self):
        """Test RAR unpacking with very long paths (>260 characters) for both download and complete directories"""

        # Create very long paths that exceed 260 characters on all platforms
        # This tests handling of long paths universally, not just on Windows

        # Build long nested directory structure to guarantee >260 character paths
        long_dir_name = "very_long_directory_name_" + "x" * 100  # 82 characters
        nested_path_parts = [long_dir_name] * 4  # 4 levels of 82-char names = 328

        temp_test_dir = os.path.join(*nested_path_parts)
        temp_complete_dir = os.path.join(*nested_path_parts)

        assert len(temp_test_dir) > 260, "Should have test directory > 260 characters"
        assert len(temp_complete_dir) > 0, "Should have complete directory > 260 characters"

        test_dir = "tests/data/basic_rar5"
        rar_files = ["testfile.rar"]
        expected_files = {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, actual_temp_complete_dir = (
            self._run_rar_unpack(
                test_dir, rar_files, custom_temp_test_dir=temp_test_dir, custom_temp_complete_dir=temp_complete_dir
            )
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            actual_temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_rar_long_path_inside(self):
        """Test  RAR unpacking functionality for file with long paths inside"""

        # Test with the basic rar5 test file
        test_dir = "tests/data/rar_long_path_inside"
        rar_files = ["long_path_in_rar.rar"]
        expected_files = {"Testfile_1234.bin", "testfile.bin", "My_Test_Download.bin"}

        # The long nested directory structure inside the rar is build the same as test_rar_unpack_long_path
        long_dir_name = "very_long_directory_name_" + "x" * 100  # 82 characters
        nested_path_parts = [long_dir_name] * 4  # 4 levels of 82-char names = 328
        expected_files = {os.path.join(*nested_path_parts, expected_file) for expected_file in expected_files}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_multipart_unicode(self):
        """Test multi-part RAR unpacking with unicode filenames"""

        # Test with unicode multi-part RAR files
        test_dir = "tests/data/unicode_rar"
        rar_files = [
            "我喜欢编程.part1.rar",
            "我喜欢编程.part2.rar",
            "我喜欢编程.part3.rar",
            "我喜欢编程.part4.rar",
            "我喜欢编程.part5.rar",
            "我喜欢编程.part6.rar",
        ]
        expected_files = {"我喜欢编程_My_Test_Download.bin"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_passworded(self):
        """Test RAR unpacking with password-protected file"""

        # Test with password-protected RAR file
        test_dir = "tests/data/test_passworded{{secret}}"
        rar_files = ["passworded-file.rar"]
        expected_files = {"testfile.bin", "My_Test_Download.bin"}

        # Set NZO with the correct password
        custom_nzo_settings = {
            "password": "secret",  # The password is "secret"
            "nzo_info": {"password": "secret"},  # Also set in nzo_info
            "meta": {"password": ["secret"]},  # And in meta for get_all_passwords
        }

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, custom_nzo_settings=custom_nzo_settings)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )

    def test_rar_unpack_wrong_password(self):
        """Test RAR unpacking with wrong password fails appropriately"""

        # Test with password-protected RAR file but wrong password
        test_dir = "tests/data/test_passworded{{secret}}"
        rar_files = ["passworded-file.rar"]

        # Set NZO with the wrong password
        custom_nzo_settings = {
            "password": "wrongpassword",  # Wrong password
            "nzo_info": {"password": "wrongpassword"},
            "meta": {"password": ["wrongpassword"]},
        }

        error_code, extracted_files, complete_contents, download_contents, _nzo, _temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files, custom_nzo_settings=custom_nzo_settings)
        )

        # Check that extraction failed with wrong password (error_code 2 = wrong password)
        assert error_code == 2, "Password-protected RAR extraction should fail with wrong password (error_code 2)"
        assert len(extracted_files) == 0, "Should have no extracted files with wrong password"
        assert len(complete_contents) == 0, "Should have no files in complete directory with wrong password"

        # Verify that the original RAR file still exists (extraction failed)
        rar_still_exists = any("passworded-file.rar" in f for f in download_contents)
        assert rar_still_exists, "Original RAR file should still exist when extraction fails"

    def test_rar_unpack_invalid_windows_filenames(self):
        """Test RAR unpacking with Windows-invalid filenames (allowed to fail on Windows)

        This test contains a RAR file with filenames that are invalid on Windows
        (e.g., files named CON, AUX, PRN, etc. or containing invalid characters).
        On Windows, this extraction may fail, which is acceptable behavior.
        """
        # Test with RAR containing Windows-invalid filenames
        test_dir = "tests/data/rar_invalid_windows"
        rar_files = ["rar_invalid_on_windows.rar"]

        # Check for expected corrected filenames, Unrar corrects it on Windows
        if sabnzbd.WINDOWS:
            expected_files = {"blabla __ bla _ bla __ __ bla ___ CON.bin"}
        else:
            expected_files = {'blabla :: bla " bla << || bla ??? CON.bin'}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_rar_unpack(test_dir, rar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=rar_files,
        )


@pytest.mark.skipif(sys.version_info < (3, 12), reason="tarfile extraction filter requires Python 3.12 or later")
@pytest.mark.usefixtures("clean_cache_dir")
class TestTarUnpack:
    @staticmethod
    def _run_tar_unpack(
        test_dir,
        tar_files,
        one_folder=False,
        custom_temp_test_dir=None,
        custom_temp_complete_dir=None,
        custom_nzo_settings=None,
    ):
        """Run tar_unpack with test data"""
        # Base
        temp_test_dir_base = temp_test_dir = long_path(os.path.join(SAB_CACHE_DIR, "tar_unpack_temp"))
        temp_complete_dir_base = temp_complete_dir = long_path(os.path.join(SAB_CACHE_DIR, "tar_complete_temp"))

        # Extend if needed
        if custom_temp_test_dir:
            temp_test_dir = os.path.join(temp_test_dir, custom_temp_test_dir)
        if custom_temp_complete_dir:
            temp_complete_dir = os.path.join(temp_complete_dir, custom_temp_complete_dir)

        assert create_all_dirs(temp_test_dir), f"Failed to create {temp_test_dir}"
        assert create_all_dirs(temp_complete_dir), f"Failed to create {temp_complete_dir}"

        # Copy test files to temp directory
        copied_tars = []
        for tar_file in tar_files:
            src_path = os.path.join(test_dir, tar_file)
            if os.path.exists(src_path):
                dst_path = os.path.join(temp_test_dir, tar_file)
                shutil.copy(src_path, dst_path)
                copied_tars.append(dst_path)

        # Make sure all programs are found
        newsunpack.find_programs(".")

        # Mock PostProcessor that's needed for TAR extraction
        sabnzbd.PostProcessor = mock.Mock()

        # Create mock NZO
        nzo = TestRarUnpack._create_test_nzo(temp_test_dir)

        # Apply custom NZO settings if provided
        if custom_nzo_settings:
            for key, value in custom_nzo_settings.items():
                setattr(nzo, key, value)

        try:
            # Run the tar_unpack function
            error_code, extracted_files = newsunpack.tar_unpack(nzo, temp_complete_dir, one_folder, copied_tars)

            # Get directory contents with full paths
            complete_contents = listdir_full(temp_complete_dir) if os.path.exists(temp_complete_dir) else []
            download_contents = os.listdir(temp_test_dir) if os.path.exists(temp_test_dir) else []

            # Check nothing extracted is executable
            if not sabnzbd.WINDOWS:
                for file_path in complete_contents:
                    assert not os.access(file_path, os.X_OK), "%s is executable" % file_path
                    st = os.stat(file_path)
                    assert st.st_mode & 0o777 == 0o666 & ~sabnzbd.ORG_UMASK
                    assert st.st_uid == os.getuid(), "%s has wrong owner" % file_path
                    assert st.st_gid == os.getgid(), "%s has wrong group" % file_path

            return error_code, extracted_files, complete_contents, download_contents, nzo, temp_complete_dir

        finally:
            # Cleanup
            shutil.rmtree(temp_test_dir_base)
            shutil.rmtree(temp_complete_dir_base)

    def _assert_successful_extraction(
        self,
        error_code,
        extracted_files,
        complete_contents,
        download_contents,
        temp_complete_dir,
        expected_files,
        should_delete_original=True,
        original_files=None,
    ):
        """Helper method to assert common successful extraction conditions"""
        # Check that extraction was successful
        assert error_code == 0, "TAR extraction should succeed"
        assert len(extracted_files) > 0, "Should have extracted files"
        assert len(complete_contents) > 0, "Should have files in complete directory"

        # Check file deletion behavior
        if should_delete_original and original_files:
            for original_file in original_files:
                tar_still_exists = any(original_file in f for f in download_contents)
                assert not tar_still_exists, f"Original TAR file {original_file} should be deleted after extraction"
        elif not should_delete_original and original_files:
            for original_file in original_files:
                tar_still_exists = any(original_file in f for f in download_contents)
                assert tar_still_exists, f"Original TAR file {original_file} should still exist when delete=False"

        # Verify full paths, but since extracted_files also includes the in-between folders we use issubset
        complete_contents_set = set(complete_contents)
        extracted_files_set = set(extracted_files)
        assert complete_contents_set.issubset(
            extracted_files_set
        ), f"{complete_contents_set} should be in {extracted_files_set}"

        # Verify the expected files are present using full paths
        expected_full_paths = {os.path.join(temp_complete_dir, filename) for filename in expected_files}
        assert expected_full_paths.issubset(
            extracted_files_set
        ), f"{expected_full_paths} should be in {extracted_files_set}"

    def test_basic_tar_unpack(self):
        """Test basic TAR unpacking functionality"""
        test_dir = "tests/data/test_tar"
        tar_files = ["testfile.tar"]
        expected_files = {"My_Test_Download.bin"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_tar_unpack(test_dir, tar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=tar_files,
        )

    def test_path_traversal_tar_unpack(self, tmp_path):
        tar_path = tmp_path / "bad.tar"

        # Create a tar containing a path traversal entry
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("../evil.txt")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"evil"))

        tar_files = ["bad.tar"]

        error_code, extracted_files, _complete_contents, _download_contents, _nzo, _temp_complete_dir = (
            self._run_tar_unpack(str(tmp_path), tar_files)
        )

        assert error_code == 1, "TAR extraction should fail"
        assert not extracted_files

    def test_link_members_skipped_tar_unpack(self, tmp_path):
        """A download never needs links, and even one that stays inside the folder is enough
        to redirect a later rename out of it, so they are dropped instead of extracted"""
        tar_path = tmp_path / "links.tar"

        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("file.txt")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"test"))
            # tarfile.data_filter() allows this one: the target stays inside the folder
            pivot = tarfile.TarInfo("pivot")
            pivot.type = tarfile.SYMTYPE
            pivot.linkname = "."
            tar.addfile(pivot)
            hardlink = tarfile.TarInfo("hardlink.txt")
            hardlink.type = tarfile.LNKTYPE
            hardlink.linkname = "file.txt"
            tar.addfile(hardlink)

        tar_files = ["links.tar"]
        expected_files = {"file.txt"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_tar_unpack(str(tmp_path), tar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=tar_files,
        )

        dropped = {"pivot", "hardlink.txt"}
        assert not [f for f in extracted_files if os.path.basename(f) in dropped]
        assert not [f for f in complete_contents if os.path.basename(f) in dropped]

    def test_pre_existing_link_in_destination(self, tmp_path):
        """A link left in the folder by another unpacker cannot be used to write a member
        through it, because tarfile.data_filter() resolves the destination"""
        base = str(tmp_path)
        extraction_path = os.path.join(base, "dest")
        outside = os.path.join(base, "outside")
        os.mkdir(extraction_path)
        os.mkdir(outside)
        os.symlink(outside, os.path.join(extraction_path, "sub"))

        tar_path = os.path.join(base, "prelink.tar")
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("sub/evil.txt")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"evil"))

        nzo = TestRarUnpack._create_test_nzo(extraction_path)
        error_code, extracted_files = newsunpack.tar_extract(nzo, tar_path, extraction_path, False)

        assert error_code == 1, "TAR extraction should fail"
        assert not extracted_files
        assert not os.listdir(outside)

    def test_dangling_link_not_used_as_unique_name(self, tmp_path):
        """get_unique_filename() picks the name after data_filter() approved the original, so
        a dangling link is neither a free name nor a way out of the folder"""
        base = str(tmp_path)
        extraction_path = os.path.join(base, "dest")
        os.mkdir(extraction_path)
        outside = os.path.join(base, "outside.txt")

        # Occupy the plain name, so a unique one has to be picked
        with open(os.path.join(extraction_path, "victim.txt"), "wb") as victim:
            victim.write(b"keep")
        # The name that gets picked next is a link that points out of the folder
        os.symlink(os.path.join("..", "outside.txt"), os.path.join(extraction_path, "victim.1.txt"))

        tar_path = os.path.join(base, "unique.tar")
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("victim.txt")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"evil"))

        nzo = TestRarUnpack._create_test_nzo(extraction_path)
        newsunpack.tar_extract(nzo, tar_path, extraction_path, False)

        assert not os.path.exists(outside), "written through the link to %s" % outside
        with open(os.path.join(extraction_path, "victim.txt"), "rb") as victim:
            assert victim.read() == b"keep", "the existing file was overwritten"

    def test_owner_permissions_sanitized_tar_unpack(self, tmp_path):
        tar_path = tmp_path / "owner.tar"

        # Create a tar containing a file owned by root with read, write, and execute permissions for everyone
        with tarfile.open(tar_path, "w") as tar:
            info = tarfile.TarInfo("file.txt")
            info.size = 4
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mode = 0o777
            tar.addfile(info, io.BytesIO(b"test"))

        tar_files = ["owner.tar"]
        expected_files = {"file.txt"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_tar_unpack(str(tmp_path), tar_files)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=tar_files,
        )

    def test_one_folder_tar_unpack(self, tmp_path):
        tar_path = tmp_path / "flatten.tar"

        # Create a tar containing a file owned by root with read, write, and execute permissions for everyone
        with tarfile.open(tar_path, "w") as tar:
            for i in range(2):
                info = tarfile.TarInfo(os.path.join(str(i), "file.txt"))
                info.size = 4
                tar.addfile(info, io.BytesIO(b"test"))

        tar_files = ["flatten.tar"]
        expected_files = {"file.txt", "file.1.txt"}

        error_code, extracted_files, complete_contents, download_contents, _nzo, temp_complete_dir = (
            self._run_tar_unpack(str(tmp_path), tar_files, True)
        )

        self._assert_successful_extraction(
            error_code,
            extracted_files,
            complete_contents,
            download_contents,
            temp_complete_dir,
            expected_files,
            should_delete_original=True,
            original_files=tar_files,
        )


@pytest.mark.usefixtures("clean_cache_dir")
@pytest.mark.config(
    {
        "enable_unrar": True,
        "enable_filejoin": False,
        "enable_tsjoin": False,
        "enable_tar": False,
        "enable_7zip": False,
        "enable_recursive": False,
    }
)
class TestUnpackNestedRarSets:
    """A rar set can live in a subfolder of the download path: quick-check moves the volumes
    into a folder of their own when the par2 set stores them that way.

    Everything hangs off build_filelists() being told about that folder. It is what makes
    unpacker() call rar_unpack(), which both unpacks the set and is the only place SABnzbd
    waits for a running DirectUnpacker. Miss the volumes and post-processing unpacks nothing
    and moves the raw rars to the complete folder, while unrar is still reading them.
    """

    SUBDIR = "Foo.Bar.S05E03.1080p"

    @staticmethod
    def _create_job(tmp_path, subdir: str = "") -> tuple[mock.Mock, str]:
        """Job with one rar set in <download_path>/<subdir>, returns the nzo and complete path"""
        download_path = os.path.join(str(tmp_path), "incomplete")
        complete_path = os.path.join(str(tmp_path), "complete")
        assert create_all_dirs(os.path.join(download_path, subdir))
        assert create_all_dirs(complete_path)
        shutil.copy(os.path.join("tests", "data", "basic_rar3", "testfile.rar"), os.path.join(download_path, subdir))

        newsunpack.find_programs(".")
        sabnzbd.PostProcessor = mock.Mock()

        nzo = make_mock_nzo(
            download_path=download_path,
            final_name="Foo.Bar.S05.1080p",
            delete=True,
            # As NzbObject.sub_directories() would report it for a job assembled into it
            sub_directories=mock.Mock(return_value={os.path.join(download_path, subdir)} if subdir else set()),
        )
        return nzo, complete_path

    @staticmethod
    def _create_direct_unpacker() -> mock.Mock:
        """Stub that reports itself as running until it is joined or aborted"""
        finished = threading.Event()
        return mock.Mock(
            success_sets={},
            next_file_lock=threading.Condition(),
            get_formatted_stats=mock.Mock(return_value="01/10"),
            is_alive=mock.Mock(side_effect=lambda: not finished.is_set()),
            join=mock.Mock(side_effect=lambda timeout=None: finished.set()),
            abort=mock.Mock(side_effect=finished.set),
        )

    def test_build_filelists_only_scans_known_subfolders(self, tmp_path):
        """The download path stays non-recursive, only folders we were told about are added"""
        rar_dir = os.path.join(str(tmp_path), self.SUBDIR)
        assert create_all_dirs(rar_dir)
        rar_path = os.path.join(rar_dir, "testfile.rar")
        shutil.copy(os.path.join("tests", "data", "basic_rar3", "testfile.rar"), rar_path)

        _joinables, rars, _sevens, _ts, _tars = build_filelists(str(tmp_path))
        assert rars == []

        _joinables, rars, _sevens, _ts, _tars = build_filelists(str(tmp_path), extra_dirs=[rar_dir])
        assert rars == [rar_path]

    def test_sub_directories_reports_only_local_subfolders(self, tmp_path):
        """Where the job assembled its files (nzf.filename) plus anything par2cmdline
        restored into a folder during repair (nzo.renames)"""
        download_path = str(tmp_path)
        nzo = make_mock_nzo(
            download_path=download_path,
            finished_files=[
                mock.Mock(filename=os.path.join(self.SUBDIR, "testfile.rar")),
                mock.Mock(filename="testfile.r00"),
            ],
            renames={
                os.path.join("Sample", "sample.mkv"): "obfuscated",
                os.path.join(os.pardir, "escaped.rar"): "obfuscated.2",
            },
        )

        assert sabnzbd.nzb.NzbObject.sub_directories(nzo) == {
            os.path.join(download_path, self.SUBDIR),
            os.path.join(download_path, "Sample"),
        }

    def test_unpacker_unpacks_rars_in_subfolder(self, tmp_path):
        """Without a DirectUnpacker in play the set still has to be unpacked, not moved as-is"""
        nzo, complete_path = self._create_job(tmp_path, self.SUBDIR)

        error, newfiles = newsunpack.unpacker(nzo, complete_path, False)

        assert not error
        assert newfiles, "the rar set in the subfolder was never found, so nothing was unpacked"
        assert os.path.exists(os.path.join(complete_path, "testfile.bin"))

    def test_quick_check_rename_updates_setname_and_vol(self, tmp_path):
        """The rename is what puts the volumes in the subfolder, so the set and volume number
        derived from the obfuscated name go stale. A DirectUnpacker looks up the next volume by
        those, and would hand unrar a path built from the new name."""
        download_path = str(tmp_path)
        obfuscated_name = "6f1ed002ab5595859014ebf0951522d9"
        par2_name = "%s/foo.bar.s05e03.r00" % self.SUBDIR
        obfuscated_path = os.path.join(download_path, obfuscated_name)
        with open(obfuscated_path, "wb") as test_file:
            test_file.write(b"volume contents")

        nzf = mock.Mock(
            filename=obfuscated_name,
            filepath=obfuscated_path,
            crc32=1234,
            setname=obfuscated_name,
            vol=1,
        )
        nzo = make_mock_nzo(
            download_path=download_path,
            finished_files=[nzf],
            par2packs={
                "testset": {
                    par2_name: FilePar2Info(
                        filename=par2_name,
                        hash16k=b"",
                        filesize=os.path.getsize(obfuscated_path),
                        filehash=nzf.crc32,
                    )
                }
            },
        )

        assert newsunpack.quick_check_set("testset", nzo)

        assert nzf.filename == os.path.normpath(par2_name)
        # The setname is the name of the set, never the folder it happens to live in, so it
        # matches what rar_unpack() derives from the path on disk
        assert (nzf.setname, nzf.vol) == ("foo.bar.s05e03", 2)

    def test_quick_check_rename_rekeys_completed_direct_unpack_set(self, tmp_path):
        """DirectUnpack keys the sets it finished by the name they had while downloading.
        rar_unpack() looks them up by the name on disk, so after the rename moved the volumes
        into their own folder it no longer recognizes the set and extracts it a second time."""
        download_path = str(tmp_path)
        # Flattened par2 name, exactly what the volumes are called before the rename
        flat_name = "%s_foo.bar.s05e03.r00" % self.SUBDIR
        par2_name = "%s/foo.bar.s05e03.r00" % self.SUBDIR
        flat_path = os.path.join(download_path, flat_name)
        with open(flat_path, "wb") as test_file:
            test_file.write(b"volume contents")

        nzf = mock.Mock(filename=flat_name, filepath=flat_path, crc32=1234, vol=2)
        nzf.setname = "%s_foo.bar.s05e03" % self.SUBDIR
        direct_unpacker = mock.Mock(success_sets={nzf.setname: (["volumes"], ["extracted.mkv"])})
        nzo = make_mock_nzo(
            download_path=download_path,
            finished_files=[nzf],
            direct_unpacker=direct_unpacker,
            par2packs={
                "testset": {
                    par2_name: FilePar2Info(
                        filename=par2_name,
                        hash16k=b"",
                        filesize=os.path.getsize(flat_path),
                        filehash=nzf.crc32,
                    )
                }
            },
        )

        assert newsunpack.quick_check_set("testset", nzo)

        assert list(direct_unpacker.success_sets) == ["foo.bar.s05e03"], (
            "the completed set is still keyed by its old name, so post-processing will "
            "extract it again on top of what DirectUnpack already produced"
        )
        assert direct_unpacker.success_sets["foo.bar.s05e03"] == (["volumes"], ["extracted.mkv"])

    def test_sfv_check_rename_updates_setname_and_vol(self, tmp_path):
        """sfv_check() de-obfuscates the same way quick_check_set() does"""
        download_path = str(tmp_path)
        obfuscated_name = "6f1ed002ab5595859014ebf0951522d9"
        real_name = "foo.bar.s05e03.r00"
        with open(os.path.join(download_path, obfuscated_name), "wb") as test_file:
            test_file.write(b"volume contents")

        crc32 = 1234
        sfv_path = os.path.join(download_path, "foo.bar.s05e03.sfv")
        with open(sfv_path, "wb") as sfv_file:
            sfv_file.write(b"; generated by test\n%s %08x\n" % (real_name.encode(), crc32))

        nzf = mock.Mock(filename=obfuscated_name, crc32=crc32, setname=obfuscated_name, vol=1)
        nzo = make_mock_nzo(download_path=download_path, finished_files=[nzf])

        assert newsunpack.sfv_check([sfv_path], nzo)

        assert nzf.filename == real_name
        assert (nzf.setname, nzf.vol) == ("foo.bar.s05e03", 2)

    @pytest.mark.parametrize(
        "subdir",
        [
            pytest.param("", id="rars_in_download_path"),
            pytest.param(SUBDIR, id="rars_in_subfolder_of_download_path"),
        ],
    )
    def test_unpacker_waits_for_active_direct_unpacker(self, subdir, tmp_path):
        nzo, complete_path = self._create_job(tmp_path, subdir)
        nzo.direct_unpacker = self._create_direct_unpacker()

        newsunpack.unpacker(nzo, complete_path, False)

        assert nzo.direct_unpacker.join.called or nzo.direct_unpacker.abort.called, (
            "unpacker() returned while the DirectUnpacker was still running; post-processing "
            "will move and purge the job's files from under unrar"
        )
        assert not nzo.direct_unpacker.is_alive(), "DirectUnpacker should no longer be running"


@pytest.mark.usefixtures("clean_cache_dir")
class TestExternalProcessingEnv:
    """Harness for the SAB_* environment variables passed to post-processing scripts.

    external_processing() builds the environment (via create_env) and runs a user script.
    These tests invoke a *real* receiving script that captures every SAB_* variable it sees
    and echoes them back as JSON, so any SAB_* variable can be asserted on. The round-trip
    proves the script decodes exactly the values SAB sent.

    SAB_FILES gets extra attention because its value is itself a JSON list of the new files:
    emojis, non-latin characters and characters that must be JSON-escaped (quotes,
    backslashes, tabs, newlines, control chars) all have to survive the round-trip intact.
    """

    # Receiving script: capture every SAB_* variable and echo it back. SAB_FILES is the only
    # variable SAB JSON-encodes, so it is the only one this script json-decodes; all other
    # values are passed through as plain strings. The script deliberately has no shebang,
    # so build_and_run_command() prepends the current interpreter (sys.executable) and it
    # runs under the same Python as the test suite. The captured mapping is re-emitted as
    # ASCII-safe JSON purely to ferry it back over stdout, independent of the console encoding.
    RECEIVING_SCRIPT = (
        "import os, json\n"
        "env = {k: v for k, v in os.environ.items() if k.startswith('SAB_')}\n"
        "if 'SAB_FILES' in env:\n"
        "    env['SAB_FILES'] = json.loads(env['SAB_FILES'])\n"
        "print(json.dumps(env))\n"
    )

    # Realistic defaults so every SAB_<field> derived from the NZO is a clean string unless
    # a test overrides it. Keys mirror newsunpack.ENV_NZO_FIELDS.
    NZO_DEFAULTS = {
        "bytes": 1024,
        "bytes_downloaded": 1024,
        "bytes_tried": 1024,
        "cat": "movies",
        "correct_password": "",
        "duplicate": False,
        "duplicate_key": "",
        "encrypted": 0,
        "fail_msg": "",
        "filename": "test.nzb",
        "final_name": "Test Job",
        "group": "alt.binaries.test",
        "nzo_id": "SABnzbd_nzo_abc123",
        "oversized": False,
        "password": "",
        "pp": 3,
        "priority": 0,
        "repair": True,
        "script": "recv.py",
        "status": "Completed",
        "unpack": True,
        "unwanted_ext": 0,
        "url": "",
    }

    @staticmethod
    def _write_receiving_script(directory: str) -> str:
        """Write the receiving script and give it the execute bit post-proc scripts need."""
        script_path = os.path.join(directory, "recv_sab_env.py")
        with open(script_path, "w", encoding="utf-8") as script_file:
            script_file.write(TestExternalProcessingEnv.RECEIVING_SCRIPT)
        os.chmod(
            script_path,
            os.stat(script_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )
        return script_path

    @classmethod
    def _make_nzo(cls, admin_dir: str, overrides: dict):
        """A mock NZO with clean string values for every field create_env reads."""
        return make_mock_nzo(
            **{**cls.NZO_DEFAULTS, **overrides},
            admin_path=admin_dir,
            avg_bps_total=0,
            avg_bps_freq=0,
            avg_date=datetime.datetime(2026, 1, 1),
        )

    def _run(self, filenames=None, status=0, nzo_overrides=None):
        """Invoke external_processing with a real script.

        Returns (sab_env, complete_dir, ret) where 'sab_env' is the dict of every SAB_*
        variable exactly as the receiving script saw it.
        """
        base = long_path(os.path.join(SAB_CACHE_DIR, "sab_env"))
        complete_dir = os.path.join(base, "complete")
        admin_dir = os.path.join(base, JOB_ADMIN)
        assert create_all_dirs(complete_dir), f"Failed to create {complete_dir}"
        assert create_all_dirs(admin_dir), f"Failed to create {admin_dir}"

        script_path = self._write_receiving_script(base)

        # Full paths as external_processing receives them
        newfiles = [os.path.join(complete_dir, name) for name in (filenames or [])]

        nzo = self._make_nzo(admin_dir, nzo_overrides or {})
        sabnzbd.PostProcessor = mock.Mock()
        output, ret = newsunpack.external_processing(script_path, nzo, complete_dir, status, newfiles)

        sab_env = json.loads(output)
        return sab_env, clip_path(complete_dir), ret

    def _run_files(self, filenames):
        """SAB_FILES convenience wrapper: returns (decoded_files, expected, ret).

        The receiving script already json-decodes SAB_FILES, so sab_env["SAB_FILES"] is the
        list the script parsed out of the environment variable.
        """
        sab_env, complete_dir, ret = self._run(filenames=filenames)
        decoded = sab_env["SAB_FILES"]
        expected = sorted(os.path.relpath(os.path.join(complete_dir, name), complete_dir) for name in filenames)
        return decoded, expected, ret

    @pytest.mark.parametrize(
        "filenames",
        [
            pytest.param(["movie.mkv", "sample.mkv", "readme.txt"], id="plain-ascii"),
            pytest.param(
                ['quote".mkv', "back\\slash.mkv", "tab\tchar.txt", "new\nline.txt", "control\x01.dat"],
                id="json-escaped",
            ),
            pytest.param(["clip_🎬.mkv", "party_🎉🎉.mkv", "flag_🏴‍☠️.txt"], id="emoji"),
            pytest.param(
                ["naïve.txt", "Пример.mkv", "测试文件.mkv", "日本語のファイル.txt", "ملف.txt", "Ω_Δ.dat"],
                id="non-latin",
            ),
            pytest.param(['Movie (2026) 🎬 — naïve 测试 "final".mkv'], id="mixed"),
        ],
    )
    def test_sab_files_round_trip(self, filenames):
        """The receiving script decodes SAB_FILES to exactly the filenames that went in."""
        decoded, expected, ret = self._run_files(filenames)
        assert ret == 0
        assert decoded == expected

    def test_sab_files_is_sorted(self):
        """Unsorted input arrives at the script as a sorted list."""
        decoded, expected, ret = self._run_files(["zebra.mkv", "apple.mkv", "Éclair.mkv", "mango.mkv"])
        assert ret == 0
        assert decoded == sorted(decoded)
        assert decoded == expected

    def test_sab_files_relative_paths(self):
        """Files in subdirectories are made relative to the complete dir, no absolute leak."""
        decoded, expected, ret = self._run_files([os.path.join("Season 1", "épisode 🎬.mkv"), "root.mkv"])
        assert ret == 0
        assert decoded == expected
        assert all(not os.path.isabs(path) for path in decoded)

    def test_sab_files_empty(self):
        """No new files; SAB_FILES is an empty JSON list."""
        decoded, expected, ret = self._run_files([])
        assert ret == 0
        assert decoded == []
        assert expected == []

    @pytest.mark.parametrize(
        "field, value, env_var",
        [
            pytest.param("cat", "tv 📺", "SAB_CAT", id="cat-emoji"),
            pytest.param("final_name", "Naïve.Show.测试.S01", "SAB_FINAL_NAME", id="final_name-non-latin"),
            pytest.param("nzo_id", "SABnzbd_nzo_xyz789", "SAB_NZO_ID", id="nzo_id"),
            pytest.param("group", 'alt."quoted".group', "SAB_GROUP", id="group-quotes"),
        ],
    )
    def test_sab_nzo_field_round_trip(self, field, value, env_var):
        """Any NZO-derived SAB_* variable arrives at the script unchanged."""
        sab_env, _complete_dir, ret = self._run(nzo_overrides={field: value})
        assert ret == 0
        assert sab_env[env_var] == value

    def test_sab_bool_field_is_normalised(self):
        """Boolean NZO fields are passed as '1'/'0' (create_env's str(value * 1))."""
        sab_env, _complete_dir, ret = self._run(nzo_overrides={"repair": True, "duplicate": False})
        assert ret == 0
        assert sab_env["SAB_REPAIR"] == "1"
        assert sab_env["SAB_DUPLICATE"] == "0"

    def test_sab_always_supplied_fields(self):
        """The always-present SAB_* variables reflect the arguments and SAB globals."""
        sab_env, complete_dir, ret = self._run(status=2)
        assert ret == 0
        assert sab_env["SAB_VERSION"] == sabnzbd.__version__
        assert sab_env["SAB_COMPLETE_DIR"] == complete_dir
        assert sab_env["SAB_PP_STATUS"] == "2"
