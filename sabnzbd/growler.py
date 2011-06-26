#!/usr/bin/python -OO
# Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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
#
"""
sabnzbd.growler - Send notifications to Growl
"""
#------------------------------------------------------------------------------

import os.path
import logging
import socket

import sabnzbd
import sabnzbd.cfg
from sabnzbd.encoding import unicoder, latin1
from gntp import GNTPRegister
from gntp.notifier import GrowlNotifier
try:
    import Growl
    _HAVE_OSX_GROWL = True
except ImportError:
    _HAVE_OSX_GROWL = False
try:
    import pynotify
    _HAVE_NTFOSD = True
except ImportError:
    _HAVE_NTFOSD = False

#------------------------------------------------------------------------------
# Define translatable message table
TT = lambda x:x
_NOTIFICATION = {
    'startup'  : TT('Startup/Shutdown'),        #: Message class for Growl server
    'download' : TT('Added NZB'),               #: Message class for Growl server
    'pp'       : TT('Post-processing started'), #: Message class for Growl server
    'complete' : TT('Job finished'),            #: Message class for Growl server
    'other'    : TT('Other Messages')           #: Message class for Growl server
}
_KEYS = ('startup', 'download', 'pp', 'complete', 'other')

#------------------------------------------------------------------------------
# Setup platform dependent Growl support
#
_GROWL_ICON = None  # Platform-dependant icon path
_GROWL = None       # Instance of the Notifier after registration
_GROWL_REG = False  # Succesful registration


#------------------------------------------------------------------------------
def get_icon():
    icon = os.path.join(sabnzbd.DIR_PROG, 'sabnzbd.ico')
    if not os.path.isfile(icon):
        icon = None
    return icon


#------------------------------------------------------------------------------
def change_value():
    """ Signal that we should register with a new Growl server
    """
    global _GROWL_REG
    _GROWL_REG = False


#------------------------------------------------------------------------------
def have_growl():
    """ Return if any Growl support is present
    """
    return True

def have_ntfosd():
    """ Return if any PyNotify support is present
    """
    return bool(_HAVE_NTFOSD)


#------------------------------------------------------------------------------
def send_notification(title , msg, gtype):
    """ Send Notification message
    """
    if have_growl():
        send_growl(title, msg, gtype)
    if have_ntfosd():
        send_notify_osd(title, msg)


#------------------------------------------------------------------------------
def register_growl():
    """ Register this app with Growl
    """
    host, port = sabnzbd.misc.split_host(sabnzbd.cfg.growl_server())

    if host:
        sys_name = '@' + sabnzbd.misc.hostname().lower()
    else:
        sys_name = ''

    # Clean up persistent data in GNTP to make re-registration work
    GNTPRegister.notifications = []
    GNTPRegister.headers = {}

    growler = GrowlNotifier(
        applicationName = 'SABnzbd%s' % sys_name,
        applicationIcon = get_icon(),
        notifications = [Tx(_NOTIFICATION[key]) for key in _KEYS],
        hostname = host or None,
        port = port or 23053,
        password = sabnzbd.cfg.growl_password() or None
    )

    try:
        ret = growler.register()
        if ret is None or isinstance(ret, bool):
            logging.info('Registered with Growl')
            ret = growler
        else:
            logging.debug('Cannot register with Growl %s', ret)
            del growler
            ret = None
    except socket.error, err:
        logging.debug('Cannot register with Growl %s', err)
        del growler
        ret = None
    return ret


#------------------------------------------------------------------------------
def send_growl(title , msg, gtype):
    """ Send Growl message
    """
    global _GROWL, _GROWL_REG
    if not sabnzbd.cfg.growl_enable():
        return

    if _HAVE_OSX_GROWL and not sabnzbd.cfg.growl_server():
        send_local_growl(title, msg, gtype)
        return

    for n in (0, 1):
        if not _GROWL_REG: _GROWL = None
        _GROWL = _GROWL or register_growl()
        if _GROWL:
            assert isinstance(_GROWL, GrowlNotifier)
            _GROWL_REG = True
            logging.debug('Send to Growl: %s %s %s', gtype, latin1(title), latin1(msg))
            try:
                ret = _GROWL.notify(
                    noteType = Tx(_NOTIFICATION.get(gtype, 'other')),
                    title = title,
                    description = unicoder(msg),
                    #icon = options.icon,
                    #sticky = options.sticky,
                    #priority = options.priority
                )
                if ret is None or isinstance(ret, bool):
                    return
                elif ret[0] == '401':
                    _GROWL = False
                else:
                    logging.debug('Growl error %s', ret)
                    return
            except socket.error, err:
                logging.debug('Growl error %s', err)
                return
        else:
            return


#------------------------------------------------------------------------------
# Local OSX Growl support
#
if _HAVE_OSX_GROWL:

    if os.path.isfile('sabnzbdplus.icns'):
        _OSX_ICON = Growl.Image.imageFromPath('sabnzbdplus.icns')
    elif os.path.isfile('osx/resources/sabnzbdplus.icns'):
        _OSX_ICON = Growl.Image.imageFromPath('osx/resources/sabnzbdplus.icns')
    else:
        _OSX_ICON = Growl.Image.imageWithIconForApplication('Terminal')

    def send_local_growl(title , msg, gtype):
        """ Send to local Growl server, OSX-only """
        notes = [Tx(_NOTIFICATION[key]) for key in _KEYS]
        growler = Growl.GrowlNotifier(
            applicationName = 'SABnzbd',
            applicationIcon = _OSX_ICON,
            notifications = notes,
            defaultNotifications = notes
            )
        growler.register()
        growler.notify(Tx(_NOTIFICATION.get(gtype, 'other')), title, msg)


#------------------------------------------------------------------------------
# Ubuntu NotifyOSD Support
#
if _HAVE_NTFOSD:
    _NTFOSD = False
    def send_notify_osd(title, message):
        """ Send a message to NotifyOSD
        """
        global _NTFOSD
        if sabnzbd.cfg.ntfosd_enable():
            icon = os.path.join(sabnzbd.DIR_PROG, 'sabnzbd.ico')
            _NTFOSD = _NTFOSD or pynotify.init('icon-summary-body')
            if _NTFOSD:
                logging.info('Send to NotifyOSD: %s / %s', latin1(title), latin1(message))
                note = pynotify.Notification(title, message, icon)
                note.show()
