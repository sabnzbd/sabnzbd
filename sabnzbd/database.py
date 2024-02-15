#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
import zlib
import logging
import sys
import threading
import sqlite3
from sqlite3 import Connection, Cursor
from typing import Optional, List, Sequence, Dict, Any, Tuple

import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DB_HISTORY_NAME, STAGES, Status, PP_LOOKUP
from sabnzbd.bpsmeter import this_week, this_month
from sabnzbd.decorators import synchronized
from sabnzbd.encoding import ubtou, utob
from sabnzbd.misc import int_conv, caller_name, opts_to_pp, to_units
from sabnzbd.filesystem import remove_file, clip_path

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

    def execute(self, command: str, args: Sequence = ()) -> bool:
        """Wrapper for executing SQL commands"""
        for tries in (4, 3, 2, 1, 0):
            try:
                self.cursor.execute(command, args)
                return True
            except:
                error = str(sys.exc_info()[1])
                if tries > 0 and "is locked" in error:
                    logging.debug("Database locked, wait and retry")
                    time.sleep(0.5)
                    continue
                elif "readonly" in error:
                    logging.error(T("Cannot write to History database, check access rights!"))
                    # Report back success, because there's no recovery possible
                    return True
                elif "not a database" in error or "malformed" in error or "duplicate column name" in error:
                    logging.error(T("Damaged History database, created empty replacement"))
                    logging.info("Traceback: ", exc_info=True)
                    self.close()
                    try:
                        remove_file(HistoryDB.db_path)
                    except:
                        pass
                    HistoryDB.startup_done = False
                    self.connect()
                    # Return False in case of "duplicate column" error
                    # because the column addition in connect() must be terminated
                    return "duplicate column name" not in error
                else:
                    logging.error(T("SQL Command Failed, see log"))
                    logging.info("SQL: %s", command)
                    logging.info("Arguments: %s", repr(args))
                    logging.info("Traceback: ", exc_info=True)
                    try:
                        self.connection.rollback()
                    except:
                        # Can fail in case of automatic rollback
                        logging.debug("Rollback Failed:", exc_info=True)
            return False

    def create_history_db(self):
        """Create a new (empty) database file"""
        self.execute(
            """
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
            "archive" INTEGER
        )
        """
        )
        self.execute("PRAGMA user_version = 4;")

    def close(self):
        """Close database connection"""
        try:
            self.cursor.close()
            self.connection.close()
        except:
            logging.error(T("Failed to close database, see log"))
            logging.info("Traceback: ", exc_info=True)

    def remove_completed(self, search=None):
        """Remove all completed jobs from the database, optional with `search` pattern"""
        search = convert_search(search)
        logging.info("Removing all completed jobs from history")
        return self.execute("""DELETE FROM history WHERE name LIKE ? AND status = ?""", (search, Status.COMPLETED))

    def get_failed_paths(self, search=None):
        """Return list of all storage paths of failed jobs (may contain non-existing or empty paths)"""
        search = convert_search(search)
        fetch_ok = self.execute(
            """SELECT path FROM history WHERE name LIKE ? AND status = ?""", (search, Status.FAILED)
        )
        if fetch_ok:
            return [item["path"] for item in self.cursor.fetchall()]
        else:
            return []

    def remove_failed(self, search=None):
        """Remove all failed jobs from the database, optional with `search` pattern"""
        search = convert_search(search)
        logging.info("Removing all failed jobs from history")
        return self.execute("""DELETE FROM history WHERE name LIKE ? AND status = ?""", (search, Status.FAILED))

    def remove_history(self, jobs=None):
        """Remove all jobs in the list `jobs`, empty list will remove all completed jobs"""
        if jobs is None:
            self.remove_completed()
        else:
            if not isinstance(jobs, list):
                jobs = [jobs]

            for job in jobs:
                self.execute("""DELETE FROM history WHERE nzo_id = ?""", (job,))
                logging.info("[%s] Removing job %s from history", caller_name(), job)

    def auto_history_purge(self):
        """Remove history items based on the configured history-retention"""
        if sabnzbd.cfg.history_retention() == "0":
            return

        if sabnzbd.cfg.history_retention() == "-1":
            # Delete all non-failed ones
            self.remove_completed()

        if "d" in sabnzbd.cfg.history_retention():
            # How many days to keep?
            days_to_keep = int_conv(sabnzbd.cfg.history_retention().strip()[:-1])
            seconds_to_keep = int(time.time()) - days_to_keep * 86400
            if days_to_keep > 0:
                logging.info("Removing completed jobs older than %s days from history", days_to_keep)
                return self.execute(
                    """DELETE FROM history WHERE status = ? AND completed < ?""", (Status.COMPLETED, seconds_to_keep)
                )
        else:
            # How many to keep?
            to_keep = int_conv(sabnzbd.cfg.history_retention())
            if to_keep > 0:
                logging.info("Removing all but last %s completed jobs from history", to_keep)
                return self.execute(
                    """DELETE FROM history WHERE status = ? AND id NOT IN (
                        SELECT id FROM history WHERE status = ? ORDER BY completed DESC LIMIT ?
                    )""",
                    (Status.COMPLETED, Status.COMPLETED, to_keep),
                )

    def add_history_db(self, nzo, storage: str, postproc_time: int, script_output: str, script_line: str):
        """Add a new job entry to the database"""
        t = build_history_info(nzo, storage, postproc_time, script_output, script_line)

        self.execute(
            """INSERT INTO history (completed, name, nzb_name, category, pp, script, report,
            url, status, nzo_id, storage, path, script_log, script_line, download_time, postproc_time, stage_log,
            downloaded, fail_message, url_info, bytes, duplicate_key, md5sum, password)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            t,
        )
        logging.info("Added job %s to history", nzo.final_name)

    def fetch_history(
        self,
        start: Optional[int] = None,
        limit: Optional[int] = None,
        archive: Optional[bool] = None,
        search: Optional[str] = None,
        categories: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        nzo_ids: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return records for specified jobs"""
        command_args = [convert_search(search)]

        post = ""
        if archive:
            post += " AND archive = 1"
        if categories:
            categories = ["*" if c == "Default" else c for c in categories]
            post = " AND (category = ?"
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
        total = 0
        if self.execute(
            """
            SELECT COUNT(*) 
            FROM History 
            WHERE 
                duplicate_key = ? AND 
                STATUS != ?""",
            (duplicate_key, Status.FAILED),
        ):
            total = self.cursor.fetchone()["COUNT(*)"]
        return total > 0

    def have_name_or_md5sum(self, name: str, md5sum: str) -> bool:
        """Check whether this name or md5sum is already in History"""
        total = 0
        if self.execute(
            """
            SELECT COUNT(*) 
            FROM History 
            WHERE 
                ( LOWER(name) = LOWER(?) OR md5sum = ? ) AND 
                STATUS != ?""",
            (name, md5sum, Status.FAILED),
        ):
            total = self.cursor.fetchone()["COUNT(*)"]
        return total > 0

    def get_history_size(self) -> Tuple[int, int, int]:
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
            except:
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

    def get_other(self, nzo_id: str) -> Tuple[str, str, str, str, str]:
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


def build_history_info(nzo, workdir_complete: str, postproc_time: int, script_output: str, script_line: str):
    """Collects all the information needed for the database"""
    nzo: sabnzbd.nzbstuff.NzbObject
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
    )


def unpack_history_info(item: sqlite3.Row) -> Dict[str, Any]:
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
        except:
            logging.warning(T("Invalid stage logging in history for %s"), item["name"])
            logging.debug("Lines: %s", lst)
            all_stages_lines = []

        for stage_lines in all_stages_lines:
            try:
                key, logs = stage_lines.split(":::")
            except:
                logging.info('Missing key:::logs "%s"', stage_lines)
                continue
            stage = {"name": key, "actions": []}
            try:
                stage["actions"] = logs.split(";")
            except:
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

    # Retry and retry for failed URL-fetch
    item["retry"] = int_conv(item["status"] == Status.FAILED and item["path"] and os.path.exists(item["path"]))
    if item["report"] == "future":
        item["retry"] = True

    return item


def scheduled_history_purge():
    logging.info("Scheduled history purge")
    with HistoryDB() as history_db:
        history_db.auto_history_purge()
