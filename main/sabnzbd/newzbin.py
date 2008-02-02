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

from threading import Lock

import sabnzbd
from sabnzbd.constants import *

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


################################################################################
# 'Public' Methods                                                             #
################################################################################
class Bookmarks:
    """ Get list of bookmarks from www.newzbin.com
    """
    def __init__(self, username, password, opts):
        self.username = username
        self.password = password
        self.opts = opts
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
             'User-Agent': 'grabnzb.py',
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
                            sabnzbd.add_msgid(int(msgid), self.opts)
            self.bookmarks = new_bookmarks

    def save(self):
        sabnzbd.save_data(self.bookmarks, BOOKMARK_FILE_NAME)

    def bookmarksList(self):
        return self.bookmarks

    def del_bookmark(self, msgid):
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
