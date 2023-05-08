#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_dirscanner - Testing functions in dirscanner.py
"""

import pyfakefs.fake_filesystem_unittest as ffs

from sabnzbd.nzbparser import AddNzbFileResult
from tests.testhelper import *

# Set the global uid for fake filesystems to a non-root user;
# by default this depends on the user running pytest.
global_uid = 1000
ffs.set_uid(global_uid)


@pytest.fixture
def create_mock_coroutine(mocker, monkeypatch):
    def _create_mock_patch_coro(to_patch=None):
        mock = mocker.Mock()

        async def coroutine(*args, **kwargs):
            return mock(*args, **kwargs)

        if to_patch:
            monkeypatch.setattr(to_patch, coroutine)
        return mock

    return _create_mock_patch_coro


@pytest.fixture
def mock_sleep(create_mock_coroutine):
    return create_mock_coroutine(to_patch="asyncio.sleep")


class TestDirScanner:
    @set_config({"dirscan_dir": os.path.join(SAB_CACHE_DIR, "watched")})
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path, catdir",
        [
            ("file.zip", None),
            ("file.rar", None),
            ("file.7z", None),
            ("file.nzb", None),
            ("file.gz", None),
            ("file.bz2", None),
            ("file.zip", "movies"),
            ("file.rar", "tv"),
            ("file.7z", "audio"),
            ("file.nzb", "software"),
            ("file.gz", "movies"),
            ("file.bz2", "tv"),
        ],
    )
    async def test_adds_valid_nzbs(self, mock_sleep, fs, mocker, path, catdir):
        mocker.patch("sabnzbd.nzbparser.add_nzbfile", return_value=(AddNzbFileResult.ERROR, []))
        mocker.patch("sabnzbd.config.save_config", return_value=True)

        fs.create_file(os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), catdir or "", path), contents="FAKEFILE")

        scanner = sabnzbd.dirscanner.DirScanner()

        await scanner.scan_async(scanner.dirscan_dir)

        sabnzbd.nzbparser.add_nzbfile.assert_any_call(
            os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), catdir or "", path), catdir=catdir, keep=False
        )

    @set_config({"dirscan_dir": os.path.join(SAB_CACHE_DIR, "watched")})
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "file.zip",
            "file.rar",
            "file.7z",
            "file.nzb",
            "file.gz",
            "file.bz2",
        ],
    )
    async def test_ignores_empty_files(self, mock_sleep, fs, mocker, path):
        mocker.patch("sabnzbd.nzbparser.add_nzbfile", return_value=(AddNzbFileResult.ERROR, []))
        mocker.patch("sabnzbd.config.save_config", return_value=True)

        fs.create_file(os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), path))

        scanner = sabnzbd.dirscanner.DirScanner()

        await scanner.scan_async(scanner.dirscan_dir)

        sabnzbd.nzbparser.add_nzbfile.assert_not_called()

    @set_config({"dirscan_dir": os.path.join(SAB_CACHE_DIR, "watched")})
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path",
        [
            "file.doc",
            "filenzb",
        ],
    )
    async def test_ignores_non_nzbs(self, mock_sleep, fs, mocker, path):
        mocker.patch("sabnzbd.nzbparser.add_nzbfile", return_value=(AddNzbFileResult.ERROR, []))
        mocker.patch("sabnzbd.config.save_config", return_value=True)

        fs.create_file(os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), path), contents="FAKEFILE")

        scanner = sabnzbd.dirscanner.DirScanner()

        await scanner.scan_async(scanner.dirscan_dir)

        sabnzbd.nzbparser.add_nzbfile.assert_not_called()
