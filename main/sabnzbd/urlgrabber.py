#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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

__NAME__ = "urlgrabber"

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
        self.queue.put((url, future_nzo))

    def stop(self):
        logging.info('[%s] URLGrabber shutting down', __NAME__)
        self.shutdown = True
        self.queue.put((None, None))

    def run(self):
        logging.info('[%s] URLGrabber starting up', __NAME__)
        self.shutdown = False

        while not self.shutdown:
            (url, future_nzo) = self.queue.get()
            if not url:
                continue

            # If nzo entry deleted, give up
            try:
                deleted = future_nzo.deleted
            except:
                deleted = True
            if deleted:
                logging.debug('[%s] Dropping URL %s, job entry missing', __NAME__, url)
                continue

            if url.lower().find('nzbmatrix.com') > 0:
                fn, filename = _grab_nzbmatrix(url)
            else:
                # _grab_url cannot reside in a function, because the tempfile
                # would not survive the end of the function
                logging.info('[%s] Grabbing URL %s', __NAME__, url)
                opener = urllib.FancyURLopener({})
                opener.prompt_user_passwd = None
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

            if not fn:
                misc.BadFetch(future_nzo, url, retry=filename)
                continue

            if not filename:
                filename = os.path.basename(url)
            else:
                filename = misc.sanitize_foldername(filename)
            _r, _u, _d = future_nzo.get_repair_opts()
            pp = sabnzbd.opts_to_pp(_r, _u, _d)
            script = future_nzo.get_script()
            cat = future_nzo.get_cat()
            priority = future_nzo.get_priority()
            cat, pp, script = misc.Cat2Opts(cat, pp, script)


            if os.path.splitext(filename)[1].lower() == '.nzb':
                res = dirscanner.ProcessSingleFile(filename, fn, pp=pp, script=script, cat=cat, priority=priority)
                if res == 0:
                    nzbqueue.remove_nzo(future_nzo.nzo_id, add_to_history=False, unload=True)
                elif res == -2:
                    self.add(url, future_nzo)
                else:
                    misc.BadFetch(future_nzo, url, retry=False)
            else:
                if dirscanner.ProcessArchiveFile(filename, fn, pp, script, cat, priority=priority) == 0:
                    nzbqueue.remove_nzo(future_nzo.nzo_id, add_to_history=False, unload=True)
                else:
                    try:
                        os.remove(fn)
                    except:
                        pass
                    misc.BadFetch(future_nzo, url, retry=False, archive=True)

            # Don't pound the website!
            time.sleep(2.0)



#------------------------------------------------------------------------------
# Function "_grab_nzbmatrix" was contibuted by
# SABnzbd.org forum-user "ultimatejones"

RE_NZBMATRIX = re.compile(r'(nzbmatrix).com/nzb-details.php\?id=(\d+)', re.I)

def _grab_nzbmatrix(url):
    """ Grab one msgid from nzbmatrix """

    m = RE_NZBMATRIX.search(url)
    if m and m.group(1).lower() == 'nzbmatrix' and m.group(2):
        msgid = m.group(2)
    else:
        return (None, None)

    logging.info('[%s] Fetching NZB for nzbmatrix report #%s', __NAME__, msgid)

    if _HAVE_SSL:
        login_url = 'https://nzbmatrix.com/account-login.php'
        download_url = 'https://nzbmatrix.com/nzb-download.php?id=' + msgid
    else:
        login_url = 'http://nzbmatrix.com/account-login.php'
        download_url = 'http://nzbmatrix.com/nzb-download.php?id=' + msgid

    # TODO don't hardcode these
    cmn_headers = {'User-agent' : 'Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)'}

    logging.debug('[%s] Using login url: %s', __NAME__, login_url)
    logging.debug('[%s] Using download url: %s', __NAME__, download_url)

    # username and password
    login_info = {'username': cfg.USERNAME_MATRIX.get(), 'password': cfg.PASSWORD_MATRIX.get()}
    login_info_encode = urllib.urlencode(login_info)

    # create and install the cookie jar and handler so we can save the login cookie
    cj = cookielib.CookieJar()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
    urllib2.install_opener(opener)

    #create the request to login
    request = urllib2.Request(login_url, login_info_encode, cmn_headers)
    response = urllib2.urlopen(request)

    # assuming the login is successful( should through an exception if it is not)
    # create the download link
    logging.info('[%s] Downloading NZB: %s', __NAME__, download_url)

    #create the download request
    request = urllib2.Request(download_url, None, cmn_headers)

    try:
        #request the file
        response = urllib2.urlopen(request)

        # save the data from the response
        data = response.read()

        # save the filename from the headers
        filename = response.info()["Content-Disposition"].split("\"")[1]
    except:
        logging.warning('[%s] Problem accessing nzbmatrix server.', __NAME__)
        return (None, True)

    if data.startswith("<!DOCTYPE"):
        # We got HTML, probably an invalid report number
        logging.warning('[%s] Invalid nzbmatrix report number %s', __NAME__, msgid)
        return (None, False)

    # save the file to disk
    filename = os.path.basename(filename)
    root, ext = os.path.splitext(filename)

    try:
        fn, path = tempfile.mkstemp(suffix=ext, text=False)
        os.write(fn, data)
        os.close(fn)
    except:
        logging.error("[%s] Cannot create temp file for %s", __NAME__, filename)
        logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
        path = None

    return (path, filename)
