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
from warnings import warn

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
def run_sabnzbd_sabnews_and_selenium(clean_cache_dir):
    """
    Start SABnzbd (with translations), SABNews and Selenium/Chromedriver, shared
    among all testcases of the pytest session. A number of key configuration
    parameters are defined in testhelper.py (SAB_* variables).
    """

    # Define a shutdown routine; directory cleanup is handled by clean_cache_dir()
    def shutdown_all():
        """ Shutdown all services """
        # Shutdown SABNews
        try:
            sabnews_process.kill()
            sabnews_process.communicate(timeout=10)
        except:
            warn("Failed to shutdown the sabnews process")

        # Shutdown Selenium/Chrome
        try:
            driver.close()
            driver.quit()
        except:
            # If something else fails, this can cause very non-informative long tracebacks
            warn("Failed to shutdown the selenium/chromedriver process")

        # Shutdown SABnzbd
        try:
            get_url_result("shutdown", SAB_HOST, SAB_PORT)
        except requests.ConnectionError:
            sabnzbd_process.kill()
            sabnzbd_process.communicate(timeout=10)
        except Exception:
            warn("Failed to shutdown the sabnzbd process")

    # Copy basic config file with API key
    os.makedirs(SAB_CACHE_DIR, exist_ok=True)
    shutil.copyfile(os.path.join(SAB_DATA_DIR, "sabnzbd.basic.ini"), os.path.join(SAB_CACHE_DIR, "sabnzbd.ini"))

    # Check if we have language files
    locale_dir = os.path.join(SAB_BASE_DIR, "..", "locale")
    if not os.path.isdir(locale_dir):
        try:
            # Language files missing; let make_mo do its thing
            make_mo = subprocess.Popen([sys.executable, os.path.join(SAB_BASE_DIR, "..", "tools", "make_mo.py")])
            make_mo.communicate(timeout=30)

            # Check the dir again, should exist now
            if not os.path.isdir(locale_dir):
                raise FileNotFoundError
        except Exception:
            pytest.fail("Failed to compile language files in %s" % locale_dir)

    # Start SABnzbd and continue
    sabnzbd_process = subprocess.Popen(
        [
            sys.executable,
            os.path.join(SAB_BASE_DIR, "..", "SABnzbd.py"),
            "--new",
            "--server",
            "%s:%s" % (SAB_HOST, str(SAB_PORT)),
            "--browser",
            "0",
            "--logging",
            "2",
            "--config",
            SAB_CACHE_DIR,
        ]
    )

    # In the meantime, start Selenium and Chrome;
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
    sabnews_process = subprocess.Popen([sys.executable, os.path.join(SAB_BASE_DIR, "sabnews.py")])

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
        shutdown_all()
        raise requests.ConnectionError()

    # Now we run the tests
    yield

    # Shutdown gracefully
    shutdown_all()


@pytest.fixture(scope="class")
def generate_fake_history(request):
    """ Add fake entries to the history db """
    history_size = randint(42, 81)
    try:
        history_db = os.path.join(SAB_CACHE_DIR, DEF_ADMIN_DIR, DB_HISTORY_NAME)
        with FakeHistoryDB(history_db) as fake_history:
            fake_history.add_fake_history_jobs(history_size)
            # Make history parameters available to the test class
            request.cls.history_category_options = fake_history.category_options
            request.cls.history_distro_names = fake_history.distro_names
            request.cls.history_size = history_size
    except Exception:
        pytest.fail("Failed to add fake entries to history db %s" % history_db)

    return


@pytest.fixture(scope="function")
def update_history_specs(request):
    """ Update the history size at the start of every test """
    if request.function.__name__.startswith("test_"):
        json = get_api_result(
            "history",
            SAB_HOST,
            SAB_PORT,
            extra_arguments={"limit": request.cls.history_size},
        )
        request.cls.history_size = len(json["history"]["slots"])

    # Test o'clock
    return
