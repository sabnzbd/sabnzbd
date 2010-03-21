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

"""
sabnzbd.bpsmeter - bpsmeter
"""

import time
import logging

#------------------------------------------------------------------------------

class BPSMeter:
    do = None

    def __init__(self, bytes_sum = 0):
        t = time.time()

        self.start_time = t
        self.log_time = t
        self.last_update = t
        self.bps = 0.0
        self.bytes_total = 0
        self.bytes_sum = bytes_sum
        BPSMeter.do = self

    def update(self, bytes_recvd):
        self.bytes_total += bytes_recvd
        self.bytes_sum += bytes_recvd

        t = time.time()
        try:
            self.bps = (self.bps * (self.last_update - self.start_time)
                        + bytes_recvd) / (t - self.start_time)
        except:
            self.bps = 0.0

        self.last_update = t

        check_time = t - 5.0

        if self.start_time < check_time:
            self.start_time = check_time

        if self.bps < 0.01:
            self.reset()

        elif self.log_time < check_time:
            logging.debug("bps: %s", self.bps)
            self.log_time = t

    def get_sum(self):
        return self.bytes_sum

    def reset(self):
        self.__init__(bytes_sum = self.bytes_sum)

    def get_bps(self):
        return self.bps


BPSMeter()
