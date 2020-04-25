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

from sabnzbd import lang
from sabnzbd import misc
from sabnzbd.config import ConfigCat
from tests.testhelper import *


class TestMisc:
    def assertTime(self, offset, age):
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
        # Need to create the Default category
        # Otherwise it will try to save the config
        ConfigCat("*", {})
        assert ("*", "", "Default", -100) == misc.cat_to_opts("*")
        assert ("*", "", "Default", -100) == misc.cat_to_opts("Nonsense")
        assert ("*", 1, "Default", -100) == misc.cat_to_opts("*", pp=1)
        assert ("*", 1, "test.py", -100) == misc.cat_to_opts("*", pp=1, script="test.py")

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
