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

# this is for the drive letter code, it only works on windows
if os.name == 'nt':
    from ctypes import windll

# adapted from http://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python/827490
def get_win_drives():
    """ Return list of detected drives """
    assert os.name == 'nt'
    drives = []
    bitmask = windll.kernel32.GetLogicalDrives() #@UndefinedVariable
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        if bitmask & 1:
            drives.append(letter)
        bitmask >>= 1
    return drives

def folders_at_path(path, include_parent = False):
    """ Returns a list of dictionaries with the folders contained at the given path
        Give the empty string as the path to list the contents of the root path
        under Unix this means "/", on Windows this will be a list of drive letters)
        from sabnzbd.encoding import unicoder
        assert os.path.isabs(path) or path == ""
    """
    from sabnzbd.encoding import unicoder

    # walk up the tree until we find a valid path
    while path and not os.path.isdir(path):
        if path == os.path.dirname(path):
            path = ''
            break
        else:
            path = os.path.dirname(path)

    if path == "":
        if os.name == 'nt':
            entries = [{'name': letter + ':\\', 'path': letter + ':\\'} for letter in get_win_drives()]
            entries.insert(0, {'current_path': 'Root'})
            return entries
        else:
            path = '/'

    # fix up the path and find the parent
    path = os.path.abspath(os.path.normpath(path))
    parent_path = os.path.dirname(path)

    # if we're at the root then the next step is the meta-node showing our drive letters
    if path == parent_path and os.name == 'nt':
        parent_path = ""

    file_list = [{ 'name': unicoder(filename), 'path': unicoder(os.path.join(path, filename)) } for filename in os.listdir(path)]
    file_list = filter(lambda entry: os.path.isdir(entry['path']), file_list)
    file_list = sorted(file_list, lambda x, y: cmp(os.path.basename(x['name']).lower(), os.path.basename(y['path']).lower()))

    file_list.insert(0, {'current_path': path})
    if include_parent and parent_path != path:
        file_list.insert(1,{ 'name': "..", 'path': parent_path })

    return file_list

