#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.rssmodels - models for rss functionality
"""

import re
import logging
import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import sqlite3

from sabnzbd.constants import DEFAULT_PRIORITY
from sabnzbd.misc import (
    from_units,
    int_conv,
)

import feedparser


_RE_SIZE1 = re.compile(r"Size:\s*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_SIZE2 = re.compile(r"\W*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_BR = re.compile(r"<br\s*/?>", re.I)  # Strip content after first <br/>
_RE_TAG = re.compile(r"<[^>]+>")  # Strip HTML tags from descriptions


class RSSState(str, Enum):
    """Primary RSS entry state."""

    NEW = "N"  # Seen but not evaluated yet
    GOOD = "G"  # Matched by filter rules (should be grabbed)
    BAD = "B"  # Rejected by filter rules
    DOWNLOADED = "D"  # Successfully downloaded to queue
    EXPIRED = "X"  # No longer in feed (marked for cleanup)


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
    created_at: datetime.datetime = datetime.datetime.now()  # When first seen and evaluated / mabe this is age?
    downloaded_at: Optional[datetime.datetime] = None  # What added to queue
    archived_at: Optional[datetime.datetime] = None  # What added to queue
    initial_scan: bool = True  # True if discovered during initial scan
    state: RSSState = RSSState.NEW
    cat: Optional[str] = None
    pp: Optional[int] = None
    script: Optional[str] = None
    priority: Optional[int] = None
    rule: Optional[int] = None

    def __post_init__(self):
        # Normalise "default-ish" values to None
        self.cat = normalise_str_or_none(self.cat)
        self.priority = normalise_priority(self.priority)
        self.pp = normalise_pp(self.pp)
        self.script = normalise_str_or_none(self.script)

    @property
    def is_good(self) -> bool:
        return self.state == RSSState.GOOD

    @property
    def is_bad(self) -> bool:
        return self.state == RSSState.BAD

    @property
    def is_downloaded(self) -> bool:
        return self.state == RSSState.DOWNLOADED

    @property
    def is_hidden(self) -> bool:
        return self.archived_at is not None

    @property
    def is_starred(self) -> bool:
        return self.initial_scan and self.is_good

    @property
    def is_expired(self) -> bool:
        return self.state == RSSState.EXPIRED

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
            created_at=(datetime.datetime.fromtimestamp(item["created_at"], tz=datetime.timezone.utc).astimezone()),
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


def normalise_str_or_none(value: Optional[str]) -> Optional[str]:
    """Normalise default values to None"""
    if not value:
        return None
    v = str(value).strip()
    if v.lower() in ("", "*", "default"):
        return None
    return v


def normalise_priority(value) -> Optional[int]:
    """Normalise default priority values to None"""
    if value in (None, "", "*", "default", DEFAULT_PRIORITY):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalise_pp(value) -> Optional[int]:
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
