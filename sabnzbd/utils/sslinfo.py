# v23 indicates "negotiate highest possible"
_ALL_PROTOCOLS = ('v23', 't12', 't11', 't1', 'v3', 'v2')
_SSL_PROTOCOLS = {}
_SSL_PROTOCOLS_LABELS = []

def ssl_potential():
    ''' Return a list of potentially supported SSL protocols'''
    try:
        import ssl
    except ImportError:
        return []
    return [p[9:] for p in dir(ssl) if p.startswith('PROTOCOL_')]

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


def ssl_method(method):
    ''' Translate SSL acronym to a method value '''
    if method in _SSL_PROTOCOLS:
        return _SSL_PROTOCOLS[method]
    else:
        # The default is "negotiate a protocol"
        try:
            return ssl.PROTOCOL_SSLv23
        except AttributeError:
            return _SSL_PROTOCOLS[0]


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


def pyopenssl_version():
    try:
        import OpenSSL
        return OpenSSL.__version__
    except ImportError:
        return None

if __name__ == '__main__':
    print 'SSL version: %s' % ssl_version()
    print 'pyOpenSSL version: %s' % pyopenssl_version()
    print 'Supported protocols: %s' % ssl_protocols()
