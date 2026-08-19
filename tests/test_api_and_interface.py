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
tests.test_api - Tests for API functions
"""

import asyncio
import os
from functools import cached_property
import pytest
from random import choice, randint
from unittest import mock
from unittest.mock import Mock, patch
from starlette.requests import Request
from starlette.responses import Response
from starlette.datastructures import Headers, Address, QueryParams, State

import sabnzbd.api as api
import sabnzbd.interface as interface
import sabnzbd
import sabnzbd.database as db
from sabnzbd.constants import DB_HISTORY_NAME, DEF_ADMIN_DIR, PP_LOOKUP, AddNzbFileResult, Status
from sabnzbd.misc import pp_to_opts
from tests.testhelper import FakeHistoryDB, SAB_CACHE_DIR
from tests.test_interface import resolve_client


def run_api_handler(kwargs) -> Response:
    """Run the (async) api_handler to completion, like the /api route does"""
    return asyncio.run(api.api_handler(kwargs))


class TestApiInternals:
    """Test internal functions of the API"""

    def test_empty(self):
        with pytest.raises(AttributeError):
            run_api_handler(None)
        # Empty string should work but result in undefined mode
        result = run_api_handler(QueryParams({}))
        assert "not implemented" in result.body.decode()

    def test_mode_invalid(self):
        result = run_api_handler(QueryParams({"mode": "invalid"}))
        assert "not implemented" in result.body.decode()

    def test_version(self):
        result = run_api_handler(QueryParams({"mode": "version"}))
        assert sabnzbd.__version__ in result.body.decode()

    def test_auth(self):
        result = run_api_handler(QueryParams({"mode": "auth"}))
        assert "apikey" in result.body.decode()

    @pytest.mark.parametrize(
        "line,ip",
        [
            (
                b"2026-05-19 18:35:18,271::INFO::[notifier:169] Sending notification: Warning - Unsuccessful login attempt from ::ffff:172.18.0.1 [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0] (type=warning, job_cat=None)\n",
                b"::ffff:172.18.0.1",
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 172.18.0.1 [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"172.18.0.1",
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 2001:4860::1 [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"<REMOVED>",
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 8.8.8.8 [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"<REMOVED>",
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 127.0.0.1 [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"127.0.0.1",
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from fe80::1 [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"fe80::1",
            ),
        ],
        ids=[
            "ipv6-local",
            "ipv4-local",
            "ipv6-removed",
            "ipv4-removed",
            "ipv4-loopback",
            "ipv6-linklocal",
        ],
    )
    def test_log_sanitize_remote_label(self, line, ip):
        sanitized = api.sanitize_line(line)
        assert (
            sanitized.count(
                b"%s [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]" % ip
            )
            == 1
        )

    @pytest.mark.parametrize(
        "line,ip,xff",
        [
            (
                b"2026-05-19 18:35:18,271::INFO::[notifier:169] Sending notification: Warning - Unsuccessful login attempt from ::ffff:172.18.0.1 (X-Forwarded-For: 8.8.8.8, 1.1.1.1) [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0] (type=warning, job_cat=None)\n",
                b"::ffff:172.18.0.1",
                [b"<REMOVED>", b"<REMOVED>"],
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 172.18.0.1 (X-Forwarded-For: 8.8.8.8, 1.1.1.1) [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"172.18.0.1",
                [b"<REMOVED>", b"<REMOVED>"],
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 2001:4860::1 (X-Forwarded-For: 192.168.0.50, 8.8.8.8) [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"<REMOVED>",
                [b"192.168.0.50", b"<REMOVED>"],
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 8.8.8.8 (X-Forwarded-For: 1.1.1.1) [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"<REMOVED>",
                [b"<REMOVED>"],
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from 127.0.0.1 (X-Forwarded-For: 127.1.2.3) [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"127.0.0.1",
                [b"127.1.2.3"],
            ),
            (
                b"2026-05-19 18:35:18,271::WARNING::[interface:689] Unsuccessful login attempt from fe80::1 (X-Forwarded-For: fe80::2) [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]\n",
                b"fe80::1",
                [b"fe80::2"],
            ),
        ],
        ids=[
            "ipv6-local-removed-removed",
            "ipv4-local-removed-removed",
            "ipv6-removed-local-removed",
            "ipv4-removed-removed",
            "ipv4-loopback-loopback",
            "ipv6-linklocal-linklocal",
        ],
    )
    def test_log_sanitize_remote_label_xff(self, line, ip, xff):
        sanitized = api.sanitize_line(line)
        assert (
            sanitized.count(
                b"%s (X-Forwarded-For: %s) [Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0]"
                % (ip, b", ".join(xff))
            )
            == 1
        )


def create_mock_request(
    hostname: str = "localhost",
    remote_ip: str = "127.0.0.1",
    headers: dict | None = None,
    query_params: dict | None = None,
):
    """Create a mock Starlette Request object for testing"""
    mock_request = Mock(spec=Request)
    mock_request.client = Address(remote_ip, 12345)

    # Set up headers
    request_headers = {"Host": hostname}
    if headers:
        request_headers.update(headers)
    mock_request.headers = Headers(request_headers)

    # Set up query params, both on the Request itself and on request.state.params,
    # where secured_expose stores the merged GET/POST params (see request_params)
    mock_request.query_params = QueryParams(query_params or {})
    mock_request.state = State()
    mock_request.state.params = mock_request.query_params

    return mock_request


def run_get_request_params(method, query_string="", body=b"", content_type=None, merge_query=False):
    """Drive interface.get_request_params with a real Starlette Request"""
    headers = [(b"content-type", content_type.encode())] if content_type else []
    scope = {
        "type": "http",
        "method": method,
        "query_string": query_string.encode(),
        "headers": headers,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive)
    return asyncio.run(interface.get_request_params(request, merge_query=merge_query))


FORM = "application/x-www-form-urlencoded"


class TestGetRequestParams:
    """The /api route must expose GET and POST arguments identically to CherryPy"""

    def test_api_duplicate_scalar_key_first_wins(self):
        """A repeated routing/scalar key resolves to its first value, as CherryPy did"""
        params = run_get_request_params("GET", "mode=queue&mode=version", merge_query=True)
        assert params.get("mode") == "queue"

    def test_api_get_and_post_resolve_duplicates_identically(self):
        """GET and a form POST must dispatch a duplicated key the same way"""
        get_params = run_get_request_params("GET", "mode=queue&mode=version", merge_query=True)
        post_params = run_get_request_params(
            "POST", "mode=queue&mode=version", body=b"nzbname=x", content_type=FORM, merge_query=True
        )
        assert get_params.get("mode") == post_params.get("mode") == "queue"

    def test_api_body_wins_over_query(self):
        """On a form POST the body value replaces the query value for the same key"""
        params = run_get_request_params(
            "POST", "mode=version&apikey=K", body=b"mode=addfile", content_type=FORM, merge_query=True
        )
        assert params.get("mode") == "addfile"
        assert params.get("apikey") == "K"

    def test_api_query_only_multi_value_key_preserved(self):
        """A genuinely multi-valued key supplied only in the query keeps every value"""
        params = run_get_request_params(
            "POST", "keyword=a&keyword=b", body=b"section=misc", content_type=FORM, merge_query=True
        )
        assert params.getlist("keyword") == ["a", "b"]

    def test_api_bodyless_post_uses_query(self):
        """An /api POST without a form body falls back to the query string"""
        params = run_get_request_params("POST", "mode=queue&apikey=K", merge_query=True)
        assert params.get("mode") == "queue"
        assert params.get("apikey") == "K"

    def test_page_post_ignores_query_string(self):
        """A page POST (no merge) reads the form body only; the query is not merged in"""
        params = run_get_request_params("POST", "smuggled=1", body=b"field=value", content_type=FORM, merge_query=False)
        assert params.get("field") == "value"
        assert params.get("smuggled") is None


class TestOrphanPathTraversal:
    """Orphaned-job handlers must not allow deleting/adding paths outside the download folder"""

    @pytest.fixture
    def download_dir(self, tmp_path):
        """Point cfg.download_dir at a temporary folder for the duration of a test"""
        ddir = tmp_path / "incomplete"
        ddir.mkdir()
        with mock.patch.object(api.cfg.download_dir, "get_path", return_value=str(ddir)):
            yield str(ddir)

    # Values that must be silently rejected: absolute paths and '..' traversal escape the
    # download folder, an empty value resolves to the download folder itself
    traversal_values = [
        "/etc/passwd",  # absolute path overrides the join base
        "../../../etc/passwd",  # traversal with ..
        "..",  # the parent of the download folder
        "sub/../../escape",  # traversal hidden behind a valid component
        "",  # resolves to the download folder itself
    ]

    @pytest.mark.parametrize("value", traversal_values)
    def test_delete_orphan_does_not_remove_outside(self, download_dir, value):
        with mock.patch.object(api, "remove_all") as remove_all_mock:
            api._api_delete_orphan(value, {})
            remove_all_mock.assert_not_called()

    def test_delete_orphan_removes_valid_child(self, download_dir):
        with mock.patch.object(api, "remove_all") as remove_all_mock:
            api._api_delete_orphan("myjob", {})
            remove_all_mock.assert_called_once_with(os.path.join(download_dir, "myjob"), recursive=True)

    @pytest.mark.parametrize("value", traversal_values)
    def test_add_orphan_does_not_repair_outside(self, download_dir, value):
        with mock.patch.object(sabnzbd, "NzbQueue", create=True) as nzbqueue_mock:
            api._api_add_orphan(value, {})
            nzbqueue_mock.repair_job.assert_not_called()

    def test_add_orphan_repairs_valid_child(self, download_dir):
        with mock.patch.object(sabnzbd, "NzbQueue", create=True) as nzbqueue_mock:
            api._api_add_orphan("myjob", {})
            nzbqueue_mock.repair_job.assert_called_once_with(os.path.join(download_dir, "myjob"), None, None)


class TestRetryJobFuturetype:
    """A futuretype job never got past fetching its URL, so there is nothing on disk to
    repair: retry_job() has to re-fetch the URL instead of going through repair_job()"""

    @pytest.fixture
    def history_db(self, tmp_path, monkeypatch):
        """A real history database, also served by the pool that retry_job() borrows from"""
        monkeypatch.setattr(db.HistoryDB, "db_path", str(tmp_path / DB_HISTORY_NAME))
        monkeypatch.setattr(db.HistoryDB, "startup_done", False)
        pool = db.HistoryDBPool(max_connections=1)
        monkeypatch.setattr(sabnzbd, "db_pool", pool)
        fake_history_db = FakeHistoryDB(db.HistoryDB.db_path)
        yield fake_history_db
        fake_history_db.close()
        pool.close()

    @staticmethod
    def _add_futuretype_job(history_db) -> tuple[str, tuple]:
        """Add a failed URL-fetch to the history, return its nzo_id and stored settings"""
        nzo_id = history_db.add_fake_history_job(
            "Ubuntu.Linux.ISO-Usenet", status=Status.FAILED, category="catA", futuretype=True
        )
        stored_settings = history_db.get_other(nzo_id)
        assert stored_settings[0] == "future"
        return nzo_id, stored_settings

    def test_futuretype_job_url_is_refetched(self, history_db):
        nzo_id, (_, url, pp, script, cat) = self._add_futuretype_job(history_db)

        with (
            mock.patch.object(
                sabnzbd.urlgrabber, "add_url", return_value=(AddNzbFileResult.OK, ["new_nzo_id"])
            ) as add_url_mock,
            mock.patch.object(sabnzbd, "NzbQueue", create=True) as nzbqueue_mock,
        ):
            assert api.retry_job(nzo_id) == "new_nzo_id"

        # Retried with the settings stored in the history, but without the duplicate check:
        # the job that is being retried is still in the history at that point
        add_url_mock.assert_called_once_with(url, pp, script, cat, dup_check=False)
        # There is no incomplete folder to repair
        nzbqueue_mock.repair_job.assert_not_called()
        # The old entry is gone, the re-added job will create its own
        assert history_db.get_other(nzo_id) == ("", "", "", "", "")

    @pytest.mark.parametrize(
        "add_url_result",
        [
            (AddNzbFileResult.NO_FILES_FOUND, []),
            (AddNzbFileResult.ERROR, []),
            (AddNzbFileResult.RETRY, []),
            (AddNzbFileResult.PREQUEUE_REJECTED, []),
        ],
    )
    def test_futuretype_job_kept_in_history_when_refetch_fails(self, history_db, add_url_result):
        """Only a job that was actually re-added may leave the history, otherwise the
        failure disappears without anything taking its place"""
        nzo_id, stored_settings = self._add_futuretype_job(history_db)

        with mock.patch.object(sabnzbd.urlgrabber, "add_url", return_value=add_url_result):
            assert api.retry_job(nzo_id) is None

        assert history_db.get_other(nzo_id) == stored_settings


class TestSecuredExpose:
    """Test the security handling for Starlette interface"""

    @cached_property
    def main_page(self):
        return sabnzbd.interface.MainPage()

    def setup_method(self):
        """Set up mocks for SABnzbd components before each test"""
        # Instead of mocking every individual component, let's mock the main API functions
        # that are used in testing to return simple, predictable responses

        # Mock build_queue to return a simple queue response
        mock_queue_response = {
            "version": "test-version",
            "paused": False,
            "slots": [],
            "noofslots": 0,
            "limit": 0,
            "start": 0,
            "finish": 0,
            "cache_art": "0",
            "cache_size": "0 B",
            "kbpersec": "0.00",
            "speed": "0 B/s",
            "mbleft": "0.00",
            "mb": "0.00",
            "sizeleft": "0 B",
            "size": "0 B",
            "timeleft": "0:00:00",
            "eta": "unknown",
        }

        # Apply patches for main API functions
        self.build_queue_patch = patch("sabnzbd.api.build_queue", return_value=mock_queue_response)

        # Start all patches
        self.build_queue_patch.start()

    def teardown_method(self):
        """Clean up mocks after each test"""
        self.build_queue_patch.stop()

    async def call_api_endpoint(self, request: Request):
        """Call the API endpoint directly"""
        return await interface.api(request)

    async def call_main_endpoint(self, request: Request):
        """Call the main endpoint directly"""
        return await interface.main_index(request)

    def api_wrapper(self, **kwargs):
        """Wrapper to test API calls with query parameters"""
        request = create_mock_request(query_params=kwargs)
        return run_api_handler(request.query_params)

    def check_full_access(self, hostname="localhost", remote_ip="127.0.0.1"):
        """Basic test if we have full access to API and interface"""
        # Test API access
        result = self.api_wrapper(mode="version")
        assert sabnzbd.__version__ in result.body.decode()
        # Test API with correct key
        result = self.api_wrapper(mode="queue", apikey=sabnzbd.cfg.api_key())
        assert "queue" in result.body.decode()  # Should return queue data

    def test_basic(self):
        """Test basic API access functionality"""
        self.check_full_access()

    def test_api_no_or_wrong_api_key(self):
        """Test API key validation through direct API handler calls"""
        # Allowed to access "auth" and "version" without key
        result = self.api_wrapper(mode="auth")
        assert "apikey" in result.body.decode()
        result = self.api_wrapper(mode="version")
        assert sabnzbd.__version__ in result.body.decode()

        # Other modes should work with correct API key
        result = self.api_wrapper(mode="queue", apikey=sabnzbd.cfg.api_key())
        assert "queue" in result.body.decode()

    def test_api_nzb_key(self):
        """Test NZB key functionality"""
        # NZB key should work for addfile (level 1 access)
        result = self.api_wrapper(mode="addfile", apikey=sabnzbd.cfg.nzb_key())
        assert api._MSG_NO_VALUE in result.body.decode()  # No file provided, but key was accepted

    def test_check_hostname_basic(self):
        """Test hostname checking functionality"""
        # Test the check_hostname_starlette function directly

        # Block bad host
        bad_request = create_mock_request(hostname="not_me")
        assert interface.check_hostname(bad_request) is False

        # Block empty hostname
        empty_request = create_mock_request(hostname="")
        assert interface.check_hostname(empty_request) is False

        # Allow valid hostnames/IPs
        for test_hostname in (
            "100.100.100.100",
            "100.100.100.100:8080",
            "[2001:db8:3333:4444:5555:6666:7777:8888]",
            "[2001:db8:3333:4444:5555:6666:7777:8888]:8080",
            "test.local",
            "test.local:8080",
            "test.local.",
            "localhost",
        ):
            good_request = create_mock_request(hostname=test_hostname)
            assert interface.check_hostname(good_request) is True

    @pytest.mark.config({"username": "foo", "password": "bar"})
    def test_check_hostname_with_auth(self):
        """Test hostname checking with authentication enabled"""
        # With username/password set, hostname check should always pass
        bad_request = create_mock_request(hostname="not_me")
        assert interface.check_hostname(bad_request) is True

    def test_check_hostname_bare_ipv6_is_refused(self):
        """An IPv6 literal must be bracketed in a Host header (RFC 7230). A bare one is
        ambiguous, as there is no telling where the address ends and the port begins,
        so it must not be accepted as if the trailing group were a port number."""
        for bad_hostname in (
            "1234:5678::1:8080",
            "bla:bla:1234",
            "::ffff:127.0.0.1:8080",
            "2001:db8:3333:4444:5555:6666:7777:8888",
        ):
            assert interface.check_hostname(create_mock_request(hostname=bad_hostname)) is False

        # The bracketed forms of the same addresses stay allowed
        for good_hostname in ("[1234:5678::1]:8080", "[::ffff:127.0.0.1]:8080", "[1234:5678::1]"):
            assert interface.check_hostname(create_mock_request(hostname=good_hostname)) is True

    @pytest.mark.config({"host_whitelist": "test.com, not_evil"})
    def test_check_hostname_whitelist(self):
        """Test hostname whitelist functionality"""
        # Whitelisted hostnames should be allowed
        request1 = create_mock_request(hostname="test.com")
        assert interface.check_hostname(request1) is True

        request2 = create_mock_request(hostname="not_evil")
        assert interface.check_hostname(request2) is True

        # Non-whitelisted hostname should be blocked
        request3 = create_mock_request(hostname="evil.com")
        assert interface.check_hostname(request3) is False

    def test_dual_stack(self):
        """Test IPv6 dual stack functionality"""
        request = create_mock_request(remote_ip="::ffff:192.168.0.10")
        # Dual stack IPs should be treated as local
        assert interface.check_access(request, access_type=4) is True

    @pytest.mark.config({"local_ranges": "132.10."})
    def test_dual_stack_local_ranges(self):
        """Test custom local ranges"""
        # IP not in custom local_ranges should be blocked
        request1 = create_mock_request(remote_ip="::ffff:192.168.0.10")
        assert interface.check_access(request1, access_type=5) is False

        # IP in custom local_ranges should be allowed
        request2 = create_mock_request(remote_ip="::ffff:132.10.0.10")
        assert interface.check_access(request2, access_type=4) is True

    @pytest.mark.config({"inet_exposure": 2})
    def test_inet_exposure_basic(self):
        """Test basic inet exposure functionality"""
        # Test with external IP (should be blocked for high access levels)
        external_request = create_mock_request(remote_ip="11.11.11.11")

        # Level 1-2 should be allowed
        assert interface.check_access(external_request, access_type=1) is True
        assert interface.check_access(external_request, access_type=2) is True
        # Level 3+ should be blocked
        assert interface.check_access(external_request, access_type=3) is False
        assert interface.check_access(external_request, access_type=4) is False

    @pytest.mark.config({"inet_exposure": 0})
    def test_local_access_always_allowed(self):
        """Test that local IPs are always allowed regardless of inet_exposure"""
        local_request = create_mock_request(remote_ip="127.0.0.1")

        # Even with minimal exposure, local IPs should be allowed
        assert interface.check_access(local_request, access_type=4) is True
        assert interface.check_access(local_request, access_type=5) is True

    @pytest.mark.parametrize("inet_exposure", [0, 1, 2, 3, 4, 5])
    @pytest.mark.parametrize("access_type", [1, 2, 3, 4, 5, 6])
    @pytest.mark.parametrize(
        "remote_ip,expected_local",
        [
            ("192.168.1.10", True),  # Local IP
            ("127.0.0.1", True),  # Loopback IP
            ("8.8.8.8", False),  # External IP
        ],
    )
    @pytest.mark.config(lambda params: {"inet_exposure": params["inet_exposure"]})
    def test_inet_exposure_levels_comprehensive(self, inet_exposure, access_type, remote_ip, expected_local):
        """Test all inet_exposure levels with different access types and IP types"""
        request = create_mock_request(remote_ip=remote_ip)

        if expected_local:
            # Local and loopback IPs should always be allowed
            assert interface.check_access(request, access_type) is True
        else:
            # External IPs should follow inet_exposure rules
            expected_allowed = access_type <= inet_exposure
            assert interface.check_access(request, access_type) is expected_allowed

    @pytest.mark.config({"inet_exposure": 2, "verify_xff_header": True})
    def test_inet_exposure_with_xff_headers(self):
        """Test inet_exposure behavior with X-Forwarded-For headers.

        The XFF chain is resolved by uvicorn's ProxyHeadersMiddleware before
        check_access sees the request (see tests/test_interface.py), so
        request.client already holds the effective client address here.
        """
        # Local remote IP with external XFF: uvicorn rewrites the client to the
        # external XFF address, which should be denied
        local_request_external_xff = create_mock_request(
            remote_ip=resolve_client(remote_ip="192.168.1.1", xff_header="8.8.8.8").host
        )

        # Local remote IP with local XFF: effective client is the (local) XFF address
        local_request_local_xff = create_mock_request(
            remote_ip=resolve_client(remote_ip="192.168.1.1", xff_header="192.168.1.10").host
        )

        # External remote IP: untrusted peer, XFF is ignored and the client is untouched
        external_request = create_mock_request(
            remote_ip=resolve_client(remote_ip="8.8.8.8", xff_header="192.168.1.10").host
        )

        # Local IP with external XFF should be denied
        assert interface.check_access(local_request_external_xff, access_type=4) is False

        # Local IP with local XFF should be allowed
        assert interface.check_access(local_request_local_xff, access_type=4) is True

        # External IP should follow inet_exposure rules (XFF ignored for external IPs)
        assert interface.check_access(external_request, access_type=1) is True
        assert interface.check_access(external_request, access_type=2) is True
        assert interface.check_access(external_request, access_type=3) is False

    # Note: The comprehensive parametrized test above covers all these scenarios,
    # but this test provides explicit documentation of the API access level meanings
    @pytest.mark.config({"inet_exposure": 2})
    def test_inet_exposure_api_levels_documentation(self):
        """Document the different API access levels with inet_exposure"""
        external_request = create_mock_request(remote_ip="8.8.8.8")

        # access_type = 1: NZB upload access
        assert interface.check_access(external_request, access_type=1) is True
        # access_type = 2: Basic API access
        assert interface.check_access(external_request, access_type=2) is True
        # access_type = 3: Full API access (blocked with inet_exposure=2)
        assert interface.check_access(external_request, access_type=3) is False
        # access_type = 4: WebUI access (blocked with inet_exposure=2)
        assert interface.check_access(external_request, access_type=4) is False

    @pytest.mark.config({"inet_exposure": 1})
    def test_inet_exposure_ipv6(self):
        """Test IPv6 edge cases for inet_exposure"""
        # Test IPv6 addresses
        ipv6_external_request = create_mock_request(remote_ip="2001:4860:4860::8888")
        ipv6_local_request = create_mock_request(remote_ip="::1")

        # Test dual-stack (IPv4-mapped IPv6)
        dual_stack_request = create_mock_request(remote_ip="::ffff:192.168.1.10")

        # IPv6 loopback should always be allowed
        assert interface.check_access(ipv6_local_request, access_type=4) is True

        # IPv6 external should follow inet_exposure rules
        assert interface.check_access(ipv6_external_request, access_type=1) is True
        assert interface.check_access(ipv6_external_request, access_type=2) is False

        # Dual-stack should be treated as local
        assert interface.check_access(dual_stack_request, access_type=4) is True

    @pytest.mark.config({"inet_exposure": 1, "local_ranges": ["4.4.4.0/24"]})
    def test_inet_exposure_custom_local_ranges(self):
        """Test custom local ranges for inet_exposure"""
        # Test with custom local ranges
        custom_local_request = create_mock_request(remote_ip="4.4.4.10")

        # IP in custom local range should be treated as local
        assert interface.check_access(custom_local_request, access_type=4) is True

    # Note: Boundary conditions are covered by the comprehensive parametrized test
    # These tests serve as explicit documentation of the most restrictive/permissive settings
    @pytest.mark.config({"inet_exposure": 0})
    def test_inet_exposure_most_restrictive(self):
        """Document the most restrictive inet_exposure setting"""
        external_request = create_mock_request(remote_ip="1.1.1.1")
        # inet_exposure=0: No external access allowed for any access type
        assert interface.check_access(external_request, access_type=1) is False

    @pytest.mark.config({"inet_exposure": 5})
    def test_inet_exposure_most_permissive(self):
        """Document the most permissive inet_exposure setting"""
        external_request = create_mock_request(remote_ip="1.1.1.1")
        # inet_exposure=5: External access allowed for access_type 1-5, but not 6
        assert interface.check_access(external_request, access_type=5) is True
        assert interface.check_access(external_request, access_type=6) is False


class TestHistory:
    @pytest.mark.usefixtures("run_sabnzbd")
    def test_add_active_history_consistency(self):
        """Verify that add_active_history has the same structure as fetch_history"""
        history_db = os.path.join(SAB_CACHE_DIR, DEF_ADMIN_DIR, DB_HISTORY_NAME)
        with FakeHistoryDB(history_db) as fake_history:
            fake_history.add_fake_history_jobs(1)
            jobs, _total_items = fake_history.fetch_history()
            history_job = jobs[-1]

            # Add minimal attributes to create pp-job
            nzo = mock.Mock()
            nzo.final_name = "test_add_active_history"
            nzo.repair, nzo.unpack, nzo.delete = pp_to_opts(choice(list(PP_LOOKUP.keys())))
            nzo.download_path = os.path.join(os.path.dirname(db.HistoryDB.db_path), "placeholder_downpath")
            nzo.bytes_downloaded = randint(1024, 1024**4)
            nzo.unpack_info = {"unpack_info": "placeholder unpack_info line\r\n" * 3}
            api.add_active_history([nzo], jobs)

            # Make sure the job was added to the list
            pp_job = jobs[-1]
            assert pp_job["name"] == nzo.final_name
            assert pp_job["name"] != history_job["name"]

            # Compare the keys, so not the values!
            pp_keys = list(pp_job.keys())
            pp_keys.sort()
            history_keys = list(history_job.keys())
            history_keys.sort()
            assert pp_keys == history_keys

    @pytest.mark.usefixtures("run_sabnzbd")
    def test_add_active_history_duplicate(self):
        """Verify that add_active_history does not add duplicate entries"""
        history_db = os.path.join(SAB_CACHE_DIR, DEF_ADMIN_DIR, DB_HISTORY_NAME)
        with FakeHistoryDB(history_db) as fake_history:
            fake_history.add_fake_history_jobs(1)
            jobs, total_items = fake_history.fetch_history()
            history_job = jobs[-1]

            # Add minimal attributes to create pp-job
            nzo = mock.Mock()
            nzo.nzo_id = history_job["nzo_id"]
            nzo.final_name = "test_add_active_history"
            nzo.repair, nzo.unpack, nzo.delete = pp_to_opts(choice(list(PP_LOOKUP.keys())))
            nzo.download_path = os.path.join(os.path.dirname(db.HistoryDB.db_path), "placeholder_downpath")
            nzo.bytes_downloaded = randint(1024, 1024**4)
            nzo.unpack_info = {"unpack_info": "placeholder unpack_info line\r\n" * 3}
            api.add_active_history([nzo], jobs)

            # Make sure the job was not added to the list, a completed entry already exists
            assert total_items == len(jobs)
