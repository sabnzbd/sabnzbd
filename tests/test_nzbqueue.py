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

import shutil
from pathlib import Path
from types import SimpleNamespace

from sabnzbd.downloader import Server
from sabnzbd.nzb import NzbObject, NzbFile
from sabnzbd.nzbqueue import NzbQueue
from tests.testhelper import *


@pytest.fixture()
def nzbqueue_env(monkeypatch, mocker, tmp_path):
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
    monkeypatch.setattr(sabnzbd.cfg.admin_dir, "get_path", lambda: str(tmp_path))
    monkeypatch.setattr(sabnzbd.cfg.download_dir, "get_path", lambda: str(tmp_path))

    yield

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


@pytest.mark.usefixtures("nzbqueue_env")
class TestNzbQueue:
    def test_save_and_restore_(self):
        q = NzbQueue()
        joba = make_dummy_nzo("a")
        jobb = make_dummy_nzo("b")
        q.add(joba)
        q.add(jobb)

        # Mark one of joba articles as tried
        article = list(joba.files[0].articles)[0]
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
        assert sabnzbd.Downloader.servers[0] in list(joba.files[0].articles)[0].try_list

    @pytest.mark.skipif(not sabnzbd.WINDOWS, reason="Legacy 3.0.0 queue fixture contains Windows-specific paths")
    def test_restore_legacy_queue_format_3_0_0(self, tmp_path, monkeypatch):
        fixture_path = Path(SAB_DATA_DIR) / "test_3_0_0_queue_format"
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
