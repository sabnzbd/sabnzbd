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
tests.test_misc - Testing functions in misc.py
"""

import datetime
import subprocess
import tempfile
from unittest import mock

from sabnzbd import lang
from sabnzbd import misc
from sabnzbd import newsunpack
from sabnzbd.config import ConfigCat
from sabnzbd.constants import HIGH_PRIORITY, TOP_PRIORITY, DEFAULT_PRIORITY, NORMAL_PRIORITY
from tests.testhelper import *


class TestMisc:
    @staticmethod
    def assertTime(offset, age):
        assert offset == misc.calc_age(age, trans=True)
        assert offset == misc.calc_age(age, trans=False)

    def test_timeformat24h(self):
        assert "%H:%M:%S" == misc.time_format("%H:%M:%S")
        assert "%H:%M" == misc.time_format("%H:%M")

    @set_config({"ampm": True})
    def test_timeformatampm(self):
        misc.HAVE_AMPM = True
        assert "%I:%M:%S %p" == misc.time_format("%H:%M:%S")
        assert "%I:%M %p" == misc.time_format("%H:%M")

    def test_calc_age(self):
        date = datetime.datetime.now()
        m = date - datetime.timedelta(minutes=1)
        h = date - datetime.timedelta(hours=1)
        d = date - datetime.timedelta(days=1)
        self.assertTime("1m", m)
        self.assertTime("1h", h)
        self.assertTime("1d", d)

    def test_monthrange(self):
        # Dynamic dates would be a problem
        assert 12 == len(list(misc.monthrange(datetime.date(2018, 1, 1), datetime.date(2018, 12, 31))))
        assert 2 == len(list(misc.monthrange(datetime.date(2019, 1, 1), datetime.date(2019, 2, 1))))

    def test_safe_lower(self):
        assert "all caps" == misc.safe_lower("ALL CAPS")
        assert "" == misc.safe_lower(None)

    def test_cmp(self):
        assert misc.cmp(1, 2) < 0
        assert misc.cmp(2, 1) > 0
        assert misc.cmp(1, 1) == 0

    def test_cat_to_opts(self):
        # Need to create the Default category, as we would in normal instance
        # Otherwise it will try to save the config
        ConfigCat("*", {"pp": 3, "script": "None", "priority": NORMAL_PRIORITY})

        assert ("*", 3, "None", NORMAL_PRIORITY) == misc.cat_to_opts("*")
        assert ("*", 3, "None", NORMAL_PRIORITY) == misc.cat_to_opts("Nonsense")
        assert ("*", 1, "None", NORMAL_PRIORITY) == misc.cat_to_opts("*", pp=1)
        assert ("*", 1, "test.py", NORMAL_PRIORITY) == misc.cat_to_opts("*", pp=1, script="test.py")

        ConfigCat("movies", {"priority": HIGH_PRIORITY, "script": "test.py"})
        assert ("movies", 3, "test.py", HIGH_PRIORITY) == misc.cat_to_opts("movies")
        assert ("movies", 1, "test.py", HIGH_PRIORITY) == misc.cat_to_opts("movies", pp=1)
        assert ("movies", 1, "not_test.py", HIGH_PRIORITY) == misc.cat_to_opts("movies", pp=1, script="not_test.py")
        assert ("movies", 3, "test.py", TOP_PRIORITY) == misc.cat_to_opts("movies", priority=TOP_PRIORITY)

        # If the category has DEFAULT_PRIORITY, it should use the priority of the *-category (NORMAL_PRIORITY)
        # If the script-name is Default for a category, it should use the script of the *-category (None)
        ConfigCat("software", {"priority": DEFAULT_PRIORITY, "script": "Default"})
        assert ("software", 3, "None", NORMAL_PRIORITY) == misc.cat_to_opts("software")
        assert ("software", 3, "None", TOP_PRIORITY) == misc.cat_to_opts("software", priority=TOP_PRIORITY)

    def test_wildcard_to_re(self):
        assert "\\\\\\^\\$\\.\\[" == misc.wildcard_to_re("\\^$.[")
        assert "\\]\\(\\)\\+.\\|\\{\\}.*" == misc.wildcard_to_re("]()+?|{}*")

    def test_cat_convert(self):
        # TODO: Make test
        pass

    def test_convert_version(self):
        assert (3010099, False) == misc.convert_version("3.1.0")
        assert (3010099, False) == misc.convert_version("3.1.0BlaBla")
        assert (3010001, True) == misc.convert_version("3.1.0Alpha1")
        assert (3010041, True) == misc.convert_version("3.1.0Beta1")
        assert (3010081, True) == misc.convert_version("3.1.0RC1")
        assert (3010194, True) == misc.convert_version("3.1.1RC14")

    def test_from_units(self):
        assert -1.0 == misc.from_units("-1")
        assert 100.0 == misc.from_units("100")
        assert 1024.0 == misc.from_units("1KB")
        assert 1048576.0 == misc.from_units("1024KB")
        assert 1048576.0 == misc.from_units("1024Kb")
        assert 1048576.0 == misc.from_units("1024kB")
        assert 1048576.0 == misc.from_units("1MB")
        assert 1073741824.0 == misc.from_units("1GB")
        assert 1125899906842624.0 == misc.from_units("1P")

    def test_to_units(self):
        assert "1 K" == misc.to_units(1024)
        assert "1 KBla" == misc.to_units(1024, postfix="Bla")
        assert "1.0 M" == misc.to_units(1024 * 1024)
        assert "1.0 M" == misc.to_units(1024 * 1024 + 10)
        assert "10.0 M" == misc.to_units(1024 * 1024 * 10)
        assert "100.0 M" == misc.to_units(1024 * 1024 * 100)
        assert "9.8 G" == misc.to_units(1024 * 1024 * 10000)
        assert "1024.0 P" == misc.to_units(1024 ** 6)

    def test_unit_back_and_forth(self):
        assert 100 == misc.from_units(misc.to_units(100))
        assert 1024 == misc.from_units(misc.to_units(1024))
        assert 1024 ** 3 == misc.from_units(misc.to_units(1024 ** 3))

    def test_caller_name(self):
        @set_config({"log_level": 0})
        def test_wrapper(skip):
            return misc.caller_name(skip=skip)

        @set_config({"log_level": 2})
        def test_wrapper_2(skip):
            return misc.caller_name(skip=skip)

        # No logging on lower-level
        assert "N/A" == test_wrapper(1)
        assert "N/A" == test_wrapper(2)
        assert "N/A" == test_wrapper(3)

        # Wrappers originate from the set_config-wrapper
        assert "test_wrapper_2" in test_wrapper_2(1)
        assert "wrapper_func" in test_wrapper_2(2)

    def test_split_host(self):
        assert (None, None) == misc.split_host(None)
        assert (None, None) == misc.split_host("")
        assert ("sabnzbd.org", 123) == misc.split_host("sabnzbd.org:123")
        assert ("sabnzbd.org", None) == misc.split_host("sabnzbd.org")
        assert ("127.0.0.1", 566) == misc.split_host("127.0.0.1:566")
        assert ("[::1]", 1234) == misc.split_host("[::1]:1234")
        assert ("[2001:db8::8080]", None) == misc.split_host("[2001:db8::8080]")

    @set_config({"cleanup_list": [".exe", ".nzb"]})
    def test_on_cleanup_list(self):
        assert misc.on_cleanup_list("test.exe")
        assert misc.on_cleanup_list("TEST.EXE")
        assert misc.on_cleanup_list("longExeFIlanam.EXe")
        assert not misc.on_cleanup_list("testexe")
        assert misc.on_cleanup_list("test.nzb")
        assert not misc.on_cleanup_list("test.nzb", skip_nzb=True)
        assert not misc.on_cleanup_list("test.exe.lnk")

    def test_format_time_string(self):
        assert "0 seconds" == misc.format_time_string(None)
        assert "0 seconds" == misc.format_time_string("Test")
        assert "0 seconds" == misc.format_time_string(0)
        assert "1 sec" == misc.format_time_string(1)
        assert "10 seconds" == misc.format_time_string(10)
        assert "1 min" == misc.format_time_string(60)
        assert "1 hour 1 min 1 sec" == misc.format_time_string(60 * 60 + 60 + 1)
        assert "1 day 59 seconds" == misc.format_time_string(86400 + 59)
        assert "2 days 2 hours 2 seconds" == misc.format_time_string(2 * 86400 + 2 * 60 * 60 + 2)

    def test_format_time_string_locale(self):
        # Have to set the languages, if it was compiled
        locale_dir = os.path.join(SAB_BASE_DIR, "..", sabnzbd.constants.DEF_LANGUAGE)
        if not os.path.exists(locale_dir):
            pytest.mark.skip("No language files compiled")

        lang.set_locale_info("SABnzbd", locale_dir)
        lang.set_language("de")
        assert "1 Sekunde" == misc.format_time_string(1)
        assert "10 Sekunden" == misc.format_time_string(10)
        assert "1 Minuten" == misc.format_time_string(60)
        assert "1 Stunde 1 Minuten 1 Sekunde" == misc.format_time_string(60 * 60 + 60 + 1)
        assert "1 Tag 59 Sekunden" == misc.format_time_string(86400 + 59)
        assert "2 Tage 2 Stunden 2 Sekunden" == misc.format_time_string(2 * 86400 + 2 * 60 * 60 + 2)

    def test_int_conv(self):
        assert 0 == misc.int_conv("0")
        assert 10 == misc.int_conv("10")
        assert 10 == misc.int_conv(10)
        assert 10 == misc.int_conv(10.0)
        assert 0 == misc.int_conv(None)
        assert 1 == misc.int_conv(True)
        assert 0 == misc.int_conv(object)

    def test_create_https_certificates(self):
        cert_file = "test.cert"
        key_file = "test.key"
        assert misc.create_https_certificates(cert_file, key_file)
        assert os.path.exists(cert_file)
        assert os.path.exists(key_file)

        # Remove files
        os.unlink("test.cert")
        os.unlink("test.key")


class TestBuildAndRunCommand:
    def test_none_check(self):
        with pytest.raises(IOError):
            misc.build_and_run_command([None])

    @set_platform("win32")
    @mock.patch("subprocess.Popen")
    def test_win(self, mock_subproc_popen):
        # Needed for priority check
        import win32process

        misc.build_and_run_command(["test.cmd", "input 1"])
        assert mock_subproc_popen.call_args.args[0] == ["test.cmd", "input 1"]
        assert mock_subproc_popen.call_args.kwargs["creationflags"] == win32process.NORMAL_PRIORITY_CLASS

        misc.build_and_run_command(["test.py", "input 1"])
        assert mock_subproc_popen.call_args.args[0] == ["python.exe", "test.py", "input 1"]
        assert mock_subproc_popen.call_args.kwargs["creationflags"] == win32process.NORMAL_PRIORITY_CLASS

        # See: https://github.com/sabnzbd/sabnzbd/issues/1043
        misc.build_and_run_command(["UnRar.exe", "\\\\?\\C:\\path\\"])
        assert mock_subproc_popen.call_args.args[0] == ["UnRar.exe", "\\\\?\\C:\\path\\"]
        misc.build_and_run_command(["UnRar.exe", "\\\\?\\C:\\path\\"], flatten_command=True)
        assert mock_subproc_popen.call_args.args[0] == '"UnRar.exe" "\\\\?\\C:\\path\\"'

    @mock.patch("subprocess.Popen")
    def test_std_override(self, mock_subproc_popen):
        misc.build_and_run_command(["test.py"], stderr=subprocess.DEVNULL)
        assert mock_subproc_popen.call_args.kwargs["stderr"] == subprocess.DEVNULL

    @set_platform("linux")
    @set_config({"nice": "--adjustment=-7", "ionice": "-t -n9 -c7"})
    @mock.patch("sabnzbd.misc.userxbit")
    @mock.patch("subprocess.Popen")
    def test_linux_features(self, mock_subproc_popen, userxbit):
        # Path should exist
        script_path = os.path.join(SAB_BASE_DIR, "test_misc.py")

        # Should break on no-execute permissions
        userxbit.return_value = False
        with pytest.raises(IOError):
            misc.build_and_run_command([script_path, "input 1"])
        userxbit.return_value = True

        # Check if python-call is added if not supplied by shebang
        temp_file_fd, temp_file_path = tempfile.mkstemp(suffix=".py")
        os.close(temp_file_fd)
        misc.build_and_run_command([temp_file_path, "input 1"])
        assert mock_subproc_popen.call_args.args[0] == ["python", temp_file_path, "input 1"]
        os.remove(temp_file_path)

        # Have to fake these for it to work
        newsunpack.IONICE_COMMAND = "ionice"
        newsunpack.NICE_COMMAND = "nice"
        userxbit.return_value = True
        misc.build_and_run_command([script_path, "input 1"])
        assert mock_subproc_popen.call_args.args[0] == [
            "nice",
            "--adjustment=-7",
            "ionice",
            "-t",
            "-n9",
            "-c7",
            script_path,
            "input 1",
        ]
