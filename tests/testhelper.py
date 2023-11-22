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
tests.testhelper - Basic helper functions
"""
import io
import os
import time
from http.client import RemoteDisconnected
from typing import BinaryIO, Optional, Dict, List

import pytest
from random import choice, randint
import requests
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from string import ascii_lowercase, digits
from unittest import mock
from urllib3.exceptions import ProtocolError
import xmltodict
import functools

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.constants import (
    DB_HISTORY_NAME,
    DEF_ADMIN_DIR,
    DEF_INI_FILE,
    DEFAULT_PRIORITY,
    FORCE_PRIORITY,
    HIGH_PRIORITY,
    INTERFACE_PRIORITIES,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    REPAIR_PRIORITY,
    Status,
    PP_LOOKUP,
)
import sabnzbd.database as db
from sabnzbd.misc import pp_to_opts
import sabnzbd.filesystem as filesystem

import tests.sabnews

SAB_HOST = "127.0.0.1"
SAB_PORT = randint(4200, 4299)
SAB_APIKEY = "apikey"
SAB_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAB_CACHE_DIR = os.path.join(SAB_BASE_DIR, "cache")
SAB_DATA_DIR = os.path.join(SAB_BASE_DIR, "data")
SAB_INCOMPLETE_DIR = os.path.join(SAB_CACHE_DIR, "Downloads", "incomplete")
SAB_COMPLETE_DIR = os.path.join(SAB_CACHE_DIR, "Downloads", "complete")
SAB_NEWSSERVER_HOST = "127.0.0.1"
SAB_NEWSSERVER_PORT = 8888


def set_config(settings_dict):
    """Change config-values on the fly, per test"""

    def set_config_decorator(func):
        @functools.wraps(func)
        def wrapper_func(*args, **kwargs):
            # Setting up as requested
            for item, val in settings_dict.items():
                getattr(cfg, item).set(val)

            # Perform test
            value = func(*args, **kwargs)

            # Reset values
            for item in settings_dict:
                getattr(cfg, item).set(getattr(cfg, item).default)
            return value

        return wrapper_func

    return set_config_decorator


def set_platform(platform):
    """Change config-values on the fly, per test"""

    def set_platform_decorator(func):
        def wrapper_func(*args, **kwargs):
            # Save original values
            is_windows = sabnzbd.WIN32
            is_macos = sabnzbd.MACOS

            # Set current platform
            if platform == "win32":
                sabnzbd.WIN32 = True
                sabnzbd.MACOS = False
            elif platform == "macos":
                sabnzbd.WIN32 = False
                sabnzbd.MACOS = True
            elif platform == "linux":
                sabnzbd.WIN32 = False
                sabnzbd.MACOS = False

            # Perform test
            value = func(*args, **kwargs)

            # Reset values
            sabnzbd.WIN32 = is_windows
            sabnzbd.MACOS = is_macos

            return value

        return wrapper_func

    return set_platform_decorator


def get_url_result(url="", host=SAB_HOST, port=SAB_PORT):
    """Do basic request to web page"""
    arguments = {"apikey": SAB_APIKEY}
    return requests.get("http://%s:%s/%s/" % (host, port, url), params=arguments).text


def get_api_result(mode, host=SAB_HOST, port=SAB_PORT, extra_arguments={}):
    """Build JSON request to SABnzbd"""
    arguments = {"apikey": SAB_APIKEY, "output": "json", "mode": mode}
    arguments.update(extra_arguments)
    r = requests.get("http://%s:%s/api" % (host, port), params=arguments)
    if arguments["output"] == "text":
        return r.text
    elif arguments["output"] == "xml":
        return xmltodict.parse(r.text)
    return r.json()


def create_nzb(nzb_dir: str, metadata: Optional[Dict[str, str]] = None) -> str:
    """Create NZB from directory using SABNews"""
    nzb_dir_full = os.path.join(SAB_DATA_DIR, nzb_dir)
    return tests.sabnews.create_nzb(nzb_dir=nzb_dir_full, metadata=metadata)


def create_and_read_nzb_fp(nzbdir: str, metadata: Optional[Dict[str, str]] = None) -> BinaryIO:
    """Create NZB, return data and delete file"""
    # Create NZB-file to import
    nzb_path = create_nzb(nzbdir, metadata)
    with open(nzb_path, "rb") as nzb_data_fp:
        nzb_data = nzb_data_fp.read()
    # Remove the created NZB-file
    os.remove(nzb_path)
    return io.BytesIO(nzb_data)


def random_name(length: int = 16) -> str:
    """Shorthand to create a simple random string"""
    return "".join(choice(ascii_lowercase + digits) for _ in range(length))


class FakeHistoryDB(db.HistoryDB):
    """
    HistoryDB class with added control of the db_path via an argument and the
    capability to generate history entries.
    """

    category_options = ["catA", "catB", "1234", "يوزنت"]
    distro_names = ["Ubuntu", "デビアン", "Gentoo_Hobby_Edition", "Красная Шляпа"]
    status_options = [
        Status.COMPLETED,
        Status.EXTRACTING,
        Status.FAILED,
        Status.MOVING,
        Status.QUICK_CHECK,
        Status.REPAIRING,
        Status.RUNNING,
        Status.VERIFYING,
    ]

    def __init__(self, db_path):
        db.HistoryDB.db_path = db_path
        super().__init__()

    def add_fake_history_jobs(self, number_of_entries=1):
        """Generate a history db with any number of fake entries"""

        for _ in range(0, number_of_entries):
            nzo = mock.Mock()

            # Mock all input build_history_info() needs
            distro_choice = choice(self.distro_names)
            distro_random = random_name()
            nzo.password = choice(["secret", ""])
            nzo.correct_password = "secret"
            nzo.final_name = "%s.%s.Linux.ISO-Usenet" % (distro_choice, distro_random)
            nzo.filename = "%s.%s.Linux-Usenet%s.nzb" % (
                (distro_choice, distro_random, "{{" + nzo.password + "}}")
                if nzo.password
                else (distro_choice, distro_random, "")
            )
            nzo.cat = choice(self.category_options)
            nzo.script = "placeholder_script"
            nzo.url = "placeholder_url"
            nzo.status = choice([Status.COMPLETED, choice(self.status_options)])
            nzo.fail_msg = "¡Fracaso absoluto!" if nzo.status == Status.FAILED else ""
            nzo.nzo_id = "SABnzbd_nzo_%s" % ("".join(choice(ascii_lowercase + digits) for i in range(8)))
            nzo.bytes_downloaded = randint(1024, 1024**4)
            nzo.md5sum = "".join(choice("abcdef" + digits) for i in range(32))
            nzo.repair, nzo.unpack, nzo.delete = pp_to_opts(choice(list(PP_LOOKUP.keys())))  # for "pp"
            nzo.nzo_info = {"download_time": randint(1, 10**4)}
            nzo.unpack_info = {"unpack_info": "placeholder unpack_info line\r\n" * 3}
            nzo.duplicate_series_key = "show/season/episode"
            nzo.futuretype = False  # for "report", only True when fetching an URL
            nzo.download_path = os.path.join(os.path.dirname(db.HistoryDB.db_path), "placeholder_downpath")

            # Mock time when calling add_history_db() to randomize completion times
            almost_time = mock.Mock(return_value=time.time() - randint(0, 10**8))
            with mock.patch("time.time", almost_time):
                self.add_history_db(
                    nzo,
                    storage=os.path.join(os.path.dirname(db.HistoryDB.db_path), "placeholder_workdir"),
                    postproc_time=randint(1, 10**3),
                    script_output="",
                    script_line="",
                )


@pytest.mark.usefixtures("run_sabnzbd", "run_sabnews_and_selenium")
class SABnzbdBaseTest:
    driver = None

    def no_page_crash(self):
        # Do a base test if CherryPy did not report test
        assert "500 Internal Server Error" not in self.driver.title

    def open_page(self, url):
        # Open a page and test for crash
        self.driver.get(url)
        self.no_page_crash()

    def scroll_to_top(self):
        self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.CONTROL + Keys.HOME)
        time.sleep(2)

    def wait_for_ajax(self):
        # We catch common nonsense errors from Selenium
        try:
            wait = WebDriverWait(self.driver, 15)
            wait.until(lambda driver_wait: self.driver.execute_script("return jQuery.active") == 0)
            wait.until(lambda driver_wait: self.driver.execute_script("return document.readyState") == "complete")
        except (RemoteDisconnected, ProtocolError):
            pass

    @staticmethod
    def selenium_wrapper(func, *args):
        """Wrapper with retries for more stable Selenium"""
        for _ in range(3):
            try:
                return func(*args)
            except WebDriverException as e:
                # Try again in 2 seconds!
                time.sleep(2)
                pass
        else:
            raise e


class DownloadFlowBasics(SABnzbdBaseTest):
    def is_server_configured(self):
        """Check if the wizard was already performed.
        If not: run the wizard!
        """
        with open(os.path.join(SAB_CACHE_DIR, DEF_INI_FILE), "r") as config_file:
            if f"[[{SAB_NEWSSERVER_HOST}]]" not in config_file.read():
                self.start_wizard()

    def start_wizard(self):
        # Language-selection
        self.open_page("http://%s:%s/sabnzbd/wizard/" % (SAB_HOST, SAB_PORT))
        self.selenium_wrapper(self.driver.find_element, By.ID, "en").click()
        self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, "button.btn.btn-default").click()

        # Fill server-info
        self.no_page_crash()
        host_inp = self.selenium_wrapper(self.driver.find_element, By.NAME, "host")
        host_inp.clear()
        host_inp.send_keys(SAB_NEWSSERVER_HOST)

        # Disable SSL for testing
        self.selenium_wrapper(self.driver.find_element, By.NAME, "ssl").click()

        # This will fail if the translations failed to compile!
        self.selenium_wrapper(self.driver.find_element, By.PARTIAL_LINK_TEXT, "Advanced Settings").click()

        # Change port
        port_inp = self.selenium_wrapper(self.driver.find_element, By.NAME, "port")
        port_inp.clear()
        port_inp.send_keys(SAB_NEWSSERVER_PORT)

        # Test server-check
        self.selenium_wrapper(self.driver.find_element, By.ID, "serverTest").click()
        self.wait_for_ajax()
        assert "Connection Successful" in self.selenium_wrapper(self.driver.find_element, By.ID, "serverResponse").text

        # Final page done
        self.selenium_wrapper(self.driver.find_element, By.ID, "next-button").click()
        self.no_page_crash()
        check_result = self.selenium_wrapper(self.driver.find_element, By.CLASS_NAME, "quoteBlock").text
        assert "http://%s:%s/sabnzbd" % (SAB_HOST, SAB_PORT) in check_result

        # Go to SAB!
        self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, ".btn.btn-success").click()
        self.no_page_crash()

    def download_nzb(self, nzb_dir: str, file_output: List[str], dir_name_as_job_name: bool = False):
        # Verify if the server was setup before we start
        self.is_server_configured()

        # Create NZB
        nzb_path = create_nzb(nzb_dir)

        # Add NZB
        if dir_name_as_job_name:
            test_job_name = os.path.basename(nzb_dir)
        else:
            test_job_name = "testfile_%s" % time.time()
        api_result = get_api_result("addlocalfile", extra_arguments={"name": nzb_path, "nzbname": test_job_name})
        assert api_result["status"]

        # Remove NZB-file
        os.remove(nzb_path)

        # See how it's doing
        self.open_page("http://%s:%s/sabnzbd/" % (SAB_HOST, SAB_PORT))

        # We wait for 20 seconds to let it complete
        for _ in range(20):
            try:
                # Locate status of our job
                status_text = self.driver.find_element(
                    By.XPATH,
                    (
                        '//div[@id="history-tab"]//tr[td/div/span[contains(text(), "%s")]]/td[contains(@class, "status")]'
                        % test_job_name
                    ),
                ).text
                # Always sleep to give it some time
                time.sleep(1)
                if status_text == "Completed":
                    break
            except WebDriverException:
                time.sleep(1)
        else:
            pytest.fail("Download did not complete")

        # Verify all files in the expected file_output are present among the completed files.
        # Sometimes par2 can also be included, but we accept that. For example when small
        # par2 files get assembled in after the download already finished (see #1509)
        for _ in range(10):
            completed_files = filesystem.globber(os.path.join(SAB_COMPLETE_DIR, test_job_name), "*")
            try:
                for filename in file_output:
                    assert filename in completed_files
                # All filenames found
                break
            except AssertionError:
                print("Expected filename %s not found in completed_files %s" % (filename, completed_files))
                # Wait a sec before trying again with a fresh list of completed files
                time.sleep(1)
        else:
            pytest.fail("Time ran out waiting for expected filenames to show up")

        # Verify if the garbage collection works (see #1628)
        # We need to give it a second to calm down and clear the variables
        time.sleep(2)
        gc_results = get_api_result("gc_stats")["value"]
        if gc_results:
            pytest.fail(f"Objects were left in memory after the job finished! {gc_results}")
