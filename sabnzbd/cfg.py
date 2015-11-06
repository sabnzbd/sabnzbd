#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
    DEF_ADMIN_DIR
from sabnzbd.config import OptionBool, OptionNumber, OptionPassword, \
    OptionDir, OptionStr, OptionList, no_nonsense, \
    validate_octal, validate_safedir, validate_dir_exists, \
    create_api_key, validate_notempty

##############################################################################
# Email validation support
##############################################################################
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

if sabnzbd.WIN32:
    DEF_FOLDER_MAX = 128
else:
    DEF_FOLDER_MAX = 256

##############################################################################
# Configuration instances
##############################################################################
quick_check = OptionBool('misc', 'quick_check', True)
sfv_check = OptionBool('misc', 'sfv_check', True)

email_server = OptionStr('misc', 'email_server', validation=validate_server)
email_to = OptionList('misc', 'email_to', validation=validate_email)
email_from = OptionStr('misc', 'email_from', validation=validate_email)
email_account = OptionStr('misc', 'email_account')
email_pwd = OptionPassword('misc', 'email_pwd')
email_endjob = OptionNumber('misc', 'email_endjob', 0, 0, 2)
email_full = OptionBool('misc', 'email_full', False)
email_dir = OptionDir('misc', 'email_dir', create=True)
email_rss = OptionBool('misc', 'email_rss', False)

version_check = OptionNumber('misc', 'check_new_rel', 1)
autobrowser = OptionBool('misc', 'auto_browser', True)
replace_illegal = OptionBool('misc', 'replace_illegal', True)
pre_script = OptionStr('misc', 'pre_script', 'None')
script_can_fail = OptionBool('misc', 'script_can_fail', False)
start_paused = OptionBool('misc', 'start_paused', False)
enable_https_verification = OptionBool('misc', 'enable_https_verification', True)
ipv6_test_host = OptionStr('misc', 'ipv6_test_host', 'test-ipv6.sabnzbd.org')

enable_unrar = OptionBool('misc', 'enable_unrar', True)
enable_unzip = OptionBool('misc', 'enable_unzip', True)
enable_7zip = OptionBool('misc', 'enable_7zip', True)
enable_recursive = OptionBool('misc', 'enable_recursive', True)
enable_filejoin = OptionBool('misc', 'enable_filejoin', True)
enable_tsjoin = OptionBool('misc', 'enable_tsjoin', True)
enable_par_cleanup = OptionBool('misc', 'enable_par_cleanup', True)
enable_all_par = OptionBool('misc', 'enable_all_par', False)
never_repair = OptionBool('misc', 'never_repair', False)
ignore_unrar_dates = OptionBool('misc', 'ignore_unrar_dates', False)
overwrite_files = OptionBool('misc', 'overwrite_files', False)
flat_unpack = OptionBool('misc', 'flat_unpack', False)

par_option = OptionStr('misc', 'par_option', '', validation=no_nonsense)
nice = OptionStr('misc', 'nice', '', validation=no_nonsense)
ionice = OptionStr('misc', 'ionice', '', validation=no_nonsense)
ignore_wrong_unrar = OptionBool('misc', 'ignore_wrong_unrar', False)
par2_multicore = OptionBool('misc', 'par2_multicore', True)
allow_64bit_tools = OptionBool('misc', 'allow_64bit_tools', True)
allow_streaming = OptionBool('misc', 'allow_streaming', False)
pre_check = OptionBool('misc', 'pre_check', False)
fail_hopeless = OptionBool('misc', 'fail_hopeless', False)
req_completion_rate = OptionNumber('misc', 'req_completion_rate', 100.2, 100, 200)

rating_enable = OptionBool('misc', 'rating_enable', False)
rating_host = OptionStr('misc', 'rating_host', 'api.oznzb.com')
rating_api_key = OptionStr('misc', 'rating_api_key')
rating_feedback = OptionBool('misc', 'rating_feedback', True)
rating_filter_enable = OptionBool('misc', 'rating_filter_enable', False)
rating_filter_abort_audio = OptionNumber('misc', 'rating_filter_abort_audio', 0)
rating_filter_abort_video = OptionNumber('misc', 'rating_filter_abort_video', 0)
rating_filter_abort_encrypted = OptionBool('misc', 'rating_filter_abort_encrypted', False)
rating_filter_abort_encrypted_confirm = OptionBool('misc', 'rating_filter_abort_encrypted_confirm', False)
rating_filter_abort_spam = OptionBool('misc', 'rating_filter_abort_spam', False)
rating_filter_abort_spam_confirm = OptionBool('misc', 'rating_filter_abort_spam_confirm', False)
rating_filter_abort_downvoted = OptionBool('misc', 'rating_filter_abort_downvoted', False)
rating_filter_abort_keywords = OptionStr('misc', 'rating_filter_abort_keywords')
rating_filter_pause_audio = OptionNumber('misc', 'rating_filter_pause_audio', 0)
rating_filter_pause_video = OptionNumber('misc', 'rating_filter_pause_video', 0)
rating_filter_pause_encrypted = OptionBool('misc', 'rating_filter_pause_encrypted', False)
rating_filter_pause_encrypted_confirm = OptionBool('misc', 'rating_filter_pause_encrypted_confirm', False)
rating_filter_pause_spam = OptionBool('misc', 'rating_filter_pause_spam', False)
rating_filter_pause_spam_confirm = OptionBool('misc', 'rating_filter_pause_spam_confirm', False)
rating_filter_pause_downvoted = OptionBool('misc', 'rating_filter_pause_downvoted', False)
rating_filter_pause_keywords = OptionStr('misc', 'rating_filter_pause_keywords')

top_only = OptionBool('misc', 'top_only', False)
autodisconnect = OptionBool('misc', 'auto_disconnect', True)
queue_complete = OptionStr('misc', 'queue_complete')
queue_complete_pers = OptionBool('misc', 'queue_complete_pers', False)

replace_spaces = OptionBool('misc', 'replace_spaces', False)
replace_dots = OptionBool('misc', 'replace_dots', False)
no_dupes = OptionNumber('misc', 'no_dupes', 0)
no_series_dupes = OptionNumber('misc', 'no_series_dupes', 0)
backup_for_duplicates = OptionBool('misc', 'backup_for_duplicates', True)

ignore_samples = OptionNumber('misc', 'ignore_samples', 0, 0, 2)
create_group_folders = OptionBool('misc', 'create_group_folders', False)
auto_sort = OptionBool('misc', 'auto_sort', False)
folder_rename = OptionBool('misc', 'folder_rename', True)
folder_max_length = OptionNumber('misc', 'folder_max_length', DEF_FOLDER_MAX, 20, 65000)
pause_on_pwrar = OptionBool('misc', 'pause_on_pwrar', True)
prio_sort_list = OptionList('misc', 'prio_sort_list')
enable_meta = OptionBool('misc', 'enable_meta', True)

safe_postproc = OptionBool('misc', 'safe_postproc', True)
empty_postproc = OptionBool('misc', 'empty_postproc', False)
pause_on_post_processing = OptionBool('misc', 'pause_on_post_processing', False)
ampm = OptionBool('misc', 'ampm', False)
rss_filenames = OptionBool('misc', 'rss_filenames', False)
rss_odd_titles = OptionList('misc', 'rss_odd_titles', ['nzbindex.nl/', 'nzbindex.com/', 'nzbclub.com/'])

schedules = OptionList('misc', 'schedlines')
sched_converted = OptionBool('misc', 'sched_converted', False)

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

configlock = OptionBool('misc', 'config_lock', 0)

umask = OptionStr('misc', 'permissions', '', validation=validate_octal)
download_dir = OptionDir('misc', 'download_dir', DEF_DOWNLOAD_DIR, create=False, validation=validate_safedir)
download_free = OptionStr('misc', 'download_free')
complete_dir = OptionDir('misc', 'complete_dir', DEF_COMPLETE_DIR, create=False,
                         apply_umask=True, validation=validate_notempty)
script_dir = OptionDir('misc', 'script_dir', create=True, writable=False)
nzb_backup_dir = OptionDir('misc', 'nzb_backup_dir', DEF_NZBBACK_DIR)
admin_dir = OptionDir('misc', 'admin_dir', DEF_ADMIN_DIR, validation=validate_safedir)
# log_dir = OptionDir('misc', 'log_dir', 'logs')
dirscan_dir = OptionDir('misc', 'dirscan_dir', create=False)
dirscan_speed = OptionNumber('misc', 'dirscan_speed', DEF_SCANRATE, 0, 3600)
size_limit = OptionStr('misc', 'size_limit', '0')
password_file = OptionDir('misc', 'password_file', '', create=False)
fsys_type = OptionNumber('misc', 'fsys_type', 0, 0, 2)
wait_for_dfolder = OptionBool('misc', 'wait_for_dfolder', False)
warn_empty_nzb = OptionBool('misc', 'warn_empty_nzb', True)
sanitize_safe = OptionBool('misc', 'sanitize_safe', False)
api_logging = OptionBool('misc', 'api_logging', True)

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
bandwidth_perc = OptionNumber('misc', 'bandwidth_perc', 0, 0, 100)
bandwidth_max = OptionStr('misc', 'bandwidth_max')
refresh_rate = OptionNumber('misc', 'refresh_rate', 0)
rss_rate = OptionNumber('misc', 'rss_rate', 60, 15, 24 * 60)
cache_limit = OptionStr('misc', 'cache_limit')
web_dir = OptionStr('misc', 'web_dir', DEF_STDINTF)
web_dir2 = OptionStr('misc', 'web_dir2')
web_color = OptionStr('misc', 'web_color', '')
web_color2 = OptionStr('misc', 'web_color2')
cleanup_list = OptionList('misc', 'cleanup_list')
warned_old_queue = OptionBool('misc', 'warned_old_queue9', False)
notified_new_skin = OptionBool('misc', 'notified_new_skin', False)

unwanted_extensions = OptionList('misc', 'unwanted_extensions')
action_on_unwanted_extensions = OptionNumber('misc', 'action_on_unwanted_extensions', 0)

log_web = OptionBool('logging', 'enable_cherrypy_logging', False)
log_dir = OptionDir('misc', 'log_dir', 'logs', validation=validate_notempty)
log_level = OptionNumber('logging', 'log_level', 1, -1, 2)
log_size = OptionStr('logging', 'max_log_size', '5242880')
log_backups = OptionNumber('logging', 'log_backups', 5, 1, 1024)
log_new = OptionBool('logging', 'log_new', False)

https_cert = OptionDir('misc', 'https_cert', 'server.cert', create=False)
https_key = OptionDir('misc', 'https_key', 'server.key', create=False)
https_chain = OptionDir('misc', 'https_chain', create=False)
enable_https = OptionBool('misc', 'enable_https', False)

language = OptionStr('misc', 'language', 'en')
unpack_check = OptionBool('misc', 'unpack_check', True)
no_penalties = OptionBool('misc', 'no_penalties', False)
load_balancing = OptionNumber('misc', 'load_balancing', 2)
ipv6_servers = OptionNumber('misc', 'ipv6_servers', 1, 0, 2)

# Internal options, not saved in INI file
debug_delay = OptionNumber('misc', 'debug_delay', 0, add=False)

api_key = OptionStr('misc', 'api_key', create_api_key())
nzb_key = OptionStr('misc', 'nzb_key', create_api_key())
disable_key = OptionBool('misc', 'disable_api_key', False, protect=True)
api_warnings = OptionBool('misc', 'api_warnings', True, protect=True)
local_ranges = OptionList('misc', 'local_ranges', protect=True)
inet_exposure = OptionNumber('misc', 'inet_exposure', 0, protect=True)  # 0=local-only, 1=nzb, 2=api, 3=full_api, 4=webui
max_art_tries = OptionNumber('misc', 'max_art_tries', 3, 2)
max_art_opt = OptionBool('misc', 'max_art_opt', False)
use_pickle = OptionBool('misc', 'use_pickle', False)
no_ipv6 = OptionBool('misc', 'no_ipv6', False)

# [ncenter]
ncenter_enable = OptionBool('ncenter', 'ncenter_enable', sabnzbd.DARWIN_VERSION > 7)
ncenter_prio_startup = OptionBool('ncenter', 'ncenter_prio_startup', True)
ncenter_prio_download = OptionBool('ncenter', 'ncenter_prio_download', False)
ncenter_prio_pp = OptionBool('ncenter', 'ncenter_prio_pp', False)
ncenter_prio_complete = OptionBool('ncenter', 'ncenter_prio_complete', True)
ncenter_prio_failed = OptionBool('ncenter', 'ncenter_prio_failed', True)
ncenter_prio_disk_full = OptionBool('ncenter', 'ncenter_prio_disk_full', True)
ncenter_prio_warning = OptionBool('ncenter', 'ncenter_prio_warning', False)
ncenter_prio_error = OptionBool('ncenter', 'ncenter_prio_error', False)
ncenter_prio_queue_done = OptionBool('ncenter', 'ncenter_prio_queue_done', True)
ncenter_prio_other = OptionBool('ncenter', 'ncenter_prio_other', False)

# [ntfosd]
ntfosd_enable = OptionBool('ntfosd', 'ntfosd_enable', not sabnzbd.WIN32 and not sabnzbd.DARWIN)
ntfosd_prio_startup = OptionBool('ntfosd', 'ntfosd_prio_startup', True)
ntfosd_prio_download = OptionBool('ntfosd', 'ntfosd_prio_download', False)
ntfosd_prio_pp = OptionBool('ntfosd', 'ntfosd_prio_pp', False)
ntfosd_prio_complete = OptionBool('ntfosd', 'ntfosd_prio_complete', True)
ntfosd_prio_failed = OptionBool('ntfosd', 'ntfosd_prio_failed', True)
ntfosd_prio_disk_full = OptionBool('ntfosd', 'ntfosd_prio_disk_full', True)
ntfosd_prio_warning = OptionBool('ntfosd', 'ntfosd_prio_warning', False)
ntfosd_prio_error = OptionBool('ntfosd', 'ntfosd_prio_error', False)
ntfosd_prio_queue_done = OptionBool('ntfosd', 'ntfosd_prio_queue_done', True)
ntfosd_prio_other = OptionBool('ntfosd', 'ntfosd_prio_other', False)

# [growl]
growl_enable = OptionBool('growl', 'growl_enable', sabnzbd.DARWIN_VERSION < 8)
growl_server = OptionStr('growl', 'growl_server')
growl_password = OptionPassword('growl', 'growl_password')
growl_prio_startup = OptionBool('growl', 'growl_prio_startup', True)
growl_prio_download = OptionBool('growl', 'growl_prio_download', False)
growl_prio_pp = OptionBool('growl', 'growl_prio_pp', False)
growl_prio_complete = OptionBool('growl', 'growl_prio_complete', True)
growl_prio_failed = OptionBool('growl', 'growl_prio_failed', True)
growl_prio_disk_full = OptionBool('growl', 'growl_prio_disk_full', True)
growl_prio_warning = OptionBool('growl', 'growl_prio_warning', False)
growl_prio_error = OptionBool('growl', 'growl_prio_error', False)
growl_prio_queue_done = OptionBool('growl', 'growl_prio_queue_done', True)
growl_prio_other = OptionBool('growl', 'growl_prio_other', False)

# [prowl]
prowl_enable = OptionBool('prowl', 'prowl_enable', False)
prowl_apikey = OptionStr('prowl', 'prowl_apikey')
prowl_prio_startup = OptionNumber('prowl', 'prowl_prio_startup', -3)
prowl_prio_download = OptionNumber('prowl', 'prowl_prio_download', -3)
prowl_prio_pp = OptionNumber('prowl', 'prowl_prio_pp', -3)
prowl_prio_complete = OptionNumber('prowl', 'prowl_prio_complete', 0)
prowl_prio_failed = OptionNumber('prowl', 'prowl_prio_failed', 1)
prowl_prio_disk_full = OptionNumber('prowl', 'prowl_prio_disk_full', 1)
prowl_prio_warning = OptionNumber('prowl', 'prowl_prio_warning', -3)
prowl_prio_error = OptionNumber('prowl', 'prowl_prio_error', -3)
prowl_prio_queue_done = OptionNumber('prowl', 'prowl_prio_queue_done', 0)
prowl_prio_other = OptionNumber('prowl', 'prowl_prio_other', -3)

# [pushover]
pushover_token = OptionStr('pushover', 'pushover_token')
pushover_userkey = OptionStr('pushover', 'pushover_userkey')
pushover_device = OptionStr('pushover', 'pushover_device')
pushover_enable = OptionBool('pushover', 'pushover_enable')
pushover_prio_startup = OptionNumber('pushover', 'pushover_prio_startup', -2)
pushover_prio_download = OptionNumber('pushover', 'pushover_prio_download', -2)
pushover_prio_pp = OptionNumber('pushover', 'pushover_prio_pp', -2)
pushover_prio_complete = OptionNumber('pushover', 'pushover_prio_complete', 1)
pushover_prio_failed = OptionNumber('pushover', 'pushover_prio_failed', 1)
pushover_prio_disk_full = OptionNumber('pushover', 'pushover_prio_disk_full', 1)
pushover_prio_warning = OptionNumber('pushover', 'pushover_prio_warning', -2)
pushover_prio_error = OptionNumber('pushover', 'pushover_prio_error', -2)
pushover_prio_queue_done = OptionNumber('pushover', 'pushover_prio_queue_done', -1)
pushover_prio_other = OptionNumber('pushover', 'pushover_prio_other', -2)

# [pushbullet]
pushbullet_enable = OptionBool('pushbullet', 'pushbullet_enable')
pushbullet_apikey = OptionStr('pushbullet', 'pushbullet_apikey')
pushbullet_device = OptionStr('pushbullet', 'pushbullet_device')
pushbullet_prio_startup = OptionNumber('pushbullet', 'pushbullet_prio_startup', 0)
pushbullet_prio_download = OptionNumber('pushbullet', 'pushbullet_prio_download', 0)
pushbullet_prio_pp = OptionNumber('pushbullet', 'pushbullet_prio_pp', 0)
pushbullet_prio_complete = OptionNumber('pushbullet', 'pushbullet_prio_complete', 1)
pushbullet_prio_failed = OptionNumber('pushbullet', 'pushbullet_prio_failed', 1)
pushbullet_prio_disk_full = OptionNumber('pushbullet', 'pushbullet_prio_disk_full', 1)
pushbullet_prio_warning = OptionNumber('pushbullet', 'pushbullet_prio_warning', 0)
pushbullet_prio_error = OptionNumber('pushbullet', 'pushbullet_prio_error', 0)
pushbullet_prio_queue_done = OptionNumber('pushbullet', 'pushbullet_prio_queue_done', 0)
pushbullet_prio_other = OptionNumber('pushbullet', 'pushbullet_prio_other', 0)


quota_size = OptionStr('misc', 'quota_size')
quota_day = OptionStr('misc', 'quota_day')
quota_resume = OptionBool('misc', 'quota_resume', False)
quota_period = OptionStr('misc', 'quota_period', 'm')

osx_menu = OptionBool('misc', 'osx_menu', True)
osx_speed = OptionBool('misc', 'osx_speed', True)
keep_awake = OptionBool('misc', 'keep_awake', True)
win_menu = OptionBool('misc', 'win_menu', True)
allow_incomplete_nzb = OptionBool('misc', 'allow_incomplete_nzb', False)
marker_file = OptionStr('misc', 'nomedia_marker', '')
wait_ext_drive = OptionNumber('misc', 'wait_ext_drive', 5, 1, 60)
queue_limit = OptionNumber('misc', 'queue_limit', 20, 0)
history_limit = OptionNumber('misc', 'history_limit', 10, 0)
show_sysload = OptionNumber('misc', 'show_sysload', 2, 0, 2)
web_watchdog = OptionBool('misc', 'web_watchdog', False)
enable_bonjour = OptionBool('misc', 'enable_bonjour', True)
warn_dupl_jobs = OptionBool('misc', 'warn_dupl_jobs', True)
new_nzb_on_failure = OptionBool('misc', 'new_nzb_on_failure', False)


##############################################################################
# Set root folders for Folder config-items
##############################################################################
def set_root_folders(home, lcldata):
    email_dir.set_root(home)
    download_dir.set_root(home)
    complete_dir.set_root(home)
    script_dir.set_root(home)
    nzb_backup_dir.set_root(lcldata)
    admin_dir.set_root(lcldata)
    dirscan_dir.set_root(home)
    log_dir.set_root(lcldata)
    password_file.set_root(home)


def set_root_folders2():
    https_cert.set_root(admin_dir.get_path())
    https_key.set_root(admin_dir.get_path())
    https_chain.set_root(admin_dir.get_path())
