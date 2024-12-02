#!/usr/bin/python3 -OO
# Copyright 2008-2024 by The SABnzbd-Team (sabnzbd.org)
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

import os
import re

# Constants
VERSION_FILE = "sabnzbd/version.py"
APPDATA_FILE = "linux/org.sabnzbd.sabnzbd.appdata.xml"

# To draft a release or not to draft a release?
ON_GITHUB_ACTIONS = os.environ.get("CI", False)
RELEASE_THIS = "refs/tags/" in os.environ.get("GITHUB_REF", "")

# Import version.py without the sabnzbd overhead
with open(VERSION_FILE) as version_file:
    exec(version_file.read())
RELEASE_VERSION = __version__

# Pre-releases are longer than 6 characters (e.g. 3.1.0Beta1 vs 3.1.0, but also 3.0.11)
PRERELEASE = len(RELEASE_VERSION) > 5

# Parse the version info for Windows file properties information
version_regexed = re.search(r"(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)", RELEASE_VERSION)
RELEASE_VERSION_TUPLE = (int(version_regexed.group(1)), int(version_regexed.group(2)), int(version_regexed.group(3)), 0)
RELEASE_VERSION_BASE = f"{RELEASE_VERSION_TUPLE[0]}.{RELEASE_VERSION_TUPLE[1]}.{RELEASE_VERSION_TUPLE[2]}"

# Define release name
RELEASE_NAME = "SABnzbd-%s" % RELEASE_VERSION
RELEASE_TITLE = "SABnzbd %s" % RELEASE_VERSION
RELEASE_SRC = RELEASE_NAME + "-src.tar.gz"
RELEASE_BINARY = RELEASE_NAME + "-win64-bin.zip"
RELEASE_INSTALLER = RELEASE_NAME + "-win-setup.exe"
RELEASE_MACOS = RELEASE_NAME + "-osx.dmg"
RELEASE_README = "README.mkd"

# Used in package.py and SABnzbd.spec
EXTRA_FILES = [
    RELEASE_README,
    "README.txt",
    "INSTALL.txt",
    "LICENSE.txt",
    "GPL2.txt",
    "GPL3.txt",
    "COPYRIGHT.txt",
    "ISSUES.txt",
]
EXTRA_FOLDERS = [
    "scripts/",
    "licenses/",
    "locale/",
    "email/",
    "interfaces/Glitter/",
    "interfaces/wizard/",
    "interfaces/Config/",
    "scripts/",
    "icons/",
]
