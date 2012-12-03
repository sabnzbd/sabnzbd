#------------------------------------------------------------------------------------------------
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
if os.name == 'nt':
    import win32api, win32con, win32file
    MASK = win32con.FILE_ATTRIBUTE_DIRECTORY | win32con.FILE_ATTRIBUTE_HIDDEN
    TMASK = win32con.FILE_ATTRIBUTE_DIRECTORY
    DRIVES = (2, 3, 4)
    NT = True
else:
    NT = False

import sabnzbd

_JUNKFOLDERS = (
        'boot', 'bootmgr', 'cache', 'msocache', 'recovery', '$recycle.bin', 'recycler',
        'system volume information', 'temporary internet files', # windows specific
        '.fseventd', '.spotlight', '.trashes', '.vol', 'cachedmessages', 'caches', 'trash' # osx specific
        )

# this is for the drive letter code, it only works on windows
if os.name == 'nt':
    from ctypes import windll

# adapted from http://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python/827490
def get_win_drives():
    """ Return list of detected drives """
    assert NT
    drives = []
    bitmask = windll.kernel32.GetLogicalDrives()
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        if (bitmask & 1) and win32file.GetDriveType('%s:\\' % letter) in DRIVES:
            drives.append(letter)
        bitmask >>= 1
    return drives

def folders_at_path(path, include_parent = False):
    """ Returns a list of dictionaries with the folders contained at the given path
        Give the empty string as the path to list the contents of the root path
        under Unix this means "/", on Windows this will be a list of drive letters)
    """
    from sabnzbd.encoding import unicoder

    if path == "":
        if NT:
            entries = [{'name': letter + ':\\', 'path': letter + ':\\'} for letter in get_win_drives()]
            entries.insert(0, {'current_path': 'Root'})
            return entries
        else:
            path = '/'

    # walk up the tree until we find a valid path
    path = sabnzbd.misc.real_path(sabnzbd.DIR_HOME, path)
    while path and not os.path.isdir(path):
        if path == os.path.dirname(path):
            return folders_at_path('', include_parent)
        else:
            path = os.path.dirname(path)

    # fix up the path and find the parent
    path = os.path.abspath(os.path.normpath(path))
    parent_path = os.path.dirname(path)

    # if we're at the root then the next step is the meta-node showing our drive letters
    if path == parent_path and os.name == 'nt':
        parent_path = ""

    file_list = []
    try:
        for filename in os.listdir(path):
            fpath = os.path.join(path, filename)
            try:
                if NT:
                    doit = (win32api.GetFileAttributes(fpath) & MASK) == TMASK and filename != 'PerfLogs'
                else:
                    doit = not filename.startswith('.')
            except:
                doit = False
            if doit:
                file_list.append({ 'name': unicoder(filename), 'path': unicoder(fpath) })
        file_list = filter(lambda entry: os.path.isdir(entry['path']), file_list)
        file_list = filter(lambda entry: entry['name'].lower() not in _JUNKFOLDERS, file_list)
        file_list = sorted(file_list, lambda x, y: cmp(os.path.basename(x['name']).lower(), os.path.basename(y['path']).lower()))
    except:
        # No access, ignore
        pass
    file_list.insert(0, {'current_path': path})
    if include_parent and parent_path != path:
        file_list.insert(1,{ 'name': "..", 'path': parent_path })

    return file_list

