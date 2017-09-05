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
tests.testhelper - Basic helper functions
"""

import urllib2
import json

SAB_HOST = 'localhost'
SAB_PORT = 8081

def get_url_result(url=''):
    return urllib2.urlopen('http://%s:%s/%s/?session=apikey' % (SAB_HOST, SAB_PORT, url)).read()

def get_api_result(method='', args=''):
    return json.loads(urllib2.urlopen('http://%s:%s/api?apikey=apikey&output=json&mode=%s&%s' % (SAB_HOST, SAB_PORT, method, args)).read())