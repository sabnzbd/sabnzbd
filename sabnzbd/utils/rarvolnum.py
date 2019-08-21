#!/usr/bin/env python3
# Find out volume number of a rar file. Useful with obfuscated files
# Works with python 2.7 too

import os
import sabnzbd.utils.rarfile as rarfile


def get_volume_number(myrarfile):
    """Find out volume number of a rar file. Returns < 0 in case of file problems
    """
    volumenumber = -1  # default aka something bad

    if not os.path.isfile(myrarfile):
        return volumenumber

    try:
        rar_ver = rarfile._get_rar_version(myrarfile)  # ... or rarfile.is_rarfile(myrarfile))
        with open(myrarfile, "rb") as fh:
            if rar_ver == 3:
                # At the end of the file, we need about 20 bytes
                fh.seek(-20, os.SEEK_END)
                mybuf = fh.read()
                volumenumber = 1 + mybuf[-9] + 256 * mybuf[-8]

            elif rar_ver == 5:
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
