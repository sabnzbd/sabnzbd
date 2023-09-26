#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team (sabnzbd.org)
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
tests.test_functional_downloads - Test the downloading flow
"""
from tests.testhelper import *
from flaky import flaky


@flaky
class TestDownloadFlow(DownloadFlowBasics):
    def test_download_basic_rar5(self):
        self.download_nzb("basic_rar5", ["My_Test_Download.bin"])

    def test_download_zip(self):
        self.download_nzb("test_zip", ["My_Test_Download.bin"])

    def test_download_7zip(self):
        self.download_nzb("test_7zip", ["My_Test_Download.bin"])

    def test_download_passworded(self):
        self.download_nzb("test_passworded{{secret}}", ["My_Test_Download.bin"])

    @pytest.mark.xfail(reason="Probably #1633")
    def test_download_unicode_made_on_windows(self):
        self.download_nzb("test_win_unicode", ["frènch_german_demö.bin"])

    def test_download_fully_obfuscated(self):
        # This is also covered by a unit test but added to test full flow
        self.download_nzb("obfuscated_single_rar_set", ["My_Test_Download.bin"])

    def test_download_unicode_rar(self):
        self.download_nzb("unicode_rar", ["我喜欢编程_My_Test_Download.bin"])
