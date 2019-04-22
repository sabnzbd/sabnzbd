#!/usr/bin/python3 -OO
# Copyright 2007-2019 The SABnzbd-Team <team@sabnzbd.org>
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

import os
import time
import unittest
import pytest
import requests

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

import sabnzbd
import sabnzbd.cfg as cfg

SAB_HOST = "localhost"
SAB_PORT = 8081
SAB_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAB_CACHE_DIR = os.path.join(SAB_BASE_DIR, "cache")
SAB_COMPLETE_DIR = os.path.join(SAB_CACHE_DIR, "Downloads", "complete")


def set_config(settings_dict):
    """ Change config-values on the fly, per test"""

    def set_config_decorator(func):
        def wrapper_func(*args, **kwargs):
            # Setting up as requested
            for item, val in settings_dict.items():
                getattr(cfg, item).set(val)

            # Perform test
            value = func(*args, **kwargs)

            # Reset values
            for item, val in settings_dict.items():
                getattr(cfg, item).default()
            return value

        return wrapper_func

    return set_config_decorator


def set_platform(platform):
    """ Change config-values on the fly, per test"""

    def set_platform_decorator(func):
        def wrapper_func(*args, **kwargs):
            # Save original values
            is_windows = sabnzbd.WIN32
            is_darwin = sabnzbd.DARWIN

            # Set current platform
            if platform == "win32":
                sabnzbd.WIN32 = True
                sabnzbd.DARWIN = False
            elif platform == "darwin":
                sabnzbd.WIN32 = False
                sabnzbd.DARWIN = True
            elif platform == "linux":
                sabnzbd.WIN32 = False
                sabnzbd.DARWIN = False

            # Perform test
            value = func(*args, **kwargs)

            # Reset values
            sabnzbd.WIN32 = is_windows
            sabnzbd.DARWIN = is_darwin

            return value

        return wrapper_func

    return set_platform_decorator


def get_url_result(url="", host=SAB_HOST, port=SAB_PORT):
    """ Do basic request to web page """
    arguments = {"session": "apikey"}
    return requests.get("http://%s:%s/%s/" % (host, port, url), params=arguments).text


def get_api_result(mode, host=SAB_HOST, port=SAB_PORT, extra_arguments={}):
    """ Build JSON request to SABnzbd """
    arguments = {"apikey": "apikey", "output": "json", "mode": mode}
    arguments.update(extra_arguments)
    r = requests.get("http://%s:%s/api" % (host, port), params=arguments)
    return r.json()


def upload_nzb(filename, host=SAB_HOST, port=SAB_PORT):
    """ Upload file and return nzo_id reponse """
    files = {"name": open(filename, "rb")}
    arguments = {"apikey": "apikey", "mode": "addfile", "output": "json"}
    return requests.post("http://%s:%s/api" % (host, port), files=files, data=arguments).json()


@pytest.mark.usefixtures("start_sabnzbd")
class SABnzbdBaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We try Chrome, fallback to Firefox

        try:
            driver_options = ChromeOptions()
            # Headless on Appveyor/Travis
            if "CI" in os.environ:
                driver_options.add_argument("--headless")
                driver_options.add_argument("--no-sandbox")
            cls.driver = webdriver.Chrome(options=driver_options)
        except WebDriverException:
            driver_options = FirefoxOptions()
            # Headless on Appveyor/Travis
            if "CI" in os.environ:
                driver_options.headless = True
            cls.driver = webdriver.Firefox(options=driver_options)

        # Get the newsserver-info, if available
        if "SAB_NEWSSERVER_HOST" in os.environ:
            cls.newsserver_host = os.environ["SAB_NEWSSERVER_HOST"]
            cls.newsserver_user = os.environ["SAB_NEWSSERVER_USER"]
            cls.newsserver_password = os.environ["SAB_NEWSSERVER_PASSWORD"]

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()
        cls.driver.quit()

    def no_page_crash(self):
        # Do a base test if CherryPy did not report test
        self.assertNotIn("500 Internal Server Error", self.driver.title)

    def open_page(self, url):
        # Open a page and test for crash
        self.driver.get(url)
        self.no_page_crash()

    def scroll_to_top(self):
        self.driver.find_element_by_tag_name("body").send_keys(Keys.CONTROL + Keys.HOME)
        time.sleep(2)

    def wait_for_ajax(self):
        wait = WebDriverWait(self.driver, 15)
        wait.until(lambda driver_wait: self.driver.execute_script("return jQuery.active") == 0)
        wait.until(lambda driver_wait: self.driver.execute_script("return document.readyState") == "complete")
