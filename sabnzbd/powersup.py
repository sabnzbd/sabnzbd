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
sabnzbd.powersup - System power management support
"""

import os
import subprocess
import logging
import time


##############################################################################
# Power management for Windows
##############################################################################

def win_hibernate():
    """ Hibernate Windows system, returns after wakeup """
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Hibernate")
        time.sleep(10)
    except:
        logging.error(T('Failed to hibernate system'))
        logging.info("Traceback: ", exc_info=True)


def win_standby():
    """ Standby Windows system, returns after wakeup """
    try:
        subprocess.Popen("rundll32 powrprof.dll,SetSuspendState Standby")
        time.sleep(10)
    except:
        logging.error(T('Failed to standby system'))
        logging.info("Traceback: ", exc_info=True)


def win_shutdown():
    """ Shutdown Windows system, never returns """
    try:
        import win32security
        import win32api
        import ntsecuritycon

        flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES | ntsecuritycon.TOKEN_QUERY
        htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
        id_ = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_SHUTDOWN_NAME)
        newPrivileges = [(id_, ntsecuritycon.SE_PRIVILEGE_ENABLED)]
        win32security.AdjustTokenPrivileges(htoken, 0, newPrivileges)
        win32api.InitiateSystemShutdown("", "", 30, 1, 0)
    finally:
        os._exit(0)


##############################################################################
# Power management for OSX
##############################################################################

def osx_shutdown():
    """ Shutdown OSX system, never returns """
    try:
        subprocess.call(['osascript', '-e', 'tell app "System Events" to shut down'])
    except:
        logging.error(T('Error while shutting down system'))
        logging.info("Traceback: ", exc_info=True)
    os._exit(0)


def osx_standby():
    """ Make OSX system sleep, returns after wakeup """
    try:
        subprocess.call(['osascript', '-e', 'tell app "System Events" to sleep'])
        time.sleep(10)
    except:
        logging.error(T('Failed to standby system'))
        logging.info("Traceback: ", exc_info=True)


def osx_hibernate():
    """ Make OSX system sleep, returns after wakeup """
    osx_standby()


##############################################################################
# Power management for Linux
##############################################################################

#    Requires DBus plus either HAL [1] or the more modern ConsoleKit [2] and
#    DeviceKit(-power) [3]. HAL will eventually be deprecated but older systems
#    might still use it.
#    [1] http://people.freedesktop.org/~hughsient/temp/dbus-interface.html
#    [2] http://www.freedesktop.org/software/ConsoleKit/doc/ConsoleKit.html
#    [3] http://hal.freedesktop.org/docs/DeviceKit-power/
#
#    Original code was contributed by Marcel de Vries <marceldevries@phannet.cc>
#

try:
    import dbus
    HAVE_DBUS = True
except ImportError:
    HAVE_DBUS = False


def _get_sessionproxy():
    """ Return (proxy-object, interface), (None, None) if not available """
    name = 'org.freedesktop.PowerManagement'
    path = '/org/freedesktop/PowerManagement'
    interface = 'org.freedesktop.PowerManagement'
    try:
        bus = dbus.SessionBus()
        return bus.get_object(name, path), interface
    except dbus.exceptions.DBusException:
        return None, None


def _get_systemproxy(method):
    """ Return (proxy-object, interface, pinterface), (None, None, None) if not available """
    if method == 'ConsoleKit':
        name = 'org.freedesktop.ConsoleKit'
        path = '/org/freedesktop/ConsoleKit/Manager'
        interface = 'org.freedesktop.ConsoleKit.Manager'
        pinterface = None
    elif method == 'DeviceKit':
        name = 'org.freedesktop.DeviceKit.Power'
        path = '/org/freedesktop/DeviceKit/Power'
        interface = 'org.freedesktop.DeviceKit.Power'
        pinterface = 'org.freedesktop.DBus.Properties'
    elif method == 'UPower':
        name = 'org.freedesktop.UPower'
        path = '/org/freedesktop/UPower'
        interface = 'org.freedesktop.UPower'
        pinterface = 'org.freedesktop.DBus.Properties'
    try:
        bus = dbus.SystemBus()
        return bus.get_object(name, path), interface, pinterface
    except dbus.exceptions.DBusException, msg:
        logging.info('DBus not reachable (%s)', msg)
        return None, None, None


def linux_shutdown():
    """ Make Linux system shutdown, never returns """
    if not HAVE_DBUS:
        os._exit(0)

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanShutdown():
            proxy.Shutdown(dbus_interface=interface)
    else:
        proxy, interface, _pinterface = _get_systemproxy('ConsoleKit')
        if proxy:
            if proxy.CanStop(dbus_interface=interface):
                try:
                    proxy.Stop(dbus_interface=interface)
                except dbus.exceptions.DBusException, msg:
                    logging.info('Received a DBus exception %s', msg)
        else:
            logging.info('DBus does not support Stop (shutdown)')
    os._exit(0)


def linux_hibernate():
    """ Make Linux system go into hibernate, returns after wakeup """
    if not HAVE_DBUS:
        return

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanHibernate():
            proxy.Hibernate(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('UPower')
        if not proxy:
            proxy, interface, pinterface = _get_systemproxy('DeviceKit')
        if proxy:
            if proxy.Get(interface, 'can-hibernate', dbus_interface=pinterface):
                try:
                    proxy.Hibernate(dbus_interface=interface)
                except dbus.exceptions.DBusException, msg:
                    logging.info('Received a DBus exception %s', msg)
        else:
            logging.info('DBus does not support Hibernate')
    time.sleep(10)


def linux_standby():
    """ Make Linux system go into standby, returns after wakeup """
    if not HAVE_DBUS:
        return

    proxy, interface = _get_sessionproxy()
    if proxy:
        if proxy.CanSuspend():
            proxy.Suspend(dbus_interface=interface)
    else:
        proxy, interface, pinterface = _get_systemproxy('UPower')
        if not proxy:
            proxy, interface, pinterface = _get_systemproxy('DeviceKit')
        if proxy:
            if proxy.Get(interface, 'can-suspend', dbus_interface=pinterface):
                try:
                    proxy.Suspend(dbus_interface=interface)
                except dbus.exceptions.DBusException, msg:
                    logging.info('Received a DBus exception %s', msg)
        else:
            logging.info('DBus does not support Suspend (standby)')
    time.sleep(10)
