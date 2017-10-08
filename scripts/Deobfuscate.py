#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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

Deobfuscation post-processing script:

Will check in the completed job folder if maybe there are par2 files,
for example "rename.par2", and use those to rename the files.
If there is no "rename.par2" available, it will rename the largest
file to the job-name in the queue.

NOTES:
 1) To use this script you need Python installed on your system and
    select "Add to path" during its installation. Select this folder in
    Config > Folders > Scripts Folder and select this script for each job
    you want it sued for, or link it to a category in Config > Categories.
 2) Beware that files on the 'Cleanup List' are removed before
    scripts are called and if any of them happen to be required by
    the found par2 file, it will fail.
 3) If there are multiple larger (>40MB) files, then the script will not
    rename anything, since it could be a multi-pack.
 4) If you want to modify this script, make sure to copy it out
    of this directory, or it will be overwritten when SABnzbd is updated.
 5) Feedback or bugs in this script can be reported in on our forum:
    https://forums.sabnzbd.org/viewforum.php?f=9

"""

import os
import sys
import time
import fnmatch
import subprocess

# Files to exclude and minimal file size for renaming
EXCLUDED_FILE_EXTS = ('.vob', '.bin')
MIN_FILE_SIZE = 40*1024*1024

# Are we being called from SABnzbd?
if not os.environ.get('SAB_VERSION'):
    print("This script needs to be called from SABnzbd as post-processing script.")
    sys.exit(1)

def print_splitter():
    """ Simple helper function """
    print('\n------------------------\n')

# Windows or others?
par2_command = os.environ['SAB_PAR2_COMMAND']
if os.environ['SAB_MULTIPAR_COMMAND']:
    par2_command = os.environ['SAB_MULTIPAR_COMMAND']

# Diagnostic info
print_splitter()
print(('SABnzbd version: ', os.environ['SAB_VERSION']))
print(('Job location: ', os.environ['SAB_COMPLETE_DIR']))
print(('Par2-command: ', par2_command))
print_splitter()

# Search for par2 files
matches = []
for root, dirnames, filenames in os.walk(os.environ['SAB_COMPLETE_DIR']):
    for filename in fnmatch.filter(filenames, '*.par2'):
        matches.append(os.path.join(root, filename))
        print(('Found file:', os.path.join(root, filename)))

# Found any par2 files we can use?
run_renamer = True
if not matches:
    print("No par2 files found to process.")

# Run par2 from SABnzbd on them
for par2_file in matches:
    # Build command, make it check the whole directory
    wildcard = os.path.join(os.environ['SAB_COMPLETE_DIR'], '*')
    command = [str(par2_command), 'r', par2_file, wildcard]

    # Start command
    print_splitter()
    print(('Starting command: ', repr(command)))
    try:
        result = subprocess.check_output(command)
    except subprocess.CalledProcessError as e:
        # Multipar also gives non-zero in case of succes
        result = e.output

    # Show output
    print_splitter()
    print(result)
    print_splitter()

    # Last status-line for the History
    # Check if the magic words are there
    if 'Repaired successfully' in result or 'All files are correct' in result or \
       'Repair complete' in result or 'All Files Complete' in result or 'PAR File(s) Incomplete' in result:
        print('Recursive repair/verify finished.')
        run_renamer = False
    else:
        print('Recursive repair/verify did not complete!')


# No matches? Then we try to rename the largest file to the job-name
if run_renamer:
    print_splitter()
    print('Trying to see if there are large files to rename')
    print_splitter()

    # If there are more larger files, we don't rename
    largest_file = None
    for root, dirnames, filenames in os.walk(os.environ['SAB_COMPLETE_DIR']):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            file_size = os.path.getsize(full_path)
            # Do we count this file?
            if file_size > MIN_FILE_SIZE and os.path.splitext(filename)[1].lower() not in EXCLUDED_FILE_EXTS:
                # Did we already found one?
                if largest_file:
                    print(('Found:', largest_file))
                    print(('Found:', full_path))
                    print_splitter()
                    print('Found multiple larger files, aborting.')
                    largest_file = None
                    break
                largest_file = full_path

    # Found something large enough?
    if largest_file:
        # We don't need to do any cleaning of dir-names
        # since SABnzbd already did that!
        new_name = '%s%s' % (os.path.join(os.environ['SAB_COMPLETE_DIR'], os.environ['SAB_FINAL_NAME']), os.path.splitext(largest_file)[1].lower())
        print(('Renaming %s to %s' % (largest_file, new_name)))

        # With retries for Windows
        for r in range(3):
            try:
                os.rename(largest_file, new_name)
                print('Renaming done!')
                break
            except:
                time.sleep(1)
    else:
        print('No par2 files or large files found')

# Always exit with succes-code
sys.exit(0)
