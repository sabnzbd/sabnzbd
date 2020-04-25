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
tests.test_sleepless - Test sleepless for macOS
"""

import sys
import pytest
import time
import subprocess

if not sys.platform.startswith("darwin"):
    pytest.skip("Skipping macOS-only tests", allow_module_level=True)

import sabnzbd.utils.sleepless as sleepless


class TestSleepless:
    sleep_msg = "SABnzbd is running, don't you stop us now!"

    def check_msg_in_assertions(self):
        return self.sleep_msg in subprocess.check_output(["pmset", "-g", "assertions"], universal_newlines=True)

    def test_sleepless(self):
        # Run twice to see if it keeps going well
        for _ in range(2):
            # Keep it awake
            sleepless.keep_awake(self.sleep_msg)
            time.sleep(2)

            # Check if it's still in the assertions list
            assert self.check_msg_in_assertions()

            # Remove and see if it's still there
            sleepless.allow_sleep()
            assert not self.check_msg_in_assertions()
            assert sleepless.assertion_id is None

    def test_sleepless_not_there(self):
        assert not self.check_msg_in_assertions()
        assert sleepless.assertion_id is None

        sleepless.allow_sleep()
        assert not self.check_msg_in_assertions()
        assert sleepless.assertion_id is None
