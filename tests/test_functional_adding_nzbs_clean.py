#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team (sabnzbd.org)
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
import time
from zipfile import ZipFile
import tests.test_functional_adding_nzbs as test_functional_adding_nzbs
from sabnzbd.constants import STOP_PRIORITY
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
            # Pause the queue at first
            assert get_api_result(mode="pause")["status"] is True

            # Add the job a first time
            job1 = get_api_result(mode="addlocalfile", extra_arguments={"name": nzbfile})
            assert job1["status"]
            assert job1["nzo_ids"]

            # 1=Discard
            self._api_set_config("no_dupes", 1)

            # Add the job a second time, it should be added with ALTERNATIVE label
            job2 = get_api_result(mode="addlocalfile", extra_arguments={"name": nzbfile})
            assert job2["status"]
            assert job2["nzo_ids"]
            queue = get_api_result(mode="queue", extra_arguments={"nzo_ids": job2["nzo_ids"][0]})
            job_in_queue = queue["queue"]["slots"][0]
            assert "ALTERNATIVE" in job_in_queue["labels"]
            assert job_in_queue["status"] == "Paused"

            # Stop the first job
            get_api_result(
                mode="queue", extra_arguments={"name": "priority", "value": job1["nzo_ids"][0], "value2": STOP_PRIORITY}
            )

            # Wait for the job to be removed
            time.sleep(2)
            assert get_api_result(mode="history", extra_arguments={"nzo_ids": job1["nzo_ids"][0]})["history"]["slots"]

            # Now the second job should no longer be paused and labelled
            queue = get_api_result(mode="queue", extra_arguments={"nzo_ids": job2["nzo_ids"][0]})
            job_in_queue = queue["queue"]["slots"][0]
            assert "ALTERNATIVE" not in job_in_queue["labels"]
            assert job_in_queue["status"] == "Queued"

            # Reset duplicate detection
            self._api_set_config("no_dupes", 0)

            # Test unwanted extensions Fail to history
            self._api_set_config("unwanted_extensions", ["bin"])
            self._api_set_config("action_on_unwanted_extensions", 2)
            job = get_api_result(mode="addlocalfile", extra_arguments={"name": nzbfile})
            assert job["status"]
            assert job["nzo_ids"]
            time.sleep(1)
            assert not get_api_result(mode="queue", extra_arguments={"nzo_ids": job["nzo_ids"][0]})["queue"]["slots"]
            assert get_api_result(mode="history", extra_arguments={"nzo_ids": job["nzo_ids"][0]})["history"]["slots"]

            # Reset and clean up
            get_api_result(
                mode="set_config_default",
                extra_arguments={"keyword": ["unwanted_extensions", "action_on_unwanted_extensions"]},
            )

            # Delete all jobs from queue and history
            for mode in ("queue", "history"):
                get_api_result(mode=mode, extra_arguments={"name": "delete", "value": "all", "del_files": 1})
