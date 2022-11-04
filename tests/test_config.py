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
tests.test_config - Tests of config methods
"""
from tests.testhelper import *
import shutil
import zipfile
import os

import sabnzbd.cfg
from sabnzbd.constants import DEF_INI_FILE
from sabnzbd import config
from sabnzbd import filesystem


@pytest.mark.usefixtures("clean_cache_dir")
class TestConfig:
    @staticmethod
    def create_dummy_zip(filename: str) -> bytes:
        with io.BytesIO() as zip_buffer:
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_ref:
                zip_ref.writestr(filename, "foobar")
            return zip_buffer.getvalue()

    @set_config({"admin_dir": os.path.join(SAB_CACHE_DIR, "test_config"), "complete_dir": SAB_COMPLETE_DIR})
    def test_config(self):
        full_ini_path = os.path.join(sabnzbd.cfg.admin_dir.get_path(), DEF_INI_FILE)
        shutil.copyfile(os.path.join(SAB_DATA_DIR, "sabnzbd.basic.ini"), full_ini_path)
        assert os.path.exists(full_ini_path)
        config.read_config(full_ini_path)

        # Make sure the Complete folder exists
        filesystem.create_all_dirs(sabnzbd.cfg.complete_dir())

        # Check actual backup data
        config_backup_path = config.create_config_backup()
        assert os.path.exists(config_backup_path)
        assert sabnzbd.__version__ in config_backup_path
        assert time.strftime("%Y.%m.%d_%H") in config_backup_path

        with open(config_backup_path, "rb") as config_backup_fp:
            config_backup_data = config_backup_fp.read()

        assert config.validate_config_backup(config_backup_data)

        # Validate basic dummy data
        assert not config.validate_config_backup(b"invalid")
        assert not config.validate_config_backup(self.create_dummy_zip("dummyfile"))
        assert config.validate_config_backup(self.create_dummy_zip(DEF_INI_FILE))

        # Check restore
        os.remove(full_ini_path)
        assert not os.path.exists(full_ini_path)
        config.restore_config_backup(config_backup_data)
        assert os.path.isfile(full_ini_path)
