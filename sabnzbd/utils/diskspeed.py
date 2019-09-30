#!/usr/bin/env python3

import time
import os
import sys

_DUMP_DATA_SIZE = 10 * 1024 * 1024
_DUMP_DATA = os.urandom(_DUMP_DATA_SIZE)


def diskspeedmeasure(dirname):
    """ Returns writing speed to dirname in MB/s
        method: keep writing a file, until 1 second is passed.
        Then divide bytes written by time passed
        In case of problems (ie non-writable dir or file), return None
    """
    maxtime = 1.0  # sec
    total_written = 0
    filename = os.path.join(dirname, "outputTESTING.txt")

    try:
        # Use low-level I/O
        fp = os.open(filename, os.O_CREAT | os.O_WRONLY, 0o777)

        # Start looping
        total_time = 0.0
        while total_time < maxtime:
            start = time.time()
            os.write(fp, _DUMP_DATA)
            os.fsync(fp)
            total_time += time.time() - start
            total_written += _DUMP_DATA_SIZE

        # Remove the file
        try:
            # Have to use low-level close
            os.close(fp)
            os.remove(filename)
        except OSError:
            pass
    except OSError:
        # No succesful measurement, so ... report None
        return None

    return total_written / total_time / 1024 / 1024


if __name__ == "__main__":

    print("Let's go")

    if len(sys.argv) >= 2:
        directoryname = sys.argv[1]
        if not os.path.isdir(directoryname):
            print("Specified argument is not a directory. Bailing out")
            sys.exit(1)
    else:
        # no argument, so use current working directory
        directoryname = os.getcwd()
        print("Using current working directory")

    try:
        speed = diskspeedmeasure(directoryname)
        if speed:
            print("Disk writing speed: {:.2f} Mbytes per second".format(speed))
        else:
            print("No measurement possible. Check that directory is writable.")
    except OSError:
        print("Something went wrong. I don't know what")
        raise

    print("Done")
