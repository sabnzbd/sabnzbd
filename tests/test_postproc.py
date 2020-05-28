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
import os, shutil

class TestPostProc:

    # Tests of rar_renamer() (=deobfuscate) against various input directories
    def test_rar_renamer(self):

        # Function to deobfuscate one directorty with rar_renamer()
        def deobfuscate_dir(sourcedir):
            # sourcedir is the relative path to the directory with obfuscated files

            # enrich to absolute path:
            sourcedir = os.path.join(os.getcwd(), sourcedir)
            # We create a workingdir, because the filenames are really changed
            workingdir = sourcedir + "---WORKING-DIR"
            # if workingdir still there from previous run, remove it:
            try:
                shutil.rmtree(workingdir)
            except:
                pass
            # create a fresh copy
            try:
                shutil.copytree(sourcedir, workingdir)
            except:
                assert False

            # And now let the magic happen:
            nzo = mock.Mock()
            nzo.final_name = "some-download-name"
            number_renamed_files = rar_renamer(nzo, workingdir)

            # Remove workingdir again
            try:
                shutil.rmtree(workingdir)
            except:
                pass

            return number_renamed_files


        # The tests and asserts per directory:
        assert deobfuscate_dir("tests/data/obfuscated_single_rar_set") == 7
        assert deobfuscate_dir("tests/data/obfuscated_two_rar_sets") == 16
        assert deobfuscate_dir("tests/data/obfuscated_but_no_rar/") == 0
