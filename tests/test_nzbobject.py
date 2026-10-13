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
tests.test_nzbobject - Testing functions in nzbobject.py
"""

import datetime
import os
import pytest
from unittest import mock

import sabnzbd
from tests.testhelper import SAB_CACHE_DIR, create_and_read_nzb_fp

from sabnzbd.nzb import NzbObject
from sabnzbd.nzb.article import Article
from sabnzbd.nzb.file import NzbFile
from sabnzbd.par2file import FilePar2Info
from sabnzbd.config import ConfigCat
from sabnzbd.constants import NORMAL_PRIORITY, MAX_BAD_ARTICLES
from sabnzbd.filesystem import globber, sanitize_filename, create_all_dirs, long_path


@pytest.mark.usefixtures("clean_cache_dir")
class TestNZO:
    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_nzo_basic(self):
        # Need to create the Default category, as we would in normal instance
        # Otherwise it will try to save the config
        def_cat = ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})

        # Create empty object, normally used to grab URL's
        nzo = NzbObject("test_basic")
        assert nzo.work_name == "test_basic"
        assert not nzo.files

        # Renaming a file twice should remove the redundant entry
        nzo.renamed_file("YENC NAME", "NZF NAME")
        assert nzo.renames["YENC NAME"] == "NZF NAME"
        nzo.renamed_file("PAR2 NAME", "YENC NAME")
        assert nzo.renames["PAR2 NAME"] == "NZF NAME"
        assert len(nzo.renames) == 1

        # Create NZB-file to import
        nzb_fp = create_and_read_nzb_fp("basic_rar5")

        # Very basic test of NZO creation with data
        nzo = NzbObject("test_basic_data", nzb_fp=nzb_fp)
        assert nzo.final_name == "test_basic_data"
        assert nzo.files
        assert nzo.files[0].filename == "testfile.rar"
        assert nzo.bytes == 283
        assert nzo.files[0].bytes == 283

        # work_name can be trimmed in Windows due to max-path-length
        assert "test_basic_data".startswith(nzo.work_name)
        assert os.path.exists(nzo.admin_path)

        # Check if there's an nzf file and the backed-up nzb
        assert globber(nzo.admin_path, "*.nzb.gz")
        assert globber(nzo.admin_path, "SABnzbd_nzf*")

        # Should have picked up the default category settings
        assert nzo.cat == "*"
        assert nzo.script == def_cat.script() == "None"
        assert nzo.priority == def_cat.priority() == NORMAL_PRIORITY
        assert nzo.repair and nzo.unpack and nzo.delete

        # TODO: More checks!

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_get_unique_filepath_subdirs(self):
        """Par2 can name a file inside a sub-directory of the job, which we have to create"""
        ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})
        nzo = NzbObject("test_subdirs", nzb_fp=create_and_read_nzb_fp("basic_rar5"))

        filename, path = nzo.get_unique_filepath(sanitize_filename("sub/testfile.rar", allow_subdirs=True))
        assert filename == os.path.join("sub", "testfile.rar")
        assert path == os.path.join(nzo.download_path, "sub", "testfile.rar")
        # Created up front, so the assembler can write straight into it
        assert os.path.isdir(os.path.join(nzo.download_path, "sub"))

        # A repeat stays in the same folder, only the name is made unique
        filename, _path = nzo.get_unique_filepath(sanitize_filename("sub/testfile.rar", allow_subdirs=True))
        assert filename == os.path.join("sub", "testfile.1.rar")

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_check_existing_files_matches_subdirs(self):
        """On a retry the volumes can already be in the folder par2 named them in"""
        ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})
        nzo = NzbObject("test_reuse", nzb_fp=create_and_read_nzb_fp("basic_rar5"))
        nzf = nzo.files[0]
        assert nzf.filename == "testfile.rar"

        # A previous run adopted the par2 name, which is recorded for exactly this purpose
        nzo.renamed_file("sub/testfile.rar", "testfile.rar")

        # Put it on disk where par2 named it, as that previous run would have left it
        subdir = os.path.join(nzo.download_path, "sub")
        create_all_dirs(subdir)
        existing_path = os.path.join(subdir, "testfile.rar")
        with open(existing_path, "wb") as existing_file:
            existing_file.write(b"already downloaded")

        nzo.check_existing_files(nzo.download_path)

        assert nzf.filename == os.path.join("sub", "testfile.rar"), "sub-directory was not matched, re-downloading"
        assert nzf.filepath == existing_path

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    @pytest.mark.parametrize(
        "hostile_name",
        ["../escape.rar", "/escape.rar", "sub/../../escape.rar", "../../../../etc/escape.rar"],
    )
    def test_get_unique_filepath_cannot_escape_download_path(self, hostile_name):
        """Nothing a par2 can claim may put a file outside of the job folder"""
        ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})
        nzo = NzbObject("test_no_escape", nzb_fp=create_and_read_nzb_fp("basic_rar5"))

        _filename, path = nzo.get_unique_filepath(sanitize_filename(hostile_name, allow_subdirs=True))

        resolved = os.path.normpath(path)
        assert resolved.startswith(os.path.normpath(nzo.download_path) + os.sep), "%s escaped to %s" % (
            hostile_name,
            resolved,
        )

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    @pytest.mark.parametrize("hostile_name", ["http://../../../escape", "https://../escape", "a://../escape"])
    def test_url_nzbname_cannot_escape_download_dir(self, hostile_name):
        """A job name that looks like a URL is not exempt from sanitizing"""
        ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})
        nzo = NzbObject("test_url_name", nzb_fp=create_and_read_nzb_fp("basic_rar5"), nzbname=hostile_name)

        assert os.sep not in nzo.work_name
        assert os.sep not in nzo.final_name
        assert os.path.dirname(os.path.normpath(nzo.download_path)) == os.path.normpath(long_path(SAB_CACHE_DIR))

    @pytest.mark.config({"download_dir": SAB_CACHE_DIR})
    def test_purge_releases_par2_sessions(self):
        ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})
        nzo = NzbObject("test_purge_sessions")
        session = mock.Mock()
        nzo.par2_sessions = {"test": session}
        with (
            mock.patch.object(sabnzbd, "ArticleCache", create=True),
            mock.patch.object(sabnzbd, "Assembler", create=True),
        ):
            nzo.purge_data()
        session.close.assert_called_once()
        assert nzo.par2_sessions == {}


class TestCheckAvailabilityRatio:
    """Tests for NzbObject.check_availability_ratio().

    Setup: 1000 bytes of main files + 100 bytes of par2 (10% ratio).
    Formula: availability_ratio = 100 * (bytes - bytes_missing) / (bytes - bytes_par2)
                                = 100 * (1100 - bytes_missing) / 1000
    Passes (>= req_completion_rate of 100.2) when bytes_missing <= 98.
    """

    BYTES_MAIN = 1000
    BYTES_PAR2 = 100
    BYTES_TOTAL = BYTES_MAIN + BYTES_PAR2  # 1100

    def _make_nzo(self, bytes_missing: int, bad_articles: int = MAX_BAD_ARTICLES + 1) -> NzbObject:
        """Create a bare NzbObject with counters set directly (no NZB file needed)."""
        nzo = NzbObject("test_availability")
        nzo.bytes = self.BYTES_TOTAL
        nzo.bytes_par2 = self.BYTES_PAR2
        nzo.bytes_missing = bytes_missing
        nzo.bad_articles = bad_articles
        return nzo

    def test_nothing_missing(self):
        """All files present: ratio is well above the threshold."""
        nzo = self._make_nzo(bytes_missing=0)
        result, ratio = nzo.check_availability_ratio()
        assert result is True
        assert ratio == pytest.approx(110.0)

    def test_par2_missing_main_complete(self):
        """Regression: missing par2 articles must not cause a job abort.

        Before the fix, a failing par2 article would both decrement bytes_par2
        and increment bytes_missing, collapsing the ratio even when all main
        files were intact:
            old state (all par2 lost): bytes_par2=0, bytes_missing=100
            old ratio = 100 * (1100-100) / (1100-0) ≈ 90.9%  →  ABORT (bug)

        After the fix, bytes_par2 is stable and bytes_missing only tracks
        non-par2 failures:
            new state: bytes_par2=100, bytes_missing=0
            new ratio = 100 * 1100 / 1000 = 110%  →  OK
        """
        # Confirm the old code path would have triggered an abort
        old_ratio = 100 * (self.BYTES_TOTAL - self.BYTES_PAR2) / (self.BYTES_TOTAL - 0)
        assert old_ratio < 100.2  # would have aborted the job

        # With the fix: par2 bytes are not counted in bytes_missing
        nzo = self._make_nzo(bytes_missing=0)  # bytes_par2 stays at 100
        result, ratio = nzo.check_availability_ratio()
        assert result is True
        assert ratio == pytest.approx(110.0)

    def test_main_missing_within_threshold(self):
        """Some main bytes missing but still within par2 repair capacity."""
        nzo = self._make_nzo(bytes_missing=50)  # 5% of main
        result, ratio = nzo.check_availability_ratio()
        assert result is True
        assert ratio == pytest.approx(105.0)

    def test_main_missing_beyond_threshold(self):
        """Main bytes missing beyond repair capacity: job cannot succeed."""
        nzo = self._make_nzo(bytes_missing=150)  # 15% of main
        result, ratio = nzo.check_availability_ratio()
        assert result is False
        assert ratio == pytest.approx(95.0)

    def test_few_bad_articles_bypass(self):
        """When bad_articles <= MAX_BAD_ARTICLES the check always passes,
        allowing RAR-only jobs with minor corruption to proceed."""
        # bytes_missing=500 would normally fail, but the guard kicks in first
        nzo = self._make_nzo(bytes_missing=500, bad_articles=MAX_BAD_ARTICLES)
        result, ratio = nzo.check_availability_ratio()
        assert result is True
        # req_ratio is returned unchanged when the guard triggers
        assert ratio == pytest.approx(100.2)

    def test_only_par2_nzb(self):
        """NZB that consists entirely of par2 files: guard prevents division
        by zero and the job is allowed to proceed."""
        nzo = NzbObject("test_availability_par2_only")
        nzo.bytes = self.BYTES_PAR2
        nzo.bytes_par2 = self.BYTES_PAR2  # bytes == bytes_par2
        nzo.bytes_missing = 0
        nzo.bad_articles = MAX_BAD_ARTICLES + 1
        result, _ratio = nzo.check_availability_ratio()
        assert result is True

    def test_no_par2_missing_data(self):
        """NZB with no par2 at all: missing main bytes directly fail the check."""
        nzo = NzbObject("test_availability_no_par2")
        nzo.bytes = self.BYTES_MAIN
        nzo.bytes_par2 = 0
        nzo.bytes_missing = 50  # 5% of total
        nzo.bad_articles = MAX_BAD_ARTICLES + 1
        result, ratio = nzo.check_availability_ratio()
        assert result is False
        assert ratio == pytest.approx(95.0)


@pytest.mark.usefixtures("clean_cache_dir")
@pytest.mark.config({"download_dir": SAB_CACHE_DIR})
class TestBlockAccounting:
    """Tests for the block accounting NzbObject does during the download.

    One set of two 10000-byte files at a 1000-byte block size, so 10 blocks each,
    downloaded in 2500-byte articles.
    """

    BLOCKSIZE = 1000
    BLOCKCOUNT = 10
    FILESIZE = 10000
    ARTICLE_SIZE = 2500

    def _make_nzf(self, nzo: NzbObject, name: str, failed_articles=()) -> NzbFile:
        nzf = NzbFile(datetime.datetime(2026, 1, 1), name, [], self.FILESIZE, nzo)
        nzf.filename = name
        for index, offset in enumerate(range(0, self.FILESIZE, self.ARTICLE_SIZE)):
            article = Article("<a%d-%s>" % (index, name), self.ARTICLE_SIZE, nzf)
            article.data_begin = offset
            article.data_size = self.ARTICLE_SIZE
            if index in failed_articles:
                article.failed = True
            else:
                article.crc32 = 1
                article.on_disk = True
                nzf.bytes_left -= self.ARTICLE_SIZE
            nzf.decodetable.append(article)
        return nzf

    def _make_parfile(self, nzo: NzbObject, name: str, blocks: int) -> NzbFile:
        nzf = NzbFile(datetime.datetime(2026, 1, 1), name, [], 100, nzo)
        nzf.filename = name
        nzf.set_par2("myset", 1, blocks)
        # An article left outstanding, so the file does not count as downloaded
        article = Article("<p-%s>" % name, 100, nzf)
        nzf.articles[article] = article
        nzf.decodetable.append(article)
        return nzf

    def _make_nzo(self, failed_articles=()) -> NzbObject:
        nzo = NzbObject("test_block_accounting")
        nzo.par2packs["myset"] = {
            name: FilePar2Info(name, b"\0" * 16, self.FILESIZE, None, False, self.BLOCKSIZE, self.BLOCKCOUNT)
            for name in ("file1.rar", "file2.rar")
        }
        nzo.finished_files = [
            self._make_nzf(nzo, "file1.rar", failed_articles),
            self._make_nzf(nzo, "file2.rar"),
        ]
        nzo.extrapars["myset"] = [
            self._make_parfile(nzo, "myset.vol00+01.par2", 1),
            self._make_parfile(nzo, "myset.vol01+02.par2", 2),
            self._make_parfile(nzo, "myset.vol03+04.par2", 4),
        ]
        return nzo

    def test_undamaged(self):
        nzo = self._make_nzo()
        assert nzo.blocks_destroyed("myset") == 0

    def test_one_lost_article_destroys_every_block_it_touches(self):
        """A 2500-byte article covers part of blocks 2, 3 and 4."""
        nzo = self._make_nzo(failed_articles=(1,))
        assert nzo.blocks_destroyed("myset") == 3

    def test_unknown_set(self):
        nzo = self._make_nzo()
        assert nzo.blocks_destroyed("other") is None

    def test_no_block_geometry(self):
        """Jobs queued before the geometry was recorded fall back to the heuristic."""
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.par2packs["myset"]["file2.rar"].blocksize = 0
        assert nzo.blocks_destroyed("myset") is None

    def test_file_assembled_at_a_different_layout(self):
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.finished_files[1].direct_written = False
        assert nzo.blocks_destroyed("myset") is None

    def test_only_finished_files_count(self):
        """The count is a lower bound that grows as files complete."""
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.finished_files = nzo.finished_files[:1]
        assert nzo.blocks_destroyed("myset") == 3

    def test_recovery_blocks(self):
        nzo = self._make_nzo()
        assert nzo.recovery_blocks("myset") == 7
        assert nzo.recovery_blocks("otherset") == 0

    def test_another_sets_recovery_blocks_do_not_count(self):
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.extrapars["otherset"] = nzo.extrapars.pop("myset")
        for nzf in nzo.extrapars["otherset"]:
            nzf.setname = "otherset"
        assert nzo.blocks_beyond_recovery() is True

    def test_within_recovery(self):
        nzo = self._make_nzo(failed_articles=(1,))
        assert nzo.blocks_beyond_recovery() is False

    def test_beyond_recovery(self):
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.extrapars["myset"] = nzo.extrapars["myset"][:1]
        assert nzo.blocks_beyond_recovery() is True

    def test_beyond_recovery_needs_geometry(self):
        """Without geometry there is no fact to state, whatever the damage."""
        nzo = self._make_nzo(failed_articles=(0, 1, 2, 3))
        nzo.par2packs.clear()
        assert nzo.blocks_beyond_recovery() is False

    def test_prospective_add_sizes_against_the_blocks_destroyed(self):
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.prospective_add(nzo.finished_files[0])
        assert sorted(nzf.blocks for nzf in nzo.files) == [1, 2]

    def test_prospective_add_tops_up_rather_than_stacks(self):
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.prospective_add(nzo.finished_files[0])
        nzo.prospective_add(nzo.finished_files[0])
        assert sorted(nzf.blocks for nzf in nzo.files) == [1, 2]

    def test_damage_no_set_describes(self):
        """A file the packs do not name is damage the accounting cannot locate."""
        nzo = self._make_nzo()
        assert nzo.unmapped_damage() is False

        obfuscated = self._make_nzf(nzo, "abc123def.bin", failed_articles=(0, 1, 2, 3))
        nzo.finished_files.append(obfuscated)
        assert nzo.unmapped_damage() is True
        # It counts against no set, so the exact number cannot see it
        assert nzo.blocks_destroyed("myset") == 0

    def test_prospective_add_covers_damage_no_set_describes(self):
        """Regression: an unnamed file reads as undamaged and must not fetch nothing."""
        nzo = self._make_nzo()
        obfuscated = self._make_nzf(nzo, "abc123def.bin", failed_articles=(0, 1, 2, 3))
        nzo.finished_files.append(obfuscated)
        nzo.bad_articles = 4

        nzo.prospective_add(obfuscated)
        assert sorted(nzf.blocks for nzf in nzo.files) == [1, 2, 4]

    def test_undamaged_file_the_packs_do_not_name(self):
        """Only a file that lost articles leaves damage unaccounted for."""
        nzo = self._make_nzo()
        nzo.finished_files.append(self._make_nzf(nzo, "abc123def.bin"))
        assert nzo.unmapped_damage() is False

    def test_prospective_add_falls_back_to_bad_articles(self):
        nzo = self._make_nzo(failed_articles=(1,))
        nzo.par2packs.clear()
        nzo.bad_articles = 5
        nzo.prospective_add(nzo.finished_files[0])
        assert sorted(nzf.blocks for nzf in nzo.files) == [1, 2, 4]
