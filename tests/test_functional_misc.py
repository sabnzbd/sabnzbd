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
tests.test_functional_misc - Functional tests of various functions
"""

import sys
import subprocess
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
