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
sabnzbd.security - authentication, sessions and the per-route access checks
"""

import hashlib
import logging
import hmac
import secrets
import time
from typing import Any

from starlette.datastructures import Address
from starlette.requests import Request
from starlette.responses import Response

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.encoding import utob
from sabnzbd.misc import is_local_addr, is_loopback_addr

_MSG_MISSING_SESSION = "Access denied - Missing or invalid session token, reload the page and try again"
_MSG_APIKEY_NOT_ON_PAGES = (
    "Access denied - The apikey is only accepted on /api, use the matching api-call instead of this page"
)
_MSG_SESSION_EXPIRED = "Session expired, reload the page"


# Holds a database-backed login token, or the anonymous tag when the login is bypassed
SESSION_COOKIE_USER = "sabnzbd_user"
# The SessionMiddleware cookie, used for RSS flash messages only. Not authentication.
SESSION_COOKIE_FLASH = "sabnzbd_flash"
# How long a session survives without being used
SESSION_DURATION = 3600 * 24 * 14  # 14 days
# Lifetime from the created stamp, so a session that keeps being used still ends
SESSION_MAX_AGE = 3600 * 24 * 90  # 90 days
# Only extend a session's expiry when doing so buys it more than this much extra time
SESSION_REFRESH_THRESHOLD = 3600 * 24  # 1 day

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_TIME = 300  # 5 minutes

# {host: (failures, cooldown_expiry)} cooldown_expiry uses the monotonic clock
_login_attempts: dict[str, tuple[int, float]] = {}

# Anonymous sessions are issued where the login is bypassed, so the frontend can still authenticate by cookie.
_ANONYMOUS_SESSION_KEY = secrets.token_bytes(32)

# A token is hmac(_CSRF_KEY, cookie_value), so it is bound to its session and dies with it.
# The key is regenerated each run, leaving a page open across a restart with a stale token.
# The token is rendered into the page and echoed back in the header or a field.
_CSRF_KEY = secrets.token_bytes(32)
CSRF_HEADER = "X-SABnzbd-CSRF"
CSRF_FIELD = "csrf_token"


def client_address(request: Request) -> Address:
    """Safe access to request.client, which can be None (e.g. when serving on a
    unix socket, or with some test clients). Treated as an unknown, non-local
    client, so access checks fail closed."""
    return request.client or Address("", 0)


def client_address_info(request: Request) -> str:
    """The client as host:port for logging, with the forwarding chain when there is one"""
    client = client_address(request)
    # Bracketed, so the port cannot be read as another group of an IPv6 address
    host = f"[{client.host}]" if ":" in client.host else client.host
    if cfg.verify_xff_header() and (xff_ips := request.headers.get("X-Forwarded-For")):
        return f"{host}:{client.port} (X-Forwarded-For: {xff_ips})"
    return f"{host}:{client.port}"


def use_secure_cookies(request: Request) -> bool:
    """Whether cookies for this request should carry the Secure attribute"""
    return request.scope.get("scheme") == "https" or bool(cfg.enable_https())


def check_access(request: Request, access_type: int = 4, warn_user: bool = False) -> bool:
    """Check if external address is allowed given access_type (Starlette version):
    1=nzb
    2=api
    3=full_api
    4=webui
    5=webui with login for external
    """
    # Easy, it's allowed
    if access_type <= cfg.inet_exposure():
        return True

    # X-Forwarded-For is resolved by uvicorn's ProxyHeadersMiddleware (see the
    # uvicorn.Config in SABnzbd.py): when verify_xff_header is enabled and the
    # connecting peer is a trusted local proxy, request.client already holds the
    # effective client address taken from the XFF chain.
    remote_ip = client_address(request).host

    # Check if the client IP is a loopback address or considered local
    is_allowed = is_loopback_addr(remote_ip) or is_local_addr(remote_ip)

    if not is_allowed and warn_user and cfg.api_warnings():
        logging.warning("%s %s", T("Refused connection from:"), client_address_info(request))
    return is_allowed


def _prune_login_attempts(now: float):
    """Forget clients whose cooldown has run out"""
    for host in [host for host, (_, cooldown_expiry) in _login_attempts.items() if cooldown_expiry <= now]:
        del _login_attempts[host]


def login_cooldown_remaining(request: Request) -> int:
    """Whole seconds this client must sit out before another login attempt is considered"""
    _prune_login_attempts(time.monotonic())
    failures, cooldown_expiry = _login_attempts.get(client_address(request).host, (0, 0.0))
    remaining = cooldown_expiry - time.monotonic()
    if failures < LOGIN_MAX_ATTEMPTS or remaining <= 0:
        return 0
    # Rounded up, because a Retry-After of 0 would invite a retry that is still too early
    return int(remaining) + 1


def record_login_failure(request: Request):
    """Count a failed login against this client"""
    now = time.monotonic()
    _prune_login_attempts(now)

    host = client_address(request).host
    failures = _login_attempts.get(host, (0, 0.0))[0]
    _login_attempts[host] = (failures + 1, now + LOGIN_LOCKOUT_TIME)


def clear_login_failures(request: Request):
    """Give a client its full allowance back, once it has proved it knows the password"""
    _login_attempts.pop(client_address(request).host, None)


def constant_time_equals(presented: Any, expected: str) -> bool:
    """Constant-time comparison of a secret. Anything that is not text counts as nothing presented."""
    if not isinstance(presented, str):
        presented = ""
    return hmac.compare_digest(
        presented.encode("utf-8", "backslashreplace"), expected.encode("utf-8", "backslashreplace")
    )


def credential_fingerprint() -> str:
    """Fingerprint of the current username/password, stored with each session, so changing either invalidates all sessions"""
    return hashlib.sha256(utob("%s:%s" % (cfg.username(), cfg.password()))).hexdigest()


def hash_session_token(token: str) -> str:
    """Hash of the raw cookie token; only the hash is stored server-side"""
    return hashlib.sha256(utob(token)).hexdigest()


def create_session(request: Request, response: Response, remember_me: bool = False):
    """Create a login session and set the session cookie"""
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    sabnzbd.SessionStore.add(
        token_hash=hash_session_token(token),
        created=now,
        expires=now + SESSION_DURATION,
        cred_fingerprint=credential_fingerprint(),
    )

    max_age = SESSION_MAX_AGE if remember_me else None
    response.set_cookie(
        SESSION_COOKIE_USER,
        token,
        path="/",
        httponly=True,
        secure=use_secure_cookies(request),
        samesite="strict",
        max_age=max_age,
    )


def login_bypassed(request: Request) -> bool:
    """Return True when check_login lets this request through without a login session"""
    # No authentication required when no username/password is set
    if not cfg.username() or not cfg.password():
        return True

    # If we show login for external IP, by using access_type=6 we can check if IP match
    return cfg.inet_exposure() == 5 and check_access(request, access_type=6)


def anonymous_session_tag() -> str:
    """The stateless anonymous session cookie value for this run"""
    return hmac.new(_ANONYMOUS_SESSION_KEY, b"anonymous-session", hashlib.sha256).hexdigest()


def validate_anonymous_session(request: Request) -> bool:
    """Return True when the login is bypassed for this request and it carries a valid
    anonymous session cookie."""
    if not login_bypassed(request):
        return False
    return constant_time_equals(request.cookies.get(SESSION_COOKIE_USER, ""), anonymous_session_tag())


def create_anonymous_session(request: Request, response: Response):
    """Set the stateless anonymous session cookie on the response"""
    response.set_cookie(
        SESSION_COOKIE_USER,
        anonymous_session_tag(),
        path="/",
        httponly=True,
        secure=use_secure_cookies(request),
        samesite="strict",
        max_age=SESSION_DURATION,
    )


def csrf_token_for(cookie_value: str) -> str:
    """The CSRF token belonging to a session cookie value"""
    return hmac.new(_CSRF_KEY, utob(cookie_value), hashlib.sha256).hexdigest()


def presented_csrf_token(request: Request, header_only: bool = False) -> str:
    """The CSRF token this request offers, from the header or a form field"""
    if header_only:
        return request.headers.get(CSRF_HEADER) or ""
    presented = request.headers.get(CSRF_HEADER) or request.state.params.get(CSRF_FIELD) or ""
    # A multipart part named csrf_token arrives as an UploadFile, which is not a token
    return presented if isinstance(presented, str) else ""


def csrf_token_matches(request: Request, header_only: bool = False) -> bool:
    """Whether the request echoes the CSRF token belonging to the cookie it sent"""
    return constant_time_equals(
        presented_csrf_token(request, header_only=header_only),
        csrf_token_for(request.cookies.get(SESSION_COOKIE_USER, "")),
    )


def validate_csrf(request: Request) -> bool:
    """Return True when the request carries a valid session and the CSRF token belonging to it"""
    return validate_any_session(request) and csrf_token_matches(request)


def clear_session(request: Request, response: Response):
    """Delete the request's session (if any) and clear the session cookie"""
    if token := request.cookies.get(SESSION_COOKIE_USER):
        sabnzbd.SessionStore.delete(hash_session_token(token))
    response.set_cookie(
        SESSION_COOKIE_USER,
        "",
        path="/",
        httponly=True,
        secure=use_secure_cookies(request),
        samesite="strict",
        expires="Thu, 01 Jan 1970 00:00:00 GMT",
    )


def validate_session(request: Request) -> bool:
    """Return True when the request carries a live session cookie whose credential fingerprint still matches. Others are deleted, a valid one slides its expiry forward."""
    if (cached := getattr(request.state, "session_valid", None)) is None:
        cached = _validate_session(request)
        request.state.session_valid = cached
    return cached


def _validate_session(request: Request) -> bool:
    """The lookup behind validate_session. Call that instead, so a request pays for this once."""
    token = request.cookies.get(SESSION_COOKIE_USER)
    if not token:
        return False

    token_hash = hash_session_token(token)
    now = int(time.time())
    session = sabnzbd.SessionStore.get(token_hash)
    if not session:
        return False

    # Idle-expired, past the deadline, or from before a credential change
    if (
        session["expires"] < now
        or session["created"] + SESSION_MAX_AGE < now
        or session["cred_fingerprint"] != credential_fingerprint()
    ):
        sabnzbd.SessionStore.delete(token_hash)
        return False

    # Slide the idle timeout forward, never past the deadline and never backwards, and only
    # when it gains real time
    new_expires = max(session["expires"], min(now + SESSION_DURATION, session["created"] + SESSION_MAX_AGE))
    if new_expires > session["expires"] + SESSION_REFRESH_THRESHOLD:
        sabnzbd.SessionStore.touch(token_hash, new_expires)

    return True


def validate_any_session(request: Request) -> bool:
    """Return True when the request carries a session cookie this instance issued"""
    return validate_anonymous_session(request) or validate_session(request)


def _anonymous_session_sender(request: Request, send):
    """Wrap an ASGI send so the anonymous session cookie is added to the response start"""
    carrier = Response()
    create_anonymous_session(request, carrier)
    cookie_headers = [(key, value) for key, value in carrier.raw_headers if key == b"set-cookie"]

    async def send_with_cookie(message):
        if message["type"] == "http.response.start":
            message["headers"] = list(message.get("headers", [])) + cookie_headers
        await send(message)

    return send_with_cookie
