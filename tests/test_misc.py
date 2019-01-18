import unittest
import datetime
import time
from sabnzbd import misc
import sabnzbd.cfg as cfg

class MiscTest(unittest.TestCase):

    def fake_cfg_ampm(self):
        return True

    def assertTime(self, offset, time):
        self.assertEqual(offset, misc.calc_age(time, trans=True))
        self.assertEqual(offset, misc.calc_age(time, trans=False))

    def test_timeformat24h(self):
        self.assertEqual('%H:%M:%S', misc.time_format('%H:%M:%S'))
        self.assertEqual('%H:%M', misc.time_format('%H:%M'))

    def test_timeformatampm(self):
        misc.HAVE_AMPM = True
        cfg.ampm = self.fake_cfg_ampm
        self.assertEqual('%I:%M:%S %p', misc.time_format('%H:%M:%S'))
        self.assertEqual('%I:%M %p', misc.time_format('%H:%M'))

    def test_calc_age(self):
        date = datetime.datetime.now()
        m = date - datetime.timedelta(minutes=1)
        h = date - datetime.timedelta(hours=1)
        d = date - datetime.timedelta(days=1)
        self.assertTime('1m', m)
        self.assertTime('1h', h)
        self.assertTime('1d', d)

    def test_monthrange(self):
        # months_recorded = list(sabnzbd.misc.monthrange(min_date, datetime.date.today()))
        min_date = datetime.date.today() - datetime.timedelta(days=330)
        r = list(misc.monthrange(min_date, datetime.date.today()))
        self.assertEqual(12, len(r))
        print(r)

    def test_safe_lower(self):
        self.assertEqual("all caps", misc.safe_lower("ALL CAPS"))
