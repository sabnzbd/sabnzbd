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


##############################################################################
# Wrapper functions
##############################################################################


def _normalise_default(value: Optional[str]) -> Optional[str]:
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


def coalesce(*args):
    """Return first value which is not None"""
    for a in args:
        if a is not None:
            return a
    return None


def remove_obsolete(jobs, new_jobs):
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


RSS_LOCK = threading.RLock()
_RE_SP = re.compile(r"s*(\d+)[ex](\d+)", re.I)
_RE_SIZE1 = re.compile(r"Size:\s*(\d+\.\d+\s*[KMG]?)B\W*", re.I)
_RE_SIZE2 = re.compile(r"\W*(\d+\.\d+\s*[KMG]?)B\W*", re.I)


class RSSReader:
    def __init__(self):
        self.jobs = {}
        self.next_run = time.time()
        self.shutdown = False

        try:
            self.jobs = sabnzbd.filesystem.load_admin(RSS_FILE_NAME)
            if self.jobs:
                for feed in self.jobs:
                    remove_obsolete(self.jobs[feed], list(self.jobs[feed]))
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
        patch_feedparser()

    def stop(self):
        self.shutdown = True

    @synchronized(RSS_LOCK)
    def run_feed(self, feed=None, download=False, ignoreFirst=False, force=False, readout=True):
        """Run the query for one URI and apply filters"""
        self.shutdown = False

        if not feed:
            return "No such feed"

        newlinks = []
        new_downloads = []

        # Preparations, get options
        try:
            feeds = config.get_rss()[feed]
        except KeyError:
            logging.error(T('Incorrect RSS feed description "%s"'), feed)
            logging.info("Traceback: ", exc_info=True)
            return T('Incorrect RSS feed description "%s"') % feed

        uris = feeds.uri()
        filters = FeedConfig.from_config(feeds)

        # Set first if this is the very first scan of this URI
        first = (feed not in self.jobs) and ignoreFirst

        # Add SABnzbd's custom User Agent
        feedparser.USER_AGENT = "SABnzbd/%s" % sabnzbd.__version__

        # Read the RSS feed
        msg = ""
        entries = []
        if readout:
            all_entries = []
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
            entries = all_entries

        # In case of a new feed
        if feed not in self.jobs:
            self.jobs[feed] = {}
        jobs = self.jobs[feed]

        # Error in readout or now new readout
        if readout:
            if not entries:
                return msg
        else:
            entries = jobs

        # Filter out valid new links
        for entry in entries:
            if self.shutdown:
                return

            if readout:
                try:
                    link, infourl, category, size, age, season, episode = _get_link(entry)
                except (AttributeError, IndexError):
                    logging.info(T("Incompatible feed") + " " + uri)
                    logging.info("Traceback: ", exc_info=True)
                    return T("Incompatible feed")
                title = entry.title

                # If there's multiple feeds, remove the duplicates based on title and size
                if len(uris) > 1:
                    skip_job = False
                    for job_link, job in jobs.items():
                        # Allow 5% size deviation because indexers might have small differences for same release
                        if (
                            job.get("title") == title
                            and link != job_link
                            and (job.get("size") * 0.95) < size < (job.get("size") * 1.05)
                        ):
                            logging.info("Ignoring job %s from other feed", title)
                            skip_job = True
                            break
                    if skip_job:
                        continue
            else:
                link = entry
                infourl = jobs[link].get("infourl", "")
                category = jobs[link].get("orgcat", "")
                if category in ("", "*"):
                    category = None
                title = jobs[link].get("title", "")
                size = jobs[link].get("size", 0)
                age = jobs[link].get("age")
                season = jobs[link].get("season", 0)
                episode = jobs[link].get("episode", 0)

            if link:
                # Make sure spaces are quoted in the URL
                link = link.strip().replace(" ", "%20")

                newlinks.append(link)

                if link in jobs:
                    jobstat = jobs[link].get("status", " ")[0]
                else:
                    jobstat = "N"
                if jobstat in "NGB" or (jobstat == "X" and readout):
                    # Match this title against all filters
                    logging.debug("Trying title %s", title)
                    match = filters.evaluate(
                        title=title,
                        category=category,
                        size=size,
                        season=season,
                        episode=episode,
                    )

                    job = jobs.get(link)
                    is_starred = job and job.get("status", "").endswith("*")
                    star = first or is_starred
                    act = (download and not first and not is_starred) or force

                    _HandleLink(
                        feed=feed,
                        jobs=jobs,
                        link=link,
                        infourl=infourl,
                        title=title,
                        size=size,
                        age=age,
                        season=match.season,
                        episode=match.episode,
                        flag="G" if match.matched else "B",
                        orgcat=category,
                        cat=match.category,
                        pp=match.pp,
                        script=match.script,
                        download=act and match.matched,
                        star=star,
                        priority=match.priority,
                        rule=match.rule_index,
                    )
                    if match.matched and act:
                        new_downloads.append(title)

        # Send email if wanted and not "forced"
        if new_downloads and cfg.email_rss() and not force:
            emailer.rss_mail(feed, new_downloads)

        remove_obsolete(jobs, newlinks)
        return msg

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
                        self.run_feed(feed, download=True, ignoreFirst=True)
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


@dataclass(frozen=True)
class FeedMatch:
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
        self.category = _normalise_default(self.category)
        self.priority = _normalise_priority(self.priority)
        self.pp = _normalise_pp(self.pp)
        self.script = _normalise_default(self.script)


@dataclass
class FeedConfig:
    default_category: Optional[str] = None
    default_priority: Optional[int] = None
    default_pp: Optional[int] = None
    default_script: Optional[str] = None
    rules: list[FeedRule] = field(default_factory=list)

    def __post_init__(self):
        self.default_category = _normalise_default(self.default_category)
        if self.default_category not in sabnzbd.api.list_cats(default=False):
            self.default_category = None
        self.default_priority = _normalise_priority(self.default_priority)
        self.default_pp = _normalise_pp(self.default_pp)
        self.default_script = _normalise_default(self.default_script)

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
    ) -> FeedMatch:
        """Evaluate rules for a single RSS entry."""
        result: bool = False
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
            return FeedMatch(
                matched=result,
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
        logging.debug("Size %s", size)
        for idx, rule in enumerate(self.rules):
            if not rule.enabled:
                continue

            if category and rule.type == "C":
                found = re.search(rule.regex, category)
                if not found:
                    logging.debug("Filter rejected on rule %d", idx)
                    result = False
                    matched_index = idx
                    break
            elif rule.type == "<" and size and from_units(rule.regex) < size:
                # "Size at most" : too large
                logging.debug("Filter rejected on rule %d", idx)
                result = False
                matched_index = idx
                break
            elif rule.type == ">" and size and from_units(rule.regex) > size:
                # "Size at least" : too small
                logging.debug("Filter rejected on rule %d", idx)
                result = False
                matched_index = idx
                break
            elif rule.type == "F" and not ep_match(cur_season, cur_episode, rule.regex):
                # "Starting from SxxEyy", too early episode
                logging.debug("Filter requirement match on rule %d", idx)
                result = False
                matched_index = idx
                break
            elif rule.type == "S" and ep_match(cur_season, cur_episode, rule.regex, title):
                logging.debug("Filter matched on rule %d", idx)
                result = True
                matched_index = idx
                matched_rule = rule
                break
            else:
                if rule.regex:
                    found = re.search(rule.regex, title)
                else:
                    found = False

                if rule.type == "M" and not found:
                    logging.debug("Filter rejected on rule %d", idx)
                    result = False
                    matched_index = idx
                    break
                if found and rule.type == "A":
                    logging.debug("Filter matched on rule %d", idx)
                    result = True
                    matched_index = idx
                    matched_rule = rule
                    break
                if found and rule.type == "R":
                    logging.debug("Filter rejected on rule %d", idx)
                    result = False
                    matched_index = idx
                    break

        if matched_rule is None:
            # No rule matched; keep my_category/my_pp/my_script/my_priority at feed defaults,
            # or use original category if there is no default.
            if category is not None and self.default_category is None:
                my_category = cat_convert(category)
            if my_category:
                my_category, category_pp, category_script, category_priority = cat_to_opts(my_category)
                category_pp = _normalise_pp(category_pp)
                category_script = _normalise_default(category_script)
                category_priority = _normalise_priority(category_priority)
            else:
                my_category = category_pp = category_script = category_priority = None
            # pp/script/priority only come from category defaults in this case
            my_pp = coalesce(category_pp, self.default_pp)
            my_script = category_script or self.default_script
            my_priority = coalesce(category_priority, self.default_priority)

            return FeedMatch(
                matched=result,
                rule_index=matched_index,
                season=int_conv(cur_season),
                episode=int_conv(cur_episode),
                category=my_category,
                pp=my_pp,
                script=my_script,
                priority=my_priority,
            )

        # At this point we know a rule fired and matched_rule is not None.
        my_category = matched_rule.category or cat_convert(category) or self.default_category
        if my_category:
            my_category, category_pp, category_script, category_priority = cat_to_opts(my_category)
            category_pp = _normalise_pp(category_pp)
            category_script = _normalise_default(category_script)
            category_priority = _normalise_priority(category_priority)
        else:
            my_category = category_pp = category_script = category_priority = None
        my_pp = coalesce(matched_rule.pp, category_pp, self.default_pp)
        my_script = matched_rule.script or category_script or self.default_script
        my_priority = coalesce(matched_rule.priority, category_priority, self.default_priority)

        return FeedMatch(
            matched=result,
            rule_index=matched_index,
            season=int_conv(cur_season),
            episode=int_conv(cur_episode),
            category=my_category,
            pp=my_pp,
            script=my_script,
            priority=my_priority,
        )


def patch_feedparser():
    """Apply options that work for SABnzbd
    Add additional parsing of attributes
    """
    feedparser.SANITIZE_HTML = 0
    feedparser.RESOLVE_RELATIVE_URIS = 0

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


def _HandleLink(
    feed,
    jobs,
    link,
    infourl,
    title,
    size,
    age,
    season,
    episode,
    flag,
    orgcat,
    cat,
    pp,
    script,
    download,
    star,
    priority=DEFAULT_PRIORITY,
    rule=0,
):
    """Process one link"""
    if script == "":
        script = None
    if pp == "":
        pp = None

    jobs[link] = {}
    jobs[link]["title"] = title
    jobs[link]["url"] = link
    jobs[link]["infourl"] = infourl
    jobs[link]["cat"] = cat
    jobs[link]["pp"] = pp
    jobs[link]["script"] = script
    jobs[link]["prio"] = str(priority) if priority is not None else str(DEFAULT_PRIORITY)
    jobs[link]["orgcat"] = orgcat
    jobs[link]["size"] = size
    jobs[link]["age"] = age
    jobs[link]["time"] = time.time()
    jobs[link]["rule"] = str(rule)
    jobs[link]["season"] = str(season)
    jobs[link]["episode"] = str(episode)

    if special_rss_site(link):
        nzbname = None
    else:
        nzbname = title

    if download:
        jobs[link]["status"] = "D"
        jobs[link]["time_downloaded"] = time.localtime()

        logging.info("Adding %s (%s) to queue", link, title)
        sabnzbd.urlgrabber.add_url(
            link,
            pp=pp,
            script=script,
            cat=cat,
            priority=priority,
            nzbname=nzbname,
            nzo_info={"RSS": feed},
        )
    else:
        if star:
            jobs[link]["status"] = flag + "*"
        else:
            jobs[link]["status"] = flag


def _get_link(entry):
    """Retrieve the post link from this entry
    Returns (link, category, size)
    """
    link = None
    size = 0
    age = datetime.datetime.now()

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
                size = from_units(m.group(1))
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

    if link and link.lower().startswith("http"):
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

        return link, infourl, category, size, age, season, episode
    else:
        logging.info(T("Empty RSS entry found (%s)"), link)
        return None, None, "", 0, None, 0, 0


def special_rss_site(url):
    """Return True if url describes an RSS site with odd titles"""
    return cfg.rss_filenames() or match_str(url, cfg.rss_odd_titles())


def ep_match(season, episode, expr, title=None):
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
