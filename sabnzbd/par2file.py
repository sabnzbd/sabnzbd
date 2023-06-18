#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.par2file - All par2-related functionality
"""
import hashlib
import logging
import os
import re
import struct
import sabctools
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from sabnzbd.constants import MEBI
from sabnzbd.encoding import correct_unknown_encoding

PROBABLY_PAR2_RE = re.compile(r"(.*)\.vol(\d*)[+\-](\d*)\.par2", re.I)
SCAN_LIMIT = 10 * MEBI
PAR_PKT_ID = b"PAR2\x00PKT"
PAR_MAIN_ID = b"PAR 2.0\x00Main\x00\x00\x00\x00"
PAR_FILE_ID = b"PAR 2.0\x00FileDesc"
PAR_CREATOR_ID = b"PAR 2.0\x00Creator\x00"
PAR_SLICE_ID = b"PAR 2.0\x00IFSC\x00\x00\x00\x00"
PAR_RECOVERY_ID = b"RecvSlic"


@dataclass
class FilePar2Info:
    """Class for keeping track of par2 information of a file"""

    filename: str
    hash16k: bytes
    filesize: int
    filehash: Optional[int] = None
    has_duplicate: bool = False


def is_parfile(filename: str) -> bool:
    """Check quickly whether file has par2 signature
    or if the filename has '.par2' in it
    """
    if os.path.exists(filename):
        try:
            with open(filename, "rb") as f:
                buf = f.read(8)
                return buf.startswith(PAR_PKT_ID)
        except:
            pass
    elif ".par2" in filename.lower():
        return True
    return False


def analyse_par2(name: str, filepath: Optional[str] = None) -> Tuple[str, int, int]:
    """Check if file is a par2-file and determine vol/block
    return setname, vol, block
    setname is empty when not a par2 file
    """
    name = name.strip()
    vol = block = 0
    if m := PROBABLY_PAR2_RE.search(name):
        setname = m.group(1)
        vol = m.group(2)
        block = m.group(3)
    else:
        # Base-par2 file
        setname = os.path.splitext(name)[0].strip()
        # Could not parse the filename, need deep inspection
        # We already know it's a par2 from the is_parfile
        if filepath:
            try:
                # Quick loop to find number blocks
                # Assumes blocks are larger than 128 bytes
                # Worst case, we only count 1, still good
                with open(filepath, "rb") as f:
                    buf = f.read(128)
                    while buf:
                        if PAR_RECOVERY_ID in buf:
                            block += 1
                        buf = f.read(128)
            except:
                pass
    return setname, vol, block


def parse_par2_file(fname: str, md5of16k: Dict[bytes, str]) -> Tuple[str, Dict[str, FilePar2Info]]:
    """Get the hash table and the first-16k hash table from a PAR2 file
    Return as dictionary, indexed on names or hashes for the first-16 table
    The input md5of16k is modified in place and thus not returned!

    Note that par2 can and will appear in random order, so the code has to collect data first
    before we process them!

    For a full description of the par2 specification, visit:
    http://parchive.sourceforge.net/docs/specifications/parity-volume-spec/article-spec.html
    """
    set_id = slice_size = coeff = nr_files = None
    filepar2info = {}
    filecrc32 = {}
    table = {}
    duplicates16k = []

    try:
        total_size = os.path.getsize(fname)
        with open(fname, "rb") as f:
            while header := f.read(8):
                if header == PAR_PKT_ID:
                    # All packages start with a header before the body
                    # 8	  : PAR2\x00PKT
                    # 8	  : Length of the entire packet. Must be multiple of 4. (NB: Includes length of header.)
                    # 16  : MD5 Hash of packet.
                    # 16  : Recovery Set ID.
                    # 16  : Type of packet.
                    # ?*4 : Body of Packet. Must be a multiple of 4 bytes.

                    # Length must be multiple of 4 and at least 20
                    pack_len = struct.unpack("<Q", f.read(8))[0]
                    if int(pack_len / 4) * 4 != pack_len or pack_len < 20:
                        continue

                    # Next 16 bytes is md5sum of this packet
                    md5sum = f.read(16)

                    # Read and check the data
                    # Subtract 32 because we already read these bytes of the header
                    data = f.read(pack_len - 32)
                    if md5sum != hashlib.md5(data).digest():
                        continue

                    # See if it's any of the packages we care about
                    par2_packet_type = data[16:32]

                    # Get the Recovery Set ID
                    set_id = data[:16].hex()

                    if par2_packet_type == PAR_FILE_ID:
                        # The FileDesc packet looks like:
                        # 16 : "PAR 2.0\0FileDesc"
                        # 16 : FileId
                        # 16 : Hash for full file
                        # 16 : Hash for first 16K
                        #  8 : File length
                        # xx : Name (multiple of 4, padded with \0 if needed)

                        fileid = data[32:48].hex()
                        if filepar2info.get(fileid):
                            # Already have data
                            continue
                        hash16k = data[64:80]
                        filesize = struct.unpack("<Q", data[80:88])[0]
                        filename = correct_unknown_encoding(data[88:].strip(b"\0"))
                        filepar2info[fileid] = FilePar2Info(filename, hash16k, filesize)
                    elif par2_packet_type == PAR_CREATOR_ID:
                        # From here until the end is the creator-text
                        # Useful in case of bugs in the par2-creating software
                        # "PAR 2.0\x00Creator\x00"
                        par2creator = data[32:].strip(b"\0")  # Remove any trailing \0
                        logging.debug(
                            "Par2-creator of %s is: %s", os.path.basename(f.name), correct_unknown_encoding(par2creator)
                        )
                    elif par2_packet_type == PAR_MAIN_ID:
                        # The Main packet looks like:
                        # 16 : "PAR 2.0\0Main"
                        # 8  : Slice size
                        # 4  : Number of files in the recovery set
                        slice_size = struct.unpack("<Q", data[32:40])[0]
                        coeff = sabctools.crc32_xpow8n(slice_size)
                        nr_files = struct.unpack("<I", data[40:44])[0]
                    elif par2_packet_type == PAR_SLICE_ID:
                        # "PAR 2.0\0IFSC\0\0\0\0"
                        fileid = data[32:48].hex()
                        if not filecrc32.get(fileid):
                            filecrc32[fileid] = []
                            for i in range(48, pack_len - 32, 20):
                                filecrc32[fileid].append(struct.unpack("<I", data[i + 16 : i + 20])[0])

                    # On large files, we stop after seeing all the listings
                    # On smaller files, we scan them fully to get the par2-creator
                    if total_size > SCAN_LIMIT and len(filepar2info) == nr_files:
                        break

            # Process all the data
            for fileid in filepar2info.keys():
                # Sanity check
                par2info = filepar2info[fileid]
                if not filecrc32.get(fileid) or not nr_files or not slice_size:
                    logging.debug("Missing essential information for %s", par2info)
                    continue

                # Handle also cases where slice_size is exact match for filesize
                # We currently don't have an unittest for that!
                slices = par2info.filesize // slice_size
                slice_nr = 0
                crc32 = 0
                while slice_nr < slices:
                    crc32 = sabctools.crc32_multiply(crc32, coeff) ^ filecrc32[fileid][slice_nr]
                    slice_nr += 1

                if tail_size := par2info.filesize % slice_size:
                    crc32 = sabctools.crc32_combine(
                        crc32, sabctools.crc32_zero_unpad(filecrc32[fileid][-1], slice_size - tail_size), tail_size
                    )
                par2info.filehash = crc32

                # We found hash data, add it to final tabel
                table[par2info.filename] = par2info

                # Check for md5of16k duplicates
                if par2info.hash16k not in md5of16k:
                    md5of16k[par2info.hash16k] = par2info.filename
                elif md5of16k[par2info.hash16k] != par2info.filename:
                    # Not unique and not already linked to this file
                    # Mark and remove to avoid false-renames
                    duplicates16k.append(par2info.hash16k)
                    table[par2info.filename].has_duplicate = True

    except Exception as e:
        logging.info("Par2 parser crashed in file %s", fname)
        logging.debug("Traceback: ", exc_info=True)
        table = {}
        set_id = None

    # Have to remove duplicates at the end to make sure
    # no trace is left in case of multi-duplicates
    for hash16k in duplicates16k:
        if hash16k in md5of16k:
            old_name = md5of16k.pop(hash16k)
            logging.debug("Par2-16k signature of %s not unique, discarding", old_name)

    return set_id, table
