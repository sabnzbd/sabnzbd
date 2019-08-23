#!/usr/bin/python3 -OO
# Copyright 2009-2019 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.utils.rarvolnum - Find out volume number of a rar file. Useful with obfuscated files
"""

import os
import sabnzbd.utils.rarfile as rarfile


def get_rar_volume_number(myrarfile):
    """
    Find out volume number of a rar file. Returns < 0 in case of file problems
    """
    volumenumber = -1  # default aka something bad

    if not os.path.isfile(myrarfile):
        return volumenumber

    try:
        rar_ver = rarfile.is_rarfile(myrarfile)
        with open(myrarfile, "rb") as fh:
            if rar_ver.endswith("3"):
                # At the end of the file, we need about 20 bytes
                fh.seek(-20, os.SEEK_END)
                mybuf = fh.read()
                volumenumber = 1 + mybuf[-9] + 256 * mybuf[-8]

            elif rar_ver.endswith("5"):
                mybuf = fh.read(100)  # first 100 bytes is enough

                # Get (and skip) the first 8 + 4 bytes
                rar5sig, newpos = rarfile.load_bytes(mybuf, 8, 0)  # Rar5 signature
                crc32, newpos = rarfile.load_bytes(mybuf, 4, newpos)  # crc32

                # Then get the VINT values (with variable size, so parse them all):
                headersize, newpos = rarfile.load_vint(mybuf, newpos)
                headertype, newpos = rarfile.load_vint(mybuf, newpos)
                headerflags, newpos = rarfile.load_vint(mybuf, newpos)
                extraareasize, newpos = rarfile.load_vint(mybuf, newpos)
                archiveflags, newpos = rarfile.load_vint(mybuf, newpos)

                # Now we're ready for the volume number:
                if archiveflags & 2:
                    value, newpos = rarfile.load_vint(mybuf, newpos)
                    volumenumber = value + 1
                else:
                    # first volume, aka 1
                    volumenumber = 1
    except:
        volumenumber = -2
        pass

    return volumenumber
