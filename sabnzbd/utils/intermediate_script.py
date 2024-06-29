#!/usr/bin/python3

"""
Handling of running an intermediate_script on a given directory

If that directory contains .rar files, those rar files are first unrarred

The given directory might contain partial files.

The intermediate_script itself should return the same parameters as a pre-queue script, with in position 6:

-100 = Default
-2 = Paused
-1 = Low
0 = Normal
1 = High
2 = Force

"""

import os
import logging

from sabnzbd.misc import build_and_run_command


def intermediate_script(script, directory):
    # run script on directory
    # returns the decision (=prio).
    # returns None if no decision

    # check if directory contains  *.rar files
    files = os.listdir(directory)
    rar_files = [file for file in files if file.endswith(".rar")]
    if rar_files:
        pass  # TODO fill out below
        # unpack rar files into a temp directory
        # create tempdir
        # unpack wild-card style *rar (?)
        directory = tempdir

    # OK, let's run the script on the given directory
    command = [script, directory]
    try:
        p = build_and_run_command(command)
    except:
        logging.debug("Failed script %s, Traceback: ", script_path, exc_info=True)
        return None  # TODO remove this line, and handle exception correctly

    output = p.stdout.read()
    ret = p.wait()
    logging.info("Intermediate script returned %s and output=\n%s", ret, output)
    if ret == 0:
        split_output = output.splitlines()
        # line #6 is the decision, so [5] in python speak
        decision = int(split_output[5])
        if decision != 0:
            # there was a decision, so use it!
            logging.debug("SJ decision %s", decision)
            return decision

    return None
