#!/usr/bin/python -OO
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
tests.testhelper - Basic helper functions
"""

import os
import shutil
import subprocess
import time

import requests

SAB_HOST = 'localhost'
SAB_PORT = 8081
SAB_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAB_CACHE_DIR = os.path.join(SAB_BASE_DIR, 'cache')
SAB_COMPLETE_DIR = os.path.join(SAB_CACHE_DIR, 'Downloads', 'complete')


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


def upload_nzb(filename):
    """ Upload file and return nzo_id reponse """
    files = {'name': open(filename, 'rb')}
    arguments = {'apikey': 'apikey', 'mode': 'addfile', 'output': 'json'}
    return requests.post('http://%s:%s/api' % (SAB_HOST, SAB_PORT), files=files, data=arguments).json()


def setUpModule():
    # Remove cache if already there
    if os.path.isdir(SAB_CACHE_DIR):
        shutil.rmtree(SAB_CACHE_DIR)

    # Copy basic config file with API key
    os.mkdir(SAB_CACHE_DIR)
    shutil.copyfile(os.path.join(SAB_BASE_DIR, 'sabnzbd.basic.ini'), os.path.join(SAB_CACHE_DIR, 'sabnzbd.ini'))

    # Check if we have language files
    if not os.path.exists(os.path.join(SAB_BASE_DIR, '..', 'locale')):
        lang_command = 'python %s/../tools/make_mo.py' % SAB_BASE_DIR
        subprocess.Popen(lang_command.split())

    # Start SABnzbd
    sab_command = 'python %s/../SABnzbd.py --new -l2 -s %s:%s -b0 -f %s' % (SAB_BASE_DIR, SAB_HOST, SAB_PORT, SAB_CACHE_DIR)
    subprocess.Popen(sab_command.split())

    # Wait for SAB to respond
    for _ in range(10):
        try:
            get_url_result()
            # Woohoo, we're up!
            break
        except requests.ConnectionError:
            time.sleep(1)
    else:
        # Make sure we clean up
        tearDownModule()
        raise requests.ConnectionError()


def tearDownModule():
    # Graceful shutdown request
    try:
        get_url_result('shutdown')
    except requests.ConnectionError:
        pass

    # Takes a second to shutdown
    for x in range(10):
        try:
            shutil.rmtree(SAB_CACHE_DIR)
            break
        except OSError:
            print "Unable to remove cache dir (try %d)" % x
            time.sleep(1)
