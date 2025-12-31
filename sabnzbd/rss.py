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
sabnzbd.rss - rss client functionality
"""

import os
import re
import logging
import sys
import time
import datetime
import threading
import urllib.parse
import weakref
from dataclasses import dataclass, field
from typing import Union, Optional, Sequence, Any, Generator, Iterable
import sqlite3
from sqlite3 import Connection, Cursor
import more_itertools

import sabnzbd
from sabnzbd.constants import RSS_FILE_NAME, DB_RSS_FILE_NAME, DEFAULT_PRIORITY
from sabnzbd.database import convert_search
from sabnzbd.decorators import synchronized
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.misc import (
    cat_convert,
    convert_filter,
    cat_to_opts,
    match_str,
    from_units,
    int_conv,
    get_base_url,
    helpful_warning,
)
import sabnzbd.emailer as emailer
from sabnzbd.filesystem import remove_file

import feedparser

RSS_LOCK = threading.RLock()
_RE_SP = re.compile(r"s*(\d+)[ex](\d+)", re.I)
_RE_SIZE1 = re.compile(r"Size:\s*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_SIZE2 = re.compile(r"\W*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_BR = re.compile(r"<br\s*/?>", re.I)  # Strip content after first <br/>
_RE_TAG = re.compile(r"<[^>]+>")  # Strip HTML tags from descriptions


@dataclass
class NormalisedEntry:
    link: Optional[str]
    infourl: Optional[str]
    orgcat: Optional[str]
    title: str
    size: int
    age: Optional[datetime.datetime]
    season: int
    episode: int


@dataclass
class ResolvedEntry(NormalisedEntry):
    feed: str
    cat: Optional[str] = None
    pp: Optional[int] = None
    script: Optional[str] = None
    priority: Optional[int] = None
    rule: Optional[int] = None
    status: str = "N"  # New
    downloaded_at: Optional[datetime.datetime] = None

    def __post_init__(self):
        # Normalise "default-ish" values to None
        self.cat = _normalise_str_or_none(self.cat)
        self.priority = _normalise_priority(self.priority)
        self.pp = _normalise_pp(self.pp)
        self.script = _normalise_str_or_none(self.script)

    def merge(self, existing: "ResolvedEntry"):
        """Merge existing entry into self"""
        self.cat = existing.cat
        self.pp = existing.pp
        self.script = existing.script
        self.priority = existing.priority
        self.rule = existing.rule
        self.status = existing.status
        self.downloaded_at = existing.downloaded_at

    @classmethod
    def from_sqlite(cls, item: sqlite3.Row):
        return cls(
            feed=item["feed"],
            link=item["url"],
            title=item["title"],
            infourl=item["infourl"],
            size=item["size"],
            age=datetime.datetime.fromtimestamp(item["age"], tz=datetime.timezone.utc).astimezone(),
            season=item["season"],
            episode=item["episode"],
            orgcat=item["orgcat"],
            cat=item["category"],
            pp=item["pp"],
            script=item["script"],
            priority=item["priority"],
            rule=item["rule"],
            status=item["status"],
            downloaded_at=(
                datetime.datetime.fromtimestamp(item["downloaded_at"], tz=datetime.timezone.utc).astimezone()
                if item["downloaded_at"]
                else None
            ),
        )

    @classmethod
    def from_feed(cls, feed: str, entry: feedparser.FeedParserDict) -> Optional["ResolvedEntry"]:
        """Build NormalisedEntry from feedparser entry"""
        link: Optional[str] = None
        size: int = 0
        age: datetime.datetime = datetime.datetime.now()

        # Try standard link and enclosures first
        if "enclosures" in entry and entry["enclosures"]:
            try:
                for enclosure in entry["enclosures"]:
                    if "type" in enclosure and enclosure["type"] != "application/x-nzb":
                        continue

                    link = enclosure["href"]
                    size = int(enclosure["length"])
                    break
            except Exception:
                pass
        else:
            link = entry.link
            if not link:
                link = entry.links[0].href

        # GUID usually has URL to result on page
        infourl = None
        if entry.get("id") and entry.id != link and entry.id.lower().startswith("http"):
            infourl = entry.id

        if size == 0:
            # Try to find size in Description
            try:
                desc = entry.description.replace("\n", " ").replace("&nbsp;", " ")
                m = _RE_SIZE1.search(desc) or _RE_SIZE2.search(desc)
                if m:
                    size = int_conv(from_units(m.group(1)))
            except Exception:
                pass

        # Try newznab attribute first, this is the correct one
        try:
            # Convert it to format that calc_age understands
            age = datetime.datetime(*entry["newznab"]["usenetdate_parsed"][:6], tzinfo=datetime.timezone.utc)
        except Exception:
            # Date from feed (usually lags behind)
            try:
                # Convert it to format that calc_age understands
                age = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc)
            except Exception:
                pass
        finally:
            age = age.replace(tzinfo=datetime.timezone.utc)

        # Maybe the newznab also provided SxxExx info
        try:
            season = re.findall(r"\d+", entry["newznab"]["season"])[0]
            episode = re.findall(r"\d+", entry["newznab"]["episode"])[0]
        except (KeyError, IndexError):
            season = episode = 0

        if not link or not link.lower().startswith("http"):
            logging.info(T("Empty RSS entry found (%s)"), link)
            return None

        try:
            category = entry.cattext
        except AttributeError:
            try:
                category = entry.category
            except AttributeError:
                try:  # nzb.su
                    category = entry.tags[0]["term"]
                except (AttributeError, IndexError, KeyError):
                    try:
                        desc = entry.description
                        # Split on any <br>, <br/>, <br /> (case-insensitive) to avoid some large descriptions
                        first_part = _RE_BR.split(desc, maxsplit=1)[0]
                        category = _RE_TAG.sub("", first_part).strip()
                    except AttributeError:
                        category = ""

        # Make sure spaces are quoted in the URL
        link = link.strip().replace(" ", "%20")

        return cls(
            feed=feed,
            link=link,
            title=entry.title,
            infourl=infourl,
            size=size,
            age=age,
            season=season,
            episode=episode,
            orgcat=category,
        )


@dataclass(frozen=True)
class FeedEvaluation:
    matched: bool
    rule_index: int
    season: int
    episode: int
    category: Optional[str] = None
    priority: Optional[int] = None
    pp: Optional[int] = None
    script: Optional[str] = None


@dataclass
class FeedRule:
    regex: Union[str, re.Pattern]
    type: str
    category: Optional[str] = None
    priority: Optional[int] = None
    pp: Optional[int] = None
    script: Optional[str] = None
    enabled: bool = True

    def __post_init__(self):
        # Convert regex if needed
        if self.type not in {"<", ">", "F", "S"}:
            self.regex = convert_filter(self.regex)
        # Normalise "default-ish" values to None
        self.category = _normalise_str_or_none(self.category)
        self.priority = _normalise_priority(self.priority)
        self.pp = _normalise_pp(self.pp)
        self.script = _normalise_str_or_none(self.script)

    def matches(
        self, *, title: str, category: Optional[str], size: int, season: int, episode: int, rule_index: int
    ) -> Optional[bool]:
        """
        Returns:
            True  -> positive match
            False -> negative match
            None  -> rule does not apply
        """
        # Category rule
        if category and self.type == "C":
            found = bool(re.search(self.regex, category))
            if not found:
                logging.debug("Filter rejected on rule %d (category mismatch)", rule_index)
                return False

        # Size rules
        elif self.type == "<" and size and from_units(self.regex) < size:
            logging.debug("Filter rejected on rule %d (size too large)", rule_index)
            return False
        elif self.type == ">" and size and from_units(self.regex) > size:
            logging.debug("Filter rejected on rule %d (size too small)", rule_index)
            return False

        # Episode / season rules
        elif self.type == "F" and not self.ep_match(season, episode, self.regex):
            logging.debug("Filter rejected on rule %d (episode too early)", rule_index)
            return False
        elif self.type == "S" and self.ep_match(season, episode, self.regex, title):
            logging.debug("Filter matched on rule %d (show SxxEyy match)", rule_index)
            return True

        # Title regex match
        if self.regex:
            found = bool(re.search(self.regex, title))
        else:
            found = False

        # Standard match types
        if self.type == "M" and not found:
            logging.debug("Filter rejected on rule %d (mandatory match failed)", rule_index)
            return False
        if self.type == "A" and found:
            logging.debug("Filter matched on rule %d (always match)", rule_index)
            return True
        if self.type == "R" and found:
            logging.debug("Filter rejected on rule %d (reject match)", rule_index)
            return False

        return None

    @staticmethod
    def ep_match(season: int, episode: int, expr: str, title: Optional[str] = None):
        """Return True if season, episode is at or above expected
        Optionally `title` can be matched
        """
        if m := _RE_SP.search(expr):
            # Make sure they are all integers for comparison
            req_season = int(m.group(1))
            req_episode = int(m.group(2))
            season = int_conv(season)
            episode = int_conv(episode)
            if season > req_season or (season == req_season and episode >= req_episode):
                if title:
                    show = expr[: m.start()].replace(".", " ").replace("_", " ").strip()
                    show = show.replace(" ", "[._ ]+")
                    return bool(re.search(show, title, re.I))
                else:
                    return True
            else:
                return False
        else:
            return True


@dataclass
class FeedConfig:
    default_category: Optional[str] = None
    default_priority: Optional[int] = None
    default_pp: Optional[int] = None
    default_script: Optional[str] = None
    rules: list[FeedRule] = field(default_factory=list)

    def __post_init__(self):
        self.default_category = _normalise_str_or_none(self.default_category)
        if self.default_category not in sabnzbd.api.list_cats(default=False):
            self.default_category = None
        self.default_priority = _normalise_priority(self.default_priority)
        self.default_pp = _normalise_pp(self.default_pp)
        self.default_script = _normalise_str_or_none(self.default_script)

    def has_type(self, *types: str) -> bool:
        """Check if any rule matches the given types"""
        return any(rule.type in types for rule in self.rules)

    @classmethod
    def from_config(cls, c: config.ConfigRSS) -> "FeedConfig":
        """Build a FeedConfig from a RSS config."""
        rules: list[FeedRule] = []
        for cat, pp, script, ftype, regex, priority, enabled in c.filters():
            rules.append(
                FeedRule(
                    regex=regex,
                    type=ftype,
                    category=cat,
                    priority=priority,
                    pp=pp,
                    script=script,
                    enabled=(enabled != "0"),
                )
            )

        return cls(
            default_category=c.cat(),
            default_priority=c.priority(),
            default_pp=c.pp(),
            default_script=c.script(),
            rules=rules,
        )

    def evaluate(
        self,
        *,
        title: str,
        category: Optional[str],
        size: int,
        season: int,
        episode: int,
    ) -> FeedEvaluation:
        """Evaluate rules for a single RSS entry."""
        is_match: bool = False
        matched_rule: Optional[FeedRule] = None
        matched_index: int = 0
        cur_season: int = season
        cur_episode: int = episode

        # Start from feed defaults for options.
        my_category: Optional[str] = self.default_category
        my_pp: Optional[str] = self.default_pp
        my_script: Optional[str] = self.default_script
        my_priority: Optional[int] = self.default_priority

        # If there are no rules; return early
        if not self.rules:
            return FeedEvaluation(
                matched=is_match,
                rule_index=matched_index,
                season=int_conv(cur_season),
                episode=int_conv(cur_episode),
                category=my_category,
                pp=my_pp,
                script=my_script,
                priority=my_priority,
            )

        # Fill in missing season / episode information when F/S rules exist
        if self.has_type("F", "S") and (not cur_season or not cur_episode):
            show_analysis = sabnzbd.sorting.BasicAnalyzer(title)
            cur_season = show_analysis.info.get("season_num")
            cur_episode = show_analysis.info.get("episode_num")

        # Match against all filters until a positive or negative match
        for idx, rule in enumerate(self.rules):
            if not rule.enabled:
                continue

            outcome = rule.matches(
                title=title,
                category=category,
                size=size,
                season=cur_season,
                episode=cur_episode,
                rule_index=idx,
            )

            if outcome is None:
                continue

            matched_index = idx
            is_match = outcome
            matched_rule = rule if outcome else None
            break

        if matched_rule is None:
            base_category = (
                cat_convert(category) if category and self.default_category is None else self.default_category
            )
        else:
            base_category = matched_rule.category or cat_convert(category) or self.default_category

        my_category, my_pp, my_script, my_priority = self._resolve_options(
            base_category=base_category,
            rule=matched_rule,
        )

        return FeedEvaluation(
            matched=is_match,
            rule_index=matched_index,
            season=int_conv(cur_season),
            episode=int_conv(cur_episode),
            category=my_category,
            pp=my_pp,
            script=my_script,
            priority=my_priority,
        )

    def _resolve_options(
        self,
        *,
        base_category: Optional[str],
        rule: Optional[FeedRule],
    ) -> tuple[Optional[str], Optional[int], Optional[str], Optional[int]]:
        """Resolve options for a feed rule."""
        if base_category:
            cat, cat_pp, cat_script, cat_prio = cat_to_opts(base_category)
            cat_pp = _normalise_pp(cat_pp)
            cat_script = _normalise_str_or_none(cat_script)
            cat_prio = _normalise_priority(cat_prio)
        else:
            cat = cat_pp = cat_script = cat_prio = None

        pp = first_not_none(
            rule.pp if rule else None,
            cat_pp,
            self.default_pp,
        )
        script = first_not_none(
            rule.script if rule else None,
            cat_script,
            self.default_script,
        )
        priority = first_not_none(
            rule.priority if rule else None,
            cat_prio,
            self.default_priority,
        )

        return cat, pp, script, priority


class RSSStore:
    """Class to access the RSS database
    Each class-instance will create an access channel that can be used in one thread.
    Each thread needs its own class-instance!
    """

    # These class attributes will be accessed directly because they need to be shared by all instances
    db_path: Optional[str] = None  # Full path to rss database
    startup_done: bool = False

    @synchronized(RSS_LOCK)
    def __init__(self):
        """Determine database path and create connection"""
        self.connection: Optional[Connection] = None
        self.cursor: Optional[Cursor] = None
        self.connect()

    def connect(self):
        """Create a connection to the database"""
        if not RSSStore.db_path:
            RSSStore.db_path = os.path.join(sabnzbd.cfg.admin_dir.get_path(), DB_RSS_FILE_NAME)
        create_table = not RSSStore.startup_done and not os.path.exists(RSSStore.db_path)

        # check_same_thread=False because CherryPy calls stop_thread on its main thread
        self.connection = sqlite3.connect(RSSStore.db_path, check_same_thread=False)
        self.connection.isolation_level = None  # autocommit attribute only introduced in Python 3.12
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

        # Perform initialization only once
        if not RSSStore.startup_done:
            if create_table:
                self.create_rss_db()
                self.import_old_records()

            self.execute("PRAGMA journal_mode=WAL")
            self.execute("PRAGMA synchronous=NORMAL")

            # When an object (table, index, or trigger) is dropped from the database, it leaves behind empty space
            # http://www.sqlite.org/lang_vacuum.html
            self.execute("VACUUM")

            # See if we need to perform any updates
            # self.execute("PRAGMA user_version;")
            # try:
            #     version = self.cursor.fetchone()["user_version"]
            # except (IndexError, TypeError):
            #     version = 0
            #
            # Add any new columns added since last DB version
            # Use "and" to stop when database has been reset due to corruption
            # if version < 1:
            #     _ = (
            #         self.execute("PRAGMA user_version = 1;")
            #         and self.execute("ALTER TABLE rss ADD COLUMN ... TEXT;")
            #     )

            for feed in self.get_feeds():
                self.remove_obsolete(feed)

            RSSStore.startup_done = True

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
                    logging.error(T("Cannot write to RSS database, check access rights!"))
                    # Report back success, because there's no recovery possible
                    return True
                elif match_str(error, ("not a database", "malformed", "no such table", "duplicate column name")):
                    logging.error(T("Damaged RSS database, created empty replacement"))
                    logging.info("Traceback: ", exc_info=True)
                    self.close()
                    try:
                        remove_file(RSSStore.db_path)
                    except Exception:
                        pass
                    RSSStore.startup_done = False
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

    def create_rss_db(self):
        """Create a new (empty) database file"""
        self.execute(
            """
        CREATE TABLE rss (
            "id" INTEGER PRIMARY KEY,
            "feed" TEXT NOT NULL,
            "status" TEXT NOT NULL
                     CHECK (status IN (
                     'G',  -- Good
                     'B',  -- Bad
                     'D',  -- Downloaded
                     'X',  -- Expired
                     'G*', -- Good Initial
                     'D-', -- Downloaded Hidden
                     'N'   -- New
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
            "downloaded_at" INTEGER,
            "created_at" INTEGER NOT NULL,
            UNIQUE (feed, url)
        );
        """
        )
        self.execute("CREATE INDEX idx_rss_feed ON rss(feed)")
        self.execute("CREATE INDEX idx_rss_feed_status ON rss(feed, status)")
        self.execute("CREATE INDEX idx_rss_feed_status_downloaded_at ON rss(feed, status, downloaded_at DESC)")
        self.execute("CREATE INDEX idx_rss_feed_status_age ON rss(feed, status, age DESC)")

    def import_old_records(self):
        """Migrate old RSS database"""
        try:
            jobs = sabnzbd.filesystem.load_admin(RSS_FILE_NAME) or {}
            local_tz = datetime.datetime.now().astimezone().tzinfo
            for feed, jobs in jobs.items():
                for link, job in jobs.items():
                    category = job.get("orgcat") or None
                    if category in ("", "*"):
                        category = None
                    entry = ResolvedEntry(
                        feed=feed,
                        link=link.strip().replace(" ", "%20"),
                        title=job.get("title", ""),
                        infourl=job.get("infourl"),
                        size=job.get("size", 0),
                        age=(
                            # datetime.datetime: convert to local time then to UTC
                            job.get("age").replace(tzinfo=local_tz).astimezone(datetime.timezone.utc)
                            if job.get("age")
                            else None
                        ),
                        season=job.get("season", 0),
                        episode=job.get("episode", 0),
                        orgcat=category,
                        cat=job.get("cat", 0),
                        pp=job.get("pp", 0),
                        script=job.get("script", 0),
                        priority=job.get("prio", 0),
                        rule=job.get("rule", 0),
                        status=job.get("status"),
                        downloaded_at=(
                            # time.struct_time: convert to local time then to UTC
                            datetime.datetime.fromtimestamp(
                                time.mktime(job.get("time_downloaded")), tz=datetime.timezone.utc
                            )
                            if job.get("time_downloaded")
                            else None
                        ),
                    )
                    self.upsert(entry)
        except Exception as e:
            logging.error(e)
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

    def get_job(self, feed: str, url: str) -> Optional[ResolvedEntry]:
        if not feed or not url:
            return None
        if self.execute("SELECT * FROM rss WHERE feed = ? AND url = ?", (feed, url)):
            row = self.cursor.fetchone()
            if row is None:
                return None
            return ResolvedEntry.from_sqlite(row)
        return None

    def get_jobs(
        self,
        feed: Optional[str] = None,
        search: Optional[str] = None,
        statuses: Optional[list[str]] = None,
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

        if statuses:
            placeholders = " OR ".join(["status = ?"] * len(statuses))
            where_clauses.append(f"({placeholders})")
            command_args.extend(statuses)

        # Combine all WHERE clauses
        where_sql = " AND ".join(where_clauses)

        # Final query
        cmd = f"SELECT * FROM rss WHERE {where_sql} ORDER BY COALESCE(downloaded_at, age) DESC"

        if self.execute(cmd, command_args):
            for item in self.cursor:
                yield ResolvedEntry.from_sqlite(item)

    def get_feeds(self) -> list[str]:
        self.execute("SELECT DISTINCT feed from rss")
        return [row["feed"] for row in self.cursor]

    def has_feed(self, feed: str) -> bool:
        self.execute("SELECT EXISTS(SELECT 1 FROM rss WHERE feed = ?) AS found", (feed,))
        return bool(self.cursor.fetchone()["found"])

    def upsert(self, entry: ResolvedEntry):
        """Add or update a job entry in the database"""
        t = self.build_job_info(entry)

        self.execute(
            """
            INSERT INTO rss (
                feed, status, title, url, infourl, category, orgcat, pp, script, priority,
                season, episode, size, rule, age, downloaded_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(feed, url) DO UPDATE SET
                status        = excluded.status,
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
                downloaded_at = COALESCE(excluded.downloaded_at, rss.downloaded_at);
            """,
            t,
        )

    @staticmethod
    def build_job_info(entry: ResolvedEntry):
        """Collects all the information needed for the database"""
        return (
            entry.feed,
            entry.status,
            entry.title,
            entry.link,
            entry.infourl,
            entry.cat,
            entry.orgcat,
            entry.pp,
            entry.script,
            str(entry.priority) if entry.priority is not None else str(DEFAULT_PRIORITY),
            entry.season,
            entry.episode,
            entry.size,
            entry.rule,
            int(entry.age.timestamp()),
            int(entry.downloaded_at.timestamp()) if entry.downloaded_at else None,
            int(time.time()),
        )

    def delete_feed(self, feed: str):
        """Permanently remove job from the history"""
        self.execute("""DELETE FROM rss WHERE feed = ?""", (feed,))

    def rename_feed(self, old_feed: str, new_feed: str):
        self.execute("""UPDATE rss SET feed = ? WHERE feed = ?""", (old_feed, new_feed))

    def show_result(self, feed: str) -> Generator[ResolvedEntry, Any, None]:
        if self.execute(
            """
            SELECT * 
            FROM rss 
            WHERE feed = ? AND substr(status, 1, 1) IN ('G', 'B', 'D')
            ORDER BY COALESCE(downloaded_at, age) DESC
            """,
            (feed,),
        ):
            for row in self.cursor:
                yield ResolvedEntry.from_sqlite(row)

    def flag_downloaded(self, feed: str, url: str):
        if not feed or not url:
            return
        self.execute(
            "UPDATE rss SET status = 'D', downloaded_at = ? WHERE feed = ? AND url = ?",
            (
                int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                feed,
                url,
            ),
        )

    def clear_feed(self, feed: str):
        """Remove any previous references to this feed name, and start fresh."""
        self.delete_feed(feed)

    def clear_downloaded(self, feed: str):
        """Mark downloaded jobs so that they won't be displayed any more."""
        self.execute("UPDATE rss SET status = 'D-' WHERE feed = ? AND status = 'D'", (feed,))

    def is_duplicate(self, entry: ResolvedEntry) -> bool:
        """
        Check if a job with the same title and size already exists in another feed

        Allow 5% size deviation because indexers might have small differences for same release
        """
        self.execute(
            "SELECT EXISTS(SELECT 1 FROM rss WHERE title = ? AND url <> ? AND size BETWEEN ? AND ?) AS found",
            (entry.title, entry.link, entry.size * 0.95, entry.size * 1.05),
        )
        return bool(self.cursor.fetchone()["found"])

    @synchronized(RSS_LOCK)
    def remove_obsolete(self, feed: str, new_urls: Optional[Iterable[str]] = None):
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
            for batch in more_itertools.batched(new_urls, 500):
                placeholders = ",".join(["(?)"] * len(batch))
                self.execute(f"INSERT INTO temp_urls(url) VALUES {placeholders}", batch)

            # Update rss to mark G/B not in temp_urls as X
            self.execute(
                """
                UPDATE rss
                SET status = 'X'
                WHERE feed = ?
                  AND substr(status,1,1) IN ('G','B')
                  AND url NOT IN (SELECT url FROM temp_urls)
            """,
                (feed,),
            )

            # Drop temp table
            self.execute("DROP TABLE temp_urls")

        # Purge
        if not self.execute(
            """
            SELECT url FROM rss
            WHERE feed = ?
              AND status = 'X'
              AND age < ?
        """,
            (feed, limit),
        ):
            return

        expired_urls = [row["url"] for row in self.cursor]
        for url in expired_urls:
            logging.debug("Purging link %s", url)
            self.execute("DELETE FROM rss WHERE feed = ? AND url = ?", (feed, url))


class RSSReader:
    def __init__(self):
        self.next_run = time.time()
        self.shutdown = False
        self._active_stores = weakref.WeakSet()
        self._thread_local = threading.local()

        # Patch feedparser
        self.patch_feedparser()

    def stop(self):
        self.shutdown = True
        self.store = None

    @property
    def is_store_active(self):
        """Are there any stores still running?"""
        return any(self._active_stores)

    @property
    def store(self) -> RSSStore:
        """Get the store for the current thread"""
        if not hasattr(self._thread_local, "store"):
            store = RSSStore()
            self._active_stores.add(store)
            self._thread_local.store = store
        return self._thread_local.store

    @store.setter
    def store(self, db: Optional[RSSStore]) -> None:
        """Set the store for the current thread, setting to None closes the connection"""
        if current := getattr(self._thread_local, "store", None):
            current.close()
            del self._thread_local.store
        if db:
            self._active_stores.add(db)
            self._thread_local.store = db

    @synchronized(RSS_LOCK)
    def run_feed(
        self,
        feed: str,
        download: bool = False,
        ignore_first: bool = False,
        force: bool = False,
        readout: bool = True,
    ) -> str:
        """Run the query for one URI and apply filters"""
        self.shutdown = False

        if not feed:
            return "No such feed"

        new_links: set[str] = set()
        new_downloads: list[str] = []

        # Configuration
        uris, filters, first, config_error = self.configure_rss(feed, ignore_first)
        if config_error:
            return config_error

        # Fetch & parse RSS
        if readout:
            try:
                entries, msg = self.fetch_rss(feed, uris)
            except (AttributeError, IndexError):
                last_uri = uris[-1] if uris else ""
                logging.info(T("Incompatible feed") + " " + last_uri)
                logging.info("Traceback: ", exc_info=True)
                return T("Incompatible feed")
            # Error in readout or no new readout
            if not entries:
                return msg
        else:
            entries, msg = (list(self.store.get_jobs(feed=feed)), "")

        # Evaluate rules and apply side effects
        for entry in entries:
            if self.shutdown:
                return ""

            # Skip duplicates across multiple feeds
            if entry.link in new_links or len(uris) > 1 and self.store.is_duplicate(entry):
                logging.info("Ignoring job %s from other feed", entry.title)
                continue

            # Track all valid links so obsolete ones can be cleaned up later
            new_links.add(entry.link)

            evaluation, should_download, is_starred = self._evaluate_entry(
                entry=entry,
                filters=filters,
                first=first,
                download=download,
                force=force,
                readout=readout,
            )
            if evaluation is None:
                continue

            downloaded = self._process_entry(
                feed=feed,
                entry=entry,
                evaluation=evaluation,
                should_download=should_download,
                is_starred=is_starred,
            )
            if downloaded:
                new_downloads.append(entry.title)

        # Send email if wanted and not "forced"
        if new_downloads and cfg.email_rss() and not force:
            emailer.rss_mail(feed, new_downloads)

        self.store.remove_obsolete(feed, new_links)

        return msg

    def configure_rss(
        self, feed: str, ignore_first: bool
    ) -> tuple[list[str], Optional[FeedConfig], bool, Optional[str]]:
        """Prepare configuration and state for a feed run.

        Returns (uris, filters, first, error_message).
        If `error_message` is not empty, the caller should abort and return it.
        """
        # Preparations, get options
        try:
            feeds = config.get_rss()[feed]
        except KeyError:
            logging.error(T('Incorrect RSS feed description "%s"'), feed)
            logging.info("Traceback: ", exc_info=True)
            return [], None, False, T('Incorrect RSS feed description "%s"') % feed

        uris = feeds.uri()
        filters = FeedConfig.from_config(feeds)

        # Set first if this is the very first scan of this URI
        first = (not self.store.has_feed(feed)) and ignore_first

        return uris, filters, first, ""

    @staticmethod
    def patch_feedparser():
        """Apply options that work for SABnzbd
        Add additional parsing of attributes
        """
        feedparser.SANITIZE_HTML = 0
        feedparser.RESOLVE_RELATIVE_URIS = 0

        # Add SABnzbd's custom User Agent
        feedparser.USER_AGENT = "SABnzbd/%s" % sabnzbd.__version__

        # Support both feedparser 5 and 6
        try:
            feedparser_mixin = feedparser._FeedParserMixin
            feedparser_parse_date = feedparser._parse_date
        except AttributeError:
            feedparser_mixin = feedparser.mixin._FeedParserMixin
            feedparser_parse_date = feedparser.datetimes._parse_date

        # Add our own namespace
        feedparser_mixin.namespaces["http://www.newznab.com/DTD/2010/feeds/attributes/"] = "newznab"

        # Add parsers for the namespace
        def _start_newznab_attr(self, attrsD):
            # Support both feedparser 5 and 6
            try:
                context = self._getContext()
            except AttributeError:
                context = self._get_context()

            # Add the dict
            if "newznab" not in context:
                context["newznab"] = {}
            # Don't crash when it fails
            try:
                # Add keys
                context["newznab"][attrsD["name"]] = attrsD["value"]
                # Try to get date-object
                if attrsD["name"] == "usenetdate":
                    context["newznab"][attrsD["name"] + "_parsed"] = feedparser_parse_date(attrsD["value"])
            except KeyError:
                pass

        feedparser_mixin._start_newznab_attr = _start_newznab_attr
        feedparser_mixin._start_nZEDb_attr = _start_newznab_attr
        feedparser_mixin._start_nzedb_attr = _start_newznab_attr
        feedparser_mixin._start_nntmux_attr = _start_newznab_attr

    def fetch_rss(self, feed: str, uris: list[str]) -> tuple[list[ResolvedEntry], str]:
        """Fetch and parse RSS feeds for the given URIs.

        Returns (entries, message).
        """
        all_entries = []
        msg = ""

        for uri in uris:
            # Reset parsing message for each feed
            msg = ""
            feed_parsed = {}
            uri = uri.replace(" ", "%20").replace("feed://", "http://")
            logging.debug("Running feedparser on %s", uri)
            try:
                feed_parsed = feedparser.parse(uri)
            except Exception as feedparser_exc:
                # Feedparser 5 would catch all errors, while 6 just throws them back at us
                feed_parsed["bozo_exception"] = feedparser_exc
            logging.debug("Finished parsing %s", uri)

            status = feed_parsed.get("status", 999)
            if status in (401, 402, 403):
                msg = T("Do not have valid authentication for feed %s") % uri
            elif 500 <= status <= 599:
                msg = T("Server side error (server code %s); could not get %s on %s") % (status, feed, uri)

            entries = feed_parsed.get("entries", [])
            if not entries and "feed" in feed_parsed and "error" in feed_parsed["feed"]:
                msg = T("Failed to retrieve RSS from %s: %s") % (uri, feed_parsed["feed"]["error"])

            # Exception was thrown
            if "bozo_exception" in feed_parsed and not entries:
                msg = str(feed_parsed["bozo_exception"])
                if "CERTIFICATE_VERIFY_FAILED" in msg:
                    msg = T("Server %s uses an untrusted HTTPS certificate") % get_base_url(uri)
                    msg += " - https://sabnzbd.org/certificate-errors"
                elif "href" in feed_parsed and feed_parsed["href"] != uri and "login" in feed_parsed["href"]:
                    # Redirect to login page!
                    msg = T("Do not have valid authentication for feed %s") % uri
                else:
                    msg = T("Failed to retrieve RSS from %s: %s") % (uri, msg)

            if msg:
                # We need to escape any "%20" that could be in the warning due to the URL's
                helpful_warning(urllib.parse.unquote(msg))
            elif not entries:
                msg = T("RSS Feed %s was empty") % uri
                logging.info(msg)

            for entry in entries:
                normalised = ResolvedEntry.from_feed(feed, entry)
                if not normalised:
                    continue
                # Merge the existing state
                existing = self.store.get_job(feed, normalised.link)
                if existing:
                    normalised.merge(existing)
                all_entries.append(normalised)

        return all_entries, msg

    @staticmethod
    def _evaluate_entry(
        *,
        entry: ResolvedEntry,
        filters: FeedConfig,
        first: bool,
        download: bool,
        force: bool,
        readout: bool,
    ) -> tuple[Optional[FeedEvaluation], Optional[bool], Optional[bool]]:
        """Evaluate a normalised entry against filters

        Returns a tuple (evaluation, should_download, star) or None if the entry should be skipped.
        """
        if entry.status not in "NGB" and not (entry.status == "X" and readout):
            return None, None, None

        # Match this title against all filters
        logging.debug("Trying title=%r, size=%d", entry.title, entry.size)
        evaluation = filters.evaluate(
            title=entry.title,
            category=entry.orgcat,
            size=entry.size,
            season=entry.season,
            episode=entry.episode,
        )

        is_starred = entry.status.endswith("*")
        star = first or is_starred
        should_download = (download and not first and not is_starred) or force

        return evaluation, should_download, star

    def enqueue_download(self, update: ResolvedEntry) -> None:
        if not update.status == "D":
            return
        if not update.downloaded_at:
            self.store.flag_downloaded(update)

        nzbname = None if special_rss_site(update.link) else update.title

        logging.info("Adding %s (%s) to queue", update.link, update.title)
        sabnzbd.urlgrabber.add_url(
            update.link,
            pp=update.pp,
            script=update.script,
            cat=update.cat,
            priority=update.priority,
            nzbname=nzbname,
            nzo_info={"RSS": update.feed},
        )

    def _process_entry(
        self,
        *,
        feed: str,
        entry: NormalisedEntry,
        evaluation: FeedEvaluation,
        should_download: bool,
        is_starred: bool,
    ) -> bool:
        """Apply side effects for a single normalised entry.

        Returns True if the entry was queued for download.
        """
        if should_download and evaluation.matched:
            status = "D"
        elif is_starred and evaluation.matched:
            status = "G*"
        elif evaluation.matched:
            status = "G"
        else:
            status = "B"

        update = ResolvedEntry(
            feed=feed,
            link=entry.link,
            title=entry.title,
            infourl=entry.infourl,
            size=entry.size,
            age=entry.age,
            season=evaluation.season,
            episode=evaluation.episode,
            orgcat=entry.orgcat,
            cat=evaluation.category,
            pp=evaluation.pp,
            script=evaluation.script,
            priority=evaluation.priority,
            rule=evaluation.rule_index,
            status=status,
            downloaded_at=datetime.datetime.now() if status == "D" else None,
        )

        self.store.upsert(update)
        self.enqueue_download(update)

        return bool(evaluation.matched and should_download)

    def run(self):
        """Run all the URI's and filters"""
        if not sabnzbd.PAUSED_ALL:
            active = False
            if self.next_run < time.time():
                self.next_run = time.time() + cfg.rss_rate() * 60
            feeds = config.get_rss()
            try:
                for feed in feeds:
                    if feeds[feed].enable():
                        logging.info('Starting scheduled RSS read-out for "%s"', feed)
                        active = True
                        self.run_feed(feed, download=True, ignore_first=True)
                        # Wait 15 seconds, else sites may get irritated
                        for _ in range(15):
                            if self.shutdown:
                                return
                            else:
                                time.sleep(1.0)
            except (KeyError, RuntimeError):
                # Feed must have been deleted
                logging.info("RSS read-out crashed, feed must have been deleted or edited")
                logging.debug("Traceback: ", exc_info=True)
                pass
            finally:
                self.store = None
            if active:
                logging.info("Finished scheduled RSS read-outs")


def _normalise_str_or_none(value: Optional[str]) -> Optional[str]:
    """Normalise default values to None"""
    if not value:
        return None
    v = str(value).strip()
    if v.lower() in ("", "*", "default"):
        return None
    return v


def _normalise_priority(value) -> Optional[int]:
    """Normalise default priority values to None"""
    if value in (None, "", "*", "default", DEFAULT_PRIORITY):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalise_pp(value) -> Optional[int]:
    """Normalise pp value to an int between 0 and 3, or None if invalid/empty."""
    if value in (None, ""):
        return None
    try:
        iv = int(value)
        if 0 <= iv <= 3:
            return iv
    except (TypeError, ValueError):
        pass
    return None


def first_not_none(*args):
    """Return first value which is not None"""
    for a in args:
        if a is not None:
            return a
    return None


def special_rss_site(url: str) -> bool:
    """Return True if url describes an RSS site with odd titles"""
    return cfg.rss_filenames() or match_str(url, cfg.rss_odd_titles())
