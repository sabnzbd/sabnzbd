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
tests.testhelper - Basic helper functions
"""

import os
import time
from http.client import RemoteDisconnected

import pytest
import requests
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.exceptions import ProtocolError

import sabnzbd
import sabnzbd.cfg as cfg
import tests.sabnews

SAB_HOST = "localhost"
SAB_PORT = 8081
SAB_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAB_CACHE_DIR = os.path.join(SAB_BASE_DIR, "cache")
SAB_DATA_DIR = os.path.join(SAB_BASE_DIR, "data")
SAB_COMPLETE_DIR = os.path.join(SAB_CACHE_DIR, "Downloads", "complete")
SAB_NEWSSERVER_HOST = "127.0.0.1"
SAB_NEWSSERVER_PORT = 8888


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
    arguments = {"apikey": "apikey"}
    return requests.get("http://%s:%s/%s/" % (host, port, url), params=arguments).text


def get_api_result(mode, host=SAB_HOST, port=SAB_PORT, extra_arguments={}):
    """ Build JSON request to SABnzbd """
    arguments = {"apikey": "apikey", "output": "json", "mode": mode}
    arguments.update(extra_arguments)
    r = requests.get("http://%s:%s/api" % (host, port), params=arguments)
    return r.json()


def create_nzb(nzb_dir):
    """ Create NZB from directory using SABNews """
    nzb_dir_full = os.path.join(SAB_DATA_DIR, nzb_dir)
    return tests.sabnews.create_nzb(nzb_dir=nzb_dir_full)


@pytest.mark.usefixtures("start_sabnzbd_and_selenium")
class SABnzbdBaseTest:
    def no_page_crash(self):
        # Do a base test if CherryPy did not report test
        assert "500 Internal Server Error" not in self.driver.title

    def open_page(self, url):
        # Open a page and test for crash
        self.driver.get(url)
        self.no_page_crash()

    def scroll_to_top(self):
        self.driver.find_element_by_tag_name("body").send_keys(Keys.CONTROL + Keys.HOME)
        time.sleep(2)

    def wait_for_ajax(self):
        # We catch common nonsense errors from Selenium
        try:
            wait = WebDriverWait(self.driver, 15)
            wait.until(lambda driver_wait: self.driver.execute_script("return jQuery.active") == 0)
            wait.until(lambda driver_wait: self.driver.execute_script("return document.readyState") == "complete")
        except (RemoteDisconnected, ProtocolError):
            pass

    def selenium_wrapper(self, func, *args):
        """ Wrapper with retries for more stable Selenium """
        for i in range(3):
            try:
                return func(*args)
            except WebDriverException as e:
                # Try again in 2 seconds!
                time.sleep(2)
                pass
        else:
            raise e
