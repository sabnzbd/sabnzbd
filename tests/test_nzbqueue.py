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
tests.test_nzbqueue - Testing functions in nzbqueue.py
"""

import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest import mock

import pytest

import sabnzbd
from sabnzbd.constants import (
    JOB_ADMIN,
    ONDISK_VERSION,
    ONDISK_FILE,
    RENAMES_FILE,
    Status,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
)
from sabnzbd.database import HistoryDB
from sabnzbd.downloader import Server
from sabnzbd.filesystem import save_compressed, save_data
from sabnzbd.nzb import NzbFile, NzbObject
from sabnzbd.nzbqueue import NzbQueue
from tests.testhelper import (
    FakeHistoryDB,
    SAB_DATA_DIR,
    SAB_NEWSSERVER_HOST,
    SAB_NEWSSERVER_PORT,
    create_and_read_nzb_fp,
)


@pytest.fixture()
def nzbqueue_env(monkeypatch, mocker, tmp_path):
    sabnzbd.config.ConfigCat("*", {})

    sabnzbd.Scheduler = mocker.Mock()
    sabnzbd.Scheduler.analyse = mocker.Mock(return_value=False)
    sabnzbd.ArticleCache = mocker.Mock()
    sabnzbd.Assembler = mocker.Mock()
    sabnzbd.BPSMeter = mocker.Mock()
    sabnzbd.Downloader = SimpleNamespace(paused=False)
    sabnzbd.Downloader.servers = [
        Server(
            server_id="testserver1",
            displayname="testserver1",
            host=SAB_NEWSSERVER_HOST,
            port=SAB_NEWSSERVER_PORT,
            timeout=30,
            threads=8,
            priority=0,
            use_ssl=False,
            ssl_verify=3,
            ssl_ciphers="",
            pipelining_requests=mocker.Mock(return_value=1),
        )
    ]
    sabnzbd.NzbQueue = NzbQueue()
    sabnzbd.Downloader.disconnect = mocker.Mock()
    monkeypatch.setattr(sabnzbd.cfg.admin_dir, "get_path", lambda: str(tmp_path))
    monkeypatch.setattr(sabnzbd.cfg.download_dir, "get_path", lambda: str(tmp_path))

    yield

    del sabnzbd.NzbQueue
    del sabnzbd.Downloader
    del sabnzbd.BPSMeter
    del sabnzbd.Assembler
    del sabnzbd.ArticleCache
    del sabnzbd.Scheduler


def make_dummy_nzo(name: str, priority: int = NORMAL_PRIORITY, files: int = 50, articles: int = 200) -> NzbObject:
    work_name = f"job-{name}"

    article_size = 750_000
    nzo = NzbObject(work_name, priority=priority)
    nzo.files = [
        NzbFile(
            date=nzo.avg_date,
            subject=f"test-file-{file}",
            raw_article_db=[[f"{file}-article-{article}", article_size] for article in range(articles)],
            file_bytes=article_size * articles,
            nzo=nzo,
        )
        for file in range(files)
    ]

    return nzo


def make_dummy_postproc_nzo(name: str, download_path: str, status: str = Status.QUEUED, pp_active: bool = False):
    """Mock NzbObject in the post-processing queue, with all the attributes
    add_active_history() needs so it can pass through build_history()"""
    nzo = mock.Mock()
    nzo.nzo_id = f"SABnzbd_nzo_{name}"
    nzo.final_name = name
    nzo.filename = f"{name}.nzb"
    nzo.cat = "*"
    nzo.script = "none"
    nzo.url = ""
    nzo.status = status
    nzo.pp_active = pp_active
    nzo.repair = nzo.unpack = nzo.delete = True
    nzo.nzo_info = {}
    nzo.unpack_info = {}
    nzo.bytes_downloaded = 1024
    nzo.fail_msg = ""
    nzo.correct_password = ""
    nzo.action_line = ""
    nzo.duplicate_key = ""
    nzo.time_added = 0
    nzo.download_path = download_path
    return nzo


@pytest.fixture()
def make_nzb_workdir(nzbqueue_env):
    def _make_workdir(
        name: str,
        on_disk: Optional[dict[str, list[bool]]] = None,
        renames: Optional[dict[str, str]] = None,
    ) -> str:
        """Create a working directory for nzbqueue from tests/data"""
        wdir = tempfile.TemporaryDirectory(prefix=name, dir=sabnzbd.cfg.download_dir.get_path()).name
        admin_dir = os.path.join(wdir, JOB_ADMIN)
        os.makedirs(admin_dir)

        # Copy test data, create NZB-file and __ADMIN__
        nzb_fp = create_and_read_nzb_fp(name)
        save_compressed(admin_dir, name, nzb_fp)
        shutil.copytree(os.path.join(SAB_DATA_DIR, name), wdir, dirs_exist_ok=True)
        if on_disk:
            save_data((ONDISK_VERSION, on_disk), ONDISK_FILE, admin_dir)
        if renames:
            save_data(renames, RENAMES_FILE, admin_dir)
        return wdir

    yield _make_workdir


@pytest.mark.usefixtures("nzbqueue_env")
class TestNzbQueue:
    def test_save_and_restore_(self):
        q = NzbQueue()
        joba = make_dummy_nzo("a")
        jobb = make_dummy_nzo("b")
        q.add(joba)
        q.add(jobb)

        # Mark one of joba articles as tried
        article = next(iter(joba.files[0].articles))
        article.add_to_try_list(sabnzbd.Downloader.servers[0])
        q.save()

        # Both should be in the queue
        assert q.get_nzo(joba.nzo_id)
        assert q.get_nzo(jobb.nzo_id)

        # Reload the queue with no repair
        q = NzbQueue()
        q.read_queue(0)
        joba = q.get_nzo(joba.nzo_id)
        jobb = q.get_nzo(jobb.nzo_id)
        assert joba
        assert jobb

        # Try list restored
        assert sabnzbd.Downloader.servers[0] in next(iter(joba.files[0].articles)).try_list

    def test_stop_idle_jobs_no_crash_on_exhausted_articles(self):
        """Regression test: stop_idle_jobs must not raise RuntimeError when
        register_article removes an article from nzf.articles (a dict) while
        the same dict is being iterated.  Introduced by commit 44d94226e when
        nzf.articles was changed from list to dict but the protective [:] copy
        was dropped from the iteration in stop_idle_jobs."""
        server = sabnzbd.Downloader.servers[0]

        nzo = make_dummy_nzo("stall-test", files=1, articles=3)
        nzf = nzo.files[0]

        # Load all articles into memory (only first is loaded at NzbFile init)
        nzf.finish_import()

        q = NzbQueue()
        # add() resets try lists, so saturate them after adding
        q.add(nzo)
        sabnzbd.NzbQueue = q

        # Saturate all try-lists so stop_idle_jobs enters the article-removal branch
        nzo.add_to_try_list(server)
        nzf.add_to_try_list(server)
        for article in list(nzf.articles):
            article.add_to_try_list(server)

        # Must not raise RuntimeError: dictionary changed size during iteration
        q.stop_idle_jobs()

    @pytest.mark.skipif(not sabnzbd.WINDOWS, reason="Legacy 3.0.0 queue fixture contains Windows-specific paths")
    def test_restore_legacy_queue_format_3_0_0(self, tmp_path, monkeypatch):
        fixture_path = Path(SAB_DATA_DIR) / "test_3_0_0_data_format"
        shutil.copytree(fixture_path, tmp_path, dirs_exist_ok=True)

        nzbqueue = NzbQueue()
        nzbqueue.read_queue(repair=0)

        assert nzbqueue.actives() == 1
        nzo = nzbqueue.get_nzo("SABnzbd_nzo_7ormqfeg")

        # Check a number of basis statistics and parameters
        assert nzo.nzo_id == "SABnzbd_nzo_7ormqfeg"
        assert nzo.work_name == "test_download_100MB"
        assert nzo.filename == "test_download_100MB.nzb"
        assert nzo.cat == "*"
        assert nzo.priority == 1
        assert nzo.pp == 3

        assert len(nzo.files_table) == 13
        assert len(nzo.files) == 4
        assert len(nzo.finished_files) == 1
        assert len(nzo.extrapars["par-files"]) == 8
        assert len(nzo.saved_articles) == 22

        assert nzo.bytes == 114967316
        assert nzo.bytes_downloaded == 18532805
        assert nzo.bytes_missing == 0
        assert nzo.bytes_par2 == 42560
        assert nzo.bytes_tried == 30077349
        assert nzo.remaining == 84889967

        # Validate we can also load legacy NZF pickles from the restored NZO
        for nzf in nzo.files:
            nzf.finish_import()

        # Validate from specifc nzf some attributes
        cnzf = nzo.get_nzf_by_id("SABnzbd_nzf_799tdim0")
        assert cnzf.nzo == nzo
        assert cnzf.filename == "rar-files.part1.rar"
        assert cnzf.md5of16k == b"e\xc4^\x93\xc4\x92\xf9s\x057Oe!\x9dA\xe7"
        assert len(cnzf.articles) == 51
        assert len(cnzf.decodetable) == 73

        assert cnzf.bytes == 27049565
        assert cnzf.bytes_left == 10777869
        assert cnzf.crc32 is None

    def test_nzo_reuse(self, make_nzb_workdir):
        wdir = make_nzb_workdir("basic_rar5")

        nzo_id = sabnzbd.NzbQueue.repair_job(wdir, None, None)
        assert nzo_id
        nzo = sabnzbd.NzbQueue.get_nzo(nzo_id)
        # No files to download so goes straight to post-processing
        assert not nzo

    def test_nzo_reuse_failed_articles(self, make_nzb_workdir):
        wdir = make_nzb_workdir("basic_rar5", {"testfile.rar": [False]})

        nzo_id = sabnzbd.NzbQueue.repair_job(wdir, None, None)
        assert nzo_id
        nzo = sabnzbd.NzbQueue.get_nzo(nzo_id)
        assert nzo
        # testfile.rar is on disk, but it has missing articles
        assert nzo.files
        assert not nzo.finished_files

    def test_nzo_reuse_failed_articles_renamed(self, make_nzb_workdir):
        wdir = make_nzb_workdir(
            "basic_rar5",
            {"renamed.rar": [False]},
            {"renamed.rar": "testfile.rar"},
        )
        os.rename(os.path.join(wdir, "testfile.rar"), os.path.join(wdir, "renamed.rar"))

        nzo_id = sabnzbd.NzbQueue.repair_job(wdir, None, None)
        assert nzo_id
        nzo = sabnzbd.NzbQueue.get_nzo(nzo_id)
        assert nzo
        # renamed.rar is on disk, but it has missing articles
        assert nzo.files
        assert not nzo.finished_files

    def test_scan_jobs_known_jobs(self, mocker, monkeypatch, tmp_path):
        """Folders belonging to jobs in the download queue, the post-processing
        queue, or retryable from History must not be treated as orphans.
        Anything else in the incomplete folder is an orphan."""
        monkeypatch.setattr(HistoryDB, "db_path", str(tmp_path / "history1.db"))
        monkeypatch.setattr(HistoryDB, "startup_done", False)

        def make_job_folder(name: str) -> str:
            path = os.path.join(sabnzbd.cfg.download_dir.get_path(), name)
            os.makedirs(path, exist_ok=True)
            return path

        # Job in the download queue
        queued_nzo = make_dummy_nzo("queued", files=1, articles=1)
        sabnzbd.NzbQueue.add(queued_nzo, save=False)
        make_job_folder(queued_nzo.work_name)

        # Job waiting in the post-processing queue
        postproc_path = make_job_folder("job-postproc")
        pp_nzo = make_dummy_postproc_nzo("job-postproc", postproc_path)
        mocker.patch.object(sabnzbd, "PostProcessor", create=True)
        sabnzbd.PostProcessor.get_queue.return_value = [pp_nzo]

        with FakeHistoryDB(str(tmp_path / "history1.db")) as history_db:
            # The postproc job is also already in the history database, which briefly happens at the end of post-processing
            history_db.add_fake_history_job("job-postproc", Status.COMPLETED, path=postproc_path)
            # Failed job with the incomplete folder still on disk: retryable
            history_db.add_fake_history_job("job-failed", Status.FAILED, path=make_job_folder("job-failed"))
            # Failed job whose recorded incomplete folder no longer exists is not retryable, so a same-named folder is an orphan
            make_job_folder("job-gone")
            history_db.add_fake_history_job("job-gone", Status.FAILED, path=str(tmp_path / "elsewhere" / "job-gone"))
            # A failed URL-fetch (report = 'future') is always retryable, regardless of status or whether the folder exists
            history_db.add_fake_history_job(
                "job-future", Status.COMPLETED, path=make_job_folder("job-future"), futuretype=True
            )
            # Completed job: its folder should no longer exist, so treat leftovers as orphans
            history_db.add_fake_history_job("job-completed", Status.COMPLETED, path=make_job_folder("job-completed"))
            # Archived jobs are not visible to queue repair, even when they would
            # otherwise be retryable, so the folder is treated as an orphan
            history_db.add_fake_history_job(
                "job-archived", Status.FAILED, path=make_job_folder("job-archived"), archive=True
            )

        # Folder not known anywhere
        make_job_folder("job-orphan")

        orphans = sabnzbd.NzbQueue.scan_jobs(action=False)
        assert sorted(orphans) == ["job-archived", "job-completed", "job-gone", "job-orphan"]

        # With all_jobs=True the download queue itself is not considered registered
        orphans_all = sabnzbd.NzbQueue.scan_jobs(all_jobs=True, action=False)
        assert queued_nzo.work_name in orphans_all

    @pytest.fixture
    def queue(self, nzbqueue_env):
        return NzbQueue()

    def test_add_inserts_and_tracks_jobs(self, queue):
        a = make_dummy_nzo("a", priority=NORMAL_PRIORITY)
        b = make_dummy_nzo("b", priority=LOW_PRIORITY)
        c = make_dummy_nzo("c", priority=FORCE_PRIORITY)

        ida = queue.add(a, save=False, quiet=True)
        idb = queue.add(b, save=False, quiet=True)
        idc = queue.add(c, save=False, quiet=True)

        # All ids registered
        assert queue.get_nzo(ida) is a
        assert queue.get_nzo(idb) is b
        assert queue.get_nzo(idc) is c

        # queue_info returns all three, first should be the forced job
        _, _, _, nzo_list, _, count = queue.queue_info()
        assert count == 3
        assert [n.final_name for n in nzo_list] == [c.final_name, a.final_name, b.final_name]

    def test_remove_removes_from_queue_and_table(self, queue):
        a = make_dummy_nzo("a", priority=0)
        b = make_dummy_nzo("b", priority=0)
        c = make_dummy_nzo("c", priority=0)

        _ida = queue.add(a, save=False, quiet=True)
        idb = queue.add(b, save=False, quiet=True)
        _idc = queue.add(c, save=False, quiet=True)

        removed = queue.remove(idb, cleanup=False, delete_all_data=False)
        assert removed is b
        assert queue.get_nzo(idb) is None

        _, _, _, nzo_list, _, count = queue.queue_info()
        assert count == 2
        assert [nzo.final_name for nzo in nzo_list] == ["job-a", "job-c"]

    def test_remove_multiple_and_remove_all(self, queue):
        jobs = [make_dummy_nzo(f"job-{i}", priority=0) for i in range(5)]
        ids = [queue.add(nzo, save=False, quiet=True) for nzo in jobs]

        # Remove two specific jobs
        subset = ids[1:3]
        removed_ids = queue.remove_multiple(subset, delete_all_data=False)
        assert set(removed_ids) == set(subset)

        # Remaining ids still there
        remaining_ids = {nid for nid in ids if nid not in subset}
        assert {nzo.nzo_id for nzo in queue.queue_info()[3]} == remaining_ids

        # remove_all with search pattern should remove the rest
        removed_all = queue.remove_all(search="job-")
        assert set(removed_all) == remaining_ids
        assert queue.queue_info()[5] == 0  # nzos_matched

    def test_change_opts_sets_pp(self, queue):
        a = make_dummy_nzo("a", priority=LOW_PRIORITY)
        ida = queue.add(a, save=False, quiet=True)

        changed = queue.change_opts([ida], pp=3)
        assert changed == 1
        assert a.pp == 3

    def test_change_script_only_when_valid(self, queue, monkeypatch):
        from sabnzbd import nzbqueue as nzbqueue_mod

        # Always accept given script
        monkeypatch.setattr(nzbqueue_mod, "is_valid_script", lambda s: True)

        a = make_dummy_nzo("a", priority=0)
        b = make_dummy_nzo("b", priority=0)
        ida = queue.add(a, save=False, quiet=True)
        idb = queue.add(b, save=False, quiet=True)

        changed = queue.change_script([ida, idb], script="myscript.py")
        assert changed == 2
        assert a.script == "myscript.py"
        assert b.script == "myscript.py"

        # Now mark scripts invalid; no changes should be made
        monkeypatch.setattr(nzbqueue_mod, "is_valid_script", lambda s: False)
        changed = queue.change_script([ida, idb], script="other.py")
        assert changed == 0
        assert a.script == "myscript.py"
        assert b.script == "myscript.py"

    def test_change_cat_updates_cat_pp_script_and_priority(self, queue, monkeypatch):
        from sabnzbd import nzbqueue as nzbqueue_mod

        # Fake cat_to_opts: (cat, pp, script, prio)
        def fake_cat_to_opts(cat):
            return f"{cat}-cat", 2, "cat_script.py", FORCE_PRIORITY

        monkeypatch.setattr(nzbqueue_mod, "cat_to_opts", fake_cat_to_opts)

        a = make_dummy_nzo("a", priority=0)
        ida = queue.add(a, save=False, quiet=True)

        changed = queue.change_cat([ida], cat="movies")
        assert changed == 1
        assert a.cat == "movies-cat"
        assert a.script == "cat_script.py"
        assert a.priority == FORCE_PRIORITY

    def test_change_name_updates_final_name(self, queue):
        a = make_dummy_nzo("a", priority=0)
        ida = queue.add(a, save=False, quiet=True)

        ok = queue.change_name(ida, "renamed")
        assert ok is True
        assert a.final_name == "renamed"

    @staticmethod
    def get_queue_order(queue):
        return [n.final_name for n in queue.queue_info()[3]]

    def test_set_priority_moves_job_to_forced_top(self, queue):
        a = make_dummy_nzo("a", priority=0)
        b = make_dummy_nzo("b", priority=0)
        c = make_dummy_nzo("c", priority=0)

        _ida = queue.add(a, save=False, quiet=True)
        idb = queue.add(b, save=False, quiet=True)
        _idc = queue.add(c, save=False, quiet=True)

        assert self.get_queue_order(queue) == ["job-a", "job-b", "job-c"]

        # Set b to FORCE_PRIORITY, should go to the top
        _pos = queue.set_priority([idb], FORCE_PRIORITY)
        # pos is index; we just verify ordering
        assert self.get_queue_order(queue)[0] == "job-b"
        assert b.priority == FORCE_PRIORITY

    def test_switch_swaps_positions(self, queue):
        a = make_dummy_nzo("a", priority=NORMAL_PRIORITY)
        b = make_dummy_nzo("b", priority=NORMAL_PRIORITY)
        c = make_dummy_nzo("c", priority=NORMAL_PRIORITY)

        ida = queue.add(a, save=False, quiet=True)
        _idb = queue.add(b, save=False, quiet=True)
        idc = queue.add(c, save=False, quiet=True)

        assert self.get_queue_order(queue) == ["job-a", "job-b", "job-c"]

        # Move a to c
        new_pos, _prio = queue.switch(ida, idc)
        assert new_pos != -1
        assert self.get_queue_order(queue) == ["job-b", "job-c", "job-a"]

    def test_switch_swaps_positions_different_priority(self, queue):
        a = make_dummy_nzo("a", priority=HIGH_PRIORITY)
        b = make_dummy_nzo("b", priority=NORMAL_PRIORITY)
        c = make_dummy_nzo("c", priority=NORMAL_PRIORITY)

        ida = queue.add(a, save=False, quiet=True)
        _idb = queue.add(b, save=False, quiet=True)
        idc = queue.add(c, save=False, quiet=True)

        assert self.get_queue_order(queue) == ["job-a", "job-b", "job-c"]

        # Move a to c
        new_pos, _prio = queue.switch(ida, idc)
        assert new_pos != -1
        assert a.priority == NORMAL_PRIORITY
        assert b.priority == NORMAL_PRIORITY
        assert c.priority == NORMAL_PRIORITY
        assert self.get_queue_order(queue) == ["job-b", "job-c", "job-a"]

    def test_switch_swaps_positions_different_priority_2(self, queue):
        a = make_dummy_nzo("a", priority=HIGH_PRIORITY)
        b = make_dummy_nzo("b", priority=HIGH_PRIORITY)
        c = make_dummy_nzo("c", priority=NORMAL_PRIORITY)

        ida = queue.add(a, save=False, quiet=True)
        _idb = queue.add(b, save=False, quiet=True)
        idc = queue.add(c, save=False, quiet=True)

        assert self.get_queue_order(queue) == ["job-a", "job-b", "job-c"]

        # Move a to c
        new_pos, _prio = queue.switch(ida, idc)
        assert new_pos != -1
        assert b.priority == HIGH_PRIORITY
        assert c.priority == NORMAL_PRIORITY
        assert a.priority == NORMAL_PRIORITY
        assert self.get_queue_order(queue) == ["job-b", "job-c", "job-a"]

    def test_switch_swaps_positions_different_priority_3(self, queue):
        a = make_dummy_nzo("a", priority=HIGH_PRIORITY)
        b = make_dummy_nzo("b", priority=NORMAL_PRIORITY)
        c = make_dummy_nzo("c", priority=NORMAL_PRIORITY)

        ida = queue.add(a, save=False, quiet=True)
        _idb = queue.add(b, save=False, quiet=True)
        idc = queue.add(c, save=False, quiet=True)

        assert self.get_queue_order(queue) == ["job-a", "job-b", "job-c"]

        # Move c to a
        new_pos, _prio = queue.switch(idc, ida)
        assert new_pos != -1
        assert c.priority == HIGH_PRIORITY
        assert a.priority == HIGH_PRIORITY
        assert b.priority == NORMAL_PRIORITY
        assert self.get_queue_order(queue) == ["job-c", "job-a", "job-b"]

    def test_switch_moves_job_below_its_lower_priority_neighbour(self, queue):
        """Moving onto the first job of the next priority group must actually move it"""
        a = make_dummy_nzo("a", priority=HIGH_PRIORITY)
        b = make_dummy_nzo("b", priority=NORMAL_PRIORITY)
        queue.add(a, save=False, quiet=True)
        queue.add(b, save=False, quiet=True)

        pos, prio = queue.switch(a.nzo_id, b.nzo_id)

        assert self.get_queue_order(queue) == ["job-b", "job-a"]
        assert pos == 1
        assert prio == NORMAL_PRIORITY

    def test_send_back_keeps_job_in_the_bucket_matching_its_priority(self, queue, monkeypatch):
        """The replacement job can resolve a different priority than the job it replaces"""
        old = make_dummy_nzo("old", priority=HIGH_PRIORITY)
        queue.add(old, save=False, quiet=True)
        monkeypatch.setattr(old, "download_path", "/tmp/old", raising=False)
        monkeypatch.setattr(sabnzbd.filesystem, "globber_full", lambda *a, **k: ["/tmp/old.nzb.gz"])
        monkeypatch.setattr("sabnzbd.nzbqueue.globber_full", lambda *a, **k: ["/tmp/old.nzb.gz"])

        def fake_process_single_nzb(*args, **kwargs):
            queue.remove(kwargs["nzo_id"], cleanup=False, delete_all_data=False)
            replacement = make_dummy_nzo("new", priority=NORMAL_PRIORITY)
            replacement.nzo_id = kwargs["nzo_id"]
            queue.add(replacement, save=False, quiet=True)
            return 0, [replacement.nzo_id]

        monkeypatch.setattr("sabnzbd.nzbqueue.process_single_nzb", fake_process_single_nzb)
        queue.send_back(old)

        # Removing must find the job in the bucket its own priority points at
        nzo_id = queue.queue_info()[3][0].nzo_id
        assert queue.remove(nzo_id, cleanup=False, delete_all_data=False)
        assert queue.queue_info()[3] == []

    @pytest.mark.parametrize(
        "value2, expected_order",
        [
            ("1", ["job-b", "job-a", "job-c"]),
            ("-1", ["job-b", "job-c", "job-a"]),
            ("-2", ["job-b", "job-a", "job-c"]),
            # Out of range, unparsable and non-decimal numerics all leave the queue alone
            ("99", ["job-a", "job-b", "job-c"]),
            ("-99", ["job-a", "job-b", "job-c"]),
            ("\u00b2", ["job-a", "job-b", "job-c"]),
            ("abc", ["job-a", "job-b", "job-c"]),
            ("", ["job-a", "job-b", "job-c"]),
        ],
    )
    def test_switch_accepts_an_index_as_second_parameter(self, queue, value2, expected_order):
        jobs = [make_dummy_nzo(name) for name in "abc"]
        for nzo in jobs:
            queue.add(nzo, save=False, quiet=True)

        queue.switch(jobs[0].nzo_id, value2)

        assert self.get_queue_order(queue) == expected_order

    def test_has_forced_jobs_true_when_forced_and_active(self, queue):
        forced = make_dummy_nzo("forced", priority=FORCE_PRIORITY)
        normal = make_dummy_nzo("normal", priority=0)

        queue.add(forced, save=False, quiet=True)
        queue.add(normal, save=False, quiet=True)

        assert queue.has_forced_jobs() is True

        # If forced job is paused, it should no longer count
        forced.status = Status.PAUSED
        assert queue.has_forced_jobs() is False

    def test_has_forced_jobs_false_when_no_forced(self, queue):
        a = make_dummy_nzo("a", priority=0)
        b = make_dummy_nzo("b", priority=LOW_PRIORITY)
        queue.add(a, save=False, quiet=True)
        queue.add(b, save=False, quiet=True)

        assert queue.has_forced_jobs() is False

    def test_add_future_job_saves_with_expected_prefix(self, queue):
        """Queue repair deletes anything in the future folder not named SABnzbd_nzo_*"""
        nzo = NzbObject("future-job", futuretype=True)
        queue.add(nzo)

        written = os.listdir(nzo.admin_path)
        assert written
        assert all(name.startswith("SABnzbd_nzo_") for name in written), written

    @pytest.mark.parametrize("field", ["name", "size", "bytes", "avg_age", "remaining", "remaining_bytes"])
    @pytest.mark.parametrize("direction", ["asc", "desc"])
    def test_sort_queue_every_field(self, queue, field, direction):
        for name, priority in (("a", NORMAL_PRIORITY), ("b", LOW_PRIORITY), ("c", HIGH_PRIORITY)):
            queue.add(make_dummy_nzo(name, priority=priority), save=False, quiet=True)

        queue.sort_queue(field, direction)

        # Whatever the field, priority grouping is preserved
        priorities = [nzo.priority for nzo in queue.queue_info()[3]]
        assert priorities == sorted(priorities, reverse=True)

    @pytest.mark.parametrize("auto_sort", ["name asc", "remaining asc", "remaining_bytes asc"])
    def test_update_sort_order(self, queue, monkeypatch, auto_sort):
        monkeypatch.setattr(sabnzbd.cfg.auto_sort, "get", lambda: auto_sort)
        queue.add(make_dummy_nzo("a"), save=False, quiet=True)

        queue.update_sort_order()
