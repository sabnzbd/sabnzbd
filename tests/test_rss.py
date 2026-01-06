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
import random
from typing import Optional

import configobj
import pytest
from pytest_httpserver import HTTPServer

import sabnzbd
import sabnzbd.rss as rss
import sabnzbd.database as db
import sabnzbd.config
from sabnzbd.constants import DEFAULT_PRIORITY, LOW_PRIORITY, HIGH_PRIORITY, FORCE_PRIORITY
from sabnzbd.rss import FeedEvaluation, FeedConfig
from sabnzbd.rssmodels import RSSState
from tests.testhelper import httpserver_handler_data_dir


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    monkeypatch.setattr(db.HistoryDB, "db_path", str(db_path))
    monkeypatch.setattr(db.HistoryDB, "startup_done", False)


def _build_random_store(
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

    store = db.HistoryDB()
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
            entry = rss.ResolvedEntry(
                feed=feed_name,
                link=link,
                title=f"Title {fi}-{ji}",
                infourl=f"http://example.test/info/{fi}/{ji}",
                size=1000 + ji,
                age=datetime.datetime.now(datetime.timezone.utc),
                season=1,
                episode=1,
                orgcat="orgcat",
                cat="cat",
                pp=0,
                script=None,
                priority=0,
                rule=0,
                state=RSSState.GOOD,
            )
            store.rss_upsert(entry)

        links_by_feed[feed_name] = links

    return store, feeds, links_by_feed


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
        filters: list[tuple[str, str, str, str, str, int, str]] = None,
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

        # Setup the config settings
        sabnzbd.config.CFG_OBJ = configobj.ConfigObj()
        sabnzbd.config.ConfigRSS(feed_name, values)

        # Need to create the Default category
        # Otherwise it will try to save the config
        sabnzbd.config.ConfigCat("*", {})
        sabnzbd.config.ConfigCat("tv", {})
        sabnzbd.config.ConfigCat("movies", {})

    def test_rss_newznab_parser(self, tmp_db):
        """Test basic RSS-parsing of custom elements
        Harder to test in functional test
        """
        feed_name = "TestFeedNewznab"
        self.setup_rss(feed_name, "https://sabnzbd.org/tests/rss_newznab_test.xml")

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert rss_obj.store.rss_has_feed(feed_name)
        job = rss_obj.store.rss_get_job(feed_name, "https://cdn.nzbgeek.info/cdn?t=get&id=FakeKey&apikey=FakeKey")
        assert job is not None

        # Check some job-data
        assert job.title == "FakeShow.S04E03.720p.WEB.H264-Obfuscated"
        assert job.infourl == "https://nzbgeek.info/geekseek.php?guid=FakeKey"
        assert job.orgcat == "TV > HD"
        assert job.cat == "tv"
        assert job.episode == 3
        assert job.season == 4
        assert job.size == 1209464000

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
        adjusted_date = datetime.datetime(2018, 4, 13, 5, 46, 25, tzinfo=datetime.timezone.utc)
        assert job.age == adjusted_date

    def test_rss_nzedb_parser(self, tmp_db):
        feed_name = "TestFeednZEDb"
        self.setup_rss(feed_name, "https://sabnzbd.org/tests/rss_nzedb_test.xml")

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert rss_obj.store.rss_has_feed(feed_name)
        job = rss_obj.store.rss_get_job(feed_name, "https://nzbfinder.ws/getnzb/FakeKey.nzb&i=46181&r=FakeKey")
        assert job is not None

        # Check some job-data
        # Added fake season and episode to test file
        assert job.title == "Movie.With.a.Dog.2018.720p.BluRay.x264-SPRiNTER"
        assert job.infourl == "https://nzbfinder.ws/details/FakeKey"
        assert job.orgcat == "Movies > HD"
        assert job.cat == "movies"
        assert job.episode == 720
        assert job.season == 2018
        assert job.size == 5164539914

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
        adjusted_date = datetime.datetime(2019, 3, 2, 17, 18, 7, tzinfo=datetime.timezone.utc)
        assert job.age == adjusted_date

    def test_rss_link(self, httpserver: HTTPServer, tmp_db):
        httpserver.expect_request("/rss_link.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedLink"
        self.setup_rss(feed_name, httpserver.url_for("/rss_link.xml"))

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert rss_obj.store.rss_has_feed(feed_name)
        job = rss_obj.store.rss_get_job(feed_name, "http://LINK")
        assert job is not None

        # Check some job-data
        assert job.title == "TITLE"
        assert job.infourl == "https://sabnzbd.org/rss_link"
        assert job.size == 200

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
        adjusted_date = datetime.datetime(2025, 5, 20, 18, 21, 1, tzinfo=datetime.timezone.utc)
        assert job.age == adjusted_date

    def test_rss_enclosure_no_nzb(self, httpserver: HTTPServer, tmp_db):
        httpserver.expect_request("/rss_enclosure_no_nzb.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedEnclosureNoNZB"
        self.setup_rss(feed_name, httpserver.url_for("/rss_enclosure_no_nzb.xml"))

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert not rss_obj.store.rss_has_feed(feed_name)

    def test_rss_enclosure_multiple(self, httpserver: HTTPServer, tmp_db):
        httpserver.expect_request("/rss_enclosure_multiple.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedEnclosureMultiple"
        self.setup_rss(feed_name, httpserver.url_for("/rss_enclosure_multiple.xml"))

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert rss_obj.store.rss_has_feed(feed_name)
        job = rss_obj.store.rss_get_job(feed_name, "http://NZB_LINK")
        assert job is not None

        # Check some job-data
        assert job.title == "TITLE"
        assert job.infourl == "https://sabnzbd.org/rss_enclosure_multiple"
        assert job.size == 200

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
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
                FeedEvaluation(matched=True, rule_index=0, season=0, episode=0),
            ),
            (
                (None, None, None, None),
                [("", "", "", ">", "500", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                FeedEvaluation(matched=True, rule_index=1, season=0, episode=0),
            ),
            (
                (None, None, None, None),
                [("", "", "", "F", "S03E08", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title S05E02",
                None,
                1000,
                0,
                0,
                FeedEvaluation(matched=True, rule_index=1, season=5, episode=2),
            ),
            (
                (None, None, None, None),
                [("", "", "", "F", "S03E08", "", "1"), ("", "", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title S01E02",
                None,
                1000,
                0,
                0,
                FeedEvaluation(matched=False, rule_index=0, season=1, episode=2),
            ),
            (
                (None, None, None, LOW_PRIORITY),
                [],
                "Title",
                None,
                1000,
                0,
                0,
                FeedEvaluation(matched=True, rule_index=0, season=0, episode=0, priority=LOW_PRIORITY),
            ),
            (
                (None, None, None, LOW_PRIORITY),
                [("", "", "", "A", "*", HIGH_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                FeedEvaluation(matched=True, rule_index=0, season=0, episode=0, priority=HIGH_PRIORITY),
            ),
            (
                (None, 1, None, None),
                [],
                "Title",
                None,
                1000,
                0,
                0,
                FeedEvaluation(matched=True, rule_index=0, season=0, episode=0, pp=1),
            ),
            (
                (None, 1, None, None),
                [("", "3", "", "A", "*", DEFAULT_PRIORITY, "1")],
                "Title",
                None,
                1000,
                0,
                0,
                FeedEvaluation(matched=True, rule_index=0, season=0, episode=0, pp=3),
            ),
            (  # category overrides
                ("tv", 1, DEFAULT_PRIORITY, ""),
                [("evaluator", "", "", "A", "*", "", "1")],
                "Title",
                None,
                1000,
                0,
                0,
                FeedEvaluation(
                    matched=True,
                    rule_index=0,
                    season=0,
                    episode=0,
                    category="evaluator",
                    pp=3,
                    script="evaluator.py",
                    priority=FORCE_PRIORITY,
                ),
            ),
            (  # category with rule overrides
                ("tv", 1, DEFAULT_PRIORITY, ""),
                [("evaluator", "2", "override.py", "A", "*", "", "1")],
                "Title",
                None,
                1000,
                0,
                0,
                FeedEvaluation(
                    matched=True,
                    rule_index=0,
                    season=0,
                    episode=0,
                    category="evaluator",
                    pp=2,
                    script="override.py",
                    priority=FORCE_PRIORITY,
                ),
            ),
        ],
    )
    def test_feedconfig_evaluator(
        self,
        httpserver: HTTPServer,
        defaults: tuple[Optional[str], Optional[str], Optional[str], Optional[int]],
        filters: list[tuple[str, str, str, str, str, int, str]],
        title: str,
        category: Optional[str],
        size: int,
        season: int,
        episode: int,
        expected_match: FeedEvaluation,
    ):
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

        feed_cfg = FeedConfig.from_config(sabnzbd.config.get_rss()[feed_name])
        result_match = feed_cfg.evaluate(title=title, category=category, size=size, season=season, episode=episode)

        assert result_match == expected_match

    def test_rssstore_random_crud(self, tmp_db):
        rnd = random.Random(123)
        store, feeds, links_by_feed = _build_random_store(
            rnd,
            min_feeds=2,
            max_feeds=3,
            min_jobs=1,
            max_jobs=4,
        )

        # Basic structure and accessors
        db_feeds = set(store.rss_get_feeds())
        for feed in feeds:
            assert feed in db_feeds

        for feed in feeds:
            entries = list(store.rss_show_result(feed))
            assert {e.link for e in entries} == set(links_by_feed[feed])

        # Pick one concrete feed/link to exercise per-job helpers
        feed = feeds[0]
        link = links_by_feed[feed][0]

        job = store.rss_get_job(feed, link)
        assert job is not None
        assert job.link == link

        # flag_downloaded + clear_downloaded modify status as expected
        store.rss_flag_downloaded(feed, link)
        job_after_flag = store.rss_get_job(feed, link)
        assert job_after_flag is not None
        assert job_after_flag.state is RSSState.DOWNLOADED
        assert job_after_flag.downloaded_at is not None
        assert job_after_flag.is_downloaded

        store.rss_clear_downloaded(feed)
        job_after_clear = store.rss_get_job(feed, link)
        assert job_after_clear is not None
        assert job_after_clear.state is RSSState.DOWNLOADED
        assert job_after_clear.downloaded_at is not None
        assert job_after_clear.archived_at is not None
        assert job_after_clear.is_downloaded
        assert job_after_clear.is_hidden

        # get_jobs should return all jobs for a feed
        jobs_from_get_jobs = list(store.rss_get_jobs(feed=feed))
        assert {j.link for j in jobs_from_get_jobs} == set(links_by_feed[feed])

        # is_duplicate should detect similar jobs in other feeds
        duplicate_candidate = rss.ResolvedEntry(
            feed="other-feed",
            link="http://example.test/other-feed/dup",
            title=job.title,
            infourl=job.infourl,
            size=int(job.size * 1.02),
            age=job.age,
            season=job.season,
            episode=job.episode,
            orgcat=job.orgcat,
        )
        assert store.rss_is_duplicate(duplicate_candidate)

        # rename_feed + clear_feed work on arbitrary feeds
        new_feed_name = feed + "-renamed"
        store.rss_rename_feed(feed, new_feed_name)
        feeds_after_rename = set(store.rss_get_feeds())
        assert new_feed_name in feeds_after_rename
        assert feed not in feeds_after_rename

        store.rss_clear_feed(new_feed_name)
        feeds_after_clear = set(store.rss_get_feeds())
        assert new_feed_name not in feeds_after_clear

        # delete_feed removes remaining test feeds
        for remaining in list(feeds[1:]):
            store.rss_delete_feed(remaining)
            assert remaining not in set(store.rss_get_feeds())

    def test_rssstore_remove_obsolete_marks_and_purges(self, tmp_db):
        """remove_obsolete should mark old G/B items as X and purge expired X."""
        store = db.HistoryDB()
        feed = "feed-remove"

        now = datetime.datetime.now(datetime.timezone.utc)
        old_age = now - datetime.timedelta(days=4)
        new_age = now - datetime.timedelta(days=1)

        # Old good item that should be kept because it is part of the new_urls set
        keep_url = "http://example.test/keep"
        store.rss_upsert(
            rss.ResolvedEntry(
                feed=feed,
                link=keep_url,
                title="keep",
                infourl=None,
                size=10,
                age=old_age,
                season=1,
                episode=1,
                orgcat=None,
                state=RSSState.GOOD,
            )
        )

        # Old good item that is not in new_urls: should be marked X and purged
        purge_old_g_url = "http://example.test/purge-old-g"
        store.rss_upsert(
            rss.ResolvedEntry(
                feed=feed,
                link=purge_old_g_url,
                title="old-g",
                infourl=None,
                size=20,
                age=old_age,
                season=1,
                episode=1,
                orgcat=None,
                state=RSSState.GOOD,
            )
        )

        # Old X item should be purged directly
        purge_old_x_url = "http://example.test/purge-old-x"
        store.rss_upsert(
            rss.ResolvedEntry(
                feed=feed,
                link=purge_old_x_url,
                title="old-x",
                infourl=None,
                size=30,
                age=old_age,
                season=1,
                episode=1,
                orgcat=None,
                state=RSSState.EXPIRED,
            )
        )

        # Recent X item should be kept
        keep_x_url = "http://example.test/keep-young-x"
        store.rss_upsert(
            rss.ResolvedEntry(
                feed=feed,
                link=keep_x_url,
                title="young-x",
                infourl=None,
                size=40,
                age=new_age,
                season=1,
                episode=1,
                orgcat=None,
                state=RSSState.EXPIRED,
            )
        )

        # Run remove_obsolete with only keep_url as the set of current URLs
        store.rss_remove_obsolete(feed, {keep_url})

        jobs = {e.link: e for e in store.rss_get_jobs(feed=feed)}

        # keep_url should still exist and remain G
        assert keep_url in jobs
        assert jobs[keep_url].state is RSSState.GOOD

        # Old G not in new_urls should have been purged entirely
        assert purge_old_g_url not in jobs

        # Old X should have been purged
        assert purge_old_x_url not in jobs

        # Young X should still exist
        assert keep_x_url in jobs
        assert jobs[keep_x_url].state is RSSState.EXPIRED

        store.close()

    def test_rssreader_store_lifecycle(self, tmp_db):
        """RSSReader.store setter should register and close stores properly."""

        reader = rss.RSSReader()
        store = db.HistoryDB()

        closed = {"value": False}

        def fake_close():
            closed["value"] = True

        store.close = fake_close

        # Inject our store and verify it's used
        reader.store = store
        assert reader.store is store

        # Stopping the reader should close all active stores
        reader.stop()
        assert closed["value"]

    def test_rssreader_multi_uri_deduplicates_entries(self, httpserver: HTTPServer, tmp_db):
        """A feed with multiple URIs should not create duplicate jobs for the same link."""

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

        reader = rss.RSSReader()
        reader.run_feed(feed_name)

        entries = list(reader.store.rss_get_jobs(feed=feed_name))
        links = {e.link for e in entries}

        # Shared link must only appear once
        assert links == {shared_link, a_only_link, b_only_link}
