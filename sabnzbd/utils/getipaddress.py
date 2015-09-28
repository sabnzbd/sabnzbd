#!/usr/bin/python -OO

import socket


def localipv4():
    try:
        s_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_ipv4.connect(('1.2.3.4', 80))    # Option: use 100.64.1.1 (IANA-Reserved IPv4 Prefix for Shared Address Space)
        ipv4 = s_ipv4.getsockname()[0]
        s_ipv4.close()
    except:
        ipv4 = None
        pass
    return ipv4


def publicipv4():
    try:
        import urllib2
        f = urllib2.urlopen("http://api.ipify.org", timeout=2)    # timeout 2 seconds, in case website is not accessible
        public_ipv4 = f.read()
        socket.inet_aton(public_ipv4)  # if we got anything else than a plain IPv4 address, this will raise an exception
    except:
        public_ipv4 = None
        pass
    return public_ipv4


def ipv6():
    try:
        s_ipv6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s_ipv6.connect(('2001:db8::8080', 80))    # IPv6 prefix for documentation purpose
        ipv6 = s_ipv6.getsockname()[0]
        s_ipv6.close()
    except:
        ipv6 = None
    return ipv6

if __name__ == '__main__':
    print localipv4()
    print publicipv4()
    print ipv6()
