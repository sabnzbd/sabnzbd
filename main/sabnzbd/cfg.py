#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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
__NAME__ = "sabnzbd.cfg"

import sabnzbd.config as config


QUICK_CHECK = config.OptionBool('misc', 'quick_check', True)
FAIL_ON_CRC = config.OptionBool('misc', 'fail_on_crc', False)
SEND_GROUP = config.OptionBool('misc', 'send_group', False)

EMAIL_SERVER = config.OptionStr('misc', 'email_server')
EMAIL_TO     = config.OptionStr('misc', 'email_to', validation=config.validate_email)
EMAIL_FROM   = config.OptionStr('misc', 'email_from', validation=config.validate_email)
EMAIL_ACCOUNT= config.OptionStr('misc', 'email_account')
EMAIL_PWD    = config.OptionPassword('misc', 'email_pwd')
EMAIL_ENDJOB = config.OptionNumber('misc', 'email_endjob', 0, 0, 2)
EMAIL_FULL   = config.OptionBool('misc', 'email_full', False)
EMAIL_DIR    = config.OptionDir('misc', 'email_dir', create=False)

DIRSCAN_PP = config.OptionNumber('misc', 'dirscan_opts', 3)
VERSION_CHECK = config.OptionBool('misc', 'check_new_rel', True)
DIRSCAN_SCRIPT = config.OptionStr('misc', 'dirscan_script', 'None')
DIRSCAN_PRIORITY = config.OptionNumber('misc', 'dirscan_priority', 0)
AUTOBROWSER = config.OptionBool('misc', 'auto_browser', True)
REPLACE_ILLEGAL = config.OptionBool('misc', 'replace_illegal', True)

enable_unrar = config.OptionBool('misc', 'enable_unrar', True)
enable_unzip = config.OptionBool('misc', 'enable_unzip', True)
enable_filejoin = config.OptionBool('misc', 'enable_filejoin', True)
enable_tsjoin = config.OptionBool('misc', 'enable_tsjoin', True)
enable_par_cleanup = config.OptionBool('misc', 'enable_par_cleanup', True)
par_option = config.OptionStr('misc', 'par_option', '', validation=config.no_nonsense)
ionice = config.OptionStr('misc', 'ionice',  '', validation=config.no_nonsense)

USERNAME_NEWZBIN = config.OptionStr('newzbin', 'username')
PASSWORD_NEWZBIN = config.OptionPassword('newzbin', 'password')
NEWZBIN_BOOKMARKS = config.OptionBool('newzbin', 'bookmarks', False)
NEWZBIN_UNBOOKMARK = config.OptionBool('newzbin', 'unbookmark', False)
BOOKMARK_RATE = config.OptionNumber('newzbin', 'bookmark_rate', 60, minval=15, maxval=24*60)

TOP_ONLY = config.OptionBool('misc', 'top_only', True)
AUTODISCONNECT = config.OptionBool('misc', 'auto_disconnect', True)

REPLACE_SPACES = config.OptionBool('misc', 'replace_spaces', False)
NO_DUPES = config.OptionBool('misc', 'no_dupes', False)
IGNORE_SAMPLES = config.OptionBool('misc', 'ignore_samples', False)
CREATE_GROUP_FOLDERS = config.OptionBool('misc', 'create_group_folders', False)
AUTO_SORT = config.OptionBool('misc', 'auto_sort', False)

SAFE_POSTPROC = config.OptionBool('misc', 'safe_postproc', False)
PAUSE_ON_POST_PROCESSING = config.OptionBool('misc', 'pause_on_post_processing', False)

SCHEDULES = config.OptionList('misc', 'schedlines')

ENABLE_TV_SORTING = config.OptionBool('misc', 'enable_tv_sorting', False)
TV_SORT_STRING = config.OptionStr('misc', 'tv_sort_string')

ENABLE_MOVIE_SORTING = config.OptionBool('misc', 'enable_movie_sorting', False)
MOVIE_SORT_STRING = config.OptionStr('misc', 'movie_sort_string') 
MOVIE_SORT_EXTRA = config.OptionStr('misc', 'movie_sort_extra', '-cd%1')
MOVIE_EXTRA_FOLDER = config.OptionBool('misc', 'movie_extra_folder', False)
MOVIE_CATEGORIES = config.OptionList('misc', 'movie_categories', ['movies'])

ENABLE_DATE_SORTING = config.OptionBool('misc', 'enable_date_sorting', False)
DATE_SORT_STRING = config.OptionStr('misc', 'date_sort_string')
DATE_CATEGORIES = config.OptionStr('misc', 'date_categories', ['tv'])

USERNAME_MATRIX = config.OptionStr('nzbmatrix', 'username')
PASSWORD_MATRIX = config.OptionPassword('nzbmatrix', 'password')

#### Set root folders for Folder config-items
def set_root_folders(home, lcldata, prog):
    EMAIL_DIR.set_root(home)
