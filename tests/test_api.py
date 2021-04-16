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
tests.test_api - Tests for API functions
"""

from tests.testhelper import *

import sabnzbd.api as api


class TestApiInternals:
    """ Test internal functions of the API """

    def test_empty(self):
        with pytest.raises(TypeError):
            api.api_handler(None)
        with pytest.raises(AttributeError):
            api.api_handler("")

    @set_config({"disable_key": False})
    def test_mode_invalid(self):
        expected_error = "error: not implemented"
        assert api.api_handler({"mode": "invalid"}).strip() == expected_error
        with pytest.raises(IndexError):
            assert api.api_handler({"mode": []}).strip() == expected_error
            assert api.api_handler({"mode": ""}).strip() == expected_error
            assert api.api_handler({"mode": None}).strip() == expected_error

    def test_version(self):
        assert api.api_handler({"mode": "version"}).strip() == sabnzbd.__version__

    @set_config({"disable_key": False})
    def test_auth(self):
        assert api.api_handler({"mode": "auth"}).strip() == "apikey"

    @set_config({"disable_key": True, "username": "foo", "password": "bar"})
    def test_auth_apikey_disabled(self):
        assert api.api_handler({"mode": "auth"}).strip() == "login"

    @set_config({"disable_key": True, "username": "", "password": ""})
    def test_auth_unavailable(self):
        assert api.api_handler({"mode": "auth"}).strip() == "None"

    @set_config({"disable_key": True, "username": "foo", "password": ""})
    def test_auth_unavailable_username_set(self):
        assert api.api_handler({"mode": "auth"}).strip() == "None"

    @set_config({"disable_key": True, "username": "", "password": "bar"})
    def test_auth_unavailable_password_set(self):
        assert api.api_handler({"mode": "auth"}).strip() == "None"
