                                SABnzbd v0.2.6a
								
Patched by ShyPike

v0.2.6a:
Corrected: Feature "download directory is renamed after the original NZB name"
           contained an error, ignoring "category" folders.

v0.2.6:
Added features:
Option: download directory is renamed after the original NZB name
        (so no disappearing spaces and specials chars)
Option: Add post-download script support
Option: Add scan-speed for the NZB-black hole
Option: Add auto-refresh to the download page
        The templates have been modfied to give 3 additional processing choices
            "R+Script", "U+Script" and "D+Script".
        "None+Script" would not be very useful and is not implemented.
Added: Safer handling when self-unpacking RARs have been downloaded
Added: Option to automatically refresh the Queue web page.
Added: favicon in all templates
Added: The fix for the new Newzbin RSS-feed.
       (From: http://sourceforge.net/forum/forum.php?thread_id=1795210&forum_id=498261)
Added: NovaTemplate (with patches for the new options)
Fixed: incorrect handling of server without port-spec
       (SABnzbd.ini.sample was incorrect)
Added: Automatic refresh for connection-info, useful for troubleshooting.
-------------------------------------------------------------------------------
0) LICENSE
-------------------------------------------------------------------------------

Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

-------------------------------------------------------------------------------
1) INSTALL
-------------------------------------------------------------------------------
SABnzbd-0.2.5-w32 (pre-built binary) users:
o) Everything below already included, goto 2)

Preqrequisites:
- Without these modules, SABnzbd won't work -
- (Included in w32 build) -
- Dependencies in [] are not needed with python-2.5 -

[o) Python-2.4.4]          http://www.python.org
o) Python-2.5              http://www.python.org
o) CherryPy-2.2.1          http://www.cherrypy.org
o) cheetah-2.0rc7          http://www.cheetahtemplate.org/
[o) elementtree >= 1.2.6]  http://effbot.org/downloads/
- w32 only -
o) pywin32-208	   	   https://sourceforge.net/projects/pywin32/

Semi-Optional:
- Required for post processing -
- (Included in w32 build) -
o) unrar >= 3.6.6          http://www.rarlab.com/rar_add.htm
o) unzip >= 5.5.2          http://www.info-zip.org/
o) par2cmdline >= 0.4      http://parchive.sourceforge.net/

Optional:
- (Included in w32 build) -
o) yenc module >= 0.3      unix: 
                           http://sabnzbd.sourceforge.net/yenc-0.3.tar.gz
                           
                           w32:
                           http://sabnzbd.sourceforge.net/yenc-0.3-w32fixed.zip
                           (crippled version that compiles on w32)

[o) cElementTree >= 1.0.5] http://effbot.org/downloads/

o) feedparser >= 4.1       http://feedparser.org/

System-wide install is not required, but possible by using the provided
setup.py script => python setup.py install

-------------------------------------------------------------------------------
2) CONFIG
-------------------------------------------------------------------------------
SABnzbd-0.2.5-w32 users:
 See 3)

Everyone else:
 View SABnzbd.ini.sample for all config options, then copy your edited
 SABnzbd.ini to <your_config_dir>/SABnzbd.ini
 
-------------------------------------------------------------------------------
3) USE
-------------------------------------------------------------------------------
SABnzbd-0.2.5-w32 users:
 Run SABnzbd.exe 
 Point your browser to http://127.0.0.1:8080/sabnzbd
 Goto the config page and enter your preferences.
 
Everyone else:
 Run "python SABnzbd.py -h" for a list of options.
 
 Run "python SABnzbd.py -f <your_config_dir>/SABnzbd.ini", 
 Point your browser to http://127.0.0.1:<your_port>/sabnzbd

-------------------------------------------------------------------------------
4) CREDITS
-------------------------------------------------------------------------------

o) SABnzbd uses various code from pynewsleecher, newsunpack and grabnzb by: 
   Freddie (freddie@madcowdisease.org) (http://www.madcowdisease.org/mcd)

o) SABnzbd interface is served by: 
   cherrypy (http://www.cherrypy.org/)

o) SABnzbd configfile is interpreted by:
   pythonutils.configObj (http://www.voidspace.org.uk/python/pythonutils.html)
   
o) SABnzbd MS Windows .exe is generated by : 
   py2exe (http://starship.python.net/crew/theller/py2exe/)
   
o) SABnzbd Scheduler:
   kronos (http://www.razorvine.net/downloads.html)
   
o) SABnzbd Authentication:
   MultiAuth (http://projects.dowski.com/view/multiauth)
   
o) python yenc module:
   http://golug.cc.uniud.it/yenc.html
   
o) cElementTree and elementtree:
   http://effbot.org/downloads/
  
o) Contributors:
   gwynevans, Jigal van Hemert, ...
   
-------------------------------------------------------------------------------
5) FAQ
-------------------------------------------------------------------------------
o) Q: How can I download a set of *par2/*PAR2 files without activating
      auto-par2 mode?
   A: Select None as your PostProcess option while importing your nzb file.
