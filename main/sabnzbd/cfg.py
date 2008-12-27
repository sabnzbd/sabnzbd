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

from sabnzbd.config import OptionBool, OptionNumber, OptionNumber, OptionPassword, \
                           OptionDir, OptionStr, OptionList, validate_email, no_nonsense


QUICK_CHECK = OptionBool('misc', 'quick_check', True)
FAIL_ON_CRC = OptionBool('misc', 'fail_on_crc', False)
SEND_GROUP = OptionBool('misc', 'send_group', False)

EMAIL_SERVER = OptionStr('misc', 'email_server')
EMAIL_TO     = OptionStr('misc', 'email_to', validation=validate_email)
EMAIL_FROM   = OptionStr('misc', 'email_from', validation=validate_email)
EMAIL_ACCOUNT= OptionStr('misc', 'email_account')
EMAIL_PWD    = OptionPassword('misc', 'email_pwd')
EMAIL_ENDJOB = OptionNumber('misc', 'email_endjob', 0, 0, 2)
EMAIL_FULL   = OptionBool('misc', 'email_full', False)
EMAIL_DIR    = OptionDir('misc', 'email_dir', create=False)

DIRSCAN_PP = OptionNumber('misc', 'dirscan_opts', 3, 0, 3)
VERSION_CHECK = OptionBool('misc', 'check_new_rel', True)
DIRSCAN_SCRIPT = OptionStr('misc', 'dirscan_script', 'None')
DIRSCAN_PRIORITY = OptionNumber('misc', 'dirscan_priority', 0)
AUTOBROWSER = OptionBool('misc', 'auto_browser', True)
REPLACE_ILLEGAL = OptionBool('misc', 'replace_illegal', True)

enable_unrar = OptionBool('misc', 'enable_unrar', True)
enable_unzip = OptionBool('misc', 'enable_unzip', True)
enable_filejoin = OptionBool('misc', 'enable_filejoin', True)
enable_tsjoin = OptionBool('misc', 'enable_tsjoin', True)
enable_par_cleanup = OptionBool('misc', 'enable_par_cleanup', True)
par_option = OptionStr('misc', 'par_option', '', validation=no_nonsense)
ionice = OptionStr('misc', 'ionice',  '', validation=no_nonsense)

USERNAME_NEWZBIN = OptionStr('newzbin', 'username')
PASSWORD_NEWZBIN = OptionPassword('newzbin', 'password')
NEWZBIN_BOOKMARKS = OptionBool('newzbin', 'bookmarks', False)
NEWZBIN_UNBOOKMARK = OptionBool('newzbin', 'unbookmark', False)
BOOKMARK_RATE = OptionNumber('newzbin', 'bookmark_rate', 60, minval=15, maxval=24*60)

TOP_ONLY = OptionBool('misc', 'top_only', True)
AUTODISCONNECT = OptionBool('misc', 'auto_disconnect', True)

REPLACE_SPACES = OptionBool('misc', 'replace_spaces', False)
NO_DUPES = OptionBool('misc', 'no_dupes', False)
IGNORE_SAMPLES = OptionBool('misc', 'ignore_samples', False)
CREATE_GROUP_FOLDERS = OptionBool('misc', 'create_group_folders', False)
AUTO_SORT = OptionBool('misc', 'auto_sort', False)

SAFE_POSTPROC = OptionBool('misc', 'safe_postproc', False)
PAUSE_ON_POST_PROCESSING = OptionBool('misc', 'pause_on_post_processing', False)

SCHEDULES = OptionList('misc', 'schedlines')

ENABLE_TV_SORTING = OptionBool('misc', 'enable_tv_sorting', False)
TV_SORT_STRING = OptionStr('misc', 'tv_sort_string')

ENABLE_MOVIE_SORTING = OptionBool('misc', 'enable_movie_sorting', False)
MOVIE_SORT_STRING = OptionStr('misc', 'movie_sort_string') 
MOVIE_SORT_EXTRA = OptionStr('misc', 'movie_sort_extra', '-cd%1')
MOVIE_EXTRA_FOLDER = OptionBool('misc', 'movie_extra_folder', False)
MOVIE_CATEGORIES = OptionList('misc', 'movie_categories', ['movies'])

ENABLE_DATE_SORTING = OptionBool('misc', 'enable_date_sorting', False)
DATE_SORT_STRING = OptionStr('misc', 'date_sort_string')
DATE_CATEGORIES = OptionStr('misc', 'date_categories', ['tv'])

USERNAME_MATRIX = OptionStr('nzbmatrix', 'username')
PASSWORD_MATRIX = OptionPassword('nzbmatrix', 'password')

#### Set root folders for Folder config-items
def set_root_folders(home, lcldata, prog):
    EMAIL_DIR.set_root(home)
