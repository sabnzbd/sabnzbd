#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_consistency - Keep things consistent
"""

import os
import re
import pkg_resources

import sabnzbd
import pkginfo
import lxml.html
from sabnzbd.skintext import SKIN_TEXT
from tests.testhelper import *


class TestVersion:
    def test_sabnzbd_version_match(self):
        assert sabnzbd.__version__ == pkginfo.Develop(".").version


class TestSkintext:
    def test_skintext(self):
        # Make one giant string of all the text for semi-efficient search
        combined_files = ""
        for dirname, dirnames, filenames in os.walk("interfaces"):
            for filename in filenames:
                # Only .tmpl and .htm(l) files
                if ".tmpl" in filename or ".htm" in filename:
                    with open(os.path.join(dirname, filename), "r") as myfile:
                        data = myfile.read().replace("\n", "")
                    combined_files = combined_files + data

        # Items to ignore, we might use them in the future!
        to_ignore = ("sch-", "hours", "removeNZB", "purgeNZBs", "purgeQueue", "menu-home")

        # Search for translation function
        not_found = []
        for key in SKIN_TEXT:
            if "T('" + key not in combined_files and 'T("' + key not in combined_files:
                if not key.startswith(to_ignore):
                    not_found.append(key)

        # If anything shows up, the translation string is no longer used and should be removed!
        assert not not_found
