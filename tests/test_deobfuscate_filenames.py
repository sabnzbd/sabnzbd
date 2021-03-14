#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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


def create_big_file(filename):
    with open(filename, "wb") as myfile:
        # must be above MIN_SIZE, so ... 15MB
        myfile.truncate(15 * 1024 * 1024)

def create_small_file(filename):
    with open(filename, "wb") as myfile:
        myfile.truncate(1024)


class TestDeobfuscateFinalResult:
    def test_is_probably_obfuscated(self):
        # Test the base function test_is_probably_obfuscated(), which gives a boolean as RC

        # obfuscated names
        assert is_probably_obfuscated("599c1c9e2bdfb5114044bf25152b7eaa.mkv")
        assert is_probably_obfuscated("/my/blabla/directory/stuff/599c1c9e2bdfb5114044bf25152b7eaa.mkv")
        assert is_probably_obfuscated(
            "/my/blabla/directory/A Directory Should Not Count 2020/599c1c9e2bdfb5114044bf25152b7eaa.mkv"
        )
        assert is_probably_obfuscated("/my/blabla/directory/stuff/afgm.avi")
        assert is_probably_obfuscated("/my/blabla/directory/stuff/afgm2020.avi")
        assert is_probably_obfuscated("MUGNjK3zi65TtN.mkv")
        assert is_probably_obfuscated("T306077.avi")
        assert is_probably_obfuscated("bar10nmbkkjjdfr.mkv")
        assert is_probably_obfuscated("4rFF-fdtd480p.bin")
        assert is_probably_obfuscated("e0nFmxBNTprpbQiVQ44WeEwSrBkLlJ7IgaSj3uzFu455FVYG3q.bin")
        assert is_probably_obfuscated("e0nFmxBNTprpbQiVQ44WeEwSrBkLlJ7IgaSj3uzFu455FVYG3q")  # no ext
        assert is_probably_obfuscated("greatdistro.iso")
        assert is_probably_obfuscated("my.download.2020")
        assert is_probably_obfuscated("abc.xyz.a4c567edbcbf27.BLA")  # by definition
        assert is_probably_obfuscated("abc.xyz.iso")  # lazy brother
        assert is_probably_obfuscated("0675e29e9abfd2.f7d069dab0b853283cc1b069a25f82.6547")

        # non-obfuscated names:
        assert not is_probably_obfuscated("/my/blabla/directory/stuff/My Favorite Distro S03E04.iso")
        assert not is_probably_obfuscated("/my/blabla/directory/stuff/Great Distro (2020).iso")
        assert not is_probably_obfuscated("ubuntu.2004.iso")
        assert not is_probably_obfuscated("/my/blabla/directory/stuff/GreatDistro2020.iso")
        assert not is_probably_obfuscated("Catullus.avi")
        assert not is_probably_obfuscated("Der.Mechaniker.HDRip.XviD-SG.avi")
        assert not is_probably_obfuscated("Bonjour.1969.FRENCH.BRRiP.XviD.AC3-HuSh.avi")
        assert not is_probably_obfuscated("Bonjour.1969.avi")
        assert not is_probably_obfuscated("This That S01E11")
        assert not is_probably_obfuscated("This_That_S01E11")
        assert not is_probably_obfuscated("this_that_S01E11")
        assert not is_probably_obfuscated("My.Download.2020")
        assert not is_probably_obfuscated("this_that_there_here.avi")
        assert not is_probably_obfuscated("Lorem Ipsum.avi")
        assert not is_probably_obfuscated("Lorem Ipsum")  # no ext

    def test_deobfuscate_filelist_lite(self):
        # ligthweight test of deobfuscating: with just one file

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_DATA_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a big enough file with a non-useful, obfuscated filename
        output_file1 = os.path.join(dirname, "111c1c9e2bdfb5114044bf25152b7eab.bla")
        create_big_file(output_file1)
        assert os.path.isfile(output_file1)

        # create the filelist, with just the above file
        myfilelist = [output_file1]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        deobfuscate_list(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(output_file1)  # original filename should not be there anymore

        # Check the renaming
        assert os.path.isfile(os.path.join(dirname, jobname + ".bla"))  # ... it should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_filelist_full(self):
        # Full test, with a combinantion of files: Test that deobfuscate() works and renames correctly
        # ... but only the files that are in the filelist

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_DATA_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a big enough file with a non-useful filename
        output_file1 = os.path.join(dirname, "111c1c9e2bdfb5114044bf25152b7eaa.bla")
        create_big_file(output_file1)
        assert os.path.isfile(output_file1)

        # and another one
        output_file2 = os.path.join(dirname, "222c1c9e2bdfb5114044bf25152b7eaa.bla")
        create_big_file(output_file2)
        assert os.path.isfile(output_file2)

        # create the filelist, with just the above files
        myfilelist = [output_file1, output_file2]

        # Create some extra files ... that will not be in the list
        output_file3 = os.path.join(dirname, "333c1c9e2bdfb5114044bf25152b7eaa.bla")
        create_big_file(output_file3)
        assert os.path.isfile(output_file3)

        output_file4 = os.path.join(dirname, "This Great Download 2020.bla")
        create_big_file(output_file4)
        assert os.path.isfile(output_file4)

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        deobfuscate_list(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(output_file1)  # original filename should not be there anymore
        assert not os.path.isfile(output_file2)  # original filename should not be there anymore
        assert os.path.isfile(output_file3)  # but this one should still be there
        assert os.path.isfile(output_file4)  # and this one too

        # Check the renaming
        assert os.path.isfile(os.path.join(dirname, jobname + ".bla"))  # ... it should be renamed to the jobname
        assert os.path.isfile(os.path.join(dirname, jobname + ".1.bla"))  # should not be there

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_filelist_subdir(self):
        # test of deobfuscating with sub directories

        # Create directory with subdirs
        dirname = os.path.join(SAB_DATA_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)
        subdirname = os.path.join(dirname, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(subdirname)
        subsubdirname = os.path.join(subdirname, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(subsubdirname)

        # Create a big enough file with a non-useful, obfuscated filename
        output_file1 = os.path.join(subsubdirname, "111c1c9e2bdfb5114044bf25152b7eab.bla")
        create_big_file(output_file1)
        assert os.path.isfile(output_file1)

        # create the filelist, with just the above file
        myfilelist = [output_file1]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        deobfuscate_list(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(output_file1)  # original filename should not be there anymore

        # Check the renaming
        assert os.path.isfile(os.path.join(subsubdirname, jobname + ".bla"))  # ... it should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_big_file_small_accompanying_files(self):
        # input: myiso.iso, with accompanying files (.srt files in this case)
        # test that the small accompanying files (with same basename) are renamed accordingly to the big ISO

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_DATA_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a big enough file with a non-useful filename
        isofile = os.path.join(dirname, "myiso.iso")
        create_big_file(isofile)
        assert os.path.isfile(isofile)

        # and a srt file
        srtfile = os.path.join(dirname, "myiso.srt")
        create_small_file(srtfile)
        assert os.path.isfile(srtfile)

        # and a dut.srt file
        dutsrtfile = os.path.join(dirname, "myiso.dut.srt")
        create_small_file(dutsrtfile)
        assert os.path.isfile(dutsrtfile)

        # and a non-related file
        txtfile = os.path.join(dirname, "something.txt")
        create_small_file(txtfile)
        assert os.path.isfile(txtfile)

        # create the filelist, with just the above files
        myfilelist = [isofile, srtfile, dutsrtfile, txtfile]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        deobfuscate_list(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(isofile)  # original iso not be there anymore
        assert not os.path.isfile(srtfile)  # ... and accompanying file neither
        assert not os.path.isfile(dutsrtfile)  # ... and this one neither
        assert os.path.isfile(txtfile)  # should still be there: not accompanying, and too small to rename

        # Check the renaming
        assert os.path.isfile(os.path.join(dirname, jobname + ".iso"))  # ... should be renamed to the jobname
        assert os.path.isfile(os.path.join(dirname, jobname + ".srt"))  # ... should be renamed to the jobname
        assert os.path.isfile(os.path.join(dirname, jobname + ".dut.srt"))  # ... should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_filelist_nasty_tests(self):
        # check no problems occur with nasty use cases

        # non existing file
        myfilelist = ["/bla/bla/notthere.bin"]
        jobname = "My Important Download 2020"
        deobfuscate_list(myfilelist, jobname)

        # Create directory with a directory name to could be renamed
        dirname = os.path.join(SAB_DATA_DIR, "333c1c9e2bdfb5114044bf25152b7eaa.bla")
        os.mkdir(dirname)
        myfilelist = [dirname]
        jobname = "My Important Download 2020"
        deobfuscate_list(myfilelist, jobname)
        assert os.path.exists(dirname)
        shutil.rmtree(dirname)

    def test_deobfuscate_par2(self):
        # Simple test to see if the par2 file is picked up
        test_dir = os.path.join(SAB_DATA_DIR, "deobfuscate_filenames")
        test_input = os.path.join(test_dir, "E0CcYdGDFbeCAsT3LoID")
        test_output = os.path.join(test_dir, "random.bin")

        # Check if it is there
        assert os.path.exists(test_input)

        list_of_files = []
        for (dirpath, dirnames, filenames) in os.walk(test_dir):
            list_of_files += [os.path.join(dirpath, file) for file in filenames]
        # Run deobfuscate
        deobfuscate_list(list_of_files, "doesnt_matter")

        # Should now be renamed to the filename in the par2 file
        assert not os.path.exists(test_input)
        assert os.path.exists(test_output)

        # Rename back
        os.rename(test_output, test_input)
        assert os.path.exists(test_input)
