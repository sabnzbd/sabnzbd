#!/usr/bin/python -OO
#"""OSX Growl Notification
#
#This library expose Growl notifications
#
#
#You may freely use this code in any way you can think of.
#"""
NOTIFICATION = {'startup':'Startup/Shutdown','download':'NZB Added','pp':'Post-Processing','other':'Other messages'}

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

    def sendGrowlMsg(nTitle , nMsg, nType=NOTIFICATION['other']):
        gnotifier = SABGrowlNotifier(applicationIcon=nIcon)
        gnotifier.register()
        gnotifier.notify(nType, nTitle, nMsg)

    class SABGrowlNotifier(Growl.GrowlNotifier):
    	applicationName = "SABnzbd"
    	notifications = NOTIFICATION.values()
except ImportError:
    def sendGrowlMsg(nTitle , nMsg):
        pass