import socket
socket.setdefaulttimeout(4)
import sys

from sabnzbd.newswrapper import NewsWrapper
from sabnzbd.downloader import Server, clues_login, clues_too_many
from sabnzbd.config import get_servers

def test_nntp_server(host, port, username=None, password=None, ssl=None, timeout=120):
    ''' Will connect (blocking) to the nttp server and report back any errors '''
    if '*' in password and not password.strip('*'):
        # If the password is masked, try retrieving it from the config
        servers = get_servers()
        got_pass = False
        current = '%s:%s' % (host, port)
        for server in servers:
            if server == current:
                srv = servers[server]
                password = srv.password.get()
                got_pass = True
        if not got_pass:
            return 'Password masked in ******, please re-enter'
    try:
        s = Server(-1, host, port, timeout, 1, 0, ssl, username, password)
    except:
        return 'Invalid server details'
    
    try:
        nw = NewsWrapper(s, -1, block=True)
        nw.init_connect()
        while not nw.connected:
            nw.lines = []
            nw.recv_chunk(block=True)
            nw.finish_connect()
            
    except socket.timeout, e:
        if port != 119 and not ssl:
            return 'Timed out: Try enabling SSL or connecting on a different port.'
        else:
            return 'Timed out'
    except socket.error, e:
        return xml_name(str(e))
    
    except:
        return xml_name(str(sys.exc_info()[1]))
    
    
    if not username or not password:
        nw.nntp.sock.sendall('HELP\r\n')
        try:
            nw.lines = []
            nw.recv_chunk(block=True)
        except:
            return xml_name(str(sys.exc_info()[1]))
    
    # Could do with making a function for return codes to be used by downloader
    code = nw.lines[0][:3]
    if code == '502':
        return 'Authentication failed, check username/password'
    
    elif code == '480':
        return 'Server requires username and password'
    
    elif code == '100' or code.startswith('2'):
        return 'Connected Successfully!'
    
    elif clues_login(nw.lines[0]):
        return 'Authentication failed, check username/password'
    
    elif clues_too_many(nw.lines[0]):
        return 'Too many connections, please pause downloading or try again later'
    
    else:
        return 'Cound not determine connection result (%s)' % xml_name(nw.lines[0])
