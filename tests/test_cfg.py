#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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
import sabnzbd.cfg as cfg
import socket


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

    def test_validate_single_tag(self):
        assert cfg.validate_single_tag(["TV", ">", "HD"]) == (None, ["TV > HD"])
        assert cfg.validate_single_tag(["TV", ">", "HD", "Plus"]) == (
            None,
            ["TV", ">", "HD", "Plus"],
        )
        assert cfg.validate_single_tag(["alt.bin", "alt.tv"]) == (
            None,
            ["alt.bin", "alt.tv"],
        )
        assert cfg.validate_single_tag(["alt.group"]) == (None, ["alt.group"])

    def test_lower_case_ext(self):
        assert cfg.lower_case_ext("") == (None, "")
        assert cfg.lower_case_ext(".Bla") == (None, "bla")
        assert cfg.lower_case_ext([".foo", ".bar"]) == (None, ["foo", "bar"])
        assert cfg.lower_case_ext([".foo ", " .bar"]) == (None, ["foo", "bar"])

    def test_validate_host(self):
        assert cfg.validate_host("127.0.0.1") == (None, "127.0.0.1")
        assert cfg.validate_host("0.0.0.0") == (None, "0.0.0.0")
        assert cfg.validate_host("1.1.1.1") == (None, "1.1.1.1")
        assert cfg.validate_host("::1") == (None, "::1")
        assert cfg.validate_host("::") == (None, "::")
        assert cfg.validate_host("www.example.com")[1]
        assert cfg.validate_host(socket.gethostname())[1]

        assert cfg.validate_host("0.0.0.0.") == (None, None)  # Trailing dot
        assert cfg.validate_host("kajkdjflkjasd") == (None, None)  # does not resolve
        assert cfg.validate_host("100") == (None, None)  # just a number
