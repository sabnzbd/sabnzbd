# ------------------------------------------------------------------------------------------------
# This file is an excerpt from Sick Beard's browser.py
# Modified and improved to fit SABnzbd.
#
# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard. If not, see <http://www.gnu.org/licenses/>.

import os
import sabnzbd

if os.name == "nt":
    import win32api
    import win32con
    import win32file
    from ctypes import windll

    MASK = win32con.FILE_ATTRIBUTE_DIRECTORY | win32con.FILE_ATTRIBUTE_HIDDEN
    TMASK = win32con.FILE_ATTRIBUTE_DIRECTORY
    DRIVES = (2, 3, 4)
    NT = True
else:
    NT = False

_JUNKFOLDERS = (
    "boot",
    "bootmgr",
    "cache",
    "msocache",
    "recovery",
    "$recycle.bin",
    "recycler",
    "system volume information",
    "temporary internet files",
    "perflogs",  # windows specific
    ".fseventd",
    ".spotlight",
    ".trashes",
    ".vol",
    "cachedmessages",
    "caches",
    "trash",  # osx specific
)


def get_win_drives():
    """ Return list of detected drives, adapted from:
        http://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python/827490
    """
    assert NT
    drives = []
    bitmask = windll.kernel32.GetLogicalDrives()
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if (bitmask & 1) and win32file.GetDriveType("%s:\\" % letter) in DRIVES:
            drives.append(letter)
        bitmask >>= 1
    return drives


def folders_at_path(path, include_parent=False, show_hidden=False):
    """ Returns a list of dictionaries with the folders contained at the given path
        Give the empty string as the path to list the contents of the root path
        under Unix this means "/", on Windows this will be a list of drive letters)
    """
    if path == "":
        if NT:
            entries = [{"name": letter + ":\\", "path": letter + ":\\"} for letter in get_win_drives()]
            entries.insert(0, {"current_path": "Root"})
            return entries
        else:
            path = "/"

    # Walk up the tree until we find a valid path
    path = sabnzbd.filesystem.real_path(sabnzbd.DIR_HOME, path)
    while path and not os.path.isdir(path):
        if path == os.path.dirname(path):
            return folders_at_path("", include_parent)
        else:
            path = os.path.dirname(path)

    # Fix up the path and find the parent
    path = os.path.abspath(os.path.normpath(path))
    parent_path = os.path.dirname(path)

    # If we're at the root then the next step is the meta-node showing our drive letters
    if path == parent_path and NT:
        parent_path = ""

    # List all files and folders
    file_list = []
    for filename in os.listdir(path):
        fpath = os.path.join(path, filename)
        try:
            if NT:
                # Remove hidden folders
                list_folder = (win32api.GetFileAttributes(fpath) & MASK) == TMASK
            elif not show_hidden:
                list_folder = not filename.startswith(".")
            else:
                list_folder = True
        except:
            list_folder = False

        # Remove junk and sort results
        if list_folder and os.path.isdir(fpath) and filename.lower() not in _JUNKFOLDERS:
            file_list.append(
                {"name": sabnzbd.filesystem.clip_path(filename), "path": sabnzbd.filesystem.clip_path(fpath)}
            )

    # Sort results
    file_list = sorted(file_list, key=lambda x: os.path.basename(x["name"]).lower())

    # Add current path
    file_list.insert(0, {"current_path": sabnzbd.filesystem.clip_path(path)})
    if include_parent and parent_path != path:
        file_list.insert(1, {"name": "..", "path": sabnzbd.filesystem.clip_path(parent_path)})

    return file_list
