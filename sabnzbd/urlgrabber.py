#!/usr/bin/python -OO
# Copyright 2008-2013 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.urlgrabber - Queue for grabbing NZB files from websites
"""

import os
import time
import re
import logging
import Queue
import urllib2
from threading import Thread

import sabnzbd
from sabnzbd.constants import FUTURE_Q_FOLDER
import sabnzbd.misc as misc
import sabnzbd.dirscanner as dirscanner
from sabnzbd.nzbqueue import NzbQueue
import sabnzbd.cfg as cfg

_BAD_GZ_HOSTS = ('.zip', 'nzbsa.co.za', 'newshost.za.net')

#------------------------------------------------------------------------------

class URLGrabber(Thread):
    do = None  # Link to instance of the thread

    def __init__(self):
        Thread.__init__(self)
        self.queue = Queue.Queue()
        for tup in NzbQueue.do.get_urls():
            url, nzo = tup
            self.queue.put((url, nzo))
        self.shutdown = False
        URLGrabber.do = self

    def add(self, url, future_nzo, when=None):
        """ Add an URL to the URLGrabber queue, 'when' is seconds from now """
        if when and future_nzo:
            future_nzo.wait = time.time() + when
        self.queue.put((url, future_nzo))

    def stop(self):
        logging.info('URLGrabber shutting down')
        self.shutdown = True
        self.add(None, None)

    def run(self):
        logging.info('URLGrabber starting up')
        self.shutdown = False

        while not self.shutdown:
            # Don't pound the website!
            time.sleep(5.0)

            (url, future_nzo) = self.queue.get()

            if not url:
                # stop signal, go test self.shutdown
                continue
            if future_nzo and future_nzo.wait and future_nzo.wait > time.time():
                # Requeue when too early and still active

                self.add(url, future_nzo)
                continue
            url = url.replace(' ', '')

            try:
                if future_nzo:
                    # If nzo entry deleted, give up
                    try:
                        deleted = future_nzo.deleted
                    except AttributeError:
                        deleted = True
                    if deleted:
                        logging.debug('Dropping URL %s, job entry missing', url)
                        continue

                logging.info('Grabbing URL %s', url)
                req = urllib2.Request(url)
                req.add_header('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__)
                if not [True for item in _BAD_GZ_HOSTS if item in url]:
                    req.add_header('Accept-encoding','gzip')
                filename = None
                category = None
                length = 0
                gzipped = False
                nzo_info = {}
                try:
                    fn = urllib2.urlopen(req)
                except:
                    ret = None

                if fn:
                    for hdr in fn.headers:
                        try:
                            item = hdr.lower()
                            value = fn.headers[hdr]
                        except:
                            continue
                        if item in ('content-encoding',) and value == 'gzip':
                            gzipped = True
                        if item in ('category_id', 'x-dnzb-category'):
                            category = value
                        elif item in ('x-dnzb-moreinfo',):
                            nzo_info['more_info'] = value
                        elif item in ('x-dnzb-name',):
                            filename = value
                            if not filename.endswith('.nzb'):
                                filename += '.nzb'
                        elif item in ('content-length',):
                            length = misc.int_conv(value)

                        if not filename and "filename=" in value:
                            filename = value[value.index("filename=") + 9:].strip(';').strip('"')

                fn, msg, retry, wait, data = _analyse(fn, url)
                if not fn:
                    if retry:
                        logging.info('Retry URL %s', url)
                        self.add(url, future_nzo, wait)
                    else:
                        misc.bad_fetch(future_nzo, url, msg, retry=True)
                    continue

                if not filename:
                    filename = os.path.basename(url) + '.nzb'
                # Sanitize and trim name, preserving the extension
                filename, ext = os.path.splitext(filename)
                filename = misc.sanitize_foldername(filename)
                filename += '.' + misc.sanitize_foldername(ext)

                pp = future_nzo.pp
                script = future_nzo.script
                cat = future_nzo.cat
                if (cat is None or cat == '*') and category:
                    cat = misc.cat_convert(category)
                priority = future_nzo.priority
                nzbname = future_nzo.custom_name

                # process data
                if gzipped:
                    filename = filename + '.gz'
                if not data:
                    data = fn.read()
                fn.close()

                # Write data to temp file
                path = os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)
                path = os.path.join(path, filename)
                f = open(path, 'wb')
                f.write(data)
                f.close()
                del data

                # Check if nzb file
                if os.path.splitext(filename)[1].lower() in ('.nzb', '.gz'):
                    res, nzo_ids = dirscanner.ProcessSingleFile(filename, path, pp=pp, script=script, cat=cat, priority=priority, \
                                                       nzbname=nzbname, nzo_info=nzo_info, url=future_nzo.url, keep=False)
                    if res == 0:
                        NzbQueue.do.remove(future_nzo.nzo_id, add_to_history=False)
                    else:
                        if res == -2:
                            logging.info('Incomplete NZB, retry after 5 min %s', url)
                            when = 300
                        elif res == -1:
                            # Error, but no reason to retry. Warning is already given
                            NzbQueue.do.remove(future_nzo.nzo_id, add_to_history=False)
                            continue
                        else:
                            logging.info('Unknown error fetching NZB, retry after 2 min %s', url)
                            when = 120
                        self.add(url, future_nzo, when)
                # Check if a supported archive
                else:
                    if dirscanner.ProcessArchiveFile(filename, fn, pp, script, cat, priority=priority, url=future_nzo.url, keep=False)[0] == 0:
                        NzbQueue.do.remove(future_nzo.nzo_id, add_to_history=False)
                    else:
                        # Not a supported filetype, not an nzb (text/html ect)
                        try:
                            os.remove(fn)
                        except:
                            pass
                        logging.info('Unknown filetype when fetching NZB, retry after 30s %s', url)
                        self.add(url, future_nzo, 30)
            except:
                logging.error('URLGRABBER CRASHED', exc_info=True)
                logging.debug("URLGRABBER Traceback: ", exc_info=True)




RUS_FATAL = ('DENIED_MISSING_CREDENTIALS', 'DENIED_NO_ACCOUNT',
             'DENIED_INVALID_CREDENTIALS', 'INCORRECT_URL',
             'NZB_DELETED', 'POST_NUKED', 'FILE_UNAVAILABLE'
            )
RUS_15M =   ('SQL_ERROR', 'SERVICE_OFFLINE')
RUS_60M =   ('MAX_DOWNLOAD_REACHED_UPGRADE_TO_VIP', 'MAX_DOWNLOAD_REACHED')

def _analyse(fn, url):
    """ Analyse respons of indexer
        returns fn|None, error-message|None, retry, wait-seconds, data
    """
    data = None
    wait = 0
    if fn.code != 200:
        logging.debug('No usable response from indexer, retry after 60 sec')
        return None, fn.msg, True, 60, data

    # Check for an error response
    if fn.msg != 'OK':
        logging.debug('Received nothing from indexer, retry after 60 sec')
        return None, fn.msg, True, 60, data

    if '.nzbsrus.' in url:
        # Partial support for nzbsrus.com's API
        data = fn.read()
        if misc.match_str(data, RUS_FATAL):
            logging.debug('nzbsrus says: %s, abort', data)
            return None, data, False, 0, data
        if misc.match_str(data, RUS_15M):
            logging.debug('nzbsrus says: %s, wait 15m', data)
            return None, data, True, 900, data
        if misc.match_str(data, RUS_60M):
            logging.debug('nzbsrus says: %s, wait 60m', data)
            return None, data, True, 3600, data

    return fn, fn.msg, False, 0, data

