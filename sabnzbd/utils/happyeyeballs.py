import socket
import time
import ssl

# Python implementation of RFC 6555 / Happy Eyeballs: find the quickest IPv4/IPv6 connection
# See https://tools.ietf.org/html/rfc6555


def happyeyeballs(HOST, **kwargs):
    try:
        PORT=kwargs['port']
    except:
        PORT=80
    try:
        SSL=kwargs['ssl']
    except:
        SSL=False
    try:
        DEBUG=kwargs['debug']
    except:
        DEBUG=False

    shortesttime = 10000000	# something very big
    quickestserver = None

    if DEBUG: print "Checking", HOST, PORT, "SSL:", SSL, "DEBUG:", DEBUG
    try:
        allinfo = socket.getaddrinfo(HOST, 80, 0, 0, socket.IPPROTO_TCP)
    except:
        if DEBUG: print "Could not resolve", HOST
        return None

    for i in allinfo:
        address = i[4][0]
        if DEBUG: print "Address is ", address
        # note: i[0] contains socket.AF_INET or socket.AF_INET6

        try:
            start = time.clock()
            # CREATE SOCKET
            s = socket.socket(i[0], socket.SOCK_STREAM)
            s.settimeout(2)
            if not SSL:
                s.connect((address, PORT))
                s.close()
            else:
                # WRAP SOCKET
                wrappedSocket = ssl.wrap_socket(s, ssl_version=ssl.PROTOCOL_TLSv1)    
                # CONNECT
                wrappedSocket.connect((address, PORT))
                # CLOSE SOCKET CONNECTION
                wrappedSocket.close()

            delay = 1000.0*(time.clock() - start)
            if DEBUG: print "Connecting took:", delay, "msec"
            if delay < shortesttime:
                shortesttime = delay
                quickestserver = address
        except:
            if DEBUG: print "Something went wrong (possibly just no connection)"
            pass
    if DEBUG: print "Quickest server is", quickestserver
    return quickestserver



if __name__ == '__main__':
    print happyeyeballs('www.google.com')
    print happyeyeballs('www.google.com', port=443, ssl=True)
    print happyeyeballs('www.google.com', port=80, ssl=False)
    print happyeyeballs('block.cheapnews.eu', port=119)
    print happyeyeballs('block.cheapnews.eu', port=443, ssl=True)
    print happyeyeballs('block.cheapnews.eu', port=443, ssl=True, debug=True)
    print happyeyeballs('newszilla.xs4all.nl', port=119)
    print happyeyeballs('does.not.resolve', port=443, ssl=True, debug=True)    
    print happyeyeballs('216.58.211.164')

