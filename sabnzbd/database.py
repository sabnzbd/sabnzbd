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
import time
import datetime
import zlib
import logging
import sys
import threading
import sqlite3
from sqlite3 import Connection, Cursor
from typing import Optional, Sequence, Any, Generator, Iterable
from more_itertools import batched

import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DB_HISTORY_NAME, STAGES, Status, PP_LOOKUP, RSS_FILE_NAME
from sabnzbd.bpsmeter import this_week, this_month
from sabnzbd.decorators import synchronized
from sabnzbd.encoding import ubtou, utob
from sabnzbd.misc import caller_name, opts_to_pp, to_units, bool_conv, match_str, int_conv
from sabnzbd.filesystem import remove_file, clip_path
from sabnzbd.rssmodels import (
    ResolvedEntry,
    RSSState,
    normalise_priority,
    normalise_pp,
    normalise_str_or_none,
    _RE_BR,
    _RE_TAG,
)

DB_LOCK = threading.Lock()


class HistoryDB:
    """Class to access the History database
    Each class-instance will create an access channel that
    can be used in one thread.
    Each thread needs its own class-instance!
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

        self.connection = sqlite3.connect(HistoryDB.db_path)
        self.connection.isolation_level = None  # autocommit attribute only introduced in Python 3.12
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

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
            if version < 6:
                _ = (
                    self.execute("PRAGMA user_version = 6;")
                    and self.execute("CREATE UNIQUE INDEX idx_history_nzo_id ON history(nzo_id);")
                    and self.execute("CREATE INDEX idx_history_archive_completed ON history(archive, completed DESC);")
                )
            if version < 7:
                _ = self.execute("PRAGMA user_version = 6;") and self.create_rss_table() and self.import_rss_records()

            for feed in self.rss_get_feeds():
                self.rss_remove_obsolete(feed)

            HistoryDB.startup_done = True

    def execute(self, command: str, args: Sequence = ()) -> bool:
        """Wrapper for executing SQL commands"""
        for tries in (4, 3, 2, 1, 0):
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
            return False
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
        self.execute("PRAGMA user_version = 7;")
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
                "state" TEXT NOT NULL
                         CHECK (state IN (
                         'G',  -- Good
                         'B',  -- Bad
                         'D',  -- Downloaded
                         'X'  -- Expired
                         )),
                "title" TEXT NOT NULL,
                "url" TEXT NOT NULL,
                "infourl" TEXT,
                "category" TEXT,
                "orgcat" TEXT,
                "pp" TEXT,
                "script" TEXT,
                "priority" TEXT,
                "season" INTEGER,
                "episode" INTEGER,
                "size" INTEGER,
                "rule" INTEGER,
                "age" INTEGER NOT NULL,
                "initial_scan" INTEGER,
                "created_at" INTEGER NOT NULL,
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

    def import_rss_records(self):
        """Migrate old RSS database"""
        try:
            jobs = sabnzbd.filesystem.load_admin(RSS_FILE_NAME) or {}
            local_tz = datetime.datetime.now().astimezone().tzinfo
            for feed, jobs in jobs.items():
                for link, job in jobs.items():
                    orgcat = job.get("orgcat", None) or None
                    if orgcat in ("", "*"):
                        orgcat = None
                    if orgcat is not None and len(orgcat) > 128:
                        # Probably HTML content
                        orgcat = _RE_TAG.sub("", _RE_BR.split(orgcat, maxsplit=1)[0]).strip()
                    entry = ResolvedEntry(
                        feed=feed,
                        link=link.strip().replace(" ", "%20"),
                        title=job.get("title", ""),
                        infourl=job.get("infourl", None),
                        size=job.get("size", 0),
                        age=(
                            # datetime.datetime: with no tzinfo
                            job.get("age").replace(tzinfo=local_tz).astimezone(datetime.timezone.utc)
                            if job.get("age", None)
                            else None
                        ),
                        season=job.get("season", 0),
                        episode=job.get("episode", 0),
                        orgcat=orgcat,
                        cat=normalise_str_or_none(job.get("cat", None)),
                        pp=normalise_pp(job.get("pp", None)),
                        script=normalise_str_or_none(job.get("script", None)),
                        priority=normalise_priority(job.get("prio", None)),
                        rule=int_conv(job.get("rule", None)),
                        state=RSSState(job.get("status", "")[:1]),
                        downloaded_at=(
                            # time.struct_time
                            datetime.datetime(
                                *job.get("time_downloaded")[:6],
                                tzinfo=datetime.timezone(
                                    datetime.timedelta(seconds=job.get("time_downloaded").tm_gmtoff)
                                ),
                            ).astimezone(datetime.timezone.utc)
                            if job.get("time_downloaded", None)
                            else None
                        ),
                        created_at=(
                            # float timestamp
                            datetime.datetime.fromtimestamp(job.get("time", 0))
                            .replace(tzinfo=local_tz)
                            .astimezone(datetime.timezone.utc)
                        ),
                        initial_scan=False,
                    )
                    self.rss_upsert(entry)
        except Exception:
            logging.warning(T("Cannot read %s"), RSS_FILE_NAME)
            logging.info("Traceback: ", exc_info=True)

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

    def rss_get_job(self, feed: str, url: str) -> Optional[ResolvedEntry]:
        if not feed or not url:
            return None
        if self.execute("SELECT * FROM rss WHERE feed = ? AND url = ?", (feed, url)):
            row = self.cursor.fetchone()
            if row is None:
                return None
            return ResolvedEntry.from_sqlite(row)
        return None

    def rss_get_jobs(
        self,
        feed: Optional[str] = None,
        search: Optional[str] = None,
        states: Optional[list[RSSState]] = None,
    ) -> Generator[ResolvedEntry, Any, None]:
        """Return records for specified jobs"""
        command_args = []
        where_clauses = []

        if search is not None:
            where_clauses.append("title LIKE ?")
            command_args.append(convert_search(search))

        if feed:
            where_clauses.append("feed = ?")
            command_args.append(feed)

        if states:
            placeholders = " OR ".join(["state = ?"] * len(states))
            where_clauses.append(f"({placeholders})")
            command_args.extend(states)

        # Combine all WHERE clauses
        where_sql = " AND ".join(where_clauses)

        # Final query
        cmd = f"SELECT * FROM rss WHERE {where_sql} ORDER BY downloaded_at DESC, age DESC"

        if self.execute(cmd, command_args):
            for item in self.cursor:
                yield ResolvedEntry.from_sqlite(item)

    def rss_get_feeds(self) -> list[str]:
        self.execute("SELECT DISTINCT feed from rss")
        return [row["feed"] for row in self.cursor]

    def rss_has_feed(self, feed: str) -> bool:
        self.execute("SELECT EXISTS(SELECT 1 FROM rss WHERE feed = ?) AS found", (feed,))
        return bool(self.cursor.fetchone()["found"])

    def rss_upsert(self, entry: ResolvedEntry):
        """Add or update a rss job entry in the database"""
        t = self.rss_build_job_info(entry)

        self.execute(
            """
            INSERT INTO rss (
                feed, state, title, url, infourl, category, orgcat, pp, script, priority,
                season, episode, size, rule, age, initial_scan, created_at, downloaded_at, archived_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(feed, url) DO UPDATE SET
                state         = excluded.state,
                title         = excluded.title,
                infourl       = excluded.infourl,
                category      = excluded.category,
                orgcat        = excluded.orgcat,
                pp            = excluded.pp,
                script        = excluded.script,
                priority      = excluded.priority,
                season        = excluded.season,
                episode       = excluded.episode,
                size          = excluded.size,
                rule          = excluded.rule,
                age           = excluded.age,
                initial_scan  = excluded.initial_scan,
                downloaded_at = COALESCE(excluded.downloaded_at, rss.downloaded_at),
                archived_at = COALESCE(excluded.archived_at, rss.archived_at)
            """,
            t,
        )

    @staticmethod
    def rss_build_job_info(entry: ResolvedEntry):
        """Collects all the information needed for the database"""
        return (
            entry.feed,
            entry.state,
            entry.title,
            entry.link,
            entry.infourl,
            entry.cat,
            entry.orgcat,
            entry.pp,
            entry.script,
            entry.priority,
            entry.season,
            entry.episode,
            entry.size,
            entry.rule,
            int(entry.age.timestamp()),
            entry.initial_scan,
            # created_at is ignored for updates
            int(entry.created_at.timestamp()),
            int(entry.downloaded_at.timestamp()) if entry.downloaded_at else None,
            int(entry.archived_at.timestamp()) if entry.archived_at else None,
        )

    def rss_delete_feed(self, feed: str):
        """Permanently remove job from the history"""
        self.execute("""DELETE FROM rss WHERE feed = ?""", (feed,))

    def rss_rename_feed(self, old_feed: str, new_feed: str):
        """Rename all rows for a given feed to a new feed name."""
        self.execute("""UPDATE rss SET feed = ? WHERE feed = ?""", (new_feed, old_feed))

    def rss_show_result(self, feed: str) -> Generator[ResolvedEntry, Any, None]:
        if self.execute(
            """
            SELECT * 
            FROM rss 
            WHERE feed = ? 
            AND state IN (?, ?, ?)
            AND archived_at IS NULL
            ORDER BY downloaded_at DESC, age DESC
            """,
            (feed, RSSState.GOOD, RSSState.BAD, RSSState.DOWNLOADED),
        ):
            for row in self.cursor:
                yield ResolvedEntry.from_sqlite(row)

    def rss_flag_downloaded(self, feed: str, url: str):
        if not feed or not url:
            return
        self.execute(
            "UPDATE rss SET state = ?, downloaded_at = ? WHERE feed = ? AND url = ?",
            (
                RSSState.DOWNLOADED,
                int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                feed,
                url,
            ),
        )

    def rss_clear_feed(self, feed: str):
        """Remove any previous references to this feed name, and start fresh."""
        self.rss_delete_feed(feed)

    def rss_clear_downloaded(self, feed: str):
        """Mark downloaded jobs so that they won't be displayed any more."""
        self.execute(
            "UPDATE rss SET archived_at = ? WHERE feed = ? AND state = ?",
            (
                int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                feed,
                RSSState.DOWNLOADED,
            ),
        )

    def rss_is_duplicate(self, entry: ResolvedEntry) -> bool:
        """
        Check if a job with the same title and size already exists in another feed

        Allow 5% size deviation because indexers might have small differences for same release
        """
        self.execute(
            "SELECT EXISTS(SELECT 1 FROM rss WHERE title = ? AND url <> ? AND size BETWEEN ? AND ?) AS found",
            (entry.title, entry.link, entry.size * 0.95, entry.size * 1.05),
        )
        return bool(self.cursor.fetchone()["found"])

    def rss_remove_obsolete(self, feed: str, new_urls: Optional[Iterable[str]] = None):
        """
        Expire G/B links that are not in new_jobs (mark them 'X')

        Expired links older than 3 days are removed
        """
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        limit = now - 3 * 24 * 3600  # 3 days in seconds

        if new_urls:
            # Create temporary table for all new URLs
            self.execute("CREATE TEMP TABLE temp_urls(url TEXT PRIMARY KEY)")

            # Insert all new URLs in batches; SQLite can "only" do 999 per query
            for batch in batched(new_urls, 500):
                placeholders = ",".join(["(?)"] * len(batch))
                self.execute(f"INSERT INTO temp_urls(url) VALUES {placeholders}", batch)

            # Update rss to mark G/B not in temp_urls as X
            self.execute(
                """
                UPDATE rss
                SET state = ?
                WHERE feed = ?
                  AND state IN (?, ?)
                  AND url NOT IN (SELECT url FROM temp_urls)
            """,
                (
                    RSSState.EXPIRED,
                    feed,
                    RSSState.GOOD,
                    RSSState.BAD,
                ),
            )

            # Drop temp table
            self.execute("DROP TABLE temp_urls")

        # Purge
        if not self.execute(
            """
            SELECT url FROM rss
            WHERE feed = ?
              AND state = ?
              AND age < ?
        """,
            (
                feed,
                RSSState.EXPIRED,
                limit,
            ),
        ):
            return

        expired_urls = [row["url"] for row in self.cursor]
        for url in expired_urls:
            logging.debug("Purging link %s", url)
            self.execute("DELETE FROM rss WHERE feed = ? AND url = ?", (feed, url))

    def __enter__(self):
        """For context manager support"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """For context manager support, ignore any exception"""
        self.close()


def convert_search(search: str) -> str:
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
    with HistoryDB() as history_db:
        history_db.auto_history_purge()
