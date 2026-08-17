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
tests.test_misc - Testing functions in misc.py
"""

import datetime
import uuid
from typing import Optional
import random

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Response
from xml.etree.ElementTree import Element, SubElement, tostring

import sabnzbd.rss as rss
import sabnzbd.config
from sabnzbd.constants import DEFAULT_PRIORITY, LOW_PRIORITY, HIGH_PRIORITY, FORCE_PRIORITY, PAUSED_PRIORITY
from sabnzbd.database import HistoryDB
from sabnzbd.rss import RSSState, ResolvedEntry, RSSReader, RSSRepository
from tests.testhelper import httpserver_handler_data_dir


@pytest.fixture
def tmp_rss(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    monkeypatch.setattr(HistoryDB, "db_path", str(db_path))
    monkeypatch.setattr(HistoryDB, "startup_done", False)

    store = HistoryDB()
    repo = RSSRepository(store)
    reader = rss.RSSReader()

    yield repo, reader

    store.close()


def _build_random_store(
    repo: rss.RSSRepository,
    rnd: Optional[random.Random] = None,
    min_feeds: int = 1,
    max_feeds: int = 3,
    min_jobs: int = 1,
    max_jobs: int = 5,
):
    """Create an RSSStore filled with a random number of feeds and jobs.

    The randomness is controlled via the provided Random instance so tests
    remain deterministic while still exercising varying sizes and shapes of
    data.
    """

    if rnd is None:
        rnd = random.Random(42)

    feeds: list[str] = []
    links_by_feed: dict[str, list[str]] = {}

    num_feeds = rnd.randint(min_feeds, max_feeds)
    for fi in range(num_feeds):
        feed_name = f"feed-{fi}"
        feeds.append(feed_name)
        links: list[str] = []

        num_jobs = rnd.randint(min_jobs, max_jobs)
        for ji in range(num_jobs):
            link = f"http://example.test/{feed_name}/{ji}"
            links.append(link)
            entry = ResolvedEntry(
                feed=feed_name,
                link=link,
                title=f"Title {fi}-{ji}",
                infourl=f"http://example.test/info/{fi}/{ji}",
                size=1000 + ji,
                age=datetime.datetime.now(datetime.timezone.utc),
                season=1,
                episode=1,
                category="category",
                cat="cat",
                pp=0,
                script=None,
                priority=0,
                rule=0,
                state=RSSState.GOOD,
            )
            repo.upsert(entry)

        links_by_feed[feed_name] = links

    return feeds, links_by_feed


class TestRSS:
    @staticmethod
    def setup_rss(
        feed_name: str,
        feed_url: str,
        *,
        category: Optional[str] = None,
        pp: Optional[str] = None,
        script: Optional[str] = None,
        priority: Optional[int] = None,
        filters: Optional[list[tuple[str, str, str, str, str, int, str]]] = None,
    ):
        """Setup the basic settings to get things going"""
        values: dict = {"uri": feed_url}
        if category is not None:
            values["category"] = category
        if pp is not None:
            values["pp"] = str(pp)
        if script is not None:
            values["script"] = script
        if priority is not None:
            values["priority"] = str(priority)
        if filters is not None:
            for n, f in enumerate(filters):
                values[f"filter{n}"] = f

        # Setup the config settings. Clear the INI structure and drop the filename so
        # the test can't write to disk: clear() alone keeps the filename from a
        # previously-read INI, and save_config() would then rewrite that file.
        sabnzbd.config.CONFIG.clear()
        sabnzbd.config.CONFIG.filename = None
        sabnzbd.config.ConfigRSS(feed_name, values)

        # Pre-create the default "*" category (and the ones the feeds use) so
        # get_categories() doesn't seed the full default set on first access
        sabnzbd.config.ConfigCat("*", {})
        sabnzbd.config.ConfigCat("tv", {})
        sabnzbd.config.ConfigCat("movies", {})

    def test_rss_newznab_parser(self, httpserver: HTTPServer, tmp_rss):
        """Test basic RSS-parsing of custom elements
        Harder to test in functional test
        """
        httpserver.expect_request("/rss_newznab_test.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedNewznab"
        self.setup_rss(feed_name, httpserver.url_for("/rss_newznab_test.xml"))

        # Start the RSS reader
        repo, reader = tmp_rss
        reader.process_feed(feed_name)

        # Is the feed processed?
        assert repo.has_feed(feed_name)
        job = repo.find_job_by_url(feed_name, "https://cdn.example.com/cdn?t=get&id=FakeKey&apikey=FakeKey")
        assert job is not None

        # Check some job-data
        assert job.title == "FakeShow.S04E03.720p.WEB.H264-Obfuscated"
        assert job.infourl == "https://example.com/download.php?guid=FakeKey"
        assert job.category == "TV > HD"
        assert job.cat == "tv"
        assert job.episode == 3
        assert job.season == 4
        assert job.size == 1209464000

        adjusted_date = datetime.datetime(2018, 4, 13, 5, 46, 25, tzinfo=datetime.timezone.utc)
        assert job.age == adjusted_date

    def test_rss_nzedb_parser(self, httpserver: HTTPServer, tmp_rss):
        httpserver.expect_request("/rss_nzedb_test.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeednZEDb"
        self.setup_rss(feed_name, httpserver.url_for("/rss_nzedb_test.xml"))

        # Start the RSS reader
        repo, reader = tmp_rss
        reader.process_feed(feed_name)

        # Is the feed processed?
        assert repo.has_feed(feed_name)
        job = repo.find_job_by_url(feed_name, "https://example.com/getnzb/FakeKey.nzb&i=46181&r=FakeKey")
        assert job is not None

        # Check some job-data
        # Added fake season and episode to test file
        assert job.title == "Movie.With.a.Dog.2018.720p.BluRay.x264-SPRiNTER"
        assert job.infourl == "https://example.com/details/FakeKey"
        assert job.category == "Movies > HD"
        assert job.cat == "movies"
        assert job.episode == 720
        assert job.season == 2018
        assert job.size == 5164539914

        adjusted_date = datetime.datetime(2019, 3, 2, 17, 18, 7, tzinfo=datetime.timezone.utc)
        assert job.age == adjusted_date

    def test_rss_link(self, httpserver: HTTPServer, tmp_rss):
        httpserver.expect_request("/rss_link.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedLink"
        self.setup_rss(feed_name, httpserver.url_for("/rss_link.xml"))

        # Start the RSS reader
        repo, reader = tmp_rss
        reader.process_feed(feed_name)

        # Is the feed processed?
        assert repo.has_feed(feed_name)
        job = repo.find_job_by_url(feed_name, "http://LINK")
        assert job is not None

        # Check some job-data
        assert job.title == "TITLE"
        assert job.infourl == "https://sabnzbd.org/rss_link"
        assert job.size == 200

        adjusted_date = datetime.datetime(2025, 5, 20, 18, 21, 1, tzinfo=datetime.timezone.utc)
        assert job.age == adjusted_date

    def test_rss_enclosure_no_nzb(self, httpserver: HTTPServer, tmp_rss):
        httpserver.expect_request("/rss_enclosure_no_nzb.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedEnclosureNoNZB"
        self.setup_rss(feed_name, httpserver.url_for("/rss_enclosure_no_nzb.xml"))

        # Start the RSS reader
        repo, reader = tmp_rss
        reader.process_feed(feed_name)

        # Is the feed processed?
        assert not repo.has_feed(feed_name)

    def test_rss_enclosure_multiple(self, httpserver: HTTPServer, tmp_rss):
        httpserver.expect_request("/rss_enclosure_multiple.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedEnclosureMultiple"
        self.setup_rss(feed_name, httpserver.url_for("/rss_enclosure_multiple.xml"))

        # Start the RSS reader
        repo, reader = tmp_rss
        reader.process_feed(feed_name)

        # Is the feed processed?
        assert repo.has_feed(feed_name)
        job = repo.find_job_by_url(feed_name, "http://NZB_LINK")
        assert job is not None

        # Check some job-data
        assert job.title == "TITLE"
        assert job.infourl == "https://sabnzbd.org/rss_enclosure_multiple"
        assert job.size == 200

        adjusted_date = datetime.datetime(2025, 5, 20, 18, 21, 1, tzinfo=datetime.timezone.utc)
        assert job.age == adjusted_date

    @pytest.mark.parametrize(
        "defaults, filters, title, category, size, season, episode, expected_match",
        [
            # filters are (cat, pp, script, ftype, regex, priority, enabled)
            (
                (None, None, None, None),
                [],  # config always adds a default accept rule
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0},
            ),
            (
                (None, None, None, None),
                [("", "", "", ">", "500", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 1, "season": 0, "episode": 0},
            ),
            (  # age: minimum-age satisfied (feed item is well over a year old) -> falls through to accept
                (None, None, None, None),
                [("", "", "", "G", ">30d", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 1, "season": 0, "episode": 0},
            ),
            (  # age: hours unit, minimum-age satisfied -> accept
                (None, None, None, None),
                [("", "", "", "G", ">12h", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 1, "season": 0, "episode": 0},
            ),
            (  # age: years unit; feed item (May 2025) is over a year old -> min-age satisfied -> accept
                (None, None, None, None),
                [("", "", "", "G", ">1y", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 1, "season": 0, "episode": 0},
            ),
            (  # age: years unit; item older than 1y fails a max-age of 1y -> rejected
                (None, None, None, None),
                [("", "", "", "G", "<1y", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "state": RSSState.BAD},
            ),
            (  # age: >= comparator (inclusive alias of >) minimum-age satisfied -> accept
                (None, None, None, None),
                [("", "", "", "G", ">=1y", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 1, "season": 0, "episode": 0},
            ),
            (  # age: <= comparator (inclusive alias of <) maximum-age violated -> rejected
                (None, None, None, None),
                [("", "", "", "G", "<=30d", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "state": RSSState.BAD},
            ),
            (  # age: maximum-age violated (item older than 30d) -> rejected on the age rule
                (None, None, None, None),
                [("", "", "", "G", "<30d", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "state": RSSState.BAD},
            ),
            (  # age: bare value (no comparator) is treated as a maximum age -> rejected
                (None, None, None, None),
                [("", "", "", "G", "30d", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "state": RSSState.BAD},
            ),
            (  # age range via two rules: min 30d AND max 100y -> both pass, accept
                (None, None, None, None),
                [
                    ("", "", "", "G", ">30d", "", "1"),
                    ("", "", "", "G", "<36500d", "", "1"),
                    ("", "", "", "A", "*", DEFAULT_PRIORITY, "1"),
                ],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 2, "season": 0, "episode": 0},
            ),
            (
                (None, None, None, None),
                [("", "", "", "F", "S03E08", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title S05E02",
                None,
                1000,
                0,
                0,
                {"rule": 1, "season": 5, "episode": 2},
            ),
            (
                (None, None, None, None),
                [("", "", "", "F", "S03E08", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title S01E02",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 1, "episode": 2},
            ),
            (
                (None, None, None, LOW_PRIORITY),
                [("", "", "", "A", "*", "", "")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "priority": LOW_PRIORITY},
            ),
            (
                (None, None, None, LOW_PRIORITY),
                [("", "", "", "A", "*", HIGH_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "priority": HIGH_PRIORITY},
            ),
            (
                (None, 1, None, None),
                [],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "pp": None},
            ),
            (
                (None, 1, None, None),
                [("", "3", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {"rule": 0, "season": 0, "episode": 0, "pp": 3},
            ),
            (  # category overrides
                ("tv", 1, "", DEFAULT_PRIORITY),
                [("evaluator", "", "", "A", "*", "", "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {
                    "rule": 0,
                    "season": 0,
                    "episode": 0,
                    "cat": "evaluator",
                    "pp": 1,
                    "script": None,
                    "priority": DEFAULT_PRIORITY,
                },
            ),
            (  # category with rule overrides
                ("tv", 1, "", DEFAULT_PRIORITY),
                [("evaluator", "2", "override.py", "A", "*", "", "1")],
                "Title",
                None,
                1000,
                0,
                0,
                {
                    "rule": 0,
                    "season": 0,
                    "episode": 0,
                    "cat": "evaluator",
                    "pp": 2,
                    "script": "override.py",
                    "priority": DEFAULT_PRIORITY,
                },
            ),
            (
                ("", "", "", PAUSED_PRIORITY),
                [("", "", "", "A", "*", "", "")],
                "Title",
                "TV > HD",
                1000,
                0,
                0,
                {
                    "rule": 0,
                    "season": 0,
                    "episode": 0,
                    "cat": "tv",
                    "priority": PAUSED_PRIORITY,
                },
            ),
            (
                ("", "", "", PAUSED_PRIORITY),
                [("", "", "", "F", "", "", "")],
                "Title",
                "TV > HD",
                1000,
                3,
                5,
                {
                    "rule": 0,
                    "season": 3,
                    "episode": 5,
                    "cat": "tv",
                    "priority": PAUSED_PRIORITY,
                },
            ),
        ],
    )
    def test_feedconfig_evaluator(
        self,
        httpserver: HTTPServer,
        tmp_rss: RSSReader,
        defaults: tuple[Optional[str], Optional[str], Optional[str], Optional[int]],
        filters: list[tuple[str, str, str, str, str, int, str]],
        title: str,
        category: Optional[str],
        size: int,
        season: int,
        episode: int,
        expected_match: dict,
    ):
        def build_xml_response(
            title: str, category: Optional[str], size: Optional[int], season: Optional[int], episode: Optional[int]
        ):
            root = Element("rss", version="2.0")

            channel = SubElement(root, "channel")
            SubElement(channel, "title").text = "RSS feed"
            SubElement(channel, "description").text = "RSS feed"
            SubElement(channel, "link").text = "https://sabnzbd.org/"

            item = SubElement(channel, "item")

            SubElement(item, "title").text = title
            SubElement(item, "link").text = "http://LINK"
            SubElement(item, "comments").text = "COMMENTS"
            SubElement(item, "pubDate").text = "Tue, 20 May 2025 18:21:01 +0000"

            guid = SubElement(item, "guid")
            guid.set("isPermaLink", "true")
            guid.text = uuid.uuid4().hex

            # optional fields
            if category is not None:
                SubElement(item, "category").text = category

            if size is not None:
                SubElement(item, "size").text = str(size)

            if season is not None:
                SubElement(
                    item,
                    "newznab:attr",
                    {
                        "name": "season",
                        "value": str(season),
                    },
                )

            if episode is not None:
                SubElement(
                    item,
                    "newznab:attr",
                    {
                        "name": "episode",
                        "value": str(episode),
                    },
                )

            xml_bytes = tostring(root, encoding="utf-8")

            return xml_bytes

        httpserver.expect_request("/evaluator.xml").respond_with_handler(
            lambda request: Response(
                build_xml_response(title=title, category=category, size=size, season=season, episode=episode),
                status=200,
                content_type="application/rss+xml",
            )
        )
        default_category, default_pp, default_script, default_priority = defaults
        feed_name = "Evaluator"
        self.setup_rss(
            feed_name,
            httpserver.url_for("/evaluator.xml"),
            category=default_category,
            pp=default_pp,
            script=default_script,
            priority=default_priority,
            filters=filters,
        )
        sabnzbd.config.ConfigCat(
            "evaluator",
            {
                "pp": "3",
                "script": "evaluator.py",
                "priority": FORCE_PRIORITY,
            },
        )

        # Start the RSS reader
        repo, reader = tmp_rss
        reader.process_feed(feed_name)

        # Is the feed processed?
        assert repo.has_feed(feed_name)
        job = repo.find_job_by_url(feed_name, "http://LINK")
        assert job is not None

        # Check some job-data
        for k, expected in expected_match.items():
            actual = getattr(job, k, None)
            assert actual == expected, f"Expected {k!r}: {actual!r} == {expected!r}"

    def test_from_feed_entry_age_defaults_to_none_without_date(self):
        """A feed item with no parseable date has age None so age filters skip it."""
        import feedparser

        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<rss version="2.0"><channel><title>f</title><link>http://x/</link>'
            "<description>f</description>"
            "<item><title>No Date Item</title><link>http://LINK</link>"
            '<enclosure url="http://LINK" length="1000" type="application/x-nzb" />'
            "</item></channel></rss>"
        )
        parsed = feedparser.parse(xml)
        entry = ResolvedEntry.from_feed_entry("feed", parsed.entries[0])

        assert entry is not None
        assert entry.age is None

        # An age filter must not apply (returns None -> "go to next filter")
        age_rule = rss.FeedRule(type="G", value=">10d")
        assert (
            age_rule.matches(
                title=entry.title, category=None, size=entry.size, season=0, episode=0, rule_index=0, age=entry.age
            )
            is None
        )

    def test_age_comparator_aliases(self):
        """<=, >= and the reversed =<, => behave as inclusive aliases of < and >."""
        now = datetime.datetime.now(datetime.timezone.utc)
        old = now - datetime.timedelta(days=66)
        recent = now - datetime.timedelta(days=2)

        def matches(value, age):
            return rss.FeedRule(type="G", value=value).matches(
                title="T", category=None, size=0, season=0, episode=0, rule_index=0, age=age
            )

        # Minimum-age family: satisfied by the old item, violated by the recent one.
        # A missing unit defaults to days, so ">30" behaves like ">30d".
        for value in (">30d", ">=30d", "=>30d", ">30", ">=30", "=>30"):
            assert matches(value, old) is None, value
            assert matches(value, recent) is False, value

        # Maximum-age family: satisfied by the recent item, violated by the old one.
        # A bare value with no comparator or unit ("30") is an inclusive maximum age.
        for value in ("<30d", "<=30d", "=<30d", "30d", "<30", "<=30", "=<30", "30"):
            assert matches(value, recent) is None, value
            assert matches(value, old) is False, value

    def test_none_age_persists_as_fallback_and_round_trips(self, tmp_rss):
        """The NOT NULL age column is satisfied by a fallback when age is unknown."""
        repo, _reader = tmp_rss
        entry = ResolvedEntry(
            feed="feed",
            link="http://example.test/no-age",
            infourl=None,
            category=None,
            title="No age",
            size=1000,
            age=None,
            season=0,
            episode=0,
            state=RSSState.GOOD,
        )
        repo.upsert(entry)

        stored = repo.find_job_by_url("feed", "http://example.test/no-age")
        assert stored is not None
        # Persisted as a fallback (~seen_at) rather than NULL, so it reloads as a datetime.
        # Storage is integer seconds, so compare at whole-second resolution.
        assert stored.age is not None
        assert int(stored.age.timestamp()) == int(entry.seen_at.timestamp())

    def test_rssstore_random_crud(self, tmp_rss):
        rnd = random.Random(123)
        repo, _reader = tmp_rss
        feeds, links_by_feed = _build_random_store(
            repo,
            rnd,
            min_feeds=2,
            max_feeds=3,
            min_jobs=1,
            max_jobs=4,
        )

        # Basic structure and accessors
        db_feeds = set(repo.get_feeds())
        for feed in feeds:
            assert feed in db_feeds

        for feed in feeds:
            entries = list(repo.get_feed_jobs(feed))
            assert {e.link for e in entries} == set(links_by_feed[feed])

        # Pick one concrete feed/link to exercise per-job helpers
        feed = feeds[0]
        link = links_by_feed[feed][0]

        job = repo.find_job_by_url(feed, link)
        assert job is not None
        assert job.link == link

        # flag_downloaded + clear_downloaded modify status as expected
        repo.flag_downloaded(feed, link)
        job_after_flag = repo.find_job_by_url(feed, link)
        assert job_after_flag is not None
        assert job_after_flag.state is RSSState.DOWNLOADED
        assert job_after_flag.downloaded_at is not None
        assert job_after_flag.is_downloaded

        repo.clear_downloaded(feed)
        job_after_clear = repo.find_job_by_url(feed, link)
        assert job_after_clear is not None
        assert job_after_clear.state is RSSState.DOWNLOADED
        assert job_after_clear.downloaded_at is not None
        assert job_after_clear.archived_at is not None
        assert job_after_clear.is_downloaded

        # get_jobs should return all jobs for a feed
        jobs_from_get_jobs = list(repo.get_feed_jobs(feed=feed))
        assert {j.link for j in jobs_from_get_jobs} == set(links_by_feed[feed])

        # is_duplicate should detect similar jobs in other feeds
        duplicate_candidate = ResolvedEntry(
            feed="other-feed",
            link="http://example.test/other-feed/dup",
            title=job.title,
            infourl=job.infourl,
            size=int(job.size * 1.02),
            age=job.age,
            season=job.season,
            episode=job.episode,
            category=job.category,
        )
        assert repo.is_duplicate(duplicate_candidate)

        # rename_feed + clear_feed work on arbitrary feeds
        new_feed_name = feed + "-renamed"
        repo.rename(feed, new_feed_name)
        feeds_after_rename = set(repo.get_feeds())
        assert new_feed_name in feeds_after_rename
        assert feed not in feeds_after_rename

        repo.clear_feed(new_feed_name)
        feeds_after_clear = set(repo.get_feeds())
        assert new_feed_name not in feeds_after_clear

        # delete_feed removes remaining test feeds
        for remaining in list(feeds[1:]):
            repo.clear_feed(remaining)
            assert remaining not in set(repo.get_feeds())

    def test_rssstore_remove_obsolete_marks_and_purges(self, tmp_rss):
        """remove_obsolete should mark old G/B items as X and purge expired X."""
        repo, _reader = tmp_rss
        feed = "feed-remove"

        now = datetime.datetime.now(datetime.timezone.utc)
        age = now - datetime.timedelta(weeks=52)
        old_seen_at = now - datetime.timedelta(days=4)
        new_seen_at = now - datetime.timedelta(days=1)

        # Old good item that should be kept because it is part of the new_urls set
        keep_url = "http://example.test/keep"
        repo.upsert(
            ResolvedEntry(
                feed=feed,
                link=keep_url,
                title="keep",
                infourl=None,
                size=10,
                age=age,
                seen_at=old_seen_at,
                season=1,
                episode=1,
                category=None,
                state=RSSState.GOOD,
            )
        )

        # Old good item that is not in new_urls: should be marked X and purged
        purge_old_g_url = "http://example.test/purge-old-g"
        repo.upsert(
            ResolvedEntry(
                feed=feed,
                link=purge_old_g_url,
                title="old-g",
                infourl=None,
                size=20,
                age=age,
                seen_at=old_seen_at,
                season=1,
                episode=1,
                category=None,
                state=RSSState.GOOD,
            )
        )

        # Old X item should be purged directly
        purge_old_x_url = "http://example.test/purge-old-x"
        repo.upsert(
            ResolvedEntry(
                feed=feed,
                link=purge_old_x_url,
                title="old-x",
                infourl=None,
                size=30,
                age=age,
                seen_at=old_seen_at,
                season=1,
                episode=1,
                category=None,
                state=RSSState.EXPIRED,
            )
        )

        # Old D item should be purged directly
        purge_old_d_url = "http://example.test/purge-old-d"
        repo.upsert(
            ResolvedEntry(
                feed=feed,
                link=purge_old_d_url,
                title="old-d",
                infourl=None,
                size=30,
                age=age,
                seen_at=old_seen_at,
                season=1,
                episode=1,
                category=None,
                state=RSSState.DOWNLOADED,
            )
        )

        # Recent X item should be kept
        keep_x_url = "http://example.test/keep-young-x"
        repo.upsert(
            ResolvedEntry(
                feed=feed,
                link=keep_x_url,
                title="young-x",
                infourl=None,
                size=40,
                age=age,
                seen_at=new_seen_at,
                season=1,
                episode=1,
                category=None,
                state=RSSState.EXPIRED,
            )
        )

        # Recent D item should be kept
        keep_d_url = "http://example.test/keep-young-d"
        repo.upsert(
            ResolvedEntry(
                feed=feed,
                link=keep_d_url,
                title="young-d",
                infourl=None,
                size=40,
                age=age,
                seen_at=new_seen_at,
                season=1,
                episode=1,
                category=None,
                state=RSSState.DOWNLOADED,
            )
        )

        # Run remove_obsolete with only keep_url as the set of current URLs
        repo.remove_obsolete(feed, {keep_url}, purge_downloaded=True)

        jobs = {e.link: e for e in repo.get_feed_jobs(feed=feed)}

        # keep_url should still exist and remain G
        assert keep_url in jobs
        assert jobs[keep_url].state is RSSState.GOOD

        # Old G not in new_urls should have been purged entirely
        assert purge_old_g_url not in jobs

        # Old X should have been purged
        assert purge_old_x_url not in jobs

        # Old D should have been purged
        assert purge_old_d_url not in jobs

        # Young X should still exist
        assert keep_x_url in jobs
        assert jobs[keep_x_url].state is RSSState.EXPIRED

        # Young D should still exist
        assert keep_d_url in jobs
        assert jobs[keep_d_url].state is RSSState.DOWNLOADED

    def test_rss_is_starred_persists_and_affects_later_runs(self, httpserver: HTTPServer, tmp_rss, mocker):
        """Initial scan should mark GOOD entries as starred and persist this across runs.

        On the initial run with ignore_first=True, matching entries should be stored
        as GOOD+initial_scan (is_starred=True) but not downloaded. On a subsequent
        run, those same entries should still be present, still starred, and still
        not auto-downloaded.
        """
        repo, reader = tmp_rss
        feed_name = "StarredFeed"
        # Simple feed with one tv item that will match default accept rule
        item_xml = """
        <item>
            <title>Show.S01E01.720p</title>
            <link>http://example.test/starred-episode</link>
            <guid>http://example.test/info/starred-episode</guid>
            <category>tv</category>
            <pubDate>Wed, 01 Jan 2025 00:00:00 GMT</pubDate>
        </item>
        """
        feed_xml = f"""
        <?xml version=\"1.0\" encoding=\"utf-8\"?>
        <rss version=\"2.0\">
          <channel>
            <title>Starred</title>
            {item_xml}
          </channel>
        </rss>
        """

        httpserver.expect_request("/rss_starred.xml").respond_with_data(feed_xml, content_type="application/rss+xml")

        # Configure feed; no special filters needed because a default accept rule is added
        self.setup_rss(feed_name, httpserver.url_for("/rss_starred.xml"))

        # First run: ignore_first=True, download=True (scheduled-like behaviour)
        # This should mark the entry as GOOD+initial_scan, but not download it
        msg_first = reader.process_feed(feed_name, download=True, ignore_first=True)
        assert msg_first == ""

        job_first = repo.find_job_by_url(feed_name, "http://example.test/starred-episode")
        assert job_first is not None
        assert job_first.state is RSSState.GOOD
        assert job_first.is_starred  # initial_scan True + GOOD
        assert job_first.downloaded_at is None

        # Simulate a later run: readout only, no download
        msg_second = reader.process_feed(feed_name, download=True, ignore_first=False)
        assert msg_second == ""

        job_second = repo.find_job_by_url(feed_name, "http://example.test/starred-episode")
        assert job_second is not None
        # Still GOOD and still from initial scan
        assert job_second.state is RSSState.GOOD
        assert job_second.is_starred
        # And it should still not have been auto-downloaded
        assert job_second.downloaded_at is None

        # Third phase: force download; this should clear the starred status
        add_url_mock = mocker.patch("sabnzbd.urlgrabber.add_url")
        msg_third = reader.process_feed(feed_name, download=True, ignore_first=False, force=True)
        assert msg_third == ""
        assert add_url_mock.call_count == 1

        job_third = repo.find_job_by_url(feed_name, "http://example.test/starred-episode")
        assert job_third is not None
        assert job_third.state is RSSState.DOWNLOADED
        assert job_third.downloaded_at is not None
        # Starred status should no longer apply once downloaded
        assert not job_third.is_starred

    def test_rssreader_multi_uri_deduplicates_entries(self, httpserver: HTTPServer, tmp_rss):
        """A feed with multiple URIs should not create duplicate jobs for the same link."""
        repo, reader = tmp_rss
        shared_link = "http://example.test/shared"
        a_only_link = "http://example.test/a-only"
        b_only_link = "http://example.test/b-only"

        item_template = """
        <item>
            <title>{title}</title>
            <link>{link}</link>
            <guid>{guid}</guid>
            <category>tv</category>
            <pubDate>Wed, 01 Jan 2025 00:00:00 GMT</pubDate>
        </item>
        """
        feed_template = """
        <?xml version=\"1.0\" encoding=\"utf-8\"?>
        <rss version=\"2.0\">
        <channel>
            <title>Multi</title>
            {items}
        </channel>
        </rss>
        """

        xml_a = feed_template.format(
            items=(
                item_template.format(title="Shared", link=shared_link, guid="http://example.test/info/shared-a")
                + item_template.format(title="OnlyA", link=a_only_link, guid="http://example.test/info/a-only")
            )
        )
        xml_b = feed_template.format(
            items=(
                item_template.format(title="Shared", link=shared_link, guid="http://example.test/info/shared-b")
                + item_template.format(title="OnlyB", link=b_only_link, guid="http://example.test/info/b-only")
            )
        )

        httpserver.expect_request("/rss_multi_a.xml").respond_with_data(xml_a, content_type="application/rss+xml")
        httpserver.expect_request("/rss_multi_b.xml").respond_with_data(xml_b, content_type="application/rss+xml")

        feed_name = "MultiURI"
        uri_a = httpserver.url_for("/rss_multi_a.xml")
        uri_b = httpserver.url_for("/rss_multi_b.xml")
        multi_uri = f"{uri_a} {uri_b}"

        self.setup_rss(feed_name, multi_uri)

        reader.process_feed(feed_name)

        entries = list(repo.get_feed_jobs(feed=feed_name))
        links = {e.link for e in entries}

        # Shared link must only appear once
        assert links == {shared_link, a_only_link, b_only_link}

    def test_purge_removed_feeds_only_drops_unconfigured_feeds(self, tmp_rss):
        """Records should only be dropped for feeds that are no longer configured."""
        repo, _reader = tmp_rss
        configured_feed = "ConfiguredFeed"
        removed_feed = "RemovedFeed"

        self.setup_rss(configured_feed, "http://example.test/rss.xml")

        age = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(weeks=52)
        old_seen_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
        for feed in (configured_feed, removed_feed):
            repo.upsert(
                ResolvedEntry(
                    feed=feed,
                    link=f"http://example.test/{feed}/job",
                    title=f"{feed} job",
                    infourl=None,
                    size=10,
                    age=age,
                    seen_at=old_seen_at,
                    season=1,
                    episode=1,
                    category=None,
                    state=RSSState.GOOD,
                )
            )

        repo.purge_removed_feeds()

        assert set(repo.get_feeds()) == {configured_feed}

    def test_process_feed_without_readout_keeps_stored_jobs(self, httpserver: HTTPServer, tmp_rss):
        """Replaying stored jobs (readout=False) must not expire or purge anything."""
        repo, reader = tmp_rss
        feed_name = "NoReadoutFeed"
        feed_xml = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
          <channel>
            <title>NoReadout</title>
            <item>
                <title>New.Show.S01E01.720p</title>
                <link>http://example.test/no-readout/current</link>
                <guid>http://example.test/info/no-readout-current</guid>
                <category>tv</category>
                <pubDate>Wed, 01 Jan 2025 00:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """
        httpserver.expect_request("/rss_no_readout.xml").respond_with_data(feed_xml, content_type="application/rss+xml")
        self.setup_rss(feed_name, httpserver.url_for("/rss_no_readout.xml"))

        now = datetime.datetime.now(datetime.timezone.utc)
        old_url = "http://example.test/no-readout/expired"
        repo.upsert(
            ResolvedEntry(
                feed=feed_name,
                link=old_url,
                title="Old.Show.S01E01.720p",
                infourl=None,
                size=10,
                age=now - datetime.timedelta(weeks=52),
                seen_at=now - datetime.timedelta(days=4),
                season=1,
                episode=1,
                category=None,
                state=RSSState.EXPIRED,
            )
        )

        assert reader.process_feed(feed_name, readout=False) == ""
        assert repo.find_job_by_url(feed_name, old_url) is not None

        # A real readout does not find the link anymore, so it gets purged
        assert reader.process_feed(feed_name, readout=True) == ""
        assert repo.find_job_by_url(feed_name, old_url) is None
