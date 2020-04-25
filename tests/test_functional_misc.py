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
tests.test_functional_misc - Functional tests of various functions
"""
import shutil
import subprocess
import sys

import sabnzbd.encoding
from tests.testhelper import *


class SABnzbdShowLoggingTest(SABnzbdBaseTest):
    def test_showlog(self):
        """ Test the output of the filtered-log button """
        # Basic URL-fetching, easier than Selenium file download
        log_result = get_url_result("status/showlog")

        # Make sure it has basic log stuff
        assert "The log" in log_result
        assert "Full executable path" in log_result

        # Make sure sabnzbd.ini was appended
        assert "__encoding__ = utf-8" in log_result
        assert "[misc]" in log_result


class TestSamplePostProc:
    def test_sample_post_proc(self):
        """ Make sure we don't break things """
        # Set parameters
        script_params = [
            "somedir222",
            "nzbname",
            "frènch_german_demö",
            "Index12",
            "Cat88",
            "MyGroup",
            "PP0",
            "https://example.com/",
        ]
        script_call = [sys.executable, "scripts/Sample-PostProc.py", "server"]
        script_call.extend(script_params)

        # Set parameters via env
        env = os.environ.copy()
        env["SAB_VERSION"] = "frènch_german_demö_version"

        # Run script and check output
        script_call = subprocess.Popen(script_call, stdout=subprocess.PIPE, env=env)
        script_output, errs = script_call.communicate(timeout=15)

        # This is a bit bad, since we use our own function
        # But in a way it is also a test if the function does its job!
        script_output = sabnzbd.encoding.platform_btou(script_output)

        # Check if all parameters are there
        for param in script_params:
            assert param in script_output
        assert env["SAB_VERSION"] in script_output


class TestExtractPot:
    def test_extract_pot(self):
        """ Simple test if translation extraction still works """
        script_call = [sys.executable, "tools/extract_pot.py"]

        # Run script and check output
        script_call = subprocess.Popen(script_call, stdout=subprocess.PIPE)
        script_output, errs = script_call.communicate(timeout=15)
        script_output = sabnzbd.encoding.platform_btou(script_output)

        # Success message?
        assert "Creating POT file" in script_output
        assert "Finished creating POT file" in script_output
        assert "Post-process POT file" in script_output
        assert "Finished post-process POT file" in script_output
        assert "Creating email POT file" in script_output
        assert "Finished creating email POT file" in script_output

        # Check if the file was modified less than 30 seconds ago
        cur_time = time.time()
        assert (cur_time - os.path.getmtime("po/main/SABnzbd.pot")) < 30
        assert (cur_time - os.path.getmtime("po/email/SABemail.pot")) < 30


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Skipping on Windows")
@pytest.mark.skipif(sys.platform.startswith("darwin"), reason="Fails for now due to PyObjC problem")
class TestDaemonizing(SABnzbdBaseTest):
    def test_daemonizing(self):
        """ Simple test to see if daemon-mode still works.
            Also test removal of large "sabnzbd.error.log"
            We inherit from SABnzbdBaseTest so we can use it's clean-up logic!
        """
        daemon_host = "localhost"
        daemon_port = 23456
        ini_location = os.path.join(SAB_CACHE_DIR, "daemon_test")

        # Create large output-file
        error_log_path = os.path.join(ini_location, sabnzbd.cfg.log_dir(), sabnzbd.constants.DEF_LOG_ERRFILE)
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
        with open(error_log_path, "wb") as large_log:
            large_log.seek(6 * 1024 * 1024)
            large_log.write(b"\1")

        # We need the basic-config to set the API-key
        # Otherwise we can't shut it down at the end
        shutil.copyfile(os.path.join(SAB_BASE_DIR, "sabnzbd.basic.ini"), os.path.join(ini_location, "sabnzbd.ini"))

        # Combine it all into the script call
        script_call = [
            sys.executable,
            "SABnzbd.py",
            "-d",
            "-s",
            "%s:%s" % (daemon_host, daemon_port),
            "-f",
            ini_location,
            "--pid",
            ini_location,
        ]

        # Run script and check output
        script_call = subprocess.Popen(script_call, stdout=subprocess.PIPE)
        script_output, errs = script_call.communicate(timeout=15)

        # No error or output should be thrown by main process
        assert not script_output
        assert not errs

        # It should be online after 3 seconds
        time.sleep(3.0)
        assert "version" in get_api_result("version", daemon_host, daemon_port)

        # Did it create the PID file
        pid_file = os.path.join(ini_location, "sabnzbd-%d.pid" % daemon_port)
        assert os.path.exists(pid_file)

        # Did it remove the bad log file?
        assert os.path.exists(error_log_path)
        assert os.path.getsize(error_log_path) < 1024

        # Let's shut it down and give it some time to do so
        get_url_result("shutdown", daemon_host, daemon_port)
        time.sleep(3.0)
