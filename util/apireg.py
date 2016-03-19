#!/usr/bin/python -OO
# Copyright 2012-2015 The SABnzbd-Team <team@sabnzbd.org>
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
util.apireg - Registration of API connection info
"""

import _winreg


def reg_info(user):
    """ Return the reg key for API """
    if user:
        # Normally use the USER part of the registry
        section = _winreg.HKEY_CURRENT_USER
        keypath = r"Software\SABnzbd"
    else:
        # A Windows Service will use the service key instead
        section = _winreg.HKEY_LOCAL_MACHINE
        keypath = r"SYSTEM\CurrentControlSet\Services\SABnzbd"
    return section, keypath


def get_connection_info(user=True):
    """ Return URL of the API running SABnzbd instance
        'user' == True will first try user's registry, otherwise system is used
    """
    section, keypath = reg_info(user)
    url = None

    try:
        hive = _winreg.ConnectRegistry(None, section)
        key = _winreg.OpenKey(hive, keypath + r'\api')
        for i in range(0, _winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, i)
            if name == 'url':
                url = value

        _winreg.CloseKey(key)
    except WindowsError:
        pass
    finally:
        _winreg.CloseKey(hive)

    # Nothing in user's registry, try system registry
    if user and not url:
        url = get_connection_info(user=False)

    return url


def set_connection_info(url, user=True):
    """ Set API info in register """
    section, keypath = reg_info(user)
    try:
        hive = _winreg.ConnectRegistry(None, section)
        try:
            key = _winreg.CreateKey(hive, keypath)
        except:
            pass
        key = _winreg.OpenKey(hive, keypath)
        mykey = _winreg.CreateKey(key, 'api')
        _winreg.SetValueEx(mykey, 'url', None, _winreg.REG_SZ, url)
        _winreg.CloseKey(mykey)
        _winreg.CloseKey(key)
    except WindowsError:
        if user:
            set_connection_info(url, user=False)
        pass
    finally:
        _winreg.CloseKey(hive)


def del_connection_info(user=True):
    """ Remove API info from register """
    section, keypath = reg_info(user)
    try:
        hive = _winreg.ConnectRegistry(None, section)
        key = _winreg.OpenKey(hive, keypath)
        _winreg.DeleteKey(key, 'api')
        _winreg.CloseKey(key)
    except WindowsError:
        if user:
            del_connection_info(user=False)
        pass
    finally:
        _winreg.CloseKey(hive)


def get_install_lng():
    """ Return language-code used by the installer """
    lng = 0
    try:
        hive = _winreg.ConnectRegistry(None, _winreg.HKEY_LOCAL_MACHINE)
        key = _winreg.OpenKey(hive, r"Software\SABnzbd")
        for i in range(0, _winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, i)
            if name == 'Installer Language':
                lng = value
        _winreg.CloseKey(key)
    except WindowsError:
        pass
    finally:
        _winreg.CloseKey(hive)
    return lng


if __name__ == '__main__':
    print 'URL = %s' % get_connection_info()
    print 'Language = %s' % get_install_lng()
    # del_connection_info()
    # set_connection_info('localhost', '8080', 'blabla', user=False)
