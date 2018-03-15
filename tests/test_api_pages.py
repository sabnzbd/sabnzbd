#!/usr/bin/python -OO
# Copyright 2007-2018 The SABnzbd-Team <team@sabnzbd.org>
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
tests.test_api_pages - The most basic testing if things work
"""

import pytest
import testhelper


def test_basic_api(sabnzbd_connect):
    # Basic API test
    assert 'queue' in testhelper.get_api_result('queue')
    assert 'history' in testhelper.get_api_result('history')
    assert 'status' in testhelper.get_api_result('fullstatus')
    assert 'config' in testhelper.get_api_result('get_config')


def test_main_pages(sabnzbd_connect):
    # See if the basic pages work
    assert 'Traceback' not in testhelper.get_url_result()
    assert 'Traceback' not in testhelper.get_url_result('history')
    assert 'Traceback' not in testhelper.get_url_result('queue')
    assert 'Traceback' not in testhelper.get_url_result('status')


def test_wizard_pages(sabnzbd_connect):
    # Test if wizard pages work
    assert 'Traceback' not in testhelper.get_url_result('wizard')
    assert 'Traceback' not in testhelper.get_url_result('wizard/one')
    assert 'Traceback' not in testhelper.get_url_result('wizard/two')


def test_config_pages(sabnzbd_connect):
    # Test if config pages work
    assert 'Traceback' not in testhelper.get_url_result('config')
    assert 'Traceback' not in testhelper.get_url_result('config/general')
    assert 'Traceback' not in testhelper.get_url_result('config/server')
    assert 'Traceback' not in testhelper.get_url_result('config/categories')
    assert 'Traceback' not in testhelper.get_url_result('config/switches')
    assert 'Traceback' not in testhelper.get_url_result('config/sorting')
    assert 'Traceback' not in testhelper.get_url_result('config/notify')
    assert 'Traceback' not in testhelper.get_url_result('config/scheduling')
    assert 'Traceback' not in testhelper.get_url_result('config/rss')
    assert 'Traceback' not in testhelper.get_url_result('config/special')

