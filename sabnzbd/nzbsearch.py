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

"""sabnzbd.nzbsearch - Search configured newznab indexers.

Two classes:
    Indexer          - one configured Newznab endpoint.
    NzbIndexerSearch - fans a search out across configured indexers.

This module only returns plain dataclasses/lists/dicts - building the actual
API response belongs to api.py.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock

import sabnzbd
import sabnzbd.config as config
from sabnzbd.decorators import synchronized
from sabnzbd.misc import get_base_url, int_conv, to_units

SEARCH_LIMIT = 100  # latest results requested per indexer
DEFAULT_TIMEOUT = 15  # seconds per indexer request; not user-configurable
UNKNOWN_AGE = datetime(1970, 1, 1, tzinfo=timezone.utc)


class IndexerError(Exception):
    """A single indexer request failed."""


def text_from_element(element: ET.Element, tag: str) -> str:
    return (element.findtext(tag) or "").strip()


def valid_details_url(url: str) -> str:
    return url if urllib.parse.urlparse(url).scheme.lower() in ("http", "https") else ""


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml_response(data: bytes) -> ET.Element:
    """Parse an indexer XML response and raise its reported error, if any."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise IndexerError(f"Invalid indexer response: {error}")
    if strip_namespace(root.tag).lower() == "error":
        raise IndexerError(root.get("description") or "Unknown indexer error")
    return root


@dataclass(slots=True)
class SearchResult:
    """One Newznab search hit, normalized for the search modal."""

    title: str
    url: str  # NZB download link (already carries the indexer apikey)
    baselink: str  # indexer's root domain, e.g. "nzbgeek.info" - for its favicon
    size_str: str = ""  # human-readable, e.g. "1.4 GB"
    age: datetime = UNKNOWN_AGE
    category: str = ""
    details_url: str = ""
    password: bool = False


class Indexer:
    """One configured newznab endpoint.

    Knows how to build its own request URLs and fetch and parse search results.
    """

    def __init__(self, name: str, base_url: str, api_path: str, api_key: str):
        self.name = name
        self.base_url = base_url
        self.api_path = api_path
        self.api_key = api_key

    def _build_url(self, **params) -> str:
        """Compose this indexer's API URL, defaulting the scheme to https and
        dropping params whose value is None or empty."""
        base = self.base_url.strip().rstrip("/")
        if not base.lower().startswith(("http://", "https://")):
            base = "https://" + base
        path = self.api_path.strip().strip("/")
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
        return f"{base}/{path or 'api'}?{query}"

    def fetch(self, **params) -> ET.Element:
        """GET this indexer's API."""
        url = self._build_url(apikey=self.api_key, **params)
        request = urllib.request.Request(
            url, headers={"User-Agent": f"SABnzbd/{sabnzbd.__version__}", "Accept-Encoding": "gzip"}
        )
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                body = response.read()
                if "gzip" in (response.headers.get("Content-Encoding") or ""):
                    body = gzip.decompress(body)
                return parse_xml_response(body)
        except urllib.error.HTTPError as error:
            raise IndexerError(f"Request failed (HTTP {error.code})")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise IndexerError(f"Cannot reach indexer: {error}")

    def test(self):
        """Verify that the indexer accepts its configured credentials."""
        self.fetch(t="caps")

    def get_categories(self) -> list[ET.Element]:
        """Return the categories advertised by this indexer."""
        logging.debug("Getting categories from indexer %s", self.name)
        try:
            categories = self.fetch(t="caps").findall("./categories/category")
        except Exception as error:
            logging.debug("Could not get categories from indexer %s: %s", self.name, error)
            raise

        logging.debug(
            "Indexer %s reported %s categories and %s subcategories",
            self.name,
            len(categories),
            sum(len(category.findall("subcat")) for category in categories),
        )
        return categories

    def search(self, text: str, category_ids: tuple = ()) -> tuple[list[SearchResult], int | None]:
        """Run one t=search against this indexer; returns (results, reported total)."""
        root = self.fetch(
            t="search",
            q=text,
            cat=",".join(str(cat_id) for cat_id in category_ids) or None,
            limit=SEARCH_LIMIT,
            extended=1,
            o="xml",
        )

        channel = root.find("channel")
        if channel is None:
            return [], None

        results = []
        for item in channel.findall("item"):
            attrs = {
                child.get("name"): child.get("value") or ""
                for child in item
                if strip_namespace(child.tag) == "attr" and child.get("name")
            }
            link = text_from_element(item, "link")
            size = int_conv(attrs.get("size"))
            enclosure = item.find("enclosure")
            if enclosure is not None and enclosure.get("url"):
                link = enclosure.get("url").strip()
                size = int_conv(enclosure.get("length")) or size
            if not link:
                continue
            details_url = valid_details_url(text_from_element(item, "comments"))
            raw_date = attrs.get("usenetdate") or text_from_element(item, "pubDate")
            try:
                age = parsedate_to_datetime(raw_date) if raw_date else UNKNOWN_AGE
            except (TypeError, ValueError):
                age = UNKNOWN_AGE
            if age.tzinfo is None:
                age = age.replace(tzinfo=timezone.utc)
            results.append(
                SearchResult(
                    title=text_from_element(item, "title"),
                    url=link,
                    baselink=get_base_url(self.base_url),
                    size_str=to_units(size, "B"),
                    age=age.astimezone(timezone.utc),
                    category=text_from_element(item, "category"),
                    details_url=details_url,
                    password=attrs.get("password") not in ("", "0", None),
                )
            )
        for child in channel:
            if strip_namespace(child.tag) == "response":
                return results, int_conv(child.get("total"))
        return results, None


def indexer_from_config(conf: config.ConfigIndexer) -> Indexer:
    values = conf.get_dict()
    return Indexer(values["name"], values["host"], values["api_path"], values["api_key"])


class CategoryCache:
    """Build the category tree once, until indexers are added or removed."""

    def __init__(self):
        self.lock = Lock()
        self.categories: list[dict] | None = None

    @synchronized()
    def get(self, indexers: list[Indexer]) -> list[dict]:
        if self.categories is None:
            logging.info("Getting categories from %s enabled indexers", len(indexers))
            categories = [
                {"id": 1000, "name": "Console", "subcats": []},
                {"id": 2000, "name": "Movies", "subcats": []},
                {"id": 3000, "name": "Audio", "subcats": []},
                {"id": 4000, "name": "PC", "subcats": []},
                {"id": 5000, "name": "TV", "subcats": []},
                {"id": 6000, "name": "XXX", "subcats": []},
                {"id": 7000, "name": "Books", "subcats": []},
                {"id": 8000, "name": "Other", "subcats": []},
            ]
            categories_by_id = {category["id"]: category for category in categories}
            for indexer in indexers:
                try:
                    indexer_categories = indexer.get_categories()
                except Exception:
                    continue
                for caps_category in indexer_categories:
                    category = categories_by_id.get(int_conv(caps_category.get("id")))
                    if category is None:
                        continue
                    existing_ids = {subcategory["id"] for subcategory in category["subcats"]}
                    for subcategory in caps_category.findall("subcat"):
                        subcategory_id = int_conv(subcategory.get("id"))
                        name = subcategory.get("name")
                        if subcategory_id and name and subcategory_id not in existing_ids:
                            category["subcats"].append({"id": subcategory_id, "name": name})
                            existing_ids.add(subcategory_id)
            for category in categories:
                category["subcats"].sort(key=lambda subcategory: subcategory["id"])
            logging.info("Loaded %s subcategories", sum(len(category["subcats"]) for category in categories))
            self.categories = categories
        return self.categories

    @synchronized()
    def clear(self):
        self.categories = None


CATEGORY_CACHE = CategoryCache()


def invalidate_categories():
    CATEGORY_CACHE.clear()


class NzbIndexerSearch:
    """Fans a search out across a set of indexers."""

    def __init__(self):
        self.indexers = sorted(
            (indexer_from_config(indexer) for indexer in config.get_indexers().values() if indexer.enable()),
            key=lambda indexer: indexer.name,
        )

    # --------------------------------------------------------------------- #
    #  Search
    # --------------------------------------------------------------------- #
    async def search(
        self,
        text: str,
        category_ids: list | None = None,
    ) -> tuple[list[SearchResult], int]:
        """Query every enabled indexer and return their latest results."""
        text = (text or "").strip()
        category_ids = tuple(category_ids or ())
        if not self.indexers:
            return [], 0
        logging.info("Searching %s enabled indexers", len(self.indexers))
        outcomes = await asyncio.gather(*(self._search_one(indexer, text, category_ids) for indexer in self.indexers))

        results = []
        total_available = 0
        for indexer_results, reported_total in outcomes:
            results.extend(indexer_results)
            total_available += reported_total if reported_total is not None else len(indexer_results)
        results.sort(key=lambda result: result.age, reverse=True)
        logging.info("Indexer search returned %s results (%s reported available)", len(results), total_available)
        return results, total_available

    async def _search_one(
        self,
        indexer: Indexer,
        text: str,
        category_ids: tuple,
    ) -> tuple[list[SearchResult], int | None]:
        """Search one indexer off the event loop; never raises - failures return no results."""
        try:
            logging.debug("Searching indexer %s", indexer.name)
            results, reported_total = await asyncio.to_thread(indexer.search, text, category_ids)
            logging.debug("Indexer %s returned %s results", indexer.name, len(results))
            return results, reported_total
        except IndexerError as error:
            logging.info("Indexer %s search failed: %s", indexer.name, error)
        except Exception as error:
            logging.info("Indexer %s search failed: %s", indexer.name, error)
            logging.debug("Traceback: ", exc_info=True)
        return [], None

    async def category_tree(self) -> list[dict]:
        """Return the cached category tree."""
        return await asyncio.to_thread(CATEGORY_CACHE.get, self.indexers)
