#!/usr/bin/python -OO
# Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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
#
#"""
#TO FIX : Translations are not working with this implementation
#         Growl Registration may only be done once per run ?
#         Registration is made too early, the language module has not read the text file yet
#NOTIFICATION = {'startup':'grwl-notif-startup','download':'grwl-notif-dl','pp':'grwl-notif-pp','other':'grwl-notif-other'}
NOTIFICATION = {'startup':'1. On Startup/Shutdown','download':'2. On adding NZB','pp':'3. On post-processing','complete':'4. On download terminated','other':'5. Other Messages'}

# For a future release, make texts translatable.
if 0:
    #------------------------------------------------------------------------------
    # Define translatable message table
    TT = lambda x:x
    _NOTIFICATION = {
        'startup'  : TT('1. On Startup/Shutdown'),
        'download' : TT('2. On adding NZB'),
        'pp'       : TT('3. On post-processing'),
        'complete' : TT('4. On download terminated'),
        'other'    : TT('5. Other Messages')
    }

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
    def sendGrowlMsg(nTitle , nMsg, nType):
        pass
