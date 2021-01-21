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
tests.test_functional_adding_nzbs - Tests for settings interaction when adding NZBs
"""
# TODO:
# input from nzb metadata
# interaction with duplicate handling setting, size limit option

import os
import stat
import sys
from random import choice, randint, sample
from string import ascii_lowercase, digits

import sabnzbd.config
from sabnzbd.constants import (
    DUP_PRIORITY,
    PAUSED_PRIORITY,
    DEFAULT_PRIORITY,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
    REPAIR_PRIORITY,
)
from sabnzbd.database import _PP_LOOKUP

from tests.testhelper import *


# Repair priority is out of scope for the purpose of these tests: it cannot be
# set as a default, upon adding a job, or from a pre-queue script.
# "None" is used to *not* set any particular priority at a given stage.

# Define valid options for various stages
PRIO_OPTS_ADD = [
    DEFAULT_PRIORITY,
    DUP_PRIORITY,
    PAUSED_PRIORITY,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
    None,
]
PRIO_OPTS_PREQ = [
    DEFAULT_PRIORITY,
    DUP_PRIORITY,
    PAUSED_PRIORITY,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
    None,
]
PRIO_OPTS_ADD_CAT = [
    DEFAULT_PRIORITY,
    PAUSED_PRIORITY,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
    None,
]
PRIO_OPTS_PREQ_CAT = [
    DEFAULT_PRIORITY,
    PAUSED_PRIORITY,
    LOW_PRIORITY,
    NORMAL_PRIORITY,
    HIGH_PRIORITY,
    FORCE_PRIORITY,
    None,
]
# Valid priority values for the Default category (as determined by their availability from the interface)
VALID_DEFAULT_PRIORITIES = [PAUSED_PRIORITY, LOW_PRIORITY, NORMAL_PRIORITY, HIGH_PRIORITY, FORCE_PRIORITY]

# Priorities that do *not* set a job state
REGULAR_PRIOS = [LOW_PRIORITY, NORMAL_PRIORITY, HIGH_PRIORITY, FORCE_PRIORITY]
# Priorities that set job states
STATE_PRIOS = [DUP_PRIORITY, PAUSED_PRIORITY]

# Needed for translating priority values to names
ALL_PRIOS = {
    DEFAULT_PRIORITY: "Default",
    DUP_PRIORITY: "Duplicate",
    PAUSED_PRIORITY: "Paused",
    LOW_PRIORITY: "Low",
    NORMAL_PRIORITY: "Normal",
    HIGH_PRIORITY: "High",
    FORCE_PRIORITY: "Force",
    REPAIR_PRIORITY: "Repair",
}


@pytest.mark.usefixtures("run_sabnzbd")
class TestAddingNZBs:
    # Re-usable randomized category/script/nzb name
    CAT_RANDOM = os.urandom(4).hex()
    SCRIPT_RANDOM = os.urandom(4).hex()
    NZB_RANDOM = os.urandom(4).hex()
    # Full path to script dir resp. nzb file, once in place/generated
    SCRIPT_DIR = None
    NZB_FILE = None
    PRE_QUEUE_SETUP_DONE = False

    def _setup_script_dir(self):
        self.SCRIPT_DIR = os.path.join(SAB_CACHE_DIR, "scripts")
        try:
            os.makedirs(self.SCRIPT_DIR, exist_ok=True)
        except Exception:
            pytest.fail("Cannot create script_dir %s" % self.SCRIPT_DIR)

        json = get_api_result(
            mode="set_config",
            extra_arguments={
                "section": "misc",
                "keyword": "script_dir",
                "value": self.SCRIPT_DIR,
            },
        )
        assert self.SCRIPT_DIR in json["config"]["misc"]["script_dir"]

    def _customize_pre_queue_script(self, priority, category):
        """ Add a script that accepts the job and sets priority & category """
        script_name = "SCRIPT%s.py" % self.SCRIPT_RANDOM
        try:
            script_path = os.path.join(self.SCRIPT_DIR, script_name)
            with open(script_path, "w") as f:
                # line 1 = accept; 4 = category; 6 = priority
                f.write(
                    "#!%s\n\nprint('1\\n\\n\\n%s\\n\\n%s\\n')"
                    % (
                        sys.executable,
                        (category if category else ""),
                        (str(priority) if priority != None else ""),
                    )
                )
            if not sys.platform.startswith("win"):
                os.chmod(script_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except Exception:
            pytest.fail("Cannot add script %s to script_dir %s" % (script_name, self.SCRIPT_DIR))

        if not self.PRE_QUEUE_SETUP_DONE:
            # Set as pre-queue script
            json = get_api_result(
                mode="set_config",
                extra_arguments={
                    "section": "misc",
                    "keyword": "pre_script",
                    "value": script_name,
                },
            )
            assert script_name in json["config"]["misc"]["pre_script"]
            self.PRE_QUEUE_SETUP_DONE = True

    def _configure_cat(self, priority, tag):
        category_name = "cat" + tag + self.CAT_RANDOM
        category_config = {
            "section": "categories",
            "name": category_name,
            "pp": choice(list(_PP_LOOKUP.keys())),
            "script": "None",
            "priority": priority if priority != None else DEFAULT_PRIORITY,
        }

        # Add the category
        json = get_api_result(mode="set_config", extra_arguments=category_config)
        assert json["config"]["categories"][0]["name"] == category_name
        if priority != None:
            assert json["config"]["categories"][0]["priority"] == priority

        return category_name

    def _configure_default_category_priority(self, priority):
        if priority not in VALID_DEFAULT_PRIORITIES:
            priority = DEFAULT_PRIORITY
        json = get_api_result(
            mode="set_config",
            extra_arguments={
                "section": "categories",
                "name": "*",
                "priority": priority,
            },
        )
        assert ("*", priority) == (json["config"]["categories"][0]["name"], json["config"]["categories"][0]["priority"])

    def _create_random_nzb(self):
        # Create some simple, unique nzb
        job_dir = os.path.join(SAB_CACHE_DIR, "NZB" + os.urandom(16).hex())
        try:
            os.mkdir(job_dir)
            job_file = "%s.%s" % (
                "".join(choice(ascii_lowercase + digits) for i in range(randint(6, 18))),
                "".join(sample(ascii_lowercase, 3)),
            )
            with open(os.path.join(job_dir, job_file), "wb") as f:
                f.write(os.urandom(randint(128, 1024)))
        except Exception:
            pytest.fail("Failed to create random nzb")

        return create_nzb(job_dir)

    def _expected_results(self, STAGES, return_state=None):
        """ Figure out what priority and state the job should end up with """
        # Define a bunch of helpers
        def sanitize_stages(hit_stage, STAGES):
            # Fallback is always category-based, so nix any explicit priorities (stages 1, 3).
            # This is conditional only because explicit priority-upon-adding takes precedence
            # over implicit-from-pre-queue, as discussed in #1703.
            if not (hit_stage == 4 and STAGES[1] != None):
                STAGES[1] = None
                STAGES[3] = None

            # If the category was set from pre-queue, it replaces any category priority set earlier
            if hit_stage == 4:
                STAGES[2] = None

            return STAGES

        def handle_state_prio(hit_stage, STAGES, return_state):
            """ Find the priority that should to be set after changing the job state """
            # Keep record of the priority that caused the initial hit (for verification of the job state later on)
            if not return_state:
                return_state = STAGES[hit_stage]

            # No point in trying to find a fallback
            if hit_stage == 0:
                return NORMAL_PRIORITY, return_state

            STAGES = sanitize_stages(hit_stage, STAGES)

            # Work forward to find the priority prior to the hit_stage
            pre_state_prio = None
            pre_state_stage = None
            # default cat -> implicit on add -> explicit on add -> implicit pre-q -> explicit pre-q
            for stage in (0, 2, 1, 4, 3):
                if stage == hit_stage:
                    if hit_stage == 1 and STAGES[4] != None:
                        # An explicit state-setting priority still has to deal with the category from pre-queue
                        # for fallback purposes, unlike non-state-setting priorities-on-add that override it.
                        continue
                    else:
                        break
                if STAGES[stage] != None:
                    pre_state_prio = STAGES[stage]
                    pre_state_stage = stage

            if pre_state_prio != None and LOW_PRIORITY <= pre_state_prio <= HIGH_PRIORITY:
                return pre_state_prio, return_state
            else:
                # The next-in-line prio is unsuitable; recurse with relevant stages zero'ed out
                STAGES[hit_stage] = None
                if pre_state_stage:
                    STAGES[pre_state_stage] = None
                    if pre_state_stage == 4:
                        # The category from pre-queue replaces any earlier category setting. While this
                        # is also done by the sanitize_stages(), it's needed again in case hit_stage 3
                        # sets a job state, and the fallback comes from stage 4.
                        STAGES[2] = None
                return self._expected_results(STAGES, return_state)

        def handle_default_cat(hit_stage, STAGES, return_state):
            """ Figure out the (category) default priority """
            STAGES = sanitize_stages(hit_stage, STAGES)

            # Strip the current -100 hit before recursing
            STAGES[hit_stage] = None

            return self._expected_results(STAGES, return_state)

        # Work backwards through all stages:
        # explicit pre-q -> implicit pre-q -> explicit on add -> implicit on add
        for stage in (3, 4, 1, 2):
            if STAGES[stage] != None:
                if stage == 4 and STAGES[1] != None:
                    # Explicit priority on add takes precedence over implicit-from-pre-queue
                    continue
                if STAGES[stage] in REGULAR_PRIOS:
                    return STAGES[stage], return_state
                if STAGES[stage] in STATE_PRIOS:
                    return handle_state_prio(stage, STAGES, return_state)
                if STAGES[stage] == DEFAULT_PRIORITY:
                    return handle_default_cat(stage, STAGES, return_state)

        # ...and finally the Default category (stage 0)
        if STAGES[0] not in (None, DEFAULT_PRIORITY):
            if STAGES[0] in REGULAR_PRIOS:
                # Avoid falling back to priority Force after setting a job state
                if not (return_state in STATE_PRIOS and STAGES[0] == FORCE_PRIORITY):
                    return STAGES[0], return_state
                else:
                    return NORMAL_PRIORITY, return_state
            if STAGES[0] in STATE_PRIOS:
                return handle_state_prio(0, STAGES, return_state)

        # The default of defaults...
        return NORMAL_PRIORITY, return_state

    def _test_runner(self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat):
        if not self.SCRIPT_DIR:
            self._setup_script_dir()
        if not self.NZB_FILE:
            self.NZB_FILE = self._create_random_nzb()

        # Set the priority for the Default category
        self._configure_default_category_priority(prio_def_cat)

        cat_add = None
        if prio_add_cat != None:
            cat_add = self._configure_cat(prio_add_cat, "add")

        cat_preq = None
        if prio_preq_cat != None:
            cat_preq = self._configure_cat(prio_preq_cat, "pre")

        # Setup the pre-queue script
        self._customize_pre_queue_script(prio_preq, cat_preq)

        # Pause the queue
        assert get_api_result(mode="pause")["status"] is True

        # Queue the job, store the nzo_id
        extra = {"name": self.NZB_FILE}
        if cat_add:
            extra["cat"] = cat_add
        if prio_add != None:
            extra["priority"] = prio_add
        nzo_id = ",".join(get_api_result(mode="addlocalfile", extra_arguments=extra)["nzo_ids"])

        # Fetch the queue output for the current job
        json = get_api_result(mode="queue", extra_arguments={"nzo_ids": nzo_id})

        # Determine the expected results
        expected_prio, expected_state = self._expected_results(
            [prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat]
        )

        # Verify the results; queue output uses a string representation for the priority
        assert ALL_PRIOS.get(expected_prio) == json["queue"]["slots"][0]["priority"]
        if expected_state:
            # Also check the correct state or label was set
            if expected_state == DUP_PRIORITY:
                assert "DUPLICATE" in json["queue"]["slots"][0]["labels"]
            if expected_state == PAUSED_PRIORITY:
                assert "Paused" == json["queue"]["slots"][0]["status"]

        # Delete all jobs
        assert (
            get_api_result(mode="queue", extra_arguments={"name": "delete", "value": "all", "del_files": 1})["status"]
            is True
        )
        # Unpause the queue
        assert get_api_result(mode="resume")["status"] is True

    # Caution: a full run is good for 15k+ tests
    # @pytest.mark.parametrize("prio_def_cat", VALID_DEFAULT_PRIORITIES)
    # @pytest.mark.parametrize("prio_add", PRIO_OPTS_ADD)
    # @pytest.mark.parametrize("prio_add_cat", PRIO_OPTS_ADD_CAT)
    # @pytest.mark.parametrize("prio_preq", PRIO_OPTS_PREQ)
    # @pytest.mark.parametrize("prio_preq_cat", PRIO_OPTS_PREQ_CAT)

    @pytest.mark.parametrize("prio_def_cat", sample(VALID_DEFAULT_PRIORITIES, 2))
    @pytest.mark.parametrize("prio_add", sample(PRIO_OPTS_ADD, 3))
    @pytest.mark.parametrize("prio_add_cat", sample(PRIO_OPTS_ADD_CAT, 3))
    @pytest.mark.parametrize("prio_preq", sample(PRIO_OPTS_PREQ, 3))
    @pytest.mark.parametrize("prio_preq_cat", sample(PRIO_OPTS_PREQ_CAT, 3))
    def test_adding_nzbs_random_sample(self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat):
        self._test_runner(prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat)

    @pytest.mark.parametrize(
        "prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat",
        [
            # Specific triggers for fixed bugs
            (-1, -2, None, None, None),  # State-setting priorities always fell back to Normal
            (-1, -3, None, None, None),
            (1, None, -2, None, None),
            (2, None, None, -2, None),
            (2, None, None, -3, None),
            (2, -2, None, -3, None),
            (0, -3, None, None, None),
            (0, 2, None, None, 1),  # Explicit priority on add was bested by implicit from pre-queue
            (1, None, None, None, -1),  # Category-based values from pre-queue didn't work at all
            # Checks for test code regressions
            (-2, -100, 2, None, None),
            (-2, 0, 2, -100, None),
            (1, 2, 0, -100, None),
            (-2, None, -2, None, 2),
            (-2, None, -1, None, 1),
            (2, None, -1, None, -2),
            (-2, -3, 1, None, None),
            (2, 2, None, -2, None),
            (2, 1, None, -2, None),
            (1, -2, 0, None, None),
            (0, -3, None, None, 1),
            (0, -1, -1, -3, 2),
            (0, None, None, None, None),
        ],
    )
    def test_adding_nzbs_bugs_bunny(self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat):
        self._test_runner(prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat)