#!/usr/bin/python3 -OO
# Copyright 2007-2019 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_misc - Testing functions in misc.py
"""

import datetime

from sabnzbd import misc
from tests.testhelper import *


class TestMisc:

    def assertTime(self, offset, age):
        assert offset == misc.calc_age(age, trans=True)
        assert offset == misc.calc_age(age, trans=False)

    def test_timeformat24h(self):
        assert '%H:%M:%S' == misc.time_format('%H:%M:%S')
        assert '%H:%M' == misc.time_format('%H:%M')

    @set_config({'ampm': True})
    def test_timeformatampm(self):
        misc.HAVE_AMPM = True
        assert '%I:%M:%S %p' == misc.time_format('%H:%M:%S')
        assert '%I:%M %p' == misc.time_format('%H:%M')

    def test_calc_age(self):
        date = datetime.datetime.now()
        m = date - datetime.timedelta(minutes=1)
        h = date - datetime.timedelta(hours=1)
        d = date - datetime.timedelta(days=1)
        self.assertTime('1m', m)
        self.assertTime('1h', h)
        self.assertTime('1d', d)

    def test_monthrange(self):
        # Dynamic dates would be a problem
        assert 12 == len(list(misc.monthrange(datetime.date(2018, 1, 1), datetime.date(2018, 12, 31))))
        assert 2 == len(list(misc.monthrange(datetime.date(2019, 1, 1), datetime.date(2019, 2, 1))))

    def test_safe_lower(self):
        assert 'all caps' == misc.safe_lower('ALL CAPS')
        assert '' == misc.safe_lower(None)
