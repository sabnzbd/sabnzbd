#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
import urllib2
from threading import Thread

import sabnzbd
from sabnzbd.constants import FUTURE_Q_FOLDER, Status
from sabnzbd.encoding import unicoder
import sabnzbd.misc as misc
import sabnzbd.dirscanner as dirscanner
from sabnzbd.nzbqueue import NzbQueue
import sabnzbd.cfg as cfg
import sabnzbd.emailer as emailer
import sabnzbd.growler as growler


_BAD_GZ_HOSTS = ('.zip', 'nzbsa.co.za', 'newshost.za.net')


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
                # Re-queue when too early and still active

                self.add(url, future_nzo)
                continue
            url = url.replace(' ', '')

            try:
                if future_nzo:
                    # If nzo entry deleted, give up
                    try:
                        deleted = future_nzo.deleted
                    except AttributeError:
                        deleted = True
                    if deleted:
                        logging.debug('Dropping URL %s, job entry missing', url)
                        continue

                logging.info('Grabbing URL %s', url)
                req = urllib2.Request(url)
                req.add_header('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__)
                if not [True for item in _BAD_GZ_HOSTS if item in url]:
                    req.add_header('Accept-encoding', 'gzip')
                filename = None
                category = None
                gzipped = False
                nzo_info = {}
                wait = 0
                retry = True
                fn = None
                try:
                    fn = urllib2.urlopen(req)
                except:
                    # Cannot list exceptions here, because of unpredictability over platforms
                    error0 = str(sys.exc_info()[0]).lower()
                    error1 = str(sys.exc_info()[1]).lower()
                    logging.debug('Error "%s" trying to get the url %s', error1, url)
                    if 'certificate_verify_failed' in error1 or 'certificateerror' in error0:
                        msg = T('Server %s uses an untrusted HTTPS certificate') % ''
                        retry = False
                    elif 'nodename nor servname provided' in error1:
                        msg = T('Server name does not resolve')
                        retry = False
                    elif '401' in error1 or 'unauthorized' in error1:
                        msg = T('Unauthorized access')
                        retry = False

                new_url = dereferring(url, fn)
                if new_url:
                    self.add(new_url, future_nzo)
                    continue

                if fn:
                    for hdr in fn.headers:
                        try:
                            item = hdr.lower()
                            value = fn.headers[hdr]
                        except:
                            continue
                        if item in ('content-encoding',) and value == 'gzip':
                            gzipped = True
                        if item in ('category_id', 'x-dnzb-category'):
                            category = value
                        elif item in ('x-dnzb-moreinfo',):
                            nzo_info['more_info'] = value
                        elif item in ('x-dnzb-name',):
                            filename = value
                            if not filename.endswith('.nzb'):
                                filename += '.nzb'
                        elif item == 'x-dnzb-propername':
                            nzo_info['propername'] = value
                        elif item == 'x-dnzb-episodename':
                            nzo_info['episodename'] = value
                        elif item == 'x-dnzb-year':
                            nzo_info['year'] = value
                        elif item == 'x-dnzb-failure':
                            nzo_info['failure'] = value
                        elif item == 'x-dnzb-details':
                            nzo_info['details'] = value
                        elif item == 'retry-after':
                            # For NZBFinder
                            wait = misc.int_conv(value)

                        if not filename and "filename=" in value:
                            filename = value[value.index("filename=") + 9:].strip(';').strip('"')

                if wait:
                    # For sites that have a rate-limiting attribute
                    msg = ''
                    retry = True
                    fn = None
                elif retry:
                    fn, msg, retry, wait, data = _analyse(fn, url)

                if not fn:
                    if retry:
                        logging.info('Retry URL %s', url)
                        self.add(url, future_nzo, wait)
                    else:
                        bad_fetch(future_nzo, url, msg)
                    continue

                if not filename:
                    filename = os.path.basename(url) + '.nzb'

                pp = future_nzo.pp
                script = future_nzo.script
                cat = future_nzo.cat
                if (cat is None or cat == '*') and category:
                    cat = misc.cat_convert(category)
                priority = future_nzo.priority
                nzbname = future_nzo.custom_name

                # process data
                if gzipped:
                    filename = filename + '.gz'
                if not data:
                    data = fn.read()
                fn.close()

                # Write data to temp file
                path = os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)
                path = os.path.join(path, filename)
                f = open(path, 'wb')
                f.write(data)
                f.close()
                del data

                # Check if nzb file
                if os.path.splitext(filename)[1].lower() in ('.nzb', '.gz', 'bz2'):
                    res = dirscanner.ProcessSingleFile(filename, path, pp=pp, script=script, cat=cat, priority=priority,
                                                       nzbname=nzbname, nzo_info=nzo_info, url=future_nzo.url, keep=False,
                                                       nzo_id=future_nzo.nzo_id)[0]
                    if res:
                        if res == -2:
                            logging.info('Incomplete NZB, retry after 5 min %s', url)
                            when = 300
                        elif res == -1:
                            # Error, but no reason to retry. Warning is already given
                            NzbQueue.do.remove(future_nzo.nzo_id, add_to_history=False)
                            continue
                        else:
                            logging.info('Unknown error fetching NZB, retry after 2 min %s', url)
                            when = 120
                        self.add(url, future_nzo, when)
                # Check if a supported archive
                else:
                    if dirscanner.ProcessArchiveFile(filename, path, pp, script, cat, priority=priority,
                                                     nzbname=nzbname, url=future_nzo.url, keep=False,
                                                     nzo_id=future_nzo.nzo_id)[0]:
                        # Not a supported filetype, not an nzb (text/html ect)
                        try:
                            os.remove(fn)
                        except:
                            pass
                        logging.info('Unknown filetype when fetching NZB, retry after 30s %s', url)
                        self.add(url, future_nzo, 30)
            except:
                logging.error(T('URLGRABBER CRASHED'), exc_info=True)
                logging.debug("URLGRABBER Traceback: ", exc_info=True)


def _analyse(fn, url):
    """ Analyze response of indexer
        returns fn|None, error-message|None, retry, wait-seconds, data
    """
    data = None
    if not fn or fn.code != 200:
        logging.debug('No usable response from indexer, retry after 60 sec')
        if fn:
            msg = fn.msg
        else:
            msg = ''
        return None, msg, True, 60, data

    # Check for an error response
    if not fn or fn.msg != 'OK':
        logging.debug('Received nothing from indexer, retry after 60 sec')
        return None, fn.msg, True, 60, data

    if '.oznzb.com' in url and 'login?' in fn.url:
        return None, T('Unauthorized access'), False, 0, data

    return fn, fn.msg, False, 0, data


def dereferring(url, fn):
    """ Find out if we're being diverted to another location.
        If so, return new url else None
    """
    if 'derefer.me' in url:
        _RE_DEREFER = re.compile(r'content=".*url=([^"]+)">')
        data = fn.read()
        for line in data.split('\n'):
            if '<meta' in line:
                m = _RE_DEREFER.search(data)
                if m:
                    return m.group(1)
    return None


def bad_fetch(nzo, url, msg='', content=False):
    """ Create History entry for failed URL Fetch
        msg : message to be logged
        retry : make retry link in history
        content : report in history that cause is a bad NZB file
    """
    if msg:
        msg = unicoder(msg)
    else:
        msg = ''

    nzo.status = Status.FAILED

    if url:
        nzo.filename = url
        nzo.final_name = url.strip()

    if content:
        # Bad content
        msg = T('Unusable NZB file')
    else:
        # Failed fetch
        msg = T('URL Fetching failed; %s') % msg

    nzo.fail_msg = msg

    growler.send_notification(T('URL Fetching failed; %s') % '', '%s\n%s' % (msg, url), 'other')
    if cfg.email_endjob() > 0:
        emailer.badfetch_mail(msg, url)

    NzbQueue.do.remove(nzo.nzo_id, add_to_history=True)
