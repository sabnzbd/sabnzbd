# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
tests.test_postproc- Tests of various functions in newspack, among which rar_renamer()
"""

import os
import re
import shutil
from unittest import mock

from sabnzbd import postproc
from sabnzbd.config import ConfigSorter, ConfigCat
from sabnzbd.filesystem import globber_full, clip_path
from sabnzbd.misc import sort_to_opts

from tests.testhelper import *


@pytest.mark.usefixtures("clean_cache_dir")
class TestPostProc:
    # Tests of rar_renamer() (=deobfuscate) against various input directories
    def test_rar_renamer(self):
        # Function to deobfuscate one directory with rar_renamer()
        def deobfuscate_dir(sourcedir, expected_filename_matches):
            # We create a workingdir inside the sourcedir, because the filenames are really changed
            workingdir = os.path.join(sourcedir, "workingdir")

            # if workingdir is still there from previous run, remove it:
            if os.path.isdir(workingdir):
                try:
                    shutil.rmtree(workingdir)
                except PermissionError:
                    pytest.fail("Could not remove existing workingdir %s for rar_renamer" % workingdir)

            # create a fresh copy
            try:
                shutil.copytree(sourcedir, workingdir)
            except:
                pytest.fail("Could not create copy of files for rar_renamer")

            # And now let the magic happen:
            nzo = mock.Mock()
            nzo.final_name = "somedownloadname"
            nzo.download_path = workingdir
            number_renamed_files = postproc.rar_renamer(nzo)

            # run check on the resulting files
            if expected_filename_matches:
                for filename_match in expected_filename_matches:
                    if len(globber_full(workingdir, filename_match)) != expected_filename_matches[filename_match]:
                        pytest.fail("Failed filename_match %s in %s" % (filename_match, workingdir))

            # Remove workingdir again
            try:
                shutil.rmtree(workingdir)
            except:
                pytest.fail("Could not remove existing workingdir %s for rar_renamer" % workingdir)

            return number_renamed_files

        # obfuscated, single rar set
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_single_rar_set")
        # Now define the filematches we want to see, in which amount ("*-*-*-*-*" are the input files):
        expected_filename_matches = {"*part007.rar": 1, "*-*-*-*-*": 0}
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 7

        # obfuscated, two rar sets
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_two_rar_sets")
        expected_filename_matches = {"*part007.rar": 2, "*part009.rar": 1, "*-*-*-*-*": 0}
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 16

        # obfuscated, but not a rar set
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_but_no_rar")
        expected_filename_matches = {"*.rar": 0, "*-*-*-*-*": 6}
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 0

        # One obfuscated rar set, but first rar (.part1.rar) is missing
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_single_rar_set_missing_first_rar")
        # single rar set (of 6 obfuscated rar files), so we expect renaming
        # thus result must 6 rar files, and 0 obfuscated files
        expected_filename_matches = {"*.rar": 6, "*-*-*-*-*": 0}
        # 6 files should have been renamed
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 6

        # Two obfuscated rar sets, but some rars are missing
        sourcedir = os.path.join(SAB_DATA_DIR, "obfuscated_double_rar_set_missing_rar")
        # Two sets, missing rar, so we expect no renaming
        # thus result should be 0 rar files, and still 8 obfuscated files
        expected_filename_matches = {"*.rar": 0, "*-*-*-*-*": 8}
        # 0 files should have been renamed
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 0

        # fully encrypted rar-set, and obfuscated rar names
        sourcedir = os.path.join(SAB_DATA_DIR, "fully_encrypted_and_obfuscated_rars")
        # SABnzbd cannot do anything with this, so we expect no renaming
        expected_filename_matches = {"*.rar": 0, "*-*-*-*-*": 6}
        # 0 files should have been renamed
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 0

    @pytest.mark.parametrize("category", ["testcat", "Default", None])
    @pytest.mark.parametrize("has_jobdir", [True, False])  # With or without a job dir
    @pytest.mark.parametrize("has_catdir", [True, False])  # Complete directory is defined at category level
    @pytest.mark.parametrize("has_active_sorter", [True, False])  # Sorter active for the fake nzo
    @pytest.mark.parametrize("sort_string", ["%sn (%r)", "%sn (%r)/file.%ext", ""])  # Identical path result
    @pytest.mark.parametrize("marker_file", [None, ".marker"])
    @pytest.mark.parametrize("do_folder_rename", [True, False])
    def test_prepare_extraction_path(
        self, category, has_jobdir, has_catdir, has_active_sorter, sort_string, marker_file, do_folder_rename
    ):
        # Ensure global CFG_ vars are initialised
        sabnzbd.config.read_config(os.devnull)

        # Define a sorter and a category (as @set_config cannot handle those)
        ConfigSorter(
            "sorter__test_prepare_extraction_path",
            {
                "order": 0,
                "min_size": 42,
                "multipart_label": "",
                "sort_string": sort_string,
                "sort_cats": [category if category else "no_such_category"],
                "sort_type": [
                    sort_to_opts("all"),
                ],
                "is_active": int(has_active_sorter),
            },
        )
        assert sabnzbd.config.CFG_DATABASE["sorters"]["sorter__test_prepare_extraction_path"]

        if category:
            ConfigCat(
                category,
                {
                    "order": 0,
                    "pp": None,
                    "script": None,
                    "dir": os.path.join(
                        SAB_CACHE_DIR, ("category_dir_for_" + category + ("*" if not has_jobdir else ""))
                    )
                    if has_catdir
                    else None,
                    "newzbin": "",
                    "priority": 0,
                },
            )
            assert sabnzbd.config.CFG_DATABASE["categories"][category]

        # Mock a minimal nzo, required as function input
        fake_nzo = mock.Mock()
        fake_nzo.final_name = "FOSS.Rules.S23E06.2160p-SABnzbd"
        fake_nzo.cat = category
        fake_nzo.nzo_info = {}  # Placeholder to prevent a crash in sorting.get_titles()

        @set_config(
            {
                "download_dir": os.path.join(SAB_CACHE_DIR, "incomplete"),
                "complete_dir": os.path.join(SAB_CACHE_DIR, "complete"),
                "marker_file": marker_file,
                "folder_rename": do_folder_rename,
            }
        )
        def _func():
            (
                tmp_workdir_complete,
                workdir_complete,
                file_sorter,
                not_create_job_dir,
                marker_file_result,
            ) = postproc.prepare_extraction_path(fake_nzo)

            tmp_workdir_complete = clip_path(tmp_workdir_complete)
            workdir_complete = clip_path(workdir_complete)

            # Verify marker file
            if marker_file and not not_create_job_dir:
                assert marker_file_result
            else:
                assert not marker_file_result

            # Verify sorter
            assert file_sorter
            if has_active_sorter and category and sort_string:
                assert file_sorter.sorter_active
            else:
                assert not file_sorter.sorter_active

            # Verify not_create_job_dir
            if category and has_catdir and not has_jobdir and not file_sorter.sorter_active:
                assert not_create_job_dir
            else:
                # Double negatives ftw
                assert not not_create_job_dir

            # Verify workdir_complete
            if not category or not has_catdir:
                # Using standard Complete directory as base
                assert workdir_complete.startswith(os.path.join(SAB_CACHE_DIR, "complete"))
            elif category and has_catdir:
                # Based on the category directory
                assert workdir_complete.startswith(os.path.join(SAB_CACHE_DIR, "category_dir_for_" + category))
            # Check the job directory part (or the lack thereof) as well
            if has_active_sorter and category and sort_string:
                # Sorter path, with an extra job name work directory inside
                assert re.fullmatch(
                    re.escape(SAB_CACHE_DIR)
                    + r".*"
                    + re.escape(os.sep)
                    + r"Foss Rules \(2160p\)"
                    + re.escape(os.sep)
                    + fake_nzo.final_name
                    + r"(\.\d+)?",
                    workdir_complete,
                )
            elif has_jobdir or not (category and has_catdir):
                # Standard job name directory
                assert re.fullmatch(
                    re.escape(SAB_CACHE_DIR) + r".*" + re.escape(os.sep) + r"FOSS.Rules.S23E06.2160p-SABnzbd(\.\d+)?",
                    workdir_complete,
                )
            else:
                # No job directory at all
                assert re.fullmatch(
                    re.escape(SAB_CACHE_DIR) + r".*" + re.escape(os.sep) + r"category_dir_for_([a-zA-Z]+)",
                    workdir_complete,
                )

            # Verify tmp_workdir_complete
            if do_folder_rename:
                if not not_create_job_dir:
                    assert tmp_workdir_complete != workdir_complete
                assert tmp_workdir_complete.replace("_UNPACK_", "") == workdir_complete
            else:
                assert tmp_workdir_complete == workdir_complete

        _func()
