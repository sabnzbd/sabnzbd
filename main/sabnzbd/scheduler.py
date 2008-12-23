#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.scheduler - Event Scheduler
"""
#------------------------------------------------------------------------------

__NAME__ = "scheduler"


import random
import logging
import time

from sabnzbd.utils.kronos import ThreadedScheduler
import sabnzbd.rss as rss
import sabnzbd.newzbin as newzbin
import sabnzbd.misc
import sabnzbd.config as config

SCHEDULES = config.OptionList('misc', 'schedlines')

__SCHED = None  # Global pointer to Scheduler instance

RSSTASK_MINUTE = random.randint(0, 59)
SCHEDULE_GUARD_FLAG = False


def schedule_guard():
    """ Set flag for scheduler restart """
    global SCHEDULE_GUARD_FLAG
    SCHEDULE_GUARD_FLAG = True


def init():
    """ Create the scheduler and set all required events
    """
    global __SCHED, CFG

    need_rsstask = True
    need_versioncheck = sabnzbd.misc.VERSION_CHECK.get()
    bookmarks = newzbin.NEWZBIN_BOOKMARKS.get()
    bookmark_rate = newzbin.BOOKMARK_RATE.get()
    schedlines = SCHEDULES.get()

    __SCHED = ThreadedScheduler()

    for schedule in schedlines:
        arguments = []
        argument_list = None
        try:
            m, h, d, action_name = schedule.split()
        except:
            m, h, d, action_name, argument_list = schedule.split(None, 4)
        if argument_list:
            arguments = argument_list.split()

        m = int(m)
        h = int(h)
        if d == '*':
            d = range(1, 8)
        else:
            d = [int(d)]

        if action_name == 'resume':
            action = sabnzbd.resume_downloader
            arguments = []
        elif action_name == 'pause':
            action = sabnzbd.pause_downloader
            arguments = []
        elif action_name == 'shutdown':
            action = sabnzbd.shutdown_program
            arguments = []
        elif action_name == 'speedlimit' and arguments != []:
            action = sabnzbd.limit_speed
        elif action_name == 'enable_server' and arguments != []:
            action = sabnzbd.enable_server
        elif action_name == 'disable_server' and arguments != []:
            action = sabnzbd.disable_server
        else:
            logging.warning("[%s] Unknown action: %s", __NAME__, action_name)
            continue

        logging.debug("[%s] scheduling action:%s arguments:%s",__NAME__, action_name, arguments)

        #(action, taskname, initialdelay, interval, processmethod, actionargs)
        __SCHED.addDaytimeTask(action, '', d, None, (h, m),
                             __SCHED.PM_SEQUENTIAL, arguments)

    if need_rsstask:
        d = range(1, 8) # all days of the week
        interval = sabnzbd.RSS_RATE
        ran_m = random.randint(0,interval-1)
        for n in range(0, 24*60, interval):
            at = n + ran_m
            h = int(at/60)
            m = at - h*60
            logging.debug("Scheduling RSS task %s %s:%s", d, h, m)
            __SCHED.addDaytimeTask(rss.run_method, '', d, None, (h, m), __SCHED.PM_SEQUENTIAL, [])


    if need_versioncheck:
        # Check for new release, once per week on random time
        m = random.randint(0, 59)
        h = random.randint(0, 23)
        d = (random.randint(1, 7), )

        logging.debug("Scheduling VersionCheck day=%s time=%s:%s", d, h, m)
        __SCHED.addDaytimeTask(sabnzbd.misc.check_latest_version, '', d, None, (h, m), __SCHED.PM_SEQUENTIAL, [])


    if bookmarks:
        d = range(1, 8) # all days of the week
        interval = bookmark_rate
        ran_m = random.randint(0,interval-1)
        for n in range(0, 24*60, interval):
            at = n + ran_m
            h = int(at/60)
            m = at - h*60
            logging.debug("Scheduling Bookmark task %s %s:%s", d, h, m)
            __SCHED.addDaytimeTask(newzbin.getBookmarksNow, '', d, None, (h, m), __SCHED.PM_SEQUENTIAL, [])

    # Subscribe to bookmark schedule changes
    newzbin.NEWZBIN_BOOKMARKS.callback(schedule_guard)
    newzbin.BOOKMARK_RATE.callback(schedule_guard)


def start():
    """ Start the scheduler
    """
    global __SCHED
    if __SCHED:
        logging.debug('[%s] Starting scheduler', __NAME__)
        __SCHED.start()


def restart(force=False):
    """ Stop and start scheduler
    """
    global __PARMS, SCHEDULE_GUARD_FLAG

    if force or SCHEDULE_GUARD_FLAG:
        SCHEDULE_GUARD_FLAG = False
        stop()

        analyse()

        init()
        start()


def stop():
    """ Stop the scheduler, destroy instance
    """
    global __SCHED
    if __SCHED:
        logging.debug('Stopping scheduler')
        __SCHED.stop()
        del __SCHED
        __SCHED = None



def sort_schedules(forward):
    """ Sort the schedules, based on order of happening from now
        forward: assume expired daily event to occur tomorrow
    """

    events = []
    paused = None
    speedlimit = None
    now = time.localtime()
    now_hm = int(now[3])*60 + int(now[4])
    now = int(now[6])*24*60 + now_hm

    for schedule in SCHEDULES.get():
        parms = None
        try:
            m, h, d, action, parms = schedule.split(None, 4)
        except:
            try:
                m, h, d, action = schedule.split(None, 3)
            except:
                continue # Bad schedule, ignore
        action = action.strip()
        try:
            then = int(h)*60 + int(m)
            if d == '*':
                d = int(now/(24*60))
                if forward and (then < now_hm): d = (d + 1) % 7
            else:
                d = int(d)-1
            then = d*24*60 + then
        except:
            continue # Bad schedule, ignore

        dif = then - now
        if dif < 0: dif = dif + 7*24*60

        events.append((dif, action, parms, schedule))

    events.sort(lambda x, y: x[0]-y[0])
    return events


def analyse(was_paused=False):
    """ Determine what pause/resume state we would have now.
        Return True if paused mode would be active.
        Return speedlimit
    """
    paused = None
    speedlimit = None
    servers = {}

    for ev in sort_schedules(forward=False):
        logging.debug('[%s] Schedule check result = %s', __NAME__, ev)
        action = ev[1]
        try:
            value = ev[2]
        except:
            value = None
        if action == 'pause':
            paused = True
        elif action == 'resume':
            paused = False
        elif action == 'speedlimit' and value!=None:
            speedlimit = int(ev[2])
        elif action == 'enable_server':
            try:
                servers[value] = 1
            except:
                logging.warning('[%s] Schedule for non-existing server %s', __NAME__, value)
        elif action == 'disable_server':
            try:
                servers[value] = 0
            except:
                logging.warning('[%s] Schedule for non-existing server %s', __NAME__, value)

    if not was_paused:
        sabnzbd.DOWNLOADER.paused = paused
    if speedlimit:
        sabnzbd.DOWNLOADER.limit_speed(s)
        sabnzbd.BANDWITH_LIMIT = speedlimit
    for serv in servers:
        try:
            config.get_config('servers', serv).enable.set(servers[serv])
        except:
            pass
    config.save_config()
