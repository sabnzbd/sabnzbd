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

import os
from functools import cached_property
from random import choice, randint
from unittest import mock

import cherrypy
import pytest

import sabnzbd
import sabnzbd.api as api
import sabnzbd.cfg
import sabnzbd.config
import sabnzbd.database as db
import sabnzbd.interface as interface
from sabnzbd.constants import DB_HISTORY_NAME, DEF_ADMIN_DIR, PP_LOOKUP
from sabnzbd.misc import pp_to_opts
from tests.testhelper import FakeHistoryDB, SAB_CACHE_DIR


class TestApiInternals:
    """Test internal functions of the API"""

    def test_empty(self):
        with pytest.raises(TypeError):
            api.api_handler(None)
        with pytest.raises(AttributeError):
            api.api_handler("")

    def test_mode_invalid(self):
        assert "not implemented" in str(api.api_handler({"mode": "invalid"}))

    def test_version(self):
        assert sabnzbd.__version__ in str(api.api_handler({"mode": "version"}))

    def test_auth(self):
        assert "apikey" in str(api.api_handler({"mode": "auth"}))

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


def set_remote_host_or_ip(hostname: str = "localhost", remote_ip: str = "127.0.0.1"):
    """Change CherryPy's "Host" and "remote.ip"-values"""
    cherrypy.request.headers["Host"] = hostname
    cherrypy.request.remote.ip = remote_ip


class TestSecuredExpose:
    """Test the security handling"""

    @cached_property
    def main_page(self):
        return sabnzbd.interface.MainPage()

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        monkeypatch.setattr(cherrypy.request, "headers", {})
        monkeypatch.setattr(cherrypy.request.remote, "ip", "127.0.0.1")
        yield

    def api_wrapper(self, *args, **kwargs):
        """Wrapper to convert bytes to str"""
        if api_response := self.main_page.api(*args, **kwargs):
            return str(api_response)

    def check_full_access(self, redirect_match: str = r".*wizard.*"):
        """Basic test if we have full access to API and interface"""
        assert sabnzbd.__version__ in self.api_wrapper(mode="version")
        # Passed authentication
        assert api._MSG_NOT_IMPLEMENTED in self.api_wrapper(apikey=sabnzbd.cfg.api_key())
        # Raises a redirect to the wizard
        with pytest.raises(cherrypy._cperror.HTTPRedirect, match=redirect_match):
            self.main_page.index()

    def test_basic(self):
        set_remote_host_or_ip()
        self.check_full_access()

    def test_api_no_or_wrong_api_key(self):
        set_remote_host_or_ip()
        # Get blocked
        assert interface._MSG_APIKEY_REQUIRED in self.api_wrapper()
        assert interface._MSG_APIKEY_REQUIRED in self.api_wrapper(mode="queue")
        # Allowed to access "auth" and "version" without key
        assert "apikey" in self.api_wrapper(mode="auth")
        assert sabnzbd.__version__ in self.api_wrapper(mode="version")
        # Blocked when you do something wrong
        assert interface._MSG_APIKEY_INCORRECT in self.api_wrapper(mode="queue", apikey="wrong")

    def test_api_nzb_key(self):
        set_remote_host_or_ip()
        # It should only access the nzb-functions, nothing else
        assert api._MSG_NO_VALUE in self.api_wrapper(mode="addfile", apikey=sabnzbd.cfg.nzb_key())
        assert interface._MSG_APIKEY_INCORRECT in self.api_wrapper(mode="set_config", apikey=sabnzbd.cfg.nzb_key())
        assert interface._MSG_APIKEY_INCORRECT in self.main_page.shutdown(apikey=sabnzbd.cfg.nzb_key())

    def test_check_hostname_basic(self):
        # Block bad host
        set_remote_host_or_ip(hostname="not_me")
        assert interface._MSG_ACCESS_DENIED_HOSTNAME in self.api_wrapper()
        assert interface._MSG_ACCESS_DENIED_HOSTNAME in self.main_page.index()
        # Block empty value
        set_remote_host_or_ip(hostname="")
        assert interface._MSG_ACCESS_DENIED_HOSTNAME in self.api_wrapper()
        assert interface._MSG_ACCESS_DENIED_HOSTNAME in self.main_page.index()

        # Fine if ip-address
        for test_hostname in (
            "100.100.100.100",
            "100.100.100.100:8080",
            "[2001:db8:3333:4444:5555:6666:7777:8888]",
            "[2001:db8:3333:4444:5555:6666:7777:8888]:8080",
            "test.local",
            "test.local:8080",
            "test.local.",
        ):
            set_remote_host_or_ip(hostname=test_hostname)
            self.check_full_access()

    @pytest.mark.config({"username": "foo", "password": "bar"})
    def test_check_hostname_not_user_password(self):
        set_remote_host_or_ip(hostname="not_me")
        self.check_full_access(redirect_match=r".*login.*")

    @pytest.mark.config({"host_whitelist": "test.com, not_evil"})
    def test_check_hostname_whitelist(self):
        set_remote_host_or_ip(hostname="test.com")
        self.check_full_access()
        set_remote_host_or_ip(hostname="not_evil")
        self.check_full_access()

    def test_dual_stack(self):
        set_remote_host_or_ip(remote_ip="::ffff:192.168.0.10")
        self.check_full_access()

    @pytest.mark.config({"local_ranges": "132.10."})
    def test_dual_stack_local_ranges(self):
        # Without custom local_ranges this one would be allowed
        set_remote_host_or_ip(remote_ip="::ffff:192.168.0.10")
        self.check_inet_blocks(inet_exposure=0)
        # But now we only allow the custom ones
        set_remote_host_or_ip(remote_ip="::ffff:132.10.0.10")
        self.check_full_access()

    def check_inet_allows(self, inet_exposure: int):
        """Each should allow all previous ones and the current one"""
        # Level 1: nzb
        if inet_exposure >= 1:
            assert api._MSG_NO_VALUE in self.api_wrapper(mode="addfile", apikey=sabnzbd.cfg.nzb_key())
            assert api._MSG_NO_VALUE in self.api_wrapper(mode="addfile", apikey=sabnzbd.cfg.api_key())

        # Level 2: basic API
        if inet_exposure >= 2:
            assert api._MSG_NO_VALUE in self.api_wrapper(mode="get_files", apikey=sabnzbd.cfg.api_key())
            assert api._MSG_NO_VALUE in self.api_wrapper(mode="change_script", apikey=sabnzbd.cfg.api_key())
            # Sub-function
            assert "status" in self.api_wrapper(mode="queue", name="resume", apikey=sabnzbd.cfg.api_key())

        # Level 3: full API
        if inet_exposure >= 3:
            assert "misc" in self.api_wrapper(mode="get_config", apikey=sabnzbd.cfg.api_key())
            # Sub-function
            assert "The hostname is not set" in self.api_wrapper(
                mode="config", name="test_server", apikey=sabnzbd.cfg.api_key()
            )

        # Level 4: full interface
        if inet_exposure >= 4:
            self.check_full_access()

    def check_inet_blocks(self, inet_exposure: int):
        """We count from the most exposure down"""
        # Level 4: full interface, no blocking
        # Level 3: full API
        if inet_exposure <= 3:
            assert interface._MSG_ACCESS_DENIED in self.main_page.index()

        # Level 2: basic API
        if inet_exposure <= 2:
            assert interface._MSG_ACCESS_DENIED in self.api_wrapper(mode="get_config", apikey=sabnzbd.cfg.api_key())
            assert interface._MSG_ACCESS_DENIED in self.api_wrapper(
                mode="config", name="set_nzbkey", apikey=sabnzbd.cfg.api_key()
            )
        # Level 1: nzb
        if inet_exposure <= 1:
            assert interface._MSG_ACCESS_DENIED in self.api_wrapper(mode="get_scripts", apikey=sabnzbd.cfg.api_key())
            assert interface._MSG_ACCESS_DENIED in self.api_wrapper(
                mode="queue", name="resume", apikey=sabnzbd.cfg.api_key()
            )

        # Level 0: nothing, already checked above, but just to be sure
        if inet_exposure <= 0:
            assert interface._MSG_ACCESS_DENIED in self.api_wrapper(mode="addfile", apikey=sabnzbd.cfg.api_key())
            # Check with or without API-key
            assert interface._MSG_ACCESS_DENIED in self.api_wrapper(mode="auth", apikey=sabnzbd.cfg.api_key())
            assert interface._MSG_ACCESS_DENIED in self.api_wrapper(mode="auth")

    def test_inet_exposure(self):
        # Run all tests as external user
        set_remote_host_or_ip(hostname="100.100.100.100", remote_ip="11.11.11.11")

        # We don't use the wrapper, it would require creating many extra functions
        # Option 5 is special, so it also gets it's own special test
        for inet_exposure in range(6):
            sabnzbd.cfg.inet_exposure.set(inet_exposure)
            self.check_inet_allows(inet_exposure=inet_exposure)
            self.check_inet_blocks(inet_exposure=inet_exposure)

        # Reset it
        sabnzbd.cfg.inet_exposure.set(sabnzbd.cfg.inet_exposure.default)

    @pytest.mark.config({"inet_exposure": 5, "username": "foo", "password": "bar"})
    def test_inet_exposure_login_for_external(self):
        # Local user: full access
        set_remote_host_or_ip()
        self.check_full_access()

        # Remote user: redirect to login
        set_remote_host_or_ip(hostname="100.100.100.100", remote_ip="11.11.11.11")
        self.check_full_access(redirect_match=r".*login.*")

    @pytest.mark.config({"api_warnings": False})
    def test_no_text_warnings(self):
        assert self.main_page.index() is None
        assert cherrypy.response.status == 403
        assert self.api_wrapper(mode="queue") is None
        assert cherrypy.response.status == 403
        set_remote_host_or_ip(hostname="not_me")
        assert self.api_wrapper() is None
        assert cherrypy.response.status == 403


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
