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
tests.test_bpsmeter - Testing SABnzbd bpsmeter
"""

import time

from sabnzbd.bpsmeter import BPSMeter


class TestNextReset:
    def test_monthly_reset_on_last_day_of_short_month(self):
        meter = BPSMeter()
        meter.q_period = "m"
        meter.q_day = 31
        meter.q_hour = meter.q_minute = 0

        # Just after the reset on 30 November, the next one is 31 December
        meter.next_reset(time.mktime((2026, 11, 30, 0, 0, 5, 0, 0, -1)))
        assert time.localtime(meter.q_time)[:5] == (2026, 12, 31, 0, 0)

        # Before it, the reset is on the last day of November
        meter.next_reset(time.mktime((2026, 11, 15, 12, 0, 0, 0, 0, -1)))
        assert time.localtime(meter.q_time)[:5] == (2026, 11, 30, 0, 0)
