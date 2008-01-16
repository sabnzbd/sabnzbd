#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#           2007 The ShyPike <shypike@users.sourceforge.net>
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
sabnzbd.rss - rss client functionality
"""

__NAME__ = "RSS"


import os
import re
import logging
import sabnzbd

from sabnzbd.decorators import *
from threading import RLock

try:
    import feedparser
    HAVE_FEEDPARSER = True
except ImportError:
    HAVE_FEEDPARSER = False

LOCK = RLock()
class RSSQueue:
    def __init__(self, uris= [], uri_table = {}, old_entries = {}):
        self.uris = uris
        self.uri_table = uri_table
        self.old_entries = old_entries

    @synchronized(LOCK)
    def run(self):
        for uri in self.uris:
            filter_list, filter_table = self.uri_table[uri]

            logging.info("[%s] Parsing %s", __NAME__, uri)
            d = feedparser.parse(uri)
            logging.info("[%s] Done parsing %s", __NAME__, uri)
            logging.debug("[%s] PARSE RESULT %s", __NAME__, d)

            if not d or not d['entries'] or 'bozo_exception' in d:
                continue

            entries = d['entries']

            new = not uri in self.old_entries

            entry_links = []
            new_entry_links = []
            for entry in entries:
                try:
                    link = entry['link']
                    link.index('http')
                except:
                    link = entry['guid']

                if link.find('http') >= 0:
                    entry_links.append(link)
                    if new or link not in self.old_entries[uri]:
                        new_entry_links.append(link)

            logging.debug("[%s] new: %s", __NAME__, new)
            logging.debug("[%s] entry_links: %s", __NAME__, entry_links)
            logging.debug("[%s] new_entry_links: %s", __NAME__,
                          new_entry_links)

            self.old_entries[uri] = entry_links

            if new or not new_entry_links:
                continue

            for _filter in filter_list[:]:
                filter_name, unpack_opts, match_multiple, filter_matcher = _filter

                matched_links = filter_table[filter_name]

                logging.debug("[%s] %s matched_links: %s", __NAME__,
                              filter_name, matched_links)

                for link in matched_links[:]:
                    if link not in entry_links:
                        matched_links.remove(link)
                        logging.debug("[%s] Purged link (%s) removed",
                                      __NAME__, link)

                for entry in entries:
                    try:
                        link = entry['link']
                        link.index('http')
                    except:
                        link = entry['guid']

                    if (link.find('http') < 0) or (link not in new_entry_links):
                        continue

                    title = entry['title'].lower()

                    found_match = True
                    if filter_matcher:
                        found_match = re.search(filter_matcher, title)
                    elif filter_name != '*':
                        for match_part in filter_name.split():
                            match_part = match_part.lower()
                            if match_part not in title:
                                found_match = False
                                break

                    if found_match and link not in matched_links:
                        matched_links.append(link)

                        _id = link_to_id(link)
                        if _id:
                            logging.info("[%s] Adding %s (%s) to queue",
                                         __NAME__, _id, title)
                            sabnzbd.add_msgid(_id, unpack_opts)
                        else:
                            logging.info("[%s] Adding %s (%s) to queue",
                                         __NAME__, link, title)
                            sabnzbd.add_url(link, unpack_opts)

                        if not match_multiple:
                            filter_list.remove(_filter)
                            break

        self.save()

    @synchronized(LOCK)
    def add_feed(self, uri, text_filter, re_filter, unpack_opts, match_multiple):
        if uri not in self.uris:
            self.uris.append(uri)
            self.uri_table[uri] = [[], {}]

        filter_list, filter_table = self.uri_table[uri]
        filter_name = text_filter
        filter_matcher = None
        if re_filter:
            filter_name = re_filter
            try:
                filter_matcher = re.compile(filter_name, re.I)
            except:
                logging.exception("[%s] Error compiling %s", __NAME__,
                                  filter_name)
                filter_name = None

        if filter_name:
            filter_table[filter_name] = []
            filter_list.append([filter_name, unpack_opts, match_multiple,
                                filter_matcher])
            self.run()

        elif not filter_list:
            self.uris.remove(uri)
            self.uri_table.pop(uri)

    @synchronized(LOCK)
    def del_feed(self, uri_id):
        for uri in self.uris:
            if uri_id == str(id(uri)):
                self.uris.remove(uri)
                self.uri_table.pop(uri)
                if uri in self.old_entries:
                    self.old_entries.pop(uri)
                self.save()
                break

    @synchronized(LOCK)
    def del_filter(self, uri_id, filter_id):
        for uri in self.uris:
            if uri_id == str(id(uri)):
                filter_list, filter_table = self.uri_table[uri]

                save = False
                for _filter in filter_list[:]:
                    if filter_id == str(id(_filter)):
                        filter_name, unpack_opts, match_multiple, filter_matcher = _filter
                        filter_list.remove(_filter)
                        filter_table.pop(filter_name)
                        save = True
                if save:
                    self.save()
                break

    @synchronized(LOCK)
    def get_info(self):
        return ([uri for uri in self.uris], self.uri_table.copy())

    @synchronized(LOCK)
    def save(self):
        sabnzbd.save_data((self.uris, self.uri_table, self.old_entries),
                          sabnzbd.RSS_FILE_NAME)

def link_to_id(link):
    _id = None

    link = link.lower()

    if 'newzbin' in link or 'newzxxx' in link:
        if link[-1] == '/':
            _id = int(os.path.basename(link[:-1]))
        else:
            _id = int(os.path.basename(link))

    return _id
