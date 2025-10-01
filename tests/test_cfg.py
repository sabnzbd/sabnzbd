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
tests.test_cfg - Testing functions in cfg.py
"""
import sys
import pytest

import sabnzbd.cfg as cfg


class TestValidators:
    def test_clean_nice_ionice_parameters_allowed(self):
        """Allowed nice and ionice parameters
        https://linux.die.net/man/1/nice
        https://linux.die.net/man/1/ionice
        """

        def assert_allowed(inp_value):
            """Helper function to check for block"""
            msg, value = cfg.clean_nice_ionice_parameters(inp_value)
            assert msg is None
            assert value == inp_value

        # nice
        assert_allowed("-n1")
        assert_allowed("-n-11")
        assert_allowed("-n 3")
        assert_allowed("-n -4")
        assert_allowed("--adjustment=11")
        assert_allowed("--adjustment=-7")
        assert_allowed("--adjustment 20")
        assert_allowed("--adjustment -8")

        # ionice
        assert_allowed("-c1")
        assert_allowed("-c-11")
        assert_allowed("-c 3")
        assert_allowed("-c -4")
        assert_allowed("--classdata=1")
        assert_allowed("--classdata=-11")
        assert_allowed("--classdata 3")
        assert_allowed("--classdata -4")
        assert_allowed("-t")
        assert_allowed("--ignore")
        assert_allowed("-c 11 -n 12 -t")
        assert_allowed("-c 11 --classdata=12 --ignore")
        assert_allowed("--ignore -n9 --class=7")
        assert_allowed("-t -n9 -c7")

    def test_clean_nice_ionice_parameters_blocked(self):
        """Should all be blocked"""

        def assert_blocked(inp_value):
            """Helper function to check for block"""
            msg, value = cfg.clean_nice_ionice_parameters(inp_value)
            assert msg
            assert msg.startswith("Incorrect parameter")
            assert value is None

        assert_blocked("-ca")
        assert_blocked("-t11")
        assert_blocked("-p 11")
        assert_blocked("123")
        assert_blocked("/bin/sh /tmp/test.sh")
        assert_blocked("'/evil.sh' 11")
        assert_blocked("; 11")
        assert_blocked("python evil.py")
        assert_blocked("-n5 /bin/echo 666")
        assert_blocked("4 && test.sh")
        assert_blocked("-t | bla.py")
        assert_blocked("5 || now")
        assert_blocked("echo 'how;now;brown;cow'")
        assert_blocked("-c'echo'")
        assert_blocked("--classdata=;/bin/echo")
        assert_blocked("-h")
        assert_blocked("--help")
        assert_blocked("-h -c1")
        assert_blocked("-c1 --help")

    @pytest.mark.parametrize(
        "setting, is_correct_win, is_correct_unix",
        [
            ("-mlp", True, True),
            ("-Mlp", True, True),  # matching is case-insensitive
            ("-mlP", True, True),
            ("-MLP", True, True),
            ("-om", True, False),  # -om variants without argument
            ("-om1", True, False),
            ("-OM1", True, False),
            ("-om-", True, False),
            ("-om=foo", True, False),  # -om variants with argument
            ("-om1=foo,bar", True, False),
            ("-om-=f,o,o,b,a,r", True, False),
            ("-ri0", True, False),  # -ri without sleep time
            ("-ri6", True, False),
            ("-rI6", True, False),
            ("-ri15", True, False),
            ("-ri0:0", True, False),  # -ri with sleep time
            ("-ri6:42", True, False),
            ("-ri15:666", True, False),
            ("-ri0:1000", True, False),
            ("-ri6:666", True, False),
            ("-ri15:1", True, False),
            ("-mlp -ri0", True, False),  # combinations of valid parameters
            ("-mlp -ri0 -om", True, False),
            ("-om -mlp -ri0", True, False),
            ("-om -mlp", True, False),
            ("-ri15:200 -mlp", True, False),
            (None, True, True),  # empty setting
            ("", True, True),
            (" ", True, True),  # effectively empty; not a problem as none of these survive str.split()
            ("\t", True, True),
            ("\r\n", True, True),
            ("mlp", False, False),  # missing "-"
            ("om-=foobar", False, False),
            ("ri0", False, False),
            ("ri0:1000", False, False),
            ("--mlp", False, False),  # too many "-"
            ("--om-=foobar", False, False),
            ("--ri0", False, False),
            ("--ri0:1000", False, False),
            ("-ri0:-1", False, False),  # -ri with invalid sleep time
            ("-ri0:1001", False, False),
            ("-ri0:9876", False, False),
            ("-ri0:0123", False, False),
            ("-ri0:-1001", False, False),
            ("-ri0:blabla", False, False),
            ("-ri00:0", False, False),  # -ri with invalid priority
            ("-ri-1:100", False, False),
            ("-ri16:42", False, False),
            ("-ri1000:10", False, False),
            ("-ri06:66", False, False),
            ("-ri6=42", False, False),  # -ri with invalid sleep time separator
            ("-ri15 666", False, False),
            ("-mlp -ri42", False, False),  # combinations of partially invalid parameters
            ("-mlp -ri0:12345 -om", False, False),
            ("-mlp --ri12:345 -om", False, False),
            ("-om -mlp=nope", False, False),
            ("-ri15=200 -mlp", False, False),
            ("-ri16:200 -mlp", False, False),
            ("-greed -is -good", False, False),  # non-existent parameters
            ("-waddup?", False, False),
            ("-psecret", False, False),  # unsupported parameters
            ("-p-", False, False),
            ("-o+ -psecret", False, False),
            ("-p- -ai", False, False),
            ("-vp -ri6:666", False, False),
            ("-ri15:1 -huuuuuge", False, False),  # triggers a bug in argparse >=3.11 without add_help=False?
            ("-h", False, False),  # ensure argparse's automatic -h/--help is off
            ("-mlp -h", False, False),
            ("--help", False, False),
            ("--help -mlp", False, False),
            ("-mlp -scf -ri0", False, False),
            ("-mlp -ri0 -ppassword -om", False, False),
            ("-ommlp -ri0", False, False),  # missing spacing
            ("-om-mlp", False, False),
            ("-ri15:200-mlp", False, False),
            ("-om mlp -ri0", True, False),  # corner case: everything after -om gets interpreted as its argument
            ("/bin/sh /tmp/test.sh", False, False),  # script kiddies
            ("'/evil.sh' 11", False, False),
            ("; 11", False, False),
            ("python evil.py", False, False),
            ("-mlp /bin/echo 666", False, False),
            ("4 && test.sh", False, False),
            ("-mlp | bla.py", False, False),
            ("5 || now", False, False),
            ("echo 'how;now;brown;cow'", False, False),
            ("-mlp'echo'", False, False),
        ],
    )
    def test_supported_unrar_parameters(self, setting, is_correct_win, is_correct_unix):
        msg, value = cfg.supported_unrar_parameters(setting)
        is_correct = is_correct_win if sys.platform.startswith("win") else is_correct_unix

        if is_correct:
            assert msg == None
            assert value == setting
        else:
            assert msg
            assert msg.startswith("Incorrect parameter")
            assert value == None

    def test_validate_single_tag(self):
        assert cfg.validate_single_tag(["TV", ">", "HD"]) == (None, ["TV > HD"])
        assert cfg.validate_single_tag(["TV", ">", "HD", "Plus"]) == (None, ["TV", ">", "HD", "Plus"])
        assert cfg.validate_single_tag(["alt.bin", "alt.tv"]) == (None, ["alt.bin", "alt.tv"])
        assert cfg.validate_single_tag(["alt.group"]) == (None, ["alt.group"])

    def test_all_lowercase(self):
        assert cfg.all_lowercase("") == (None, "")
        assert cfg.all_lowercase("Bla") == (None, "bla")
        assert cfg.all_lowercase(["foo", "bar"]) == (None, ["foo", "bar"])
        assert cfg.all_lowercase(["foo ", " bar"]) == (None, ["foo", "bar"])

    def test_lower_case_ext(self):
        assert cfg.lower_case_ext("") == (None, "")
        assert cfg.lower_case_ext(".Bla") == (None, "bla")
        assert cfg.lower_case_ext([".foo", ".bar"]) == (None, ["foo", "bar"])
        assert cfg.lower_case_ext([".foo ", " .bar"]) == (None, ["foo", "bar"])

    def test_validate_safedir(self):
        assert cfg.validate_safedir("", "", "def") == (None, "def")
        assert cfg.validate_safedir("", "C:\\", "") == (None, "C:\\")

    def test_validate_host(self):
        # valid input
        assert cfg.validate_host("127.0.0.1") == (None, "127.0.0.1")
        assert cfg.validate_host("0.0.0.0") == (None, "0.0.0.0")
        assert cfg.validate_host("1.1.1.1") == (None, "1.1.1.1")
        assert cfg.validate_host("::1") == (None, "::1")
        assert cfg.validate_host("::") == (None, "::")

        # non-valid input. Should return None as second parameter
        assert not cfg.validate_host("0.0.0.0.")[1]  # Trailing dot
        assert not cfg.validate_host("kajkdjflkjasd")[1]  # does not resolve
        assert not cfg.validate_host("100")[1]  # just a number