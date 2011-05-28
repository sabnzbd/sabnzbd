"""Manage HTTP servers with CherryPy."""

import warnings

import cherrypy
from cherrypy.lib import attributes

# We import * because we want to export check_port
# et al as attributes of this module.
from cherrypy.process.servers import *


class Server(ServerAdapter):
    """An adapter for an HTTP server.
    
    You can set attributes (like socket_host and socket_port)
    on *this* object (which is probably cherrypy.server), and call
    quickstart. For example:
    
        cherrypy.server.socket_port = 80
        cherrypy.quickstart()
    """
    
    socket_port = 8080
    
    _socket_host = '127.0.0.1'
    def _get_socket_host(self):
        return self._socket_host
    def _set_socket_host(self, value):
        if value == '':
            raise ValueError("The empty string ('') is not an allowed value. "
                             "Use '0.0.0.0' instead to listen on all active "
                             "interfaces (INADDR_ANY).")
        self._socket_host = value
    socket_host = property(_get_socket_host, _set_socket_host,
        doc="""The hostname or IP address on which to listen for connections.
        
        Host values may be any IPv4 or IPv6 address, or any valid hostname.
        The string 'localhost' is a synonym for '127.0.0.1' (or '::1', if
        your hosts file prefers IPv6). The string '0.0.0.0' is a special
        IPv4 entry meaning "any active interface" (INADDR_ANY), and '::'
        is the similar IN6ADDR_ANY for IPv6. The empty string or None are
        not allowed.""")
    
    socket_file = None
    socket_queue_size = 5
    socket_timeout = 10
    shutdown_timeout = 5
    protocol_version = 'HTTP/1.1'
    reverse_dns = False
    thread_pool = 10
    thread_pool_max = -1
    max_request_header_size = 500 * 1024
    max_request_body_size = 100 * 1024 * 1024
    instance = None
    ssl_context = None
    ssl_certificate = None
    ssl_certificate_chain = None
    ssl_private_key = None
    nodelay = True
    
    def __init__(self):
        self.bus = cherrypy.engine
        self.httpserver = None
        self.interrupt = None
        self.running = False
    
    def quickstart(self, server=None):
        """This does nothing now and will be removed in 3.2."""
        warnings.warn('quickstart does nothing now and will be removed in '
                      '3.2. Call cherrypy.engine.start() instead.',
                      DeprecationWarning)
    
    def httpserver_from_self(self, httpserver=None):
        """Return a (httpserver, bind_addr) pair based on self attributes."""
        if httpserver is None:
            httpserver = self.instance
        if httpserver is None:
            from cherrypy import _cpwsgi_server
            httpserver = _cpwsgi_server.CPWSGIServer(self)
        if isinstance(httpserver, basestring):
            # Is anyone using this? Can I add an arg?
            httpserver = attributes(httpserver)(self)
        return httpserver, self.bind_addr
    
    def start(self):
        """Start the HTTP server."""
        if not self.httpserver:
            self.httpserver, self.bind_addr = self.httpserver_from_self()
        ServerAdapter.start(self)
    start.priority = 75
    
    def _get_bind_addr(self):
        if self.socket_file:
            return self.socket_file
        if self.socket_host is None and self.socket_port is None:
            return None
        return (self.socket_host, self.socket_port)
    def _set_bind_addr(self, value):
        if value is None:
            self.socket_file = None
            self.socket_host = None
            self.socket_port = None
        elif isinstance(value, basestring):
            self.socket_file = value
            self.socket_host = None
            self.socket_port = None
        else:
            try:
                self.socket_host, self.socket_port = value
                self.socket_file = None
            except ValueError:
                raise ValueError("bind_addr must be a (host, port) tuple "
                                 "(for TCP sockets) or a string (for Unix "
                                 "domain sockets), not %r" % value)
    bind_addr = property(_get_bind_addr, _set_bind_addr)
    
    def base(self):
        """Return the base (scheme://host[:port] or sock file) for this server."""
        if self.socket_file:
            return self.socket_file
        
        host = self.socket_host
        if host in ('0.0.0.0', '::'):
            # 0.0.0.0 is INADDR_ANY and :: is IN6ADDR_ANY.
            # Look up the host name, which should be the
            # safest thing to spit out in a URL.
            import socket
            host = socket.gethostname()
        
        port = self.socket_port
        
        if self.ssl_certificate:
            scheme = "https"
            if port != 443:
                host += ":%s" % port
        else:
            scheme = "http"
            if port != 80:
                host += ":%s" % port
        
        return "%s://%s" % (scheme, host)

