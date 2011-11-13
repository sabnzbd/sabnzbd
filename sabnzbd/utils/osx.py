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
from sabnzbd.encoding import unicoder, latin1
import gntp
import gntp.notifier

try:
    import Growl
    import platform
    # If running on OSX-Lion and classic Growl (older than 1.3) is absent, assume GNTP-only
    if [int(n) for n in platform.mac_ver()[0].split('.')] >= [10, 7, 0]:
        _HAVE_OSX_GROWL = os.path.isfile('/Library/PreferencePanes/Growl.prefPane/Contents/MacOS/Growl')
    else:
        _HAVE_OSX_GROWL = True
except ImportError:
    _HAVE_OSX_GROWL = False

#------------------------------------------------------------------------------
# Define translatable message table
NOTIFICATION = {'startup':'1. On Startup/Shutdown','download':'2. On adding NZB','pp':'3. On post-processing','complete':'4. On download terminated','other':'5. Other Messages'}

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
def register_growl():
    """ Register this app with Growl
    """
    error = None

    # Clean up persistent data in GNTP to make re-registration work
    gntp.GNTPRegister.notifications = []
    gntp.GNTPRegister.headers = {}

    growler = gntp.notifier.GrowlNotifier(
        applicationName = 'SABnzbd',
        applicationIcon = get_icon(),
        notifications = sorted(NOTIFICATION.values()),
        hostname = None,
        port = 23053,
        password = None
    )

    try:
        ret = growler.register()
        if ret is None or isinstance(ret, bool):
            logging.info('Registered with Growl')
            ret = growler
        else:
            error = 'Cannot register with Growl %s' % ret
            logging.debug(error)
            del growler
            ret = None
    except socket.error, err:
        error = 'Cannot register with Growl %s' % err
        logging.debug(error)
        del growler
        ret = None
    except:
        error = 'Unknown Growl registration error'
        logging.debug(error)
        del growler
        ret = None

    return ret, error


#------------------------------------------------------------------------------
def sendGrowlMsg(title , msg, gtype):
    """ Send Growl message
    """
    global _GROWL, _GROWL_REG

    if not sabnzbd.cfg.growl_enable() or not sabnzbd.DARWIN:
        return

    if _HAVE_OSX_GROWL:
        res = send_local_growl(title, msg, gtype)
        return res

    for n in (0, 1):
        if not _GROWL_REG: _GROWL = None
        if not _GROWL:
            _GROWL, error = register_growl()
        if _GROWL:
            assert isinstance(_GROWL, gntp.notifier.GrowlNotifier)
            _GROWL_REG = True
            #logging.debug('Send to Growl: %s %s %s', gtype, latin1(title), latin1(msg))
            try:
                ret = _GROWL.notify(
                    noteType = gtype,
                    title = title,
                    description = unicoder(msg),
                    #icon = options.icon,
                    #sticky = options.sticky,
                    #priority = options.priority
                )
                if ret is None or isinstance(ret, bool):
                    return None
                elif ret[0] == '401':
                    _GROWL = False
                else:
                    logging.debug('Growl error %s', ret)
                    return 'Growl error %s', ret
            except socket.error, err:
                error = 'Growl error %s' % err
                logging.debug(error)
                return error
            except:
                error = 'Growl error (unknown)'
                logging.debug(error)
                return error
        else:
            return error
    return None

#------------------------------------------------------------------------------
# Local OSX Growl support
#
if _HAVE_OSX_GROWL:
    _local_growl = None
    if os.path.isfile('sabnzbdplus.icns'):
        _OSX_ICON = Growl.Image.imageFromPath('sabnzbdplus.icns')
    elif os.path.isfile('osx/resources/sabnzbdplus.icns'):
        _OSX_ICON = Growl.Image.imageFromPath('osx/resources/sabnzbdplus.icns')
    else:
        _OSX_ICON = Growl.Image.imageWithIconForApplication('Terminal')

    def send_local_growl(title , msg, gtype):
        """ Send to local Growl server, OSX-only """
        global _local_growl
        if not _local_growl:
            notes = sorted(NOTIFICATION.values())
            _local_growl = Growl.GrowlNotifier(
                applicationName = 'SABnzbd',
                applicationIcon = _OSX_ICON,
                notifications = notes,
                defaultNotifications = notes
                )
            _local_growl.register()
        _local_growl.notify(gtype, title, msg)
        return None
