#!/usr/bin/python -OO
# Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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
sabtray.py - Systray icon for SABnzbd on Windows, contributed by Jan Schejbal
"""

from SysTrayIconThread import SysTrayIconThread
from threading import Thread
from time import sleep

import sabnzbd
from sabnzbd.panic import launch_a_browser
import sabnzbd.api as api
import sabnzbd.scheduler as scheduler
from sabnzbd.downloader import Downloader
import cherrypy
import win32gui


# contains the tray icon, which demands its own thread
class SABTrayThread(SysTrayIconThread):
    sabpaused = False
    sabicons = {
        'default': 'win/tray/sabnzbd16.ico',
        'green': 'win/tray/sabnzbd16green.ico',
        'pause': 'win/tray/sabnzbd16paused.ico'    
    }
    
    
    def __init__(self):


        text = "SABnzbd"
        
        menu_options = (
            ('Show interface', None, self.browse),
            ('Pause/Resume', None, self.pauseresume),
            ('Shutdown', None, self.shutdown),
        )
        
        SysTrayIconThread.__init__(self, self.sabicons['default'], text, menu_options, None, 0, "SabTrayIcon")
    
    
    # called every few ms by SysTrayIconThread 
    def doUpdates(self):
        status = api.qstatus_data()
        state = status.get('state', "SABnzbd");
        self.sabpaused = status.get('paused', False);
        
        if state == 'IDLE':
            self.hover_text = 'SABnzbd idle'
            self.icon = self.sabicons['default']
        elif state == 'PAUSED':
            self.hover_text = 'SABnzbd paused'
            self.icon = self.sabicons['pause']
        elif state == 'DOWNLOADING':
            self.hover_text = status.get('speed', "---") + "B/s, Remaining: " + status.get('timeleft', "---") + " (" + str(int(status.get('mbleft', "0"))) + " MB)"  
            self.icon = self.sabicons['green']
        else:
            self.hover_text = 'UNKNOWN STATE'
            self.icon = self.sabicons['pause']
            
                
        self.refresh_icon()
        if sabnzbd.SABSTOP:
            self.terminate = True
    
    # menu handler 
    def browse(self, icon): launch_a_browser(sabnzbd.BROWSER_URL, True)
  
    # menu handler 
    def pauseresume(self, icon):
        if self.sabpaused:
            self.resume()
        else:
            self.pause()
  
    # menu handler - adapted from interface.py
    def shutdown(self, icon):
        sabnzbd.halt()
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True

    # adapted from interface.py
    def pause(self):
        scheduler.plan_resume(0)
        Downloader.do.pause()

    # adapted from interface.py
    def resume(self):
        scheduler.plan_resume(0)
        sabnzbd.unpause_all()
    



# start the tray
SABTrayThread()
