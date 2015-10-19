import ssl
import logging
DEBUG = False

def sslversion():
    try:
        return ssl.OPENSSL_VERSION
    except:
        return None
        
def sslversioninfo():
    try:
        return ssl.OPENSSL_VERSION_INFO
    except:
        return None

def sslprotocols():
    protocollist = []   
    try:
        for i in dir(ssl):
            #print i
            if i.find('PROTOCOL_') == 0:
                protocollist.append(i[9:])
        return protocollist
    except:
        return None

if __name__ == '__main__':

    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)
    if DEBUG: logger.setLevel(logging.DEBUG)
    
    print sslversion()
    print sslversioninfo()
    print sslprotocols()
    print str(sslprotocols())



