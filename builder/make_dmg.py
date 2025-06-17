#!/usr/bin/python3 -OO
# Copyright 2008-2025 by The SABnzbd-Team (sabnzbd.org)
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

import os
from constants import RELEASE_VERSION


# We need to call dmgbuild from command-line, so here we can setup how
if __name__ == "__main__":
    # Check for DMGBuild
    try:
        import dmgbuild
    except Exception:
        print("Requires dmgbuild-module, use pip install dmgbuild")
        exit()

    # Make sure we are in the src folder
    if not os.path.exists("builder"):
        raise FileNotFoundError("Run from the main SABnzbd source folder: python builder/package.py")

    # Check if signing is possible
    authority = os.environ.get("SIGNING_AUTH")

    # Extract version info and set DMG path
    # Create sub-folder to upload later
    release = RELEASE_VERSION
    prod = "SABnzbd-" + release
    fileDmg = prod + "-macos.dmg"

    # Path to app file
    apppath = "dist/SABnzbd.app"

    # Copy Readme
    readmepath = os.path.join(apppath, "Contents/Resources/README.txt")

    # Path to background and the icon
    backgroundpath = "builder/macos/image/sabnzbd_new_bg.png"
    iconpath = "builder/macos/image/sabnzbdplus.icns"

    # Make DMG
    print("Building DMG")
    dmgbuild.build_dmg(
        filename=fileDmg,
        volume_name=prod,
        settings_file="builder/make_dmg.py",
        defines={"app": apppath, "readme": readmepath, "background": backgroundpath, "iconpath": iconpath},
    )

    # Resign APP
    if authority:
        print("Siging DMG")
        os.system('codesign --deep -f -i "org.sabnzbd.SABnzbd" -s "%s" "%s"' % (authority, fileDmg))
        print("Signed!")
    else:
        print("Signing skipped, missing SIGNING_AUTH.")
    exit()


### START OF DMGBUILD SETTINGS
### COPIED AND MODIFIED FROM THE EXAMPLE ONLINE
application = defines.get("app", "AppName.app")
readme = defines.get("readme", "ReadMe.rtf")
appname = os.path.basename(application)

# .. Basics ....................................................................

# Volume format (see hdiutil create -help)
format = defines.get("format", "UDBZ")

# Volume size (must be large enough for your files)
size = defines.get("size", "100M")

# Files to include
files = [application, readme]

# Symlinks to create
symlinks = {"Applications": "/Applications"}

# Volume icon
#
# You can either define icon, in which case that icon file will be copied to the
# image, *or* you can define badge_icon, in which case the icon file you specify
# will be used to badge the system's Removable Disk icon
#
badge_icon = defines.get("iconpath", "")

# Where to put the icons
icon_locations = {readme: (70, 160), appname: (295, 220), "Applications": (510, 220)}

# .. Window configuration ......................................................

# Window position in ((x, y), (w, h)) format
window_rect = ((100, 100), (660, 360))

# Background
#
# This is a STRING containing any of the following:
#
#    #3344ff          - web-style RGB color
#    #34f             - web-style RGB color, short form (#34f == #3344ff)
#    rgb(1,0,0)       - RGB color, each value is between 0 and 1
#    hsl(120,1,.5)    - HSL (hue saturation lightness) color
#    hwb(300,0,0)     - HWB (hue whiteness blackness) color
#    cmyk(0,1,0,0)    - CMYK color
#    goldenrod        - X11/SVG named color
#    builtin-arrow    - A simple built-in background with a blue arrow
#    /foo/bar/baz.png - The path to an image file
#
# Other color components may be expressed either in the range 0 to 1, or
# as percentages (e.g. 60% is equivalent to 0.6).
background = defines.get("background", "builtin-arrow")

show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 0

# Select the default view; must be one of
#
#    'icon-view'
#    'list-view'
#    'column-view'
#    'coverflow'
#
default_view = "icon-view"

# General view configuration
show_icon_preview = False

# Set these to True to force inclusion of icon/list view settings (otherwise
# we only include settings for the default view)
include_icon_view_settings = "auto"
include_list_view_settings = "auto"

# .. Icon view configuration ...................................................

arrange_by = None
grid_offset = (0, 0)
grid_spacing = 50
scroll_position = (0, 0)
label_pos = "bottom"  # or 'right'
text_size = 16
icon_size = 64

# .. List view configuration ...................................................

# Column names are as follows:
#
#   name
#   date-modified
#   date-created
#   date-added
#   date-last-opened
#   size
#   kind
#   label
#   version
#   comments
#
list_icon_size = 16
list_text_size = 12
list_scroll_position = (0, 0)
list_sort_by = "name"
list_use_relative_dates = True
list_calculate_all_sizes = (False,)
list_columns = ("name", "date-modified", "size", "kind", "date-added")
list_column_widths = {
    "name": 300,
    "date-modified": 181,
    "date-created": 181,
    "date-added": 181,
    "date-last-opened": 181,
    "size": 97,
    "kind": 115,
    "label": 100,
    "version": 75,
    "comments": 300,
}
list_column_sort_directions = {
    "name": "ascending",
    "date-modified": "descending",
    "date-created": "descending",
    "date-added": "descending",
    "date-last-opened": "descending",
    "size": "descending",
    "kind": "ascending",
    "label": "ascending",
    "version": "ascending",
    "comments": "ascending",
}
