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

import binascii
import logging
import re
import hashlib
from time import sleep
from threading import Thread

import sabnzbd
from sabnzbd.constants import Status, MAX_DECODE_QUEUE, LIMIT_DECODE_QUEUE, SABYENC_VERSION_REQUIRED
import sabnzbd.articlecache
import sabnzbd.downloader
import sabnzbd.nzbqueue
from sabnzbd.encoding import yenc_name_fixer, platform_encode
from sabnzbd.misc import match_str, is_obfuscated_filename

# Check for basic-yEnc
try:
    import _yenc
    HAVE_YENC = True
except ImportError:
    HAVE_YENC = False

# Check for correct SABYenc version
SABYENC_VERSION = None
try:
    import sabyenc
    SABYENC_ENABLED = True
    SABYENC_VERSION = sabyenc.__version__
    # Verify version
    if SABYENC_VERSION != SABYENC_VERSION_REQUIRED:
        raise ImportError
except ImportError:
    SABYENC_ENABLED = False


class CrcError(Exception):

    def __init__(self, needcrc, gotcrc, data):
        Exception.__init__(self)
        self.needcrc = needcrc
        self.gotcrc = gotcrc
        self.data = data


class BadYenc(Exception):

    def __init__(self):
        Exception.__init__(self)


YDEC_TRANS = ''.join([chr((i + 256 - 42) % 256) for i in xrange(256)])


class Decoder(Thread):

    def __init__(self, servers, queue):
        Thread.__init__(self)

        self.queue = queue
        self.servers = servers

    def stop(self):
        # Put multiple to stop all decoders
        self.queue.put(None)
        self.queue.put(None)

    def run(self):
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
            if (sabnzbd.articlecache.ArticleCache.do.free_reserve_space(lines) or qsize < MAX_DECODE_QUEUE) and \
               (qsize < LIMIT_DECODE_QUEUE) and sabnzbd.downloader.Downloader.do.delayed:
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
                    logging.debug("Decoding %s", art_id)

                    data = self.decode(article, lines, raw_data)
                    nzf.article_count += 1
                    found = True

                except IOError, e:
                    logme = T('Decoding %s failed') % art_id
                    logging.warning(logme)
                    logging.info("Traceback: ", exc_info=True)

                    sabnzbd.downloader.Downloader.do.pause()
                    article.fetcher = None
                    sabnzbd.nzbqueue.NzbQueue.do.reset_try_lists(nzf, nzo)
                    register = False

                except MemoryError, e:
                    logme = T('Decoder failure: Out of memory')
                    logging.warning(logme)
                    anfo = sabnzbd.articlecache.ArticleCache.do.cache_info()
                    logging.info("Decoder-Queue: %d, Cache: %d, %d, %d", self.queue.qsize(), anfo.article_sum, anfo.cache_size, anfo.cache_limit)
                    logging.info("Traceback: ", exc_info=True)

                    sabnzbd.downloader.Downloader.do.pause()
                    article.fetcher = None
                    sabnzbd.nzbqueue.NzbQueue.do.reset_try_lists(nzf, nzo)
                    register = False

                except CrcError, e:
                    logme = T('CRC Error in %s (%s -> %s)') % (art_id, e.needcrc, e.gotcrc)
                    logging.info(logme)

                    data = e.data

                except (BadYenc, ValueError):
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
                            logging.debug('Server %s has article %s', article.fetcher, art_id)
                            register = True
                    elif not killed and not found:
                        logme = T('Badly formed yEnc article in %s') % art_id
                        logging.info(logme)

                    if not found or killed:
                        new_server_found = self.search_new_server(article)
                        if new_server_found:
                            register = False
                            logme = None

                except:
                    logme = T('Unknown Error while decoding %s') % art_id
                    logging.info(logme)
                    logging.info("Traceback: ", exc_info=True)
                    new_server_found = self.search_new_server(article)
                    if new_server_found:
                        register = False
                        logme = None

                if logme:
                    if killed:
                        nzo.inc_log('killed_art_log', art_id)
                    else:
                        nzo.inc_log('bad_art_log', art_id)

            else:
                new_server_found = self.search_new_server(article)
                if new_server_found:
                    register = False
                elif nzo.precheck:
                    found = False

            if data:
                sabnzbd.articlecache.ArticleCache.do.save_article(article, data)

            if register:
                sabnzbd.nzbqueue.NzbQueue.do.register_article(article, found)

    def decode(self, article, data, raw_data):
        # Do we have SABYenc? Let it do all the work
        if sabnzbd.decoder.SABYENC_ENABLED:
            decoded_data, output_filename, crc, crc_expected, crc_correct = sabyenc.decode_usenet_chunks(raw_data, article.bytes)

            # Assume it is yenc
            article.nzf.type = 'yenc'

            # Only set the name if it was found and not obfuscated
            self.verify_filename(article, decoded_data, output_filename)

            # CRC check
            if not crc_correct:
                raise CrcError(crc_expected, crc, decoded_data)

            return decoded_data

        # Continue for _yenc or Python-yEnc
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
                    output_filename = yenc_name_fixer(ybegin['name'])
                else:
                    output_filename = None
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
                    _partcrc = yenc_name_fixer('0' * (8 - len(yend[crcname])) + yend[crcname].upper())
                else:
                    _partcrc = None
                    logging.debug("Corrupt header detected => yend: %s", yend)

                if not _partcrc == partcrc:
                    raise CrcError(_partcrc, partcrc, decoded_data)
            else:
                raise BadYenc()

            # Parse filename if there was data
            if decoded_data:
                # Only set the name if it was found and not obfuscated
                self.verify_filename(article, decoded_data, output_filename)

            return decoded_data

    def search_new_server(self, article):
        # Search new server
        article.add_to_try_list(article.fetcher)
        for server in self.servers:
            if server.active and not article.server_in_try_list(server):
                if server.priority >= article.fetcher.priority:
                    article.fetcher = None
                    article.tries = 0
                    # Allow all servers for this nzo and nzf again (but not for this article)
                    sabnzbd.nzbqueue.NzbQueue.do.reset_try_lists(article.nzf, article.nzf.nzo)
                    return True

        msg = T('%s => missing from all servers, discarding') % article
        logging.info(msg)
        article.nzf.nzo.inc_log('missing_art_log', msg)
        return False

    def verify_filename(self, article, decoded_data, yenc_filename):
        """ Verify the filename provided by yenc by using
            par2 information and otherwise fall back to NZB name
        """
        nzf = article.nzf
        # Was this file already verified and did we get a name?
        if nzf.filename_checked or not yenc_filename:
            return

        # Set the md5-of-16k if this is the first article
        if article.partnum == 1:
            nzf.md5of16k = hashlib.md5(decoded_data[:16384]).digest()

        # If we have the md5, use it to rename
        if nzf.md5of16k:
            # Don't check again, even if no match
            nzf.filename_checked = True
            # Find the match and rename
            if nzf.md5of16k in nzf.nzo.md5of16k:
                new_filename = platform_encode(nzf.nzo.md5of16k[nzf.md5of16k])
                # Was it even new?
                if new_filename != nzf.filename:
                    logging.info('Detected filename based on par2: %s -> %s', nzf.filename, new_filename)
                    nzf.nzo.renamed_file(new_filename, nzf.filename)
                    nzf.filename = new_filename
                return

        # Fallback to yenc/nzb name (also when there is no partnum=1)
        # We also keep the NZB name in case it ends with ".par2" (usually correct)
        if yenc_filename != nzf.filename and not is_obfuscated_filename(yenc_filename) and not nzf.filename.endswith('.par2'):
            logging.info('Detected filename from yenc: %s -> %s', nzf.filename, yenc_filename)
            nzf.nzo.renamed_file(yenc_filename, nzf.filename)
            nzf.filename = yenc_filename


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
