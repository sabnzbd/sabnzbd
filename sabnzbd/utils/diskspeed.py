#!/usr/bin/python3

"""Measure writing speed of disk specified (or working directory if not specified)"""

import os
import sys
import logging
import time

_DUMP_DATA_SIZE = 10 * 1024 * 1024


def diskspeedmeasure(dirname: str) -> float:
    """Returns writing speed to my_dirname in MB/s
    method: keep writing a file, until certain time is passed.
    Then divide bytes written by time passed
    In case of problems (ie non-writable dir or file), return 0.0
    """
    dump_data = os.urandom(_DUMP_DATA_SIZE)
    start = time.time()
    maxtime = 0.5  # sec
    total_written = 0
    filename = os.path.join(dirname, "outputTESTING.txt")

    try:
        # Use low-level I/O
        try:
            fp_testfile = os.open(filename, os.O_CREAT | os.O_WRONLY | os.O_BINARY, 0o777)
        except AttributeError:
            fp_testfile = os.open(filename, os.O_CREAT | os.O_WRONLY, 0o777)

        # Start looping
        total_time = 0.0
        while total_time < maxtime:
            start = time.time()
            os.write(fp_testfile, dump_data)
            os.fsync(fp_testfile)
            total_time += time.time() - start
            total_written += _DUMP_DATA_SIZE

        # Have to use low-level close
        os.close(fp_testfile)
        # Remove the file
        os.remove(filename)
    except OSError:
        # Could not write, so ... report 0.0
        logging.debug("Failed to measure disk speed on %s", dirname)
        return 0.0

    megabyte_per_second = round(total_written / total_time / 1024 / 1024, 1)
    logging.debug("Disk speed of %s = %.2f MB/s (in %.2f seconds)", dirname, megabyte_per_second, time.time() - start)
    return megabyte_per_second


if __name__ == "__main__":
    print("Let's go")

    if len(sys.argv) >= 2:
        DIRNAME = sys.argv[1]
        if not os.path.isdir(DIRNAME):
            print("Specified argument is not a directory. Bailing out")
            sys.exit(1)
    else:
        # no argument, so use current working directory
        DIRNAME = os.getcwd()
        print("Using current working directory")

    try:
        SPEED = max(diskspeedmeasure(DIRNAME), diskspeedmeasure(DIRNAME))
        if SPEED:
            print("Disk writing speed: %.2f Mbytes per second" % SPEED)
        else:
            print("No measurement possible. Check that directory is writable.")
    except:
        print("Something went wrong. I don't know what")
        raise

    print("Done")
