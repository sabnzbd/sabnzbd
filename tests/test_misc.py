#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
from random import randint, sample

from sabnzbd import lang
from sabnzbd import misc
from sabnzbd import newsunpack
from sabnzbd.config import ConfigCat, get_sorters, save_config
from sabnzbd.constants import HIGH_PRIORITY, FORCE_PRIORITY, DEFAULT_PRIORITY, NORMAL_PRIORITY, GUESSIT_SORT_TYPES
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

    def test_is_none(self):
        assert misc.is_none(None) is True
        assert misc.is_none(0) is True
        assert misc.is_none(False) is True
        assert misc.is_none("None") is True
        assert misc.is_none("nOne") is True

        assert misc.is_none(True) is False
        assert misc.is_none(1) is False
        assert misc.is_none(True) is False
        assert misc.is_none("Not None") is False

    def test_clean_comma_separated_list(self):
        assert misc.clean_comma_separated_list("") == []
        assert misc.clean_comma_separated_list(None) == []
        assert misc.clean_comma_separated_list(123) == []
        assert misc.clean_comma_separated_list("a,b") == ["a", "b"]
        assert misc.clean_comma_separated_list(",b") == ["b"]
        assert misc.clean_comma_separated_list("   a  ,  b  ") == ["a", "b"]
        assert misc.clean_comma_separated_list(["a  ", "  b", ""]) == ["a", "b"]

    def test_cmp(self):
        assert misc.cmp(1, 2) < 0
        assert misc.cmp(2, 1) > 0
        assert misc.cmp(1, 1) == 0

    @pytest.mark.parametrize(
        "cat, pp, script, expected",
        [
            (None, None, None, (None, None, None)),
            ("", "", "", (None, None, None)),
            ("none", "-1", "default", (None, None, None)),
            ("SomeCategory", "5", "SomeScript", ("SomeCategory", "5", "SomeScript")),
            ("none", 0, "default", (None, 0, None)),
            ("Movies", "", "default", ("Movies", None, None)),
            ("", "10", "default", (None, "10", None)),
            ("none", "15", "", (None, "15", None)),
            ("none", 0, "Default", (None, 0, None)),
            ("other", "-1", "Default", ("other", None, None)),
            ("none", "None", "default", (None, None, None)),
            ("some", "none", "script", ("some", None, "script")),
            ("none", "NONE", "Default", (None, None, None)),
        ],
    )
    def test_cat_pp_script_sanitizer(self, cat, pp, script, expected):
        assert misc.cat_pp_script_sanitizer(cat, pp, script) == expected

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
        assert "" == misc.to_units("foobar")
        assert "1 K" == misc.to_units(1024)
        assert "1 KBla" == misc.to_units(1024, postfix="Bla")
        assert "1.0 M" == misc.to_units(1024 * 1024)
        assert "1.0 M" == misc.to_units(1024 * 1024 + 10)
        assert "-1.0 M" == misc.to_units(-1024 * 1024)
        assert "10.0 M" == misc.to_units(1024 * 1024 * 10)
        assert "100.0 M" == misc.to_units(1024 * 1024 * 100)
        assert "9.8 G" == misc.to_units(1024 * 1024 * 10000)
        assert "1024.0 P" == misc.to_units(1024**6)

    def test_unit_back_and_forth(self):
        assert 100 == misc.from_units(misc.to_units(100))
        assert 1024 == misc.from_units(misc.to_units(1024))
        assert 1024**3 == misc.from_units(misc.to_units(1024**3))

        # Negative numbers are not supported
        assert 100 == misc.from_units(misc.to_units(-100))

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
        # Reset language
        lang.set_language()

    def test_format_time_left(self):
        assert "0:00:00" == misc.format_time_left(0)
        assert "0:00:00" == misc.format_time_left(-1)
        assert "0:00:01" == misc.format_time_left(1)
        assert "0:01:01" == misc.format_time_left(60 + 1)
        assert "0:11:10" == misc.format_time_left(60 * 11 + 10)
        assert "3:11:10" == misc.format_time_left(60 * 60 * 3 + 60 * 11 + 10)
        assert "13:11:10" == misc.format_time_left(60 * 60 * 13 + 60 * 11 + 10)
        assert "1:09:11:10" == misc.format_time_left(60 * 60 * 33 + 60 * 11 + 10)

    def test_format_time_left_short(self):
        assert "0:00" == misc.format_time_left(0, short_format=True)
        assert "0:01" == misc.format_time_left(1, short_format=True)
        assert "1:01" == misc.format_time_left(60 + 1, short_format=True)
        assert "11:10" == misc.format_time_left(60 * 11 + 10, short_format=True)
        assert "3:11:10" == misc.format_time_left(60 * 60 * 3 + 60 * 11 + 10, short_format=True)
        assert "13:11:10" == misc.format_time_left(60 * 60 * 13 + 60 * 11 + 10, short_format=True)
        assert "1:09:11:10" == misc.format_time_left(60 * 60 * 33 + 60 * 11 + 10, short_format=True)

    @pytest.mark.parametrize(
        "value, default, expected, description",
        [
            (None, "", "", "Test with None value and default empty string"),
            (None, "default", "default", "Test with None value and default 'default'"),
            (0, "", "0", "Test with zero value"),
            (1, "", "1", "Test with one value"),
            (-1, "", "-1", "Test with negative one value"),
            (100, "", "100", "Test with 100 value"),
            ("abc", "", "abc", "Test with alphabetic string"),
            ("", "", "", "Test with empty string"),
            (True, "", "True", "Test with boolean True value"),
            (False, "", "False", "Test with boolean False value"),
            (0.0, "", "0.0", "Test with float zero value"),
            (1.5, "", "1.5", "Test with positive float value"),
            (-2.7, "", "-2.7", "Test with negative float value"),
            (complex(1, 1), "", "(1+1j)", "Test with complex number"),
            ([], "", "[]", "Test with empty list"),
            ([1, 2, 3], "", "[1, 2, 3]", "Test with list of integers"),
            ({}, "", "{}", "Test with empty dictionary"),
            ({"key": "value"}, "", "{'key': 'value'}", "Test with dictionary"),
            (set(), "", "set()", "Test with empty set"),
        ],
    )
    def test_str_conv(self, value, default, expected, description):
        assert misc.str_conv(value, default) == expected

    def test_int_conv(self):
        assert 0 == misc.int_conv("0")
        assert 10 == misc.int_conv("10")
        assert 10 == misc.int_conv(10)
        assert 10 == misc.int_conv(10.0)
        assert 0 == misc.int_conv(None)
        assert 1 == misc.int_conv(True)
        assert 0 == misc.int_conv(object)

    @pytest.mark.parametrize(
        "value, expected, description",
        [
            (None, False, "Test with None value"),
            (0, False, "Test with zero value"),
            ("0", False, "Test with zero string"),
            (1, True, "Test with one value"),
            (-1, True, "Test with negative one value"),
            (100, True, "Test with 100 value"),
            ("1", True, "Test with one string"),
            ("100", True, "Test with 100 string"),
            ("", False, "Test with empty string"),
            ("abc", False, "Test with non-numeric string"),
            ("true", False, "Test with 'true' string"),
            (True, True, "Test with boolean True value"),
            (False, False, "Test with boolean False value"),
            (0.0, False, "Test with float zero value"),
            (1.5, True, "Test with positive float value"),
            (-2.7, True, "Test with negative float value"),
            ("1.5", False, "Test with float string value"),
            ("0.0", False, "Test with float zero string value"),
        ],
    )
    def test_bool_conv(self, value, expected, description):
        assert misc.bool_conv(value) == expected, description

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
        "name, result",
        [
            ("Free.Open.Source.Movie.2001.1080p.WEB-DL.DD5.1.H264-FOSS", False),  # Not samples
            ("Setup.exe", False),
            ("23.123.hdtv-rofl", False),
            ("Something.1080p.WEB-DL.DD5.1.H264-EMRG-sample", True),  # Samples
            ("Something.1080p.WEB-DL.DD5.1.H264-EMRG-sample.ogg", True),
            ("Sumtin_Else_1080p_WEB-DL_DD5.1_H264_proof-EMRG", True),
            ("Wot.Eva.540i.WEB-DL.aac.H264-Groupie sample.mp4", True),
            ("file-sample.mkv", True),
            ("PROOF.JPG", True),
            ("Bla.s01e02.title.1080p.aac-sample proof.mkv", True),
            ("Bla.s01e02.title.1080p.aac-proof.mkv", True),
            ("Bla.s01e02.title.1080p.aac sample proof.mkv", True),
            ("Bla.s01e02.title.1080p.aac proof.mkv", True),
            ("Lwtn.s08e26.1080p.web.h264-glhf-sample.par2", True),
            ("Lwtn.s08e26.1080p.web.h264-glhf-sample.vol001-002.par2", True),
            ("Look at That 2011 540i WEB-DL.H265-NoSample", False),
        ],
    )
    def test_is_sample(self, name, result):
        assert misc.is_sample(name) == result

    @pytest.mark.parametrize(
        "name, result",
        [
            ("Not Death Proof (2022) 1080p x264 (DD5.1) BE Subs", False),  # Try to trigger some false positives
            ("Proof.of.Everything.(2042).4320p.x266-4U", False),
            ("Crime_Scene_S01E13_Free_Sample_For_Sale_480p-OhDear", False),
            ("Sample That 2011 480p WEB-DL.H265-aMiGo", False),
            ("NOT A SAMPLE.JPG", False),
        ],
    )
    def test_is_sample_known_false_positives(self, name, result):
        """We know these fail, but don't have a better solution for them at the moment."""
        assert misc.is_sample(name) != result

    @pytest.mark.parametrize(
        "test_input, expected_output",
        [
            (["cmd1", 9, "cmd3"], '"cmd1" "9" "cmd3"'),  # sending all commands as valid string
            (["", "cmd1", "5"], '"" "cmd1" "5"'),  # sending blank string
            (["cmd1", None, "cmd3", "tail -f"], '"cmd1" "" "cmd3" "tail -f"'),  # sending None in command
            (["cmd1", 0, "ps ux"], '"cmd1" "" "ps ux"'),  # sending 0
            (['pass"word', "command"], '"pass""word" "command"'),  # special escaping of unrar
        ],
    )
    def test_list2cmdline_unrar(self, test_input, expected_output):
        """Test to convert list to a cmd.exe-compatible command string"""
        res = misc.list2cmdline_unrar(test_input)
        # Make sure the output is cmd.exe-compatible
        assert res == expected_output

    def test_recursive_html_escape(self):
        """Very basic test if the recursive clean-up works"""
        input_test = {
            "foo": "<b>?ar'\"",
            "test_list": ["test&1", 'test"2'],
            "test_nested_list": [["test&1", 'test"2', 4]],
            "test_dict": {"test": ["test<>1", "#"]},
        }
        # Dict is updated in-place
        misc.recursive_html_escape(input_test)
        # Have to check them by hand
        assert input_test["foo"] == "&lt;b&gt;?ar&#x27;&quot;"
        assert input_test["test_list"] == ["test&amp;1", "test&quot;2"]
        assert input_test["test_nested_list"] == [["test&amp;1", "test&quot;2", 4]]
        assert input_test["test_dict"]["test"] == ["test&lt;&gt;1", "#"]

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
        "value, local_ranges, result",
        [
            ("10.11.12.13", None, True),
            ("172.16.2.81", None, True),
            ("192.168.255.255", None, True),
            ("169.254.42.42", None, True),  # Link-local
            ("fd00::ffff", None, True),  # Part of fc00::/7, IPv6 "Unique Local Addresses"
            ("fe80::a1", None, True),  # IPv6 Link-local
            ("::1", None, False),
            ("localhost", None, False),
            ("127.0.0.1", None, False),
            ("2001:1337:babe::", None, False),
            ("172.32.32.32", None, False),  # Near but not part of 172.16.0.0/12
            ("100.64.0.1", None, False),  # Test net
            ("[2001::1]", None, False),
            ("::", None, False),
            ("::a:b:c", None, False),
            ("1.2.3.4", None, False),
            ("255.255.255.255", None, False),
            ("0.0.0.0", None, False),
            ("127.0.0.1", None, False),
            ("400.500.600.700", None, False),
            ("blabla", None, False),
            (-666, None, False),
            ("example.org", None, False),
            (None, None, False),
            ("", None, False),
            ("[1.2.3.4]", None, False),
            ("2001:1", None, False),
            ("2001::[2001::1]", None, False),
            ("::ffff:192.168.1.100", None, True),
            ("::ffff:1.1.1.1", None, False),
            ("::ffff:127.0.0.1", None, False),
            ("10.11.12.13", "10.0.0.0/8", True),
            ("10.11.12.13", "12.34.56.78, 10.0.0.0/8", True),
            ("10.11.12.13", "10.0.0.0/24", False),
            ("172.16.2.81", "10.0.0.0/24", False),
            ("192.168.255.255", "2001::/64", False),
            ("2001:1337:babe::42", "2001:1337:babe::/48", True),
            ("2001:1337:babe::11", "1002:1337:babe::/48", False),
            ("2001:1337:babe::", "2001:1337:babe::/16", False),  # Invalid local range
            ("2001:1337:babe::", "1002:1337:babe::/8", False),  # Idem
            ("2001::1", "2001::/2", False),
            ("::", "1.2.3.0/26, 9.8.7.6", False),
            ("::a:b:c", "1.2.3.0/26, 9.8.7.6", False),
            ("1.2.3.4", "1.2.3.0/24, 9.8.7.6", True),
            ("1.2.3.4", "1.2.3.4/32, 9.8.7.6", True),
            ("1.2.3.4", "9.8.7.6, 1.2.3.4/32", True),
            ("1.2.3.4", "ffff:1234::/128, 1.2.3.4/32, 9.8.7.6", True),
            ("ffff:1234::0", "ffff:1234::/128, 1.2.3.4/32, 9.8.7.6", True),
            ("EEEE::ccc", "ffff:1234::/128, 1.2.3.4/32, 9.8.7.6", False),
            ("FFFFFFFF:1234::0", "ffff:1234::/128, 1.2.3.4/32, 9.8.7.6", False),
            ("1.2.3.4", "1.2.3.3/32, 9.8.7.6", False),
            ("1.2.3.4", "1.2.3.5/32, 9.8.7.6", False),
        ],
    )
    def test_is_local_addr(self, value, local_ranges, result):
        @set_config({"local_ranges": local_ranges})
        def _func():
            assert misc.is_local_addr(value) is result

        _func()

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

    def test_sort_to_opts(self):
        for result, sort_type in GUESSIT_SORT_TYPES.items():
            assert misc.sort_to_opts(sort_type) == result

    @pytest.mark.parametrize(
        "sort_type, result",
        [
            ("", 0),
            ("foobar", 0),
            (False, 0),
            (666, 0),
        ],
    )
    def test_sort_to_opts_edge_cases(self, sort_type, result):
        assert misc.sort_to_opts(sort_type) == result

    @pytest.mark.parametrize("movie_limit", ["", "42M"])
    @pytest.mark.parametrize("episode_limit", ["", "13M"])
    @pytest.mark.parametrize("movie_sort_extra", ["", "disc%1"])
    @pytest.mark.parametrize("tv_enabled", [True, False])
    @pytest.mark.parametrize("tv_str", ["", "foobar tv"])
    @pytest.mark.parametrize("tv_cats", [sample(["tv", "sports"], randint(0, 2))])
    @pytest.mark.parametrize("date_enabled", [True, False])
    @pytest.mark.parametrize("date_str", ["", "foobar date"])
    @pytest.mark.parametrize("date_cats", [sample(["date"], randint(0, 1))])
    @pytest.mark.parametrize("movie_enabled", [True, False])
    @pytest.mark.parametrize("movie_str", ["", "foobar movie"])
    @pytest.mark.parametrize("movie_cats", [[], ["movie"], ["movie", "horror", "docu"]])
    def test_convert_sorter_settings(
        self,
        movie_limit,
        episode_limit,
        movie_sort_extra,
        tv_enabled,
        tv_str,
        tv_cats,
        date_enabled,
        date_str,
        date_cats,
        movie_enabled,
        movie_str,
        movie_cats,
    ):
        @set_config(
            {
                "movie_rename_limit": movie_limit,
                "episode_rename_limit": episode_limit,
                "movie_sort_extra": movie_sort_extra,
                "enable_tv_sorting": tv_enabled,
                "tv_sort_string": tv_str,
                "tv_categories": tv_cats,
                "enable_movie_sorting": movie_enabled,
                "movie_sort_string": movie_str,
                "movie_categories": movie_cats,
                "enable_date_sorting": date_enabled,
                "date_sort_string": date_str,
                "date_categories": date_cats,
                "language": "en",  # Avoid translated sorter names in the test
            }
        )
        def _func():
            # Delete any leftover/pre-defined new-style sorters
            if existing_sorters := get_sorters():
                for config in list(existing_sorters.keys()):
                    try:
                        existing_sorters[config].delete()
                    except NameError as error:
                        if "CFG_OBJ" in str(error):
                            # Ignore failure to save the config to file in this very barebones test environment
                            pass
            assert not get_sorters()

            # Run conversion
            misc.convert_sorter_settings()

            try:
                save_config()
            except NameError as error:
                if "CFG_OBJ" in str(error):
                    # Once again, ignore failure to save the config
                    pass

            # Verify the resulting config
            new_sorters = get_sorters()
            new_sorter_count = 0

            for old_sorter_type, old_name, old_str, old_cats, old_enabled in (
                ("tv", "Series Sorting", tv_str, tv_cats, tv_enabled),
                ("date", "Date Sorting", date_str, date_cats, date_enabled),
                ("movie", "Movie Sorting", movie_str, movie_cats, movie_enabled),
            ):
                if not old_str or not old_cats or not old_enabled:
                    # Without these two essential variables, no new sorter config should be generated
                    assert old_name not in new_sorters.keys()
                    continue

                # Run basic checks on the new sorter
                assert new_sorters[old_name]
                new_sorter = new_sorters[old_name].get_dict()
                assert len(new_sorter) == 8

                # Handle the old, movie-specific sorting features
                size_limit = movie_limit if old_sorter_type == "movie" else episode_limit
                part_label = movie_sort_extra if old_sorter_type == "movie" else ""

                # Verify the entire new sorter config
                for key, value in (
                    ("name", old_name),
                    ("order", new_sorter_count),
                    ("min_size", size_limit),
                    ("multipart_label", part_label),
                    ("sort_string", old_str),
                    ("sort_cats", old_cats),
                    ("sort_type", [misc.sort_to_opts(old_sorter_type)]),
                    ("is_active", int(old_enabled)),
                ):
                    assert (new_sorter[key]) == value

                # Update counter
                new_sorter_count += 1

            # Verify no extra sorters appeared out of nowhere
            assert new_sorter_count == len(new_sorters)

        _func()


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
        misc.build_and_run_command(["UnRar.exe", "\\\\?\\C:\\path\\", "pass'\"word"], windows_unrar_command=True)
        assert mock_subproc_popen.call_args[0][0] == '"UnRar.exe" "\\\\?\\C:\\path\\" "pass\'""word"'

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

        # Make sure Windows UnRar patching stays on Windows
        test_cmd = ["unrar", "/home/", "pass'\"word"]
        misc.build_and_run_command(test_cmd, windows_unrar_command=True)
        assert mock_subproc_popen.call_args[0][0] == test_cmd

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
