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
tests.test_misc - Testing functions in misc.py
"""

import datetime
import subprocess
import sys
import tempfile
from unittest import mock

from sabnzbd import lang
from sabnzbd import misc
from sabnzbd import newsunpack
from sabnzbd.config import ConfigCat
from sabnzbd.constants import HIGH_PRIORITY, FORCE_PRIORITY, DEFAULT_PRIORITY, NORMAL_PRIORITY
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
        assert ("movies", 3, "test.py", FORCE_PRIORITY) == misc.cat_to_opts("movies", priority=FORCE_PRIORITY)

        # If the category has DEFAULT_PRIORITY, it should use the priority of the *-category (NORMAL_PRIORITY)
        # If the script-name is Default for a category, it should use the script of the *-category (None)
        ConfigCat("software", {"priority": DEFAULT_PRIORITY, "script": "Default"})
        assert ("software", 3, "None", NORMAL_PRIORITY) == misc.cat_to_opts("software")
        assert ("software", 3, "None", FORCE_PRIORITY) == misc.cat_to_opts("software", priority=FORCE_PRIORITY)

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

    @pytest.mark.parametrize(
        "test_input, expected_output",
        [
            (["cmd1", 9, "cmd3"], '"cmd1" "9" "cmd3"'),  # sending all commands as valid string
            (["", "cmd1", "5"], '"" "cmd1" "5"'),  # sending blank string
            (["cmd1", None, "cmd3", "tail -f"], '"cmd1" "" "cmd3" "tail -f"'),  # sending None in command
            (["cmd1", 0, "ps ux"], '"cmd1" "" "ps ux"'),  # sending 0
        ],
    )
    def test_list_to_cmd(self, test_input, expected_output):
        """Test to convert list to a cmd.exe-compatible command string"""

        res = misc.list2cmdline(test_input)
        # Make sure the output is cmd.exe-compatible
        assert res == expected_output

    @pytest.mark.parametrize(
        "value, result",
        [
            ("1.2.3.4", True),
            ("255.255.255.255", True),
            ("0.0.0.0", True),
            ("10.11.12.13", True),
            ("127.0.0.1", True),
            ("400.500.600.700", False),
            ("blabla", False),
            ("2001::1", False),
            ("::1", False),
            ("::", False),
            ("example.org", False),
            (None, False),
            ("", False),
            ("3.2.0", False),
            (-42, False),
            ("::ffff:192.168.1.100", False),
        ],
    )
    def test_is_ipv4_addr(self, value, result):
        assert misc.is_ipv4_addr(value) is result

    @pytest.mark.parametrize(
        "value, result",
        [
            ("2001::1", True),
            ("::1", True),
            ("[2001::1]", True),
            ("fdd6:5a2d:3f20:0:14b0:d8f4:ccb9:fab6", True),
            ("::", True),
            ("a::b", True),
            ("1.2.3.4", False),
            ("255.255.255.255", False),
            ("0.0.0.0", False),
            ("10.11.12.13", False),
            ("127.0.0.1", False),
            ("400.500.600.700", False),
            ("blabla", False),
            (666, False),
            ("example.org", False),
            (None, False),
            ("", False),
            ("[1.2.3.4]", False),
            ("2001:1", False),
            ("2001::[2001::1]", False),
            ("::ffff:192.168.1.100", True),
        ],
    )
    def test_is_ipv6_addr(self, value, result):
        assert misc.is_ipv6_addr(value) is result

    @pytest.mark.parametrize(
        "value, result",
        [
            ("::1", True),
            ("[::1]", True),
            ("127.0.0.1", True),
            ("127.255.0.0", True),
            ("127.1.2.7", True),
            ("fdd6:5a2d:3f20:0:14b0:d8f4:ccb9:fab6", False),
            ("::", False),
            ("a::b", False),
            ("1.2.3.4", False),
            ("255.255.255.255", False),
            ("0.0.0.0", False),
            ("10.11.12.13", False),
            ("400.500.600.700", False),
            ("localhost", False),
            (-666, False),
            ("example.org", False),
            (None, False),
            ("", False),
            ("[127.6.6.6]", False),
            ("2001:1", False),
            ("2001::[2001::1]", False),
            ("::ffff:192.168.1.100", False),
            ("::ffff:1.1.1.1", False),
            ("::ffff:127.0.0.1", True),
        ],
    )
    def test_is_loopback_addr(self, value, result):
        assert misc.is_loopback_addr(value) is result

    @pytest.mark.parametrize(
        "value, result",
        [
            ("localhost", True),
            ("::1", True),
            ("[::1]", True),
            ("localhost", True),
            ("127.0.0.1", True),
            ("127.255.0.0", True),
            ("127.1.2.7", True),
            (".local", False),
            ("test.local", False),
            ("fdd6:5a2d:3f20:0:14b0:d8f4:ccb9:fab6", False),
            ("::", False),
            ("a::b", False),
            ("1.2.3.4", False),
            ("255.255.255.255", False),
            ("0.0.0.0", False),
            ("10.11.12.13", False),
            ("400.500.600.700", False),
            (-1984, False),
            ("example.org", False),
            (None, False),
            ("", False),
            ("[127.6.6.6]", False),
            ("2001:1", False),
            ("2001::[2001::1]", False),
            ("::ffff:192.168.1.100", False),
            ("::ffff:1.1.1.1", False),
            ("::ffff:127.0.0.1", True),
        ],
    )
    def test_is_localhost(self, value, result):
        assert misc.is_localhost(value) is result

    @pytest.mark.parametrize(
        "value, result",
        [
            ("10.11.12.13", True),
            ("172.16.2.81", True),
            ("192.168.255.255", True),
            ("169.254.42.42", True),  # Link-local
            ("fd00::ffff", True),  # Part of fc00::/7, IPv6 "Unique Local Addresses"
            ("fe80::a1", True),  # IPv6 Link-local
            ("::1", False),
            ("localhost", False),
            ("127.0.0.1", False),
            ("2001:1337:babe::", False),
            ("172.32.32.32", False),  # Near but not part of 172.16.0.0/12
            ("100.64.0.1", False),  # Test net
            ("[2001::1]", False),
            ("::", False),
            ("::a:b:c", False),
            ("1.2.3.4", False),
            ("255.255.255.255", False),
            ("0.0.0.0", False),
            ("127.0.0.1", False),
            ("400.500.600.700", False),
            ("blabla", False),
            (-666, False),
            ("example.org", False),
            (None, False),
            ("", False),
            ("[1.2.3.4]", False),
            ("2001:1", False),
            ("2001::[2001::1]", False),
            ("::ffff:192.168.1.100", True),
            ("::ffff:1.1.1.1", False),
            ("::ffff:127.0.0.1", False),
        ],
    )
    def test_is_lan_addr(self, value, result):
        assert misc.is_lan_addr(value) is result

    @pytest.mark.parametrize(
        "ip, subnet, result",
        [
            ("2001:c0f:fee::1", "2001:c0f:fee", True),  # Old-style range setting
            ("2001:c0f:fee::1", "2001:c0f:FEE:", True),
            ("2001:c0f:fee::1", "2001:c0FF:ffee", False),
            ("2001:c0f:fee::1", "2001:c0ff:ffee:", False),
            ("2001:C0F:FEE::1", "2001:c0f:fee::/48", True),
            ("2001:c0f:fee::1", "2001:c0f:fee::/112", True),
            ("2001:c0f:fee::1", "::/0", True),  # Subnet equals the entire IPv6 address space
            ("2001:c0f:fee::1", "2001:c0:ffee::/48", False),
            ("2001:c0f:fee::1", "2001:c0ff:ee::/112", False),
            ("2001:c0f:fEE::1", "2001:c0f:fee:eeee::/48", False),  # Invalid subnet
            ("2001:c0f:Fee::1", "2001:c0f:fee:/64", False),
            ("2001:c0f:fee::1", "2001:c0f:fee:eeee:3:2:1:0/112", False),
            ("2001:c0f:fee::1", "2001:c0f:fee::1", True),  # Single-IP subnet
            ("2001:c0f:fee::1", "2001:c0f:fee::1/128", True),
            ("2001:c0f:fee::1", "2001:c0f:fee::2", False),
            ("2001:c0f:fee::1", "2001:c0f:fee::2/128", False),
            ("::1", "::/127", True),
            ("::1", "2021::/64", False),  # Localhost not in subnet
            ("192.168.43.21", "192.168.43", True),  # Old-style subnet setting
            ("192.168.43.21", "192.168.43.", True),
            ("192.168.43.21", "192.168.4", False),
            ("192.168.43.21", "192.168.4.", False),
            ("10.11.12.13", "10", True),  # Bad old-style setting (allowed 100.0.0.0/6, 104.0.0.0/6 and 108.0.0.0/7)
            ("10.11.12.13", "10.", True),  # Correct version of the same (10.0.0.0/8 only)
            ("108.1.2.3", "10", False),  # This used to be allowed with the bad setting!
            ("108.1.2.3", "10.", False),
            ("192.168.43.21", "192.168.0.0/16", True),
            ("192.168.43.21", "192.168.0.0/255.255.255.0", True),
            ("::ffff:192.168.43.21", "192.168.43.0/24", True),  # IPv4-mapped IPv6 ("dual-stack") notation
            ("::FFff:192.168.43.21", "192.168.43.0/24", True),
            ("::ffff:192.168.12.34", "192.168.43.0/24", False),
            ("::ffFF:192.168.12.34", "192.168.43.0/24", False),
            ("192.168.43.21", "192.168.43.0/26", True),
            ("200.100.50.25", "0.0.0.0/0", True),  # Subnet equals the entire IPv4 address space
            ("192.168.43.21", "10.0.0.0/8", False),
            ("192.168.43.21", "192.168.1.0/22", False),
            ("192.168.43.21", "192.168.43.21/24", False),  # Invalid subnet
            ("192.168.43.21", "192.168.43/24", False),
            ("192.168.43.21", "192.168.43.0/16", False),
            ("192.168.43.21", "192.168.43.0/255.252.0.0", False),
            ("192.168.43.21", "192.168.43.21", True),  # Single-IP subnet
            ("192.168.43.21", "192.168.43.21/32", True),
            ("192.168.43.21", "192.168.43.21/255.255.255.255", True),
            ("192.168.43.21", "192.168.43.12", False),
            ("192.168.43.21", "192.168.43.0/32", False),
            ("192.168.43.21", "43.21.168.192/255.255.255.255", False),
            ("127.0.0.1", "127.0.0.0/31", True),
            ("127.0.1.1", "127.0.0.0/24", False),  # Localhost not in subnet
            ("111.222.33.44", "111:222:33::/96", False),  # IPv4/IPv6 mixup
            ("111:222:33::44", "111.222.0.0/24", False),
            ("aaaa::1:2:3:4", "f:g:h:i:43:21::/112", False),  # Invalid subnet
            ("4.3.2.1", "654.3.2.1.0/24", False),
            (None, "1.2.3.4/32", False),  # Missing input
            ("1:a:2:b::", None, False),
            (None, None, False),
        ],
    )
    def test_ip_in_subnet(self, ip, subnet, result):
        misc.ip_in_subnet(ip, subnet) is result

    @pytest.mark.parametrize(
        "ip, result",
        [
            ("::ffff:127.0.0.1", "127.0.0.1"),
            ("::FFFF:127.0.0.1", "127.0.0.1"),
            ("::ffff:192.168.1.255", "192.168.1.255"),
            ("::ffff:8.8.8.8", "8.8.8.8"),
            ("2007::2021", "2007::2021"),
            ("::ffff:2007:2021", "::ffff:2007:2021"),
            ("2007::ffff:2021", "2007::ffff:2021"),
            ("12.34.56.78", "12.34.56.78"),
            ("foobar", "foobar"),
            ("0:0:0:0:0:ffff:8.8.4.4", "8.8.4.4"),
            ("0000:0000:0000:0000:0000:ffff:1.0.0.1", "1.0.0.1"),
            ("0000::0:ffff:1.1.1.1", "1.1.1.1"),
        ],
    )
    def test_strip_ipv4_mapped_notation(self, ip, result):
        misc.strip_ipv4_mapped_notation(ip) == result


class TestBuildAndRunCommand:
    # Path should exist
    script_path = os.path.join(SAB_BASE_DIR, "test_misc.py")

    def test_none_check(self):
        with pytest.raises(IOError):
            misc.build_and_run_command([None])

    @mock.patch("subprocess.Popen")
    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows tests")
    def test_win(self, mock_subproc_popen):
        # Needed for priority and startupinfo check
        import win32process
        import win32con

        misc.build_and_run_command(["test.cmd", "input 1"])
        assert mock_subproc_popen.call_args[0][0] == ["test.cmd", "input 1"]
        assert mock_subproc_popen.call_args[1]["creationflags"] == win32process.NORMAL_PRIORITY_CLASS
        assert mock_subproc_popen.call_args[1]["startupinfo"].dwFlags == win32process.STARTF_USESHOWWINDOW
        assert mock_subproc_popen.call_args[1]["startupinfo"].wShowWindow == win32con.SW_HIDE

        misc.build_and_run_command(["test.py", "input 1"])
        assert mock_subproc_popen.call_args[0][0] == ["python.exe", "test.py", "input 1"]
        assert mock_subproc_popen.call_args[1]["creationflags"] == win32process.NORMAL_PRIORITY_CLASS
        assert mock_subproc_popen.call_args[1]["startupinfo"].dwFlags == win32process.STARTF_USESHOWWINDOW
        assert mock_subproc_popen.call_args[1]["startupinfo"].wShowWindow == win32con.SW_HIDE

        # See: https://github.com/sabnzbd/sabnzbd/issues/1043
        misc.build_and_run_command(["UnRar.exe", "\\\\?\\C:\\path\\"])
        assert mock_subproc_popen.call_args[0][0] == ["UnRar.exe", "\\\\?\\C:\\path\\"]
        misc.build_and_run_command(["UnRar.exe", "\\\\?\\C:\\path\\"], flatten_command=True)
        assert mock_subproc_popen.call_args[0][0] == '"UnRar.exe" "\\\\?\\C:\\path\\"'

    @mock.patch("sabnzbd.misc.userxbit")
    @mock.patch("subprocess.Popen")
    def test_std_override(self, mock_subproc_popen, userxbit):
        userxbit.return_value = True
        misc.build_and_run_command([self.script_path], stderr=subprocess.DEVNULL)
        assert mock_subproc_popen.call_args[1]["stderr"] == subprocess.DEVNULL

    @set_platform("linux")
    @set_config({"nice": "--adjustment=-7", "ionice": "-t -n9 -c7"})
    @mock.patch("sabnzbd.misc.userxbit")
    @mock.patch("subprocess.Popen")
    def test_linux_features(self, mock_subproc_popen, userxbit):
        # Should break on no-execute permissions
        userxbit.return_value = False
        with pytest.raises(IOError):
            misc.build_and_run_command([self.script_path, "input 1"])
        userxbit.return_value = True

        # Check if python-call is added if not supplied by shebang
        temp_file_fd, temp_file_path = tempfile.mkstemp(suffix=".py")
        os.close(temp_file_fd)
        misc.build_and_run_command([temp_file_path, "input 1"])
        assert mock_subproc_popen.call_args[0][0] == [
            sys.executable if sys.executable else "python",
            temp_file_path,
            "input 1",
        ]
        os.remove(temp_file_path)

        # Have to fake these for it to work
        newsunpack.IONICE_COMMAND = "ionice"
        newsunpack.NICE_COMMAND = "nice"
        userxbit.return_value = True
        misc.build_and_run_command([self.script_path, "input 1"])
        assert mock_subproc_popen.call_args[0][0] == [
            "nice",
            "--adjustment=-7",
            "ionice",
            "-t",
            "-n9",
            "-c7",
            self.script_path,
            "input 1",
        ]
