#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
sabnzbd.wizard - Wizard Webinterface
"""

import os
import cherrypy
import logging
from Cheetah.Template import Template

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.lang import T, list_languages, reset_language
from sabnzbd.utils.servertests import test_nntp_server_dict
from sabnzbd.misc import IntConv
import sabnzbd.interface
import sabnzbd.config as config
import sabnzbd.cfg as cfg

#------------------------------------------------------------------------------
class Wizard:
    def __init__(self, web_dir, root, prim):
        self.__root = root
        # Get the path for the folder named wizard
        self.__web_dir = sabnzbd.WIZARD_DIR
        self.__prim = prim
        self.info = {'webdir': sabnzbd.WIZARD_DIR,
                     'steps':5, 'version':sabnzbd.__version__,
                     'T': T}

    @cherrypy.expose
    def index(self, **kwargs):

        info = self.info.copy()
        info['num'] = ''
        info['number'] = 0
        info['lang'] = cfg.LANGUAGE.get()
        info['languages'] = list_languages(sabnzbd.DIR_LANGUAGE)

        if not os.path.exists(self.__web_dir):
            # If the wizard folder does not exist, simply load the normal page
            raise cherrypy.HTTPRedirect('')
        else:
            template = Template(file=os.path.join(self.__web_dir, 'index.html'),
                                searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
            return template.respond()

    @cherrypy.expose
    def one(self, **kwargs):
        # Handle special options
        language = kwargs.get('lang')
        if language and language != cfg.LANGUAGE.get():
            cfg.LANGUAGE.set(language)
            reset_language(language)

        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('wizard-step-one')
        info['number'] = 1
        info['skin'] = cfg.WEB_DIR.get().lower()

        template = Template(file=os.path.join(self.__web_dir, 'one.html'),
                                searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def two(self, **kwargs):
        # Save skin setting
        if kwargs:
            if 'skin' in kwargs:
                sabnzbd.interface.change_web_dir(kwargs['skin'])

        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('wizard-step-two')
        info['number'] = 2

        host = cfg.CHERRYHOST.get()
        info['host'] = host
        # Allow special operation if host is not one of the defaults
        if host not in ('localhost','0.0.0.0'):
            info['custom_host'] = True
        else:
            info['custom_host'] = False

        if sabnzbd.newswrapper.HAVE_SSL:
            info['have_ssl'] = True
        else:
            info['have_ssl'] = False

        info['enable_https'] = cfg.ENABLE_HTTPS.get()
        info['autobrowser'] = cfg.AUTOBROWSER.get()
        info['web_user'] = cfg.USERNAME.get()
        info['web_pass'] = cfg.PASSWORD.get()

        template = Template(file=os.path.join(self.__web_dir, 'two.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def three(self, **kwargs):
        # Save access/autobrowser/autostart
        if kwargs:
            if 'access' in kwargs:
                cfg.CHERRYHOST.set(kwargs['access'])
            cfg.ENABLE_HTTPS.set(kwargs.get('enable_https',0))
            cfg.AUTOBROWSER.set(kwargs.get('autobrowser',0))
            cfg.USERNAME.set(kwargs.get('web_user', ''))
            cfg.PASSWORD.set(kwargs.get('web_pass', ''))
            if not cfg.USERNAME.get() or not cfg.PASSWORD.get():
                sabnzbd.interface.set_auth(cherrypy.config)
        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('wizard-step-three')
        info['number'] = 3
        info['session'] = cfg.API_KEY.get()

        servers = config.get_servers()
        if not servers:
            info['host'] = ''
            info['port'] = ''
            info['username'] = ''
            info['password'] = ''
            info['connections'] = ''
            info['ssl'] = 0
        else:
            for server in servers:
                # If there are multiple servers, just use the first enabled one
                s = servers[server]
                info['host'] = s.host.get()
                info['port'] = s.port.get()
                info['username'] = s.username.get()
                info['password'] = s.password.get_stars()
                info['connections'] = s.connections.get()
                info['ssl'] = s.ssl.get()
                if s.enable.get():
                    break
        template = Template(file=os.path.join(self.__web_dir, 'three.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def four(self, **kwargs):
        # Save server details
        if kwargs:
            kwargs['enable'] = 1
            sabnzbd.interface.handle_server(kwargs)

        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('wizard-step-four')
        info['number'] = 4
        info['newzbin_user'] = cfg.USERNAME_NEWZBIN.get()
        info['newzbin_pass'] = cfg.PASSWORD_NEWZBIN.get_stars()
        info['newzbin_bookmarks'] = cfg.NEWZBIN_BOOKMARKS.get()
        info['matrix_user'] = cfg.MATRIX_USERNAME.get()
        info['matrix_apikey'] = cfg.MATRIX_APIKEY.get()
        template = Template(file=os.path.join(self.__web_dir, 'four.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def five(self, **kwargs):
        # Save server details
        if kwargs:
            if 'newzbin_user' in kwargs and 'newzbin_pass' in kwargs:
                cfg.USERNAME_NEWZBIN.set(kwargs.get('newzbin_user',''))
                cfg.PASSWORD_NEWZBIN.set(kwargs.get('newzbin_pass',''))
            cfg.NEWZBIN_BOOKMARKS.set(kwargs.get('newzbin_bookmarks', '0'))
            if 'matrix_user' in kwargs and 'matrix_pass' in kwargs:
                cfg.MATRIX_USERNAME.set(kwargs.get('matrix_user',''))
                cfg.MATRIX_APIKEY.set(kwargs.get('matrix_apikey',''))

        config.save_config()

        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('wizard-step-five')
        info['number'] = 5
        info['helpuri'] = 'http://sabnzbd.wikidot.com/'
        info['session'] = cfg.API_KEY.get()

        info['access_url'], info['urls'] = self.get_access_info()

        template = Template(file=os.path.join(self.__web_dir, 'five.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()

    def get_access_info(self):
        ''' Build up a list of url's that sabnzbd can be accessed from '''
        # Access_url is used to provide the user a link to sabnzbd depending on the host
        access_uri = 'localhost'
        cherryhost = cfg.CHERRYHOST.get()

        if cherryhost == '0.0.0.0':
            import socket
            host = socket.gethostname()
            socks = [host]
            # Grab a list of all ips for the hostname
            addresses = socket.getaddrinfo(host, None)
            for addr in addresses:
                address = addr[4][0]
                # Filter out ipv6 addresses (should not be allowed)
                if ':' not in address and address not in socks:
                    socks.append(address)
            if cherrypy.request.headers.has_key('host'):
                host = cherrypy.request.headers['host']
                host = host.rsplit(':')[0]
                access_uri = host
                socks.insert(0, host)
            else:
                socks.insert(0, 'localhost')

        elif cherryhost == '::':
            import socket
            host = socket.gethostname()
            socks = [host]
            # Grab a list of all ips for the hostname
            addresses = socket.getaddrinfo(host, None)
            for addr in addresses:
                address = addr[4][0]
                # Only ipv6 addresses will work
                if ':' in address:
                    address = '[%s]' % address
                    if address not in socks:
                        socks.append(address)
            if cherrypy.request.headers.has_key('host'):
                host = cherrypy.request.headers['host']
                host = host.rsplit(':')[0]
                access_uri = host
                socks.insert(0, host)
            else:
                socks.insert(0, 'localhost')

        elif not cherryhost:
            import socket
            socks = [socket.gethostname()]
            access_uri = socket.gethostname()
        else:
            socks = [cherryhost]
            access_uri = cherryhost

        urls = []
        for sock in socks:
            if sock:
                if cfg.ENABLE_HTTPS.get():
                    url = 'https://%s:%s/sabnzbd/' % (sock, cfg.HTTPS_PORT.get())
                else:
                    url = 'http://%s:%s/sabnzbd/' % (sock, cfg.CHERRYPORT.get())

                urls.append(url)

        if cfg.ENABLE_HTTPS.get():
            access_url = 'https://%s:%s/sabnzbd/' % (access_uri, cfg.HTTPS_PORT.get())
        else:
            access_url = 'http://%s:%s/sabnzbd/' % (access_uri, cfg.CHERRYPORT.get())

        return access_url, urls

    @cherrypy.expose
    def servertest(self, **kwargs):
        result, msg = test_nntp_server_dict(kwargs)
        return msg
