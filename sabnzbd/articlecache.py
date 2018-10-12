#!/usr/bin/python3 -OO
# Copyright 2007-2018 The SABnzbd-Team <team@sabnzbd.org>
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

import sys
import logging
import threading
import struct

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import GIGI, ANFO


ARTICLE_LOCK = threading.Lock()


class ArticleCache(object):
    do = None

    def __init__(self):
        self.__cache_limit_org = 0
        self.__cache_limit = 0
        self.__cache_size = 0
        self.__article_list = []    # List of buffered articles
        self.__article_table = {}   # Dict of buffered articles

        # On 32 bit we only allow the user to set 1GB
        # For 64 bit we allow up to 4GB, in case somebody wants that
        self.__cache_upper_limit = GIGI
        if sabnzbd.DARWIN or sabnzbd.WIN64 or (struct.calcsize("P") * 8) == 64:
            self.__cache_upper_limit = 4*GIGI

        ArticleCache.do = self

    @synchronized(ARTICLE_LOCK)
    def cache_info(self):
        return ANFO(len(self.__article_list), abs(self.__cache_size), self.__cache_limit_org)

    @synchronized(ARTICLE_LOCK)
    def new_limit(self, limit):
        """ Called when cache limit changes """
        self.__cache_limit_org = limit
        if limit < 0:
            self.__cache_limit = self.__cache_upper_limit
        else:
            self.__cache_limit = min(limit, self.__cache_upper_limit)

    @synchronized(ARTICLE_LOCK)
    def reserve_space(self, data):
        """ Is there space left in the set limit? """
        data_size = sys.getsizeof(data) * 64
        self.__cache_size += data_size
        if self.__cache_size + data_size > self.__cache_limit:
            return False
        else:
            return True

    @synchronized(ARTICLE_LOCK)
    def free_reserve_space(self, data):
        """ Remove previously reserved space """
        data_size = sys.getsizeof(data) * 64
        self.__cache_size -= data_size
        return self.__cache_size + data_size < self.__cache_limit

    @synchronized(ARTICLE_LOCK)
    def save_article(self, article, data):
        if article.nzf.nzo.is_gone():
            # Do not discard this article because the
            # file might still be processed at this moment!!
            return

        # Register article
        if article not in article.nzf.nzo.saved_articles:
            article.nzf.nzo.saved_articles.append(article)

        if article.lowest_partnum and not article.nzf.import_finished:
            # Write the first-fetched articles to disk
            # Otherwise the cache could overflow
            self.__flush_article(article, data)
            return

        if self.__cache_limit:
            if self.__cache_limit < 0:
                self.__add_to_cache(article, data)
            else:
                data_size = len(data)

                while (self.__cache_size > (self.__cache_limit - data_size)) \
                        and self.__article_list:
                    # Flush oldest article in cache
                    old_article = self.__article_list.pop(0)
                    old_data = self.__article_table.pop(old_article)
                    self.__cache_size -= len(old_data)
                    # No need to flush if this is a refreshment article
                    if old_article != article:
                        self.__flush_article(old_article, old_data)

                # Does our article fit into our limit now?
                if (self.__cache_size + data_size) <= self.__cache_limit:
                    self.__add_to_cache(article, data)
                else:
                    self.__flush_article(article, data)

        else:
            self.__flush_article(article, data)

    @synchronized(ARTICLE_LOCK)
    def load_article(self, article):
        data = None
        nzo = article.nzf.nzo

        if article in self.__article_list:
            data = self.__article_table.pop(article)
            self.__article_list.remove(article)
            self.__cache_size -= len(data)
        elif article.art_id:
            data = sabnzbd.load_data(article.art_id, nzo.workpath, remove=True,
                                     do_pickle=False, silent=True)

        if article in nzo.saved_articles:
            nzo.remove_saved_article(article)

        return data

    @synchronized(ARTICLE_LOCK)
    def flush_articles(self):
        self.__cache_size = 0
        while self.__article_list:
            article = self.__article_list.pop(0)
            data = self.__article_table.pop(article)
            self.__flush_article(article, data)

    @synchronized(ARTICLE_LOCK)
    def purge_articles(self, articles):
        for article in articles:
            if article in self.__article_list:
                self.__article_list.remove(article)
                data = self.__article_table.pop(article)
                self.__cache_size -= len(data)
            if article.art_id:
                sabnzbd.remove_data(article.art_id, article.nzf.nzo.workpath)

    def __flush_article(self, article, data):
        nzf = article.nzf
        nzo = nzf.nzo

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

    def __add_to_cache(self, article, data):
        if article in self.__article_table:
            self.__cache_size -= len(self.__article_table[article])
        else:
            self.__article_list.append(article)
        self.__article_table[article] = data
        self.__cache_size += len(data)


# Create the instance
ArticleCache()
