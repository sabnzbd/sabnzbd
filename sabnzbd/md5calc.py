#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.md5calc - threaded MD5 calculator
"""

import queue
import logging
from threading import Thread
from typing import Tuple, Optional

from sabnzbd.nzbstuff import NzbFile


class MD5Calc(Thread):
    def __init__(self):
        super().__init__()
        self.queue: queue.Queue[Tuple[Optional[NzbFile], Optional[str]]] = queue.Queue()

    def stop(self):
        self.queue.put((None, None))

    def process(self, nzf: Optional[NzbFile] = None, data: Optional[str] = None):
        self.queue.put((nzf, data))

    def run(self):
        while 1:
            data = nzf = None
            nzf, data = self.queue.get()
            if not nzf:
                logging.debug("Shutting down MD5Calc")
                break
            if data:
                nzf.md5.update(data)
            else:
                logging.debug("Finishing MD5calc for %s", nzf.filename)
                nzf.md5sum = nzf.md5.digest()
