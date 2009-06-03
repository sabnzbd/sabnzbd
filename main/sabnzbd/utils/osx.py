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
    import logging
    import logging.handlers    


    #logging.info('%s/osx/resources/sabnzbdplus.icns' % (sabnzbd.DIR_PROG))

    if os.path.isfile('sabnzbdplus.icns'):
        nIcon = Growl.Image.imageFromPath('sabnzbdplus.icns')
    elif os.path.isfile('osx/resources/sabnzbdplus.icns'):
        nIcon = Growl.Image.imageFromPath('osx/resources/sabnzbdplus.icns')
    else:
        nIcon = Growl.Image.imageWithIconForApplication('Terminal')
    
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