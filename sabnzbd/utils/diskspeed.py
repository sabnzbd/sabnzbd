#!/usr/bin/env python

import time
import os
import sys
import logging

_DUMP_DATA = '*' * 10000

def writetofile(filename, mysizeMB):
    # writes string to specified file repeat delay, until mysizeMB is reached.
    writeloops = int(1024 * 1024 * mysizeMB / len(_DUMP_DATA))
    try:
        f = open(filename, 'w')
    except:
        logging.debug('Cannot create file %s', filename)
        logging.debug("Traceback: ", exc_info=True)
        return False

    try:
        for x in xrange(writeloops):
            f.write(_DUMP_DATA)
    except:
        logging.debug('Cannot write to file %s', filename)
        logging.debug("Traceback: ", exc_info=True)
        return False
    f.close()
    return True


def diskspeedmeasure(dirname):
    # returns writing speed to dirname in MB/s
    # method: keep writing a file, until 0.5 seconds is passed. Then divide bytes written by time passed
    filesize = 10  # MB
    maxtime = 0.5  # sec
    filename = os.path.join(dirname, 'outputTESTING.txt')

    if os.name == 'nt':
        # On Windows, this crazy action is needed to
        # avoid a "permission denied" error
        try:
            os.system('echo Hi >%s' % filename)
        except:
            pass

    start = time.time()
    loopcounter = 0
    while True:
        if not writetofile(filename, filesize):
            return 0
        loopcounter += 1
        diff = time.time() - start
        if diff > maxtime:
            break
    try:
        os.remove(filename)
    except:
        pass
    return (loopcounter * filesize) / diff


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
        print("Disk writing speed: %.2f Mbytes per second" % speed)
    except IOError, e:
        # print "IOError:", e
        if e.errno == 13:
            print "Could not create test file. Check that you have write rights to directory", dirname
    except:
        print "Something else went wrong"
        raise

    print "Done"
