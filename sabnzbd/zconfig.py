#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.zconfig - bonjour/zeroconfig support
"""

import os
import logging
import cherrypy

_HOST_PORT = (None, None)

try:
    from sabnzbd.utils import pybonjour
    from threading import Thread
    _HAVE_BONJOUR = True
except:
    _HAVE_BONJOUR = False

import sabnzbd
import sabnzbd.cfg as cfg
from sabnzbd.misc import match_str

_BONJOUR_OBJECT = None


def hostname():
    """ Return host's pretty name """
    if sabnzbd.WIN32:
        return os.environ.get('computername', 'unknown')
    try:
        return os.uname()[1]
    except:
        return 'unknown'


def _zeroconf_callback(sdRef, flags, errorCode, name, regtype, domain):
    logging.debug('Full Bonjour-callback sdRef=%s, flags=%s, errorCode=%s, name=%s, regtype=%s, domain=%s',
                  sdRef, flags, errorCode, name, regtype, domain)
    if errorCode == pybonjour.kDNSServiceErr_NoError:
        logging.info('Registered in Bonjour as "%s" (%s)', name, domain)


def set_bonjour(host=None, port=None):
    """ Publish host/port combo through Bonjour """
    global _HOST_PORT, _BONJOUR_OBJECT

    if not _HAVE_BONJOUR or not cfg.enable_bonjour():
        logging.info('No Bonjour/ZeroConfig support installed')
        return

    if host is None and port is None:
        host, port = _HOST_PORT
    else:
        _HOST_PORT = (host, port)

    scope = pybonjour.kDNSServiceInterfaceIndexAny
    zhost = None
    domain = None

    if match_str(host, ('localhost', '127.0.', '::1')):
        logging.info('Bonjour/ZeroConfig does not support "localhost"')
        # All implementations fail to implement "localhost" properly
        # A false address is published even when scope==kDNSServiceInterfaceIndexLocalOnly
        return

    name = hostname()
    if '.local' in name:
        suffix = ''
    else:
        suffix = '.local'
    if hasattr(cherrypy.wsgiserver, 'redirect_url'):
        cherrypy.wsgiserver.redirect_url("https://%s%s:%s/sabnzbd" % (name, suffix, port))
    logging.debug('Try to publish in Bonjour as "%s" (%s:%s)', name, host, port)
    try:
        refObject = pybonjour.DNSServiceRegister(
            interfaceIndex=scope,
            name='SABnzbd on %s:%s' % (name, port),
            regtype='_http._tcp',
            domain=domain,
            host=zhost,
            port=int(port),
            txtRecord=pybonjour.TXTRecord({'path': '/sabnzbd/'}),
            callBack=_zeroconf_callback)
    except sabnzbd.utils.pybonjour.BonjourError:
        _BONJOUR_OBJECT = None
        logging.debug('Failed to start Bonjour service')
    else:
        Thread(target=_bonjour_server, args=(refObject,))
        _BONJOUR_OBJECT = refObject
        logging.debug('Successfully started Bonjour service')


def _bonjour_server(refObject):
    while 1:
        pybonjour.DNSServiceProcessResult(refObject)
        logging.debug('GOT A BONJOUR CALL')


def remove_server():
    """ Remove Bonjour registration """
    global _BONJOUR_OBJECT
    if _BONJOUR_OBJECT:
        _BONJOUR_OBJECT.close()
    _BONJOUR_OBJECT = None
