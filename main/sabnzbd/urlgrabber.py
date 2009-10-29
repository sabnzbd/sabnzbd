#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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
import sys
import time
import re
import logging
import Queue
import urllib, urllib2
import cookielib
import tempfile
from threading import *

import socket
try:
    socket.ssl
    _HAVE_SSL = True
except:
    _HAVE_SSL = False

import sabnzbd
import sabnzbd.misc as misc
import sabnzbd.dirscanner as dirscanner
import sabnzbd.nzbqueue as nzbqueue
import sabnzbd.cfg as cfg
from sabnzbd.lang import T

#------------------------------------------------------------------------------
# Wrapper functions

__GRABBER = None  # Global pointer to url-grabber instance

def init():
    global __GRABBER
    if __GRABBER:
        __GRABBER.__init__()
    else:
        __GRABBER = URLGrabber()

def start():
    global __GRABBER
    if __GRABBER: __GRABBER.start()

def add(url, future_nzo):
    global __GRABBER
    if __GRABBER: __GRABBER.add(url, future_nzo)

def stop():
    global __GRABBER
    if __GRABBER:
        __GRABBER.stop()
        try:
            __GRABBER.join()
        except:
            pass

def alive():
    global __GRABBER
    if __GRABBER:
        return __GRABBER.isAlive()
    else:
        return False



#------------------------------------------------------------------------------
class URLGrabber(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.queue = Queue.Queue()
        for tup in sabnzbd.nzbqueue.get_urls():
            self.queue.put(tup)
        self.shutdown = False

    def add(self, url, future_nzo):
        """ Add an URL to the URLGrabber queue """
        self.queue.put((url, future_nzo, 5))

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

            # Normal http fetching support
            # _grab_url cannot reside in a function, because the tempfile
            # would not survive the end of the function
            logging.info('Grabbing URL %s', url)
            opener = urllib.FancyURLopener({})
            opener.prompt_user_passwd = None
            opener.addheaders = []
            opener.addheader('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__)
            opener.addheader('Accept-encoding','gzip')
            filename = None
            try:
                fn, header = opener.retrieve(url)
            except:
                fn = None
                filename = True

            if fn:
                for tup in header.items():
                    for item in tup:
                        if "filename=" in item:
                            filename = item[item.index("filename=") + 9:].strip(';').strip('"')
                            break

            # Check if the filepath is specified, if not use the filename as whether it should be retried (bool)
            if not fn:
                retry_count -= 1
                if retry_count > 0:
                    logging.info('Retry URL %s', url)
                    self.queue.put((url, future_nzo, retry_count))
                else:
                    misc.bad_fetch(future_nzo, url, retry=filename)
                continue

            if not filename:
                filename = os.path.basename(url) + '.nzb'
            filename = misc.sanitize_foldername(filename)
            _r, _u, _d = future_nzo.get_repair_opts()
            pp = sabnzbd.opts_to_pp(_r, _u, _d)
            script = future_nzo.get_script()
            cat = future_nzo.get_cat()
            priority = future_nzo.get_priority()
            nzbname = future_nzo.get_dirname_rename()

            # Check if nzb file
            if os.path.splitext(filename)[1].lower() == '.nzb':
                res = dirscanner.ProcessSingleFile(filename, fn, pp=pp, script=script, cat=cat, priority=priority, nzbname=nzbname)
                if res == 0:
                    nzbqueue.remove_nzo(future_nzo.nzo_id, add_to_history=False, unload=True)
                elif res == -2:
                    self.add(url, future_nzo)
                else:
                    misc.bad_fetch(future_nzo, url, retry=False)
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
                    misc.bad_fetch(future_nzo, url, retry=False, archive=True)

            # Don't pound the website!
            time.sleep(5.0)



RE_NZBMATRIX = re.compile(r'(nzbmatrix).com/nzb-details.php\?id=(\d+)', re.I)

def _grab_nzbmatrix(url):
    """
    Grab one msgid from nzbmatrix
    Returns:
        path
        filename
    """

    m = RE_NZBMATRIX.search(url)
    if m and m.group(1).lower() == 'nzbmatrix' and m.group(2):
        msgid = m.group(2)
    else:
        return (None, None)

    logging.info('Fetching NZB for nzbmatrix report #%s', msgid)

    headers = {'User-agent' : 'SABnzbd+/' + sabnzbd.version.__version__}

    # Current api syntax: http://nzbmatrix.com/api-nzb-download.php?id={NZBID}&username={USERNAME}&apikey={APIKEY}
    if _HAVE_SSL:
        request_url = 'https://nzbmatrix.com/api-nzb-download.php?'
    else:
        request_url = 'http://nzbmatrix.com/api-nzb-download.php?'

    arguments = {'id': msgid, 'username': cfg.MATRIX_USERNAME.get(), 'apikey': cfg.MATRIX_APIKEY.get()}
    # NZBMatrix API does not currently support sending details over POST, so use GET instead
    request_url += urllib.urlencode(arguments)


    try:
        # Send off the download request
        logging.info('Downloading NZB: %s', request_url)
        request = urllib2.Request(request_url, headers=headers)
        response = urllib2.urlopen(request)

        # read the response into memory (could do with only reading first 80 bytes or so)
        data = response.read()

        # Check for an error response
        if data.startswith('error'):
            # Check if we are required to wait - if so sleep the urlgrabber
            if 'please_wait' in data[6:]:
                # must wait x amount of seconds
                wait = data[18:]
                if wait.isdigit():
                    time.sleep(int(wait))
                    # Return, but tell the urlgrabber to retry
                    return (None, True)
            else:
                matrix_report_error(data[6:])
                return (None, False)

        # save the filename from the headers
        filename = response.info()["Content-Disposition"].split("\"")[1]
    except:
        logging.warning(T('warn-matrixFail'))
        return (None, True)

    if data.startswith("<!DOCTYPE"):
        # We got HTML, probably an invalid report number
        logging.warning(T('warn-matrixBadRep@1'), msgid)
        return (None, False)

    # save the file to disk
    filename = os.path.basename(filename)
    root, ext = os.path.splitext(filename)

    try:
        fn, path = tempfile.mkstemp(suffix=ext, text=False)
        os.write(fn, data)
        os.close(fn)
    except:
        logging.error(T('error-tvTemp@1'), filename)
        logging.debug("Traceback: ", exc_info = True)
        path = None

    return (path, filename)

def matrix_report_error(error_msg):
    """
    Looks for the error supplied in the response form nzbmatrix and gives an appropriate error message
    # error:invalid_login = There is a problem with the username you have provided.
    # error:invalid_api = There is a problem with the API Key you have provided.
    # error:invalid_nzbid = There is a problem with the NZBid supplied.
    # error:please_wait_x = Please wait x seconds before retry.
    # error:vip_only = You need to be VIP or higher to access.
    # error:disabled_account = User Account Disabled.
    # error:x_daily_limit = You have reached the daily download limit of x.
    # error:no_nzb_found = No NZB found.
    """

    if error_msg == 'invalid_login':
        logging.warning(T('warn-matrixFail'))
    elif error_msg == 'invalid_api':
        logging.warning(T('warn-matrixFail'))
    elif error_msg == 'invalid_nzbid':
        logging.warning(T('warn-matrixFail'))
    elif error_msg == 'vip_only':
        logging.warning(T('warn-matrixFail'))
    elif error_msg == 'disabled_account':
        logging.warning(T('warn-matrixFail'))
    elif error_msg == 'daily_limit':
        logging.warning(T('warn-matrixFail'))
    elif error_msg == 'no_nzb_found':
        logging.warning(T('warn-matrixFail'))
    else:
        # Unrecognised error message
        logging.warning(T('warn-matrixFail'))
