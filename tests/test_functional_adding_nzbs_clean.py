#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_functional_adding_nzbs_clean - Tests for settings interaction when adding NZBs (clean SABnzbd instance)
"""

from zipfile import ZipFile
import tests.test_functional_adding_nzbs as test_functional_adding_nzbs
from tests.testhelper import *


@pytest.mark.usefixtures("run_sabnzbd")
class TestAddingNZBsClean:
    # Copy from the base class
    _api_set_config = test_functional_adding_nzbs.TestAddingNZBs._api_set_config
    _create_random_nzb = test_functional_adding_nzbs.TestAddingNZBs._create_random_nzb
    _add_backup_directory = test_functional_adding_nzbs.TestAddingNZBs._add_backup_directory
    _clear_and_reset_backup_directory = test_functional_adding_nzbs.TestAddingNZBs._clear_and_reset_backup_directory

    def test_adding_nzbs_nzoids(self):
        """Test if we return the right output"""
        # Create NZB and zipped version
        basenzbfile = self._create_random_nzb()
        zipnzbfile = basenzbfile + ".zip"
        with ZipFile(zipnzbfile, "w") as zipobj:
            zipobj.write(basenzbfile)
        assert os.path.exists(zipnzbfile)

        # Test for both normal and zipped version
        for nzbfile in (basenzbfile, zipnzbfile):
            # Add backup directory for duplicate detection
            backup_dir = self._add_backup_directory()

            # Add the job a first time
            job = get_api_result(mode="addlocalfile", extra_arguments={"name": nzbfile})
            assert job["status"]
            assert job["nzo_ids"]

            # 1=Discard, should return False and no nzo_ids
            self._api_set_config("no_dupes", 1)

            # Add the job a second time
            job = get_api_result(mode="addlocalfile", extra_arguments={"name": nzbfile})
            assert not job["status"]
            assert not job["nzo_ids"]

            # 3=Fail to history, should return True and nzo_ids
            self._api_set_config("no_dupes", 3)
            job = get_api_result(mode="addlocalfile", extra_arguments={"name": nzbfile})
            assert job["status"]
            assert job["nzo_ids"]
            assert not get_api_result(mode="queue", extra_arguments={"nzo_ids": job["nzo_ids"][0]})["queue"]["slots"]
            assert get_api_result(mode="history", extra_arguments={"nzo_ids": job["nzo_ids"][0]})["history"]["slots"]

            # Reset
            self._api_set_config("no_dupes", 0)

            # Test unwanted extensions Fail to history
            self._api_set_config("unwanted_extensions", ["bin"])
            self._api_set_config("action_on_unwanted_extensions", 2)
            job = get_api_result(mode="addlocalfile", extra_arguments={"name": nzbfile})
            assert job["status"]
            assert job["nzo_ids"]
            assert not get_api_result(mode="queue", extra_arguments={"nzo_ids": job["nzo_ids"][0]})["queue"]["slots"]
            assert get_api_result(mode="history", extra_arguments={"nzo_ids": job["nzo_ids"][0]})["history"]["slots"]

            # Reset and clean up
            get_api_result(
                mode="set_config_default",
                extra_arguments={"keyword": ["unwanted_extensions", "action_on_unwanted_extensions"]},
            )
            self._clear_and_reset_backup_directory(backup_dir)
