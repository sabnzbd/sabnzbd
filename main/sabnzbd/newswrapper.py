"""
sabnzbd.newswrapper - based (and largely copied) from pynewsleecher-0.7 
                      WrapNews.py by Freddie freddie@madcowdisease.org
"""

import errno
import socket
from threading import Thread

from nntplib import NNTPPermanentError
from time import time

__NAME__ = "newswrapper"

TIMEOUT_VALUE = 60

socket.setdefaulttimeout(TIMEOUT_VALUE)

def con(sock, host, port):
    sock.connect((host, port))
    sock.setblocking(0)
    
class NNTP:
    def __init__(self, host, port, user=None, password=None):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(0)
        
        try:
            self.sock.connect((self.host, self.port))
        except socket.error, (_errno, strerror):
            #expected, do nothing
            if _errno == errno.EINPROGRESS:
                pass
                
            #windows can't connect non-blocking sockets
            elif _errno == errno.EWOULDBLOCK:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                #self.sock.connect((self.host, self.port))
                #self.sock.setblocking(0)
                Thread(target=con, args=(self.sock, self.host, self.port)).start()
                
            else:
                raise socket.error(_errno, strerror)

class NewsWrapper:
    def __init__(self, server, thrdnum):
        self.server = server
        self.thrdnum = thrdnum
        
        self.timeout = None
        self.article = None
        self.data = ''
        self.lines = []
        
        self.nntp = None
        self.recv = None
        
        self.connected = False
        
        self.user_sent = False
        self.pass_sent = False
        
        self.group = None
        
        self.user_ok = False
        self.pass_ok = False
        
    def init_connect(self):
        self.nntp = NNTP(self.server.host, self.server.port, 
                         self.server.username, self.server.password)
        self.recv = self.nntp.sock.recv
        
        self.timeout = time() + TIMEOUT_VALUE
        
    def finish_connect(self):
        if not self.server.username or not self.server.password:
            self.connected = True
            self.user_sent = True
            self.user_ok = True
            self.pass_sent = True
            self.pass_ok = True
            
        if not self.user_sent:
            command = 'authinfo user %s\r\n' % (self.server.username)
            self.nntp.sock.sendall(command)
            self.user_sent = True
        elif not self.user_ok:
            if self.lines[0][:3] == '381':
                self.user_ok = True
                
        if self.user_ok and not self.pass_sent:
            command = 'authinfo pass %s\r\n' % (self.server.password)
            self.nntp.sock.sendall(command)
            self.pass_sent = True
        elif self.user_ok and not self.pass_ok:
            if self.lines[0][:3] != '281':
                raise NNTPPermanentError(self.lines[0])
            else:
                self.connected = True
                
        self.timeout = time() + TIMEOUT_VALUE
        
    def body(self):
        self.timeout = time() + TIMEOUT_VALUE
        command = 'BODY <%s>\r\n' % (self.article.article)
        self.nntp.sock.sendall(command)
        
    def send_group(self, group):
        self.timeout = time() + TIMEOUT_VALUE
        command = 'GROUP %s\r\n' % (group)
        self.nntp.sock.sendall(command)
        
    def recv_chunk(self):
        self.timeout = time() + TIMEOUT_VALUE
        chunk = self.recv(32768)
        
        self.data += chunk
        new_lines = self.data.split('\r\n')
        
        self.data = new_lines.pop()
        self.lines.extend(new_lines)
        
        if self.lines and self.lines[-1] == '.':
            self.lines = self.lines[1:-1]
            return (len(chunk), True)
        else:
            return (len(chunk), False)
            
    def soft_reset(self):
        self.timeout = None
        self.article = None
        self.data = ''
        self.lines = []
        
    def hard_reset(self):
        if self.nntp:
            try:
                self.nntp.sock.close()
            except:
                pass
                
        self.__init__(self.server, self.thrdnum)
        
        # Wait before resuing this newswrapper
        self.timeout = time() + TIMEOUT_VALUE
