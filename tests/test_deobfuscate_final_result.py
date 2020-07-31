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
Testing SABnzbd deobfuscate util
"""

from sabnzbd.utils.deobfuscate import *
import os
import shutil
import random


class TestItAll:
    def test_is_probably_obfuscated(self):

        # obfuscated names
        assert is_probably_obfuscated("599c1c9e2bdfb5114044bf25152b7eaa.mkv")
        assert is_probably_obfuscated("/my/blabla/directory/stuff/599c1c9e2bdfb5114044bf25152b7eaa.mkv")
        assert is_probably_obfuscated("/my/blabla/directory/stuff/afgm.avi")

        # non-obfuscated names:
        assert not is_probably_obfuscated("/my/blabla/directory/stuff/My Favorite Program S03E04.mkv")
        assert not is_probably_obfuscated("/my/blabla/directory/stuff/Great Movie (2020).mkv")

    def test_rename(self):
        # Create directory (with random name)
        dirname = "testdir" + str(random.randint(10000, 99999))
        os.mkdir(dirname)

        # Create a big enough file with a non-useful filename
        output_file = dirname + "/599c1c9e2bdfb5114044bf25152b7eaa.mkv"
        with open(output_file, "wb") as myfile:
            # must be above MIN_SIZE, so ... 15MB
            myfile.truncate(15 * 1024 * 1024)
        # Check it exists now:
        assert os.path.isfile(output_file)

        # and now unleash the magic on that directory:
        jobname = "My Important Download 2020"
        # deobfuscate(os.path.abspath(dirname), jobname)
        deobfuscate(dirname, jobname)
        # Check if file was renamed
        assert not os.path.isfile(output_file)
        assert os.path.isfile(dirname + "/" + jobname + ".mkv")

        # Done. Remove non-empty directory
        shutil.rmtree(dirname)
