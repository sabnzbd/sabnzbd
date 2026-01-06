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
import weakref
from dataclasses import dataclass, field
from typing import Union, Optional

import sabnzbd
from sabnzbd.database import HistoryDB
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
from sabnzbd.rssmodels import (
    ResolvedEntry,
    NormalisedEntry,
    normalise_pp,
    normalise_str_or_none,
    normalise_priority,
    first_not_none,
    RSSState,
)

import feedparser

RSS_LOCK = threading.RLock()
_RE_SP = re.compile(r"s*(\d+)[ex](\d+)", re.I)


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
        self.category = normalise_str_or_none(self.category)
        self.priority = normalise_priority(self.priority)
        self.pp = normalise_pp(self.pp)
        self.script = normalise_str_or_none(self.script)

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
        self.default_category = normalise_str_or_none(self.default_category)
        if self.default_category not in sabnzbd.api.list_cats(default=False):
            self.default_category = None
        self.default_priority = normalise_priority(self.default_priority)
        self.default_pp = normalise_pp(self.default_pp)
        self.default_script = normalise_str_or_none(self.default_script)

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
            cat_pp = normalise_pp(cat_pp)
            cat_script = normalise_str_or_none(cat_script)
            cat_prio = normalise_priority(cat_prio)
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
        self.next_run = time.time()
        self.shutdown = False
        self._active_stores = weakref.WeakSet()
        self._thread_local = threading.local()

        # Patch feedparser
        self.patch_feedparser()

    def stop(self):
        self.shutdown = True
        for store in list(self._active_stores):
            store.close()

    @property
    def is_store_active(self):
        """Are there any stores still running?"""
        return any(self._active_stores)

    @property
    def store(self) -> HistoryDB:
        """Get the store for the current thread"""
        if not hasattr(self._thread_local, "store"):
            store = HistoryDB()
            self._active_stores.add(store)
            self._thread_local.store = store
        return self._thread_local.store

    @store.setter
    def store(self, db: Optional[HistoryDB]) -> None:
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
            entries, msg = (list(self.store.rss_get_jobs(feed=feed)), "")

        # Evaluate rules and apply side effects
        for entry in entries:
            if self.shutdown:
                return ""

            # Skip duplicates across multiple feeds
            if entry.link in new_links or len(uris) > 1 and self.store.rss_is_duplicate(entry):
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

        self.store.rss_remove_obsolete(feed, new_links)

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
        first = (not self.store.rss_has_feed(feed)) and ignore_first

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
                existing = self.store.rss_get_job(feed, normalised.link)
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
        if entry.state not in (RSSState.NEW, RSSState.GOOD, RSSState.BAD) and not (
            entry.state is RSSState.EXPIRED and readout
        ):
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

        star = first or entry.is_starred
        should_download = (download and not first and not entry.is_starred) or force

        return evaluation, should_download, star

    def enqueue_download(self, update: ResolvedEntry) -> None:
        if not update.state is RSSState.DOWNLOADED:
            return
        if not update.downloaded_at:
            self.store.rss_flag_downloaded(update.feed, update.link)

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
            state = RSSState.DOWNLOADED
        elif evaluation.matched:
            state = RSSState.GOOD
        else:
            state = RSSState.BAD

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
            state=state,
            downloaded_at=datetime.datetime.now() if state is RSSState.DOWNLOADED else None,
            initial_scan=True if state is is_starred and state is RSSState.GOOD else False,
        )

        self.store.rss_upsert(update)
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


def special_rss_site(url: str) -> bool:
    """Return True if url describes an RSS site with odd titles"""
    return cfg.rss_filenames() or match_str(url, cfg.rss_odd_titles())
