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
        session_store.add("hash1", now, now + 2000, "fp", "1.2.3.4", "agent")
        assert session_store.get("hash1") == {
            "created": now,
            "expires": now + 2000,
            "last_seen": now,
            "cred_fingerprint": "fp",
            "ip": "1.2.3.4",
            "user_agent": "agent",
        }

        session_store.touch("hash1", now + 5000, now + 100, "5.6.7.8", "other")
        session = session_store.get("hash1")
        assert session["expires"] == now + 5000
        assert session["last_seen"] == now + 100
        assert session["ip"] == "5.6.7.8"
        assert session["user_agent"] == "other"

        session_store.delete("hash1")
        assert session_store.get("hash1") is None

    def test_user_agent_is_capped(self, session_store):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, "fp", "1.2.3.4", "u" * 5000)
        assert len(session_store.get("hash1")["user_agent"]) == sessionstore.MAX_USER_AGENT_LENGTH

    def test_sessions_survive_a_restart(self, session_store):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, "fp", "1.2.3.4", "agent")
        assert sessionstore.SessionStore().get("hash1") is not None

    def test_expired_sessions_are_dropped_on_load(self, session_store):
        now = int(time.time())
        session_store.add("fresh", now, now + 10000, "fp", "1.2.3.4", "agent")
        # Adding purges before it inserts, so this one is still there to be dropped on load
        session_store.add("old", 0, now - 100, "fp", "1.2.3.4", "agent")

        reopened = sessionstore.SessionStore()
        assert reopened.get("fresh") is not None
        assert reopened.get("old") is None

    def test_generation_bump_drops_the_contents(self, session_store, monkeypatch):
        now = int(time.time())
        session_store.add("hash1", now, now + 10000, "fp", "1.2.3.4", "agent")
        monkeypatch.setattr(sessionstore, "SESSIONS_VERSION", sessionstore.SESSIONS_VERSION + 1)
        assert sessionstore.SessionStore().get("hash1") is None

    def test_unreadable_file_starts_empty(self, session_store, tmp_path):
        (tmp_path / sessionstore.SESSIONS_FILE_NAME).write_bytes(b"not a pickle" * 42)
        assert sessionstore.SessionStore().get("hash1") is None

    def test_public_list_hides_the_hash_and_sorts_by_last_seen(self, session_store):
        now = int(time.time())
        stale = "a" * 64
        recent = "b" * 64
        session_store.add(stale, now - 500, now + 2000, "fp", "1.1.1.1", "old")
        session_store.add(recent, now - 100, now + 2000, "fp", "2.2.2.2", "new")
        session_store.touch(recent, now + 2000, now, "2.2.2.2", "new")

        listed = session_store.public_list()
        assert [s["ip"] for s in listed] == ["2.2.2.2", "1.1.1.1"]
        assert all("hash" not in s and len(s["id"]) == sessionstore.SESSION_ID_LENGTH for s in listed)
        assert stale not in [s["id"] for s in listed]

    def test_public_list_excludes_expired(self, session_store):
        now = int(time.time())
        session_store.add("f" * 64, now, now + 2000, "fp", "1.1.1.1", "live")
        session_store._sessions["e" * 64] = sessionstore.Session(
            created=0, expires=now - 10, last_seen=0, cred_fingerprint="fp", ip="9.9.9.9", user_agent="dead"
        )
        assert [s["ip"] for s in session_store.public_list()] == ["1.1.1.1"]

    def test_delete_by_id(self, session_store):
        now = int(time.time())
        token_hash = "c" * 64
        session_store.add(token_hash, now, now + 2000, "fp", "1.1.1.1", "agent")
        session_id = sessionstore.public_session_id(token_hash)

        assert session_store.delete_by_id("does-not-exist") is False
        assert session_store.delete_by_id(session_id) is True
        assert session_store.get(token_hash) is None

    def test_delete_all(self, session_store):
        now = int(time.time())
        session_store.add("d" * 64, now, now + 2000, "fp", "1.1.1.1", "agent")
        session_store.add("d" * 63 + "e", now, now + 2000, "fp", "2.2.2.2", "agent")
        session_store.delete_all()
        assert session_store.public_list() == []
        assert sessionstore.SessionStore().public_list() == []
