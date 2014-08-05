#!/usr/bin/env python -OO
#
# Copyright 2008-2014 The SABnzbd-Team <team@sabnzbd.org>
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

import os
import sys
import re

if len(sys.argv) < 2:
    print 'Usage: %s <release>' % os.path.split(sys.argv[0])[1]
    exit(1)

# Setup file names
release = sys.argv[1]
prod = 'SABnzbd-' + release
fileDmg = prod + '-osx.dmg'
fileOSr = prod + '-osx-src.tar.gz'
fileImg = prod + '.sparseimage'
builds = ('sl', 'lion', 'ml')
build_folders = (
        '10.5 (Leopard) 10.6 (S-Leopard)',
        '10.7 (Lion)',
        '10.8 (M-Lion) 10.9 (Mavericks)'
        )

# Check presense of all builds
sharepath = os.environ.get('SHARE')
if not (sharepath and os.path.exists(sharepath)):
    print 'Build share not defined or not found'
    exit(1)

build_paths = []
for build in builds:
    path = os.path.join(sharepath, '%s-%s.cpio' % (prod, build))
    if os.path.exists(path):
        build_paths.append(path)
    else:
        print 'Missing build %s' % path
        exit(1)

# Create sparseimage from template
os.system("unzip -o osx/image/template.sparseimage.zip")
os.rename('template.sparseimage', fileImg)

# mount sparseimage and modify volume label
os.system("hdiutil mount %s | grep /Volumes/SABnzbd >mount.log" % fileImg)

# Rename the volume
fp = open('mount.log', 'r')
data = fp.read()
fp.close()
os.remove('mount.log')
m = re.search(r'/dev/(\w+)\s+', data)
volume = 'SABnzbd-' + str(release)
os.system('diskutil rename %s %s' % (m.group(1), volume))

authority = os.environ.get('SIGNING_AUTH')

# Unpack build into image and sign if possible
for build in xrange(len(builds)):
    vol_path = '/Volumes/%s/%s/' % (volume, build_folders[build])
    os.system('ditto -x -z "%s" "%s"' % (build_paths[build], vol_path))
    if authority:
        app_name = '%s-%s' % (volume, builds[build])
        os.system('codesign -f -i "%s" -s "%s" "%s/SABnzbd.app"' % (app_name, authority, vol_path))


# Put README.rtf in root
from_path = '/Volumes/%s/%s/SABnzbd.app/Contents/Resources/Credits.rtf' % (volume, build_folders[0])
to_path = '/Volumes/%s/README.rtf' % volume
os.system('cp "%s" "%s"' % (from_path, to_path))

# Unmount sparseimage
print 'Eject volume'
os.system("hdiutil eject /Volumes/%s/>/dev/null" % volume)

print 'Wait 1 second'
os.system("sleep 1")

# Convert sparseimage to read-only compressed dmg
print 'Create DMG file'
if os.path.exists(fileDmg):
    os.remove(fileDmg)
os.system("hdiutil convert %s  -format UDBZ -o %s>/dev/null" % (fileImg, fileDmg))

# Remove sparseimage
os.system("rm %s>/dev/null" % fileImg)

print 'Make image internet-enabled'
os.system("hdiutil internet-enable %s" % fileDmg)

print 'Copy GZ file'
os.system('cp "%s" .' % os.path.join(sharepath, fileOSr))
