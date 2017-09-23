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

Recursive par2 scanning post-processing script:

Will check in the completed job folder if there maybe are par2 files,
for example "rename.par2" and use those to check the files.

NOTES:
 1) To use this script you need Python installed on your system and
    select "Add to path" during its installation.
 2) Beware that files on the 'Cleanup List' are removed before
    scripts are called and if any of them happen to be required by
    the found par2 file, it will fail.
 3) If you want to modify this script, make sure to copy it out
    of this directory, or it will be overwritten when SABnzbd is updated.

"""

import os
import sys
import fnmatch
import subprocess

# Are we being called from SABnzbd?
if not os.environ.get('SAB_VERSION'):
    print "This script needs to be called from SABnzbd as post-processing script."
    sys.exit(1)

# Windows or others?
par2_command = os.environ['SAB_PAR2_COMMAND']
if os.environ['SAB_MULTIPAR_COMMAND']:
    par2_command = os.environ['SAB_MULTIPAR_COMMAND']

# Diagnostic info
print '\n------------------------\n'
print 'SABnzbd version: ', os.environ['SAB_VERSION']
print 'Job location: ', os.environ['SAB_COMPLETE_DIR']
print 'Par2-command: ', par2_command
print '\n------------------------\n'

# Search for par2 files
matches = []
for root, dirnames, filenames in os.walk(os.environ['SAB_COMPLETE_DIR']):
    for filename in fnmatch.filter(filenames, '*.par2'):
        matches.append(os.path.join(root, filename))
        print 'Found file:', os.path.join(root, filename)

# Found any?
if not matches:
    print "No par2 files found to process."
    sys.exit(0)

# Run par2 on them
for par2_file in matches:
    # Build command, make it check the whole directory
    wildcard = os.path.join(os.environ['SAB_COMPLETE_DIR'], '*')
    command = [str(par2_command), 'r', par2_file, wildcard]

    # Start command
    print '\n------------------------\n'
    print 'Starting command: ', repr(command)
    try:
        result = subprocess.check_output(command)
    except subprocess.CalledProcessError as e:
        # Multipar also gives non-zero in case of succes
        result = e.output

    # Show output
    print '\n------------------------\n'
    print result

    # Last status-line for the History
    print '\n------------------------\n'

    # Check if the magic words are there
    if 'Repaired successfully' in result or 'All files are correct' in result or \
       'Repair complete' in result or 'All Files Complete' in result or 'PAR File(s) Incomplete' in result:
        print 'Recursive repair/verify finished.'
    else:
        print 'Recursive repair/verify did not complete!'

# Always exit with succes-code
sys.exit(0)
