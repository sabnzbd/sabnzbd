#!/usr/bin/python3 -OO
# Copyright 2009-2021 The SABnzbd-Team <team@sabnzbd.org>
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
https://tools.ietf.org/html/draft-cai-ssdp-v1-03

XML:
UPnP™ Device Architecture 1.1, paragraph 2.3 Device description
http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf


"""
import logging
import time
import socket
import uuid
from threading import Thread
from typing import Optional

import socket, os


def codelength(s):
    """ returns the given string/bytes as bytes, prepended with the 7-bit-encoded length (which might be >1 bytes)"""
    # We want bytes as input
    if not isinstance(s, bytes):
        # Not bytes. Let's try to convert to bytes, but only plain ASCII
        try:
            s = str.encode(s, "ascii")
        except:
            s = b""
    l = len(s)
    if l == 0:
        return b"\x00"
    encodedlen = (l & 0x7F).to_bytes(1, "little")
    while l > 0x7F:
        l = l >> 7
        c = (l & 0x7F) | 0x80
        encodedlen = c.to_bytes(1, "little") + encodedlen
    return encodedlen + s


def submit_to_minissdpd(st, usn, server, url, sockpath="/var/run/minissdpd.sock"):
    """ submits the specified service to MiniSSDPD (if running)"""
    """
    ST = Search Target of the service that is responding.
        Example: "urn:schemas-upnp-org:device:InternetGatewayDevice:1"
    USN = The unique service name to identify the service.
        Example: "uuid:73616d61-6a6b-7a74-650a-0d24d4a5d636::urn:schemas-upnp-org:device:InternetGatewayDevice:1"
    SERVER = The server system information (SERVER) value providing information in the following format: [OS-Name] UPnP/[Version] [Product-Name]/[Product-Version]
        Example: "MyServer/0.0"
    URL = The URL location to allow the control point to gain more information about this service.
        Example: "http://192.168.0.1:1234/rootDesc.xml"
    """
    # First check if sockpath exists i.e. MiniSSDPD is running
    if not os.path.exists(sockpath):
        return -1, f"Error: {sockpath} does not exist. Is minissdpd running?"
    # OK, submit
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(sockpath)
        sock.send(b"\x04" + codelength(st) + codelength(usn) + codelength(server) + codelength(url))
    except socket.error as msg:
        print(msg)
        return -1, msg
    finally:
        sock.close()
    return 0, "OK"


class SSDP(Thread):
    def __init__(self, host, server_name, url, description, manufacturer, manufacturer_url, model, **kwargs):
        self.__host = host  # Note: this is the LAN IP address!
        self.__server_name = server_name
        self.__url = url
        self.__description = description
        self.__manufacturer = manufacturer
        self.__manufacturer_url = manufacturer_url
        self.__model = model
        self.__ssdp_broadcast_interval = kwargs.get("ssdp_broadcast_interval", 15)  # optional, default 15 seconds

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

        # Create the XML info (description.xml)
        self.__myxml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>{self.__url}</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>{self.__server_name} ({self.__myhostname})</friendlyName>
<manufacturer>{self.__manufacturer}</manufacturer>
<manufacturerURL>{self.__manufacturer_url}</manufacturerURL>
<modelDescription>{self.__model} </modelDescription>
<modelName>{self.__model}</modelName>
<modelNumber> </modelNumber>
<modelDescription>{self.__description}</modelDescription>
<modelURL>{self.__manufacturer_url}</modelURL>
<UDN>uuid:{self.__uuid}</UDN>
<presentationURL>{self.__url}</presentationURL>
</device>
</root>"""

        self.__stop = False
        super().__init__()

    def stop(self):
        logging.info("Stopping SSDP")
        self.__stop = True

    def run(self):
        logging.info("Serving SSDP on %s as %s", self.__host, self.__server_name)
        # logging.info("self.__url is %s", self.__url)

        logging.info("Trying if miniSSDPd is there")
        rc, message = submit_to_minissdpd(
            b"urn:schemas-upnp-org:device:InternetGatewayDevice:1",
            "uuid:" + str(self.__uuid) + "::upnp:rootdevice",
            self.__server_name,
            self.__url + "/description.xml",
        )
        if rc == 0:
            logging.info("miniSSDPd OK: submitting to MiniSSDPD went OK")
        else:
            logging.info("miniSSDPd not there")
            logging.debug("miniSSDPd Not OK. Error message is: %s", message)

        # the standard multicast settings for SSDP:
        MCAST_GRP = "239.255.255.250"
        MCAST_PORT = 1900
        MULTICAST_TTL = 2

        if rc == 0:
            # TODO is this necessary to keep the class alive? Or can we leave this out?
            logging.info("We have miniSSPDd running, so no SSDP broadcasts sending needed")
            while True and not self.__stop:
                time.sleep(20)
        else:
            logging.info("Start sending SSDP broadcasts")
            while 1 and not self.__stop:
                # Do network stuff
                # Use self.__host, self.__url, self.__server_name to do stuff!

                # Create socket, send the broadcast, and close the socket again
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
                        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
                        sock.sendto(self.__mySSDPbroadcast, (MCAST_GRP, MCAST_PORT))
                except:
                    # probably no network
                    pass
                time.sleep(self.__ssdp_broadcast_interval)

    def serve_xml(self):
        """Returns an XML-structure based on the information being
        served by this service, returns nothing if not running"""
        if self.__stop:
            return
        # Use self.__host, self.__url, self.__server_name to do stuff!

        return self.__myxml


# Reserve class variable, to be started later
__SSDP: Optional[SSDP] = None


# Wrapper functions to be called by program
def start_ssdp(*args, **kwargs):
    global __SSDP
    __SSDP = SSDP(*args, **kwargs)
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
