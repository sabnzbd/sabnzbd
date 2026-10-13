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
tests.test_par2repair - par2 repair sessions
"""

import os
from unittest import mock

from sabnzbd.par2file import FilePar2Info
from sabnzbd.par2repair import RepairSession
from tests.testhelper import make_mock_nzo


class TestFilesUsed:
    @staticmethod
    def make_session(tmp_path, files: list[dict], blocks_from: list[str]) -> RepairSession:
        info = FilePar2Info("", b"", 1)
        nzo = make_mock_nzo(
            download_path=str(tmp_path),
            par2packs={"setA": {"a.bin": info}, "setB": {"b.bin": info}},
        )
        session = RepairSession(nzo, "setA", str(tmp_path / "setA.par2"))
        session.repairer = mock.Mock(files=files, renames={})
        session.blocks_from = dict.fromkeys(blocks_from, 1)
        return session

    def test_another_sets_files_are_not_deleted_as_consumed(self, tmp_path):
        session = self.make_session(
            tmp_path,
            [{"name": "a.bin", "target": str(tmp_path / "a.bin")}],
            [str(tmp_path / "a.bin"), str(tmp_path / "b.bin"), str(tmp_path / "dupe.bin")],
        )
        assert session.files_used([]) == ([], [str(tmp_path / "dupe.bin")])

    def test_an_extra_file_named_like_a_target_elsewhere_is_still_consumed(self, tmp_path):
        os.mkdir(tmp_path / "sub")
        session = self.make_session(
            tmp_path,
            [{"name": "sub/c.bin", "target": str(tmp_path / "sub" / "c.bin")}],
            [str(tmp_path / "c.bin")],
        )
        assert session.files_used([]) == ([], [str(tmp_path / "c.bin")])

    def test_joinables_are_reported_and_not_consumed(self, tmp_path):
        joinable = str(tmp_path / "a.bin.001")
        session = self.make_session(tmp_path, [], [joinable, joinable])
        assert session.files_used([joinable]) == ([joinable], [])


class TestExtraFiles:
    def test_another_sets_files_are_not_scanned_as_extras(self, tmp_path):
        for name in ("a.bin", "b.bin", "dupe.bin", "setA.par2", "setB.par2"):
            (tmp_path / name).write_bytes(b"x")
        info = FilePar2Info("", b"", 1)
        nzo = make_mock_nzo(
            download_path=str(tmp_path),
            extrapars={"setA": [], "setB": []},
            par2packs={"setA": {"a.bin": info}, "setB": {"b.bin": info}},
        )
        session = RepairSession(nzo, "setA", str(tmp_path / "setA.par2"))
        with mock.patch("sabnzbd.par2repair.sabctools.Par2Repairer") as repairer:
            session.open()
        extras = repairer.call_args.kwargs["extrafiles"]
        assert sorted(os.path.basename(path) for path in extras) == ["a.bin", "dupe.bin"]
