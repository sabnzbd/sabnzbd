#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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
tests.conftest - Setup pytest fixtures
These have to be separate otherwise SABnzbd is started multiple times!
"""
import shutil
import subprocess
import sys

from tests.testhelper import *


@pytest.fixture(scope="session")
def start_sabnzbd():
    # Remove cache if already there
    if os.path.isdir(SAB_CACHE_DIR):
        shutil.rmtree(SAB_CACHE_DIR)

    # Copy basic config file with API key
    os.makedirs(SAB_CACHE_DIR, exist_ok=True)
    shutil.copyfile(os.path.join(SAB_BASE_DIR, "sabnzbd.basic.ini"), os.path.join(SAB_CACHE_DIR, "sabnzbd.ini"))

    # Check if we have language files
    if not os.path.exists(os.path.join(SAB_BASE_DIR, "..", "locale")):
        # Compile and wait to complete
        lang_command = "%s %s/../tools/make_mo.py" % (sys.executable, SAB_BASE_DIR)
        subprocess.Popen(lang_command.split()).communicate(timeout=30)

        # Check if it exists now, fail otherwise
        if not os.path.exists(os.path.join(SAB_BASE_DIR, "..", "locale")):
            raise FileNotFoundError("Failed to compile language files")

    # Start SABnzbd and continue
    sab_command = "%s %s/../SABnzbd.py --new -l2 -s %s:%s -b0 -f %s" % (
        sys.executable,
        SAB_BASE_DIR,
        SAB_HOST,
        SAB_PORT,
        SAB_CACHE_DIR,
    )
    subprocess.Popen(sab_command.split())

    # Wait for SAB to respond
    for _ in range(10):
        try:
            get_url_result()
            # Woohoo, we're up!
            break
        except requests.ConnectionError:
            time.sleep(1)
    else:
        # Make sure we clean up
        shutdown_sabnzbd()
        raise requests.ConnectionError()

    # How we run the tests
    yield True

    # Shutdown SABnzbd gracefully
    shutdown_sabnzbd()


def shutdown_sabnzbd():
    # Graceful shutdown request
    try:
        get_url_result("shutdown")
    except requests.ConnectionError:
        pass

    # Takes a second to shutdown
    for x in range(10):
        try:
            shutil.rmtree(SAB_CACHE_DIR)
            break
        except OSError:
            print("Unable to remove cache dir (try %d)" % x)
            time.sleep(1)
