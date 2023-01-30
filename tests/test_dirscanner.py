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
import threading
import time

import pyfakefs.fake_filesystem_unittest as ffs
from pyfakefs.fake_filesystem import OSType

from tests.testhelper import *

# Set the global uid for fake filesystems to a non-root user;
# by default this depends on the user running pytest.
global_uid = 1000
ffs.set_uid(global_uid)


class WrappedDirScanner(sabnzbd.dirscanner.DirScanner):
    def __init__(self):
        self.finished_startup_scan = threading.Event()

        super().__init__()

    def scan(self):
        super().scan()

        self.finished_startup_scan.set()

    def __enter__(self):
        pass

    def __exit__(self, *args):
        self.stop()
        self.join()


@pytest.fixture
def dirscanner():
    scanner = WrappedDirScanner()
    with scanner:
        yield scanner


def wait_for(condition, timeout: float = 30):
    timeout = time.time() + timeout
    while time.time() < timeout:
        if condition():
            break
        time.sleep(0.01)


class TestDirScanner:
    @set_config({"dirscan_dir": os.path.join(SAB_CACHE_DIR, "watched")})
    def test_adds_valid_nzbs_on_startup(self, fs, mocker, dirscanner):
        mocker.patch("sabnzbd.nzbparser.add_nzbfile", return_value=(-1, []))
        mocker.patch("sabnzbd.config.save_config", return_value=True)

        filenames = [
            "file.zip",
            "file.rar",
            "file.7z",
            "file.nzb",
            "file.gz",
            "file.bz2",
        ]

        for filename in filenames:
            fs.create_file(os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), filename), contents="FAKEFILE")

        # This could be in __enter__ instead
        dirscanner.start()

        wait_for(lambda: sabnzbd.nzbparser.add_nzbfile.call_count == len(filenames))

        for filename in filenames:
            sabnzbd.nzbparser.add_nzbfile.assert_any_call(
                os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), filename), catdir=None, keep=False
            )

    @set_config({"dirscan_dir": os.path.join(SAB_CACHE_DIR, "watched")})
    def test_detects_nzbs(self, fs, mocker, dirscanner):
        mocker.patch("sabnzbd.nzbparser.add_nzbfile", return_value=(-1, []))
        mocker.patch("sabnzbd.config.save_config", return_value=True)

        dirscanner.start()

        dirscanner.finished_startup_scan.wait()

        fs.create_file(os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), "file.nzb"), contents="FAKEFILE")

        wait_for(lambda: sabnzbd.nzbparser.add_nzbfile.called)

        sabnzbd.nzbparser.add_nzbfile.assert_called_once_with(
            os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), "file.nzb"), catdir=None, keep=False
        )

    @set_config({"dirscan_dir": os.path.join(SAB_CACHE_DIR, "watched")})
    def test_detects_catdir_nzbs(self, fs, mocker, dirscanner):
        mocker.patch("sabnzbd.nzbparser.add_nzbfile", return_value=(-1, []))
        mocker.patch("sabnzbd.config.save_config", return_value=True)

        dirscanner.start()

        dirscanner.finished_startup_scan.wait()

        fs.create_file(os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), "movies", "file.nzb"), contents="FAKEFILE")

        wait_for(lambda: sabnzbd.nzbparser.add_nzbfile.called)

        sabnzbd.nzbparser.add_nzbfile.assert_called_once_with(
            os.path.join(sabnzbd.cfg.dirscan_dir.get_path(), "movies", "file.nzb"), catdir="movies", keep=False
        )
