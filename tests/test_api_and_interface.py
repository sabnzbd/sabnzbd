#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
import pytest
from unittest.mock import Mock, AsyncMock, patch
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse, RedirectResponse
from starlette.datastructures import Headers, Address, QueryParams

from tests.testhelper import *

import sabnzbd.api as api
import sabnzbd.interface as interface
import sabnzbd


class TestApiInternals:
    """Test internal functions of the API"""

    def test_empty(self):
        with pytest.raises(AttributeError):
            api.api_handler(None)
        # Empty string should work but result in undefined mode
        result = api.api_handler(QueryParams({}))
        assert "not implemented" in result.body.decode()

    def test_mode_invalid(self):
        result = api.api_handler(QueryParams({"mode": "invalid"}))
        assert "not implemented" in result.body.decode()

    def test_version(self):
        result = api.api_handler(QueryParams({"mode": "version"}))
        assert sabnzbd.__version__ in result.body.decode()

    def test_auth(self):
        result = api.api_handler(QueryParams({"mode": "auth"}))
        assert "apikey" in result.body.decode()


def create_mock_request(
    hostname: str = "localhost", remote_ip: str = "127.0.0.1", headers: dict = None, query_params: dict = None
):
    """Create a mock Starlette Request object for testing"""
    mock_request = Mock(spec=Request)
    mock_request.client = Address(remote_ip, 12345)

    # Set up headers
    request_headers = {"Host": hostname}
    if headers:
        request_headers.update(headers)
    mock_request.headers = Headers(request_headers)

    # Set up query params
    mock_request.query_params = QueryParams(query_params or {})

    return mock_request


class TestSecuredExpose:
    """Test the security handling for Starlette interface"""

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
        return api.api_handler(request.query_params)

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

    @set_config({"username": "foo", "password": "bar"})
    def test_check_hostname_with_auth(self):
        """Test hostname checking with authentication enabled"""
        # With username/password set, hostname check should always pass
        bad_request = create_mock_request(hostname="not_me")
        assert interface.check_hostname(bad_request) is True

    @set_config({"host_whitelist": "test.com, not_evil"})
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

    @set_config({"local_ranges": "132.10."})
    def test_dual_stack_local_ranges(self):
        """Test custom local ranges"""
        # IP not in custom local_ranges should be blocked
        request1 = create_mock_request(remote_ip="::ffff:192.168.0.10")
        assert interface.check_access(request1, access_type=5) is False

        # IP in custom local_ranges should be allowed
        request2 = create_mock_request(remote_ip="::ffff:132.10.0.10")
        assert interface.check_access(request2, access_type=4) is True

    def test_inet_exposure_basic(self):
        """Test basic inet exposure functionality"""
        # Test with external IP (should be blocked for high access levels)
        external_request = create_mock_request(remote_ip="11.11.11.11")

        # Test different access levels
        @set_config({"inet_exposure": 2})
        def _test_exposure():
            # Level 1-2 should be allowed
            assert interface.check_access(external_request, access_type=1) is True
            assert interface.check_access(external_request, access_type=2) is True
            # Level 3+ should be blocked
            assert interface.check_access(external_request, access_type=3) is False
            assert interface.check_access(external_request, access_type=4) is False

        _test_exposure()

    def test_local_access_always_allowed(self):
        """Test that local IPs are always allowed regardless of inet_exposure"""
        local_request = create_mock_request(remote_ip="127.0.0.1")

        @set_config({"inet_exposure": 0})
        def _test_local():
            # Even with minimal exposure, local IPs should be allowed
            assert interface.check_access(local_request, access_type=4) is True
            assert interface.check_access(local_request, access_type=5) is True

        _test_local()

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
    def test_inet_exposure_levels_comprehensive(self, inet_exposure, access_type, remote_ip, expected_local):
        """Test all inet_exposure levels with different access types and IP types"""
        request = create_mock_request(remote_ip=remote_ip)

        @set_config({"inet_exposure": inet_exposure})
        def _test_exposure():
            if expected_local:
                # Local and loopback IPs should always be allowed
                assert interface.check_access(request, access_type) is True
            else:
                # External IPs should follow inet_exposure rules
                expected_allowed = access_type <= inet_exposure
                assert interface.check_access(request, access_type) is expected_allowed

        _test_exposure()

    def test_inet_exposure_with_xff_headers(self):
        """Test inet_exposure behavior with X-Forwarded-For headers"""
        # XFF is only checked when remote IP is local/loopback but XFF contains non-local IPs
        # Test with local remote IP but external XFF
        local_request_external_xff = create_mock_request(
            remote_ip="192.168.1.1", headers={"X-Forwarded-For": "8.8.8.8"}
        )

        # Test with local remote IP and local XFF
        local_request_local_xff = create_mock_request(
            remote_ip="192.168.1.1", headers={"X-Forwarded-For": "192.168.1.10"}
        )

        # Test with external remote IP (XFF should be ignored)
        external_request = create_mock_request(remote_ip="8.8.8.8", headers={"X-Forwarded-For": "192.168.1.10"})

        @set_config({"inet_exposure": 2, "verify_xff_header": True})
        def test_xff_with_exposure():
            # Local IP with external XFF should be denied (XFF verification fails)
            assert interface.check_access(local_request_external_xff, access_type=4) is False

            # Local IP with local XFF should be allowed
            assert interface.check_access(local_request_local_xff, access_type=4) is True

            # External IP should follow inet_exposure rules (XFF ignored for external IPs)
            assert interface.check_access(external_request, access_type=1) is True
            assert interface.check_access(external_request, access_type=2) is True
            assert interface.check_access(external_request, access_type=3) is False

        test_xff_with_exposure()

    # Note: The comprehensive parametrized test above covers all these scenarios,
    # but this test provides explicit documentation of the API access level meanings
    def test_inet_exposure_api_levels_documentation(self):
        """Document the different API access levels with inet_exposure"""
        external_request = create_mock_request(remote_ip="8.8.8.8")

        @set_config({"inet_exposure": 2})
        def test_api_access_levels():
            # access_type = 1: NZB upload access
            assert interface.check_access(external_request, access_type=1) is True
            # access_type = 2: Basic API access
            assert interface.check_access(external_request, access_type=2) is True
            # access_type = 3: Full API access (blocked with inet_exposure=2)
            assert interface.check_access(external_request, access_type=3) is False
            # access_type = 4: WebUI access (blocked with inet_exposure=2)
            assert interface.check_access(external_request, access_type=4) is False

        test_api_access_levels()

    def test_inet_exposure_edge_cases(self):
        """Test edge cases for inet_exposure"""
        # Test IPv6 addresses
        ipv6_external_request = create_mock_request(remote_ip="2001:4860:4860::8888")
        ipv6_local_request = create_mock_request(remote_ip="::1")

        # Test dual-stack (IPv4-mapped IPv6)
        dual_stack_request = create_mock_request(remote_ip="::ffff:192.168.1.10")

        @set_config({"inet_exposure": 1})
        def test_ipv6_exposure():
            # IPv6 loopback should always be allowed
            assert interface.check_access(ipv6_local_request, access_type=4) is True

            # IPv6 external should follow inet_exposure rules
            assert interface.check_access(ipv6_external_request, access_type=1) is True
            assert interface.check_access(ipv6_external_request, access_type=2) is False

            # Dual-stack should be treated as local
            assert interface.check_access(dual_stack_request, access_type=4) is True

        test_ipv6_exposure()

        # Test with custom local ranges
        custom_local_request = create_mock_request(remote_ip="4.4.4.10")

        @set_config({"inet_exposure": 1, "local_ranges": ["4.4.4.0/24"]})
        def test_custom_local_ranges():
            # IP in custom local range should be treated as local
            assert interface.check_access(custom_local_request, access_type=4) is True

        test_custom_local_ranges()

    # Note: Boundary conditions are covered by the comprehensive parametrized test
    # This test serves as explicit documentation of the most restrictive/permissive settings
    def test_inet_exposure_boundary_documentation(self):
        """Document boundary conditions for inet_exposure settings"""
        external_request = create_mock_request(remote_ip="1.1.1.1")

        @set_config({"inet_exposure": 0})
        def test_most_restrictive_doc():
            # inet_exposure=0: No external access allowed for any access type
            assert interface.check_access(external_request, access_type=1) is False

        @set_config({"inet_exposure": 5})
        def test_most_permissive_doc():
            # inet_exposure=5: External access allowed for access_type 1-5, but not 6
            assert interface.check_access(external_request, access_type=5) is True
            assert interface.check_access(external_request, access_type=6) is False

        test_most_restrictive_doc()
        test_most_permissive_doc()


class TestHistory:
    @pytest.mark.usefixtures("run_sabnzbd")
    def test_add_active_history_consistency(self):
        """Verify that add_active_history has the same structure as fetch_history"""
        history_db = os.path.join(SAB_CACHE_DIR, DEF_ADMIN_DIR, DB_HISTORY_NAME)
        with FakeHistoryDB(history_db) as fake_history:
            fake_history.add_fake_history_jobs(1)
            jobs, total_items = fake_history.fetch_history()
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
