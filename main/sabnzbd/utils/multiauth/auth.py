# Copyright (c) 2005 Christian Wyglendowski
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


import types

import cherrypy
from cherrypy.filters.basefilter import BaseFilter
from sabnzbd.utils.multiauth.providers import DictAuthProvider

class protected(type):
    """Metaclass that decorates all class methods for auth."""
    def __init__(cls, name, bases, dict):
        super(protected, cls).__init__(name, bases, dict)
        for name, value in dict.iteritems():
            if type(value)==types.FunctionType and not name.startswith('_'):
                setattr(cls, name, secure()(value))
                if hasattr(value, 'exposed'):
                    cls.__dict__[name].exposed = True
                

class ProtectedClass:
    """Inherit from this class to protect an entire class with auth."""
    __metaclass__ = protected
    def __init__(self,roles):
        self.roles = roles

def secure(roles=None):
    """Decorates a method to only allow access if user has specified role."""
    if roles is None:
        roles = []
    def _wrapper(f):
        def _innerwrapper(self, roles=roles, *args, **kwargs):
            _roles = roles[:]
            # check to see if we should inherit or replace roles
            if f.__dict__.get('inherit', False):
                # this will combine class level roles and method
                # level roles (inheritance)
                if hasattr(self, 'roles'):
                    _roles.extend(self.roles)
                if hasattr(f, 'roles'):
                    _roles.extend(f.roles)
            else:
                # this will apply either class level or method
                # level roles - method level roles take precedence
                if hasattr(self, 'roles'):
                    _roles = self.roles[:]
                if hasattr(f, 'roles'):
                    _roles = f.roles[:]
            return SecureResource(_roles, f, self, *args, **kwargs)
        return _innerwrapper
    return _wrapper

def allow(roles, inherit=False):
    def _wrapper(f):
        f.roles = roles
        f.inherit = inherit
        return f
    return _wrapper

class SecureResource(object):
    def __init__(self, roles, callable, instance, *args, **kwargs):
        self.roles = roles
        self.callable = callable
        self.instance = instance
        self.callable_args = args
        self.callable_kwargs = kwargs

