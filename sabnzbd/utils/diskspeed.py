#!/usr/bin/env python

import time
import os
import sys

_DUMP_DATA_SIZE = 10 * 1024 * 1024
_DUMP_DATA = os.urandom(_DUMP_DATA_SIZE)


def diskspeedmeasure(dirname):
    """ Returns writing speed to dirname in MB/s
        method: keep writing a file, until 1 second is passed.
        Then divide bytes written by time passed
    """
    maxtime = 1.0  # sec
    total_written = 0
    filename = os.path.join(dirname, 'outputTESTING.txt')

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
    except:
        pass

    return total_written / total_time / 1024 / 1024

if __name__ == "__main__":

    print "Let's go"

    if len(sys.argv) >= 2:
        dirname = sys.argv[1]
        if not os.path.isdir(dirname):
            print "Specified argument is not a directory. Bailing out"
            sys.exit(1)
    else:
        # no argument, so use current working directory
        dirname = os.getcwd()
        print "Using current working directory"

    try:
        speed = diskspeedmeasure(dirname)
        print "Disk writing speed: %.2f Mbytes per second" % speed
    except IOError, e:
        # print "IOError:", e
        if e.errno == 13:
            print "Could not create test file. Check that you have write rights to directory", dirname
    except:
        print "Something else went wrong"
        raise

    print "Done"
