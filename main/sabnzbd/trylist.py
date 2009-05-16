#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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

from sabnzbd.decorators import synchronized

from threading import Lock

# TryList keeps track of which servers have been tried for
# a specific article

TRYLIST_LOCK = Lock()
class TryList:
    def __init__(self):
        self.__try_list = []

    @synchronized(TRYLIST_LOCK)
    def server_in_try_list(self, server):
        """ Return whether specified server has been tried """
        return (server in self.__try_list)

    @synchronized(TRYLIST_LOCK)
    def add_to_try_list(self, server):
        """ Register server as having been tried already """
        if server not in self.__try_list:
            logging.debug("Appending %s to %s.__try_list", server, self)
            self.__try_list.append(server)

    @synchronized(TRYLIST_LOCK)
    def remove_from_try_list(self, server):
        """ Server is no longer listed as tried """
        if server in self.__try_list:
            logging.debug("Removing %s from %s.__try_list",  server, self)
            self.__try_list.remove(server)

    @synchronized(TRYLIST_LOCK)
    def reset_try_list(self):
        """ Clean the list """
        if self.__try_list:
            logging.debug("Reseting %s.__try_list", self)
            self.__try_list = []
