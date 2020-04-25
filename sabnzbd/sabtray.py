#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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

import os
import logging
from time import sleep

import sabnzbd
from sabnzbd.panic import launch_a_browser
import sabnzbd.api as api
import sabnzbd.scheduler as scheduler
from sabnzbd.downloader import Downloader
import sabnzbd.cfg as cfg
from sabnzbd.misc import to_units

# contains the tray icon, which demands its own thread
from sabnzbd.utils.systrayiconthread import SysTrayIconThread


class SABTrayThread(SysTrayIconThread):
    sabicons = {
        'default': 'icons/sabnzbd16_32.ico',
        'green': 'icons/sabnzbd16_32green.ico',
        'pause': 'icons/sabnzbd16_32paused.ico'
    }

    def __init__(self):
        # Wait for translated texts to be loaded
        while not sabnzbd.WEBUI_READY:
            sleep(0.2)
            logging.debug('language file not loaded, waiting')

        self.sabpaused = False
        self.counter = 0
        self.set_texts()

        menu_options = (
            (T('Show interface'), None, self.browse),
            (T('Open complete folder'), None, self.opencomplete),
            ('SEPARATOR', None, None),
            (T('Pause') + '/' + T('Resume'), None, self.pauseresume),
            (T('Pause for'), None, ((T('Pause for 5 minutes'), None, self.pausefor5min),
                                    (T('Pause for 15 minutes'), None, self.pausefor15min),
                                    (T('Pause for 30 minutes'), None, self.pausefor30min),
                                    (T('Pause for 1 hour'), None, self.pausefor1hour),
                                    (T('Pause for 3 hours'), None, self.pausefor3hour),
                                    (T('Pause for 6 hours'), None, self.pausefor6hour))),
            ('SEPARATOR', None, None),
            (T('Read all RSS feeds'), None, self.rss),
            ('SEPARATOR', None, None),
            (T('Troubleshoot'), None, ((T('Restart'), None, self.restart_sab),
                                       (T('Restart without login'), None, self.nologin),
                                       (T('Restart') + ' - 127.0.0.1:8080', None, self.defhost))),
            (T('Shutdown'), None, self.shutdown),
        )

        SysTrayIconThread.__init__(self, self.sabicons['default'], "SABnzbd", menu_options, None, 0, "SabTrayIcon")

    def set_texts(self):
        """ Cache texts for performance, doUpdates is called often """
        self.txt_idle = T('Idle')
        self.txt_paused = T('Paused')
        self.txt_remaining = T('Remaining')

    # called every few ms by SysTrayIconThread
    def doUpdates(self):
        """ Update menu info, once every 10 calls """
        self.counter += 1
        if self.counter > 10:
            self.sabpaused, bytes_left, bpsnow, time_left = api.fast_queue()
            mb_left = to_units(bytes_left)
            speed = to_units(bpsnow)

            if self.sabpaused:
                if bytes_left > 0:
                    self.hover_text = "%s - %s: %sB" % (self.txt_paused, self.txt_remaining, mb_left)
                else:
                    self.hover_text = self.txt_paused
                self.icon = self.sabicons['pause']
            elif bytes_left > 0:
                self.hover_text = "%sB/s - %s: %sB (%s)" % (speed, self.txt_remaining, mb_left, time_left)
                self.icon = self.sabicons['green']
            else:
                self.hover_text = self.txt_idle
                self.icon = self.sabicons['default']

            self.refresh_icon()
            self.counter = 0

    # left-click handler
    def click(self, *args):
        # Make sure to stop the timer
        self.stop_click_timer()
        # Pause/resume and force update of icon/text
        self.pauseresume(None)
        self.counter = 11

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

    def pausefor(self, minutes):
        """ Need function for each pause-timer """
        scheduler.plan_resume(minutes)

    def pausefor5min(self, icon):
        self.pausefor(5)

    def pausefor15min(self, icon):
        self.pausefor(15)

    def pausefor30min(self, icon):
        self.pausefor(30)

    def pausefor1hour(self, icon):
        self.pausefor(60)

    def pausefor3hour(self, icon):
        self.pausefor(3*60)

    def pausefor6hour(self, icon):
        self.pausefor(6*60)

    def restart_sab(self, icon):
        self.hover_text = T('Restart')
        logging.info('Restart requested by tray')
        sabnzbd.trigger_restart()

    def rss(self, icon):
        self.hover_text = T('Read all RSS feeds')
        scheduler.force_rss()

    def nologin(self, icon):
        sabnzbd.cfg.username.set('')
        sabnzbd.cfg.password.set('')
        sabnzbd.config.save_config()
        self.hover_text = T('Restart')
        sabnzbd.trigger_restart()

    def defhost(self, icon):
        sabnzbd.cfg.cherryhost.set('127.0.0.1')
        sabnzbd.cfg.enable_https.set(False)
        sabnzbd.config.save_config()
        self.hover_text = T('Restart')
        sabnzbd.trigger_restart()

    def shutdown(self, icon):
        self.hover_text = T('Shutdown')
        sabnzbd.shutdown_program()

    def pause(self):
        scheduler.plan_resume(0)
        Downloader.do.pause()

    def resume(self):
        scheduler.plan_resume(0)
        sabnzbd.unpause_all()
