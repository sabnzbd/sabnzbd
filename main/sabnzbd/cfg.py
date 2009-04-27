#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.cfg - Configuration Parameters
"""

import os
import sabnzbd
from sabnzbd.constants import *
from sabnzbd.config import OptionBool, OptionNumber, OptionPassword, \
                           OptionDir, OptionStr, OptionList, no_nonsense, \
                           validate_octal, validate_safedir, validate_dir_exists, \
                           create_api_key

#------------------------------------------------------------------------------
# Email validation support
#
import re
RE_VAL = re.compile('[^@ ]+@[^.@ ]+\.[^.@ ]')
def validate_email(value):
    global EMAIL_ENDJOB, EMAIL_FULL
    if EMAIL_ENDJOB.get() or EMAIL_FULL.get():
        if value and RE_VAL.match(value):
            return None, value
        else:
            return "%s is not a valid email address" % value, None
    else:
        return None, value


def validate_server(value):
    """ Check if server non-empty"""
    global EMAIL_ENDJOB, EMAIL_FULL
    if value == '' and (EMAIL_ENDJOB.get() or EMAIL_FULL.get()):
        return "Server address required", None
    else:
        return None, value


#------------------------------------------------------------------------------
# Configuration instances
#
QUICK_CHECK = OptionBool('misc', 'quick_check', True)
FAIL_ON_CRC = OptionBool('misc', 'fail_on_crc', False)
SEND_GROUP = OptionBool('misc', 'send_group', False)

EMAIL_SERVER = OptionStr('misc', 'email_server', validation=validate_server)
EMAIL_TO     = OptionStr('misc', 'email_to', validation=validate_email)
EMAIL_FROM   = OptionStr('misc', 'email_from', validation=validate_email)
EMAIL_ACCOUNT= OptionStr('misc', 'email_account')
EMAIL_PWD    = OptionPassword('misc', 'email_pwd')
EMAIL_ENDJOB = OptionNumber('misc', 'email_endjob', 0, 0, 2)
EMAIL_FULL   = OptionBool('misc', 'email_full', False)
EMAIL_DIR    = OptionDir('misc', 'email_dir', create=False, validation=validate_dir_exists)

DIRSCAN_PP = OptionNumber('misc', 'dirscan_opts', 3, 0, 3)
VERSION_CHECK = OptionBool('misc', 'check_new_rel', True)
DIRSCAN_SCRIPT = OptionStr('misc', 'dirscan_script', 'None')
DIRSCAN_PRIORITY = OptionNumber('misc', 'dirscan_priority', NORMAL_PRIORITY)
AUTOBROWSER = OptionBool('misc', 'auto_browser', True)
REPLACE_ILLEGAL = OptionBool('misc', 'replace_illegal', True)

enable_unrar = OptionBool('misc', 'enable_unrar', True)
enable_unzip = OptionBool('misc', 'enable_unzip', True)
enable_filejoin = OptionBool('misc', 'enable_filejoin', True)
enable_tsjoin = OptionBool('misc', 'enable_tsjoin', True)
enable_par_cleanup = OptionBool('misc', 'enable_par_cleanup', True)
par_option = OptionStr('misc', 'par_option', '', validation=no_nonsense)
nice = OptionStr('misc', 'nice',  '', validation=no_nonsense)
ionice = OptionStr('misc', 'ionice',  '', validation=no_nonsense)

USERNAME_NEWZBIN = OptionStr('newzbin', 'username')
PASSWORD_NEWZBIN = OptionPassword('newzbin', 'password')
NEWZBIN_BOOKMARKS = OptionBool('newzbin', 'bookmarks', False)
NEWZBIN_UNBOOKMARK = OptionBool('newzbin', 'unbookmark', True)
BOOKMARK_RATE = OptionNumber('newzbin', 'bookmark_rate', 60, minval=15, maxval=24*60)

TOP_ONLY = OptionBool('misc', 'top_only', True)
AUTODISCONNECT = OptionBool('misc', 'auto_disconnect', True)

REPLACE_SPACES = OptionBool('misc', 'replace_spaces', False)
NO_DUPES = OptionBool('misc', 'no_dupes', False)
IGNORE_SAMPLES = OptionNumber('misc', 'ignore_samples', 0, 0, 2)
CREATE_GROUP_FOLDERS = OptionBool('misc', 'create_group_folders', False)
AUTO_SORT = OptionBool('misc', 'auto_sort', False)

SAFE_POSTPROC = OptionBool('misc', 'safe_postproc', False)
PAUSE_ON_POST_PROCESSING = OptionBool('misc', 'pause_on_post_processing', False)

SCHEDULES = OptionList('misc', 'schedlines')

ENABLE_TV_SORTING = OptionBool('misc', 'enable_tv_sorting', False)
TV_SORT_STRING = OptionStr('misc', 'tv_sort_string')

ENABLE_MOVIE_SORTING = OptionBool('misc', 'enable_movie_sorting', False)
MOVIE_SORT_STRING = OptionStr('misc', 'movie_sort_string')
MOVIE_SORT_EXTRA = OptionStr('misc', 'movie_sort_extra', '-cd%1', strip=False)
MOVIE_EXTRA_FOLDER = OptionBool('misc', 'movie_extra_folder', False)
MOVIE_CATEGORIES = OptionList('misc', 'movie_categories', ['movies'])

ENABLE_DATE_SORTING = OptionBool('misc', 'enable_date_sorting', False)
DATE_SORT_STRING = OptionStr('misc', 'date_sort_string')
DATE_CATEGORIES = OptionStr('misc', 'date_categories', ['tv'])

USERNAME_MATRIX = OptionStr('nzbmatrix', 'username')
PASSWORD_MATRIX = OptionPassword('nzbmatrix', 'password')

CONFIGLOCK = OptionBool('misc', 'config_lock', 0)

UMASK = OptionStr('misc', 'permissions', '', validation=validate_octal)
DOWNLOAD_DIR = OptionDir('misc', 'download_dir', DEF_DOWNLOAD_DIR, validation=validate_safedir)
DOWNLOAD_FREE = OptionStr('misc', 'download_free')
COMPLETE_DIR = OptionDir('misc', 'complete_dir', DEF_COMPLETE_DIR, apply_umask=True)
SCRIPT_DIR = OptionDir('misc', 'script_dir', create=False, validation=validate_dir_exists)
NZB_BACKUP_DIR = OptionDir('misc', 'nzb_backup_dir', DEF_NZBBACK_DIR)
CACHE_DIR = OptionDir('misc', 'cache_dir', 'cache', validation=validate_safedir)
ADMIN_DIR = OptionDir('misc', 'admin_dir', 'admin', validation=validate_safedir)
#LOG_DIR = OptionDir('misc', 'log_dir', 'logs')
DIRSCAN_DIR = OptionDir('misc', 'dirscan_dir', create=False)
DIRSCAN_SPEED = OptionNumber('misc', 'dirscan_speed', DEF_SCANRATE, 1, 3600)

CHERRYHOST = OptionStr('misc','host', DEF_HOST)
if sabnzbd.WIN32:
    CHERRYPORT = OptionStr('misc','port', DEF_PORT_WIN)
else:
    CHERRYPORT = OptionStr('misc','port', DEF_PORT_UNIX)
if sabnzbd.WIN32:
    HTTPS_PORT = OptionStr('misc','https_port', DEF_PORT_WIN_SSL)
else:
    HTTPS_PORT = OptionStr('misc','https_port', DEF_PORT_UNIX_SSL)

USERNAME = OptionStr('misc', 'username')
PASSWORD = OptionPassword('misc', 'password')
BANDWIDTH_LIMIT = OptionNumber('misc', 'bandwith_limit', 0)
REFRESH_RATE = OptionNumber('misc', 'refresh_rate', 0)
RSS_RATE = OptionNumber('misc', 'rss_rate', 60, 15, 24*60)
CACHE_LIMIT = OptionStr('misc', 'cache_limit')
WEB_DIR = OptionStr('misc', 'web_dir', 'Default')
WEB_DIR2 = OptionStr('misc', 'web_dir2')
WEB_COLOR = OptionStr('misc', 'web_color', 'darkblue')
WEB_COLOR2 = OptionStr('misc', 'web_color2')
CLEANUP_LIST = OptionList('misc', 'cleanup_list')

LOG_WEB = OptionBool('logging', 'enable_cherrypy_logging', False)
LOG_DIR = OptionDir('misc', 'log_dir', 'logs')
LOG_LEVEL = OptionNumber('logging', 'log_level', 0, 0, 2)
LOG_SIZE = OptionStr('logging', 'max_log_size', '5242880')
LOG_BACKUPS = OptionNumber('logging', 'log_backups', 5, 1, 1024)

HTTPS_CERT = OptionDir('misc', 'https_cert', 'server.cert', create=False)
HTTPS_KEY = OptionDir('misc', 'https_key', 'server.key', create=False)
ENABLE_HTTPS = OptionBool('misc', 'enable_https', False)

# Internal options, not saved in INI file
DEBUG_DELAY = OptionNumber('misc', 'debug_delay', 0, add=False)

API_KEY = OptionStr('misc','api_key', create_api_key())

#------------------------------------------------------------------------------
# Set root folders for Folder config-items
#
def set_root_folders(home, lcldata, prog, interf):
    EMAIL_DIR.set_root(home)
    DOWNLOAD_DIR.set_root(home)
    COMPLETE_DIR.set_root(home)
    SCRIPT_DIR.set_root(home)
    NZB_BACKUP_DIR.set_root(lcldata)
    CACHE_DIR.set_root(lcldata)
    ADMIN_DIR.set_root(lcldata)
    DIRSCAN_DIR.set_root(home)
    LOG_DIR.set_root(lcldata)
    HTTPS_CERT.set_root(ADMIN_DIR.get_path())
    HTTPS_KEY.set_root(ADMIN_DIR.get_path())
