#!/usr/bin/env python
# Example Post-Processing Script for SABnzbd (3.0.0 and higher), written in Python.
# For Linux, MacOS, Windows and any other platform with Python
# See https://sabnzbd.org/wiki/scripts/post-processing-scripts for details
#
# Example test run on Linux:
# env SAB_VERSION=X.Y SAB_AVG_BPS=666 python ./Sample-PostProc.py somedir222 nzbname CleanJobName123 Index12 Cat88 MyGroup PP0 https://example.com/

import sys, os

# Raw parsing of input parameters en SABnzbd environment variables
counter = 0
print("INPUT from argv:")
for item in sys.argv:
    print("Argument", counter, ":", item)
    counter += 1

print("INPUT from environment variables (only SAB specifics):")
for item in os.environ:
    if item.find("SAB_") == 0:
        print(item, os.environ[item])

# More intelligent parsing:
try:
    (scriptname, directory, orgnzbname, jobname, reportnumber, category, group, postprocstatus, url) = sys.argv
except:
    print("No SAB compliant number of commandline parameters found (should be 8):", len(sys.argv) - 1)
    sys.exit(1)  # non-zero return code

# Some examples:
print("Examples of some specific values:")
print("jobname is:", jobname)
try:
    sabversion = os.environ["SAB_VERSION"]
    print("SAB_VERSION is:", sabversion)
except:
    pass

""" your code here """

# We're done:
print("Script done. All OK.")  # the last line will appear in the SABnzb History GUI
sys.exit(0)  # The result code towards SABnzbd
