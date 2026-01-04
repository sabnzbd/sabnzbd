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
sabnzbd.articlecache - Article cache handling
"""

import logging
import threading
import struct
import time
from typing import Collection, Optional

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import (
    GIGI,
    ANFO,
    ARTICLE_CACHE_UPPER_PERCENTAGE,
    ARTICLE_CACHE_LOWER_PERCENTAGE,
    ARTICLE_CACHE_DIRECT_WRITE_LIMIT_WAIT,
)
from sabnzbd.nzb import Article, NzbFile
from sabnzbd.misc import to_units

# Operations on the article table are handled via try/except.
# The counters need to be made atomic to ensure consistency.
ARTICLE_COUNTER_LOCK = threading.RLock()

_SECONDS_BETWEEN_FLUSHES = 0.5


class ArticleCache(threading.Thread):
    def __init__(self):
        super().__init__()
        self.shutdown = False
        self.__direct_write: bool = bool(sabnzbd.cfg.direct_write())
        self.__cache_limit_org = 0
        self.__cache_limit = 0
        self.__cache_size = 0
        self.__article_table: dict[Article, bytearray] = {}  # Dict of buffered articles
        self.__cache_size_cv: threading.Condition = threading.Condition(ARTICLE_COUNTER_LOCK)
        self.__next_flush: float = 0
        self.__cache_size_upper: int = 0  # Force flush trigger
        self.__cache_size_lower: int = 0  # Resume normal behaviour once cache recovers after force flush

        # On 32 bit we only allow the user to set 1GB
        # For 64 bit we allow up to 4GB, in case somebody wants that
        self.__cache_upper_limit = GIGI
        if sabnzbd.MACOS or sabnzbd.WINDOWS or (struct.calcsize("P") * 8) == 64:
            self.__cache_upper_limit = 4 * GIGI

    def change_direct_write(self, direct_write: bool) -> None:
        self.__direct_write = direct_write

    def stop(self):
        self.shutdown = True
        with self.__cache_size_cv:
            self.__cache_size_cv.notify_all()

    def should_flush(self) -> bool:
        """
        Should we flush the cache?
        Only if direct write is supported and cache usage is over the upper limit.
        Or the downloader is paused and cache is not empty.
        """
        return (
            self.__direct_write
            and self.__cache_limit
            and (
                self.__cache_size > self.__cache_size_upper or self.__cache_size and sabnzbd.Downloader.no_active_jobs()
            )
            and time.monotonic() > self.__next_flush
        )

    def flush_cache(self) -> None:
        """In direct_write mode flush cache contents to file"""
        nzfs: set[NzbFile] = set()
        self.__next_flush = time.monotonic() + _SECONDS_BETWEEN_FLUSHES
        for article in self.__article_table.copy():
            if article.can_direct_write:
                nzfs.add(article.nzf)
        for nzf in nzfs:
            logging.debug("Forcing write of %s", nzf.filepath)
            sabnzbd.Assembler.process(nzf.nzo, nzf, force=True)

    def run(self):
        while True:
            with self.__cache_size_cv:
                self.__cache_size_cv.wait_for(
                    lambda: self.shutdown or self.should_flush(),
                    timeout=5.0,
                )
            if self.shutdown:
                break
            # Could be reached by timeout when paused and no further articles arrive
            with self.__cache_size_cv:
                if not self.should_flush():
                    continue
            self.flush_cache()

    def cache_info(self):
        return ANFO(len(self.__article_table), abs(self.__cache_size), self.__cache_limit)

    @synchronized(ARTICLE_COUNTER_LOCK)
    def new_limit(self, limit: int):
        """Called when cache limit changes"""
        self.__cache_limit_org = limit
        if limit < 0:
            self.__cache_limit = self.__cache_upper_limit
        else:
            self.__cache_limit = min(limit, self.__cache_upper_limit)
        self.__cache_size_upper = self.__cache_limit * ARTICLE_CACHE_UPPER_PERCENTAGE
        self.__cache_size_lower = self.__cache_limit * ARTICLE_CACHE_LOWER_PERCENTAGE
        if self.__cache_limit:
            logging.debug(
                "Article cache trigger upper:%s lower:%s",
                to_units(self.__cache_size_upper),
                to_units(self.__cache_size_lower),
            )

    @synchronized(ARTICLE_COUNTER_LOCK)
    def reserve_space(self, data_size: int) -> bool:
        """Reserve space in the cache"""
        if (usage := self.__cache_size + data_size) > self.__cache_limit:
            return False
        self.__cache_size = usage
        self.__cache_size_cv.notify_all()
        return True

    @synchronized(ARTICLE_COUNTER_LOCK)
    def free_reserved_space(self, data_size: int):
        """Remove previously reserved space"""
        self.__cache_size -= data_size
        self.__cache_size_cv.notify_all()

    @synchronized(ARTICLE_COUNTER_LOCK)
    def space_left(self) -> bool:
        """Is there space left in the set limit?"""
        return self.__cache_size < self.__cache_limit

    def save_article(self, article: Article, data: bytearray):
        """Save article in cache, either memory or disk"""
        nzo = article.nzf.nzo
        # Skip if already post-processing or fully finished
        if nzo.pp_or_finished:
            return

        # Register article for bookkeeping in case the job is deleted
        with nzo.lock:
            nzo.saved_articles.add(article)

        if article.lowest_partnum and not (article.nzf.import_finished or article.nzf.filename_checked):
            # Write the first-fetched articles to temporary file unless downloading
            # of the rest of the parts has started or filename is verified.
            # Otherwise the cache could overflow.
            self.__flush_article_to_disk(article, data)
            return

        # Check if we exceed the limit
        if self.__cache_limit and self.reserve_space(len(data)):
            # Add new article to the cache
            self.__article_table[article] = data
        else:
            # No data saved in memory, direct to disk
            self.__flush_article_to_disk(article, data)

    def load_article(self, article: Article) -> Optional[bytearray]:
        """Load the data of the article"""
        data: Optional[bytearray] = None
        nzo = article.nzf.nzo

        if article in self.__article_table:
            try:
                data = self.__article_table.pop(article)
                self.free_reserved_space(len(data))
            except KeyError:
                # Could fail due the article already being deleted by purge_articles, for example
                # when post-processing deletes the job while delayed articles still come in
                logging.debug("Failed to load %s from cache, probably already deleted", article)
                return data
        elif article.art_id:
            data = sabnzbd.filesystem.load_data(
                article.art_id, nzo.admin_path, remove=True, do_pickle=False, silent=True, mutable=True
            )
        with nzo.lock:
            nzo.saved_articles.discard(article)
        return data

    def flush_articles(self):
        logging.debug("Saving %s cached articles to disk", len(self.__article_table))
        self.__cache_size = 0
        while self.__article_table:
            try:
                article, data = self.__article_table.popitem()
                self.__flush_article_to_disk(article, data)
            except KeyError:
                # Could fail if already deleted by purge_articles or load_data
                logging.debug("Failed to flush item from cache, probably already deleted or written to disk")

    def purge_articles(self, articles: Collection[Article]):
        """Remove all saved articles, from memory and disk"""
        logging.debug("Purging %s articles from the cache/disk", len(articles))
        for article in articles:
            if article in self.__article_table:
                try:
                    data = self.__article_table.pop(article)
                    self.free_reserved_space(len(data))
                except KeyError:
                    # Could fail if already deleted by flush_articles or load_data
                    logging.debug("Failed to flush %s from cache, probably already deleted or written to disk", article)
            elif article.art_id:
                sabnzbd.filesystem.remove_data(article.art_id, article.nzf.nzo.admin_path)

    def __flush_article_to_disk(self, article: Article, data: bytearray):
        # Save data, but don't complain when destination folder is missing
        # because this flush may come after completion of the NZO.
        # Direct write to destination if cache is being used
        if self.__cache_limit and self.__direct_write and sabnzbd.Assembler.assemble_article(article, data):
            with article.nzf.nzo.lock:
                article.nzf.nzo.saved_articles.discard(article)
            self.flush_cache()
            return

        # Fallback to disk cache
        sabnzbd.filesystem.save_data(
            data, article.get_art_id(), article.nzf.nzo.admin_path, do_pickle=False, silent=True
        )
