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
from sabnzbd.misc import is_local_addr, xff_trusted_networks
from sabnzbd import interface

from tests.testhelper import run_async


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


def proxied_request(
    remote_ip: str,
    xff_header: Optional[str | list] = None,
    forwarded_header: Optional[str] = None,
):
    """A request that really went through ProxyTrustMiddleware, so the headers, the resolved
    client and the trust verdict all agree with each other, exactly as in a served request.

    xff_header takes a list to send X-Forwarded-For as several header lines, which is what a
    proxy that appends rather than rewrites produces, and what a dict of headers cannot say."""
    captured = {}

    async def asgi_app(scope, receive, send):
        captured.update(scope)

    raw = []
    if xff_header is not None:
        for value in xff_header if isinstance(xff_header, list) else [xff_header]:
            raw.append((b"x-forwarded-for", value.encode("latin1")))
    if forwarded_header:
        raw.append((b"forwarded", forwarded_header.encode("latin1")))

    scope = {"type": "http", "client": (remote_ip, 12345), "headers": raw}
    asyncio.run(security.ProxyTrustMiddleware(asgi_app)(scope, None, None))

    request = mock_request(remote_ip=captured["client"][0], remote_port=captured["client"][1])
    request.headers = Headers(raw=raw)
    request.scope["headers"] = raw
    request.scope[security.SCOPE_PEER] = captured[security.SCOPE_PEER]
    request.scope[security.SCOPE_PEER_TRUSTED] = captured[security.SCOPE_PEER_TRUSTED]
    return request


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
            run_async(interface.login_index(request))

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
            run_async(interface.login_index(wrong))
        assert render.call_args.kwargs["status_code"] == 200
        assert security._login_attempts["127.0.0.1"][0] == 1

        right = login_post(username="user", password="pass")
        run_async(interface.login_index(right))
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
            response = run_async(interface.login_index(request))

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


class TestForwardedHeaderTrust:
    """A forwarded header means the peer is speaking for someone else. Unless the client was
    resolved from it, the peer's own address must not stand in for theirs."""

    @pytest.mark.parametrize(
        "verify_xff_header, xff_header, forwarded_header, expected",
        [
            # Nothing forwarded: the peer is the client, exactly as before
            (True, None, None, True),
            (False, None, None, True),
            # A trusted local peer speaking for a local client stays local
            (True, "192.168.1.50", None, True),
            # ...but not when we were told never to trust the header
            (False, "192.168.1.50", None, False),
            # A trusted local peer speaking for the internet resolves to the internet
            (True, "8.8.8.8", None, False),
            (False, "8.8.8.8", None, False),
            # RFC 7239 is not parsed, so it can only tell us the client is someone else
            (True, None, 'for="8.8.8.8"', False),
            (False, None, 'for="8.8.8.8"', False),
            # X-Forwarded-For wins when both are present
            (True, "192.168.1.50", 'for="8.8.8.8"', True),
            # An empty header tells us nothing, so the peer is still the client
            (True, "", None, True),
        ],
    )
    @pytest.mark.config(lambda params: {"verify_xff_header": params["verify_xff_header"], "inet_exposure": 0})
    def test_unresolved_client_is_not_local(self, verify_xff_header, xff_header, forwarded_header, expected):
        def _func():
            request = proxied_request("192.168.1.5", xff_header=xff_header, forwarded_header=forwarded_header)
            assert security.check_access(request, access_type=4) is expected

        _func()

    @pytest.mark.config({"verify_xff_header": False, "inet_exposure": 5, "username": "u", "password": "p"})
    def test_login_is_not_bypassed_behind_an_unverified_proxy(self):
        """The escalation this exists to remove: at inet_exposure 5 a client considered local
        is let through without a login, so a proxy standing in for the client handed that
        bypass to everyone behind it."""

        def _func():
            assert security.login_bypassed(proxied_request("127.0.0.1", xff_header="8.8.8.8")) is False
            # A genuinely local client with no proxy in front is unaffected
            assert security.login_bypassed(proxied_request("127.0.0.1")) is True

        _func()

    @pytest.mark.config({"xff_trusted_hosts": ["104.16.0.0/13"]})
    def test_trusted_hosts_grant_no_local_access(self):
        """The point of splitting this off from local_ranges: a public reverse proxy can be
        trusted to speak for others without any of its addresses counting as local."""

        def _func():
            assert "104.16.0.0/13" in xff_trusted_networks()
            assert is_local_addr("104.16.0.1") is False
            # The proxy speaks, and the real client is who we act on
            request = proxied_request("104.16.0.1", xff_header="8.8.8.8")
            assert security.client_address(request).host == "8.8.8.8"

        _func()

    @pytest.mark.config({"xff_trusted_hosts": ["104.16.0.0/13"]})
    def test_trusted_hosts_replace_the_default(self):
        """An explicit list is the whole trust boundary, so trust can be narrowed below the
        LAN default rather than only widened."""

        def _func():
            assert "10.0.0.0/8" not in xff_trusted_networks()
            # A LAN peer outside the list cannot speak for anyone
            request = proxied_request("10.11.12.13", xff_header="10.11.12.99")
            assert security.check_access(request, access_type=4) is False

        _func()

    @pytest.mark.config({"local_ranges": ["192.168.1."]})
    def test_legacy_local_range_is_a_trusted_proxy(self):
        """Old-style local_ranges entries used to reach uvicorn verbatim, where they became
        literals that never matched, leaving such a peer local but untrusted: its header was
        ignored and it stood in for its own clients."""

        def _func():
            assert "192.168.1.0/24" in xff_trusted_networks()
            assert is_local_addr("192.168.1.5") is True
            request = proxied_request("192.168.1.5", xff_header="8.8.8.8")
            assert security.client_address(request).host == "8.8.8.8"

        _func()

    @pytest.mark.config({"xff_trusted_hosts": ["*"]})
    def test_wildcard_is_not_a_trust_list(self):
        """`*` would hand the choice of client address to anyone who can reach us, so it is
        not accepted. It is refused like any other entry that is not a network, which leaves
        loopback trusted rather than everybody."""

        def _func():
            assert xff_trusted_networks() == ["127.0.0.0/8", "::ffff:127.0.0.0/104", "::1/128"]
            # The peer speaks only for itself, so a header from it is not resolved
            request = proxied_request("8.8.8.8", xff_header="1.1.1.1")
            assert security.client_address(request).host == "8.8.8.8"
            assert security.check_access(request, access_type=4) is False

        _func()

    @pytest.mark.config({"xff_trusted_hosts": ["192.168.1.0/24", "not-a-network", "10."]})
    def test_invalid_entries_are_skipped_not_fatal(self):
        """One bad entry must not take the valid ones down with it, because that would fall
        back to trusting the whole local network."""

        def _func():
            networks = xff_trusted_networks()
            assert "192.168.1.0/24" in networks
            assert "10.0.0.0/8" in networks
            assert "not-a-network" not in networks

        _func()

    @pytest.mark.config({"local_ranges": ["192.168.1.0/24"], "inet_exposure": 0})
    def test_local_ranges_can_only_narrow_trust(self):
        """Saying who counts as local restricts who may speak for others, and never widens it.
        A LAN neighbour outside local_ranges has no access of its own, so it must not be able
        to claim an address that does."""

        def _func():
            assert "10.0.0.0/8" not in xff_trusted_networks()
            outsider = proxied_request("10.11.12.13")
            assert security.check_access(outsider, access_type=4) is False
            # The same neighbour claiming an address inside local_ranges gets no further
            forged = proxied_request("10.11.12.13", xff_header="192.168.1.23")
            assert security.check_access(forged, access_type=4) is False

        _func()

    @pytest.mark.config({"local_ranges": ["8.8.8.0/24"], "inet_exposure": 0})
    def test_public_local_range_speaks_only_for_itself(self):
        """local_ranges accepts any range, including a public one. Being called local says
        nothing about being trusted to name other clients."""

        def _func():
            assert "8.8.8.0/24" not in xff_trusted_networks()
            # It keeps the local access it was given
            assert security.check_access(proxied_request("8.8.8.8"), access_type=4) is True
            # ...but cannot hand it to anyone else
            forged = proxied_request("8.8.8.8", xff_header="1.2.3.4")
            assert security.check_access(forged, access_type=4) is False

        _func()

    @pytest.mark.parametrize("remote_ip", ["2002::1", "2001::1", "203.0.113.5", "240.0.0.1"])
    @pytest.mark.config({"inet_exposure": 0})
    def test_routable_special_ranges_are_not_local(self, remote_ip):
        """These are private only in the sense that ipaddress.is_private means "not ordinary
        public internet". 6to4 and Teredo in particular are globally routable, so counting
        them as a local network handed such clients local access, and at inet_exposure 5
        entry without a password."""

        def _func():
            assert security.check_access(mock_request(remote_ip=remote_ip), access_type=4) is False

        _func()

    @pytest.mark.parametrize(
        "xff_header",
        [
            # A proxy that appends rather than rewrites sends a second line, so a client can
            # prepend one of its own. Reading only the first line would miss the real chain.
            ["", "8.8.8.8"],
            ["", "", "8.8.8.8"],
            ["8.8.8.8", ""],
            # Nothing the resolver can take an address from, so the peer is still not the client
            [",,,"],
            [" "],
            ["", ","],
        ],
    )
    @pytest.mark.config({"verify_xff_header": False, "inet_exposure": 0})
    def test_header_split_over_lines_is_still_a_header(self, xff_header):
        """The guard has to see the header the way the resolver does. Starlette returns the
        first line and ProxyHeadersMiddleware joins them all, so asking for one line let a
        prepended empty value hide a chain and leave the proxy standing in for its client."""

        def _func():
            request = proxied_request("127.0.0.1", xff_header=xff_header)
            assert security.check_access(request, access_type=4) is False

        _func()

    @pytest.mark.config({"verify_xff_header": True, "inet_exposure": 0})
    def test_trusted_peer_sending_an_unusable_header(self):
        """A trusted proxy whose header names nobody leaves request.client as the proxy. It
        was speaking for someone, so its own address must not be taken for theirs."""

        def _func():
            assert security.check_access(proxied_request("192.168.1.5", xff_header=",,,"), access_type=4) is False
            # ...while a header naming a local client still resolves as it should
            resolved = proxied_request("192.168.1.5", xff_header="192.168.1.50")
            assert security.check_access(resolved, access_type=4) is True

        _func()

    @pytest.mark.config({"verify_xff_header": True, "inet_exposure": 5, "username": "u", "password": "p"})
    def test_login_is_not_bypassed_by_a_split_header(self):
        """The same bypass reached through login_bypassed(), which is what turns it into
        entry without a password."""

        def _func():
            assert security.login_bypassed(proxied_request("127.0.0.1", xff_header=["", "8.8.8.8"])) is False

        _func()
