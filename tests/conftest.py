#!/usr/bin/python -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
tests.conftest - Wrappers to start SABnzbd for testing
"""

import os
import itertools
import urllib2
import pytest
import shutil
import time
import testhelper

from xprocess import ProcessStarter

@pytest.fixture(scope='session')
def sabnzbd_connect(request, xprocess):
    # Get cache directory
    base_path = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(base_path, 'cache')

    # Copy basic config file
    try:
        os.mkdir(cache_dir)
        shutil.copyfile(os.path.join(base_path, 'sabnzbd.basic.ini'), os.path.join(cache_dir, 'sabnzbd.ini'))
    except:
        pass

    class Starter(ProcessStarter):
        # Wait for SABnzbd to start
        pattern = "ENGINE Bus STARTED"

        # Start without browser and with basic logging
        args = 'python ../../SABnzbd.py -l1 -s %s:%s -b0 -f %s' % (testhelper.SAB_HOST, testhelper.SAB_PORT, cache_dir)
        args = args.split()

        # We have to wait a bit longer than default
        def filter_lines(self, lines):
            return itertools.islice(lines, 500)

    # Shut it down at the end
    def shutdown_sabnzbd():
        # Gracefull shutdown request
        testhelper.get_url_result('shutdown')
        # Takes a second to shutdown
        for x in range(5):
            try:
                shutil.rmtree(cache_dir)
                break
            except:
                time.sleep(1)
    request.addfinalizer(shutdown_sabnzbd)

    return xprocess.ensure("sabnzbd", Starter)

