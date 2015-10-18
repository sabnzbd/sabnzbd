import ssl
import logging
DEBUG = False

def sslversion():
    return ssl.OPENSSL_VERSION
    
def sslversioninfo():
    return ssl.OPENSSL_VERSION_INFO    

def sslprotocols():
    protocollist = []   
    for i in dir(ssl):
        #print i
        if i.find('PROTOCOL_') == 0:
            protocollist.append(i)
    return protocollist


if __name__ == '__main__':

    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)
    if DEBUG: logger.setLevel(logging.DEBUG)
    
    print sslversion()
    print sslversioninfo()
    print sslprotocols()
    print str(sslprotocols())



