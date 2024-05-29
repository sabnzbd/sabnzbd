#!/usr/bin/python3

"""
Functions to check if the path filesystem uses FAT
"""

import sys
import os
import subprocess
from typing import List


def getcmdoutput(cmd: List[str]) -> List[str]:
    """execute cmd, and return a list of output lines"""
    subprocess_kwargs = {
        "bufsize": 0,
        "shell": False,
        "text": True,
        "encoding": "utf8",
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }
    return subprocess.run(cmd, **subprocess_kwargs).stdout.splitlines()


def isFAT(check_dir: str) -> bool:
    """Check if the given directory is on FAT, which has a maximum file size of only 4 GiB.
    Works for Linux, Windows, MacOS; on Windows, a full path with drive letter is needed!
    """
    if not (os.path.isdir(check_dir) or os.path.isfile(check_dir)):
        # Not a dir, not a file ... so not FAT:
        return False

    FAT = False  # default: not FAT
    # We're dealing with OS calls, so put everything in a try/except, just in case:
    try:
        if "linux" in sys.platform:
            """
            Example output of a 500GB external USB drive formatted with FAT:
            $ df -T /media/sander/INTENSO
            Filesystem     Type 1K-blocks      Used Available Use% Mounted on
            /dev/sda1      vfat 488263616 163545248 324718368  34% /media/sander/INTENSO
            """

            for thisline in getcmdoutput(["df", "-T", check_dir]):
                if thisline.find("/") == 0:
                    # Starts with /, so a real, local device
                    fstype = thisline.split()[1]
                    if fstype.lower().find("fat") >= 0 and fstype.lower().find("exfat") < 0:
                        # FAT, but not EXFAT
                        FAT = True
                        break
        elif "win32" in sys.platform:
            import win32api

            if "?" in check_dir:
                #  Remove \\?\ or \\?\UNC\ prefix from Windows path
                check_dir = check_dir.replace("\\\\?\\UNC\\", "\\\\", 1).replace("\\\\?\\", "", 1)
            try:
                result = win32api.GetVolumeInformation(os.path.splitdrive(check_dir)[0])
                if result[4].startswith("FAT"):
                    FAT = True
            except Exception:
                pass
        elif "darwin" in sys.platform:
            """
            MacOS needs a two-step approach:

            # First: directory => device
            server:~ sander$ df /Volumes/CARTUNES/Tuna/
            Filesystem   512-blocks      Used Available Capacity iused ifree %iused  Mounted on
            /dev/disk9s1  120815744 108840000  11975744    91%       0     0  100%   /Volumes/CARTUNES

            # Then: device => filesystem type
            server:~ sander$ mount | grep /dev/disk9s1
            /dev/disk9s1 on /Volumes/CARTUNES (msdos, local, nodev, nosuid, noowners)
            """
            for thisline in getcmdoutput(["df", check_dir]):
                if thisline.find("/") == 0:
                    # Starts with /, so a real, local device
                    device = thisline.split()[0]

                    # Run the equivalent of "mount | grep $device"
                    p_mount = subprocess.Popen(["mount"], stdout=subprocess.PIPE)
                    p_grep = subprocess.Popen(
                        ["grep", device + "[[:space:]]"], stdin=p_mount.stdout, stdout=subprocess.PIPE, text=True, encoding="utf8"
                    )
                    p_mount.stdout.close()
                    mountoutput = p_grep.communicate()[0].strip()

                    if "msdos" in mountoutput.split("(")[1]:
                        FAT = True
                    break

    except Exception:
        pass
    return FAT


if __name__ == "__main__":
    try:
        dir_to_check = sys.argv[1]
    except Exception:
        print("Specify dir on the command line")
        sys.exit(0)
    if isFAT(dir_to_check):
        print((dir_to_check, "is on FAT"))
    else:
        print((dir_to_check, "is not on FAT"))
