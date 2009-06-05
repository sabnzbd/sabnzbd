#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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

import objc
from Foundation import *
from AppKit import *
from PyObjCTools import NibClassBuilder, AppHelper
from objc import YES, NO, nil
from threading import Thread

import os
import cherrypy
import sys

import logging
import logging.handlers

import sabnzbd
import sabnzbd.cfg

from sabnzbd.constants import *
from sabnzbd.misc import launch_a_browser,get_filename,get_ext,diskfree
from sabnzbd.utils import osx
from sabnzbd.lang import T

import sabnzbd.nzbqueue as nzbqueue
import sabnzbd.config as config
import sabnzbd.scheduler as scheduler
import sabnzbd.downloader as downloader
import sabnzbd.dirscanner as dirscanner
from sabnzbd.database import get_history_handle

status_icons = {'idle':'../Resources/sab_idle.png','pause':'../Resources/sab_pause.png','clicked':'../Resources/sab_clicked.png'}
start_time = NSDate.date()

NibClassBuilder.extractClasses("MainMenu")

class SABnzbdDelegate(NibClassBuilder.AutoBaseClass):

    icons = {}
    status_bar = None

    def awakeFromNib(self):
        #Status Bar iniatilize
        status_bar = NSStatusBar.systemStatusBar()
        self.status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        for i in status_icons.keys():
            self.icons[i] = NSImage.alloc().initByReferencingFile_(status_icons[i])
        self.status_item.setImage_(self.icons['idle'])
        self.status_item.setAlternateImage_(self.icons['clicked'])
        self.status_item.setHighlightMode_(1)
        self.status_item.setToolTip_('SABnzbd')
        
        #Variables
        self.state = "Idle"
        self.speed = downloader.get_limit()
        self.version_notify = 1
        
        #Menu construction
        self.menu = NSMenu.alloc().init()
        
        #Warnings Item
        self.warnings_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Warnings', 'openBrowserAction:', '')
        self.warnings_menu_item.setHidden_(YES)
        self.warnings_menu_item.setRepresentedObject_("connections/")
        self.menu.addItem_(self.warnings_menu_item)

        #State Item
        self.state_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Idle', 'openBrowserAction:', '')
        self.state_menu_item.setRepresentedObject_("")
        self.menu.addItem_(self.state_menu_item)

        #Config Item
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Configuration', 'openBrowserAction:', '')
        menu_item.setRepresentedObject_("config/general/")
        menu_item.setAlternate_(YES)
        menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(menu_item)

        #Queue Item
        self.queue_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Queue', 'openBrowserAction:', '')
        self.queue_menu_item.setRepresentedObject_("")
        self.menu.addItem_(self.queue_menu_item)

        #Purge Queue Item
        self.purgequeue_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Purge Queue', 'purgeAction:', '')
        self.purgequeue_menu_item.setRepresentedObject_("queue")
        self.purgequeue_menu_item.setAlternate_(YES)
        self.purgequeue_menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(self.purgequeue_menu_item)

        #History Item
        self.history_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('History', 'openBrowserAction:', '')
        self.history_menu_item.setRepresentedObject_("")
        self.menu.addItem_(self.history_menu_item)
        
        #Purge History Item
        self.purgehistory_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Purge History', 'purgeAction:', '')
        self.purgehistory_menu_item.setRepresentedObject_("history")
        self.purgehistory_menu_item.setAlternate_(YES)
        self.purgehistory_menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(self.purgehistory_menu_item)
        
        self.separator_menu_item = NSMenuItem.separatorItem()
        self.menu.addItem_(self.separator_menu_item)

        #Limit Speed Item & Submenu
        self.speed_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Limit Speed', '', '')

        self.menu_speed = NSMenu.alloc().init()

        speeds ={  0 : 'None', 50 :'50 KB/s' , 100 : '100 KB/s', 200 : '200 KB/s' , 300 : '300 KB/s' ,
                   400 : '400 KB/s', 500 :'500 KB/s' , 600 : '600 KB/s', 700 : '700 KB/s' , 800 : '800 KB/s' , 
                   900 : '900 KB/s', 1000 :'1000 KB/s' , 1500 : '1500 KB/s', 2000 : '2000 KB/s' , 3000 : '3000 KB/s' 
                }
                
        for speed in sorted(speeds.keys()):
            menu_speed_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('%s' % (speeds[speed]), 'speedlimitAction:', '')
            menu_speed_item.setRepresentedObject_("%s" % (speed))
            self.menu_speed.addItem_(menu_speed_item)
        
        self.speed_menu_item.setSubmenu_(self.menu_speed)
        self.menu.addItem_(self.speed_menu_item)

        #Pause Item & Submenu
        self.pause_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Pause', 'pauseAction:', '')
        self.pause_menu_item.setRepresentedObject_('0')
        
        self.menu_pause = NSMenu.alloc().init()

        for i in range(6):
            menu_pause_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('%s min.' % ((i+1)*10), 'pauseAction:', '')
            menu_pause_item.setRepresentedObject_("%s" % ((i+1)*10))
            self.menu_pause.addItem_(menu_pause_item)
        
        self.pause_menu_item.setSubmenu_(self.menu_pause)
        self.menu.addItem_(self.pause_menu_item)
        
        #Resume Item
        self.resume_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Resume', 'resumeAction:', '')
        self.resume_menu_item.setHidden_(YES)
        self.menu.addItem_(self.resume_menu_item)

        #Newzbin Item
        self.newzbin_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Get Newzbin Bookmarks', 'getNewzbinBookmarksAction:', '')
        self.newzbin_menu_item.setHidden_(YES)
        self.menu.addItem_(self.newzbin_menu_item)
        
        self.separator2_menu_item = NSMenuItem.separatorItem()
        self.menu.addItem_(self.separator2_menu_item)
        
        #Complete Folder Item
        self.completefolder_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Complete Folder', 'openFolderAction:', '')
        self.completefolder_menu_item.setRepresentedObject_(sabnzbd.cfg.COMPLETE_DIR.get_path())
        self.menu.addItem_(self.completefolder_menu_item)

        #Incomplete Folder Item
        self.incompletefolder_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Incomplete Folder', 'openFolderAction:', '')
        self.incompletefolder_menu_item.setRepresentedObject_(sabnzbd.cfg.DOWNLOAD_DIR.get_path())
        self.menu.addItem_(self.incompletefolder_menu_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        #About Item (TO FIX)
        #menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('About SABnzbd', 'aboutAction:', '')
        #self.menu.addItem_(menu_item)
        
        #Quit Item
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Quit', 'terminate:', '')
        self.menu.addItem_(menu_item)

        #Restart Item
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Restart', 'restartAction:', '')
        menu_item.setAlternate_(YES)
        menu_item.setKeyEquivalentModifierMask_(NSAlternateKeyMask)
        self.menu.addItem_(menu_item)

        #Add menu to Status Item
        self.status_item.setMenu_(self.menu)

        #Timer for updating menu
        self.timer = NSTimer.alloc().initWithFireDate_interval_target_selector_userInfo_repeats_(start_time, 3.0, self, 'updateAction:', None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSDefaultRunLoopMode)
        self.timer.fire()

    def updateAction_(self, notification):
        try:
            if self.serverUpdate():
                self.warningsUpdate()
                self.queueUpdate()
                self.historyUpdate()
                self.stateUpdate()
                self.iconUpdate()
                self.pauseUpdate()
                self.speedlimitUpdate() 
                self.versionUpdate()
                self.newzbinUpdate()
                self.diskspaceUpdate()
        except :
            logging.info("[osx] Exception %s" % (sys.exc_info()[0]))
            
    def queueUpdate(self):
        try:
            qnfo = sabnzbd.nzbqueue.queue_info()
            pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]

            bytesleftprogess = 0
            bpsnow = sabnzbd.bpsmeter.method.get_bps()
            self.info = ""
                
            self.menu_queue = NSMenu.alloc().init()

            if len(pnfo_list):

                job_nb = 1
                for pnfo in pnfo_list:
                    filename = pnfo[PNFO_FILENAME_FIELD]
                    msgid = pnfo[PNFO_MSGID_FIELD]
                    bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
                    bytesleftprogess += pnfo[PNFO_BYTES_LEFT_FIELD]
                    bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
                    nzo_id = pnfo[PNFO_NZO_ID_FIELD]
                    timeleft = self.calc_timeleft(bytesleftprogess, bpsnow)
                    
                    job = "%d. %s (%d/%d MB) %s" % (job_nb, filename, bytesleft, bytes, timeleft)
                    job_nb += 1
                    menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, '', '')
                    self.menu_queue.addItem_(menu_queue_item)
            
                self.info = "%d nzb(s) (%d/%d MB)" % (len(pnfo_list),(qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI), (qnfo[QNFO_BYTES_FIELD] / MEBI))
            
            else:
                menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('empty', '', '')
                self.menu_queue.addItem_(menu_queue_item)
            
            self.queue_menu_item.setSubmenu_(self.menu_queue)

        except :
            logging.info("[osx] queueUpdate Exception %s" % (sys.exc_info()[0]))
            
    def historyUpdate(self):
        try:
            # Fetch history items
            history_db = sabnzbd.database.get_history_handle()
            items, fetched_items, total_items = history_db.fetch_history(0,10,None)
    
            self.menu_history = NSMenu.alloc().init()
            failedAttributes = { NSForegroundColorAttributeName:  NSColor.redColor(),
                                 NSFontAttributeName:             NSFont.menuFontOfSize_(14.0), }
    
            if fetched_items:
                for history in items:
                    #logging.info("[osx] history : %s" % (history))
                    job = "%s" % (history['name'])
                    if os.path.isdir(history['storage']):
                        menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, 'openFolderAction:', '')
                    else:
                        menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, '', '')
                    if history['status'] != "Completed":
                        jobfailed = NSAttributedString.alloc().initWithString_attributes_(job, failedAttributes)
                        menu_history_item.setAttributedTitle_(jobfailed)
                    menu_history_item.setRepresentedObject_("%s" % (history['storage']))
                    self.menu_history.addItem_(menu_history_item)
            else:
                menu_history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("empty", '', '')
                self.menu_history.addItem_(menu_history_item)
                
            self.history_menu_item.setSubmenu_(self.menu_history)
        except :
            logging.info("[osx] historyUpdate Exception %s" % (sys.exc_info()[0]))

    def warningsUpdate(self):
        try:
            warnings = sabnzbd.GUIHANDLER.count()
            if warnings:
                warningsAttributes = {  
                                        NSForegroundColorAttributeName:  NSColor.redColor(),
                                        NSFontAttributeName:             NSFont.menuFontOfSize_(14.0)
                                     }
                
                warningsTitle = NSAttributedString.alloc().initWithString_attributes_("Warnings : %s" % (warnings), warningsAttributes)

                self.warnings_menu_item.setAttributedTitle_(warningsTitle)
                self.warnings_menu_item.setHidden_(NO)
            else:
                self.warnings_menu_item.setTitle_("No Warnings")
                self.warnings_menu_item.setHidden_(YES)            
        except :
            logging.info("[osx] warningsUpdate Exception %s" % (sys.exc_info()[0]))
           
    def stateUpdate(self):
        try:
            qnfo = sabnzbd.nzbqueue.queue_info()
            bpsnow = sabnzbd.bpsmeter.method.get_bps()
            if downloader.paused():
                self.state = "Paused"
                if sabnzbd.scheduler.pause_int() != "0":
                    self.setMenuTitle("\n\n%s\n" % (sabnzbd.scheduler.pause_int()))
                else:
                    self.setMenuTitle("")
            elif qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI > 0:
                
                self.state = ""
                statusbarText = "\n\n%s\n%d KB/s\n" % (self.calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsnow), (bpsnow/KIBI))
                
                if sabnzbd.SABSTOP:
                    statusbarText = "..."
                
                self.setMenuTitle(statusbarText)
            else:
                self.state = "Idle"
                self.setMenuTitle("")
            
            if self.state != "" and self.info != "":
                self.state_menu_item.setTitle_("%s - %s" % (self.state,self.info))
            if self.info == "":
                self.state_menu_item.setTitle_("%s" % (self.state))
            else:
                self.state_menu_item.setTitle_("%s" % (self.info))
        except :
            logging.info("[osx] stateUpdate Exception %s" % (sys.exc_info()[0]))
            
    def iconUpdate(self):
        try:
            if downloader.paused():
                self.status_item.setImage_(self.icons['pause'])
            else:
                self.status_item.setImage_(self.icons['idle'])
        except :
            logging.info("[osx] iconUpdate Exception %s" % (sys.exc_info()[0]))
            
    def pauseUpdate(self):
        try:
            if downloader.paused():
                self.resume_menu_item.setHidden_(NO)
                self.pause_menu_item.setHidden_(YES)
            else:
                self.resume_menu_item.setHidden_(YES)
                self.pause_menu_item.setHidden_(NO)
        except :
            logging.info("[osx] pauseUpdate Exception %s" % (sys.exc_info()[0]))

    def speedlimitUpdate(self):
        try:
            speed = int(downloader.get_limit())
            if self.speed != speed :
                self.speed = speed
                speedsValues = self.menu_speed.numberOfItems()
                for i in range(speedsValues):
                    menuitem = self.menu_speed.itemAtIndex_(i)
                    if speed == int(menuitem.representedObject()):
                        menuitem.setState_(NSOnState)
                    else:
                        menuitem.setState_(NSOffState)
        except :
            logging.info("[osx] speedlimitUpdate Exception %s" % (sys.exc_info()[0]))
                                                    
    def versionUpdate(self):
        try:
            if sabnzbd.NEW_VERSION and self.version_notify:
                logging.info("[osx] New Version : %s" % (sabnzbd.NEW_VERSION))              
                new_release, new_rel_url = sabnzbd.NEW_VERSION.split(';')
                osx.sendGrowlMsg("SABnzbd","New release %s available" % (new_release) )
                self.version_notify = 0
        except :
            logging.info("[osx] versionUpdate Exception %s" % (sys.exc_info()[0]))


    def newzbinUpdate(self):
        try:
            if sabnzbd.cfg.USERNAME_NEWZBIN.get() and sabnzbd.cfg.PASSWORD_NEWZBIN.get() and sabnzbd.cfg.NEWZBIN_BOOKMARKS.get():
                self.newzbin_menu_item.setHidden_(NO)
            else:
                self.newzbin_menu_item.setHidden_(YES)
        except :
            logging.info("[osx] newzbinUpdate Exception %s" % (sys.exc_info()[0]))

    def serverUpdate(self):
        try:
            if not config.get_servers():
                self.state_menu_item.setTitle_("Go to wizard")
                hide=YES
                alternate=NO
                value=0
            else:
                hide=NO
                alternate=YES
                value=1
            self.speed_menu_item.setHidden_(hide)
            self.resume_menu_item.setHidden_(hide)
            self.pause_menu_item.setHidden_(hide)
            self.newzbin_menu_item.setHidden_(hide)
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
            return value

        except :
            logging.info("[osx] configUpdate Exception %s" % (sys.exc_info()[0]))
            return 0

    def diskspaceUpdate(self):
        try:
            self.completefolder_menu_item.setTitle_("Complete Folder\t\t%.2f GB" % (diskfree(sabnzbd.cfg.COMPLETE_DIR.get_path())))
            self.incompletefolder_menu_item.setTitle_("Incomplete Folder\t%.2f GB" % (diskfree(sabnzbd.cfg.DOWNLOAD_DIR.get_path())))
        except :
            logging.info("[osx] diskspaceUpdate Exception %s" % (sys.exc_info()[0]))

    def setMenuTitle(self,text):
        try:
            style = NSMutableParagraphStyle.new()
            style.setParagraphStyle_(NSParagraphStyle.defaultParagraphStyle())
            style.setAlignment_(NSCenterTextAlignment)
            style.setLineSpacing_(0.0)
            style.setMaximumLineHeight_(9.0)
            style.setParagraphSpacing_(-3.0)
    
            titleAttributes = {
                NSBaselineOffsetAttributeName :  5.0,
                NSFontAttributeName:             NSFont.menuFontOfSize_(9.0),
                NSParagraphStyleAttributeName:   style#,
                #NSForegroundColorAttributeName: NSColor.colorWithDeviceWhite_alpha_(0.34, 1)
                }
    
            title = NSAttributedString.alloc().initWithString_attributes_(text, titleAttributes)
            self.status_item.setAttributedTitle_(title)
        except :
            logging.info("[osx] setMenuTitle Exception %s" % (sys.exc_info()[0]))

    def calc_timeleft(self, bytesleft, bps):
        """
        Calculate the time left in the format HH:MM:SS
        """
        try:
            totalseconds = int(bytesleft / bps)
            minutes, seconds = divmod(totalseconds, 60)
            hours, minutes = divmod(minutes, 60)
            if minutes <10:
                minutes = '0%s' % minutes
            if seconds <10:
                seconds = '0%s' % seconds
            return '%s:%s:%s' % (hours, minutes, seconds)
        except:
            return '0:00:00'

    def openBrowserAction_(self, sender):
        if sender.representedObject:
            link = sender.representedObject()
        else:
            link = ""
        #logging.info("[osx] opening http://%s:%s/sabnzbd/%s" % (sabnzbd.cfg.CHERRYHOST.get(), sabnzbd.cfg.CHERRYPORT.get(),link))
        launch_a_browser("http://%s:%s/sabnzbd/%s" % (sabnzbd.cfg.CHERRYHOST.get(), sabnzbd.cfg.CHERRYPORT.get(),link),True)

    def speedlimitAction_(self, sender):
        #logging.info("[osx] speed limit to %s" % (sender.representedObject()))
        speed = int(sender.representedObject())
        if speed != self.speed:
            downloader.limit_speed(speed)
            self.speedlimitUpdate()

    def purgeAction_(self, sender):
        mode = sender.representedObject()
        #logging.info("[osx] purge %s" % (mode))
        if mode == "queue":
            nzbqueue.remove_all_nzo()
        elif mode == "history":
            history_db = sabnzbd.database.get_history_handle()
            history_db.remove_history()

    def pauseAction_(self, sender):
        minutes = int(sender.representedObject())
        #logging.info("[osx] pause for %s" % (minutes))
        if minutes:
            scheduler.plan_resume(minutes)
        else:
            downloader.pause_downloader()

    def resumeAction_(self, sender):
        scheduler.plan_resume(0)

    def getNewzbinBookmarksAction_(self, sender):
        sabnzbd.newzbin.getBookmarksNow()

    def openFolderAction_(self, sender):
        os.system('open "%s"' % sender.representedObject())

#    def aboutAction_(self, sender):
#        app = NSApplication.sharedApplication()
#        app.orderFrontStandardAboutPanel_(nil)

    def restartAction_(self, sender):
        self.setMenuTitle("\n\nStopping...\n")
        sabnzbd.halt()
        cherrypy.engine.restart()
        self.setMenuTitle("\n\nStopping...\n")
        
    def application_openFiles_(self, nsapp, filenames):
        #logging.info('[osx] file open')
        #logging.info('[osx] file : %s' % (filenames))
        pp = None
        script = None
        cat = None
        priority = None
        for name in filenames :
            #logging.info('[osx] processing : %s' % (name))
            if os.path.exists(name):
                fn = get_filename(name)
                #logging.info('[osx] filename : %s' % (fn))
                if fn:
                    if get_ext(name) in ('.zip','.rar', '.gz'):
                        #logging.info('[osx] archive')
                        dirscanner.ProcessArchiveFile(fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True)
                    elif get_ext(name) in ('.nzb'):
                        #logging.info('[osx] nzb')
                        dirscanner.ProcessSingleFile(fn, name, pp=pp, script=script, cat=cat, priority=priority, keep=True)
        #logging.info('opening done')

    def applicationShouldTerminate_(self, sender):
        logging.info('[osx] application terminating')
        self.setMenuTitle("\n\nStopping...\n")
        self.status_item.setHighlightMode_(NO)
        logging.info('[osx] application stopping daemon')
        sabnzbd.halt()
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True
        osx.sendGrowlMsg('SABnzbd',"SABnzbd shutdown finished")
        logging.info('Leaving SABnzbd')
        sys.stderr.flush()
        sys.stdout.flush()
        return NSTerminateNow

