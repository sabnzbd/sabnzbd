#!/usr/bin/python -OO
# Copyright 2008-2010 The SABnzbd-Team <team@sabnzbd.org>
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
if sys.version_info < (2,4):
    print "Sorry, requires Python 2.4 or higher."
    sys.exit(1)

import os
import time
import subprocess

#------------------------------------------------------------------------------
try:
    import win32api, win32file
    import win32serviceutil, win32evtlogutil, win32event, win32service, pywintypes
except ImportError:
    if sabnzbd.WIN32:
        print "Sorry, requires Python module PyWin32."
        sys.exit(1)

from sabnzbd.utils.mailslot import MailSlot

#------------------------------------------------------------------------------

WIN_SERVICE = None

#------------------------------------------------------------------------------
def HandleCommandLine(allow_service=True):
    """ Handle command line for a Windows Service
        Prescribed name that will be called by Py2Exe.
        You MUST set 'cmdline_style':'custom' in the package.py!
        Returns True when any service commands were detected.
    """
    win32serviceutil.HandleCommandLine(SABHelper)


#------------------------------------------------------------------------------
def main():

    mail = MailSlot()
    if not mail.create(200):
        return '- Cannot create Mailslot'

    while True:
        msg = mail.receive()
        if msg == 'restart':
            time.sleep(1.0)
            res = subprocess.Popen('net start SABnzbd', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).stdout.read()
        rc = win32event.WaitForMultipleObjects((WIN_SERVICE.hWaitStop,
             WIN_SERVICE.overlapped.hEvent), 0, 500)
        if rc == win32event.WAIT_OBJECT_0:
            mail.disconnect()
            return ''


#####################################################################
#
# Windows Service Support
#
import servicemanager
class SABHelper(win32serviceutil.ServiceFramework):
    """ Win32 Service Handler """

    _svc_name_ = 'SABHelper'
    _svc_display_name_ = 'SABnzbd Helper'
    _svc_deps_ = ["EventLog", "Tcpip"]
    _svc_description_ = 'Automated downloading from Usenet. ' \
                        'This service helps SABnzbdcd.. to restart itself.'

    def __init__(self, args):
        global WIN_SERVICE
        win32serviceutil.ServiceFramework.__init__(self, args)

        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.overlapped = pywintypes.OVERLAPPED()
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



#####################################################################
#
# Platform specific startup code
#
if __name__ == '__main__':

    win32serviceutil.HandleCommandLine(SABHelper, argv=sys.argv)
