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
sabnzbd.decoder - article decoder
"""

import logging
import hashlib
from time import sleep
from threading import Thread

import sabnzbd
from sabnzbd.constants import MAX_DECODE_QUEUE, LIMIT_DECODE_QUEUE, SABYENC_VERSION_REQUIRED
import sabnzbd.articlecache
import sabnzbd.downloader
import sabnzbd.nzbqueue
import sabnzbd.cfg as cfg
from sabnzbd.encoding import ubtou
from sabnzbd.misc import match_str

# Check for correct SABYenc version
SABYENC_VERSION = None
try:
    import sabyenc3
    SABYENC_ENABLED = True
    SABYENC_VERSION = sabyenc3.__version__
    # Verify version to at least match minor version
    if SABYENC_VERSION[:3] != SABYENC_VERSION_REQUIRED[:3]:
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


class Decoder(Thread):

    def __init__(self, servers, queue):
        Thread.__init__(self)

        self.queue = queue
        self.servers = servers
        self.__log_decoding = cfg.debug_log_decoding()

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

            article, raw_data = art_tup
            nzf = article.nzf
            nzo = nzf.nzo
            art_id = article.article
            killed = False

            # Check if the space that's now free can let us continue the queue?
            qsize = self.queue.qsize()
            if (sabnzbd.articlecache.ArticleCache.do.free_reserve_space(article.bytes) or qsize < MAX_DECODE_QUEUE) and \
               (qsize < LIMIT_DECODE_QUEUE) and sabnzbd.downloader.Downloader.do.delayed:
                sabnzbd.downloader.Downloader.do.undelay()

            data = None
            register = True  # Finish article
            found = False    # Proper article found
            logme = None

            if raw_data:
                try:
                    if nzo.precheck:
                        raise BadYenc
                    register = True

                    if self.__log_decoding:
                        logging.debug("Decoding %s", art_id)

                    data = self.decode(article, raw_data)
                    nzf.article_count += 1
                    found = True

                except IOError:
                    logme = T('Decoding %s failed') % art_id
                    logging.warning(logme)
                    logging.info("Traceback: ", exc_info=True)

                    sabnzbd.downloader.Downloader.do.pause()
                    sabnzbd.nzbqueue.NzbQueue.do.reset_try_lists(article)
                    register = False

                except MemoryError:
                    logme = T('Decoder failure: Out of memory')
                    logging.warning(logme)
                    anfo = sabnzbd.articlecache.ArticleCache.do.cache_info()
                    logging.info("Decoder-Queue: %d, Cache: %d, %d, %d", self.queue.qsize(), anfo.article_sum, anfo.cache_size, anfo.cache_limit)
                    logging.info("Traceback: ", exc_info=True)

                    sabnzbd.downloader.Downloader.do.pause()
                    sabnzbd.nzbqueue.NzbQueue.do.reset_try_lists(article)
                    register = False

                except CrcError as e:
                    logme = 'CRC Error in %s' % art_id
                    logging.info(logme)

                    data = e.data

                except (BadYenc, ValueError):
                    # Handles precheck and badly formed articles
                    killed = False
                    found = False
                    if nzo.precheck and raw_data and raw_data[0].startswith(b'223 '):
                        # STAT was used, so we only get a status code
                        found = True
                    else:
                        # Examine headers (for precheck) or body (for download)
                        # And look for DMCA clues (while skipping "X-" headers)
                        for line in raw_data:
                            lline = ubtou(line).lower()
                            if 'message-id:' in lline:
                                found = True
                            if not lline.startswith('X-') and match_str(lline, ('dmca', 'removed', 'cancel', 'blocked')):
                                killed = True
                                break
                    if killed:
                        logme = 'Article removed from server (%s)'
                        logging.info(logme, art_id)
                    if nzo.precheck:
                        if found and not killed:
                            # Pre-check, proper article found, just register
                            if sabnzbd.LOG_ALL:
                                logging.debug('Server %s has article %s', article.fetcher, art_id)
                            register = True
                    elif not killed and not found:
                        logme = T('Badly formed yEnc article in %s') % art_id
                        logging.info(logme)
                        # bad yEnc article, so ... let's check if it's uuencode, to inform user and stop download
                        if raw_data[0].lower().find(b'\nbegin ') >= 0:
                            logme = T('UUencode detected, only yEnc encoding is supported [%s]') % nzo.final_name
                            logging.error(logme)
                            nzo.fail_msg = logme
                            sabnzbd.nzbqueue.NzbQueue.do.end_job(nzo)
                            break

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
                        nzo.increase_bad_articles_counter('killed_articles')
                    else:
                        nzo.increase_bad_articles_counter('bad_articles')

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

    def decode(self, article, raw_data):
        # Let SABYenc do all the heavy lifting
        decoded_data, output_filename, crc, crc_expected, crc_correct = sabyenc3.decode_usenet_chunks(raw_data, article.bytes)

        # Assume it is yenc
        article.nzf.type = 'yenc'

        # Only set the name if it was found and not obfuscated
        self.verify_filename(article, decoded_data, output_filename)

        # CRC check
        if not crc_correct:
            raise CrcError(crc_expected, crc, decoded_data)

        return decoded_data

    def search_new_server(self, article):
        # Search new server
        article.add_to_try_list(article.fetcher)
        for server in self.servers:
            if server.active and not article.server_in_try_list(server):
                if server.priority >= article.fetcher.priority:

                    article.tries = 0
                    # Allow all servers for this nzo and nzf again (but not for this article)
                    sabnzbd.nzbqueue.NzbQueue.do.reset_try_lists(article, article_reset=False)
                    return True

        msg = T('%s => missing from all servers, discarding') % article
        logging.info(msg)
        article.nzf.nzo.increase_bad_articles_counter('missing_articles')
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
        if article.lowest_partnum:
            nzf.md5of16k = hashlib.md5(decoded_data[:16384]).digest()

        # Try the rename
        nzf.nzo.verify_nzf_filename(nzf, yenc_filename)
