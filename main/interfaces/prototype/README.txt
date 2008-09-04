Prototype - New web-iu by switch - switch@sabnzbd.org

Prototype is licenced under the Creative Commons Public Licence.
Please see LICENCE.txt or http://creativecommons.org/licenses/by/3.0/ for more information
------------------------

Credits
------------------------
Ext-JS Javascript library - See Licence-Ext-JS
Icons - famfamfam.com: Silk Icons
Snippets from the Ext-Js Forums:
    Row Actions by jsakalos - Ext.ux.grid.RowAction is licensed under the terms of the Open Source LGPL 3.0 license.
    Drag and drop re-order rows by clarkke8


Changelog:
======================
Added: New Skin currently codenamed Prototype. Using Ext-Js, it is Javascript based with the look of a real application (similar to the look of utorrent). Features multiple drag and drop, keyboard shortcuts, nice new graph.

Also Added are:
-Pause and resume individual downloads (p and r keys)
-Prioritize items from High, Normal to Low (h,n,l keys)
-Perform actions on multiple downloads, such as deleting (del key) pausing, priorizing.
-No restart needed for skin changes. However will need to navigate the the index page to avoid anything looking strange
-Loads more API options

Not currently implemented:
-Settings page
-Menu for Adding an nzb
-Shutting down sabnzbd
-Action on queue finish
-Variable refresh rate

Current Bugs:
-Broke Plush by changing "dummy" dummy variable to "_dc"
-Drag and drop places items in the wrong place if finished downloads are being repaired/unpacked/waiting
-The size of the grids in the lower section are currently fixed height, so the bottom of the scrollbar may be hidden.