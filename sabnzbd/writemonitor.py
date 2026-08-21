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
sabnzbd.writemonitor - whether the download directory keeps up with scattered writes
"""

import logging
import threading
import time
from collections import deque
from typing import Optional

import sabctools

import sabnzbd
from sabnzbd.constants import KIBI, MEBI
from sabnzbd.decorators import synchronized
from sabnzbd.filesystem import is_rotational
from sabnzbd.misc import to_units

# Seconds between readings of the write counters
SAMPLE_INTERVAL = 2.0
# Minimum reading to mean anything
MIN_COST_BYTES = 512 * KIBI
# Minimum reading to go into the rate estimate, which needs volume
MIN_RATE_BYTES = 4 * MEBI
# Weight of the newest sample in the reported average
EMA_ALPHA = 0.3
# Seconds of writes the rate estimate is averaged over. Long enough to span both a
# burst the page cache absorbed and the stall that follows it.
WRITE_RATE_WINDOW = 30.0
# Throughput inside write() below which the destination counts as not keeping up
SLOW_WRITE_MBPS = 100
# The same figure as nanoseconds per byte, which is what is tracked
SLOW_WRITE_COST = 1e9 / (SLOW_WRITE_MBPS * MEBI)
# Consecutive slow samples before backing off to the cache
SLOW_SAMPLES_BEFORE_BACKOFF = 3
# Seconds on the cache before decoding to disk is tried again, doubling on each refusal
RETRY_AFTER = 300.0
RETRY_AFTER_MAX = 3600.0


class WriteMonitor:
    """Whether the download directory is absorbing scattered writes"""

    def __init__(self):
        self.lock = threading.RLock()
        self.path: str = ""
        self.allow_direct_decode = False
        self.hint: Optional[bool] = None
        # Nanoseconds per byte spent inside write(), smoothed
        self.cost: Optional[float] = None
        # Bytes per second the destination actually drained, over WRITE_RATE_WINDOW.
        # Zero until measured, which a real reading can never be.
        self.throughput: float = 0.0
        self.window: deque[tuple[int, float]] = deque()
        # Consecutive samples in which the device did not keep up
        self.slow_samples = 0
        self.retry_after = RETRY_AFTER
        self.retry_at = 0.0
        self.sampled_at = 0.0
        # Counters as of the previous sample
        self.seen = (0, 0, 0)
        self.reset()

    @synchronized()
    def reset(self):
        """Start again for the download directory, reading the hint but measuring nothing"""
        self.path = sabnzbd.cfg.download_dir.get_path()
        self.hint = is_rotational(self.path)
        self.allow_direct_decode = not self.hint
        self.retry_after = RETRY_AFTER
        self.retry_at = time.monotonic() + RETRY_AFTER
        self.rebaseline()
        logging.info(
            "Storage profile for %s: %s -> %s",
            self.path,
            {True: "rotational", False: "non-rotational", None: "unknown"}[self.hint],
            "articles written as they arrive" if self.allow_direct_decode else "articles held in the cache",
        )

    def rebaseline(self):
        """Start counting writes from this moment, keeping what they have cost so far"""
        self.slow_samples = 0
        self.seen = self.read_counters()
        # So the next sample measures from here, not from whenever the process started
        self.sampled_at = time.monotonic()

    @synchronized()
    def sample(self):
        """Look at what the writes have cost since last time"""
        now = time.monotonic()
        if (elapsed := now - self.sampled_at) < SAMPLE_INTERVAL:
            return
        self.sampled_at = now

        _, written, nanos = self.consume_counters()
        cost = nanos / written if written >= MIN_COST_BYTES and nanos > 0 else None
        if cost is not None:
            self.cost = cost if self.cost is None else EMA_ALPHA * cost + (1 - EMA_ALPHA) * self.cost
        if written >= MIN_RATE_BYTES:
            # Over the wall clock, not over the time spent inside write()
            self.record_rate(written, elapsed)

        if not self.allow_direct_decode:
            # Only the clock changes the mode back
            if now >= self.retry_at:
                logging.info("Writing articles to %s as they arrive again, to see whether it keeps up", self.path)
                self.allow_direct_decode = True
                self.rebaseline()
        elif cost is not None:
            # Without a cost the streak neither grows nor is given up
            if cost <= SLOW_WRITE_COST:
                self.slow_samples = 0
            else:
                self.slow_samples += 1
                if self.slow_samples >= SLOW_SAMPLES_BEFORE_BACKOFF:
                    self.demote()

    def record_rate(self, written: int, elapsed: float):
        """Fold a reading into the windowed rate"""
        self.window.append((written, elapsed))
        span = sum(seconds for _, seconds in self.window)
        while len(self.window) > 1 and span > WRITE_RATE_WINDOW:
            span -= self.window.popleft()[1]
        self.throughput = sum(size for size, _ in self.window) / span

    @synchronized()
    def forget_rate(self):
        """Drop what the destination was measured to drain"""
        self.cost = None
        self.throughput = 0.0
        self.window.clear()

    @staticmethod
    def read_counters() -> tuple[int, int, int]:
        """Writes, bytes and nanoseconds every file has cost since sabctools loaded"""
        stats = sabctools.write_stats()
        return stats["count"], stats["bytes"], stats["nanos"]

    def consume_counters(self) -> tuple[int, int, int]:
        """The same three, but only since the previous sample"""
        current = self.read_counters()
        interval = tuple(now - before for now, before in zip(current, self.seen))
        self.seen = current
        return interval

    def demote(self):
        """Hold articles in the cache again, and wait longer before trying once more"""
        logging.info(
            "Writes to %s are not being absorbed (%s/s inside write), holding articles in the cache for %.0f minutes",
            self.path,
            to_units(1e9 / self.cost),
            self.retry_after / 60,
        )
        self.allow_direct_decode = False
        self.retry_at = time.monotonic() + self.retry_after
        self.retry_after = min(self.retry_after * 2, RETRY_AFTER_MAX)
        self.rebaseline()
