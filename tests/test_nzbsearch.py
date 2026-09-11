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
tests.test_nzbsearch - Testing sabnzbd.nzbsearch
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import fields
from datetime import datetime, timezone

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Response

import sabnzbd.config as config
import sabnzbd.nzbsearch as nzbsearch
from tests.testhelper import SAB_DATA_DIR, run_async


def _data(name: str) -> bytes:
    with open(os.path.join(SAB_DATA_DIR, name), "rb") as f:
        return f.read()


def _make_indexer_config(
    name: str, httpserver: HTTPServer, mount: str = "", api_key: str = "KEY"
) -> config.ConfigIndexer:
    return config.ConfigIndexer(
        name,
        {
            "host": httpserver.url_for(mount).rstrip("/"),
            "api_path": "/api",
            "api_key": api_key,
            "enable": True,
        },
    )


def _make_indexer(name: str, httpserver: HTTPServer, mount: str = "", api_key: str = "KEY") -> nzbsearch.Indexer:
    return nzbsearch.indexer_from_config(_make_indexer_config(name, httpserver, mount, api_key))


def _route(httpserver: HTTPServer, mount: str, results_file: str):
    """Answer t=caps and t=search for one mounted indexer path"""

    def handler(request):
        function = request.args.get("t")
        if function == "caps":
            return Response(_data("nzbsearch_caps.xml"), content_type="application/xml")
        if function == "search":
            return Response(_data(results_file), content_type="application/rss+xml")
        return Response("<error code='202' description='No such function'/>", status=200)

    httpserver.expect_request(mount + "/api").respond_with_handler(handler)


class TestUrlBuilder:
    def test_adds_scheme_and_path(self):
        indexer = nzbsearch.Indexer("x", "api.example.com", "api", "K")
        url = indexer._build_url(t="search", apikey="K", q="x y")
        assert url.startswith("https://api.example.com/api?")
        assert "t=search" in url and "apikey=K" in url and "q=x+y" in url

    def test_keeps_explicit_scheme_and_strips_slashes(self):
        indexer = nzbsearch.Indexer("x", "http://box.local/", "/rss/", "K")
        assert indexer._build_url(t="caps") == "http://box.local/rss?t=caps"

    def test_drops_empty_params(self):
        indexer = nzbsearch.Indexer("x", "h.example", "/api", "K")
        url = indexer._build_url(t="search", cat=None, unused="", limit=50)
        assert "cat=" not in url and "unused=" not in url and "limit=50" in url


class TestParsing:

    def test_parse_results_fields(self, httpserver: HTTPServer):
        indexer = _make_indexer("a", httpserver)
        indexer.fetch = lambda **_: nzbsearch.parse_xml_response(_data("nzbsearch_results_a.xml"))
        results, total = indexer.search("Ubuntu")
        assert total == 2
        first = results[0]
        assert first.title == "Ubuntu.22.04.Desktop.amd64-ISO"
        assert first.url.endswith("aaa1.nzb&apikey=AKEY")
        assert first.baselink == "localhost"
        assert first.size_str
        assert isinstance(first.age, datetime)
        assert results[1].password is True
        assert [item.name for item in fields(nzbsearch.SearchResult)] == [
            "title",
            "url",
            "baselink",
            "size_str",
            "age",
            "category",
            "details_url",
            "password",
        ]

    def test_newznab_error_message(self):
        with pytest.raises(nzbsearch.IndexerError) as exc:
            nzbsearch.parse_xml_response(b'<error code="100" description="Incorrect user credentials"/>')
        assert str(exc.value) == "Incorrect user credentials"

        # A normal RSS body must pass through untouched
        nzbsearch.parse_xml_response(b"<rss><channel></channel></rss>")

    def test_missing_item_date_defaults_to_zero_days(self):
        indexer = nzbsearch.Indexer("x", "example.com", "api", "KEY")
        indexer.fetch = lambda **_: ET.fromstring(
            "<rss><channel><item><link>https://example.com/item.nzb</link></item></channel></rss>"
        )
        results, _ = indexer.search("item")
        assert results[0].age == datetime(1970, 1, 1, tzinfo=timezone.utc)


class TestNzbIndexerSearch:
    def test_fan_out_combines_all_indexers_without_deduping(self, httpserver: HTTPServer):
        _route(httpserver, "/one", "nzbsearch_results_a.xml")
        _route(httpserver, "/two", "nzbsearch_results_b.xml")
        _make_indexer_config("alpha", httpserver, mount="/one")
        _make_indexer_config("beta", httpserver, mount="/two")

        results, _ = run_async(nzbsearch.NzbIndexerSearch().search("show"))
        assert len(results) == 4
        titles = [r.title for r in results]
        # The same release appears on both indexers; both copies are kept
        assert titles.count("Some.Show.S01E01.1080p.WEB.H264-GRP") == 2

    def test_auth_failure_does_not_break_other_indexers(self, httpserver: HTTPServer):
        _route(httpserver, "/ok", "nzbsearch_results_a.xml")
        httpserver.expect_request("/bad/api").respond_with_data(
            '<error code="100" description="Incorrect user credentials"/>', status=200
        )
        _make_indexer_config("good", httpserver, mount="/ok")
        _make_indexer_config("broken", httpserver, mount="/bad")

        results, _ = run_async(nzbsearch.NzbIndexerSearch().search("show"))
        assert len(results) == 2  # only the reachable indexer's results

    def test_no_indexers_configured(self):
        results, total_available = run_async(nzbsearch.NzbIndexerSearch().search("show"))
        assert results == []
        assert total_available == 0

    def test_category_filter_and_fixed_limit_passed_through(self, httpserver: HTTPServer):
        seen = {}

        def handler(request):
            seen["cat"] = request.args.get("cat")
            seen["offset"] = request.args.get("offset")
            seen["limit"] = request.args.get("limit")
            return Response(_data("nzbsearch_results_a.xml"), content_type="application/rss+xml")

        httpserver.expect_request("/x/api").respond_with_handler(handler)
        _make_indexer_config("x", httpserver, mount="/x")
        run_async(nzbsearch.NzbIndexerSearch().search("show", category_ids=[2000, 2040]))
        assert seen == {"cat": "2000,2040", "offset": None, "limit": "100"}


class TestCategories:
    def test_category_tree_uses_indexer_caps(self, httpserver: HTTPServer):
        nzbsearch.invalidate_categories()
        _route(httpserver, "/one", "nzbsearch_results_a.xml")
        httpserver.expect_request("/two/api").respond_with_data(
            """
            <caps><categories>
                <category id="1000"><subcat id="1010" name="NDS"/></category>
                <category id="2000"><subcat id="2010" name="Foreign"/></category>
            </categories></caps>
            """,
            content_type="application/xml",
        )
        _make_indexer_config("alpha", httpserver, mount="/one")
        _make_indexer_config("beta", httpserver, mount="/two")
        tree = run_async(nzbsearch.NzbIndexerSearch().category_tree())
        assert [category["id"] for category in tree] == list(range(1000, 9000, 1000))
        assert tree[0]["subcats"] == [{"id": 1010, "name": "NDS"}]
        assert tree[1]["subcats"] == [
            {"id": 2010, "name": "Foreign"},
            {"id": 2030, "name": "SD"},
            {"id": 2040, "name": "HD"},
            {"id": 2045, "name": "UHD"},
        ]
        assert tree[4]["subcats"] == [
            {"id": 5030, "name": "SD"},
            {"id": 5040, "name": "HD"},
            {"id": 5070, "name": "Anime"},
        ]

    def test_category_tree_caches_caps_until_invalidated(self):
        calls = 0
        indexer = nzbsearch.Indexer("x", "example.com", "api", "KEY")

        def get_categories():
            nonlocal calls
            calls += 1
            return [ET.fromstring('<category id="2000"><subcat id="2040" name="HD"/></category>')]

        searcher = nzbsearch.NzbIndexerSearch()
        searcher.indexers = [indexer]
        indexer.get_categories = get_categories
        nzbsearch.invalidate_categories()

        assert run_async(searcher.category_tree())[1]["subcats"] == [{"id": 2040, "name": "HD"}]
        assert run_async(searcher.category_tree())[1]["subcats"] == [{"id": 2040, "name": "HD"}]
        assert calls == 1

        nzbsearch.invalidate_categories()
        assert run_async(searcher.category_tree())[1]["subcats"] == [{"id": 2040, "name": "HD"}]
        assert calls == 2
        nzbsearch.invalidate_categories()
