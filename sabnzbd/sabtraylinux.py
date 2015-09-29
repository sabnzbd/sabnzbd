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
sabnzbd.sabtraylinux - System tray icon for Linux, inspired from the Windows one
"""

import os
import gtk
import gobject
import cherrypy
from time import sleep
import subprocess
import threading
import logging
from threading import Thread

import sabnzbd
from sabnzbd.panic import launch_a_browser
import sabnzbd.api as api
import sabnzbd.scheduler as scheduler
from sabnzbd.downloader import Downloader
import sabnzbd.cfg as cfg
from sabnzbd.constants import MEBI
from sabnzbd.misc import to_units
from sabnzbd.utils.upload import add_local


class StatusIcon(Thread):
    sabicons = {
        'default': 'icons/sabnzbd16.ico',
        'green': 'icons/sabnzbd16green.ico',
        'pause': 'icons/sabnzbd16paused.ico'
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
        self.statusicon = gtk.StatusIcon()
        self.icon = self.sabicons['default']
        self.refresh_icon()
        self.tooltip = "SABnzbd"
        self.refresh_tooltip()
        self.statusicon.connect("popup-menu", self.right_click_event)

        gtk.gdk.threads_init()
        gtk.gdk.threads_enter()
        gobject.timeout_add(self.updatefreq, self.run)
        gtk.main()

    def refresh_icon(self):
        self.statusicon.set_from_file(self.icon)

    def refresh_tooltip(self):
        self.statusicon.set_tooltip(self.tooltip)

    # run this every updatefreq ms
    def run(self):
        self.sabpaused, bytes_left, bpsnow, time_left = api.fast_queue()
        mb_left = to_units(bytes_left, dec_limit=1)
        speed = to_units(bpsnow, dec_limit=1)

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
        menu = gtk.Menu()

        maddnzb = gtk.MenuItem(T("Add NZB"))
        mshowinterface = gtk.MenuItem(T("Show interface"))
        mopencomplete = gtk.MenuItem(T("Open complete folder"))
        mrss = gtk.MenuItem(T("Read all RSS feeds"))

        if self.sabpaused:
            mpauseresume = gtk.MenuItem(T("Resume"))
        else:
            mpauseresume = gtk.MenuItem(T("Pause"))
        mrestart = gtk.MenuItem(T("Restart"))
        mshutdown = gtk.MenuItem(T("Shutdown"))

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
        menu.popup(None, None, gtk.status_icon_position_menu, button, time, self.statusicon)

    def addnzb(self, icon):
        """ menu handlers """
        dialog = gtk.FileChooserDialog(title=None, action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        dialog.set_select_multiple(True)

        filter = gtk.FileFilter()
        filter.set_name("*.nbz,*.nbz.gz,*.bz2,*.zip,*.rar")
        filter.add_pattern("*.nzb*")
        filter.add_pattern("*.nzb.gz")
        filter.add_pattern("*.nzb.bz2")
        filter.add_pattern("*.zip")
        filter.add_pattern("*.rar")
        dialog.add_filter(filter)

        response = dialog.run()
        if response == gtk.RESPONSE_OK:
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
        sabnzbd.halt()
        cherrypy.engine.restart()

    def shutdown(self, icon):
        self.hover_text = T('Shutdown')
        sabnzbd.halt()
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True

    def pause(self):
        scheduler.plan_resume(0)
        Downloader.do.pause()

    def resume(self):
        scheduler.plan_resume(0)
        sabnzbd.unpause_all()

    def rss(self, icon):
        scheduler.force_rss()
