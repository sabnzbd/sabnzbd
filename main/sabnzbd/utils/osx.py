#!/usr/bin/python -OO
#"""OSX Growl Notification
#
#This library expose Growl notifications
#
#
#You may freely use this code in any way you can think of.
#"""
#TO FIX : Translations are not working with this implementation
#         Growl Registration may only be done once per run ?
#         Registration is made too early, the language module has not read the text file yet
#from sabnzbd.lang import T
#NOTIFICATION = {'startup':'grwl-notif-startup','download':'grwl-notif-dl','pp':'grwl-notif-pp','other':'grwl-notif-other'}
NOTIFICATION = {'startup':'1. On Startup/Shutdown','download':'2. On adding NZB','pp':'3. On post-processing','other':'4. Other Messages'}

try:
    import Growl
    import os.path
    import logging

    if os.path.isfile('sabnzbdplus.icns'):
        nIcon = Growl.Image.imageFromPath('sabnzbdplus.icns')
    elif os.path.isfile('osx/resources/sabnzbdplus.icns'):
        nIcon = Growl.Image.imageFromPath('osx/resources/sabnzbdplus.icns')
    else:
        nIcon = Growl.Image.imageWithIconForApplication('Terminal')

    def sendGrowlMsg(nTitle , nMsg, nType=NOTIFICATION['other']):
        gnotifier = SABGrowlNotifier(applicationIcon=nIcon)
        gnotifier.register()
        #TO FIX
        #gnotifier.notify(T(nType), nTitle, nMsg)
        gnotifier.notify(nType, nTitle, nMsg)

    class SABGrowlNotifier(Growl.GrowlNotifier):
        applicationName = "SABnzbd"
        #TO FIX
        #notifications = [T(notification) for notification in NOTIFICATION.values()]
        notifications = NOTIFICATION.values()

except ImportError:
    def sendGrowlMsg(nTitle , nMsg):
        pass
