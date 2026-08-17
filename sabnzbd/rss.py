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

import re
import logging
import sqlite3
import time
import datetime
import threading
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional, Any, Generator, Iterable
from enum import Enum
from dateutil.relativedelta import relativedelta
from more_itertools import batched

import sabnzbd
from sabnzbd.constants import RSS_FILE_NAME, DEFAULT_PRIORITY
from sabnzbd.database import HistoryDB, convert_search
from sabnzbd.decorators import synchronized
from sabnzbd.nzb import NzoInfo
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

import feedparser

RSS_LOCK = threading.RLock()
_RE_SP = re.compile(r"s*(\d+)[ex](\d+)", re.I)
_RE_SIZE1 = re.compile(r"Size:\s*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_SIZE2 = re.compile(r"\W*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_BR = re.compile(r"<br\s*/?>", re.I)  # Strip content after first <br/>
_RE_TAG = re.compile(r"<[^>]+>")  # Strip HTML tags from descriptions
# Age rule value, e.g. ">3d", "<=12h", "1y", "6mo".
# Optional leading comparator (<, >, <=, >=; the reversed =<, => are accepted too),
# an integer amount and an optional unit suffix (years/months/weeks/days/hours/minutes/seconds).
_RE_AGE = re.compile(r"^\s*(<=|>=|=<|=>|[<>])?\s*(\d+)\s*(mo|[ywdhms])?\s*$", re.I)
# Map to relativedelta keyword so calendar units (years/months) honor variable-length months/leap days relative to "now".
_AGE_UNIT_FIELD = {
    "y": "years",
    "mo": "months",
    "w": "weeks",
    "d": "days",
    "h": "hours",
    "m": "minutes",
    "s": "seconds",
}


class RSSState(str, Enum):
    """Primary RSS entry state."""

    GOOD = "G"  # Matched by filter rules (should be grabbed)
    BAD = "B"  # Rejected by filter rules
    DOWNLOADED = "D"  # Successfully downloaded to queue
    EXPIRED = "X"  # No longer in feed (marked for cleanup)


class FeedRuleType(str, Enum):
    """Type of RSS feed filter rule"""

    ACCEPT = "A"  # Accept on title regex match (positive)
    MUST = "M"  # Reject unless title regex matches (mandatory)
    REJECT = "R"  # Reject on title regex match
    CATEGORY = "C"  # Reject unless category regex matches
    AT_MOST = "<"  # Reject if size is larger than value
    AT_LEAST = ">"  # Reject if size is smaller than value
    FROM = "F"  # Reject episodes before the given SxxEyy
    FROM_SHOW = "S"  # Accept given show from the given SxxEyy onwards
    AGE = "G"  # Reject if entry age is outside the given bound


NON_REGEX_FEED_RULE_TYPES = frozenset(
    {
        FeedRuleType.AT_MOST,
        FeedRuleType.AT_LEAST,
        FeedRuleType.FROM,
        FeedRuleType.FROM_SHOW,
        FeedRuleType.AGE,
    }
)


@dataclass(slots=True)
class ResolvedEntry:
    feed: str
    link: str
    infourl: Optional[str]
    category: Optional[str]
    title: str
    size: int
    age: Optional[datetime.datetime]
    season: int
    episode: int
    seen_at: datetime.datetime = field(
        # When last seen in feed and evaluated
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    downloaded_at: Optional[datetime.datetime] = None  # When added to queue
    archived_at: Optional[datetime.datetime] = None  # When expired
    initial_scan: bool = True  # True if discovered during initial scan
    state: Optional[RSSState] = None
    cat: Optional[str] = None
    pp: Optional[int] = None
    script: Optional[str] = None
    priority: Optional[int] = None
    rule: Optional[int] = None

    def __post_init__(self):
        # Normalise "default-ish" values to None
        self.cat = _normalise_str_or_none(self.cat)
        priority = _normalise_priority(self.priority)
        self.priority = priority if priority is not None else DEFAULT_PRIORITY
        self.pp = _normalise_pp(self.pp)
        self.script = _normalise_str_or_none(self.script)

    @property
    def is_good(self) -> bool:
        return self.state is RSSState.GOOD

    @property
    def is_bad(self) -> bool:
        return self.state is RSSState.BAD

    @property
    def is_downloaded(self) -> bool:
        return self.state is RSSState.DOWNLOADED

    @property
    def is_expired(self) -> bool:
        return self.state is RSSState.EXPIRED

    @property
    def is_starred(self) -> bool:
        return self.initial_scan and self.is_good

    @property
    def is_special_rss_site(self) -> bool:
        """Return True if url describes an RSS site with odd titles"""
        return bool(cfg.rss_filenames() or match_str(self.link, cfg.rss_odd_titles()))

    @property
    def nzbname(self) -> Optional[str]:
        return None if self.is_special_rss_site else self.title

    def merge(self, existing: "ResolvedEntry"):
        """Merge existing entry into self"""
        self.cat = existing.cat
        self.pp = existing.pp
        self.script = existing.script
        self.priority = existing.priority
        self.rule = existing.rule
        self.state = existing.state
        self.downloaded_at = existing.downloaded_at

    @classmethod
    def from_feed_entry(cls, feed: str, entry: feedparser.FeedParserDict) -> Optional["ResolvedEntry"]:
        """Build NormalisedEntry from feedparser entry"""
        link: str = ""
        size: int = 0
        # Unknown until a date is parsed from the feed; age filters skip a None age
        age: Optional[datetime.datetime] = None

        # Try standard link and enclosures first
        if entry.get("enclosures"):
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

        # Maybe the newznab also provided SxxExx info
        try:
            season = int_conv(re.findall(r"\d+", entry["newznab"]["season"])[0])
            episode = int_conv(re.findall(r"\d+", entry["newznab"]["episode"])[0])
        except (KeyError, IndexError):
            season = episode = 0

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
                        # Split on any <br>, <br/>, <br /> (case-insensitive) to avoid some large descriptions
                        category = _RE_TAG.sub("", _RE_BR.split(entry.description, maxsplit=1)[0]).strip()
                    except AttributeError:
                        category = ""

        # Make sure spaces are quoted in the URL
        link = link.strip().replace(" ", "%20")

        if not link or not link.lower().startswith("http"):
            logging.info(T("Empty RSS entry found (%s)"), link)
            return None

        return cls(
            feed=feed,
            link=link,
            infourl=infourl,
            category=category,
            title=entry.title,
            size=size,
            age=age,
            season=season,
            episode=episode,
        )

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
            category=item["category"],
            cat=item["cat"],
            pp=item["pp"],
            script=item["script"],
            priority=item["priority"],
            rule=item["rule"],
            state=RSSState(item["state"]),
            initial_scan=bool(item["initial_scan"]),
            downloaded_at=(
                datetime.datetime.fromtimestamp(item["downloaded_at"], tz=datetime.timezone.utc).astimezone()
                if item["downloaded_at"]
                else None
            ),
            archived_at=(
                datetime.datetime.fromtimestamp(item["archived_at"], tz=datetime.timezone.utc).astimezone()
                if item["archived_at"]
                else None
            ),
            seen_at=(datetime.datetime.fromtimestamp(item["seen_at"], tz=datetime.timezone.utc).astimezone()),
        )


@dataclass(frozen=True, slots=True)
class FeedEvaluation:
    matched: bool
    rule_index: int
    season: int
    episode: int
    category: Optional[str] = None
    priority: Optional[int] = None
    pp: Optional[int] = None
    script: Optional[str] = None


@dataclass(slots=True)
class FeedRule:
    type: str
    value: str
    regex: Optional[re.Pattern] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    pp: Optional[int] = None
    script: Optional[str] = None
    enabled: bool = True

    def __post_init__(self):
        # Convert regex if needed
        if self.type not in NON_REGEX_FEED_RULE_TYPES:
            self.regex = convert_filter(self.value)
        # Normalise "default-ish" values to None
        self.category = _normalise_str_or_none(self.category)
        self.priority = _normalise_priority(self.priority)
        self.pp = _normalise_pp(self.pp)
        self.script = _normalise_str_or_none(self.script)

    def matches(
        self,
        *,
        title: str,
        category: Optional[str],
        size: int,
        season: int,
        episode: int,
        rule_index: int,
        age: Optional[datetime.datetime] = None,
    ) -> Optional[bool]:
        """
        Returns:
            True  -> positive match
            False -> negative match
            None  -> rule does not apply
        """
        # Category rule
        if category and self.type == FeedRuleType.CATEGORY:
            found = bool(self.regex is not None and re.search(self.regex, category))
            if not found:
                logging.debug("Filter rejected on rule %d (category mismatch)", rule_index)
                return False

        # Size rules
        elif self.type == FeedRuleType.AT_MOST and size and from_units(self.value) < size:
            logging.debug("Filter rejected on rule %d (size too large)", rule_index)
            return False
        elif self.type == FeedRuleType.AT_LEAST and size and from_units(self.value) > size:
            logging.debug("Filter rejected on rule %d (size too small)", rule_index)
            return False

        # Age rule (age is optional; a missing age means the rule does not apply)
        elif self.type == FeedRuleType.AGE:
            if age is not None and not self.age_matches(age, self.value):
                logging.debug("Filter rejected on rule %d (age out of bounds)", rule_index)
                return False

        # Episode / season rules
        elif self.type == FeedRuleType.FROM and not self.episode_matches(season, episode, self.value):
            logging.debug("Filter rejected on rule %d (episode too early)", rule_index)
            return False
        elif self.type == FeedRuleType.FROM_SHOW and self.episode_matches(season, episode, self.value, title):
            logging.debug("Filter matched on rule %d (show SxxEyy match)", rule_index)
            return True

        # Title regex match
        if self.regex:
            found = bool(re.search(self.regex, title))
        else:
            found = False

        # Standard match types
        if self.type == FeedRuleType.MUST and not found:
            logging.debug("Filter rejected on rule %d (mandatory match failed)", rule_index)
            return False
        if self.type == FeedRuleType.ACCEPT and found:
            logging.debug("Filter matched on rule %d (always match)", rule_index)
            return True
        if self.type == FeedRuleType.REJECT and found:
            logging.debug("Filter rejected on rule %d (reject match)", rule_index)
            return False

        return None

    @staticmethod
    def age_matches(age: datetime.datetime, expr: str) -> bool:
        """Return True if the entry `age` satisfies the age bound `expr`.

        expr is a comparator (>/>= minimum age, </<= maximum age; the reversed
        =>/=< are accepted too) followed by an amount and optional unit suffix
        (y/mo/w/d/h/m/s, default days), e.g. ">3d", "<=12h", "1y", "6mo". Because
        age is compared against a live clock, the inclusive/strict distinction is
        a measure-zero boundary, so >= is treated as an alias of > (and <= of <).
        A bare value with no comparator is treated as a maximum age, i.e. only
        recent entries pass. Unparseable expressions are ignored (match).
        """
        m = _RE_AGE.match(expr or "")
        if not m:
            logging.debug("Ignoring unparseable age filter %r", expr)
            return True

        comparator = m.group(1) or "<"
        amount = int(m.group(2))
        unit = (m.group(3) or "d").lower()

        # Cutoff instant; using relativedelta means calendar units (years) respect
        # variable-length years/leap days relative to "now" (age is always tz-aware).
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - relativedelta(**{_AGE_UNIT_FIELD[unit]: amount})

        match comparator:
            case ">" | ">=" | "=>":
                # Minimum age: entry must be at least this old (older than the cutoff)
                return age <= cutoff
            case _:
                # "<", "<=", "=<" or bare -> maximum age: entry no older than the cutoff
                return age >= cutoff

    @staticmethod
    def episode_matches(season: int, episode: int, expr: str, title: Optional[str] = None):
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


@dataclass(slots=True)
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
        for cat, pp, script, filter_type, value, priority, enabled in c.filters():
            rules.append(
                FeedRule(
                    type=filter_type,
                    value=value,
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
        age: Optional[datetime.datetime] = None,
    ) -> FeedEvaluation:
        """Evaluate rules for a single RSS entry."""
        entry_cat = category
        rule_matched: bool = False
        last_rule: Optional[FeedRule] = None
        last_rule_index: int = 0
        feed_season: int = season
        feed_episode: int = episode

        # Start from feed defaults for options.
        resolved_cat: Optional[str] = self.default_category
        resolved_pp: Optional[int] = self.default_pp
        resolved_script: Optional[str] = self.default_script
        resolved_priority: Optional[int] = self.default_priority

        # Fill in missing season / episode information when F/S rules exist
        if self.has_type("F", "S") and (not feed_season or not feed_episode):
            show_analysis = sabnzbd.sorting.BasicAnalyzer(title)
            feed_season = int_conv(show_analysis.info.get("season_num"))
            feed_episode = int_conv(show_analysis.info.get("episode_num"))

        # Match against all filters until a positive or negative match
        for idx, rule in enumerate(self.rules):
            if not rule.enabled:
                continue

            outcome = rule.matches(
                title=title,
                category=entry_cat,
                size=size,
                season=feed_season,
                episode=feed_episode,
                rule_index=idx,
                age=age,
            )

            if outcome is None:
                continue

            last_rule = rule
            last_rule_index = idx
            rule_matched = outcome
            break

        rule_has_category = bool(last_rule and last_rule.category)

        # Category resolution
        if not rule_matched and self.default_category:
            effective_category = self.default_category
        elif rule_matched and rule_has_category:
            effective_category = last_rule.category
        elif entry_cat and not self.default_category:
            effective_category = cat_convert(entry_cat)
        else:
            effective_category = resolved_cat

        # Category-derived defaults
        if effective_category:
            resolved_cat, cat_pp, cat_script, cat_prio = cat_to_opts(effective_category)
            cat_pp = _normalise_pp(cat_pp)
            cat_script = _normalise_str_or_none(cat_script)
            cat_prio = _normalise_priority(cat_prio)
        else:
            resolved_cat = cat_pp = cat_script = cat_prio = None

        # PP resolution
        if last_rule and last_rule.pp is not None:
            resolved_pp = last_rule.pp
        elif not (rule_has_category or entry_cat):
            resolved_pp = cat_pp

        # Script resolution
        if last_rule and last_rule.script is not None:
            resolved_script = last_rule.script
        elif not (rule_has_category or entry_cat):
            resolved_script = cat_script

        # Priority resolution
        if last_rule and last_rule.priority not in (DEFAULT_PRIORITY, None):
            resolved_priority = last_rule.priority
        elif not ((last_rule and last_rule.priority != DEFAULT_PRIORITY) or entry_cat):
            resolved_priority = cat_prio

        return FeedEvaluation(
            matched=rule_matched,
            rule_index=last_rule_index,
            season=feed_season,
            episode=feed_episode,
            category=resolved_cat,
            pp=resolved_pp,
            script=resolved_script,
            priority=resolved_priority,
        )


class RSSRepository:
    def __init__(self, db: HistoryDB):
        self.db = db

    def remove_obsolete(self, feed: str, new_urls: Optional[Iterable[str]] = None, purge_downloaded: bool = False):
        """
        Expire G/B links that are not in new_jobs (mark them 'X')

        Expired links older than 3 days are removed
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        limit = int((now - datetime.timedelta(days=3)).timestamp())

        if new_urls:
            # Create temporary table for all new URLs
            self.db.execute("CREATE TEMP TABLE temp_urls(url TEXT PRIMARY KEY)")

            # Insert all new URLs in batches; SQLite can "only" do 999 per query
            for batch in batched(new_urls, 500):
                placeholders = ",".join(["(?)"] * len(batch))
                self.db.execute(f"INSERT INTO temp_urls(url) VALUES {placeholders}", batch)

            # Update rss to mark G/B not in temp_urls as X
            self.db.execute(
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
            self.db.execute("DROP TABLE temp_urls")

        # Purge
        if purge_downloaded:
            states = (RSSState.EXPIRED, RSSState.DOWNLOADED)
        else:
            states = (RSSState.EXPIRED,)
        placeholders = ", ".join("?" for _ in states)
        if not self.db.execute(
            f"""
            SELECT url FROM rss
            WHERE feed = ?
              AND state in ({placeholders})
              AND seen_at < ?
        """,
            (
                feed,
                *states,
                limit,
            ),
        ):
            return

        expired_urls = [row["url"] for row in self.db.cursor]
        for batch in batched(expired_urls, 500):
            for url in batch:
                logging.debug("Purging link %s", url)
            placeholders = ",".join("?" * len(batch))
            self.db.execute(f"DELETE FROM rss WHERE feed = ? AND url IN ({placeholders})", (feed, *batch))

    def get_feed_jobs(
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

        if self.db.execute(cmd, command_args):
            for item in self.db.cursor:
                yield ResolvedEntry.from_sqlite(item)

    def find_job_by_url(self, feed: str, url: str) -> Optional[ResolvedEntry]:
        if not feed or not url:
            return None
        if self.db.execute("SELECT * FROM rss WHERE feed = ? AND url = ?", (feed, url)):
            row = self.db.cursor.fetchone()
            if row is None:
                return None
            return ResolvedEntry.from_sqlite(row)
        return None

    def clear_feed(self, feed: str):
        """Permanently remove job from the history"""
        self.db.execute("""DELETE FROM rss WHERE feed = ?""", (feed,))

    def get_feeds(self) -> list[str]:
        self.db.execute("SELECT DISTINCT feed from rss")
        return [row["feed"] for row in self.db.cursor]

    def clear_downloaded(self, feed: str):
        """Mark downloaded jobs so that they won't be displayed anymore"""
        self.db.execute(
            "UPDATE rss SET archived_at = ? WHERE feed = ? AND state = ?",
            (
                int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                feed,
                RSSState.DOWNLOADED,
            ),
        )

    def has_feed(self, feed: str) -> bool:
        self.db.execute("SELECT EXISTS(SELECT 1 FROM rss WHERE feed = ?) AS found", (feed,))
        return bool(self.db.cursor.fetchone()["found"])

    def upsert(self, entry: ResolvedEntry):
        """Add or update a rss job entry in the database"""
        t = self.build_entry_info(entry)

        self.db.execute(
            """
            INSERT INTO rss (
                feed, state, title, url, infourl, category, cat, pp, script, priority,
                season, episode, size, rule, age, initial_scan, seen_at, downloaded_at, archived_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(feed, url) DO UPDATE SET
                state         = excluded.state,
                title         = excluded.title,
                infourl       = excluded.infourl,
                category      = excluded.category,
                cat           = excluded.cat,
                pp            = excluded.pp,
                script        = excluded.script,
                priority      = excluded.priority,
                season        = excluded.season,
                episode       = excluded.episode,
                size          = excluded.size,
                rule          = excluded.rule,
                age           = excluded.age,
                initial_scan  = excluded.initial_scan,
                seen_at       = COALESCE(excluded.seen_at, rss.seen_at),
                downloaded_at = COALESCE(excluded.downloaded_at, rss.downloaded_at),
                archived_at   = COALESCE(excluded.archived_at, rss.archived_at)
            """,
            t,
        )

    @staticmethod
    def build_entry_info(entry: ResolvedEntry):
        """Collects all the information needed for the database"""
        return (
            entry.feed,
            entry.state,
            entry.title,
            entry.link,
            entry.infourl,
            entry.category,
            entry.cat,
            entry.pp,
            entry.script,
            entry.priority,
            entry.season,
            entry.episode,
            entry.size,
            entry.rule,
            # age column is NOT NULL; fallback to seen_at (now) when the feed gave no date
            int((entry.age or entry.seen_at).timestamp()),
            entry.initial_scan,
            int(entry.seen_at.timestamp()),
            int(entry.downloaded_at.timestamp()) if entry.downloaded_at else None,
            int(entry.archived_at.timestamp()) if entry.archived_at else None,
        )

    def rename(self, old_feed: str, new_feed: str):
        """Rename all rows for a given feed to a new feed name."""
        # Remove conflicts because the same URL already exists for the new feed
        self.db.execute(
            """
            DELETE
            FROM rss
            WHERE feed = ?
              AND EXISTS (SELECT 1 FROM rss existing WHERE existing.feed = ? AND existing.url = rss.url)
            """,
            (old_feed, new_feed),
        )
        self.db.execute("UPDATE rss SET feed = ? WHERE feed = ?", (new_feed, old_feed))

    def flag_downloaded(self, feed: str, url: str):
        if not feed or not url:
            return
        self.db.execute(
            "UPDATE rss SET state = ?, downloaded_at = ? WHERE feed = ? AND url = ?",
            (
                RSSState.DOWNLOADED,
                int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                feed,
                url,
            ),
        )

    def is_duplicate(self, entry: ResolvedEntry) -> bool:
        """
        Check if a job with the same title and size already exists in another feed

        Allow 5% size deviation because indexers might have small differences for same release
        """
        self.db.execute(
            "SELECT EXISTS(SELECT 1 FROM rss WHERE title = ? AND url <> ? AND size BETWEEN ? AND ?) AS found",
            (entry.title, entry.link, entry.size * 0.95, entry.size * 1.05),
        )
        return bool(self.db.cursor.fetchone()["found"])

    def purge_removed_feeds(self):
        """Remove all records of feeds that are no longer configured"""
        configured = set(config.get_rss())
        for feed in self.get_feeds():
            if feed not in configured:
                logging.debug("Purging records of removed feed %s", feed)
                self.clear_feed(feed)

    def import_rss_records(self):
        """Migrate old RSS database"""
        try:
            data = sabnzbd.filesystem.load_admin(RSS_FILE_NAME) or {}
            local_tz = datetime.datetime.now().astimezone().tzinfo
            for feed, jobs in data.items():
                for link, job in jobs.items():
                    category: Optional[str] = job.get("orgcat", None) or None
                    if category in ("", "*"):
                        category = None
                    if category is not None and len(category) > 128:
                        # Probably HTML content
                        category = _RE_TAG.sub("", _RE_BR.split(category, maxsplit=1)[0]).strip()
                    time_downloaded = (
                        # time.struct_time
                        datetime.datetime(
                            *job.get("time_downloaded")[:6],
                            tzinfo=datetime.timezone(datetime.timedelta(seconds=job.get("time_downloaded").tm_gmtoff)),
                        ).astimezone(datetime.timezone.utc)
                        if job.get("time_downloaded", None)
                        else None
                    )
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
                        category=category,
                        cat=job.get("cat", None),
                        pp=job.get("pp", None),
                        script=job.get("script", None),
                        priority=job.get("prio", None),
                        rule=int_conv(job.get("rule", None)),
                        state=RSSState(job.get("status", "")[:1]),
                        downloaded_at=time_downloaded,
                        seen_at=(
                            # float timestamp
                            datetime.datetime.fromtimestamp(job.get("time", 0))
                            .replace(tzinfo=local_tz)
                            .astimezone(datetime.timezone.utc)
                        ),
                        archived_at=(
                            # Time of archiving/hiding is not stored
                            time_downloaded
                            if job.get("status", "")[-1] == "-"
                            else None
                        ),
                        initial_scan=False,
                    )
                    self.upsert(entry)
        except Exception:
            logging.warning(T("Cannot read %s"), RSS_FILE_NAME)
            logging.info("Traceback: ", exc_info=True)


class RSSReader:
    def __init__(self):
        self.next_run = time.time()
        self.shutdown = False

        # Patch feedparser
        self.patch_feedparser()

    def stop(self):
        self.shutdown = True

    @synchronized(RSS_LOCK)
    def process_feed(
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
        try:
            feeds = config.get_rss()[feed]
        except KeyError:
            logging.error(T('Incorrect RSS feed description "%s"'), feed)
            logging.info("Traceback: ", exc_info=True)
            return T('Incorrect RSS feed description "%s"') % feed

        uris = feeds.uri()
        filters = FeedConfig.from_config(feeds)

        with sabnzbd.rss.rss_repository() as repo:
            # Set first if this is the very first scan of this URI
            first = (not repo.has_feed(feed)) and ignore_first

            # Fetch & parse RSS
            if readout:
                gen = self.fetch_rss(feed, uris)
            else:
                gen = repo.get_feed_jobs(feed=feed)

            # Evaluate rules and apply side effects
            try:
                for entry in gen:
                    if self.shutdown:
                        return ""

                    # Skip duplicates across multiple feeds
                    if entry.link in new_links or (len(uris) > 1 and repo.is_duplicate(entry)):
                        logging.info("Ignoring job %s from other feed", entry.title)
                        continue

                    # Track all valid links so obsolete ones can be cleaned up later
                    new_links.add(entry.link)

                    downloaded = self._process_entry(
                        repo,
                        feed_entry=entry,
                        filters=filters,
                        first=first,
                        download=download,
                        force=force,
                        readout=readout,
                    )
                    if downloaded:
                        new_downloads.append(entry.title)
            except RuntimeError as e:
                return str(e)

            # Send email if wanted and not "forced"
            if new_downloads and cfg.email_rss() and not force:
                emailer.rss_mail(feed, new_downloads)

            if readout:
                repo.remove_obsolete(feed, new_links, purge_downloaded=True)

        return ""

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

    def fetch_rss(self, feed: str, uris: list[str]) -> Generator[ResolvedEntry, Any, None]:
        """Fetch and parse RSS feeds for the given URIs."""

        with sabnzbd.rss.rss_repository() as repo:
            for uri in uris:
                try:
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
                        raise RuntimeError(T("Do not have valid authentication for feed %s") % uri)
                    elif 500 <= status <= 599:
                        raise RuntimeError(
                            T("Server side error (server code %s); could not get %s on %s") % (status, feed, uri)
                        )

                    entries = feed_parsed.get("entries", [])
                    if not entries and "feed" in feed_parsed and "error" in feed_parsed["feed"]:
                        raise RuntimeError(
                            T("Failed to retrieve RSS from %s: %s") % (uri, feed_parsed["feed"]["error"])
                        )

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
                        raise RuntimeError(msg)
                    elif not entries:
                        msg = T("RSS Feed %s was empty") % uri
                        logging.info(msg)
                        raise RuntimeError(msg)

                    for entry in entries:
                        normalised = ResolvedEntry.from_feed_entry(feed, entry)
                        if not normalised:
                            continue
                        # Merge the existing state
                        existing = repo.find_job_by_url(feed, normalised.link)
                        if existing:
                            normalised.merge(existing)
                        yield normalised
                except (AttributeError, IndexError):
                    logging.info(T("Incompatible feed") + " " + uri)
                    logging.info("Traceback: ", exc_info=True)
                    raise RuntimeError(T("Incompatible feed"))

    def _process_entry(
        self,
        repo: RSSRepository,
        *,
        feed_entry: ResolvedEntry,
        filters: FeedConfig,
        first: bool,
        download: bool,
        force: bool,
        readout: bool,
    ) -> bool:
        """Evaluate a normalised entry against filters

        Returns True if the entry was queued for download.
        """
        if feed_entry.state not in (None, RSSState.GOOD, RSSState.BAD) and not (feed_entry.is_expired and readout):
            return False

        # Match this title against all filters
        logging.debug("Trying title=%r, size=%d", feed_entry.title, feed_entry.size)
        evaluation = filters.evaluate(
            title=feed_entry.title,
            category=feed_entry.category,
            size=feed_entry.size,
            season=feed_entry.season,
            episode=feed_entry.episode,
            age=feed_entry.age,
        )

        is_starred = first or feed_entry.is_starred
        should_download = (download and not first and not feed_entry.is_starred) or force

        if should_download and evaluation.matched:
            state = RSSState.DOWNLOADED
        elif evaluation.matched:
            state = RSSState.GOOD
        else:
            state = RSSState.BAD

        initial_scan = bool(is_starred and state is RSSState.GOOD)

        resolved_entry = ResolvedEntry(
            feed=feed_entry.feed,
            link=feed_entry.link,
            title=feed_entry.title,
            infourl=feed_entry.infourl,
            size=feed_entry.size,
            age=feed_entry.age,
            season=evaluation.season,
            episode=evaluation.episode,
            category=feed_entry.category,
            cat=evaluation.category,
            pp=evaluation.pp,
            script=evaluation.script,
            priority=evaluation.priority,
            rule=evaluation.rule_index,
            state=state,
            downloaded_at=datetime.datetime.now() if state is RSSState.DOWNLOADED else None,
            initial_scan=initial_scan,
        )

        repo.upsert(resolved_entry)
        self.enqueue_download(repo, resolved_entry)

        return bool(evaluation.matched and should_download)

    def enqueue_download(self, repo: RSSRepository, resolved_entry: ResolvedEntry) -> None:
        if not resolved_entry.is_downloaded:
            return
        if not resolved_entry.downloaded_at:
            repo.flag_downloaded(resolved_entry.feed, resolved_entry.link)

        logging.info("Adding %s (%s) to queue", resolved_entry.link, resolved_entry.title)
        sabnzbd.urlgrabber.add_url(
            resolved_entry.link,
            pp=resolved_entry.pp,
            script=resolved_entry.script,
            cat=resolved_entry.cat,
            priority=resolved_entry.priority,
            nzbname=resolved_entry.nzbname,
            nzo_info=NzoInfo(RSS=resolved_entry.feed),
        )

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
                        self.process_feed(feed, download=True, ignore_first=True)
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
    if value in (None, "", "*", "default", DEFAULT_PRIORITY, str(DEFAULT_PRIORITY)):
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


def special_rss_site(url: str) -> bool:
    """Return True if url describes an RSS site with odd titles"""
    return bool(cfg.rss_filenames() or match_str(url, cfg.rss_odd_titles()))


def purge_removed_feeds():
    """Purge records of feeds that are no longer configured"""
    with rss_repository() as repo:
        repo.purge_removed_feeds()


@contextmanager
def rss_repository(db: Optional[sabnzbd.database.HistoryDB] = None):
    if db is None:
        with sabnzbd.db_pool.connection() as db:
            yield RSSRepository(db)
    else:
        yield RSSRepository(db)
