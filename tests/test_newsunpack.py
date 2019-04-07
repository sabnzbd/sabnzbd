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
tests.test_newsunpack- Tests of various functions in newspack
"""

import sys
import subprocess
from sabnzbd.newsunpack import *
from tests.testhelper import *


class TestNewsUnpack():
    def test_list_to_cmd(self):
        """ Test to convert list to a cmd.exe-compatible command string """
        lst = ['cmd1', 9, 'cmd3']
        res = list2cmdline(lst)
        # Make sure the output is cmd.exe-compatible
        assert res == '"cmd1" "9" "cmd3"'

    def test_run_simple(self):
        """ Test the output of an external command """
        cmd = "echo $PATH"
        res = run_simple(cmd)
        # Make sure the command output is not blank,
        # should have values on both Windows and Linux
        assert res != ""