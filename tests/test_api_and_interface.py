#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
import cherrypy
import pytest

from tests.testhelper import *

import sabnzbd.api as api
import sabnzbd.interface as interface


class TestApiInternals:
    """Test internal functions of the API"""

    def test_empty(self):
        with pytest.raises(TypeError):
            api.api_handler(None)
        with pytest.raises(AttributeError):
            api.api_handler("")

    def test_mode_invalid(self):
        expected_error = "error: not implemented"
        assert api.api_handler({"mode": "invalid"}).strip() == expected_error
        with pytest.raises(IndexError):
            assert api.api_handler({"mode": []}).strip() == expected_error
            assert api.api_handler({"mode": ""}).strip() == expected_error
            assert api.api_handler({"mode": None}).strip() == expected_error

    def test_version(self):
        assert api.api_handler({"mode": "version"}).strip() == sabnzbd.__version__

    def test_auth(self):
        assert api.api_handler({"mode": "auth"}).strip() == "apikey"


def set_remote_host_or_ip(hostname: str = "localhost", remote_ip: str = "127.0.0.1"):
    """Change CherryPy's "Host" and "remote.ip"-values"""
    cherrypy.request.headers["Host"] = hostname
    cherrypy.request.remote.ip = remote_ip


class TestSecuredExpose:
    """Test the security handling"""

    main_page = sabnzbd.interface.MainPage()

    def check_full_access(self, redirect_match: str = r".*wizard.*"):
        """Basic test if we have full access to API and interface"""
        assert sabnzbd.__version__ in self.main_page.api(mode="version")
        # Passed authentication
        assert api._MSG_NOT_IMPLEMENTED in self.main_page.api(apikey=sabnzbd.cfg.api_key())
        # Raises a redirect to the wizard
        with pytest.raises(cherrypy._cperror.HTTPRedirect, match=redirect_match):
            self.main_page.index()

    def test_basic(self):
        set_remote_host_or_ip()
        self.check_full_access()

    def test_api_no_or_wrong_api_key(self):
        set_remote_host_or_ip()
        # Get blocked
        assert interface._MSG_APIKEY_REQUIRED in self.main_page.api()
        assert interface._MSG_APIKEY_REQUIRED in self.main_page.api(mode="queue")
        # Allowed to access "auth" and "version" without key
        assert "apikey" in self.main_page.api(mode="auth")
        assert sabnzbd.__version__ in self.main_page.api(mode="version")
        # Blocked when you do something wrong
        assert interface._MSG_APIKEY_INCORRECT in self.main_page.api(mode="queue", apikey="wrong")

    def test_api_nzb_key(self):
        set_remote_host_or_ip()
        # It should only access the nzb-functions, nothing else
        assert api._MSG_NO_VALUE in self.main_page.api(mode="addfile", apikey=sabnzbd.cfg.nzb_key())
        assert interface._MSG_APIKEY_INCORRECT in self.main_page.api(mode="set_config", apikey=sabnzbd.cfg.nzb_key())
        assert interface._MSG_APIKEY_INCORRECT in self.main_page.shutdown(apikey=sabnzbd.cfg.nzb_key())

    def test_check_hostname_basic(self):
        # Block bad host
        set_remote_host_or_ip(hostname="not_me")
        assert interface._MSG_ACCESS_DENIED_HOSTNAME in self.main_page.api()
        assert interface._MSG_ACCESS_DENIED_HOSTNAME in self.main_page.index()
        # Block empty value
        set_remote_host_or_ip(hostname="")
        assert interface._MSG_ACCESS_DENIED_HOSTNAME in self.main_page.api()
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

    @set_config({"username": "foo", "password": "bar"})
    def test_check_hostname_not_user_password(self):
        set_remote_host_or_ip(hostname="not_me")
        self.check_full_access(redirect_match=r".*login.*")

    @set_config({"host_whitelist": "test.com, not_evil"})
    def test_check_hostname_whitelist(self):
        set_remote_host_or_ip(hostname="test.com")
        self.check_full_access()
        set_remote_host_or_ip(hostname="not_evil")
        self.check_full_access()

    def test_dual_stack(self):
        set_remote_host_or_ip(remote_ip="::ffff:192.168.0.10")
        self.check_full_access()

    @set_config({"local_ranges": "132.10."})
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
            assert api._MSG_NO_VALUE in self.main_page.api(mode="addfile", apikey=sabnzbd.cfg.nzb_key())
            assert api._MSG_NO_VALUE in self.main_page.api(mode="addfile", apikey=sabnzbd.cfg.api_key())

        # Level 2: basic API
        if inet_exposure >= 2:
            assert api._MSG_NO_VALUE in self.main_page.api(mode="get_files", apikey=sabnzbd.cfg.api_key())
            assert api._MSG_NO_VALUE in self.main_page.api(mode="change_script", apikey=sabnzbd.cfg.api_key())
            # Sub-function
            assert "status" in self.main_page.api(mode="queue", name="resume", apikey=sabnzbd.cfg.api_key())

        # Level 3: full API
        if inet_exposure >= 3:
            assert "misc" in self.main_page.api(mode="get_config", apikey=sabnzbd.cfg.api_key())
            # Sub-function
            assert "The hostname is not set" in self.main_page.api(
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
            assert interface._MSG_ACCESS_DENIED in self.main_page.api(mode="get_config", apikey=sabnzbd.cfg.api_key())
            assert interface._MSG_ACCESS_DENIED in self.main_page.api(
                mode="config", name="set_nzbkey", apikey=sabnzbd.cfg.api_key()
            )
        # Level 1: nzb
        if inet_exposure <= 1:
            assert interface._MSG_ACCESS_DENIED in self.main_page.api(mode="get_scripts", apikey=sabnzbd.cfg.api_key())
            assert interface._MSG_ACCESS_DENIED in self.main_page.api(
                mode="queue", name="resume", apikey=sabnzbd.cfg.api_key()
            )

        # Level 0: nothing, already checked above, but just to be sure
        if inet_exposure <= 0:
            assert interface._MSG_ACCESS_DENIED in self.main_page.api(mode="addfile", apikey=sabnzbd.cfg.api_key())
            # Check with or without API-key
            assert interface._MSG_ACCESS_DENIED in self.main_page.api(mode="auth", apikey=sabnzbd.cfg.api_key())
            assert interface._MSG_ACCESS_DENIED in self.main_page.api(mode="auth")

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

    @set_config({"inet_exposure": 5, "username": "foo", "password": "bar"})
    def test_inet_exposure_login_for_external(self):
        # Local user: full access
        set_remote_host_or_ip()
        self.check_full_access()

        # Remote user: redirect to login
        set_remote_host_or_ip(hostname="100.100.100.100", remote_ip="11.11.11.11")
        self.check_full_access(redirect_match=r".*login.*")

    @set_config({"api_warnings": False})
    def test_no_text_warnings(self):
        assert self.main_page.index() is None
        assert cherrypy.response.status == 403
        assert self.main_page.api(mode="queue") is None
        assert cherrypy.response.status == 403
        set_remote_host_or_ip(hostname="not_me")
        assert self.main_page.api() is None
        assert cherrypy.response.status == 403


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
