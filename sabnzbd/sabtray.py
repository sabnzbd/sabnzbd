#!/usr/bin/python -OO
# Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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

import logging
from time import sleep

import sabnzbd
from sabnzbd.panic import launch_a_browser
import sabnzbd.api as api
import sabnzbd.scheduler as scheduler
from sabnzbd.downloader import Downloader
import sabnzbd.cfg as cfg
import os
import cherrypy

from sabnzbd.utils.systrayiconthread import SysTrayIconThread

# contains the tray icon, which demands its own thread
class SABTrayThread(SysTrayIconThread):
    sabicons = {
        'default': 'icons/sabnzbd16.ico',
        'green': 'icons/sabnzbd16green.ico',
        'pause': 'icons/sabnzbd16paused.ico'
    }


    def __init__(self):
        # Wait for translated texts to be loaded
        while not api.check_trans():
            sleep(0.2)
            logging.debug('language file not loaded, waiting')

        self.sabpaused = False
        self.counter = 0
        text = "SABnzbd"

        codepage = sabnzbd.lang.CODEPAGE
        logging.debug('WinTray uses codepage %s', codepage)
        menu_options = (
            (T('Show interface'), None, self.browse),
            (T('Open complete folder'), None, self.opencomplete),
            (T('Restart without login'), None, self.nologin),
            (T('Restart') + ' - 127.0.0.1:8080', None, self.defhost),
            (T('Pause') + '/' + T('Resume'), None, self.pauseresume),
            (T('Shutdown'), None, self.shutdown),
        )

        SysTrayIconThread.__init__(self, self.sabicons['default'], text, menu_options, None, 0, "SabTrayIcon")


    # called every few ms by SysTrayIconThread
    def doUpdates(self):
        """ Update menu info, once every 10 calls """
        self.counter += 1
        if self.counter > 10:
            status = api.qstatus_data()
            state = status.get('state', "SABnzbd")
            self.sabpaused = status.get('paused', False)

            if state == 'IDLE':
                self.hover_text = 'SABnzbd idle'
                self.icon = self.sabicons['default']
            elif state == 'PAUSED':
                self.hover_text = 'SABnzbd paused'
                self.icon = self.sabicons['pause']
            elif state == 'DOWNLOADING':
                self.hover_text = "%sB/s %s: %s MB (%s)" % (status.get('speed', "---"), T('Remaining').encode(sabnzbd.lang.CODEPAGE, 'replace'), str(int(status.get('mbleft', "0"))), status.get('timeleft', "---"))
                self.icon = self.sabicons['green']
            else:
                self.hover_text = 'UNKNOWN STATE'
                self.icon = self.sabicons['pause']


            self.refresh_icon()
            self.counter = 0
        if sabnzbd.SABSTOP:
            self.terminate = True

    # menu handler
    def opencomplete(self, icon):
        os.startfile(cfg.complete_dir.get_path())

    # menu handler
    def browse(self, icon):
        launch_a_browser(sabnzbd.BROWSER_URL, True)

    # menu handler
    def pauseresume(self, icon):
        if self.sabpaused:
            self.resume()
        else:
            self.pause()

    # menu handler
    def nologin(self, icon):
        sabnzbd.cfg.username.set('')
        sabnzbd.cfg.password.set('')
        sabnzbd.config.save_config()
        self.hover_text = T('Restart').encode(codepage, 'replace')
        sabnzbd.halt()
        cherrypy.engine.restart()

    # menu handler
    def defhost(self, icon):
        sabnzbd.cfg.cherryhost.set('127.0.0.1')
        sabnzbd.cfg.enable_https.set(False)
        sabnzbd.config.save_config()
        self.hover_text = T('Restart')
        sabnzbd.halt()
        cherrypy.engine.restart()

    # menu handler - adapted from interface.py
    def shutdown(self, icon):
        self.hover_text = T('Shutdown').encode(codepage, 'replace')
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

