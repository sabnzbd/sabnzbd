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
import time
import datetime
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Union, Optional, Any

import sabnzbd
from sabnzbd.constants import RSS_FILE_NAME, DEFAULT_PRIORITY
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

import feedparser

RSS_LOCK = threading.RLock()
_RE_SP = re.compile(r"s*(\d+)[ex](\d+)", re.I)
_RE_SIZE1 = re.compile(r"Size:\s*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_SIZE2 = re.compile(r"\W*(\d+\.\d+\s*[KMG]?)B\W*", re.I)


@dataclass(frozen=True)
class NormalisedEntry:
    link: Optional[str]
    infourl: Optional[str]
    category: Optional[str]
    title: str
    size: int
    age: Optional[datetime.datetime]
    season: int
    episode: int

    @classmethod
    def from_feed_entry(cls, entry: feedparser.FeedParserDict) -> Optional["NormalisedEntry"]:
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
            age = datetime.datetime(*entry["newznab"]["usenetdate_parsed"][:6])
        except Exception:
            # Date from feed (usually lags behind)
            try:
                # Convert it to format that calc_age understands
                age = datetime.datetime(*entry.published_parsed[:6])
            except Exception:
                pass
        finally:
            # We need to convert it to local timezone, feedparser always returns UTC
            age = age - datetime.timedelta(seconds=time.timezone)

        # Maybe the newznab also provided SxxExx info
        try:
            season = int_conv(re.findall(r"\d+", entry["newznab"]["season"])[0])
            episode = int_conv(re.findall(r"\d+", entry["newznab"]["episode"])[0])
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
                        category = entry.description
                    except AttributeError:
                        category = ""

        # Make sure spaces are quoted in the URL
        link = link.strip().replace(" ", "%20")

        return cls(
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
    def from_job_entry(cls, link: str, jobs: dict) -> "NormalisedEntry":
        """Build NormalisedEntry from an existing job (readout=False)"""
        job = jobs.get(link, {})
        category = job.get("orgcat") or None
        if category in ("", "*"):
            category = None
        # Make sure spaces are quoted in the URL
        link = link.strip().replace(" ", "%20")
        return cls(
            link=link,
            infourl=job.get("infourl"),
            category=category,
            title=job.get("title", ""),
            size=job.get("size", 0),
            age=job.get("age"),
            season=job.get("season", 0),
            episode=job.get("episode", 0),
        )

    def is_duplicate(self, jobs: dict[str, dict[str, Any]]) -> bool:
        """Check if a job with the same title and size already exists in another feed"""
        for job_link, job in jobs.items():
            # Allow 5% size deviation because indexers might have small differences for same release
            if (
                job.get("title") == self.title
                and self.link != job_link
                and (job.get("size") * 0.95) < self.size < (job.get("size") * 1.05)
            ):
                logging.info("Ignoring job %s from other feed", self.title)
                return True
        return False


@dataclass(frozen=True)
class ResolvedEntry:
    link: str
    title: str
    infourl: Optional[str]
    size: int
    age: Optional[datetime.datetime]
    season: int
    episode: int
    orgcat: Optional[str]

    cat: Optional[str]
    pp: Optional[int]
    script: Optional[str]
    priority: Optional[int]
    rule: int

    status: str  # "G", "B", "G*", "D"
    download: bool


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
        elif self.type == "F" and not self.episode_matches(season, episode, self.regex):
            logging.debug("Filter rejected on rule %d (episode too early)", rule_index)
            return False
        elif self.type == "S" and self.episode_matches(season, episode, self.regex, title):
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


class RSSReader:
    def __init__(self):
        self.jobs = {}
        self.next_run = time.time()
        self.shutdown = False

        try:
            self.jobs = sabnzbd.filesystem.load_admin(RSS_FILE_NAME)
            if self.jobs:
                for feed in self.jobs:
                    self.remove_obsolete(self.jobs[feed], list(self.jobs[feed]))
        except Exception:
            logging.warning(T("Cannot read %s"), RSS_FILE_NAME)
            logging.info("Traceback: ", exc_info=True)

        # Storage needs to be dict
        if not self.jobs:
            self.jobs = {}

        # jobs is a NAME-indexed dictionary
        #    Each element is link-indexed dictionary
        #        Each element is another dictionary:
        #           status : 'D', 'G', 'B', 'X' (downloaded, good-match, bad-match, obsolete)
        #               '*' added means: from the initial batch
        #               '-' added to 'D' means downloaded, but not displayed anymore
        #           title : Title
        #           url : URL
        #           cat : category
        #           orgcat : category as read from feed
        #           pp : pp
        #           script : script
        #           prio : priority
        #           time : timestamp (used for time-based clean-up)
        #           size : size in bytes
        #           age : age in datetime format as specified by feed
        #           season : season number (if applicable)
        #           episode : episode number (if applicable)

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

        new_links: list[str] = []
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

        # Set first if this is the very first scan of this URI
        first = (feed not in self.jobs) and ignore_first

        # In case of a new feed, ensure we have a jobs dict
        if feed not in self.jobs:
            self.jobs[feed] = {}
        jobs = self.jobs[feed]

        # Fetch & parse RSS
        if readout:
            entries, msg = self.fetch_rss(feed, uris)
        else:
            entries, msg = (jobs, "")

        # Error in readout or no new readout
        if readout and not entries:
            return msg

        # Normalise entries, evaluate rules and apply side effects
        for raw_entry in entries:
            if self.shutdown:
                return ""

            try:
                if readout:
                    feed_entry = NormalisedEntry.from_feed_entry(raw_entry)
                    if not feed_entry:
                        continue
                    # Skip duplicates across multiple feeds
                    if len(uris) > 1 and feed_entry.is_duplicate(jobs):
                        continue
                else:
                    feed_entry = NormalisedEntry.from_job_entry(raw_entry, jobs)
            except (AttributeError, IndexError):
                last_uri = uris[-1] if uris else ""
                logging.info(T("Incompatible feed") + " " + last_uri)
                logging.info("Traceback: ", exc_info=True)
                return T("Incompatible feed")
            if not feed_entry.link:
                continue

            # Track all valid links so obsolete ones can be cleaned up later
            new_links.append(feed_entry.link)

            evaluation, should_download, is_starred = self._evaluate_entry(
                feed_entry=feed_entry,
                jobs=jobs,
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
                feed_entry=feed_entry,
                jobs=jobs,
                evaluation=evaluation,
                should_download=should_download,
                is_starred=is_starred,
            )
            if downloaded:
                new_downloads.append(feed_entry.title)

        # Send email if wanted and not "forced"
        if new_downloads and cfg.email_rss() and not force:
            emailer.rss_mail(feed, new_downloads)

        self.remove_obsolete(jobs, new_links)

        return msg

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

    @staticmethod
    def remove_obsolete(jobs: dict[str, dict], new_jobs: list[str]):
        """Expire G/B links that are not in new_jobs (mark them 'X')
        Expired links older than 3 days are removed from 'jobs'
        """
        now = time.time()
        limit = now - 259200  # 3days (3x24x3600)
        for old in list(jobs):
            tm = jobs[old]["time"]
            if old not in new_jobs:
                if jobs[old].get("status", " ")[0] in ("G", "B"):
                    jobs[old]["status"] = "X"
            if jobs[old]["status"] == "X" and tm < limit:
                logging.debug("Purging link %s", old)
                del jobs[old]

    @staticmethod
    def fetch_rss(feed: str, uris: list[str]) -> tuple[list[feedparser.FeedParserDict], str]:
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
            all_entries.extend(entries)

        return all_entries, msg

    @staticmethod
    def _evaluate_entry(
        *,
        feed_entry: NormalisedEntry,
        jobs: dict,
        filters: FeedConfig,
        first: bool,
        download: bool,
        force: bool,
        readout: bool,
    ) -> tuple[Optional[FeedEvaluation], bool, bool]:
        """Evaluate a normalised entry against filters

        Returns a tuple (evaluation, should_download, star) or None if the entry should be skipped.
        """
        link = feed_entry.link
        job = jobs.get(link)
        job_status = job.get("status", " ")[0] if job else "N"

        if job_status not in "NGB" and not (job_status == "X" and readout):
            return None, False, False

        # Match this title against all filters
        logging.debug("Trying title=%r, size=%d", feed_entry.title, feed_entry.size)
        evaluation = filters.evaluate(
            title=feed_entry.title,
            category=feed_entry.category,
            size=feed_entry.size,
            season=feed_entry.season,
            episode=feed_entry.episode,
        )

        is_starred = bool(job and job.get("status", "").endswith("*"))
        star = first or is_starred
        should_download = (download and not first and not is_starred) or force

        return evaluation, should_download, star

    @staticmethod
    def update_job_entry(jobs: dict, resolved_entry: ResolvedEntry) -> None:
        """Update the stored job entry"""
        jobs[resolved_entry.link] = {
            "title": resolved_entry.title,
            "url": resolved_entry.link,
            "infourl": resolved_entry.infourl,
            "cat": resolved_entry.cat,
            "pp": resolved_entry.pp,
            "script": resolved_entry.script,
            "prio": resolved_entry.priority if resolved_entry.priority is not None else DEFAULT_PRIORITY,
            "orgcat": resolved_entry.orgcat,
            "size": resolved_entry.size,
            "age": resolved_entry.age,
            "time": time.time(),
            "rule": resolved_entry.rule,
            "season": resolved_entry.season,
            "episode": resolved_entry.episode,
            "status": resolved_entry.status,
        }

        if resolved_entry.status == "D":
            jobs[resolved_entry.link]["time_downloaded"] = time.localtime()

    @staticmethod
    def enqueue_download(feed: str, resolved_entry: ResolvedEntry) -> None:
        if not resolved_entry.download:
            return

        nzbname = None if special_rss_site(resolved_entry.link) else resolved_entry.title

        logging.info("Adding %s (%s) to queue", resolved_entry.link, resolved_entry.title)
        sabnzbd.urlgrabber.add_url(
            resolved_entry.link,
            pp=resolved_entry.pp,
            script=resolved_entry.script,
            cat=resolved_entry.cat,
            priority=resolved_entry.priority,
            nzbname=nzbname,
            nzo_info={"RSS": feed},
        )

    def _process_entry(
        self,
        *,
        feed: str,
        jobs: dict[str, dict],
        feed_entry: NormalisedEntry,
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

        resolved_entry = ResolvedEntry(
            link=feed_entry.link,
            title=feed_entry.title,
            infourl=feed_entry.infourl,
            size=feed_entry.size,
            age=feed_entry.age,
            season=evaluation.season,
            episode=evaluation.episode,
            orgcat=feed_entry.category,
            cat=evaluation.category,
            pp=evaluation.pp,
            script=evaluation.script,
            priority=evaluation.priority,
            rule=evaluation.rule_index,
            status=status,
            download=(status == "D"),
        )

        self.update_job_entry(jobs, resolved_entry)
        self.enqueue_download(feed, resolved_entry)

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
                self.save()
                logging.info("Finished scheduled RSS read-outs")

    @synchronized(RSS_LOCK)
    def get_feed_jobs(self, feed):
        if feed in self.jobs:
            try:
                return self.jobs[feed]
            except Exception:
                return {}
        else:
            return {}

    @synchronized(RSS_LOCK)
    def save(self):
        sabnzbd.filesystem.save_admin(self.jobs, RSS_FILE_NAME)

    @synchronized(RSS_LOCK)
    def delete(self, feed):
        if feed in self.jobs:
            del self.jobs[feed]

    @synchronized(RSS_LOCK)
    def rename(self, old_feed, new_feed):
        if old_feed in self.jobs:
            old_data = self.jobs.pop(old_feed)
            self.jobs[new_feed] = old_data

    @synchronized(RSS_LOCK)
    def flag_downloaded(self, feed, fid):
        if feed in self.jobs:
            lst = self.jobs[feed]
            for link in lst:
                if lst[link].get("url", "") == fid:
                    lst[link]["status"] = "D"
                    lst[link]["time_downloaded"] = time.localtime()

    @synchronized(RSS_LOCK)
    def find_job_by_url(self, feed, url):
        if url and feed in self.jobs:
            lst = self.jobs[feed]
            for link in lst:
                if lst[link].get("url") == url:
                    return lst[link]
        return None

    @synchronized(RSS_LOCK)
    def clear_feed(self, feed):
        # Remove any previous references to this feed name, and start fresh
        if feed in self.jobs:
            del self.jobs[feed]

    @synchronized(RSS_LOCK)
    def clear_downloaded(self, feed):
        # Mark downloaded jobs, so that they won't be displayed any more.
        if feed in self.jobs:
            for item in self.jobs[feed]:
                if self.jobs[feed][item]["status"] == "D":
                    self.jobs[feed][item]["status"] = "D-"


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
    return cfg.rss_filenames() or match_str(url, cfg.rss_odd_titles())
