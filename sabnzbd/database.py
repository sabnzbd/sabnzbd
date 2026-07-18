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
sabnzbd.database - Database Support
"""

import os
import tempfile
import time
import uuid
import zlib
import logging
import queue
import sys
import threading
import sqlite3
from contextlib import contextmanager
from sqlite3 import Connection, Cursor
from typing import Optional, Sequence, Any, Iterator

import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DB_HISTORY_NAME, STAGES, Status, PP_LOOKUP
from sabnzbd.bpsmeter import this_week, this_month
from sabnzbd.decorators import synchronized
from sabnzbd.encoding import ubtou, utob
from sabnzbd.misc import caller_name, opts_to_pp, to_units, bool_conv, match_str
from sabnzbd.filesystem import remove_file, clip_path

DB_LOCK = threading.Lock()


class HistoryDB:
    """Class to access the History database.
    Each class-instance creates its own database connection.
    Instances may move between threads (check_same_thread=False), but must
    only ever be used by one thread at a time. Normal code should not create
    instances directly but borrow one from sabnzbd.db_pool, which guarantees
    exclusive use through checkout.
    """

    # These class attributes will be accessed directly because
    # they need to be shared by all instances
    db_path = None  # Full path to history database
    startup_done = False

    @synchronized(DB_LOCK)
    def __init__(self):
        """Determine database path and create connection"""
        self.connection: Optional[Connection] = None
        self.cursor: Optional[Cursor] = None
        self.connect()

    def connect(self):
        """Create a connection to the database"""
        if not HistoryDB.db_path:
            HistoryDB.db_path = os.path.join(sabnzbd.cfg.admin_dir.get_path(), DB_HISTORY_NAME)
        create_table = not HistoryDB.startup_done and not os.path.exists(HistoryDB.db_path)

        # Remember which file this connection was opened against, so the pool
        # can discard it when the database path changes
        self.db_path_at_connect = HistoryDB.db_path

        # check_same_thread=False so pooled connections can move between threads;
        # exclusive use is guaranteed by HistoryDBPool checkout
        self.connection = sqlite3.connect(HistoryDB.db_path, check_same_thread=False)
        self.connection.isolation_level = None  # autocommit attribute only introduced in Python 3.12
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

        try:
            # Multiple readers can work simultaneously with one writer
            self.cursor.execute("PRAGMA journal_mode = WAL")
            # Sync to disk at critical moments, not every write
            self.cursor.execute("PRAGMA synchronous = NORMAL")
            # Wait for lock instead of failing at once
            self.cursor.execute("PRAGMA busy_timeout = 5000")
            # Keep up to ~4MiB in memory per connection
            self.cursor.execute("PRAGMA cache_size = -4000")
            # Stores temporary tables, indexes, and sorting operations in RAM
            self.cursor.execute("PRAGMA temp_store = MEMORY")
            # Reduce disk access
            self.cursor.execute("PRAGMA mmap_size = 16777216")
        except Exception:
            # Can fail on a readonly database; writes will report the error later
            logging.debug("Failed to set database pragmas", exc_info=True)

        # Perform initialization only once
        if not HistoryDB.startup_done:
            if create_table:
                self.create_history_db()

            # When an object (table, index, or trigger) is dropped from the database, it leaves behind empty space
            # http://www.sqlite.org/lang_vacuum.html
            self.execute("VACUUM")

            # See if we need to perform any updates
            self.execute("PRAGMA user_version;")
            try:
                version = self.cursor.fetchone()["user_version"]
            except (IndexError, TypeError):
                version = 0

            # Add any new columns added since last DB version
            # Use "and" to stop when database has been reset due to corruption
            if version < 1:
                _ = (
                    self.execute("PRAGMA user_version = 1;")
                    and self.execute("ALTER TABLE history ADD COLUMN series TEXT;")
                    and self.execute("ALTER TABLE history ADD COLUMN md5sum TEXT;")
                )
            if version < 2:
                _ = self.execute("PRAGMA user_version = 2;") and self.execute(
                    "ALTER TABLE history ADD COLUMN password TEXT;"
                )
            if version < 3:
                # Transfer data to new column (requires WHERE-hack), original column should be removed later
                _ = (
                    self.execute("PRAGMA user_version = 3;")
                    and self.execute("ALTER TABLE history ADD COLUMN duplicate_key TEXT;")
                    and self.execute("UPDATE history SET duplicate_key = series WHERE 1 = 1;")
                )
            if version < 4:
                _ = self.execute("PRAGMA user_version = 4;") and self.execute(
                    "ALTER TABLE history ADD COLUMN archive INTEGER;"
                )
            if version < 5:
                _ = self.execute("PRAGMA user_version = 5;") and self.execute(
                    "ALTER TABLE history ADD COLUMN time_added INTEGER;"
                )
            if version < 7:
                try:
                    self.connection.execute("BEGIN")
                    self.execute("PRAGMA user_version = 7", raise_on_error=True)
                    if self.execute(
                        """
                        WITH duplicates AS (SELECT id, ROW_NUMBER() OVER (PARTITION BY nzo_id ORDER BY id) AS rn FROM history)
                        SELECT id FROM duplicates WHERE rn > 1
                        """,
                        raise_on_error=True,
                    ):
                        for (row_id,) in self.cursor.fetchall():
                            self.execute(
                                "UPDATE history SET nzo_id = ? WHERE id = ?",
                                (str(uuid.uuid4()), row_id),
                                raise_on_error=True,
                            )
                    self.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_history_nzo_id ON history(nzo_id)",
                        raise_on_error=True,
                    )
                    self.execute(
                        "CREATE INDEX IF NOT EXISTS idx_history_archive_completed ON history(archive, completed DESC)",
                        raise_on_error=True,
                    )
                    self.connection.commit()
                except:
                    self.connection.rollback()
                    raise
            if version < 8:
                _ = self.execute("PRAGMA user_version = 8;") and self.create_rss_table()
                with sabnzbd.rss.rss_repository(self) as repo:
                    repo.import_rss_records()

            HistoryDB.startup_done = True

    def execute(self, command: str, args: Sequence = (), raise_on_error: bool = False) -> bool:
        """Wrapper for executing SQL commands"""
        # Lock contention is normally handled by SQLite itself through the
        # busy_timeout pragma; a single retry remains as a safety net
        for tries in (1, 0):
            try:
                self.cursor.execute(command, args)
                return True
            except Exception:
                error = str(sys.exc_info()[1])
                if tries > 0 and "is locked" in error:
                    logging.debug("Database locked, wait and retry")
                    time.sleep(0.5)
                    continue
                elif "readonly" in error:
                    logging.error(T("Cannot write to History database, check access rights!"))
                    if raise_on_error:
                        raise
                    # Report back success, because there's no recovery possible
                    return True
                elif match_str(error, ("not a database", "malformed", "no such table", "duplicate column name")):
                    logging.error(T("Damaged History database, created empty replacement"))
                    logging.info("Traceback: ", exc_info=True)
                    self.close()
                    try:
                        remove_file(HistoryDB.db_path)
                    except Exception:
                        pass
                    HistoryDB.startup_done = False
                    self.connect()
                    # Sibling pooled connections hold handles to the deleted file;
                    # mark them stale so they are discarded instead of reused
                    if sabnzbd.db_pool:
                        sabnzbd.db_pool.invalidate(reconnected=self)
                    if raise_on_error:
                        raise sqlite3.DatabaseError(error)
                    # Return False in case of "duplicate column" error
                    # because the column addition in connect() must be terminated
                    return True
                else:
                    logging.error(T("SQL Command Failed, see log"))
                    logging.info("SQL: %s", command)
                    logging.info("Arguments: %s", repr(args))
                    logging.info("Traceback: ", exc_info=True)
                    try:
                        self.connection.rollback()
                    except Exception:
                        # Can fail in case of automatic rollback
                        logging.debug("Rollback Failed:", exc_info=True)
                    if raise_on_error:
                        raise
            return False

    def create_history_db(self):
        """Create a new (empty) database file"""
        self.execute("""
        CREATE TABLE history (
            "id" INTEGER PRIMARY KEY,
            "completed" INTEGER NOT NULL,
            "name" TEXT NOT NULL,
            "nzb_name" TEXT NOT NULL,
            "category" TEXT,
            "pp" TEXT,
            "script" TEXT,
            "report" TEXT,
            "url" TEXT,
            "status" TEXT,
            "nzo_id" TEXT,
            "storage" TEXT,
            "path" TEXT,
            "script_log" BLOB,
            "script_line" TEXT,
            "download_time" INTEGER,
            "postproc_time" INTEGER,
            "stage_log" TEXT,
            "downloaded" INTEGER,
            "completeness" INTEGER,
            "fail_message" TEXT,
            "url_info" TEXT,
            "bytes" INTEGER,
            "meta" TEXT,
            "series" TEXT,
            "md5sum" TEXT,
            "password" TEXT,
            "duplicate_key" TEXT,
            "archive" INTEGER,
            "time_added" INTEGER
        )
        """)
        self.execute("PRAGMA user_version = 8;")
        self.execute("CREATE UNIQUE INDEX idx_history_nzo_id ON history(nzo_id);")
        self.execute("CREATE INDEX idx_history_archive_completed ON history(archive, completed DESC);")
        self.create_rss_table()

    def create_rss_table(self):
        """Create the rss history table"""
        return (
            self.execute("""
            CREATE TABLE rss (
                "id" INTEGER PRIMARY KEY,
                "feed" TEXT NOT NULL,
                "state" TEXT NOT NULL,
                "title" TEXT NOT NULL,
                "url" TEXT NOT NULL,
                "infourl" TEXT,
                "category" TEXT,
                "cat" TEXT,
                "pp" INTEGER,
                "script" TEXT,
                "priority" INTEGER,
                "season" INTEGER,
                "episode" INTEGER,
                "size" INTEGER,
                "rule" INTEGER,
                "age" INTEGER NOT NULL,
                "initial_scan" INTEGER,
                "seen_at" INTEGER NOT NULL,
                "downloaded_at" INTEGER,
                "archived_at" INTEGER,
                UNIQUE (feed, url)
            );
            """)
            and self.execute("CREATE INDEX idx_rss_feed ON rss(feed)")
            and self.execute("CREATE INDEX idx_rss_feed_state ON rss(feed, state)")
            and self.execute(
                "CREATE INDEX idx_rss_feed_state_downloaded_at_age ON rss(feed, state, downloaded_at DESC, age DESC)"
            )
        )

    def close(self):
        """Close database connection"""
        try:
            self.cursor.close()
            self.connection.close()
        except Exception:
            logging.error(T("Failed to close database, see log"))
            logging.info("Traceback: ", exc_info=True)

    def archive(self, job: str):
        """Move job to the archive"""
        self.execute("""UPDATE history SET archive = 1 WHERE nzo_id = ?""", (job,))
        logging.info("[%s] Moved job %s to archive", caller_name(), job)

    def remove(self, job: str):
        """Permanently remove job from the history"""
        self.execute("""DELETE FROM history WHERE nzo_id = ?""", (job,))
        logging.info("[%s] Removing job %s from history", caller_name(), job)

    def archive_with_status(self, status: str, search: Optional[str] = None):
        """Archive all jobs with a specific status, optional with `search` pattern"""
        search = convert_search(search)
        logging.info("Archiving all jobs with status=%s", status)
        self.execute(
            """UPDATE history SET archive = 1 WHERE archive IS NULL AND name LIKE ? AND status = ?""",
            (search, status),
        )

    def remove_with_status(self, status: str, search: Optional[str] = None):
        """Remove all jobs from the database with a specific status, optional with `search` pattern"""
        search = convert_search(search)
        logging.info("Removing all jobs with status=%s", status)
        self.execute("""DELETE FROM history WHERE name LIKE ? AND status = ?""", (search, status))

    def mark_as_completed(self, job: str):
        """Mark a job as completed in the history"""
        self.execute("""UPDATE history SET status = ? WHERE nzo_id = ?""", (Status.COMPLETED, job))
        logging.info("[%s] Marked job %s as completed", caller_name(), job)

    def get_failed_paths(self, search: Optional[str] = None) -> list[str]:
        """Return list of all storage paths of failed jobs (may contain non-existing or empty paths)"""
        search = convert_search(search)
        fetch_ok = self.execute(
            """SELECT path FROM history WHERE name LIKE ? AND status = ?""", (search, Status.FAILED)
        )
        if fetch_ok:
            return [item["path"] for item in self.cursor.fetchall()]
        else:
            return []

    def auto_history_purge(self):
        """Archive or remove history items based on the configured history-retention"""
        history_retention_option = sabnzbd.cfg.history_retention_option()
        to_keep = sabnzbd.cfg.history_retention_number()

        if history_retention_option == "all":
            return
        elif history_retention_option == "number-archive":
            # Archive if more than X jobs
            logging.info("Archiving all but last %s completed jobs", to_keep)
            self.execute(
                """UPDATE history SET archive = 1 WHERE status = ? AND  archive IS NULL AND id NOT IN (
                    SELECT id FROM history WHERE status = ? AND archive IS NULL ORDER BY completed DESC LIMIT ?
                )""",
                (Status.COMPLETED, Status.COMPLETED, to_keep),
            )
        elif history_retention_option == "number-delete":
            # Delete if more than X jobs
            logging.info("Removing all but last %s completed jobs from history", to_keep)
            self.execute(
                """DELETE FROM history WHERE status = ? AND id NOT IN (
                    SELECT id FROM history WHERE status = ? ORDER BY completed DESC LIMIT ?
                )""",
                (Status.COMPLETED, Status.COMPLETED, to_keep),
            )
        elif history_retention_option == "days-archive":
            # Archive jobs older dan X days
            seconds_to_keep = int(time.time()) - to_keep * 86400
            logging.info("Archiving completed jobs older than %s days from history", to_keep)
            self.execute(
                """UPDATE history SET archive = 1 WHERE status = ? AND archive IS NULL AND completed < ?""",
                (Status.COMPLETED, seconds_to_keep),
            )
        elif history_retention_option == "days-delete":
            # Delete jobs older dan X days
            seconds_to_keep = int(time.time()) - to_keep * 86400
            logging.info("Removing completed jobs older than %s days from history", to_keep)
            self.execute(
                """DELETE FROM history WHERE status = ? AND completed < ?""",
                (Status.COMPLETED, seconds_to_keep),
            )
        elif history_retention_option == "all-archive":
            # Archive all non-failed ones
            self.archive_with_status(Status.COMPLETED)
        elif history_retention_option == "all-delete":
            # Delete all non-failed ones
            self.remove_with_status(Status.COMPLETED)

    def add_history_db(self, nzo, storage: str, postproc_time: int, script_output: str, script_line: str):
        """Add a new job entry to the database"""
        t = build_history_info(nzo, storage, postproc_time, script_output, script_line)

        self.execute(
            """INSERT INTO history (completed, name, nzb_name, category, pp, script, report,
            url, status, nzo_id, storage, path, script_log, script_line, download_time, postproc_time, stage_log,
            downloaded, fail_message, url_info, bytes, duplicate_key, md5sum, password, time_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            t,
        )
        logging.info("Added job %s to history", nzo.final_name)

    def fetch_history(
        self,
        start: Optional[int] = None,
        limit: Optional[int] = None,
        archive: Optional[bool] = None,
        search: Optional[str] = None,
        categories: Optional[list[str]] = None,
        statuses: Optional[list[str]] = None,
        nzo_ids: Optional[list[str]] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return records for specified jobs"""
        command_args = [convert_search(search)]

        post = ""
        if archive:
            post += " AND archive = 1"
        else:
            post += " AND archive IS NULL"
        if categories:
            categories = ["*" if c == "Default" else c for c in categories]
            post += " AND (category = ?"
            post += " OR category = ? " * (len(categories) - 1)
            post += ")"
            command_args.extend(categories)
        if statuses:
            post += " AND (status = ?"
            post += " OR status = ? " * (len(statuses) - 1)
            post += ")"
            command_args.extend(statuses)
        if nzo_ids:
            post += " AND (nzo_id = ?"
            post += " OR nzo_id = ? " * (len(nzo_ids) - 1)
            post += ")"
            command_args.extend(nzo_ids)

        cmd = "SELECT COUNT(*) FROM history WHERE name LIKE ?"
        total_items = -1
        if self.execute(cmd + post, command_args):
            total_items = self.cursor.fetchone()["COUNT(*)"]

        if not start:
            start = 0
        if not limit:
            limit = total_items

        command_args.extend([start, limit])
        cmd = "SELECT * FROM history WHERE name LIKE ?"
        if self.execute(cmd + post + " ORDER BY completed desc LIMIT ?, ?", command_args):
            items = self.cursor.fetchall()
        else:
            items = []

        # Unpack the single line stage log
        # Stage Name is separated by ::: stage lines by ; and stages by \r\n
        items = [unpack_history_info(item) for item in items]

        return items, total_items

    def get_retryable_jobs(self) -> list[dict[str, Any]]:
        """Return the nzo_id and path of all history items that can be retried,
        failed jobs whose incomplete folder still exists and failed URL-fetches
        """
        jobs = []
        if self.execute(
            "SELECT nzo_id, path, report FROM history WHERE archive IS NULL AND (status = ? OR report = 'future')",
            (Status.FAILED,),
        ):
            for item in self.cursor:
                if item["report"] == "future" or (item["path"] and os.path.exists(item["path"])):
                    jobs.append({"nzo_id": item["nzo_id"], "path": item["path"]})
        return jobs

    def have_duplicate_key(self, duplicate_key: str) -> bool:
        """Check whether History contains this duplicate key"""
        if self.execute(
            """
            SELECT EXISTS(
                SELECT 1
                FROM history
                WHERE duplicate_key = ? AND status != ?
            ) as found
            """,
            (duplicate_key, Status.FAILED),
        ):
            return bool(self.cursor.fetchone()["found"])
        return False

    def have_name_or_md5sum(self, name: str, md5sum: str) -> bool:
        """Check whether this name or md5sum is already in History"""
        if self.execute(
            """
            SELECT EXISTS(
                SELECT 1
                FROM history
                WHERE (name = ? COLLATE NOCASE OR md5sum = ?)
                  AND status != ?
            ) as found
            """,
            (name, md5sum, Status.FAILED),
        ):
            return bool(self.cursor.fetchone()["found"])
        return False

    def get_history_size(self) -> tuple[int, int, int]:
        """Returns the total size of the history and
        amounts downloaded in the last month and week
        """
        # Total Size of the history
        total = 0
        if self.execute("""SELECT sum(bytes) FROM history"""):
            total = self.cursor.fetchone()["sum(bytes)"]

        # Amount downloaded this month
        month_timest = int(this_month(time.time()))

        month = 0
        if self.execute("""SELECT sum(bytes) FROM history WHERE completed > ?""", (month_timest,)):
            month = self.cursor.fetchone()["sum(bytes)"]

        # Amount downloaded this week
        week_timest = int(this_week(time.time()))

        week = 0
        if self.execute("""SELECT sum(bytes) FROM history WHERE completed > ?""", (week_timest,)):
            week = self.cursor.fetchone()["sum(bytes)"]

        return total, month, week

    def get_script_log(self, nzo_id: str) -> str:
        """Return decompressed log file"""
        data = ""
        if self.execute("""SELECT script_log FROM history WHERE nzo_id = ?""", (nzo_id,)):
            try:
                data = ubtou(zlib.decompress(self.cursor.fetchone()["script_log"]))
            except Exception:
                pass
        return data

    def get_name(self, nzo_id: str) -> str:
        """Return name of the job `nzo_id`"""
        name = ""
        if self.execute("""SELECT name FROM history WHERE nzo_id = ?""", (nzo_id,)):
            try:
                return self.cursor.fetchone()["name"]
            except TypeError:
                # No records found
                pass
        return name

    def get_incomplete_path(self, nzo_id: str) -> str:
        """Return the `incomplete` path of the job `nzo_id` if
        the job failed and if the path is still there"""
        path = ""
        if self.execute("""SELECT path FROM history WHERE nzo_id = ?  AND status = ?""", (nzo_id, Status.FAILED)):
            try:
                path = self.cursor.fetchone()["path"]
            except TypeError:
                # No records found
                pass
        if os.path.exists(path):
            return path
        return path

    def get_other(self, nzo_id: str) -> tuple[str, str, str, str, str]:
        """Return additional data for job `nzo_id`"""
        if self.execute("""SELECT * FROM history WHERE nzo_id = ?""", (nzo_id,)):
            try:
                item = self.cursor.fetchone()
                return item["report"], item["url"], item["pp"], item["script"], item["category"]
            except TypeError:
                # No records found
                pass
        return "", "", "", "", ""

    def __enter__(self):
        """For context manager support"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """For context manager support, ignore any exception"""
        self.close()


class HistoryDBPool:
    """Bounded LIFO pool of HistoryDB connections, available as sabnzbd.db_pool.

    Thread-safety comes from exclusive checkout: a connection is only ever used
    by one borrower at a time. LIFO keeps hot connections hot, and since SQLite
    serializes writers anyway a handful of connections is plenty. When the pool
    is exhausted, checkout waits briefly and then falls back to a temporary
    overflow connection (closed on check-in) so requests degrade instead of
    deadlocking. Connections are created lazily, so the pool can be constructed
    before the configuration (database path) is known.
    """

    def __init__(self, max_connections: int = 5, checkout_timeout: float = 10.0):
        self.max_connections = max_connections
        self.checkout_timeout = checkout_timeout
        self._idle: queue.LifoQueue = queue.LifoQueue()
        self._lock = threading.Lock()
        self._created = 0
        self._generation = 0
        self._closed = False

    @contextmanager
    def connection(self) -> Iterator[HistoryDB]:
        """Borrow a connection for exclusive use: with sabnzbd.db_pool.connection() as history_db"""
        db, pooled = self._checkout()
        try:
            yield db
        finally:
            self._checkin(db, pooled)

    def _new_connection(self) -> HistoryDB:
        db = HistoryDB()
        db.pool_generation = self._generation
        return db

    def _is_stale(self, db: HistoryDB) -> bool:
        """Stale connections predate invalidate(), or hold handles to a
        replaced database file or a since-changed database path"""
        return getattr(db, "pool_generation", -1) != self._generation or db.db_path_at_connect != HistoryDB.db_path

    def _discard(self, db: HistoryDB):
        db.close()
        with self._lock:
            self._created -= 1

    def _checkout(self) -> tuple[HistoryDB, bool]:
        if self._closed:
            # Shutting down: serve a temporary connection so late requests still work
            return HistoryDB(), False

        deadline = time.time() + self.checkout_timeout
        while True:
            # Prefer an idle pooled connection
            try:
                db = self._idle.get_nowait()
            except queue.Empty:
                db = None
            if db is not None:
                if self._is_stale(db):
                    self._discard(db)
                    continue
                return db, True

            # Nothing idle: create a new one if the pool is not full yet.
            # Connect outside the pool lock: connecting can trigger schema
            # migration or corruption recovery, which calls invalidate()
            with self._lock:
                create = self._created < self.max_connections
                if create:
                    self._created += 1
            if create:
                try:
                    return self._new_connection(), True
                except Exception:
                    with self._lock:
                        self._created -= 1
                    raise

            # Pool full: wait for a connection to be returned
            timeout = deadline - time.time()
            if timeout <= 0:
                logging.debug("HistoryDB pool exhausted, using overflow connection")
                return HistoryDB(), False
            try:
                db = self._idle.get(timeout=timeout)
            except queue.Empty:
                continue
            if self._is_stale(db):
                self._discard(db)
                continue
            return db, True

    def _checkin(self, db: HistoryDB, pooled: bool):
        if not pooled:
            # Overflow connection, never pooled
            db.close()
        elif self._closed or self._is_stale(db):
            self._discard(db)
        else:
            self._idle.put(db)

    def invalidate(self, reconnected: Optional[HistoryDB] = None):
        """Discard all pooled connections, e.g. after the database file was
        replaced due to corruption. Connections currently checked out are
        discarded on check-in. The connection that triggered the replacement
        has already reconnected and stays valid."""
        with self._lock:
            self._generation += 1
            generation = self._generation
        if reconnected is not None:
            reconnected.pool_generation = generation
        # Drain the stale idle connections
        while True:
            try:
                db = self._idle.get_nowait()
            except queue.Empty:
                break
            if self._is_stale(db):
                self._discard(db)
            else:
                self._idle.put(db)
                break

    def close(self):
        """Close all idle connections; called at shutdown. Connections still
        checked out are closed on check-in, later checkouts get temporary
        overflow connections."""
        self._closed = True
        while True:
            try:
                db = self._idle.get_nowait()
            except queue.Empty:
                break
            self._discard(db)


def convert_search(search: Optional[str]) -> str:
    """Convert classic wildcard to SQL wildcard"""
    if not search or not isinstance(search, str):
        # Default value
        search = ""
    else:
        # Allow * for wildcard matching and space
        search = search.replace("*", "%").replace(" ", "%")

    # Allow ^ for start of string and $ for end of string
    if search and search.startswith("^"):
        search = search.replace("^", "")
        search += "%"
    elif search and search.endswith("$"):
        search = search.replace("$", "")
        search = "%" + search
    else:
        search = "%" + search + "%"
    return search


def build_history_info(
    nzo: "sabnzbd.nzb.NzbObject",
    workdir_complete: str,
    postproc_time: int,
    script_output: str,
    script_line: str,
):
    """Collects all the information needed for the database"""
    completed = int(time.time())
    pp = PP_LOOKUP.get(opts_to_pp(nzo.repair, nzo.unpack, nzo.delete), "X")

    if script_output:
        # Compress the output of the script
        script_output = sqlite3.Binary(zlib.compress(utob(script_output)))

    download_time = nzo.nzo_info.get("download_time", 0)
    url_info = nzo.nzo_info.get("details", "") or nzo.nzo_info.get("more_info", "")

    # Get the dictionary containing the stages and their unpack process
    # Pack the dictionary up into a single string
    # Stage Name is separated by ::: stage lines by ; and stages by \r\n
    lines = []
    for key, results in nzo.unpack_info.items():
        lines.append("%s:::%s" % (key, ";".join(results)))
    stage_log = "\r\n".join(lines)

    # Reuse the old 'report' column to indicate a URL-fetch
    report = "future" if nzo.futuretype else ""

    # Make sure we have the duplicate key
    nzo.set_duplicate_key()

    return (
        completed,
        nzo.final_name,
        nzo.filename,
        nzo.cat,
        pp,
        nzo.script,
        report,
        nzo.url,
        nzo.status,
        nzo.nzo_id,
        clip_path(workdir_complete),
        clip_path(nzo.download_path),
        script_output,
        script_line,
        download_time,
        postproc_time,
        stage_log,
        nzo.bytes_downloaded,
        nzo.fail_msg,
        url_info,
        nzo.bytes_downloaded,
        nzo.duplicate_key,
        nzo.md5sum,
        nzo.correct_password,
        nzo.time_added,
    )


def unpack_history_info(item: sqlite3.Row) -> dict[str, Any]:
    """Expands the single line stage_log from the DB
    into a python dictionary for use in the history display
    """
    # Convert result to dictionary
    item = dict(item)

    # Stage Name is separated by ::: stage lines by ; and stages by \r\n
    lst = item["stage_log"]
    if lst:
        parsed_stage_log = []
        try:
            all_stages_lines = lst.split("\r\n")
        except Exception:
            logging.warning(T("Invalid stage logging in history for %s"), item["name"])
            logging.debug("Lines: %s", lst)
            all_stages_lines = []

        for stage_lines in all_stages_lines:
            try:
                key, logs = stage_lines.split(":::")
            except Exception:
                logging.info('Missing key:::logs "%s"', stage_lines)
                continue
            stage = {"name": key, "actions": []}
            try:
                stage["actions"] = logs.split(";")
            except Exception:
                logging.warning(T("Invalid stage logging in history for %s"), item["name"])
                logging.debug("Logs: %s", logs)
            parsed_stage_log.append(stage)

        # Sort it so it is more logical
        parsed_stage_log.sort(key=lambda stage_log: STAGES.get(stage_log["name"], 100))
        item["stage_log"] = parsed_stage_log
    else:
        item["stage_log"] = []

    # Remove database id
    item.pop("id")

    # Human-readable size
    item["size"] = to_units(item["bytes"], "B")

    # We do not want the raw script output here
    item.pop("script_log")

    # The action line and loaded is only available for items in the postproc queue
    item["action_line"] = ""
    item["loaded"] = False
    item["archive"] = bool(item["archive"])

    # Retry and retry for failed URL-fetch
    item["retry"] = bool_conv(item["status"] == Status.FAILED and item["path"] and os.path.exists(item["path"]))
    if item["report"] == "future":
        item["retry"] = True

    return item


def scheduled_history_purge():
    with sabnzbd.db_pool.connection() as history_db:
        history_db.auto_history_purge()


def history_db_snapshot() -> Optional[bytes]:
    """Return a consistent snapshot of the history database as bytes, for backups.

    Under WAL the main database file alone misses any transactions that have not
    been checkpointed yet, so a raw file copy would silently lose recent history
    (and could even be inconsistent when copied mid-checkpoint). SQLite's online
    backup API produces a consistent, checkpointed, single-file copy that is safe
    to take while other connections are reading or writing.
    """
    snapshot_fd, snapshot_path = tempfile.mkstemp(suffix=".db")
    os.close(snapshot_fd)
    try:
        with sabnzbd.db_pool.connection() as history_db:
            snapshot_connection = sqlite3.connect(snapshot_path)
            try:
                history_db.connection.backup(snapshot_connection)
            finally:
                snapshot_connection.close()
        with open(snapshot_path, "rb") as snapshot_data:
            return snapshot_data.read()
    except Exception:
        logging.info("Failed to snapshot history database: ", exc_info=True)
        return None
    finally:
        try:
            remove_file(snapshot_path)
        except Exception:
            pass
