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
tests.test_nzb - Basic NZB adding support
"""

import os
import pytest
import testhelper


# Where are we now?
base_path = os.path.dirname(os.path.abspath(__file__))


def nzo_in_queue(nzo_response):
    """ Helper function for checking if file is in queue and then remove it """
    queue_res = testhelper.get_api_result('queue')
    nzo_id = nzo_response['nzo_ids'][0]

    # Was it added?
    assert nzo_response['status'] == True
    assert queue_res['queue']['slots'][0]['nzo_id'] == nzo_response['nzo_ids'][0]

    # Let's remove it
    remove_response = testhelper.get_api_result('queue', {'name': 'delete', 'value': nzo_id})
    assert nzo_response['status'] == True

    # Really gone?
    queue_res = testhelper.get_api_result('queue')
    assert not queue_res['queue']['slots']


def test_addfile(sabnzbd_connect):
    # See if basic upload works
    nzo_response = testhelper.upload_nzb(os.path.join(base_path, 'data', 'reftestnzb.nzb'))
    nzo_in_queue(nzo_response)


def test_addlocalfile(sabnzbd_connect):
    # See if basic adding from disk-file works
    nzo_response = testhelper.get_api_result('addlocalfile', {'name': os.path.join(base_path, 'data', 'reftestnzb.nzb')})
    nzo_in_queue(nzo_response)
