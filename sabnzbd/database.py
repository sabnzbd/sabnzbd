#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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

import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DB_HISTORY_NAME, STAGES, Status
from sabnzbd.bpsmeter import this_week, this_month
from sabnzbd.decorators import synchronized
from sabnzbd.encoding import ubtou, utob
from sabnzbd.misc import int_conv, caller_name, opts_to_pp
from sabnzbd.filesystem import remove_file

DB_LOCK = threading.RLock()


def convert_search(search):
    """ Convert classic wildcard to SQL wildcard """
    if not search:
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


class HistoryDB:
    """ Class to access the History database
        Each class-instance will create an access channel that
        can be used in one thread.
        Each thread needs its own class-instance!
    """

    # These class attributes will be accessed directly because
    # they need to be shared by all instances
    db_path = None  # Will contain full path to history database
    done_cleaning = False  # Ensure we only do one Vacuum per session

    @synchronized(DB_LOCK)
    def __init__(self):
        """ Determine databse path and create connection """
        self.con = self.c = None
        if not HistoryDB.db_path:
            HistoryDB.db_path = os.path.join(sabnzbd.cfg.admin_dir.get_path(), DB_HISTORY_NAME)
        self.connect()

    def connect(self):
        """ Create a connection to the database """
        create_table = not os.path.exists(HistoryDB.db_path)
        self.con = sqlite3.connect(HistoryDB.db_path)
        self.con.row_factory = dict_factory
        self.c = self.con.cursor()
        if create_table:
            self.create_history_db()
        elif not HistoryDB.done_cleaning:
            # Run VACUUM on sqlite
            # When an object (table, index, or trigger) is dropped from the database, it leaves behind empty space
            # http://www.sqlite.org/lang_vacuum.html
            HistoryDB.done_cleaning = True
            self.execute("VACUUM")

        self.execute("PRAGMA user_version;")
        try:
            version = self.c.fetchone()["user_version"]
        except TypeError:
            version = 0
        if version < 1:
            # Add any missing columns added since first DB version
            # Use "and" to stop when database has been reset due to corruption
            _ = (
                self.execute("PRAGMA user_version = 1;")
                and self.execute('ALTER TABLE "history" ADD COLUMN series TEXT;')
                and self.execute('ALTER TABLE "history" ADD COLUMN md5sum TEXT;')
            )
        if version < 2:
            # Add any missing columns added since second DB version
            # Use "and" to stop when database has been reset due to corruption
            _ = self.execute("PRAGMA user_version = 2;") and self.execute(
                'ALTER TABLE "history" ADD COLUMN password TEXT;'
            )

    def execute(self, command, args=(), save=False):
        """ Wrapper for executing SQL commands """
        for tries in range(5, 0, -1):
            try:
                if args and isinstance(args, tuple):
                    self.c.execute(command, args)
                else:
                    self.c.execute(command)
                if save:
                    self.con.commit()
                return True
            except:
                error = str(sys.exc_info()[1])
                if tries >= 0 and "is locked" in error:
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
                        self.con.rollback()
                    except:
                        logging.debug("Rollback Failed:", exc_info=True)
            return False

    def create_history_db(self):
        """ Create a new (empty) database file """
        self.execute(
            """
        CREATE TABLE "history" (
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
            "password" TEXT
        )
        """
        )
        self.execute("PRAGMA user_version = 2;")

    def close(self):
        """ Close database connection """
        try:
            self.c.close()
            self.con.close()
        except:
            logging.error(T("Failed to close database, see log"))
            logging.info("Traceback: ", exc_info=True)

    def remove_completed(self, search=None):
        """ Remove all completed jobs from the database, optional with `search` pattern """
        search = convert_search(search)
        logging.info("Removing all completed jobs from history")
        return self.execute(
            """DELETE FROM history WHERE name LIKE ? AND status = ?""", (search, Status.COMPLETED), save=True
        )

    def get_failed_paths(self, search=None):
        """ Return list of all storage paths of failed jobs (may contain non-existing or empty paths) """
        search = convert_search(search)
        fetch_ok = self.execute(
            """SELECT path FROM history WHERE name LIKE ? AND status = ?""", (search, Status.FAILED)
        )
        if fetch_ok:
            return [item.get("path") for item in self.c.fetchall()]
        else:
            return []

    def remove_failed(self, search=None):
        """ Remove all failed jobs from the database, optional with `search` pattern """
        search = convert_search(search)
        logging.info("Removing all failed jobs from history")
        return self.execute(
            """DELETE FROM history WHERE name LIKE ? AND status = ?""", (search, Status.FAILED), save=True
        )

    def remove_history(self, jobs=None):
        """ Remove all jobs in the list `jobs`, empty list will remove all completed jobs """
        if jobs is None:
            self.remove_completed()
        else:
            if not isinstance(jobs, list):
                jobs = [jobs]

            for job in jobs:
                self.execute("""DELETE FROM history WHERE nzo_id = ?""", (job,), save=True)
                logging.info("[%s] Removing job %s from history", caller_name(), job)

    def auto_history_purge(self):
        """ Remove history items based on the configured history-retention """
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
                    """DELETE FROM history WHERE status = ? AND completed < ?""",
                    (Status.COMPLETED, seconds_to_keep),
                    save=True,
                )
        else:
            # How many to keep?
            to_keep = int_conv(sabnzbd.cfg.history_retention())
            if to_keep > 0:
                logging.info("Removing all but last %s completed jobs from history", to_keep)
                return self.execute(
                    """DELETE FROM history WHERE status = ? AND id NOT IN ( SELECT id FROM history WHERE status = ? ORDER BY completed DESC LIMIT ? )""",
                    (Status.COMPLETED, Status.COMPLETED, to_keep),
                    save=True,
                )

    def add_history_db(self, nzo, storage="", path="", postproc_time=0, script_output="", script_line=""):
        """ Add a new job entry to the database """
        t = build_history_info(nzo, storage, path, postproc_time, script_output, script_line, series_info=True)

        self.execute(
            """INSERT INTO history (completed, name, nzb_name, category, pp, script, report,
            url, status, nzo_id, storage, path, script_log, script_line, download_time, postproc_time, stage_log,
            downloaded, completeness, fail_message, url_info, bytes, series, md5sum, password)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            t,
            save=True,
        )
        logging.info("Added job %s to history", nzo.final_name)

    def fetch_history(self, start=None, limit=None, search=None, failed_only=0, categories=None):
        """ Return records for specified jobs """
        command_args = [convert_search(search)]

        post = ""
        if categories:
            categories = ["*" if c == "Default" else c for c in categories]
            post = " AND (CATEGORY = ?"
            post += " OR CATEGORY = ? " * (len(categories) - 1)
            post += ")"
            command_args.extend(categories)
        if failed_only:
            post += " AND STATUS = ?"
            command_args.append(Status.FAILED)

        cmd = "SELECT COUNT(*) FROM history WHERE name LIKE ?"
        res = self.execute(cmd + post, tuple(command_args))
        total_items = -1
        if res:
            try:
                total_items = self.c.fetchone().get("COUNT(*)")
            except AttributeError:
                pass

        if not start:
            start = 0
        if not limit:
            limit = total_items

        command_args.extend([start, limit])
        cmd = "SELECT * FROM history WHERE name LIKE ?"
        fetch_ok = self.execute(cmd + post + " ORDER BY completed desc LIMIT ?, ?", tuple(command_args))

        if fetch_ok:
            items = self.c.fetchall()
        else:
            items = []

        fetched_items = len(items)

        # Unpack the single line stage log
        # Stage Name is separated by ::: stage lines by ; and stages by \r\n
        items = [unpack_history_info(item) for item in items]

        return items, fetched_items, total_items

    def have_episode(self, series, season, episode):
        """ Check whether History contains this series episode """
        total = 0
        series = series.lower().replace(".", " ").replace("_", " ").replace("  ", " ")
        if series and season and episode:
            pattern = "%s/%s/%s" % (series, season, episode)
            res = self.execute(
                "select count(*) from History WHERE series = ? AND STATUS != ?", (pattern, Status.FAILED)
            )
            if res:
                try:
                    total = self.c.fetchone().get("count(*)")
                except AttributeError:
                    pass
        return total > 0

    def have_name_or_md5sum(self, name, md5sum):
        """ Check whether this name or md5sum is already in History """
        total = 0
        res = self.execute("select count(*) from History WHERE md5sum = ? AND STATUS != ?", (md5sum, Status.FAILED))
        if res:
            try:
                total = self.c.fetchone().get("count(*)")
            except AttributeError:
                pass
        return total > 0

    def get_history_size(self):
        """ Returns the total size of the history and
            amounts downloaded in the last month and week
        """
        # Total Size of the history
        total = 0
        if self.execute("""SELECT sum(bytes) FROM history"""):
            try:
                total = self.c.fetchone().get("sum(bytes)")
            except AttributeError:
                pass

        # Amount downloaded this month
        # r = time.gmtime(time.time())
        # month_timest = int(time.mktime((r.tm_year, r.tm_mon, 0, 0, 0, 1, r.tm_wday, r.tm_yday, r.tm_isdst)))
        month_timest = int(this_month(time.time()))

        month = 0
        if self.execute("""SELECT sum(bytes) FROM history WHERE completed > ?""", (month_timest,)):
            try:
                month = self.c.fetchone().get("sum(bytes)")
            except AttributeError:
                pass

        # Amount downloaded this week
        week_timest = int(this_week(time.time()))

        week = 0
        if self.execute("""SELECT sum(bytes) FROM history WHERE completed > ?""", (week_timest,)):
            try:
                week = self.c.fetchone().get("sum(bytes)")
            except AttributeError:
                pass

        return total, month, week

    def get_script_log(self, nzo_id):
        """ Return decompressed log file """
        data = ""
        t = (nzo_id,)
        if self.execute("SELECT script_log FROM history WHERE nzo_id = ?", t):
            try:
                data = ubtou(zlib.decompress(self.c.fetchone().get("script_log")))
            except:
                pass
        return data

    def get_name(self, nzo_id):
        """ Return name of the job `nzo_id` """
        t = (nzo_id,)
        name = ""
        if self.execute("SELECT name FROM history WHERE nzo_id = ?", t):
            try:
                name = self.c.fetchone().get("name")
            except AttributeError:
                pass
        return name

    def get_path(self, nzo_id):
        """ Return the `incomplete` path of the job `nzo_id` if it is still there """
        t = (nzo_id,)
        path = ""
        if self.execute("SELECT path FROM history WHERE nzo_id = ?", t):
            try:
                path = self.c.fetchone().get("path")
            except AttributeError:
                pass
        if os.path.exists(path):
            return path
        return None

    def get_other(self, nzo_id):
        """ Return additional data for job `nzo_id` """
        t = (nzo_id,)
        if self.execute("SELECT * FROM history WHERE nzo_id = ?", t):
            try:
                items = self.c.fetchone()
                dtype = items.get("report")
                url = items.get("url")
                pp = items.get("pp")
                script = items.get("script")
                cat = items.get("category")
                return dtype, url, pp, script, cat
            except (AttributeError, IndexError):
                pass
        return "", "", "", "", ""


def dict_factory(cursor, row):
    """ Return a dictionary for the current database position """
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


_PP_LOOKUP = {0: "", 1: "R", 2: "U", 3: "D"}


def build_history_info(
    nzo, storage="", downpath="", postproc_time=0, script_output="", script_line="", series_info=False
):
    """ Collects all the information needed for the database """
    completed = int(time.time())
    if not downpath:
        downpath = nzo.downpath
    pp = _PP_LOOKUP.get(opts_to_pp(*nzo.repair_opts), "X")

    if script_output:
        # Compress the output of the script
        script_output = sqlite3.Binary(zlib.compress(utob(script_output)))

    download_time = nzo.nzo_info.get("download_time", 0)
    completeness = 0
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

    # Analyze series info only when job is finished
    series = ""
    if series_info:
        seriesname, season, episode, _ = sabnzbd.newsunpack.analyse_show(nzo.final_name)
        if seriesname and season and episode:
            series = "%s/%s/%s" % (seriesname.lower(), season, episode)

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
        storage,
        downpath,
        script_output,
        script_line,
        download_time,
        postproc_time,
        stage_log,
        nzo.bytes_downloaded,
        completeness,
        nzo.fail_msg,
        url_info,
        nzo.bytes_downloaded,
        series,
        nzo.md5sum,
        nzo.password,
    )


def unpack_history_info(item):
    """ Expands the single line stage_log from the DB
        into a python dictionary for use in the history display
    """
    # Stage Name is separated by ::: stage lines by ; and stages by \r\n
    lst = item["stage_log"]
    if lst:
        try:
            lines = lst.split("\r\n")
        except:
            logging.error(T("Invalid stage logging in history for %s") + " (\\r\\n)", item["name"])
            logging.debug("Lines: %s", lst)
            lines = []
        lst = [None for x in STAGES]
        for line in lines:
            stage = {}
            try:
                key, logs = line.split(":::")
            except:
                logging.debug('Missing key:::logs "%s"', line)
                key = line
                logs = ""
            stage["name"] = key
            stage["actions"] = []
            try:
                logs = logs.split(";")
            except:
                logging.error(T("Invalid stage logging in history for %s") + " (;)", item["name"])
                logging.debug("Logs: %s", logs)
                logs = []
            for log in logs:
                stage["actions"].append(log)
            try:
                lst[STAGES[key]] = stage
            except KeyError:
                lst.append(stage)
        # Remove unused stages
        item["stage_log"] = [x for x in lst if x is not None]

    if item["script_log"]:
        item["script_log"] = ""
    # The action line is only available for items in the postproc queue
    if "action_line" not in item:
        item["action_line"] = ""
    return item


def midnight_history_purge():
    logging.info("Scheduled history purge")
    history_db = HistoryDB()
    history_db.auto_history_purge()
    history_db.close()
