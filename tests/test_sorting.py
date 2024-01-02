#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
tests.test_sorting - Testing functions in sorting.py
"""
import os
import pyfakefs
import re
import shutil
import sys
import datetime
from random import choice, choices, randint, sample
from string import ascii_letters
from unittest import mock

from sabnzbd import sorting
from sabnzbd.constants import IGNORED_MOVIE_FOLDERS, GUESSIT_PART_INDICATORS
from sabnzbd.filesystem import globber, get_ext
from sabnzbd.misc import sort_to_opts
from tests.testhelper import *


class TestSortingFunctions:
    @pytest.mark.parametrize(
        "name, result",
        [
            (
                "2147.Confinement.2015.1080p.WEB-DL.DD5.1.H264-EMRG",
                {"type": "movie", "title": "2147 Confinement"},
            ),  # Digit at the start
            (
                "2146.Confinement.1080p.WEB-DL.DD5.1.H264-EMRG",
                {"type": "movie", "title": "2146 Confinement"},
            ),  # No year, guessit sets type to episode
            ("Setup.exe", {"type": "unknown", "title": "Setup exe"}),  # Guessit uses 'movie' as its default type
            (
                "25.817.hdtv-rofl",
                {"type": "episode", "title": "25", "season": 8, "episode": 17},
            ),  # Guessit comes up with bad episode info: [25, 17]
            (
                "The.Wonders.of.Usenet.E08.2160p-SABnzbd",
                {"type": "episode", "season": 1, "episode": 8},
            ),  # Episode without season
            (
                "Glade Runner 2094 2022.avi",
                {"type": "movie", "title": "Glade Runner 2094", "year": 2022},
            ),  # Double year
            ("Micro.Maffia.s01.web.aac.x265-Tfoe{{Wollah}}", {"release_group": "Tfoe"}),  # Password in jobname
            ("No.Choking.Part.2.2008.360i-NotLOL", {"part": None, "title": "No Choking Part 2"}),  # Part property
            (
                "John.Hamburger.III.US.S01E01.OMG.WTF.BBQ.4320p.WEB.H265-HeliUM.mkv",
                {
                    "type": "episode",
                    "episode_title": "OMG WTF BBQ",
                    "screen_size": "4320p",
                    "title": "John Hamburger III",
                    "country": "US",
                },
            ),
            ("Test Movie 720p HDTV AAC x265 MYgroup-Sample", {"release_group": "MYgroup", "other": "Sample"}),
            ("Test Date Detection 22.07.14", {"date": datetime.date(2022, 7, 14)}),
            (None, None),  # Jobname missing
            ("", None),
        ],
    )
    def test_guess_what(self, name, result):
        """Test guessing quirks"""
        if not result:
            # Bad input
            with pytest.raises(ValueError):
                guess = sorting.guess_what(name)
        else:
            guess = sorting.guess_what(name)
            for key, value in result.items():
                if value is None:
                    # Property should not exist in the guess
                    assert key not in guess
                else:
                    assert guess[key] == value

    @pytest.mark.parametrize("platform", ["linux", "macos", "win32"])
    @pytest.mark.parametrize(
        "path, result_unix, result_win",
        [
            ("/tmp/test.file", True, True),
            ("/boot", True, True),
            ("/y.e.p", True, True),
            ("/ok/", True, True),
            ("/this.is.a/full.path", True, True),
            ("f:\\e.txt", False, True),
            ("\\\\relative.path", False, True),
            ("Z:\\some\\thing", False, True),
            ("Bitte ein Bit", False, False),
            ("this/is/not/an/abs.path", False, False),
            ("this\\is\\not\\an\\abs.path", False, False),
            ("AAA", False, False),
            ("", False, False),
        ],
    )
    def test_is_full_path(self, platform, path, result_unix, result_win):
        @set_platform(platform)
        def _func():
            result = result_win if sabnzbd.WIN32 else result_unix
            assert sorting.is_full_path(path) == result

        _func()

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows tests")
    @pytest.mark.parametrize(
        "path, result",
        [
            ("P:\\foo\\bar", "P:\\foo\\bar"),
            ("FOO\\bar\\", "FOO\\bar"),
            ("foo\\_bar_", "foo\\bar"),
            ("foo\\__bar", "foo\\bar"),
            ("foo\\bar__", "foo\\bar"),
            ("foo\\ bar ", "foo\\bar"),
            ("foo\\  bar", "foo\\bar"),
            ("E:\\foo\\bar  _", "E:\\foo\\bar"),
            ("E:\\foo_\\_bar", "E:\\foo\\bar"),
            ("E:\\foo._\\bar", "E:\\foo\\bar"),
            (".foo\\bar", "foo\\bar"),  # Dots
            ("E:\\\\foo\\bar\\...", "E:\\foo\\bar"),
            ("E:\\\\foo\\bar\\...", "E:\\foo\\bar"),
            ("E:\\foo_\\bar\\...", "E:\\foo\\bar"),
            ("\\\\some.path.\\foo\\_bar_", "\\\\some.path\\foo\\bar"),  # UNC
            ("\\\\some.path.\\foo\\_bar_", "\\\\some.path\\foo\\bar"),
            (r"\\?\UNC\SRVR\SHR\__File.txt__", r"\\SRVR\SHR\File.txt"),
            ("F:\\.path.\\  more\\foo  bar ", "F:\\path\\more\\foo  bar"),  # Drive letter
            ("c:\\.path.\\  more\\foo  bar \\ ", "c:\\path\\more\\foo  bar"),
            ("c:\\foo_.\\bar", "c:\\foo\\bar"),  # The remainder are all regression tests
            ("c:\\foo_ _\\bar", "c:\\foo\\bar"),
            ("c:\\foo. _\\bar", "c:\\foo\\bar"),
            ("c:\\foo. .\\bar", "c:\\foo\\bar"),
            ("c:\\foo. _\\bar", "c:\\foo\\bar"),
            ("c:\\foo. .\\bar", "c:\\foo\\bar"),
            ("c:\\__\\foo\\bar", "c:\\foo\\bar"),  # No double \\\\ when an entire element is stripped
            ("c:\\...\\foobar", "c:\\foobar"),
        ],
    )
    def test_strip_path_elements_win(self, path, result):
        def _func():
            assert sorting.strip_path_elements(path) == result

        _func()

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Unix tests")
    @pytest.mark.parametrize(
        "path, result",
        [
            ("/foo/bar", "/foo/bar"),
            ("FOO/bar/", "FOO/bar"),
            ("foo/_bar_", "foo/bar"),
            ("foo/__bar", "foo/bar"),
            ("foo/bar__", "foo/bar"),
            ("foo/ bar ", "foo/bar"),
            ("foo/  bar", "foo/bar"),
            ("/foo/bar  _", "/foo/bar"),
            ("/foo_/_bar", "/foo/bar"),
            ("/foo._/bar", "/foo./bar"),
            (".foo/bar", ".foo/bar"),  # Dots
            ("/foo/bar/...", "/foo/bar/..."),
            ("foo_\\bar\\...", "foo_\\bar\\..."),
            ("foo_./bar", "foo_./bar"),  # The remainder are all regression tests
            ("foo_ _/bar", "foo/bar"),
            ("foo. _/bar", "foo./bar"),
            ("foo. ./bar", "foo. ./bar"),
            ("foo. _/bar", "foo./bar"),
            ("/foo. ./bar", "/foo. ./bar"),
            ("/__/foo/bar", "/foo/bar"),  # No double // when an entire element is stripped
        ],
    )
    def test_strip_path_elements_unix(self, path, result):
        def _func():
            assert sorting.strip_path_elements(path) == result

        _func()

    @pytest.mark.parametrize(
        "path, result",
        [
            ("/Foo/Bar", "/Foo/Bar"),  # Nothing to do
            ("/{Foo}/Bar", "/foo/Bar"),
            ("{/Foo/B}ar", "/foo/bar"),
            ("/{F}oo/B{AR}", "/foo/Bar"),  # Multiple
            ("/F{{O}O/{B}A}R", "/Foo/baR"),  # Multiple, overlapping
            ("/F}oo/B{ar", "/Foo/Bar"),  # Wrong order, no lowercasing should be done but { and } removed still
            ("", ""),
        ],
    )
    def test_to_lowercase(self, path, result):
        assert sorting.to_lowercase(path) == result

    @pytest.mark.parametrize(
        "path, result",
        [
            ("/Foo/Bar", False),
            ("", False),
            ("%fn", True),
            (".%ext", True),
            ("%fn.%ext", True),
            ("{%fn}", True),  # A single closing lowercase marker is allowed
            ("{.%ext}", True),
            ("%fn{}", False),  # But not the opening lowercase marker
            (".%ext{}", False),
            ("%fn}}", False),  # Nor multiple closing lowercase markers
            (".%ext}}", False),
            ("%ext.%fn", True),
            ("%ext", False),  # Missing dot
            ("%fn.ext", False),
            (".ext", False),
            (".fn", False),
            ("", False),
        ],
    )
    def test_ends_in_file(self, path, result):
        assert sorting.ends_in_file(path) is result
        assert sorting.ends_in_file(os.path.join("/tmp", path)) is result  # Prepending makes no difference
        assert sorting.ends_in_file("foo.bar-" + path) is result
        assert sorting.ends_in_file(path + "-foo.bar") is False  # Appending does, obviously
        assert sorting.ends_in_file(os.path.join("/tmp", path + "-foo.bar")) is False

    @pytest.mark.parametrize("extra_file", [None, "Setup.exe", "cd1cd2cd3.cda"])
    @pytest.mark.parametrize("indicator", ["", "cd", "cd ", " cd", " cd ", "CD", "part", "diskette", "floppy "])
    @pytest.mark.parametrize(
        "files, result",
        [
            ([], None),  # Empty input
            (["foo.bar"], None),  # Single file
            (["foo", "bar"], None),  # No multipart files, without extension
            (["foo.txt", "bar.txt"], None),  # No multipart files, with extension
            (["foobar.txt", "foobar.ini"], None),  # No multipart files, same basename, different extension
            (["INDICATOR1.txt", "INDICATOR1.ini"], None),  # No multipart files, same basename, different extension
            (["INDICATOR.txt1", "INDICATOR.txt2"], None),  # No multipart files, same basename, sequential extension
            (
                ["INDICATOR1.txt", "INDICATOR2.txt", "INDICATOR3.txt"],
                {"1": "INDICATOR1.txt", "2": "INDICATOR2.txt", "3": "INDICATOR3.txt"},
            ),  # Sequential basename, same extension
            (
                ["INDICATOR1.txt1", "INDICATOR2.txt2", "INDICATOR3.txt3"],
                {"1": "INDICATOR1.txt1", "2": "INDICATOR2.txt2", "3": "INDICATOR3.txt3"},
            ),  # Sequential basename, sequential extension
            (
                ["INDICATOR1.foo", "INDICATOR2.bar", "INDICATOR3.!!!"],
                {"1": "INDICATOR1.foo", "2": "INDICATOR2.bar", "3": "INDICATOR3.!!!"},
            ),  # Sequential basename, different extension
            (
                ["foo-INDICATOR1.txt", "foo-INDICATOR2.txt"],
                {"1": "foo-INDICATOR1.txt", "2": "foo-INDICATOR2.txt"},
            ),  # Appended multipart indicator
            (["foo-INDICATOR1.txt1", "foo-INDICATOR2.txt2"], {"1": "foo-INDICATOR1.txt1", "2": "foo-INDICATOR2.txt2"}),
            (["foo-INDICATOR1.foo", "foo-INDICATOR2.bar"], {"1": "foo-INDICATOR1.foo", "2": "foo-INDICATOR2.bar"}),
            (
                ["INDICATOR1-bar.txt", "INDICATOR2-bar.txt"],
                {"1": "INDICATOR1-bar.txt", "2": "INDICATOR2-bar.txt"},
            ),  # Prepended multipart indicator
            (["INDICATOR1-bar.txt1", "INDICATOR2-bar.txt2"], {"1": "INDICATOR1-bar.txt1", "2": "INDICATOR2-bar.txt2"}),
            (["INDICATOR1-bar.foo", "INDICATOR2-bar.bar"], {"1": "INDICATOR1-bar.foo", "2": "INDICATOR2-bar.bar"}),
            (["foo-INDICATOR1.txt", "foo-INDICATOR1.txt"], None),  # Appended multipart indicator, duplicate key
            (["foo-INDICATOR1.txt1", "foo-INDICATOR1.txt2"], None),
            (["foo-INDICATOR1.foo", "foo-INDICATOR1.bar"], None),
            (["INDICATOR1-bar.txt", "INDICATOR1-bar.txt"], None),  # Prepended multipart indicator, duplicate key
            (["INDICATOR1-bar.txt1", "INDICATOR1-bar.txt2"], None),
            (["INDICATOR1-bar.foo", "INDICATOR1-bar.bar"], None),
            (["foo-INDICATOR1.txt", "foo-INDICATOR3.txt"], None),  # Appended multipart indicator, non-sequential keys
            (["foo-INDICATOR4.txt1", "foo-INDICATOR1.txt2"], None),
            (["foo-INDICATOR5.foo", "foo-INDICATOR8.bar"], None),
            (["INDICATOR4-bar.txt", "INDICATOR1-bar.txt"], None),  # Prepended multipart indicator, non-sequential keys
            (["INDICATOR7-bar.txt1", "INDICATOR1-bar.txt2"], None),
            (["INDICATOR9-bar.foo", "INDICATOR1-bar.bar"], None),
        ],
    )
    def test_check_for_multiple(self, extra_file, indicator, files, result):
        # Replace indicators in both function input and expected result
        if files:
            files = [f.replace("INDICATOR", indicator) for f in files]
        if result:
            result = {k: v.replace("INDICATOR", indicator) for k, v in result.items()}
        # Insert noise
        if extra_file:
            if len(files) > 0:
                # Never insert at the start as that can have decisive influence on the test result
                files.insert(randint(1, len(files)), extra_file)
            else:
                files.append(extra_file)
        # Only expect a result for known indicators
        if indicator.strip().lower() not in GUESSIT_PART_INDICATORS:
            result = None

        assert sorting.check_for_multiple(files) == result

    @pytest.mark.parametrize(
        "sort_string, job_name, multipart_label, result",
        [
            ("", "", "", None),  # Empty sort_string and job_name
            ("AAA", "", "", None),  # Empty job_name
            ("", "BBB", "", None),  # Empty sort_string
            ("%y/%r/%sn", "SABnzbd.ftw.2023.divx.480i-Team", "", "2023/480i/Sabnzbd Ftw/"),
            ("%y/%r/%sn.%ext", "SABnzbd.ftw.2023.divx.480i-Team", "", "2023/480i/Sabnzbd Ftw.ext"),
            ("{%s.n.%y.%r}-%GI<release_group>", "SABnzbd.ftw.2023.divx.480i-Team", "", "sabnzbd.ftw.2023.480i-Team/"),
            (
                "%s_n_%y_%r_%GI<release_group>_%1.%ext",
                "SABnzbd.ftw.2023.divx.480i-Team",
                "cd%1",
                "Sabnzbd_Ftw_2023_480i_Team_cd1.ext",
            ),
            (
                "{%s.n.%y.%r}-%GI<release_group>/%fn",
                "SABnzbd.ftw.2023.divx.480i-Team",
                "",
                "sabnzbd.ftw.2023.480i-Team/Original Filename.ext",
            ),
            ("%dn_%1.%ext", "SABnzbd.ftw.2023.divx.480i-Team", "cd%1", "SABnzbd.ftw.2023.divx.480i-Team_cd1.ext"),
        ],
    )
    def test_eval_sort(self, sort_string, job_name, multipart_label, result):
        if sabnzbd.WIN32 and result:
            result = result.replace("/", "\\")
        assert sorting.eval_sort(sort_string, job_name, multipart_label) == result

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Unix tests")
    def test_move_to_parent_directory_unix(self):
        # Standard files/dirs
        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            pyfakefs.fake_filesystem_unittest.set_uid(0)
            # Create a fake filesystem with some file content in a random base directory
            base_dir = "/" + os.urandom(4).hex() + "/" + os.urandom(2).hex()
            for test_dir in ["dir/2", "TEST/DIR2"]:
                ffs.fs.create_dir(base_dir + "/" + test_dir, perm_bits=755)
                assert os.path.exists(base_dir + "/" + test_dir) is True
            for test_file in ["dir/some.file", "TEST/DIR/FILE"]:
                ffs.fs.create_file(base_dir + "/" + test_file, int("0644", 8))
                assert os.path.exists(base_dir + "/" + test_file) is True

            return_path, return_status = sorting.move_to_parent_directory(base_dir + "/TEST")

            # Affected by move
            assert not os.path.exists(base_dir + "/TEST/DIR/FILE")  # Moved to subdir
            assert not os.path.exists(base_dir + "/TEST/DIR2")  # Deleted empty directory
            assert not os.path.exists(base_dir + "/DIR2")  # Dirs don't get moved, only their file content
            assert os.path.exists(base_dir + "/DIR/FILE")  # Moved file
            # Not moved
            assert not os.path.exists(base_dir + "/some.file")
            assert not os.path.exists(base_dir + "/2")
            assert os.path.exists(base_dir + "/dir/some.file")
            assert os.path.exists(base_dir + "/dir/2")
            # Function return values
            assert (return_path) == base_dir
            assert (return_status) is True

        # Exception for DVD directories
        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            pyfakefs.fake_filesystem_unittest.set_uid(0)
            # Create a fake filesystem in a random base directory, and included a typical DVD directory
            base_dir = "/" + os.urandom(4).hex() + "/" + os.urandom(2).hex()
            dvd = choice(IGNORED_MOVIE_FOLDERS)
            for test_dir in ["dir/2", "TEST/DIR2"]:
                ffs.fs.create_dir(base_dir + "/" + test_dir, perm_bits=755)
                assert os.path.exists(base_dir + "/" + test_dir) is True
            for test_file in ["dir/some.file", "TEST/" + dvd + "/FILE"]:
                ffs.fs.create_file(base_dir + "/" + test_file, int("0644", 8))
                assert os.path.exists(base_dir + "/" + test_file) is True

            return_path, return_status = sorting.move_to_parent_directory(base_dir + "/TEST")

            # Nothing should move in the presence of a DVD directory structure
            assert os.path.exists(base_dir + "/TEST/" + dvd + "/FILE")
            assert os.path.exists(base_dir + "/TEST/DIR2")
            assert not os.path.exists(base_dir + "/DIR2")
            assert not os.path.exists(base_dir + "/DIR/FILE")
            assert not os.path.exists(base_dir + "/some.file")
            assert not os.path.exists(base_dir + "/2")
            assert os.path.exists(base_dir + "/dir/some.file")
            assert os.path.exists(base_dir + "/dir/2")
            # Function return values
            assert (return_path) == base_dir + "/TEST"
            assert (return_status) is True

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows tests")
    def test_move_to_parent_directory_win(self):
        # Standard files/dirs
        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            pyfakefs.fake_filesystem_unittest.set_uid(0)
            # Create a fake filesystem with some file content in a random base directory
            base_dir = "Z:\\" + os.urandom(4).hex() + "\\" + os.urandom(2).hex()
            for test_dir in ["dir\\2", "TEST\\DIR2"]:
                ffs.fs.create_dir(base_dir + "\\" + test_dir, perm_bits=755)
                assert os.path.exists(base_dir + "\\" + test_dir) is True
            for test_file in ["dir\\some.file", "TEST\\DIR\\FILE"]:
                ffs.fs.create_file(base_dir + "\\" + test_file, int("0644", 8))
                assert os.path.exists(base_dir + "\\" + test_file) is True

            return_path, return_status = sorting.move_to_parent_directory(base_dir + "\\TEST")

            # Affected by move
            assert not os.path.exists(base_dir + "\\TEST\\DIR\\FILE")  # Moved to subdir
            assert not os.path.exists(base_dir + "\\TEST\\DIR2")  # Deleted empty directory
            assert not os.path.exists(base_dir + "\\DIR2")  # Dirs don't get moved, only their file content
            assert os.path.exists(base_dir + "\\DIR\\FILE")  # Moved file
            # Not moved
            assert not os.path.exists(base_dir + "\\some.file")
            assert not os.path.exists(base_dir + "\\2")
            assert os.path.exists(base_dir + "\\dir\\some.file")
            assert os.path.exists(base_dir + "\\dir\\2")
            # Function return values
            assert (return_path) == base_dir
            assert (return_status) is True

        # Exception for DVD directories
        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            pyfakefs.fake_filesystem_unittest.set_uid(0)
            # Create a fake filesystem in a random base directory, and included a typical DVD directory
            base_dir = "D:\\" + os.urandom(4).hex() + "\\" + os.urandom(2).hex()
            dvd = choice(IGNORED_MOVIE_FOLDERS)
            for test_dir in ["dir\\2", "TEST\\DIR2"]:
                ffs.fs.create_dir(base_dir + "\\" + test_dir, perm_bits=755)
                assert os.path.exists(base_dir + "\\" + test_dir) is True
            for test_file in ["dir\\some.file", "TEST\\" + dvd + "\\FILE"]:
                ffs.fs.create_file(base_dir + "\\" + test_file, int("0644", 8))
                assert os.path.exists(base_dir + "\\" + test_file) is True

            return_path, return_status = sorting.move_to_parent_directory(base_dir + "\\TEST")

            # Nothing should move in the presence of a DVD directory structure
            assert os.path.exists(base_dir + "\\TEST\\" + dvd + "\\FILE")
            assert os.path.exists(base_dir + "\\TEST\\DIR2")
            assert not os.path.exists(base_dir + "\\DIR2")
            assert not os.path.exists(base_dir + "\\DIR\\FILE")
            assert not os.path.exists(base_dir + "\\some.file")
            assert not os.path.exists(base_dir + "\\2")
            assert os.path.exists(base_dir + "\\dir\\some.file")
            assert os.path.exists(base_dir + "\\dir\\2")
            # Function return values
            assert (return_path) == base_dir + "\\TEST"
            assert (return_status) is True


@pytest.mark.usefixtures("clean_cache_dir")
class TestSortingSorter:
    @pytest.mark.parametrize(
        "s_class, jobname, sort_string, result_path, result_setname",
        [
            (
                "date",
                "My.EveryDay.Show.20210203.Great.Success.1080p.aac.hdtv-mygrp.mkv",
                "%y-%0m/%t - %y-%0m-%0d - %desc.%ext",
                "2021-02",
                "My EveryDay Show - 2021-02-03 - Great Success",
            ),
            (
                "date",
                "My.EveryDay.Show.20210606.Greater.Successes.2160p.dts.bluray-mygrp.mkv",
                "%y-%m/%t - %y-%m-%d - %desc.%ext",
                "2021-6",
                "My EveryDay Show - 2021-6-6 - Greater Successes",
            ),
            (
                "date",
                "ME!.1999.12.31.720p.hd-tv",
                "{%t}/%0decade_%r/%t - %y-%0m-%0d.%ext",
                "me!/1990_720p",
                "ME! - 1999-12-31",
            ),
            (
                "date",
                "2000 A.D. 28-01-2000 360i dvd-r.avi",
                "%y/%0m/%0d/%r.%dn.%ext",
                "2000/01/28",
                "360i.2000 A.D. 28-01-2000 360i dvd-r.avi",
            ),
            ("date", "Allo_Allo_07-SEP-1984", "%y/%0m/%0d/%.t.%ext", "1984/09/07", "Allo.Allo"),
            (
                "date",
                "www.example.org Allo_Allo_07-SEP-1984",
                "%GI<website>/%GI<nonexistent>/%y/%0m/%0d/%.t%GI<audio_codec>.%ext",
                "www.example.org/1984/09/07",
                "Allo.Allo",
            ),
            (
                "tv",
                "onslow.goes.to.university.s06e66-grp.mkv",
                "%sn/Season %s/%sn - %sx%0e - %en.%ext",
                "Onslow Goes To University/Season 6",
                "Onslow Goes To University - 6x66 - grp",
            ),
            (
                "tv",
                "rose's_BEAUTY_parlour",
                "%sn/S%0sE%0e - %en/%sn - S%0sE%0e - %en.%ext",
                "Rose's Beauty Parlour/SE -",  # Season used to default to '1' if missing, episode never did
                "Rose's Beauty Parlour - SE -",
            ),
            (
                "tv",
                "Cooking with Hyacinth S01E13 Biscuits 2160p DD5.1 Cookies",
                "{%s.N}/%sx%0e - %en/%s_N - %0sx%0e - %en (%r).%ext",
                "cooking.with.hyacinth/1x13 - Biscuits",
                "Cooking_with_Hyacinth - 01x13 - Biscuits (2160p)",
            ),
            (
                "tv",
                "Daisy _ (1987) _ S01E02 _ 480i.avi",
                "%dn.%ext",
                "",
                "Daisy _ (1987) _ S01E02 _ 480i.avi",
            ),
            (
                "tv",
                "Bruce.and.Violet.S126E202.Oh.Dear.Benz.4320p.mkv",
                "%sn/Season W%s/W%0e_%desc.%ext",
                "Bruce and Violet/Season W126",
                "W202",
            ),  # %desc should be stripped, season and episode numbers >=100 handled correctly, and "and" remain lowercase
            (
                "tv",
                "[www.sabnzbd.org]Candle.Light.Dinners.S02E13.Elite.Soups.dts.hvec-NZBLuv.mkv",
                "%s.N.S%0sE%0e.(%e.n).%G.I<audio_codec>.%GI<website>-%GI<release_group>.%ext",
                "",
                "Candle.Light.Dinners.S02E13.(Elite.Soups).DTS.www.sabnzbd.org-hvec-NZBLuv",
            ),  # GI<property>
            (
                "tv",
                "Candle.Light.Dinners.S02E13.DD+5.1.x265.Hi10-NZBLuv.mkv",
                "%s_N_S%0sE%0e_%G_I<video_codec>_%G.I<color_depth>_%G_I<audio_codec>.%ext",
                "",
                "Candle_Light_Dinners_S02E13_H.265_10-bit_Dolby_Digital_Plus",
            ),  # GI<property> with spacer
            (
                "movie",
                "Pantomimes.Lumineuses.1982.2160p.WEB-DL.DDP5.1.H.264-TheOpt.mkv",
                "%r/%year/%title-%G.I<release_group>.%ext",
                "2160p/1982",
                "Pantomimes Lumineuses-TheOpt",
            ),
            (
                "movie",
                "The Lucky Dog 1921 540i Tape ac3 mono-LnH proof sample.avi",
                "%year/%_t-%G.I<other>.%ext",
                "1921",
                "The_Lucky_Dog-Proof-Sample",
            ),
            (
                "movie",
                "Kid_Auto_Races_at_Venice_[2014]",
                "%0decades/%y_%_t",
                "2010s/2014_Kid_Auto_Races_at_Venice",
                "",
            ),
        ],
    )
    @pytest.mark.parametrize("enable_sorting", [0, 1])
    @pytest.mark.parametrize("category", ["sortme", "nosort", "*"])
    @pytest.mark.parametrize("selected_types", [sample([0, 1, 2, 3], randint(0, 3)) for i in range(4)])
    def test_sorter_get_final_path(
        self, s_class, enable_sorting, jobname, sort_string, category, selected_types, result_path, result_setname
    ):
        """Test the final path of the Sorter class"""
        selected_cats = ["*", "sortme"]  # categories for which the sorter is active

        def _func():
            path = ("/tmp/" if not sys.platform.startswith("win") else "c:\\tmp\\") + os.urandom(4).hex()
            sorter = sorting.Sorter(
                None,
                jobname,
                path,
                category,
                False,
                {
                    "name": "test_sorter",
                    "order": 0,
                    "min_size": 1234,
                    "multipart_label": " CD%1" if s_class == "movie" else "",
                    "sort_string": sort_string,
                    "sort_cats": selected_cats,
                    "sort_type": selected_types,
                    "is_active": enable_sorting,
                },
            )

            if (
                bool(enable_sorting)
                and category in selected_cats
                and (len(selected_types) == 0 or any(t in selected_types for t in (sort_to_opts(sorter.type), 0)))
            ):
                if sys.platform.startswith("win"):
                    assert sorter.get_final_path() == (path + "/" + result_path).replace("/", "\\")
                    assert sorter.filename_set == result_setname.replace("/", "\\")
                else:
                    assert sorter.get_final_path() == path + "/" + result_path
                    assert sorter.filename_set == result_setname
            else:
                if sys.platform.startswith("win"):
                    assert sorter.get_final_path() == (path + "/" + jobname).replace("/", "\\")
                else:
                    assert sorter.get_final_path() == path + "/" + jobname
                assert sorter.filename_set == ""

        _func()

    @pytest.mark.parametrize(
        "sort_string, should_rename",
        [
            ("%sn s%0se%0e.%ext", True),  # %0e marker
            ("%sn s%se%e.%ext", True),  # %e marker
            ("{%sn }s%se%e.%ext", True),  # Same with lowercasing; test for issue #2578
            ("%sn.%ext", False),  # No episode marker
            ("%sn_%0se%0e", False),  # No extension marker
            ("%r/%sn s%0se%0e.%ext", True),  # %0e marker, with dir in sort string
            ("%r/%sn s%se%e.%ext", True),  # %e marker, with dir in sort string
            ("%r/{%sn} s%se%e.%ext", True),  # Same with lowercasing; test for issue #2578
            ("%r/%sn.%ext", False),  # No episode marker, with dir in sort string
            ("%r/%sn_%0se%0e", False),  # No extension marker, with dir in sort string
        ],
    )
    @pytest.mark.parametrize("generate_season_pack", [True, False])
    @pytest.mark.parametrize("pack_files_have_season", [True, False])
    @pytest.mark.parametrize("number_of_files", [0, 1, 2, 4])
    @pytest.mark.parametrize("spacer", [".", "_", " "])
    @pytest.mark.parametrize("extension", [".mkv", ""])
    def test_sorter_rename_season_pack(
        self,
        sort_string,
        should_rename,
        generate_season_pack,
        pack_files_have_season,
        number_of_files,
        spacer,
        extension,
    ):
        # Initialise the sorter
        sorter = sorting.Sorter(
            None,
            "Pack" + spacer + "Renamer" + spacer + "S23" + spacer + "2160p-SABnzbd",
            SAB_CACHE_DIR,
            "*",
            False,
            {
                "name": "test_sorter",
                "order": 0,
                "min_size": 512,
                "multipart_label": "",
                "sort_string": sort_string,
                "sort_cats": ["*"],
                "sort_type": [0],
                "is_active": 1,
            },
        )
        """Test the season pack renaming of the Sorter class"""
        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            base_dir = os.path.abspath(os.path.join(os.urandom(4).hex(), os.urandom(2).hex()))
            all_files = []
            # Ensure the format never resembles a season or episode marker
            random_string = "-".join(os.urandom(2).hex())

            # Create a fake filesystem with a random base directory and test files as specified
            ffs.fs.create_dir(base_dir)
            assert os.path.exists(base_dir)
            for i in range(1, number_of_files + 1):
                if generate_season_pack:
                    test_file = (
                        "Yes-pack"
                        + spacer
                        + random_string
                        + spacer
                        + ("S23" if pack_files_have_season else "")
                        + "E"
                        + "{0:0>2}".format(i)
                        + spacer
                        + "2160p-SABnzbdTeam"
                        + extension
                    )
                else:
                    test_file = (
                        "No-pack"
                        + spacer
                        + random_string
                        + "".join(choices(ascii_letters, k=randint(4, 12)))
                        + spacer
                        + "2160p-SABnzbdTeam"
                        + extension
                    )
                all_files.append(test_file)
                ffs.fs.create_file(os.path.join(base_dir, test_file), st_size=1024)
                assert os.path.exists(os.path.join(base_dir, test_file))

            # Filter files as they normally would have been by Sorter.rename() prior to calling the season pack renamer
            all_files = [f for f in all_files if sorter._filter_files(f, base_dir)]

            # Engage the sorter
            sorter.get_values()
            sorter.construct_path()

            # Run some sanity checks, mimicking what's normally done prior to season pack handling
            if sorter.rename_files and sorter.is_season_pack and len(all_files) > 1:
                # Call the season pack renamer directly, bypassing Sorter.rename()
                sorter._rename_season_pack(all_files, base_dir)

                # Check the result
                try:
                    for f in all_files:
                        if generate_season_pack and sorter.is_season_pack and should_rename and number_of_files >= 2:
                            # Verify season pack files have been renamed
                            assert not os.path.exists(os.path.join(base_dir, f))
                            # Also do a basic filename check
                            for root, dirs, files in os.walk(base_dir):
                                for filename in files:
                                    if "{" in sort_string:
                                        # Lowercasing marker in sort string, expect lowercase results
                                        assert re.fullmatch(r"pack renamer s23e0?\d.*" + extension, filename)
                                    else:
                                        assert re.fullmatch(r"Pack Renamer s23e0?\d.*" + extension, filename)
                        else:
                            # No season pack renaming should happen, verify original files are still in place
                            assert os.path.exists(os.path.join(base_dir, f))
                except AssertionError:
                    # Get some insight into what *did* happen and re-raise the error
                    for root, dirs, files in os.walk(base_dir):
                        print(base_dir, dirs, files, all_files)
                    raise AssertionError()

    @pytest.mark.parametrize(
        "s_class, job_tag, sort_string, sort_filename_result",  # Supply sort_filename_result without extension
        [
            ("tv", "S01E02", "%r/%sn s%0se%0e.%ext", "Simulated Job s01e02"),
            ("tv", "S01E02", "%r/%sn s%0se%0e", ""),
            ("movie", "2021", "%y_%.title.%r.%ext", "2021_Simulated.Job.2160p"),
            ("movie", "2021", "%y_%.title.%r", ""),
            ("date", "2020-02-29", "%y/%0m/%0d/%.t-%GI<release_group>.%ext", "Simulated.Job-SAB"),
            ("date", "2020-02-29", "%y/%0m/%0d/%.t-%GI<release_group>", ""),
        ],
    )
    @pytest.mark.parametrize("size_limit, file_size", [(512, 1024), (1024, 512)])
    @pytest.mark.parametrize("extension", [".mkv", ".data", ".mkv", ".vob"])
    @pytest.mark.parametrize("number_of_files", [0, 1, 2, 4])
    @pytest.mark.parametrize("generate_sequential_filenames", [True, False])
    def test_sorter_rename(
        self,
        s_class,
        job_tag,
        sort_string,
        sort_filename_result,
        size_limit,
        file_size,
        extension,
        number_of_files,
        generate_sequential_filenames,
    ):
        """Test the file renaming of the Sorter class"""
        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            # Make up a job name
            job_name = "Simulated.Job." + job_tag + ".2160p.Web.x264-SAB"

            # Prep the filesystem
            storage_dir = os.path.join(SAB_CACHE_DIR, "complete" + "".join(choices(ascii_letters, k=randint(4, 12))))
            try:
                shutil.rmtree(storage_dir)
            except FileNotFoundError:
                pass
            job_dir = os.path.join(storage_dir, job_name)
            ffs.fs.create_dir(job_dir)
            assert os.path.exists(job_dir)

            # Create "downloaded" file(s)
            all_files = []
            fixed_random = "".join(choices(ascii_letters, k=8))
            for number in range(1, 1 + number_of_files):
                if not generate_sequential_filenames:
                    job_file = "".join(choices(ascii_letters, k=randint(4, 12))) + extension
                else:
                    job_file = fixed_random + ".CD" + str(number) + extension
                job_filepath = os.path.join(job_dir, job_file)
                ffs.fs.create_file(job_filepath, int("0644", 8), st_size=file_size)
                # Introduce a minor difference in file size, so we know which one will be renamed if
                # the largest file is targeted (e.g. single file, or no season pack and no sequential
                # naming in case of multiple files)
                file_size += 1
                assert os.path.exists(job_filepath)
                all_files.append(job_file)

            # Initialise the sorter and rename
            sorter = sorting.Sorter(
                None,
                job_name,
                job_dir,
                "*",
                False,
                {
                    "name": "test_sorter",
                    "order": 0,
                    "min_size": size_limit,
                    "multipart_label": " CD%1" if s_class == "movie" else "",
                    "sort_string": sort_string,
                    "sort_cats": ["*"],
                    "sort_type": [0],
                    "is_active": 1,
                },
            )
            sorter.get_values()
            sorter.construct_path()
            sort_dest, is_ok = sorter.rename(all_files, job_dir)

            # Check the result
            try:
                if (
                    is_ok
                    and number_of_files > 0
                    and sort_filename_result
                    and file_size > size_limit
                    and extension not in sorting.EXCLUDED_FILE_EXTS
                ):
                    if number_of_files > 1 and generate_sequential_filenames and sorter.multipart_label:
                        # Sequential file handling
                        for n in range(1, number_of_files + 1):
                            expected = os.path.join(sort_dest, sort_filename_result + " CD" + str(n) + extension)
                            assert os.path.exists(expected)
                    else:
                        # Renaming only for the largest file (which in this test is always the last one created)
                        for job_file in all_files:
                            if (not sort_filename_result) or all_files.index(job_file) != len(all_files) - 1:
                                # Smaller files
                                expected = os.path.join(sort_dest, job_file)
                            else:
                                expected = os.path.join(sort_dest, sort_filename_result + extension)
                            assert os.path.exists(expected)
                else:
                    # No renaming at all
                    for job_file in all_files:
                        expected = os.path.join(sort_dest, job_file)
                        assert os.path.exists(expected)

            except AssertionError:
                # Get some insight into what *did* happen and re-raise the error
                for root, dirs, files in os.walk(sort_dest):
                    print(sort_dest, dirs, files)
                raise AssertionError()

            # Cleanup
            try:
                shutil.rmtree(storage_dir)
            except FileNotFoundError:
                pass

    @pytest.mark.parametrize(
        "job_name, result_sort_file, result_class",
        [
            ("OGEL.NinjaGo.Masters.of.Jinspitzu.S13.1080p.CN.WEB-DL.AAC2.0.H.264", True, "tv"),
            (
                "The.Hunt.for.Blue.November.1990.NORDiC.REMUX.2160p.DV.HDR.UHD-BluRay.HEVC.TrueHD.5.1-SLoWGoaTS",
                True,
                "movie",
            ),
            ("가요무대.1985-11-18.480p.Sat.KorSub", True, "date"),
            ("Virus.cmd", True, "unknown"),
            ("SABnzbd 0.3.9 LeadyNas Mono (incl. Python2.3).pkg", True, "unknown"),
        ],
    )
    def test_sorter_type(self, job_name, result_sort_file, result_class):
        """Check if the sorter gets the type right"""
        sorter = sorting.Sorter(
            None,
            job_name,
            SAB_CACHE_DIR,
            "test_cat",
            False,
            {
                "name": "test_sorter",
                "order": 0,
                "min_size": 1234,
                "multipart_label": "",
                "sort_string": "test",
                "sort_cats": ["test_cat"],
                "sort_type": [0],
                "is_active": 1,
            },
        )
        assert sorter.type is result_class
        assert sorter.sorter_active is result_sort_file

    @pytest.mark.parametrize(
        "name, result",
        [
            ("Undrinkable.2010.PROPER", True),
            ("Undrinkable.2010.EXTENDED.DVDRip.XviD-MoveIt", False),
            ("The.Choir.S01E02.The.Details.AC3.DVDRip.XviD-AD1100", False),
            ("The.Choir.S01E02.The.Real.Details.AC3.DVDRip.XviD-AD1100", False),
            ("The.Choir.S01E02.The.Details.REAL.AC3.DVDRip.XviD-AD1100", True),
            ("real.steal.2011.dvdrip.xvid.ac3-4lt1n", False),
            ("The.Stalking.Mad.S88E01.repack.ReaL.PROPER.CONVERT.1080p.WEB.h265-BTS", True),
            ("The.Stalking.Mad.S88E01.CONVERT.1080p.WEB.h265-BTS", False),
        ],
    )
    def test_sorter_is_proper(self, name, result):
        """Test the is_proper method of the Sorter class"""
        sorter = sorting.Sorter.__new__(sorting.Sorter)  # Skip __init__
        sorter.guess = sorting.guess_what(name)
        assert sorter.is_proper() is result

    @pytest.mark.parametrize(
        "name, result_date, result_resolution, result_season, result_episode",
        [
            (
                "Undrinkable.2010.EXTENDED.DVDRip.XviD-MoveIt",
                datetime.date(2010, 1, 1),
                None,
                None,
                None,
            ),  # Basic movie naming
            ("The.Choir.S01E02.The.Details.REAL.AC3.DVDRip.XviD-AD1100", None, None, "1", "2"),  # Basic series naming
            ("666.2000.dvdrip.xvid.ac3-4lt1n", datetime.date(2000, 1, 1), None, None, None),  # Numerical title
            ("The.Stalking.Mad.S09E876.CONVERT.1080p.WEB.h265-BTS", None, "1080p", "9", "876"),  # Episode > 99
            (
                "The.Stalking.Mad.1999.S88E01.repack.ReaL.PROPER.CONVERT.1080p.WEB.h265-BTS",
                datetime.date(1999, 1, 1),
                "1080p",
                "88",
                "1",
            ),  # Season episode with a year
            ("The.Walking.Sad.S03E04E05E08.1080p.WEB.h265-BTS", None, "1080p", "3", "4-5-8"),  # Multi-episode
            (
                "The.Walking.Sad.E16.1080p.WEB.h265-BTS",
                None,
                "1080p",
                "1",
                "16",
            ),  # Episode only, season should be adjusted to 1
            (
                "The.Walking.Sad.E05E08.2160p.UHD.WEB.h265-BTS",
                None,
                "2160p",
                "1",
                "5-8",
            ),  # Multi-episode only, season should be adjusted to 1
            ("The.Balking.Fat.S11.4k.WEB.h265-BTS", None, "2160p", "11", None),  # Season only
            ("가요무대.1985-11-18.480p.Sat.KorSub", datetime.date(1985, 11, 18), "480p", None, None),  # Date
        ],
    )
    def test_sorter_get_values(self, name, result_date, result_resolution, result_season, result_episode):
        """Test the methods of the Sorter class underpinning get_values()"""
        sorter = sorting.Sorter(None, name, SAB_CACHE_DIR, "*", False, None)
        sorter.guess = sorting.guess_what(name)
        sorter.get_values()
        # year
        if result_date and result_date.year:
            assert sorter.info["year"] == str(result_date.year)
            assert sorter.info["decade"] == str(result_date.year)[2:3] + "0"
            assert sorter.info["decade_two"] == str(result_date.year)[:3] + "0"
        else:
            assert sorter.info["year"] == ""
            assert sorter.info["decade"] == ""
            assert sorter.info["decade_two"] == ""
        # resolution
        if result_resolution:
            assert sorter.info["resolution"] == result_resolution
        else:
            assert sorter.info["resolution"] == ""
        # season
        if result_season:
            assert sorter.info["season_num"] == result_season
            if "-" in result_season:
                # handle multi-season formatting
                assert sorter.info["season_num_alt"] == "-".join(["0" + ep for ep in result_season.split("-")])
            else:
                assert sorter.info["season_num_alt"] == result_season.rjust(2, "0")
        else:
            assert sorter.info["season_num"] == ""
            assert sorter.info["season_num_alt"] == ""
        # episode
        if result_episode:
            assert sorter.info["episode_num"] == result_episode
            if "-" in result_episode:
                # handle multi-episode formatting
                assert sorter.info["episode_num_alt"] == "-".join(["0" + ep for ep in result_episode.split("-")])
            else:
                assert sorter.info["episode_num_alt"] == result_episode.rjust(2, "0")
        else:
            assert sorter.info["episode_num"] == ""
            assert sorter.info["episode_num_alt"] == ""
        # day
        if result_date and result_date.day and result_date.day != 1:
            assert sorter.info["day"] == str(result_date.day)
            assert sorter.info["day_two"] == str(result_date.day).rjust(2, "0")
        else:
            assert sorter.info["day"] == ""
            assert sorter.info["day_two"] == ""
        # month
        if result_date and result_date.month and result_date.month != 1:
            assert sorter.info["month"] == str(result_date.month)
            assert sorter.info["month_two"] == str(result_date.month).rjust(2, "0")
        else:
            assert sorter.info["month"] == ""
            assert sorter.info["month_two"] == ""

    @pytest.mark.parametrize(
        "data_set, job_name, sort_string, result_is_season_pack_initial, result_is_season_pack_later, result_globs",
        [
            # Season in the filename, matching the jobname
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv"),
                "My.Files.S01.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*01*in_2160p*": 4, "myfiles*": 0},
            ),
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x02.nfo", "myfiles.1x02.srt"),
                "My.Files.S01.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*01*in_2160p*.mkv": 2, "myfiles*": 0, "*in_2160p.nfo": 1, "*in_2160p.srt": 1},
            ),  # small similar files (.nfo, .srt)
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv"),
                "My.Files.S01.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4},
            ),  # No extension marker in the sort string
            # Season in the filename, not matching the jobname; jobname should take precedence
            (
                ("myfiles.9x21.mkv", "myfiles.9x22.mkv", "myfiles.9x23.mkv", "myfiles.9x24.mkv"),
                "My.Files.S05.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*05*in_2160p*": 4, "myfiles*": 0},
            ),
            (
                ("myfiles.9x21.mkv", "myfiles.9x22.mkv", "myfiles.9x23.mkv", "myfiles.9x24.mkv"),
                "My.Files.S06.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4},
            ),  # No extension marker in the sort string
            # No season in the filename; shouldn't matter for the result
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv"),
                "My.Files.S05.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*05*in_2160p*": 4, "myfiles*": 0},
            ),
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv"),
                "My.Files.S06.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4},
            ),  # No extension marker in the sort string
            # Multi-episode in the filename
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E07-09.mkv", "myfiles.E04-E05.mkv"),
                "My.Files.S05.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*05*in_2160p*": 4, "myfiles*": 0, "*07-08-09*": 1, "*04-05*": 1},
            ),
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E07-09.mkv", "myfiles.E04-E05.mkv"),
                "My.Files.S05.4k-SABnzbd",
                "s%se%e_in_%r.%ext",
                True,
                True,
                {"*5*in_2160p*": 4, "myfiles*": 0, "*e7-8-9*": 1, "*e4-5*": 1},
            ),  # Episode marker without leading zero
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E07-09.mkv", "myfiles.E04-E05.mkv"),
                "My.Files.S06.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4},
            ),  # No extension marker in the sort string
            # No season in the jobname, shouldn't trigger season sorting even if the filenames have season info
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv"),
                "My.Files.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                False,
                False,
                {"*in_2160p*": 1, "myfiles*": 3},
            ),  # No season in the job name, only the largest file will be renamed
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv"),
                "My.Files.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                False,
                False,
                {"*in_2160p*": 1, "myfiles*": 3},
            ),  # No season in the job name, only the largest file will be renamed
            # Season in the filename, matching the jobname + unrelated file
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv", "foo.bar"),
                "My.Files.S01.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*01*in_2160p*": 4, "myfiles*": 0, "foo.bar": 1},
            ),
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv", "foo.bar"),
                "My.Files.S01.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4, "foo.bar": 1},
            ),  # No extension marker in the sort string
            # Season in the filename, not matching the jobname; jobname should take precedence + unrelated file
            (
                ("myfiles.9x21.mkv", "myfiles.9x22.mkv", "myfiles.9x23.mkv", "myfiles.9x24.mkv", "foo.bar"),
                "My.Files.S05.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*05*in_2160p*": 4, "myfiles*": 0, "foo.bar": 1},
            ),
            (
                ("myfiles.9x21.mkv", "myfiles.9x22.mkv", "myfiles.9x23.mkv", "myfiles.9x24.mkv", "foo.bar"),
                "My.Files.S06.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4, "foo.bar": 1},
            ),  # No extension marker in the sort string
            # No season in the filename; shouldn't matter for the result + unrelated file
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv", "foo.bar"),
                "My.Files.S05.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*05*in_2160p*": 4, "myfiles*": 0, "foo.bar": 1},
            ),
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv", "foo.bar"),
                "My.Files.S06.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4, "foo.bar": 1},
            ),  # No extension marker in the sort string
            # No season in the jobname, shouldn't trigger season sorting even if the filenames have season info + unrelated file
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv", "foo.bar"),
                "My.Files.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                False,
                False,
                {"*in_2160p*": 2, "myfiles*": 3, "foo.bar": 0, "*.bar": 1},
            ),  # No season in the job name, only the largest file will be renamed (plus 'similar' .bar)
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv", "foo.bar"),
                "My.Files.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                False,
                False,
                {"*in_2160p*": 2, "myfiles*": 3, "foo.bar": 0, "*.bar": 1},
            ),  # No season in the job name, only the largest file will be renamed (plus 'similar' .bar)
            # Season in the filename, matching the jobname + unrelated file with episode info
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv", "foo Episode 666.bar"),
                "My.Files.S01.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*01*in_2160p*": 5, "myfiles*": 0, "foo Episode 666.bar": 0, "*.bar": 1},
            ),  # Episode 666 will be accepted regardless of the unrelated basename
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv", "foo Episode 666.bar"),
                "My.Files.S01.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4},
            ),  # No extension marker in the sort string
            # Season in the filename, not matching the jobname; jobname should take precedence + unrelated file with episode info
            (
                ("myfiles.9x21.mkv", "myfiles.9x22.mkv", "myfiles.9x23.mkv", "myfiles.9x24.mkv", "foo Episode 666.bar"),
                "My.Files.S05.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*05*in_2160p*": 5, "myfiles*": 0, "foo Episode 666.bar": 0, "*.bar": 1},
            ),  # Episode 666 will be accepted regardless of the unrelated basename
            (
                ("myfiles.9x21.mkv", "myfiles.9x22.mkv", "myfiles.9x23.mkv", "myfiles.9x24.mkv", "foo Episode 666.bar"),
                "My.Files.S06.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4},
            ),  # No extension marker in the sort string
            # No season in the filename; shouldn't matter for the result + unrelated file with episode info
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv", "foo Episode 666.bar"),
                "My.Files.S05.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*05*in_2160p*": 5, "myfiles*": 0, "foo Episode 666.bar": 0, "*.bar": 1},
            ),
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv", "foo Episode 666.bar"),
                "My.Files.S06.4k-SABnzbd",
                "s%0se%0e_in_%r",
                True,
                False,
                {"*in_2160p*": 0, "myfiles*": 4, "foo Episode 666.bar": 1},
            ),  # No extension marker in the sort string
            # No season in the jobname, shouldn't trigger season sorting even if the filenames have season info + unrelated file with episode info
            (
                ("myfiles.1x01.mkv", "myfiles.1x02.mkv", "myfiles.1x03.mkv", "myfiles.1x04.mkv", "foo Episode 666.bar"),
                "My.Files.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                False,
                False,
                {"*in_2160p*": 2, "myfiles*": 3, "foo Episode 666.bar": 0, "*.bar": 1},
            ),  # No season in the job name, only the largest file will be renamed
            (
                ("myfiles.E01.mkv", "myfiles.E02.mkv", "myfiles.E03.mkv", "myfiles.E04.mkv", "foo Episode 666.bar"),
                "My.Files.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                False,
                False,
                {"*in_2160p*": 2, "myfiles*": 3, "foo Episode 666.bar": 0, "*.bar": 1},
            ),  # No season in the job name, only the largest file will be renamed
            # No episode number in any of the files, season pack renaming will try all files but not rename any
            (
                ("myfiles a.mkv", "myfiles b.mkv", "myfiles c.mkv", "myfiles d.mkv"),
                "My.Files.S03.4k-SABnzbd",
                "s%0se%0e_in_%r.%ext",
                True,
                True,
                {"*in_2160p*": 1, "myfiles*": 3},
            ),  # Largest file will be renamed
        ],
    )
    def test_sorter_rename_with_season_packs(
        self, data_set, job_name, sort_string, result_is_season_pack_initial, result_is_season_pack_later, result_globs
    ):
        """Run the renamer against assorted season packs in the data dir"""
        # Mock a minimal nzo
        job_dir = os.path.join(SAB_CACHE_DIR, "".join(choices(ascii_letters, k=randint(4, 12))), job_name)
        nzo = mock.Mock()
        nzo.final_name = job_name
        nzo.download_path = job_dir
        nzo.nzo_info = {}

        # Setup a sorter instance
        sorter = sorting.Sorter(
            nzo,
            job_name,
            job_dir,
            "*",
            False,
            {
                "name": "test_sorter",
                "order": 0,
                "min_size": 640 * 1024,
                "multipart_label": "",
                "sort_string": sort_string,
                "sort_cats": ["*"],
                "sort_type": [1, 2, 3, 4],
                "is_active": 1,
            },
        )
        assert sorter.is_season_pack is result_is_season_pack_initial
        sorter.get_values()

        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            # Prep the filesystem
            ffs.fs.create_dir(job_dir)
            assert os.path.exists(job_dir)

            # Create "downloaded" files
            file_size = 42 * 1024**2
            for filename in data_set:
                job_filepath = os.path.join(job_dir, filename)
                # Create only mkv and bar as large files, keep anything else below the sorter's min_size
                if get_ext(filename) in (".mkv", ".bar"):
                    size = file_size
                    file_size -= randint(1, 1024)
                else:
                    size = 666
                ffs.fs.create_file(job_filepath, int("0644", 8), st_size=size)
                assert os.path.exists(job_filepath)

            # Sorter stuff, pt. 2
            sorted_path = sorter.construct_path()
            # Check season pack status again after constructing the path
            assert sorter.is_season_pack is result_is_season_pack_later
            sorted_dest, sorted_ok = sorter.rename(globber(job_dir), job_dir)

            # Verify the results
            for pattern, number in result_globs.items():
                try:
                    assert len(glob := globber(sorted_dest or job_dir, pattern)) == number
                except AssertionError:
                    # Print some details to help diagnose the issue
                    pytest.fail(
                        "Globbing for %s didn't returned the expected %s results in %s: %s"
                        % (pattern, number, sorted_path, glob)
                    )
