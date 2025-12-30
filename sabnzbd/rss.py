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
sabnzbd.rss - rss client functionality
"""

import re
import logging
import time
import datetime
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Union, Optional

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

    def is_duplicate(self, jobs: dict[str, dict]) -> bool:
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

        new_links: list[str] = []
        new_downloads: list[str] = []

        # Configuration
        uris, filters, first, jobs, config_error = self.configure_rss(feed, ignore_first)
        if config_error:
            return config_error

        # Fetch & parse RSS
        if readout:
            entries, msg = self.fetch_rss(feed, uris)
        else:
            entries, msg = (jobs, "")

        # Error in readout or no new readout
        if readout and not entries:
            return msg

        # Normalise entries, evaluate rules and apply side effects
        for entry in entries:
            if self.shutdown:
                return ""

            try:
                if readout:
                    normalised = NormalisedEntry.from_feed_entry(entry)
                    if not normalised:
                        continue
                    # Skip duplicates across multiple feeds
                    if len(uris) > 1 and self.is_duplicate(normalised, jobs):
                        continue
                else:
                    normalised = NormalisedEntry.from_job_entry(entry, jobs)
            except (AttributeError, IndexError):
                last_uri = uris[-1] if uris else ""
                logging.info(T("Incompatible feed") + " " + last_uri)
                logging.info("Traceback: ", exc_info=True)
                return T("Incompatible feed")

            if not normalised.link:
                continue

            # Track all valid links so obsolete ones can be cleaned up later
            new_links.append(normalised.link)

            evaluation, should_download, is_starred = self._evaluate_entry(
                entry=normalised,
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
                entry=normalised,
                jobs=jobs,
                evaluation=evaluation,
                should_download=should_download,
                is_starred=is_starred,
            )
            if downloaded:
                new_downloads.append(normalised.title)

        # Send email if wanted and not "forced"
        if new_downloads and cfg.email_rss() and not force:
            emailer.rss_mail(feed, new_downloads)

        self.remove_obsolete(jobs, new_links)

        return msg

    def configure_rss(
        self, feed: str, ignore_first: bool
    ) -> tuple[list[str], Optional[FeedConfig], bool, dict, Optional[str]]:
        """Prepare configuration and state for a feed run.

        Returns (uris, filters, first, jobs, error_message).
        If `error_message` is not empty, the caller should abort and return it.
        """
        # Preparations, get options
        try:
            feeds = config.get_rss()[feed]
        except KeyError:
            logging.error(T('Incorrect RSS feed description "%s"'), feed)
            logging.info("Traceback: ", exc_info=True)
            return [], None, False, {}, T('Incorrect RSS feed description "%s"') % feed

        uris = feeds.uri()
        filters = FeedConfig.from_config(feeds)

        # Set first if this is the very first scan of this URI
        first = (feed not in self.jobs) and ignore_first

        # In case of a new feed, ensure we have a jobs dict
        if feed not in self.jobs:
            self.jobs[feed] = {}
        jobs = self.jobs[feed]

        return uris, filters, first, jobs, ""

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
        entry: NormalisedEntry,
        jobs: dict,
        filters: FeedConfig,
        first: bool,
        download: bool,
        force: bool,
        readout: bool,
    ) -> tuple[Optional[FeedEvaluation], Optional[bool], Optional[bool]]:
        """Evaluate a normalised entry against filters

        Returns a tuple (evaluation, should_download, star) or None if the entry should be skipped.
        """
        link = entry.link
        job = jobs.get(link)
        job_status = job.get("status", " ")[0] if job else "N"

        if job_status not in "NGB" and not (job_status == "X" and readout):
            return None, None, None

        # Match this title against all filters
        logging.debug("Trying title=%r, size=%d", entry.title, entry.size)
        evaluation = filters.evaluate(
            title=entry.title,
            category=entry.category,
            size=entry.size,
            season=entry.season,
            episode=entry.episode,
        )

        is_starred = job and job.get("status", "").endswith("*")
        star = first or is_starred
        should_download = (download and not first and not is_starred) or force

        return evaluation, should_download, star

    @staticmethod
    def update_job_entry(jobs: dict, update: ResolvedEntry) -> None:
        """Update the stored job entry"""
        jobs[update.link] = {
            "title": update.title,
            "url": update.link,
            "infourl": update.infourl,
            "cat": update.cat,
            "pp": update.pp,
            "script": update.script,
            "prio": str(update.priority) if update.priority is not None else str(DEFAULT_PRIORITY),
            "orgcat": update.orgcat,
            "size": update.size,
            "age": update.age,
            "time": time.time(),
            "rule": str(update.rule),
            "season": str(update.season),
            "episode": str(update.episode),
            "status": update.status,
        }

        if update.status == "D":
            jobs[update.link]["time_downloaded"] = time.localtime()

    @staticmethod
    def enqueue_download(feed: str, update: ResolvedEntry) -> None:
        if not update.download:
            return

        nzbname = None if special_rss_site(update.link) else update.title

        logging.info("Adding %s (%s) to queue", update.link, update.title)
        sabnzbd.urlgrabber.add_url(
            update.link,
            pp=update.pp,
            script=update.script,
            cat=update.cat,
            priority=update.priority,
            nzbname=nzbname,
            nzo_info={"RSS": feed},
        )

    @staticmethod
    def is_duplicate(entry: NormalisedEntry, jobs: dict[str, dict]) -> bool:
        """Check if a job with the same title and size already exists in another feed"""
        for job_link, job in jobs.items():
            # Allow 5% size deviation because indexers might have small differences for same release
            if (
                job.get("title") == entry.title
                and entry.link != job_link
                and (job.get("size") * 0.95) < entry.size < (job.get("size") * 1.05)
            ):
                logging.info("Ignoring job %s from other feed", entry.title)
                return True
        return False

    def _process_entry(
        self,
        *,
        feed: str,
        jobs: dict[str, dict],
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
            link=entry.link,
            title=entry.title,
            infourl=entry.infourl,
            size=entry.size,
            age=entry.age,
            season=evaluation.season,
            episode=evaluation.episode,
            orgcat=entry.category,
            cat=evaluation.category,
            pp=evaluation.pp,
            script=evaluation.script,
            priority=evaluation.priority,
            rule=evaluation.rule_index,
            status=status,
            download=(status == "D"),
        )

        self.update_job_entry(jobs, update)
        self.enqueue_download(feed, update)

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
            if active:
                self.save()
                logging.info("Finished scheduled RSS read-outs")

    @synchronized(RSS_LOCK)
    def show_result(self, feed):
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
    def lookup_url(self, feed, url):
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
