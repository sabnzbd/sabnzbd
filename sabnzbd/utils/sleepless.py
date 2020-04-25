#!/usr/bin/python3 -OO
# Copyright 2009-2020 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.utils.sleepless - Keep macOS (OSX) awake by setting power assertions
"""


import objc
from Foundation import NSBundle


# https://developer.apple.com/documentation/iokit/iopowersources.h?language=objc
IOKit = NSBundle.bundleWithIdentifier_("com.apple.framework.IOKit")

functions = [
    ("IOPMAssertionCreateWithName", b"i@i@o^i"),
    ("IOPMAssertionRelease", b"vi"),
]

objc.loadBundleFunctions(IOKit, globals(), functions)

# Keep track of the assertion ID at the module-level
assertion_id = None


def keep_awake(reason):
    """ Tell OS to stay awake. One argument: text to send to OS.
        Stays in effect until next 'allow_sleep' call.
        Multiple calls allowed.
    """
    global assertion_id
    kIOPMAssertionTypeNoIdleSleep = "PreventUserIdleSystemSleep"
    kIOPMAssertionLevelOn = 255
    errcode, assertion_id = IOPMAssertionCreateWithName(
        kIOPMAssertionTypeNoIdleSleep, kIOPMAssertionLevelOn, reason, None
    )
    return errcode == 0


def allow_sleep():
    """ Allow OS to go to sleep """
    global assertion_id
    if assertion_id:
        IOPMAssertionRelease(assertion_id)
        assertion_id = None
