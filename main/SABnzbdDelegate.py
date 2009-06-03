#!/usr/bin/python -OO
#from email import header
#import Cheetah.DummyTransaction
import objc
from Foundation import *
from AppKit import *
from PyObjCTools import NibClassBuilder, AppHelper
from objc import YES, NO, nil
from threading import Thread

import os
import cherrypy 

import logging
import logging.handlers

import sabnzbd
import sabnzbd.cfg

from sabnzbd.constants import *
from sabnzbd.misc import launch_a_browser
from sabnzbd.utils import osx
from sabnzbd.lang import T

import sabnzbd.scheduler as scheduler
import sabnzbd.downloader as downloader

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
        
        #Menu construction
        self.menu = NSMenu.alloc().init()
        
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Open Web Interface', 'open:', '')
        self.menu.addItem_(menu_item)

        self.queue_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Queue', 'open:', '')
        self.menu.addItem_(self.queue_menu_item)
                            
        self.pause_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Pause', 'pause:', '')
        self.pause_menu_item.setToolTip_('0')
        
        self.menu_pause = NSMenu.alloc().init()

        for i in range(6):
            menu_pause_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('%s min.' % ((i+1)*10), 'pause:', '')
            menu_pause_item.setToolTip_("%s" % ((i+1)*10))
            self.menu_pause.addItem_(menu_pause_item)
        
        self.pause_menu_item.setSubmenu_(self.menu_pause)
        self.menu.addItem_(self.pause_menu_item)
        
        self.resume_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Resume', 'resume:', '')
        self.resume_menu_item.setHidden_(YES)

        self.menu.addItem_(self.resume_menu_item)

        if sabnzbd.cfg.USERNAME_NEWZBIN.get() and sabnzbd.cfg.PASSWORD_NEWZBIN.get() and sabnzbd.cfg.NEWZBIN_BOOKMARKS.get():
            menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Get Newzbin Bookmarks', 'getNewzbinBookmarks:', '')
            self.menu.addItem_(menu_item)                   
        
        self.menu.addItem_(NSMenuItem.separatorItem())
        
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Complete Folder', 'openCompleteFolder:', '')
        self.menu.addItem_(menu_item)

        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Incomplete Folder', 'openIncompleteFolder:', '')
        self.menu.addItem_(menu_item)

        self.menu.addItem_(NSMenuItem.separatorItem())

        #menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('About', 'infoPanel:', '')
        #self.menu.addItem_(menu_item)
        
        menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Quit', 'terminate:', '')
        self.menu.addItem_(menu_item)

        self.status_item.setMenu_(self.menu)

        #Timer for updating menu                    
        self.timer = NSTimer.alloc().initWithFireDate_interval_target_selector_userInfo_repeats_(start_time, 3.0, self, 'update:', None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSDefaultRunLoopMode)
        self.timer.fire()

    def setMenuTitle(self,text):
    
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
#            NSForegroundColorAttributeName: NSColor.colorWithDeviceWhite_alpha_(0.34, 1)
            }

        title = NSAttributedString.alloc().initWithString_attributes_(text, titleAttributes)
        self.status_item.setAttributedTitle_(title)

    def update_(self, notification):
    
    
        try:
            qnfo = sabnzbd.nzbqueue.queue_info()
            bpsnow = sabnzbd.bpsmeter.method.get_bps()
            state = "IDLE"
            if downloader.paused():
                state = "PAUSED"
                if sabnzbd.scheduler.pause_int() != "0":
                    self.setMenuTitle("\n\n%s\n" % (sabnzbd.scheduler.pause_int()))
                else:
                    self.setMenuTitle("")
            elif qnfo[QNFO_BYTES_LEFT_FIELD] / MEBI > 0:
                
                state = "DOWNLOADING"
                statusbarText = "\n\n%s\n%d KB/s\n" % (self.calc_timeleft(qnfo[QNFO_BYTES_LEFT_FIELD], bpsnow), (bpsnow/KIBI))
                
                if sabnzbd.SABSTOP:
                    statusbarText = "..."
                
                self.setMenuTitle(statusbarText)
            else:
                self.setMenuTitle("")
        except:
            pass                      
    
        if downloader.paused():
            self.status_item.setImage_(self.icons['pause'])
            self.resume_menu_item.setHidden_(NO)
            self.pause_menu_item.setHidden_(YES)
        else:
            self.status_item.setImage_(self.icons['idle'])
            self.resume_menu_item.setHidden_(YES)
            self.pause_menu_item.setHidden_(NO)
        
        self.queueupdate()                   
        

    def queueupdate(self):

        try:
            qnfo = sabnzbd.nzbqueue.queue_info()
            pnfo_list = qnfo[QNFO_PNFO_LIST_FIELD]
                
            bytesleftprogess = 0
            bpsnow = sabnzbd.bpsmeter.method.get_bps()
                
            self.menu_queue = NSMenu.alloc().init()

            job_nb = 1
            for pnfo in pnfo_list:
                filename = pnfo[PNFO_FILENAME_FIELD]
                msgid = pnfo[PNFO_MSGID_FIELD]
                bytesleft = pnfo[PNFO_BYTES_LEFT_FIELD] / MEBI
                bytesleftprogess += pnfo[PNFO_BYTES_LEFT_FIELD]
                bytes = pnfo[PNFO_BYTES_FIELD] / MEBI
                nzo_id = pnfo[PNFO_NZO_ID_FIELD]
                timeleft = self.calc_timeleft(bytesleftprogess, bpsnow)
                
                job = "%d. %s (%d / %d MB) %s" % (job_nb, filename, bytesleft, bytes, timeleft)
                job_nb += 1
                menu_queue_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(job, '', '')
                self.menu_queue.addItem_(menu_queue_item)
            
            self.queue_menu_item.setSubmenu_(self.menu_queue)
        except:
            pass

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

    def pause_(self, notification):
        #logging.info("[osx] pause for %s" % (notification.toolTip()))
        minutes = int(notification.toolTip())
        logging.info("[osx] pause for %s" % (minutes))
        scheduler.plan_resume(minutes)
        downloader.set_paused(True)

    def infoPanel_(self):
        self.activateIgnoringOtherApps_(1)
        self.orderFrontStandardAboutPanel(self)

    def resume_(self, notification):
        scheduler.plan_resume(0)
        downloader.set_paused(False)

    def open_(self, notification):
        #logging.info("[osx] opening http://%s:%s/sabnzbd" % (sabnzbd.cfg.CHERRYHOST.get(), sabnzbd.cfg.CHERRYPORT.get()))
        launch_a_browser("http://%s:%s/sabnzbd" % (sabnzbd.cfg.CHERRYHOST.get(), sabnzbd.cfg.CHERRYPORT.get()),True)

    def openCompleteFolder_(self, notification):
        #logging.info("[osx] opening %s" % (sabnzbd.cfg.COMPLETE_DIR.get_path()))
        os.system('open "%s"' % sabnzbd.cfg.COMPLETE_DIR.get_path())

    def openIncompleteFolder_(self, notification):
        #logging.info("[osx] opening %s" % (sabnzbd.cfg.DOWNLOAD_DIR.get_path()))
        os.system('open "%s"' % sabnzbd.cfg.DOWNLOAD_DIR.get_path())

    def getNewzbinBookmarks_(self, notification):
        sabnzbd.newzbin.getBookmarksNow()

    def applicationShouldTerminate_(self, sender):
        logging.info('[osx] application terminating')
        self.setMenuTitle("\n\nStopping...\n")
        self.status_item.setHighlightMode_(0)
        logging.info('[osx] application stopping daemon')
        sabnzbd.halt()
        cherrypy.engine.exit()
        sabnzbd.SABSTOP = True
        osx.sendGrowlMsg('SABnzbd',"SABnzbd shutdown finished")
        logging.info('Leaving SABnzbd')
        sys.stderr.flush()
        sys.stdout.flush()
        return NSTerminateNow

