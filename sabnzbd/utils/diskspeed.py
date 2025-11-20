#!/usr/bin/python3

"""Measure writing speed of disk specified (or working directory if not specified)"""

import os
import sys
import logging
import time

BUFFERSIZE = 16 * 1024 * 1024


def diskspeedmeasure(dirname: str) -> float:
    """Returns writing speed to my_dirname in MB/s
    method: keep writing a file, until certain time is passed.
    Then divide bytes written by time passed
    In case of problems (ie non-writable dir or file), return 0.0
    """
    maxtime = 1  # sec
    total_written = 0
    filename = os.path.join(dirname, "outputTESTING.txt")

    # Prepare the whole buffer now for better write performance later
    # This is done before timing starts to exclude buffer creation from measurement
    buffer = os.urandom(BUFFERSIZE)

    try:
        # Use low-level I/O
        fp_testfile = os.open(
            filename,
            os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_SYNC", 0),
            0o777,
        )

        overall_start = time.perf_counter()
        maxtime = overall_start + 1
        total_time = 0.0

        # Start looping
        for i in range(1, 5):
            # Stop writing next buffer block, if time exceeds limit
            if time.perf_counter() >= maxtime:
                break
            # Prepare the data chunk outside of timing
            data_chunk = buffer * (i**2)

            # Only measure the actual write and sync operations
            write_start = time.perf_counter()
            total_written += os.write(fp_testfile, data_chunk)
            os.fsync(fp_testfile)
            total_time += time.perf_counter() - write_start

        # Have to use low-level close
        os.close(fp_testfile)
        # Remove the file
        os.remove(filename)

    except OSError:
        # Could not write, so ... report 0.0
        logging.debug("Failed to measure disk speed on %s", dirname)
        return 0.0

    megabyte_per_second = round(total_written / total_time / 1024 / 1024, 1)
    logging.debug(
        "Disk speed of %s = %.2f MB/s (in %.2f seconds)",
        dirname,
        megabyte_per_second,
        time.perf_counter() - overall_start,
    )
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
            print("Disk writing speed: %.2f MBytes per second" % SPEED)
        else:
            print("No measurement possible. Check that directory is writable.")
    except Exception:
        print("Something went wrong. I don't know what")
        raise

    print("Done")
