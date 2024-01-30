import logging
import time

from .pystone import pystones


def getpystone():
    # Start calculation
    maxpystone = 0
    start = time.time()
    # Start with a short run, find the the pystone, and increase runtime until duration took > 0.1 second
    for pyseed in [1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]:
        duration, pystonefloat = pystones(pyseed)
        maxpystone = max(maxpystone, int(pystonefloat))
        # Stop when pystone() has been running for at least 0.1 second
        if duration > 0.1:
            break

    logging.debug("Pystone performance = %d (in %.2f seconds)", maxpystone, time.time() - start)
    return maxpystone


if __name__ == "__main__":
    print(getpystone())
