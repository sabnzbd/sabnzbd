#!/usr/bin/python3
# Python implementation of RFC 6555 / Happy Eyeballs: find the quickest IPv4/IPv6 connection
# See https://tools.ietf.org/html/rfc6555
# Method: Start parallel sessions using threads, and only wait for the quickest succesful socket connect
# If the HOST has an IPv6 address, IPv6 is given a head start by delaying IPv4. See https://tools.ietf.org/html/rfc6555#section-4.1

# You can run this as a standalone program, or as a module:
"""
from happyeyeballs import happyeyeballs
print happyeyeballs('newszilla.xs4all.nl', port=119)
"""
# or with more logging:
"""
from happyeyeballs import happyeyeballs
import logging
logger = logging.getLogger('')
logger.setLevel(logging.DEBUG)
print happyeyeballs('newszilla.xs4all.nl', port=119)
"""

import socket
import ssl
import threading
import time
import logging
import queue

DEBUG = False


# called by each thread
def do_socket_connect(queue, ip, PORT, SSL, ipv4delay):
    # connect to the ip, and put the result into the queue
    if DEBUG:
        logging.debug("Input for thread is %s %s %s", ip, PORT, SSL)

    try:
        # CREATE SOCKET
        if ip.find(":") >= 0:
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        if ip.find(".") >= 0:
            time.sleep(ipv4delay)  # IPv4 ... so a delay for IPv4 as we prefer IPv6. Note: ipv4delay could be 0
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        s.settimeout(3)
        if not SSL:
            # Connect ...
            s.connect((ip, PORT))
            # ... and close
            s.close()
        else:
            # WRAP SOCKET
            wrappedSocket = ssl.wrap_socket(s)
            # CONNECT
            wrappedSocket.connect((ip, PORT))
            # CLOSE SOCKET CONNECTION
            wrappedSocket.close()
        queue.put((ip, True))
        if DEBUG:
            logging.debug("connect to %s OK", ip)
    except:
        queue.put((ip, False))
        if DEBUG:
            logging.debug("connect to %s not OK", ip)
        pass


def happyeyeballs(HOST, **kwargs):
    # Happyeyeballs function, with caching of the results

    # Fill out the parameters into the variables
    try:
        PORT = kwargs["port"]
    except:
        PORT = 80
    try:
        SSL = kwargs["ssl"]
    except:
        SSL = False
    try:
        preferipv6 = kwargs["preferipv6"]
    except:
        preferipv6 = True  # prefer IPv6, so give IPv6 connects a head start by delaying IPv4

        # Find out if a cached result is available, and recent enough:
    timecurrent = int(time.time())  # current time in seconds since epoch
    retentionseconds = 100
    hostkey = (HOST, PORT, SSL, preferipv6)  # Example key: (u'ssl.astraweb.com', 563, True, True)
    try:
        happyeyeballs.happylist[hostkey]  # just to check: does it exist?
        # No exception, so entry exists, so let's check the time:
        timecached = happyeyeballs.happylist[hostkey][1]
        if timecurrent - timecached <= retentionseconds:
            if DEBUG:
                logging.debug("existing cached result recent enough")
            return happyeyeballs.happylist[hostkey][0]
        else:
            if DEBUG:
                logging.debug("existing cached result too old. Find a new one")
            # Continue a few lines down
    except:
        # Exception, so entry not there, so we have to fill it out
        if DEBUG:
            logging.debug("Host not yet in the cache. Find entry")
        pass
        # we only arrive here if the entry has to be determined. So let's do that:

        # We have to determine the (new) best IP address
    start = time.perf_counter()
    if DEBUG:
        logging.debug("\n\n%s %s %s %s", HOST, PORT, SSL, preferipv6)

    ipv4delay = 0
    try:
        # Check if there is an AAAA / IPv6 result for this host:
        socket.getaddrinfo(HOST, PORT, socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_IP, socket.AI_CANONNAME)
        if DEBUG:
            logging.debug("IPv6 address found for %s", HOST)
        if preferipv6:
            ipv4delay = 0.1  # preferipv6, AND at least one IPv6 found, so give IPv4 (!) a delay so that IPv6 has a head start and is preferred
    except:
        if DEBUG:
            logging.debug("No IPv6 address found for %s", HOST)

    myqueue = queue.Queue()  # queue used for threads giving back the results

    try:
        # Get all IP (IPv4 and IPv6) addresses:
        allinfo = socket.getaddrinfo(HOST, PORT, 0, 0, socket.IPPROTO_TCP)
        for info in allinfo:
            address = info[4][0]
            thisthread = threading.Thread(target=do_socket_connect, args=(myqueue, address, PORT, SSL, ipv4delay))
            thisthread.daemon = True
            thisthread.start()
        result = None  # default return value, used if none of threads says True/"OK", so no connect on any IP address
        # start reading from the Queue for message from the threads:
        for i in range(len(allinfo)):
            s = myqueue.get()  # get a response
            if s[1] == True:
                result = s[0]
                break  # the first True/"OK" is enough, so break out of for loop
    except:
        if DEBUG:
            logging.debug("something went wrong in the try block")
        result = None
    logging.info(
        "Quickest IP address for %s (port %s, ssl %s, preferipv6 %s) is %s", HOST, PORT, SSL, preferipv6, result
    )
    delay = int(1000 * (time.perf_counter() - start))
    logging.debug("Happy Eyeballs lookup and port connect took %s ms", delay)

    # We're done. Store and return the result
    if result:
        happyeyeballs.happylist[hostkey] = (result, timecurrent)
        if DEBUG:
            logging.debug("Determined new result for %s with result %s", hostkey, happyeyeballs.happylist[hostkey])
    return result


happyeyeballs.happylist = {}  # The cached results. This static variable must be after the def happyeyeballs()


if __name__ == "__main__":

    logger = logging.getLogger("")
    logger.setLevel(logging.INFO)
    if DEBUG:
        logger.setLevel(logging.DEBUG)

    # plain HTTP/HTTPS sites:
    print((happyeyeballs("www.google.com")))
    print((happyeyeballs("www.google.com", port=443, ssl=True)))
    print((happyeyeballs("www.nu.nl")))

    # newsservers:
    print((happyeyeballs("newszilla6.xs4all.nl", port=119)))
    print((happyeyeballs("newszilla.xs4all.nl", port=119)))
    print((happyeyeballs("block.cheapnews.eu", port=119)))
    print((happyeyeballs("block.cheapnews.eu", port=443, ssl=True)))
    print((happyeyeballs("sslreader.eweka.nl", port=563, ssl=True)))
    print((happyeyeballs("news.thundernews.com", port=119)))
    print((happyeyeballs("news.thundernews.com", port=119, preferipv6=False)))
    print((happyeyeballs("secure.eu.thundernews.com", port=563, ssl=True)))

    # Strange cases
    print((happyeyeballs("does.not.resolve", port=443, ssl=True)))
    print((happyeyeballs("www.google.com", port=119)))
    print((happyeyeballs("216.58.211.164")))
