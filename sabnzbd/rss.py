#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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

import sabnzbd
from sabnzbd.constants import RSS_FILE_NAME, DEFAULT_PRIORITY, DUP_PRIORITY
from sabnzbd.decorators import synchronized
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.misc import cat_convert, convert_filter, cat_to_opts, match_str, from_units, int_conv, get_base_url
import sabnzbd.emailer as emailer

import feedparser


##############################################################################
# Wrapper functions
##############################################################################


def notdefault(item):
    """Return True if not 'Default|''|*'"""
    return bool(item) and str(item).lower() not in ("default", "*", "", str(DEFAULT_PRIORITY))


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
_RE_SIZE1 = re.compile(r"Size:\s*(\d+\.\d+\s*[KMG]{0,1})B\W*", re.I)
_RE_SIZE2 = re.compile(r"\W*(\d+\.\d+\s*[KMG]{0,1})B\W*", re.I)


class RSSReader:
    def __init__(self):
        self.jobs = {}
        self.next_run = time.time()
        self.shutdown = False

        try:
            self.jobs = sabnzbd.load_admin(RSS_FILE_NAME)
            if self.jobs:
                for feed in self.jobs:
                    remove_obsolete(self.jobs[feed], list(self.jobs[feed]))
        except:
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
        defCat = feeds.cat()

        if not notdefault(defCat) or defCat not in sabnzbd.api.list_cats(default=False):
            defCat = None
        defPP = feeds.pp()
        if not notdefault(defPP):
            defPP = None
        defScript = feeds.script()
        if not notdefault(defScript):
            defScript = None
        defPrio = feeds.priority()
        if not notdefault(defPrio):
            defPrio = None

        # Preparations, convert filters to regex's
        regexes = []
        reTypes = []
        reCats = []
        rePPs = []
        rePrios = []
        reScripts = []
        reEnabled = []
        for feed_filter in feeds.filters():
            reCat = feed_filter[0]
            if defCat in ("", "*"):
                reCat = None
            reCats.append(reCat)
            rePPs.append(feed_filter[1])
            reScripts.append(feed_filter[2])
            reTypes.append(feed_filter[3])
            if feed_filter[3] in ("<", ">", "F", "S"):
                regexes.append(feed_filter[4])
            else:
                regexes.append(convert_filter(feed_filter[4]))
            rePrios.append(feed_filter[5])
            reEnabled.append(feed_filter[6] != "0")
        regcount = len(regexes)

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
                    logging.warning_helpful(urllib.parse.unquote(msg))
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
                    result = False
                    myCat = defCat
                    myPP = defPP
                    myScript = defScript
                    myPrio = defPrio
                    n = 0
                    if ("F" in reTypes or "S" in reTypes) and (not season or not episode):
                        season, episode = sabnzbd.newsunpack.analyse_show(title)[1:3]

                    # Match against all filters until an positive or negative match
                    logging.debug("Size %s", size)
                    for n in range(regcount):
                        if reEnabled[n]:
                            if category and reTypes[n] == "C":
                                found = re.search(regexes[n], category)
                                if not found:
                                    logging.debug("Filter rejected on rule %d", n)
                                    result = False
                                    break
                            elif reTypes[n] == "<" and size and from_units(regexes[n]) < size:
                                # "Size at most" : too large
                                logging.debug("Filter rejected on rule %d", n)
                                result = False
                                break
                            elif reTypes[n] == ">" and size and from_units(regexes[n]) > size:
                                # "Size at least" : too small
                                logging.debug("Filter rejected on rule %d", n)
                                result = False
                                break
                            elif reTypes[n] == "F" and not ep_match(season, episode, regexes[n]):
                                # "Starting from SxxEyy", too early episode
                                logging.debug("Filter requirement match on rule %d", n)
                                result = False
                                break
                            elif (
                                reTypes[n] == "S"
                                and season
                                and episode
                                and ep_match(season, episode, regexes[n], title)
                            ):
                                logging.debug("Filter matched on rule %d", n)
                                result = True
                                break
                            else:
                                if regexes[n]:
                                    found = re.search(regexes[n], title)
                                else:
                                    found = False
                                if reTypes[n] == "M" and not found:
                                    logging.debug("Filter rejected on rule %d", n)
                                    result = False
                                    break
                                if found and reTypes[n] == "A":
                                    logging.debug("Filter matched on rule %d", n)
                                    result = True
                                    break
                                if found and reTypes[n] == "R":
                                    logging.debug("Filter rejected on rule %d", n)
                                    result = False
                                    break

                    if len(reCats):
                        if not result and defCat:
                            # Apply Feed-category on non-matched items
                            myCat = defCat
                        elif result and notdefault(reCats[n]):
                            # Use the matched info
                            myCat = reCats[n]
                        elif category and not defCat:
                            # No result and no Feed-category
                            myCat = cat_convert(category)

                        if myCat:
                            myCat, catPP, catScript, catPrio = cat_to_opts(myCat)
                        else:
                            myCat = catPP = catScript = catPrio = None
                        if notdefault(rePPs[n]):
                            myPP = rePPs[n]
                        elif not (reCats[n] or category):
                            myPP = catPP
                        if notdefault(reScripts[n]):
                            myScript = reScripts[n]
                        elif not (notdefault(reCats[n]) or category):
                            myScript = catScript
                        if rePrios[n] not in (str(DEFAULT_PRIORITY), ""):
                            myPrio = rePrios[n]
                        elif not ((rePrios[n] != str(DEFAULT_PRIORITY)) or category):
                            myPrio = catPrio

                    if cfg.no_dupes() and self.check_duplicate(title):
                        if cfg.no_dupes() == 1:
                            # Dupe-detection: Discard
                            logging.info("Ignoring duplicate job %s", title)
                            continue
                        elif cfg.no_dupes() == 3:
                            # Dupe-detection: Fail
                            # We accept it so the Queue can send it to the History
                            logging.info("Found duplicate job %s", title)
                        else:
                            # Dupe-detection: Pause
                            myPrio = DUP_PRIORITY

                    act = download and not first
                    if link in jobs:
                        act = act and not jobs[link].get("status", "").endswith("*")
                        act = act or force
                        star = first or jobs[link].get("status", "").endswith("*")
                    else:
                        star = first
                    if result:
                        _HandleLink(
                            jobs,
                            link,
                            infourl,
                            title,
                            size,
                            age,
                            season,
                            episode,
                            "G",
                            category,
                            myCat,
                            myPP,
                            myScript,
                            act,
                            star,
                            priority=myPrio,
                            rule=n,
                        )
                        if act:
                            new_downloads.append(title)
                    else:
                        _HandleLink(
                            jobs,
                            link,
                            infourl,
                            title,
                            size,
                            age,
                            season,
                            episode,
                            "B",
                            category,
                            myCat,
                            myPP,
                            myScript,
                            False,
                            star,
                            priority=myPrio,
                            rule=n,
                        )

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
            except:
                return {}
        else:
            return {}

    @synchronized(RSS_LOCK)
    def save(self):
        sabnzbd.save_admin(self.jobs, RSS_FILE_NAME)

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

    def check_duplicate(self, title):
        """Check if this title was in this or other feeds
        Return matching feed name
        """
        title = title.lower()
        for fd in self.jobs:
            for lk in self.jobs[fd]:
                item = self.jobs[fd][lk]
                if item.get("status", " ")[0] == "D" and item.get("title", "").lower() == title:
                    return fd
        return ""


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
    jobs[link]["prio"] = str(priority)
    jobs[link]["orgcat"] = orgcat
    jobs[link]["size"] = size
    jobs[link]["age"] = age
    jobs[link]["time"] = time.time()
    jobs[link]["rule"] = str(rule)
    jobs[link]["season"] = season
    jobs[link]["episode"] = episode

    if special_rss_site(link):
        nzbname = None
    else:
        nzbname = title

    if download:
        jobs[link]["status"] = "D"
        jobs[link]["time_downloaded"] = time.localtime()
        logging.info("Adding %s (%s) to queue", link, title)
        sabnzbd.add_url(link, pp=pp, script=script, cat=cat, priority=priority, nzbname=nzbname)
    else:
        if star:
            jobs[link]["status"] = flag + "*"
        else:
            jobs[link]["status"] = flag


def _get_link(entry):
    """Retrieve the post link from this entry
    Returns (link, category, size)
    """
    size = 0
    age = datetime.datetime.now()

    # Try standard link and enclosures first
    link = entry.link
    if not link:
        link = entry.links[0].href
    if "enclosures" in entry:
        try:
            link = entry.enclosures[0]["href"]
            size = int(entry.enclosures[0]["length"])
        except:
            pass

    # GUID usually has URL to result on page
    infourl = None
    if entry.get("id") and entry.id != link and entry.id.startswith("http"):
        infourl = entry.id

    if size == 0:
        # Try to find size in Description
        try:
            desc = entry.description.replace("\n", " ").replace("&nbsp;", " ")
            m = _RE_SIZE1.search(desc) or _RE_SIZE2.search(desc)
            if m:
                size = from_units(m.group(1))
        except:
            pass

    # Try newznab attribute first, this is the correct one
    try:
        # Convert it to format that calc_age understands
        age = datetime.datetime(*entry["newznab"]["usenetdate_parsed"][:6])
    except:
        # Date from feed (usually lags behind)
        try:
            # Convert it to format that calc_age understands
            age = datetime.datetime(*entry.published_parsed[:6])
        except:
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

    if link and "http" in link.lower():
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
        logging.warning(T("Empty RSS entry found (%s)"), link)
        return None, None, "", 0, None, 0, 0


def special_rss_site(url):
    """Return True if url describes an RSS site with odd titles"""
    return cfg.rss_filenames() or match_str(url, cfg.rss_odd_titles())


def ep_match(season, episode, expr, title=None):
    """Return True if season, episode is at or above expected
    Optionally `title` can be matched
    """
    m = _RE_SP.search(expr)
    if m:
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
