#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
tests.test_scheduler - Testing the timed pause/resume logic in scheduler.py
"""

import pytest

import sabnzbd
from sabnzbd.scheduler import Scheduler


@pytest.fixture()
def scheduler_env(mocker):
    sabnzbd.Downloader = mocker.Mock()
    sabnzbd.BPSMeter = mocker.Mock()
    sabnzbd.BPSMeter.get_quota.return_value = (None, None, None)
    sabnzbd.RSSReader = mocker.Mock()
    sabnzbd.NzbQueue = mocker.Mock()
    sabnzbd.NzbQueue.is_empty.return_value = False
    mocker.patch("sabnzbd.scheduler.kronos.ThreadedScheduler")
    mocker.patch("sabnzbd.downloader.unpause_all")
    mocker.patch("sabnzbd.downloader.pause_all")

    yield

    del sabnzbd.NzbQueue
    del sabnzbd.RSSReader
    del sabnzbd.BPSMeter
    del sabnzbd.Downloader


@pytest.mark.usefixtures("scheduler_env")
class TestScheduler:
    def test_pause_int_and_resume_int(self, mocker):
        """Both timers return '0' when idle and minutes:seconds while counting down"""
        sched = Scheduler()
        assert sched.pause_int() == "0"
        assert sched.resume_int() == "0"

        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched.pause_end = 1090.0
        sched.resume_end = 1125.0
        assert sched.pause_int() == "1:30"
        assert sched.resume_int() == "2:05"

    def test_pause_int_and_resume_int_clamp_expired(self, mocker):
        """An expired timer returns '0' rather than a negative countdown"""
        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched = Scheduler()

        # End moment already passed (scheduler cleanup not yet fired)
        sched.pause_end = 999.9
        sched.resume_end = 990.0
        assert sched.pause_int() == "0"
        assert sched.resume_int() == "0"

    def test_plan_pause_resumes_and_schedules(self, mocker):
        """plan_pause(>0) resumes now and schedules a one-shot re-pause after the interval"""
        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched = Scheduler()
        sched.scheduler.reset_mock()

        sched.plan_pause(5)

        assert sched.resume_end == 1300.0
        assert sched.pause_end is None
        sabnzbd.downloader.unpause_all.assert_called_once()
        sched.scheduler.add_single_task.assert_called_once()
        args, kwargs = sched.scheduler.add_single_task.call_args
        assert args[2] == 300
        assert kwargs["args"] == [1300.0]

    def test_plan_pause_zero_pauses_now(self):
        """plan_pause(0) cancels the timer and pauses immediately"""
        sched = Scheduler()
        sched.resume_end = 12345.0
        sched.plan_pause(0)
        assert sched.resume_end is None
        sabnzbd.Downloader.pause.assert_called_once()

    def test_scheduled_modes_are_mutually_exclusive(self):
        """Starting any scheduled mode cancels the pending timers/flag of the others"""
        sched = Scheduler()

        # A timed re-pause clears a pending timed resume and the until-empty flag
        sched.pause_end = 99999.0
        sched.resume_until_empty = True
        sched.plan_pause(5)
        assert sched.pause_end is None
        assert sched.resume_until_empty is False

        # A timed resume clears a pending re-pause and the until-empty flag
        sched.resume_end = 99999.0
        sched.resume_until_empty = True
        sched.plan_resume(5)
        assert sched.resume_end is None
        assert sched.resume_until_empty is False

        # Unpause-until-empty clears both timers
        sched.pause_end = 99999.0
        sched.resume_end = 88888.0
        sched.plan_resume_until_empty()
        assert sched.pause_end is None
        assert sched.resume_end is None
        assert sched.resume_until_empty is True

    def test_oneshot_pause_only_fires_at_planned_time(self, mocker):
        """The scheduled re-pause is ignored unless it fires near the planned time"""
        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched = Scheduler()
        sched.plan_pause(5)
        oneshot = sched.scheduler.add_single_task.call_args[0][0]

        # A stale (cancelled) firing is ignored
        oneshot(500.0)
        sabnzbd.Downloader.pause.assert_not_called()
        assert sched.resume_end == 1300.0

        # Firing at the planned time re-pauses and clears the timer
        oneshot(1300.0)
        sabnzbd.Downloader.pause.assert_called_once()
        assert sched.resume_end is None

    def test_pause_check_force_repause(self, mocker):
        """pause_check re-pauses when the resume timer has gone negative"""
        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched = Scheduler()

        sched.resume_end = 1100.0
        sched.pause_check()
        sabnzbd.Downloader.pause.assert_not_called()
        assert sched.resume_end == 1100.0

        sched.resume_end = 999.0
        sched.pause_check()
        sabnzbd.Downloader.pause.assert_called_once()
        assert sched.resume_end is None

    def test_plan_resume_until_empty_arms_and_resumes(self):
        """plan_resume_until_empty resumes now and arms the re-pause flag"""
        sched = Scheduler()
        sched.plan_resume_until_empty()
        assert sched.resume_until_empty is True
        sabnzbd.downloader.unpause_all.assert_called_once()

    def test_plan_resume_until_empty_noop_when_queue_empty(self):
        """plan_resume_until_empty does nothing when nothing is queued"""
        sabnzbd.NzbQueue.is_empty.return_value = True
        sched = Scheduler()
        sched.plan_resume_until_empty()
        assert sched.resume_until_empty is False
        sabnzbd.downloader.unpause_all.assert_not_called()

    def test_repause_on_empty_queue(self):
        """repause_on_empty_queue re-pauses and clears the flag only when armed"""
        sched = Scheduler()

        # Not armed: nothing happens
        sched.repause_on_empty_queue()
        sabnzbd.Downloader.pause.assert_not_called()

        # Armed: re-pause and clear
        sched.resume_until_empty = True
        sched.repause_on_empty_queue()
        sabnzbd.Downloader.pause.assert_called_once()
        assert sched.resume_until_empty is False

    def test_plan_resume_pauses_and_schedules(self, mocker):
        """plan_resume(>0) pauses now and schedules a one-shot resume after the interval"""
        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched = Scheduler()
        sched.scheduler.reset_mock()

        sched.plan_resume(5)

        assert sched.pause_end == 1300.0
        assert sched.resume_end is None
        sabnzbd.Downloader.pause.assert_called_once()
        sched.scheduler.add_single_task.assert_called_once()
        args, kwargs = sched.scheduler.add_single_task.call_args
        assert args[2] == 300
        assert kwargs["args"] == [1300.0]

    def test_plan_resume_zero_resumes_now(self):
        """plan_resume(0) cancels the timer and resumes immediately"""
        sched = Scheduler()
        sched.pause_end = 12345.0
        sched.plan_resume(0)
        assert sched.pause_end is None
        sabnzbd.downloader.unpause_all.assert_called_once()

    def test_oneshot_resume_only_fires_at_planned_time(self, mocker):
        """The scheduled resume is ignored unless it fires near the planned time"""
        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched = Scheduler()
        sched.plan_resume(5)
        oneshot = sched.scheduler.add_single_task.call_args[0][0]

        # A stale (cancelled) firing is ignored
        oneshot(500.0)
        sabnzbd.downloader.unpause_all.assert_not_called()
        assert sched.pause_end == 1300.0

        # Firing at the planned time resumes and clears the timer
        oneshot(1300.0)
        sabnzbd.downloader.unpause_all.assert_called_once()
        assert sched.pause_end is None

    def test_pause_check_force_resume(self, mocker):
        """pause_check resumes when the pause timer has gone negative"""
        mocker.patch("sabnzbd.scheduler.time.time", return_value=1000.0)
        sched = Scheduler()

        sched.pause_end = 1100.0
        sched.pause_check()
        sabnzbd.downloader.unpause_all.assert_not_called()
        assert sched.pause_end == 1100.0

        sched.pause_end = 999.0
        sched.pause_check()
        sabnzbd.downloader.unpause_all.assert_called_once()
        assert sched.pause_end is None

    def test_scheduled_resume_respects_active_timer(self):
        """scheduled_resume resumes only when no one-shot pause timer is active"""
        sched = Scheduler()

        # A pending one-shot pause blocks the scheduled resume
        sched.pause_end = 12345.0
        sched.scheduled_resume()
        sabnzbd.downloader.unpause_all.assert_not_called()

        # No timer: it resumes
        sched.pause_end = None
        sched.scheduled_resume()
        sabnzbd.downloader.unpause_all.assert_called_once()
