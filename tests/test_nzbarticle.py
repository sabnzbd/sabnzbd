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
tests.test_nzbarticle - Testing functions in nzbarticle.py
"""

from sabnzbd.nzb import Article

from tests.testhelper import *


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
        assert article.get_article(server, servers) == None
        article.fetcher = None
        article.add_to_try_list(server)
        assert article.get_article(server, servers) == None

        # Test fetching when there is a higher priority server available
        server = servers[2]
        assert article.fetcher_priority == 10
        assert article.get_article(server, servers) == None
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
