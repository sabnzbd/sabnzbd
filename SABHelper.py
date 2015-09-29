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

import sys
if sys.version_info[:2] < (2, 6) or sys.version_info[:2] >= (3, 0):
    print "Sorry, requires Python 2.6 or 2.7."
    sys.exit(1)

import os
import time
import subprocess


try:
    import win32api
    import win32file
    import win32serviceutil
    import win32evtlogutil
    import win32event
    import win32service
    import pywintypes
except ImportError:
    print "Sorry, requires Python module PyWin32."
    sys.exit(1)

from util.mailslot import MailSlot
from util.apireg import del_connection_info, set_connection_info


WIN_SERVICE = None


def HandleCommandLine(allow_service=True):
    """ Handle command line for a Windows Service
        Prescribed name that will be called by Py2Exe.
        You MUST set 'cmdline_style':'custom' in the package.py!
    """
    win32serviceutil.HandleCommandLine(SABHelper)


def start_sab():
    return subprocess.Popen('net start SABnzbd', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).stdout.read()


def main():

    mail = MailSlot()
    if not mail.create(10):
        return '- Cannot create Mailslot'

    active = False  # SABnzbd should be running
    counter = 0     # Time allowed for SABnzbd to be silent
    while True:
        msg = mail.receive()
        if msg:
            if msg == 'restart':
                time.sleep(1.0)
                counter = 0
                del_connection_info(user=False)
                start_sab()
            elif msg == 'stop':
                active = False
                del_connection_info(user=False)
            elif msg == 'active':
                active = True
                counter = 0
            elif msg.startswith('api '):
                active = True
                counter = 0
                _cmd, url = msg.split()
                if url:
                    set_connection_info(url.strip(), user=False)

        if active:
            counter += 1
            if counter > 120:  # 120 seconds
                counter = 0
                start_sab()

        rc = win32event.WaitForMultipleObjects((WIN_SERVICE.hWaitStop,
             WIN_SERVICE.overlapped.hEvent), 0, 1000)
        if rc == win32event.WAIT_OBJECT_0:
            del_connection_info(user=False)
            mail.disconnect()
            return ''


##############################################################################
# Windows Service Support
##############################################################################
import servicemanager


class SABHelper(win32serviceutil.ServiceFramework):
    """ Win32 Service Handler """

    _svc_name_ = 'SABHelper'
    _svc_display_name_ = 'SABnzbd Helper'
    _svc_deps_ = ["EventLog", "Tcpip"]
    _svc_description_ = 'Automated downloading from Usenet. ' \
                        'This service helps SABnzbd to restart itself.'

    def __init__(self, args):
        global WIN_SERVICE
        win32serviceutil.ServiceFramework.__init__(self, args)

        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.overlapped = pywintypes.OVERLAPPED()  # @UndefinedVariable
        self.overlapped.hEvent = win32event.CreateEvent(None, 0, 0, None)
        WIN_SERVICE = self

    def SvcDoRun(self):
        msg = 'SABHelper-service'
        self.Logger(servicemanager.PYS_SERVICE_STARTED, msg + ' has started')
        res = main()
        self.Logger(servicemanager.PYS_SERVICE_STOPPED, msg + ' has stopped' + res)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def Logger(self, state, msg):
        win32evtlogutil.ReportEvent(self._svc_display_name_,
                                    state, 0,
                                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                                    (self._svc_name_, unicode(msg)))

    def ErrLogger(self, msg, text):
        win32evtlogutil.ReportEvent(self._svc_display_name_,
                                    servicemanager.PYS_SERVICE_STOPPED, 0,
                                    servicemanager.EVENTLOG_ERROR_TYPE,
                                    (self._svc_name_, unicode(msg)),
                                    unicode(text))


##############################################################################
# Platform specific startup code
##############################################################################
if __name__ == '__main__':

    win32serviceutil.HandleCommandLine(SABHelper, argv=sys.argv)
