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
Testing SABnzbd deobfuscate module
"""

import random
import shutil

from sabnzbd.deobfuscate_filenames import *
from tests.testhelper import *


class TestDeobfuscateFinalResult:
    def test_is_probably_obfuscated(self):
        # Test the base function test_is_probably_obfuscated(), which gives a boolean as RC

        # obfuscated names
        assert is_probably_obfuscated("599c1c9e2bdfb5114044bf25152b7eaa.mkv")
        assert is_probably_obfuscated("/my/blabla/directory/stuff/599c1c9e2bdfb5114044bf25152b7eaa.mkv")
        assert is_probably_obfuscated("/my/blabla/directory/stuff/afgm.avi")

        # non-obfuscated names:
        assert not is_probably_obfuscated("/my/blabla/directory/stuff/My Favorite Program S03E04.mkv")
        assert not is_probably_obfuscated("/my/blabla/directory/stuff/Great Movie (2020).mkv")

    def test_deobfuscate(self):
        # Full test: a directory with a non-useful named file in it: Test that deobfuscate() works and renames it

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_DATA_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a big enough file with a non-useful filename
        output_file = dirname + "/599c1c9e2bdfb5114044bf25152b7eaa.mkv"
        with open(output_file, "wb") as myfile:
            # must be above MIN_SIZE, so ... 15MB
            myfile.truncate(15 * 1024 * 1024)
        # Check it exists now:
        assert os.path.isfile(output_file)

        # and now unleash the magic on that directory, with a more useful jobname:
        jobname = "My Important Download 2020"
        deobfuscate(dirname, jobname)
        # Check if file was renamed
        assert not os.path.exists(output_file)  # original filename should not be there anymore
        assert os.path.exists(os.path.join(dirname, jobname + ".mkv"))  # ... it should be renamed to the jobname

        # Done. Remove non-empty directory
        shutil.rmtree(dirname)

    def test_deobfuscate_par2(self):
        # Simple test to see if the par2 file is picked up
        test_dir = os.path.join(SAB_DATA_DIR, "deobfuscate_filenames")
        test_input = os.path.join(test_dir, "E0CcYdGDFbeCAsT3LoID")
        test_output = os.path.join(test_dir, "random.bin")

        # Check if it is there
        assert os.path.exists(test_input)

        # Run deobfuscate
        deobfuscate(test_dir, "doesnt_matter")

        # Should now be renamed to the filename in the par2 file
        assert not os.path.exists(test_input)
        assert os.path.exists(test_output)

        # Rename back
        os.rename(test_output, test_input)
        assert os.path.exists(test_input)
