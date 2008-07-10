#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License V2
# as published by the Free Software Foundation.
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
from sabnzbd.misc import Cat2OptsDef, sanitize_filename, BadFetch
from sabnzbd.nzbstuff import CatConvert
import sabnzbd.newswrapper

# Regex to find msgid in the Bookmarks page
RE_BOOKMARK = re.compile(r'<a href="/browse/post/(\d+)/">')


def InitCats():
    """ Initialise categories with newzbin categories """
    cats = ['Unknown', 'Anime', 'Apps', 'Books', 'Consoles', 'Emulation', 'Games',
            'Misc', 'Movies', 'Music', 'PDA', 'Resources', 'TV']
    cfg = sabnzbd.CFG['categories']
    for cat in cats:
        lcat = cat.lower()
        cfg[lcat] = {}
        cfg[lcat]['newzbin'] = cat
        cfg[lcat]['dir'] = cat


def IsNewzbin(uri):
    """ Return True if URI points to newzbin.com """
    return uri.find('newzbin') > 0 or uri.find('newzxxx') > 0



################################################################################
# DirectNZB support
################################################################################

class MSGIDGrabber(Thread):
    """ Thread for msgid-grabber queue """
    def __init__(self, nzbun, nzbpw):
        Thread.__init__(self)
        self.nzbun = nzbun
        self.nzbpw = nzbpw
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

            filename, data, cat = _grabnzb(msgid, self.nzbun, self.nzbpw)
            if filename and data:
                cat = CatConvert(cat)                    
                try:
                    cat, name, pp, script = Cat2OptsDef(filename, cat)
                    sabnzbd.insert_future_nzo(nzo, name, data, pp=pp, script=script, cat=cat)
                except:
                    logging.error("[%s] Failed to update newzbin job %s", __NAME__, msgid)
                    sabnzbd.remove_nzo(nzo.nzo_id, False)
                msgid = None
            else:
                if filename:
                    sleeper(int(filename))
                else:
                    # Fatal error, give up on this one
                    BadFetch(nzo, msgid)
                    msgid = None

            # Keep some distance between the grabs
            sleeper(5)

        logging.debug('[%s] Stopping MSGIDGrabber', __NAME__)


def _grabnzb(msgid, username_newzbin, password_newzbin):
    """ Grab one msgid from newzbin """

    nothing  = (None, None, None)
    retry = (300, None, None)

    logging.info('[%s] Fetching NZB for Newzbin report #%s', __NAME__, msgid)

    headers = { 'User-Agent': 'SABnzbd', }

    # Connect to Newzbin
    try:
        if _HAVE_SSL:
            conn = httplib.HTTPSConnection('www.newzbin.com')
        else:
            conn = httplib.HTTPConnection('www.newzbin.com')

        postdata = { 'username': username_newzbin, 'password': password_newzbin, 'reportid': msgid }
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

    return (newname, data, report_cat)


################################################################################
# BookMark support
################################################################################
BOOK_LOCK = Lock()

class Bookmarks:
    """ Get list of bookmarks from www.newzbin.com
    """
    def __init__(self, username, password):
        self.username = username
        self.password = password
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
                postdata = { 'username': self.username, 'password': self.password, 'action': 'delete', \
                             'reportids' : delete }
            else:
                logging.info('[%s] Fetching Newzbin bookmarks', __NAME__)
                postdata = { 'username': self.username, 'password': self.password, 'action': 'fetch'}
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
                        sabnzbd.add_msgid(int(msgid), sabnzbd.DIRSCAN_PP, sabnzbd.DIRSCAN_SCRIPT)
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
