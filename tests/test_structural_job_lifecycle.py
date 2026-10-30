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
tests.test_structural_job_lifecycle - structural yEnc-encryption error lifecycle tests (OFFLINE, no network).

A fatal local structural yEnc-encryption error (missing password, unsupported version/cipher)
on one article must end the WHOLE job through the existing fail-to-history lifecycle: no
further articles of the job may be scheduled, and in-flight successful articles must not
revive the job. Wire/auth failures keep using search_new_server/provider failover
(tested in test_encryption.py).
"""

from types import SimpleNamespace
from unittest import mock

import pytest
from argon2.exceptions import HashingError
import sabctools

import sabnzbd
from sabnzbd.downloader import Server
from sabnzbd.constants import Status
from sabnzbd.decoder import decode
from sabnzbd.encryption import DecryptionAdapter, YEncEncryptionStructuralError
from sabnzbd.nzb import NzbFile, NzbObject
from sabnzbd.nzbqueue import NzbQueue
from tests.testhelper import SAB_NEWSSERVER_HOST, SAB_NEWSSERVER_PORT

ARTICLE_SIZE = 750_000


class TestStructuralErrorJobLifecycle:
    @pytest.fixture()
    def job_env(self, monkeypatch, mocker, tmp_path):
        """Real queue + real NZO with one file of several articles; network mocked."""
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
                pipelining_requests=1,
            )
        ]
        sabnzbd.Downloader.highest_server = lambda server: True
        monkeypatch.setattr(sabnzbd.cfg.admin_dir, "get_path", lambda: str(tmp_path))
        monkeypatch.setattr(sabnzbd.cfg.download_dir, "get_path", lambda: str(tmp_path))

        queue = NzbQueue()
        sabnzbd.NzbQueue = queue
        sabnzbd.PostProcessor = mocker.Mock()

        # One file, 5 articles
        nzo = NzbObject("structural-lifecycle-job")
        nzo.yenc_encrypted = True
        nzo.password = None  # structural trigger: no password anywhere
        nzo.precheck = False
        nzo.files = [
            NzbFile(
                date=nzo.avg_date,
                subject="test-file-0",
                raw_article_db=[[f"article-{a}", ARTICLE_SIZE] for a in range(5)],
                file_bytes=ARTICLE_SIZE * 5,
                nzo=nzo,
            )
        ]
        for nzf in nzo.files:
            nzf.finish_import()

        yield SimpleNamespace(queue=queue, nzo=nzo, nzf=nzo.files[0])

        for attr in ("NzbQueue", "Downloader", "BPSMeter", "Assembler", "ArticleCache", "Scheduler", "PostProcessor"):
            delattr(sabnzbd, attr)

    def _articles(self, nzo):
        arts = []
        for nzf in nzo.files:
            arts.extend(nzf.articles.keys())
        return arts

    def _fail_first_article_structurally(self, nzo):
        articles = sorted(self._articles(nzo), key=lambda a: a.article)
        first = articles[0]
        first.fetcher = sabnzbd.Downloader.servers[0]

        response = mock.MagicMock()
        response.status_code = 222
        response.sink_failed = False

        with mock.patch("sabnzbd.decoder.decode_yenc", side_effect=YEncEncryptionStructuralError("MISSING_PASSWORD")):
            decode(first, response)
        return first

    def test_structural_error_aborts_whole_job(self, job_env):
        """After a structural error on one article, the job leaves the queue and
        no further articles of the job can be scheduled."""
        nzo, queue = job_env.nzo, job_env.queue

        first = self._fail_first_article_structurally(nzo)

        # fail_to_history removed the job from the queue without data cleanup
        assert nzo.removed_from_queue
        assert nzo.fail_msg
        assert nzo.status == Status.FAILED

        # No further articles obtainable for this job (queue-level scheduler path)
        server = sabnzbd.Downloader.servers[0]
        server.article_queue.clear()
        queue.get_articles(server, sabnzbd.Downloader.servers, fetch_limit=10)
        assert not server.article_queue, "remaining articles must not be scheduled after job abort"

        # The failed article was never registered as on-disk or cached
        assert not first.on_disk
        assert nzo.bad_articles == 0, "structural path never searches a new server"

    def test_second_inflight_structural_error_does_not_reprocess_job(self, job_env):
        """Two in-flight articles of one job both hitting a structural error must
        produce a single PostProcessor.process run: the job leaves the queue on the
        first failure and later structural errors on in-flight articles must be
        ignored (job already failed to history)."""
        nzo = job_env.nzo

        articles = sorted(self._articles(nzo), key=lambda a: a.article)
        first, second = articles[0], articles[1]
        for article in (first, second):
            article.fetcher = sabnzbd.Downloader.servers[0]

        response = mock.MagicMock()
        response.status_code = 222
        response.sink_failed = False

        with mock.patch("sabnzbd.decoder.decode_yenc", side_effect=YEncEncryptionStructuralError("MISSING_PASSWORD")):
            # Both articles were in flight when the first structural error aborted the job
            decode(first, response)
            decode(second, response)

        # Only the first failure runs the post-processing lifecycle; the second
        # structural error on the already-removed job must be a no-op
        assert sabnzbd.PostProcessor.process.call_count == 1
        assert nzo.removed_from_queue, "job stays removed"
        assert nzo.status == Status.FAILED
        assert not second.on_disk, "second failing article must not be registered"

    def test_inflight_success_cannot_revive_failed_job(self, job_env):
        """An article that completes after the structural abort must not send the
        job back to the queue or to post-processing as a success."""
        nzo, queue = job_env.nzo, job_env.queue

        self._fail_first_article_structurally(nzo)
        assert nzo.removed_from_queue

        # A later article arrives successfully (in-flight completion)
        for article in sorted(self._articles(nzo), key=lambda a: a.article):
            article.decoded = False
            article.on_disk = True
            queue.register_article(article, success=True)

        # register_article discarded the articles for the removed/failed job;
        # the only PostProcessor.process call is the one from fail_to_history itself
        assert sabnzbd.PostProcessor.process.call_count == 1
        assert nzo.removed_from_queue, "job stays removed; success cannot revive it"

    def test_argon2_hashing_error_fails_job_without_server_failover(self, job_env):
        """A local Argon2id derivation failure (HashingError) must be re-typed as
        a structural error: the job fails to history and search_new_server is
        never called, because no other provider can cure a local KDF failure."""
        nzo = job_env.nzo
        nzo.password = "conformance-fixture-test-password"
        article = sorted(self._articles(nzo), key=lambda a: a.article)[0]
        article.fetcher = sabnzbd.Downloader.servers[0]

        # Minimal encrypted BODY response reaching restore_control_lines ->
        # get_master_key: Line 1 bootstrap (16-byte salt, segment index 1)
        # plus the minimum further lines before the master key is derived.
        bootstrap = b"\x01" * 16 + (1).to_bytes(4, "big")
        response = mock.MagicMock()
        response.status_code = 222
        response.sink_failed = False
        response.format = sabctools.EncodingFormat.YENC
        response.bytes_decoded = 0
        response.lines = [bootstrap + b"xy", b"y", b"z"]

        with (
            mock.patch("argon2.low_level.hash_secret_raw", side_effect=HashingError("mocked argon2 failure")),
            mock.patch("sabnzbd.decoder.search_new_server") as search_new_server,
        ):
            decode(article, response)

        search_new_server.assert_not_called()
        assert nzo.removed_from_queue
        assert nzo.fail_msg == "Structural yEnc-encryption failure: missing or invalid metadata"
        assert nzo.status == Status.FAILED
        sabnzbd.PostProcessor.process.assert_called_once_with(nzo)
        assert not article.on_disk
        assert nzo.bad_articles == 0

    def test_get_master_key_reraises_hashing_error_as_structural(self):
        """Unit pin for the re-typing in DecryptionAdapter.get_master_key."""
        adapter = DecryptionAdapter(password="conformance-fixture-test-password")
        with mock.patch("argon2.low_level.hash_secret_raw", side_effect=HashingError("mocked argon2 failure")):
            with pytest.raises(YEncEncryptionStructuralError) as excinfo:
                adapter.get_master_key(b"\x01" * 16)
        assert isinstance(excinfo.value.__cause__, HashingError)

    def test_structural_error_ends_as_failed_history_with_fail_msg(self, job_env):
        """fail_to_history must hand the job to the post-processor with the
        structural fail_msg intact, so it lands as FAILED in history."""
        nzo = job_env.nzo

        self._fail_first_article_structurally(nzo)

        sabnzbd.PostProcessor.process.assert_called_once_with(nzo)
        assert nzo.fail_msg == "Structural yEnc-encryption failure: missing or invalid metadata"
