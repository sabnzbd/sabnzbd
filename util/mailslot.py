#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.mailslot - Mailslot communication
"""

import os
from win32file import GENERIC_WRITE, FILE_SHARE_READ, \
                      OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL
from ctypes import c_uint, c_buffer, byref, sizeof, windll

# Win32API Shortcuts
CreateFile = windll.kernel32.CreateFileA
ReadFile = windll.kernel32.ReadFile
WriteFile = windll.kernel32.WriteFile
CloseHandle = windll.kernel32.CloseHandle
CreateMailslot = windll.kernel32.CreateMailslotA


class MailSlot(object):
    """ Simple Windows Mailslot communication """
    slotname = r'mailslot\SABnzbd\ServiceSlot'

    def __init__(self):
        self.handle = -1

    def create(self, timeout):
        """ Create the Mailslot, after this only receiving  is possible
            timeout is the read timeout used for receive calls.
        """
        slot = r'\\.\%s' % MailSlot.slotname
        self.handle = CreateMailslot(slot, 0, timeout, None)

        return self.handle != -1

    def connect(self):
        """ Connect to existing Mailslot so that writing is possible """
        slot = r'\\%s\%s' % (os.environ['COMPUTERNAME'], MailSlot.slotname)
        self.handle = CreateFile(slot, GENERIC_WRITE, FILE_SHARE_READ, 0, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, 0)
        return self.handle != -1

    def disconnect(self):
        """ Disconnect from Mailslot """
        if self.handle != -1:
            CloseHandle(self.handle)
            self.handle = -1
        return True

    def send(self, command):
        """ Send one message to Mailslot """
        if self.handle == -1:
            return False
        w = c_uint()
        return bool(WriteFile(self.handle, command, len(command), byref(w), 0))

    def receive(self):
        """ Receive one message from Mailslot """
        r = c_uint()
        buf = c_buffer(1024)
        if ReadFile(self.handle, buf, sizeof(buf), byref(r), 0):
            return buf.value
        else:
            return None


##############################################################################
# Simple test
#
# First start "mailslot.py server" in one process,
# Then start "mailslot.py client" in another.
# Five "restart" and one "stop" will be send from client to server.
# The server will stop after receiving "stop"
##############################################################################

if __name__ == '__main__':
    import sys
    from time import sleep

    if not __debug__:
        print 'Run this test in non-optimized mode'
        exit(1)

    if len(sys.argv) > 1 and 'server' in sys.argv[1]:

        recv = MailSlot()
        ret = recv.create(2)
        assert ret, 'Failed to create'
        while True:
            data = recv.receive()
            if data is not None:
                print data
                if data.startswith('stop'):
                    break
            sleep(2.0)
        recv.disconnect()

    elif len(sys.argv) > 1 and 'client' in sys.argv[1]:

        send = MailSlot()
        ret = send.connect()
        assert ret, 'Failed to connect'
        for n in xrange(5):
            ret = send.send('restart')
            assert ret, 'Failed to send'
            sleep(2.0)
        send.send('stop')
        assert ret, 'Failed to send'
        send.disconnect()

    else:
        print 'Usage: mailslot.py server|client'
