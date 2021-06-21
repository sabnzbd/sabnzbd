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
tests.test_sorting - Testing functions in sorting.py
"""
import os
import pyfakefs
import shutil
import sys
from random import choice

from sabnzbd import sorting
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
            ),  # Guessit comes up with bad episode info: [24, 17]
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
            ("Test Movie 720p HDTV AAC x265 sample-MYgroup", {"release_group": "MYgroup", "other": "Sample"}),
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
            ("Not Death Proof (2022) 1080p x264 (DD5.1) BE Subs", False),  # Try to trigger some false positives
            ("Proof.of.Everything.(2042).4320p.x266-4U", False),
            ("Crime_Scene_S01E13_Free_Sample_For_Sale_480p-OhDear", False),
            ("Sample That 2011 480p WEB-DL.H265-aMiGo", False),
            ("Look at That 2011 540i WEB-DL.H265-NoSample", False),
            ("NOT A SAMPLE.JPG", False),
        ],
    )
    def test_is_sample(self, name, result):
        assert sorting.is_sample(name) == result

    @pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
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

    def test_has_subdirectory(self):
        with pyfakefs.fake_filesystem_unittest.Patcher() as ffs:
            pyfakefs.fake_filesystem_unittest.set_uid(0)
            # Prep the fake filesystem
            for test_dir in ["/another/test/dir", "/some/TEST/DIR"]:
                ffs.fs.create_dir(test_dir, perm_bits=755)
                # Sanity check
                assert os.path.exists(test_dir) is True

            assert sorting.has_subdirectory("/") is True
            assert sorting.has_subdirectory("/some") is True
            assert sorting.has_subdirectory("/another/test/") is True
            # No subdirs
            assert sorting.has_subdirectory("/another/test/dir") is False
            assert sorting.has_subdirectory("/some/TEST/DIR/") is False
            # Nonexistent dir
            assert sorting.has_subdirectory("/some/TEST/NoSuchDir") is False
            assert sorting.has_subdirectory("/some/TEST/NoSuchDir/") is False
            # Relative path
            assert sorting.has_subdirectory("some/TEST/NoSuchDir") is False
            assert sorting.has_subdirectory("some/TEST/NoSuchDir/") is False
            assert sorting.has_subdirectory("TEST") is False
            assert sorting.has_subdirectory("TEST/") is False
            # Empty input
            assert sorting.has_subdirectory("") is False

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
            dvd = choice(("video_ts", "audio_ts", "bdmv"))
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
            dvd = choice(("video_ts", "audio_ts", "bdmv"))
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
class TestSortingSorters:
    @pytest.mark.parametrize(
        "s_class, jobname, sort_string, result_path, result_setname",
        [
            (
                sorting.DateSorter,
                "My.EveryDay.Show.20210203.Great.Success.1080p.aac.hdtv-mygrp.mkv",
                "%y-%0m/%t - %y-%0m-%0d - %desc.%ext",
                "2021-02",
                "My EveryDay Show - 2021-02-03 - Great Success",
            ),
            (
                sorting.DateSorter,
                "My.EveryDay.Show.20210606.Greater.Successes.2160p.dts.bluray-mygrp.mkv",
                "%y-%m/%t - %y-%m-%d - %desc.%ext",
                "2021-6",
                "My EveryDay Show - 2021-6-6 - Greater Successes",
            ),
            (
                sorting.DateSorter,
                "ME!.1999.12.31.720p.hd-tv",
                "{%t}/%0decade_%r/%t - %y-%0m-%0d.%ext",
                "me!/1990_720p",
                "ME! - 1999-12-31",
            ),
            (
                sorting.DateSorter,
                "2000 A.D. 28-01-2000 360i dvd-r.avi",
                "%y/%0m/%0d/%r.%dn.%ext",
                "2000/01/28",
                "360i.2000 A.D. 28-01-2000 360i dvd-r.avi",
            ),
            (sorting.DateSorter, "Allo_Allo_07-SEP-1984", "%y/%0m/%0d/%.t.%ext", "1984/09/07", "Allo.Allo"),
            (
                sorting.DateSorter,
                "www.example.org Allo_Allo_07-SEP-1984",
                "%GI<website>/%GI<nonexistent>/%y/%0m/%0d/%.t%GI<audio_codec>.%ext",
                "www.example.org/1984/09/07",
                "Allo.Allo",
            ),
            (
                sorting.SeriesSorter,
                "onslow.goes.to.university.s06e66-grp.mkv",
                "%sn/Season %s/%sn - %sx%0e - %en.%ext",
                "Onslow Goes To University/Season 6",
                "Onslow Goes To University - 6x66 - grp",
            ),
            (
                sorting.SeriesSorter,
                "rose's_BEAUTY_parlour",
                "%sn/S%0sE%0e - %en/%sn - S%0sE%0e - %en.%ext",
                "Rose's Beauty Parlour/S01E01 -",
                "Rose's Beauty Parlour - S01E01 -",
            ),
            (
                sorting.SeriesSorter,
                "Cooking with Hyacinth S01E13 Biscuits 2160p DD5.1 Cookies",
                "{%s.N}/%sx%0e - %en/%s_N - %0sx%0e - %en (%r).%ext",
                "cooking.with.hyacinth/1x13 - Biscuits",
                "Cooking_with_Hyacinth - 01x13 - Biscuits (2160p)",
            ),
            (
                sorting.SeriesSorter,
                "Daisy _ (1987) _ S01E02 _ 480i.avi",
                "%dn.%ext",
                "",
                "Daisy _ (1987) _ S01E02 _ 480i.avi",
            ),
            (
                sorting.SeriesSorter,
                "Bruce.and.Violet.S126E202.Oh.Dear.Benz.4320p.mkv",
                "%sn/Season W%s/W%0e_%desc.%ext",
                "Bruce and Violet/Season W126",
                "W202",
            ),  # %desc should be stripped, season and episode numbers >=100 handled correctly, and "and" remain lowercase
            (
                sorting.SeriesSorter,
                "[www.sabnzbd.org]Candle.Light.Dinners.S02E13.Elite.Soups.dts.hvec-NZBLuv.mkv",
                "%s.N.S%0sE%0e.(%e.n).%G.I<audio_codec>.%GI<website>-%GI<release_group>.%ext",
                "",
                "Candle.Light.Dinners.S02E13.(Elite.Soups).DTS.www.sabnzbd.org-hvec-NZBLuv",
            ),  # GI<property>
            (
                sorting.SeriesSorter,
                "Candle.Light.Dinners.S02E13.DD+5.1.x265.Hi10-NZBLuv.mkv",
                "%s_N_S%0sE%0e_%G_I<video_codec>_%G.I<color_depth>_%G_I<audio_codec>.%ext",
                "",
                "Candle_Light_Dinners_S02E13_H.265_10-bit_Dolby_Digital_Plus",
            ),  # GI<property> with spacer
            (
                sorting.MovieSorter,
                "Pantomimes.Lumineuses.1982.2160p.WEB-DL.DDP5.1.H.264-TheOpt.mkv",
                "%r/%year/%title-%G.I<release_group>.%ext",
                "2160p/1982",
                "Pantomimes Lumineuses-TheOpt",
            ),
            (
                sorting.MovieSorter,
                "The Lucky Dog 1921 540i Tape ac3 mono-LnH proof sample.avi",
                "%year/%_t-%G.I<other>.%ext",
                "1921",
                "The_Lucky_Dog-Proof-Sample",
            ),
            (
                sorting.MovieSorter,
                "Kid_Auto_Races_at_Venice_[2014]",
                "%0decades/%y_%_t",
                "2010s/2014_Kid_Auto_Races_at_Venice",
                "",
            ),
        ],
    )
    @pytest.mark.parametrize("enable_sorting", [0, 1])
    @pytest.mark.parametrize("category", ["sortme", "nosort", "*"])
    def test_sorter_get_final_path(
        self, s_class, enable_sorting, jobname, sort_string, category, result_path, result_setname
    ):
        sort_cats = "*, sortme"

        @set_config(
            {
                "date_sort_string": sort_string,
                "date_categories": sort_cats,
                "enable_date_sorting": enable_sorting,
                "tv_sort_string": sort_string,
                "tv_categories": sort_cats,
                "enable_tv_sorting": enable_sorting,
                "movie_sort_string": sort_string,
                "movie_categories": sort_cats,
                "enable_movie_sorting": enable_sorting,
                "movie_sort_extra": " CD%1",
                "movie_extra_folder": 0,
                "movie_rename_limit": "100M",
            }
        )
        def _func():
            path = ("/tmp/" if not sys.platform.startswith("win") else "c:\\tmp\\") + os.urandom(4).hex()
            sorter = s_class(None, jobname, path, category)
            if bool(enable_sorting) and category in sort_cats:
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
        "s_class, job_tag, sort_string, sort_result",  # sort_result without extension
        [
            (sorting.SeriesSorter, "S01E02", "%r/%sn s%0se%0e.%ext", "Simulated Job s01e02"),
            (sorting.MovieSorter, "2021", "%y_%.title.%r.%ext", "2021_Simulated.Job.2160p"),
            (sorting.DateSorter, "2020-02-29", "%y/%0m/%0d/%.t-%GI<release_group>", "Simulated.Job-SAB"),
        ],
    )
    @pytest.mark.parametrize("size_limit, file_size", [(512, 1024), (1024, 512)])
    @pytest.mark.parametrize("extension", [".mkv", ".data", ".mkv", ".vob"])
    @pytest.mark.parametrize("number_of_files", [1, 2])
    @pytest.mark.parametrize("generate_sequential_filenames", [True, False])
    def test_sorter_rename(
        self,
        s_class,
        job_tag,
        sort_string,
        sort_result,
        size_limit,
        file_size,
        extension,
        number_of_files,
        generate_sequential_filenames,
    ):
        """Test the file renaming of the Sorter classes"""

        @set_config(
            {
                "tv_sort_string": sort_string,  # TV
                "tv_categories": "*",
                "enable_tv_sorting": 1,
                "movie_sort_string": sort_string,  # Movie
                "movie_categories": "*",
                "enable_movie_sorting": 1,
                "movie_sort_extra": " CD%1",
                "movie_extra_folder": 0,
                "movie_rename_limit": size_limit,
                "date_sort_string": sort_string,  # Date
                "date_categories": "*",
                "enable_date_sorting": 1,
                "episode_rename_limit": size_limit,  # TV & Date
            }
        )
        def _func():
            # Make up a job name
            job_name = "Simulated.Job." + job_tag + ".2160p.Web.x264-SAB"

            # Prep the filesystem
            storage_dir = os.path.join(SAB_CACHE_DIR, "complete" + os.urandom(4).hex())
            try:
                shutil.rmtree(storage_dir)
            except FileNotFoundError:
                pass
            job_dir = os.path.join(storage_dir, job_name)
            os.makedirs(job_dir, exist_ok=True)
            assert os.path.exists(job_dir) is True

            # Create "downloaded" file(s)
            all_files = []
            fixed_random = os.urandom(8).hex()
            for number in range(1, 1 + number_of_files):
                if not generate_sequential_filenames:
                    job_file = os.urandom(8).hex() + extension
                else:
                    job_file = fixed_random + ".CD" + str(number) + extension
                job_filepath = os.path.join(job_dir, job_file)
                with open(job_filepath, "wb") as f:
                    f.write(os.urandom(file_size))
                assert os.path.exists(job_filepath) is True
                all_files.append(job_file)

            # Initialise the sorter and rename
            sorter = s_class(None, job_name, job_dir, "*", force=True)
            sorter.get_values()
            sorter.construct_path()
            sort_dest, is_ok = sorter.rename(all_files, job_dir, size_limit)

            # Check the result
            try:
                if (
                    is_ok
                    and file_size > size_limit
                    and extension not in sorting.EXCLUDED_FILE_EXTS
                    and not (sorter.type == "movie" and number_of_files > 1 and not generate_sequential_filenames)
                    and not (sorter.type != "movie" and number_of_files > 1)
                ):
                    # File(s) should be renamed
                    if number_of_files > 1 and generate_sequential_filenames and sorter.type == "movie":
                        # Movie sequential file handling
                        for n in range(1, number_of_files + 1):
                            expected = os.path.join(sort_dest, sort_result + " CD" + str(n) + extension)
                            assert os.path.exists(expected)
                    else:
                        expected = os.path.join(sort_dest, sort_result + extension)
                        assert os.path.exists(expected)
                else:
                    # No renaming should happen
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

        _func()

    @pytest.mark.parametrize(
        "job_name, result_sort_file, result_class",
        [
            ("OGEL.NinjaGo.Masters.of.Jinspitzu.S13.1080p.CN.WEB-DL.AAC2.0.H.264", True, sorting.SeriesSorter),
            (
                "The.Hunt.for.Blue.November.1990.NORDiC.REMUX.2160p.DV.HDR.UHD-BluRay.HEVC.TrueHD.5.1-SLoWGoaTS",
                True,
                sorting.MovieSorter,
            ),
            ("가요무대.1985-11-18.480p.Sat.KorSub", True, sorting.DateSorter),
            ("Virus.cmd", False, None),
            ("SABnzbd 0.3.9 DeadyNas Mono (incl. Python2.3).pkg", False, None),
        ],
    )
    def test_sorter_generic(self, job_name, result_sort_file, result_class):
        """Check if the generic sorter makes the right choices"""
        generic = sorting.Sorter(None, None)
        generic.detect(job_name, SAB_CACHE_DIR)

        assert generic.sort_file is result_sort_file
        if result_sort_file:
            assert generic.sorter
            assert generic.sorter.__class__ is result_class
        else:
            assert not generic.sorter

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
        """Test the is_proper method of the BaseSorter class"""
        sorter = sorting.BaseSorter.__new__(sorting.BaseSorter)  # Skip __init__
        sorter.guess = sorting.guess_what(name)
        assert sorter.is_proper() is result
