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
tests.test_nzbarticle - Testing functions in nzbarticle.py
"""

import gc
import os
import weakref
from random import randint
from unittest import mock

from sabnzbd.nzb import Article, TryList


class Server:
    def __init__(self, host, priority, active):
        self.host = host
        self.priority = priority
        self.active = active


class TestArticle:
    def test_get_article(self):
        article_id = "test@host" + os.urandom(8).hex() + ".sab"
        mock_nzf = mock.Mock()
        article = Article(article_id, randint(4321, 54321), mock_nzf)
        servers = []
        servers.append(Server("testserver1", 10, True))
        servers.append(Server("testserver2", 20, True))
        servers.append(Server("testserver3", 30, True))

        # Test fetching top priority server
        server = servers[0]
        assert article.get_article(server, servers) == article
        assert article.fetcher_priority == 10
        assert article.fetcher == server
        assert article.get_article(server, servers) is None
        article.fetcher = None
        article.add_to_try_list(server)
        assert article.get_article(server, servers) is None

        # Test fetching when there is a higher priority server available
        server = servers[2]
        assert article.fetcher_priority == 10
        assert article.get_article(server, servers) is None
        assert article.fetcher_priority == 20

        # Server should be used even if article.fetcher_priority is a higher number than server.priority
        article.fetcher_priority = 30
        server = servers[1]
        assert article.get_article(server, servers) == article

        # Inactive servers in servers list should be ignored
        article.fetcher = None
        article.fetcher_priority = 0
        servers[1].active = False
        server = servers[2]
        assert article.get_article(server, servers) == article
        assert article.tries == 3

    def test_untried_article_has_no_set(self):
        article = Article("test@host.sab", 1234, mock.MagicMock())
        server = Server("testserver1", 0, True)
        assert not isinstance(article.try_list, set)
        article.remove_from_try_list(server)
        article.add_to_try_list(server)
        assert article.server_in_try_list(server)
        article.reset_try_list()
        assert not article.server_in_try_list(server)
        assert not isinstance(article.try_list, set)

    def test_equal_try_lists_are_shared(self):
        server1, server2 = Server("testserver1", 0, True), Server("testserver2", 0, True)
        first, second, untried = (Article("test@host%d.sab" % i, 1234, mock.MagicMock()) for i in range(3))
        first.add_to_try_list(server1)
        second.add_to_try_list(server1)
        assert first.try_list is second.try_list

        # Adding twice changes nothing
        first.add_to_try_list(server1)
        assert first.try_list is second.try_list

        # The order in which servers were added does not matter
        first.add_to_try_list(server2)
        second.add_to_try_list(server2)
        assert first.try_list == {server1, server2}
        assert first.try_list is second.try_list
        second.reset_try_list()
        second.add_to_try_list(server2)
        second.add_to_try_list(server1)
        assert first.try_list is second.try_list

        # Removing goes back to the shared lists, down to the empty one
        first.remove_from_try_list(server2)
        assert first.try_list == {server1}
        assert first.try_list is not second.try_list
        first.remove_from_try_list(server1)
        assert first.try_list is untried.try_list
        assert second.try_list == {server1, server2}

    def test_shared_try_lists_do_not_keep_servers_alive(self):
        """The shared lists are weak, so a replaced Server is freed once no article refers to it"""
        server = Server("testserver1", 0, True)
        server_ref = weakref.ref(server)
        first, second = (Article("test@host%d.sab" % i, 1234, mock.MagicMock()) for i in range(2))
        first.add_to_try_list(server)
        second.add_to_try_list(server)
        key = (server,)
        assert key in TryList._shared_try_lists
        del server, key

        # Still in use, so it stays shared and alive
        first.reset_try_list()
        gc.collect()
        assert server_ref() is not None
        assert second.server_in_try_list(server_ref())

        # Unused, so the entry and the server are gone
        second.reset_try_list()
        gc.collect()
        assert server_ref() is None
        assert not any(isinstance(server, Server) for key in TryList._shared_try_lists for server in key)

    def test_empty_try_list_state(self):
        article = Article("test@host.sab", 1234, mock.MagicMock())
        assert not article.__getstate__()["try_list"]
