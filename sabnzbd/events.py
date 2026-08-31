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
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

import sabnzbd

# How often the state is sampled, matching the default refresh rate
SAMPLE_INTERVAL = 1.0

# Comfortably under the 60 second read timeout nginx defaults to
HEARTBEAT_INTERVAL = 15.0

# Enough for a slow reader to catch up, few enough to notice one that never will
SUBSCRIBER_BACKLOG = 20

_subscribers: set[asyncio.Queue] = set()
_producer: Optional[asyncio.Task] = None
_last_snapshot: dict[str, Any] = {}


def format_message(event: str, data: Any) -> str:
    """Render one event in the server-sent events wire format"""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def subscribe() -> asyncio.Queue:
    """Register a stream and hand back the queue it should read"""
    subscriber = asyncio.Queue(maxsize=SUBSCRIBER_BACKLOG)
    _subscribers.add(subscriber)
    return subscriber


def unsubscribe(subscriber: asyncio.Queue):
    _subscribers.discard(subscriber)


def subscriber_count() -> int:
    return len(_subscribers)


def publish(event: str, data: Any):
    """Hand an event to every stream, from within the event loop"""
    for subscriber in _subscribers:
        try:
            subscriber.put_nowait((event, data))
        except asyncio.QueueFull:
            # A reader this far behind cannot be caught up by sending it more, so
            # throw away what it missed and tell it to fetch the state itself
            while not subscriber.empty():
                subscriber.get_nowait()
            subscriber.put_nowait(("resync", {}))


def publish_threadsafe(event: str, data: Any):
    """Hand an event to every stream from a thread that is not running the event loop"""
    if _producer and (loop := _producer.get_loop()):
        loop.call_soon_threadsafe(publish, event, data)


def snapshot() -> dict[str, Any]:
    """The parts of the state that are the same for every client, and cheap to read"""
    return {
        "speed": int(sabnzbd.BPSMeter.bps),
        "paused": sabnzbd.Downloader.paused,
        "queue_bytes_left": sabnzbd.NzbQueue.remaining(),
        "queue_slots": sabnzbd.NzbQueue.actives(),
        "history_update": sabnzbd.LAST_HISTORY_UPDATE,
    }


async def _run():
    """Sample the state and publish it whenever it differs from the last sample"""
    global _last_snapshot
    while True:
        await asyncio.sleep(SAMPLE_INTERVAL)
        if not _subscribers:
            continue
        try:
            current = await run_in_threadpool(snapshot)
        except Exception:
            logging.info("Failed to sample state for events", exc_info=True)
            continue
        if current != _last_snapshot:
            _last_snapshot = current
            publish("status", current)


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

    for subscriber in list(_subscribers):
        try:
            subscriber.put_nowait((None, None))
        except asyncio.QueueFull:
            pass
    _subscribers.clear()
    _last_snapshot = {}
