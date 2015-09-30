#!/usr/bin/env python

# Python implementation of RFC 6555 / Happy Eyeballs: find the quickest IPv4/IPv6 connection
# See https://tools.ietf.org/html/rfc6555
# Method: Start parallel sessions using threads, and only wait for the quickest succesful socket connect
# If the HOST has an IPv6 address, IPv6 is given a head start by delaying IPv4. See https://tools.ietf.org/html/rfc6555#section-4.1

# You can run this as a standalone program, or as a module:
'''
from happyeyeballs import happyeyeballs
print happyeyeballs('newszilla.xs4all.nl', port=119)
'''
# or with more logging:
'''
from happyeyeballs import happyeyeballs
import logging
logger = logging.getLogger('')
logger.setLevel(logging.DEBUG)
print happyeyeballs('newszilla.xs4all.nl', port=119)
'''

import socket
import ssl
import Queue
import threading
import time
import logging

DEBUG = False


# called by each thread
def do_socket_connect(queue, ip, PORT, SSL, ipv4delay):
    # connect to the ip, and put the result into the queue
    if DEBUG: logging.debug("Input for thread is %s %s %s", ip, PORT, SSL)

    try:
        # CREATE SOCKET
        if ip.find(':') >= 0:
                s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        if ip.find('.') >= 0:
            time.sleep(ipv4delay)    # IPv4 ... so a delay for IPv4 as we prefer IPv6. Note: ipv4delay could be 0
            s = socket.socket(socket.AF_INET,  socket.SOCK_STREAM)

        s.settimeout(3)
        if not SSL:
            # Connect ...
            s.connect((ip, PORT))
            # ... and close
            s.close()
        else:
            # WRAP SOCKET
            wrappedSocket = ssl.wrap_socket(s, ssl_version=ssl.PROTOCOL_TLSv1)
            # CONNECT
            wrappedSocket.connect((ip, PORT))
            # CLOSE SOCKET CONNECTION
            wrappedSocket.close()
        queue.put((ip, True))
        if DEBUG: logging.debug("connect to %s OK", ip)
    except:
        queue.put((ip, False))
        if DEBUG: logging.debug("connect to %s not OK", ip)
        pass


def happyeyeballs(HOST, **kwargs):
    try:
        PORT = kwargs['port']
    except:
        PORT = 80
    try:
        SSL = kwargs['ssl']
    except:
        SSL = False
    try:
        preferipv6 = kwargs['preferipv6']
    except:
        preferipv6 = True     # prefer IPv6, so give IPv6 connects a head start by delaying IPv4

    start = time.clock()
    if DEBUG: logging.debug("\n\n%s %s %s %s", HOST, PORT, SSL, preferipv6)

    ipv4delay = 0
    try:
        info = socket.getaddrinfo(HOST, PORT, socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_IP, socket.AI_CANONNAME)
        if DEBUG: logging.debug("IPv6 address found for %s", HOST)
        if preferipv6:
            ipv4delay=0.1    # preferipv6, AND at least one IPv6 found, so give IPv4 (!) a delay so that IPv6 has a head start and is preferred
    except:
        if DEBUG: logging.debug("No IPv6 address found for %s", HOST)

    myqueue = Queue.Queue()    # queue used for threads giving back the results

    try:
        allinfo = socket.getaddrinfo(HOST, PORT, 0, 0, socket.IPPROTO_TCP)
        for info in allinfo:
            address = info[4][0]
            thisthread = threading.Thread(target=do_socket_connect, args=(myqueue, address, PORT, SSL, ipv4delay))
            thisthread.daemon = True
            thisthread.start()
        result = None    # default return value, used if none of threads says True/"OK", so no connect on any IP address
        # start reading from the Queue for message from the threads:
        for i in range(len(allinfo)):
            s = myqueue.get()    # get a response
            if s[1] == True:
                result = s[0]
                break    # the first True/"OK" is enough, so break out of for loop
    except:
        if DEBUG: logging.debug("some went wrong in the try block")
        result = None
    logging.info("Quickest IP address for %s (port %s, ssl %s, preferipv6 %s) is %s", HOST, PORT, SSL, preferipv6, result)
    delay = 1000.0 * (time.clock() - start)
    logging.debug("Happy Eyeballs lookup took %s microseconds", delay)
    return result



if __name__ == '__main__':

    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)
    if DEBUG: logger.setLevel(logging.DEBUG)

    # plain HTTP/HTTPS sites:
    print happyeyeballs('www.google.com')
    print happyeyeballs('www.google.com', port=443, ssl=True)
    print happyeyeballs('www.nu.nl')

    # newsservers:
    print happyeyeballs('newszilla6.xs4all.nl', port=119)
    print happyeyeballs('newszilla.xs4all.nl', port=119)
    print happyeyeballs('block.cheapnews.eu', port=119)
    print happyeyeballs('block.cheapnews.eu', port=443, ssl=True)
    print happyeyeballs('sslreader.eweka.nl', port=563, ssl=True)
    print happyeyeballs('news.thundernews.com', port=119)
    print happyeyeballs('news.thundernews.com', port=119, preferipv6=False)
    print happyeyeballs('secure.eu.thundernews.com', port=563, ssl=True)

    # Strange cases
    print happyeyeballs('does.not.resolve', port=443, ssl=True)
    print happyeyeballs('216.58.211.164')

