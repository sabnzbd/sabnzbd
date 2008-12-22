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
sabnzbd.newzbin - newzbin.com support functions
"""

__NAME__ = "newzbin"

import httplib
import urllib
import time
import logging
import re
import Queue
import socket
try:
    socket.ssl
    _HAVE_SSL = True
except:
    _HAVE_SSL = False

from threading import *

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.decorators import *
from sabnzbd.misc import Cat2Opts, sanitize_filename, BadFetch
from sabnzbd.nzbstuff import CatConvert
from sabnzbd.codecs import name_fixer
import sabnzbd.newswrapper
import sabnzbd.config as config

################################################################################
# Configuration Instances
################################################################################

USERNAME_NEWZBIN = config.OptionStr('newzbin', 'username')
PASSWORD_NEWZBIN = config.OptionPassword('newzbin', 'password')
NEWZBIN_BOOKMARKS = config.OptionBool('newzbin', 'bookmarks', False)
NEWZBIN_UNBOOKMARK = config.OptionBool('newzbin', 'unbookmark', False)
BOOKMARK_RATE = config.OptionNumber('newzbin', 'bookmark_rate', 60, minval=15, maxval=24*60)


################################################################################
# BOOKMARK Wrappers
################################################################################

__BOOKMARKS = None

def bookmarks_init():
    global __BOOKMARKS
    if not __BOOKMARKS:
        __BOOKMARKS = Bookmarks()


def bookmarks_save():
    global __BOOKMARKS
    if __BOOKMARKS:
        __BOOKMARKS.save()


def getBookmarksNow():
    global __BOOKMARKS
    if __BOOKMARKS:
        __BOOKMARKS.run()


def getBookmarksList():
    global __BOOKMARKS
    if __BOOKMARKS:
        return __BOOKMARKS.bookmarksList()


def delete_bookmark(msgid):
    global __BOOKMARKS
    if __BOOKMARKS and NEWZBIN_BOOKMARKS.get() and NEWZBIN_UNBOOKMARK.get():
        __BOOKMARKS.del_bookmark(msgid)


################################################################################
# Msgid Grabber Wrappers
################################################################################
__MSGIDGRABBER = None

def init_grabber():
    global __MSGIDGRABBER
    if __MSGIDGRABBER:
        __MSGIDGRABBER.__init__()
    else:
        __MSGIDGRABBER = MSGIDGrabber()


def start_grabber():
    global __MSGIDGRABBER
    if __MSGIDGRABBER:
        logging.debug('[%s] Starting msgidgrabber', __NAME__)
        __MSGIDGRABBER.start()


def stop_grabber():
    global __MSGIDGRABBER
    if __MSGIDGRABBER:
        logging.debug('Stopping msgidgrabber')
        __MSGIDGRABBER.stop()
        try:
            __MSGIDGRABBER.join()
        except:
            pass


def grab(msgid, future_nzo):
    global __MSGIDGRABBER
    if __MSGIDGRABBER:
        __MSGIDGRABBER.grab(msgid, future_nzo)


################################################################################
# DirectNZB support
################################################################################

class MSGIDGrabber(Thread):
    """ Thread for msgid-grabber queue """
    def __init__(self):
        Thread.__init__(self)
        self.queue = Queue.Queue()
        for tup in sabnzbd.NZBQ.get_msgids():
            self.queue.put(tup)
        self.shutdown = False

    def grab(self, msgid, nzo):
        logging.debug("Adding msgid %s to the queue", msgid)
        self.queue.put((msgid, nzo))

    def stop(self):
        # Put None on the queue to stop "run"
        self.shutdown = True
        self.queue.put((None, None))

    def run(self):
        """ Process the queue (including waits and retries) """
        def sleeper(delay):
            for n in range(delay):
                if not self.shutdown:
                    time.sleep(1.0)

        self.shutdown = False
        msgid = None
        while not self.shutdown:
            if not msgid:
                (msgid, nzo) = self.queue.get()
                if self.shutdown or not msgid:
                    break
            logging.debug("[%s] Popping msgid %s", __NAME__, msgid)

            filename, data, newzbin_cat, nzo_info = _grabnzb(msgid)
            if filename and data:
                filename = name_fixer(filename)

                _r, _u, _d = nzo.get_repair_opts()
                pp = sabnzbd.opts_to_pp(_r, _u, _d)
                script = nzo.get_script()
                cat = nzo.get_cat()
                if not cat:
                    cat = CatConvert(newzbin_cat)
                cat, pp, script = Cat2Opts(cat, pp, script)

                priority = nzo.get_priority()
                try:
                    sabnzbd.insert_future_nzo(nzo, filename, data, pp=pp, script=script, cat=cat, priority=priority, nzo_info=nzo_info)
                except:
                    logging.error("[%s] Failed to update newzbin job %s", __NAME__, msgid)
                    sabnzbd.remove_nzo(nzo.nzo_id, False)
                msgid = None
            else:
                if filename:
                    sleeper(int(filename))
                else:
                    # Fatal error, give up on this one
                    BadFetch(nzo, msgid, retry=False)
                    msgid = None

            # Keep some distance between the grabs
            sleeper(5)

        logging.debug('[%s] Stopping MSGIDGrabber', __NAME__)


def _grabnzb(msgid):
    """ Grab one msgid from newzbin """

    nothing  = (None, None, None, None)
    retry = (300, None, None, None)
    nzo_info = {'msgid': msgid}

    logging.info('[%s] Fetching NZB for Newzbin report #%s', __NAME__, msgid)

    headers = { 'User-Agent': 'SABnzbd', }

    # Connect to Newzbin
    try:
        if _HAVE_SSL:
            conn = httplib.HTTPSConnection('www.newzbin.com')
        else:
            conn = httplib.HTTPConnection('www.newzbin.com')

        postdata = { 'username': USERNAME_NEWZBIN.get(), 'password': PASSWORD_NEWZBIN.get(), 'reportid': msgid }
        postdata = urllib.urlencode(postdata)

        headers['Content-type'] = 'application/x-www-form-urlencoded'

        fetchurl = '/api/dnzb/'
        conn.request('POST', fetchurl, postdata, headers)
        response = conn.getresponse()
    except:
        logging.warning('[%s] Problem accessing Newzbin server, wait 5 min.', __NAME__)
        return retry

    # Save debug info if we have to
    data = response.read()

    # Get the filename
    rcode = response.getheader('X-DNZB-RCode')
    rtext = response.getheader('X-DNZB-RText')
    try:
        nzo_info['more_info'] = response.getheader('X-DNZB-MoreInfo')
    except:
        # Only some reports will generate a moreinfo header
        pass
    if not (rcode or rtext):
        logging.error("[%s] Newzbin server changed its protocol", __NAME__)
        return nothing

    # Official return codes:
    # 200 = OK, NZB content follows
    # 400 = Bad Request, please supply all parameters
    #       (this generally means reportid or fileid is missing; missing user/pass gets you a 401)
    # 401 = Unauthorised, check username/password?
    # 402 = Payment Required, not Premium
    # 404 = Not Found, data doesn't exist?
    #       (only working for reportids, see Technical Limitations)
    # 450 = Try Later, wait <x> seconds for counter to reset
    #       (for an explanation of this, see DNZB Rate Limiting)
    # 500 = Internal Server Error, please report to Administrator
    # 503 = Service Unavailable, site is currently down

    if rcode == '450':
        wait_re = re.compile('wait (\d+) seconds')
        try:
            wait = int(wait_re.findall(rtext)[0])
        except:
            wait = 60
        if wait > 60:
            wait = 60
        logging.info("Newzbin says we should wait for %s sec", wait)
        return int(wait+1), None, None

    if rcode in ('402'):
        logging.warning("[%s] You have no credit on your Newzbin account", __NAME__)
        return nothing
    
    if rcode in ('401'):
        logging.warning("[%s] Unauthorised, check your newzbin username/password", __NAME__)
        return nothing

    if rcode in ('400', '404'):
        logging.error("[%s] Newzbin report %s not found", __NAME__, msgid)
        return nothing

    if rcode in ('500', '503'):
        logging.warning('[%s] Newzbin has a server problem (%s, %s), wait 5 min.', __NAME__, rcode, rtext)
        return retry

    if rcode != '200':
        logging.error('[%s] Newzbin gives undocumented error code (%s, %s)', __NAME__, rcode, rtext)
        return nothing

    # Process data
    report_name = response.getheader('X-DNZB-Name')
    report_cat  = response.getheader('X-DNZB-Category')
    if not (report_name and report_cat):
        logging.error("[%s] Newzbin server fails to give info for %s", __NAME__, msgid)
        return nothing

    # sanitize report_name
    newname = sanitize_filename(report_name)
    if len(newname) > 80:
        newname = "%s[%s]" % (newname[0:70], id(newname))
    newname = "msgid_%s %s.nzb" % (msgid, newname.strip())

    logging.info('[%s] Successfully fetched %s (cat=%s) (%s)', __NAME__, report_name, report_cat, newname)

    return (newname, data, report_cat, nzo_info)


################################################################################
# BookMark support
################################################################################
BOOK_LOCK = Lock()

class Bookmarks:
    """ Get list of bookmarks from www.newzbin.com
    """
    def __init__(self):
        self.bookmarks = sabnzbd.load_data(BOOKMARK_FILE_NAME)
        if not self.bookmarks:
            self.bookmarks = []

    @synchronized(BOOK_LOCK)
    def run(self, delete=None):

        headers = { 'User-Agent': 'SABnzbd', }
    
        # Connect to Newzbin
        try:
            if _HAVE_SSL:
                conn = httplib.HTTPSConnection('www.newzbin.com')
            else:
                conn = httplib.HTTPConnection('www.newzbin.com')

            if delete:
                logging.info('[%s] Deleting Newzbin bookmark %s', __NAME__, delete)
                postdata = { 'username': USERNAME_NEWZBIN.get(), 'password': PASSWORD_NEWZBIN.get(), 'action': 'delete', \
                             'reportids' : delete }
            else:
                logging.info('[%s] Fetching Newzbin bookmarks', __NAME__)
                postdata = { 'username': USERNAME_NEWZBIN.get(), 'password': PASSWORD_NEWZBIN.get(), 'action': 'fetch'}
            postdata = urllib.urlencode(postdata)
    
            headers['Content-type'] = 'application/x-www-form-urlencoded'
    
            fetchurl = '/api/bookmarks/'
            conn.request('POST', fetchurl, postdata, headers)
            response = conn.getresponse()
        except:
            logging.warning('[%s] Problem accessing Newzbin server.', __NAME__)
            return
    
        data = response.read()
    
        # Get the status
        rcode = str(response.status)
    
        # Official return codes:
        # 200 = OK, NZB content follows
        # 204 = No content
        # 400 = Bad Request, please supply all parameters
        #       (this generally means reportid or fileid is missing; missing user/pass gets you a 401)
        # 401 = Unauthorised, check username/password?
        # 402 = Payment Required, not Premium
        # 403 = Forbidden (incorrect auth)
        # 500 = Internal Server Error, please report to Administrator
        # 503 = Service Unavailable, site is currently down
    
        if rcode == '204':
            logging.debug("[%s] No bookmarks set", __NAME__)
        elif rcode in ('401', '403'):
            logging.warning("[%s] Unauthorised, check your newzbin username/password", __NAME__)
        elif rcode in ('402'):
            logging.warning("[%s] You have no credit on your Newzbin account", __NAME__)
        elif rcode in ('500', '503'):
            logging.warning('[%s] Newzbin has a server problem (%s).', __NAME__, rcode)
        elif rcode != '200':
            logging.error('[%s] Newzbin gives undocumented error code (%s)', __NAME__, rcode)

        if rcode == '200':
            if delete:
                self.bookmarks.remove(delete)
            else:
                for line in data.split('\n'):
                    try:
                        msgid, size, text = line.split('\t', 2)
                    except:
                        msgid = size = text = None
                    if msgid and (msgid not in self.bookmarks):
                        self.bookmarks.append(msgid)
                        logging.info("[%s] Found new bookmarked msgid %s (%s)", __NAME__, msgid, text)
                        sabnzbd.add_msgid(int(msgid), None, None, priority=sabnzbd.misc.DIRSCAN_PRIORITY.get())
        self.__busy = False

    @synchronized(BOOK_LOCK)
    def save(self):
        sabnzbd.save_data(self.bookmarks, BOOKMARK_FILE_NAME)

    def bookmarksList(self):
        return self.bookmarks

    def del_bookmark(self, msgid):
        logging.debug('[%s] Try delete newzbin bookmark %s', __NAME__, msgid)
        if msgid in self.bookmarks:
            self.run(msgid)
