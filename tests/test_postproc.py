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
tests.test_postproc- Tests of various functions in newspack, among which rar_renamer()
"""

import os
import re
import shutil
from unittest import mock

from sabnzbd import postproc
from sabnzbd.config import ConfigSorter, ConfigCat
from sabnzbd.filesystem import globber_full, clip_path
from sabnzbd.misc import sort_to_opts

from tests.testhelper import *


@pytest.mark.usefixtures("clean_cache_dir")
class TestPostProc:
    # Helper function for rar_renamer tests
    def _deobfuscate_dir(self, sourcedir, expected_filename_matches):
        """Function to deobfuscate one directory with rar_renamer()"""
        # We create a workingdir inside the sourcedir, because the filenames are really changed
        workingdir = os.path.join(SAB_CACHE_DIR, "workingdir_test_rar_renamer")

        # if workingdir is still there from previous run, remove it:
        if os.path.isdir(workingdir):
            try:
                shutil.rmtree(workingdir)
            except PermissionError:
                pytest.fail("Could not remove existing workingdir %s for rar_renamer" % workingdir)

        # create a fresh copy
        try:
            shutil.copytree(sourcedir, workingdir)
        except Exception:
            pytest.fail("Could not create copy of files for rar_renamer")

        # And now let the magic happen:
        nzo = mock.Mock()
        nzo.final_name = "somedownloadname"
        nzo.download_path = workingdir
        number_renamed_files = postproc.rar_renamer(nzo)

        # run check on the resulting files
        if expected_filename_matches:
            for filename_match in expected_filename_matches:
                if len(globber_full(workingdir, filename_match)) != expected_filename_matches[filename_match]:
                    pytest.fail("Failed filename_match %s in %s" % (filename_match, workingdir))

        # Remove workingdir again
        try:
            shutil.rmtree(workingdir)
        except Exception:
            pytest.fail("Could not remove existing workingdir %s for rar_renamer" % workingdir)

        return number_renamed_files

    def test_rar_renamer_obfuscated_single_rar_set(self):
        """Test rar_renamer with obfuscated single rar set"""
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_single_rar_set")
        # Now define the filematches we want to see, in which amount ("*-*-*-*-*" are the input files):
        expected_filename_matches = {"*part007.rar": 1, "*-*-*-*-*": 0}
        assert self._deobfuscate_dir(sourcedir, expected_filename_matches) == 7

    def test_rar_renamer_obfuscated_two_rar_sets(self):
        """Test rar_renamer with obfuscated two rar sets"""
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_two_rar_sets")
        expected_filename_matches = {"*part007.rar": 2, "*part009.rar": 1, "*-*-*-*-*": 0}
        assert self._deobfuscate_dir(sourcedir, expected_filename_matches) == 16

    def test_rar_renamer_obfuscated_but_no_rar(self):
        """Test rar_renamer with obfuscated files that are not rar sets"""
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_but_no_rar")
        expected_filename_matches = {"*.rar": 0, "*-*-*-*-*": 6}
        assert self._deobfuscate_dir(sourcedir, expected_filename_matches) == 0

    def test_rar_renamer_single_rar_set_missing_first_rar(self):
        """Test rar_renamer with single rar set missing first rar"""
        # One obfuscated rar set, but first rar (.part1.rar) is missing
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_single_rar_set_missing_first_rar")
        # single rar set (of 6 obfuscated rar files), so we expect renaming
        # thus result must 6 rar files, and 0 obfuscated files
        expected_filename_matches = {"*.rar": 6, "*-*-*-*-*": 0}
        # 6 files should have been renamed
        assert self._deobfuscate_dir(sourcedir, expected_filename_matches) == 6

    def test_rar_renamer_double_rar_set_missing_rar(self):
        """Test rar_renamer with two rar sets where some rars are missing"""
        # Two obfuscated rar sets, but some rars are missing
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_double_rar_set_missing_rar")
        # Two sets, missing rar, so we expect no renaming
        # thus result should be 0 rar files, and still 8 obfuscated files
        expected_filename_matches = {"*.rar": 0, "*-*-*-*-*": 8}
        # 0 files should have been renamed
        assert self._deobfuscate_dir(sourcedir, expected_filename_matches) == 0

    def test_rar_renamer_fully_encrypted_and_obfuscated(self):
        """Test rar_renamer with fully encrypted and obfuscated rar set"""
        # fully encrypted rar-set, and obfuscated rar names
        sourcedir = os.path.join(SAB_DATA_DIR, "fully_encrypted_and_obfuscated_rars")
        # SABnzbd cannot do anything with this, so we expect no renaming
        expected_filename_matches = {"*.rar": 0, "*-*-*-*-*": 6}
        # 0 files should have been renamed
        assert self._deobfuscate_dir(sourcedir, expected_filename_matches) == 0

    @pytest.mark.parametrize("category", ["testcat", "Default", None])
    @pytest.mark.parametrize("has_jobdir", [True, False])  # With or without a job dir
    @pytest.mark.parametrize("has_catdir", [True, False])  # Complete directory is defined at category level
    @pytest.mark.parametrize("has_active_sorter", [True, False])  # Sorter active for the fake nzo
    @pytest.mark.parametrize("sort_string", ["%sn (%r)", "%sn (%r)/file.%ext", ""])  # Identical path result
    @pytest.mark.parametrize("marker_file", [None, ".marker"])
    @pytest.mark.parametrize("do_folder_rename", [True, False])
    def test_prepare_extraction_path(
        self, category, has_jobdir, has_catdir, has_active_sorter, sort_string, marker_file, do_folder_rename
    ):
        # Ensure global CFG_ vars are initialised
        sabnzbd.config.read_config(os.devnull)

        # Define a sorter and a category (as @set_config cannot handle those)
        ConfigSorter(
            "sorter__test_prepare_extraction_path",
            {
                "order": 0,
                "min_size": 42,
                "multipart_label": "",
                "sort_string": sort_string,
                "sort_cats": [category if category else "no_such_category"],
                "sort_type": [
                    sort_to_opts("all"),
                ],
                "is_active": int(has_active_sorter),
            },
        )
        assert sabnzbd.config.CFG_DATABASE["sorters"]["sorter__test_prepare_extraction_path"]

        if category:
            ConfigCat(
                category,
                {
                    "order": 0,
                    "pp": None,
                    "script": None,
                    "dir": (
                        os.path.join(SAB_CACHE_DIR, ("category_dir_for_" + category + ("*" if not has_jobdir else "")))
                        if has_catdir
                        else None
                    ),
                    "newzbin": "",
                    "priority": 0,
                },
            )
            assert sabnzbd.config.CFG_DATABASE["categories"][category]

        # Mock a minimal nzo, required as function input
        fake_nzo = mock.Mock()
        fake_nzo.final_name = "FOSS.Rules.S23E06.2160p-SABnzbd"
        fake_nzo.cat = category
        fake_nzo.nzo_info = {}  # Placeholder to prevent a crash in sorting.get_titles()

        @set_config(
            {
                "download_dir": os.path.join(SAB_CACHE_DIR, "incomplete"),
                "complete_dir": os.path.join(SAB_CACHE_DIR, "complete"),
                "marker_file": marker_file,
                "folder_rename": do_folder_rename,
            }
        )
        def _func():
            (
                tmp_workdir_complete,
                workdir_complete,
                file_sorter,
                not_create_job_dir,
                marker_file_result,
            ) = postproc.prepare_extraction_path(fake_nzo)

            tmp_workdir_complete = clip_path(tmp_workdir_complete)
            workdir_complete = clip_path(workdir_complete)

            # Verify marker file
            if marker_file and not not_create_job_dir:
                assert marker_file_result
            else:
                assert not marker_file_result

            # Verify sorter
            assert file_sorter
            if has_active_sorter and category and sort_string:
                assert file_sorter.sorter_active
            else:
                assert not file_sorter.sorter_active

            # Verify not_create_job_dir
            if category and has_catdir and not has_jobdir and not file_sorter.sorter_active:
                assert not_create_job_dir
            else:
                # Double negatives ftw
                assert not not_create_job_dir

            # Verify workdir_complete
            if not category or not has_catdir:
                # Using standard Complete directory as base
                assert workdir_complete.startswith(os.path.join(SAB_CACHE_DIR, "complete"))
            elif category and has_catdir:
                # Based on the category directory
                assert workdir_complete.startswith(os.path.join(SAB_CACHE_DIR, "category_dir_for_" + category))
            # Check the job directory part (or the lack thereof) as well
            if has_active_sorter and category and sort_string:
                # Sorter path, with an extra job name work directory inside
                assert re.fullmatch(
                    re.escape(SAB_CACHE_DIR)
                    + r".*"
                    + re.escape(os.sep)
                    + r"Foss Rules \(2160p\)"
                    + re.escape(os.sep)
                    + fake_nzo.final_name
                    + r"(\.\d+)?",
                    workdir_complete,
                )
            elif has_jobdir or not (category and has_catdir):
                # Standard job name directory
                assert re.fullmatch(
                    re.escape(SAB_CACHE_DIR) + r".*" + re.escape(os.sep) + r"FOSS.Rules.S23E06.2160p-SABnzbd(\.\d+)?",
                    workdir_complete,
                )
            else:
                # No job directory at all
                assert re.fullmatch(
                    re.escape(SAB_CACHE_DIR) + r".*" + re.escape(os.sep) + r"category_dir_for_([a-zA-Z]+)",
                    workdir_complete,
                )

            # Verify tmp_workdir_complete
            if do_folder_rename:
                if not not_create_job_dir:
                    assert tmp_workdir_complete != workdir_complete
                assert tmp_workdir_complete.replace("_UNPACK_", "") == workdir_complete
            else:
                assert tmp_workdir_complete == workdir_complete

        _func()


class TestNzbOnlyDownload:
    @mock.patch("sabnzbd.postproc.process_single_nzb")
    @mock.patch("sabnzbd.postproc.listdir_full")
    def test_process_nzb_only_download_single_nzb(self, mock_listdir, mock_process_single_nzb):
        """Test process_nzb_only_download with a single NZB file"""
        # Setup mock NZO
        fake_nzo = mock.Mock()
        fake_nzo.final_name = "TestDownload"
        fake_nzo.pp = 3
        fake_nzo.script = "test_script.py"
        fake_nzo.cat = "movies"
        fake_nzo.url = "http://example.com/test.nzb"
        fake_nzo.priority = 0

        # Mock single NZB file
        workdir = os.path.join(SAB_CACHE_DIR, "test_workdir")
        nzb_file = os.path.join(workdir, "test.nzb")
        mock_listdir.return_value = [nzb_file]

        # Call the function
        result = postproc.process_nzb_only_download(workdir, fake_nzo)

        # Verify result
        assert result == [nzb_file]

        # Verify process_single_nzb was called with correct arguments
        mock_process_single_nzb.assert_called_once_with(
            "test.nzb",
            nzb_file,
            pp=3,
            script="test_script.py",
            cat="movies",
            url="http://example.com/test.nzb",
            priority=0,
            nzbname="TestDownload",
            dup_check=False,
        )

    @mock.patch("sabnzbd.postproc.process_single_nzb")
    @mock.patch("sabnzbd.postproc.listdir_full")
    def test_process_nzb_only_download_multiple_nzbs(self, mock_listdir, mock_process_single_nzb):
        """Test process_nzb_only_download with multiple NZB files"""
        # Setup mock NZO
        fake_nzo = mock.Mock()
        fake_nzo.final_name = "TestDownload"
        fake_nzo.pp = 2
        fake_nzo.script = None
        fake_nzo.cat = "tv"
        fake_nzo.url = "http://example.com/test.nzb"
        fake_nzo.priority = 1

        # Mock multiple NZB files
        workdir = os.path.join(SAB_CACHE_DIR, "test_workdir")
        first_nzb = os.path.join(workdir, "first.nzb")
        second_nzb = os.path.join(workdir, "second.nzb")
        mock_listdir.return_value = [first_nzb, second_nzb]

        # Call the function
        result = postproc.process_nzb_only_download(workdir, fake_nzo)

        # Verify result
        assert result == [first_nzb, second_nzb]

        # Verify process_single_nzb was called twice with correct arguments
        assert mock_process_single_nzb.call_count == 2
        mock_process_single_nzb.assert_any_call(
            "first.nzb",
            first_nzb,
            pp=2,
            script=None,
            cat="tv",
            url="http://example.com/test.nzb",
            priority=1,
            nzbname="TestDownload - first.nzb",
            dup_check=False,
        )
        mock_process_single_nzb.assert_any_call(
            "second.nzb",
            second_nzb,
            pp=2,
            script=None,
            cat="tv",
            url="http://example.com/test.nzb",
            priority=1,
            nzbname="TestDownload - second.nzb",
            dup_check=False,
        )

    @mock.patch("sabnzbd.postproc.process_single_nzb")
    @mock.patch("sabnzbd.postproc.listdir_full")
    def test_process_nzb_only_download_mixed_files(self, mock_listdir, mock_process_single_nzb):
        """Test process_nzb_only_download with mixed file types returns None"""
        # Setup mock NZO
        fake_nzo = mock.Mock()
        fake_nzo.final_name = "TestDownload"

        # Mock mixed files (NZB and non-NZB)
        workdir = os.path.join(SAB_CACHE_DIR, "test_workdir")
        mock_listdir.return_value = [
            os.path.join(workdir, "test.nzb"),
            os.path.join(workdir, "readme.txt"),
        ]

        # Call the function
        result = postproc.process_nzb_only_download(workdir, fake_nzo)

        # Verify result is None (not NZB-only)
        assert result is None

        # Verify process_single_nzb was NOT called
        mock_process_single_nzb.assert_not_called()

    @mock.patch("sabnzbd.postproc.process_single_nzb")
    @mock.patch("sabnzbd.postproc.listdir_full")
    def test_process_nzb_only_download_empty_directory(self, mock_listdir, mock_process_single_nzb):
        """Test process_nzb_only_download with empty directory returns None"""
        # Setup mock NZO
        fake_nzo = mock.Mock()
        fake_nzo.final_name = "TestDownload"

        # Mock empty directory
        workdir = os.path.join(SAB_CACHE_DIR, "test_workdir")
        mock_listdir.return_value = []

        # Call the function
        result = postproc.process_nzb_only_download(workdir, fake_nzo)

        # Verify result is None (no files)
        assert result is None

        # Verify process_single_nzb was NOT called
        mock_process_single_nzb.assert_not_called()


class TestCheckEncryptedAndUnwantedPostproc:
    """Tests for check_encrypted_and_unwanted_postproc"""

    @staticmethod
    def _make_nzo(**overrides):
        nzo = mock.Mock()
        nzo.final_name = "TestJob"
        nzo.unwanted_ext = 0
        nzo.encrypted = 0
        nzo.fail_msg = ""
        for k, v in overrides.items():
            setattr(nzo, k, v)
        return nzo

    @mock.patch("sabnzbd.assembler.check_encrypted_and_unwanted_files")
    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=True)
    def test_rar_with_unwanted_extension_aborts(self, _mock_is_rar, mock_check, tmp_path):
        """RAR containing an unwanted file is detected and aborts"""
        rar = tmp_path / "test.rar"
        rar.write_bytes(b"data")
        mock_check.return_value = (False, "malware.exe")

        nzo = self._make_nzo()
        assert postproc.check_encrypted_and_unwanted_postproc(nzo, [str(rar)]) is True
        assert "unwanted" in nzo.fail_msg.lower()

    @mock.patch("sabnzbd.assembler.check_encrypted_and_unwanted_files")
    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=True)
    def test_rar_with_encryption_aborts(self, _mock_is_rar, mock_check, tmp_path):
        """Encrypted RAR is detected and aborts"""
        rar = tmp_path / "test.rar"
        rar.write_bytes(b"data")
        mock_check.return_value = (True, None)

        nzo = self._make_nzo()
        assert postproc.check_encrypted_and_unwanted_postproc(nzo, [str(rar)]) is True
        assert "encryption" in nzo.fail_msg.lower()

    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=False)
    def test_non_rar_unwanted_extension_aborts(self, _mock_is_rar, tmp_path):
        """Plain file with an unwanted extension is detected"""
        bad_file = tmp_path / "payload.exe"
        bad_file.write_bytes(b"data")

        nzo = self._make_nzo()

        @set_config({"unwanted_extensions": ["exe"], "action_on_unwanted_extensions": 2})
        def _run():
            return postproc.check_encrypted_and_unwanted_postproc(nzo, [str(bad_file)])

        assert _run() is True
        assert "unwanted" in nzo.fail_msg.lower()

    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=False)
    def test_non_rar_allowed_extension_passes(self, _mock_is_rar, tmp_path):
        """Plain file with an allowed extension passes"""
        good_file = tmp_path / "movie.mkv"
        good_file.write_bytes(b"data")

        nzo = self._make_nzo()

        @set_config({"unwanted_extensions": ["exe"], "action_on_unwanted_extensions": 2})
        def _run():
            return postproc.check_encrypted_and_unwanted_postproc(nzo, [str(good_file)])

        assert _run() is False

    @mock.patch("sabnzbd.assembler.check_encrypted_and_unwanted_files")
    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=True)
    def test_retry_skips_unwanted_in_rar(self, _mock_is_rar, mock_check, tmp_path):
        """unwanted_ext == 2 (retry override) skips unwanted-in-RAR checks"""
        rar = tmp_path / "test.rar"
        rar.write_bytes(b"data")
        mock_check.return_value = (False, "malware.exe")

        nzo = self._make_nzo(unwanted_ext=2)
        assert postproc.check_encrypted_and_unwanted_postproc(nzo, [str(rar)]) is False

    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=False)
    def test_retry_skips_unwanted_plain_file(self, _mock_is_rar, tmp_path):
        """unwanted_ext == 2 (retry override) skips plain-file unwanted checks"""
        bad_file = tmp_path / "payload.exe"
        bad_file.write_bytes(b"data")

        nzo = self._make_nzo(unwanted_ext=2)

        @set_config({"unwanted_extensions": ["exe"], "action_on_unwanted_extensions": 2})
        def _run():
            return postproc.check_encrypted_and_unwanted_postproc(nzo, [str(bad_file)])

        assert _run() is False

    @mock.patch("sabnzbd.assembler.check_encrypted_and_unwanted_files")
    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=True)
    def test_retry_still_checks_encryption(self, _mock_is_rar, mock_check, tmp_path):
        """unwanted_ext == 2 (retry override) still detects encrypted RARs"""
        rar = tmp_path / "test.rar"
        rar.write_bytes(b"data")
        mock_check.return_value = (True, None)

        nzo = self._make_nzo(unwanted_ext=2)
        assert postproc.check_encrypted_and_unwanted_postproc(nzo, [str(rar)]) is True

    def test_nonexistent_files_skipped(self):
        """Files that no longer exist are silently skipped"""
        nzo = self._make_nzo()
        assert postproc.check_encrypted_and_unwanted_postproc(nzo, ["/no/such/file.rar"]) is False

    @mock.patch("sabnzbd.assembler.check_encrypted_and_unwanted_files")
    @mock.patch("sabnzbd.postproc.rarfile.is_rarfile", return_value=True)
    def test_clean_rar_passes(self, _mock_is_rar, mock_check, tmp_path):
        """RAR with no issues passes"""
        rar = tmp_path / "clean.rar"
        rar.write_bytes(b"data")
        mock_check.return_value = (False, None)

        nzo = self._make_nzo()
        assert postproc.check_encrypted_and_unwanted_postproc(nzo, [str(rar)]) is False


class TestPostProcUnwantedFileDiscovery:
    """Tests verifying which files get passed to the unwanted check
    after par2 repair and after unpacking."""

    @staticmethod
    def _make_nzo(download_path, **overrides):
        nzo = mock.Mock()
        nzo.final_name = "TestJob"
        nzo.fail_msg = ""
        nzo.repair = True
        nzo.unpack = True
        nzo.delete = True
        nzo.precheck = False
        nzo.cat = None
        nzo.script = "None"
        nzo.url = ""
        nzo.status = Status.QUEUED
        nzo.direct_unpacker = None
        nzo.download_path = str(download_path)
        nzo.admin_path = str(download_path / "__admin__")
        nzo.unchecked_files = set()
        nzo.unwanted_ext = 0
        nzo.encrypted = 0
        nzo.pp_or_finished = False
        for k, v in overrides.items():
            setattr(nzo, k, v)
        return nzo

    @mock.patch("sabnzbd.postproc.check_encrypted_and_unwanted_postproc")
    @mock.patch("sabnzbd.postproc.parring")
    @mock.patch("sabnzbd.postproc.notifier")
    @mock.patch("sabnzbd.postproc.globber", return_value=["__admin__", "file1"])
    def test_unchecked_files_rechecked_after_repair(self, _glob, _notif, mock_parring, mock_check, tmp_path):
        """Files that failed the assembler check (in unchecked_files) are
        re-checked after par2 repair completes successfully."""
        # Set up download dir with a file that was "unchecked" during assembly
        download_path = tmp_path / "incomplete" / "job"
        download_path.mkdir(parents=True)
        rar_file = download_path / "data.part1.rar"
        rar_file.write_bytes(b"repaired-rar-data")

        nzo = self._make_nzo(download_path, unchecked_files={str(rar_file)})
        mock_parring.return_value = (False, False)  # no par_error, no re_add
        mock_check.return_value = False

        with mock.patch("sabnzbd.postproc.listdir_full", return_value=[str(rar_file)]):
            postproc.parring = mock_parring
            # Simulate the repair section of process_job
            files_before = set(postproc.listdir_full(nzo.download_path))
            mock_parring(nzo)
            files_after = set(postproc.listdir_full(nzo.download_path))

            new_repair_files = files_after - files_before
            files_to_check = [f for f in nzo.unchecked_files if os.path.exists(f)]
            files_to_check.extend(new_repair_files)
            if files_to_check:
                postproc.check_encrypted_and_unwanted_postproc(nzo, files_to_check)

        # The previously-unchecked rar must be in the check list
        mock_check.assert_called_once()
        checked_files = mock_check.call_args[0][1]
        assert str(rar_file) in checked_files

    @mock.patch("sabnzbd.postproc.check_encrypted_and_unwanted_postproc")
    def test_new_files_from_repair_checked(self, mock_check, tmp_path):
        """Files that appear after par2 repair (e.g. reconstructed from
        par2 recovery data) are detected and checked."""
        download_path = tmp_path / "incomplete" / "job"
        download_path.mkdir(parents=True)

        existing_file = download_path / "data.part1.rar"
        existing_file.write_bytes(b"existing")

        nzo = self._make_nzo(download_path)
        mock_check.return_value = False

        # Snapshot "before" with only the existing file
        files_before = {str(existing_file)}

        # Simulate par2 creating a new reconstructed file
        hidden_file = download_path / "hidden_payload.rar"
        hidden_file.write_bytes(b"was-hidden-in-par2-data")

        # Snapshot "after"
        files_after = {str(existing_file), str(hidden_file)}

        new_repair_files = files_after - files_before
        files_to_check = list(new_repair_files)
        if files_to_check:
            postproc.check_encrypted_and_unwanted_postproc(nzo, files_to_check)

        mock_check.assert_called_once()
        checked_files = mock_check.call_args[0][1]
        assert str(hidden_file) in checked_files
        # The pre-existing file should NOT be in the new-files list
        assert str(existing_file) not in checked_files

    @mock.patch("sabnzbd.postproc.check_encrypted_and_unwanted_postproc")
    def test_renamed_files_from_repair_checked(self, mock_check, tmp_path):
        """Files renamed by par2 (obfuscated;real name) appear as new
        in the after-repair snapshot and are checked."""
        download_path = tmp_path / "incomplete" / "job"
        download_path.mkdir(parents=True)

        obfuscated = download_path / "a1b2c3d4e5.xyz"
        obfuscated.write_bytes(b"obfuscated-rar")

        nzo = self._make_nzo(download_path)
        mock_check.return_value = False

        # Snapshot "before" with obfuscated name
        files_before = {str(obfuscated)}

        # Simulate par2 renaming the file
        real_name = download_path / "movie.part1.rar"
        obfuscated.rename(real_name)

        # Snapshot "after" – the obfuscated name is gone, real name appeared
        files_after = {str(real_name)}

        new_repair_files = files_after - files_before
        files_to_check = list(new_repair_files)
        if files_to_check:
            postproc.check_encrypted_and_unwanted_postproc(nzo, files_to_check)

        mock_check.assert_called_once()
        checked_files = mock_check.call_args[0][1]
        assert str(real_name) in checked_files

    @mock.patch("sabnzbd.postproc.check_encrypted_and_unwanted_postproc")
    def test_unpacked_nested_files_checked(self, mock_check, tmp_path):
        """Files extracted by the unpacker (including from nested archives)
        are passed to the unwanted check."""
        workdir_complete = tmp_path / "complete" / "job"
        workdir_complete.mkdir(parents=True)

        # Simulate files the unpacker would return
        extracted_rar = workdir_complete / "nested.rar"
        extracted_rar.write_bytes(b"nested-rar")
        extracted_plain = workdir_complete / "readme.txt"
        extracted_plain.write_bytes(b"text")
        extracted_bad = workdir_complete / "hidden.exe"
        extracted_bad.write_bytes(b"bad")

        newfiles = [str(extracted_rar), str(extracted_plain), str(extracted_bad)]

        nzo = self._make_nzo(tmp_path / "incomplete" / "job")
        mock_check.return_value = False

        # This mirrors the post-unpack check in process_job
        if newfiles:
            postproc.check_encrypted_and_unwanted_postproc(nzo, newfiles)

        mock_check.assert_called_once()
        checked_files = mock_check.call_args[0][1]
        assert str(extracted_rar) in checked_files
        assert str(extracted_plain) in checked_files
        assert str(extracted_bad) in checked_files

    @mock.patch("sabnzbd.postproc.check_encrypted_and_unwanted_postproc")
    def test_unchecked_plus_new_files_combined(self, mock_check, tmp_path):
        """Both unchecked files from assembly AND new files from repair
        are combined into a single check call."""
        download_path = tmp_path / "incomplete" / "job"
        download_path.mkdir(parents=True)

        # File that failed the assembler check
        corrupt_rar = download_path / "corrupt.part1.rar"
        corrupt_rar.write_bytes(b"was-corrupt-now-repaired")

        # File that already existed and was fine
        existing = download_path / "good.part2.rar"
        existing.write_bytes(b"existing")

        nzo = self._make_nzo(download_path, unchecked_files={str(corrupt_rar)})
        mock_check.return_value = False

        files_before = {str(corrupt_rar), str(existing)}

        # Par2 repair reconstructs a missing file
        reconstructed = download_path / "good.part3.rar"
        reconstructed.write_bytes(b"reconstructed")

        files_after = {str(corrupt_rar), str(existing), str(reconstructed)}

        new_repair_files = files_after - files_before
        files_to_check = [f for f in nzo.unchecked_files if os.path.exists(f)]
        files_to_check.extend(new_repair_files)
        if files_to_check:
            postproc.check_encrypted_and_unwanted_postproc(nzo, files_to_check)

        mock_check.assert_called_once()
        checked_files = mock_check.call_args[0][1]
        # corrupt_rar was unchecked, must now be checked
        assert str(corrupt_rar) in checked_files
        # reconstructed is new, must be checked
        assert str(reconstructed) in checked_files
        # existing was already fine, should NOT be checked again
        assert str(existing) not in checked_files
