#!/usr/bin/python3
# Example Post-Processing Script for SABnzbd, written in Python.
# For Linux, MacOS, Windows and any other platform with Python
# See https://sabnzbd.org/wiki/scripts/post-processing-scripts for details
#
# All information is passed via SAB_* environment variables.
# Example test run on Linux:
# env SAB_VERSION=X.Y SAB_COMPLETE_DIR=somedir222 SAB_FINAL_NAME=CleanJobName123 SAB_PP_STATUS=0 python3 ./Sample-PostProc.py

import sys
import os

print("INPUT from environment variables (only SAB specifics):")
for item in os.environ:
    if item.startswith("SAB_"):
        print(item, os.environ[item])

# Some examples:
print("Examples of some specific values:")
print("Job name is:", os.environ.get("SAB_FINAL_NAME"))
print("Result directory is:", os.environ.get("SAB_COMPLETE_DIR"))
print("SAB_VERSION is:", os.environ.get("SAB_VERSION"))

""" your code here """

# We're done:
print("Script done. All OK.")  # the last line will appear in the SABnzb History GUI
sys.exit(0)  # The result code towards SABnzbd
