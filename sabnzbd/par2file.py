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
sabnzbd.par2file - All par2-related functionality
"""
import hashlib
import logging
import os
import re
import struct
from typing import Dict, Optional, Tuple, BinaryIO

from sabnzbd.constants import MEBI
from sabnzbd.encoding import correct_unknown_encoding

PROBABLY_PAR2_RE = re.compile(r"(.*)\.vol(\d*)[+\-](\d*)\.par2", re.I)
SCAN_LIMIT = 10 * MEBI
PAR_PKT_ID = b"PAR2\x00PKT"
PAR_MAIN_ID = b"PAR 2.0\x00Main\x00\x00\x00\x00"
PAR_FILE_ID = b"PAR 2.0\x00FileDesc"
PAR_CREATOR_ID = b"PAR 2.0\x00Creator\x00"
PAR_RECOVERY_ID = b"RecvSlic"


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
    m = PROBABLY_PAR2_RE.search(name)
    if m:
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


def parse_par2_file(fname: str, md5of16k: Dict[bytes, str]) -> Tuple[str, Dict[str, Tuple[bytes, bytes]]]:
    """Get the hash table and the first-16k hash table from a PAR2 file
    Return as dictionary, indexed on names or hashes for the first-16 table
    The input md5of16k is modified in place and thus not returned!

    For a full description of the par2 specification, visit:
    http://parchive.sourceforge.net/docs/specifications/parity-volume-spec/article-spec.html
    """
    total_size = os.path.getsize(fname)
    table = {}
    duplicates16k = []
    total_nr_files = None

    try:
        with open(fname, "rb") as f:
            header = f.read(8)
            while header:
                if header == PAR_PKT_ID:
                    name, filehash, hash16k, set_id, nr_files = parse_par2_packet(f)
                    if name:
                        table[name] = (hash16k, filehash)
                        if hash16k not in md5of16k:
                            md5of16k[hash16k] = name
                        elif md5of16k[hash16k] != name:
                            # Not unique and not already linked to this file
                            # Remove to avoid false-renames
                            duplicates16k.append(hash16k)

                    # Store the number of files for later
                    if nr_files:
                        total_nr_files = nr_files

                    # On large files, we stop after seeing all the listings
                    # On smaller files, we scan them fully to get the par2-creator
                    if total_size > SCAN_LIMIT and len(table) == total_nr_files:
                        break

                header = f.read(8)
    except:
        logging.info("Par2 parser crashed in file %s", fname)
        logging.debug("Traceback: ", exc_info=True)
        table = {}

    # Have to remove duplicates at the end to make sure
    # no trace is left in case of multi-duplicates
    for hash16k in duplicates16k:
        if hash16k in md5of16k:
            old_name = md5of16k.pop(hash16k)
            logging.debug("Par2-16k signature of %s not unique, discarding", old_name)

    return set_id, table


def parse_par2_packet(
    f: BinaryIO,
) -> Tuple[Optional[str], Optional[bytes], Optional[bytes], Optional[str], Optional[int]]:
    """Look up and analyze a PAR2 packet"""

    filename, filehash, hash16k, set_id, nr_files = nothing = None, None, None, None, None

    # All packages start with a header before the body
    # 8	  : PAR2\x00PKT
    # 8	  : Length of the entire packet. Must be multiple of 4. (NB: Includes length of header.)
    # 16  : MD5 Hash of packet. Calculation starts at first byte of Recovery Set ID and ends at last byte of body.
    # 16  : Recovery Set ID.
    # 16  : Type of packet.
    # ?*4 : Body of Packet. Must be a multiple of 4 bytes.

    # Length must be multiple of 4 and at least 20
    pack_len = struct.unpack("<Q", f.read(8))[0]
    if int(pack_len / 4) * 4 != pack_len or pack_len < 20:
        return nothing

    # Next 16 bytes is md5sum of this packet
    md5sum = f.read(16)

    # Read and check the data
    # Subtract 32 because we already read these bytes of the header
    data = f.read(pack_len - 32)
    md5 = hashlib.md5()
    md5.update(data)
    if md5sum != md5.digest():
        return nothing

    # Get the Recovery Set ID
    set_id = data[:16].hex()

    # See if it's any of the packages we care about
    par2_packet_type = data[16:32]

    if par2_packet_type == PAR_FILE_ID:
        # The FileDesc packet looks like:
        # 16 : "PAR 2.0\0FileDesc"
        # 16 : FileId
        # 16 : Hash for full file
        # 16 : Hash for first 16K
        #  8 : File length
        # xx : Name (multiple of 4, padded with \0 if needed)
        filehash = data[48:64]
        hash16k = data[64:80]
        filename = correct_unknown_encoding(data[88:].strip(b"\0"))
    elif par2_packet_type == PAR_CREATOR_ID:
        # From here until the end is the creator-text
        # Useful in case of bugs in the par2-creating software
        par2creator = data[32:].strip(b"\0")  # Remove any trailing \0
        logging.debug("Par2-creator of %s is: %s", os.path.basename(f.name), correct_unknown_encoding(par2creator))
    elif par2_packet_type == PAR_MAIN_ID:
        # The Main packet looks like:
        # 16 : "PAR 2.0\0Main"
        # 8  : Slice size
        # 4  : Number of files in the recovery set
        nr_files = struct.unpack("<I", data[40:44])[0]

    return filename, filehash, hash16k, set_id, nr_files
