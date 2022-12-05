# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
tests.test_postproc- Tests of various functions in newspack, among which rar_renamer()
"""

import shutil
from unittest import mock

from sabnzbd.postproc import *
from tests.testhelper import *


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
            number_renamed_files = rar_renamer(nzo)

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
