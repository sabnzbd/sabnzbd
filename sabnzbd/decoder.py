#!/usr/bin/python -OO
# Copyright 2008-2010 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.decoder - article decoder
"""

import Queue
import binascii
import logging
import re
from threading import Thread
try:
    import _yenc
    HAVE_YENC = True

except ImportError:
    HAVE_YENC = False

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.articlecache import ArticleCache
import sabnzbd.downloader
import sabnzbd.cfg as cfg
import sabnzbd.nzbqueue
from sabnzbd.codecs import name_fixer
from sabnzbd.lang import Ta

#-------------------------------------------------------------------------------

class CrcError(Exception):
    def __init__(self, needcrc, gotcrc, data):
        Exception.__init__(self)
        self.needcrc = needcrc
        self.gotcrc = gotcrc
        self.data = data

class BadYenc(Exception):
    def __init__(self):
        Exception.__init__(self)

#-------------------------------------------------------------------------------

class Decoder(Thread):
    def __init__(self, servers):
        Thread.__init__(self)

        self.queue = Queue.Queue()
        self.servers = servers

    def decode(self, article, lines):
        self.queue.put((article, lines))
        if self.queue.qsize() > MAX_DECODE_QUEUE:
            sabnzbd.downloader.delay_downloader()

    def stop(self):
        self.queue.put(None)

    def run(self):
        while 1:
            art_tup = self.queue.get()
            if not art_tup:
                break

            if self.queue.qsize() < MIN_DECODE_QUEUE and sabnzbd.downloader.delayed():
                sabnzbd.downloader.undelay_downloader()

            article, lines = art_tup
            nzf = article.nzf
            nzo = nzf.nzo

            data = None

            register = True

            if lines:
                try:
                    logging.info("Decoding %s", article)

                    data = decode(article, lines)
                    nzf.increase_article_count()
                except IOError, e:
                    logging.error(Ta('error-decode@1'), article)
                    sabnzbd.downloader.pause_downloader()

                    article.fetcher = None

                    sabnzbd.nzbqueue.reset_try_lists(nzf, nzo)

                    register = False

                except CrcError, e:
                    logging.warning(Ta('warn-crcError@3'), article, e.needcrc, e.gotcrc)

                    data = e.data

                    if cfg.fail_on_crc():
                        new_server_found = self.__search_new_server(article)
                        if new_server_found:
                            register = False

                except BadYenc, e:
                    logging.warning("Badly formed yEnc article in %s", article)

                    if cfg.fail_on_crc():
                        new_server_found = self.__search_new_server(article)
                        if new_server_found:
                            register = False

                except:
                    logging.error(Ta('error-decodeUnknown@1'), article)

            else:
                new_server_found = self.__search_new_server(article)
                if new_server_found:
                    register = False

            if data:
                ArticleCache.do.save_article(article, data)

            if register:
                sabnzbd.nzbqueue.register_article(article)

    def __search_new_server(self, article):
        article.add_to_try_list(article.fetcher)

        nzf = article.nzf
        nzo = nzf.nzo

        new_server_found = False
        fill_server_found = False

        for server in self.servers:
            if server.active and not article.server_in_try_list(server):
                if server.fillserver:
                    fill_server_found = True
                else:
                    new_server_found = True
                    break

        # Only found one (or more) fill server(s)
        if not new_server_found and fill_server_found:
            article.allow_fill_server = True
            new_server_found = True

        if new_server_found:
            article.fetcher = None

            ## Allow all servers to iterate over this nzo and nzf again ##
            sabnzbd.nzbqueue.reset_try_lists(nzf, nzo)

            logging.info('%s => found at least one untested server', article)

        else:
            logging.warning(Ta('warn-artAllMissing@1'), article)

        return new_server_found
#-------------------------------------------------------------------------------

YDEC_TRANS = ''.join([chr((i + 256 - 42) % 256) for i in xrange(256)])
def decode(article, data):
    data = strip(data)
    ## No point in continuing if we don't have any data left
    if data:
        nzf = article.nzf
        nzo = nzf.nzo
        yenc, data = yCheck(data)
        ybegin, ypart, yend = yenc
        decoded_data = None

        #Deal with non-yencoded posts
        if not ybegin:
            found = False
            for i in xrange(10):
                if data[i].startswith('begin '):
                    nzf.set_filename(name_fixer(data[i].split(None, 2)[2]))
                    nzf.set_type('uu')
                    found = True
                    break
            if found:
                for n in xrange(i):
                    data.pop(0)
            if data[-1] == 'end':
                data.pop()
                if data[-1] == '`':
                    data.pop()

            decoded_data = '\r\n'.join(data)

        #Deal with yenc encoded posts
        elif (ybegin and yend):
            if 'name' in ybegin:
                nzf.set_filename(name_fixer(ybegin['name']))
            else:
                logging.debug("Possible corrupt header detected " + \
                              "=> ybegin: %s", ybegin)
            nzf.set_type('yenc')
            # Decode data
            if HAVE_YENC:
                decoded_data, crc = _yenc.decode_string(''.join(data))[:2]
                partcrc = '%08X' % ((crc ^ -1) & 2**32L - 1)
            else:
                data = ''.join(data)
                for i in (0, 9, 10, 13, 27, 32, 46, 61):
                    j = '=%c' % (i + 64)
                    data = data.replace(j, chr(i))
                decoded_data = data.translate(YDEC_TRANS)
                crc = binascii.crc32(decoded_data)
                partcrc = '%08X' % (crc & 2**32L - 1)

            if ypart:
                crcname = 'pcrc32'
            else:
                crcname = 'crc32'

            if crcname in yend:
                _partcrc = '0' * (8 - len(yend[crcname])) + yend[crcname].upper()
            else:
                _partcrc = None
                logging.debug("Corrupt header detected " + \
                              "=> yend: %s", yend)

            if not (_partcrc == partcrc):
                raise CrcError(_partcrc, partcrc, decoded_data)
        else:
            raise BadYenc()

        return decoded_data

def yCheck(data):
    ybegin = None
    ypart = None
    yend = None

    ## Check head
    for i in xrange(10):
        try:
            if data[i].startswith('=ybegin '):
                splits = 3
                if data[i].find(' part=') > 0:
                    splits += 1
                if data[i].find(' total=') > 0:
                    splits += 1

                ybegin = ySplit(data[i], splits)

                if data[i+1].startswith('=ypart '):
                    ypart = ySplit(data[i+1])
                    data = data[i+2:]
                    break
                else:
                    data = data[i+1:]
                    break
        except IndexError:
            break

    ## Check tail
    for i in xrange(-1, -11, -1):
        try:
            if data[i].startswith('=yend '):
                yend = ySplit(data[i])
                data = data[:i]
                break
        except IndexError:
            break

    return ((ybegin, ypart, yend), data)

# Example: =ybegin part=1 line=128 size=123 name=-=DUMMY=- abc.par
YSPLIT_RE = re.compile(r'([a-zA-Z0-9]+)=')
def ySplit(line, splits = None):
    fields = {}

    if splits:
        parts = YSPLIT_RE.split(line, splits)[1:]
    else:
        parts = YSPLIT_RE.split(line)[1:]

    if len(parts) % 2:
        return fields

    for i in range(0, len(parts), 2):
        key, value = parts[i], parts[i+1]
        fields[key] = value.strip()

    return fields

def strip(data):
    while data and not data[0]:
        data.pop(0)

    while data and not data[-1]:
        data.pop()

    for i in xrange(len(data)):
        if data[i][:2] == '..':
            data[i] = data[i][1:]
    return data
