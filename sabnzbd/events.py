#!/usr/bin/python3 -OO
# Copyright 2008-2026 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.events - Server-sent events for the web interface
"""

import asyncio
import json
import logging
import zlib
from dataclasses import dataclass
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

import sabnzbd
import sabnzbd.api
from sabnzbd.constants import KIBI
from sabnzbd.misc import to_units

# How often the state is sampled, matching the default refresh rate
SAMPLE_INTERVAL = 1.0

# Comfortably under the 60 second read timeout nginx defaults to
HEARTBEAT_INTERVAL = 15.0

# Enough for a slow reader to catch up, few enough to notice one that never will
SUBSCRIBER_BACKLOG = 20


@dataclass(frozen=True)
class StreamOptions:
    """The arguments a subscriber wants its queue and history built with.

    Frozen so that subscribers asking for the same view share one group, and the
    building is done once for all of them instead of once each.
    """

    start: int = 0
    limit: int = 0
    search: Optional[str] = None
    categories: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    history_start: int = 0
    history_limit: int = 0
    history_search: Optional[str] = None
    history_categories: tuple[str, ...] = ()
    history_statuses: tuple[str, ...] = ()
    failed_only: bool = False
    archive: bool = False


class SubscriptionGroup:
    """Every subscriber wanting the same view, and the rows last sent to them"""

    def __init__(self, options: StreamOptions):
        self.options = options
        self.subscribers: set[asyncio.Queue] = set()
        self.queue_baseline: dict[str, int] = {}
        self.queue_order: list[str] = []
        self.queue_seeded = False
        self.history_baseline: dict[str, int] = {}
        self.history_order: list[str] = []
        self.history_seeded = False
        self.history_update = 0
        self.joined = False


_groups: dict[StreamOptions, SubscriptionGroup] = {}
_producer: Optional[asyncio.Task] = None
_last_snapshot: dict[str, Any] = {}


def format_message(event: str, data: Any) -> str:
    """Render one event in the server-sent events wire format"""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def subscribe(options: StreamOptions) -> asyncio.Queue:
    """Register a stream and hand back the queue it should read"""
    if not (group := _groups.get(options)):
        group = _groups[options] = SubscriptionGroup(options)
    else:
        # A joiner has no rows yet, and deltas alone would never give it any. Only note
        # it here: the flags themselves belong to the producer, which builds frames on a
        # worker thread, and writing them from both sides loses whichever wrote first.
        group.joined = True

    subscriber = asyncio.Queue(maxsize=SUBSCRIBER_BACKLOG)
    group.subscribers.add(subscriber)
    return subscriber


def unsubscribe(options: StreamOptions, subscriber: asyncio.Queue):
    if group := _groups.get(options):
        group.subscribers.discard(subscriber)
        if not group.subscribers:
            del _groups[options]


def subscriber_count() -> int:
    return sum(len(group.subscribers) for group in _groups.values())


def _deliver(subscribers, event: str, data: Any):
    for subscriber in subscribers:
        try:
            subscriber.put_nowait((event, data))
        except asyncio.QueueFull:
            # A reader this far behind cannot be caught up by sending it more, so
            # throw away what it missed and tell it to fetch the state itself
            while not subscriber.empty():
                subscriber.get_nowait()
            subscriber.put_nowait(("resync", {}))


def publish(event: str, data: Any):
    """Hand an event to every stream, from within the event loop"""
    for group in list(_groups.values()):
        _deliver(group.subscribers, event, data)


def publish_threadsafe(event: str, data: Any):
    """Hand an event to every stream from a thread that is not running the event loop"""
    if _producer and (loop := _producer.get_loop()):
        loop.call_soon_threadsafe(publish, event, data)


def snapshot() -> dict[str, Any]:
    """The parts of the state that are the same for every client, and cheap to read"""
    anfo = sabnzbd.ArticleCache.cache_info()
    return {
        # Same fields the queue carries, so the interface formats them in one place
        "speed": to_units(sabnzbd.BPSMeter.bps),
        "kbpersec": "%.2f" % (sabnzbd.BPSMeter.bps / KIBI),
        "cache_art": str(anfo.article_sum),
        "cache_size": to_units(anfo.cache_size, "B"),
        "paused": sabnzbd.Downloader.paused,
        "queue_bytes_left": sabnzbd.NzbQueue.remaining(),
        "queue_slots": sabnzbd.NzbQueue.actives(),
        "history_update": sabnzbd.LAST_HISTORY_UPDATE,
    }


def row_fingerprint(row: dict[str, Any]) -> int:
    return zlib.crc32(json.dumps(row, sort_keys=True, default=str).encode())


def row_delta(rows: list[dict[str, Any]], baseline: dict[str, int]) -> tuple[list[str], list[int], dict[str, int]]:
    """Split rows into the order they are in and the indexes that differ from the baseline"""
    order: list[str] = []
    changed: list[int] = []
    fingerprints: dict[str, int] = {}
    for index, row in enumerate(rows):
        key = row.get("nzo_id") or str(index)
        fingerprint = row_fingerprint(row)
        order.append(key)
        fingerprints[key] = fingerprint
        if baseline.get(key) != fingerprint:
            changed.append(index)
    return order, changed, fingerprints


def _frame(payload: dict[str, Any], rows_key: str, rows, order, previous_order, seeded) -> dict[str, Any]:
    """A full payload the first time, and only what moved after that"""
    if not seeded:
        return {"type": "init", rows_key: payload}

    delta = dict(payload)
    delta["slots"] = rows
    frame = {"type": "delta", rows_key: delta}
    if order != previous_order:
        # Sent even when empty: without it a page that drained to nothing looks the
        # same as a page that did not change, and the client keeps showing the rows
        frame["order"] = order
    return frame


def build_frames(group: SubscriptionGroup) -> list[tuple[str, dict[str, Any]]]:
    """Build this group's queue and history frames, called off the event loop"""
    options = group.options
    frames = []

    queue = sabnzbd.api.build_queue(
        start=options.start,
        limit=options.limit,
        search=options.search,
        categories=list(options.categories) or None,
        priorities=list(options.priorities) or None,
        statuses=list(options.statuses) or None,
    )
    slots = queue.get("slots", [])
    order, changed, fingerprints = row_delta(slots, group.queue_baseline)
    previous_order, seeded = group.queue_order, group.queue_seeded
    group.queue_baseline, group.queue_order, group.queue_seeded = fingerprints, order, True
    if not seeded or changed or order != previous_order:
        frames.append(("queue", _frame(queue, "queue", [slots[i] for i in changed], order, previous_order, seeded)))

    # The counter only moves when something in the history did
    history_update = sabnzbd.LAST_HISTORY_UPDATE
    if history_update != group.history_update or not group.history_seeded:
        group.history_update = history_update
        history = sabnzbd.api.build_history_payload(
            start=options.history_start,
            limit=options.history_limit,
            search=options.history_search,
            categories=list(options.history_categories) or None,
            statuses=list(options.history_statuses) or None,
            failed_only=options.failed_only,
            archive=options.archive,
        )
        slots = history.get("slots", [])
        order, changed, fingerprints = row_delta(slots, group.history_baseline)
        previous_order, seeded = group.history_order, group.history_seeded
        group.history_baseline, group.history_order, group.history_seeded = fingerprints, order, True
        if not seeded or changed or order != previous_order:
            frames.append(
                ("history", _frame(history, "history", [slots[i] for i in changed], order, previous_order, seeded))
            )

    return frames


async def _run():
    """Sample the state and publish what changed, once per group of identical views"""
    global _last_snapshot
    while True:
        await asyncio.sleep(SAMPLE_INTERVAL)
        if not _groups:
            continue

        try:
            current = await run_in_threadpool(snapshot)
        except Exception:
            logging.info("Failed to sample state for events", exc_info=True)
            continue
        if current != _last_snapshot:
            _last_snapshot = current
            publish("status", current)

        for group in list(_groups.values()):
            if not group.subscribers:
                continue
            if group.joined:
                # Sending the whole view again costs the others one frame and keeps
                # every subscriber reading the same baseline
                group.queue_seeded = False
                group.history_seeded = False
                group.joined = False
            try:
                frames = await run_in_threadpool(build_frames, group)
            except Exception:
                logging.info("Failed to build events for a subscription", exc_info=True)
                continue
            for event, data in frames:
                _deliver(group.subscribers, event, data)


def start():
    """Start sampling, called once the event loop is running"""
    global _producer
    if not _producer:
        _producer = asyncio.create_task(_run())


async def stop():
    """Stop sampling and release every stream.

    Without this the server waits for the streams to end by themselves, which they
    never do, and a restart hangs.
    """
    global _producer, _last_snapshot
    if _producer:
        _producer.cancel()
        try:
            await _producer
        except asyncio.CancelledError:
            pass
        _producer = None

    for group in list(_groups.values()):
        for subscriber in group.subscribers:
            try:
                subscriber.put_nowait((None, None))
            except asyncio.QueueFull:
                pass
    _groups.clear()
    _last_snapshot = {}
