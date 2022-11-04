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
Automatically release the latest "edge" snap.
This might not be the latest commit, but it will have to do.
"""

import subprocess
from typing import List


def run_external_command(command: List[str]) -> str:
    """Wrapper to ease the use of calling external programs"""
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, _ = process.communicate()
    ret = process.wait()
    if output:
        print(output)
    if ret != 0:
        raise RuntimeError("Command returned non-zero exit code %s!" % ret)
    return output


# Read the current status
snap_status = run_external_command(["snapcraft", "status", "sabnzbd"])

if not snap_status:
    raise ValueError("No information to parse")

# To store the version and number of released items
arch = None
released_items = 0

# Parse line-by-line
for line in snap_status.splitlines():
    split_line = line.split()

    # First line has 1 extra word
    if "latest" in split_line:
        split_line.remove("latest")

    # Only care for the lines that have the revision and the arch
    if len(split_line) == 5:
        arch = split_line[0]
        if arch not in ("amd64", "arm64", "armhf"):
            # Don't care about this arch
            arch = None

    # Line that has the channel and the revision, but not the arch
    if len(split_line) == 4:
        # Do we have an arch that we care about?
        if arch and split_line[0] == "edge":
            # Release this version
            run_external_command(["snapcraft", "release", "sabnzbd", split_line[2], "stable"])
            released_items += 1

# We expect to release something, crash if not
if not released_items:
    raise ValueError("No releases updated! Is this expected?")
