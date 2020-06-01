# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
tests.test_postproc- Tests of various functions in newspack, among which rar_renamer()
"""

from sabnzbd.postproc import *
from unittest import mock
import os, shutil, pytest
from distutils.dir_util import copy_tree


class TestPostProc:

    # Tests of rar_renamer() (=deobfuscate) against various input directories
    def test_rar_renamer(self):

        # Function to deobfuscate one directorty with rar_renamer()
        def deobfuscate_dir(sourcedir, expected_filename_matches):
            # sourcedir is the relative path to the directory with obfuscated files

            # enrich to absolute path:
            sourcedir = os.path.join(os.getcwd(), sourcedir)
            # We create a workingdir inside the sourcedir, because the filenames are really changed
            workingdir = os.path.join(sourcedir, "workingdir")
            # print("workingdir is", workingdir)
            # if workingdir is still there from previous run, remove it:
            if os.path.isdir(workingdir):
                try:
                    shutil.rmtree(workingdir)
                except PermissionError:
                    pytest.fail(
                        "Could not remove existing workingdir %s for rar_renamer"
                        % workingdir
                    )
            # create a fresh copy
            try:
                # shutil.copytree(sourcedir, workingdir) gives problems on AppVeyor, so:
                copy_tree(sourcedir, workingdir)
            except:
                pytest.fail("Could not create copy of files for rar_renamer")

            # And now let the magic happen:
            nzo = mock.Mock()
            nzo.final_name = "somedownloadname"
            number_renamed_files = rar_renamer(nzo, workingdir)

            # run check on the resulting files
            if expected_filename_matches:
                for filename_match in expected_filename_matches:
                    if (
                        len(globber_full(workingdir, filename_match))
                        != expected_filename_matches[filename_match]
                    ):
                        pytest.fail(
                            "Failed filename_match %s in %s"
                            % (filename_match, workingdir)
                        )

            # Remove workingdir again
            try:
                shutil.rmtree(workingdir)
            except:
                pytest.fail(
                    "Could not remove existing workingdir %s for rar_renamer"
                    % workingdir
                )

            return number_renamed_files

        # The tests and asserts per directory:
        # we use os.path.join("test","data","..." ) to make it OS compatible

        # obfuscated, single rar set
        sourcedir = os.path.join("tests", "data", "obfuscated_single_rar_set")
        # Now define the filematches we want to see, in which amount:
        expected_filename_matches = {"*part007.rar": 1, "*-*-*-*-*": 0}
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 7

        # obfuscated, two rar sets
        sourcedir = os.path.join("tests", "data", "obfuscated_two_rar_sets")
        expected_filename_matches = {
            "*part007.rar": 2,
            "*part009.rar": 1,
            "*-*-*-*-*": 0,
        }
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 16

        # obfuscated, but not a rar set
        sourcedir = os.path.join("tests", "data", "obfuscated_but_no_rar")
        expected_filename_matches = {"*.rar": 0, "*-*-*-*-*": 6}
        assert deobfuscate_dir(sourcedir, expected_filename_matches) == 0
