#!/usr/bin/python -OO
#"""OSX Growl Notification
#
#This library expose Growl notifications
#
#
#You may freely use this code in any way you can think of.
#"""
NOTIFICATION_NAME = 'SABnzbd Messages'

try:
    import Growl
    import os.path
    
    try:
        nIcon = Growl.Image.imageFromPath('sabnzbdplus.icns')
    except:
        nIcon = Growl.Image.imageFromPath('osx/resources/sabnzbdplus.icns')
    
    def sendGrowlMsg(nTitle , nMsg):
        gnotifier = SABGrowlNotifier(applicationIcon=nIcon)
        gnotifier.register()
        gnotifier.notify(NOTIFICATION_NAME, nTitle, nMsg)

    class SABGrowlNotifier(Growl.GrowlNotifier):
    	applicationName = "SABnzbd"
    	notifications = [NOTIFICATION_NAME]    
except:
    def sendGrowlMsg(nTitle , nMsg):
        pass