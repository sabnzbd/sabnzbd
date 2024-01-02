#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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

import random
import logging
import time
from typing import Optional

import sabnzbd.utils.kronos as kronos
import sabnzbd.downloader
import sabnzbd.misc
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.filesystem import diskspace
from sabnzbd.constants import LOW_PRIORITY, NORMAL_PRIORITY, HIGH_PRIORITY

DAILY_RANGE = list(range(1, 8))


class Scheduler:
    def __init__(self):
        self.scheduler = kronos.ThreadedScheduler()
        self.pause_end: Optional[float] = None  # Moment when pause will end
        self.resume_task: Optional[kronos.Task] = None
        self.restart_scheduler = False
        self.pp_pause_event = False
        self.load_schedules()

    def start(self):
        """Start the scheduler"""
        self.scheduler.start()

    def stop(self):
        """Stop the scheduler, destroy instance"""
        logging.debug("Stopping scheduler")
        self.scheduler.stop()

    def restart(self, plan_restart=True):
        """Stop and start scheduler"""
        if plan_restart:
            self.restart_scheduler = True
        elif self.restart_scheduler:
            logging.debug("Restarting scheduler")
            self.restart_scheduler = False
            self.scheduler.stop()
            self.scheduler.start()
            self.analyse(sabnzbd.Downloader.paused)
            self.load_schedules()

    def abort(self):
        """Emergency stop, just set the running attribute false so we don't
        have to wait the full scheduler-check cycle before it really stops"""
        self.scheduler.running = False

    def is_alive(self):
        """Thread-like check if we are doing fine"""
        if self.scheduler.thread:
            return self.scheduler.thread.is_alive()
        return False

    def load_schedules(self):
        rss_planned = False

        for schedule in cfg.schedules():
            arguments = []
            argument_list = None

            try:
                enabled, m, h, d, action_name = schedule.split()
            except:
                try:
                    enabled, m, h, d, action_name, argument_list = schedule.split(None, 5)
                except:
                    continue  # Bad schedule, ignore

            if argument_list:
                arguments = argument_list.split()

            action_name = action_name.lower()
            try:
                m = int(m)
                h = int(h)
            except:
                logging.warning(T("Bad schedule %s at %s:%s"), action_name, m, h)
                continue

            if d.isdigit():
                d = [int(i) for i in d]
            else:
                d = DAILY_RANGE

            if action_name == "resume":
                action = self.scheduled_resume
                arguments = []
            elif action_name == "pause":
                action = sabnzbd.Downloader.pause
                arguments = []
            elif action_name == "pause_all":
                action = sabnzbd.downloader.pause_all
                arguments = []
            elif action_name == "shutdown":
                action = sabnzbd.shutdown_program
                arguments = []
            elif action_name == "restart":
                action = restart_program
                arguments = []
            elif action_name == "pause_post":
                action = pp_pause
            elif action_name == "resume_post":
                action = pp_resume
            elif action_name == "speedlimit" and arguments != []:
                action = sabnzbd.Downloader.limit_speed
            elif action_name == "enable_server" and arguments != []:
                action = enable_server
            elif action_name == "disable_server" and arguments != []:
                action = disable_server
            elif action_name == "scan_folder":
                action = sabnzbd.DirScanner.scan
            elif action_name == "rss_scan":
                action = sabnzbd.RSSReader.run
                rss_planned = True
            elif action_name == "create_backup":
                action = sabnzbd.config.create_config_backup
            elif action_name == "remove_failed":
                action = sabnzbd.api.history_remove_failed
            elif action_name == "remove_completed":
                action = sabnzbd.api.history_remove_completed
            elif action_name == "enable_quota":
                action = sabnzbd.BPSMeter.set_status
                arguments = [True]
            elif action_name == "disable_quota":
                action = sabnzbd.BPSMeter.set_status
                arguments = [False]
            elif action_name == "pause_all_low":
                action = sabnzbd.NzbQueue.pause_on_prio
                arguments = [LOW_PRIORITY]
            elif action_name == "pause_all_normal":
                action = sabnzbd.NzbQueue.pause_on_prio
                arguments = [NORMAL_PRIORITY]
            elif action_name == "pause_all_high":
                action = sabnzbd.NzbQueue.pause_on_prio
                arguments = [HIGH_PRIORITY]
            elif action_name == "resume_all_low":
                action = sabnzbd.NzbQueue.resume_on_prio
                arguments = [LOW_PRIORITY]
            elif action_name == "resume_all_normal":
                action = sabnzbd.NzbQueue.resume_on_prio
                arguments = [NORMAL_PRIORITY]
            elif action_name == "resume_all_high":
                action = sabnzbd.NzbQueue.resume_on_prio
                arguments = [HIGH_PRIORITY]
            elif action_name == "pause_cat":
                action = sabnzbd.NzbQueue.pause_on_cat
                arguments = [argument_list]
            elif action_name == "resume_cat":
                action = sabnzbd.NzbQueue.resume_on_cat
                arguments = [argument_list]
            else:
                logging.warning(T("Unknown action: %s"), action_name)
                continue

            if enabled == "1":
                logging.info("Scheduling %s(%s) on days %s at %02d:%02d", action_name, arguments, d, h, m)
                self.scheduler.add_daytime_task(action, action_name, d, None, (h, m), args=arguments)
            else:
                logging.debug("Skipping %s(%s) on days %s at %02d:%02d", action_name, arguments, d, h, m)

        # Set RSS check interval
        if not rss_planned:
            interval = cfg.rss_rate()
            delay = random.randint(0, interval - 1)
            logging.info("Scheduling RSS interval task every %s min (delay=%s)", interval, delay)
            sabnzbd.RSSReader.next_run = time.time() + delay * 60
            self.scheduler.add_interval_task(sabnzbd.RSSReader.run, "RSS", delay * 60, interval * 60)
            self.scheduler.add_single_task(sabnzbd.RSSReader.run, "RSS", 15)

        if cfg.version_check():
            # Check for new release daily at a random time
            m = random.randint(0, 59)
            h = random.randint(0, 23)

            logging.info("Scheduling version check in 10 minutes and daily at %s:%s", h, m)
            self.scheduler.add_single_task(sabnzbd.misc.check_latest_version, "version_check", 10 * 60)
            self.scheduler.add_daytime_task(
                sabnzbd.misc.check_latest_version,
                "recurring_version_check",
                DAILY_RANGE,
                None,
                (h, m),
            )

        action, hour, minute = sabnzbd.BPSMeter.get_quota()
        if action:
            logging.info("Setting schedule for quota check daily at %s:%s", hour, minute)
            self.scheduler.add_daytime_task(action, "quota_reset", DAILY_RANGE, None, (hour, minute))

        if sabnzbd.misc.int_conv(cfg.history_retention()) > 0:
            logging.info("Setting schedule for midnight auto history-purge")
            self.scheduler.add_daytime_task(
                sabnzbd.database.scheduled_history_purge,
                "midnight_history_purge",
                DAILY_RANGE,
                None,
                (0, 0),
            )

        logging.info("Setting schedule for midnight BPS reset")
        self.scheduler.add_daytime_task(
            sabnzbd.BPSMeter.update,
            "midnight_bps",
            DAILY_RANGE,
            None,
            (0, 0),
        )

        logging.info("Setting schedule for midnight server expiration check")
        self.scheduler.add_daytime_task(
            sabnzbd.downloader.check_server_expiration,
            "check_server_expiration",
            DAILY_RANGE,
            None,
            (0, 0),
        )

        logging.info("Setting schedule for server quota check")
        self.scheduler.add_interval_task(
            sabnzbd.downloader.check_server_quota,
            "check_server_quota",
            0,
            10 * 60,
        )

        # Subscribe to special schedule changes
        cfg.rss_rate.callback(self.scheduler_restart_guard)

    def analyse(self, was_paused=False, priority=None):
        """Determine what pause/resume state we would have now.
        'priority': evaluate only effect for given priority, return True for paused
        """
        self.pp_pause_event = False
        paused = None
        paused_all = False
        pause_post = False
        pause_low = pause_normal = pause_high = False
        speedlimit = None
        quota = True
        servers = {}

        for ev in sort_schedules(all_events=True):
            if priority is None:
                logging.debug("Schedule check result = %s", ev)

            # Skip if disabled
            if ev[4] == "0":
                continue

            action = ev[1]
            try:
                value = ev[2]
            except:
                value = None
            if action == "pause":
                paused = True
            elif action == "pause_all":
                paused_all = True
                self.pp_pause_event = True
            elif action == "resume":
                paused = False
                paused_all = False
            elif action == "pause_post":
                pause_post = True
                self.pp_pause_event = True
            elif action == "resume_post":
                pause_post = False
                self.pp_pause_event = True
            elif action == "speedlimit" and value is not None:
                speedlimit = ev[2]
            elif action == "pause_all_low":
                pause_low = True
            elif action == "pause_all_normal":
                pause_normal = True
            elif action == "pause_all_high":
                pause_high = True
            elif action == "resume_all_low":
                pause_low = False
            elif action == "resume_all_normal":
                pause_normal = False
            elif action == "resume_all_high":
                pause_high = False
            elif action == "enable_quota":
                quota = True
            elif action == "disable_quota":
                quota = False
            elif action == "enable_server":
                try:
                    servers[value] = 1
                except:
                    logging.warning(T("Schedule for non-existing server %s"), value)
            elif action == "disable_server":
                try:
                    servers[value] = 0
                except:
                    logging.warning(T("Schedule for non-existing server %s"), value)

        # Special case, a priority was passed, so evaluate only that and return state
        if priority == LOW_PRIORITY:
            return pause_low
        if priority == NORMAL_PRIORITY:
            return pause_normal
        if priority == HIGH_PRIORITY:
            return pause_high
        if priority is not None:
            return False

        # Normal analysis
        if not was_paused:
            if paused_all:
                sabnzbd.downloader.pause_all()
            else:
                sabnzbd.downloader.unpause_all()
            sabnzbd.Downloader.set_paused_state(paused or paused_all)

        sabnzbd.PostProcessor.paused = pause_post
        if speedlimit is not None:
            sabnzbd.Downloader.limit_speed(speedlimit)

        sabnzbd.BPSMeter.set_status(quota, action=False)

        for serv in servers:
            try:
                item = config.get_config("servers", serv)
                value = servers[serv]
                if bool(item.enable()) != bool(value):
                    item.enable.set(value)
                    sabnzbd.Downloader.init_server(serv, serv)
            except:
                pass
        config.save_config()

    def scheduler_restart_guard(self):
        """Set flag for scheduler restart"""
        self.restart_scheduler = True

    def scheduled_resume(self):
        """Scheduled resume, only when no oneshot resume is active"""
        if self.pause_end is None:
            sabnzbd.downloader.unpause_all()

    def __oneshot_resume(self, when):
        """Called by delayed resume schedule
        Only resumes if call comes at the planned time
        """
        if self.pause_end is not None and (when > self.pause_end - 5) and (when < self.pause_end + 55):
            self.pause_end = None
            logging.debug("Resume after pause-interval")
            sabnzbd.downloader.unpause_all()
        else:
            logging.debug("Ignoring cancelled resume")

    def plan_resume(self, interval):
        """Set a scheduled resume after the interval"""
        if interval > 0:
            self.pause_end = time.time() + (interval * 60)
            logging.debug("Schedule resume at %s", self.pause_end)
            self.scheduler.add_single_task(self.__oneshot_resume, "", interval * 60, args=[self.pause_end])
            sabnzbd.Downloader.pause()
        else:
            self.pause_end = None
            sabnzbd.downloader.unpause_all()

    def __check_diskspace(self, full_dir: str, required_space: float):
        """Resume if there is sufficient available space"""
        if not cfg.fulldisk_autoresume():
            self.cancel_resume_task()
            return

        disk_free = diskspace(force=True)[full_dir][1]
        if disk_free > required_space:
            logging.info("Resuming, %s has %d GB free, needed %d GB", full_dir, disk_free, required_space)
            sabnzbd.Downloader.resume()
        else:
            logging.info("%s has %d GB free, need %d GB to resume", full_dir, disk_free, required_space)

        # Remove scheduled task if user manually resumed or we auto-resumed
        if not sabnzbd.Downloader.paused:
            self.cancel_resume_task()

    def plan_diskspace_resume(self, full_dir: str, required_space: float):
        """Create regular check for free disk space"""
        self.cancel_resume_task()
        logging.info("Will resume when %s has more than %d GB free space", full_dir, required_space)
        self.resume_task = self.scheduler.add_interval_task(
            self.__check_diskspace, "check_diskspace", 5 * 60, 9 * 60, "threaded", args=[full_dir, required_space]
        )

    def plan_required_server_resume(self, interval: int = 5):
        """Create task for resuming downloading"""
        if not sabnzbd.Downloader.paused:
            self.plan_resume(interval)

    def cancel_resume_task(self):
        """Cancel the current auto resume task"""
        if self.resume_task:
            logging.debug("Cancelling existing resume_task '%s'", self.resume_task.name)
            self.scheduler.cancel(self.resume_task)
            self.resume_task = None

    def pause_int(self) -> str:
        """Return minutes:seconds until pause ends"""
        if self.pause_end is None:
            return "0"
        else:
            val = self.pause_end - time.time()
            if val < 0:
                sign = "-"
                val = abs(val)
            else:
                sign = ""
            mins = int(val / 60)
            sec = int(val - mins * 60)
            return "%s%d:%02d" % (sign, mins, sec)

    def pause_check(self):
        """Unpause when time left is negative, compensate for missed schedule"""
        if self.pause_end is not None and (self.pause_end - time.time()) < 0:
            self.pause_end = None
            logging.debug("Force resume, negative timer")
            sabnzbd.downloader.unpause_all()

    def plan_server(self, action, parms, interval):
        """Plan to re-activate server after 'interval' minutes"""
        self.scheduler.add_single_task(action, "", interval * 60, args=parms)

    def force_rss(self):
        """Add a one-time RSS scan, one second from now"""
        self.scheduler.add_single_task(sabnzbd.RSSReader.run, "RSS", 1)


def sort_schedules(all_events, now=None):
    """Sort the schedules, based on order of happening from now
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
            # Note: the last parameter can have spaces (category name)!
            enabled, m, h, dd, action, parms = schedule.split(None, 5)
        except:
            try:
                enabled, m, h, dd, action = schedule.split(None, 4)
            except:
                continue  # Bad schedule, ignore
        action = action.strip()
        if dd == "*":
            dd = "1234567"
        if not dd.isdigit():
            continue  # Bad schedule, ignore
        for d in dd:
            then = (int(d) - 1) * day_min + int(h) * 60 + int(m)
            dif = then - now
            if all_events and dif < 0:
                # Expired event will occur again after a week
                dif = dif + week_min

            events.append((dif, action, parms, schedule, enabled))
            if not all_events:
                break

    events.sort(key=lambda x: x[0])
    return events


def pp_pause():
    sabnzbd.PostProcessor.paused = True


def pp_resume():
    sabnzbd.PostProcessor.paused = False


def enable_server(server):
    """Enable server (scheduler only)"""
    try:
        config.get_config("servers", server).enable.set(1)
    except:
        logging.warning(T("Trying to set status of non-existing server %s"), server)
        return
    config.save_config()
    sabnzbd.Downloader.update_server(server, server)


def disable_server(server):
    """Disable server (scheduler only)"""
    try:
        config.get_config("servers", server).enable.set(0)
    except:
        logging.warning(T("Trying to set status of non-existing server %s"), server)
        return
    config.save_config()
    sabnzbd.Downloader.update_server(server, server)


def restart_program():
    """Restart program (used by scheduler)"""
    logging.info("Scheduled restart request")
    # Just set the stop flag, because stopping CherryPy from
    # the scheduler is not reliable
    sabnzbd.TRIGGER_RESTART = True
