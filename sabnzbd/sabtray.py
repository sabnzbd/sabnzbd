#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
from sabnzbd.constants import MEBI
from sabnzbd.misc import to_units
import os
import cherrypy

# contains the tray icon, which demands its own thread
from sabnzbd.utils.systrayiconthread import SysTrayIconThread


class SABTrayThread(SysTrayIconThread):
    sabicons = {
        'default': 'icons/sabnzbd16.ico',
        'green': 'icons/sabnzbd16green.ico',
        'pause': 'icons/sabnzbd16paused.ico'
    }

    def __init__(self):
        # Wait for translated texts to be loaded
        while not sabnzbd.WEBUI_READY:
            sleep(0.2)
            logging.debug('language file not loaded, waiting')

        self.sabpaused = False
        self.counter = 0
        text = "SABnzbd"

        self.set_texts()
        menu_options = (
            (self.txt_show_int, None, self.browse),
            (self.txt_open_comp, None, self.opencomplete),
            (self.txt_trouble, None, ((self.txt_restart, None, self.restart),
                                      (self.txt_restart_nl, None, self.nologin),
                                      (self.txt_restart + ' - 127.0.0.1:8080', None, self.defhost))),
            (self.txt_pause + '/' + self.txt_resume, None, self.pauseresume),
            (self.txt_rss, None, self.rss),
            (self.txt_shutdown, None, self.shutdown),
        )

        SysTrayIconThread.__init__(self, self.sabicons['default'], text, menu_options, None, 0, "SabTrayIcon")

    def set_texts(self):
        def fix(txt):
            if trans:
                return Tx(txt)
            else:
                return txt

        trans = str(get_codepage()) == str(sabnzbd.lang.CODEPAGE)
        self.txt_show_int = fix(TT('Show interface'))
        self.txt_open_comp = fix(TT('Open complete folder'))
        self.txt_trouble = fix(TT('Troubleshoot'))
        self.txt_pause = fix(TT('Pause'))
        self.txt_shutdown = fix(TT('Shutdown'))
        self.txt_resume = fix(TT('Resume'))
        self.txt_restart = fix(TT('Restart'))
        self.txt_restart_nl = fix(TT('Restart without login'))
        self.txt_idle = fix(TT('Idle'))
        self.txt_paused = fix(TT('Paused'))
        self.txt_remaining = fix(TT('Remaining'))
        self.txt_rss = fix(TT('Read all RSS feeds'))

    # called every few ms by SysTrayIconThread
    def doUpdates(self):
        """ Update menu info, once every 10 calls """
        self.counter += 1
        if self.counter > 10:
            self.sabpaused, bytes_left, bpsnow, time_left = api.fast_queue()
            mb_left = to_units(bytes_left, dec_limit=1)
            speed = to_units(bpsnow, dec_limit=1)

            if self.sabpaused:
                self.hover_text = self.txt_paused
                self.icon = self.sabicons['pause']
            elif bytes_left > 0:
                self.hover_text = "%sB/s %s: %sB (%s)" % (speed, self.txt_remaining, mb_left, time_left)
                self.icon = self.sabicons['green']
            else:
                self.hover_text = self.txt_idle
                self.icon = self.sabicons['default']

            self.refresh_icon()
            self.counter = 0
        if sabnzbd.SABSTOP:
            self.terminate = True

    # menu handler
    def opencomplete(self, icon):
        try:
            os.startfile(cfg.complete_dir.get_path())
        except WindowsError:
            pass

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
    def restart(self, icon):
        self.hover_text = self.txt_restart
        sabnzbd.halt()
        cherrypy.engine.restart()

    # menu handler
    def rss(self, icon):
        self.hover_text = self.txt_rss
        scheduler.force_rss()

    # menu handler
    def nologin(self, icon):
        sabnzbd.cfg.username.set('')
        sabnzbd.cfg.password.set('')
        sabnzbd.config.save_config()
        self.hover_text = self.txt_restart
        sabnzbd.halt()
        cherrypy.engine.restart()

    # menu handler
    def defhost(self, icon):
        sabnzbd.cfg.cherryhost.set('127.0.0.1')
        sabnzbd.cfg.enable_https.set(False)
        sabnzbd.config.save_config()
        self.hover_text = self.txt_restart
        sabnzbd.halt()
        cherrypy.engine.restart()

    # menu handler - adapted from interface.py
    def shutdown(self, icon):
        self.hover_text = self.txt_shutdown
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


def get_codepage():
    import locale
    _lang, code = locale.getlocale()
    logging.debug('SysTray uses codepage %s', code)
    return code
