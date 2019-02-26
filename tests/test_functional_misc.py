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

import getpass
from tests.testhelper import *


class SABnzbdShowLoggingTest(SABnzbdBaseTest):
    def test_showlog(self):
        # Basic URL-fetching, easier than Selenium file download
        log_result = get_url_result("status/showlog")

        # Make sure it has basic log stuff
        assert "The log" in log_result
        assert "Full executable path" in log_result

        # Make sure sabnzbd.ini was appended
        assert "__encoding__ = utf-8" in log_result
        assert "[misc]" in log_result

        # Did we filter out username?
        assert getpass.getuser() not in log_result
        assert "<USERNAME>" in log_result
