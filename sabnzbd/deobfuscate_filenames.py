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

Deobfuscation post-processing script:

Will check in the completed job folder if maybe there are par2 files,
for example "rename.par2", and use those to rename the files.
If there is no "rename.par2" available, it will rename large, not-excluded
files to the job-name in the queue if the filename looks obfuscated

Based on work by P1nGu1n

"""

import hashlib
import logging
import math
import os
import re

from sabnzbd.filesystem import get_unique_filename, globber_full, renamer, get_ext
from sabnzbd.par2file import is_parfile, parse_par2_file

# Files to exclude and minimal file size for renaming
EXCLUDED_FILE_EXTS = (".vob", ".rar", ".par2")
MIN_FILE_SIZE = 10 * 1024 * 1024


def decode_par2(parfile):
    """ Parse a par2 file and rename files listed in the par2 to their real name """
    # Check if really a par2 file
    if not is_parfile(parfile):
        logging.info("Par2 file %s was not really a par2 file")
        return False

    # Parse the par2 file
    md5of16k = {}
    parse_par2_file(parfile, md5of16k)

    # Parse all files in the folder
    dirname = os.path.dirname(parfile)
    result = False
    for fn in os.listdir(dirname):
        filepath = os.path.join(dirname, fn)
        # Only check files
        if os.path.isfile(filepath):
            with open(filepath, "rb") as fileToMatch:
                first16k_data = fileToMatch.read(16384)

            # Check if we have this hash
            file_md5of16k = hashlib.md5(first16k_data).digest()
            if file_md5of16k in md5of16k:
                new_path = os.path.join(dirname, md5of16k[file_md5of16k])
                # Make sure it's a unique name
                renamer(filepath, get_unique_filename(new_path))
                result = True
    return result


def entropy(string):
    """ Calculates the Shannon entropy of a string """
    # get probability of chars in string
    prob = [float(string.count(c)) / len(string) for c in dict.fromkeys(list(string))]
    # calculate the entropy
    entropy = -sum([p * math.log(p) / math.log(2.0) for p in prob])
    return entropy


def is_probably_obfuscated(myinputfilename):
    """Returns boolean if filename is probably obfuscated
    myinputfilename can be a plain file name, or a full path"""

    # Find filebasename
    path, filename = os.path.split(myinputfilename)
    filebasename, fileextension = os.path.splitext(filename)

    # ...blabla.H.264/b082fa0beaa644d3aa01045d5b8d0b36.mkv is certainly obfuscated
    if re.findall("^[a-f0-9]{32}$", filebasename):
        logging.debug("Obfuscated: 32 hex digit")
        # exactly 32 hex digits, so:
        return True

    # these are signals for the obfuscation versus non-obfuscation
    capitals = sum(1 for c in filebasename if c.isupper())
    smallletters = sum(1 for c in filebasename if c.lower())
    spacesdots = sum(1 for c in filebasename if c == " " or c == ".")
    decimals = sum(1 for c in filebasename if c.isnumeric())

    if capitals >= 2 and smallletters >= 2 and spacesdots >= 1:
        logging.debug("Not obfuscated: capitals >= 2 and smallletters >= 2  and spacesdots >= 1")
        # useful signs in filebasename, so not obfuscated
        return False

    if spacesdots > 3:
        # useful signs in filebasename, so not obfuscated
        logging.debug("Not obfuscated: spacesdots > 3")
        return False

    if decimals > 3 and spacesdots > 1:
        # useful signs in filebasename, so not obfuscated
        logging.debug("Not obfuscated: decimals > 3 and spacesdots > 1")
        return False

    # little entropy in the filebasename is a sign of useless names
    if entropy(filebasename) < 3.5:
        logging.debug("Obfuscated: entropy < 3.5")
        return True
    # high entropy in the filebasename is a sign of useful name, so not obfuscated
    if entropy(filebasename) > 4.0:
        logging.debug("Not obfuscated: entropy > 4.0")
        return False

    # If we get here ... let's default to not obfuscated
    logging.debug("Not obfuscated (default)")
    return False  # default not obfuscated


def deobfuscate(workingdirectory, usefulname):
    """ In workingdirectory, check all filenames, and if wanted, rename """

    # Search for par2 files
    par2_files = globber_full(workingdirectory, "*.par2")

    # Found any par2 files we can use?
    run_renamer = True
    if not par2_files:
        logging.debug("No par2 files found to process, running renamer.")
    else:
        # Run par2 from SABnzbd on them
        for par2_file in par2_files:
            # Analyse data and analyse result
            logging.debug("Deobfuste par2: handling %s", par2_file)
            if decode_par2(par2_file):
                logging.debug("Deobfuste par2 repair/verify finished.")
                run_renamer = False
            else:
                logging.debug("Deobfuste par2 repair/verify did not find anything to rename.")

    # No par2 files? Then we try to rename qualifying files to the job-name
    if run_renamer:
        logging.debug("Trying to see if there are qualifying files to be deobfusted")
        for root, dirnames, filenames in os.walk(workingdirectory):
            for filename in filenames:
                logging.debug("Deobfuste inspecting %s", filename)
                full_path = os.path.join(root, filename)
                file_size = os.path.getsize(full_path)
                # Do we need to rename this file?
                # Criteria: big, not-excluded extension, obfuscated
                if (
                    file_size > MIN_FILE_SIZE
                    and get_ext(filename) not in EXCLUDED_FILE_EXTS
                    and is_probably_obfuscated(filename)  # this as last test to avoid unnecessary analysis
                ):
                    # OK, rename
                    new_name = get_unique_filename(
                        "%s%s" % (os.path.join(workingdirectory, usefulname), get_ext(filename))
                    )
                    logging.info("Deobfuscate renaming %s to %s", filename, new_name)
                    # Rename and make sure the new filename is unique
                    renamer(full_path, new_name)
    else:
        logging.info("No qualifying files found to deobfuscate")
