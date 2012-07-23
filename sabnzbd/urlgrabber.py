#!/usr/bin/python -OO
# Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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
from threading import Thread

import socket
try:
    socket.ssl
    _PROTOCOL = 'https'
except:
    _PROTOCOL = 'http'

import sabnzbd
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

    def rm_bookmark(self, url):
        """ Add removal request for nzbmatrix bookmark """
        if 'nzbmatrix.com' in url and cfg.matrix_del_bookmark():
            url = url.replace('download.php?', 'bookmarks.php?action=remove&')
            self.add(url, None)

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
                del_bookmark = not future_nzo
                if future_nzo:
                    # If nzo entry deleted, give up
                    try:
                        deleted = future_nzo.deleted
                    except AttributeError:
                        deleted = True
                    if deleted:
                        logging.debug('Dropping URL %s, job entry missing', url)
                        continue

                # Add nzbmatrix credentials if needed
                url, matrix_id = _matrix_url(url)

                # _grab_url cannot reside in a function, because the tempfile
                # would not survive the end of the function
                if del_bookmark:
                    logging.info('Removing nzbmatrix bookmark %s', matrix_id)
                else:
                    logging.info('Grabbing URL %s', url)
                if '.nzbsrus.' in url:
                    opener = urllib.URLopener({})
                else:
                    opener = urllib.FancyURLopener({})
                opener.prompt_user_passwd = None
                opener.addheaders = []
                opener.addheader('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__)
                if not [True for item in _BAD_GZ_HOSTS if item in url]:
                    opener.addheader('Accept-encoding','gzip')
                filename = None
                category = None
                length = 0
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
                        elif item in ('content-length',):
                            length = misc.int_conv(value)

                        if not filename:
                            for item in tup:
                                if "filename=" in item:
                                    filename = item[item.index("filename=") + 9:].strip(';').strip('"')

                if matrix_id:
                    fn, msg, retry, wait = _analyse_matrix(fn, matrix_id)
                    if not fn:
                        if retry:
                            logging.info(msg)
                            logging.debug('Retry nzbmatrix item %s after waiting %s sec', matrix_id, wait)
                            self.add(url, future_nzo, wait)
                        else:
                            logging.error(msg)
                            misc.bad_fetch(future_nzo, clean_matrix_url(url), msg, retry=True)
                        continue
                    category = _MATRIX_MAP.get(category, category)

                    if del_bookmark:
                        # No retries of nzbmatrix bookmark removals
                        continue

                else:
                    fn, msg, retry, wait = _analyse_others(fn, url)
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

                # Check if nzb file
                if os.path.splitext(filename)[1].lower() in ('.nzb', '.gz'):
                    res, nzo_ids = dirscanner.ProcessSingleFile(filename, fn, pp=pp, script=script, cat=cat, priority=priority, \
                                                       nzbname=nzbname, nzo_info=nzo_info, url=future_nzo.url)
                    if res == 0:
                        NzbQueue.do.remove(future_nzo.nzo_id, add_to_history=False)
                    else:
                        if res == -2:
                            logging.info('Incomplete NZB, retry after 5 min %s', url)
                            when = 300
                        else:
                            logging.info('Unknown error fetching NZB, retry after 2 min %s', url)
                            when = 120
                        self.add(url, future_nzo, when)
                # Check if a supported archive
                else:
                    if dirscanner.ProcessArchiveFile(filename, fn, pp, script, cat, priority=priority, url=future_nzo.url)[0] == 0:
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




#-------------------------------------------------------------------------------
_RE_NZBMATRIX = re.compile(r'nzbmatrix\.com/(.*)[\?&]id=(\d+)', re.I)
_RE_NZBXXX    = re.compile(r'nzbxxx\.com/(.*)[\?&]id=(\d+)', re.I)
_RE_NZBMATRIX_USER = re.compile(r'&username=([^&=]+)', re.I)
_RE_NZBMATRIX_API  = re.compile(r'&apikey=([^&=]+)', re.I)

def _matrix_url(url):
    """ Patch up the url for nzbmatrix.com """

    matrix_id = 0
    m = _RE_NZBMATRIX.search(url)
    if not m:
        mx = _RE_NZBXXX.search(url)

    if m:
        site = 'nzbmatrix.com'
        user = urllib.quote_plus(cfg.matrix_username())
        key = urllib.quote_plus(cfg.matrix_apikey())
    elif mx:
        site = 'nzbxxx.com'
        user = urllib.quote_plus(cfg.xxx_username())
        key = urllib.quote_plus(cfg.xxx_apikey())
        m = mx

    if m:
        matrix_id = m.group(2)
        if not _RE_NZBMATRIX_USER.search(url) or not _RE_NZBMATRIX_API.search(url):
            url = '%s://api.%s/v1.1/download.php?id=%s&username=%s&apikey=%s' % \
                  (_PROTOCOL, site, matrix_id, user, key)
    return url, matrix_id


def clean_matrix_url(url):
    ''' Return nzbmatrix url without user credentials '''
    site = 'nzbmatrix.com'
    m = _RE_NZBMATRIX.search(url)
    if not m:
        m = _RE_NZBXXX.search(url)
        site = 'nzbxxx.com'

    if m:
        matrix_id = m.group(2)
        url = '%s://api.%s/v1.1/download.php?id=%s' % (_PROTOCOL, site, matrix_id)
    return url


_RE_MATRIX_ERR = re.compile(r'please_wait[_ ]+(\d+)', re.I)

def _analyse_matrix(fn, matrix_id):
    """ Analyse respons of nzbmatrix
        returns fn|None, error-message|None, retry, wait-seconds
    """
    msg = ''
    wait = 0
    if not fn:
        logging.debug('No response from nzbmatrix, retry after 60 sec')
        return None, msg, True, 60
    try:
        f = open(fn, 'r')
        data = f.read(40).lower()
        f.close()
    except:
        logging.debug('Problem with tempfile %s from nzbmatrix, retry after 60 sec', fn)
        return None, msg, True, 60

    # Check for an error response
    if data and '<!DOCTYPE' in data:
        # We got HTML, probably a temporary problem, keep trying
        msg = Ta('Invalid nzbmatrix report number %s') % matrix_id
        wait = 300
    elif data and data.startswith('error'):
        txt = misc.match_str(data, ('invalid_login', 'invalid_api', 'disabled_account', 'vip_only'))
        if txt:
            if 'vip' in txt:
                msg = Ta('You need an nzbmatrix VIP account to use the API')
            else:
                msg = (Ta('Invalid nzbmatrix credentials') + ' (%s)') % txt
            return None, msg, False, 0
        elif 'limit_reached' in data:
            msg = 'Too many nzbmatrix hits, waiting 10 min'
            wait = 600
        elif misc.match_str(data, ('daily_limit', 'limit is reached')):
            # Daily limit reached, just wait an hour before trying again
            msg = 'Daily limit nzbmatrix reached, waiting 1 hour'
            wait = 3600
        elif 'no_nzb_found' in data:
            msg = Ta('Invalid nzbmatrix report number %s') % matrix_id
            wait = 300
        else:
            # Check if we are required to wait - if so sleep the urlgrabber
            m = _RE_MATRIX_ERR.search(data)
            if m:
                wait = min(int(m.group(1)), 600)
            else:
                msg = Ta('Problem accessing nzbmatrix server (%s)') % data
                wait = 60
    if wait:
        # Return, but tell the urlgrabber to retry
        return None, msg, True, wait

    return fn, msg, False, 0



RUS_FATAL = ('DENIED_MISSING_CREDENTIALS', 'DENIED_NO_ACCOUNT',
             'DENIED_INVALID_CREDENTIALS', 'INCORRECT_URL',
             'NZB_DELETED', 'POST_NUKED', 'FILE_UNAVAILABLE'
            )
RUS_15M =   ('SQL_ERROR', 'SERVICE_OFFLINE')
RUS_60M =   ('MAX_DOWNLOAD_REACHED_UPGRADE_TO_VIP', 'MAX_DOWNLOAD_REACHED')

def _analyse_others(fn, url):
    """ Analyse respons of indexer
        returns fn|None, error-message|None, retry, wait-seconds
    """
    msg = ''
    wait = 0
    if not fn:
        logging.debug('No response from indexer, retry after 60 sec')
        return None, msg, True, 60
    try:
        f = open(fn, 'r')
        data = f.read(100)
        f.close()
    except:
        logging.debug('Problem with tempfile %s from indexer, retry after 60 sec', fn)
        return None, msg, True, 60

    # Check for an error response
    if not data:
        logging.debug('Received nothing from indexer, retry after 60 sec')
        return None, msg, True, 60

    if '.nzbsrus.' in url:
        # Partial support for nzbsrus.com's API
        if misc.match_str(data, RUS_FATAL):
            logging.debug('nzbsrus says: %s, abort', data)
            return None, data, False, 0
        if misc.match_str(data, RUS_15M):
            logging.debug('nzbsrus says: %s, wait 15m', data)
            return None, data, True, 900
        if misc.match_str(data, RUS_60M):
            logging.debug('nzbsrus says: %s, wait 60m', data)
            return None, data, True, 3600

    return fn, msg, False, 0

#------------------------------------------------------------------------------
_MATRIX_MAP = {
'28' : 'anime.all',
'20' : 'apps.linux',
'19' : 'apps.mac',
'21' : 'apps.other',
'18' : 'apps.pc',
'52' : 'apps.portable',
'53' : 'documentaries.hd',
'9'  : 'documentaries.std',
'45' : 'games.ds',
'17' : 'games.other',
'10' : 'games.pc',
'11' : 'games.ps2',
'43' : 'games.ps3',
'12' : 'games.psp',
'44' : 'games.wii',
'51' : 'games.wii vc',
'13' : 'games.xbox',
'14' : 'games.xbox360',
'56' : 'games.xbox360 (other)',
'54' : 'movies.brrip',
'2'  : 'movies.divx/xvid',
'1'  : 'movies.dvd',
'50' : 'movies.hd (image)',
'42' : 'movies.hd (x264)',
'4'  : 'movies.other',
'24' : 'music.dvd',
'23' : 'music.lossless',
'22' : 'music.mp3, albums',
'47' : 'music.mp3, singles',
'27' : 'music.other',
'25' : 'music.video',
'55' : 'other.android',
'49' : 'other.audio, books',
'36' : 'other.e-books',
'39' : 'other.extra, pars/fills',
'37' : 'other.images',
'38' : 'other.iOS/iPhone',
'40' : 'other.other',
'26' : 'other.radio',
'5'  : 'tv.dvd (image)',
'57' : 'tv.hd (image)',
'41' : 'tv.hd (x264)',
'8'  : 'tv.other',
'6'  : 'tv.sd',
'7'  : 'tv.sport/ent'
}

