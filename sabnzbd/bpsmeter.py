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

"""
sabnzbd.bpsmeter - bpsmeter
"""

import time
import logging
import re

import sabnzbd
from sabnzbd.constants import BYTES_FILE_NAME
import sabnzbd.cfg as cfg

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

_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
def last_month_day():
    """ Return last day of this month """
    year, month = time.localtime(time.time())[:2]
    day = _DAYS[month]
    if day == 28 and (year % 4) == 0 and (year % 400) == 0:
        day = 29
    return day

def this_day():
    """ Return current day of the month """
    return time.localtime(time.time())[2]

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

def reset_quotum(day):
    """ Reset quotum if turn-over day is reached
    """
    BPSMeter.do.reset_quotum(day)

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
        self.last_month_day = last_month_day()
        self.quotum = self.left = 0.0
        BPSMeter.do = self


    def save(self):
        """ Save admin to disk """
        if self.grand_total or self.day_total or self.week_total or self.month_total:
            data = (self.last_update, self.grand_total,
                    self.day_total, self.week_total, self.month_total,
                    self.end_of_day, self.end_of_week, self.end_of_month, self.quotum, self.left
                   )
            sabnzbd.save_admin(data, BYTES_FILE_NAME)


    def read(self):
        """ Read admin from disk """
        quotum = self.left = cfg.quotum_size.get_float() # Quotum for this month
        data = sabnzbd.load_admin(BYTES_FILE_NAME)
        try:
            self.last_update, self.grand_total, \
            self.day_total, self.week_total, self.month_total, \
            self.end_of_day, self.end_of_week, self.end_of_month = data[:8]
            if len(data) == 10:
                self.quotum, self.left = data[8:]
                logging.debug('Read quotum q=%s l=%s', self.quotum, self.left)
                if abs(quotum - self.quotum) > 0.5:
                    self.change_quotum()
        except:
            # Get the latest data from the database and assign to a fake server
            logging.debug('Setting default BPS meter values')
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

        if self.quotum > 0.0:
            if self.left > 0.0:
                self.left -= amount
            if self.left <= 0.0:
                self.left = -1.0
                from sabnzbd.downloader import Downloader
                if Downloader.do and not Downloader.do.paused:
                    Downloader.do.pause()
                    logging.warning(Ta('Quotum spent, pausing downloading'))

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

    def reset_quotum(self):
        last_day = last_month_day()
        if self.day > last_day:
            self.day = last_day
        if self.day == this_day():
            self.quotum = self.left = cfg.quotum_size.get_float()
            logging.info('Quotum was reset to %s', self.quotum)
            if cfg.quotum_resume():
                logging.info('Auto-resume due to quotum reset')
                sabnzbd.downloader.Downloader.do.resume()

    def change_quotum(self):
        quotum = cfg.quotum_size.get_float()
        self.left = quotum - (self.quotum - self.left)
        self.quotum = quotum
        self.update(0)
        if self.left > 0.5:
            from sabnzbd.downloader import Downloader
            if cfg.quotum_resume() and Downloader.do and Downloader.do.paused:
                Downloader.do.resume()

    __re_day = re.compile('(\d+) +(\d+):(\d+)')
    def get_quotum(self):
        """ If quotum active, return check-function, hour, minute
        """
        if self.quotum > 0.0:
            self.day = 1
            self.hour = self.minute = 0
            txt = cfg.quotum_day().strip()
            if txt.isdigit():
                self.day = int(txt)
            else:
                m = self.__re_day.search(txt)
                if m:
                    self.day = int(m.group(1))
                    self.hour = int(m.group(2))
                    self.minute = int(m.group(3))
            return quotum_handler, self.hour, self.minute
        else:
            return None, 0, 0

    def change_quotum_day(self):
        sabnzbd.scheduler.restart(force=True)


def quotum_handler():
    logging.debug('Checking quotum')
    BPSMeter.do.reset_quotum()


BPSMeter()
