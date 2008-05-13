#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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

__NAME__ = "trylist"

import logging

from sabnzbd.decorators import *

from threading import Lock

TRYLIST_LOCK = Lock()
class TryList:
    def __init__(self):
        self.__try_list = []
        
    @synchronized(TRYLIST_LOCK)
    def server_in_try_list(self, server):
        return (server in self.__try_list)
    
    @synchronized(TRYLIST_LOCK)
    def add_to_try_list(self, server):
        if server not in self.__try_list:
            logging.debug("[%s] Appending %s to %s.__try_list",
                          __NAME__, server, self)
            self.__try_list.append(server)
            
    @synchronized(TRYLIST_LOCK)
    def remove_from_try_list(self, server):
        if server in self.__try_list:
            logging.debug("[%s] Removing %s from %s.__try_list", 
                          __NAME__, server, self)
            self.__try_list.remove(server)
            
    @synchronized(TRYLIST_LOCK)
    def reset_try_list(self):
        if self.__try_list:
            logging.debug("[%s] Reseting %s.__try_list", 
                          __NAME__, self)
            self.__try_list = []
