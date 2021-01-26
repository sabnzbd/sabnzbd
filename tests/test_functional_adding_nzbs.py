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

import os
import shutil
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
PRIO_OPTS_META_CAT = [
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

# Min/max size for random files used in generated NZBs (bytes)
MIN_FILESIZE = 128
MAX_FILESIZE = 1024

# Tags to randomise category/script/nzb name
CAT_RANDOM = os.urandom(4).hex()
SCRIPT_RANDOM = os.urandom(4).hex()
NZB_RANDOM = os.urandom(4).hex()


class ModuleVars:
    # Full path to script directory resp. nzb files, once in place/generated
    SCRIPT_DIR = None
    NZB_FILE = None
    META_NZB_FILE = None
    # Pre-queue script setup marker
    PRE_QUEUE_SETUP_DONE = False


# Shared variables at module-level
VAR = ModuleVars()


@pytest.mark.usefixtures("run_sabnzbd")
class TestAddingNZBs:
    def _setup_script_dir(self):
        VAR.SCRIPT_DIR = os.path.join(SAB_CACHE_DIR, "scripts" + SCRIPT_RANDOM)
        try:
            os.makedirs(VAR.SCRIPT_DIR, exist_ok=True)
        except Exception:
            pytest.fail("Cannot create script_dir %s" % VAR.SCRIPT_DIR)

        json = get_api_result(
            mode="set_config",
            extra_arguments={
                "section": "misc",
                "keyword": "script_dir",
                "value": VAR.SCRIPT_DIR,
            },
        )
        assert VAR.SCRIPT_DIR in json["config"]["misc"]["script_dir"]

    def _customize_pre_queue_script(self, priority, category):
        """ Add a script that accepts the job and sets priority & category """
        script_name = "SCRIPT%s.py" % SCRIPT_RANDOM
        try:
            script_path = os.path.join(VAR.SCRIPT_DIR, script_name)
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
            pytest.fail("Cannot add script %s to script_dir %s" % (script_name, VAR.SCRIPT_DIR))

        if not VAR.PRE_QUEUE_SETUP_DONE:
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
            VAR.PRE_QUEUE_SETUP_DONE = True

    def _configure_cat(self, priority, tag):
        category_name = "cat" + tag + CAT_RANDOM
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

    def _create_random_nzb(self, metadata=None):
        # Create some simple, unique nzb
        job_dir = os.path.join(SAB_CACHE_DIR, "NZB" + os.urandom(16).hex())
        try:
            os.mkdir(job_dir)
            job_file = "%s.%s" % (
                "".join(choice(ascii_lowercase + digits) for i in range(randint(6, 18))),
                "".join(sample(ascii_lowercase, 3)),
            )
            with open(os.path.join(job_dir, job_file), "wb") as f:
                f.write(os.urandom(randint(MIN_FILESIZE, MAX_FILESIZE)))
        except Exception:
            pytest.fail("Failed to create random nzb")

        return create_nzb(job_dir, metadata=metadata)

    def _create_meta_nzb(self, cat_meta):
        return self._create_random_nzb(metadata={"category": cat_meta})

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

            # If the category was set from pre-queue, it replaces any category set earlier
            if hit_stage == 4:
                STAGES[2] = None
                STAGES[5] = None
            if hit_stage == 2:
                STAGES[5] = None

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
            # default cat -> implicit meta -> implicit on add -> explicit on add -> implicit pre-q -> explicit pre-q
            for stage in (0, 5, 2, 1, 4, 3):
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
                    if pre_state_prio == DEFAULT_PRIORITY:
                        handle_default_cat(pre_state_stage, STAGES, return_state)
                    else:
                        STAGES[pre_state_stage] = None
                        # Sanitize again, with 'pre_state_stage' as the new hit_stage. This is needed again
                        # in cases such as hit_stage 3 setting a job state, with a fallback from stage 4.
                        sanitize_stages(pre_state_stage, STAGES)
                return self._expected_results(STAGES, return_state)

        def handle_default_cat(hit_stage, STAGES, return_state):
            """ Figure out the (category) default priority """
            STAGES = sanitize_stages(hit_stage, STAGES)

            # Strip the current -100 hit before recursing
            STAGES[hit_stage] = None

            return self._expected_results(STAGES, return_state)

        # Work backwards through all stages:
        # explicit pre-q -> implicit pre-q -> explicit on add -> implicit on add -> implicit meta
        for stage in (3, 4, 1, 2, 5):
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

        # # ...and finally the Default category (stage 0)
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

    def _prep_test_runner(self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat):
        if not VAR.SCRIPT_DIR:
            self._setup_script_dir()
        if not VAR.NZB_FILE:
            VAR.NZB_FILE = self._create_random_nzb()

        # Set the priority for the Default category
        self._configure_default_category_priority(prio_def_cat)

        # Setup categories
        cat_meta = None
        if prio_meta_cat != None:
            cat_meta = self._configure_cat(prio_meta_cat, "meta")
            if not VAR.META_NZB_FILE:
                VAR.META_NZB_FILE = self._create_meta_nzb(cat_meta)
        cat_add = None
        if prio_add_cat != None:
            cat_add = self._configure_cat(prio_add_cat, "add")

        cat_preq = None
        if prio_preq_cat != None:
            cat_preq = self._configure_cat(prio_preq_cat, "pre")

        # Setup the pre-queue script
        self._customize_pre_queue_script(prio_preq, cat_preq)

        # Queue the job, store the nzo_id
        extra = {"name": VAR.META_NZB_FILE if cat_meta else VAR.NZB_FILE}
        if cat_add:
            extra["cat"] = cat_add
        if prio_add != None:
            extra["priority"] = prio_add
        nzo_id = ",".join(get_api_result(mode="addlocalfile", extra_arguments=extra)["nzo_ids"])

        # Fetch the queue output for the current job
        return get_api_result(mode="queue", extra_arguments={"nzo_ids": nzo_id})["queue"]["slots"][0]

    def _test_runner(self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat):
        # Pause the queue
        assert get_api_result(mode="pause")["status"] is True

        job = self._prep_test_runner(prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat)

        # Determine the expected results
        expected_prio, expected_state = self._expected_results(
            [prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat]
        )

        # Verify the results; queue output uses a string representation for the priority
        assert ALL_PRIOS.get(expected_prio) == job["priority"]
        if expected_state:
            # Also check the correct state or label was set
            if expected_state == DUP_PRIORITY:
                assert "DUPLICATE" in job["labels"]
            if expected_state == PAUSED_PRIORITY:
                assert "Paused" == job["status"]

        # Delete all jobs
        assert (
            get_api_result(mode="queue", extra_arguments={"name": "delete", "value": "all", "del_files": 1})["status"]
            is True
        )
        # Unpause the queue
        assert get_api_result(mode="resume")["status"] is True

    # Caution: a full run is good for 90k+ tests
    # @pytest.mark.parametrize("prio_meta_cat", PRIO_OPTS_META_CAT)
    # @pytest.mark.parametrize("prio_def_cat", VALID_DEFAULT_PRIORITIES)
    # @pytest.mark.parametrize("prio_add", PRIO_OPTS_ADD)
    # @pytest.mark.parametrize("prio_add_cat", PRIO_OPTS_ADD_CAT)
    # @pytest.mark.parametrize("prio_preq", PRIO_OPTS_PREQ)
    # @pytest.mark.parametrize("prio_preq_cat", PRIO_OPTS_PREQ_CAT)

    @pytest.mark.parametrize("prio_meta_cat", sample(PRIO_OPTS_META_CAT, 2))
    @pytest.mark.parametrize("prio_def_cat", sample(VALID_DEFAULT_PRIORITIES, 2))
    @pytest.mark.parametrize("prio_add", sample(PRIO_OPTS_ADD, 3))
    @pytest.mark.parametrize("prio_add_cat", sample(PRIO_OPTS_ADD_CAT, 2))
    @pytest.mark.parametrize("prio_preq", sample(PRIO_OPTS_PREQ, 2))
    @pytest.mark.parametrize("prio_preq_cat", sample(PRIO_OPTS_PREQ_CAT, 2))
    def test_adding_nzbs_priority_sample(
        self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat
    ):
        self._test_runner(prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat)

    @pytest.mark.parametrize(
        "prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat",
        [
            # Specific triggers for fixed bugs
            (-1, -2, None, None, None, None),  # State-setting priorities always fell back to Normal
            (-1, -3, None, None, None, None),
            (1, None, -2, None, None, None),
            (2, None, None, -2, None, None),
            (2, None, None, -3, None, None),
            (2, -2, None, -3, None, None),
            (0, -3, None, None, None, None),
            (0, 2, None, None, 1, None),  # Explicit priority on add was bested by implicit from pre-queue
            (1, None, None, None, -1, None),  # Category-based values from pre-queue didn't work at all
            # Checks for test code regressions
            (-2, -100, 2, None, None, None),
            (-2, 0, 2, -100, None, None),
            (1, 2, 0, -100, None, None),
            (-2, None, -2, None, 2, None),
            (-2, None, -1, None, 1, None),
            (2, None, -1, None, -2, None),
            (-2, -3, 1, None, None, None),
            (2, 2, None, -2, None, None),
            (2, 1, None, -2, None, None),
            (1, -2, 0, None, None, None),
            (0, -3, None, None, 1, None),
            (0, -1, -1, -3, 2, None),
            (0, 2, None, -2, None, -1),
            (1, -2, -100, None, None, -1),
            (1, None, None, None, None, -1),
            (-1, None, None, None, None, 1),
            (0, None, None, None, None, None),
        ],
    )
    def test_adding_nzbs_priority_triggers(
        self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat
    ):
        self._test_runner(prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, prio_meta_cat)

    def test_adding_nzbs_partial(self):
        """Test adding parts of an NZB file, cut off somewhere in the middle to simulate
        the effects of an interrupted download or bad hardware. Should fail, of course."""
        if not VAR.NZB_FILE:
            VAR.NZB_FILE = self._create_random_nzb()

        nzb_basedir, nzb_basename = os.path.split(VAR.NZB_FILE)
        nzb_size = os.stat(VAR.NZB_FILE).st_size
        part_size = round(randint(20, 80) / 100 * nzb_size)
        first_part = os.path.join(nzb_basedir, "part1_of_" + nzb_basename)
        second_part = os.path.join(nzb_basedir, "part2_of_" + nzb_basename)

        with open(VAR.NZB_FILE, "rb") as nzb_in:
            for nzb_part, chunk in (first_part, part_size), (second_part, -1):
                with open(nzb_part, "wb") as nzb_out:
                    nzb_out.write(nzb_in.read(chunk))

        for nzb_part in first_part, second_part:
            json = get_api_result(mode="addlocalfile", extra_arguments={"name": nzb_part})
            assert json["status"] is False
            assert json["nzo_ids"] == []
            os.remove(nzb_part)

    @pytest.mark.parametrize(
        "keep_first, keep_last, strip_first, strip_last, should_work",
        [
            # Keep parts
            (6, 3, 0, 0, False),  # Remove all segments content
            (6, 0, 0, 0, False),
            (5, 2, 0, 0, False),  # Remove all segments
            (5, 0, 0, 0, False),
            (4, 2, 0, 0, False),  # Remove all groups
            (3, 1, 0, 0, False),  # Remove all files
            # Strip parts
            (0, 0, 1, 0, True),  # Strip '?xml' line (survivable)
            (0, 0, 2, 0, True),  # Also strip 'doctype' line (survivable)
            (0, 0, 3, 0, False),  # Also strip 'nzb xmlns' line
            (0, 0, 0, 1, False),  # Forget the 'nzb' closing tag
            (0, 0, 0, 2, False),  # Also forget the (last) 'file' closing tag
            (0, 0, 0, 3, False),  # Also forget the (last) 'segment' closing tag
        ],
    )
    def test_adding_nzbs_malformed(self, keep_first, keep_last, strip_first, strip_last, should_work):
        """ Test adding broken, empty, or otherwise malformed NZB file """
        if not VAR.NZB_FILE:
            VAR.NZB_FILE = self._create_random_nzb()

        with open(VAR.NZB_FILE, "rt") as nzb_in:
            nzb_lines = nzb_in.readlines()
            assert len(nzb_lines) >= 9

        broken_nzb_basename = "broken_" + os.urandom(4).hex() + ".nzb"
        broken_nzb = os.path.join(SAB_CACHE_DIR, broken_nzb_basename)
        with open(broken_nzb, "wt") as nzb_out:
            # Keep only first x, last y lines
            if keep_first:
                nzb_out.write("".join(nzb_lines[:keep_first]))
            elif strip_first:
                nzb_out.write("".join(nzb_lines[strip_first:]))
            if keep_last:
                nzb_out.write("".join(nzb_lines[(-1 * keep_last) :]))
            elif strip_last:
                nzb_out.write("".join(nzb_lines[: (-1 * strip_last)]))

        json = get_api_result(mode="warnings", extra_arguments={"name": "clear"})
        json = get_api_result(mode="addlocalfile", extra_arguments={"name": broken_nzb})
        assert json["status"] is should_work
        assert len(json["nzo_ids"]) == int(should_work)

        json = get_api_result(mode="warnings")
        assert (len(json["warnings"]) == 0) is should_work
        if not should_work:
            for warning in range(0, len(json["warnings"])):
                assert (("Empty NZB file" or "Failed to import") and broken_nzb_basename) in json["warnings"][warning][
                    "text"
                ]

        os.remove(broken_nzb)

    @pytest.mark.parametrize("prio_meta_cat", sample(PRIO_OPTS_META_CAT, 1))
    @pytest.mark.parametrize("prio_def_cat", sample(VALID_DEFAULT_PRIORITIES, 1))
    @pytest.mark.parametrize("prio_add", PRIO_OPTS_ADD)
    def test_adding_nzbs_size_limit(self, prio_meta_cat, prio_def_cat, prio_add):
        """ Verify state and priority of a job exceeding the size_limit """
        # Set size limit
        json = get_api_result(
            mode="set_config", extra_arguments={"section": "misc", "keyword": "size_limit", "value": MIN_FILESIZE - 1}
        )
        assert int(json["config"]["misc"]["size_limit"]) < MIN_FILESIZE
        # Pause the queue
        assert get_api_result(mode="pause")["status"] is True

        job = self._prep_test_runner(prio_def_cat, prio_add, None, None, None, prio_meta_cat)

        # Verify job is paused and low priority, and correctly labeled
        assert job["status"] == "Paused"
        assert job["priority"] == ALL_PRIOS.get(-1)
        assert "TOO LARGE" in job["labels"]

        # Unset size limit
        json = get_api_result(
            mode="set_config", extra_arguments={"section": "misc", "keyword": "size_limit", "value": ""}
        )
        # Delete all jobs
        assert (
            get_api_result(mode="queue", extra_arguments={"name": "delete", "value": "all", "del_files": 1})["status"]
            is True
        )
        # Unpause the queue
        assert get_api_result(mode="resume")["status"] is True

    @pytest.mark.parametrize("prio_def_cat", sample(VALID_DEFAULT_PRIORITIES, 2))
    @pytest.mark.parametrize("prio_add", PRIO_OPTS_ADD)
    @pytest.mark.parametrize("prio_add_cat", sample(PRIO_OPTS_ADD_CAT, 1))
    @pytest.mark.parametrize("prio_preq", sample(PRIO_OPTS_PREQ, 1))
    @pytest.mark.parametrize("prio_preq_cat", sample(PRIO_OPTS_PREQ_CAT, 2))
    def test_adding_nzbs_duplicate_pausing(self, prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat):
        # Set an nzb backup directory
        try:
            backup_dir = os.path.join(SAB_CACHE_DIR, "nzb_backup_dir" + os.urandom(4).hex())
            assert (
                get_api_result(
                    mode="set_config",
                    extra_arguments={"section": "misc", "keyword": "nzb_backup_dir", "value": backup_dir},
                )["config"]["misc"]["nzb_backup_dir"]
                == backup_dir
            )
        except Exception:
            pytest.fail("Cannot create nzb_backup_dir %s" % backup_dir)

        # Pause the queue
        assert get_api_result(mode="pause")["status"] is True

        # Add the job a first time
        job = self._prep_test_runner(None, None, None, None, None, None)
        assert job["status"] == "Queued"

        # Setup duplicate handling to 2 (Pause)
        assert (
            get_api_result(mode="set_config", extra_arguments={"section": "misc", "keyword": "no_dupes", "value": 2})[
                "config"
            ]["misc"]["no_dupes"]
            == 2
        )

        expected_prio, _ = self._expected_results(
            [prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, None]
        )

        job = self._prep_test_runner(prio_def_cat, prio_add, prio_add_cat, prio_preq, prio_preq_cat, None)

        # Verify job is paused and correctly labeled, and given the right (fallback) priority
        assert "DUPLICATE" in job["labels"]
        assert job["priority"] == ALL_PRIOS.get(expected_prio)
        # Priority Force overrules the duplicate pause
        assert job["status"] == "Paused" if expected_prio != FORCE_PRIORITY else "Downloading"

        # Reset duplicate handling (0), nzb_backup_dir ("")
        get_api_result(mode="set_config_default", extra_arguments={"keyword": "no_dupes", "keyword": "nzb_backup_dir"})

        # Remove backup_dir
        for timer in range(0, 5):
            try:
                shutil.rmtree(backup_dir)
                break
            except OSError:
                time.sleep(1)
        else:
            pytest.fail("Failed to erase nzb_backup_dir %s" % backup_dir)

        # Delete all jobs from queue and history
        for mode in ("queue", "history"):
            assert (
                get_api_result(mode=mode, extra_arguments={"name": "delete", "value": "all", "del_files": 1})["status"]
                is True
            )
        # Unpause the queue
        assert get_api_result(mode="resume")["status"] is True
