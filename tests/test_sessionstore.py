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
tests.test_sessionstore - Testing the web-UI session store
"""

import time

import sabnzbd.sessionstore as sessionstore


class TestSessionStore:
    def test_roundtrip_and_delete(self, session_store):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, "fp")
        assert session_store.get("hash1") == {"created": now, "expires": now + 2000, "cred_fingerprint": "fp"}

        session_store.touch("hash1", now + 5000)
        assert session_store.get("hash1")["expires"] == now + 5000

        session_store.delete("hash1")
        assert session_store.get("hash1") is None

    def test_sessions_survive_a_restart(self, session_store):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, "fp")
        assert sessionstore.SessionStore().get("hash1") is not None

    def test_expired_sessions_are_dropped_on_load(self, session_store):
        now = int(time.time())
        session_store.add("fresh", now, now + 10000, "fp")
        # Adding purges before it inserts, so this one is still there to be dropped on load
        session_store.add("old", 0, now - 100, "fp")

        reopened = sessionstore.SessionStore()
        assert reopened.get("fresh") is not None
        assert reopened.get("old") is None

    def test_generation_bump_drops_the_contents(self, session_store, monkeypatch):
        now = int(time.time())
        session_store.add("hash1", now, now + 10000, "fp")
        monkeypatch.setattr(sessionstore, "SESSIONS_VERSION", sessionstore.SESSIONS_VERSION + 1)
        assert sessionstore.SessionStore().get("hash1") is None

    def test_unreadable_file_starts_empty(self, session_store, tmp_path):
        (tmp_path / sessionstore.SESSIONS_FILE_NAME).write_bytes(b"not a pickle" * 42)
        assert sessionstore.SessionStore().get("hash1") is None
