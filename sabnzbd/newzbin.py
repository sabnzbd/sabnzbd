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
sabnzbd.newzbin - newzbin.com support functions
"""

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
from sabnzbd.decorators import synchronized
from sabnzbd.misc import cat_to_opts, sanitize_foldername, bad_fetch, cat_convert
from sabnzbd.encoding import name_fixer
import sabnzbd.newswrapper
import sabnzbd.nzbqueue
import sabnzbd.cfg as cfg
from sabnzbd.utils import osx


################################################################################
# DirectNZB support
################################################################################

_gFailures = 0
def _warn_user(msg):
    """ Warn user if too many soft newzbin errors occurred
    """
    global _gFailures
    _gFailures += 1
    if _gFailures > 5:
        logging.warning(msg)
        _gFailures = 0
    else:
        logging.debug(msg)

def _access_ok():
    global _gFailures
    _gFailures = 0


class MSGIDGrabber(Thread):
    """ Thread for msgid-grabber queue """
    do = None # Link to instance of thread

    def __init__(self):
        Thread.__init__(self)
        self.queue = Queue.Queue()
        for tup in sabnzbd.nzbqueue.get_msgids():
            self.queue.put(tup)
        self.shutdown = False
        MSGIDGrabber.do = self

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
                    time.sleep(1.05)

        self.shutdown = False
        msgid = None
        while not self.shutdown:
            if not msgid:
                (msgid, nzo) = self.queue.get()
                if self.shutdown or not msgid:
                    break
            logging.debug("Popping msgid %s", msgid)

            filename, data, newzbin_cat, nzo_info = _grabnzb(msgid)
            if filename and data:
                filename = name_fixer(filename)

                pp = nzo.pp
                script = nzo.script
                cat = nzo.cat
                if not cat:
                    cat = cat_convert(newzbin_cat)

                priority = nzo.priority
                nzbname = nzo.custom_name

                cat, pp, script, priority = cat_to_opts(cat, pp, script, priority)

                try:
                    sabnzbd.nzbqueue.insert_future_nzo(nzo, filename, msgid, data, pp=pp, script=script, cat=cat, priority=priority, nzbname=nzbname, nzo_info=nzo_info)
                except:
                    logging.error(Ta('Failed to update newzbin job %s'), msgid)
                    logging.info("Traceback: ", exc_info = True)
                    sabnzbd.nzbqueue.remove_nzo(nzo.nzo_id, False)
                msgid = None
            else:
                if filename:
                    sleeper(int(filename))
                else:
                    # Fatal error, give up on this one
                    bad_fetch(nzo, msgid, msg=nzo_info, retry=True)
                    msgid = None

            osx.sendGrowlMsg(T('NZB added to queue'),filename,osx.NOTIFICATION['download'])

            # Keep some distance between the grabs
            sleeper(5)

        logging.debug('Stopping MSGIDGrabber')


def _grabnzb(msgid):
    """ Grab one msgid from newzbin """

    msg = ''
    retry = (60, None, None, None)
    nzo_info = {'msgid': msgid}

    logging.info('Fetching NZB for Newzbin report #%s', msgid)

    headers = {'User-agent' : 'SABnzbd+/%s' % sabnzbd.version.__version__}

    # Connect to Newzbin
    try:
        if _HAVE_SSL:
            conn = httplib.HTTPSConnection('www.newzbin.com')
        else:
            conn = httplib.HTTPConnection('www.newzbin.com')

        postdata = { 'username': cfg.newzbin_username(), 'password': cfg.newzbin_password(), 'reportid': msgid }
        postdata = urllib.urlencode(postdata)

        headers['Content-type'] = 'application/x-www-form-urlencoded'

        fetchurl = '/api/dnzb/'
        conn.request('POST', fetchurl, postdata, headers)
        response = conn.getresponse()

        # Save debug info if we have to
        data = response.read()

    except:
        _warn_user('Problem accessing Newzbin server, wait 1 min.')
        logging.info("Traceback: ", exc_info = True)
        return retry

    # Get the filename
    rcode = response.getheader('X-DNZB-RCode')
    rtext = response.getheader('X-DNZB-RText')
    try:
        nzo_info['more_info'] = response.getheader('X-DNZB-MoreInfo')
    except:
        # Only some reports will generate a moreinfo header
        pass
    if not (rcode or rtext):
        logging.error(T('Newzbin server changed its protocol'))
        return None, None, None, None

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

    if rcode in ('500', '503'):
        _warn_user('Newzbin has a server problem (%s, %s), wait 5 min.' % (rcode, rtext))
        return retry

    _access_ok()

    if rcode == '450':
        wait_re = re.compile('wait (\d+) seconds')
        try:
            wait = int(wait_re.findall(rtext)[0])
        except:
            wait = 60
        if wait > 60:
            wait = 60
        logging.debug("Newzbin says we should wait for %s sec", wait)
        return int(wait+1), None, None, None

    if rcode in ('402'):
        msg = Ta('You have no credit on your Newzbin account')
        return None, None, None, msg

    if rcode in ('401'):
        msg = Ta('Unauthorised, check your newzbin username/password')
        return None, None, None, msg

    if rcode in ('400', '404'):
        msg = Ta('Newzbin report %s not found') % msgid
        return None, None, None, msg

    if rcode != '200':
        msg = Ta('Newzbin gives undocumented error code (%s, %s)') % (rcode, rtext)
        return None, None, None, msg

    # Process data
    report_name = response.getheader('X-DNZB-Name')
    report_cat  = response.getheader('X-DNZB-Category')
    if not (report_name and report_cat):
        msg = Ta('Newzbin server fails to give info for %s') %  msgid
        return None, None, None, msg

    # sanitize report_name
    newname = sanitize_foldername(report_name)
    if len(newname) > 80:
        newname = newname[0:79].strip('. ')
    newname += ".nzb"

    logging.info('Successfully fetched report %s - %s (cat=%s) (%s)', msgid, report_name, report_cat, newname)

    return (newname, data, report_cat, nzo_info)


################################################################################
# BookMark support
################################################################################
BOOK_LOCK = Lock()

class Bookmarks(object):
    """ Get list of bookmarks from www.newzbin.com
    """
    do = None # Link to instance

    def __init__(self):
        self.bookmarks = sabnzbd.load_admin(BOOKMARK_FILE_NAME)
        if not self.bookmarks:
            self.bookmarks = []
        self.__busy = False
        Bookmarks.do = self

    @synchronized(BOOK_LOCK)
    def run(self, delete=None):

        headers = { 'User-Agent': 'SABnzbd+/%s' % sabnzbd.__version__, }

        # Connect to Newzbin
        try:
            if _HAVE_SSL:
                conn = httplib.HTTPSConnection('www.newzbin.com')
            else:
                conn = httplib.HTTPConnection('www.newzbin.com')

            if delete:
                logging.debug('Trying to delete Newzbin bookmark %s', delete)
                postdata = { 'username': cfg.newzbin_username(), 'password': cfg.newzbin_password(), 'action': 'delete', \
                             'reportids' : delete }
            else:
                logging.info('Fetching Newzbin bookmarks')
                postdata = { 'username': cfg.newzbin_username(), 'password': cfg.newzbin_password(), 'action': 'fetch'}
            postdata = urllib.urlencode(postdata)

            headers['Content-type'] = 'application/x-www-form-urlencoded'

            fetchurl = '/api/bookmarks/'
            conn.request('POST', fetchurl, postdata, headers)
            response = conn.getresponse()
        except:
            _warn_user('Problem accessing Newzbin server.')
            logging.info("Traceback: ", exc_info = True)
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

        if rcode not in ('500', '503'):
            _access_ok()

        if rcode == '204':
            logging.debug("No bookmarks set")
        elif rcode in ('401', '403'):
            logging.warning(Ta('Unauthorised, check your newzbin username/password'))
        elif rcode in ('402'):
            logging.warning(Ta('You have no credit on your Newzbin account'))
        elif rcode in ('500', '503'):
            _warn_user('Newzbin has a server problem (%s).' % rcode)
        elif rcode == '200':
            if delete:
                if data.startswith('1'):
                    logging.info('Deleted newzbin bookmark %s', delete)
                    if delete in self.bookmarks:
                        self.bookmarks.remove(delete)
                else:
                    if delete in self.bookmarks:
                        logging.warning(Ta('Could not delete newzbin bookmark %s'), delete)
            else:
                for line in data.split('\n'):
                    try:
                        msgid, size, text = line.split('\t', 2)
                    except:
                        msgid = size = text = None
                    if msgid and (msgid not in self.bookmarks):
                        self.bookmarks.append(msgid)
                        logging.info("Found new bookmarked msgid %s (%s)", msgid, text)
                        sabnzbd.add_msgid(int(msgid), None, None, priority=None)
        else:
            logging.error(Ta('Newzbin gives undocumented error code (%s)'), rcode)

        self.__busy = False

    @synchronized(BOOK_LOCK)
    def save(self):
        sabnzbd.save_admin(self.bookmarks, BOOKMARK_FILE_NAME)

    def bookmarksList(self):
        return self.bookmarks

    def del_bookmark(self, msgid):
        if cfg.newzbin_unbookmark():
            self.run(str(msgid))
