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
sabnzbd.urlgrabber - Queue for grabbing NZB files from websites
"""

import os
import time
import re
import logging
import Queue
import urllib
from threading import *

import socket
try:
    socket.ssl
    _PROTOCOL = 'https'
except:
    _PROTOCOL = 'http'

import sabnzbd
import sabnzbd.misc as misc
import sabnzbd.dirscanner as dirscanner
import sabnzbd.nzbqueue as nzbqueue
import sabnzbd.cfg as cfg
from sabnzbd.lang import Ta

#------------------------------------------------------------------------------
_RETRIES = 10

class URLGrabber(Thread):
    do = None  # Link to instance of the thread

    def __init__(self):
        Thread.__init__(self)
        self.queue = Queue.Queue()
        for tup in sabnzbd.nzbqueue.get_urls():
            url, nzo = tup
            self.queue.put((url, nzo, _RETRIES))
        self.shutdown = False
        URLGrabber.do = self

    def add(self, url, future_nzo):
        """ Add an URL to the URLGrabber queue """
        self.queue.put((url, future_nzo, _RETRIES))

    def stop(self):
        logging.info('URLGrabber shutting down')
        self.shutdown = True
        self.queue.put((None, None, 0))

    def run(self):
        logging.info('URLGrabber starting up')
        self.shutdown = False

        while not self.shutdown:
            (url, future_nzo, retry_count) = self.queue.get()
            if not url:
                continue

            # If nzo entry deleted, give up
            try:
                deleted = future_nzo.deleted
            except:
                deleted = True
            if deleted:
                logging.debug('Dropping URL %s, job entry missing', url)
                continue

            # Add nzbmatrix credentials if needed
            url, matrix_id = _matrix_url(url)

            # _grab_url cannot reside in a function, because the tempfile
            # would not survive the end of the function
            logging.info('Grabbing URL %s', url)
            opener = urllib.FancyURLopener({})
            opener.prompt_user_passwd = None
            opener.addheaders = []
            opener.addheader('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__)
            opener.addheader('Accept-encoding','gzip')
            filename = None
            category = None
            nzo_info = {}
            try:
                fn, header = opener.retrieve(url)
            except:
                fn = None

            if fn:
                for tup in header.items():
                    try:
                        item = tup[0].lower()
                        value = tup[1].strip()
                    except:
                        continue
                    if item in ('category_id', 'x-dnzb-category'):
                        category = value
                    elif item in ('x-dnzb-moreinfo',):
                        nzo_info['more_info'] = value
                    elif item in ('x-dnzb-name',):
                        filename = value
                        if not filename.endswith('.nzb'):
                            filename += '.nzb'

                    if not filename:
                        for item in tup:
                            if "filename=" in item:
                                filename = item[item.index("filename=") + 9:].strip(';').strip('"')

            if matrix_id:
                fn, msg, retry = _analyse_matrix(fn, matrix_id)
                category = map_matrix(category)
            else:
                msg = ''
                retry = True

            # Check if the filepath is specified, if not, check if a retry is allowed.
            if not fn:
                retry_count -= 1
                if retry_count > 0 and retry:
                    logging.info('Retry URL %s', url)
                    self.queue.put((url, future_nzo, retry_count))
                else:
                    misc.bad_fetch(future_nzo, url, msg, retry=True)
                continue

            if not filename:
                filename = os.path.basename(url) + '.nzb'
            filename = misc.sanitize_foldername(filename)
            pp = future_nzo.pp
            script = future_nzo.script
            cat = future_nzo.cat
            if cat is None and category:
                cat = misc.cat_convert(category)
            priority = future_nzo.priority
            nzbname = future_nzo.custom_name

            # Check if nzb file
            if os.path.splitext(filename)[1].lower() in ('.nzb', '.gz'):
                res = dirscanner.ProcessSingleFile(filename, fn, pp=pp, script=script, cat=cat, priority=priority, \
                                                   nzbname=nzbname, nzo_info=nzo_info)
                if res == 0:
                    nzbqueue.remove_nzo(future_nzo.nzo_id, add_to_history=False, unload=True)
                elif res == -2:
                    self.add(url, future_nzo)
                else:
                    misc.bad_fetch(future_nzo, url, retry=True, content=True)
            # Check if a supported archive
            else:
                if dirscanner.ProcessArchiveFile(filename, fn, pp, script, cat, priority=priority) == 0:
                    nzbqueue.remove_nzo(future_nzo.nzo_id, add_to_history=False, unload=True)
                else:
                    # Not a supported filetype, not an nzb (text/html ect)
                    try:
                        os.remove(fn)
                    except:
                        pass
                    misc.bad_fetch(future_nzo, url, retry=True, content=True)

            # Don't pound the website!
            time.sleep(5.0)



#-------------------------------------------------------------------------------
_RE_NZBMATRIX = re.compile(r'nzbmatrix.com/(.*)[\?&]id=(\d+)', re.I)
_RE_NZBMATRIX_USER = re.compile(r'&username=([^&=]+)', re.I)
_RE_NZBMATRIX_API  = re.compile(r'&apikey=([^&=]+)', re.I)

def _matrix_url(url):
    """ Patch up the url for nzbmatrix.com """

    matrix_id = 0
    m = _RE_NZBMATRIX.search(url)
    if m:
        matrix_id = m.group(2)
        if not _RE_NZBMATRIX_USER.search(url) or not _RE_NZBMATRIX_API.search(url):
            user = urllib.quote_plus(cfg.matrix_username())
            key = urllib.quote_plus(cfg.matrix_apikey())
            url = '%s://nzbmatrix.com/api-nzb-download.php?id=%s&username=%s&apikey=%s' % \
                  (_PROTOCOL, matrix_id, user, key)
    return url, matrix_id


_RE_MATRIX_ERR = re.compile(r'please_wait[_ ]+(\d+)', re.I)

def _analyse_matrix(fn, matrix_id):
    """ Analyse respons of nzbmatrix
    """
    msg = ''
    if not fn:
        # No response, just retry
        return (None, msg, True)
    try:
        f = open(fn, 'r')
        data = f.read(40)
        f.close()
    except:
        return (None, msg, True)

    # Check for an error response
    if data and data.startswith('error'):
        # Check if we are required to wait - if so sleep the urlgrabber
        m = _RE_MATRIX_ERR.search(data)
        if m:
            wait = int(m.group(1))
            if wait:
                logging.debug('Sleeping URL grabber %s sec', wait)
                time.sleep(min(wait, 60))
                # Return, but tell the urlgrabber to retry
                return (None, msg, True)
        else:
            # Clear error message, don't retry
            msg = Ta('warn-matrixFail@1') % data
            return (None, msg, False)

    if data.startswith("<!DOCTYPE"):
        # We got HTML, probably a temporary problem, keep trying
        msg = Ta('warn-matrixBadRep@1') % matrix_id
        return (None, msg, True)

    return fn, msg, False


#------------------------------------------------------------------------------
_MATRIX_MAP = None

def map_matrix(index):
    """ Translate nzbmatrix category_id to category text """

    if _MATRIX_MAP is None:
        read_matrix_cats()
    return _MATRIX_MAP.get(index, index)


def read_matrix_cats():
    """ Read mapping of NzbMatrix categories """
    global _MATRIX_MAP

    _MATRIX_MAP = {}
    path = os.path.join(sabnzbd.DIR_PROG, 'nzbmatrix.txt')
    try:
        for line in open(path, 'r'):
            try:
                number, text = line.split(',', 1)
                _MATRIX_MAP[number] = text.strip(', \n\r')
            except ValueError:
                pass
    except IOError:
        logging.warning('Cannot open %s', path)

