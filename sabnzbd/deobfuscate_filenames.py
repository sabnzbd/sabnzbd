#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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

Deobfuscation post-processing script:

Will check in the completed job folder if maybe there are par2 files,
for example "rename.par2", and use those to rename the files.
If there is no "rename.par2" available, it will rename large, not-excluded
files to the job-name in the queue if the filename looks obfuscated

Based on work by P1nGu1n

"""

import hashlib
import logging
import os
import re

from sabnzbd.filesystem import get_unique_filename, renamer, get_ext
from sabnzbd.par2file import is_parfile, parse_par2_file
import sabnzbd.utils.file_extension as file_extension
from sabnzbd.misc import match_str
from sabnzbd.constants import IGNORED_MOVIE_FOLDERS
from typing import List

# Files to exclude and minimal file size for renaming
EXCLUDED_FILE_EXTS = (".vob", ".rar", ".par2", ".mts", ".m2ts", ".cpi", ".clpi", ".mpl", ".mpls", ".bdm", ".bdmv")
MIN_FILE_SIZE = 10 * 1024 * 1024


def decode_par2(parfile: str) -> List[str]:
    """Parse a par2 file and rename files listed in the par2 to their real name. Resturn list of generated files"""
    # Check if really a par2 file
    if not is_parfile(parfile):
        logging.info("Par2 file %s was not really a par2 file")
        return []

    # Parse the par2 file
    md5of16k = {}
    parse_par2_file(parfile, md5of16k)

    # Parse all files in the folder
    dirname = os.path.dirname(parfile)
    new_files = []  # list of new files generated
    for fn in os.listdir(dirname):
        filepath = os.path.join(dirname, fn)
        # Only check files
        if os.path.isfile(filepath):
            with open(filepath, "rb") as fileToMatch:
                first16k_data = fileToMatch.read(16384)

            # Check if we have this hash and the filename is different
            file_md5of16k = hashlib.md5(first16k_data).digest()
            if file_md5of16k in md5of16k and fn != md5of16k[file_md5of16k]:
                new_path = os.path.join(dirname, md5of16k[file_md5of16k])
                # Make sure it's a unique name
                unique_filename = get_unique_filename(new_path)
                renamer(filepath, unique_filename)
                new_files.append(unique_filename)
    return new_files


def recover_par2_names(filelist: List[str]) -> List[str]:
    """Find par2 files and use them for renaming"""
    # Check that files exists
    filelist = [f for f in filelist if os.path.isfile(f)]
    # Search for par2 files in the filelist
    par2_files = [f for f in filelist if f.endswith(".par2")]
    # Found any par2 files we can use?
    if not par2_files:
        logging.debug("No additional par2 files found to process")
    else:
        # Run par2 from SABnzbd on them
        for par2_file in par2_files:
            # Analyse data and analyse result
            logging.debug("Deobfuscate par2: handling %s", par2_file)
            new_files = decode_par2(par2_file)
            if new_files:
                logging.debug("Deobfuscate par2 repair/verify finished")
                filelist += new_files
                filelist = [f for f in filelist if os.path.isfile(f)]
            else:
                logging.debug("Deobfuscate par2 repair/verify did not find anything to rename")
    return filelist


def is_probably_obfuscated(myinputfilename: str) -> bool:
    """Returns boolean if filename is likely obfuscated. Default: True, so obfuscated
    myinputfilename (string) can be a plain file name, or a full path"""

    # Find filebasename
    path, filename = os.path.split(myinputfilename)
    filebasename, fileextension = os.path.splitext(filename)
    logging.debug("Checking: %s", filebasename)

    # First: the patterns that are certainly obfuscated:

    # ...blabla.H.264/b082fa0beaa644d3aa01045d5b8d0b36.mkv is certainly obfuscated
    if re.findall(r"^[a-f0-9]{32}$", filebasename):
        logging.debug("Obfuscated: 32 hex digit")
        # exactly 32 hex digits, so:
        return True

    # 0675e29e9abfd2.f7d069dab0b853283cc1b069a25f82.6547
    if re.findall(r"^[a-f0-9.]{40,}$", filebasename):
        logging.debug("Obfuscated: starting with 40+ lower case hex digits and/or dots")
        return True

    # "[BlaBla] something [More] something 5937bc5e32146e.bef89a622e4a23f07b0d3757ad5e8a.a02b264e [Brrr]"
    # So: square brackets plus 30+ hex digit
    if re.findall(r"[a-f0-9]{30}", filebasename) and len(re.findall(r"\[\w+\]", filebasename)) >= 2:
        logging.debug("Obfuscated: square brackets plus a 30+ hex")
        return True

    # /some/thing/abc.xyz.a4c567edbcbf27.BLA is certainly obfuscated
    if re.findall(r"^abc\.xyz", filebasename):
        logging.debug("Obfuscated: starts with 'abc.xyz'")
        # ... which we consider as obfuscated:
        return True

    # Then: patterns that are not obfuscated but typical, clear names:

    # these are signals for the obfuscation versus non-obfuscation
    decimals = sum(1 for c in filebasename if c.isnumeric())
    upperchars = sum(1 for c in filebasename if c.isupper())
    lowerchars = sum(1 for c in filebasename if c.islower())
    spacesdots = sum(1 for c in filebasename if c == " " or c == "." or c == "_")  # space-like symbols

    # Example: "Great Distro"
    if upperchars >= 2 and lowerchars >= 2 and spacesdots >= 1:
        logging.debug("Not obfuscated: upperchars >= 2 and lowerchars >= 2  and spacesdots >= 1")
        return False

    # Example: "this is a download"
    if spacesdots >= 3:
        logging.debug("Not obfuscated: spacesdots >= 3")
        return False

    # Example: "Beast 2020"
    if (upperchars + lowerchars >= 4) and decimals >= 4 and spacesdots >= 1:
        logging.debug("Not obfuscated: (upperchars + lowerchars >= 4) and decimals > 3 and spacesdots > 1")
        return False

    # Example: "Catullus", starts with a capital, and most letters are lower case
    if filebasename[0].isupper() and lowerchars > 2 and upperchars / lowerchars <= 0.25:
        logging.debug("Not obfuscated: starts with a capital, and most letters are lower case")
        return False

    # Finally: default to obfuscated:
    logging.debug("Obfuscated (default)")
    return True  # default is obfuscated


def first_file_is_much_bigger(filelist):
    # returns True if first file is much bigger than second file
    # Note: input parameter filelist must ordered on size!
    try:
        factor = os.path.getsize(filelist[0]) / os.path.getsize(filelist[1])
        if factor > 3:
            return True
        else:
            return False
    except:
        # no second file at all
        return True


def deobfuscate(nzo, filelist: List[str], usefulname: str):
    """For files in filelist:
    # 1. if no meaningful extension, add it
    # 2. pick biggest file (and its lookalikes), and deobfuscate (if needed), to usefulname"""

    # Can't be imported directly due to circular import
    nzo: sabnzbd.nzbstuff.NzbObject

    # to be sure, only keep really existing files:
    filelist = [f for f in filelist if os.path.isfile(f)]

    # Do not deobfuscate/rename anything if there is a typical DVD or Bluray directory:
    ignored_movie_folders_with_dir_sep = tuple(os.path.sep + f + os.path.sep for f in IGNORED_MOVIE_FOLDERS)
    match_ignored_movie_folders = [f for f in filelist if match_str(f, ignored_movie_folders_with_dir_sep)]
    if match_ignored_movie_folders:
        logging.info(
            "Skipping deobfuscation because of DVD/Bluray directory name(s), like: %s",
            str(match_ignored_movie_folders)[:200],
        )
        nzo.set_unpack_info("Deobfuscate", T("Deobfuscate skipped due to DVD/Bluray directories"))
        return

    # If needed, add a useful extension (by looking at file contents)
    # Example: if 'kjladsflkjadf.adsflkjads' is probably a PNG, rename to 'kjladsflkjadf.adsflkjads.png'
    newlist = []
    nr_ext_renamed = 0
    for file in filelist:
        if file_extension.has_popular_extension(file):
            # common extension, like .doc or .iso, so assume OK and change nothing
            logging.debug("Extension of %s looks common", file)
            newlist.append(file)
        else:
            # uncommon (so: obfuscated) extension
            new_extension_to_add = file_extension.what_is_most_likely_extension(file)
            if new_extension_to_add:
                new_name = get_unique_filename("%s%s" % (file, new_extension_to_add))
                logging.info("Deobfuscate renaming (adding extension) %s to %s", file, new_name)
                renamer(file, new_name)
                newlist.append(new_name)
                nr_ext_renamed += 1
            else:
                # no new extension found
                newlist.append(file)

    if nr_ext_renamed:
        nzo.set_unpack_info("Deobfuscate", T("Deobfuscate corrected the extension of %d file(s)") % nr_ext_renamed)
        filelist = newlist

    """
    Deobfuscation: we want to rename meaningless / obfuscated filenames. 
    We do that only with the biggest file, plus including accompanying files with the same base filename
    Typical cases:
    
    Case 1:
    
    bla.iso (1000MB, so much bigger than next biggest file)
    bla-sample.iso (100MB)
    bla.txt (1MB)
    something.txt (1MB)
    
    Because "bla" looks meaningless / obfuscated, we rename these files to
    
    Nice_Name_1234.iso
    Nice_Name_1234-sample.iso
    Nice_Name_1234.txt
    something.txt (no renaming)
    
    Case 2:
    
    one.bin (10MB)
    two.bin (12MB)
    three.bin (8MB)
    
    No renaming, because the biggest file (12MB) is not much bigger than the second biggest file (10MB)
    
    Case 3:
    
    Great_File_1969.iso (1000MB)
    
    No renaming because the filename looks OK already (not obfuscated)
    
    """

    logging.debug("Trying to see if there are qualifying files to be deobfuscated")
    nr_files_renamed = 0

    # We pick the biggest file ... probably the most important file
    # so sort filelist on size:
    filelist = sorted(filelist, key=os.path.getsize, reverse=True)
    if filelist:
        biggest_file = filelist[0]
    else:
        biggest_file = None
    if not (biggest_file and os.path.isfile(biggest_file)):
        # no file found
        return
    logging.debug("Deobfuscate inspecting biggest file%s", biggest_file)
    if not first_file_is_much_bigger(filelist):
        logging.debug("%s excluded from deobfuscation because it is not much bigger than other file(s)", biggest_file)
        return
    if get_ext(biggest_file) in EXCLUDED_FILE_EXTS:
        logging.debug("%s excluded from deobfuscation because of excluded extension", biggest_file)
        return
    if not is_probably_obfuscated(biggest_file):
        logging.debug("%s excluded from deobfuscation based because filename does not obfuscatec", biggest_file)
        return

    # if we get here, the biggest_file is relatively big, has no excluded extension, and is obfuscated
    # Rename the biggest_file and make sure the new filename is unique
    path, file = os.path.split(biggest_file)
    # construct new_name: <path><usefulname><extension>
    new_name = get_unique_filename("%s%s" % (os.path.join(path, usefulname), get_ext(biggest_file)))
    logging.info("Deobfuscate renaming %s to %s", biggest_file, new_name)
    renamer(biggest_file, new_name)
    nr_files_renamed += 1

    # Now find other files with the same basename in filelist, and rename them in the same way:
    basedirfile, _ = os.path.splitext(biggest_file)  # something like "/home/this/myiso"
    for otherfile in filelist:
        if otherfile.startswith(basedirfile) and os.path.isfile(otherfile):
            # yes, same basedirfile, only different ending
            remaining_ending = otherfile.replace(basedirfile, "")  # might be long ext, like ".dut.srt" or "-sample.iso"
            new_name = get_unique_filename("%s%s" % (os.path.join(path, usefulname), remaining_ending))
            logging.info("Deobfuscate renaming %s to %s", otherfile, new_name)
            # Rename and make sure the new filename is unique
            renamer(otherfile, new_name)
            nr_files_renamed += 1

    if nr_files_renamed:
        nzo.set_unpack_info("Deobfuscate", T("Deobfuscate renamed %d file(s)") % nr_files_renamed)
