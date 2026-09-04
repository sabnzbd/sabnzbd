#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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

import builtins
import datetime
import functools
import os
import socket
import subprocess
import sys
import tempfile
import wave
from contextlib import contextmanager, nullcontext
from functools import cached_property
from random import randint, sample
from unittest import mock

import pytest
import rarfile
import socks

from sabnzbd import lang, misc, newsunpack, cfg
from sabnzbd.config import ConfigCat, get_sorters, save_config
from sabnzbd.constants import (
    DEFAULT_PRIORITY,
    FORCE_PRIORITY,
    GUESSIT_SORT_TYPES,
    HIGH_PRIORITY,
    NORMAL_PRIORITY,
)
from sabnzbd.misc import SABRarFile
from tests.testhelper import SAB_BASE_DIR


@pytest.fixture
def reset_language(compiled_language_files, monkeypatch):
    """Provide a compiled-translations environment for a test and guarantee the global
    translation state is restored on teardown"""
    monkeypatch.setattr(lang, "_DOMAIN", lang._DOMAIN)
    monkeypatch.setattr(lang, "_LOCALEDIR", lang._LOCALEDIR)
    monkeypatch.setitem(builtins.__dict__, "T", builtins.__dict__.get("T"))
    monkeypatch.setitem(builtins.__dict__, "TT", builtins.__dict__.get("TT"))
    yield compiled_language_files
    # Reset to the default (English) translators regardless of what the test selected
    lang.set_language()


class TestMisc:
    @staticmethod
    def assertTime(offset, age):
        assert offset == misc.calc_age(age, trans=True)
        assert offset == misc.calc_age(age, trans=False)

    def test_timeformat24h(self):
        assert "%H:%M:%S" == misc.time_format("%H:%M:%S")
        assert "%H:%M" == misc.time_format("%H:%M")

    @pytest.mark.config({"ampm": True})
    def test_timeformatampm(self, monkeypatch):
        monkeypatch.setattr(misc, "HAVE_AMPM", True)
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
            ("SomeCategory", "1", "SomeScript", ("SomeCategory", 1, "SomeScript")),
            ("none", 0, "default", (None, 0, None)),
            ("Movies", "", "default", ("Movies", None, None)),
            ("none", 0, "Default", (None, 0, None)),
            ("other", "-1", "Default", ("other", None, None)),
            ("none", "None", "default", (None, None, None)),
            ("some", "none", "script", ("some", None, "script")),
            ("none", "NONE", "Default", (None, None, None)),
            # pp must be a PP_LOOKUP key or None
            ("none", "2", "default", (None, 2, None)),
            ("none", 3, "default", (None, 3, None)),
            # Out-of-range ints are invalid
            ("", "10", "default", (None, None, None)),
            ("none", "15", "", (None, None, None)),
            ("none", 4, "default", (None, None, None)),
            # Non-numeric never passes as a string
            ("none", "-c", "default", (None, 0, None)),
            ("none", "echo pwned", "default", (None, 0, None)),
            ("none", "2; rm -rf /", "default", (None, 0, None)),
            ("none", "1.5", "default", (None, 0, None)),
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

        # Values that round up to the next unit should be shown in that unit
        assert "1023 K" == misc.to_units(1024**2 - 1024)
        assert "1.0 M" == misc.to_units(1024**2 - 1)
        assert "-1.0 M" == misc.to_units(-(1024**2 - 1))
        assert "1.0 MBla" == misc.to_units(1024**2 - 1, postfix="Bla")
        assert "1023.9 M" == misc.to_units(1024**3 - 1024**2 // 8)
        assert "1.0 G" == misc.to_units(1024**3 - 1)
        assert "1.0 T" == misc.to_units(1024**4 - 1)
        assert "1.0 P" == misc.to_units(1024**5 - 1)

    def test_unit_back_and_forth(self):
        assert 100 == misc.from_units(misc.to_units(100))
        assert 1024 == misc.from_units(misc.to_units(1024))
        assert 1024**3 == misc.from_units(misc.to_units(1024**3))

        # Negative numbers are not supported
        assert 100 == misc.from_units(misc.to_units(-100))

    def test_caller_name(self):
        def set_config(settings_dict):
            """Change config-values on the fly, per test"""

            def set_config_decorator(func):
                @functools.wraps(func)
                def wrapper_func(*args, **kwargs):
                    # Setting up as requested
                    for item, val in settings_dict.items():
                        getattr(cfg, item).set(val)

                    # Perform test
                    value = func(*args, **kwargs)

                    # Reset values
                    for item in settings_dict:
                        getattr(cfg, item).set(getattr(cfg, item).default)
                    return value

                return wrapper_func

            return set_config_decorator

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

    @pytest.mark.config({"cleanup_list": [".exe", ".nzb"]})
    def test_on_cleanup_list(self):
        assert misc.on_cleanup_list("test.exe")
        assert misc.on_cleanup_list("TEST.EXE")
        assert misc.on_cleanup_list("longExeFIlanam.EXe")
        assert not misc.on_cleanup_list("testexe")
        assert misc.on_cleanup_list("test.nzb")
        assert not misc.on_cleanup_list("test.nzb", skip_nzb=True)
        assert not misc.on_cleanup_list("test.exe.lnk")

    @pytest.mark.config({"cleanup_list": ["Thumbs.db"]})
    def test_on_cleanup_list_exact_filenames(self):
        # Exact filename matching (case-insensitive)
        assert misc.on_cleanup_list("Thumbs.db")
        assert misc.on_cleanup_list("thumbs.db")
        assert misc.on_cleanup_list("THUMBS.DB")
        assert not misc.on_cleanup_list("Thumbs.db.bak")
        assert not misc.on_cleanup_list("not_thumbs.db")

    @pytest.mark.config({"cleanup_list": ["*.tmp", "cleanup.*"]})
    def test_on_cleanup_list_wildcard_patterns(self):
        # Wildcard filename patterns
        assert misc.on_cleanup_list("file.tmp")
        assert misc.on_cleanup_list("temp.tmp")
        assert misc.on_cleanup_list("FILE.TMP")
        assert not misc.on_cleanup_list("file.tmp.bak")
        assert misc.on_cleanup_list("cleanup.log")
        assert misc.on_cleanup_list("cleanup.txt")
        assert misc.on_cleanup_list("CLEANUP.LOG")
        assert not misc.on_cleanup_list("cleanup")

    # cleanup_list is always lowercased by validator
    @pytest.mark.config({"cleanup_list": ["images/*", "*/test.jpg", "cache/*.log", "deep/*/pic.png", "temp\\*.tmp"]})
    def test_on_cleanup_list_path_patterns(self):
        # Path patterns with relative paths
        assert misc.on_cleanup_list("file.jpg", relative_path="images/file.jpg")
        assert misc.on_cleanup_list("pic.png", relative_path="images/pic.png")
        assert not misc.on_cleanup_list("file.jpg", relative_path="file.jpg")
        assert misc.on_cleanup_list("test.jpg", relative_path="subfolder/test.jpg")
        assert misc.on_cleanup_list("test.jpg", relative_path="deep/nested/test.jpg")
        assert not misc.on_cleanup_list("other.jpg", relative_path="subfolder/other.jpg")
        assert misc.on_cleanup_list("error.log", relative_path="cache/error.log")
        assert not misc.on_cleanup_list("error.log", relative_path="logs/error.log")
        # Case-insensitive path matching
        assert misc.on_cleanup_list("file.jpg", relative_path="IMAGES/file.jpg")
        # Wildcard with paths: deep/*/pic.png uses fnmatch which treats * as matching any chars including /
        assert misc.on_cleanup_list("pic.png", relative_path="deep/nested/pic.png")
        assert misc.on_cleanup_list("pic.png", relative_path="deep/nested/subfolder/pic.png")
        # Cross-platform: patterns with backslashes in config are normalized at match time
        # temp\*.tmp pattern should match temp/file.tmp
        assert misc.on_cleanup_list("file.tmp", relative_path="temp/file.tmp")
        # Cross-platform: relative paths with backslashes (from os.path.relpath on Windows)
        # should also work with forward slash patterns
        assert misc.on_cleanup_list("pic.png", relative_path="deep\\nested\\pic.png")

    # cleanup_list is always lowercased by validator
    @pytest.mark.config({"cleanup_list": ["exe", "thumbs.db", "*.tmp"]})
    def test_on_cleanup_list_mixed(self):
        # Mixed list of extensions, filenames, and patterns
        assert misc.on_cleanup_list("test.exe")
        assert misc.on_cleanup_list("Thumbs.db")
        assert misc.on_cleanup_list("temp.tmp")
        assert not misc.on_cleanup_list("test.txt")

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

    def test_format_time_string_locale(self, reset_language):
        locale_dir = reset_language
        lang.set_locale_info("SABnzbd", locale_dir)
        lang.set_language("de")
        assert "1 Sekunde" == misc.format_time_string(1)
        assert "10 Sekunden" == misc.format_time_string(10)
        assert "1 Minuten" == misc.format_time_string(60)
        assert "1 Stunde 1 Minuten 1 Sekunde" == misc.format_time_string(60 * 60 + 60 + 1)
        assert "1 Tag 59 Sekunden" == misc.format_time_string(86400 + 59)
        assert "2 Tage 2 Stunden 2 Sekunden" == misc.format_time_string(2 * 86400 + 2 * 60 * 60 + 2)

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
        """These cannot be resolved by name alone; they are handled by inspecting
        the actual media duration when the file is available (see #2083 tests below)."""
        assert misc.is_sample(name) != result

    @staticmethod
    def _write_wav(path: str, seconds: float):
        """Create a real WAV file of the given length (pure Python, no external tools)"""
        framerate = 8000
        with wave.open(path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(framerate)
            wav.writeframes(b"\x00\x00" * int(framerate * seconds))

    def test_get_media_duration(self, tmp_path):
        wav_file = os.path.join(tmp_path, "tone.wav")
        self._write_wav(wav_file, 2.5)
        assert misc.get_media_duration(wav_file) == pytest.approx(2.5, abs=0.1)

        # Not a media file and a non-existent file both yield no duration
        not_media = os.path.join(tmp_path, "notmedia.bin")
        with open(not_media, "wb") as fp:
            fp.write(b"this is not a media file")
        assert misc.get_media_duration(not_media) is None
        assert misc.get_media_duration(os.path.join(tmp_path, "does_not_exist.mkv")) is None

    @pytest.mark.parametrize(
        "name",
        [
            "Not Death Proof (2022) 1080p x264 (DD5.1) BE Subs.mkv",
            "Proof.of.Everything.(2042).4320p.x266-4U.mkv",
            "Crime_Scene_S01E13_Free_Sample_For_Sale_480p-OhDear.mp4",
            "Sample That 2011 480p WEB-DL.H265-aMiGo.avi",
        ],
    )
    def test_is_sample_long_media_not_a_sample(self, name, tmp_path, monkeypatch):
        """Real content whose title contains 'sample'/'proof' must not be flagged as
        a sample once the actual (long) media file is available on disk (#2083)."""
        media_file = os.path.join(tmp_path, name)
        self._write_wav(media_file, 2.0)
        # Treat anything over 1s as "long" so the short test file counts as real content
        monkeypatch.setattr(misc, "SAMPLE_MAX_DURATION", 1)
        # The name alone still trips the detector...
        assert misc.is_sample(name) is True
        # ...but with the real (long) file on disk it is correctly kept
        assert misc.is_sample(media_file) is False

    def test_is_sample_short_media_still_a_sample(self, tmp_path):
        """A genuinely short media file matching the sample pattern stays a sample"""
        media_file = os.path.join(tmp_path, "Something.1080p.H264-EMRG-sample.avi")
        self._write_wav(media_file, 2.0)
        assert misc.is_sample(media_file) is True

    def test_is_sample_unanalysable_file_falls_back_to_name(self, tmp_path):
        """When the file cannot be analysed, fall back to the name-based result"""
        non_media = os.path.join(tmp_path, "file-sample.mkv")
        with open(non_media, "wb") as fp:
            fp.write(b"not really an mkv")
        assert misc.is_sample(non_media) is True
        # A non-sample name is never a sample, regardless of the file on disk
        assert misc.is_sample(os.path.join(tmp_path, "regular-movie.mkv")) is False

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
    @pytest.mark.config(
        lambda params: {
            "local_ranges": params["local_ranges"],
        }
    )
    def test_is_local_addr(self, value, local_ranges, result):
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
    @pytest.mark.config(
        lambda params: {
            "movie_rename_limit": params["movie_limit"],
            "episode_rename_limit": params["episode_limit"],
            "movie_sort_extra": params["movie_sort_extra"],
            "enable_tv_sorting": params["tv_enabled"],
            "tv_sort_string": params["tv_str"],
            "tv_categories": params["tv_cats"],
            "enable_movie_sorting": params["movie_enabled"],
            "movie_sort_string": params["movie_str"],
            "movie_categories": params["movie_cats"],
            "enable_date_sorting": params["date_enabled"],
            "date_sort_string": params["date_str"],
            "date_categories": params["date_cats"],
            "language": "en",  # Avoid translated sorter names in the test
        }
    )
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
        def _func():
            # Delete any leftover/pre-defined new-style sorters
            if existing_sorters := get_sorters():
                for config in list(existing_sorters.keys()):
                    existing_sorters[config].delete()
            assert not get_sorters()

            # Run conversion
            misc.convert_sorter_settings()

            # Persisting is a no-op here (no INI file backs the config in this barebones
            # test); save_config() returns False rather than raising. The in-memory result
            # is what's verified below.
            save_config()

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

    @pytest.mark.parametrize(
        "argument, name, password",
        [
            ("my_awesome_nzb_file{{password}}", "my_awesome_nzb_file", "password"),
            ("file_with_text_after_pw{{passw0rd}}_[180519]", "file_with_text_after_pw", "passw0rd"),
            ("file_without_pw", "file_without_pw", None),
            ("multiple_pw{{first-pw}}_{{second-pw}}", "multiple_pw", "first-pw}}_{{second-pw"),  # Greed is Good
            ("デビアン", "デビアン", None),  # Unicode
            ("Gentoo_Hobby_Edition {{secret}}", "Gentoo_Hobby_Edition", "secret"),  # Space between name and password
            ("Test {{secret}}.nzb", "Test", "secret"),
            ("Mandrake{{top{{secret}}", "Mandrake", "top{{secret"),  # Double opening {{
            ("Красная}}{{Шляпа}}", "Красная}}", "Шляпа"),  # Double closing }}
            ("{{Jobname{{PassWord}}", "{{Jobname", "PassWord"),  # {{ at start
            ("Hello/kITTY", "Hello", "kITTY"),  # Notation with slash
            ("Hello/kITTY.nzb", "Hello", "kITTY"),  # Notation with slash and extension
            ("/Jobname", "/Jobname", None),  # Slash at start
            ("Jobname/Top{{Secret}}", "Jobname", "Top{{Secret}}"),  # Slash with braces
            ("Jobname / Top{{Secret}}", "Jobname", "Top{{Secret}}"),  # Slash with braces and extra spaces
            ("Jobname / Top{{Secret}}.nzb", "Jobname", "Top{{Secret}}"),
            ("לינוקס/معلومات سرية", "לינוקס", "معلومات سرية"),  # LTR with slash
            ("לינוקס{{معلومات سرية}}", "לינוקס", "معلومات سرية"),  # LTR with brackets
            ("thư điện tử password=mật_khẩu", "thư điện tử", "mật_khẩu"),  # Password= notation
            ("password=PartOfTheJobname", "password=PartOfTheJobname", None),  # Password= at the start
            ("Job password=Test.par2", "Job", "Test"),  # Password= including extension
            ("Job}}Name{{FTW", "Job}}Name{{FTW", None),  # Both {{ and }} present but incorrect order (no password)
            ("./Text", "./Text", None),  # Name would end up empty after the function strips the dot
        ],
    )
    def test_scan_password(self, argument, name, password):
        assert misc.scan_password(argument) == (name, password)

    @pytest.mark.parametrize(
        "subject, filename",
        [
            ('Great stuff (001/143) - "Filename.txt" yEnc (1/1)', "Filename.txt"),
            (
                '"910a284f98ebf57f6a531cd96da48838.vol01-03.par2" yEnc (1/3)',
                "910a284f98ebf57f6a531cd96da48838.vol01-03.par2",
            ),
            ('Subject-KrzpfTest [02/30] - ""KrzpfTest.part.nzb"" yEnc', "KrzpfTest.part.nzb"),
            (
                '[PRiVATE]-[WtFnZb]-[Supertje-_S03E11-12_-blabla_+_blabla_WEBDL-480p.mkv]-[4/12] - "" yEnc 9786 (1/1366)',
                "Supertje-_S03E11-12_-blabla_+_blabla_WEBDL-480p.mkv",
            ),
            (
                '[N3wZ] MAlXD245333\\::[PRiVATE]-[WtFnZb]-[Show.S04E04.720p.AMZN.WEBRip.x264-GalaxyTV.mkv]-[1/2] - "" yEnc  293197257 (1/573)',
                "Show.S04E04.720p.AMZN.WEBRip.x264-GalaxyTV.mkv",
            ),
            (
                'reftestnzb bf1664007a71 [1/6] - "20b9152c-57eb-4d02-9586-66e30b8e3ac2" yEnc (1/22) 15728640',
                "20b9152c-57eb-4d02-9586-66e30b8e3ac2",
            ),
            (
                "Re: REQ Author Child's The Book-Thanks much - Child, Lee - Author - The Book.epub (1/1)",
                "REQ Author Child's The Book-Thanks much - Child, Lee - Author - The Book.epub",
            ),
            ('63258-0[001/101] - "63258-2.0" yEnc (1/250) (1/250)', "63258-2.0"),
            # If specified between ", the extension is allowed to be too long
            ('63258-0[001/101] - "63258-2.0toolong" yEnc (1/250) (1/250)', "63258-2.0toolong"),
            (
                "Singer - A Album (2005) - [04/25] - 02 Sweetest Somebody (I Know).flac",
                "Singer - A Album (2005) - [04/25] - 02 Sweetest Somebody (I Know).flac",
            ),
            ("<>random!>", "<>random!>"),
            ("nZb]-[Supertje-_S03E11-12_", "nZb]-[Supertje-_S03E11-12_"),
            ("Bla [Now it's done.exe]", "Now it's done.exe"),
            # If specified between [], the extension should be a valid one
            ("Bla [Now it's done.123nonsense]", "Bla [Now it's done.123nonsense]"),
            ('[PRiVATE]-[WtFnZb]-[00000.clpi]-[1/46] - "" yEnc  788 (1/1)', "00000.clpi"),
            (
                '[PRiVATE]-[WtFnZb]-[Video_(2001)_AC5.1_-RELEASE_[TAoE].mkv]-[1/23] - "" yEnc 1234567890 (1/23456)',
                "Video_(2001)_AC5.1_-RELEASE_[TAoE].mkv",
            ),
            (
                "[PRiVATE]-[WtFnZb]-[219]-[1/series.name.s01e01.1080p.web.h264-group.mkv] - "
                " yEnc (1/[PRiVATE] \\c2b510b594\\::686ea969999193.155368eba4965e56a8cd263382e012.f2712fdc::/97bd201cf931/) 1 (1/0)",
                "series.name.s01e01.1080p.web.h264-group.mkv",
            ),
            (
                "[PRiVATE]-[WtFnZb]-[/More.Bla.S02E01.1080p.WEB.h264-EDITH[eztv.re].mkv-WtF[nZb]/"
                'More.Bla.S02E01.1080p.WEB.h264-EDITH.mkv]-[1/2] - "" yEnc  2990558544 (1/4173)',
                "More.Bla.S02E01.1080p.WEB.h264-EDITH[eztv.re].mkv",
            ),
        ],
    )
    def test_name_extractor(self, subject, filename):
        assert misc.subject_name_extractor(subject) == filename


def ipv6_loopback_available() -> bool:
    """Not every CI runner can bind ::1, so check instead of assuming"""
    if not socket.has_ipv6:
        return False
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
            sock.bind(("::1", 0))
        return True
    except OSError:
        return False


skip_without_ipv6 = pytest.mark.skipif(not ipv6_loopback_available(), reason="No usable IPv6 loopback")


def low_ports_are_privileged() -> bool:
    """Whether binding port 80 needs privileges for the user running the tests"""
    if sys.platform.startswith("win") or not hasattr(os, "geteuid") or os.geteuid() == 0:
        return False
    try:
        # Linux allows the privileged range to be moved, including down to nothing
        with open("/proc/sys/net/ipv4/ip_unprivileged_port_start") as sysctl:
            return int(sysctl.read().strip()) > 80
    except OSError:
        return True


skip_without_privileged_ports = pytest.mark.skipif(
    not low_ports_are_privileged(), reason="Low ports are not privileged for this user"
)


class TestPortIsFree:
    """Tests for misc.port_is_free() and misc.find_free_port()"""

    @staticmethod
    @contextmanager
    def _listener(host: str = "127.0.0.1", family: int = socket.AF_INET):
        """Listen on an OS-assigned port on host, yielding that port."""
        sock = socket.socket(family, socket.SOCK_STREAM)
        # Match port_is_free, so a port left in TIME_WAIT by an earlier test
        # cannot make this bind fail
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, 0))
            sock.listen(1)
            yield sock.getsockname()[1]
        finally:
            sock.close()

    @staticmethod
    @contextmanager
    def _listener_in_scan_range():
        """Listen on a port low enough for find_free_port() to scan onwards from.
        OS-assigned ports land in the dynamic range, above its 49151 ceiling."""
        for port in range(10000, 10500, 5):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                sock.listen(1)
            except OSError:
                sock.close()
                continue
            try:
                yield port
            finally:
                sock.close()
            return
        pytest.skip("No free port available in the scan range")

    @staticmethod
    def _released_port(host: str = "127.0.0.1", family: int = socket.AF_INET) -> int:
        """Return a port that was bindable a moment ago."""
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return sock.getsockname()[1]

    def test_free_port_returns_true(self):
        assert misc.port_is_free("127.0.0.1", self._released_port()) is True

    def test_occupied_port_returns_false(self):
        with self._listener() as port:
            assert misc.port_is_free("127.0.0.1", port) is False

    @pytest.mark.parametrize(
        "host, family",
        [
            ("0.0.0.0", socket.AF_INET),
            ("", socket.AF_INET),
            ("127.0.0.1", socket.AF_INET),
            ("::", socket.AF_INET6),
            ("::1", socket.AF_INET6),
        ],
    )
    def test_binds_the_host_it_was_given(self, host, family):
        """The previous version remapped the bind-all addresses to 127.0.0.1, so
        it probed the wrong address and, for ::, the wrong family as well.

        Asserted against the bind call rather than by watching two sockets fight
        over a port, because whether a wildcard and a specific address may share
        one is decided by the kernel and differs on Linux, macOS and Windows."""
        with mock.patch("sabnzbd.misc.socket.socket") as fake_socket:
            misc.port_is_free(host, 8080)
        assert fake_socket.call_args.args[0] == family
        fake_socket.return_value.bind.assert_called_once_with((host, 8080))

    def test_free_port_is_actually_bindable(self):
        """The property that matters: True has to mean uvicorn can bind it."""
        port = self._released_port()
        assert misc.port_is_free("127.0.0.1", port) is True
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))

    @skip_without_ipv6
    def test_occupied_ipv6_port_returns_false(self):
        with self._listener("::1", socket.AF_INET6) as port:
            assert misc.port_is_free("::1", port) is False

    @skip_without_ipv6
    def test_ipv4_listener_does_not_block_ipv6(self):
        """A port held on 127.0.0.1 says nothing about the same port on ::1."""
        with self._listener("127.0.0.1") as port:
            assert misc.port_is_free("::1", port) is True

    def test_non_local_host_raises(self):
        """An address that is not ours cannot be bound on any port, so it must not
        look like an ordinary busy port (192.0.2.0/24 is TEST-NET-1)."""
        with pytest.raises(misc.HostNotAvailableError):
            misc.port_is_free("192.0.2.1", 8080)

    def test_find_free_port_propagates_host_not_available(self):
        with pytest.raises(misc.HostNotAvailableError):
            misc.find_free_port("192.0.2.1", 8080)

    def test_unresolvable_host_returns_false(self):
        assert misc.port_is_free("no-such-host.invalid", 8080) is False

    def test_bind_web_socket_reserves_the_port(self):
        """The whole point of handing uvicorn a ready-made socket: from here on
        nothing else can take the port. Binding alone is not enough for that, a
        socket only reserves a port once it listens."""
        sock = misc.bind_web_socket("127.0.0.1", 0)
        try:
            host, port = sock.getsockname()[:2]
            assert host == "127.0.0.1"
            assert port > 0
            assert misc.port_is_free("127.0.0.1", port) is False
        finally:
            sock.close()

    def test_bind_web_socket_closes_socket_on_failure(self):
        """A failed bind must not leak the file descriptor."""
        with self._listener() as port:
            with pytest.raises(OSError):
                misc.bind_web_socket("127.0.0.1", port)

    @staticmethod
    def _barred_socket():
        """Patch the probe's socket so binding is refused for lack of privileges."""
        sock = mock.MagicMock()
        sock.bind.side_effect = PermissionError("Permission denied")
        return mock.patch("sabnzbd.misc.socket.socket", return_value=sock)

    def test_barred_port_raises(self):
        """A port we may not use is a different problem from an occupied one, so
        it must not come back as a plain False."""
        with self._barred_socket(), pytest.raises(PermissionError):
            misc.port_is_free("0.0.0.0", 80)

    @skip_without_privileged_ports
    def test_low_port_raises_permission_error(self):
        """Guards the premise: the platform really does report this as EACCES."""
        with pytest.raises(PermissionError):
            misc.port_is_free("127.0.0.1", 80)

    def test_find_free_port_propagates_permission_error(self):
        """Scanning on past a barred port could only end in a misleading answer."""
        with self._barred_socket(), pytest.raises(PermissionError):
            misc.find_free_port("0.0.0.0", 80)

    def test_find_free_port_returns_port_in_scan_range(self):
        port = misc.find_free_port("127.0.0.1", 10000)
        assert port is not None
        assert 10000 <= port <= 10045

    def test_find_free_port_skips_occupied(self):
        with self._listener_in_scan_range() as port:
            free = misc.find_free_port("127.0.0.1", port)
            assert free is not None
            assert free > port
            assert misc.port_is_free("127.0.0.1", free) is True

    def test_find_free_port_above_ceiling(self):
        """49152 and up is the dynamic range, so it is never scanned."""
        assert misc.find_free_port("127.0.0.1", 49200) is None

    def test_find_free_port_rejects_port_zero(self):
        """Binding port 0 always succeeds, which would return a misleading 0."""
        assert misc.find_free_port("127.0.0.1", 0) is None


class TestBuildAndRunCommand:
    # Path should exist
    @cached_property
    def script_path(self):
        return os.path.join(SAB_BASE_DIR, "test_misc.py")

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

    @pytest.mark.platform("linux")
    @pytest.mark.config({"nice": "--adjustment=-7", "ionice": "-t -n9 -c7"})
    @mock.patch("sabnzbd.misc.userxbit")
    @mock.patch("subprocess.Popen")
    def test_linux_features(self, mock_subproc_popen, userxbit, monkeypatch):
        monkeypatch.setattr(newsunpack, "NICE_COMMAND", None)
        monkeypatch.setattr(newsunpack, "IONICE_COMMAND", None)

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
        monkeypatch.setattr(newsunpack, "IONICE_COMMAND", "ionice")
        monkeypatch.setattr(newsunpack, "NICE_COMMAND", "nice")
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


class TestSABRarFile:
    @pytest.mark.parametrize(
        "test_dir, rar_files, password, expected_correct",
        [
            (
                "tests/data/basic_rar3",
                ["testfile.rar"],
                "NOT_ENCRYPTED_AND_CHECK_NOT_SUPPORTED",
                True,
            ),
            (
                "tests/data/basic_rar3_64",
                ["testfile.rar"],
                "CHECK_NOT_SUPPORTED",
                True,
            ),
            (
                "tests/data/basic_rar5",
                ["testfile.rar"],
                "NOT_ENCRYPTED",
                True,
            ),
            (
                "tests/data/basic_rar5_64_header_blake2",
                ["testfile.rar"],
                "HEADER_ENCRYPTION_WRONG_PASSWORD",
                False,
            ),
            (
                "tests/data/basic_rar5_64_header_blake2",
                ["testfile.rar"],
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
                True,
            ),
            (
                "tests/data/basic_rar5_64",
                ["testfile.rar"],
                "WRONG_PASSWORD",
                False,
            ),
            (
                "tests/data/basic_rar5_64",
                ["testfile.rar"],
                "75f8c9f91969b42eaaadc389739df9ed65e8970f9ad333a146e4f73e3875b69a",
                True,
            ),
        ],
    )
    def test_rar5_check_password(self, test_dir, rar_files, password, expected_correct):
        expected = nullcontext() if expected_correct else pytest.raises(rarfile.RarWrongPassword)

        for rar_file in rar_files:
            with SABRarFile(os.path.join(test_dir, rar_file), part_only=True) as zf:
                with expected:
                    zf.setpassword(password)
                if zf._file_parser.has_header_encryption() and expected_correct:
                    assert zf.namelist()

    @pytest.mark.parametrize(
        "test_dir, rar_files, expected_files",
        [
            (
                "tests/data/basic_rar5_64",
                ["testfile.rar"],
                ["My_Test_Download.bin", "testfile.bin", "Testfile_1234.bin"],
            ),
        ],
    )
    def test_rar5_check_password_after_parse(self, test_dir, rar_files, expected_files):
        """The password check should occur after parse finishes so
        that infolist is fully populated when headers are not encrypted"""
        for rar_file in rar_files:
            with SABRarFile(os.path.join(test_dir, rar_file), part_only=True) as zf:
                with pytest.raises(rarfile.RarWrongPassword):
                    zf.setpassword("WRONG_PASSWORD")
                assert zf.namelist() == expected_files


@pytest.mark.platform("linux")
class TestCgroupMemoryLimit:
    """Container memory detection, see _cgroup_memory_limit()"""

    GIGI = 1024**3
    V2_HIGH = "/sys/fs/cgroup/memory.high"
    V2_MAX = "/sys/fs/cgroup/memory.max"
    V1_MAX = "/sys/fs/cgroup/memory/memory.limit_in_bytes"

    def patched_open(self, files: dict[str, str]):
        real_open = open

        def _open(path, *args, **kwargs):
            if str(path).startswith("/sys/fs/cgroup"):
                if str(path) in files:
                    return mock.mock_open(read_data=files[str(path)])()
                raise FileNotFoundError(path)
            return real_open(path, *args, **kwargs)

        return mock.patch("builtins.open", _open)

    def test_no_cgroup_files(self):
        with self.patched_open({}):
            assert misc._cgroup_memory_limit() is None

    def test_v2_max_only(self):
        with self.patched_open({self.V2_MAX: str(2 * self.GIGI)}):
            assert misc._cgroup_memory_limit() == 2 * self.GIGI

    def test_v2_unlimited(self):
        with self.patched_open({self.V2_MAX: "max", self.V2_HIGH: "max"}):
            assert misc._cgroup_memory_limit() is None

    def test_v2_high_below_max_wins(self):
        """memory.high throttles, so it is the budget we should size against"""
        with self.patched_open({self.V2_HIGH: str(self.GIGI), self.V2_MAX: str(4 * self.GIGI)}):
            assert misc._cgroup_memory_limit() == self.GIGI

    def test_v2_high_unset_falls_back_to_max(self):
        with self.patched_open({self.V2_HIGH: "max", self.V2_MAX: str(2 * self.GIGI)}):
            assert misc._cgroup_memory_limit() == 2 * self.GIGI

    def test_v1_limit(self):
        with self.patched_open({self.V1_MAX: str(512 * 1024 * 1024)}):
            assert misc._cgroup_memory_limit() == 512 * 1024 * 1024

    def test_v1_unlimited_sentinel(self):
        """v1 reports a huge sentinel rather than a keyword when unlimited"""
        with self.patched_open({self.V1_MAX: "9223372036854771712"}):
            assert misc._cgroup_memory_limit() is None

    def test_garbage_is_ignored(self):
        with self.patched_open({self.V2_MAX: "not-a-number"}):
            assert misc._cgroup_memory_limit() is None

    def test_get_memory_clamps_to_cgroup(self):
        with self.patched_open({self.V2_MAX: str(self.GIGI)}):
            with mock.patch("sabnzbd.misc._physical_memory", return_value=64 * self.GIGI):
                assert misc.get_memory() == self.GIGI

    def test_get_memory_keeps_physical_when_lower(self):
        with self.patched_open({self.V2_MAX: str(64 * self.GIGI)}):
            with mock.patch("sabnzbd.misc._physical_memory", return_value=8 * self.GIGI):
                assert misc.get_memory() == 8 * self.GIGI

    def test_get_memory_uses_cgroup_when_physical_unknown(self):
        """_physical_memory() returns None when it cannot be determined"""
        with self.patched_open({self.V2_MAX: str(self.GIGI)}):
            with mock.patch("sabnzbd.misc._physical_memory", return_value=None):
                assert misc.get_memory() == self.GIGI

    def test_get_memory_zero_when_nothing_known(self):
        with self.patched_open({}):
            with mock.patch("sabnzbd.misc._physical_memory", return_value=None):
                assert misc.get_memory() == 0


class TestSetSocks5Proxy:
    """The proxy is applied by replacing socket.socket, which also affects the sockets
    our own web server accepts. It must keep reporting who is connecting to us."""

    @pytest.fixture(autouse=True)
    def restore_socket(self):
        yield
        socks.socksocket.default_proxy = None
        socket.socket = misc._ORIGINAL_SOCKET

    @pytest.mark.config({"socks5_proxy_url": "socks5://proxy.example:1080"})
    def test_proxy_is_set(self):
        misc.set_socks5_proxy()
        assert socket.socket is misc.ProxiedSocket
        assert socks.socksocket.default_proxy[:3] == (socks.SOCKS5, "proxy.example", 1080)

    def test_no_proxy_leaves_the_socket_alone(self):
        misc.set_socks5_proxy()
        assert socket.socket is misc._ORIGINAL_SOCKET
        assert not socks.socksocket.default_proxy

    @pytest.mark.config({"socks5_proxy_url": "socks5://proxy.example:1080"})
    def test_accepted_connection_still_has_a_peer(self):
        """Without this, every request reaches the web server without a client
        address and is refused by check_access()"""
        with misc._ORIGINAL_SOCKET(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            misc.set_socks5_proxy()

            # Connect without the proxy, only the accepted side is of interest here
            with misc._ORIGINAL_SOCKET(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(10)
                client.connect(listener.getsockname())
                accepted, address = listener.accept()
                with accepted:
                    assert isinstance(accepted, misc.ProxiedSocket)
                    assert accepted.getpeername() == client.getsockname() == address

    @pytest.mark.config({"socks5_proxy_url": "socks5://proxy.example:1080"})
    def test_timeout_is_applied_to_a_socket_without_a_peer(self):
        """PySocks only applies a timeout to the real socket when getpeername() does not
        raise, so a listening socket must not be left blocking by setblocking(False)"""
        misc.set_socks5_proxy()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            assert isinstance(listener, misc.ProxiedSocket)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.setblocking(False)
            assert misc._ORIGINAL_SOCKET.gettimeout(listener) == 0.0
            with pytest.raises(BlockingIOError):
                listener.accept()
