#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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

import sabnzbd.rss as rss
from sabnzbd.config import CFG, define_rss, ConfigCat


class TestRSS:
    def setup_rss(self, feed_name, feed_url):
        """ Setup the basic settings to get things going"""
        # Setup the config settings
        CFG["rss"] = {}
        CFG["rss"][feed_name] = {}
        CFG["rss"][feed_name]["uri"] = feed_url
        define_rss()

        # Need to create the Default category
        # Otherwise it will try to save the config
        ConfigCat("*", {})
        ConfigCat("tv", {})
        ConfigCat("movies", {})

    def test_rss_newznab_parser(self):
        """ Test basic RSS-parsing of custom elements
            Harder to test in functional test
        """
        feed_name = "TestFeedNewznab"
        self.setup_rss(feed_name, "https://sabnzbd.org/tests/rss_newznab_test.xml")

        # Start the RSS reader
        rss_obj = rss.RSSQueue()
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
        rss_obj = rss.RSSQueue()
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
