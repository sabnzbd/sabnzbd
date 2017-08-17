#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
sabnzbd.utils.sslinfo - Information on the system's SSL setup
"""

# v23 indicates "negotiate highest possible"
_ALL_PROTOCOLS = ('v23', 't12', 't11', 't1', 'v3', 'v2')
_SSL_PROTOCOLS = {}
_SSL_PROTOCOLS_LABELS = []

try:
    import ssl

    # Basic
    _SSL_PROTOCOLS['v23'] = ssl.PROTOCOL_SSLv23

    # Loop through supported versions
    for ssl_prop in dir(ssl):
        if ssl_prop.startswith('PROTOCOL_'):
            if ssl_prop.endswith('SSLv2'):
                _SSL_PROTOCOLS['v2'] = ssl.PROTOCOL_SSLv2
                _SSL_PROTOCOLS_LABELS.append('SSL v2')
            elif ssl_prop.endswith('SSLv3'):
                _SSL_PROTOCOLS['v3'] = ssl.PROTOCOL_SSLv3
                _SSL_PROTOCOLS_LABELS.append('SSL v3')
            elif ssl_prop.endswith('TLSv1'):
                _SSL_PROTOCOLS['t1'] = ssl.PROTOCOL_TLSv1
                _SSL_PROTOCOLS_LABELS.append('TLS v1')
            elif ssl_prop.endswith('TLSv1_1'):
                _SSL_PROTOCOLS['t11'] = ssl.PROTOCOL_TLSv1_1
                _SSL_PROTOCOLS_LABELS.append('TLS v1.1')
            elif ssl_prop.endswith('TLSv1_2'):
                _SSL_PROTOCOLS['t12'] = ssl.PROTOCOL_TLSv1_2
                _SSL_PROTOCOLS_LABELS.append('TLS v1.2')

    # Reverse the labels, SSL's always come first in the dir()
    _SSL_PROTOCOLS_LABELS.reverse()
except:
    pass


def ssl_protocols():
    ''' Return acronyms for SSL protocols '''
    return _SSL_PROTOCOLS.keys()


def ssl_protocols_labels():
    ''' Return human readable labels for SSL protocols, highest quality first '''
    return _SSL_PROTOCOLS_LABELS


def ssl_version():
    try:
        import ssl
        return ssl.OPENSSL_VERSION
    except (ImportError, AttributeError):
        return None


if __name__ == '__main__':
    print 'SSL version: %s' % ssl_version()
    print 'Supported protocols: %s' % ssl_protocols()
