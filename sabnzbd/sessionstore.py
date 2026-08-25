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
from typing import Optional, TypedDict

from sabnzbd.constants import SESSIONS_FILE_NAME, SESSIONS_VERSION
from sabnzbd.filesystem import load_admin, save_admin


class Session(TypedDict):
    created: int
    expires: int
    cred_fingerprint: str


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

    def _load(self):
        self._sessions = {}
        try:
            if data := load_admin(SESSIONS_FILE_NAME, silent=True):
                version, sessions = data
                if version == SESSIONS_VERSION:
                    now = int(time.time())
                    self._sessions = {token: s for token, s in sessions.items() if s["expires"] > now}
        except Exception:
            logging.info("Failed to load sessions", exc_info=True)

    def _save(self):
        save_admin((SESSIONS_VERSION, self.sessions), SESSIONS_FILE_NAME)

    def get(self, token_hash: str) -> Optional[Session]:
        """Return the session stored for token_hash, or None"""
        return self.sessions.get(token_hash)

    def add(self, token_hash: str, created: int, expires: int, cred_fingerprint: str):
        """Store a new login session, dropping any that expired in the meantime"""
        now = int(time.time())
        self._sessions = {token: s for token, s in self.sessions.items() if s["expires"] > now}
        self._sessions[token_hash] = Session(created=created, expires=expires, cred_fingerprint=cred_fingerprint)
        self._save()

    def touch(self, token_hash: str, expires: int):
        """Extend the expiry of a session (sliding window)"""
        if session := self.get(token_hash):
            session["expires"] = expires
            self._save()

    def delete(self, token_hash: str):
        """Delete a single session"""
        if self.sessions.pop(token_hash, None):
            self._save()
