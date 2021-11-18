#!/usr/bin/python3
# Python implementation of RFC 6555 / Happy Eyeballs: find the quickest IPv4/IPv6 connection
# See https://tools.ietf.org/html/rfc6555
# Method: Start parallel sessions using threads, and only wait for the quickest succesful socket connect
# See https://tools.ietf.org/html/rfc6555#section-4.1

# You can run this as a standalone program, or as a module:
"""
from happyeyeballs import happyeyeballs
print happyeyeballs('newszilla.xs4all.nl', port=119)
"""

import socket
import ssl
import threading
import time
import logging
import queue


# Called by each thread
def do_socket_connect(result_queue: queue.Queue, ip: str, port: int, use_ssl: bool, ipv4delay: int):
    """Connect to the ip, and put the result into the queue"""
    try:
        # Create socket
        if ip.find(":") >= 0:
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        if ip.find(".") >= 0:
            time.sleep(ipv4delay)  # IPv4 ... so a delay for IPv4 if we prefer IPv6. Note: ipv4delay could be 0
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        s.settimeout(3)

        if not use_ssl:
            try:
                # Connect ...
                s.connect((ip, port))
            finally:
                # always close
                s.close()
        else:
            # SSL, so wrap socket, don't care about any verification
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            wrapped_socket = context.wrap_socket(s)

            try:
                wrapped_socket.connect((ip, port))
            finally:
                # Always close
                wrapped_socket.close()
        result_queue.put((ip, True))
    except:
        # We got an exception, so no successful connect on IP & port:
        result_queue.put((ip, False))


def happyeyeballs(host: str, port: int = 80, use_ssl: bool = False, preferipv6: bool = False) -> str:
    """Happyeyeballs function, with caching of the results"""

    # Find out if a cached result is available, and recent enough:
    timecurrent = int(time.time())  # current time in seconds since epoch
    retentionseconds = 100
    hostkey = (host, port, use_ssl, preferipv6)  # Example key: ('ssl.astraweb.com', 563, True, True)

    try:
        # Let's check the time:
        timecached = happyeyeballs.happylist[hostkey][1]
        if timecurrent - timecached <= retentionseconds:
            return happyeyeballs.happylist[hostkey][0]
    except:
        # Exception, so entry not there, so we have to fill it out
        pass

    # we only arrive here if the entry has to be determined. So let's do that:
    # We have to determine the (new) best IP address
    start = time.perf_counter()
    ipv4delay = 0
    try:
        # Check if there is an AAAA / IPv6 result for this host:
        socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_IP, socket.AI_CANONNAME)
        # preferipv6, AND at least one IPv6 found, so give IPv4 (!) a delay so IPv6 has a head start and is preferred
        if preferipv6:
            ipv4delay = 0.1
    except:
        pass

    result_queue = queue.Queue()  # queue used for threads giving back the results

    try:
        # Get all IP (IPv4 and IPv6) addresses:
        allinfo = socket.getaddrinfo(host, port, 0, 0, socket.IPPROTO_TCP)
        for info in allinfo:
            address = info[4][0]
            resolver_thread = threading.Thread(
                target=do_socket_connect, args=(result_queue, address, port, use_ssl, ipv4delay)
            )
            resolver_thread.daemon = True
            resolver_thread.start()

        result = None  # default return value, used if none of threads says True/"OK", so no connect on any IP address
        # start reading from the Queue for message from the threads:
        for _ in range(len(allinfo)):
            connect_result = result_queue.get()  # get a response
            if connect_result[1]:
                result = connect_result[0]
                break  # the first True/"OK" is enough, so break out of for loop
    except:
        result = None

    logging.info(
        "Quickest IP address for %s (port %s, ssl %s, preferipv6 %s) is %s", host, port, use_ssl, preferipv6, result
    )
    delay = int(1000 * (time.perf_counter() - start))
    logging.debug("Happy Eyeballs lookup and port connect took %s ms", delay)

    # We're done. Store and return the result
    if result:
        happyeyeballs.happylist[hostkey] = (result, timecurrent)
    return result


happyeyeballs.happylist = {}  # The cached results. This static variable must be after the def happyeyeballs()


if __name__ == "__main__":
    # plain HTTP/HTTPS sites:
    print((happyeyeballs("www.google.com")))
    print((happyeyeballs("www.google.com", port=443, use_ssl=True)))
    print((happyeyeballs("www.nu.nl")))

    # newsservers:
    print((happyeyeballs("newszilla6.xs4all.nl", port=119)))
    print((happyeyeballs("newszilla.xs4all.nl", port=119)))
    print((happyeyeballs("block.cheapnews.eu", port=119)))
    print((happyeyeballs("block.cheapnews.eu", port=443, use_ssl=True)))
    print((happyeyeballs("sslreader.eweka.nl", port=563, use_ssl=True)))
    print((happyeyeballs("news.thundernews.com", port=119)))
    print((happyeyeballs("news.thundernews.com", port=119, preferipv6=False)))
    print((happyeyeballs("secure.eu.thundernews.com", port=563, use_ssl=True)))
    print((happyeyeballs("bonus.frugalusenet.com", port=563, use_ssl=True)))

    # Strange cases
    print((happyeyeballs("does.not.resolve", port=443, use_ssl=True)))
    print((happyeyeballs("www.google.com", port=119)))
    print((happyeyeballs("216.58.211.164")))
