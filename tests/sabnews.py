#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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
tests.sabnews - Fake newsserver to use in end-to-end testing

Run sabnews.py -h for parameters!

"""

import argparse
import asyncio
import logging
import os
import re
import time

from random import randint

import sabyenc3

logging.getLogger().setLevel(logging.INFO)


# Expecting the following message-id:
# ARTICLE <file=folder/filename.mkv|part=4|start=5000|size=5000>\r\n
ARTICLE_INFO = re.compile(
    b"^(ARTICLE|BODY) (?P<message_id><file=(?P<file>.*)\|part=(?P<part>\d+)\|start=(?P<start>\d+)\|size=(?P<size>\d+)>)\\r\\n$",
    re.MULTILINE,
)
YENC_ESCAPE = [0x00, 0x0A, 0x0D, ord("="), ord(".")]


class NewsServerProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self.connected = False
        self.in_article = False
        super().__init__()

    def connection_made(self, transport):
        logging.info("Connection from %s", transport.get_extra_info("peername"))
        self.transport = transport
        self.connected = True
        self.transport.write(b"200 Welcome (SABNews)\r\n")

    def data_received(self, message):
        logging.debug("Data received: %s", message.strip())

        # Handle basic commands
        if message.startswith(b"QUIT"):
            self.close_connection()
        elif message.startswith((b"ARTICLE", b"BODY")):
            parsed_message = ARTICLE_INFO.search(message)
            self.serve_article(parsed_message)

        # self.transport.write(data)

    def serve_article(self, parsed_message):
        # Check if we parsed everything
        try:
            message_id = parsed_message.group("message_id")
            file = parsed_message.group("file").decode("utf-8")
            file_base = os.path.basename(file)
            part = int(parsed_message.group("part"))
            start = int(parsed_message.group("start"))
            size = int(parsed_message.group("size"))
        except (AttributeError, ValueError):
            logging.warning("Can't parse article information")
            self.transport.write(b"430 No Such Article Found (bad message-id)\r\n")
            return

        # Check if file exists
        if not os.path.exists(file):
            logging.warning("File not found: %s", file)
            self.transport.write(b"430 No Such Article Found (no file on disk)\r\n")
            return

        # Check if sizes are valid
        file_size = os.path.getsize(file)
        if start + size > file_size:
            logging.warning("Invalid start/size attributes")
            self.transport.write(b"430 No Such Article Found (invalid start/size attributes)\r\n")
            return

        logging.debug("Serving %s" % message_id)

        # File is found, send headers
        self.transport.write(b"222 0 %s\r\n" % message_id)
        self.transport.write(b"Message-ID: %s\r\n" % message_id)
        self.transport.write(b'Subject: "%s"\r\n\r\n' % file_base.encode("utf-8"))

        # Write yEnc headers
        self.transport.write(
            b"=ybegin part=%d line=128 size=%d name=%s\r\n" % (part, file_size, file_base.encode("utf-8"))
        )
        self.transport.write(b"=ypart begin=%d end=%d\r\n" % (start + 1, start + size))

        with open(file, "rb") as inp_file:
            inp_file.seek(start)
            inp_buffer = inp_file.read(size)

        # Encode data
        output_string, crc = sabyenc3.encode(inp_buffer)
        self.transport.write(output_string)

        # Write footer
        self.transport.write(b"\r\n=yend size=%d part=%d pcrc32=%08x\r\n" % (size, part, crc))
        self.transport.write(b".\r\n")

    def close_connection(self):
        logging.debug("Closing connection")
        self.transport.write(b"205 Connection closing\r\n")
        self.transport.close()


async def serve_sabnews(hostname, port):
    # Start server
    logging.info("Starting SABNews on %s:%d", hostname, port)

    # Needed for Python 3.5 support!
    loop = asyncio.get_event_loop()
    server = await loop.create_server(lambda: NewsServerProtocol(), hostname, port)
    return server


def create_nzb(nzb_file=None, nzb_dir=None):
    article_size = 500000
    files_for_nzb = []
    output_file = ""

    # Either use directory or single file
    if nzb_dir:
        if not os.path.exists(nzb_dir) or not os.path.isdir(nzb_dir):
            raise NotADirectoryError("%s is not a valid directory" % nzb_dir)

        # List all files
        files_for_nzb = [os.path.join(nzb_dir, fl) for fl in os.listdir(nzb_dir)]
        files_for_nzb = [fl for fl in files_for_nzb if os.path.isfile(fl)]
        output_file = os.path.join(nzb_dir, os.path.basename(os.path.normpath(nzb_dir)) + ".nzb")

    if nzb_file:
        if not os.path.exists(nzb_file) or not os.path.isfile(nzb_file):
            raise FileNotFoundError("Cannot find %s or it is not a file" % nzb_file)
        files_for_nzb = [nzb_file]
        output_file = os.path.splitext(nzb_file)[0] + ".nzb"

    if not files_for_nzb:
        raise RuntimeError("No files found to include in NZB")

    # Let's write a file!
    with open(output_file, "w", encoding="utf-8") as nzb:
        nzb.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        nzb.write('<!DOCTYPE nzb PUBLIC "-//newzBin//DTD NZB 1.0//EN" "http://www.newzbin.com/DTD/nzb/nzb-1.0.dtd">\n')
        nzb.write('<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">\n')

        nzb_time = time.time() - randint(0, int(time.time() - 746863566))

        for fl in files_for_nzb:
            nzb.write(
                '<file poster="SABNews" date="%d" subject="&quot;%s&quot;">\n' % (nzb_time, os.path.basename(fl))
            )
            nzb.write("<groups><group>alt.binaries.test</group></groups>\n")
            nzb.write("<segments>\n")

            # Create segments
            file_size = os.path.getsize(fl)
            for seg_nr, seg_start in enumerate(range(0, file_size, article_size), 1):
                segement_size = min(article_size, file_size - seg_start)
                nzb.write(
                    '<segment number="%d" bytes="%d">file=%s|part=%s|start=%d|size=%d</segment>\n'
                    % (seg_nr, segement_size, fl, seg_nr, seg_start, segement_size)
                )
            nzb.write("</segments>\n")
            nzb.write("</file>\n")
        nzb.write("</nzb>\n")

    logging.info("NZB saved to %s" % output_file)
    return output_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", help="Hostname", dest="hostname", default="127.0.0.1")
    parser.add_argument("-p", help="Port", dest="port", type=int, default=8888)
    parser.add_argument("--nzbfile", help="Create NZB of specified file", dest="nzb_file", metavar="FILE")
    parser.add_argument("--nzbdir", help="Create NZB for files in specified directory", dest="nzb_dir", metavar="DIR")

    args = parser.parse_args()

    # Serve if we are not creating NZB's
    if not args.nzb_file and not args.nzb_dir:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(serve_sabnews(args.hostname, args.port))
        loop.run_forever()
    else:
        create_nzb(args.nzb_file, args.nzb_dir)


if __name__ == "__main__":
    main()
