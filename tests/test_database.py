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
tests.test_database - Testing the HistoryDB connection pool
"""

import threading

import pytest

import sabnzbd.database as db


@pytest.fixture
def pool(tmp_path):
    """Fresh pool against a fresh database file"""
    db.HistoryDB.db_path = str(tmp_path / "history1.db")
    db.HistoryDB.startup_done = False
    pool = db.HistoryDBPool(max_connections=2, checkout_timeout=0.2)
    yield pool
    pool.close()


class TestHistoryDBPool:
    def test_lifo_reuse(self, pool):
        with pool.connection() as first:
            assert first.execute("SELECT COUNT(*) FROM history")
        with pool.connection() as second:
            # The returned connection is reused, not a new one
            assert second is first
        assert pool._created == 1

    def test_exclusive_checkout_and_bounded(self, pool):
        with pool.connection() as first, pool.connection() as second:
            assert first is not second
            assert pool._created == 2
            # Third concurrent checkout exceeds max_connections: served by a
            # temporary overflow connection instead of blocking forever
            with pool.connection() as third:
                assert third is not first
                assert third is not second
                assert pool._created == 2
            # Overflow connection was closed on check-in, not pooled
            assert pool._idle.qsize() == 0

    def test_returned_connections_reused_when_full(self, pool):
        with pool.connection() as first:
            with pool.connection() as second:
                pass
        with pool.connection() as reused:
            assert reused in (first, second)
        assert pool._created == 2

    def test_invalidate_discards_pooled_connections(self, pool):
        with pool.connection() as first:
            pass
        pool.invalidate()
        with pool.connection() as second:
            assert second is not first
            # Still works after replacement
            assert second.execute("SELECT COUNT(*) FROM history")
        assert pool._created == 1

    def test_invalidate_spares_reconnected_instance(self, pool):
        with pool.connection() as first:
            pool.invalidate(reconnected=first)
        # The reconnected instance survives and is pooled again
        with pool.connection() as second:
            assert second is first

    def test_close_discards_and_serves_overflow(self, pool):
        with pool.connection() as first:
            pass
        pool.close()
        assert pool._idle.qsize() == 0
        # Late checkout after shutdown still works, via a temporary connection
        with pool.connection() as late:
            assert late is not first
            assert late.execute("SELECT COUNT(*) FROM history")
        assert pool._idle.qsize() == 0

    def test_connection_usable_across_threads(self, pool):
        """Pooled connections move between (e.g. AnyIO worker) threads"""
        with pool.connection() as history_db:
            pass

        result = {}

        def worker():
            with pool.connection() as history_db2:
                result["same"] = history_db2 is history_db
                history_db2.execute("SELECT COUNT(*) FROM history")
                result["count"] = history_db2.cursor.fetchone()[0]

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert result["same"] is True
        assert result["count"] == 0

    def test_wal_mode_enabled(self, pool):
        with pool.connection() as history_db:
            history_db.execute("PRAGMA journal_mode;")
            assert history_db.cursor.fetchone()[0] == "wal"
