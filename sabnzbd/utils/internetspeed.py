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
    [50, "https://sabnzbd.org/tests/internetspeed/50MB.bin"],
    [100, "https://sabnzbd.org/tests/internetspeed/100MB.bin"],
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

    return downloaded_bytes / 1024**2 / duration


def bytes_to_bits(megabytes_per_second: float) -> float:
    """convert bytes (per second) to bits (per second), taking into a account network overhead"""
    return 8.05 * megabytes_per_second  # bits


def iperf3_downstream_speed(server="ams.speedtest.clouvider.net", duration=3):
    # Returns Internet in Mbps
    try:
        import iperf3  # needs iperf3 binary and iperf python module.
    except:
        return None
    import random

    client = iperf3.Client()
    client.duration = duration  # seconds
    client.num_streams = 20  # should be enough for ... 2500 Mbps?
    client.server_hostname = server # todo ipv4 versus ipv6 for strange setups?
    client.reverse = True  # Downstream

    portlist = list(range(5200, 5209 + 1))
    for _ in range(8):
        myport = random.choice(portlist)
        portlist.remove(myport)
        client.port = myport
        logging.debug("Trying %s on port %s", server, myport)
        try:
            result = client.run()  # run the test
            # ... after some time:
            Mbps = int(result.received_Mbps)
            return Mbps
        except:
            pass
    return None


def internetspeed() -> float:
    """Report Internet speed in MB/s as a float"""

    # check if on Linux (incl docker)
    import platform

    if platform.system() == "Linux":
        maxspeed_iperf3 = None
        iperf3_servers = ["ams.speedtest.clouvider.net", "fra.speedtest.clouvider.net", "nyc.speedtest.clouvider.net"]
        for myserver in iperf3_servers:
            iperf3_speed = iperf3_downstream_speed(myserver)
            logging.debug("speed via %s is %s [Mbps]", myserver, iperf3_speed)
            maxspeed_iperf3 = max(maxspeed_iperf3 or 0, iperf3_speed or 0)

        if maxspeed_iperf3 > 0:
            # OK, done
            return maxspeed_iperf3 / 8.05

    # Do basic test with a small download
    logging.debug("Basic measurement, with small download:")
    start = time.time()
    urlbasic = SIZE_URL_LIST[0][1]  # get first URL, which is smallest download
    base_megabytes_per_second = measure_speed_from_url(urlbasic)
    logging.debug("Speed in MB/s: %.2f", base_megabytes_per_second)
    if base_megabytes_per_second == 0:
        # no Internet connection, or other problem
        return 0.0

    """
    Based on this first, small download, do a bigger download; the biggest download that still fits in total 8 seconds
    Rationale: a bigger download could yield higher MB/s because the 'starting delay' is relatively less
    We do two downloads, so one download must fit in 4 seconds
    Note: a slow DNS lookup does influence the total time, so the measured speed (read: seemingly lower download speed)
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

    logging.debug("Internet Bandwidth = %.2f MB/s (in %.2f seconds)", max_megabytes_per_second, time.time() - start)
    return max_megabytes_per_second


# MAIN

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("Log level is DEBUG")
    print("Starting speed test:")
    maxMBps = internetspeed()
    print("Speed in MB/s: %.2f" % maxMBps)
    print("Speed in Mbps: %.2f" % bytes_to_bits(maxMBps))
