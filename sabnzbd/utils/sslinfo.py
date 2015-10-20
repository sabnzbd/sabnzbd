import ssl
import logging

def sslversion():
    try:
        return ssl.OPENSSL_VERSION
    except:
        logging.info("ssl.OPENSSL_VERSION not defined")
        return None
        
def sslversioninfo():
    try:
        return ssl.OPENSSL_VERSION_INFO
    except:
        logging.info("ssl.OPENSSL_VERSION_INFO not defined")
        return None

def sslprotocols():
    protocollist = []   
    try:
        for i in dir(ssl):
            if i.find('PROTOCOL_') == 0:
                protocollist.append(i[9:])
        return protocollist
    except:
        return None

if __name__ == '__main__':

    logger = logging.getLogger('')
    logger.setLevel(logging.INFO)

    print sslversion()
    print sslversioninfo()
    print sslprotocols()

