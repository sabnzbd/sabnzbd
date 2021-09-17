#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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
from random import choice, randint
import requests
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from string import ascii_lowercase, digits
from unittest import mock
from urllib3.exceptions import ProtocolError
import xmltodict

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.constants import (
    DB_HISTORY_NAME,
    DEF_ADMIN_DIR,
    DEFAULT_PRIORITY,
    FORCE_PRIORITY,
    HIGH_PRIORITY,
    INTERFACE_PRIORITIES,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    REPAIR_PRIORITY,
    Status,
)
import sabnzbd.database as db
from sabnzbd.misc import pp_to_opts

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
        def wrapper_func(*args, **kwargs):
            # Setting up as requested
            for item, val in settings_dict.items():
                getattr(cfg, item).set(val)

            # Perform test
            value = func(*args, **kwargs)

            # Reset values
            for item in settings_dict:
                getattr(cfg, item).set(getattr(cfg, item).default())
            return value

        return wrapper_func

    return set_config_decorator


def set_platform(platform):
    """Change config-values on the fly, per test"""

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


def create_nzb(nzb_dir, metadata=None):
    """Create NZB from directory using SABNews"""
    nzb_dir_full = os.path.join(SAB_DATA_DIR, nzb_dir)
    return tests.sabnews.create_nzb(nzb_dir=nzb_dir_full, metadata=metadata)


def create_and_read_nzb(nzbdir):
    """Create NZB, return data and delete file"""
    # Create NZB-file to import
    nzb_path = create_nzb(nzbdir)
    with open(nzb_path, "r") as nzb_data_fp:
        nzb_data = nzb_data_fp.read()
    # Remove the created NZB-file
    os.remove(nzb_path)
    return nzb_data


def random_name(lenghth: int = 16) -> str:
    """Shorthand to create a simple random string"""
    return "".join(choice(ascii_lowercase + digits) for _ in range(lenghth))


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
            nzo.bytes_downloaded = randint(1024, 1024 ** 4)
            nzo.md5sum = "".join(choice("abcdef" + digits) for i in range(32))
            nzo.repair_opts = pp_to_opts(choice(list(db._PP_LOOKUP.keys())))  # for "pp"
            nzo.nzo_info = {"download_time": randint(1, 10 ** 4)}
            nzo.unpack_info = {"unpack_info": "placeholder unpack_info line\r\n" * 3}
            nzo.futuretype = False  # for "report", only True when fetching an URL
            nzo.download_path = os.path.join(os.path.dirname(db.HistoryDB.db_path), "placeholder_downpath")

            # Mock time when calling add_history_db() to randomize completion times
            almost_time = mock.Mock(return_value=time.time() - randint(0, 10 ** 8))
            with mock.patch("time.time", almost_time):
                self.add_history_db(
                    nzo,
                    storage=os.path.join(os.path.dirname(db.HistoryDB.db_path), "placeholder_workdir"),
                    postproc_time=randint(1, 10 ** 3),
                    script_output="",
                    script_line="",
                )


@pytest.mark.usefixtures("run_sabnzbd", "run_sabnews_and_selenium")
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

    @staticmethod
    def selenium_wrapper(func, *args):
        """Wrapper with retries for more stable Selenium"""
        for i in range(3):
            try:
                return func(*args)
            except WebDriverException as e:
                # Try again in 2 seconds!
                time.sleep(2)
                pass
        else:
            raise e
