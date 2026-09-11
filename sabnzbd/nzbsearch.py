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

"""sabnzbd.nzbsearch - Search configured newznab indexers."""

from __future__ import annotations

import asyncio
import gzip
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import sabnzbd
import sabnzbd.config as config
from sabnzbd.misc import int_conv, cat_convert, to_units

CAPS_TTL = 24 * 3600
DEFAULT_LIMIT = 50  # results requested per indexer; not user-configurable
DEFAULT_TIMEOUT = 15  # seconds per indexer request; not user-configurable

_NEWZNAB_ERROR_KIND = {
    100: "auth",  # incorrect credentials
    101: "auth",  # account suspended
    102: "auth",  # insufficient privileges
    910: "auth",  # api disabled
    500: "rate_limited",  # request limit reached
    501: "rate_limited",  # download limit reached
}


# Standard newznab top-level categories, used when no indexer's caps can be fetched.
# Subcategories are indexer-specific and only ever come from a live t=caps response.
STANDARD_CATEGORIES = [
    {"id": 1000, "name": "Console", "subcats": []},
    {"id": 2000, "name": "Movies", "subcats": []},
    {"id": 3000, "name": "Audio", "subcats": []},
    {"id": 4000, "name": "PC", "subcats": []},
    {"id": 5000, "name": "TV", "subcats": []},
    {"id": 6000, "name": "XXX", "subcats": []},
    {"id": 7000, "name": "Books", "subcats": []},
    {"id": 8000, "name": "Other", "subcats": []},
]


# --------------------------------------------------------------------------- #
#  Data types
# --------------------------------------------------------------------------- #
class IndexerError(Exception):
    """A single indexer failed. `kind` is one of: auth, rate_limited, offline, error."""

    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class Indexer:
    """A configured newznab endpoint."""

    name: str
    display_name: str
    base_url: str
    api_path: str
    api_key: str

    @classmethod
    def from_config(cls, conf: config.ConfigIndexer) -> Indexer:
        values = conf.get_dict()
        return cls(
            name=values["name"],
            display_name=values["displayname"] or values["name"],
            base_url=values["host"],
            api_path=values["api_path"],
            api_key=values["api_key"],
        )


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str  # NZB download link (already carries the indexer apikey)
    indexer: str
    size: int = 0
    size_str: str = ""  # human-readable, e.g. "1.4 GB"
    age_days: int | None = None
    date: str | None = None  # ISO 8601, UTC
    category: str = ""
    category_ids: list[int] = field(default_factory=list)
    guid: str = ""
    details_url: str = ""
    grabs: int = 0
    files: int = 0
    poster: str = ""
    group: str = ""
    password: bool = False
    sab_category: str | None = None  # matching SABnzbd category, if any


@dataclass(slots=True)
class Caps:
    """A newznab indexer's advertised capabilities (t=caps)."""

    limits: dict = field(default_factory=dict)
    search_types: dict = field(default_factory=dict)
    categories: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  HTTP & XML parsing
# --------------------------------------------------------------------------- #
def _build_url(base_url: str, api_path: str, params: dict) -> str:
    """Compose ``<base_url>/<api_path>?<params>``, defaulting the scheme to https
    and dropping params whose value is None or empty."""
    base = (base_url or "").strip().rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        base = "https://" + base
    path = api_path.strip().strip("/")
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value not in (None, "")})
    return f"{base}/{path or 'api'}?{query}"


def _http_get(url: str, timeout: int) -> bytes:
    """GET a URL, translating transport or HTTP failures into an IndexerError."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"SABnzbd/{sabnzbd.__version__}", "Accept-Encoding": "gzip"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            if "gzip" in (response.headers.get("Content-Encoding") or ""):
                body = gzip.decompress(body)
            return body
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise IndexerError(f"Authentication failed (HTTP {error.code})", "auth")
        if error.code == 429:
            raise IndexerError("Rate limited (HTTP 429)", "rate_limited")
        try:
            _raise_for_newznab_error(error.read())
        except IndexerError:
            raise
        except Exception:
            pass
        raise IndexerError(f"HTTP error {error.code}", "offline" if error.code >= 500 else "error")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise IndexerError(f"Cannot reach indexer: {error}", "offline")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _raise_for_newznab_error(data: bytes):
    """Raise a classified IndexerError when `data` is a newznab <error> document."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return
    if _localname(root.tag).lower() == "error":
        desc = root.get("description") or "Unknown indexer error"
        code = int_conv(root.get("code"))
        raise IndexerError(desc, _NEWZNAB_ERROR_KIND.get(code, "error"))


def _parse_caps(data: bytes) -> Caps:
    """Parse a ``t=caps`` document."""
    _raise_for_newznab_error(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as err:
        raise IndexerError(f"Invalid capabilities response: {err}", "error")

    limits_el = root.find("limits")
    searching_el = root.find("searching")
    categories_el = root.find("categories")

    return Caps(
        limits={
            "max": int_conv(limits_el.get("max")),
            "default": int_conv(limits_el.get("default")),
        } if limits_el is not None else {},
        search_types={
            child.tag: {
                "available": child.get("available") == "yes",
                "params": [p for p in (child.get("supportedParams") or "").split(",") if p],
            }
            for child in (searching_el if searching_el is not None else [])
        },
        categories=[
            {
                "id": int_conv(cat.get("id")),
                "name": cat.get("name") or "",
                "subcats": [
                    {"id": int_conv(sub.get("id")), "name": sub.get("name") or ""}
                    for sub in cat.findall("subcat")
                ],
            }
            for cat in (categories_el.findall("category") if categories_el is not None else [])
        ],
    )


def _parse_results(data: bytes, indexer: Indexer) -> tuple[list[SearchResult], int | None]:
    """Parse a ``t=search`` RSS document into results plus the reported total hit count."""
    _raise_for_newznab_error(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as err:
        raise IndexerError(f"Invalid search response: {err}", "error")

    channel = root.find("channel")
    if channel is None:
        return [], None

    total = None
    for child in channel:
        if _localname(child.tag) == "response":
            total = int_conv(child.get("total"))
            break

    results = []
    for item in channel.findall("item"):
        if parsed := _parse_item(item, indexer):
            results.append(parsed)

    return results, total


def _parse_item(item: ET.Element, indexer: Indexer) -> SearchResult | None:
    """Build one SearchResult, or None when the entry has no usable download link."""
    attrs: dict[str, list[str]] = {}
    for child in item:
        if _localname(child.tag) == "attr" and (name := child.get("name")):
            attrs.setdefault(name, []).append(child.get("value") or "")

    link = (item.findtext("link") or "").strip()
    size = int_conv(attrs.get("size", [""])[0])
    enclosure = item.find("enclosure")
    if enclosure is not None and enclosure.get("url"):
        link = enclosure.get("url").strip()
        size = int_conv(enclosure.get("length")) or size

    if not link:
        return None

    age_days, date_iso = None, None
    raw_date = attrs.get("usenetdate", [""])[0] or (item.findtext("pubDate") or "").strip()
    if raw_date:
        try:
            posted = parsedate_to_datetime(raw_date)
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
            posted = posted.astimezone(timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - posted).days)
            date_iso = posted.isoformat()
        except (TypeError, ValueError):
            pass

    category = (item.findtext("category") or "").strip()
    return SearchResult(
        title=(item.findtext("title") or "").strip(),
        url=link,
        indexer=indexer.display_name,
        size=size,
        size_str=to_units(size, "B") if size else "",
        age_days=age_days,
        date=date_iso,
        category=category,
        category_ids=sorted({cid for val in attrs.get("category", []) if (cid := int_conv(val))}),
        guid=(item.findtext("guid") or "").strip(),
        details_url=(item.findtext("comments") or "").strip(),
        grabs=int_conv(attrs.get("grabs", [""])[0]),
        files=int_conv(attrs.get("files", [""])[0]),
        poster=attrs.get("poster", [""])[0],
        group=attrs.get("group", [""])[0],
        password=attrs.get("password", [""])[0] not in ("", "0", None),
        sab_category=cat_convert(category) or None,
    )


# --------------------------------------------------------------------------- #
#  Capabilities & Cache
# --------------------------------------------------------------------------- #
_caps_cache: dict[str, tuple[float, Caps]] = {}
_caps_lock = threading.Lock()


def get_caps(indexer: Indexer, *, refresh: bool = False) -> Caps:
    """Return an indexer's capabilities, from the 24h cache unless refresh=True."""
    if not refresh:
        with _caps_lock:
            cached_time, cached_caps = _caps_cache.get(indexer.name, (0, None))
            if cached_caps and (time.time() - cached_time < CAPS_TTL):
                return cached_caps

    url = _build_url(indexer.base_url, indexer.api_path, {"apikey": indexer.api_key, "t": "caps"})
    caps = _parse_caps(_http_get(url, DEFAULT_TIMEOUT))
    with _caps_lock:
        _caps_cache[indexer.name] = (time.time(), caps)
    return caps


def invalidate_caps(name: str | None = None):
    """Drop cached capabilities for one indexer, or all of them."""
    with _caps_lock:
        if name is None:
            _caps_cache.clear()
        else:
            _caps_cache.pop(name, None)


async def category_tree(indexer_names: list[str] | None = None) -> list[dict]:
    """The newznab category tree, merged across the selected indexers' capabilities.

    Falls back to STANDARD_CATEGORIES when no indexer's caps can be fetched.
    """
    indexers = _indexers_to_query(indexer_names)
    fetched = await asyncio.gather(
        *(asyncio.to_thread(get_caps, indexer) for indexer in indexers), return_exceptions=True
    )

    trees = []
    for indexer, caps in zip(indexers, fetched):
        if isinstance(caps, Caps):
            trees.append(caps.categories)
        else:
            logging.info("Capabilities for %s unavailable: %s", indexer.name, caps)

    return _merge_category_trees(trees) if trees else STANDARD_CATEGORIES


def _merge_category_trees(trees: list[list[dict]]) -> list[dict]:
    """Union several indexers' category trees, keyed by newznab id."""
    merged: dict[int, dict] = {}
    for tree in trees:
        for category in tree:
            node = merged.setdefault(category["id"], {"name": category["name"], "subcats": {}})
            node["name"] = node["name"] or category["name"]
            for sub in category["subcats"]:
                node["subcats"].setdefault(sub["id"], sub["name"])

    return [
        {
            "id": cid,
            "name": node["name"],
            "subcats": [{"id": sid, "name": name} for sid, name in sorted(node["subcats"].items())],
        }
        for cid, node in sorted(merged.items())
    ]


# --------------------------------------------------------------------------- #
#  Search
# --------------------------------------------------------------------------- #
def _indexers_to_query(names: list[str] | None) -> list[Indexer]:
    """The indexers to hit: the named ones, or every enabled one, name order."""
    configured = config.get_indexers()
    chosen = [configured[n] for n in names if n in configured] if names else list(configured.values())
    if not names:
        chosen = [conf for conf in chosen if conf.enable()]
    return sorted((Indexer.from_config(conf) for conf in chosen), key=lambda ix: ix.name)


def _query_indexer(indexer: Indexer, params: dict) -> tuple[dict, list[SearchResult]]:
    """Synchronous: query one indexer, returning (status_dict, results). Never raises."""
    try:
        url = _build_url(indexer.base_url, indexer.api_path, {"apikey": indexer.api_key, **params})
        data = _http_get(url, DEFAULT_TIMEOUT)
        results, total = _parse_results(data, indexer)
        return {
            "name": indexer.display_name,
            "status": "ok",
            "results": len(results),
            "total": total,
            "error": None,
        }, results
    except IndexerError as err:
        return {
            "name": indexer.display_name,
            "status": err.kind,
            "results": 0,
            "total": None,
            "error": str(err),
        }, []
    except Exception as err:
        logging.info("Indexer %s search failed: %s", indexer.display_name, err)
        logging.debug("Traceback: ", exc_info=True)
        return {
            "name": indexer.display_name,
            "status": "error",
            "results": 0,
            "total": None,
            "error": str(err),
        }, []


async def search_indexers(
    text: str,
    categories: list | None = None,
    maxage: int = 0,
    offset: int = 0,
    limit: int = 0,
    indexer_names: list[str] | None = None,
) -> dict:
    """Query every selected indexer concurrently; return their combined results, unfiltered."""
    query_text = (text or "").strip()
    params = {
        "t": "search",
        "q": query_text,
        "cat": ",".join(str(c) for c in categories) if categories else None,
        "maxage": maxage or None,
        "offset": offset or None,
        "limit": limit or DEFAULT_LIMIT,
        "extended": 1,
        "o": "xml",
    }
    indexers = _indexers_to_query(indexer_names)
    if not indexers:
        return {"query": query_text, "results": [], "total": 0, "total_available": 0, "indexers": []}

    outcomes = await asyncio.gather(
        *(asyncio.to_thread(_query_indexer, ix, params) for ix in indexers)
    )

    all_results: list[SearchResult] = []
    statuses: list[dict] = []
    for status, res in outcomes:
        statuses.append(status)
        all_results.extend(res)

    results = all_results
    results.sort(key=lambda r: (r.age_days if r.age_days is not None else 10**9, -r.grabs))

    return {
        "query": query_text,
        "results": [asdict(r) for r in results],
        "total": len(results),
        "total_available": max((s["total"] or 0 for s in statuses), default=0),
        "indexers": sorted(statuses, key=lambda s: s["name"].lower()),
    }
