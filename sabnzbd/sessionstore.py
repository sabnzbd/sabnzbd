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
sabnzbd.sessionstore - Storage for web-UI login sessions
"""

import logging
import time
from typing import Any, Optional, TypedDict

from sabnzbd.constants import SESSIONS_FILE_NAME, SESSIONS_VERSION
from sabnzbd.filesystem import load_admin, save_admin

# Cap the stored user-agent so a client cannot grow sessions.sab unbounded
MAX_USER_AGENT_LENGTH = 200
# Public session id length; it is a prefix of the token hash
SESSION_ID_LENGTH = 16


class Session(TypedDict):
    created: int
    expires: int
    last_seen: int
    cred_fingerprint: str
    ip: str
    user_agent: str


def public_session_id(token_hash: str) -> str:
    """Public id for a session: a prefix of its token hash, so the hash is never exposed"""
    return token_hash[:SESSION_ID_LENGTH]


class SessionStore:
    """Login sessions, held as a dict and written to the admin folder on every change.

    Only ever touched from the web server's event loop, so it needs no locking.
    """

    def __init__(self):
        self._sessions: Optional[dict[str, Session]] = None

    @property
    def sessions(self) -> dict[str, Session]:
        """The sessions, loaded from disk on first use"""
        if self._sessions is None:
            self._load()
        return self._sessions

    @staticmethod
    def _unexpired(sessions: dict[str, Session], now: int) -> dict[str, Session]:
        """The entries whose expiry is still in the future"""
        return {token: s for token, s in sessions.items() if s["expires"] > now}

    def _prune_and_persist(self, before: dict[str, Session], now: int):
        """Adopt the still-valid entries; persist if any were dropped, so an expired
        session's IP/user-agent does not linger on disk until something else writes"""
        live = self._unexpired(before, now)
        self._sessions = live
        if len(live) != len(before):
            self._save()

    def _load(self):
        self._sessions = {}
        try:
            if data := load_admin(SESSIONS_FILE_NAME, silent=True):
                version, sessions = data
                if version == SESSIONS_VERSION:
                    self._prune_and_persist(sessions, int(time.time()))
        except Exception:
            logging.info("Failed to load sessions", exc_info=True)

    def _save(self):
        save_admin((SESSIONS_VERSION, self.sessions), SESSIONS_FILE_NAME)

    def get(self, token_hash: str) -> Optional[Session]:
        """Return the session stored for token_hash, or None"""
        return self.sessions.get(token_hash)

    def add(self, token_hash: str, created: int, expires: int, cred_fingerprint: str, ip: str, user_agent: str):
        """Store a new login session, dropping any that expired in the meantime"""
        self._sessions = self._unexpired(self.sessions, int(time.time()))
        self._sessions[token_hash] = Session(
            created=created,
            expires=expires,
            last_seen=created,
            cred_fingerprint=cred_fingerprint,
            ip=ip,
            user_agent=user_agent[:MAX_USER_AGENT_LENGTH],
        )
        self._save()

    def touch(self, token_hash: str, expires: int, last_seen: int, ip: str, user_agent: str):
        """Record a session being used: new expiry, last_seen and client details"""
        if session := self.get(token_hash):
            session["expires"] = expires
            session["last_seen"] = last_seen
            session["ip"] = ip
            session["user_agent"] = user_agent[:MAX_USER_AGENT_LENGTH]
            self._save()

    def delete(self, token_hash: str):
        """Delete a single session"""
        if self.sessions.pop(token_hash, None):
            self._save()

    def delete_by_id(self, session_id: str) -> bool:
        """Delete the session with this public id; return whether one matched"""
        for token_hash in list(self.sessions):
            if public_session_id(token_hash) == session_id:
                del self._sessions[token_hash]
                self._save()
                return True
        return False

    def delete_all(self):
        """Drop every session"""
        self._sessions = {}
        self._save()

    def public_list(self) -> list[dict[str, Any]]:
        """Live sessions for the web-UI, newest activity first, without the token hash"""
        self._prune_and_persist(self.sessions, int(time.time()))
        sessions = [
            {
                "id": public_session_id(token_hash),
                "created": s["created"],
                "last_seen": s["last_seen"],
                "expires": s["expires"],
                "ip": s["ip"],
                "user_agent": s["user_agent"],
            }
            for token_hash, s in self._sessions.items()
        ]
        return sorted(sessions, key=lambda s: s["last_seen"], reverse=True)
