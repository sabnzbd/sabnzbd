#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
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

__NAME__ = "articlecache"

import logging
import sabnzbd


from threading import Lock

from sabnzbd.decorators import *

ARTICLE_LOCK = Lock()
class ArticleCache:
    def __init__(self, cache_limit = 0):
        self.__cache_limit = cache_limit
        self.__cache_size = 0
        
        self.__article_list = []    # List of buffered articles
        self.__article_table = {}   # Dict of buffered articles
        
    @synchronized(ARTICLE_LOCK)
    def cache_info(self):
        return (len(self.__article_list), self.__cache_size, self.__cache_limit)
        
    @synchronized(ARTICLE_LOCK)
    def save_article(self, article, data):
        nzf = article.nzf
        nzo = nzf.nzo
        
        if nzf.deleted or nzo.deleted:
            logging.debug("[%s] %s discarded", __NAME__, article)
            return
        
        saved_articles = article.nzf.nzo.saved_articles
        
        if article not in saved_articles:
            saved_articles.append(article)
            
        if self.__cache_limit:
            if self.__cache_limit < 0:
                self.__add_to_cache(article, data)
                
            else:
                data_size = len(data)
                
                while (self.__cache_size > (self.__cache_limit - data_size)) \
                and self.__article_list:
                    ## Flush oldest article in cache
                    old_article = self.__article_list.pop(0)
                    old_data = self.__article_table.pop(old_article)
                    self.__cache_size -= len(old_data)
                    ## No need to flush if this is a refreshment article
                    if old_article != article:
                        self.__flush_article(old_article, old_data)
                    
                ## Does our article fit into our limit now?
                if (self.__cache_size + data_size) <= self.__cache_limit:
                    self.__add_to_cache(article, data)
                else:
                    self.__flush_article(article, data)
                    
        else:
            self.__flush_article(article, data)
            
    @synchronized(ARTICLE_LOCK)
    def load_article(self, article):
        data = None
        
        if article in self.__article_list:
            data = self.__article_table.pop(article)
            self.__article_list.remove(article)
            self.__cache_size -= len(data)
            logging.info("[%s] Loaded %s from cache", __NAME__, article)
            logging.debug("[%s] cache_size -> %s", __NAME__, self.__cache_size)
        elif article.art_id:
            data = sabnzbd.load_data(article.art_id, remove = True, 
                                     do_pickle = False)
            
        nzo = article.nzf.nzo
        if article in nzo.saved_articles:
            nzo.saved_articles.remove(article)
            
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
        logging.debug("[%s] Purgable articles -> %s", __NAME__, articles)
        for article in articles:
            if article in self.__article_list:
                self.__article_list.remove(article)
                data = self.__article_table.pop(article)
                self.__cache_size -= len(data)
            if article.art_id:
                sabnzbd.remove_data(article.art_id)
                
    def __flush_article(self, article, data):
        nzf = article.nzf
        nzo = nzf.nzo
        
        if nzf.deleted or nzo.deleted:
            logging.debug("[%s] %s discarded", __NAME__, article)
            return
            
        art_id = article.get_art_id()
        if art_id:
            logging.info("[%s] Flushing %s to disk", __NAME__, article)
            logging.debug("[%s] cache_size -> %s", __NAME__, self.__cache_size)
            sabnzbd.save_data(data, art_id, do_pickle = False, doze=sabnzbd.DEBUG_DELAY)
        else:
            logging.warning("[%s] Flushing %s failed -> no art_id", 
                            __NAME__, article)
        
    def __add_to_cache(self, article, data):
        if article in self.__article_table:
            self.__cache_size -= len(self.__article_table[article])
        else:
            self.__article_list.append(article)
            
        self.__article_table[article] = data
        self.__cache_size += len(data)
        logging.info("[%s] Added %s to cache", __NAME__, article)
        logging.debug("[%s] cache_size -> %s", __NAME__, self.__cache_size)
        
