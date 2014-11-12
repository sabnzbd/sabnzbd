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
sabnzbd.scheduler - Event Scheduler
"""
#------------------------------------------------------------------------------


import random
import logging
import time

import sabnzbd.utils.kronos as kronos
import sabnzbd.rss as rss
from sabnzbd.newzbin import Bookmarks
import sabnzbd.downloader
import sabnzbd.dirscanner
import sabnzbd.misc
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.postproc import PostProcessor


__SCHED = None  # Global pointer to Scheduler instance

RSSTASK_MINUTE = random.randint(0, 59)
SCHEDULE_GUARD_FLAG = False
PP_PAUSE_EVENT = False

def schedule_guard():
    """ Set flag for scheduler restart """
    global SCHEDULE_GUARD_FLAG
    SCHEDULE_GUARD_FLAG = True

def pp_pause():
    PostProcessor.do.paused = True

def pp_resume():
    PostProcessor.do.paused = False

def pp_pause_event():
    return PP_PAUSE_EVENT

def init():
    """ Create the scheduler and set all required events
    """
    global __SCHED

    reset_guardian()
    __SCHED = kronos.ThreadedScheduler()
    rss_planned = False

    for schedule in cfg.schedules():
        arguments = []
        argument_list = None
        try:
            m, h, d, action_name = schedule.split()
        except:
            m, h, d, action_name, argument_list = schedule.split(None, 4)
        if argument_list:
            arguments = argument_list.split()

        action_name = action_name.lower()
        try:
            m = int(m)
            h = int(h)
        except:
            logging.warning(Ta('Bad schedule %s at %s:%s'), action_name, m, h)
            continue

        if d.isdigit():
            d = [int(i) for i in d]
        else:
            d = range(1, 8)

        if action_name == 'resume':
            action = scheduled_resume
            arguments = []
        elif action_name == 'pause':
            action = sabnzbd.downloader.Downloader.do.pause
            arguments = []
        elif action_name == 'pause_all':
            action = sabnzbd.pause_all
            arguments = []
        elif action_name == 'shutdown':
            action = sabnzbd.shutdown_program
            arguments = []
        elif action_name == 'restart':
            action = sabnzbd.restart_program
            arguments = []
        elif action_name == 'pause_post':
            action = pp_pause
        elif action_name == 'resume_post':
            action = pp_resume
        elif action_name == 'speedlimit' and arguments != []:
            action = sabnzbd.downloader.Downloader.do.limit_speed
        elif action_name == 'enable_server' and arguments != []:
            action = sabnzbd.enable_server
        elif action_name == 'disable_server' and arguments != []:
            action = sabnzbd.disable_server
        elif action_name == 'scan_folder':
            action = sabnzbd.dirscanner.dirscan
        elif action_name == 'rss_scan':
            action = rss.run_method
            rss_planned = True
        elif action_name == 'remove_failed':
            action = sabnzbd.api.history_remove_failed
        else:
            logging.warning(Ta('Unknown action: %s'), action_name)
            continue

        logging.debug("scheduling %s(%s) on days %s at %02d:%02d", action_name, arguments, d, h, m)

        __SCHED.add_daytime_task(action, action_name, d, None, (h, m),
                             kronos.method.sequential, arguments, None)

    # Set Guardian interval to 30 seconds
    __SCHED.add_interval_task(sched_guardian, "Guardian", 15, 30,
                                  kronos.method.sequential, None, None)

    # Set RSS check interval
    if not rss_planned:
        interval = cfg.rss_rate()
        delay = random.randint(0, interval-1)
        logging.debug("Scheduling RSS interval task every %s min (delay=%s)", interval, delay)
        sabnzbd.rss.next_run(time.time() + delay * 60)
        __SCHED.add_interval_task(rss.run_method, "RSS", delay*60, interval*60,
                                      kronos.method.sequential, None, None)
        __SCHED.add_single_task(rss.run_method, 'RSS', 15, kronos.method.sequential, None, None)

    if cfg.version_check():
        # Check for new release, once per week on random time
        m = random.randint(0, 59)
        h = random.randint(0, 23)
        d = (random.randint(1, 7), )

        logging.debug("Scheduling VersionCheck on day %s at %s:%s", d[0], h, m)
        __SCHED.add_daytime_task(sabnzbd.misc.check_latest_version, 'VerCheck', d, None, (h, m),
                                 kronos.method.sequential, [], None)


    if False: #cfg.newzbin_bookmarks():
        interval = cfg.bookmark_rate()
        delay = random.randint(0, interval-1)
        logging.debug("Scheduling Bookmark interval task every %s min (delay=%s)", interval, delay)
        __SCHED.add_interval_task(Bookmarks.do.run, 'Bookmarks', delay*60, interval*60,
                                  kronos.method.sequential, None, None)
        __SCHED.add_single_task(Bookmarks.do.run, 'Bookmarks', 20, kronos.method.sequential, None, None)


    action, hour, minute = sabnzbd.bpsmeter.BPSMeter.do.get_quota()
    if action:
        logging.info('Setting schedule for quota check daily at %s:%s', hour, minute)
        __SCHED.add_daytime_task(action, 'quota_reset', range(1, 8), None, (hour, minute),
                                 kronos.method.sequential, [], None)

    logging.info('Setting schedule for midnight BPS reset')
    __SCHED.add_daytime_task(sabnzbd.bpsmeter.midnight_action, 'midnight_bps', range(1, 8), None, (0, 0),
                             kronos.method.sequential, [], None)


    # Subscribe to special schedule changes
    cfg.newzbin_bookmarks.callback(schedule_guard)
    cfg.bookmark_rate.callback(schedule_guard)
    cfg.rss_rate.callback(schedule_guard)


def start():
    """ Start the scheduler
    """
    global __SCHED
    if __SCHED:
        logging.debug('Starting scheduler')
        __SCHED.start()


def restart(force=False):
    """ Stop and start scheduler
    """
    global __PARMS, SCHEDULE_GUARD_FLAG

    if force:
        SCHEDULE_GUARD_FLAG = True
    else:
        if SCHEDULE_GUARD_FLAG:
            SCHEDULE_GUARD_FLAG = False
            stop()

            analyse(sabnzbd.downloader.Downloader.do.paused)

            init()
            start()


def stop():
    """ Stop the scheduler, destroy instance
    """
    global __SCHED
    if __SCHED:
        logging.debug('Stopping scheduler')
        try:
            __SCHED.stop()
        except IndexError:
            pass
        del __SCHED
        __SCHED = None


def abort():
    """ Emergency stop, just set the running attribute false
    """
    global __SCHED
    if __SCHED:
        logging.debug('Terminating scheduler')
        __SCHED.running = False


def sort_schedules(all_events, now=None):
    """ Sort the schedules, based on order of happening from now
        `all_events=True`: Return an event for each active day
        `all_events=False`: Return only first occurring event of the week
        `now` : for testing: simulated localtime()
    """

    day_min = 24 * 60
    week_min = 7 * day_min
    events = []

    now = now or time.localtime()
    now_hm = now[3] * 60 + now[4]
    now = now[6] * day_min + now_hm

    for schedule in cfg.schedules():
        parms = None
        try:
            m, h, dd, action, parms = schedule.split(None, 4)
        except:
            try:
                m, h, dd, action = schedule.split(None, 3)
            except:
                continue # Bad schedule, ignore
        action = action.strip()
        if dd == '*':
            dd = '1234567'
        if not dd.isdigit():
            continue # Bad schedule, ignore
        for d in dd:
            then = (int(d) - 1) * day_min + int(h) * 60 + int(m)
            dif = then - now
            if all_events and dif < 0:
                # Expired event will occur again after a week
                dif = dif + week_min

            events.append((dif, action, parms, schedule))
            if not all_events:
                break

    events.sort(lambda x, y: x[0] - y[0])
    return events


def analyse(was_paused=False):
    """ Determine what pause/resume state we would have now.
    """
    global PP_PAUSE_EVENT
    PP_PAUSE_EVENT = False
    paused = None
    paused_all = False
    pause_post = False
    speedlimit = None
    servers = {}

    for ev in sort_schedules(all_events=True):
        logging.debug('Schedule check result = %s', ev)
        action = ev[1]
        try:
            value = ev[2]
        except:
            value = None
        if action == 'pause':
            paused = True
        elif action == 'pause_all':
            paused_all = True
            PP_PAUSE_EVENT = True
        elif action == 'resume':
            paused = False
            paused_all = False
        elif action == 'pause_post':
            pause_post = True
            PP_PAUSE_EVENT = True
        elif action == 'resume_post':
            pause_post = False
            PP_PAUSE_EVENT = True
        elif action == 'speedlimit' and value!=None:
            speedlimit = int(ev[2])
        elif action == 'enable_server':
            try:
                servers[value] = 1
            except:
                logging.warning(Ta('Schedule for non-existing server %s'), value)
        elif action == 'disable_server':
            try:
                servers[value] = 0
            except:
                logging.warning(Ta('Schedule for non-existing server %s'), value)

    if not was_paused:
        if paused_all:
            sabnzbd.pause_all()
        else:
            sabnzbd.unpause_all()
        sabnzbd.downloader.Downloader.do.set_paused_state(paused or paused_all)

    PostProcessor.do.paused = pause_post
    if speedlimit:
        sabnzbd.downloader.Downloader.do.limit_speed(speedlimit)
    for serv in servers:
        try:
            item = config.get_config('servers', serv)
            value = servers[serv]
            if bool(item.enable()) != bool(value):
                item.enable.set(value)
                sabnzbd.downloader.Downloader.do.init_server(serv, serv)
        except:
            pass
    config.save_config()


#------------------------------------------------------------------------------
# Support for single shot pause (=delayed resume)

__PAUSE_END = None     # Moment when pause will end

def scheduled_resume():
    """ Scheduled resume, only when no oneshot resume is active
    """
    global __PAUSE_END
    if __PAUSE_END is None:
        sabnzbd.unpause_all()


def __oneshot_resume(when):
    """ Called by delayed resume schedule
        Only resumes if call comes at the planned time
    """
    global __PAUSE_END
    if __PAUSE_END != None and (when > __PAUSE_END-5) and (when < __PAUSE_END+55):
        __PAUSE_END = None
        logging.debug('Resume after pause-interval')
        sabnzbd.unpause_all()
    else:
        logging.debug('Ignoring cancelled resume')


def plan_resume(interval):
    """ Set a scheduled resume after the interval
    """
    global __SCHED, __PAUSE_END
    if interval > 0:
        __PAUSE_END = time.time() + (interval * 60)
        logging.debug('Schedule resume at %s', __PAUSE_END)
        __SCHED.add_single_task(__oneshot_resume, '', interval*60, kronos.method.sequential, [__PAUSE_END], None)
        sabnzbd.downloader.Downloader.do.pause()
    else:
        __PAUSE_END = None
        sabnzbd.unpause_all()


def pause_int():
    """ Return minutes:seconds until pause ends """
    global __PAUSE_END
    if __PAUSE_END is None:
        return "0"
    else:
        val = __PAUSE_END - time.time()
        if val < 0:
            sign = '-'
            val = abs(val)
        else:
            sign = ''
        min = int(val / 60L)
        sec = int(val - min*60)
        return "%s%d:%02d" % (sign, min, sec)


def pause_check():
    """ Unpause when time left is negative, compensate for missed schedule
    """
    global __PAUSE_END
    if __PAUSE_END is not None and (__PAUSE_END - time.time()) < 0:
        __PAUSE_END = None
        logging.debug('Force resume, negative timer')
        sabnzbd.unpause_all()


#------------------------------------------------------------------------------
def plan_server(action, parms, interval):
    """ Plan to re-activate server after "interval" minutes
    """
    __SCHED.add_single_task(action, '', interval*60, kronos.method.sequential, parms, None)

#------------------------------------------------------------------------------
def force_rss():
    """ Add a one-time RSS scan, one second from now
    """
    __SCHED.add_single_task(rss.run_method, 'RSS', 1, kronos.method.sequential, None, None)


#------------------------------------------------------------------------------
# Scheduler Guarding system
# Each check sets the guardian flag False
# Each succesful scheduled check sets the flag
# If 4 consequetive checks fail, the sheduler is assumed to have crashed

__SCHED_GUARDIAN = False
__SCHED_GUARDIAN_CNT = 0

def reset_guardian():
    global __SCHED_GUARDIAN, __SCHED_GUARDIAN_CNT
    __SCHED_GUARDIAN = False
    __SCHED_GUARDIAN_CNT = 0

def sched_guardian():
    global __SCHED_GUARDIAN, __SCHED_GUARDIAN_CNT
    __SCHED_GUARDIAN = True

def sched_check():
    global __SCHED_GUARDIAN, __SCHED_GUARDIAN_CNT
    if not __SCHED_GUARDIAN:
        __SCHED_GUARDIAN_CNT += 1
        return __SCHED_GUARDIAN_CNT < 4
    reset_guardian()
    return True
