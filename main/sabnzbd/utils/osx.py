#!/usr/bin/python -OO
#"""OSX Growl Notification
#
#This library expose Growl notifications
#
#
#You may freely use this code in any way you can think of.
#"""
from sabnzbd.lang import T
NOTIFICATION = {'startup':'grwl-notif-startup','download':'grwl-notif-dl','pp':'grwl-notif-pp','other':'grwl-notif-other'}

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

    def sendGrowlMsg(nTitle , nMsg, nType=T(NOTIFICATION['other'])):
        gnotifier = SABGrowlNotifier(applicationIcon=nIcon)
        gnotifier.register()
        gnotifier.notify(nType, nTitle, nMsg)

    class SABGrowlNotifier(Growl.GrowlNotifier):
    	applicationName = "SABnzbd"
    	notifications = T(NOTIFICATION.values())
except ImportError:
    def sendGrowlMsg(nTitle , nMsg):
        pass
