#!/usr/bin/python3 -OO
# Copyright 2009-2020 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.utils.ssdp - Support for SSDP / Simple Service Discovery Protocol
"""
import logging
import time
from threading import Thread
from typing import Optional


class SSDP(Thread):
    def __init__(self, host, server_name, url, description):
        self.__host = host
        self.__server_name = server_name
        self.__url = url
        self.__description = description
        self.__stop = False
        super().__init__()

    def stop(self):
        logging.info("Stopping SSDP")
        self.__stop = True

    def run(self):
        logging.info("Serving SSDP on %s as %s", self.__host, self.__server_name)
        while 1 and not self.__stop:
            # Do network stuff
            # Use self.__host, self.__url, self.__server_name to do stuff!
            time.sleep(1)

    def serve_xml(self):
        """Returns an XML-structure based on the information being
        served by this service, returns nothing if not running"""
        if self.__stop:
            return
        # Use self.__host, self.__url, self.__server_name to do stuff!
        return f"<xml><name>{self.__server_name}</name><url>{self.__url}</url></xml>"


# Reserve class variable, to be started later
__SSDP: Optional[SSDP] = None


# Wrapper functions to be called by program
def start_ssdp(host, server_name, url, description):
    global __SSDP
    __SSDP = SSDP(host, server_name, url, description)
    __SSDP.start()


def stop_ssdp():
    if __SSDP and __SSDP.is_alive():
        __SSDP.stop()
        __SSDP.join()


def server_ssdp_xml():
    """Returns the description.xml if the server is alive, empty otherwise"""
    if __SSDP and __SSDP.is_alive():
        return __SSDP.serve_xml()
    return ""
