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
import sabnzbd.config as config
import shutil
import zipfile
import os

from sabnzbd.constants import DEF_INI_FILE
from sabnzbd import config


@pytest.mark.usefixtures("clean_cache_dir")
class TestConfig:
    @set_config({"admin_dir": os.path.join(SAB_CACHE_DIR, "test_config")})
    def test_config(self):
        FULL_INI_PATH = os.path.join(sabnzbd.cfg.admin_dir.get_path(), DEF_INI_FILE)
        shutil.copyfile(os.path.join(SAB_DATA_DIR, "sabnzbd.basic.ini"), FULL_INI_PATH)
        config.read_config(FULL_INI_PATH)

        config_backup_data = config.create_config_backup()

        # Check actual backup data
        assert config_backup_data
        assert config.validate_config_backup(config_backup_data)

        # Validate basic dummy data
        assert not config.validate_config_backup("invalid")
        assert not config.validate_config_backup(create_dummy_zip("dummyfile", "Dummydata"))
        assert config.validate_config_backup(create_dummy_zip(DEF_INI_FILE, "Dummydata"))

        # Check restore
        assert not os.remove(FULL_INI_PATH)
        assert config.restore_config_backup(config_backup_data)
        assert os.path.isfile(FULL_INI_PATH)


def create_dummy_zip(filename, content):
    with io.BytesIO() as zip_buffer:
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_ref:
            zip_ref.writestr(filename, content)
        return zip_buffer.getvalue()
