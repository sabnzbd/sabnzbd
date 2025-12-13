#!/usr/bin/env python3

import sys, os, glob
from pathlib import Path

"""
Output = Priority that SABnzbd will set for the job
-100 = Default
-2 = Paused
-1 = Low .... # mkv without subs
0 = Normal ... # other filetypes
1 = High .... # mkv with subs
2 = Force
"""

# MAIN

# get the directory name from command line arguments

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



prio = 0  # default priority
# check if dirname (aka nzb jobname) contains "lower" ignoring case
if dirname.lower().find("force") != -1:
    prio = 2  # Force
elif dirname.lower().find("high") != -1:
    prio = 1  # High
elif dirname.find("low") != -1:
    prio = -1  # Low

# same output as SABnzbd pre-queue script:

print("1")  # Accept the job
print()  # print(f"my result for dirname {dirname}") # "job name" ...
print()
print()
print()
print(prio)  # Priority
print()

# 0 means OK
sys.exit(0)
