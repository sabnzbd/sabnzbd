#!/usr/bin/python -OO
# Copyright 2008-2012 The SABnzbd-Team <team@sabnzbd.org>
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
import re

import sabnzbd
from sabnzbd.constants import DEF_HOST, DEF_PORT_WIN_SSL, DEF_PORT_WIN, DEF_STDINTF, \
                              DEF_DOWNLOAD_DIR, DEF_NZBBACK_DIR, DEF_PORT_UNIX_SSL, \
                              NORMAL_PRIORITY, DEF_SCANRATE, DEF_PORT_UNIX, DEF_COMPLETE_DIR, \
                              DEF_ADMIN_DIR, NOTIFY_KEYS
from sabnzbd.config import OptionBool, OptionNumber, OptionPassword, \
                           OptionDir, OptionStr, OptionList, no_nonsense, \
                           validate_octal, validate_safedir, validate_dir_exists, \
                           create_api_key, validate_notempty

#------------------------------------------------------------------------------
# Email validation support
#
RE_VAL = re.compile('[^@ ]+@[^.@ ]+\.[^.@ ]')
def validate_email(value):
    global email_endjob, email_full, email_rss
    if email_endjob() or email_full() or email_rss():
        if isinstance(value, list):
            values = value
        else:
            values = [value]
        for addr in values:
            if not (addr and RE_VAL.match(addr)):
                return T('%s is not a valid email address') % addr, None
    return None, value


def validate_server(value):
    """ Check if server non-empty"""
    global email_endjob, email_full, email_rss
    if value == '' and (email_endjob() or email_full() or email_rss()):
        return T('Server address required'), None
    else:
        return None, value

#------------------------------------------------------------------------------
if sabnzbd.WIN32:
    DEF_FOLDER_MAX = 128
else:
    DEF_FOLDER_MAX = 256

#------------------------------------------------------------------------------
# Configuration instances
#
quick_check = OptionBool('misc', 'quick_check', True)
fail_on_crc = OptionBool('misc', 'fail_on_crc', True)
send_group = OptionBool('misc', 'send_group', False)
sfv_check = OptionBool('misc', 'sfv_check', True)

email_server  = OptionStr('misc', 'email_server', validation=validate_server)
email_to      = OptionList('misc', 'email_to', validation=validate_email)
email_from    = OptionStr('misc', 'email_from', validation=validate_email)
email_account = OptionStr('misc', 'email_account')
email_pwd     = OptionPassword('misc', 'email_pwd')
email_endjob  = OptionNumber('misc', 'email_endjob', 0, 0, 2)
email_full    = OptionBool('misc', 'email_full', False)
email_dir     = OptionDir('misc', 'email_dir', create=True)
email_rss     = OptionBool('misc', 'email_rss', False)

version_check = OptionNumber('misc', 'check_new_rel', 1)
autobrowser = OptionBool('misc', 'auto_browser', True)
replace_illegal = OptionBool('misc', 'replace_illegal', True)
pre_script = OptionStr('misc', 'pre_script', 'None')
start_paused = OptionBool('misc', 'start_paused', False)

enable_unrar = OptionBool('misc', 'enable_unrar', True)
enable_unzip = OptionBool('misc', 'enable_unzip', True)
enable_filejoin = OptionBool('misc', 'enable_filejoin', True)
enable_tsjoin = OptionBool('misc', 'enable_tsjoin', True)
enable_par_cleanup = OptionBool('misc', 'enable_par_cleanup', True)
never_repair = OptionBool('misc', 'never_repair', False)
ignore_unrar_dates = OptionBool('misc', 'ignore_unrar_dates', False)
overwrite_files = OptionBool('misc', 'overwrite_files', False)

par_option = OptionStr('misc', 'par_option', '', validation=no_nonsense)
nice = OptionStr('misc', 'nice',  '', validation=no_nonsense)
ionice = OptionStr('misc', 'ionice',  '', validation=no_nonsense)
ignore_wrong_unrar = OptionBool('misc', 'ignore_wrong_unrar', False)
par2_multicore = OptionBool('misc', 'par2_multicore', True)
allow_64bit_tools = OptionBool('misc', 'allow_64bit_tools', True)
allow_streaming = OptionBool('misc', 'allow_streaming', False)
pre_check = OptionBool('misc', 'pre_check', False)
req_completion_rate = OptionNumber('misc', 'req_completion_rate', 100.2, 100, 200)

newzbin_username = OptionStr('newzbin', 'username')
newzbin_password = OptionPassword('newzbin', 'password')
newzbin_bookmarks = OptionBool('newzbin', 'bookmarks', False)
newzbin_unbookmark = OptionBool('newzbin', 'unbookmark', True)
bookmark_rate = OptionNumber('newzbin', 'bookmark_rate', 60, minval=15, maxval=24*60)
newzbin_url = OptionStr('newzbin', 'url', 'www.newzbin2.es')

top_only = OptionBool('misc', 'top_only', False)
autodisconnect = OptionBool('misc', 'auto_disconnect', True)
queue_complete = OptionStr('misc', 'queue_complete')
queue_complete_pers = OptionBool('misc', 'queue_complete_pers', False)

replace_spaces = OptionBool('misc', 'replace_spaces', False)
replace_dots = OptionBool('misc', 'replace_dots', False)
no_dupes = OptionNumber('misc', 'no_dupes', 0)
ignore_samples = OptionNumber('misc', 'ignore_samples', 0, 0, 2)
create_group_folders = OptionBool('misc', 'create_group_folders', False)
auto_sort = OptionBool('misc', 'auto_sort', False)
folder_rename = OptionBool('misc', 'folder_rename', True)
folder_max_length = OptionNumber('misc', 'folder_max_length', DEF_FOLDER_MAX, 20, 65000)
pause_on_pwrar = OptionBool('misc', 'pause_on_pwrar', True)
prio_sort_list = OptionList('misc', 'prio_sort_list')

safe_postproc = OptionBool('misc', 'safe_postproc', True)
pause_on_post_processing = OptionBool('misc', 'pause_on_post_processing', False)
ampm = OptionBool('misc', 'ampm', False)
rss_filenames = OptionBool('misc', 'rss_filenames', False)
rss_odd_titles = OptionList('misc', 'rss_odd_titles', ['nzbindex.nl/', 'nzbindex.com/', 'nzbclub.com/'])

schedules = OptionList('misc', 'schedlines')

enable_tv_sorting = OptionBool('misc', 'enable_tv_sorting', False)
tv_sort_string = OptionStr('misc', 'tv_sort_string')
tv_sort_countries = OptionNumber('misc', 'tv_sort_countries', 1)
tv_categories = OptionList('misc', 'tv_categories', '')
movie_rename_limit = OptionStr('misc', 'movie_rename_limit', '100M')

enable_movie_sorting = OptionBool('misc', 'enable_movie_sorting', False)
movie_sort_string = OptionStr('misc', 'movie_sort_string')
movie_sort_extra = OptionStr('misc', 'movie_sort_extra', '-cd%1', strip=False)
movie_extra_folders = OptionBool('misc', 'movie_extra_folder', False)
movie_categories = OptionList('misc', 'movie_categories', ['movies'])

enable_date_sorting = OptionBool('misc', 'enable_date_sorting', False)
date_sort_string = OptionStr('misc', 'date_sort_string')
date_categories = OptionStr('misc', 'date_categories', ['tv'])

matrix_username = OptionStr('nzbmatrix', 'username')
matrix_apikey = OptionStr('nzbmatrix', 'apikey')
matrix_del_bookmark = OptionBool('nzbmatrix', 'del_bookmark', True)
xxx_username = OptionStr('nzbxxx', 'username')
xxx_apikey = OptionStr('nzbxxx', 'apikey')

configlock = OptionBool('misc', 'config_lock', 0)

umask = OptionStr('misc', 'permissions', '', validation=validate_octal)
download_dir = OptionDir('misc', 'download_dir', DEF_DOWNLOAD_DIR, validation=validate_safedir)
download_free = OptionStr('misc', 'download_free')
complete_dir = OptionDir('misc', 'complete_dir', DEF_COMPLETE_DIR, create=False, \
                         apply_umask=True, validation=validate_notempty)
script_dir = OptionDir('misc', 'script_dir', create=True)
nzb_backup_dir = OptionDir('misc', 'nzb_backup_dir', DEF_NZBBACK_DIR)
cache_dir = OptionDir('misc', 'cache_dir', 'cache', create=False, validation=validate_safedir)
admin_dir = OptionDir('misc', 'admin_dir', DEF_ADMIN_DIR, validation=validate_safedir)
#log_dir = OptionDir('misc', 'log_dir', 'logs')
dirscan_dir = OptionDir('misc', 'dirscan_dir', create=False)
dirscan_speed = OptionNumber('misc', 'dirscan_speed', DEF_SCANRATE, 0, 3600)
size_limit = OptionStr('misc', 'size_limit', '0')
password_file = OptionDir('misc', 'password_file', '', create=False)
fsys_type = OptionNumber('misc', 'fsys_type', 0, 0, 2)

cherryhost = OptionStr('misc', 'host', DEF_HOST)
if sabnzbd.WIN32:
    cherryport = OptionStr('misc', 'port', DEF_PORT_WIN)
else:
    cherryport = OptionStr('misc', 'port', DEF_PORT_UNIX)
if sabnzbd.WIN32:
    https_port = OptionStr('misc', 'https_port', DEF_PORT_WIN_SSL)
else:
    https_port = OptionStr('misc', 'https_port', DEF_PORT_UNIX_SSL)

username = OptionStr('misc', 'username')
password = OptionPassword('misc', 'password')
login_realm = OptionStr('misc', 'login_realm', 'SABnzbd')
bandwidth_limit = OptionNumber('misc', 'bandwidth_limit', 0)
refresh_rate = OptionNumber('misc', 'refresh_rate', 0)
rss_rate = OptionNumber('misc', 'rss_rate', 60, 15, 24*60)
cache_limit = OptionStr('misc', 'cache_limit')
web_dir = OptionStr('misc', 'web_dir', DEF_STDINTF)
web_dir2 = OptionStr('misc', 'web_dir2')
web_color = OptionStr('misc', 'web_color', '')
web_color2 = OptionStr('misc', 'web_color2')
cleanup_list = OptionList('misc', 'cleanup_list')
warned_old_queue = OptionBool('misc', 'warned_old_queue', False)

log_web = OptionBool('logging', 'enable_cherrypy_logging', False)
log_dir = OptionDir('misc', 'log_dir', 'logs', validation=validate_notempty)
log_level = OptionNumber('logging', 'log_level', 1, -1, 2)
log_size = OptionStr('logging', 'max_log_size', '5242880')
log_backups = OptionNumber('logging', 'log_backups', 5, 1, 1024)
log_new = OptionBool('logging', 'log_new', False)

https_cert = OptionDir('misc', 'https_cert', 'server.cert', create=False)
https_key = OptionDir('misc', 'https_key', 'server.key', create=False)
https_chain = OptionDir('misc','https_chain', create=False)
enable_https = OptionBool('misc', 'enable_https', False)

language = OptionStr('misc', 'language', 'en')
ssl_type = OptionStr('misc', 'ssl_type', 'v23')
unpack_check = OptionBool('misc', 'unpack_check', True)
no_penalties = OptionBool('misc', 'no_penalties', False)
randomize_server_ip = OptionBool('misc', 'randomize_server_ip', False)

# Internal options, not saved in INI file
debug_delay = OptionNumber('misc', 'debug_delay', 0, add=False)

api_key = OptionStr('misc', 'api_key', create_api_key())
nzb_key = OptionStr('misc', 'nzb_key', create_api_key())
disable_key = OptionBool('misc', 'disable_api_key', False)
api_warnings = OptionBool('misc', 'api_warnings', True)
max_art_tries = OptionNumber('misc', 'max_art_tries', 3, 2)
max_art_opt = OptionBool('misc', 'max_art_opt', False)
use_pickle = OptionBool('misc', 'use_pickle', False)
no_ipv6 = OptionBool('misc', 'no_ipv6', False)

growl_server = OptionStr('growl', 'growl_server')
growl_password = OptionPassword('growl', 'growl_password')
growl_enable = OptionBool('growl', 'growl_enable', not sabnzbd.DARWIN_ML)
ntfosd_enable = OptionBool('growl', 'ntfosd_enable', not sabnzbd.WIN32 and not sabnzbd.DARWIN)
ncenter_enable = OptionBool('growl', 'ncenter_enable', sabnzbd.DARWIN)
notify_classes = OptionList('growl', 'notify_classes', NOTIFY_KEYS)

quota_size = OptionStr('misc', 'quota_size')
quota_day = OptionStr('misc', 'quota_day')
quota_resume = OptionBool('misc', 'quota_resume', False)
quota_period = OptionStr('misc', 'quota_period', 'm')

osx_menu = OptionBool('misc', 'osx_menu', True)
osx_speed = OptionBool('misc', 'osx_speed', True)
keep_awake = OptionBool('misc', 'keep_awake', True)
win_menu = OptionBool('misc', 'win_menu', True)
uniconfig = OptionBool('misc', 'uniconfig', True)
allow_incomplete_nzb = OptionBool('misc', 'allow_incomplete_nzb', False)
marker_file = OptionStr('misc', 'nomedia_marker', '')
wait_ext_drive = OptionNumber('misc', 'wait_ext_drive', 5, 1, 60)
history_limit = OptionNumber('misc', 'history_limit', 50, 0)
show_sysload = OptionNumber('misc', 'show_sysload', 2, 0, 2)

#------------------------------------------------------------------------------
# Set root folders for Folder config-items
#
def set_root_folders(home, lcldata):
    email_dir.set_root(home)
    download_dir.set_root(home)
    complete_dir.set_root(home)
    script_dir.set_root(home)
    nzb_backup_dir.set_root(lcldata)
    cache_dir.set_root(lcldata)
    admin_dir.set_root(lcldata)
    dirscan_dir.set_root(home)
    log_dir.set_root(lcldata)
    password_file.set_root(home)

def set_root_folders2():
    https_cert.set_root(admin_dir.get_path())
    https_key.set_root(admin_dir.get_path())
    https_chain.set_root(admin_dir.get_path())