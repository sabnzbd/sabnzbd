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
tests.test_win_utils - Testing Windows utils
"""

import sys

import pytest

if not sys.platform.startswith("win"):
    pytest.skip("Skipping Windows-only tests", allow_module_level=True)

import sabnzbd.utils.apireg as ar


class TestAPIReg:
    def test_set_get_connection_info_user(self, tmp_path):
        """Test the saving of the URL in USER-registery
        We can't test the SYSTEM one.
        """
        inifile = str(tmp_path / "sabnzbd.ini")
        test_url = "sab_test:8080"
        ar.set_connection_info(test_url, inifile, True)
        assert ar.get_connection_info(inifile, True) == test_url
        assert not ar.get_connection_info(inifile, False)

        # Remove and check if gone
        ar.del_connection_info(inifile, True)
        assert not ar.get_connection_info(inifile, True)

    def test_connection_info_is_per_config_file(self, tmp_path):
        """Instances on separate config files must not see each other's URL"""
        first_ini = str(tmp_path / "first" / "sabnzbd.ini")
        second_ini = str(tmp_path / "second" / "sabnzbd.ini")
        ar.set_connection_info("sab_test:8080", first_ini, True)
        ar.set_connection_info("sab_test:9090", second_ini, True)

        assert ar.get_connection_info(first_ini, True) == "sab_test:8080"
        assert ar.get_connection_info(second_ini, True) == "sab_test:9090"

        ar.del_connection_info(first_ini, True)
        assert not ar.get_connection_info(first_ini, True)
        assert ar.get_connection_info(second_ini, True) == "sab_test:9090"

        ar.del_connection_info(second_ini, True)
        assert not ar.get_connection_info(second_ini, True)

    def test_get_install_lng(self):
        """Not much to test yet.."""
        assert ar.get_install_lng() == "en"
