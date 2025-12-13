#!/usr/bin/env python3

import sys, os, glob
from pathlib import Path

"""
Priority
-100 = Default
-2 = Paused
-1 = Low .... # mkv without subs
0 = Normal ... # other filetypes
1 = High .... # mkv with subs
2 = Force
"""


def get_biggest_file_in_dir(directory: str):
    """Return the biggest file in a directory"""
    # pattern = os.path.join(directory, "**/*")
    # all_files = [path for path in glob.glob(pattern, recursive=True) if os.path.isfile(path)]
    # glob has problems with special characters like "[" and "]", so use pathlib
    target_dir = Path(directory)
    all_files = [f for f in target_dir.iterdir() if f.is_file()]
    if not all_files:
        return None, 0
    all_files = sorted(all_files, key=os.path.getsize)[::-1]  # reversed, so big to small. Format [start:stop:step]
    return all_files[0], os.path.getsize(all_files[0])




def file_has_text(myfile, mystring) -> bool:
    """Check if a file has a specific string in first 10_000 bytes.
    Return True if found, False otherwise
    """

    # convert mystring to bytes
    mystring = mystring.encode("utf-8")


    # read first 10_000 bytes of the file, and count the number of occurences of "S_TEXT/UTF8" or "S_TEXT/ASS"
    try:
        with open(myfile, "rb") as f:
            data = f.read(10_000)
            # does data contain the string?
            if mystring in data:
                return True
            else:
                return False
    except Exception as e:
            return False



# MAIN

try:
    # Parse the input variables for SABnzbd version >= 4.2.0
    (scriptname, dirname) = sys.argv  # we only need dirname
except Exception:
    print("specificy dirname!!!")
    sys.exit(1)  # a non-zero exit status causes SABnzbd to ignore the output of this script




# check if dirname exists
if not os.path.exists(dirname):
    print(f"Directory {dirname} does not exist!")
    sys.exit(1)

biggest_file, _ = get_biggest_file_in_dir(dirname)

if biggest_file is None:
    print(f"No files found in directory {dirname}")
    sys.exit(0)


prio = 0  # default priority

if file_has_text(biggest_file, "YESYESYES"):
    prio = 1  # High
else:
    prio = -1  # Low


# same output as SABnzbd pre-queue script:

print("1")  # Accept the job
print() #f"my result for dirname {dirname} is ... {biggest_file}")  # "job name" ...
print()
print()
print()
print(prio)  # Priority
print()

# 0 means OK
sys.exit(0)
