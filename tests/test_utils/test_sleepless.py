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
tests.test_sleepless - Test sleepless for macOS
"""

import os
import subprocess
import sys
import time

import pytest

if not sys.platform.startswith("darwin"):
    pytest.skip("Skipping macOS-only tests", allow_module_level=True)

import sabnzbd.utils.sleepless as sleepless


class TestSleepless:
    # pmset assertions are a machine-global resource, so under pytest-xdist parallel
    # workers running these tests concurrently would see each other's assertion and
    # fail the "nothing is set yet" preconditions. Making the message unique per
    # worker process means each test only ever detects its own assertion. Falls back
    # to the pid for a serial run (PYTEST_XDIST_WORKER unset).
    sleep_msg = "SABnzbd is running, don't you stop us now! [%s]" % os.environ.get("PYTEST_XDIST_WORKER", os.getpid())

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

    def test_sleepless_multi_call(self):
        # If we set it twice, is it still cleared with one call
        assert not self.check_msg_in_assertions()
        assert sleepless.assertion_id is None

        sleepless.keep_awake(self.sleep_msg)
        time.sleep(2)
        sleepless.keep_awake(self.sleep_msg)
        assert self.check_msg_in_assertions()

        sleepless.allow_sleep()
        assert not self.check_msg_in_assertions()
        assert sleepless.assertion_id is None
