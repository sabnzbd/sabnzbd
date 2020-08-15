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
files to the job-name in the queue.

Improved by P1nGu1n

"""

import os
import sys
import time
import fnmatch
import struct
import hashlib
import re
import math
import logging
from sabnzbd.filesystem import get_unique_filename

# Files to exclude and minimal file size for renaming
EXCLUDED_FILE_EXTS = (".vob", ".rar", ".par2")
MIN_FILE_SIZE = 10 * 1024 * 1024

# see: http://parchive.sourceforge.net/docs/specifications/parity-volume-spec/article-spec.html
STRUCT_PACKET_HEADER = struct.Struct(
    "<"
    "8s"  # Magic sequence
    "Q"  # Length of the entire packet (including header), must be multiple of 4
    "16s"  # MD5 Hash of packet
    "16s"  # Recovery Set ID
    "16s"  # Packet type
)

PACKET_TYPE_FILE_DESC = "PAR 2.0\x00FileDesc"
STRUCT_FILE_DESC_PACKET = struct.Struct(
    "<"
    "16s"  # File ID
    "16s"  # MD5 hash of the entire file
    "16s"  # MD5 hash of the first 16KiB of the file
    "Q"  # Length of the file
)


def decode_par2(parfile):
    result = False
    dirname = os.path.dirname(parfile)
    with open(parfile, "rb") as parfileToDecode:
        while True:
            header = parfileToDecode.read(STRUCT_PACKET_HEADER.size)
            if not header:
                break  # file fully read

            (_, packetLength, _, _, packet_type) = STRUCT_PACKET_HEADER.unpack(header)
            body_length = packetLength - STRUCT_PACKET_HEADER.size

            # only process File Description packets
            if packet_type != PACKET_TYPE_FILE_DESC:
                # skip this packet
                parfileToDecode.seek(body_length, os.SEEK_CUR)
                continue

            chunck = parfileToDecode.read(STRUCT_FILE_DESC_PACKET.size)
            (_, _, hash16k, filelength) = STRUCT_FILE_DESC_PACKET.unpack(chunck)

            # filename makes up for the rest of the packet, padded with null characters
            target_name = parfileToDecode.read(body_length - STRUCT_FILE_DESC_PACKET.size).rstrip(b"\0")
            target_path = os.path.join(dirname, target_name)

            # file already exists, skip it
            if os.path.exists(target_path):
                logging.debug("File already exists: %s" % target_name)
                continue

            # find and rename file
            src_path = find_file(dirname, filelength, hash16k)
            if src_path is not None:
                os.rename(src_path, target_path)
                logging.debug("Renamed file from %s to %s" % (os.path.basename(src_path), target_name))
                result = True
            else:
                logging.debug("No match found for: %s" % target_name)
    return result


def find_file(dirname, filelength, hash16k):
    for fn in os.listdir(dirname):
        filepath = os.path.join(dirname, fn)

        # check if the size matches as an indication
        if os.path.getsize(filepath) != filelength:
            continue

        with open(filepath, "rb") as fileToMatch:
            data = fileToMatch.read(16 * 1024)
            m = hashlib.md5()
            m.update(data)

            # compare hash to confirm the match
            if m.digest() == hash16k:
                return filepath
    return None


def entropy(string):
    """ Calculates the Shannon entropy of a string """

    # get probability of chars in string
    prob = [float(string.count(c)) / len(string) for c in dict.fromkeys(list(string))]

    # calculate the entropy
    entropy = -sum([p * math.log(p) / math.log(2.0) for p in prob])

    return entropy


def is_probably_obfuscated(myinputfilename):
    # Returns boolean if filename is probably obfuscated
    # myinputfilename can be a plain file name, or a full path

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


def deobfuscate(workingdirectory, usefulname, *args, **kwargs):
    """ in workingdirectory, check all filenames, and if wanted, rename """
    dummyrun = kwargs.get("dummyrun", None)  # do not really rename

    # Search for par2 files
    matches = []
    for root, dirnames, filenames in os.walk(workingdirectory):
        for filename in fnmatch.filter(filenames, "*.par2"):
            matches.append(os.path.join(root, filename))
    logging.debug("par2 files matches is %s", matches)

    # Found any par2 files we can use?
    run_renamer = True
    if not matches:
        logging.debug("No par2 files found to process.")

    # Run par2 from SABnzbd on them
    for par2_file in matches:
        # Analyse data and analyse result
        logging.debug("deobfus par2: handling %s", par2_file)
        if decode_par2(par2_file):
            logging.debug("Recursive repair/verify finished.")
            run_renamer = False
        else:
            logging.debug("Recursive repair/verify did not complete!")

    # No matches? Then we try to rename the largest file to the job-name
    if run_renamer:
        logging.debug("Trying to see if there are large files to be renamed")
        for root, dirnames, filenames in os.walk(workingdirectory):
            for filename in filenames:
                logging.debug("Inspecting %s", filename)
                full_path = os.path.join(root, filename)
                file_size = os.path.getsize(full_path)
                # Do we need to rename this file? Criteria: big, not-excluded extension, obfuscated
                if (
                    file_size > MIN_FILE_SIZE
                    and os.path.splitext(filename)[1].lower() not in EXCLUDED_FILE_EXTS
                    and is_probably_obfuscated(filename)  # this as last test
                ):
                    # OK, rename
                    new_name = "%s%s" % (
                        os.path.join(workingdirectory, usefulname),
                        os.path.splitext(filename)[1].lower(),
                    )
                    # make sure the filename is unique
                    new_name = get_unique_filename(new_name)
                    logging.debug("Renaming %s to %s", full_path, new_name)

                    # Rename, with retries for Windows
                    for r in range(3):
                        try:
                            os.rename(full_path, new_name)
                            logging.debug("Renaming done on run %s!", r + 1)
                            break
                        except:
                            time.sleep(1)
    else:
        logging.debug("No large files found")
