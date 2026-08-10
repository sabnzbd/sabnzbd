#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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

import rarfile


def get_rar_extension(myrarfile: str) -> tuple[int, str]:
    """
    Find out original extension of a rar file. Returns -1 and "" in case of file problems
    So ... returns:     "part001.rar", ... "part005.rar"
    or old number scheme (can only happen for rar3/rar4 files): "rar", r00, ... r89
    """
    # When things go wrong
    volumenumber = -1
    org_extension = ""

    try:
        # Let the rarfile parser do the work and collect all header blocks it finds
        headers = []
        rarfile.RarFile(myrarfile, part_only=True, info_callback=headers.append)
        main = next(h for h in headers if h.type == rarfile.RAR_BLOCK_MAIN)

        if main.extract_version >= 50:
            # RAR5: volume number is in the main header, absent means first volume
            volumenumber = (main.main_volume_number or 0) + 1
            org_extension = "part%03d.rar" % volumenumber
        else:
            # RAR3/RAR4: volume number is in the end-of-archive block, if it's a multi-volume archive
            if main.flags & rarfile.RAR_MAIN_VOLUME:
                endarc = next(h for h in headers if h.type == rarfile.RAR_BLOCK_ENDARC)
                volumenumber = endarc.endarc_volnr + 1
            else:
                volumenumber = 1
            if main.flags & rarfile.RAR_MAIN_NEWNUMBERING:
                org_extension = "part%02d.rar" % volumenumber
            else:
                # 1, 2, 3, 4 resp refers to .rar, .r00, .r01, .r02 ...
                if volumenumber == 1:
                    org_extension = "rar"
                else:
                    org_extension = "r%02d" % (volumenumber - 2)
    except Exception:
        volumenumber = -1
        org_extension = ""

    return volumenumber, org_extension


# Main
if __name__ == "__main__":
    import sys

    try:
        myfile = sys.argv[1]
        print("File:", myfile)
        print("Volume and extension:", get_rar_extension(myfile))
    except Exception:
        print("Please specify rar file as parameter")
