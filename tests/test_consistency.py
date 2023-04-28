#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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

    def test_sabctools_version_match(self):
        with open("requirements.txt", "r") as reqs:
            req_version = next(req for req in pkg_resources.parse_requirements(reqs) if req.project_name == "sabctools")
            assert sabnzbd.constants.SABCTOOLS_VERSION_REQUIRED == req_version.specs[0][1]


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


@pytest.mark.skipif(os.environ.get("GITHUB_REF_NAME", "") != "develop", reason="Only check on develop branch")
@pytest.mark.usefixtures("run_sabnzbd")
class TestWiki:
    def test_added_wiki_entries(self):
        """Test that every option has a Wiki entry, and removed options are removed from the wiki"""
        wiki_diff = {}
        config_diff = {}
        for url in ("general", "switches", "special"):
            config_tree = lxml.html.fromstring(
                requests.get("http://%s:%s/config/%s/" % (SAB_HOST, SAB_PORT, url)).content
            )
            # Have to remove some decorating stuff and empty values
            config_labels = [
                label.lower().strip().strip(" ()") for label in config_tree.xpath("//fieldset//label/text()")
            ]
            config_labels = [label for label in config_labels if label]

            # Parse the version info to get the right Wiki version
            version = re.search(r"(\d+\.\d+)\.(\d+)([a-zA-Z]*)(\d*)", pkginfo.Develop(".").version).group(1)
            wiki_tree = lxml.html.fromstring(
                requests.get("https://sabnzbd.org/wiki/configuration/%s/%s" % (version, url)).content
            )

            # Special-page needs different label locator
            label_element = "code" if "special" in url else "strong"
            wiki_labels = [label.lower() for label in wiki_tree.xpath("//tbody/tr/td[1]/%s/text()" % label_element)]

            wiki_diff[url] = set(config_labels) - set(wiki_labels)
            assert not wiki_diff[url]

            # There can be a difference, for example Windows-only options are not shown on macOS
            config_diff[url] = set(wiki_labels) - set(config_labels)
            # Add print() to see this difference
