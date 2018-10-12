#!/usr/bin/env python

"""
Functions to check if the path filesystem uses FAT
"""

import sys
import os

debug = False


def isFAT(dir):

# Check if "dir" is on FAT. FAT considered harmful (for big files)
# Works for Linux, Windows, MacOS
# NB: On Windows, full path with drive letter is needed!

    FAT = False    # default: not FAT
    # We're dealing with OS calls, so put everything in a try/except, just in case:
    try:
        if 'linux' in sys.platform:
            # On Linux:
            # df -T /home/sander/weg

            '''
            Example output of a 500GB external USB drive formatted with FAT:
            $ df -T /media/sander/INTENSO
            Filesystem     Type 1K-blocks      Used Available Use% Mounted on
            /dev/sda1      vfat 488263616 163545248 324718368  34% /media/sander/INTENSO
            '''

            cmd = "df -T " + dir + " 2>&1"
            for thisline in os.popen(cmd).readlines():
                #print thisline
                if thisline.find('/') == 0:
                    # Starts with /, so a real, local device
                    fstype = thisline.split()[1]
                    if debug: print(("File system type:", fstype))
                    if fstype.lower().find('fat') >= 0:
                        FAT = True
                        if debug: print("FAT found")
                        break
        elif 'win32' in sys.platform:
            import win32api
            if '?' in dir:
                #  Remove \\?\ or \\?\UNC\ prefix from Windows path
                dir = dir.replace('\\\\?\\UNC\\', '\\\\', 1).replace('\\\\?\\', '', 1)
            try:
                result = win32api.GetVolumeInformation(os.path.splitdrive(dir)[0])
                if debug: print(result)
                if(result[4].startswith("FAT")):
                    FAT = True
            except:
                pass
        elif 'darwin' in sys.platform:
            # MacOS formerly known as OSX
            '''
            MacOS needs a two-step approach:
            
            # First: directory => device
            server:~ sander$ df /Volumes/CARTUNES/Tuna/
            Filesystem   512-blocks      Used Available Capacity iused ifree %iused  Mounted on
            /dev/disk9s1  120815744 108840000  11975744    91%       0     0  100%   /Volumes/CARTUNES
            
            # Then: device => filesystem type
            server:~ sander$ mount | grep /dev/disk9s1
            /dev/disk9s1 on /Volumes/CARTUNES (msdos, local, nodev, nosuid, noowners)


            '''
            dfcmd = "df " + dir
            for thisline in os.popen(dfcmd).readlines():
                if thisline.find('/')==0:
                    if debug: print(thisline)
                    # Starts with /, so a real, local device
                    device = thisline.split()[0]
                    mountcmd = "mount | grep " + device
                    mountoutput = os.popen(mountcmd).readline().strip()
                    if debug: print(mountoutput)
                    if 'msdos' in mountoutput.split('(')[1]:
                        FAT = True
                    break

    except:
        pass
    return FAT



if __name__ == "__main__":
    if debug: print((sys.platform))
    try:
        dir = sys.argv[1]
    except:
        print("Specify dir on the command line")
        sys.exit(0)
    if isFAT(dir):
        print((dir, "is on FAT"))
    else:
        print((dir, "is not on FAT"))


