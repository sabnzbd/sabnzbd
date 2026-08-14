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
sabnzbd.utils.ssdp - Support for SSDP / Simple Service Discovery Protocol plus XML to appear on Windows

Method:
1) this service sends a SSDP broadcast with a description.xml URL in it
2) Windows retrieves that description.xml from this service
3) Windows presents the info from the XML in Windows Exporter's Network

Based on the following Specs:

SSDP:
Never standardized as an RFC; the original IETF draft has expired but is kept for reference.
https://tools.ietf.org/html/draft-cai-ssdp-v1-03
SSDP is now specified as part of the UPnP Device Architecture documents (see below).

XML:
UPnP(tm) Device Architecture, paragraph 2.3 Device description.
The latest revision is 2.0, but a Basic:1 device still uses the device-1-0 schema
(urn:schemas-upnp-org:device-1-0), which is what Windows expects for discovery.
UPnP is now stewarded by the Open Connectivity Foundation (OCF); the upnp.org spec
links redirect through openconnectivity.org.
https://openconnectivity.org/developer/specifications/upnp-resources/upnp/


"""

import logging
import socket
import uuid
from threading import Thread, Condition, Lock
from typing import Optional
from xml.sax.saxutils import escape


class SSDP(Thread):
    def __init__(
        self,
        host: str,
        server_name: str,
        url: str,
        description: str,
        manufacturer: str,
        manufacturer_url: str,
        model: str,
        ssdp_broadcast_interval: int = 15,
    ):
        self.__host = host  # Note: this is the LAN IP address!
        self.__server_name = server_name
        self.__url = url
        self.__description = description
        self.__manufacturer = manufacturer
        self.__manufacturer_url = manufacturer_url
        self.__model = model
        self.__ssdp_broadcast_interval = ssdp_broadcast_interval

        self.__myhostname = socket.gethostname()
        # a steady uuid: stays the same as long as hostname and ip address stay the same:
        self.__uuid = uuid.uuid3(uuid.NAMESPACE_DNS, self.__myhostname + self.__host)

        # Create the SSDP broadcast message
        self.__mySSDPbroadcast = f"""NOTIFY * HTTP/1.1
HOST: 239.255.255.250:1900
CACHE-CONTROL: max-age=60
LOCATION: {self.__url}/description.xml
SERVER: {self.__server_name}
NT: upnp:rootdevice
USN: uuid:{self.__uuid}::upnp:rootdevice
NTS: ssdp:alive
OPT: "http://schemas.upnp.org/upnp/1/0/"; ns=01

"""
        self.__mySSDPbroadcast = self.__mySSDPbroadcast.replace("\n", "\r\n").encode("utf-8")

        # Create the XML info (description.xml). Escape all interpolated values so
        # characters like & < > (common in URLs) cannot break the XML structure.
        self.__myxml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>{escape(self.__url)}</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>{escape(self.__server_name)} ({escape(self.__myhostname)})</friendlyName>
<manufacturer>{escape(self.__manufacturer)}</manufacturer>
<manufacturerURL>{escape(self.__manufacturer_url)}</manufacturerURL>
<modelName>{escape(self.__model)}</modelName>
<modelNumber> </modelNumber>
<modelDescription>{escape(self.__description)}</modelDescription>
<modelURL>{escape(self.__manufacturer_url)}</modelURL>
<UDN>uuid:{self.__uuid}</UDN>
<presentationURL>{escape(self.__url)}</presentationURL>
</device>
</root>"""

        self.__stop = False
        self.__condition = Condition(Lock())
        super().__init__()

    def stop(self):
        logging.info("Stopping SSDP")
        self.__stop = True
        with self.__condition:
            self.__condition.notify()

    def run(self):
        logging.info("Serving SSDP on %s as %s", self.__host, self.__server_name)

        # the standard multicast settings for SSDP:
        MCAST_GRP = "239.255.255.250"
        MCAST_PORT = 1900
        MULTICAST_TTL = 2

        while not self.__stop:
            # Do network stuff
            # Create socket, send the broadcast, and close the socket again
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
                    sock.sendto(self.__mySSDPbroadcast, (MCAST_GRP, MCAST_PORT))
            except Exception:
                # probably no network
                logging.debug("Failed to send SSDP broadcast", exc_info=True)

            # Wait until awoken or timeout is up
            with self.__condition:
                self.__condition.wait(self.__ssdp_broadcast_interval)

    def serve_xml(self) -> str:
        """Returns an XML-structure based on the information being
        served by this service, returns empty if not running"""
        if self.__stop:
            return ""
        return self.__myxml


# Module-level singleton, started/stopped via the functions below
_SSDP: Optional[SSDP] = None


# Wrapper functions to be called by program; they own the singleton and its lifecycle guards
def start_ssdp(
    host: str,
    server_name: str,
    url: str,
    description: str,
    manufacturer: str,
    manufacturer_url: str,
    model: str,
    ssdp_broadcast_interval: int = 15,
):
    global _SSDP
    _SSDP = SSDP(host, server_name, url, description, manufacturer, manufacturer_url, model, ssdp_broadcast_interval)
    _SSDP.start()


def stop_ssdp():
    if _SSDP and _SSDP.is_alive():
        _SSDP.stop()
        _SSDP.join()


def server_ssdp_xml() -> str:
    """Returns the description.xml if the server is alive, empty otherwise"""
    if _SSDP and _SSDP.is_alive():
        return _SSDP.serve_xml()
    return ""
