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
import queue
from threading import Thread

import sabnzbd
from sabnzbd.constants import SABYENC_VERSION_REQUIRED
from sabnzbd.articlecache import ArticleCache
from sabnzbd.downloader import Downloader
from sabnzbd.nzbqueue import NzbQueue
import sabnzbd.cfg as cfg
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


class Decoder:
    """ Implement thread-like coordinator for the decoders """

    do = None

    def __init__(self):
        logging.debug("Initializing decoders")
        # Initialize queue and servers
        self.decoder_queue = queue.Queue()

        # Initialize decoders
        self.decoder_workers = []
        for i in range(cfg.num_decoders()):
            self.decoder_workers.append(DecoderWorker(self.decoder_queue))
        Decoder.do = self

    def start(self):
        for decoder_worker in self.decoder_workers:
            decoder_worker.start()

    def is_alive(self):
        # Check all workers
        for decoder_worker in self.decoder_workers:
            if not decoder_worker.is_alive():
                return False
        return True

    def stop(self):
        # Put multiple to stop all decoders
        for _ in self.decoder_workers:
            self.decoder_queue.put(None)

    def join(self):
        # Wait for all decoders to finish
        for decoder_worker in self.decoder_workers:
            try:
                decoder_worker.join()
            except:
                pass

    def process(self, article, raw_data):
        # We use reported article-size, just like sabyenc does
        ArticleCache.do.reserve_space(article.bytes)
        self.decoder_queue.put((article, raw_data))

    def queue_full(self):
        # Check if the queue size exceeds the limits
        return self.decoder_queue.qsize() >= ArticleCache.do.decoder_cache_article_limit


class DecoderWorker(Thread):
    """ The actuall workhorse that handles decoding! """

    def __init__(self, decoder_queue):
        Thread.__init__(self)
        logging.debug("Initializing decoder %s", self.name)

        self.decoder_queue = decoder_queue
        self.__log_decoding = cfg.debug_log_decoding()

    def stop(self):
        # Put multiple to stop all decoders
        self.decoder_queue.put(None)
        self.decoder_queue.put(None)

    def run(self):
        while 1:
            # Let's get to work!
            art_tup = self.decoder_queue.get()
            if not art_tup:
                logging.info("Shutting down decoder %s", self.name)
                break

            article, raw_data = art_tup
            nzf = article.nzf
            nzo = nzf.nzo
            art_id = article.article
            killed = False

            # Free space in the article-queue
            ArticleCache.do.free_reserved_space(article.bytes)

            data = None
            register = True  # Finish article
            found = False  # Proper article found
            logme = None

            try:
                if nzo.precheck:
                    raise BadYenc
                register = True

                if self.__log_decoding:
                    logging.debug("Decoding %s", art_id)

                data = decode(article, raw_data)
                found = True

            except IOError:
                logme = T("Decoding %s failed") % art_id
                logging.warning(logme)
                logging.info("Traceback: ", exc_info=True)

                Downloader.do.pause()
                NzbQueue.do.reset_try_lists(article)
                register = False

            except MemoryError:
                logme = T("Decoder failure: Out of memory")
                logging.warning(logme)
                anfo = ArticleCache.do.cache_info()
                logging.info(
                    "Decoder-Queue: %d, Cache: %d, %d, %d",
                    self.decoder_queue.qsize(),
                    anfo.article_sum,
                    anfo.cache_size,
                    anfo.cache_limit,
                )
                logging.info("Traceback: ", exc_info=True)

                Downloader.do.pause()
                NzbQueue.do.reset_try_lists(article)
                register = False

            except CrcError as e:
                logme = "CRC Error in %s" % art_id
                logging.info(logme)

                data = e.data

            except (BadYenc, ValueError):
                # Handles precheck and badly formed articles
                killed = False
                found = False
                if nzo.precheck and raw_data and raw_data[0].startswith(b"223 "):
                    # STAT was used, so we only get a status code
                    found = True
                else:
                    # Examine headers (for precheck) or body (for download)
                    # And look for DMCA clues (while skipping "X-" headers)
                    for line in raw_data:
                        lline = line.lower()
                        if b"message-id:" in lline:
                            found = True
                        if not lline.startswith(b"X-") and match_str(
                            lline, (b"dmca", b"removed", b"cancel", b"blocked")
                        ):
                            killed = True
                            break
                if killed:
                    logme = "Article removed from server (%s)"
                    logging.info(logme, art_id)
                if nzo.precheck:
                    if found and not killed:
                        # Pre-check, proper article found, just register
                        if sabnzbd.LOG_ALL:
                            logging.debug("Server %s has article %s", article.fetcher, art_id)
                        register = True
                elif not killed and not found:
                    logme = T("Badly formed yEnc article in %s") % art_id
                    logging.info(logme)
                    # bad yEnc article, so ... let's check if it's uuencode, to inform user and stop download
                    if raw_data[0].lower().find(b"\nbegin ") >= 0:
                        logme = T("UUencode detected, only yEnc encoding is supported [%s]") % nzo.final_name
                        logging.error(logme)
                        nzo.fail_msg = logme
                        NzbQueue.do.end_job(nzo)
                        break

                if not found or killed:
                    new_server_found = article.search_new_server()
                    if new_server_found:
                        register = False
                        logme = None

            except:
                logme = T("Unknown Error while decoding %s") % art_id
                logging.info(logme)
                logging.info("Traceback: ", exc_info=True)
                new_server_found = article.search_new_server()
                if new_server_found:
                    register = False
                    logme = None

            if logme:
                if killed:
                    nzo.increase_bad_articles_counter("killed_articles")
                else:
                    nzo.increase_bad_articles_counter("bad_articles")

            if data:
                # If the data needs to be written to disk due to full cache, this will be slow
                # Causing the decoder-queue to fill up and delay the downloader
                ArticleCache.do.save_article(article, data)

            if register:
                NzbQueue.do.register_article(article, found)


def decode(article, raw_data):
    # Let SABYenc do all the heavy lifting
    decoded_data, yenc_filename, crc, crc_expected, crc_correct = sabyenc3.decode_usenet_chunks(raw_data, article.bytes)

    # Mark as decoded
    article.decoded = True

    # Assume it is yenc
    article.nzf.type = "yenc"

    # Only set the name if it was found and not obfuscated
    if not article.nzf.filename_checked and yenc_filename:
        # Set the md5-of-16k if this is the first article
        if article.lowest_partnum:
            article.nzf.md5of16k = hashlib.md5(decoded_data[:16384]).digest()

        # Try the rename, even if it's not the first article
        # For example when the first article was missing
        article.nzf.nzo.verify_nzf_filename(article.nzf, yenc_filename)

    # CRC check
    if not crc_correct:
        raise CrcError(crc_expected, crc, decoded_data)

    return decoded_data
