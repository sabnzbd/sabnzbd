#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.osxmenu - macOS Top Menu
"""

import os
import sys
import time
import logging
from typing import Optional

from objc import YES, NO, lookUpClass
from Foundation import (
    NSObject,
    NSDate,
    NSTimer,
    NSRunLoop,
    NSDefaultRunLoopMode,
    NSColor,
    NSFont,
    NSImage,
    NSAttributedString,
    NSUserNotification,
    NSUserNotificationCenter,
)
from AppKit import (
    NSStatusBar,
    NSMenu,
    NSMenuItem,
    NSAlternateKeyMask,
    NSTerminateNow,
    NSEventTrackingRunLoopMode,
    NSVariableStatusItemLength,
    NSForegroundColorAttributeName,
    NSFontAttributeName,
    NSOnState,
    NSOffState,
    NSBaselineOffsetAttributeName,
    NSParagraphStyleAttributeName,
    NSMutableParagraphStyle,
    NSParagraphStyle,
    NSCenterTextAlignment,
)

import sabnzbd
import sabnzbd.cfg

from sabnzbd.filesystem import diskspace
from sabnzbd.misc import to_units
from sabnzbd.constants import VALID_ARCHIVES, VALID_NZB_FILES, MEBI, Status
from sabnzbd.panic import launch_a_browser

from sabnzbd.api import fast_queue
import sabnzbd.config as config

DefaultUserNotificationCenter = NSUserNotificationCenter.defaultUserNotificationCenter()

status_icons = {
    "idle": "icons/sabnzbd_osx_idle.tiff",
    "pause": "icons/sabnzbd_osx_pause.tiff",
    "clicked": "icons/sabnzbd_osx_clicked.tiff",
}
start_time = NSDate.date()


class SABnzbdDelegate(NSObject):
    icons = {}
    status_bar = None
    history_db = None

    def awakeFromNib(self):
        # Wait for SABnzbd to be ready, otherwise tray_icon might not be read from config yet
        while not sabnzbd.WEBUI_READY and not sabnzbd.SABSTOP:
            time.sleep(0.5)

        # Set this thread as default handler for notification actions
        DefaultUserNotificationCenter.setDelegate_(self)

        # Do we want the menu
        if sabnzbd.cfg.tray_icon():
            # Status Bar initialize
            self.buildMenu()

            # Timer for updating menu
            self.timer = NSTimer.alloc().initWithFireDate_interval_target_selector_userInfo_repeats_(
                start_time, 3.0, self, "updateAction:", None, True
            )
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSDefaultRunLoopMode)
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSEventTrackingRunLoopMode)
            self.timer.fire()

    def buildMenu(self):
        # logging.info("building menu")
        status_bar = NSStatusBar.systemStatusBar()
        self.status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        for icon in status_icons:
            icon_path = status_icons[icon]
            if hasattr(sys, "frozen"):
                # Path is modified for the binary
                icon_path = os.path.join(os.path.dirname(sys.executable), "..", "Resources", status_icons[icon])
            self.icons[icon] = NSImage.alloc().initByReferencingFile_(icon_path)
            self.icons[icon].setTemplate_(YES)

        self.status_item.setImage_(self.icons["idle"])
        self.status_item.setAlternateImage_(self.icons["clicked"])
        self.status_item.setHighlightMode_(1)
        self.status_item.setToolTip_("SABnzbd")
        self.status_item.setEnabled_(YES)

        # Variables
        self.state = "Idle"
        self.speed = 0

        # Menu construction
        self.menu = NSMenu.alloc().init()

        # Warnings Item
        self.warnings_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("Warnings"), "openBrowserAction:", ""
        )
        self.warnings_menu_item.setHidden_(YES)
        self.menu.addItem_(self.warnings_menu_item)

        # State Item
        self.state_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("Idle"), "openBrowserAction:", ""
        )
        self.menu.addItem_(self.state_menu_item)

        # Queue Item
        self.menu_queue = None
        self.queue_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("Queue"), "openBrowserAction:", ""
        )
        self.menu.addItem_(self.queue_menu_item)

        # Purge Queue Item
        self.purgequeue_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("Purge Queue"), "purgeAction:", ""
        )
        self.purgequeue_menu_item.setRepresentedObject_("queue")
        self.purgequeue_menu_item.setAlternate_(YES)
        self.purgequeue_menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(self.purgequeue_menu_item)

        # History Item
        self.menu_history = None
        self.history_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("History"), "openBrowserAction:", ""
        )
        self.menu.addItem_(self.history_menu_item)

        # Purge History Item
        self.purgehistory_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("Purge History"), "purgeAction:", ""
        )
        self.purgehistory_menu_item.setRepresentedObject_("history")
        self.purgehistory_menu_item.setAlternate_(YES)
        self.purgehistory_menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(self.purgehistory_menu_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        # Limit Speed Item & Submenu
        self.speed_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T("Limit Speed"), "", "")
        self.menu_speed = NSMenu.alloc().init()

        for speed in range(10, 101, 10):
            menu_speed_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "%s%%" % speed, "speedlimitAction:", ""
            )
            menu_speed_item.setRepresentedObject_("%s" % speed)
            self.menu_speed.addItem_(menu_speed_item)

        self.speed_menu_item.setSubmenu_(self.menu_speed)
        self.menu.addItem_(self.speed_menu_item)

        # Pause Item & Submenu
        self.pause_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T("Pause"), "pauseAction:", "")
        self.pause_menu_item.setRepresentedObject_("0")
        self.menu_pause = NSMenu.alloc().init()
        for i in range(6):
            menu_pause_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "%s %s" % ((i + 1) * 10, T("min")), "pauseAction:", ""
            )
            menu_pause_item.setRepresentedObject_("%s" % ((i + 1) * 10))
            self.menu_pause.addItem_(menu_pause_item)

        self.pause_menu_item.setSubmenu_(self.menu_pause)
        self.menu.addItem_(self.pause_menu_item)

        # Resume Item
        self.resume_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T("Resume"), "resumeAction:", "")
        self.resume_menu_item.setHidden_(YES)
        self.menu.addItem_(self.resume_menu_item)

        # Watched folder Item
        if sabnzbd.cfg.dirscan_dir():
            self.watched_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                T("Scan watched folder"), "watchedFolderAction:", ""
            )
            self.menu.addItem_(self.watched_menu_item)

        # Read RSS feeds
        if config.get_rss():
            self.rss_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                T("Read all RSS feeds"), "rssAction:", ""
            )
            self.menu.addItem_(self.rss_menu_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        # Complete Folder Item
        self.completefolder_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("Complete Folder"), "openFolderAction:", ""
        )
        self.completefolder_menu_item.setRepresentedObject_(sabnzbd.cfg.complete_dir.get_path())
        self.menu.addItem_(self.completefolder_menu_item)

        # Incomplete Folder Item
        self.incompletefolder_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T("Incomplete Folder"), "openFolderAction:", ""
        )
        self.incompletefolder_menu_item.setRepresentedObject_(sabnzbd.cfg.download_dir.get_path())
        self.menu.addItem_(self.incompletefolder_menu_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        # Set diagnostic menu
        self.diagnostic_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T("Troubleshoot"), "", "")
        self.menu_diagnostic = NSMenu.alloc().init()
        diag_items = (
            (T("Restart"), "restartAction:"),
            (T("Restart") + " - 127.0.0.1:8080", "restartSafeHost:"),
            (T("Restart without login"), "restartNoLogin:"),
        )
        for item in diag_items:
            menu_diag_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(item[0], item[1], "")
            menu_diag_item.setRepresentedObject_(item[0])
            self.menu_diagnostic.addItem_(menu_diag_item)

        self.diagnostic_menu_item.setSubmenu_(self.menu_diagnostic)
        self.menu.addItem_(self.diagnostic_menu_item)

        # Quit Item
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T("Quit"), "terminate:", "")
        self.menu.addItem_(menu_item)

        # Add menu to Status Item
        self.status_item.setMenu_(self.menu)

    def updateAction_(self, notification):
        try:
            self.warningsUpdate()
            self.queueUpdate()
            self.historyUpdate()
            self.stateUpdate()
            self.pauseUpdate()
            self.speedlimitUpdate()
            self.diskspaceUpdate()
        except:
            logging.info("[osx] Exception", exc_info=True)

    def queueUpdate(self):
        try:
            queue_bytes_total, queue_bytes_left, _, nzo_list, _, queue_fullsize = sabnzbd.NzbQueue.queue_info(limit=10)
            bytesleftprogess = 0
            self.info = ""

            if not self.menu_queue:
                self.menu_queue = NSMenu.alloc().init()
            self.menu_queue.removeAllItems()

            if nzo_list:
                menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    T("Queue First 10 Items"), "", ""
                )
                self.menu_queue.addItem_(menu_queue_item)
                self.menu_queue.addItem_(NSMenuItem.separatorItem())

                for nzo in nzo_list:
                    bytesleft = nzo.remaining / MEBI
                    bytesleftprogess += nzo.remaining
                    bytes_total = nzo.bytes / MEBI
                    timeleft = sabnzbd.api.calc_timeleft(bytesleftprogess, sabnzbd.BPSMeter.bps)
                    job = "%s\t(%d/%d MB) %s" % (nzo.filename, bytesleft, bytes_total, timeleft)
                    self.menu_queue.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, "", ""))

                self.info = "%d nzb(s)\t(%d / %d MB)" % (
                    queue_fullsize,
                    (queue_bytes_left / MEBI),
                    (queue_bytes_total / MEBI),
                )
            else:
                menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T("Empty"), "", "")
                self.menu_queue.addItem_(menu_queue_item)
            self.queue_menu_item.setSubmenu_(self.menu_queue)
        except:
            logging.info("[osx] queueUpdate Exception", exc_info=True)

    def historyUpdate(self):
        try:
            # Fetch history items
            if not self.history_db:
                self.history_db = sabnzbd.database.HistoryDB()
            items = self.history_db.fetch_history(limit=10)[0]

            if not self.menu_history:
                self.menu_history = NSMenu.alloc().init()
            self.menu_history.removeAllItems()

            menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                T("History Last 10 Items"), "", ""
            )
            self.menu_history.addItem_(menu_history_item)
            self.menu_history.addItem_(NSMenuItem.separatorItem())

            if items:
                for history in items:
                    if os.path.isdir(history["storage"]):
                        menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                            history["name"], "openFolderAction:", ""
                        )
                    else:
                        menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                            history["name"], "", ""
                        )
                    if history["status"] != Status.COMPLETED:
                        jobfailed = NSAttributedString.alloc().initWithString_attributes_(
                            history["name"],
                            {
                                NSForegroundColorAttributeName: NSColor.redColor(),
                                NSFontAttributeName: NSFont.menuFontOfSize_(14.0),
                            },
                        )
                        menu_history_item.setAttributedTitle_(jobfailed)
                    menu_history_item.setRepresentedObject_(history["storage"])
                    self.menu_history.addItem_(menu_history_item)
            else:
                menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(T("Empty"), "", "")
                self.menu_history.addItem_(menu_history_item)
            self.history_menu_item.setSubmenu_(self.menu_history)
        except:
            logging.info("[osx] historyUpdate Exception", exc_info=True)

    def warningsUpdate(self):
        try:
            warnings = sabnzbd.GUIHANDLER.count()
            if warnings:
                warningsAttributes = {
                    NSForegroundColorAttributeName: NSColor.redColor(),
                    NSFontAttributeName: NSFont.menuFontOfSize_(14.0),
                }
                warningsTitle = NSAttributedString.alloc().initWithString_attributes_(
                    "%s : %s" % (T("Warnings"), warnings), warningsAttributes
                )
                self.warnings_menu_item.setAttributedTitle_(warningsTitle)
                self.warnings_menu_item.setHidden_(NO)
            else:
                self.warnings_menu_item.setTitle_("%s : 0" % (T("Warnings")))
                self.warnings_menu_item.setHidden_(YES)
        except:
            logging.info("[osx] warningsUpdate Exception", exc_info=True)

    def stateUpdate(self):
        try:
            paused, bytes_left, bpsnow, time_left = fast_queue()

            if paused:
                self.state = T("Paused")
                if sabnzbd.Scheduler.pause_int() != "0":
                    self.setMenuTitle_("\n%s\n%s\n" % (T("Paused"), sabnzbd.Scheduler.pause_int()))
                else:
                    self.setMenuTitle_("")
            elif bytes_left > 0:
                self.state = ""
                speed = to_units(bpsnow)
                # "10.1 MB/s" doesn't fit, remove space char
                if "M" in speed and len(speed) > 5:
                    speed = speed.replace(" ", "")
                time_left = (bpsnow > 10 and time_left) or "------"
                self.setMenuTitle_("\n\n%s\n%sB/s\n" % (time_left, speed))
            else:
                self.state = T("Idle")
                self.setMenuTitle_("")

            if self.state != "" and self.info != "":
                self.state_menu_item.setTitle_("%s - %s" % (self.state, self.info))
            if self.info == "":
                self.state_menu_item.setTitle_("%s" % self.state)
            else:
                self.state_menu_item.setTitle_("%s" % self.info)

            if not config.get_servers():
                self.state_menu_item.setTitle_(T("Go to wizard"))
        except:
            logging.info("[osx] stateUpdate Exception", exc_info=True)

    def pauseUpdate(self):
        try:
            if sabnzbd.Downloader.paused:
                self.status_item.setImage_(self.icons["pause"])
                self.resume_menu_item.setHidden_(NO)
                self.pause_menu_item.setHidden_(YES)
            else:
                self.status_item.setImage_(self.icons["idle"])
                self.resume_menu_item.setHidden_(YES)
                self.pause_menu_item.setHidden_(NO)
        except:
            logging.info("[osx] pauseUpdate Exception", exc_info=True)

    def speedlimitUpdate(self):
        try:
            if self.speed != sabnzbd.Downloader.bandwidth_perc:
                self.speed = sabnzbd.Downloader.bandwidth_perc
                speedsValues = self.menu_speed.numberOfItems()
                for i in range(speedsValues):
                    menuitem = self.menu_speed.itemAtIndex_(i)
                    if sabnzbd.Downloader.bandwidth_perc == int(menuitem.representedObject()):
                        menuitem.setState_(NSOnState)
                    else:
                        menuitem.setState_(NSOffState)
        except:
            logging.info("[osx] speedlimitUpdate Exception", exc_info=True)

    def diskspaceUpdate(self):
        try:
            self.completefolder_menu_item.setTitle_(
                "%s (%.2f GB)" % (T("Complete Folder"), diskspace()["complete_dir"][1])
            )
            self.incompletefolder_menu_item.setTitle_(
                "%s (%.2f GB)" % (T("Incomplete Folder"), diskspace()["download_dir"][1])
            )
        except:
            logging.info("[osx] diskspaceUpdate Exception", exc_info=True)

    def setMenuTitle_(self, text):
        try:
            style = NSMutableParagraphStyle.new()
            style.setParagraphStyle_(NSParagraphStyle.defaultParagraphStyle())
            style.setAlignment_(NSCenterTextAlignment)
            style.setLineSpacing_(0.0)
            style.setMaximumLineHeight_(9.0)
            style.setParagraphSpacing_(-3.0)

            titleAttributes = {
                NSBaselineOffsetAttributeName: -5.0,
                NSFontAttributeName: NSFont.menuFontOfSize_(9.0),
                NSParagraphStyleAttributeName: style,
            }

            title = NSAttributedString.alloc().initWithString_attributes_(text, titleAttributes)
            self.status_item.setAttributedTitle_(title)
        except:
            logging.info("[osx] setMenuTitle Exception", exc_info=True)

    def openBrowserAction_(self, sender):
        launch_a_browser(sabnzbd.BROWSER_URL, True)

    def speedlimitAction_(self, sender):
        # logging.info("[osx] speed limit to %s" % (sender.representedObject()))
        speed = int(sender.representedObject())
        if speed != self.speed:
            sabnzbd.Downloader.limit_speed("%s%%" % speed)
            self.speedlimitUpdate()

    def purgeAction_(self, sender):
        mode = sender.representedObject()
        # logging.info("[osx] purge %s" % (mode))
        if mode == "queue":
            sabnzbd.NzbQueue.remove_all()
        elif mode == "history":
            if not self.history_db:
                self.history_db = sabnzbd.database.HistoryDB()
            self.history_db.remove_history()

    def pauseAction_(self, sender):
        minutes = int(sender.representedObject())
        # logging.info("[osx] pause for %s" % (minutes))
        if minutes:
            sabnzbd.Scheduler.plan_resume(minutes)
        else:
            sabnzbd.Downloader.pause()

    def resumeAction_(self, sender):
        sabnzbd.Scheduler.plan_resume(0)

    def watchedFolderAction_(self, sender):
        sabnzbd.DirScanner.scan()

    def rssAction_(self, sender):
        sabnzbd.Scheduler.force_rss()

    def openFolderAction_(self, sender):
        folder2open = sender.representedObject()
        os.system('open "%s"' % folder2open)

    def restartAction_(self, sender):
        self.setMenuTitle_("\n\n%s\n" % (T("Stopping...")))
        logging.info("Restart requested by tray")
        sabnzbd.trigger_restart()
        self.setMenuTitle_("\n\n%s\n" % (T("Stopping...")))

    def restartSafeHost_(self, sender):
        sabnzbd.cfg.cherryhost.set("127.0.0.1")
        sabnzbd.cfg.cherryport.set("8080")
        sabnzbd.cfg.enable_https.set(False)
        sabnzbd.config.save_config()
        self.setMenuTitle_("\n\n%s\n" % (T("Stopping...")))
        sabnzbd.trigger_restart()
        self.setMenuTitle_("\n\n%s\n" % (T("Stopping...")))

    def restartNoLogin_(self, sender):
        sabnzbd.cfg.username.set("")
        sabnzbd.cfg.password.set("")
        sabnzbd.config.save_config()
        self.setMenuTitle_("\n\n%s\n" % (T("Stopping...")))
        sabnzbd.trigger_restart()
        self.setMenuTitle_("\n\n%s\n" % (T("Stopping...")))

    def application_openFiles_(self, nsapp, filenames):
        # logging.info('[osx] file open')
        # logging.info('[osx] file : %s' % (filenames))
        for filename in filenames:
            logging.info("[osx] receiving from macOS : %s", filename)
            if os.path.exists(filename):
                if sabnzbd.filesystem.get_ext(filename) in VALID_ARCHIVES + VALID_NZB_FILES:
                    sabnzbd.nzbparser.add_nzbfile(filename, keep=True)
        # logging.info('opening done')

    def applicationShouldTerminate_(self, sender):
        logging.info("[osx] application terminating")
        self.setMenuTitle_("\n\n%s\n" % (T("Stopping...")))
        self.status_item.setHighlightMode_(NO)
        sabnzbd.shutdown_program()
        return NSTerminateNow

    def send_notification(
        self,
        title: str,
        subtitle: str,
        msg: str,
        button_text: Optional[str] = None,
        button_action: Optional[str] = None,
    ):
        """Send a macOS notification, optionally with 1 action button"""
        notification = NSUserNotification.alloc().init()
        notification.setTitle_(title)
        notification.setSubtitle_(subtitle)
        notification.setInformativeText_(msg)
        notification.setSoundName_("NSUserNotificationDefaultSoundName")

        if button_text and button_action:
            notification.setHasActionButton_(True)
            notification.set_showsButtons_(True)
            notification.setActionButtonTitle_(button_text)
            notification.setUserInfo_({"value": button_action})
        else:
            notification.setHasActionButton_(False)
            notification.set_showsButtons_(False)

        notification.setDeliveryDate_(NSDate.dateWithTimeInterval_sinceDate_(0, NSDate.date()))
        DefaultUserNotificationCenter.scheduleNotification_(notification)

    def userNotificationCenter_didActivateNotification_(self, center, notification):
        """Handler for the clicks on the notification"""

        if notification.activationType() == 1:
            # user clicked on the notification (not on a button)
            launch_a_browser(sabnzbd.BROWSER_URL, force=True)

        elif notification.activationType() == 2:
            # User clicked on the action button
            if os.path.exists(folder2open := notification.userInfo()["value"]):
                os.system('open "%s"' % folder2open)

        # Remove this notification after interaction
        DefaultUserNotificationCenter._removeDisplayedNotification_(notification)
