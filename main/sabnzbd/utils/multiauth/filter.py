# Copyright (c) 2005 Christian Wyglendowski
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


import cherrypy
from cherrypy.filters.basefilter import BaseFilter
from sabnzbd.utils.multiauth.auth import SecureResource

def loginScreen(targetPage, message=None):
    cherrypy.response.body = """
    <html>
    <head><title>Login</title></head>
    <body>
    <form action="%s" method="POST">
    Username: <input type="text" name="ma_username" /><br />
    Password: <input type="password" name="ma_password" /><br />
    <input value="Login" type="submit" />
    </form>
    </body>
    </html>
    """ % (targetPage,)

class MultiAuthFilter(BaseFilter):
    def __init__(self, unauthorizedPath, backend, frontend=loginScreen, 
                 username_arg='ma_username', password_arg='ma_password'):
        self.backend = backend
        self.frontend = frontend
        self.unauthorizedPath = unauthorizedPath
        self.username_arg = username_arg
        self.password_arg = password_arg

    def beforeMain(self):
        if (cherrypy.request.paramMap.has_key(self.username_arg) \
            and cherrypy.request.paramMap.has_key(self.password_arg)):
            # the user is trying to login
            username = cherrypy.request.paramMap.get(self.username_arg)
            password = cherrypy.request.paramMap.get(self.password_arg)
            authenticated, roles = self.backend.authenticate(username, password)
            if authenticated:
                cherrypy.session['roles'] = roles + [username, 'loggedIn']
            del cherrypy.request.paramMap[self.username_arg]
            del cherrypy.request.paramMap[self.password_arg]
            
    def beforeFinalize(self):
        if isinstance(cherrypy.response.body, SecureResource):
            rsrc = cherrypy.response.body
            if not cherrypy.session.get('roles'):
                self.frontend(cherrypy.request.path)
                return
            matches = [role for role in rsrc.roles if role in cherrypy.session['roles']]
            if not matches:
                raise cherrypy.HTTPRedirect(self.unauthorizedPath)
            else:
                cherrypy.response.body = rsrc.callable(rsrc.instance,
                                                       *rsrc.callable_args,
                                                       **rsrc.callable_kwargs)
                