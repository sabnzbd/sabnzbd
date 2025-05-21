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
tests.test_misc - Testing functions in misc.py
"""
import datetime
import time
import configobj
from pytest_httpserver import HTTPServer

import sabnzbd.rss as rss
import sabnzbd.config
from tests.testhelper import httpserver_handler_data_dir


class TestRSS:
    @staticmethod
    def setup_rss(feed_name, feed_url):
        """Setup the basic settings to get things going"""
        # Setup the config settings
        sabnzbd.config.CFG_OBJ = configobj.ConfigObj()
        sabnzbd.config.ConfigRSS(feed_name, {"uri": feed_url})

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
