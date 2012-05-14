#!/usr/bin/python -OO
# Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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
from Cheetah.Template import Template

import sabnzbd
from sabnzbd.constants import *
import sabnzbd.api
from sabnzbd.lang import list_languages, set_language
from sabnzbd.utils.servertests import test_nntp_server_dict
from sabnzbd.api import Ttemplate
import sabnzbd.interface
import sabnzbd.config as config
import sabnzbd.cfg as cfg

#------------------------------------------------------------------------------
class Wizard(object):
    def __init__(self, web_dir, root, prim):
        self.__root = root
        # Get the path for the folder named wizard
        self.__web_dir = sabnzbd.WIZARD_DIR
        self.__prim = prim
        self.info = {'webdir': sabnzbd.WIZARD_DIR,
                     'steps':4, 'version':sabnzbd.__version__,
                     'T': T}

    @cherrypy.expose
    def index(self, **kwargs):
        """ Show the language selection page """
        info = self.info.copy()
        info['num'] = ''
        info['number'] = 0
        info['lang'] = cfg.language()
        info['languages'] = list_languages()
        info['T'] = Ttemplate

        if not os.path.exists(self.__web_dir):
            # If the wizard folder does not exist, simply load the normal page
            raise cherrypy.HTTPRedirect('')
        else:
            template = Template(file=os.path.join(self.__web_dir, 'index.html'),
                                searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
            return template.respond()

    @cherrypy.expose
    def exit(self, **kwargs):
        """ Stop SABnzbd """
        yield "Initiating shutdown..."
        sabnzbd.halt()
        yield "<br>SABnzbd-%s shutdown finished" % sabnzbd.__version__
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True

    @cherrypy.expose
    def one(self, **kwargs):
        """ Accept language and show server page """
        language = kwargs.get('lang')
        cfg.language.set(language)
        set_language(language)
        sabnzbd.api.clear_trans_cache()

        # Always setup Plush
        sabnzbd.interface.change_web_dir('Plush - Gold')

        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('Step One')
        info['number'] = 1
        info['session'] = cfg.api_key()
        info['language'] = cfg.language()
        info['T'] = Ttemplate
        info['have_ssl'] = bool(sabnzbd.newswrapper.HAVE_SSL)

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
                info['host'] = s.host()
                info['port'] = s.port()
                info['username'] = s.username()
                info['password'] = s.password.get_stars()
                info['connections'] = s.connections()

                info['ssl'] = s.ssl()
                if s.enable():
                    break
        template = Template(file=os.path.join(self.__web_dir, 'one.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()


    @cherrypy.expose
    def two(self, **kwargs):
        """ Accept server and show internal web server page """
        # Save server details
        if kwargs:
            kwargs['enable'] = 1
            sabnzbd.interface.handle_server(kwargs)

        # Create web server page
        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('Step Two')
        info['number'] = 2
        info['T'] = Ttemplate

        host = cfg.cherryhost()
        info['host'] = host
        # Allow special operation if host is not one of the defaults
        if host not in ('localhost','0.0.0.0'):
            info['custom_host'] = True
        else:
            info['custom_host'] = False

        info['have_ssl'] = bool(sabnzbd.newswrapper.HAVE_SSL)
        info['enable_https'] = cfg.enable_https()
        info['autobrowser'] = cfg.autobrowser()
        info['web_user'] = cfg.username()
        info['web_pass'] = cfg.password()

        template = Template(file=os.path.join(self.__web_dir, 'two.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()


    @cherrypy.expose
    def three(self, **kwargs):
        """ Accept webserver parms and show Indexers page """
        if kwargs:
            if 'access' in kwargs:
                cfg.cherryhost.set(kwargs['access'])
            cfg.enable_https.set(kwargs.get('enable_https',0))
            cfg.autobrowser.set(kwargs.get('autobrowser',0))
            cfg.username.set(kwargs.get('web_user', ''))
            cfg.password.set(kwargs.get('web_pass', ''))
            if not cfg.username() or not cfg.password():
                sabnzbd.interface.set_auth(cherrypy.config)

        # Create Indexers page
        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('Step Three')
        info['number'] = 3
        info['newzbin_user'] = cfg.newzbin_username()
        info['newzbin_pass'] = cfg.newzbin_password.get_stars()
        info['newzbin_bookmarks'] = cfg.newzbin_bookmarks()
        info['newzbin_url'] = cfg.newzbin_url()
        info['matrix_user'] = cfg.matrix_username()
        info['matrix_apikey'] = cfg.matrix_apikey()
        info['T'] = Ttemplate
        template = Template(file=os.path.join(self.__web_dir, 'three.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()

    @cherrypy.expose
    def four(self, **kwargs):
        """ Accept Indexers and show Restart screen """
        if kwargs:
            if 'newzbin_user' in kwargs and 'newzbin_pass' in kwargs:
                cfg.newzbin_username.set(kwargs.get('newzbin_user',''))
                cfg.newzbin_password.set(kwargs.get('newzbin_pass',''))
            cfg.newzbin_bookmarks.set(kwargs.get('newzbin_bookmarks', '0'))
            if 'matrix_user' in kwargs and 'matrix_apikey' in kwargs:
                cfg.matrix_username.set(kwargs.get('matrix_user',''))
                cfg.matrix_apikey.set(kwargs.get('matrix_apikey',''))

        config.save_config()

        # Show Restart screen
        info = self.info.copy()
        info['num'] = '&raquo; %s' % T('Step Four')
        info['number'] = 4
        info['helpuri'] = 'http://wiki.sabnzbd.org/'
        info['session'] = cfg.api_key()

        info['access_url'], info['urls'] = self.get_access_info()
        info['T'] = Ttemplate

        template = Template(file=os.path.join(self.__web_dir, 'four.html'),
                            searchList=[info], compilerSettings=sabnzbd.interface.DIRECTIVES)
        return template.respond()

    def get_access_info(self):
        ''' Build up a list of url's that sabnzbd can be accessed from '''
        # Access_url is used to provide the user a link to sabnzbd depending on the host
        access_uri = 'localhost'
        cherryhost = cfg.cherryhost()

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
                if cfg.enable_https():
                    url = 'https://%s:%s/sabnzbd/' % (sock, cfg.https_port())
                else:
                    url = 'http://%s:%s/sabnzbd/' % (sock, cfg.cherryport())

                urls.append(url)

        if cfg.enable_https():
            access_url = 'https://%s:%s/sabnzbd/' % (access_uri, cfg.https_port())
        else:
            access_url = 'http://%s:%s/sabnzbd/' % (access_uri, cfg.cherryport())

        return access_url, urls

    @cherrypy.expose
    def servertest(self, **kwargs):
        result, msg = test_nntp_server_dict(kwargs)
        return msg
