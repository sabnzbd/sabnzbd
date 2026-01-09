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
sabnzbd.article - Article and TryList classes for NZB downloading
"""
import logging
import threading
from typing import Optional

import sabnzbd
from sabnzbd.downloader import Server
from sabnzbd.filesystem import get_new_id
from sabnzbd.decorators import synchronized


##############################################################################
# Trylist
##############################################################################


class TryList:
    """TryList keeps track of which servers have been tried for a specific article"""

    # Pre-define attributes to save memory
    __slots__ = ("try_list",)

    def __init__(self):
        # Sets are faster than lists
        self.try_list: set[Server] = set()

    @synchronized()
    def server_in_try_list(self, server: Server) -> bool:
        """Return whether specified server has been tried"""
        return server in self.try_list

    @synchronized()
    def all_servers_in_try_list(self, all_servers: set[Server]) -> bool:
        """Check if all servers have been tried"""
        return all_servers.issubset(self.try_list)

    @synchronized()
    def add_to_try_list(self, server: Server):
        """Register server as having been tried already"""
        # Sets cannot contain duplicate items
        self.try_list.add(server)

    @synchronized()
    def remove_from_try_list(self, server: Server):
        """Remove server from list of tried servers"""
        # Discard does not require the item to be present
        self.try_list.discard(server)

    @synchronized()
    def reset_try_list(self):
        """Clean the list"""
        self.try_list = set()

    def __getstate__(self):
        """Save the servers"""
        return set(server.id for server in self.try_list)

    def __setstate__(self, servers_ids: list[str]):
        self.try_list = set()
        for server in sabnzbd.Downloader.servers:
            if server.id in servers_ids:
                self.add_to_try_list(server)


##############################################################################
# Article
##############################################################################
ArticleSaver = (
    "article",
    "art_id",
    "bytes",
    "lowest_partnum",
    "decoded",
    "file_size",
    "data_begin",
    "data_size",
    "on_disk",
    "nzf",
    "crc32",
    "decoded_size",
)


class Article(TryList):
    """Representation of one article"""

    # Pre-define attributes to save memory
    __slots__ = ArticleSaver + ("fetcher", "fetcher_priority", "tries", "lock")

    def __init__(self, article, article_bytes, nzf):
        super().__init__()
        self.article: str = article
        self.art_id: Optional[str] = None
        self.bytes: int = article_bytes
        self.lowest_partnum: bool = False
        self.fetcher: Optional[Server] = None
        self.fetcher_priority: int = 0
        self.tries: int = 0  # Try count
        self.decoded: bool = False
        self.file_size: Optional[int] = None
        self.data_begin: Optional[int] = None
        self.data_size: Optional[int] = None
        self.decoded_size: Optional[int] = None  # Size of the decoded article
        self.on_disk: bool = False
        self.crc32: Optional[int] = None
        self.nzf = nzf  # NzbFile reference
        # Share NzbFile lock for file-wide atomicity of try-list ops
        self.lock = nzf.lock

    @synchronized()
    def reset_try_list(self):
        """In addition to resetting the try list, also reset fetcher so all servers
        are tried again. Locked so fetcher setting changes are also protected."""
        self.fetcher = None
        self.fetcher_priority = 0
        super().reset_try_list()

    @synchronized()
    def allow_new_fetcher(self, remove_fetcher_from_try_list: bool = True):
        """Let article get new fetcher and reset try lists of file and job.
        Locked so all resets are performed at once"""
        if remove_fetcher_from_try_list:
            self.remove_from_try_list(self.fetcher)
        self.fetcher = None
        self.tries = 0
        self.nzf.reset_try_list()
        self.nzf.nzo.reset_try_list()

    def get_article(self, server: Server, servers: list[Server]):
        """Return article when appropriate for specified server"""
        if self.fetcher or self.server_in_try_list(server):
            return None

        if server.priority > self.fetcher_priority:
            # Check for higher priority server, taking advantage of servers list being sorted by priority
            for server_check in servers:
                if server_check.priority < server.priority:
                    if server_check.active and not self.server_in_try_list(server_check):
                        # There is a higher priority server, so set article priority and return
                        self.fetcher_priority = server_check.priority
                        return None
                else:
                    # All servers with a higher priority have been checked
                    break

        # If no higher priority servers, use this server
        self.fetcher_priority = server.priority
        self.fetcher = server
        self.tries += 1
        return self

    def get_art_id(self):
        """Return unique article storage name, create if needed"""
        if not self.art_id:
            self.art_id = get_new_id("article", self.nzf.nzo.admin_path)
        return self.art_id

    def search_new_server(self):
        """Search for a new server for this article"""
        # Since we need a new server, this one can be listed as failed
        sabnzbd.BPSMeter.register_server_article_failed(self.fetcher.id)
        self.add_to_try_list(self.fetcher)
        # Servers-list could be modified during iteration, so we need a copy
        for server in sabnzbd.Downloader.servers[:]:
            if server.active and not self.server_in_try_list(server):
                if server.priority >= self.fetcher.priority:
                    self.tries = 0
                    # Allow all servers for this nzo and nzf again (but not this fetcher for this article)
                    self.allow_new_fetcher(remove_fetcher_from_try_list=False)
                    return True

        logging.info("Article %s unavailable on all servers, discarding", self.article)
        return False

    @property
    def can_direct_write(self) -> bool:
        return bool(
            self.data_size  # decoder sets data_size to 0 when offsets or file_size are outside allowed range
            and self.nzf.type == "yenc"
            and self.nzf.prepare_filepath()
        )

    def __getstate__(self):
        """Save to pickle file, selecting attributes"""
        dict_ = {}
        for item in ArticleSaver:
            dict_[item] = getattr(self, item)
        dict_["try_list"] = super().__getstate__()
        return dict_

    def __setstate__(self, dict_):
        """Load from pickle file, selecting attributes"""
        for item in ArticleSaver:
            try:
                setattr(self, item, dict_[item])
            except KeyError:
                # Handle new attributes
                setattr(self, item, None)
        self.lock = threading.RLock()
        super().__setstate__(dict_.get("try_list", []))
        self.fetcher = None
        self.fetcher_priority = 0
        self.tries = 0

    def __repr__(self):
        return "<Article: article=%s, bytes=%s, art_id=%s>" % (self.article, self.bytes, self.art_id)
