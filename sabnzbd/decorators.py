#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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

##############################################################################
# Decorators
##############################################################################
from threading import RLock, Condition

DIR_LOCK = RLock()
DOWNLOADER_CV = Condition(RLock())

def synchronized(lock):
    def wrap(f):
        def newFunction(*args, **kw):
            lock.acquire()
            try:
                return f(*args, **kw)
            finally:
                lock.release()
        return newFunction
    return wrap


def notify_downloader(func):
    global DOWNLOADER_CV
    def call_func(*params, **kparams):
        DOWNLOADER_CV.acquire()
        try:
            return func(*params, **kparams)
        finally:
            DOWNLOADER_CV.notify_all()
            DOWNLOADER_CV.release()
    return call_func
