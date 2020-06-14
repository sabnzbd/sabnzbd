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
sabnzbd.par2file - All par2-related functionality
"""
import os
import logging
import re
import hashlib
import struct
from sabnzbd.encoding import correct_unknown_encoding

PROBABLY_PAR2_RE = re.compile(r"(.*)\.vol(\d*)[\+\-](\d*)\.par2", re.I)
PAR_PKT_ID = b"PAR2\x00PKT"
PAR_FILE_ID = b"PAR 2.0\x00FileDesc"
PAR_CREATOR_ID = b"PAR 2.0\x00Creator"
PAR_RECOVERY_ID = b"RecvSlic"


def is_parfile(filename):
    """ Check quickly whether file has par2 signature """
    try:
        with open(filename, "rb") as f:
            buf = f.read(8)
            return buf.startswith(PAR_PKT_ID)
    except:
        pass
    return False


def analyse_par2(name, filepath=None):
    """ Check if file is a par2-file and determine vol/block
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


def parse_par2_file(nzf, fname):
    """ Get the hash table and the first-16k hash table from a PAR2 file
        Return as dictionary, indexed on names or hashes for the first-16 table
        For a full description of the par2 specification, visit:
        http://parchive.sourceforge.net/docs/specifications/parity-volume-spec/article-spec.html
    """
    table = {}
    duplicates16k = []

    try:
        with open(fname, "rb") as f:
            header = f.read(8)
            while header:
                name, filehash, hash16k = parse_par2_file_packet(f, header)
                if name:
                    table[name] = filehash
                    if hash16k not in nzf.nzo.md5of16k:
                        nzf.nzo.md5of16k[hash16k] = name
                    elif nzf.nzo.md5of16k[hash16k] != name:
                        # Not unique and not already linked to this file
                        # Remove to avoid false-renames
                        duplicates16k.append(hash16k)

                header = f.read(8)

    except (struct.error, IndexError):
        logging.info('Cannot use corrupt par2 file for QuickCheck, "%s"', fname)
        logging.debug("Traceback: ", exc_info=True)
        table = {}
    except:
        logging.info("QuickCheck parser crashed in file %s", fname)
        logging.debug("Traceback: ", exc_info=True)
        table = {}

    # Have to remove duplicates at the end to make sure
    # no trace is left in case of multi-duplicates
    for hash16k in duplicates16k:
        if hash16k in nzf.nzo.md5of16k:
            old_name = nzf.nzo.md5of16k.pop(hash16k)
            logging.debug("Par2-16k signature of %s not unique, discarding", old_name)

    return table


def parse_par2_file_packet(f, header):
    """ Look up and analyze a FileDesc package """

    nothing = None, None, None

    if header != PAR_PKT_ID:
        return nothing

    # Length must be multiple of 4 and at least 20
    pack_len = struct.unpack("<Q", f.read(8))[0]
    if int(pack_len / 4) * 4 != pack_len or pack_len < 20:
        return nothing

    # Next 16 bytes is md5sum of this packet
    md5sum = f.read(16)

    # Read and check the data
    data = f.read(pack_len - 32)
    md5 = hashlib.md5()
    md5.update(data)
    if md5sum != md5.digest():
        return nothing

    # The FileDesc packet looks like:
    # 16 : "PAR 2.0\0FileDesc"
    # 16 : FileId
    # 16 : Hash for full file **
    # 16 : Hash for first 16K
    #  8 : File length
    # xx : Name (multiple of 4, padded with \0 if needed) **

    # See if it's the right packet and get name + hash
    for offset in range(0, pack_len, 8):
        if data[offset : offset + 16] == PAR_FILE_ID:
            filehash = data[offset + 32 : offset + 48]
            hash16k = data[offset + 48 : offset + 64]
            filename = correct_unknown_encoding(data[offset + 72 :].strip(b"\0"))
            return filename, filehash, hash16k
        elif data[offset : offset + 15] == PAR_CREATOR_ID:
            # From here until the end is the creator-text
            # Useful in case of bugs in the par2-creating software
            par2creator = data[offset + 16 :].strip(b"\0")  # Remove any trailing \0
            logging.debug("Par2-creator of %s is: %s", os.path.basename(f.name), correct_unknown_encoding(par2creator))

    return nothing
