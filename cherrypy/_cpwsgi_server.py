"""WSGI server interface (see PEP 333). This adds some CP-specific bits to
the framework-agnostic wsgiserver package.
"""

import cherrypy
from cherrypy import wsgiserver


class CPHTTPRequest(wsgiserver.HTTPRequest):
    
    def __init__(self, sendall, environ, wsgi_app):
        s = cherrypy.server
        self.max_request_header_size = s.max_request_header_size or 0
        self.max_request_body_size = s.max_request_body_size or 0
        wsgiserver.HTTPRequest.__init__(self, sendall, environ, wsgi_app)


class CPHTTPConnection(wsgiserver.HTTPConnection):
    
    RequestHandlerClass = CPHTTPRequest


class CPWSGIServer(wsgiserver.CherryPyWSGIServer):
    """Wrapper for wsgiserver.CherryPyWSGIServer.
    
    wsgiserver has been designed to not reference CherryPy in any way,
    so that it can be used in other frameworks and applications. Therefore,
    we wrap it here, so we can set our own mount points from cherrypy.tree
    and apply some attributes from config -> cherrypy.server -> wsgiserver.
    """
    
    ConnectionClass = CPHTTPConnection
    
    def __init__(self, server_adapter=cherrypy.server):
        self.server_adapter = server_adapter
        
        # We have to make custom subclasses of wsgiserver internals here
        # so that our server.* attributes get applied to every request.
        class _CPHTTPRequest(wsgiserver.HTTPRequest):
            def __init__(self, sendall, environ, wsgi_app):
                s = server_adapter
                self.max_request_header_size = s.max_request_header_size or 0
                self.max_request_body_size = s.max_request_body_size or 0
                wsgiserver.HTTPRequest.__init__(self, sendall, environ, wsgi_app)
        class _CPHTTPConnection(wsgiserver.HTTPConnection):
            RequestHandlerClass = _CPHTTPRequest
        self.ConnectionClass = _CPHTTPConnection
        
        server_name = (self.server_adapter.socket_host or
                       self.server_adapter.socket_file or
                       None)
        
        s = wsgiserver.CherryPyWSGIServer
        s.__init__(self, server_adapter.bind_addr, cherrypy.tree,
                   self.server_adapter.thread_pool,
                   server_name,
                   max = self.server_adapter.thread_pool_max,
                   request_queue_size = self.server_adapter.socket_queue_size,
                   timeout = self.server_adapter.socket_timeout,
                   shutdown_timeout = self.server_adapter.shutdown_timeout,
                   )
        self.protocol = self.server_adapter.protocol_version
        self.nodelay = self.server_adapter.nodelay
        self.ssl_context = self.server_adapter.ssl_context
        self.ssl_certificate = self.server_adapter.ssl_certificate
        self.ssl_certificate_chain = self.server_adapter.ssl_certificate_chain
        self.ssl_private_key = self.server_adapter.ssl_private_key

