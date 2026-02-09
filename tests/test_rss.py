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
import time
from typing import Optional

import configobj
import pytest
from pytest_httpserver import HTTPServer

import sabnzbd.rss as rss
import sabnzbd.config
from sabnzbd.constants import DEFAULT_PRIORITY, LOW_PRIORITY, HIGH_PRIORITY, FORCE_PRIORITY
from sabnzbd.rss import FeedEvaluation, FeedConfig
from tests.testhelper import httpserver_handler_data_dir


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

    def test_rss_newznab_parser(self):
        """Test basic RSS-parsing of custom elements
        Harder to test in functional test
        """
        feed_name = "TestFeedNewznab"
        self.setup_rss(feed_name, "https://sabnzbd.org/tests/rss_newznab_test.xml")

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert feed_name in rss_obj.jobs
        assert "https://cdn.nzbgeek.info/cdn?t=get&id=FakeKey&apikey=FakeKey" in rss_obj.jobs[feed_name]

        # Check some job-data
        job_data = rss_obj.jobs[feed_name]["https://cdn.nzbgeek.info/cdn?t=get&id=FakeKey&apikey=FakeKey"]
        assert job_data["title"] == "FakeShow.S04E03.720p.WEB.H264-Obfuscated"
        assert job_data["infourl"] == "https://nzbgeek.info/geekseek.php?guid=FakeKey"
        assert job_data["orgcat"] == "TV > HD"
        assert job_data["cat"] == "tv"
        assert job_data["episode"] == "3"
        assert job_data["season"] == "4"
        assert job_data["size"] == 1209464000

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
        adjusted_date = datetime.datetime(2018, 4, 13, 5, 46, 25) - datetime.timedelta(seconds=time.timezone)
        assert job_data["age"] == adjusted_date

    def test_rss_nzedb_parser(self):
        feed_name = "TestFeednZEDb"
        self.setup_rss(feed_name, "https://sabnzbd.org/tests/rss_nzedb_test.xml")

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert feed_name in rss_obj.jobs
        assert "https://nzbfinder.ws/getnzb/FakeKey.nzb&i=46181&r=FakeKey" in rss_obj.jobs[feed_name]

        # Check some job-data
        # Added fake season and episode to test file
        job_data = rss_obj.jobs[feed_name]["https://nzbfinder.ws/getnzb/FakeKey.nzb&i=46181&r=FakeKey"]
        assert job_data["title"] == "Movie.With.a.Dog.2018.720p.BluRay.x264-SPRiNTER"
        assert job_data["infourl"] == "https://nzbfinder.ws/details/FakeKey"
        assert job_data["orgcat"] == "Movies > HD"
        assert job_data["cat"] == "movies"
        assert job_data["episode"] == "720"
        assert job_data["season"] == "2018"
        assert job_data["size"] == 5164539914

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
        adjusted_date = datetime.datetime(2019, 3, 2, 17, 18, 7) - datetime.timedelta(seconds=time.timezone)
        assert job_data["age"] == adjusted_date

    def test_rss_link(self, httpserver: HTTPServer):
        httpserver.expect_request("/rss_link.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedLink"
        self.setup_rss(feed_name, httpserver.url_for("/rss_link.xml"))

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert feed_name in rss_obj.jobs
        assert "http://LINK" in rss_obj.jobs[feed_name]

        # Check some job-data
        job_data = rss_obj.jobs[feed_name]["http://LINK"]
        assert job_data["title"] == "TITLE"
        assert job_data["infourl"] == "https://sabnzbd.org/rss_link"
        assert job_data["size"] == 200

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
        adjusted_date = datetime.datetime(2025, 5, 20, 18, 21, 1) - datetime.timedelta(seconds=time.timezone)
        assert job_data["age"] == adjusted_date

    def test_rss_enclosure_no_nzb(self, httpserver: HTTPServer):
        httpserver.expect_request("/rss_enclosure_no_nzb.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedEnclosureNoNZB"
        self.setup_rss(feed_name, httpserver.url_for("/rss_enclosure_no_nzb.xml"))

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert feed_name in rss_obj.jobs
        assert not rss_obj.jobs[feed_name]

    def test_rss_enclosure_multiple(self, httpserver: HTTPServer):
        httpserver.expect_request("/rss_enclosure_multiple.xml").respond_with_handler(httpserver_handler_data_dir)

        feed_name = "TestFeedEnclosureMultiple"
        self.setup_rss(feed_name, httpserver.url_for("/rss_enclosure_multiple.xml"))

        # Start the RSS reader
        rss_obj = rss.RSSReader()
        rss_obj.run_feed(feed_name)

        # Is the feed processed?
        assert feed_name in rss_obj.jobs
        assert "http://NZB_LINK" in rss_obj.jobs[feed_name]

        # Check some job-data
        job_data = rss_obj.jobs[feed_name]["http://NZB_LINK"]
        assert job_data["title"] == "TITLE"
        assert job_data["infourl"] == "https://sabnzbd.org/rss_enclosure_multiple"
        assert job_data["size"] == 200

        # feedparser returns UTC so SABnzbd converts to locale
        # of the system, so now we have to return to UTC
        adjusted_date = datetime.datetime(2025, 5, 20, 18, 21, 1) - datetime.timedelta(seconds=time.timezone)
        assert job_data["age"] == adjusted_date

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
