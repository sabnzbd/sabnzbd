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
        logging.debug("No par2 files found to process, running renamer")
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
    """Returns boolean if filename is likely obfuscated. Default: True
    myinputfilename (string) can be a plain file name, or a full path"""

    # Find filebasename
    path, filename = os.path.split(myinputfilename)
    filebasename, fileextension = os.path.splitext(filename)

    # First fixed patterns that we know of:
    logging.debug("Checking: %s", filebasename)

    # ...blabla.H.264/b082fa0beaa644d3aa01045d5b8d0b36.mkv is certainly obfuscated
    if re.findall(r"^[a-f0-9]{32}$", filebasename):
        logging.debug("Obfuscated: 32 hex digit")
        # exactly 32 hex digits, so:
        return True

    # 0675e29e9abfd2.f7d069dab0b853283cc1b069a25f82.6547
    if re.findall(r"^[a-f0-9.]{40,}$", filebasename):
        logging.debug("Obfuscated: starting with 40+ lower case hex digits and/or dots")
        return True

    # /some/thing/abc.xyz.a4c567edbcbf27.BLA is certainly obfuscated
    if re.findall(r"^abc\.xyz", filebasename):
        logging.debug("Obfuscated: starts with 'abc.xyz'")
        # ... which we consider as obfuscated:
        return True

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

    # If we get here, no trigger for a clear name was found, so let's default to obfuscated
    logging.debug("Obfuscated (default)")
    return True  # default not obfuscated


def deobfuscate_list(filelist: List[str], usefulname: str):
    """Check all files in filelist, and if wanted, deobfuscate: rename to filename based on usefulname"""

    # Methods
    # 1. based on par2 (if any)
    # 2. if no meaningful extension, add it
    # 3. based on detecting obfuscated filenames

    # to be sure, only keep really exsiting files:
    filelist = [f for f in filelist if os.path.isfile(f)]

    # let's see if there are files with uncommon/unpopular (so: obfuscated) extensions
    # if so, let's give them a better extension based on their internal content/info
    # Example: if 'kjladsflkjadf.adsflkjads' is probably a PNG, rename to 'kjladsflkjadf.adsflkjads.png'
    newlist = []
    for file in filelist:
        if file_extension.has_popular_extension(file):
            # common extension, like .doc or .iso, so assume OK and change nothing
            logging.debug("extension of %s looks common", file)
            newlist.append(file)
        else:
            # uncommon (so: obfuscated) extension
            new_extension_to_add = file_extension.what_is_most_likely_extension(file)
            if new_extension_to_add:
                new_name = get_unique_filename("%s%s" % (file, new_extension_to_add))
                logging.info("Deobfuscate renaming (adding extension) %s to %s", file, new_name)
                renamer(file, new_name)
                newlist.append(new_name)
            else:
                # no new extension found
                newlist.append(file)
    filelist = newlist

    # Now we try to rename qualifying (big, not-excluded, obfuscated) files to the job-name
    excluded_file_exts = EXCLUDED_FILE_EXTS
    # If there is a collection with bigger files with the same extension, we don't want to rename it
    extcounter = {}
    for file in filelist:
        if os.path.getsize(file) < MIN_FILE_SIZE:
            # too small to care
            continue
        ext = get_ext(file)
        if ext in extcounter:
            extcounter[ext] += 1
        else:
            extcounter[ext] = 1
        if extcounter[ext] >= 3 and ext not in excluded_file_exts:
            # collection, and extension not yet in excluded_file_exts, so add it
            excluded_file_exts = (*excluded_file_exts, ext)
            logging.debug(
                "Found a collection of at least %s files with extension %s, so not renaming those files",
                extcounter[ext],
                ext,
            )

    logging.debug("Trying to see if there are qualifying files to be deobfuscated")
    # We start with he biggest file ... probably the most important file
    filelist = sorted(filelist, key=os.path.getsize, reverse=True)
    for filename in filelist:
        # check that file is still there (and not renamed by the secondary renaming process below)
        if not os.path.isfile(filename):
            continue
        logging.debug("Deobfuscate inspecting %s", filename)
        # Do we need to rename this file?
        # Criteria: big, not-excluded extension, obfuscated (in that order)
        if (
            os.path.getsize(filename) > MIN_FILE_SIZE
            and get_ext(filename) not in excluded_file_exts
            and is_probably_obfuscated(filename)  # this as last test to avoid unnecessary analysis
        ):
            # Rename and make sure the new filename is unique
            path, file = os.path.split(filename)
            # construct new_name: <path><usefulname><extension>
            new_name = get_unique_filename("%s%s" % (os.path.join(path, usefulname), get_ext(filename)))
            logging.info("Deobfuscate renaming %s to %s", filename, new_name)
            renamer(filename, new_name)
            # find other files with the same basename in filelist, and rename them in the same way:
            basedirfile, _ = os.path.splitext(filename)  # something like "/home/this/myiso"
            for otherfile in filelist:
                if otherfile.startswith(basedirfile + ".") and os.path.isfile(otherfile):
                    # yes, same basedirfile, only different extension
                    remainingextension = otherfile.replace(basedirfile, "")  # might be long ext, like ".dut.srt"
                    new_name = get_unique_filename("%s%s" % (os.path.join(path, usefulname), remainingextension))
                    logging.info("Deobfuscate renaming %s to %s", otherfile, new_name)
                    # Rename and make sure the new filename is unique
                    renamer(otherfile, new_name)
        else:
            logging.debug("%s excluded from deobfuscation based on size, extension or non-obfuscation", filename)
