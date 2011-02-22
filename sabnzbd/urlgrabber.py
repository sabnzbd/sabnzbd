#!/usr/bin/python -OO
# Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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

#------------------------------------------------------------------------------
_RETRIES = 10

class URLGrabber(Thread):
    do = None  # Link to instance of the thread

    def __init__(self):
        Thread.__init__(self)
        self.queue = Queue.Queue()
        for tup in NzbQueue.do.get_urls():
            url, nzo = tup
            self.queue.put((url, nzo, _RETRIES))
        self.shutdown = False
        URLGrabber.do = self

    def add(self, url, future_nzo):
        """ Add an URL to the URLGrabber queue """
        self.queue.put((url, future_nzo, _RETRIES))

    def rm_bookmark(self, url):
        """ Add removal request for nzbmatrix bookmark """
        if 'nzbmatrix.com' in url and cfg.matrix_del_bookmark():
            url = url.replace('download.php?', 'bookmarks.php?action=remove&')
            self.queue.put((url, None, _RETRIES))

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
            url = url.replace(' ', '')

            try:
                del_bookmark = not future_nzo
                if future_nzo:
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
                if del_bookmark:
                    logging.info('Removing nzbmatrix bookmark %s', matrix_id)
                else:
                    logging.info('Grabbing URL %s', url)
                opener = urllib.FancyURLopener({})
                opener.prompt_user_passwd = None
                opener.addheaders = []
                opener.addheader('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__)
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
                    fn, msg, retry = _analyse_matrix(fn, matrix_id)
                    category = _MATRIX_MAP.get(category, category)
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

                if del_bookmark:
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
                    res = dirscanner.ProcessSingleFile(filename, fn, pp=pp, script=script, cat=cat, priority=priority, \
                                                       nzbname=nzbname, nzo_info=nzo_info, url=future_nzo.url)
                    if res == 0:
                        NzbQueue.do.remove(future_nzo.nzo_id, add_to_history=False)
                    elif res == -2:
                        self.add(url, future_nzo)
                    elif matrix_id and length > 0:
                        # Keep retrying NzbMatrix forever (if file not empty)
                        self.add(url, future_nzo)
                    else:
                        misc.bad_fetch(future_nzo, url, retry=True, content=True)
                # Check if a supported archive
                else:
                    if dirscanner.ProcessArchiveFile(filename, fn, pp, script, cat, priority=priority, url=future_nzo.url) == 0:
                        NzbQueue.do.remove(future_nzo.nzo_id, add_to_history=False)
                    else:
                        # Not a supported filetype, not an nzb (text/html ect)
                        try:
                            os.remove(fn)
                        except:
                            pass
                        misc.bad_fetch(future_nzo, url, retry=True, content=True)
            except:
                logging.error('URLGRABBER CRASHED', exc_info=True)
                logging.debug("URLGRABBER Traceback: ", exc_info=True)


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
            url = '%s://api.nzbmatrix.com/v1.1/download.php?id=%s&username=%s&apikey=%s' % \
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
        wait = 0
        # Check for daily limit
        if 'daily_limit' in data:
            # Daily limit reached, just wait 2 minutes before trying again
            wait = 120
        else:
            # Check if we are required to wait - if so sleep the urlgrabber
            m = _RE_MATRIX_ERR.search(data)
            if m:
                wait = int(m.group(1))
            else:
                # Clear error message, don't retry
                msg = Ta('Problem accessing nzbmatrix server (%s)') % data
                return (None, msg, False)
        if wait:
            wait = min(wait, 120)
            logging.debug('Sleeping URL grabber %s sec', wait)
            time.sleep(wait)
            # Return, but tell the urlgrabber to retry
            return (None, msg, True)

    if data.startswith("<!DOCTYPE"):
        # We got HTML, probably a temporary problem, keep trying
        msg = Ta('Invalid nzbmatrix report number %s') % matrix_id
        return (None, msg, True)

    return fn, msg, False


#------------------------------------------------------------------------------
_MATRIX_MAP = {
'28' : 'anime.all',
'20' : 'apps.linux',
'19' : 'apps.mac',
'21' : 'apps.other',
'18' : 'apps.pc',
'55' : 'apps.phone',
'52' : 'apps.portable',
'53' : 'documentaries.hd',
'9'  : 'documentaries.std',
'16' : 'games.dreamcast',
'45' : 'games.ds',
'46' : 'games.gamecube',
'17' : 'games.other',
'10' : 'games.pc',
'15' : 'games.ps1',
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
'3'  : 'movies.svcd/vcd',
'48' : 'movies.wmv-hd',
'24' : 'music.dvd',
'23' : 'music.lossless',
'22' : 'music.mp3, albums',
'47' : 'music.mp3, singles',
'27' : 'music.other',
'25' : 'music.video',
'49' : 'other.audio, books',
'36' : 'other.e-books',
'33' : 'other.emulation',
'39' : 'other.extra, pars/fills',
'37' : 'other.images',
'38' : 'other.mobile, phone',
'40' : 'other.other',
'34' : 'other.ppc/pda',
'26' : 'other.radio',
'6'  : 'tv.divx/xvid',
'5'  : 'tv.dvd',
'41' : 'tv.hd',
'8'  : 'tv.other',
'7'  : 'tv.sport/ent'
}
