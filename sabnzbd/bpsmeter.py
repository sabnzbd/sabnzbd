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

import sabnzbd
from sabnzbd.constants import BYTES_FILE_NAME

DAY = float(24*60*60)
WEEK = DAY * 7

#------------------------------------------------------------------------------

def tomorrow(t):
    """ Return timestamp for tomorrow (midnight) """
    now = time.localtime(t)
    ntime = (now[0], now[1], now[2], 0, 0, 0, now[6], now[7], now[8])
    return time.mktime(ntime) + DAY


def this_week(t):
    """ Return timestamp for start of this week (monday) """
    while 1:
        tm = time.localtime(t)
        if tm.tm_wday == 0:
            break
        t -= DAY
    monday = (tm.tm_year, tm.tm_mon, tm.tm_mday, 0, 0, 0, 0, 0, tm.tm_isdst)
    return time.mktime(monday)


def next_week(t):
    """ Return timestamp for start of next week (monday) """
    return this_week(t) + WEEK


def this_month(t):
    """ Return timestamp for start of next month """
    now = time.localtime(t)
    ntime = (now[0], now[1], 1, 0, 0, 0, 0, 0, now[8])
    return time.mktime(ntime)


def next_month(t):
    """ Return timestamp for start of next month """
    now = time.localtime(t)
    month = now.tm_mon + 1
    year = now.tm_year
    if month > 12:
        month = 1
        year += 1
    ntime = (year, month, 1, 0, 0, 0, 0, 0, now[8])
    return time.mktime(ntime)


class BPSMeter(object):
    do = None

    def __init__(self):
        t = time.time()

        self.start_time = t
        self.log_time = t
        self.last_update = t
        self.bps = 0.0

        self.day_total = {}
        self.week_total = {}
        self.month_total = {}
        self.grand_total = {}

        self.end_of_day = tomorrow(t)     # Time that current day will end
        self.end_of_week = next_week(t)   # Time that current day will end
        self.end_of_month = next_month(t) # Time that current month will end
        BPSMeter.do = self


    def save(self):
        """ Save admin to disk """
        if self.grand_total or self.day_total or self.week_total or self.month_total:
            data = (self.last_update, self.grand_total,
                    self.day_total, self.week_total, self.month_total,
                    self.end_of_day, self.end_of_week, self.end_of_month,
                   )
            sabnzbd.save_admin(data, BYTES_FILE_NAME)


    def read(self):
        """ Read admin from disk """
        data = sabnzbd.load_admin(BYTES_FILE_NAME)
        try:
            self.last_update, self.grand_total, \
            self.day_total, self.week_total, self.month_total, \
            self.end_of_day, self.end_of_week, self.end_of_month = data
        except:
            # Get the latest data from the database and assign to a fake server
            grand, month, week  = sabnzbd.proxy_get_history_size()
            if grand: self.grand_total['x'] = grand
            if month: self.month_total['x'] = month
            if week:  self.week_total['x'] = week
        # Force update of counters
        self.update()


    def update(self, server=None, amount=0, testtime=None):
        """ Update counters for "server" with "amount" bytes
        """
        if testtime:
            t = testtime
        else:
            t = time.time()
        if t > self.end_of_day:
            # current day passed. get new end of day
            self.day_total = {}
            self.end_of_day = tomorrow(t) - 1.0

            if t > self.end_of_week:
                self.week_total = {}
                self.end_of_week = next_week(t) - 1.0

            if t > self.end_of_month:
                self.month_total = {}
                self.end_of_month = next_month(t) - 1.0

        if server:
            if server not in self.day_total:
                self.day_total[server] = 0L
            self.day_total[server] += amount

            if server not in self.week_total:
                self.week_total[server] = 0L
            self.week_total[server] += amount

            if server not in self.month_total:
                self.month_total[server] = 0L
            self.month_total[server] += amount

            if server not in self.grand_total:
                self.grand_total[server] = 0L
            self.grand_total[server] += amount

        # Speedometer
        try:
            self.bps = (self.bps * (self.last_update - self.start_time)
                        + amount) / (t - self.start_time)
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


    def reset(self):
        t = time.time()
        self.start_time = t
        self.log_time = t
        self.last_update = t
        self.bps = 0.0

    def get_sums(self):
        """ return tuple of grand, month, week, day totals """
        return (sum([v for v in self.grand_total.values()]),
                sum([v for v in self.month_total.values()]),
                sum([v for v in self.week_total.values()]),
                sum([v for v in self.day_total.values()])
               )

    def amounts(self, server):
        """ Return grand, month, week, day totals for specified server """
        return self.grand_total.get(server, 0L), \
               self.month_total.get(server, 0L), \
               self.week_total.get(server, 0L),  \
               self.day_total.get(server, 0L)

    def get_bps(self):
        return self.bps


BPSMeter()
