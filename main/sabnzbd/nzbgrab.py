"""
sabnzbd.nzbgrab -  basend on grabnzb.py v0.4 by
                   Freddie (freddie@madcowdisease.org)
"""

__NAME__ = "nzbgrab"

import httplib
import urllib
import time
import logging
import re

from threading import Lock

LOCK = Lock()
COOKIE = None
QUOTA = None
MATCHER = re.compile(r"Post Information.*Category:.*?href.*?>(.*?)" + \
                     "<.*?href.*?>(.*?)<.*?Upload Time", re.DOTALL)
                     
LIMIT_MATCHER = re.compile(r"<dt>Downloaded NZBs:</dt>.<dd>(\d*)", re.DOTALL)
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
def grabnzb(msgid, username_newzbin, password_newzbin):
    global QUOTA
    
    # See if we have to login
    logging.info('[%s] Checking auth cookie...', __NAME__)
    
    # Fetches cookie if necessary (synchronized)
    phpsessid = _get_phpsessid(username_newzbin, password_newzbin)
    
    if phpsessid:
            logging.info('[%s] Auth cookie successfully loaded', __NAME__)
    else:
        return (None, None, None, None)
            
    headers = {
         'Referer': 'http://www.newzbin.com',
         'User-Agent': 'grabnzb.py',
    }
    
    # Add our cookie for later attempts
    headers['Cookie'] = 'PHPSESSID=%s' % (phpsessid)
    
    # Off we go then
    conn = httplib.HTTPConnection('www.newzbin.com')
    
    logging.info('[%s] Checking NZB #%s...', __NAME__, msgid)
    
    # Reset the headers we care about
    if 'Content-type' in headers:
        del headers['Content-type']
    headers['Referer'] = 'http://www.newzbin.com'
    
    # Go fetch
    browseurl = 'http://www.newzbin.com/browse/post/%s/' % msgid
    conn.request('GET', browseurl, headers=headers)
    response = conn.getresponse()
    
    # Save debug info if we have to
    data = response.read()
    
    match = re.search(LIMIT_MATCHER, data)
    if match:
        try:
            QUOTA = int(match.group(1))
        except:
            pass
            
    match = re.search(MATCHER, data)
    cat_root = None
    cat_tail = None
    
    if match:
        try:
            cat_root = match.group(1)
            cat_tail = match.group(2)
        except:
            cat_root = None
            cat_tail = None
            
    # Ruh-roh
    if data.find('The specified post does not exist.') >= 0:
        logging.warning('[%s] Post not found!', __NAME__)
        return (None, None, None, None)
    elif data.find('No files attached') >= 0:
        logging.warning('[%s] No files attached', __NAME__)
        return (None, None, None, None)
    elif data.find('you must be logged in') >= 0:
        logging.warning('[%s] Not logged in?', __NAME__)
        return (None, None, None, None)
        
    # Build our huge post data string
    postdata = { 'msgidlist': 'Get Message-IDs' }
        
    # Find all of the attached files :0
    chunks = _find_chunks(data, ')" type="checkbox" name="',
                        '" checked="checked"')
    for chunk in chunks:
        if chunk.isdigit():
            postdata[chunk] = 'on'
        
    # Oops, no files here
    if len(postdata) == 1:
        logging.warning('[%s] No files found!', __NAME__)
        return (None, None, None, None)
    
    postdata = urllib.urlencode(postdata)
    
    # Grab it
    logging.warning('[%s] Fetching %s', __NAME__, msgid)
    
    # Fake some referer here too
    headers['Content-type'] = 'application/x-www-form-urlencoded'
    headers['Referer'] = browseurl
    
    fetchurl = 'http://www.newzbin.com/database/post/edit/?ps_id=%s' % msgid
    conn.request('POST', fetchurl, postdata, headers)
    response = conn.getresponse()
    
    # Save debug info if we have to
    data = response.read()
        
    # Follow the redirect again
    del headers['Content-type']
    headers['Referer'] = fetchurl
    location = response.getheader('Location')
    if not location or not location.startswith('http://www.newzbin.com/'):
        logging.info('[%s] Not using redirect', __NAME__)
        
    elif location or location.startswith('http://www.newzbin.com/'):
        conn.request('GET', location, headers=headers)
        response = conn.getresponse()
        data = response.read()
         
    # Get the filename
    cd = response.getheader('Content-Disposition')
    n = cd.find('filename=')
    if n >= 0:
        newname = cd[n+9:]
    # Or just make one up
    else:
        newname = 'msgid_%s.nzb' % msgid
    logging.info('[%s] Successfully fetched %s', __NAME__, newname)
    
    return (newname, data, cat_root, cat_tail)
    
################################################################################
# 'Private' Methods                                                            #
################################################################################
# Check our cookie, possibly returning the session id
def _check_cookie(cookie):
    expiretime = _find_chunk(cookie, 'expires=', ' GMT')
    
    # Merged in from grabnzb v0.5
    # Sun, 08-Aug-2004 08:57:42
    try:
        t = time.strptime(expiretime, '%a, %d-%b-%Y %H:%M:%S')
    except ValueError:
        # Sun, 08 Aug 2004 08:57:42 (ARGH)
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


# Search through text, finding the chunk between start and end.
def _find_chunk(text, start, end, pos=None):
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

# As above, but return all matches. Poor man's regexp :)
def _find_chunks(text, start, end, limit=0):
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
    # Fetch the URL!
    
    headers = {
         'Referer': 'http://www.newzbin.com',
         'User-Agent': 'SABnzbd',
    }
    
    conn = httplib.HTTPConnection('www.newzbin.com')
    
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
    if not location or not location.startswith('http://www.newzbin.com/'):
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
