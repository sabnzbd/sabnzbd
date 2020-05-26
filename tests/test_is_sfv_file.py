# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
tests.test_is_sfv_file- Testing SABnzbd is_sfv_file()
"""

from sabnzbd.newsunpack import is_sfv_file


class Test_is_sfv_file:
    """ Tests of is_sfv_file() against various input files
    """

    def test_valid_unicode_sfv(self):
        assert is_sfv_file("tests/data/good_sfv_unicode.sfv")

    def test_valid_one_line_sfv(self):
        assert is_sfv_file("tests/data/one_line.sfv")

    def test_only_comments(self):
        assert not is_sfv_file("tests/data/only_comments.sfv")

    def test_random_bin(self):
        assert not is_sfv_file("tests/data/random.bin")
