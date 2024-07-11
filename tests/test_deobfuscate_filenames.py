#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
import os.path
import random
import shutil
import zipfile

from sabnzbd.deobfuscate_filenames import *
from tests.testhelper import *


def create_big_file(filename):
    with open(filename, "wb") as myfile:
        # must be above MIN_SIZE, so ... 15MB
        myfile.truncate(15 * 1024 * 1024)


def create_small_file(filename):
    with open(filename, "wb") as myfile:
        myfile.truncate(1024)


@pytest.mark.usefixtures("clean_cache_dir")
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
        assert is_probably_obfuscated("[BlaBla] something [More] something b2.bef89a622e4a23f07b0d3757ad5e8a.a0 [Brrr]")

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

    @staticmethod
    def deobfuscate_wrapper(filelist, jobname):
        """Wrapper to avoid the need for NZO"""
        nzo = mock.Mock()
        nzo.set_unpack_info = mock.Mock()
        deobfuscate(nzo, filelist, jobname)

    def test_deobfuscate_filelist_lite(self):
        # lightweight test of deobfuscating: with just one file

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a big file with a useless, obfuscated filename
        output_file1 = os.path.join(dirname, "111c1c9e2bdfb5114044bf25152b7eab.bin")
        create_big_file(output_file1)
        assert os.path.isfile(output_file1)

        # create the filelist, with just the above file
        myfilelist = [output_file1]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(output_file1)  # original filename should not be there anymore
        # Check the renaming
        assert os.path.isfile(os.path.join(dirname, jobname + ".bin"))  # ... it should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_big_file_small_accompanying_files(self):
        # input: myiso.iso, with accompanying files (.srt and -sample files)
        # test that the accompanying files (with same basename) are renamed accordingly to the big ISO
        # Note: this is the most typical usage of deobfuscation

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a big enough file with a useless filename
        isofile = os.path.join(dirname, "myiso.iso")
        create_big_file(isofile)
        assert os.path.isfile(isofile)

        # and a srt file
        srtfile = os.path.join(dirname, "myiso.srt")
        create_small_file(srtfile)
        assert os.path.isfile(srtfile)

        # and a sample file
        samplefile = os.path.join(dirname, "myiso-sample.iso")
        create_small_file(samplefile)
        assert os.path.isfile(samplefile)

        # and a non-related file
        txtfile = os.path.join(dirname, "something.txt")
        create_small_file(txtfile)
        assert os.path.isfile(txtfile)

        # create the filelist, with just the above files
        myfilelist = [isofile, srtfile, samplefile, txtfile]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(isofile)  # original iso not be there anymore
        assert not os.path.isfile(srtfile)  # ... and accompanying file neither
        assert not os.path.isfile(samplefile)  # ... and this one neither
        assert os.path.isfile(txtfile)  # should still be there: not accompanying

        # Check the renaming
        assert os.path.isfile(os.path.join(dirname, jobname + ".iso"))  # ... should be renamed to the jobname
        assert os.path.isfile(os.path.join(dirname, jobname + ".srt"))  # ... should be renamed to the jobname
        assert os.path.isfile(os.path.join(dirname, jobname + "-sample.iso"))  # ... should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_filelist_full(self):
        # Full test, with a combinantion of files: Test that deobfuscate() works and renames correctly
        # ... but only the files that are in the filelist

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a big enough file with a useless filename
        output_file1 = os.path.join(dirname, "111c1c9e2bdfb5114044bf25152b7eaa.bin")
        create_big_file(output_file1)
        assert os.path.isfile(output_file1)

        # create a small file. Obfuscated, but should not get renamed
        output_file2 = os.path.join(dirname, "222c1c9e2bdfb5114044bf25152b7eaa.bin")
        create_small_file(output_file2)
        assert os.path.isfile(output_file2)

        # create the filelist, with just the above files
        myfilelist = [output_file1, output_file2]

        # Create some extra files ... that will not be in the list
        output_file3 = os.path.join(dirname, "333c1c9e2bdfb5114044bf25152b7eaa.bin")
        create_big_file(output_file3)
        assert os.path.isfile(output_file3)

        output_file4 = os.path.join(dirname, "This Great Download 2020.bin")
        create_big_file(output_file4)
        assert os.path.isfile(output_file4)

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(output_file1)  # original filename should not be there anymore
        assert os.path.isfile(output_file2)  # original smaller file should still be there
        assert os.path.isfile(output_file3)  # but this one should still be there
        assert os.path.isfile(output_file4)  # and this one too

        # Check the renaming
        assert os.path.isfile(os.path.join(dirname, jobname + ".bin"))  # ... it should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_one_small_file(self):
        #  Test of deobfuscating: with just one small file

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create a small file with a useless, obfuscated filename
        output_file1 = os.path.join(dirname, "blabla.txt")
        create_small_file(output_file1)
        assert os.path.isfile(output_file1)

        # create the filelist, with just the above file
        myfilelist = [output_file1]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(output_file1)  # original filename should not be there anymore
        # Check the renaming
        assert os.path.isfile(os.path.join(dirname, jobname + ".txt"))  # ... it should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_filelist_subdir(self):
        # test of deobfuscating with sub directories

        # Create directory with subdirs
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)
        subdirname = os.path.join(dirname, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(subdirname)
        subsubdirname = os.path.join(subdirname, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(subsubdirname)

        # Create a big enough file with a useless, obfuscated filename
        output_file1 = os.path.join(subsubdirname, "111c1c9e2bdfb5114044bf25152b7eab.bin")
        create_big_file(output_file1)
        assert os.path.isfile(output_file1)

        # create the filelist, with just the above file
        myfilelist = [output_file1]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # Check original files:
        assert not os.path.isfile(output_file1)  # original filename should not be there anymore

        # Check the renaming
        assert os.path.isfile(os.path.join(subsubdirname, jobname + ".bin"))  # ... it should be renamed to the jobname

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_no_deobfuscate_DVD_dir(self):
        # test of typical DVD directory structure ... no deobfuscating should happen

        # Create a working directory, with a VIDEO_TS subdirectory
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)
        subdirname = os.path.join(dirname, "VIDEO_TS")
        os.mkdir(subdirname)
        # Create a big file with a useless, obfuscated filename (which normally should get renamed)
        output_file1 = os.path.join(subdirname, "111c1c9e2bdfb5114044bf25152b7eab.bin")
        create_big_file(output_file1)
        assert os.path.isfile(output_file1)

        # create the filelist, with just the above file
        myfilelist = [output_file1]
        # and now unleash deobfuscate() on that filelist, with a useful jobname:
        jobname = "My DVD 2021"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # ... but because inside "VIDEO_TS" directory, the file should not be touched / renamed:
        assert os.path.isfile(output_file1)  # should still be there

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_collection_with_same_size(self):
        # input: a collection of a few files with about the same size
        # test that there is no renaming

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        # Create big enough files with a useless filenames, all with same extension
        file1 = os.path.join(dirname, "file1.bin")
        create_big_file(file1)
        assert os.path.isfile(file1)

        file2 = os.path.join(dirname, "file2.bin")
        create_big_file(file2)
        assert os.path.isfile(file2)

        file3 = os.path.join(dirname, "file3.bin")
        create_big_file(file3)
        assert os.path.isfile(file3)

        file4 = os.path.join(dirname, "file4.bin")
        create_big_file(file4)
        assert os.path.isfile(file4)

        # create the filelist, with the above files
        myfilelist = [file1, file2, file3, file4]

        # and now unleash the magic on that filelist, with a more useful jobname:
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # Check original files:
        # the collection with same extension should still be there:
        assert os.path.isfile(file1)  # still there
        assert os.path.isfile(file2)  # still there
        assert os.path.isfile(file3)  # still there
        assert os.path.isfile(file4)  # still there

        # Done. Remove (non-empty) directory
        shutil.rmtree(dirname)

    def test_deobfuscate_filelist_nasty_tests(self):
        # check no problems occur with nasty use cases

        # non existing file
        myfilelist = ["/bla/bla/notthere.bin"]
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)

        # Create directory with a directory name that could be renamed, but should not
        dirname = os.path.join(SAB_CACHE_DIR, "333c1c9e2bdfb5114044bf25152b7eaa.bin")
        os.mkdir(dirname)
        myfilelist = [dirname]
        jobname = "My Important Download 2020"
        self.deobfuscate_wrapper(myfilelist, jobname)
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
        for dirpath, dirnames, filenames in os.walk(test_dir):
            list_of_files += [os.path.join(dirpath, file) for file in filenames]
        # Run deobfuscate
        recover_par2_names(list_of_files)

        # Should now be renamed to the filename in the par2 file
        assert not os.path.exists(test_input)
        assert os.path.exists(test_output)

        # Rename back
        os.rename(test_output, test_input)
        assert os.path.exists(test_input)

    def test_deobfuscate_par2_plus_deobfuscate(self):
        # test for first par2 based renaming, then deobfuscate obfuscated names
        work_dir = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(work_dir)

        source_zip_file = os.path.join(SAB_DATA_DIR, "deobfuscate_par2_based", "20mb_with_par2_package.zip")
        with zipfile.ZipFile(source_zip_file, "r") as zip_ref:
            zip_ref.extractall(work_dir)
        assert os.path.isfile(os.path.join(work_dir, "rename.par2"))  # the par2 that will do renaming
        assert os.path.isfile(os.path.join(work_dir, "aaaaaaaaaaa"))  # a 20MB no-name file ...

        list_of_files = []
        for dirpath, dirnames, filenames in os.walk(work_dir):
            list_of_files += [os.path.join(dirpath, file) for file in filenames]

        # deobfuscate will do:
        # first par2 based renaming aaaaaaaaaaa to twentymb.bin,
        # then deobfuscate twentymb.bin to the job name (with same extension)
        list_of_files = recover_par2_names(list_of_files)
        print(list_of_files)
        assert os.path.isfile(os.path.join(work_dir, "twentymb.bin"))  # should exist

        self.deobfuscate_wrapper(list_of_files, "My Great Download")
        assert os.path.isfile(os.path.join(work_dir, "My Great Download.bin"))  # the twentymb.bin should be renamed
        assert not os.path.isfile(os.path.join(work_dir, "twentymb.bin"))  # should now be gone

        shutil.rmtree(work_dir)

    def test_first_file_is_much_bigger(self):

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        assert clearly_one_big_file([])

        smallfile1 = os.path.join(dirname, "AAAA.bin")
        create_small_file(smallfile1)
        assert os.path.isfile(smallfile1)

        bigfile = os.path.join(dirname, "KKKK.bin")
        create_big_file(bigfile)
        assert os.path.isfile(bigfile)

        smallfile2 = os.path.join(dirname, "LLLL.bin")
        create_small_file(smallfile2)
        assert os.path.isfile(smallfile2)

        # files of same size, so no biggest file
        myfilelist = [smallfile1, smallfile2]
        assert not clearly_one_big_file(myfilelist)

        # now add the bigger file
        myfilelist = [smallfile1, smallfile2, bigfile]
        assert clearly_one_big_file(myfilelist)

        shutil.rmtree(dirname)

    def test_deobfuscate_subtitles(self):
        # input: a big file, and srt file(s), and non-related files
        # result: srt file renamed according to the big file

        # Create directory (with a random directory name)
        dirname = os.path.join(SAB_CACHE_DIR, "testdir" + str(random.randint(10000, 99999)))
        os.mkdir(dirname)

        bigfile = os.path.join(dirname, "bigfile.avi")
        create_big_file(bigfile)
        assert os.path.isfile(bigfile)

        already_correct_srt = os.path.join(dirname, "bigfile.srt")
        create_small_file(already_correct_srt)
        assert os.path.isfile(already_correct_srt)

        small_srt = os.path.join(dirname, "dut.srt")
        create_small_file(small_srt)
        assert os.path.isfile(small_srt)
        expected_small_srt = os.path.join(dirname, "bigfile.dut.srt")

        underscore_srt = os.path.join(dirname, "13_Deutsch.srt")
        create_small_file(underscore_srt)
        assert os.path.isfile(underscore_srt)
        expected_underscore_srt = os.path.join(dirname, "bigfile.13.Deutsch.srt")

        small_txt = os.path.join(dirname, "readme.txt")
        create_small_file(small_txt)
        assert os.path.isfile(small_txt)

        # go
        deobfuscate_subtitles(dirname)

        assert os.path.isfile(bigfile)  # unchanged
        assert os.path.isfile(already_correct_srt)  # unchanged
        assert not os.path.isfile(small_srt)  # should be renamed to:
        assert os.path.isfile(expected_small_srt)
        assert not os.path.isfile(underscore_srt)  # should be renamed to:
        assert os.path.isfile(expected_underscore_srt)
        assert os.path.isfile(small_txt)  # unchanged

        # and if we go again ... nothing should happen: all files are already correct
        deobfuscate_subtitles(dirname)

        assert os.path.isfile(bigfile)  # unchanged
        assert os.path.isfile(already_correct_srt)  # unchanged
        assert not os.path.isfile(small_srt)  # should be renamed to:
        assert os.path.isfile(expected_small_srt)
        assert not os.path.isfile(underscore_srt)  # should be renamed to:
        assert os.path.isfile(expected_underscore_srt)
        assert os.path.isfile(small_txt)  # unchanged

        shutil.rmtree(dirname)
