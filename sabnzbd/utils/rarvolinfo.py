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
sabnzbd.utils.rarvolinfo - Find out volume number and/or original extension of a rar file. Useful with obfuscated files
"""


import os

try:
    import sabnzbd.utils.rarfile as rarfile
except:
    import rarfile


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


def int2zeropaddedstring(myint, digits=3):
    zeropaddedstring = ("0000" + str(myint))[-digits:]
    return zeropaddedstring


def get_rar_extension(myrarfile):
    """
    Find out orginal extension of a rar file. Returns "" in case of file problems
    So ... returns:     "part001.rar", ... "part005.rar" 
    or old number scheme (can only happen for rar3/rar4 files): "rar", r00, ... r89 
    """
    org_extension = ""  # default aka something bad

    if not os.path.isfile(myrarfile):
        return org_extension

    try:
        rar_ver = rarfile.is_rarfile(myrarfile)
        with open(myrarfile, "rb") as fh:
            if rar_ver.endswith("3"):
                # As it's rar3, let's first find the numbering scheme: old (rNNN) or new (partNNN.rar)
                mybuf = fh.read(100)  # first 100 bytes is enough
                HEAD_FLAGS_LSB = mybuf[10]  # LSB = Least Significant Byte
                newnumbering = HEAD_FLAGS_LSB & 0x10

                # For the volume number, At the end of the file, we need about 20 bytes
                fh.seek(-20, os.SEEK_END)
                mybuf = fh.read()
                volumenumber = 1 + mybuf[-9] + 256 * mybuf[-8]

                if newnumbering:
                    org_extension = "part" + int2zeropaddedstring(volumenumber) + ".rar"
                else:
                    # 1, 2, 3, 4 resp refers to .rar, .r00, .r01, .r02 ...
                    if volumenumber == 1:
                        org_extension = "rar"
                    else:
                        org_extension = "r" + int2zeropaddedstring(volumenumber - 2)

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

                # Combine into the extension
                org_extension = "part" + int2zeropaddedstring(volumenumber) + ".rar"
    except:
        org_extension = "exception"
        pass

    return org_extension


# Main
if __name__ == "__main__":
    import sys

    try:
        myfile = sys.argv[1]
        print("File:", myfile)
        print("Volume number:", get_rar_volume_number(myfile))
        print("Extension:", get_rar_extension(myfile))
    except:
        print("Please specify rar file as parameter")
