#!/usr/bin/python3

"""
Module to measure and report Internet speed
Method: get one small and then a bigger reference file, and measure how long it takes, then calculate speed
Reports in MB/s (so mega BYTES per seconds), not to be confused with Mbps
"""

import time
import logging
import urllib.request

SIZE_URL_LIST = [
    [5, "https://sabnzbd.org/tests/internetspeed/5MB.bin"],
    [10, "https://sabnzbd.org/tests/internetspeed/10MB.bin"],
    [20, "https://sabnzbd.org/tests/internetspeed/20MB.bin"],
]


def measure_speed_from_url(url: str) -> float:
    """Download the specified url (pointing to a file), and report back MB/s (as a float)"""
    logging.debug("URL is %s", url)
    start = time.time()
    downloaded_bytes = 0  # default
    try:
        req = urllib.request.Request(url, data=None, headers={"User-Agent": "Mozilla/5.0 (Macintosh)"})
        downloaded_bytes = len(urllib.request.urlopen(req, timeout=4).read())
    except:
        # No connection at all?
        pass

    time_granularity_worst_case = 0.008  # Windows has worst case 16 milliseconds
    duration = max(time.time() - start, time_granularity_worst_case)  # max() to avoid 0.0 divide error later on
    logging.debug("Downloaded bytes: %d", downloaded_bytes)
    logging.debug("Duration in seconds: %f", duration)

    return downloaded_bytes / 1024 ** 2 / duration


def bytes_to_bits(megabytes_per_second: float) -> float:
    """convert bytes (per second) to bits (per second), taking into a account network overhead"""
    return 8.05 * megabytes_per_second  # bits


def internetspeed() -> float:
    """Report Internet speed in MB/s as a float"""
    # Do basic test with a small download
    logging.debug("Basic measurement, with small download:")
    urlbasic = SIZE_URL_LIST[0][1]  # get first URL, which is smallest download
    base_megabytes_per_second = measure_speed_from_url(urlbasic)
    logging.debug("Speed in MB/s: %.2f", base_megabytes_per_second)
    if base_megabytes_per_second == 0:
        # no Internet connection, or other problem
        return 0.0

    """
    Based on this first, small download, do a bigger download; the biggest download that still fits in 10 seconds
    Rationale: a bigger download could yield higher MB/s because the 'starting delay' is relatively less
    Calculation as example: 
    If the 5MB download took 0.3 seconds, you can do a 30 times bigger download, so about 150 MB, will round to 100 MB
    """

    # Determine the biggest URL that can be downloaded within timeframe
    maxtime = 4  # seconds
    url_to_do = None
    for size, sizeurl in SIZE_URL_LIST:
        expectedtime = size / base_megabytes_per_second
        if expectedtime < maxtime:
            # ok, this one is feasible, so keep it in mind
            url_to_do = sizeurl

    max_megabytes_per_second = base_megabytes_per_second
    # Execute it twice, and get the best result
    for _ in range(2):
        if url_to_do:
            logging.debug(url_to_do)
            measured_megabytes_per_second = measure_speed_from_url(url_to_do)
            logging.debug("Speed in MB/s: %.2f", measured_megabytes_per_second)
            max_megabytes_per_second = max(max_megabytes_per_second, measured_megabytes_per_second)

    return max_megabytes_per_second


# MAIN

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("Log level is DEBUG")
    print("Starting speed test:")
    maxMBps = internetspeed()
    print("Speed in MB/s: %.2f" % maxMBps)
    print("Speed in Mbps: %.2f" % bytes_to_bits(maxMBps))
