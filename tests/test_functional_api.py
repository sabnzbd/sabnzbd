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
tests.test_functional_api - Functional tests for the API
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from math import ceil
from random import choice, randint, sample
from string import ascii_lowercase, digits
from tavern.core import run
from unittest import mock
from warnings import warn

import sabnzbd.api as api
import sabnzbd.database as db

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
from sabnzbd.misc import from_units, pp_to_opts

from tests.testhelper import *


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
        super(FakeHistoryDB, self).__init__()

    def add_fake_history_jobs(self, number_of_entries=1):
        """ Generate a history db with any number of fake entries """

        for _ in range(0, number_of_entries):
            nzo = mock.Mock()

            # Mock all input build_history_info() needs
            distro_choice = choice(self.distro_names)
            distro_random = "".join(choice(ascii_lowercase + digits) for i in range(8))
            nzo.password = choice(["secret", ""])
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


class ApiTestFunctions:
    """ Collection of (wrapper) functions for API testcases """

    def _get_api_json(self, mode, extra_args={}):
        """ Wrapper for API calls with json output """
        extra = {"output": "json", "apikey": self.daemon_apikey}
        extra.update(extra_args)
        return get_api_result(mode=mode, host=self.daemon_host, port=self.daemon_port, extra_arguments=extra)

    def _get_api_text(self, mode, extra_args={}):
        """ Wrapper for API calls with text output """
        extra = {"output": "text", "apikey": self.daemon_apikey}
        extra.update(extra_args)
        return get_api_result(mode=mode, host=self.daemon_host, port=self.daemon_port, extra_arguments=extra)

    def _get_api_xml(self, mode, extra_args={}):
        """ Wrapper for API calls with xml output """
        extra = {"output": "xml", "apikey": self.daemon_apikey}
        extra.update(extra_args)
        return get_api_result(mode=mode, host=self.daemon_host, port=self.daemon_port, extra_arguments=extra)

    def _setup_script_dir(self, dir, script=None):
        """ Set (or unset) the script_dir, add an optional script """
        script_dir_extra = {"section": "misc", "keyword": "script_dir", "value": ""}
        if dir:
            script_dir_extra["value"] = dir
            if script:
                try:
                    script_path = os.path.join(dir, script)
                    with open(script_path, "w") as f:
                        f.write("#!%s\n" % sys.executable)
                        f.write("print('script %s says hi!\n' % __file__)")
                    if not sys.platform.startswith("win"):
                        os.chmod(script_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                except Exception:
                    pytest.fail("Cannot add script %s to script_dir" % script)
        self._get_api_json("set_config", extra_args=script_dir_extra)

    def _record_slots(self, keys):
        """ Return a list of dicts, storing queue info for the items in iterable 'keys' """
        record = []
        for slot in self._get_api_json("queue")["queue"]["slots"]:
            record.append({key: slot[key] for key in keys})
        return record

    def _run_tavern(self, test_name, extra_vars=None):
        """ Run tavern tests in ${test_name}.yaml """
        vars = [
            ("daemon_host", self.daemon_host),
            ("daemon_port", self.daemon_port),
            ("daemon_version", sabnzbd.__version__),
            ("daemon_apikey", self.daemon_apikey),
        ]
        if extra_vars:
            vars.append(extra_vars)
        if self.api_server_parameters["add_fake_history"]:
            vars.append(("daemon_history_size", self.history_size))

        result = run(
            os.path.join(SAB_DATA_DIR, "tavern", test_name + ".yaml"),
            tavern_global_cfg={"variables": dict(vars)},
            pytest_args=["--tavern-file-path-regex", "api_.*.yaml"],
        )
        assert result is result.OK

    def _get_api_history(self, extra={}):
        """ Wrapper for history-related api calls """
        # Set a higher default limit; the default is 10 via cfg(history_limit)
        if "limit" not in extra.keys() and "name" not in extra.keys():
            # History calls that use 'name' don't need the limit parameter
            extra["limit"] = self.history_size * 2

        # Fake history entries never have files, but randomize del_files anyway
        if "name" in extra.keys() and "del_files" not in extra.keys():
            if extra["name"] == "delete":
                extra["del_files"] = randint(0, 1)
        return self._get_api_json("history", extra_args=extra)

    def _create_random_queue(self, minimum_size):
        """
        Ensure the queue has a minimum number of jobs entries, adding random new
        jobs as necessary; excess jobs are not trimmed. Note that while the
        queue is paused overall to prevent downloading, the individual jobs do
        not have their priority set to paused.
        """
        # Make sure the queue is paused
        assert self._get_api_json("pause")["status"] is True

        # Only add jobs if we have to, generating new ones is expensive
        queue_size = len(self._get_api_json("queue")["queue"]["slots"])
        if queue_size >= minimum_size:
            return
        else:
            minimum_size -= queue_size

        charset = ascii_lowercase + digits
        for _ in range(0, minimum_size):
            job_name = "%s-CRQ" % ("".join(choice(charset) for i in range(16)))
            job_dir = os.path.join(self.daemon_basedir, job_name)

            # Create the job_dir and fill it with a bunch of smallish files with
            # random names, sizes and content. Note that some of the tests
            # expect at least two files per NZB.
            try:
                os.mkdir(job_dir)
                for number_of_files in range(0, randint(2, 4)):
                    job_file = "%s.%s" % ("".join(choice(charset) for i in range(randint(6, 18))), sample(charset, 3))
                    with open(os.path.join(job_dir, job_file), "wb") as f:
                        f.write(os.urandom(randint(1, 512 * 1024)))
            except Exception:
                pytest.fail("Failed to create random queue stuffings")

            # Fabricate the NZB
            nzb_file = create_nzb(job_dir)

            # Add job to queue
            assert (
                self._get_api_json("addlocalfile", extra_args={"name": nzb_file, "nzbname": job_name})["status"] is True
            )

            # Remove cruft
            try:
                shutil.rmtree(job_dir)
            except Exception:
                warn("Failed to remove %s" % job_dir)

    def _purge_queue(self, del_files=0):
        """ Clear the entire queue """
        self._get_api_json("queue", extra_args={"name": "purge", "del_files": del_files})
        assert len(self._get_api_json("queue")["queue"]["slots"]) == 0


@pytest.fixture(scope="class")
def api_server(request):
    """
    Create a SABnzbd instance with optional fake history entries and locales.

    Any test class using this fixture must supply a configuration in the form of
    an api_server_parameters dictionary.
    """
    # Server configuration
    host = "127.0.0.1"
    port = randint(4000, 4999)

    # Define a shutdown & cleanup routine
    def shutdown_and_cleanup(p):
        if p:
            try:
                get_url_result("shutdown", host, port)
            except requests.ConnectionError:
                p.kill()
            except Exception:
                warn("Failed to shutdown the server process")
        # Delete the basedir
        try:
            shutil.rmtree(basedir)
        except Exception:
            warn("Failed to remove dir %s" % basedir)

    # Setup a SABnzbd instance using the basic.ini
    try:
        basedir = tempfile.mkdtemp(dir=SAB_BASE_DIR)
        os.mkdir(os.path.join(basedir, DEF_ADMIN_DIR))
        shutil.copyfile(os.path.join(SAB_DATA_DIR, "sabnzbd.basic.ini"), os.path.join(basedir, "sabnzbd.ini"))
    except Exception:
        shutdown_and_cleanup(p=None)
        pytest.fail("Cannot create setup with basedir %s" % basedir)

    # Generate a fake history db
    if request.cls.api_server_parameters["add_fake_history"]:
        try:
            history_db = os.path.join(basedir, DEF_ADMIN_DIR, DB_HISTORY_NAME)
            with FakeHistoryDB(history_db) as fake_history:
                fake_history.add_fake_history_jobs(request.cls.api_server_parameters["history_size"])

            # Make history parameters available to the test class
            request.cls.history_category_options = fake_history.category_options
            request.cls.history_distro_names = fake_history.distro_names
            request.cls.history_size = request.cls.api_server_parameters["history_size"]
        except Exception:
            shutdown_and_cleanup(p=None)
            pytest.fail("Cannot create fake history db %s" % history_db)

    # Generate language files
    locale_dir = os.path.join(SAB_BASE_DIR, "..", "locale")
    if request.cls.api_server_parameters["add_locale"] and not os.path.isdir(locale_dir):
        try:
            # Language files missing; let make_mo do its thing
            subprocess.Popen(
                [
                    sys.executable,
                    os.path.join(SAB_BASE_DIR, "..", "tools", "make_mo.py"),
                ]
            ).communicate(timeout=30)

            # Check the dir again, should exist now
            if not os.path.isdir(locale_dir):
                raise FileNotFoundError("Failed to compile language files")
        except Exception:
            shutdown_and_cleanup(p=None)
            pytest.fail("Cannot compile language files in %s" % locale_dir)

    # Start the test server
    p = subprocess.Popen(
        [
            sys.executable,
            os.path.join(SAB_BASE_DIR, "..", "SABnzbd.py"),
            "--server",
            host + ":" + str(port),
            "--browser",
            "0",
            "--logging",
            "0",
            "--weblogging",
            "--config",
            basedir,
        ]
    )

    # Try getting a response
    for _ in range(30):
        try:
            get_url_result(url="", host=host, port=port)
            break
        except requests.ConnectionError:
            time.sleep(1)
    else:
        shutdown_and_cleanup(p=p)
        pytest.fail("No response from server at %s:%s" % (host, str(port)))

    # Startup succeeded, pass server parameters to the test class
    request.cls.daemon_host = host
    request.cls.daemon_port = port
    request.cls.daemon_apikey = "apikey"
    request.cls.daemon_basedir = basedir

    # Switch over to the test class
    yield

    # Cleanup after the tests are done
    shutdown_and_cleanup(p=p)


@pytest.fixture(scope="function")
def update_history_specs(request):
    """ Update the history size at the start of every test """
    if request.function.__name__.startswith("test_"):
        json = get_api_result(
            "history",
            request.cls.daemon_host,
            request.cls.daemon_port,
            extra_arguments={"limit": request.cls.history_size},
        )
        request.cls.history_size = len(json["history"]["slots"])

    # Test o'clock
    return


@pytest.mark.usefixtures("api_server")
class TestOtherApi(ApiTestFunctions):
    """ Test API function not directly involving either history or queue """

    api_server_parameters = {
        "add_fake_history": False,
        "history_size": None,
        "add_locale": True,
    }

    def test_api_version_testhelper(self):
        """ Check the version, testhelper style """
        assert "version" in get_api_result("version", self.daemon_host, self.daemon_port)

    def test_api_version_tavern(self):
        """ Same same, tavern style """
        self._run_tavern("api_version")

    def test_api_version_json(self):
        assert self._get_api_json("version")["version"] == sabnzbd.__version__

    def test_api_version_text(self):
        assert self._get_api_text("version").rstrip() == sabnzbd.__version__

    def test_api_version_xml(self):
        assert self._get_api_xml("version")["version"] == sabnzbd.__version__

    def test_api_server_stats(self):
        """ Verify server stats format """
        self._run_tavern("api_server_stats")

    @pytest.mark.parametrize("extra_args", [{}, {"name": "change_complete_action", "value": ""}])
    def test_api_nonexistent_mode(self, extra_args):
        # Invalid mode actually returns a proper error
        json = self._get_api_json("eueuq", extra_args=extra_args)
        assert json["status"] is False
        assert json["error"]

    @pytest.mark.parametrize("speed_pct", [randint(1, 99), 100, 0])
    def test_api_speedlimit_pct(self, speed_pct):
        # Set a linespeed, otherwise percentage values cannot be used
        linespeed_value = randint(2, 1000)
        linespeed_unit = choice("KM")
        linespeed = str(linespeed_value) + linespeed_unit
        self._get_api_json(
            mode="set_config", extra_args={"section": "misc", "keyword": "bandwidth_max", "value": linespeed}
        )

        # Speedlimit as a percentage of linespeed
        assert self._get_api_json("config", extra_args={"name": "speedlimit", "value": speed_pct})["status"] is True
        # Verify results for both relative and absolute speedlimit
        json = self._get_api_json("queue")
        if speed_pct != 0:
            assert int(json["queue"]["speedlimit"]) == speed_pct
            assert pytest.approx(
                float(self._get_api_json("queue")["queue"]["speedlimit_abs"]), abs=1, rel=0.005
            ) == speed_pct / 100 * from_units(linespeed)
        else:
            assert int(json["queue"]["speedlimit"]) == 100
            assert bool(json["queue"]["speedlimit_abs"]) is False

    @pytest.mark.parametrize(
        "test_with_units, limit_pct, should_limit",
        [
            (False, randint(1, 99), True),
            (True, randint(1, 99), True),
            (False, 100, True),
            (True, 100, True),
            (True, 0, False),  # A value of zero by design equals 'no limit'
            (False, 0, False),
            (True, 101, True),
            (False, 200, True),
        ],
    )
    def test_api_speedlimit_abs(self, test_with_units, limit_pct, should_limit):
        # Set a linespeed, otherwise percentage values cannot be used
        linespeed_value = randint(2, 1000)
        linespeed = str(linespeed_value) + "M"
        self._get_api_json(
            mode="set_config", extra_args={"section": "misc", "keyword": "bandwidth_max", "value": linespeed}
        )

        if test_with_units:
            # Avoid excessive rounding errors with low linespeed and limit_pct values
            if round(limit_pct / 100 * linespeed_value) > 20:
                speed_abs = str(round(limit_pct / 100 * linespeed_value)) + "M"
            else:
                speed_abs = str(round(limit_pct * 2 ** 10 * linespeed_value / 100)) + "K"
        else:
            speed_abs = str(round(limit_pct / 100 * from_units(linespeed)))
        assert self._get_api_json("config", extra_args={"name": "speedlimit", "value": speed_abs})["status"] is True

        # Verify the result, both absolute and relative
        json = self._get_api_json("queue")
        if should_limit:
            assert float(json["queue"]["speedlimit_abs"]) == from_units(speed_abs)
            assert (
                pytest.approx(float(json["queue"]["speedlimit"]), abs=1, rel=0.005)
                == from_units(speed_abs) / from_units(linespeed) * 100
            )
        else:
            assert bool(json["queue"]["speedlimit_abs"]) is False
            assert int(json["queue"]["speedlimit"]) == 100

    @pytest.mark.parametrize(
        "language, value, translation",
        [
            ("nl", "Error", "Fout"),  # Ascii
            ("he", "Error", "שגיאה"),  # Unicode
            ("en", "Error", "Error"),  # Ask for a translation while the language is set to English
            ("nb", "Ooooooooops", "Ooooooooops"),  # Non-existent/untranslated should mirror the input value
        ],
    )
    def test_api_translate(self, language, value, translation):
        # Set language
        assert (
            self._get_api_json(
                mode="set_config", extra_args={"section": "misc", "keyword": "language", "value": language}
            )["config"]["misc"]["language"]
            == language
        )
        # Translate
        assert self._get_api_json("translate", extra_args={"value": value})["value"] == translation
        # Restore language setting to default
        assert self._get_api_json("set_config_default", extra_args={"keyword": "language"})["status"] is True

    def test_api_translate_empty(self):
        assert (
            self._get_api_json("set_config", extra_args={"section": "misc", "keyword": "language", "value": "de"})[
                "config"
            ]["misc"]["language"]
            == "de"
        )
        # Apparently, this returns some stats on the translation for the active language
        assert "Last-Translator" in self._get_api_json("translate", extra_args={"value": ""})["value"]
        # Restore language setting to default
        assert self._get_api_json("set_config_default", extra_args={"keyword": "language"})["status"] is True

    def test_api_get_clear_warnings(self):
        apikey_error = "API Key Incorrect"
        # Trigger warnings by sending requests with a truncated apikey
        for _ in range(0, 2):
            assert apikey_error in self._get_api_text("shutdown", extra_args={"apikey": self.daemon_apikey[:-1]})

        # Take delivery of our freshly baked warnings
        json = self._get_api_json("warnings")
        assert "warnings" in json.keys()
        assert len(json["warnings"]) > 0
        for warning in json["warnings"]:
            for key in ("type", "text", "time"):
                assert key in warning.keys()
        assert apikey_error.lower() in json["warnings"][-1]["text"].lower()

        # Clear all warnings
        assert self._get_api_json("warnings", extra_args={"name": "clear"})["status"] is True

        # Verify they're gone
        json = self._get_api_json("warnings")
        assert "warnings" in json.keys()
        assert len(json["warnings"]) == 0
        # Check queue output as well
        assert int(self._get_api_json("queue", extra_args={"limit": 1})["queue"]["have_warnings"]) == 0

    def test_api_pause_resume_pp(self):  # TODO include this in the queue output, like the other pause states?
        # Very basic test only, pp pause state cannot be verified for now
        assert self._get_api_json("pause_pp")["status"] is True
        assert self._get_api_text("resume_pp").startswith("ok")

    @pytest.mark.parametrize("set_watched_dir", [False, True])
    def test_api_watched_now(self, set_watched_dir):
        value = self.daemon_basedir if set_watched_dir else ""
        assert (
            self._get_api_json(
                mode="set_config", extra_args={"section": "misc", "keyword": "dirscan_dir", "value": value}
            )["config"]["misc"]["dirscan_dir"]
            == value
        )

        # Returns True even when no watched dir is set...
        assert self._get_api_json("watched_now")["status"] is True  # is set_watched_dir

    @pytest.mark.parametrize("set_quota", [False, True])
    def test_api_reset_quota(self, set_quota):
        quota_config = [
            ("quota_period", "m"),
            ("quota_day", "13"),
            ("quota_size", "123G") if set_quota else ("quota_size", ""),
        ]
        for keyword, value in quota_config:
            assert (
                self._get_api_json(
                    mode="set_config", extra_args={"section": "misc", "keyword": keyword, "value": value}
                )["config"]["misc"][keyword]
                == value
            )

        # Reset the quota and verify the response for all output types
        text = self._get_api_text("reset_quota")
        assert len(text) > 0  # Test for issue #1161
        assert text.strip() == "ok"

        xml = self._get_api_xml("reset_quota")
        assert len(xml) > 0  # Test for issue #1161
        assert xml["result"]["status"] == "True"

        json = self._get_api_json("reset_quota")
        assert len(json) > 0  # Test for issue #1161
        assert json["status"] is True

    @pytest.mark.parametrize("name, keyword", [("nzbkey", "nzb_key"), ("apikey", "api_key")])
    def test_api_set_keys(self, name, keyword):
        original_key = self._get_api_json("get_config", extra_args={"section": "misc", "keyword": keyword})["config"][
            "misc"
        ][keyword]

        # Ask the server for a new key
        json = self._get_api_json("config", extra_args={"name": "set_" + name})
        assert "error" not in json.keys()
        assert len(json[name]) == 32
        assert json[name] != original_key

        # Reset the apikey to prevent getting locked out
        if name == "apikey":
            self._get_api_json(
                "set_config",
                extra_args={"apikey": json[name], "section": "misc", "keyword": keyword, "value": "apikey"},
            )


@pytest.mark.usefixtures("api_server")
class TestQueueApi(ApiTestFunctions):
    """ Test queue-related API responses """

    api_server_parameters = {
        "add_fake_history": False,
        "history_size": None,
        "add_locale": False,
    }

    def test_api_queue_empty_format(self):
        """ Verify formatting, presence of fields for empty queue """
        self._purge_queue()
        self._run_tavern("api_queue_empty")

    @pytest.mark.parametrize("extra_args", [{"name": "woooooops", "value": "so False"}, {"name": "woooooops"}])
    def test_api_queue_nonexistent_name(self, extra_args):
        # Invalid name returns regular output for the given mode (regardless of value).
        assert self._get_api_json("queue", extra_args=extra_args)["queue"]["version"]

    # Also check repeat actions (e.g. pausing an already paused queue)
    @pytest.mark.parametrize(
        "action1, action2", [("pause", "resume"), ("resume", "pause"), ("pause", "pause"), ("resume", "resume")]
    )
    def test_api_queue_pause_resume(self, action1, action2):
        self._purge_queue()
        for action in (action1, action2):
            assert self._get_api_json(action)["status"] is True
            assert self._get_api_json("queue")["queue"]["paused"] is (action == "pause")

    # Also check repeat actions (e.g. pausing an already paused job)
    @pytest.mark.parametrize(
        "action1, action2", [("pause", "resume"), ("resume", "pause"), ("pause", "pause"), ("resume", "resume")]
    )
    def test_api_queue_pause_resume_single_job(self, action1, action2):
        self._create_random_queue(minimum_size=4)
        nzo_ids = [slot["nzo_id"] for slot in self._get_api_json("queue")["queue"]["slots"]]
        change_me = nzo_ids.pop()
        for action in (action1, action2):
            json = self._get_api_json("queue", extra_args={"name": action, "value": change_me})
            assert json["status"] is True
            assert isinstance(json["nzo_ids"], list)
            assert change_me in json["nzo_ids"]
            # Verify the correct job was indeed paused (and nothing else)
            for slot in self._get_api_json("queue")["queue"]["slots"]:
                if action == "pause" and slot["nzo_id"] == change_me:
                    assert slot["status"] == Status.PAUSED
                else:
                    assert slot["status"] != Status.PAUSED

    @pytest.mark.parametrize("delete_count", [1, 2, 5, 9, 10])
    def test_api_queue_delete_jobs(self, delete_count):
        number_of_jobs = max(10, delete_count)
        self._create_random_queue(minimum_size=number_of_jobs)
        original_nzo_ids = [slot["nzo_id"] for slot in self._get_api_json("queue")["queue"]["slots"]]

        # Select random nzo_ids to delete
        delete_me = sample(original_nzo_ids, delete_count)
        delete_me.sort()
        json = self._get_api_json("queue", extra_args={"name": "delete", "value": ",".join(delete_me)})

        # Verify the returned json
        assert json["status"] is True
        assert isinstance(json["nzo_ids"], list)
        deleted_nzo_ids = json["nzo_ids"]
        deleted_nzo_ids.sort()
        assert deleted_nzo_ids == delete_me

        # Check the remaining queue items
        remaining_nzo_ids = [slot["nzo_id"] for slot in self._get_api_json("queue")["queue"]["slots"]]
        assert len(remaining_nzo_ids) == len(original_nzo_ids) - delete_count
        for nzo_id in deleted_nzo_ids:
            assert nzo_id not in remaining_nzo_ids

    @pytest.mark.xfail(reason="Script values aren't sanitized, see issue #1650")
    @pytest.mark.parametrize(
        "should_work, set_scriptsdir, value",
        [
            (True, False, "hibernate_pc"),
            (True, False, "standby_pc"),
            (True, True, "shutdown_program"),
            (True, True, "script_Sample-PostProc.py"),
            (False, False, "script_Sample-PostProc.py"),
            (False, False, "invalid_option"),
            (False, True, "script_foobar.py"),  # Doesn't exist, see issue #1650
            (True, True, "my_script_for_sab.py"),  # Test for #1651
            (False, True, "script_" + os.path.join("..", "SABnzbd.py")),  # Outside the scriptsdir, #1650 again
            (False, True, "script_"),  # Empty after removal of the prefix
        ],
    )
    def test_api_queue_change_complete_action(self, should_work, set_scriptsdir, value):
        # To safeguard against actually triggering any of the actions, pause the
        # queue and add some random job before setting any end-of-queue actions.
        self._create_random_queue(minimum_size=1)

        # Setup the script_dir as ordered
        dir = ""
        if set_scriptsdir:
            dir = os.path.join(SAB_BASE_DIR, "..", "scripts")
        self._setup_script_dir(dir, script="my_script_for_sab.py")

        # Run the queue complete action api call
        prev_value = self._get_api_json("queue")["queue"]["finishaction"]
        json = self._get_api_json("queue", extra_args={"name": "change_complete_action", "value": value})
        assert json["status"] is True  # 'is should_work' fails here, because status is always True

        # Verify the new setting instead
        new_value = self._get_api_json("queue")["queue"]["finishaction"]
        if should_work and value == "":
            assert new_value is None
        elif should_work:
            assert new_value == value
        else:
            # This assert fails because script values go unchecked, issue #1650
            assert new_value == prev_value

        # Unset the queue completion action
        self._get_api_json("queue", extra_args={"name": "change_complete_action", "value": ""})

    def test_api_queue_single_format(self):
        """ Verify formatting, presence of fields for single queue entry """
        self._create_random_queue(minimum_size=1)
        self._run_tavern("api_queue_format")

    @pytest.mark.parametrize(
        "sort_by, slot_name, sort_order",
        [
            ("avg_age", "avg_age", "asc"),
            ("avg_age", "avg_age", "desc"),
            ("name", "filename", "asc"),
            ("name", "filename", "desc"),
            ("size", "size", "asc"),  # Issue #1666, incorrect (reversed) sort order for avg_age
            ("size", "size", "desc"),
        ],
    )
    def test_api_queue_sort(self, sort_by, slot_name, sort_order):
        self._create_random_queue(minimum_size=8)
        original_order = [slot[slot_name] for slot in self._get_api_json("queue")["queue"]["slots"]]
        # API returns "-" instead of their age for jobs dated prior to the 21st century
        geriatric_entry = "-"

        # Sort the queue
        assert (
            self._get_api_json("queue", extra_args={"name": "sort", "sort": sort_by, "dir": sort_order})["status"]
            is True
        )
        new_order = [slot[slot_name] for slot in self._get_api_json("queue")["queue"]["slots"]]

        def age_in_minutes(age):
            # Helper function for list.sort() to deal with d/h/m in avg_age values
            if age.endswith("d"):
                return int(age.strip("d")) * 60 * 24
            if age.endswith("h"):
                return int(age.strip("h")) * 60
            if age.endswith("m"):
                return int(age.strip("m"))
            if age == geriatric_entry:
                return int(time.time() / 60)
            pytest.fail("Unexpected value %s for avg_age" % age)

        def size_in_bytes(size):
            # Helper function for list.sort() to deal with B/KB/MB in size values
            if size.endswith(" MB"):
                return float(size.strip(" MB")) * 1024 ** 2
            if size.endswith(" KB"):
                return float(size.strip(" KB")) * 1024
            if size.endswith(" B"):
                return float(size.strip(" B"))
            pytest.fail("Unexpected value %s for size" % size)

        # Sort the record of the original queue the same way the api sorted the actual queue
        key = None
        if sort_by == "avg_age":
            key = age_in_minutes
        elif sort_by == "size":
            key = size_in_bytes
        original_order.sort(reverse=(sort_order == "desc"), key=key)

        # Filter out geriatric entries
        new_order = list(filter((geriatric_entry).__ne__, new_order))
        original_order = list(filter((geriatric_entry).__ne__, original_order))

        # Verify the result
        assert new_order == original_order

    @pytest.mark.parametrize(
        "queue_size, index_from, index_to, value2_is_nzo_id",
        [
            (5, 4, 1, True),
            (5, 4, 0, False),
            (5, 0, 4, True),
            (5, 2, 3, False),
            (2, 1, 0, False),
            (2, 0, 1, True),
        ],
    )
    def test_api_queue_move(self, queue_size, index_from, index_to, value2_is_nzo_id):
        self._purge_queue()
        self._create_random_queue(minimum_size=queue_size)
        original = self._record_slots(keys=("index", "nzo_id"))

        if index_from > index_to:  # Promoting job
            index_shifted = index_to + 1
        else:  # Demoting
            index_shifted = index_to - 1
        nzo_id_to_move = original[index_from]["nzo_id"]
        nzo_id_move_to = original[index_to]["nzo_id"]
        if value2_is_nzo_id:
            extra = {"value": nzo_id_to_move, "value2": nzo_id_move_to}
        else:
            extra = {"value": nzo_id_to_move, "value2": index_to}

        json = self._get_api_json("switch", extra_args=extra)

        assert json["result"]["position"] == index_to
        assert isinstance(json["result"]["priority"], int)
        for slot in self._get_api_json("queue")["queue"]["slots"]:
            if slot["index"] == index_from:
                assert slot["nzo_id"] != nzo_id_to_move
            if slot["index"] == index_to:
                assert slot["nzo_id"] == nzo_id_to_move
            if slot["index"] == index_shifted:
                assert slot["nzo_id"] == nzo_id_move_to

    def test_api_queue_change_job_cat(self):
        self._create_random_queue(minimum_size=4)
        original = self._record_slots(keys=("nzo_id", "cat"))

        value2 = choice(self._get_api_json("get_cats")["categories"])
        assert value2
        nzo_id = choice(original)["nzo_id"]
        json = self._get_api_json("change_cat", extra_args={"value": nzo_id, "value2": value2})

        assert "error" not in json.keys()
        assert json["status"] is True

        changed = self._record_slots(keys=("nzo_id", "cat"))
        for row in range(0, len(original)):
            if changed[row]["nzo_id"] == nzo_id:
                assert changed[row]["cat"] == value2
            else:
                # All other jobs should remain unchanged
                assert changed[row] == original[row]

    # TODO parametrize, test invalid values? On hold, see #1650
    def test_api_queue_change_job_script(self):
        self._create_random_queue(minimum_size=4)
        self._setup_script_dir(os.path.join(SAB_BASE_DIR, "..", "scripts"))
        original = self._record_slots(keys=("nzo_id", "script"))

        value2 = choice(self._get_api_json("get_scripts")["scripts"])
        assert value2
        nzo_id = choice(original)["nzo_id"]
        json = self._get_api_json("change_script", extra_args={"value": nzo_id, "value2": value2})

        assert "error" not in json.keys()
        assert json["status"] is True

        changed = self._record_slots(keys=("nzo_id", "script"))
        for row in range(0, len(original)):
            if changed[row]["nzo_id"] == nzo_id:
                assert changed[row]["script"] == value2
            else:
                # All other jobs should remain unchanged
                assert changed[row] == original[row]

    @pytest.mark.parametrize("value2", [DEFAULT_PRIORITY, LOW_PRIORITY, NORMAL_PRIORITY, HIGH_PRIORITY, FORCE_PRIORITY])
    def test_api_queue_change_job_prio(self, value2):
        self._create_random_queue(minimum_size=4)
        original = self._record_slots(keys=("nzo_id", "priority"))

        nzo_id = choice(original)["nzo_id"]
        json = self._get_api_json("queue", extra_args={"name": "priority", "value": nzo_id, "value2": value2})

        assert "error" not in json.keys()
        assert "position" in json.keys()

        changed = self._record_slots(keys=("nzo_id", "priority"))
        for row in range(0, len(original)):
            if changed[row]["nzo_id"] == nzo_id:
                assert row == json["position"]
                assert changed[row]["priority"] == INTERFACE_PRIORITIES.get(value2, NORMAL_PRIORITY)

    @pytest.mark.parametrize(
        "value2, expected_status, should_work",
        [
            (0, True, True),
            (1, True, True),
            (2, True, True),
            (3, True, True),
            (choice("RUD"), False, False),  # Unsupported notation for value2
            (-1, False, False),  # Docs used to say -1 means the (category) default, see #1644
        ],
    )
    def test_api_queue_change_job_postproc(self, value2, expected_status, should_work):
        self._create_random_queue(minimum_size=4)
        original = self._record_slots(keys=("nzo_id", "unpackopts"))
        nzo_id = choice(original)["nzo_id"]

        json = self._get_api_json("change_opts", extra_args={"value": nzo_id, "value2": value2})

        assert json["status"] is expected_status
        if should_work:
            changed = self._record_slots(keys=("nzo_id", "unpackopts"))
            for row in range(0, len(original)):
                if changed[row]["nzo_id"] == nzo_id:
                    assert changed[row]["unpackopts"] == str(value2)
                else:
                    # All other jobs should remain unchanged
                    assert changed[row] == original[row]
        else:
            new = self._record_slots(keys=("nzo_id", "unpackopts"))
            assert new == original

    @pytest.mark.parametrize(
        "value2, value3, expected_name, expected_password, should_work",
        [
            ("Ubuntu", None, "Ubuntu", None, True),
            ("デビアン", None, "デビアン", None, True),
            ("OpenBSD 6.8  {{25!}}", None, "OpenBSD 6.8", "25!", True),
            ("Gentoo_Hobby_Edition {{secret}} ", None, "Gentoo_Hobby_Edition", "secret", True),
            ("Mandrake{{now{{Mageia}}", None, "Mandrake", "now{{Mageia", True),
            ("Красная Шляпа", "Գաղտնաբառ", "Красная Шляпа", "Գաղտնաբառ", True),
            ("לינוקס", "معلومات{{{{ سرية", "לינוקס", "معلومات{{{{ سرية", True),
            ("Hello/kITTY", None, "Hello", "kITTY", True),
            ("thư điện tử password=mật_khẩu", None, "thư điện tử", "mật_khẩu", True),
            ("{{Jobname{{PassWord}}", None, "{{Jobname", "PassWord", True),  # Issue #1659
            ("password=PartOfTheJobname", None, "password=PartOfTheJobname", None, True),  # Issue #1659
            ("/Jobname", None, "+Jobname", None, True),  # Issue #1659
            ("", None, None, None, False),
            ("", "PassWord", None, "PassWord", False),
            (None, None, None, None, False),
            (None, "PassWord", None, "PassWord", False),
            ("Job}}Name{{FTW", None, "Job}}Name{{FTW", None, True),  # Issue #1659
            (".{{PasswordOnly}}", None, ".{{PasswordOnly}}", None, True),  # Issue #1659
            # Supplying password through value3 should leave any {{...}} in value2 alone
            ("Foo{{Bar}}", "PassFromValue3", "Foo{{Bar}}", "PassFromValue3", True),
        ],
    )
    def test_api_queue_change_job_name(self, value2, value3, expected_name, expected_password, should_work):
        self._create_random_queue(minimum_size=4)
        original = self._record_slots(keys=("nzo_id", "filename", "password"))

        nzo_id = choice(original)["nzo_id"]
        extra = [("name", "rename"), ("value", nzo_id), ("value2", value2)]
        if value3:
            extra.append(("value3", value3))

        json = self._get_api_json("queue", extra_args=dict(extra))

        assert json["status"] is should_work
        if should_work:
            assert "error" not in json.keys()
        else:
            assert "error" in json.keys()

        changed = self._record_slots(keys=("nzo_id", "filename", "password"))
        for row in range(0, len(original)):
            if should_work and changed[row]["nzo_id"] == nzo_id:
                assert len(changed[row]["filename"]) > 0
                assert changed[row]["filename"] == expected_name
                if expected_password:
                    assert changed[row]["password"] == expected_password
                    if value3:
                        assert len(changed[row]["filename"]) == len(value2)
                else:
                    assert changed[row]["password"] == original[row]["password"]
            else:
                # All other jobs should remain unchanged
                assert changed[row] == original[row]

    def test_api_queue_get_files_format(self):
        """ Verify formatting, presence of fields for mode=get_files """
        self._create_random_queue(minimum_size=1)
        nzo_id = self._get_api_json("queue")["queue"]["slots"][0]["nzo_id"]
        # Pass the nzo_id this way rather than fetching it in a tavern stage, as
        # the latter (while fine with json output) seems buggy when combined
        # with validation functions (as used for the text and xml outputs).
        self._run_tavern("api_get_files_format", extra_vars=("nzo_id", nzo_id))

    def test_api_queue_delete_nzf(self):
        self._create_random_queue(minimum_size=4)

        # Select a job and file to delete
        nzo_ids = [slot["nzo_id"] for slot in self._get_api_json("queue")["queue"]["slots"]]
        nzo_id = choice(nzo_ids)
        json = self._get_api_json("get_files", extra_args={"value": nzo_id})
        assert json["files"]
        nzf_ids = [file["nzf_id"] for file in json["files"]]
        assert nzf_ids
        nzf_id = choice(nzf_ids)

        # Remove the file from the job
        json = self._get_api_json("queue", extra_args={"name": "delete_nzf", "value": nzo_id, "value2": nzf_id})
        assert json["status"] is True
        assert nzf_id in json["nzf_ids"]

        # Verify it's really gone
        json = self._get_api_json("get_files", extra_args={"value": nzo_id})
        changed_nzf_ids = [file["nzf_id"] for file in json["files"]]
        assert nzf_id not in changed_nzf_ids
        assert len(changed_nzf_ids) == len(nzf_ids) - 1

        # Try to remove a non-existent file
        json = self._get_api_json("queue", extra_args={"name": "delete_nzf", "value": nzo_id, "value2": "FAKE"})
        assert json["status"] is False
        assert json["nzf_ids"] == []

        # Attempt to remove multiple nzf_ids at once (which isn't supported)
        nzo_ids.remove(nzo_id)
        nzo_id = choice(nzo_ids)
        json = self._get_api_json("get_files", extra_args={"value": nzo_id})
        nzf_ids = [file["nzf_id"] for file in json["files"]]
        assert len(nzf_ids) > 0
        json = self._get_api_json(
            mode="queue", extra_args={"name": "delete_nzf", "value": nzo_id, "value2": ",".join(nzf_ids)}
        )
        assert json["status"] is False
        assert json["nzf_ids"] == []


@pytest.mark.usefixtures("api_server", "update_history_specs")
class TestHistoryApi(ApiTestFunctions):
    """ Test history-related API responses """

    api_server_parameters = {
        "add_fake_history": True,
        "history_size": randint(81, 90),
        "add_locale": False,
    }

    def test_api_history_format(self):
        """ Verify formatting, presence of expected history fields """
        # Checks all output styles: json, text and xml
        self._run_tavern("api_history_format")

    def test_api_history_slot_count(self):
        slot_limit = randint(1, self.history_size - 1)
        json = self._get_api_history({"limit": slot_limit})
        assert len(json["history"]["slots"]) == slot_limit

    def test_api_history_restrict_cat(self):
        slot_sum = 0
        # Loop over all categories in the fake history, plus the Default category
        cats = list(self.history_category_options)
        cats.extend("*")
        for cat in cats:
            json = self._get_api_history({"category": cat})
            slot_sum += len(json["history"]["slots"])
            # All results should be from the correct category
            for slot in json["history"]["slots"]:
                if cat != "*":
                    assert slot["category"] == cat
        # Total number of slots should match the sum of all category slots
        json = self._get_api_history({"limit": self.history_size})
        slot_total = len(json["history"]["slots"])
        assert slot_sum == slot_total

    def test_api_history_restrict_invalid_cat(self):
        fake_cat = "FakeCat_%s" % ("".join(choice(ascii_lowercase + digits) for i in range(16)))
        json = self._get_api_history({"category": fake_cat})
        assert len(json["history"]["slots"]) == 0

    def test_api_history_restrict_cat_and_limit(self):
        cats = self.history_category_options
        for cat in cats:
            limit = min(randint(1, 5), self.history_size)
            json = self._get_api_history({"category": cat, "limit": limit})
            assert len(json["history"]["slots"]) <= limit
            for slot in json["history"]["slots"]:
                # All results should be from the correct category
                assert slot["category"] == cat

    def test_api_history_restrict_invalid_cat_and_limit(self):
        fake_cat = "FakeCat_%s" % ("".join(choice(ascii_lowercase + digits) for i in range(16)))
        json = self._get_api_history({"category": fake_cat, "limit": randint(1, 5)})
        assert len(json["history"]["slots"]) == 0

    def test_api_history_restrict_invalid_cat_and_search(self):
        fake_cat = "FakeCat_%s" % ("".join(choice(ascii_lowercase + digits) for i in range(16)))
        for distro in self.history_distro_names:
            json = self._get_api_history({"category": fake_cat, "search": distro})
            assert len(json["history"]["slots"]) == 0

    def test_api_history_restrict_search(self):
        slot_sum = 0
        for distro in self.history_distro_names:
            json = self._get_api_history({"search": distro})
            slot_sum += len(json["history"]["slots"])
        assert slot_sum == self.history_size

    def test_api_history_restrict_no_results_search(self):
        fake_search = "FakeSearch_%s" % ("".join(choice(ascii_lowercase + digits) for i in range(16)))
        json = self._get_api_history({"search": fake_search})
        assert len(json["history"]["slots"]) == 0

    def test_api_history_restrict_cat_and_search_and_limit(self):
        """ Combine search, category and limits requirements into a single query """
        limit_sum = 0
        slot_sum = 0
        limits = [randint(1, ceil(self.history_size / 10)) for _ in range(0, len(self.history_distro_names))]
        for distro, limit in zip(self.history_distro_names, limits):
            for cat in self.history_category_options:
                json = self._get_api_history({"search": distro, "limit": limit, "category": cat})
                slot_count = len(json["history"]["slots"])
                assert slot_count <= limit
                slot_sum += slot_count
                limit_sum += min(limit, slot_count)
                for slot in json["history"]["slots"]:
                    assert slot["category"] == cat

        # Verify the number of results
        assert slot_sum <= sum(limits) * len(self.history_category_options)
        assert slot_sum == limit_sum

    def test_api_history_limit_failed(self):
        json = self._get_api_history({"failed_only": 1})
        failed_count = len(json["history"]["slots"])

        # Now get all history and select jobs with status failed
        json = self._get_api_history()
        failed_sum = 0
        for slot in json["history"]["slots"]:
            if slot["status"] == Status.FAILED:
                failed_sum += 1

        assert failed_count == failed_sum

    def test_api_history_delete_single(self):
        # Collect a single random nzo_id
        json = self._get_api_history({"start": randint(0, self.history_size - 1), "limit": 1})
        delete_this = {"nzo_id": [], "name": []}
        delete_this = {
            "nzo_id": str(json["history"]["slots"][0]["nzo_id"]),
            "name": str(json["history"]["slots"][0]["name"]),
        }

        json = self._get_api_history({"name": "delete", "value": delete_this["nzo_id"]})
        assert json["status"] is True

        # Verify the job is actually gone. Unfortunately, it appears searching
        # the history by nzo_id isn't possible so we take a detour and search by
        # name, only to check the nzo_id of the returned entries (if any).
        json = self._get_api_history({"search": delete_this["name"]})
        # Searching by name could match other jobs too, so we can't rely on "noofslots" here
        for slot in json["history"]["slots"]:
            assert slot["nzo_id"] != delete_this["nzo_id"]

    def test_api_history_delete_multiple(self):
        # Collect several nzo_ids to delete
        limit = randint(2, 2 + ceil(self.history_size / 10))
        json = self._get_api_history({"start": randint(0, self.history_size - limit - 1), "limit": limit})
        delete_these = {"nzo_id": [], "name": []}
        for slot in json["history"]["slots"]:
            for item in ("nzo_id", "name"):
                delete_these[item].append(slot[item])

        # Delete 'm all
        json = self._get_api_history({"name": "delete", "value": ",".join(delete_these["nzo_id"])})
        assert json["status"] is True

        # Verify
        for name in delete_these["name"]:
            json = self._get_api_history({"search": name})
            for slot in json["history"]["slots"]:
                assert slot["nzo_id"] not in delete_these["nzo_id"]

    def test_api_history_delete_failed(self):
        # Check the number of failed entries currently in the history
        json = self._get_api_history({"failed_only": 1})
        failed_count = len(json["history"]["slots"])
        original_history_size = int(self.history_size)

        if failed_count > 0:
            # Remove all failed entries
            json = self._get_api_history({"name": "delete", "value": "failed"})
            assert json["status"] is True

            # Verify no failed history entries remain
            json = self._get_api_history()
            for slot in json["history"]["slots"]:
                assert slot["status"] != Status.FAILED

            # Make sure nothing else got axed
            new_history_size = original_history_size - failed_count
            assert len(json["history"]["slots"]) == new_history_size
        else:
            warn("Fake history doesn't contain any failed jobs")
            new_history_size = original_history_size

        # A rerun of the delete action shouldn't have any effect, since no failed entries should remain
        json = self._get_api_history({"name": "delete", "value": "failed"})
        assert json["status"] is True
        json = self._get_api_history()
        assert len(json["history"]["slots"]) == new_history_size

    def test_api_history_delete_completed(self):
        json = self._get_api_history({"name": "delete", "value": "completed"})
        assert json["status"] is True
        json = self._get_api_history()
        for slot in json["history"]["slots"]:
            assert slot["status"] != Status.COMPLETED


@pytest.mark.usefixtures("api_server", "update_history_specs")
class TestHistoryApiPart2(ApiTestFunctions):
    """Test history-related API responses, part 2. A separate testcase is
    needed because the previous one ran out of history entries to delete."""

    api_server_parameters = {
        "add_fake_history": True,
        "history_size": randint(42, 81),
        "add_locale": False,
    }

    def test_api_history_delete_all(self):
        json = self._get_api_history({"name": "delete", "value": "all"})
        assert json["status"] is True
        json = self._get_api_history()
        for slot in json["history"]["slots"]:
            assert slot["status"] != Status.COMPLETED
            assert slot["status"] != Status.FAILED

    def test_api_history_delete_everything(self):
        json = self._get_api_history()
        delete_these = [slot["nzo_id"] for slot in json["history"]["slots"]]
        assert len(delete_these) == len(json["history"]["slots"])

        # Kill 'm with fire!
        json = self._get_api_history({"name": "delete", "value": ",".join(delete_these)})
        assert json["status"] is True

        # Make sure nothing survived
        json = self._get_api_history()
        assert json["history"]["noofslots"] == 0

    def test_api_history_empty_format(self):
        """ Verify formatting, presence of fields for empty history """
        # Checks all output styles: json, text and xml
        self._run_tavern("api_history_empty")
