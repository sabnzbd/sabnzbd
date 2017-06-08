#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.trylist - trylist class
"""

import logging
from threading import Lock

import sabnzbd
from sabnzbd.decorators import synchronized

# TryList keeps track of which servers have been tried for a specific article
# This used to have a Lock, but it's not needed (all atomic) and faster without

class TryList(object):
    # Pre-define attributes to save memory
    __slots__ = ('__try_list', 'fetcher_priority')

    def __init__(self):
        self.__try_list = []
        self.fetcher_priority = 0

    def server_in_try_list(self, server):
        """ Return whether specified server has been tried """
        return server in self.__try_list

    def add_to_try_list(self, server):
        """ Register server as having been tried already """
        self.__try_list.append(server)

    def reset_try_list(self):
        """ Clean the list """
        self.__try_list = []
        self.fetcher_priority = 0
