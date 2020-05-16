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
sabnzbd.articlecache - Article cache handling
"""

import logging
import threading
import struct

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import GIGI, ANFO, MEBI, LIMIT_DECODE_QUEUE, MIN_DECODE_QUEUE

# Operations on lists and dicts are atomic, but for
# the bytes counter we do need a lock
ARTICLE_LOCK = threading.Lock()


class ArticleCache:
    do = None

    def __init__(self):
        self.__cache_limit_org = 0
        self.__cache_limit = 0
        self.__cache_size = 0
        self.__article_list = []    # List of buffered articles
        self.__article_table = {}   # Dict of buffered articles

        # Limit for the decoder is based on the total available cache
        # so it can be larger on memory-rich systems
        self.decoder_cache_article_limit = 0

        # On 32 bit we only allow the user to set 1GB
        # For 64 bit we allow up to 4GB, in case somebody wants that
        self.__cache_upper_limit = GIGI
        if sabnzbd.DARWIN or sabnzbd.WIN64 or (struct.calcsize("P") * 8) == 64:
            self.__cache_upper_limit = 4*GIGI

        ArticleCache.do = self

    def cache_info(self):
        return ANFO(len(self.__article_list), abs(self.__cache_size), self.__cache_limit_org)

    def new_limit(self, limit):
        """ Called when cache limit changes """
        self.__cache_limit_org = limit
        if limit < 0:
            self.__cache_limit = self.__cache_upper_limit
        else:
            self.__cache_limit = min(limit, self.__cache_upper_limit)

        # The decoder-limit should not be larger than 1/3th of the whole cache
        # Calculated in number of articles, assuming 1 article = 1MB max
        decoder_cache_limit = int(min(self.__cache_limit/3/MEBI, LIMIT_DECODE_QUEUE))
        # The cache should also not be too small
        self.decoder_cache_article_limit = max(decoder_cache_limit, MIN_DECODE_QUEUE)

    @synchronized(ARTICLE_LOCK)
    def reserve_space(self, data_size):
        """ Reserve space in the cache """
        self.__cache_size += data_size

    @synchronized(ARTICLE_LOCK)
    def free_reserved_space(self, data_size):
        """ Remove previously reserved space """
        self.__cache_size -= data_size

    def space_left(self):
        """ Is there space left in the set limit? """
        return self.__cache_size < self.__cache_limit

    def save_article(self, article, data):
        """ Save article in cache, either memory or disk """
        nzo = article.nzf.nzo
        if nzo.is_gone():
            # Do not discard this article because the
            # file might still be processed at this moment!!
            return

        # Register article for bookkeeping in case the job is deleted
        nzo.add_saved_article(article)

        if article.lowest_partnum and not article.nzf.import_finished:
            # Write the first-fetched articles to disk
            # Otherwise the cache could overflow
            self.__flush_article_to_disk(article, data)
            return

        if self.__cache_limit:
            # Check if we exceed the limit
            data_size = len(data)
            self.reserve_space(data_size)
            if self.space_left():
                # Add new article to the cache
                self.__article_list.append(article)
                self.__article_table[article] = data
            else:
                # Return the space and save to disk
                self.free_reserved_space(data_size)
                self.__flush_article_to_disk(article, data)
        else:
            # No data saved in memory, direct to disk
            self.__flush_article_to_disk(article, data)

    def load_article(self, article):
        """ Load the data of the article """
        data = None
        nzo = article.nzf.nzo

        if article in self.__article_list:
            data = self.__article_table.pop(article)
            self.__article_list.remove(article)
            self.free_reserved_space(len(data))
        elif article.art_id:
            data = sabnzbd.load_data(article.art_id, nzo.workpath, remove=True,
                                     do_pickle=False, silent=True)
        nzo.remove_saved_article(article)

        return data

    @synchronized(ARTICLE_LOCK)
    def flush_articles(self):
        self.__cache_size = 0
        while self.__article_list:
            article = self.__article_list.pop(0)
            data = self.__article_table.pop(article)
            self.__flush_article_to_disk(article, data)

    def purge_articles(self, articles):
        """ Remove all saved articles, from memory and disk """
        for article in articles:
            if article in self.__article_list:
                self.__article_list.remove(article)
                data = self.__article_table.pop(article)
                self.free_reserved_space(len(data))
            if article.art_id:
                sabnzbd.remove_data(article.art_id, article.nzf.nzo.workpath)

    def __flush_article_to_disk(self, article, data):
        nzo = article.nzf.nzo
        if nzo.is_gone():
            # Do not discard this article because the
            # file might still be processed at this moment!!
            return

        art_id = article.get_art_id()
        if art_id:
            # Save data, but don't complain when destination folder is missing
            # because this flush may come after completion of the NZO.
            sabnzbd.save_data(data, art_id, nzo.workpath, do_pickle=False, silent=True)
        else:
            logging.warning("Flushing %s failed -> no art_id", article)


# Create the instance
ArticleCache()
