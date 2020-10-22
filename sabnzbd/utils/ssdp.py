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
import socket
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
        logging.info("self.__url is %s", self.__url)

        # warning ... hack ahead ... to be solved
        # self.__url is http://192.168.1.101:8080/sabnzbd
        # convert into
        # descriptionxmlURL is http://192.168.1.101:8080/description.xml
        import string
        descriptionxmlURL = self.__url.replace('sabnzbd', 'description.xml')
        logging.info("descriptionxmlURL is", descriptionxmlURL)
        # /hack

        import uuid
        myuuid = uuid.uuid1()

        # the standard multicast settings for SSDP:
        MCAST_GRP = '239.255.255.250'
        MCAST_PORT = 1900
        MULTICAST_TTL = 2

        # Assuming we put the socket stuff here ... or in the loop?
        #sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        #sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)

        #mySSDPbroadcast = b'NOTIFY * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nCACHE-CONTROL: max-age=60\r\nLOCATION: http://192.168.1.101:8080/description.xml\r\nSERVER: SABnzbd\r\nNT: upnp:rootdevice\r\nUSN: uuid:11105501-bf96-4bdf-a60f-382e39a0f84c::upnp:rootdevice\r\nNTS: ssdp:alive\r\nOPT: "http://schemas.upnp.org/upnp/1/0/"; ns=01\r\n01-NLS: 1600778333\r\nBOOTID.UPNP.ORG: 1600778333\r\nCONFIGID.UPNP.ORG: 1337\r\n\r\n'
        mySSDPbroadcast = f"""NOTIFY * HTTP/1.1
HOST: 239.255.255.250:1900
CACHE-CONTROL: max-age=60
LOCATION: {descriptionxmlURL}
SERVER: SABnzbd
NT: upnp:rootdevice
USN: uuid:{myuuid}::upnp:rootdevice
NTS: ssdp:alive
OPT: "http://schemas.upnp.org/upnp/1/0/"; ns=01
01-NLS: 1600778333
BOOTID.UPNP.ORG: 1600778333
CONFIGID.UPNP.ORG: 1337

"""
        mySSDPbroadcast = mySSDPbroadcast.replace("\n", "\r\n")
        mySSDPbroadcast = bytes(mySSDPbroadcast, 'utf-8') # convert string to bytes

        while 1 and not self.__stop:
            # Do network stuff
            # Use self.__host, self.__url, self.__server_name to do stuff!

            # create socket, send broadcast, and close it again
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
                #logging.debug("Sending a SSDP multicast with size %s", len(mySSDPbroadcast))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
                sock.sendto(mySSDPbroadcast, (MCAST_GRP, MCAST_PORT))
            time.sleep(2)

    def serve_xml(self):
        """Returns an XML-structure based on the information being
        served by this service, returns nothing if not running"""
        if self.__stop:
            return
        # Use self.__host, self.__url, self.__server_name to do stuff!
        logging.debug("description.xml was retrieved by ...")

        #sabnameversion = _SSDP__description

        import uuid
        myuuid = uuid.uuid1()



        myxml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>{self.__url}</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>SABnzbd ({self.__host})</friendlyName>
<manufacturer>SABnzbd Team</manufacturer>
<manufacturerURL>http://www.sabnzbd.org</manufacturerURL>
<modelDescription>SABnzbd downloader</modelDescription>
<modelName>SABnzbd 3.4.5</modelName>
<modelNumber>model xyz</modelNumber>
<modelURL>http://www.sabnzbd.org</modelURL>
<serialNumber>001788721333</serialNumber>
<UDN>uuid:{myuuid}</UDN>
<presentationURL>sabnzbd</presentationURL>
<iconList>
<icon>
<mimetype>image/png</mimetype>
<height>48</height>
<width>48</width>
<depth>24</depth>
<url>hue_logo_0.png</url>
</icon>
</iconList>
</device>
</root>"""

        return myxml
        #return f"<xml><name>{self.__server_name}</name><url>{self.__url}</url></xml>"


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
