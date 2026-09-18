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

import threading
import time
from unittest import mock

import pytest

import sabnzbd.sessionstore as sessionstore


@pytest.fixture
def fp() -> str:
    """The fingerprint sessions created in this test's (default, blank) config match"""
    return sessionstore.credential_fingerprint()


class TestSessionStore:
    def test_roundtrip_and_delete(self, session_store, fp):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, fp, "1.2.3.4", "agent")
        assert session_store.get("hash1") == {
            "created": now,
            "expires": now + 2000,
            "last_seen": now,
            "cred_fingerprint": fp,
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

    def test_mark_seen_updates_in_memory_only(self, session_store, fp):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, fp, "1.2.3.4", "agent")

        session_store.mark_seen("hash1", now + 100, "5.6.7.8", "other")
        session = session_store.get("hash1")
        assert session["last_seen"] == now + 100
        assert session["ip"] == "5.6.7.8"
        assert session["user_agent"] == "other"
        # Not persisted: a fresh instance reading the file back sees the old values
        reopened = sessionstore.SessionStore()
        assert reopened.get("hash1")["ip"] == "1.2.3.4"

    def test_mark_seen_unknown_token_is_a_noop(self, session_store):
        assert session_store.mark_seen("does-not-exist", int(time.time()), "1.2.3.4", "agent") is None

    def test_flush_persists_mark_seen(self, session_store, fp):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, fp, "1.2.3.4", "agent")
        session_store.mark_seen("hash1", now + 100, "5.6.7.8", "other")

        session_store.flush()

        reopened = sessionstore.SessionStore()
        session = reopened.get("hash1")
        assert session["ip"] == "5.6.7.8"
        assert session["user_agent"] == "other"
        assert session["last_seen"] == now + 100

    def test_flush_is_a_noop_when_never_loaded(self, session_store):
        # Never touched this instance, so it must not load the file purely to write it
        # straight back
        store = sessionstore.SessionStore()
        with mock.patch.object(store, "_save") as mock_save:
            store.flush()
        mock_save.assert_not_called()

    def test_user_agent_is_capped(self, session_store, fp):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, fp, "1.2.3.4", "u" * 5000)
        assert len(session_store.get("hash1")["user_agent"]) == sessionstore.MAX_USER_AGENT_LENGTH

    def test_sessions_survive_a_restart(self, session_store, fp):
        now = int(time.time())
        session_store.add("hash1", now, now + 2000, fp, "1.2.3.4", "agent")
        assert sessionstore.SessionStore().get("hash1") is not None

    def test_expired_sessions_are_dropped_on_load(self, session_store, fp):
        now = int(time.time())
        session_store.add("fresh", now, now + 10000, fp, "1.2.3.4", "agent")
        # Adding purges before it inserts, so this one is still there to be dropped on load
        session_store.add("old", 0, now - 100, fp, "1.2.3.4", "agent")

        reopened = sessionstore.SessionStore()
        assert reopened.get("fresh") is not None
        assert reopened.get("old") is None

    def test_generation_bump_drops_the_contents(self, session_store, monkeypatch, fp):
        now = int(time.time())
        session_store.add("hash1", now, now + 10000, fp, "1.2.3.4", "agent")
        monkeypatch.setattr(sessionstore, "SESSIONS_VERSION", sessionstore.SESSIONS_VERSION + 1)
        assert sessionstore.SessionStore().get("hash1") is None

    def test_unreadable_file_starts_empty(self, session_store, tmp_path):
        (tmp_path / sessionstore.SESSIONS_FILE_NAME).write_bytes(b"not a pickle" * 42)
        assert sessionstore.SessionStore().get("hash1") is None

    def test_public_list_hides_the_hash_and_sorts_by_last_seen(self, session_store, fp):
        now = int(time.time())
        stale = "a" * 64
        recent = "b" * 64
        session_store.add(stale, now - 500, now + 2000, fp, "1.1.1.1", "old")
        session_store.add(recent, now - 100, now + 2000, fp, "2.2.2.2", "new")
        session_store.touch(recent, now + 2000, now, "2.2.2.2", "new")

        listed = session_store.public_list()
        assert [s["ip"] for s in listed] == ["2.2.2.2", "1.1.1.1"]
        assert all("hash" not in s and len(s["id"]) == sessionstore.SESSION_ID_LENGTH for s in listed)
        assert stale not in [s["id"] for s in listed]

    def test_public_list_excludes_expired(self, session_store, fp):
        now = int(time.time())
        session_store.add("f" * 64, now, now + 2000, fp, "1.1.1.1", "live")
        session_store._sessions["e" * 64] = sessionstore.Session(
            created=0, expires=now - 10, last_seen=0, cred_fingerprint=fp, ip="9.9.9.9", user_agent="dead"
        )
        assert [s["ip"] for s in session_store.public_list()] == ["1.1.1.1"]

    def test_public_list_excludes_a_stale_credential_fingerprint(self, session_store, fp):
        """A session from before a password change (however it changed - a save, or
        the ini edited directly) must not be listed as though it were still valid,
        and must not linger in memory or on disk with its IP/user-agent either"""
        now = int(time.time())
        session_store.add("f" * 64, now, now + 2000, fp, "1.1.1.1", "live")
        session_store.add("e" * 64, now, now + 2000, "stale-fingerprint", "9.9.9.9", "dead")
        assert [s["ip"] for s in session_store.public_list()] == ["1.1.1.1"]
        assert session_store.get("e" * 64) is None

        _, persisted = sessionstore.load_admin(sessionstore.SESSIONS_FILE_NAME, silent=True)
        assert "e" * 64 not in persisted
        assert "f" * 64 in persisted

    def test_public_list_purges_expired_from_disk(self, session_store, fp):
        """A session that expires while nothing else writes must not linger on disk"""
        now = int(time.time())
        live, dead = "1" * 64, "2" * 64
        session_store.add(live, now, now + 2000, fp, "1.1.1.1", "agent")
        session_store.add(dead, now, now + 50, fp, "2.2.2.2", "agent")  # persisted while still valid
        session_store._sessions[dead]["expires"] = now - 10  # time passes, nothing else writes

        session_store.public_list()

        _, persisted = sessionstore.load_admin(sessionstore.SESSIONS_FILE_NAME, silent=True)
        assert dead not in persisted
        assert live in persisted

    def test_load_purges_a_stale_file(self, session_store, fp):
        """A record left over from a previous run, expired by the time it is next
        loaded, must be dropped from the file too - not just filtered in memory"""
        now = int(time.time())
        live, dead = "3" * 64, "4" * 64
        session_store.add(live, now, now + 2000, fp, "1.1.1.1", "agent")
        # Write the stale record straight to disk, bypassing the store's own pruning
        raw = dict(session_store.sessions)
        raw[dead] = sessionstore.Session(
            created=0, expires=now - 10, last_seen=0, cred_fingerprint=fp, ip="9.9.9.9", user_agent="dead"
        )
        sessionstore.save_admin((sessionstore.SESSIONS_VERSION, raw), sessionstore.SESSIONS_FILE_NAME)

        sessionstore.SessionStore().get(live)  # a fresh instance, loading that file

        _, persisted = sessionstore.load_admin(sessionstore.SESSIONS_FILE_NAME, silent=True)
        assert dead not in persisted
        assert live in persisted

    def test_delete_by_id(self, session_store, fp):
        now = int(time.time())
        token_hash = "c" * 64
        session_store.add(token_hash, now, now + 2000, fp, "1.1.1.1", "agent")
        session_id = sessionstore.public_session_id(token_hash)

        assert session_store.delete_by_id("does-not-exist") is False
        assert session_store.delete_by_id(session_id) is True
        assert session_store.get(token_hash) is None

    def test_delete_all(self, session_store, fp):
        now = int(time.time())
        session_store.add("d" * 64, now, now + 2000, fp, "1.1.1.1", "agent")
        session_store.add("d" * 63 + "e", now, now + 2000, fp, "2.2.2.2", "agent")
        session_store.delete_all()
        assert session_store.public_list() == []
        assert sessionstore.SessionStore().public_list() == []

    def test_concurrent_flush_and_add_does_not_raise(self, session_store, fp):
        """flush() runs on the PostProcessor thread (via save_state()) while add()/
        touch()/delete() run on the web server's event loop - without a lock this
        raced on the same dict and crashed with RuntimeError: dictionary changed
        size during iteration"""
        now = int(time.time())
        errors = []

        def adder():
            for i in range(300):
                try:
                    session_store.add(f"concurrent-{i}", now, now + 2000, fp, "1.1.1.1", "agent")
                except Exception as exc:
                    errors.append(exc)

        def flusher():
            for _ in range(300):
                try:
                    session_store.flush()
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=adder), threading.Thread(target=flusher)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []

    def test_concurrent_adds_do_not_lose_sessions(self, session_store, fp):
        """A read-rebuild-reassign that is not atomic drops any session add() installs
        between another thread's read and reassignment"""
        now = int(time.time())
        session_count = 200

        def adder(i):
            session_store.add(f"session-{i}", now, now + 2000, fp, "1.1.1.1", "agent")

        threads = [threading.Thread(target=adder, args=(i,)) for i in range(session_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(session_store.sessions) == session_count
