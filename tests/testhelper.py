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
tests.testhelper - Basic helper functions
"""

import urllib2
import json
import requests

SAB_HOST = 'localhost'
SAB_PORT = 8081


def get_url_result(url=''):
    """ Do basic request to web page """
    arguments = {'session': 'apikey'}
    return requests.get('http://%s:%s/%s/' % (SAB_HOST, SAB_PORT, url), params=arguments).text


def get_api_result(mode, extra_arguments={}):
    """ Build JSON request to SABnzbd """
    arguments = {'apikey': 'apikey', 'output': 'json', 'mode': mode}
    arguments.update(extra_arguments)
    r = requests.get('http://%s:%s/api' % (SAB_HOST, SAB_PORT), params=arguments)
    return r.json()


def upload_nzb(file):
    """ Upload file and return nzo_id reponse """
    files = {'name': open(file, 'rb')}
    arguments ={'apikey':'apikey', 'mode':'addfile', 'output': 'json'}
    return requests.post('http://%s:%s/api' % (SAB_HOST, SAB_PORT), files=files, data=arguments).json()
