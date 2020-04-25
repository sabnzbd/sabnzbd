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
If there is no "rename.par2" available, it will rename the largest
file to the job-name in the queue.

NOTES:
 1) To use this script you need Python installed on your system and
    select "Add to path" during its installation. Select this folder in
    Config > Folders > Scripts Folder and select this script for each job
    you want it used for, or link it to a category in Config > Categories.
 2) Beware that files on the 'Cleanup List' are removed before
    scripts are called and if any of them happen to be required by
    the found par2 file, it will fail.
 3) If there are multiple larger (>40MB) files, then the script will not
    rename anything, since it could be a multi-pack.
 4) If you want to modify this script, make sure to copy it out
    of this directory, or it will be overwritten when SABnzbd is updated.
 5) Feedback or bugs in this script can be reported in on our forum:
    https://forums.sabnzbd.org/viewforum.php?f=9


Improved by P1nGu1n

"""

import os
import sys
import time
import fnmatch
import struct
import hashlib


# Are we being called from SABnzbd?
if not os.environ.get("SAB_VERSION"):
    print("This script needs to be called from SABnzbd as post-processing script.")
    sys.exit(1)


# Files to exclude and minimal file size for renaming
EXCLUDED_FILE_EXTS = (".vob", ".bin")
MIN_FILE_SIZE = 40 * 1024 * 1024

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


# Supporting functions
def print_splitter():
    """ Simple helper function """
    print("\n------------------------\n")


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
                print("File already exists: %s" % target_name)
                continue

            # find and rename file
            src_path = find_file(dirname, filelength, hash16k)
            if src_path is not None:
                os.rename(src_path, target_path)
                print("Renamed file from %s to %s" % (os.path.basename(src_path), target_name))
                result = True
            else:
                print("No match found for: %s" % target_name)
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


# Run main program
print_splitter()
print("SABnzbd version: ", os.environ["SAB_VERSION"])
print("Job location: ", os.environ["SAB_COMPLETE_DIR"])
print_splitter()

# Search for par2 files
matches = []
for root, dirnames, filenames in os.walk(os.environ["SAB_COMPLETE_DIR"]):
    for filename in fnmatch.filter(filenames, "*.par2"):
        matches.append(os.path.join(root, filename))
        print("Found file:", os.path.join(root, filename))

# Found any par2 files we can use?
run_renamer = True
if not matches:
    print("No par2 files found to process.")

# Run par2 from SABnzbd on them
for par2_file in matches:
    # Analyse data and analyse result
    print_splitter()
    if decode_par2(par2_file):
        print("Recursive repair/verify finished.")
        run_renamer = False
    else:
        print("Recursive repair/verify did not complete!")

# No matches? Then we try to rename the largest file to the job-name
if run_renamer:
    print_splitter()
    print("Trying to see if there are large files to rename")
    print_splitter()

    # If there are more larger files, we don't rename
    largest_file = None
    for root, dirnames, filenames in os.walk(os.environ["SAB_COMPLETE_DIR"]):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            file_size = os.path.getsize(full_path)
            # Do we count this file?
            if file_size > MIN_FILE_SIZE and os.path.splitext(filename)[1].lower() not in EXCLUDED_FILE_EXTS:
                # Did we already found one?
                if largest_file:
                    print("Found:", largest_file)
                    print("Found:", full_path)
                    print_splitter()
                    print("Found multiple larger files, aborting.")
                    largest_file = None
                    break
                largest_file = full_path

    # Found something large enough?
    if largest_file:
        # We don't need to do any cleaning of dir-names
        # since SABnzbd already did that!
        new_name = "%s%s" % (
            os.path.join(os.environ["SAB_COMPLETE_DIR"], os.environ["SAB_FINAL_NAME"]),
            os.path.splitext(largest_file)[1].lower(),
        )
        print("Renaming %s to %s" % (largest_file, new_name))

        # With retries for Windows
        for r in range(3):
            try:
                os.rename(largest_file, new_name)
                print("Renaming done!")
                break
            except:
                time.sleep(1)
    else:
        print("No par2 files or large files found")

# Always exit with success-code
sys.exit(0)
