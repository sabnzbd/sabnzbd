#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team (sabnzbd.org)
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
import logging
import queue
import urllib.request
import urllib.parse
import urllib.error
from http.client import IncompleteRead, HTTPResponse
from mailbox import Message
from threading import Thread
import base64
from typing import Tuple, Optional, Union, List, Dict, Any

import sabnzbd
from sabnzbd.constants import DEF_TIMEOUT, FUTURE_Q_FOLDER, VALID_NZB_FILES, Status, VALID_ARCHIVES, DEFAULT_PRIORITY
import sabnzbd.misc as misc
import sabnzbd.filesystem
import sabnzbd.cfg as cfg
import sabnzbd.emailer as emailer
import sabnzbd.notifier as notifier
from sabnzbd.encoding import ubtou, utob
from sabnzbd.nzbparser import AddNzbFileResult
from sabnzbd.nzbstuff import NzbObject, NzbRejected, NzbRejectToHistory


class URLGrabber(Thread):
    def __init__(self):
        super().__init__()
        self.queue: queue.Queue[Tuple[Optional[str], Optional[NzbObject]]] = queue.Queue()
        self.shutdown = False

    def add(self, url: str, future_nzo: NzbObject, when: Optional[int] = None):
        """Add an URL to the URLGrabber queue, 'when' is seconds from now"""
        if future_nzo and when:
            # Always increase counter
            future_nzo.url_tries += 1

            # Too many tries? Cancel
            if future_nzo.url_tries > cfg.max_url_retries():
                self.fail_to_history(future_nzo, url, T("Maximum retries"))
                return

            future_nzo.url_wait = time.time() + when

        self.queue.put((url, future_nzo))

    def stop(self):
        self.shutdown = True
        self.queue.put((None, None))

    def run(self):
        # Read all URL's to grab from the queue
        for url_nzo_tup in sabnzbd.NzbQueue.get_urls():
            self.queue.put(url_nzo_tup)

        # Start fetching
        while not self.shutdown:
            # Set NzbObject object to None so reference from this thread
            # does not keep the object alive in the future (see #1628)
            future_nzo = None
            url, future_nzo = self.queue.get()

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

            url = url.replace(" ", "")

            try:
                if future_nzo:
                    # If nzo entry deleted, give up
                    try:
                        deleted = future_nzo.removed_from_queue
                    except AttributeError:
                        deleted = True
                    if deleted:
                        logging.debug("Dropping URL %s, job entry missing", url)
                        continue

                filename = None
                nzo_info = future_nzo.nzo_info
                wait = 0
                retry = True
                fetch_request = None

                logging.info("Grabbing URL %s", url)
                try:
                    fetch_request = _build_request(url)
                except (urllib.error.HTTPError, Exception) as e:
                    # Cannot list exceptions here, because of unpredictability over platforms
                    error0 = str(sys.exc_info()[0]).lower()
                    error1 = str(sys.exc_info()[1]).lower()
                    logging.debug('Error "%s" trying to get the url %s', error1, url)
                    if "certificate_verify_failed" in error1 or "certificateerror" in error0:
                        msg = T("Server %s uses an untrusted HTTPS certificate") % ""
                        msg += " - https://sabnzbd.org/certificate-errors"
                        retry = False
                    elif "nodename nor servname provided" in error1:
                        msg = T("Server name does not resolve")
                        retry = False
                    elif "401" in error1 or "unauthorized" in error1:
                        msg = T("Unauthorized access")
                        retry = False
                    elif "404" in error1:
                        msg = T("File not on server")
                        retry = False
                    elif hasattr(e, "headers") and "retry-after" in e.headers:
                        # Catch if the server send retry (e.headers is case-INsensitive)
                        wait = misc.int_conv(e.headers["retry-after"])

                if fetch_request:
                    for hdr in fetch_request.headers:
                        try:
                            item = hdr.lower()
                            value = fetch_request.headers[hdr]
                        except:
                            continue

                        # Skip empty values
                        if not value:
                            continue

                        if item in ("category_id", "x-dnzb-category"):
                            # Use indexer category in case no specific one was set
                            if value and future_nzo.cat in (None, "*"):
                                if indexer_cat := misc.cat_convert(value):
                                    future_nzo.cat = indexer_cat
                        elif item == "x-dnzb-moreinfo":
                            nzo_info["more_info"] = value
                        elif item == "x-dnzb-name":
                            filename = value
                            if not filename.endswith(".nzb"):
                                filename += ".nzb"
                        elif item == "x-dnzb-propername":
                            nzo_info["propername"] = value
                        elif item == "x-dnzb-episodename":
                            nzo_info["episodename"] = value
                        elif item == "x-dnzb-year":
                            nzo_info["year"] = value
                        elif item == "x-dnzb-failure":
                            nzo_info["failure"] = value
                        elif item == "x-dnzb-details":
                            nzo_info["details"] = value
                        elif item == "x-dnzb-password":
                            nzo_info["password"] = value
                        elif item == "retry-after":
                            wait = misc.int_conv(value)
                        elif item == "content-disposition":
                            # Get filename from Content-Disposition header
                            if not filename and "filename" in value:
                                filename = filename_from_content_disposition(value)

                if wait:
                    # For sites that have a rate-limiting attribute
                    msg = ""
                    retry = True
                    fetch_request = None
                elif retry:
                    fetch_request, msg, retry, wait, data = _analyse(fetch_request, future_nzo)

                if not fetch_request:
                    if retry:
                        logging.info("Retry URL %s", url)
                        self.add(url, future_nzo, wait)
                    else:
                        self.fail_to_history(future_nzo, url, msg)
                    continue

                if not filename:
                    filename = os.path.basename(urllib.parse.unquote(url))

                    # URL was redirected, maybe the redirect has better filename?
                    # Check if the original URL has extension
                    if (
                        url != fetch_request.geturl()
                        and sabnzbd.filesystem.get_ext(filename) not in VALID_NZB_FILES + VALID_ARCHIVES
                    ):
                        filename = os.path.basename(urllib.parse.unquote(fetch_request.geturl()))
                elif "&nzbname=" in filename:
                    # Sometimes the filename contains the full URL, duh!
                    filename = filename[filename.find("&nzbname=") + 9 :]

                # process data
                if not data:
                    try:
                        data = fetch_request.read()
                    except (IncompleteRead, IOError):
                        self.fail_to_history(future_nzo, url, T("Server could not complete request"))
                        fetch_request.close()
                        continue
                fetch_request.close()

                if b"<nzb" in data and sabnzbd.filesystem.get_ext(filename) != ".nzb":
                    filename += ".nzb"

                # Sanitize filename first (also removing forbidden Windows-names)
                filename = sabnzbd.filesystem.sanitize_filename(filename)

                # If no filename, make one
                if not filename:
                    filename = sabnzbd.filesystem.get_new_id(
                        "url", os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)
                    )

                # Write data to temp file
                path = os.path.join(cfg.admin_dir.get_path(), FUTURE_Q_FOLDER, filename)
                with open(path, "wb") as temp_nzb:
                    temp_nzb.write(data)

                # Check if nzb file
                if sabnzbd.filesystem.get_ext(filename) in VALID_ARCHIVES + VALID_NZB_FILES:
                    res, _ = sabnzbd.nzbparser.add_nzbfile(
                        path,
                        pp=future_nzo.pp,
                        script=future_nzo.script,
                        cat=future_nzo.cat,
                        priority=future_nzo.priority,
                        nzbname=future_nzo.custom_name,
                        nzo_info=nzo_info,
                        url=future_nzo.url,
                        keep=False,
                        password=future_nzo.password,
                        nzo_id=future_nzo.nzo_id,
                    )
                    if res is AddNzbFileResult.RETRY:
                        logging.info("Incomplete NZB, retry after 5 min %s", url)
                        self.add(url, future_nzo, when=300)
                    elif res is AddNzbFileResult.ERROR:
                        # Error already thrown
                        self.fail_to_history(future_nzo, url)
                    elif res is AddNzbFileResult.NO_FILES_FOUND:
                        # No NZB-files inside archive
                        self.fail_to_history(future_nzo, url, T("Empty NZB file %s") % filename)
                else:
                    logging.info("Unknown filetype when fetching NZB, retry after 30s %s", url)
                    self.add(url, future_nzo, 30)

                # Always clean up what we wrote to disk
                try:
                    sabnzbd.filesystem.remove_file(path)
                except:
                    pass
            except:
                logging.error(T("URLGRABBER CRASHED"), exc_info=True)
                logging.debug("URLGRABBER Traceback: ", exc_info=True)

    @staticmethod
    def fail_to_history(nzo: NzbObject, url: str, msg="", content=False):
        """Create History entry for failed URL Fetch
        msg: message to be logged
        content: report in history that cause is a bad NZB file
        """
        # Overwrite the "Trying to fetch" temporary name
        url = url.strip()
        nzo.filename = url
        nzo.final_name = url
        if nzo.custom_name:
            # Try to set a nice name, if available
            nzo.final_name = "%s - %s" % (nzo.custom_name, url)

        if content:
            # Bad content
            msg = T("Unusable NZB file")
        else:
            # Failed fetch
            msg = T("URL Fetching failed; %s") % msg

        # Add RSS source
        if rss_feed := nzo.nzo_info.get("RSS"):
            nzo.set_unpack_info("RSS", rss_feed, unique=True)

        # Mark as failed and set the info why
        nzo.set_unpack_info("Source", url)
        nzo.set_unpack_info("Source", msg)
        nzo.fail_msg = msg

        notifier.send_notification(T("URL Fetching failed; %s") % "", "%s\n%s" % (msg, url), "failed", nzo.cat)
        if cfg.email_endjob() > 0:
            emailer.badfetch_mail(msg, url)

        # Parse category to make sure script is set correctly after a grab
        nzo.cat, _, nzo.script, _ = misc.cat_to_opts(nzo.cat, script=nzo.script)

        # Add to history and run script if desired
        sabnzbd.NzbQueue.fail_to_history(nzo)


def _build_request(url: str) -> HTTPResponse:
    # Detect basic auth
    # Adapted from python-feedparser
    user_passwd = None
    u = urllib.parse.urlparse(url)
    if u.username is not None or u.password is not None:
        if u.username and u.password:
            user_passwd = "%s:%s" % (u.username, u.password)
        host_port = u.hostname
        if u.port:
            host_port += ":" + str(u.port)
        url = urllib.parse.urlunparse(u._replace(netloc=host_port))

    # Start request
    req = urllib.request.Request(url)

    # Add headers
    req.add_header("User-Agent", "SABnzbd/%s" % sabnzbd.__version__)
    req.add_header("Accept-encoding", "gzip")
    if user_passwd:
        req.add_header("Authorization", "Basic " + ubtou(base64.b64encode(utob(user_passwd))).strip())
    return urllib.request.urlopen(req)


def _analyse(fetch_request: HTTPResponse, future_nzo: NzbObject):
    """Analyze response of indexer
    returns fetch_request|None, error-message|None, retry, wait-seconds, data
    """
    data = None
    if not fetch_request or fetch_request.getcode() != 200:
        if fetch_request:
            msg = fetch_request.msg
        else:
            msg = ""

        # Increasing wait-time in steps for standard errors
        when = DEF_TIMEOUT * (future_nzo.url_tries + 1)
        logging.debug("No usable response from indexer, retry after %s sec", when)
        return None, msg, True, when, data

    return fetch_request, fetch_request.msg, False, 0, data


def filename_from_content_disposition(content_disposition: str) -> Optional[str]:
    """
    Extract and validate filename from a Content-Disposition header.

    Origin: https://github.com/httpie/httpie/blob/4c8633c6e51f388523ab4fa649040934402a4fc9/httpie/downloads.py#L98
    :param content_disposition: Content-Disposition value
    :type content_disposition: str
    :return: the filename if present and valid, otherwise `None`
    :example:
        filename_from_content_disposition('attachment; filename=jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz')
        should return: 'jakubroztocil-httpie-0.4.1-20-g40bd8f6.tar.gz'
    """
    if filename := Message(f"Content-Disposition: attachment; {content_disposition}").get_filename():
        # Basic sanitation
        if filename := os.path.basename(filename).lstrip(".").strip():
            return filename


def add_url(
    url: str,
    pp: Optional[Union[int, str]] = None,
    script: Optional[str] = None,
    cat: Optional[str] = None,
    priority: Optional[Union[int, str]] = None,
    nzbname: Optional[str] = None,
    password: Optional[str] = None,
    nzo_info: Optional[Dict[str, Any]] = None,
    dup_check: bool = True,
) -> Tuple[AddNzbFileResult, List[str]]:
    """Add NZB based on a URL, attributes optional"""
    if not url.lower().startswith("http"):
        return AddNzbFileResult.NO_FILES_FOUND, []

    # Generate the placeholder
    logging.debug("Creating placeholder NZO for %s", url)
    msg = T("Trying to fetch NZB from %s") % url
    result: AddNzbFileResult = AddNzbFileResult.OK
    future_nzo = None
    nzo_ids = []
    try:
        future_nzo = NzbObject(
            filename=msg,
            pp=pp,
            script=script,
            futuretype=True,
            cat=cat,
            url=url,
            priority=priority,
            password=password,
            nzbname=nzbname,
            status=Status.GRABBING,
            nzo_info=nzo_info,
            dup_check=dup_check,
        )
    except NzbRejected:
        # Rejected as duplicate
        result = AddNzbFileResult.ERROR
    except NzbRejectToHistory as err:
        # Duplicate directed to history
        sabnzbd.NzbQueue.fail_to_history(err.nzo)
        nzo_ids.append(err.nzo.nzo_id)

    # Success
    if future_nzo:
        nzo_ids.append(sabnzbd.NzbQueue.add(future_nzo))
        sabnzbd.URLGrabber.add(url, future_nzo)

    return result, nzo_ids
