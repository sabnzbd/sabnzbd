#!/usr/bin/python3 -OO
# Copyright 2009-2020 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.utils.upload - File association functions for adding nzb files to sabnzbd
"""
import os
import logging
import urllib.request
import urllib.parse
import urllib.error

import sabnzbd.cfg as cfg
from sabnzbd.filesystem import get_ext, get_filename
from sabnzbd.constants import VALID_ARCHIVES, VALID_NZB_FILES
from sabnzbd.dirscanner import process_nzb_archive_file, process_single_nzb
from sabnzbd.misc import get_from_url


def upload_file(url, fp):
    """ Function for uploading nzbs to a running SABnzbd instance """
    try:
        fp = urllib.parse.quote_plus(fp)
        url = "%s&mode=addlocalfile&name=%s" % (url, fp)
        # Add local API-key if it wasn't already in the registered URL
        apikey = cfg.api_key()
        if apikey and "apikey" not in url:
            url = "%s&apikey=%s" % (url, apikey)
        if "apikey" not in url:
            # Use alternative login method
            username = cfg.username()
            password = cfg.password()
            if username and password:
                url = "%s&ma_username=%s&ma_password=%s" % (url, username, password)
        get_from_url(url)
    except:
        logging.error("Failed to upload file: %s", fp)
        logging.info("Traceback: ", exc_info=True)


def add_local(f):
    """ Function for easily adding nzb/zip/rar/nzb.gz to SABnzbd """
    if os.path.exists(f):
        fn = get_filename(f)
        if fn:
            if get_ext(fn) in VALID_ARCHIVES:
                process_nzb_archive_file(fn, f, keep=True)
            elif get_ext(fn) in VALID_NZB_FILES:
                process_single_nzb(fn, f, keep=True)
        else:
            logging.error("Filename not found: %s", f)
    else:
        logging.error("File not found: %s", f)
