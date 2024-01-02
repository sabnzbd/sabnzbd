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
tests.test_config - Tests of config methods
"""
from sabnzbd.filesystem import long_path
from tests.testhelper import *
import shutil
import zipfile
import os
from typing import List

import sabnzbd.cfg
from sabnzbd.constants import (
    DEF_INI_FILE,
    DEF_HTTPS_CERT_FILE,
    DEF_HTTPS_KEY_FILE,
    CONFIG_BACKUP_HTTPS,
    CONFIG_BACKUP_FILES,
)
from sabnzbd import config
from sabnzbd import filesystem


DEF_CHAIN_FILE = "server.chain"


class TestOptions:
    test_section = "test_section"
    test_keyword = "test_keyword"

    def test_base_option(self):
        test_option = config.Option(self.test_section, self.test_keyword)
        assert test_option.section == self.test_section
        assert test_option.keyword == self.test_keyword
        assert test_option.section in config.CFG_DATABASE
        assert test_option.keyword in config.CFG_DATABASE[test_option.section]
        assert config.CFG_DATABASE[test_option.section][test_option.keyword] == test_option
        # Reset database
        config.CFG_DATABASE = {}

    @pytest.mark.xfail(reason="These tests should be added")
    def test_all(self):
        # Need to add tests for all the relevant options
        raise NotImplemented

    def test_non_public(self):
        test_option = config.Option(self.test_section, self.test_keyword, public=True)
        assert test_option.get_dict() == {self.test_keyword: None}
        assert test_option.get_dict(for_public_api=False) == {self.test_keyword: None}

        test_option = config.Option(self.test_section, self.test_keyword, public=False)
        assert test_option.get_dict() == {self.test_keyword: None}
        assert test_option.get_dict(for_public_api=True) == {}

        # Password is special when using for_public_api
        test_option = config.OptionPassword(self.test_section, self.test_keyword, default_val="test_password")
        assert test_option.get_dict() == {self.test_keyword: "test_password"}
        assert test_option.get_dict(for_public_api=True) == {self.test_keyword: "**********"}

        # Reset database
        config.CFG_DATABASE = {}


@pytest.mark.usefixtures("clean_cache_dir")
class TestConfig:
    @staticmethod
    def create_dummy_zip(filename: str) -> bytes:
        with io.BytesIO() as zip_buffer:
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_ref:
                zip_ref.writestr(filename, "foobar")
            return zip_buffer.getvalue()

    @staticmethod
    def create_and_verify_backup(admin_dir: str, must_haves: List[str]):
        # Create the backup
        config_backup_path = config.create_config_backup()
        assert os.path.exists(config_backup_path)
        assert sabnzbd.__version__ in config_backup_path
        assert time.strftime("%Y.%m.%d_%H") in config_backup_path

        # Verify the zipfile has the expected content
        with open(config_backup_path, "rb") as fp:
            # Do basic backup validation
            assert config.validate_config_backup(fp.read())
            # Reset the file pointer
            fp.seek(0)
            with zipfile.ZipFile(fp, "r") as zip:
                for basename in must_haves:
                    assert zip.getinfo(basename)
                # Make sure there's nothing else in the zip
                assert (zip_len := len(zip.filelist)) == len(must_haves)

        # Move the current admin dir out of the way
        stowed_admin = os.path.join(SAB_CACHE_DIR, "stowed_admin")
        if os.path.isdir(stowed_admin):
            filesystem.remove_all(stowed_admin)
            assert not os.path.exists(stowed_admin)
        os.rename(admin_dir, stowed_admin)
        assert os.path.exists(stowed_admin)
        assert filesystem.globber(stowed_admin) != []
        assert not os.path.exists(admin_dir)
        filesystem.create_all_dirs(admin_dir)
        assert os.path.exists(admin_dir)
        assert filesystem.globber(admin_dir) == []

        # Store current test settings, as these may change when restoring a backup
        restore_me = {setting: getattr(sabnzbd.cfg, setting)() for setting in CONFIG_BACKUP_HTTPS.values()}

        # Restore the backup
        with open(config_backup_path, "rb") as config_backup_fp:
            config.restore_config_backup(config_backup_fp.read())

        # Check settings results
        restore_changed_settings = False
        for filename, setting in CONFIG_BACKUP_HTTPS.items():
            if filename in must_haves:
                restore_changed_settings = True
                value = getattr(sabnzbd.cfg, setting)()
                if setting != "https_chain":
                    # All https settings should point to the default basenames of the restored files...
                    assert value == getattr(sabnzbd.cfg, setting).default
                else:
                    # ...except the one that doesn't have a default and uses a hardcoded filename instead
                    assert value == DEF_CHAIN_FILE
        # Check filename results
        for basename in must_haves:
            # Verify all files in the backup were restored into the admin dir...
            assert os.path.exists(os.path.join(admin_dir, basename))
            # ...and nothing else
            if not restore_changed_settings:
                assert zip_len == len(filesystem.globber(admin_dir))
            else:
                # Account for sabnzbd.ini.bak in case settings were changed as part of the restore
                assert zip_len + 1 == len(filesystem.globber(admin_dir))

        # Restore the test settings
        for setting, value in restore_me.items():
            getattr(sabnzbd.cfg, setting).set(value)
        sabnzbd.config.save_config(True)

        # Purge the backup file to prevent collisions
        os.unlink(config_backup_path)
        assert not os.path.exists(config_backup_path)

        # Call the original admin dir back into active duty
        filesystem.remove_all(admin_dir)
        assert not os.path.exists(admin_dir)
        os.rename(stowed_admin, admin_dir)
        assert os.path.exists(admin_dir)
        assert filesystem.globber(admin_dir) != []
        assert not os.path.exists(stowed_admin)

    def test_validate_config_backup(self):
        """Validate basic dummy data"""
        assert not config.validate_config_backup(b"invalid")
        assert not config.validate_config_backup(self.create_dummy_zip("dummyfile"))
        assert config.validate_config_backup(self.create_dummy_zip(DEF_INI_FILE))

    @set_config(
        {
            "admin_dir": os.path.join(SAB_CACHE_DIR, "test_config_backup"),
            "complete_dir": os.path.join(SAB_COMPLETE_DIR, "test_config_backup"),
        }
    )
    def test_config_backup(self):
        """Combined tests for the config.{create,validate,restore}_config_backup functions"""
        # Prepare the basics
        admin_dir = sabnzbd.cfg.admin_dir.get_path()
        sabnzbd.cfg.set_root_folders2()
        ini_path = os.path.join(admin_dir, DEF_INI_FILE)
        shutil.copyfile(os.path.join(SAB_DATA_DIR, "sabnzbd.basic.ini"), ini_path)
        assert os.path.exists(ini_path)
        config.read_config(ini_path)
        filesystem.create_all_dirs(sabnzbd.cfg.complete_dir())
        assert os.path.exists(sabnzbd.cfg.complete_dir())

        # Create a backup and verify it has the expected files (ini only, as there are no admin and https config files)
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE])

        # Add other admin files that qualify for inclusion in backups
        for basename in CONFIG_BACKUP_FILES:
            with open(admin_file := os.path.join(admin_dir, basename), "wb") as fp:
                fp.write(os.urandom(128))
            assert os.path.exists(admin_file)
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE] + CONFIG_BACKUP_FILES)

        # Add some useless files in the admin_dir
        for basename in ["totals3.sab", "Best.Movie.Ever.1951.240p.avi", "Rating.sab"]:
            with open(useless_file := os.path.join(admin_dir, basename), "wb") as fp:
                fp.write(os.urandom(256))
            assert os.path.exists(useless_file)
        # None of these should appear in the backup
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE] + CONFIG_BACKUP_FILES)

        # Remove the extra admin files, but keep the useless ones around
        for basename in CONFIG_BACKUP_FILES:
            os.unlink(admin_file := os.path.join(admin_dir, basename))
            assert not os.path.exists(admin_file)

        # Generate fake HTTPS certificate and key files
        cert_file = os.path.join(admin_dir, DEF_HTTPS_CERT_FILE)
        key_file = os.path.join(admin_dir, DEF_HTTPS_KEY_FILE)
        for filepath in (cert_file, key_file):
            with open(filepath, "wb") as fp:
                fp.write(os.urandom(512))
        assert os.path.exists(cert_file)
        assert os.path.exists(key_file)

        # Copy cert and key to create a second set of https config files outside the admin dir
        other_cert_file = long_path(os.path.join(SAB_CACHE_DIR, "foobar.mycert"))
        other_key_file = long_path(os.path.join(SAB_CACHE_DIR, "foobar.mykey"))
        shutil.copyfile(cert_file, other_key_file)
        shutil.copyfile(key_file, other_cert_file)
        assert os.path.exists(other_cert_file)
        assert os.path.exists(other_key_file)

        # Imitate a mainstream https setup (cert and key present, but no chain file)
        sabnzbd.cfg.enable_https.set(True)
        sabnzbd.cfg.https_cert.set(DEF_HTTPS_CERT_FILE)
        sabnzbd.cfg.https_key.set(DEF_HTTPS_KEY_FILE)
        sabnzbd.config.save_config(True)
        assert not sabnzbd.cfg.https_chain()
        assert sabnzbd.CONFIG_BACKUP_HTTPS_OK == []

        # Results should remain the same, as we didn't fake the results of a startup with https enabled yet
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE])

        # Results should still remain the same, the startup data lists only bogus files
        sabnzbd.CONFIG_BACKUP_HTTPS_OK = ["/tmp/no.cert", "/lib/fuldstændig_falsk.nøgle", "/etc/存在しないファイル"]
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE])

        # Now pretend the program started with this config (note: full paths must be used for _OK)
        sabnzbd.CONFIG_BACKUP_HTTPS_OK = [cert_file, key_file]
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE, DEF_HTTPS_CERT_FILE, DEF_HTTPS_KEY_FILE])

        # Pretend some other files were loaded on startup instead
        sabnzbd.CONFIG_BACKUP_HTTPS_OK = [other_cert_file, other_key_file]
        # Files in the settings no longer match those in _OK; no https config should be in the backup
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE])

        # Set the full path to a key and cert file outside the admin dir
        sabnzbd.cfg.https_cert.set(other_cert_file)
        sabnzbd.cfg.https_key.set(other_key_file)
        sabnzbd.config.save_config(True)
        # Now the files should be included, albeit under the default names
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE, DEF_HTTPS_CERT_FILE, DEF_HTTPS_KEY_FILE])

        # Repeat with the "others" removed, so there's nothing (but the ini) left to include in the first place
        for f in (other_cert_file, other_key_file):
            os.unlink(f)
        assert not os.path.exists(other_cert_file)
        assert not os.path.exists(other_key_file)
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE])

        # Make up a chain file
        chain_file = os.path.join(admin_dir, "ssl-chain.txt")
        shutil.copyfile(cert_file, chain_file)
        assert os.path.exists(chain_file)
        # Update the config and the startup record (mostly)
        sabnzbd.cfg.https_cert.set(cert_file)
        sabnzbd.cfg.https_key.set(key_file)
        sabnzbd.cfg.https_chain.set(chain_file)
        sabnzbd.config.save_config(True)
        sabnzbd.CONFIG_BACKUP_HTTPS_OK = [cert_file, key_file]

        # There may be a chain file now, but as long as it's not listed in _OK it should be excluded from the backup
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE, DEF_HTTPS_CERT_FILE, DEF_HTTPS_KEY_FILE])

        # Now it should be included
        sabnzbd.CONFIG_BACKUP_HTTPS_OK.append(chain_file)
        self.create_and_verify_backup(
            admin_dir, [DEF_INI_FILE, DEF_HTTPS_CERT_FILE, DEF_HTTPS_KEY_FILE, DEF_CHAIN_FILE]
        )

        # Same same but more lonely
        sabnzbd.CONFIG_BACKUP_HTTPS_OK = [chain_file, "/tmp/foobar.exe"]
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE, DEF_CHAIN_FILE])

        # Disabling https shouldn't make any difference as long as the evidence shows it was active on startup
        sabnzbd.cfg.enable_https.set(False)
        sabnzbd.config.save_config(True)
        self.create_and_verify_backup(admin_dir, [DEF_INI_FILE, DEF_CHAIN_FILE])
