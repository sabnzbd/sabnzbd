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
sabnzbd.utils.ssdp - Support for SSDP / Simple Service Discovery Protocol plus XML to appear on Windows
"""
import logging
import time
import socket
import uuid
from threading import Thread
from typing import Optional


class SSDP(Thread):
    def __init__(self, host, server_name, url, description):
        self.__host = host  # Note: this is the LAN IP address!
        self.__server_name = server_name
        self.__url = url
        self.__description = description
        self.__myhostname = socket.gethostname()
        # uuid stays the same as long as hostname and ip address stay the same:
        self.__uuidXML = uuid.uuid3(uuid.NAMESPACE_DNS, self.__myhostname + self.__host)
        self.__uuidSSDP = uuid.uuid3(uuid.NAMESPACE_DNS, self.__host + self.__myhostname)

        self.__stop = False
        super().__init__()

    def stop(self):
        logging.info("Stopping SSDP")
        self.__stop = True

    def run(self):
        logging.info("Serving SSDP on %s as %s", self.__host, self.__server_name)
        logging.info("self.__url is %s", self.__url)

        descriptionxmlURL = self.__url + "/description.xml"

        # the standard multicast settings for SSDP:
        MCAST_GRP = "239.255.255.250"
        MCAST_PORT = 1900
        MULTICAST_TTL = 2

        mySSDPbroadcast = f"""NOTIFY * HTTP/1.1
HOST: 239.255.255.250:1900
CACHE-CONTROL: max-age=60
LOCATION: {descriptionxmlURL}
SERVER: SABnzbd
NT: upnp:rootdevice
USN: uuid:{self.__uuidSSDP}::upnp:rootdevice
NTS: ssdp:alive
OPT: "http://schemas.upnp.org/upnp/1/0/"; ns=01

"""

        mySSDPbroadcast = mySSDPbroadcast.replace("\n", "\r\n")
        mySSDPbroadcast = bytes(mySSDPbroadcast, "utf-8")  # convert string to bytes

        while 1 and not self.__stop:
            # Do network stuff
            # Use self.__host, self.__url, self.__server_name to do stuff!

            # Create socket, send the broadcast, and close the socket again
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
                # logging.debug("Sending a SSDP multicast with size %s", len(mySSDPbroadcast))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
                sock.sendto(mySSDPbroadcast, (MCAST_GRP, MCAST_PORT))
            time.sleep(5)

    def serve_xml(self):
        """Returns an XML-structure based on the information being
        served by this service, returns nothing if not running"""
        if self.__stop:
            return
        # Use self.__host, self.__url, self.__server_name to do stuff!

        # Create the XML info
        myxml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>{self.__url}</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>SABnzbd ({self.__myhostname})</friendlyName>
<manufacturer>SABnzbd Team</manufacturer>
<manufacturerURL>http://www.sabnzbd.org</manufacturerURL>
<modelDescription>SABnzbd downloader</modelDescription>
<modelURL>http://www.sabnzbd.org</modelURL>
<UDN>uuid:{self.__uuidXML}</UDN>
<presentationURL>sabnzbd</presentationURL>
</device>
</root>"""

        return myxml
        # return f"<xml><name>{self.__server_name}</name><url>{self.__url}</url></xml>"


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
