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
tests.test_misc - Testing mailslot communiction on Windows
"""

import sys
import subprocess
import pytest

if not sys.platform.startswith("win"):
    pytest.skip("Skipping Windows-only tests", allow_module_level=True)


class TestMailslot:
    def test_mailslot_basic(self):
        """ Do the basic testing provided by the module """
        # Start async both processes
        server_p = subprocess.Popen([sys.executable, "util/mailslot.py", "server"], stdout=subprocess.PIPE)
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
