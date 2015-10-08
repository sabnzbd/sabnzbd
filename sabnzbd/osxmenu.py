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
sabnzbd.osxmenu - OSX Top Menu
"""

import objc
from Foundation import *
from AppKit import *
from PyObjCTools import AppHelper
from objc import YES, NO, nil

import os
import subprocess
from threading import Thread

import cherrypy
import Cheetah.DummyTransaction
import sys
import time

import logging

import sabnzbd
import sabnzbd.cfg

from sabnzbd.constants import *
from sabnzbd.misc import get_filename, get_ext, diskfree, to_units
from sabnzbd.panic import launch_a_browser
import sabnzbd.growler as growler

from sabnzbd.api import fast_queue
from sabnzbd.nzbqueue import NzbQueue
import sabnzbd.config as config
import sabnzbd.scheduler as scheduler
import sabnzbd.downloader
import sabnzbd.dirscanner as dirscanner
from sabnzbd.bpsmeter import BPSMeter
from sabnzbd.database import get_history_handle
from sabnzbd.encoding import unicoder

status_icons = {'idle': '../Resources/sab_idle.tiff', 'pause': '../Resources/sab_pause.tiff', 'clicked': '../Resources/sab_clicked.tiff'}
start_time = NSDate.date()
debug = 0


class SABnzbdDelegate(NSObject):

    icons = {}
    status_bar = None
    osx_icon = True
    history_db = None
    isLeopard = 0

    def awakeFromNib(self):
        # Status Bar initialize
        if (debug == 1):
            NSLog("[osx] awake")
        self.buildMenu()
        # Timer for updating menu
        self.timer = NSTimer.alloc().initWithFireDate_interval_target_selector_userInfo_repeats_(start_time, 3.0, self, 'updateAction:', None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSDefaultRunLoopMode)
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSEventTrackingRunLoopMode)
        # NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSModalPanelRunLoopMode)

        self.timer.fire()

    def buildMenu(self):
        # logging.info("building menu")
        status_bar = NSStatusBar.systemStatusBar()
        self.status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        for i in status_icons.keys():
            self.icons[i] = NSImage.alloc().initByReferencingFile_(status_icons[i])
            if sabnzbd.DARWIN_VERSION > 9:
                # Support for Yosemite Dark Mode
                self.icons[i].setTemplate_(YES)
        self.status_item.setImage_(self.icons['idle'])
        self.status_item.setAlternateImage_(self.icons['clicked'])
        self.status_item.setHighlightMode_(1)
        self.status_item.setToolTip_('SABnzbd')
        self.status_item.setEnabled_(YES)

        if (debug == 1):
            NSLog("[osx] menu 1 building")

        # Wait for SABnzbd Initialization
        # cherrypy.engine.wait(cherrypy.process.wspbus.states.STARTED)

        # Wait for translated texts to be loaded
        while not sabnzbd.WEBUI_READY and not sabnzbd.SABSTOP:
            time.sleep(0.5)
            if (debug == 1):
                NSLog("[osx] language file not loaded, waiting")

        # Variables
        self.state = "Idle"
        try:
            self.speed = sabnzbd.downloader.Downloader.do.get_limit()
        except:
            self.speed = 0
        self.version_notify = 1
        self.status_removed = 0

        if (debug == 1):
            NSLog("[osx] menu 2 initialization")

        # Menu construction
        self.menu = NSMenu.alloc().init()

        try:
            menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Dummy", '', '')
            menu_item.setHidden_(YES)
            self.isLeopard = 1
        except:
            self.isLeopard = 0

        if (debug == 1):
            NSLog("[osx] menu 3 construction")

        # Warnings Item
        self.warnings_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Warnings'), 'openBrowserAction:', '')
        if self.isLeopard:
            self.warnings_menu_item.setHidden_(YES)
        else:
            self.warnings_menu_item.setEnabled_(NO)
        self.warnings_menu_item.setRepresentedObject_("connections/")
        self.menu.addItem_(self.warnings_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 4 warning added")

        # State Item
        self.state_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Idle'), 'openBrowserAction:', '')
        self.state_menu_item.setRepresentedObject_("")
        self.menu.addItem_(self.state_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 5 state added")

        # Config Item
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Configuration'), 'openBrowserAction:', '')
        menu_item.setRepresentedObject_("config/general/")
        menu_item.setAlternate_(YES)
        menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(menu_item)

        if (debug == 1):
            NSLog("[osx] menu 6 config added")

        # Queue Item
        self.queue_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Queue'), 'openBrowserAction:', '')
        self.queue_menu_item.setRepresentedObject_("")
        self.menu.addItem_(self.queue_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 7 queue added")

        # Purge Queue Item
        self.purgequeue_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Purge Queue'), 'purgeAction:', '')
        self.purgequeue_menu_item.setRepresentedObject_("queue")
        self.purgequeue_menu_item.setAlternate_(YES)
        self.purgequeue_menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(self.purgequeue_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 8 purge queue added")

        # History Item
        self.history_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('History'), 'openBrowserAction:', '')
        self.history_menu_item.setRepresentedObject_("")
        self.menu.addItem_(self.history_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 9 history added")

        # Purge History Item
        self.purgehistory_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Purge History'), 'purgeAction:', '')
        self.purgehistory_menu_item.setRepresentedObject_("history")
        self.purgehistory_menu_item.setAlternate_(YES)
        self.purgehistory_menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(self.purgehistory_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 10 purge history added")

        self.separator_menu_item = NSMenuItem.separatorItem()
        self.menu.addItem_(self.separator_menu_item)

        # Limit Speed Item & Submenu
        self.speed_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Limit Speed'), '', '')

        self.menu_speed = NSMenu.alloc().init()

        speeds = {10: '10%', 20: '20%', 30: '30%', 40: '40%', 50: '50%',
                   60: '60%', 70: '70%', 80: '80%', 90: '90%', 100: '100%'
                  }

        for speed in sorted(speeds.keys()):
            menu_speed_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('%s' % (speeds[speed]), 'speedlimitAction:', '')
            menu_speed_item.setRepresentedObject_("%s" % (speed))
            self.menu_speed.addItem_(menu_speed_item)

        self.speed_menu_item.setSubmenu_(self.menu_speed)
        self.menu.addItem_(self.speed_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 11 limit speed added")

        # Pause Item & Submenu
        self.pause_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Pause'), 'pauseAction:', '')
        self.pause_menu_item.setRepresentedObject_('0')

        self.menu_pause = NSMenu.alloc().init()

        for i in range(6):
            menu_pause_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("%s %s" % ((i + 1) * 10, T('min.')), 'pauseAction:', '')
            menu_pause_item.setRepresentedObject_("%s" % ((i + 1) * 10))
            self.menu_pause.addItem_(menu_pause_item)

        self.pause_menu_item.setSubmenu_(self.menu_pause)
        self.menu.addItem_(self.pause_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 12 pause added")

        # Resume Item
        self.resume_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Resume'), 'resumeAction:', '')
        if self.isLeopard:
            self.resume_menu_item.setHidden_(YES)
        else:
            self.resume_menu_item.setEnabled_(NO)
        self.menu.addItem_(self.resume_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 13 resume added")

        # Watched folder Item
        self.watched_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Scan watched folder'), 'watchedFolderAction:', '')
        if self.isLeopard:
            self.watched_menu_item.setHidden_(YES)
        else:
            self.watched_menu_item.setEnabled_(NO)
        self.menu.addItem_(self.watched_menu_item)

        # All RSS feeds
        self.rss_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Read all RSS feeds'), 'rssAction:', '')
        if self.isLeopard:
            self.rss_menu_item.setHidden_(YES)
        else:
            self.rss_menu_item.setEnabled_(NO)
        self.menu.addItem_(self.rss_menu_item)

        self.separator2_menu_item = NSMenuItem.separatorItem()
        self.menu.addItem_(self.separator2_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 14 watched folder added")

        # Complete Folder Item
        self.completefolder_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Complete Folder') + '\t\t\t', 'openFolderAction:', '')
        self.completefolder_menu_item.setRepresentedObject_(sabnzbd.cfg.complete_dir.get_path())
        self.menu.addItem_(self.completefolder_menu_item)

        # Incomplete Folder Item
        self.incompletefolder_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Incomplete Folder') + '\t\t', 'openFolderAction:', '')
        self.incompletefolder_menu_item.setRepresentedObject_(sabnzbd.cfg.download_dir.get_path())
        self.menu.addItem_(self.incompletefolder_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 15 folder added")

        self.menu.addItem_(NSMenuItem.separatorItem())

        # FIXME: About Item
        # menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('About SABnzbd', 'aboutAction:', '')
        # self.menu.addItem_(menu_item)

        # Set diagnostic menu
        self.diagnostic_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Troubleshoot'), '', '')
        self.menu_diagnostic = NSMenu.alloc().init()
        diag_items = ((T('Restart'), 'restartAction:'),
                      (T('Restart') + ' - 127.0.0.1:8080', 'restartSafeHost:'),
                      (T('Restart without login'), 'restartNoLogin:')
                      )
        for item in diag_items:
            menu_diag_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(item[0], item[1], '')
            menu_diag_item.setRepresentedObject_(item[0])
            self.menu_diagnostic.addItem_(menu_diag_item)

        self.diagnostic_menu_item.setSubmenu_(self.menu_diagnostic)
        self.menu.addItem_(self.diagnostic_menu_item)

        if (debug == 1):
            NSLog("[osx] menu 16 Diagnostic added")

        # Quit Item
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Quit'), 'terminate:', '')
        self.menu.addItem_(menu_item)

        if (debug == 1):
            NSLog("[osx] menu 16 quit added")

        # Add menu to Status Item
        self.status_item.setMenu_(self.menu)

        if (debug == 1):
            NSLog("[osx] menu 18 menu added")

    def updateAction_(self, notification):
        try:
            self.osx_icon = sabnzbd.cfg.osx_menu()

            if self.osx_icon:
                if self.status_removed == 1:
                    self.buildMenu()

                if self.serverUpdate():
                    self.warningsUpdate()
                    self.queueUpdate()
                    self.historyUpdate()
                    self.stateUpdate()
                    self.iconUpdate()
                    self.pauseUpdate()
                    self.speedlimitUpdate()
                    self.versionUpdate()
                    self.diskspaceUpdate()
                    self.watchedUpdate()
                    self.rssUpdate()
            else:
                if self.status_removed == 0:
                    status_bar = NSStatusBar.systemStatusBar()
                    status_bar.removeStatusItem_(self.status_item)
                    self.status_removed = 1
                    status_bar = None
                    self.status_item = None
        except:
            logging.info("[osx] Exception %s" % (sys.exc_info()[0]))

    def queueUpdate(self):
        try:
            qnfo = NzbQueue.do.queue_info(max_jobs=10)
            pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

            bytesleftprogess = 0
            bpsnow = BPSMeter.do.get_bps()
            self.info = ""

            self.menu_queue = NSMenu.alloc().init()

            if len(pnfo_list):

                menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Queue First 10 Items'), '', '')
                self.menu_queue.addItem_(menu_queue_item)
                self.menu_queue.addItem_(NSMenuItem.separatorItem())

                for pnfo in pnfo_list:
                    filename = unicoder(pnfo[PNFO_FILENAME_FIELD])
                    bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
                    bytesleftprogess += pnfo[PNFO_BYTES_LEFT_FIELD]
                    bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
                    nzo_id = pnfo[PNFO_NZO_ID_FIELD]
                    timeleft = self.calc_timeleft(bytesleftprogess, bpsnow)

                    job = "%s\t(%d/%d MB) %s" % (filename, bytesleft, bytes, timeleft)
                    menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, '', '')
                    self.menu_queue.addItem_(menu_queue_item)

                self.info = "%d nzb(s)\t( %d / %d MB )" % (qnfo[QNFO_Q_SIZE_LIST_FIELD], (qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI), (qnfo[QNFO_BYTES_FIELD] / MEBI))

            else:
                menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Empty'), '', '')
                self.menu_queue.addItem_(menu_queue_item)

            self.queue_menu_item.setSubmenu_(self.menu_queue)

        except:
            logging.info("[osx] queueUpdate Exception %s" % (sys.exc_info()[0]))

    def historyUpdate(self):
        try:
            # Fetch history items
            if not self.history_db:
                self.history_db = sabnzbd.database.get_history_handle()
            items, fetched_items, _total_items = self.history_db.fetch_history(0, 10, None)

            self.menu_history = NSMenu.alloc().init()
            self.failedAttributes = {NSForegroundColorAttributeName: NSColor.redColor(), NSFontAttributeName: NSFont.menuFontOfSize_(14.0)}

            menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('History Last 10 Items'), '', '')
            self.menu_history.addItem_(menu_history_item)
            self.menu_history.addItem_(NSMenuItem.separatorItem())

            if fetched_items:
                for history in items:
                    # logging.info("[osx] history : %s" % (history))
                    job = "%s" % (history['name'])
                    path = ""
                    if os.path.isdir(history['storage']) or os.path.isfile(history['storage']):
                        if os.path.isfile(history['storage']):
                            path = os.path.dirname(history['storage'])
                        else:
                            path = history['storage']
                    if path:
                        menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, 'openFolderAction:', '')
                    else:
                        menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, '', '')
                    if history['status'] != Status.COMPLETED:
                        jobfailed = NSAttributedString.alloc().initWithString_attributes_(job, self.failedAttributes)
                        menu_history_item.setAttributedTitle_(jobfailed)
                    menu_history_item.setRepresentedObject_("%s" % (path))
                    self.menu_history.addItem_(menu_history_item)
            else:
                menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T('Empty'), '', '')
                self.menu_history.addItem_(menu_history_item)

            self.history_menu_item.setSubmenu_(self.menu_history)
        except:
            logging.info("[osx] historyUpdate Exception %s" % (sys.exc_info()[0]))

    def warningsUpdate(self):
        try:
            warnings = sabnzbd.GUIHANDLER.count()
            if warnings:
                warningsAttributes = {
                    NSForegroundColorAttributeName: NSColor.redColor(),
                    NSFontAttributeName: NSFont.menuFontOfSize_(14.0)
                }

                warningsTitle = NSAttributedString.alloc().initWithString_attributes_("%s : %s" % (T('Warnings'), warnings), warningsAttributes)

                self.warnings_menu_item.setAttributedTitle_(warningsTitle)
                if self.isLeopard:
                    self.warnings_menu_item.setHidden_(NO)
                else:
                    self.warnings_menu_item.setEnabled_(YES)
            else:
                self.warnings_menu_item.setTitle_("%s : 0" % (T('Warnings')))
                if self.isLeopard:
                    self.warnings_menu_item.setHidden_(YES)
                else:
                    self.warnings_menu_item.setEnabled_(NO)
        except:
            logging.info("[osx] warningsUpdate Exception %s" % (sys.exc_info()[0]))

    def stateUpdate(self):
        try:
            paused, bytes_left, bpsnow, time_left = fast_queue()

            if paused:
                self.state = T('Paused')
                if sabnzbd.scheduler.pause_int() != "0":
                    self.setMenuTitle("\n\n%s\n" % (sabnzbd.scheduler.pause_int()))
                else:
                    self.setMenuTitle("")
            elif bytes_left > 0:
                self.state = ""
                speed = to_units(bpsnow, dec_limit=1)
                # "10.1 MB/s" doesn't fit, remove space char
                if 'M' in speed and len(speed) > 5:
                    speed = speed.replace(' ', '')
                time_left = (bpsnow > 10 and time_left) or "------"

                statusbarText = "\n\n%s\n%sB/s\n" % (time_left, speed)

                if sabnzbd.SABSTOP:
                    statusbarText = "..."

                if not sabnzbd.cfg.osx_speed():
                    statusbarText = ""

                self.setMenuTitle(statusbarText)
            else:
                self.state = T('Idle')
                self.setMenuTitle("")

            if self.state != "" and self.info != "":
                self.state_menu_item.setTitle_("%s - %s" % (self.state, self.info))
            if self.info == "":
                self.state_menu_item.setTitle_("%s" % (self.state))
            else:
                self.state_menu_item.setTitle_("%s" % (self.info))

        except:
            logging.info("[osx] stateUpdate Exception %s" % (sys.exc_info()[0]))

    def iconUpdate(self):
        try:
            if sabnzbd.downloader.Downloader.do.paused:
                self.status_item.setImage_(self.icons['pause'])
            else:
                self.status_item.setImage_(self.icons['idle'])
        except:
            logging.info("[osx] iconUpdate Exception %s" % (sys.exc_info()[0]))

    def pauseUpdate(self):
        try:
            if sabnzbd.downloader.Downloader.do.paused:
                if self.isLeopard:
                    self.resume_menu_item.setHidden_(NO)
                    self.pause_menu_item.setHidden_(YES)
                else:
                    self.resume_menu_item.setEnabled_(YES)
                    self.pause_menu_item.setEnabled_(NO)
            else:
                if self.isLeopard:
                    self.resume_menu_item.setHidden_(YES)
                    self.pause_menu_item.setHidden_(NO)
                else:
                    self.resume_menu_item.setEnabled_(NO)
                    self.pause_menu_item.setEnabled_(YES)
        except:
            logging.info("[osx] pauseUpdate Exception %s" % (sys.exc_info()[0]))

    def speedlimitUpdate(self):
        try:
            speed = int(sabnzbd.downloader.Downloader.do.get_limit())
            if self.speed != speed:
                self.speed = speed
                speedsValues = self.menu_speed.numberOfItems()
                for i in range(speedsValues):
                    menuitem = self.menu_speed.itemAtIndex_(i)
                    if speed == int(menuitem.representedObject()):
                        menuitem.setState_(NSOnState)
                    else:
                        menuitem.setState_(NSOffState)
        except:
            logging.info("[osx] speedlimitUpdate Exception %s" % (sys.exc_info()[0]))

    def versionUpdate(self):
        try:
            if sabnzbd.NEW_VERSION and self.version_notify:
                # logging.info("[osx] New Version : %s" % (sabnzbd.NEW_VERSION))
                new_release, _new_rel_url = sabnzbd.NEW_VERSION.split(';')
                growler.send_notification("SABnzbd", "%s : %s" % (T('New release available'), new_release), 'other')
                self.version_notify = 0
        except:
            logging.info("[osx] versionUpdate Exception %s" % (sys.exc_info()[0]))

    def watchedUpdate(self):
        try:
            if sabnzbd.cfg.dirscan_dir():
                if self.isLeopard:
                    self.watched_menu_item.setHidden_(NO)
                else:
                    self.watched_menu_item.setEnabled_(YES)
            else:
                if self.isLeopard:
                    self.watched_menu_item.setHidden_(YES)
                else:
                    self.watched_menu_item.setEnabled_(NO)
        except:
            logging.info("[osx] watchedUpdate Exception %s" % (sys.exc_info()[0]))

    def rssUpdate(self):
        try:
            if self.isLeopard:
                self.rss_menu_item.setHidden_(NO)
            else:
                self.rss_menu_item.setEnabled_(YES)
        except:
            logging.info("[osx] rssUpdate Exception %s" % (sys.exc_info()[0]))

    def serverUpdate(self):
        try:
            if not config.get_servers():
                self.state_menu_item.setTitle_(T('Go to wizard'))
                hide = YES
                alternate = NO
                value = 0
            else:
                hide = NO
                alternate = YES
                value = 1
            if self.isLeopard:
                self.speed_menu_item.setHidden_(hide)
                self.resume_menu_item.setHidden_(hide)
                self.pause_menu_item.setHidden_(hide)
                self.watched_menu_item.setHidden_(hide)
                self.rss_menu_item.setHidden_(hide)
                self.purgequeue_menu_item.setAlternate_(alternate)
                self.purgequeue_menu_item.setHidden_(hide)
                self.queue_menu_item.setHidden_(hide)
                self.purgehistory_menu_item.setAlternate_(alternate)
                self.purgehistory_menu_item.setHidden_(hide)
                self.history_menu_item.setHidden_(hide)
                self.separator_menu_item.setHidden_(hide)
                self.separator2_menu_item.setHidden_(hide)
                self.completefolder_menu_item.setHidden_(hide)
                self.incompletefolder_menu_item.setHidden_(hide)
            else:
                self.speed_menu_item.setEnabled_(alternate)
                self.resume_menu_item.setEnabled_(alternate)
                self.pause_menu_item.setEnabled_(alternate)
                self.watched_menu_item.setEnabled_(alternate)
                self.rss_menu_item.setEnabled_(alternate)
                self.purgequeue_menu_item.setAlternate_(alternate)
                self.purgequeue_menu_item.setEnabled_(alternate)
                self.queue_menu_item.setEnabled_(alternate)
                self.purgehistory_menu_item.setAlternate_(alternate)
                self.purgehistory_menu_item.setEnabled_(alternate)
                self.history_menu_item.setEnabled_(alternate)
                self.separator_menu_item.setEnabled_(alternate)
                self.separator2_menu_item.setEnabled_(alternate)
                self.completefolder_menu_item.setEnabled_(alternate)
                self.incompletefolder_menu_item.setEnabled_(alternate)
            return value

        except:
            logging.info("[osx] configUpdate Exception %s" % (sys.exc_info()[0]))
            return 0

    def diskspaceUpdate(self):
        try:
            self.completefolder_menu_item.setTitle_("%s%.2f GB" % (T('Complete Folder') + '\t\t\t', diskfree(sabnzbd.cfg.complete_dir.get_path())))
            self.incompletefolder_menu_item.setTitle_("%s%.2f GB" % (T('Incomplete Folder') + '\t\t', diskfree(sabnzbd.cfg.download_dir.get_path())))
        except:
            logging.info("[osx] diskspaceUpdate Exception %s" % (sys.exc_info()[0]))

    def setMenuTitle(self, text):
        try:
            style = NSMutableParagraphStyle.new()
            style.setParagraphStyle_(NSParagraphStyle.defaultParagraphStyle())
            style.setAlignment_(NSCenterTextAlignment)
            style.setLineSpacing_(0.0)
            style.setMaximumLineHeight_(9.0)
            style.setParagraphSpacing_(-3.0)

            # Trying to change color of title to white when menu is open TO FIX
            if self.menu.highlightedItem():
                # logging.info("Menu Clicked")
                titleColor = NSColor.highlightColor()
            else:
                # logging.info("Menu Not Clicked")
                titleColor = NSColor.blackColor()

            titleAttributes = {
                NSBaselineOffsetAttributeName: 5.0,
                NSFontAttributeName: NSFont.menuFontOfSize_(9.0),
                NSParagraphStyleAttributeName: style
                #,NSForegroundColorAttributeName:  titleColor
            }

            title = NSAttributedString.alloc().initWithString_attributes_(text, titleAttributes)
            self.status_item.setAttributedTitle_(title)
        except:
            logging.info("[osx] setMenuTitle Exception %s" % (sys.exc_info()[0]))

    def calc_timeleft(self, bytesleft, bps):
        """ Calculate the time left in the format HH:MM:SS """
        try:
            totalseconds = int(bytesleft / bps)
            minutes, seconds = divmod(totalseconds, 60)
            hours, minutes = divmod(minutes, 60)
            if minutes < 10:
                minutes = '0%s' % minutes
            if seconds < 10:
                seconds = '0%s' % seconds
            return '%s:%s:%s' % (hours, minutes, seconds)
        except:
            return '0:00:00'

    def openBrowserAction_(self, sender):
        if sender.representedObject:
            link = sender.representedObject()
        else:
            link = ""
        launch_a_browser(sabnzbd.BROWSER_URL, True)

    def speedlimitAction_(self, sender):
        # logging.info("[osx] speed limit to %s" % (sender.representedObject()))
        speed = int(sender.representedObject())
        if speed != self.speed:
            sabnzbd.downloader.Downloader.do.limit_speed(speed)
            self.speedlimitUpdate()

    def purgeAction_(self, sender):
        mode = sender.representedObject()
        # logging.info("[osx] purge %s" % (mode))
        if mode == "queue":
            NzbQueue.do.remove_all()
        elif mode == "history":
            if not self.history_db:
                self.history_db = sabnzbd.database.get_history_handle()
            self.history_db.remove_history()

    def pauseAction_(self, sender):
        minutes = int(sender.representedObject())
        # logging.info("[osx] pause for %s" % (minutes))
        if minutes:
            scheduler.plan_resume(minutes)
        else:
            sabnzbd.downloader.Downloader.do.pause()

    def resumeAction_(self, sender):
        scheduler.plan_resume(0)

    def watchedFolderAction_(self, sender):
        sabnzbd.dirscanner.dirscan()

    def rssAction_(self, sender):
        scheduler.force_rss()

    def openFolderAction_(self, sender):
        folder2open = sender.representedObject()
        if isinstance(folder2open, unicode):
            folder2open = folder2open.encode("utf-8")
        if (debug == 1):
            NSLog("[osx] %@", folder2open)
        os.system('open "%s"' % folder2open)

#    def aboutAction_(self, sender):
#        app = NSApplication.sharedApplication()
#        app.orderFrontStandardAboutPanel_(nil)

    def restartAction_(self, sender):
        self.setMenuTitle("\n\n%s\n" % (T('Stopping...')))
        sabnzbd.halt()
        cherrypy.engine.restart()
        self.setMenuTitle("\n\n%s\n" % (T('Stopping...')))

    def restartSafeHost_(self, sender):
        sabnzbd.cfg.cherryhost.set('127.0.0.1')
        sabnzbd.cfg.cherryport.set('8080')
        sabnzbd.cfg.https_port.set('8090')
        sabnzbd.cfg.enable_https.set(False)
        sabnzbd.config.save_config()
        self.setMenuTitle("\n\n%s\n" % (T('Stopping...')))
        sabnzbd.halt()
        cherrypy.engine.restart()
        self.setMenuTitle("\n\n%s\n" % (T('Stopping...')))

    def restartNoLogin_(self, sender):
        sabnzbd.cfg.username.set('')
        sabnzbd.cfg.password.set('')
        sabnzbd.config.save_config()
        self.setMenuTitle("\n\n%s\n" % (T('Stopping...')))
        sabnzbd.halt()
        cherrypy.engine.restart()
        self.setMenuTitle("\n\n%s\n" % (T('Stopping...')))

    def application_openFiles_(self, nsapp, filenames):
        # logging.info('[osx] file open')
        # logging.info('[osx] file : %s' % (filenames))
        for name in filenames:
            logging.info('[osx] receiving from OSX : %s' % name)
            if os.path.exists(name):
                fn = get_filename(name)
                # logging.info('[osx] filename : %s' % (fn))
                if fn:
                    if get_ext(name) in VALID_ARCHIVES:
                        # logging.info('[osx] archive')
                        dirscanner.ProcessArchiveFile(fn, name, keep=True)
                    elif get_ext(name) in ('.nzb', '.gz', '.bz2'):
                        # logging.info('[osx] nzb')
                        dirscanner.ProcessSingleFile(fn, name, keep=True)
        # logging.info('opening done')

    def applicationShouldTerminate_(self, sender):
        logging.info('[osx] application terminating')
        self.setMenuTitle("\n\n%s\n" % (T('Stopping...')))
        self.status_item.setHighlightMode_(NO)
        self.osx_icon = False
        logging.info('[osx] application stopping daemon')
        sabnzbd.halt()
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True
        try:
            growler.send_notification('SABnzbd', T('SABnzbd shutdown finished'), growler.NOTIFICATION['other'])
        except AttributeError:
            # Fails for the OSX binary
            pass
        logging.info('Leaving SABnzbd')
        sys.stderr.flush()
        sys.stdout.flush()
        return NSTerminateNow


def notify(notificationName, message):
    """ Send a notification to the OS (OSX-only) """
    if sabnzbd.FOUNDATION:
        pool = Foundation.NSAutoreleasePool.alloc().init()
        nc = Foundation.NSDistributedNotificationCenter.defaultCenter()
        nc.postNotificationName_object_(notificationName, message)
        del pool
