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
from typing import Any, Optional

from starlette.datastructures import Address
from starlette.requests import Request
from starlette.responses import Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.encoding import utob
from sabnzbd.misc import is_local_addr, is_loopback_addr, xff_trusted_networks

_MSG_MISSING_SESSION = "Access denied - Missing or invalid session token, reload the page and try again"
_MSG_APIKEY_NOT_ON_PAGES = (
    "Access denied - The apikey is only accepted on /api, use the matching api-call instead of this page"
)
_MSG_SESSION_EXPIRED = "Session expired, reload the page"


# Holds the login token for an authenticated session; absent where the login is bypassed
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

# A token is hmac(_CSRF_KEY, identity), so it is bound to its session and dies with it.
# The key is regenerated each run, leaving a page open across a restart with a stale token.
# The token is rendered into the page and echoed back in the header or a field.
_CSRF_KEY = secrets.token_bytes(32)
CSRF_HEADER = "X-SABnzbd-CSRF"
CSRF_FIELD = "csrf_token"
# A login-bypassed request carries no session cookie; its CSRF token binds to this stable
# identity instead. _CSRF_KEY, not this value, is the secret that makes the token unguessable.
_ANONYMOUS_CSRF_IDENTITY = "anonymous"


# What ProxyTrustMiddleware observed before the forwarded headers were applied
SCOPE_PEER = "sabnzbd.peer"
SCOPE_PEER_TRUSTED = "sabnzbd.peer_trusted"


class ProxyTrustMiddleware:
    """Resolve the forwarded headers, recording the connecting peer and whether it was
    trusted to speak for anyone. Run here rather than at the uvicorn layer, which leaves no
    trace of what it decided, so an address taken from X-Forwarded-For cannot afterwards be
    told apart from the proxy that sent it. The verdict comes from the same trust set that
    does the parsing, so the two cannot drift apart."""

    def __init__(self, app):
        if cfg.verify_xff_header():
            proxy_headers = ProxyHeadersMiddleware(app, trusted_hosts=xff_trusted_networks())
            self.app = proxy_headers
            self.trusted_hosts = proxy_headers.trusted_hosts
        else:
            self.app = app
            self.trusted_hosts = None

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            peer = scope.get("client")
            scope[SCOPE_PEER] = peer
            scope[SCOPE_PEER_TRUSTED] = bool(self.trusted_hosts is not None and peer and peer[0] in self.trusted_hosts)
        await self.app(scope, receive, send)


def client_address(request: Request) -> Address:
    """Safe access to request.client, which can be None (e.g. when serving on a
    unix socket, or with some test clients). Treated as an unknown, non-local
    client, so access checks fail closed."""
    return request.client or Address("", 0)


def peer_address(request: Request) -> Address:
    """The address that opened the connection, before any forwarded header was applied.
    Equal to client_address() unless a trusted proxy spoke for someone else."""
    if peer := request.scope.get(SCOPE_PEER):
        return Address(*peer)
    return client_address(request)


def forwarded_for_header(request: Request) -> str:
    """The X-Forwarded-For value as the resolver reads it. A header sent more than once
    arrives as several lines, which ProxyHeadersMiddleware joins and Headers.get() does not:
    taking only the first line would miss a chain that has one prepended to it."""
    return ", ".join(request.headers.getlist("X-Forwarded-For"))


def unresolved_client_reason(request: Request) -> Optional[str]:
    """Why request.client cannot be taken for the client address, or None when it can. A
    forwarded header means the peer is speaking for someone else, so unless the client was
    resolved from it the peer's own address must not stand in for theirs."""
    if forwarded_for_header(request):
        # The address is replaced wholesale when it is resolved, so an unchanged one means
        # the resolver declined: the peer was not trusted, or the header named nobody. No
        # recorded peer means the request never passed ProxyTrustMiddleware.
        recorded_peer = request.scope.get(SCOPE_PEER)
        if recorded_peer is not None and recorded_peer != request.scope.get("client"):
            return None
        peer = peer_address(request).host
        if not cfg.verify_xff_header():
            return (
                T(
                    "X-Forwarded-For received while verify_xff_header is off, turn it on and list %s in xff_trusted_hosts"
                )
                % peer
            )
        if not request.scope.get(SCOPE_PEER_TRUSTED):
            return T("X-Forwarded-For received from %s, which is not in xff_trusted_hosts") % peer
        return T("X-Forwarded-For from %s does not name a client address") % peer
    if request.headers.get("Forwarded"):
        # RFC 7239 is not parsed, so its presence only tells us the client is someone else
        return T("Forwarded is not supported, configure the proxy to send X-Forwarded-For instead")
    return None


def client_address_info(request: Request) -> str:
    """The client as host:port for logging, with the forwarding chain when there is one,
    and the peer that connected when it is not the client itself.

    Always ends with the user-agent, which is the shape sanitize_line() looks for when it
    redacts external addresses out of the log the showlog api-call returns. A line that
    mentions a client and does not end this way is not redacted at all."""
    client = client_address(request)
    # Bracketed, so the port cannot be read as another group of an IPv6 address
    host = f"[{client.host}]" if ":" in client.host else client.host
    info = f"{host}:{client.port}"
    # Only when it was verified: an unverified header is attacker-controlled text
    if cfg.verify_xff_header() and (xff_ips := forwarded_for_header(request)):
        info += f" (X-Forwarded-For: {xff_ips})"
    if (peer := peer_address(request)).host != client.host:
        peer_host = f"[{peer.host}]" if ":" in peer.host else peer.host
        info += f" (via {peer_host})"
    # A dash rather than nothing: the brackets have to hold something to be recognised
    return f"{info} [{request.headers.get('User-Agent') or '-'}]"


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

    # Without a resolved client there is nobody to grant access to, whatever the peer is
    if reason := unresolved_client_reason(request):
        if warn_user and cfg.api_warnings():
            logging.warning("%s %s - %s", T("Refused connection from:"), client_address_info(request), reason)
        return False

    # ProxyTrustMiddleware has resolved the chain, so this is the effective client
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


def csrf_identity(request: Request) -> str:
    """The value a request's CSRF token binds to: its session cookie, or a stable constant
    when the login is bypassed and no session cookie is present."""
    if cookie := request.cookies.get(SESSION_COOKIE_USER, ""):
        return cookie
    return _ANONYMOUS_CSRF_IDENTITY if login_bypassed(request) else ""


def csrf_token_for(identity: str) -> str:
    """The CSRF token belonging to a session identity"""
    return hmac.new(_CSRF_KEY, utob(identity), hashlib.sha256).hexdigest()


def presented_csrf_token(request: Request, header_only: bool = False) -> str:
    """The CSRF token this request offers, from the header or a form field"""
    if header_only:
        return request.headers.get(CSRF_HEADER) or ""
    presented = request.headers.get(CSRF_HEADER) or request.state.params.get(CSRF_FIELD) or ""
    # A multipart part named csrf_token arrives as an UploadFile, which is not a token
    return presented if isinstance(presented, str) else ""


def csrf_token_matches(request: Request, header_only: bool = False) -> bool:
    """Whether the request echoes the CSRF token belonging to its identity. A request
    with no identity never matches, so a direct caller cannot bypass that guard."""
    identity = csrf_identity(request)
    return bool(identity) and constant_time_equals(
        presented_csrf_token(request, header_only=header_only),
        csrf_token_for(identity),
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
    """Return True when the request may act as a session: the login is bypassed, or it
    carries a valid session cookie this instance issued."""
    return login_bypassed(request) or validate_session(request)
