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


class TestPostProc:

    # Tests of rar_renamer() (=deobfuscate) against various input directories
    def test_rar_renamer(self):

        # Function to deobfuscate one directorty with rar_renamer()
        def deobfuscate_dir(sourcedir, expected_extensions):
            # sourcedir is the relative path to the directory with obfuscated files

            # enrich to absolute path:
            sourcedir = os.path.join(os.getcwd(), sourcedir)
            # We create a workingdir inside the sourcedir, because the filenames are really changed
            workingdir = os.path.join(sourcedir, "WORKING-DIR")
            # if workingdir is still there from previous run, remove it:
            if os.path.isdir(workingdir):
                try:
                    shutil.rmtree(workingdir)
                except PermissionError:
                    pytest.fail("Could not remove existing workingdir %s for rar_renamer", workingdir)
            # create a fresh copy
            try:
                shutil.copytree(sourcedir, workingdir)
            except:
                pytest.fail("Could not create copy of files for rar_renamer")

            # And now let the magic happen:
            nzo = mock.Mock()
            nzo.final_name = "some-download-name"
            number_renamed_files = rar_renamer(nzo, workingdir)

            # run check on the resulting files
            for extension in expected_extensions:
                if len(globber_full(workingdir, "*" + extension)) != expected_extensions[extension]:
                    pytest.fail("Fail on checking extensions {}".format(extension))

            # Remove workingdir again
            try:
                shutil.rmtree(workingdir)
            except:
                pass

            return number_renamed_files

        # The tests and asserts per directory:
        expected_extensions = { "part007.rar": 1}
        assert deobfuscate_dir("tests/data/obfuscated_single_rar_set/", expected_extensions) == 7

        expected_extensions = { "part007.rar": 2,  "part009.rar": 1}
        assert deobfuscate_dir("tests/data/obfuscated_two_rar_sets", expected_extensions) == 16

        expected_extensions = { "part001.rar": 0}
        assert deobfuscate_dir("tests/data/obfuscated_but_no_rar", expected_extensions) == 0
