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
tests.test_nzbfile - Testing functions in nzb/file.py
"""

from datetime import datetime

from sabnzbd.nzb import NzbObject, NzbFile

from tests.testhelper import *


@pytest.mark.usefixtures("clean_cache_dir")
class TestNzbFile:
    @set_config({"download_dir": SAB_CACHE_DIR})
    @pytest.mark.parametrize(
        "filenames",
        [
            [
                "hello.world.par2",
                "hello.world.part01.rar",
                "hello.world.part02.rar",
                "hello.world.part03.rar",
                "hello.world.sample.mkv",
                "hello.world.sfv",
                "hello.world.nfo",
                "hello.world.vol000-001.par2",
                "hello.world.vol001-003.par2",
            ],
            [
                "a.s01e01.par2",
                "a.s01e01.vol000-001.par2",
                "a.s01e01.vol001-003.par2",
                "a.s01e02.par2",
                "a.s01e02.vol000-001.par2",
                "a.s01e02.rar",
                "a.s01e02.vol000-001.par2",
                "a.s01e03.rar",
                "a.s01e03.r00",
                "a.s01e01.rar",
                "a.s01e01.sfv",
                "a.s01e03.r01",
                "a.s01e02.r00",
                "a.s01e03.par2",
                "a.s01e01.sample.mkv",
                "a.s01e02.sample.mkv",
                "a.s01e03.sample.mkv",
            ],
        ],
    )
    def test_sort_is_consistent(self, filenames: list[str]):
        """Test sorting of nzb files is deterministic, this is that the order of input does not matter."""
        nzo = NzbObject("test")

        def make_nzf(filename: str):
            return NzbFile(
                date=datetime.now(),
                subject=filename,
                raw_article_db=[(filename, 0)],
                file_bytes=0,
                nzo=nzo,
            )

        files1 = [make_nzf(filename) for filename in filenames]
        files2 = [make_nzf(filename) for filename in reversed(filenames)]

        files1.sort()
        files2.sort()

        assert [f.filename for f in files1] == [f.filename for f in files2]
