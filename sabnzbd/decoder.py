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
sabnzbd.decoder - article decoder
"""

import Queue
import binascii
import logging
import re
from time import sleep
from threading import Thread

import sabnzbd
from sabnzbd.constants import Status, MAX_DECODE_QUEUE, LIMIT_DECODE_QUEUE, SABYENC_VERSION
from sabnzbd.articlecache import ArticleCache
import sabnzbd.downloader
import sabnzbd.cfg as cfg
from sabnzbd.encoding import yenc_name_fixer
from sabnzbd.misc import match_str

try:
    import _yenc
    HAVE_YENC = True
except ImportError:
    HAVE_YENC = False

try:
    import sabyenc
    HAVE_SABYENC = True
    # Verify version
    if sabyenc.__version__ != SABYENC_VERSION:
        raise ImportError
except ImportError:
    HAVE_SABYENC = False
if not cfg.enable_sabyenc():
    HAVE_SABYENC = False

class CrcError(Exception):

    def __init__(self, needcrc, gotcrc, data):
        Exception.__init__(self)
        self.needcrc = needcrc
        self.gotcrc = gotcrc
        self.data = data


class BadYenc(Exception):

    def __init__(self):
        Exception.__init__(self)


class Decoder(Thread):

    def __init__(self, servers, queue, dec_nr):
        Thread.__init__(self)

        self.queue = queue
        self.servers = servers
        self.shutdown = False
        self.dec_nr = dec_nr

    def stop(self):
        # Put multiple to stop all decoders
        self.queue.put(None)
        self.queue.put(None)

    def run(self):
        from sabnzbd.nzbqueue import NzbQueue
        while 1:
            # Sleep to allow decoder/assembler switching
            sleep(0.0001)
            art_tup = self.queue.get()
            if not art_tup:
                break

            article, lines, raw_data = art_tup
            nzf = article.nzf
            nzo = nzf.nzo
            art_id = article.article
            killed = False

            # Check if the space that's now free can let us continue the queue?
            qsize = self.queue.qsize()
            if (ArticleCache.do.free_reserve_space(lines) or qsize < MAX_DECODE_QUEUE) and (qsize < LIMIT_DECODE_QUEUE) and sabnzbd.downloader.Downloader.do.delayed:
                sabnzbd.downloader.Downloader.do.undelay()

            data = None
            register = True  # Finish article
            found = False    # Proper article found
            logme = None

            if lines or raw_data:
                try:
                    if nzo.precheck:
                        raise BadYenc
                    register = True
                    logging.debug("%d - Decoding %s", self.dec_nr, art_id)

                    data = decode(article, lines, raw_data)
                    nzf.article_count += 1
                    found = True

                except IOError, e:
                    logme = T('Decoding %s failed') % art_id
                    logging.warning(logme)
                    logging.info("Traceback: ", exc_info=True)

                    sabnzbd.downloader.Downloader.do.pause()
                    article.fetcher = None
                    NzbQueue.do.reset_try_lists(nzf, nzo)
                    register = False

                except MemoryError, e:
                    logme = T('Decoder failure: Out of memory')
                    logging.warning(logme)
                    anfo = sabnzbd.articlecache.ArticleCache.do.cache_info()
                    logging.info("Decoder-Queue: %d, Cache: %d, %d, %d", self.queue.qsize(), anfo.article_sum, anfo.cache_size, anfo.cache_limit)
                    logging.info("Traceback: ", exc_info=True)

                    sabnzbd.downloader.Downloader.do.pause()
                    article.fetcher = None
                    NzbQueue.do.reset_try_lists(nzf, nzo)
                    register = False

                except CrcError, e:
                    logme = T('CRC Error in %s (%s -> %s)') % (art_id, e.needcrc, e.gotcrc)
                    logging.info(logme)

                    data = e.data

                except BadYenc:
                    # Handles precheck and badly formed articles
                    killed = False
                    found = False
                    data_to_check = lines or raw_data
                    if nzo.precheck and data_to_check and data_to_check[0].startswith('223 '):
                        # STAT was used, so we only get a status code
                        found = True
                    else:
                        # Examine headers (for precheck) or body (for download)
                        # And look for DMCA clues (while skipping "X-" headers)
                        for line in data_to_check:
                            lline = line.lower()
                            if 'message-id:' in lline:
                                found = True
                            if not line.startswith('X-') and match_str(lline, ('dmca', 'removed', 'cancel', 'blocked')):
                                killed = True
                                break
                    if killed:
                        logme = 'Article removed from server (%s)'
                        logging.info(logme, art_id)
                    if nzo.precheck:
                        if found and not killed:
                            # Pre-check, proper article found, just register
                            logging.debug('Server has article %s', art_id)
                            register = True
                    elif not killed and not found:
                        logme = T('Badly formed yEnc article in %s') % art_id
                        logging.info(logme)

                    if not found or killed:
                        new_server_found = self.__search_new_server(article)
                        if new_server_found:
                            register = False
                            logme = None

                except:
                    logme = T('Unknown Error while decoding %s') % art_id
                    logging.error(logme)
                    logging.info("Traceback: ", exc_info=True)
                    new_server_found = self.__search_new_server(article)
                    if new_server_found:
                        register = False
                        logme = None

                if logme:
                    if killed:
                        nzo.inc_log('killed_art_log', art_id)
                    else:
                        nzo.inc_log('bad_art_log', art_id)

            else:
                new_server_found = self.__search_new_server(article)
                if new_server_found:
                    register = False
                elif nzo.precheck:
                    found = False

            if logme or not found:
                # Add extra parfiles when there was a damaged article
                if cfg.prospective_par_download() and nzo.extrapars:
                    nzo.prospective_add(nzf)

            if data:
                ArticleCache.do.save_article(article, data)

            if register:
                NzbQueue.do.register_article(article, found)

    def __search_new_server(self, article):
        from sabnzbd.nzbqueue import NzbQueue
        article.add_to_try_list(article.fetcher)

        nzf = article.nzf
        nzo = nzf.nzo

        new_server_found = False
        fill_server_found = False

        for server in self.servers:
            if server.active and not article.server_in_try_list(server):
                if not sabnzbd.highest_server(server):
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
            article.tries = 0

            # Allow all servers to iterate over this nzo and nzf again
            NzbQueue.do.reset_try_lists(nzf, nzo)

            if sabnzbd.LOG_ALL:
                logging.debug('%s => found at least one untested server', article)

        else:
            msg = T('%s => missing from all servers, discarding') % article
            logging.info(msg)
            article.nzf.nzo.inc_log('missing_art_log', msg)

        return new_server_found


YDEC_TRANS = ''.join([chr((i + 256 - 42) % 256) for i in xrange(256)])
def decode(article, data, raw_data):
    # Do we have SABYenc? Let it do all the work
    if HAVE_SABYENC:
        # Bam
        decoded_data, output_filename, crc, crc_yenc, crc_correct = sabyenc.decode_usenet_chunks(raw_data, article.bytes)
        #decoded_data, output_filename, crc, crc_yenc, crc_correct = sabyenc.decode_string_usenet(''.join(raw_data))

        # Assume it is yenc
        article.nzf.type = 'yenc'

        # CRC check
        if not crc_correct:
            crc_yenc = '%08X' % (crc_yenc & 2 ** 32L - 1)
            crc = '%08X' % (crc & 2 ** 32L - 1)
            raise CrcError(crc_yenc, crc, decoded_data)

        # Only set the name if it was found
        if output_filename:
            article.nzf.filename = output_filename

        return decoded_data

    # Filter out empty ones
    data = filter(None, data)
    # No point in continuing if we don't have any data left
    if data:
        nzf = article.nzf
        yenc, data = yCheck(data)
        ybegin, ypart, yend = yenc
        decoded_data = None

        # Deal with non-yencoded posts
        if not ybegin:
            found = False
            try:
                for i in xrange(min(40, len(data))):
                    if data[i].startswith('begin '):
                        nzf.type = 'uu'
                        found = True
                        # Pause the job and show warning
                        if nzf.nzo.status != Status.PAUSED:
                            nzf.nzo.pause()
                            msg = T('UUencode detected, only yEnc encoding is supported [%s]') % nzf.nzo.final_name
                            logging.warning(msg)
                        break
            except IndexError:
                raise BadYenc()

            if found:
                decoded_data = ''
            else:
                raise BadYenc()

        # Deal with yenc encoded posts
        elif ybegin and yend:
            if 'name' in ybegin:
                nzf.filename = yenc_name_fixer(ybegin['name'])
            else:
                logging.debug("Possible corrupt header detected => ybegin: %s", ybegin)
            nzf.type = 'yenc'
            # Decode data
            if HAVE_YENC:
                decoded_data, crc = _yenc.decode_string(''.join(data))[:2]
                partcrc = '%08X' % ((crc ^ -1) & 2 ** 32L - 1)
            else:
                data = ''.join(data)
                for i in (0, 9, 10, 13, 27, 32, 46, 61):
                    j = '=%c' % (i + 64)
                    data = data.replace(j, chr(i))
                decoded_data = data.translate(YDEC_TRANS)
                crc = binascii.crc32(decoded_data)
                partcrc = '%08X' % (crc & 2 ** 32L - 1)

            if ypart:
                crcname = 'pcrc32'
            else:
                crcname = 'crc32'

            if crcname in yend:
                _partcrc = '0' * (8 - len(yend[crcname])) + yend[crcname].upper()
            else:
                _partcrc = None
                logging.debug("Corrupt header detected => yend: %s", yend)

            if not _partcrc == partcrc:
                raise CrcError(_partcrc, partcrc, decoded_data)
        else:
            raise BadYenc()

        return decoded_data


def yCheck(data):
    ybegin = None
    ypart = None
    yend = None

    # Check head
    for i in xrange(min(40, len(data))):
        try:
            if data[i].startswith('=ybegin '):
                splits = 3
                if data[i].find(' part=') > 0:
                    splits += 1
                if data[i].find(' total=') > 0:
                    splits += 1

                ybegin = ySplit(data[i], splits)

                if data[i + 1].startswith('=ypart '):
                    ypart = ySplit(data[i + 1])
                    data = data[i + 2:]
                    break
                else:
                    data = data[i + 1:]
                    break
        except IndexError:
            break

    # Check tail
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
def ySplit(line, splits=None):
    fields = {}

    if splits:
        parts = YSPLIT_RE.split(line, splits)[1:]
    else:
        parts = YSPLIT_RE.split(line)[1:]

    if len(parts) % 2:
        return fields

    for i in range(0, len(parts), 2):
        key, value = parts[i], parts[i + 1]
        fields[key] = value.strip()

    return fields
