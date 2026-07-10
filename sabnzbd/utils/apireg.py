#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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

import winreg
from typing import Optional, Tuple

# Map from NSIS-codepage to our language-strings
# If you edit this list you also need to edit NSIS_Installer.nsi!
LANGUAGE_MAP = {
    "1029": "cs",
    "1030": "da",
    "1031": "de",
    "1034": "es",
    "1033": "en",
    "1035": "fi",
    "1036": "fr",
    "1037": "he",
    "1040": "it",
    "1043": "nl",
    "1044": "nb",
    "1045": "pl",
    "1046": "pt_BR",
    "1048": "ro",
    "1049": "ru",
    "3098": "sr",
    "1053": "sv",
    "1055": "tr",
    "2052": "zh_CN",
}


def reg_info(user: bool) -> Tuple[int, str]:
    """Return the registry hive and key path for the API info

    The URL of a running instance is stored so that a second start of SABnzbd
    (for example by double-clicking an NZB) can hand off to the running instance
    instead of starting a duplicate. A desktop run stores it per-user in HKCU,
    but a Windows Service runs under a service account whose HKCU is invisible
    to the desktop user, so it uses the machine-wide service key in HKLM instead.
    Readers check HKCU first and fall back to HKLM to find either kind of instance.
    """
    if user:
        # Normally use the USER part of the registry
        return winreg.HKEY_CURRENT_USER, r"Software\SABnzbd\api"
    # A Windows Service will use the service key instead
    return winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\SABnzbd\api"


def get_connection_info(user: bool = True) -> Optional[str]:
    """Return URL of the running SABnzbd instance
    'user' == True will first try user's registry, otherwise system is used
    """
    section, keypath = reg_info(user)
    try:
        with winreg.OpenKey(section, keypath) as key:
            url, _ = winreg.QueryValueEx(key, "url")
            if url:
                return url
    except OSError:
        pass

    # Nothing in user's registry, try system registry
    if user:
        return get_connection_info(user=False)
    return None


def set_connection_info(url: str, user: bool = True):
    """Set API info in registry"""
    section, keypath = reg_info(user)
    try:
        with winreg.CreateKey(section, keypath) as key:
            winreg.SetValueEx(key, "url", None, winreg.REG_SZ, url)
    except OSError:
        if user:
            set_connection_info(url, user=False)


def del_connection_info(user: bool = True):
    """Remove API info from registry"""
    section, keypath = reg_info(user)
    try:
        winreg.DeleteKey(section, keypath)
    except OSError:
        if user:
            del_connection_info(user=False)


def get_install_lng() -> str:
    """Return language-code used by the installer"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SABnzbd") as key:
            lng, _ = winreg.QueryValueEx(key, "Installer Language")
            return LANGUAGE_MAP.get(lng, "en")
    except OSError:
        return "en"


if __name__ == "__main__":
    print(f"URL = {get_connection_info()}")
    print(f"Language = {get_install_lng()}")
