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
tests.test_win_utils - Testing mailslot communiction on Windows
"""

import subprocess
import sys
import time

import pytest

if not sys.platform.startswith("win"):
    pytest.skip("Skipping Windows-only tests", allow_module_level=True)

import util.apireg as ar


class TestMailslot:
    def test_mailslot_basic(self):
        """ Do the basic testing provided by the module """
        # Start async both processes
        server_p = subprocess.Popen([sys.executable, "util/mailslot.py", "server"], stdout=subprocess.PIPE)
        # Need to pause to give server time to listen
        time.sleep(0.5)
        client_p = subprocess.Popen([sys.executable, "util/mailslot.py", "client"], stdout=subprocess.PIPE)

        # Server outputs basic response
        assert server_p.stdout.readlines() == [
            b"restart\r\n",
            b"restart\r\n",
            b"restart\r\n",
            b"restart\r\n",
            b"restart\r\n",
            b"stop\r\n",
        ]

        # Client outputs nothing
        assert not client_p.stdout.readlines()


class TestAPIReg:
    def test_set_get_connection_info_user(self):
        """ Test the saving of the URL in USER-registery
            We can't test the SYSTEM one.
        """

        test_url = "sab_test:8080"
        ar.set_connection_info(test_url, True)
        assert ar.get_connection_info(True) == test_url
        assert not ar.get_connection_info(False)

        # Remove and check if gone
        ar.del_connection_info(True)
        assert not ar.get_connection_info(True)

    def test_get_install_lng(self):
        """ Not much to test yet.. """
        assert ar.get_install_lng() == "en"
