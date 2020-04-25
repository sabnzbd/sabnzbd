#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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
from sabnzbd.constants import BYTES_FILE_NAME, KIBI
import sabnzbd.cfg as cfg

DAY = float(24 * 60 * 60)
WEEK = DAY * 7


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
def last_month_day(tm):
    """ Return last day of this month """
    year, month = tm[:2]
    day = _DAYS[month]
    # This simple formula for leap years is good enough
    if day == 28 and (year % 4) == 0:
        day = 29
    return day


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


class BPSMeter:
    do = None

    def __init__(self):
        t = time.time()
        self.start_time = t
        self.log_time = t
        self.speed_log_time = t
        self.last_update = t
        self.bps = 0.0
        self.bps_list = []
        self.bps_list_max = 275

        self.day_total = {}
        self.week_total = {}
        self.month_total = {}
        self.grand_total = {}

        self.timeline_total = {}

        self.day_label = time.strftime("%Y-%m-%d")
        self.end_of_day = tomorrow(t)      # Time that current day will end
        self.end_of_week = next_week(t)    # Time that current day will end
        self.end_of_month = next_month(t)  # Time that current month will end
        self.q_day = 1                     # Day of quota reset
        self.q_period = 'm'                # Daily/Weekly/Monthly quota = d/w/m
        self.quota = self.left = 0.0       # Quota and remaining quota
        self.have_quota = False            # Flag for quota active
        self.q_time = 0                    # Next reset time for quota
        self.q_hour = 0                    # Quota reset hour
        self.q_minute = 0                  # Quota reset minute
        self.quota_enabled = True          # Scheduled quota enable/disable
        BPSMeter.do = self

    def save(self):
        """ Save admin to disk """
        data = (self.last_update, self.grand_total,
                self.day_total, self.week_total, self.month_total,
                self.end_of_day, self.end_of_week, self.end_of_month,
                self.quota, self.left, self.q_time, self.timeline_total
               )
        sabnzbd.save_admin(data, BYTES_FILE_NAME)

    def defaults(self):
        """ Get the latest data from the database and assign to a fake server """
        logging.debug('Setting default BPS meter values')
        history_db = sabnzbd.database.HistoryDB()
        grand, month, week = history_db.get_history_size()
        history_db.close()
        self.grand_total = {}
        self.month_total = {}
        self.week_total = {}
        self.day_total = {}
        if grand:
            self.grand_total['x'] = grand
        if month:
            self.month_total['x'] = month
        if week:
            self.week_total['x'] = week
        self.quota = self.left = cfg.quota_size.get_float()

    def read(self):
        """ Read admin from disk, return True when pause is needed """
        res = False
        quota = self.left = cfg.quota_size.get_float()  # Quota for this period
        self.have_quota = bool(cfg.quota_size())
        data = sabnzbd.load_admin(BYTES_FILE_NAME)
        try:
            self.last_update, self.grand_total, \
                self.day_total, self.week_total, self.month_total, \
                self.end_of_day, self.end_of_week, self.end_of_month, \
                self.quota, self.left, self.q_time, self.timeline_total = data
            if abs(quota - self.quota) > 0.5:
                self.change_quota()
            res = self.reset_quota()
        except:
            self.defaults()
        # Force update of counters and validate data
        try:
            for server in self.grand_total.keys():
                self.update(server)
        except TypeError:
            self.defaults()
            self.update()
        return res

    def update(self, server=None, amount=0, testtime=None):
        """ Update counters for "server" with "amount" bytes """
        if testtime:
            t = testtime
        else:
            t = time.time()
        if t > self.end_of_day:
            # current day passed. get new end of day
            self.day_label = time.strftime("%Y-%m-%d")
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
                self.day_total[server] = 0
            self.day_total[server] += amount

            if server not in self.week_total:
                self.week_total[server] = 0
            self.week_total[server] += amount

            if server not in self.month_total:
                self.month_total[server] = 0
            self.month_total[server] += amount

            if server not in self.grand_total:
                self.grand_total[server] = 0
            self.grand_total[server] += amount

            if server not in self.timeline_total:
                self.timeline_total[server] = {}
            if self.day_label not in self.timeline_total[server]:
                self.timeline_total[server][self.day_label]= 0
            self.timeline_total[server][self.day_label] += amount

            # Quota check
            if self.have_quota and self.quota_enabled:
                self.left -= amount
                if self.left <= 0.0:
                    if sabnzbd.downloader.Downloader.do and not sabnzbd.downloader.Downloader.do.paused:
                        sabnzbd.downloader.Downloader.do.pause()
                        logging.warning(T('Quota spent, pausing downloading'))

        # Speedometer
        try:
            self.bps = (self.bps * (self.last_update - self.start_time) + amount) / (t - self.start_time)
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

        if self.speed_log_time < (t - 1.0):
            self.add_empty_time()
            self.bps_list.append(int(self.bps / KIBI))
            self.speed_log_time = t

    def reset(self):
        t = time.time()
        self.start_time = t
        self.log_time = t
        self.last_update = t
        self.bps = 0.0

    def add_empty_time(self):
        # Extra zeros, but never more than the maximum!
        nr_diffs = min(int(time.time() - self.speed_log_time), self.bps_list_max)
        if nr_diffs > 1:
            self.bps_list.extend([0] * nr_diffs)

        # Always trim the list to the max-length
        if len(self.bps_list) > self.bps_list_max:
            self.bps_list = self.bps_list[len(self.bps_list) - self.bps_list_max:]

    def get_sums(self):
        """ return tuple of grand, month, week, day totals """
        return (sum([v for v in self.grand_total.values()]),
                sum([v for v in self.month_total.values()]),
                sum([v for v in self.week_total.values()]),
                sum([v for v in self.day_total.values()]))

    def amounts(self, server):
        """ Return grand, month, week, day totals for specified server """
        return self.grand_total.get(server, 0), \
               self.month_total.get(server, 0), \
               self.week_total.get(server, 0),  \
               self.day_total.get(server, 0), \
               self.timeline_total.get(server, {})

    def clear_server(self, server):
        """ Clean counters for specified server """
        if server in self.day_total:
            del self.day_total[server]
        if server in self.week_total:
            del self.week_total[server]
        if server in self.month_total:
            del self.month_total[server]
        if server in self.grand_total:
            del self.grand_total[server]
        if server in self.timeline_total:
            del self.timeline_total[server]
        self.save()

    def get_bps_list(self):
        refresh_rate = int(cfg.refresh_rate()) if cfg.refresh_rate() else 1
        self.add_empty_time()
        # We record every second, but display at the user's refresh-rate
        return self.bps_list[::refresh_rate]

    def get_stable_speed(self, timespan=10):
        """ See if there is a stable speed the last <timespan> seconds
            None: indicates it can't determine yet
            False: the speed was not stable during <timespan>
        """
        if len(self.bps_list) < timespan:
            return None

        # Calculate the variance in the speed
        avg = sum(self.bps_list[-timespan:]) / timespan
        vari = 0
        for bps in self.bps_list[-timespan:]:
            vari += abs(bps - avg)
        vari = vari / timespan

        try:
            # See if the variance is less than 5%
            if (vari / (self.bps / KIBI)) < 0.05:
                return avg
            else:
                return False
        except:
            # Probably one of the values was 0
            pass
        return None

    def reset_quota(self, force=False):
        """ Check if it's time to reset the quota, optionally resuming
            Return True, when still paused
        """
        if force or (self.have_quota and time.time() > (self.q_time - 50)):
            self.quota = self.left = cfg.quota_size.get_float()
            logging.info('Quota was reset to %s', self.quota)
            if cfg.quota_resume():
                logging.info('Auto-resume due to quota reset')
                if sabnzbd.downloader.Downloader.do:
                    sabnzbd.downloader.Downloader.do.resume()
            self.next_reset()
            return False
        else:
            return True

    def next_reset(self, t=None):
        """ Determine next reset time """
        t = t or time.time()
        tm = time.localtime(t)
        if self.q_period == 'd':
            nx = (tm[0], tm[1], tm[2], self.q_hour, self.q_minute, 0, 0, 0, tm[8])
            if (tm.tm_hour * 60 + tm.tm_min) >= (self.q_hour * 60 + self.q_minute):
                # If today's moment has passed, it will happen tomorrow
                t = time.mktime(nx) + 24 * 3600
                tm = time.localtime(t)
        elif self.q_period == 'w':
            if self.q_day < tm.tm_wday + 1 or (self.q_day == tm.tm_wday + 1 and (tm.tm_hour * 60 + tm.tm_min) >= (self.q_hour * 60 + self.q_minute)):
                tm = time.localtime(next_week(t))
            dif = abs(self.q_day - tm.tm_wday - 1)
            t = time.mktime(tm) + dif * 24 * 3600
            tm = time.localtime(t)
        elif self.q_period == 'm':
            if self.q_day < tm.tm_mday or (self.q_day == tm.tm_mday and (tm.tm_hour * 60 + tm.tm_min) >= (self.q_hour * 60 + self.q_minute)):
                tm = time.localtime(next_month(t))
            day = min(last_month_day(tm), self.q_day)
            tm = (tm[0], tm[1], day, self.q_hour, self.q_minute, 0, 0, 0, tm[8])
        else:
            return
        tm = (tm[0], tm[1], tm[2], self.q_hour, self.q_minute, 0, 0, 0, tm[8])
        self.q_time = time.mktime(tm)
        logging.debug('Will reset quota at %s', tm)

    def change_quota(self, allow_resume=True):
        """ Update quota, potentially pausing downloader """
        if not self.have_quota and self.quota < 0.5:
            # Never set, use last period's size
            per = cfg.quota_period()
            sums = self.get_sums()
            if per == 'd':
                self.left = sums[3]
            elif per == 'w':
                self.left = sums[2]
            elif per == 'm':
                self.left = sums[1]

        self.have_quota = bool(cfg.quota_size())
        if self.have_quota:
            quota = cfg.quota_size.get_float()
            if self.quota:
                # Quota change, recalculate amount left
                self.left = quota - (self.quota - self.left)
            else:
                # If previously no quota, self.left holds this period's usage
                self.left = quota - self.left
            self.quota = quota
        else:
            self.quota = self.left = 0
        self.update(0)
        self.next_reset()
        if self.left > 0.5 and allow_resume:
            self.resume()

    # Pattern = <day#> <hh:mm>
    # The <day> and <hh:mm> part can both be optional
    __re_day = re.compile(r'^\s*(\d+)[^:]*')
    __re_hm = re.compile(r'(\d+):(\d+)\s*$')
    def get_quota(self):
        """ If quota active, return check-function, hour, minute """
        if self.have_quota:
            self.q_period = cfg.quota_period()[0].lower()
            self.q_day = 1
            self.q_hour = self.q_minute = 0
            txt = cfg.quota_day().lower()
            m = self.__re_day.search(txt)
            if m:
                self.q_day = int(m.group(1))
            m = self.__re_hm.search(txt)
            if m:
                self.q_hour = int(m.group(1))
                self.q_minute = int(m.group(2))
            if self.q_period == 'w':
                self.q_day = max(1, self.q_day)
                self.q_day = min(7, self.q_day)
            elif self.q_period == 'm':
                self.q_day = max(1, self.q_day)
                self.q_day = min(31, self.q_day)
            else:
                self.q_day = 1
            self.change_quota(allow_resume=False)
            return quota_handler, self.q_hour, self.q_minute
        else:
            return None, 0, 0

    def set_status(self, status, action=True):
        """ Disable/enable quota management """
        self.quota_enabled = status
        if action and not status:
            self.resume()

    def resume(self):
        """ Resume downloading """
        if cfg.quota_resume() and sabnzbd.downloader.Downloader.do and sabnzbd.downloader.Downloader.do.paused:
            sabnzbd.downloader.Downloader.do.resume()

    def midnight(self):
        """ Midnight action: dummy update for all servers """
        for server in self.day_total.keys():
            self.update(server)


def quota_handler():
    """ To be called from scheduler """
    logging.debug('Checking quota')
    BPSMeter.do.reset_quota()


def midnight_action():
    if BPSMeter.do:
        BPSMeter.do.midnight()


BPSMeter()
