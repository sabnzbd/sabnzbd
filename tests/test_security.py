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
tests.test_security - Testing authentication, sessions and the CSRF token
"""

import asyncio
import io
import time
from typing import Optional
import pytest
from unittest.mock import Mock, patch
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.datastructures import Headers, Address, QueryParams, State, UploadFile

import sabnzbd
import sabnzbd.cfg as cfg
import sabnzbd.security as security
from sabnzbd import interface


def mock_request(
    token: Optional[str] = None,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    csrf: Optional[str] = None,
    method: str = "GET",
    remote_ip: str = "127.0.0.1",
    remote_port: int = 12345,
    scheme: str = "http",
):
    """Mock Starlette Request"""
    if csrf is not None:
        headers = {**(headers or {}), security.CSRF_HEADER: csrf}

    request = Mock(spec=Request)
    request.method = method
    request.client = Address(remote_ip, remote_port)
    request.headers = Headers(headers or {})
    request.cookies = {security.SESSION_COOKIE_USER: token} if token else {}
    request.query_params = QueryParams("")
    request.state = State({})
    request.state.params = params or {}
    request.scope = {
        "type": "http",
        "method": method,
        "scheme": scheme,
        "headers": request.headers.raw,
        "client": (remote_ip, remote_port),
    }
    return request


def set_csrf_header(request, token: str):
    """Add the CSRF header to an already-built mock request"""
    request.headers = Headers({**dict(request.headers.items()), security.CSRF_HEADER: token})


def anonymous_csrf() -> str:
    """The CSRF token a login-bypassed request (no cookie) must echo"""
    return security.csrf_token_for(security._ANONYMOUS_CSRF_IDENTITY)


def api_request(token: Optional[str] = None, *, mode: str = "queue", with_token: bool = True, **kwargs):
    """Mock /api request; echoes the CSRF token its identity expects unless with_token is False"""
    request = mock_request(token, params={"mode": mode, "name": "", **kwargs})
    if with_token:
        set_csrf_header(request, security.csrf_token_for(security.csrf_identity(request)))
    return request


def store_session(
    store,
    token: str,
    expires_offset: int = security.SESSION_DURATION,
    created_offset: int = 0,
):
    """Add a login session for token, valid for the credentials configured now"""
    now = int(time.time())
    store.add(
        security.hash_session_token(token),
        now + created_offset,
        now + expires_offset,
        security.credential_fingerprint(),
    )


def login_post(username: str = "", password: str = "", remote_ip: str = "127.0.0.1"):
    """A POST of the login form"""
    return mock_request(params={"username": username, "password": password}, method="POST", remote_ip=remote_ip)


def locked_out(request) -> bool:
    """Whether the cooldown is running for this client"""
    return security.login_cooldown_remaining(request) > 0


def page_post(
    cookie: Optional[str] = None,
    remote_ip: str = "127.0.0.1",
    csrf: Optional[str] = None,
    csrf_field: Optional[str] = None,
):
    """A page POST carrying an optional session cookie and CSRF token"""
    params = {security.CSRF_FIELD: csrf_field} if csrf_field is not None else None
    return mock_request(cookie, params=params, csrf=csrf, method="POST", remote_ip=remote_ip)


def config_save_middleware() -> interface.SecurityMiddleware:
    """SecurityMiddleware as secured_expose attaches it to a config *_save route"""
    return interface.SecurityMiddleware(
        Mock(), check_configlock=True, check_for_login=True, check_api_key=False, access_type=4
    )


class TestHostileTokenValues:
    """Secrets arrive as text off the wire, and hmac.compare_digest refuses non-ASCII str"""

    # Headers and cookies are latin-1, so they carry any byte up to U+00FF. A form body is
    # UTF-8 and carries anything, including U+FFFD and a lone surrogate.
    WIRE_HOSTILE = ["\xff\xfe", "\xe9" * 64, "caf\xe9"]
    BODY_HOSTILE = [*WIRE_HOSTILE, "�", "\U0001f600", "\ud800"]

    def test_compare_helper_rejects_instead_of_raising(self):
        for value in self.BODY_HOSTILE:
            assert security.constant_time_equals(value, "a" * 64) is False
            assert security.constant_time_equals("a" * 64, value) is False
        # ...and still matches what it should
        assert security.constant_time_equals("a" * 64, "a" * 64) is True

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_hostile_session_cookie_is_rejected(self, session_store):
        """With the login enforced, a session cookie of hostile bytes matches no stored session"""
        for value in self.WIRE_HOSTILE:
            assert security.validate_any_session(mock_request(value)) is False

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_hostile_csrf_token_in_header_is_rejected(self, session_store):
        for value in self.WIRE_HOSTILE:
            assert security.csrf_token_matches(mock_request(csrf=value)) is False
            assert config_save_middleware().denied_response(page_post(csrf=value)) is not None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_hostile_csrf_token_in_form_field_is_rejected(self, session_store):
        for value in self.BODY_HOSTILE:
            request = mock_request(params={security.CSRF_FIELD: value})
            assert security.csrf_token_matches(request) is False
            assert config_save_middleware().denied_response(page_post(csrf_field=value)) is not None

    @staticmethod
    def _upload_part():
        """What a multipart part named apikey/csrf_token/password parses into"""
        return UploadFile(file=io.BytesIO(b"not-a-token"), filename="part.txt")

    def test_a_file_part_is_not_a_secret(self):
        """A field name sent as a multipart file gives an UploadFile, which has no .encode()"""
        assert security.constant_time_equals(self._upload_part(), "a" * 64) is False
        # Compared against nothing rather than str()-ed, so no repr can stand in for a secret
        assert security.constant_time_equals(self._upload_part(), str(self._upload_part())) is False

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_csrf_token_sent_as_a_file_part_is_refused(self, session_store):
        request = mock_request(params={security.CSRF_FIELD: self._upload_part()})
        assert security.presented_csrf_token(request) == ""
        assert security.csrf_token_matches(request) is False
        denied = page_post(csrf_field=self._upload_part())
        assert config_save_middleware().denied_response(denied) is not None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_apikey_sent_as_a_file_part_is_refused(self, session_store):
        request = mock_request(params={"mode": "queue", "name": "", "apikey": self._upload_part()})
        response = interface.check_apikey(request)
        assert response is not None and response.status_code == 403

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_hostile_credentials_are_rejected(self, session_store):
        for value in self.BODY_HOSTILE:
            assert security.constant_time_equals(value, "user") is False


class TestSessionAuth:

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_valid_session_authorizes(self, session_store):
        store_session(session_store, "good-token")
        assert security.validate_session(mock_request("good-token")) is True

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_no_cookie_rejected(self, session_store):
        assert security.validate_session(mock_request(None)) is False

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_expired_session_rejected_and_deleted(self, session_store):
        store_session(session_store, "old-token", expires_offset=-10)
        assert security.validate_session(mock_request("old-token")) is False
        # The stale row is cleaned up on rejection
        assert session_store.get(security.hash_session_token("old-token")) is None

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_credential_change_invalidates_session(self, session_store):
        store_session(session_store, "tok")
        assert security.validate_session(mock_request("tok")) is True
        # Changing the password changes the fingerprint, invalidating existing sessions
        cfg.password.set("newpass")
        assert security.validate_session(mock_request("tok")) is False

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_sliding_expiry_extends(self, session_store):
        # Store a session already past its refresh threshold so validation touches it
        store_session(session_store, "tok", expires_offset=security.SESSION_REFRESH_THRESHOLD)
        token_hash = security.hash_session_token("tok")
        before = session_store.get(token_hash)["expires"]
        assert security.validate_session(mock_request("tok")) is True
        after = session_store.get(token_hash)["expires"]
        assert after > before

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_recently_used_session_is_not_rewritten(self, session_store):
        store_session(session_store, "tok")
        token_hash = security.hash_session_token("tok")
        before = session_store.get(token_hash)["expires"]
        assert security.validate_session(mock_request("tok")) is True
        assert session_store.get(token_hash)["expires"] == before


class TestLoginRateLimiting:

    @pytest.fixture(autouse=True)
    def no_recorded_failures(self, monkeypatch):
        """Empty tracker per test, and a web dir for login_index to build a template path from"""
        monkeypatch.setattr(sabnzbd, "WEB_DIR_CONFIG", "/nonexistent", raising=False)
        security._login_attempts.clear()
        yield
        security._login_attempts.clear()

    def test_allowance_before_lockout(self):
        request = login_post()
        for _ in range(security.LOGIN_MAX_ATTEMPTS - 1):
            security.record_login_failure(request)
            assert locked_out(request) is False
        # The one that uses up the allowance
        security.record_login_failure(request)
        assert locked_out(request) is True

    def test_cooldown_expires(self):
        request = login_post()
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(request)
        assert locked_out(request) is True

        # Rewind the cooldown rather than sleeping through it
        failures, cooldown_expiry = security._login_attempts["127.0.0.1"]
        security._login_attempts["127.0.0.1"] = (failures, cooldown_expiry - security.LOGIN_LOCKOUT_TIME - 1)
        assert locked_out(request) is False

    def test_success_restores_the_allowance(self):
        request = login_post()
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(request)
        assert locked_out(request) is True
        security.clear_login_failures(request)
        assert locked_out(request) is False
        assert "127.0.0.1" not in security._login_attempts

    def test_lockout_is_per_client(self):
        attacker = login_post(remote_ip="10.11.12.13")
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(attacker)
        assert locked_out(attacker) is True
        assert locked_out(login_post(remote_ip="127.0.0.1")) is False

    def test_stale_entries_are_dropped(self):
        old = login_post(remote_ip="10.11.12.13")
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(old)
        failures, cooldown_expiry = security._login_attempts["10.11.12.13"]
        security._login_attempts["10.11.12.13"] = (failures, cooldown_expiry - security.LOGIN_LOCKOUT_TIME - 1)

        security.record_login_failure(login_post(remote_ip="127.0.0.1"))
        assert "10.11.12.13" not in security._login_attempts

        # And that address is back to a clean slate, not still one away from a lockout
        security.record_login_failure(old)
        assert security._login_attempts["10.11.12.13"][0] == 1

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_correct_credentials_are_refused_while_locked_out(self, session_store):
        """Answers 429, and must not look at the credentials while the cooldown runs"""
        request = login_post(username="user", password="pass")
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(request)

        with (
            patch("sabnzbd.interface.build_header", return_value={}),
            patch("sabnzbd.interface.template_filtered_response") as render,
            patch("sabnzbd.security.create_session") as create_session,
        ):
            asyncio.run(interface.login_index(request))

        # No session handed out, despite the credentials being exactly right
        create_session.assert_not_called()
        assert render.call_args.kwargs["status_code"] == 429
        assert "Too many" in render.call_args.kwargs["search_list"]["error"]

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_failed_login_is_counted_and_success_clears_it(self, session_store):
        """Through the handler rather than the helpers, so the wiring is covered too"""
        wrong = login_post(username="user", password="nope")
        with (
            patch("sabnzbd.interface.build_header", return_value={}),
            patch("sabnzbd.interface.template_filtered_response") as render,
        ):
            asyncio.run(interface.login_index(wrong))
        assert render.call_args.kwargs["status_code"] == 200
        assert security._login_attempts["127.0.0.1"][0] == 1

        right = login_post(username="user", password="pass")
        asyncio.run(interface.login_index(right))
        assert "127.0.0.1" not in security._login_attempts

    def test_cooldown_remaining_counts_down_and_rounds_up(self):
        request = login_post()
        assert security.login_cooldown_remaining(request) == 0
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(request)

        remaining = security.login_cooldown_remaining(request)
        # Rounded up, so it is never 0 while the client is still locked out
        assert 0 < remaining <= security.LOGIN_LOCKOUT_TIME + 1

        # Most of the cooldown served: still non-zero, and smaller than it was
        failures, cooldown_expiry = security._login_attempts["127.0.0.1"]
        security._login_attempts["127.0.0.1"] = (failures, cooldown_expiry - security.LOGIN_LOCKOUT_TIME + 2)
        assert 0 < security.login_cooldown_remaining(request) < remaining

    def test_cooldown_survives_a_wall_clock_jump(self, monkeypatch):
        request = login_post()
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(request)
        assert locked_out(request) is True

        # Jump the wall clock a year forward from where it really is; the cooldown is unmoved
        real_time = time.time
        monkeypatch.setattr(time, "time", lambda: real_time() + 3600 * 24 * 365)
        assert locked_out(request) is True

    def test_stale_entries_are_dropped_on_a_read(self):
        old = login_post(remote_ip="10.11.12.13")
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(old)
        failures, cooldown_expiry = security._login_attempts["10.11.12.13"]
        security._login_attempts["10.11.12.13"] = (failures, cooldown_expiry - security.LOGIN_LOCKOUT_TIME - 1)

        # A read on behalf of some other client is enough
        assert locked_out(login_post(remote_ip="127.0.0.1")) is False
        assert "10.11.12.13" not in security._login_attempts

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_lockout_response_says_how_long_to_wait(self, session_store):
        request = login_post(username="user", password="pass")
        for _ in range(security.LOGIN_MAX_ATTEMPTS):
            security.record_login_failure(request)

        # A real response, so the assertions below read the header the client would actually get
        with (
            patch("sabnzbd.interface.build_header", return_value={}),
            patch(
                "sabnzbd.interface.template_filtered_response",
                side_effect=lambda **kwargs: HTMLResponse("", status_code=kwargs["status_code"]),
            ),
        ):
            response = asyncio.run(interface.login_index(request))

        assert response.status_code == 429
        assert 0 < int(response.headers["Retry-After"]) <= security.LOGIN_LOCKOUT_TIME + 1


class TestSessionAbsoluteDeadline:
    """SESSION_MAX_AGE, counted from the created stamp, caps a session however active it is"""

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_session_past_its_deadline_is_rejected_and_deleted(self, session_store):
        # Idle timeout still in the future, so only the absolute deadline can refuse this
        store_session(
            session_store,
            "old-tok",
            created_offset=-(security.SESSION_MAX_AGE + 60),
            expires_offset=security.SESSION_DURATION,
        )
        assert security.validate_session(mock_request("old-tok")) is False
        assert session_store.get(security.hash_session_token("old-tok")) is None

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_session_just_inside_its_deadline_still_works(self, session_store):
        store_session(
            session_store,
            "tok",
            created_offset=-(security.SESSION_MAX_AGE - 3600),
            expires_offset=security.SESSION_REFRESH_THRESHOLD,
        )
        assert security.validate_session(mock_request("tok")) is True

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_slide_is_clamped_to_the_deadline(self, session_store):
        # Deadline half a window away, and idle-expiry close enough that the slide fires
        created_offset = -(security.SESSION_MAX_AGE - security.SESSION_DURATION // 2)
        store_session(session_store, "tok", created_offset=created_offset, expires_offset=3600)
        token_hash = security.hash_session_token("tok")
        deadline = session_store.get(token_hash)["created"] + security.SESSION_MAX_AGE

        assert security.validate_session(mock_request("tok")) is True
        expires = session_store.get(token_hash)["expires"]
        assert expires == deadline
        # ...and it really was clamped, not just left alone
        assert expires < int(time.time()) + security.SESSION_DURATION

    @pytest.mark.config({"username": "user", "password": "pass"})
    def test_pinned_session_stops_being_rewritten(self, session_store):
        # created so that the deadline is an hour away, with expires already pinned to it
        store_session(
            session_store,
            "tok",
            created_offset=-(security.SESSION_MAX_AGE - 3600),
            expires_offset=3600,
        )
        token_hash = security.hash_session_token("tok")
        session = session_store.get(token_hash)
        assert session["expires"] == session["created"] + security.SESSION_MAX_AGE

        with patch.object(sabnzbd.SessionStore, "touch") as touch:
            assert security.validate_session(mock_request("tok")) is True
        touch.assert_not_called()
        assert session_store.get(token_hash)["expires"] == session["expires"]

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_check_apikey_accepts_session_without_key(self, session_store):
        store_session(session_store, "browser-token")
        # A local browser call with a valid session and its CSRF token, but no apikey
        assert interface.check_apikey(api_request("browser-token")) is None


class TestBypassedLoginSession:
    """With the login bypassed there is no session cookie: the request is trusted for being
    local, and its CSRF token binds to a stable identity rather than to a cookie."""

    @pytest.mark.config({"username": "", "password": ""})
    def test_any_session_holds_without_cookie(self):
        assert security.validate_any_session(mock_request(None)) is True

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_denied_without_cookie_when_login_enforced(self, session_store):
        assert security.validate_any_session(mock_request(None)) is False

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 5})
    def test_waived_for_local_client_only(self, session_store):
        # inet_exposure 5 waives the login for local clients
        assert security.validate_any_session(mock_request(None)) is True
        # An external client still needs to log in
        assert security.validate_any_session(mock_request(None, remote_ip="9.8.7.6")) is False

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_check_apikey_accepts_csrf_without_key_or_cookie(self):
        assert interface.check_apikey(api_request(None)) is None

    @pytest.mark.config({"username": "", "password": "", "inet_exposure": 0})
    def test_check_apikey_rejects_without_csrf(self):
        assert interface.check_apikey(api_request(None, with_token=False)) is not None

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 5})
    def test_check_apikey_accepts_waived_local_with_csrf(self, session_store):
        assert interface.check_apikey(api_request(None)) is None


class TestCsrfIdentity:
    """The CSRF token binds to a session identity; a request without one never matches"""

    @pytest.mark.config({"username": "", "password": ""})
    def test_bypassed_login_uses_the_stable_identity(self):
        assert security.csrf_identity(mock_request(None)) == security._ANONYMOUS_CSRF_IDENTITY

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_session_cookie_is_the_identity(self):
        # The cookie value stands as the identity whether or not it names a live session
        assert security.csrf_identity(mock_request("some-token")) == "some-token"

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_no_identity_when_login_enforced_without_cookie(self):
        assert security.csrf_identity(mock_request(None)) == ""

    @pytest.mark.config({"username": "user", "password": "pass", "inet_exposure": 0})
    def test_empty_identity_never_matches(self, session_store):
        """The token for the empty identity is computable only by this instance, yet a
        request that carries no identity must still be refused (guards direct callers)."""
        request = mock_request(csrf=security.csrf_token_for(""))
        assert security.csrf_identity(request) == ""
        assert security.csrf_token_matches(request) is False
