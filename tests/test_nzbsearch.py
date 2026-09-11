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

import asyncio
import os

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Response

import sabnzbd.config as config
import sabnzbd.nzbsearch as nzbsearch
from tests.testhelper import SAB_DATA_DIR


def _data(name: str) -> bytes:
    with open(os.path.join(SAB_DATA_DIR, name), "rb") as f:
        return f.read()


@pytest.fixture(autouse=True)
def _clear_caps_cache():
    nzbsearch.invalidate_caps()
    yield
    nzbsearch.invalidate_caps()


def _make_indexer(
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
        url = nzbsearch._build_url("api.example.com", "api", {"t": "search", "apikey": "K", "q": "x y"})
        assert url.startswith("https://api.example.com/api?")
        assert "t=search" in url and "apikey=K" in url and "q=x+y" in url

    def test_keeps_explicit_scheme_and_strips_slashes(self):
        assert nzbsearch._build_url("http://box.local/", "/rss/", {"t": "caps"}) == "http://box.local/rss?t=caps"

    def test_drops_empty_params(self):
        url = nzbsearch._build_url("h.example", "/api", {"t": "search", "cat": None, "maxage": "", "limit": 50})
        assert "cat=" not in url and "maxage=" not in url and "limit=50" in url


class TestParsing:
    def test_parse_caps(self):
        caps = nzbsearch._parse_caps(_data("nzbsearch_caps.xml"))
        assert caps.limits == {"max": 100, "default": 50}
        assert caps.search_types["tv-search"]["available"] is True
        assert "season" in caps.search_types["tv-search"]["params"]
        assert [c["id"] for c in caps.categories] == [2000, 5000]
        tv = next(c for c in caps.categories if c["id"] == 5000)
        assert {s["id"] for s in tv["subcats"]} == {5030, 5040, 5070}

    def test_parse_results_fields(self, httpserver: HTTPServer):
        indexer = nzbsearch.Indexer.from_config(_make_indexer("a", httpserver))
        results, total = nzbsearch._parse_results(_data("nzbsearch_results_a.xml"), indexer)
        assert total == 2
        first = results[0]
        assert first.title == "Ubuntu.22.04.Desktop.amd64-ISO"
        assert first.url.endswith("aaa1.nzb&apikey=AKEY")
        assert first.size == 3000000000
        assert first.category_ids == [4000, 4020]
        assert first.indexer == "a"
        assert first.grabs == 45 and first.files == 12
        assert first.group == "alt.binaries.iso"
        assert results[1].password is True

    def test_newznab_error_classification(self):
        with pytest.raises(nzbsearch.IndexerError) as exc:
            nzbsearch._raise_for_newznab_error(b'<error code="100" description="Incorrect user credentials"/>')
        assert exc.value.kind == "auth"

        with pytest.raises(nzbsearch.IndexerError) as exc:
            nzbsearch._raise_for_newznab_error(b'<error code="500" description="Request limit reached"/>')
        assert exc.value.kind == "rate_limited"

        # A normal RSS body must pass through untouched
        nzbsearch._raise_for_newznab_error(b"<rss><channel></channel></rss>")


class TestSearchIndexers:
    def test_fan_out_combines_all_indexers_without_deduping(self, httpserver: HTTPServer):
        _route(httpserver, "/one", "nzbsearch_results_a.xml")
        _route(httpserver, "/two", "nzbsearch_results_b.xml")
        _make_indexer("alpha", httpserver, mount="/one")
        _make_indexer("beta", httpserver, mount="/two")

        out = asyncio.run(nzbsearch.search_indexers("show"))
        assert out["total"] == 4
        assert {i["status"] for i in out["indexers"]} == {"ok"}
        titles = [r["title"] for r in out["results"]]
        # The same release appears on both indexers; both copies are kept
        assert titles.count("Some.Show.S01E01.1080p.WEB.H264-GRP") == 2

    def test_auth_failure_is_surfaced_per_indexer(self, httpserver: HTTPServer):
        _route(httpserver, "/ok", "nzbsearch_results_a.xml")
        httpserver.expect_request("/bad/api").respond_with_data(
            '<error code="100" description="Incorrect user credentials"/>', status=200
        )
        _make_indexer("good", httpserver, mount="/ok")
        _make_indexer("broken", httpserver, mount="/bad")

        out = asyncio.run(nzbsearch.search_indexers("show"))
        by_name = {i["name"]: i for i in out["indexers"]}
        assert by_name["good"]["status"] == "ok"
        assert by_name["broken"]["status"] == "auth"
        assert out["total"] == 2  # only the reachable indexer's results

    def test_no_indexers_configured(self):
        out = asyncio.run(nzbsearch.search_indexers("show"))
        assert out == {"query": "show", "results": [], "total": 0, "total_available": 0, "indexers": []}

    def test_category_filter_passed_through(self, httpserver: HTTPServer):
        seen = {}

        def handler(request):
            seen["cat"] = request.args.get("cat")
            return Response(_data("nzbsearch_results_a.xml"), content_type="application/rss+xml")

        httpserver.expect_request("/x/api").respond_with_handler(handler)
        _make_indexer("x", httpserver, mount="/x")
        asyncio.run(nzbsearch.search_indexers("show", categories=[2000, 2040]))
        assert seen["cat"] == "2000,2040"


class TestCaps:
    def test_second_call_uses_cache(self, httpserver: HTTPServer):
        httpserver.expect_request("/api").respond_with_data(
            _data("nzbsearch_caps.xml"), content_type="application/xml"
        )
        indexer = nzbsearch.Indexer.from_config(_make_indexer("cached", httpserver))
        first = nzbsearch.get_caps(indexer)
        second = nzbsearch.get_caps(indexer)
        assert first is second
        assert len(httpserver.log) == 1

    def test_category_tree_merges_indexers(self, httpserver: HTTPServer):
        httpserver.expect_request("/api").respond_with_data(
            _data("nzbsearch_caps.xml"), content_type="application/xml"
        )
        _make_indexer("one", httpserver)
        tree = asyncio.run(nzbsearch.category_tree())
        assert [c["id"] for c in tree] == [2000, 5000]

    def test_category_tree_falls_back_to_standard(self, httpserver: HTTPServer):
        httpserver.expect_request("/api").respond_with_data("boom", status=500)
        _make_indexer("dead", httpserver)
        tree = asyncio.run(nzbsearch.category_tree())
        assert [c["id"] for c in tree] == [c["id"] for c in nzbsearch.STANDARD_CATEGORIES]
