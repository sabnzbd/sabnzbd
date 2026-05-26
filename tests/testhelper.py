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
tests.testhelper - Basic helper functions
"""

import io
import os
import time
import uuid
from http.client import RemoteDisconnected
from typing import BinaryIO, Optional, Callable

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
from werkzeug import Request
from werkzeug.utils import send_from_directory
from pyfakefs.fake_filesystem_unittest import Patcher
from pyfakefs.fake_filesystem import OSType
from pyfakefs.helpers import set_uid

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


@pytest.fixture(autouse=True)
def config_env(monkeypatch, request):
    """Change config-values on the fly, per test"""
    marker = request.node.get_closest_marker("config")
    if marker is None:
        # No config changes for this test
        yield
        return

    if marker.args:
        config = marker.args[0]

        if callable(config):
            if not hasattr(request.node, "callspec"):
                raise RuntimeError("Dynamic config requires parameterized test")
            config = config(request.node.callspec.params)
    else:
        if not hasattr(request.node, "callspec"):
            raise RuntimeError("@pytest.mark.config requires parameterized 'config'")
        config = request.node.callspec.params.get("config")
        if config is None:
            raise RuntimeError("Missing 'config' param for @pytest.mark.config")

    # Setting up as requested
    originals = {}
    for item, val in config.items():
        cfg_item = getattr(cfg, item)
        originals[item] = cfg_item.get()
        cfg_item.set(val)

    yield

    # Restore values
    for item, val in originals.items():
        getattr(cfg, item).set(val)


@pytest.mark.parametrize("config", [{"web_host": "0.0.0.0"}, {"web_host": "::1"}])
@pytest.mark.config()
def test_config_parametrize(config):
    for item, val in config.items():
        assert getattr(cfg, item)() == val


@pytest.mark.parametrize("web_host", ["0.0.0.0", "::1"])
@pytest.mark.config(lambda params: {"web_host": params["web_host"]})
def test_config_parametrize_dynamic(web_host):
    assert cfg.web_host() == web_host


@pytest.mark.config({"web_host": "0.0.0.0"})
def test_config_marker():
    assert cfg.web_host() == "0.0.0.0"


@pytest.fixture(autouse=True)
def platform_env(monkeypatch, request):
    """Change platform-values on the fly, per test"""
    marker = request.node.get_closest_marker("platform")
    if marker is None:
        # No platform changes for this test
        yield
        return

    if marker.args:
        platform_name = marker.args[0]

        if callable(platform_name):
            if not hasattr(request.node, "callspec"):
                raise RuntimeError("Dynamic platform requires parameterized test")
            platform_name = platform_name(request.node.callspec.params)
    else:
        if not hasattr(request.node, "callspec"):
            raise RuntimeError("@pytest.mark.platform requires parameterized 'platform'")
        platform_name = request.node.callspec.params.get("platform")
        if platform_name is None:
            raise RuntimeError("Missing 'platform' param for @pytest.mark.platform")

    if platform_name == "win32":
        monkeypatch.setattr(sabnzbd, "WINDOWS", True)
        monkeypatch.setattr(sabnzbd, "MACOS", False)
    elif platform_name == "macos":
        monkeypatch.setattr(sabnzbd, "WINDOWS", False)
        monkeypatch.setattr(sabnzbd, "MACOS", True)
    elif platform_name == "linux":
        monkeypatch.setattr(sabnzbd, "WINDOWS", False)
        monkeypatch.setattr(sabnzbd, "MACOS", False)
    else:
        raise ValueError(f"Unknown platform: {platform_name}")

    yield platform_name


@pytest.mark.parametrize("platform", ["win32", "macos", "linux"])
@pytest.mark.platform()
def test_platform_parametrize(platform):
    if platform == "win32":
        assert sabnzbd.WINDOWS
        assert not sabnzbd.MACOS
    elif platform == "macos":
        assert sabnzbd.MACOS
        assert not sabnzbd.WINDOWS
    elif platform == "linux":
        assert not sabnzbd.WINDOWS
        assert not sabnzbd.MACOS


@pytest.mark.platform("win32")
def test_platform_marker_win32():
    assert sabnzbd.WINDOWS
    assert not sabnzbd.MACOS


@pytest.mark.platform("macos")
def test_platform_marker_macos():
    assert sabnzbd.MACOS
    assert not sabnzbd.WINDOWS


@pytest.mark.platform("linux")
def test_platform_marker_linux():
    assert not sabnzbd.WINDOWS
    assert not sabnzbd.MACOS


@pytest.fixture()
def fake_fs(request):
    """Create fake filesystem"""
    fake_fs_marker = request.node.get_closest_marker("fake_fs")
    platform_marker = request.node.get_closest_marker("platform")

    with Patcher() as patcher:
        if platform_marker:
            os_map = {"win32": OSType.WINDOWS, "macos": OSType.MACOS, "linux": OSType.LINUX}
            patcher.fs.os = os_map.get(platform_marker.args[0], patcher.fs.os)

        if fake_fs_marker:
            options = fake_fs_marker.args[0] if fake_fs_marker.args else {}

            for key, val in options.items():
                if key == "create_dirs":
                    # Special case: create directories
                    for dir_path in val:
                        patcher.fs.makedirs(dir_path, mode=755, exist_ok=True)
                        # Verify the fake filesystem does its thing
                        assert os.path.exists(dir_path) is True
                elif hasattr(patcher.fs, key):
                    setattr(patcher.fs, key, val)
                else:
                    raise AttributeError(f"fake_fs has no attribute '{key}'")

        yield patcher.fs


def get_url_result(url="", host=SAB_HOST, port=SAB_PORT):
    """Do basic request to web page"""
    arguments = {"apikey": SAB_APIKEY}
    return requests.get("http://%s:%s/%s/" % (host, port, url), params=arguments).text


def get_api_result(mode, host=SAB_HOST, port=SAB_PORT, extra_arguments={}):
    """Build request to SABnzbd"""
    arguments = {"apikey": SAB_APIKEY, "mode": mode}
    arguments.update(extra_arguments)

    r = requests.get("http://%s:%s/api" % (host, port), params=arguments)
    if "xml" in r.headers["Content-Type"]:
        return xmltodict.parse(r.text)
    if "json" in r.headers["Content-Type"]:
        return r.json()
    return r.text


def create_nzb(nzb_dir: str, metadata: Optional[dict[str, str]] = None) -> str:
    """Create NZB from directory using SABNews"""
    nzb_dir_full = os.path.join(SAB_DATA_DIR, nzb_dir)
    return tests.sabnews.create_nzb(nzb_dir=nzb_dir_full, metadata=metadata)


def create_and_read_nzb_fp(nzbdir: str, metadata: Optional[dict[str, str]] = None) -> BinaryIO:
    """Create NZB, return data and delete file"""
    # Create NZB-file to import
    nzb_path = create_nzb(nzbdir, metadata)
    with open(nzb_path, "rb") as nzb_data_fp:
        nzb_data = nzb_data_fp.read()
    # Remove the created NZB-file
    os.remove(nzb_path)
    return io.BytesIO(nzb_data)


def httpserver_handler_data_dir(request: Request):
    """Respond to a httpserver request with a file in SAB_DATA_DIR"""
    return send_from_directory(directory=SAB_DATA_DIR, path=request.path.lstrip("/"), environ=request.environ)


def random_name(length: int = 16) -> str:
    """Shorthand to create a simple random string"""
    return "".join(choice(ascii_lowercase + digits) for _ in range(length))


def wait_for(
    condition: Callable,
    timeout: float = 2,
    interval: float = 0.05,
    err_msg: str = "Condition not met",
    suppress: tuple[type[Exception], ...] = (),
):
    """Polls condition every interval until timeout."""
    deadline = time.time() + timeout
    while True:
        try:
            if result := condition():
                return result
        except suppress:
            pass
        if time.time() > deadline:
            pytest.fail(err_msg)
        time.sleep(interval)


@pytest.fixture
def sleepless(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    yield


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
            nzo.nzo_id = str(uuid.uuid4())
            nzo.bytes_downloaded = randint(1024, 1024**4)
            nzo.md5sum = "".join(choice("abcdef" + digits) for i in range(32))
            nzo.repair, nzo.unpack, nzo.delete = pp_to_opts(choice(list(PP_LOOKUP.keys())))  # for "pp"
            nzo.nzo_info = {"download_time": randint(1, 10**4)}
            nzo.unpack_info = {"unpack_info": "placeholder unpack_info line\r\n" * 3}
            nzo.duplicate_key = "show/season/episode"
            nzo.time_added = int(time.time())
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
        try:
            wait = WebDriverWait(self.driver, 2)
            wait.until(lambda driver_wait: self.driver.execute_script("return window.scrollY") == 0)
        except RemoteDisconnected:
            pass

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
                prior_exception = e
                # Try again in 2 seconds!
                time.sleep(2)
                pass
        else:
            raise prior_exception


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
        self.open_page("http://%s:%s/wizard/" % (SAB_HOST, SAB_PORT))
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
        assert "http://%s:%s" % (SAB_HOST, SAB_PORT) in check_result

        # Go to SAB!
        self.selenium_wrapper(self.driver.find_element, By.CSS_SELECTOR, ".btn.btn-success").click()
        self.no_page_crash()

    def download_nzb(self, nzb_dir: str, file_output: list[str], dir_name_as_job_name: bool = False):
        # Verify if the server was setup before we start
        self.is_server_configured()

        # Delete all jobs from queue and history
        for mode in ("queue", "history"):
            get_api_result(mode=mode, extra_arguments={"name": "delete", "value": "all", "del_files": 1})

        # Create NZB
        nzb_path = create_nzb(nzb_dir)

        # Add NZB
        if dir_name_as_job_name:
            test_job_name = os.path.basename(nzb_dir)
        else:
            # replace "-" because guessit thinks AB01-9999 is episodes 1 to 9999 and takes a long time
            test_job_name = "TestDownload_%s" % str(uuid.uuid4()).replace("-", "")
        job = get_api_result("addlocalfile", extra_arguments={"name": nzb_path, "nzbname": test_job_name})
        assert job["nzo_ids"]
        assert job["status"]
        job_nzo_id = job["nzo_ids"][0]

        # Remove NZB-file
        os.remove(nzb_path)

        completed_dir = None
        queue = {}
        history = {}

        # Wait for the job to be removed and appear in the history
        for _ in range(200):
            try:
                queue = get_api_result(mode="queue", extra_arguments={"nzo_ids": job_nzo_id})["queue"]
                assert not queue["slots"]
                history = get_api_result(mode="history", extra_arguments={"nzo_ids": job_nzo_id})["history"]
                assert history["slots"][0]["nzo_id"] == job_nzo_id
                assert history["slots"][0]["status"] == "Completed"
                completed_dir = history["slots"][0]["storage"]
                assert completed_dir  # has finished postproc
                if os.path.isfile(completed_dir):
                    completed_dir = os.path.dirname(completed_dir)
                break
            except (IndexError, AssertionError):
                time.sleep(0.1)
        else:
            if not completed_dir:
                completed_dir = os.path.join(SAB_COMPLETE_DIR, test_job_name)
            completed_files = filesystem.globber(completed_dir, "*")
            if queue.get("slots"):
                pytest.fail("Download did not complete: it is still in the queue, queue=%s" % queue.get("slots"))
            if history.get("slots"):
                pytest.fail(
                    "Download did not complete: it is in the history, history=%s, completed_files=%s"
                    % (
                        history.get("slots"),
                        completed_files,
                    )
                )
            # Not in the queue or history
            pytest.fail(
                "Download did not complete: not in the queue or history, completed_files=%s" % (completed_files,)
            )

        # Verify all files in the expected file_output are present among the completed files.
        # Sometimes par2 can also be included, but we accept that. For example when small
        # par2 files get assembled in after the download already finished (see #1509)
        for i in range(100):
            completed_files = filesystem.globber(completed_dir, "*")
            try:
                for filename in file_output:
                    assert filename in completed_files
                # All filenames found
                break
            except AssertionError:
                if i % 10 == 0:
                    print("Expected filename %s not found in completed_files %s" % (filename, completed_files))
                # Wait before trying again with a fresh list of completed files
                time.sleep(0.1)
        else:
            pytest.fail("Time ran out waiting for expected filenames to show up")

        # Verify if the garbage collection works (see #1628)
        # We need to give it a second to calm down and clear the variables
        for _ in range(100):
            gc_results = get_api_result("gc_stats")["value"]
            if not gc_results:
                break
            time.sleep(0.1)
        else:
            pytest.fail(f"Objects were left in memory after the job finished! {gc_results}")
