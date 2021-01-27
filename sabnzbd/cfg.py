#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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
from sabnzbd.config import (
    OptionBool,
    OptionNumber,
    OptionPassword,
    OptionDir,
    OptionStr,
    OptionList,
    validate_octal,
    validate_safedir,
    all_lowercase,
    create_api_key,
    validate_notempty,
    clean_nice_ionice_parameters,
    validate_strip_right_slash,
)
from sabnzbd.constants import (
    DEF_HOST,
    DEF_PORT,
    DEF_STDINTF,
    DEF_ADMIN_DIR,
    DEF_DOWNLOAD_DIR,
    DEF_NZBBACK_DIR,
    DEF_SCANRATE,
    DEF_COMPLETE_DIR,
    DEF_FOLDER_MAX,
    DEF_FILE_MAX,
)

##############################################################################
# Email validation support
##############################################################################
RE_VAL = re.compile(r"[^@ ]+@[^.@ ]+\.[^.@ ]")


def validate_email(value):
    global email_endjob, email_full, email_rss
    if email_endjob() or email_full() or email_rss():
        if isinstance(value, list):
            values = value
        else:
            values = [value]
        for addr in values:
            if not (addr and RE_VAL.match(addr)):
                return T("%s is not a valid email address") % addr, None
    return None, value


def validate_server(value):
    """ Check if server non-empty"""
    global email_endjob, email_full, email_rss
    if value == "" and (email_endjob() or email_full() or email_rss()):
        return T("Server address required"), None
    else:
        return None, value


def validate_script(value):
    """ Check if value is a valid script """
    if not sabnzbd.__INITIALIZED__ or (value and sabnzbd.filesystem.is_valid_script(value)):
        return None, value
    elif (value and value == "None") or not value:
        return None, "None"
    return T("%s is not a valid script") % value, None


##############################################################################
# Special settings
##############################################################################
pre_script = OptionStr("misc", "pre_script", "None", validation=validate_script)
queue_complete = OptionStr("misc", "queue_complete")
queue_complete_pers = OptionBool("misc", "queue_complete_pers", False)
bandwidth_perc = OptionNumber("misc", "bandwidth_perc", 100, 0, 100)
refresh_rate = OptionNumber("misc", "refresh_rate", 0)
interface_settings = OptionStr("misc", "interface_settings")
log_level = OptionNumber("logging", "log_level", 1, -1, 2)
log_size = OptionNumber("logging", "max_log_size", 5242880)
log_backups = OptionNumber("logging", "log_backups", 5, 1, 1024)
queue_limit = OptionNumber("misc", "queue_limit", 20, 0)

configlock = OptionBool("misc", "config_lock", False)


##############################################################################
# One time trackers
##############################################################################
sched_converted = OptionBool("misc", "sched_converted", False)
notified_new_skin = OptionNumber("misc", "notified_new_skin", 0)
direct_unpack_tested = OptionBool("misc", "direct_unpack_tested", False)


##############################################################################
# Config - General
##############################################################################
version_check = OptionNumber("misc", "check_new_rel", 1)
autobrowser = OptionBool("misc", "auto_browser", True)
language = OptionStr("misc", "language", "en")
enable_https_verification = OptionBool("misc", "enable_https_verification", True)
cherryhost = OptionStr("misc", "host", DEF_HOST)
cherryport = OptionStr("misc", "port", DEF_PORT)
https_port = OptionStr("misc", "https_port")
username = OptionStr("misc", "username")
password = OptionPassword("misc", "password")
bandwidth_max = OptionStr("misc", "bandwidth_max")
cache_limit = OptionStr("misc", "cache_limit")
web_dir = OptionStr("misc", "web_dir", DEF_STDINTF)
web_color = OptionStr("misc", "web_color")
https_cert = OptionDir("misc", "https_cert", "server.cert", create=False)
https_key = OptionDir("misc", "https_key", "server.key", create=False)
https_chain = OptionDir("misc", "https_chain", create=False)
enable_https = OptionBool("misc", "enable_https", False)
# 0=local-only, 1=nzb, 2=api, 3=full_api, 4=webui, 5=webui with login for external
inet_exposure = OptionNumber("misc", "inet_exposure", 0, protect=True)
local_ranges = OptionList("misc", "local_ranges", protect=True)
api_key = OptionStr("misc", "api_key", create_api_key())
nzb_key = OptionStr("misc", "nzb_key", create_api_key())


##############################################################################
# Config - Folders
##############################################################################
umask = OptionStr("misc", "permissions", validation=validate_octal)
download_dir = OptionDir("misc", "download_dir", DEF_DOWNLOAD_DIR, create=False, validation=validate_safedir)
download_free = OptionStr("misc", "download_free")
complete_dir = OptionDir(
    "misc", "complete_dir", DEF_COMPLETE_DIR, create=False, apply_umask=True, validation=validate_notempty
)
complete_free = OptionStr("misc", "complete_free")
fulldisk_autoresume = OptionBool("misc", "fulldisk_autoresume", False)
script_dir = OptionDir("misc", "script_dir", create=True, writable=False)
nzb_backup_dir = OptionDir("misc", "nzb_backup_dir", DEF_NZBBACK_DIR)
admin_dir = OptionDir("misc", "admin_dir", DEF_ADMIN_DIR, validation=validate_safedir)
dirscan_dir = OptionDir("misc", "dirscan_dir", create=False)
dirscan_speed = OptionNumber("misc", "dirscan_speed", DEF_SCANRATE, 0, 3600)
password_file = OptionDir("misc", "password_file", "", create=False)
log_dir = OptionDir("misc", "log_dir", "logs", validation=validate_notempty)


##############################################################################
# Config - Switches
##############################################################################
max_art_tries = OptionNumber("misc", "max_art_tries", 3, 2)
load_balancing = OptionNumber("misc", "load_balancing", 2)
top_only = OptionBool("misc", "top_only", False)
sfv_check = OptionBool("misc", "sfv_check", True)
quick_check_ext_ignore = OptionList("misc", "quick_check_ext_ignore", ["nfo", "sfv", "srr"])
script_can_fail = OptionBool("misc", "script_can_fail", False)
enable_recursive = OptionBool("misc", "enable_recursive", True)
flat_unpack = OptionBool("misc", "flat_unpack", False)
par_option = OptionStr("misc", "par_option")
pre_check = OptionBool("misc", "pre_check", False)
nice = OptionStr("misc", "nice", validation=clean_nice_ionice_parameters)
win_process_prio = OptionNumber("misc", "win_process_prio", 3)
ionice = OptionStr("misc", "ionice", validation=clean_nice_ionice_parameters)
fail_hopeless_jobs = OptionBool("misc", "fail_hopeless_jobs", True)
fast_fail = OptionBool("misc", "fast_fail", True)
autodisconnect = OptionBool("misc", "auto_disconnect", True)
no_dupes = OptionNumber("misc", "no_dupes", 0)
no_series_dupes = OptionNumber("misc", "no_series_dupes", 0)
series_propercheck = OptionBool("misc", "series_propercheck", True)
pause_on_pwrar = OptionNumber("misc", "pause_on_pwrar", 1)
ignore_samples = OptionBool("misc", "ignore_samples", False)
deobfuscate_final_filenames = OptionBool("misc", "deobfuscate_final_filenames", False)
auto_sort = OptionStr("misc", "auto_sort")
direct_unpack = OptionBool("misc", "direct_unpack", False)
direct_unpack_threads = OptionNumber("misc", "direct_unpack_threads", 3, 1)
propagation_delay = OptionNumber("misc", "propagation_delay", 0)
folder_rename = OptionBool("misc", "folder_rename", True)
replace_spaces = OptionBool("misc", "replace_spaces", False)
replace_dots = OptionBool("misc", "replace_dots", False)
safe_postproc = OptionBool("misc", "safe_postproc", True)
pause_on_post_processing = OptionBool("misc", "pause_on_post_processing", False)
sanitize_safe = OptionBool("misc", "sanitize_safe", False)
cleanup_list = OptionList("misc", "cleanup_list")
unwanted_extensions = OptionList("misc", "unwanted_extensions")
action_on_unwanted_extensions = OptionNumber("misc", "action_on_unwanted_extensions", 0)
new_nzb_on_failure = OptionBool("misc", "new_nzb_on_failure", False)
history_retention = OptionStr("misc", "history_retention", "0")
enable_meta = OptionBool("misc", "enable_meta", True)

quota_size = OptionStr("misc", "quota_size")
quota_day = OptionStr("misc", "quota_day")
quota_resume = OptionBool("misc", "quota_resume", False)
quota_period = OptionStr("misc", "quota_period", "m")

rating_enable = OptionBool("misc", "rating_enable", False)
rating_host = OptionStr("misc", "rating_host")
rating_api_key = OptionStr("misc", "rating_api_key")
rating_filter_enable = OptionBool("misc", "rating_filter_enable", False)
rating_filter_abort_audio = OptionNumber("misc", "rating_filter_abort_audio", 0)
rating_filter_abort_video = OptionNumber("misc", "rating_filter_abort_video", 0)
rating_filter_abort_encrypted = OptionBool("misc", "rating_filter_abort_encrypted", False)
rating_filter_abort_encrypted_confirm = OptionBool("misc", "rating_filter_abort_encrypted_confirm", False)
rating_filter_abort_spam = OptionBool("misc", "rating_filter_abort_spam", False)
rating_filter_abort_spam_confirm = OptionBool("misc", "rating_filter_abort_spam_confirm", False)
rating_filter_abort_downvoted = OptionBool("misc", "rating_filter_abort_downvoted", False)
rating_filter_abort_keywords = OptionStr("misc", "rating_filter_abort_keywords")
rating_filter_pause_audio = OptionNumber("misc", "rating_filter_pause_audio", 0)
rating_filter_pause_video = OptionNumber("misc", "rating_filter_pause_video", 0)
rating_filter_pause_encrypted = OptionBool("misc", "rating_filter_pause_encrypted", False)
rating_filter_pause_encrypted_confirm = OptionBool("misc", "rating_filter_pause_encrypted_confirm", False)
rating_filter_pause_spam = OptionBool("misc", "rating_filter_pause_spam", False)
rating_filter_pause_spam_confirm = OptionBool("misc", "rating_filter_pause_spam_confirm", False)
rating_filter_pause_downvoted = OptionBool("misc", "rating_filter_pause_downvoted", False)
rating_filter_pause_keywords = OptionStr("misc", "rating_filter_pause_keywords")


##############################################################################
# Config - Sorting
##############################################################################
enable_tv_sorting = OptionBool("misc", "enable_tv_sorting", False)
tv_sort_string = OptionStr("misc", "tv_sort_string")
tv_sort_countries = OptionNumber("misc", "tv_sort_countries", 1)
tv_categories = OptionList("misc", "tv_categories", "")

enable_movie_sorting = OptionBool("misc", "enable_movie_sorting", False)
movie_sort_string = OptionStr("misc", "movie_sort_string")
movie_sort_extra = OptionStr("misc", "movie_sort_extra", "-cd%1", strip=False)
movie_extra_folders = OptionBool("misc", "movie_extra_folder", False)
movie_categories = OptionList("misc", "movie_categories", ["movies"])

enable_date_sorting = OptionBool("misc", "enable_date_sorting", False)
date_sort_string = OptionStr("misc", "date_sort_string")
date_categories = OptionList("misc", "date_categories", ["tv"])


##############################################################################
# Config - Scheduling and RSS
##############################################################################
schedules = OptionList("misc", "schedlines")
rss_rate = OptionNumber("misc", "rss_rate", 60, 15, 24 * 60)


##############################################################################
# Config - Specials
##############################################################################
# Bool switches
ampm = OptionBool("misc", "ampm", False)
replace_illegal = OptionBool("misc", "replace_illegal", True)
start_paused = OptionBool("misc", "start_paused", False)
enable_all_par = OptionBool("misc", "enable_all_par", False)
enable_par_cleanup = OptionBool("misc", "enable_par_cleanup", True)
enable_unrar = OptionBool("misc", "enable_unrar", True)
enable_unzip = OptionBool("misc", "enable_unzip", True)
enable_7zip = OptionBool("misc", "enable_7zip", True)
enable_filejoin = OptionBool("misc", "enable_filejoin", True)
enable_tsjoin = OptionBool("misc", "enable_tsjoin", True)
overwrite_files = OptionBool("misc", "overwrite_files", False)
ignore_unrar_dates = OptionBool("misc", "ignore_unrar_dates", False)
backup_for_duplicates = OptionBool("misc", "backup_for_duplicates", True)
empty_postproc = OptionBool("misc", "empty_postproc", False)
wait_for_dfolder = OptionBool("misc", "wait_for_dfolder", False)
rss_filenames = OptionBool("misc", "rss_filenames", False)
api_logging = OptionBool("misc", "api_logging", True)
html_login = OptionBool("misc", "html_login", True)
osx_menu = OptionBool("misc", "osx_menu", True)
osx_speed = OptionBool("misc", "osx_speed", True)
warn_dupl_jobs = OptionBool("misc", "warn_dupl_jobs", True)
helpfull_warnings = OptionBool("misc", "helpfull_warnings", True)
keep_awake = OptionBool("misc", "keep_awake", True)
win_menu = OptionBool("misc", "win_menu", True)
allow_incomplete_nzb = OptionBool("misc", "allow_incomplete_nzb", False)
enable_bonjour = OptionBool("misc", "enable_bonjour", True)
max_art_opt = OptionBool("misc", "max_art_opt", False)
ipv6_hosting = OptionBool("misc", "ipv6_hosting", False)
fixed_ports = OptionBool("misc", "fixed_ports", False)
api_warnings = OptionBool("misc", "api_warnings", True, protect=True)
disable_key = OptionBool("misc", "disable_api_key", False, protect=True)
no_penalties = OptionBool("misc", "no_penalties", False)
x_frame_options = OptionBool("misc", "x_frame_options", True)
require_modern_tls = OptionBool("misc", "require_modern_tls", False)
num_decoders = OptionNumber("misc", "num_decoders", 3)

# Text values
rss_odd_titles = OptionList("misc", "rss_odd_titles", ["nzbindex.nl/", "nzbindex.com/", "nzbclub.com/"])
req_completion_rate = OptionNumber("misc", "req_completion_rate", 100.2, 100, 200)
selftest_host = OptionStr("misc", "selftest_host", "self-test.sabnzbd.org")
movie_rename_limit = OptionStr("misc", "movie_rename_limit", "100M")
size_limit = OptionStr("misc", "size_limit", "0")
show_sysload = OptionNumber("misc", "show_sysload", 2, 0, 2)
history_limit = OptionNumber("misc", "history_limit", 10, 0)
wait_ext_drive = OptionNumber("misc", "wait_ext_drive", 5, 1, 60)
max_foldername_length = OptionNumber("misc", "max_foldername_length", DEF_FOLDER_MAX, 20, 65000)
marker_file = OptionStr("misc", "nomedia_marker")
ipv6_servers = OptionNumber("misc", "ipv6_servers", 1, 0, 2)
url_base = OptionStr("misc", "url_base", "/sabnzbd", validation=validate_strip_right_slash)
host_whitelist = OptionList("misc", "host_whitelist", validation=all_lowercase)
max_url_retries = OptionNumber("misc", "max_url_retries", 10, 1)
downloader_sleep_time = OptionNumber("misc", "downloader_sleep_time", 10, 0)
ssdp_broadcast_interval = OptionNumber("misc", "ssdp_broadcast_interval", 15, 1, 600)


##############################################################################
# Config - Notifications
##############################################################################
# [email]
email_server = OptionStr("misc", "email_server", validation=validate_server)
email_to = OptionList("misc", "email_to", validation=validate_email)
email_from = OptionStr("misc", "email_from", validation=validate_email)
email_account = OptionStr("misc", "email_account")
email_pwd = OptionPassword("misc", "email_pwd")
email_endjob = OptionNumber("misc", "email_endjob", 0, 0, 2)
email_full = OptionBool("misc", "email_full", False)
email_dir = OptionDir("misc", "email_dir", create=True)
email_rss = OptionBool("misc", "email_rss", False)
email_cats = OptionList("misc", "email_cats", ["*"])

# [ncenter]
ncenter_enable = OptionBool("ncenter", "ncenter_enable", sabnzbd.DARWIN)
ncenter_cats = OptionList("ncenter", "ncenter_cats", ["*"])
ncenter_prio_startup = OptionBool("ncenter", "ncenter_prio_startup", True)
ncenter_prio_download = OptionBool("ncenter", "ncenter_prio_download", False)
ncenter_prio_pause_resume = OptionBool("ncenter", "ncenter_prio_pause_resume", False)
ncenter_prio_pp = OptionBool("ncenter", "ncenter_prio_pp", False)
ncenter_prio_complete = OptionBool("ncenter", "ncenter_prio_complete", True)
ncenter_prio_failed = OptionBool("ncenter", "ncenter_prio_failed", True)
ncenter_prio_disk_full = OptionBool("ncenter", "ncenter_prio_disk_full", True)
ncenter_prio_new_login = OptionBool("ncenter", "ncenter_prio_new_login", False)
ncenter_prio_warning = OptionBool("ncenter", "ncenter_prio_warning", False)
ncenter_prio_error = OptionBool("ncenter", "ncenter_prio_error", False)
ncenter_prio_queue_done = OptionBool("ncenter", "ncenter_prio_queue_done", True)
ncenter_prio_other = OptionBool("ncenter", "ncenter_prio_other", True)

# [acenter]
acenter_enable = OptionBool("acenter", "acenter_enable", sabnzbd.WIN32)
acenter_cats = OptionList("acenter", "acenter_cats", ["*"])
acenter_prio_startup = OptionBool("acenter", "acenter_prio_startup", False)
acenter_prio_download = OptionBool("acenter", "acenter_prio_download", False)
acenter_prio_pause_resume = OptionBool("acenter", "acenter_prio_pause_resume", False)
acenter_prio_pp = OptionBool("acenter", "acenter_prio_pp", False)
acenter_prio_complete = OptionBool("acenter", "acenter_prio_complete", True)
acenter_prio_failed = OptionBool("acenter", "acenter_prio_failed", True)
acenter_prio_disk_full = OptionBool("acenter", "acenter_prio_disk_full", True)
acenter_prio_new_login = OptionBool("acenter", "acenter_prio_new_login", False)
acenter_prio_warning = OptionBool("acenter", "acenter_prio_warning", False)
acenter_prio_error = OptionBool("acenter", "acenter_prio_error", False)
acenter_prio_queue_done = OptionBool("acenter", "acenter_prio_queue_done", True)
acenter_prio_other = OptionBool("acenter", "acenter_prio_other", True)

# [ntfosd]
ntfosd_enable = OptionBool("ntfosd", "ntfosd_enable", not sabnzbd.WIN32 and not sabnzbd.DARWIN)
ntfosd_cats = OptionList("ntfosd", "ntfosd_cats", ["*"])
ntfosd_prio_startup = OptionBool("ntfosd", "ntfosd_prio_startup", True)
ntfosd_prio_download = OptionBool("ntfosd", "ntfosd_prio_download", False)
ntfosd_prio_pause_resume = OptionBool("ntfosd", "ntfosd_prio_pause_resume", False)
ntfosd_prio_pp = OptionBool("ntfosd", "ntfosd_prio_pp", False)
ntfosd_prio_complete = OptionBool("ntfosd", "ntfosd_prio_complete", True)
ntfosd_prio_failed = OptionBool("ntfosd", "ntfosd_prio_failed", True)
ntfosd_prio_disk_full = OptionBool("ntfosd", "ntfosd_prio_disk_full", True)
ntfosd_prio_new_login = OptionBool("ntfosd", "ntfosd_prio_new_login", False)
ntfosd_prio_warning = OptionBool("ntfosd", "ntfosd_prio_warning", False)
ntfosd_prio_error = OptionBool("ntfosd", "ntfosd_prio_error", False)
ntfosd_prio_queue_done = OptionBool("ntfosd", "ntfosd_prio_queue_done", True)
ntfosd_prio_other = OptionBool("ntfosd", "ntfosd_prio_other", True)

# [prowl]
prowl_enable = OptionBool("prowl", "prowl_enable", False)
prowl_cats = OptionList("prowl", "prowl_cats", ["*"])
prowl_apikey = OptionStr("prowl", "prowl_apikey")
prowl_prio_startup = OptionNumber("prowl", "prowl_prio_startup", -3)
prowl_prio_download = OptionNumber("prowl", "prowl_prio_download", -3)
prowl_prio_pause_resume = OptionNumber("prowl", "prowl_prio_pause_resume", -3)
prowl_prio_pp = OptionNumber("prowl", "prowl_prio_pp", -3)
prowl_prio_complete = OptionNumber("prowl", "prowl_prio_complete", 0)
prowl_prio_failed = OptionNumber("prowl", "prowl_prio_failed", 1)
prowl_prio_disk_full = OptionNumber("prowl", "prowl_prio_disk_full", 1)
prowl_prio_new_login = OptionNumber("prowl", "prowl_prio_new_login", -3)
prowl_prio_warning = OptionNumber("prowl", "prowl_prio_warning", -3)
prowl_prio_error = OptionNumber("prowl", "prowl_prio_error", -3)
prowl_prio_queue_done = OptionNumber("prowl", "prowl_prio_queue_done", 0)
prowl_prio_other = OptionNumber("prowl", "prowl_prio_other", 0)

# [pushover]
pushover_token = OptionStr("pushover", "pushover_token")
pushover_userkey = OptionStr("pushover", "pushover_userkey")
pushover_device = OptionStr("pushover", "pushover_device")
pushover_emergency_expire = OptionNumber("pushover", "pushover_emergency_expire", 3600)
pushover_emergency_retry = OptionNumber("pushover", "pushover_emergency_retry", 60)
pushover_enable = OptionBool("pushover", "pushover_enable")
pushover_cats = OptionList("pushover", "pushover_cats", ["*"])
pushover_prio_startup = OptionNumber("pushover", "pushover_prio_startup", -3)
pushover_prio_download = OptionNumber("pushover", "pushover_prio_download", -2)
pushover_prio_pause_resume = OptionNumber("pushover", "pushover_prio_pause_resume", -2)
pushover_prio_pp = OptionNumber("pushover", "pushover_prio_pp", -3)
pushover_prio_complete = OptionNumber("pushover", "pushover_prio_complete", -1)
pushover_prio_failed = OptionNumber("pushover", "pushover_prio_failed", -1)
pushover_prio_disk_full = OptionNumber("pushover", "pushover_prio_disk_full", 1)
pushover_prio_new_login = OptionNumber("pushover", "pushover_prio_new_login", -3)
pushover_prio_warning = OptionNumber("pushover", "pushover_prio_warning", 1)
pushover_prio_error = OptionNumber("pushover", "pushover_prio_error", 1)
pushover_prio_queue_done = OptionNumber("pushover", "pushover_prio_queue_done", -1)
pushover_prio_other = OptionNumber("pushover", "pushover_prio_other", -1)

# [pushbullet]
pushbullet_enable = OptionBool("pushbullet", "pushbullet_enable")
pushbullet_cats = OptionList("pushbullet", "pushbullet_cats", ["*"])
pushbullet_apikey = OptionStr("pushbullet", "pushbullet_apikey")
pushbullet_device = OptionStr("pushbullet", "pushbullet_device")
pushbullet_prio_startup = OptionBool("pushbullet", "pushbullet_prio_startup", False)
pushbullet_prio_download = OptionBool("pushbullet", "pushbullet_prio_download", False)
pushbullet_prio_pause_resume = OptionBool("pushbullet", "pushbullet_prio_pause_resume", False)
pushbullet_prio_pp = OptionBool("pushbullet", "pushbullet_prio_pp", False)
pushbullet_prio_complete = OptionBool("pushbullet", "pushbullet_prio_complete", True)
pushbullet_prio_failed = OptionBool("pushbullet", "pushbullet_prio_failed", True)
pushbullet_prio_disk_full = OptionBool("pushbullet", "pushbullet_prio_disk_full", True)
pushbullet_prio_new_login = OptionBool("pushbullet", "pushbullet_prio_new_login", False)
pushbullet_prio_warning = OptionBool("pushbullet", "pushbullet_prio_warning", False)
pushbullet_prio_error = OptionBool("pushbullet", "pushbullet_prio_error", False)
pushbullet_prio_queue_done = OptionBool("pushbullet", "pushbullet_prio_queue_done", False)
pushbullet_prio_other = OptionBool("pushbullet", "pushbullet_prio_other", True)

# [nscript]
nscript_enable = OptionBool("nscript", "nscript_enable")
nscript_cats = OptionList("nscript", "nscript_cats", ["*"])
nscript_script = OptionStr("nscript", "nscript_script", validation=validate_script)
nscript_parameters = OptionStr("nscript", "nscript_parameters")
nscript_prio_startup = OptionBool("nscript", "nscript_prio_startup", True)
nscript_prio_download = OptionBool("nscript", "nscript_prio_download", False)
nscript_prio_pause_resume = OptionBool("nscript", "nscript_prio_pause_resume", False)
nscript_prio_pp = OptionBool("nscript", "nscript_prio_pp", False)
nscript_prio_complete = OptionBool("nscript", "nscript_prio_complete", True)
nscript_prio_failed = OptionBool("nscript", "nscript_prio_failed", True)
nscript_prio_disk_full = OptionBool("nscript", "nscript_prio_disk_full", True)
nscript_prio_new_login = OptionBool("nscript", "nscript_prio_new_login", False)
nscript_prio_warning = OptionBool("nscript", "nscript_prio_warning", False)
nscript_prio_error = OptionBool("nscript", "nscript_prio_error", False)
nscript_prio_queue_done = OptionBool("nscript", "nscript_prio_queue_done", True)
nscript_prio_other = OptionBool("nscript", "nscript_prio_other", True)


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
