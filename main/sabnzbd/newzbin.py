#!/usr/bin/python -OO
# Copyright 2008 ShyPike <shypike@users.sourceforge.net>
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

from threading import *
from threading import Lock

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.misc import Cat2OptsDef

RE_SANITIZE = re.compile(r'[\\/><\?\*:|"]') # All forbidden file characters

LOCK = Lock()

COOKIE = None       # Last used cookie

# Regex to find msgid in the Bookmarks page
RE_BOOKMARK = re.compile(r'<a href="/browse/post/(\d+)/">')


################################################################################
# Decorators                                                                   #
################################################################################
def synchronized(func):
    def call_func(*params, **kparams):
        LOCK.acquire()
        try:
            return func(*params, **kparams)
        finally:
            LOCK.release()

    return call_func


def IsNewzbin(uri):
    """ Return True if URI points to newzbin.com """
    return uri.find('newzbin') > 0 or uri.find('newzxxx') > 0


def CatConvert(cat):
    """ Convert newzbin category to user categories
        Return unchanged if not found
    """
    newcat = cat
    if cat:
        found = False
        cat = cat.lower()
        for ucat in sabnzbd.CFG['categories']:
            try:
                newzbin = sabnzbd.CFG['categories'][ucat]['newzbin']
                if type(newzbin) != type([]):
                    newzbin = [newzbin] 
            except:
                newzbin = []
            for name in newzbin:
                if name.lower() == cat:
                    logging.debug('[%s] Convert newzbin-cat "%s" to user-cat "%s"', __NAME__, cat, ucat)
                    newcat = ucat
                    found = True
                    break
            if found: break
    return newcat
                

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
                    sabnzbd.remove_nzo(nzo.nzo_id, False)
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
        conn = httplib.HTTPSConnection('v3.newzbin.com')

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

    if rcode in ('401', '402'):
        logging.warning("[%s] You have no paid Newzbin account", __NAME__)
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

    cat = report_cat.lower()

    # sanitize report_name
    newname = RE_SANITIZE.sub('_', report_name)
    if len(newname) > 80:
        newname = "%s[%s]" % (newname[0:70], id(newname))
    newname = "msgid_%s %s.nzb" % (msgid, newname.strip())

    logging.info('[%s] Successfully fetched %s (cat=%s) (%s)', __NAME__, report_name, cat, newname)

    return (newname, data, cat)


################################################################################
# BookMark support
################################################################################
class Bookmarks:
    """ Get list of bookmarks from www.newzbin.com
    """
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.bookmarks = sabnzbd.load_data(BOOKMARK_FILE_NAME)
        if not self.bookmarks:
            self.bookmarks = []

    def run(self, delete=None):
        # See if we have to login
        logging.info('[%s] Checking auth cookie...', __NAME__)

        # Fetches cookie if necessary (synchronized)
        phpsessid = _get_phpsessid(self.username, self.password)

        if phpsessid:
                logging.info('[%s] Auth cookie successfully loaded', __NAME__)
        else:
            return (None, None, None, None)

        headers = {
             'Referer': 'https://www.newzbin.com',
             'User-Agent': 'SABnzbd',
        }

        # Add our cookie for later attempts
        headers['Cookie'] = 'PHPSESSID=%s' % (phpsessid)

        # Off we go then
        conn = httplib.HTTPSConnection('www.newzbin.com')

        logging.info('[%s] Getting the bookmarks...', __NAME__)

        # Reset the headers we care about
        if 'Content-type' in headers:
            del headers['Content-type']
        headers['Referer'] = 'https://www.newzbin.com'

        if delete:
            # Remove one bookmark
            bookmarkUrl = 'https://www.newzbin.com/account/favourites/action'
            headers['Content-type'] = "application/x-www-form-urlencoded"

            body = urllib.urlencode({ delete: 'on', 'del': 'Remove'})
            conn.request('POST', bookmarkUrl, headers=headers, body=body)
            response = conn.getresponse()
        else:
            # Go fetch all bookmarks
            bookmarkUrl = 'https://www.newzbin.com/account/favourites'
            conn.request('GET', bookmarkUrl, headers=headers)
            response = conn.getresponse()

            data = response.read()

            logging.debug("BOOKMARKS=%s", self.bookmarks)

            new_bookmarks = []
            for line in data.split('\n'):
                m= re.search(RE_BOOKMARK, line)
                if m:
                    msgid = m.group(1)
                    if msgid:
                        new_bookmarks.append(msgid)
                        if not msgid in self.bookmarks:
                            logging.info("[%s] Found new bookmarked msgid %s", __NAME__, msgid)
                            sabnzbd.add_msgid(int(msgid), sabnzbd.DIRSCAN_PP, sabnzbd.DIRSCAN_SCRIPT)
            self.bookmarks = new_bookmarks

    def save(self):
        sabnzbd.save_data(self.bookmarks, BOOKMARK_FILE_NAME)

    def bookmarksList(self):
        return self.bookmarks

    def del_bookmark(self, msgid):
        if msgid in self.bookmarks:
            self.run(msgid)

################################################################################
# 'Private' Methods                                                            #
################################################################################

def _check_cookie(cookie):
    """ Check our cookie, possibly returning the session id
    """
    expiretime = _find_chunk(cookie, 'expires=', ' GMT')

    try:
        # Day, dd-mmm-yyyy hh:mm:ss
        t = time.strptime(expiretime, '%a, %d-%b-%Y %H:%M:%S')
    except ValueError:
        # Day, dd mmm yyyy hh:mm:ss
        t = time.strptime(expiretime, '%a, %d %b %Y %H:%M:%S')

    now = time.gmtime()
    # Woops, expired
    if now > t:
        return None
    else:
        phpsessid = _find_chunk(cookie, 'PHPSESSID=', ';')
        if phpsessid is None or phpsessid == 'None':
            return None
        else:
            return phpsessid


def _find_chunk(text, start, end, pos=None):
    """ Search through text, finding the chunk between start and end.
    """
    # Can we find the start?
    if pos is None:
        startpos = text.find(start)
    else:
        startpos = text.find(start, pos)

    if startpos < 0:
        return None

    startspot = startpos + len(start)

    # Can we find the end?
    endpos = text.find(end, startspot)
    if endpos <= startspot:
        return None

    # Ok, we have some text now
    chunk = text[startspot:endpos]
    if len(chunk) == 0:
        return None

    # Return!
    if pos is None:
        return chunk
    else:
        return (endpos+len(end), chunk)


def _find_chunks(text, start, end, limit=0):
    """ As above, but return all matches. Poor man's regexp :)
    """
    chunks = []
    n = 0

    while 1:
        result = _find_chunk(text, start, end, n)
        if result is None:
            return chunks
        else:
            chunks.append(result[1])
            if limit and len(chunks) == limit:
                return chunks
            n = result[0]


def _fetch_cookie(username_newzbin, password_newzbin):
    """ Get the cookie
    """

    headers = {
         'Referer': 'https://www.newzbin.com',
         'User-Agent': 'SABnzbd',
    }

    conn = httplib.HTTPSConnection('www.newzbin.com')

    postdata = urllib.urlencode({'username': username_newzbin,
                                 'password': password_newzbin})
    headers['Content-type'] = 'application/x-www-form-urlencoded'
    conn.request('POST', '/account/login/', postdata, headers)

    response = conn.getresponse()

    logging.debug("[%s] Response: %s", __NAME__, response.read())

    # Try getting our cookie
    try:
        cookie = response.getheader('Set-Cookie')
    except KeyError:
        logging.warning('[%s] Login failed!', __NAME__)
        return None

    phpsessid = _check_cookie(cookie)
    if phpsessid is None:
        logging.warning('[%s] Login failed!', __NAME__)
        return None

    # Follow the redirect
    del headers['Content-type']

    location = response.getheader('Location')
    if not location or not location.startswith('https://www.newzbin.com/'):
        logging.warning('[%s] Login failed!', __NAME__)
        return None

    conn.request('GET', location, headers=headers)

    response = conn.getresponse()
    conn.close()

    if response.status == 200:
        logging.info('[%s] Login ok', __NAME__)
        return cookie

    else:
        logging.warning('[%s] Login failed!', __NAME__)
        return None

@synchronized
def _get_phpsessid(username_newzbin, password_newzbin):
    """ Get PHP Session ID
    """
    global COOKIE
    phpsessid = None

    if COOKIE:
        logging.info("[%s] Checking old cookie", __NAME__)
        phpsessid = _check_cookie(COOKIE)

    if not phpsessid:
        logging.info("[%s] Need to fetch a new cookie", __NAME__)

        COOKIE = None

        COOKIE = _fetch_cookie(username_newzbin, password_newzbin)

        if COOKIE:
            phpsessid = _check_cookie(COOKIE)

    return phpsessid
