#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
from typing import Dict, Collection

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import GIGI, ANFO, ASSEMBLER_WRITE_THRESHOLD
from sabnzbd.nzbstuff import Article

# Operations on the article table are handled via try/except.
# The counters need to be made atomic to ensure consistency.
ARTICLE_COUNTER_LOCK = threading.RLock()


class ArticleCache:
    def __init__(self):
        self.__cache_limit_org = 0
        self.__cache_limit = 0
        self.__cache_size = 0
        self.__article_table: Dict[Article, bytes] = {}  # Dict of buffered articles

        self.assembler_write_trigger: int = 1

        # On 32 bit we only allow the user to set 1GB
        # For 64 bit we allow up to 4GB, in case somebody wants that
        self.__cache_upper_limit = GIGI
        if sabnzbd.MACOS or sabnzbd.WIN64 or (struct.calcsize("P") * 8) == 64:
            self.__cache_upper_limit = 4 * GIGI

    def cache_info(self):
        return ANFO(len(self.__article_table), abs(self.__cache_size), self.__cache_limit_org)

    def new_limit(self, limit: int):
        """Called when cache limit changes"""
        self.__cache_limit_org = limit
        if limit < 0:
            self.__cache_limit = self.__cache_upper_limit
        else:
            self.__cache_limit = min(limit, self.__cache_upper_limit)

        # Set assembler_write_trigger to be the equivalent of ASSEMBLER_WRITE_THRESHOLD %
        # of the total cache, assuming an article size of 750 000 bytes
        self.assembler_write_trigger = int(self.__cache_limit * ASSEMBLER_WRITE_THRESHOLD / 100 / 750_000) + 1

        logging.debug(
            "Assembler trigger = %d",
            self.assembler_write_trigger,
        )

    @synchronized(ARTICLE_COUNTER_LOCK)
    def reserve_space(self, data_size: int):
        """Reserve space in the cache"""
        self.__cache_size += data_size

    @synchronized(ARTICLE_COUNTER_LOCK)
    def free_reserved_space(self, data_size: int):
        """Remove previously reserved space"""
        self.__cache_size -= data_size

    def space_left(self) -> bool:
        """Is there space left in the set limit?"""
        return self.__cache_size < self.__cache_limit

    def save_article(self, article: Article, data: bytes):
        """Save article in cache, either memory or disk"""
        nzo = article.nzf.nzo
        # Skip if already post-processing or fully finished
        if nzo.pp_or_finished:
            return

        # Register article for bookkeeping in case the job is deleted
        nzo.saved_articles.add(article)

        if article.lowest_partnum and not (article.nzf.import_finished or article.nzf.filename_checked):
            # Write the first-fetched articles to temporary file unless downloading
            # of the rest of the parts has started or filename is verified.
            # Otherwise the cache could overflow.
            self.__flush_article_to_disk(article, data)
            return

        if self.__cache_limit:
            # Check if we exceed the limit
            data_size = len(data)
            self.reserve_space(data_size)
            if self.space_left():
                # Add new article to the cache
                self.__article_table[article] = data
            else:
                # Return the space and save to disk
                self.free_reserved_space(data_size)
                self.__flush_article_to_disk(article, data)
        else:
            # No data saved in memory, direct to disk
            self.__flush_article_to_disk(article, data)

    def load_article(self, article: Article):
        """Load the data of the article"""
        data = None
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
                article.art_id, nzo.admin_path, remove=True, do_pickle=False, silent=True
            )
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

    @staticmethod
    def __flush_article_to_disk(article: Article, data):
        # Save data, but don't complain when destination folder is missing
        # because this flush may come after completion of the NZO.
        sabnzbd.filesystem.save_data(
            data, article.get_art_id(), article.nzf.nzo.admin_path, do_pickle=False, silent=True
        )
