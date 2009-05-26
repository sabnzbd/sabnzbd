#!/usr/bin/python -OO
#"""OSX Growl Notification
#
#This library expose Growl notifications
#
#
#You may freely use this code in any way you can think of.
#"""

try:
    import Growl
except:
    pass
    
NOTIFICATION_NAME = 'SABnzbd Messages'

def sendGrowlMsg(nTitle , nMsg):
    try:
        gnotifier = SABGrowlNotifier()
        gnotifier.register()
        gnotifier.notify(NOTIFICATION_NAME, nTitle, nMsg)
    except:
        pass
    
class SABGrowlNotifier(Growl.GrowlNotifier):
	applicationName = "SABnzbd"
	notifications = [NOTIFICATION_NAME]
