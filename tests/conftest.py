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

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

from tests.testhelper import *


@pytest.fixture(scope="session")
def clean_cache_dir(request):
    # Remove cache if already there
    if os.path.isdir(SAB_CACHE_DIR):
        shutil.rmtree(SAB_CACHE_DIR)

    yield request

    # Remove cache dir with retries in case it's still running
    for x in range(10):
        try:
            shutil.rmtree(SAB_CACHE_DIR)
            break
        except OSError:
            print("Unable to remove cache dir (try %d)" % x)
            time.sleep(1)


@pytest.fixture(scope="session")
def start_sabnzbd_and_selenium(clean_cache_dir):
    # Remove cache if already there
    if os.path.isdir(SAB_CACHE_DIR):
        shutil.rmtree(SAB_CACHE_DIR)

    # Copy basic config file with API key
    os.makedirs(SAB_CACHE_DIR, exist_ok=True)
    shutil.copyfile(os.path.join(SAB_DATA_DIR, "sabnzbd.basic.ini"), os.path.join(SAB_CACHE_DIR, "sabnzbd.ini"))

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

    # In the mean time, start Selenium and Chrome
    # We only try Chrome for consistent results
    driver_options = ChromeOptions()

    # Headless on Appveyor/Travis
    if "CI" in os.environ:
        driver_options.add_argument("--headless")
        driver_options.add_argument("--no-sandbox")

        # Useful for stability on Linux/macOS, doesn't work on Windows
        if not sys.platform.startswith("win"):
            driver_options.add_argument("--single-process")

        # On Linux we want to use the PPA Chrome
        # This makes sure we always match Chrome and chromedriver
        if not sys.platform.startswith(("win", "darwin")):
            driver_options.binary_location = "/usr/bin/chromium-browser"

    # Start the driver and pass it on to all the classes
    driver = webdriver.Chrome(options=driver_options)
    for item in clean_cache_dir.node.items:
        parent_class = item.getparent(pytest.Class)
        parent_class.obj.driver = driver

    # Start SABNews
    sabnews = start_sabnews()

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

    # Now we run the tests
    yield True

    # Shutdown SABNews
    try:
        sabnews.kill()
        sabnews.communicate()
    except:
        pass

    # Shutdown Selenium/Chrome
    try:
        driver.close()
        driver.quit()
    except:
        # If something else fails, this can cause very non-informative long tracebacks
        pass

    # Shutdown SABnzbd gracefully
    shutdown_sabnzbd()


def shutdown_sabnzbd():
    # Graceful shutdown request
    try:
        get_url_result("shutdown")
    except requests.ConnectionError:
        pass


def start_sabnews():
    """ Start SABNews and forget about it """
    return subprocess.Popen([sys.executable, "%s/sabnews.py" % SAB_BASE_DIR])
