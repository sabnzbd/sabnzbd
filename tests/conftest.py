#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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

import os
import random
import shutil
import socket
import subprocess
import sys
import time
from random import randint
from warnings import warn

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

from sabnzbd.constants import DB_HISTORY_NAME, DEF_ADMIN_DIR, DEF_INI_FILE
from tests.testhelper import (
    FakeHistoryDB,
    SAB_BASE_DIR,
    SAB_CACHE_DIR,
    SAB_DATA_DIR,
    SAB_HOST,
    SAB_NEWSSERVER_HOST,
    SAB_NEWSSERVER_PORT,
    SAB_PORT,
    SABnzbdBaseTest,
    get_api_result,
    get_url_result,
    wait_for,
)

# Re-export the shared fixtures so they are registered suite-wide. These are
# defined in testhelper.py; importing them here (in conftest) makes them
# available to every test without needing a wildcard import. The autouse
# fixtures (config_env, platform_env) are what apply the @pytest.mark.config
# and @pytest.mark.platform markers, so they must be globally visible.
from tests.testhelper import config_env, platform_env, fake_fs, sleepless  # noqa: F401


def pytest_configure(config):
    """Make randomized test parameters identical across pytest-xdist workers"""
    testrunuid = None
    workerinput = getattr(config, "workerinput", None)
    if workerinput:
        testrunuid = workerinput.get("testrunuid")
    testrunuid = testrunuid or os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if testrunuid:
        random.seed(testrunuid)


@pytest.fixture(scope="session")
def warm_up_guessit():
    """Force guessit to load its bundled config before any fake filesystem is active."""
    import guessit

    guessit.api.guessit("Warm.Up.S01E01.1080p.mkv")


@pytest.fixture(scope="session")
def compiled_language_files():
    """Ensure the gettext .mo translation files are compiled, once per session"""
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
    return locale_dir


def _port_is_open(host, port):
    """Return True if something is accepting connections on host:port"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


@pytest.fixture(scope="module")
def clean_cache_dir(request):
    # Remove cache if already there. PermissionError is retried (not swallowed):
    # on Windows a just-stopped instance can hold file handles for a moment, and
    # skipping the clean-up would leave a previous module's state behind.
    for x in range(100):
        try:
            if os.path.exists(SAB_CACHE_DIR):
                shutil.rmtree(SAB_CACHE_DIR)
            # Create an empty placeholder
            os.makedirs(SAB_CACHE_DIR)
            break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("Failed to freshen up cache dir %s" % SAB_CACHE_DIR)

    yield request

    # Best-effort cleanup. A lingering handle on Windows (from the just-stopped
    # instance, Defender, or the indexer) shouldn't fail teardown, and every
    # worker uses its own isolated cache dir, so leftovers can't leak between
    # workers. The setup phase above re-freshens the dir anyway.
    shutil.rmtree(SAB_CACHE_DIR, ignore_errors=True)


@pytest.fixture(scope="module")
def run_sabnzbd(clean_cache_dir, compiled_language_files, request):
    """Start SABnzbd (with translations). A number of key configuration parameters are defined
    in testhelper.py (SAB_* variables). Scope is set to 'module' to prevent configuration
    changes made during functional tests from causing failures in unrelated tests."""

    def shutdown_sabnzbd():
        # Shutdown SABnzbd
        try:
            get_url_result("shutdown", SAB_HOST, SAB_PORT)
        except requests.ConnectionError:
            sabnzbd_process.kill()
        except Exception as err:
            warn("Failed to shutdown the sabnzbd process: %s" % err)

        # Wait for the process to fully exit before returning. The shutdown request
        # returns as soon as it is accepted, but the instance keeps saving state to
        # the shared cache dir and holds the fixed port for a moment afterwards. The
        # next module's clean_cache_dir/start-up would otherwise race with it.
        try:
            sabnzbd_process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            sabnzbd_process.kill()
            sabnzbd_process.communicate(timeout=30)

        # The tracked PID exiting is not proof the instance is gone: SAB_PORT is a
        # single random port reused by every module in the session, and a lingering
        # instance (slow shutdown, re-exec, orphaned worker) keeps re-saving its own
        # config over the shared cache dir. That is what intermittently wipes the
        # freshly-copied module ini (e.g. dropping the converted [sorters] section).
        # Block until the port is actually free so the next module starts clean.
        if not wait_for(lambda: not _port_is_open(SAB_HOST, SAB_PORT), timeout=15):
            sabnzbd_process.kill()
            warn("Port %s:%s still in use after SABnzbd shutdown" % (SAB_HOST, SAB_PORT))

    # Allow the test file to specify what ini to load; if none given, use the basic one by default
    ini_file = getattr(request.module, "INI_FILE", "sabnzbd.basic.ini")

    # Copy basic config file with API key
    shutil.copyfile(os.path.join(SAB_DATA_DIR, ini_file), os.path.join(SAB_CACHE_DIR, DEF_INI_FILE))

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

    # Wait for SAB to respond. Also bail out early if the process died during
    # start-up, otherwise we'd keep polling a port that a stale instance may own.
    for _ in range(600):
        if sabnzbd_process.poll() is not None:
            pytest.fail("SABnzbd exited during start-up (code %s)" % sabnzbd_process.returncode)
        try:
            get_url_result()
            # Woohoo, we're up!
            break
        except requests.ConnectionError:
            time.sleep(0.05)
    else:
        # Make sure we clean up
        shutdown_sabnzbd()
        raise requests.ConnectionError()

    yield

    shutdown_sabnzbd()


@pytest.fixture(scope="session")
def run_sabnews_and_selenium(request):
    """Start SABNews and Selenium/Chromedriver, shared across the pytest session."""
    # We only try Chrome for consistent results
    driver_options = ChromeOptions()

    # Headless during CI testing
    if "CI" in os.environ:
        driver_options.browser_version = "127"
        driver_options.add_argument("--headless")
        driver_options.add_argument("--no-sandbox")

        # Useful for stability on Linux/macOS, doesn't work on Windows
        if not sys.platform.startswith("win"):
            driver_options.add_argument("--single-process")

    # Start the driver and pass it on to all the classes
    driver = webdriver.Chrome(options=driver_options)

    # Start SABNews on this worker's own host/port so parallel workers don't
    # collide on a single fixed newsserver port.
    sabnews_process = subprocess.Popen(
        [
            sys.executable,
            os.path.join(SAB_BASE_DIR, "sabnews.py"),
            "-s",
            SAB_NEWSSERVER_HOST,
            "-p",
            str(SAB_NEWSSERVER_PORT),
        ]
    )

    # Now we run the tests
    yield driver

    # Shutdown SABNews
    try:
        sabnews_process.kill()
        sabnews_process.communicate(timeout=10)
    except Exception as err:
        warn("Failed to shutdown the sabnews process: %s" % err)

    # Shutdown Selenium/Chrome
    try:
        driver.close()
        driver.quit()
    except Exception as err:
        # If something else fails, this can cause very non-informative long tracebacks
        warn("Failed to shutdown the selenium/chromedriver process: %s" % err)


@pytest.fixture(scope="class")
def generate_fake_history(request):
    """Add fake entries to the history db"""
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
    """Update the history size at the start of every test"""
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
