#!/usr/bin/python3 -OO
# Copyright 2007-2019 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.sabtraylinux - System tray icon for Linux, inspired from the Windows one
"""

from gi.repository import Gtk
from gi.repository import GObject
from time import sleep
import subprocess
from threading import Thread
import logging

import sabnzbd
from sabnzbd.panic import launch_a_browser
import sabnzbd.api as api
import sabnzbd.scheduler as scheduler
from sabnzbd.downloader import Downloader
import sabnzbd.cfg as cfg
from sabnzbd.misc import to_units
from sabnzbd.utils.upload import add_local


class StatusIcon(Thread):
    sabicons = {
        'default': 'icons/sabnzbd16_32.ico',
        'green': 'icons/sabnzbd16_32green.ico',
        'pause': 'icons/sabnzbd16_32paused.ico'
    }

    updatefreq = 1000  # ms

    def __init__(self):
        self.mythread = Thread(target=self.dowork)
        self.mythread.start()

    def dowork(self):
        # Wait for translated texts to be loaded
        while not sabnzbd.WEBUI_READY:
            sleep(0.2)
            logging.debug('language file not loaded, waiting')

        self.sabpaused = False
        self.statusicon = Gtk.StatusIcon()
        self.icon = self.sabicons['default']
        self.refresh_icon()
        self.tooltip = "SABnzbd"
        self.refresh_tooltip()
        self.statusicon.connect("popup-menu", self.right_click_event)

        GObject.timeout_add(self.updatefreq, self.run)
        Gtk.main()

    def refresh_icon(self):
        self.statusicon.set_from_file(self.icon)

    def refresh_tooltip(self):
        self.statusicon.set_tooltip_text(self.tooltip)

    # run this every updatefreq ms
    def run(self):
        self.sabpaused, bytes_left, bpsnow, time_left = api.fast_queue()
        mb_left = to_units(bytes_left)
        speed = to_units(bpsnow)

        if self.sabpaused:
            self.tooltip = T('Paused')
            self.icon = self.sabicons['pause']
        elif bytes_left > 0:
            self.tooltip = "%sB/s %s: %sB (%s)" % (speed, T('Remaining'), mb_left, time_left)
            self.icon = self.sabicons['green']
        else:
            self.tooltip = T('Idle')
            self.icon = self.sabicons['default']

        self.refresh_icon()
        self.refresh_tooltip()
        return 1

    def right_click_event(self, icon, button, time):
        """ menu """
        menu = Gtk.Menu()

        maddnzb = Gtk.MenuItem(T("Add NZB"))
        mshowinterface = Gtk.MenuItem(T("Show interface"))
        mopencomplete = Gtk.MenuItem(T("Open complete folder"))
        mrss = Gtk.MenuItem(T("Read all RSS feeds"))

        if self.sabpaused:
            mpauseresume = Gtk.MenuItem(T("Resume"))
        else:
            mpauseresume = Gtk.MenuItem(T("Pause"))
        mrestart = Gtk.MenuItem(T("Restart"))
        mshutdown = Gtk.MenuItem(T("Shutdown"))

        maddnzb.connect("activate", self.addnzb)
        mshowinterface.connect("activate", self.browse)
        mopencomplete.connect("activate", self.opencomplete)
        mrss.connect("activate", self.rss)
        mpauseresume.connect("activate", self.pauseresume)
        mrestart.connect("activate", self.restart)
        mshutdown.connect("activate", self.shutdown)

        menu.append(maddnzb)
        menu.append(mshowinterface)
        menu.append(mopencomplete)
        menu.append(mrss)
        menu.append(mpauseresume)
        menu.append(mrestart)
        menu.append(mshutdown)

        menu.show_all()
        menu.popup(None, None, self.statusicon.position_menu, self.statusicon, button, time)

    def addnzb(self, icon):
        """ menu handlers """
        dialog = Gtk.FileChooserDialog(title=None, action=Gtk.FileChooserAction.OPEN,
                                       buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        dialog.set_select_multiple(True)

        filter = Gtk.FileFilter()
        filter.set_name("*.nzb,*.gz,*.bz2,*.zip,*.rar,*.7z")
        filter.add_pattern("*.nzb")
        filter.add_pattern("*.gz")
        filter.add_pattern("*.bz2")
        filter.add_pattern("*.zip")
        filter.add_pattern("*.rar")
        filter.add_pattern("*.7z")
        dialog.add_filter(filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            for filename in dialog.get_filenames():
                add_local(filename)
        dialog.destroy()

    def opencomplete(self, icon):
        subprocess.Popen(["xdg-open", cfg.complete_dir.get_path()])

    def browse(self, icon):
        launch_a_browser(sabnzbd.BROWSER_URL, True)

    def pauseresume(self, icon):
        if self.sabpaused:
            self.resume()
        else:
            self.pause()

    def restart(self, icon):
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

    def rss(self, icon):
        scheduler.force_rss()
