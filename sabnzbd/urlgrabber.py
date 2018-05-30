#!/usr/bin/python -OO
# Copyright 2007-2018 The SABnzbd-Team <team@sabnzbd.org>
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
import queue
import urllib.request, urllib.error, urllib.parse
from http.client import IncompleteRead
from threading import Thread

import sabnzbd
from sabnzbd.constants import DEF_TIMEOUT, FUTURE_Q_FOLDER, VALID_NZB_FILES, Status
from sabnzbd.encoding import unicoder
import sabnzbd.misc as misc
import sabnzbd.filesystem
import sabnzbd.dirscanner as dirscanner
from sabnzbd.nzbqueue import NzbQueue
from sabnzbd.postproc import PostProcessor
import sabnzbd.cfg as cfg
import sabnzbd.emailer as emailer
import sabnzbd.notifier as notifier


_BAD_GZ_HOSTS = ('.zip', 'nzbsa.co.za', 'newshost.za.net')
_RARTING_FIELDS = ('x-rating-id', 'x-rating-url', 'x-rating-host', 'x-rating-video', 'x-rating-videocnt', 'x-rating-audio', 'x-rating-audiocnt',
    'x-rating-voteup', 'x-rating-votedown', 'x-rating-spam', 'x-rating-confirmed-spam', 'x-rating-passworded', 'x-rating-confirmed-passworded')


class URLGrabber(Thread):
    do = None  # Link to instance of the thread

    def __init__(self):
        Thread.__init__(self)
        self.queue = queue.Queue()
        for tup in NzbQueue.do.get_urls():
            url, nzo = tup
            self.queue.put((url, nzo))
        self.shutdown = False
        URLGrabber.do = self

    def add(self, url, future_nzo, when=None):
        """ Add an URL to the URLGrabber queue, 'when' is seconds from now """
        if future_nzo and when:
            # Always increase counter
            future_nzo.url_tries += 1

            # Too many tries? Cancel
            if future_nzo.url_tries > cfg.max_url_retries():
                self.fail_to_history(future_nzo, url, T('Maximum retries'))
                return

            future_nzo.url_wait = time.time() + when

        self.queue.put((url, future_nzo))

    def stop(self):
        logging.info('URLGrabber shutting down')
        self.shutdown = True
        self.add(None, None)

    def run(self):
        logging.info('URLGrabber starting up')
        self.shutdown = False

        while not self.shutdown:
            (url, future_nzo) = self.queue.get()

            if not url:
                # stop signal, go test self.shutdown
                continue

            if future_nzo:
                # Re-queue when too early and still active
                if future_nzo.url_wait and future_nzo.url_wait > time.time():
                    self.add(url, future_nzo)
                    time.sleep(1.0)
                    continue
                # Paused
                if future_nzo.status == Status.PAUSED:
                    self.add(url, future_nzo)
                    time.sleep(1.0)
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

                filename = None
                category = None
                gzipped = False
                nzo_info = {}
                wait = 0
                retry = True
                fetch_request = None

                logging.info('Grabbing URL %s', url)
                try:
                    fetch_request = _build_request(url)
                except Exception as e:
                    # Cannot list exceptions here, because of unpredictability over platforms
                    error0 = str(sys.exc_info()[0]).lower()
                    error1 = str(sys.exc_info()[1]).lower()
                    logging.debug('Error "%s" trying to get the url %s', error1, url)
                    if 'certificate_verify_failed' in error1 or 'certificateerror' in error0:
                        msg = T('Server %s uses an untrusted HTTPS certificate') % ''
                        msg += ' - https://sabnzbd.org/certificate-errors'
                        retry = False
                    elif 'nodename nor servname provided' in error1:
                        msg = T('Server name does not resolve')
                        retry = False
                    elif '401' in error1 or 'unauthorized' in error1:
                        msg = T('Unauthorized access')
                        retry = False
                    elif '404' in error1:
                        msg = T('File not on server')
                        retry = False
                    elif hasattr(e, 'headers') and 'retry-after' in e.headers:
                        # Catch if the server send retry (e.headers is case-INsensitive)
                        wait = misc.int_conv(e.headers['retry-after'])

                # Check if dereference is used
                new_url = dereferring(url, fetch_request)
                if new_url:
                    self.add(new_url, future_nzo)
                    continue

                if fetch_request:
                    for hdr in fetch_request.headers:
                        try:
                            item = hdr.lower()
                            value = fetch_request.headers[hdr]
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
                        elif item == 'x-dnzb-password':
                            nzo_info['password'] = value
                        elif item == 'retry-after':
                            wait = misc.int_conv(value)

                        # Rating fields
                        if item in _RARTING_FIELDS:
                            nzo_info[item] = value

                        # Get filename from Content-Disposition header
                        if not filename and "filename=" in value:
                            filename = value[value.index("filename=") + 9:].strip(';').strip('"')

                if wait:
                    # For sites that have a rate-limiting attribute
                    msg = ''
                    retry = True
                    fetch_request = None
                elif retry:
                    fetch_request, msg, retry, wait, data = _analyse(fetch_request, url, future_nzo)

                if not fetch_request:
                    if retry:
                        logging.info('Retry URL %s', url)
                        self.add(url, future_nzo, wait)
                    else:
                        self.fail_to_history(future_nzo, url, msg)
                    continue

                if not filename:
                    filename = os.path.basename(urllib.parse.unquote(url))

                    # URL was redirected, maybe the redirect has better filename?
                    # Check if the original URL has extension
                    if url != fetch_request.url and misc.get_ext(filename) not in VALID_NZB_FILES:
                        filename = os.path.basename(urllib.parse.unquote(fetch_request.url))
                elif '&nzbname=' in filename:
                    # Sometimes the filename contains the full URL, duh!
                    filename = filename[filename.find('&nzbname=') + 9:]

                pp = future_nzo.pp
                script = future_nzo.script
                cat = future_nzo.cat
                if (cat is None or cat == '*') and category:
                    cat = misc.cat_convert(category)
                priority = future_nzo.priority
                nzbname = future_nzo.custom_name

                # process data
                if gzipped:
                    filename += '.gz'
                if not data:
                    try:
                        data = fetch_request.read()
                    except (IncompleteRead, IOError):
                        self.fail_to_history(future_nzo, url, T('Server could not complete request'))
                        fetch_request.close()
                        continue
                fetch_request.close()

                if '<nzb' in data and sabnzbd.filesystem.get_ext(filename) != '.nzb':
                    filename += '.nzb'

                # Sanitize filename first (also removing forbidden Windows-names)
                filename = sabnzbd.filesystem.sanitize_filename(filename)

                # Write data to temp file
                path = os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)
                path = os.path.join(path, filename)
                f = open(path, 'wb')
                f.write(data)
                f.close()
                del data

                # Check if nzb file
                if misc.get_ext(filename) in VALID_NZB_FILES:
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

                else:
                    # Check if a supported archive
                    status, zf, exp_ext = dirscanner.is_archive(path)
                    if status == 0:
                        if sabnzbd.filesystem.get_ext(filename) not in ('.rar', '.zip', '.7z'):
                            filename = filename + exp_ext
                            os.rename(path, path + exp_ext)
                            path = path + exp_ext

                        dirscanner.ProcessArchiveFile(filename, path, pp, script, cat, priority=priority,
                                                     nzbname=nzbname, url=future_nzo.url, keep=False,
                                                     nzo_id=future_nzo.nzo_id)
                    else:
                        # Not a supported filetype, not an nzb (text/html ect)
                        try:
                            os.remove(fetch_request)
                        except:
                            pass
                        logging.info('Unknown filetype when fetching NZB, retry after 30s %s', url)
                        self.add(url, future_nzo, 30)
            except:
                logging.error(T('URLGRABBER CRASHED'), exc_info=True)
                logging.debug("URLGRABBER Traceback: ", exc_info=True)

    def fail_to_history(self, nzo, url, msg='', content=False):
        """ Create History entry for failed URL Fetch
            msg: message to be logged
            content: report in history that cause is a bad NZB file
        """
        # Remove the "Trying to fetch" part
        if url:
            nzo.filename = url
            nzo.final_name = url.strip()

        if content:
            # Bad content
            msg = T('Unusable NZB file')
        else:
            # Failed fetch
            msg = T('URL Fetching failed; %s') % unicoder(msg)

        # Mark as failed
        nzo.status = Status.FAILED
        nzo.fail_msg = msg

        notifier.send_notification(T('URL Fetching failed; %s') % '', '%s\n%s' % (msg, url), 'other', nzo.cat)
        if cfg.email_endjob() > 0:
            emailer.badfetch_mail(msg, url)

        # Parse category to make sure script is set correctly after a grab
        nzo.cat, _, nzo.script, _ = misc.cat_to_opts(nzo.cat, script=nzo.script)

        # Add to history and run script if desired
        NzbQueue.do.remove(nzo.nzo_id, add_to_history=False)
        PostProcessor.do.process(nzo)


def _build_request(url):
    # Detect basic auth
    # Adapted from python-feedparser
    urltype, rest = urllib.parse.splittype(url)
    realhost, rest = urllib.parse.splithost(rest)
    if realhost:
        user_passwd, realhost = urllib.parse.splituser(realhost)
        if user_passwd:
            url = '%s://%s%s' % (urltype, realhost, rest)

    # Start request
    req = urllib.request.Request(url)

    # Add headers
    req.add_header('User-Agent', 'SABnzbd+/%s' % sabnzbd.version.__version__)
    if not any(item in url for item in _BAD_GZ_HOSTS):
        req.add_header('Accept-encoding', 'gzip')
    if user_passwd:
        req.add_header('Authorization', 'Basic ' + user_passwd.encode('base64').strip())
    return urllib.request.urlopen(req)


def _analyse(fetch_request, url, future_nzo):
    """ Analyze response of indexer
        returns fetch_request|None, error-message|None, retry, wait-seconds, data
    """
    data = None
    if not fetch_request or fetch_request.code != 200:
        if fetch_request:
            msg = fetch_request.msg
        else:
            msg = ''

        # Increasing wait-time in steps for standard errors
        when = DEF_TIMEOUT * (future_nzo.url_tries + 1)
        logging.debug('No usable response from indexer, retry after %s sec', when)
        return None, msg, True, when, data

    return fetch_request, fetch_request.msg, False, 0, data


def dereferring(url, fetch_request):
    """ Find out if we're being diverted to another location.
        If so, return new url else None
    """
    if 'derefer.me' in url:
        _RE_DEREFER = re.compile(r'content=".*url=([^"]+)">')
        data = fetch_request.read()
        for line in data.split('\n'):
            if '<meta' in line:
                m = _RE_DEREFER.search(data)
                if m:
                    return m.group(1)
    return None


