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
tests.test_utils.test_checkdir - Testing SABnzbd checkdir
"""

from sabnzbd.utils.checkdir import isFAT


class TestIsFAT:
    """test sabnzbd.utils.checkdir.isFAT"""

    def test_not_fat(self, tmp_path, capsys):
        """The test system is not expected to run on FAT"""
        assert isFAT(str(tmp_path)) is False
        # isFAT prints in its exception handler, so no output means no exception was raised
        assert capsys.readouterr().out == ""

    def test_non_existing_dir(self, capsys):
        """A non-existing dir is not FAT"""
        assert isFAT("such_a_dir_does_not_exist") is False
        assert capsys.readouterr().out == ""
