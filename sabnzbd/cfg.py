#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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

import logging
import os
import re
import argparse
import socket
import ipaddress
from typing import List, Tuple, Union

import sabnzbd
from sabnzbd.config import (
    OptionBool,
    OptionNumber,
    OptionPassword,
    OptionDir,
    OptionStr,
    OptionList,
    create_api_key,
    get_servers,
    save_config,
)
from sabnzbd.constants import (
    DEF_HOST,
    DEF_PORT,
    DEF_STD_WEB_DIR,
    DEF_ADMIN_DIR,
    DEF_DOWNLOAD_DIR,
    DEF_NZBBACK_DIR,
    DEF_SCANRATE,
    DEF_COMPLETE_DIR,
    DEF_FOLDER_MAX,
    DEF_STD_WEB_COLOR,
    DEF_HTTPS_CERT_FILE,
    DEF_HTTPS_KEY_FILE,
)
from sabnzbd.filesystem import same_directory, real_path, is_valid_script, is_network_path

# Validators currently only are made for string/list-of-strings
# and return those on success or an error message.
ValidateResult = Union[Tuple[None, str], Tuple[None, List[str]], Tuple[str, None]]


##############################################################################
# Default Validation handlers
##############################################################################
class ErrorCatchingArgumentParser(argparse.ArgumentParser):
    def error(self, status=0, message=None):
        # Need to override so it doesn't raise SystemExit
        if status:
            raise ValueError


def clean_nice_ionice_parameters(value: str) -> ValidateResult:
    """Verify that the passed parameters are not exploits"""
    if value:
        parser = ErrorCatchingArgumentParser(add_help=False)

        # Nice parameters
        parser.add_argument("-n", "--adjustment", type=int)

        # Ionice parameters, not supporting -p
        parser.add_argument("--classdata", type=int)
        parser.add_argument("-c", "--class", type=int)
        parser.add_argument("-t", "--ignore", action="store_true")

        try:
            parser.parse_args(value.split())
        except ValueError:
            # Also log at start-up if invalid parameter was set in the ini
            msg = "%s: %s" % (T("Incorrect parameter"), value)
            logging.error(msg)
            return msg, None
    return None, value


def supported_unrar_parameters(value: str) -> ValidateResult:
    """Verify the user-set extra parameters are valid and supported"""
    if value:
        parser = ErrorCatchingArgumentParser(add_help=False)

        # Large memory pages
        parser.add_argument("-mlp", action="store_true")
        if sabnzbd.WINDOWS:
            # Mark of the web propagation: -om[-|1][=list]
            parser.add_argument("-om", "-om1", "-om-", nargs="?", type=str)
            # Priority and sleep time: -ri<p>[:<s>] (p: 0-15, s: 0-1000)
            parser.add_argument(*("-ri" + str(p) for p in range(16)), action="store_true")

        try:
            # Make the regexp and argument parsing case-insensitive, as unrar seems to do that as well, and
            # strip the sleep time from valid forms of -ri to avoid handling ~16k combinations of <p> and <s>
            parser.parse_args(
                re.sub(r"(?i)(^|\s)(-ri(?:1[0-5]|[0-9]))(?::(?:1000|[1-9][0-9]{,2}|0))?($|\s)", r"\1\2\3", value)
                .lower()
                .split()
            )
        except ValueError:
            # Also log at start-up if invalid parameter was set in the ini
            msg = "%s: %s" % (T("Incorrect parameter"), value)
            logging.error(msg)
            return msg, None
    return None, value


def all_lowercase(value: Union[str, List]) -> Tuple[None, Union[str, List]]:
    """Lowercase and strip everything!"""
    if isinstance(value, list):
        return None, [item.lower().strip() for item in value]
    return None, value.lower().strip()


def lower_case_ext(value: Union[str, List]) -> Tuple[None, Union[str, List]]:
    """Generate lower case extension(s), without dot"""
    if isinstance(value, list):
        return None, [item.lower().strip(" .") for item in value]
    return None, value.lower().strip(" .")


def validate_single_tag(value: List[str]) -> Tuple[None, List[str]]:
    """Don't split single indexer tags like "TV > HD"
    into ['TV', '>', 'HD']
    """
    if len(value) == 3:
        if value[1] == ">":
            return None, [" ".join(value)]
    return None, value


def validate_url_base(value: str) -> Tuple[None, str]:
    """Strips the right slash and adds starting slash, if not present"""
    if value and isinstance(value, str):
        if not value.startswith("/"):
            value = "/" + value
        return None, value.rstrip("/")
    return None, value


RE_VAL = re.compile(r"[^@ ]+@[^.@ ]+\.[^.@ ]")


def validate_email(value: Union[List, str]) -> ValidateResult:
    if email_endjob() or email_full() or email_rss():
        if isinstance(value, list):
            values = value
        else:
            values = [value]
        for addr in values:
            if not (addr and RE_VAL.match(addr)):
                return T("%s is not a valid email address") % addr, None
    return None, value


def validate_server(value: str) -> ValidateResult:
    """Check if server non-empty"""
    if value == "" and (email_endjob() or email_full() or email_rss()):
        return T("Server address required"), None
    else:
        return None, value


def validate_host(value: str) -> ValidateResult:
    """Check if host is valid: an IP address, or a name/FQDN that resolves to an IP address"""
    # easy: value is a plain IPv4 or IPv6 address:
    try:
        ipaddress.ip_address(value)
        # valid host, so return it
        return None, value
    except Exception:
        pass

    # we don't want a plain number. As socket.getaddrinfo("100", ...) allows that, we have to pre-check
    try:
        int(value)
        # plain int as input, which is not allowed
        return T("Invalid server address."), None
    except Exception:
        pass

    # not a plain IPv4 nor IPv6 address, so let's check if it's a name that resolves to IPv4
    try:
        socket.getaddrinfo(value, None, socket.AF_INET)
        # all good
        logging.debug("Valid host name")
        return None, value
    except Exception:
        pass

    # ... and if not: does it resolve to IPv6 ... ?
    try:
        socket.getaddrinfo(value, None, socket.AF_INET6)
        # all good
        logging.debug("Valid host name")
        return None, value
    except Exception:
        logging.debug("No valid host name")
        pass

    # if we get here, it is not valid host, so return None
    return T("Invalid server address."), None


def validate_script(value: str) -> ValidateResult:
    """Check if value is a valid script"""
    if not sabnzbd.__INITIALIZED__ or (value and is_valid_script(value)):
        return None, value
    elif sabnzbd.misc.is_none(value):
        return None, "None"
    return T("%s is not a valid script") % value, None


def validate_permissions(value: str) -> ValidateResult:
    """Check the permissions for correct input"""
    # Octal verification
    if not value:
        return None, value
    try:
        oct_value = int(value, 8)
        # Block setting it to 0
        if not oct_value:
            raise ValueError
    except ValueError:
        return T("%s is not a correct octal value") % value, None

    # Check if we at least have user-permissions
    if oct_value < int("700", 8):
        sabnzbd.misc.helpful_warning(
            T("Permissions setting of %s might deny SABnzbd access to the files and folders it creates."), value
        )
    return None, value


def validate_safedir(root: str, value: str, default: str) -> ValidateResult:
    """Allow only when queues are empty and not a network-path"""
    if not sabnzbd.__INITIALIZED__ or (sabnzbd.PostProcessor.empty() and sabnzbd.NzbQueue.is_empty()):
        # We allow it, but send a warning
        if is_network_path(real_path(root, value)):
            sabnzbd.misc.helpful_warning(T('Network path "%s" should not be used here'), value)
        return validate_default_if_empty(root, value, default)
    else:
        return T("Queue not empty, cannot change folder."), None


def validate_download_vs_complete_dir(root: str, value: str, default: str):
    """Make sure download_dir and complete_dir are not identical
    or that download_dir is not a subfolder of complete_dir"""
    # Check what new value we are trying to set
    if default == DEF_COMPLETE_DIR:
        check_download_dir = download_dir.get_path()
        check_complete_dir = real_path(root, value)
    elif default == DEF_DOWNLOAD_DIR:
        check_download_dir = real_path(root, value)
        check_complete_dir = complete_dir.get_path()
    else:
        raise ValueError("Validator can only be used for download_dir/complete_dir")

    if same_directory(check_download_dir, check_complete_dir):
        return (
            T("The Completed Download Folder cannot be the same or a subfolder of the Temporary Download Folder"),
            None,
        )
    elif default == DEF_COMPLETE_DIR:
        # The complete_dir allows UNC
        return validate_default_if_empty(root, value, default)
    else:
        return validate_safedir(root, value, default)


def validate_scriptdir_not_appdir(root: str, value: str, default: str) -> Tuple[None, str]:
    """Warn users to not use the Program Files folder for their scripts"""
    # Need to add separator so /mnt/sabnzbd and /mnt/sabnzbd-data are not detected as equal
    if value and same_directory(sabnzbd.DIR_PROG, os.path.join(root, value)):
        # Warn, but do not block
        sabnzbd.misc.helpful_warning(
            T(
                "Do not use a folder in the application folder as your Scripts Folder, it might be emptied during updates."
            )
        )
    return None, value


def validate_default_if_empty(root: str, value: str, default: str) -> Tuple[None, str]:
    """If value is empty, return default"""
    if value:
        return None, value
    else:
        return None, default


##############################################################################
# Special settings
##############################################################################

# Increase everytime we do a configuration conversion
config_conversion_version = OptionNumber("misc", "config_conversion_version", default_val=0)

# This should be here so it's initialized first when the config is read
helpful_warnings = OptionBool("misc", "helpful_warnings", True)

queue_complete = OptionStr("misc", "queue_complete")
queue_complete_pers = OptionBool("misc", "queue_complete_pers", False)
bandwidth_perc = OptionNumber("misc", "bandwidth_perc", 100, minval=0, maxval=100)
refresh_rate = OptionNumber("misc", "refresh_rate", 0)
interface_settings = OptionStr("misc", "interface_settings")
log_level = OptionNumber("logging", "log_level", 1, minval=-1, maxval=2)
log_size = OptionNumber("logging", "max_log_size", 5242880)
log_backups = OptionNumber("logging", "log_backups", 5, minval=1, maxval=1024)
queue_limit = OptionNumber("misc", "queue_limit", 20, minval=0)

configlock = OptionBool("misc", "config_lock", False)


##############################################################################
# One time trackers
##############################################################################
fixed_ports = OptionBool("misc", "fixed_ports", False, public=False)
notified_new_skin = OptionNumber("misc", "notified_new_skin", 0)
direct_unpack_tested = OptionBool("misc", "direct_unpack_tested", False, public=False)
sorters_converted = OptionBool("misc", "sorters_converted", False, public=False)


##############################################################################
# Config - General
##############################################################################
version_check = OptionNumber("misc", "check_new_rel", 1)
autobrowser = OptionBool("misc", "auto_browser", True)
language = OptionStr("misc", "language", "en")
enable_https_verification = OptionBool("misc", "enable_https_verification", True)
web_host = OptionStr("misc", "host", DEF_HOST, validation=validate_host)
web_port = OptionStr("misc", "port", DEF_PORT)
https_port = OptionStr("misc", "https_port")
username = OptionStr("misc", "username")
password = OptionPassword("misc", "password")
bandwidth_max = OptionStr("misc", "bandwidth_max")
cache_limit = OptionStr("misc", "cache_limit")
web_dir = OptionStr("misc", "web_dir", DEF_STD_WEB_DIR)
web_color = OptionStr("misc", "web_color", DEF_STD_WEB_COLOR)
https_cert = OptionDir("misc", "https_cert", DEF_HTTPS_CERT_FILE, create=False)
https_key = OptionDir("misc", "https_key", DEF_HTTPS_KEY_FILE, create=False)
https_chain = OptionDir("misc", "https_chain", create=False)
enable_https = OptionBool("misc", "enable_https", False)
# 0=local-only, 1=nzb, 2=api, 3=full_api, 4=webui, 5=webui with login for external
inet_exposure = OptionNumber("misc", "inet_exposure", 0, protect=True)
api_key = OptionStr("misc", "api_key", create_api_key())
nzb_key = OptionStr("misc", "nzb_key", create_api_key())
socks5_proxy_url = OptionStr("misc", "socks5_proxy_url")

##############################################################################
# Config - Folders
##############################################################################
permissions = OptionStr("misc", "permissions", validation=validate_permissions)
download_dir = OptionDir(
    "misc",
    "download_dir",
    DEF_DOWNLOAD_DIR,
    create=False,  # Flag is modified and directory is created during initialize!
    apply_permissions=True,
    validation=validate_download_vs_complete_dir,
)
download_free = OptionStr("misc", "download_free")
complete_dir = OptionDir(
    "misc",
    "complete_dir",
    DEF_COMPLETE_DIR,
    create=False,  # Flag is modified and directory is created during initialize!
    apply_permissions=True,
    validation=validate_download_vs_complete_dir,
)
complete_free = OptionStr("misc", "complete_free")
fulldisk_autoresume = OptionBool("misc", "fulldisk_autoresume", False)
script_dir = OptionDir("misc", "script_dir", writable=False, validation=validate_scriptdir_not_appdir)
nzb_backup_dir = OptionDir("misc", "nzb_backup_dir", DEF_NZBBACK_DIR)
admin_dir = OptionDir("misc", "admin_dir", DEF_ADMIN_DIR, validation=validate_safedir)
backup_dir = OptionDir("misc", "backup_dir")
dirscan_dir = OptionDir("misc", "dirscan_dir", writable=False)
dirscan_speed = OptionNumber("misc", "dirscan_speed", DEF_SCANRATE, minval=0, maxval=3600)
password_file = OptionDir("misc", "password_file", "", create=False)
log_dir = OptionDir("misc", "log_dir", "logs", validation=validate_default_if_empty)


##############################################################################
# Config - Switches
##############################################################################
max_art_tries = OptionNumber("misc", "max_art_tries", 3, minval=2)
top_only = OptionBool("misc", "top_only", False)
sfv_check = OptionBool("misc", "sfv_check", True)
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
pre_script = OptionStr("misc", "pre_script", "None", validation=validate_script)
end_queue_script = OptionStr("misc", "end_queue_script", "None", validation=validate_script)
no_dupes = OptionNumber("misc", "no_dupes", 0)
no_series_dupes = OptionNumber("misc", "no_series_dupes", 0)  # Kept for converting to no_smart_dupes
no_smart_dupes = OptionNumber("misc", "no_smart_dupes", 0)
dupes_propercheck = OptionBool("misc", "dupes_propercheck", True)
pause_on_pwrar = OptionNumber("misc", "pause_on_pwrar", 1)
ignore_samples = OptionBool("misc", "ignore_samples", False)
deobfuscate_final_filenames = OptionBool("misc", "deobfuscate_final_filenames", True)
auto_sort = OptionStr("misc", "auto_sort")
direct_unpack = OptionBool("misc", "direct_unpack", False)
propagation_delay = OptionNumber("misc", "propagation_delay", 0, minval=0)
folder_rename = OptionBool("misc", "folder_rename", True)
replace_spaces = OptionBool("misc", "replace_spaces", False)
replace_underscores = OptionBool("misc", "replace_underscores", False)
replace_dots = OptionBool("misc", "replace_dots", False)
safe_postproc = OptionBool("misc", "safe_postproc", True)
pause_on_post_processing = OptionBool("misc", "pause_on_post_processing", False)
enable_all_par = OptionBool("misc", "enable_all_par", False)
sanitize_safe = OptionBool("misc", "sanitize_safe", False)
cleanup_list = OptionList("misc", "cleanup_list", validation=lower_case_ext)
unwanted_extensions = OptionList("misc", "unwanted_extensions", validation=lower_case_ext)
action_on_unwanted_extensions = OptionNumber("misc", "action_on_unwanted_extensions", 0)
unwanted_extensions_mode = OptionNumber("misc", "unwanted_extensions_mode", 0)
new_nzb_on_failure = OptionBool("misc", "new_nzb_on_failure", False)
history_retention = OptionStr("misc", "history_retention", "0")  # Kept for converting to split option
history_retention_option = OptionStr("misc", "history_retention_option", "all")
history_retention_number = OptionNumber("misc", "history_retention_number", minval=1)

quota_size = OptionStr("misc", "quota_size")
quota_day = OptionStr("misc", "quota_day")
quota_resume = OptionBool("misc", "quota_resume", False)
quota_period = OptionStr("misc", "quota_period", "m")

##############################################################################
# Config - Sorting (OLD SORTER)
##############################################################################
enable_tv_sorting = OptionBool("misc", "enable_tv_sorting", False, public=False)
tv_sort_string = OptionStr("misc", "tv_sort_string", public=False)
tv_categories = OptionList("misc", "tv_categories", ["tv"], public=False)

enable_movie_sorting = OptionBool("misc", "enable_movie_sorting", False, public=False)
movie_sort_string = OptionStr("misc", "movie_sort_string", public=False)
movie_sort_extra = OptionStr("misc", "movie_sort_extra", "-cd%1", strip=False, public=False)
movie_categories = OptionList("misc", "movie_categories", ["movies"], public=False)

enable_date_sorting = OptionBool("misc", "enable_date_sorting", False, public=False)
date_sort_string = OptionStr("misc", "date_sort_string", public=False)
date_categories = OptionList("misc", "date_categories", ["tv"], public=False)

##############################################################################
# Config - Scheduling and RSS
##############################################################################
schedules = OptionList("misc", "schedlines")
rss_rate = OptionNumber("misc", "rss_rate", 60, minval=15, maxval=24 * 60)

##############################################################################
# Config - Specials
##############################################################################
# Bool switches
ampm = OptionBool("misc", "ampm", False)
start_paused = OptionBool("misc", "start_paused", False)
preserve_paused_state = OptionBool("misc", "preserve_paused_state", False)
enable_par_cleanup = OptionBool("misc", "enable_par_cleanup", True)
process_unpacked_par2 = OptionBool("misc", "process_unpacked_par2", True)
enable_unrar = OptionBool("misc", "enable_unrar", True)
enable_7zip = OptionBool("misc", "enable_7zip", True)
enable_filejoin = OptionBool("misc", "enable_filejoin", True)
enable_tsjoin = OptionBool("misc", "enable_tsjoin", True)
overwrite_files = OptionBool("misc", "overwrite_files", False)
ignore_unrar_dates = OptionBool("misc", "ignore_unrar_dates", False)
backup_for_duplicates = OptionBool("misc", "backup_for_duplicates", False)
empty_postproc = OptionBool("misc", "empty_postproc", False)
wait_for_dfolder = OptionBool("misc", "wait_for_dfolder", False)
rss_filenames = OptionBool("misc", "rss_filenames", False)
api_logging = OptionBool("misc", "api_logging", True)
html_login = OptionBool("misc", "html_login", True)
disable_archive = OptionBool("misc", "disable_archive", False)
warn_dupl_jobs = OptionBool("misc", "warn_dupl_jobs", False)

keep_awake = OptionBool("misc", "keep_awake", True)
tray_icon = OptionBool("misc", "tray_icon", True)
allow_incomplete_nzb = OptionBool("misc", "allow_incomplete_nzb", False)
enable_broadcast = OptionBool("misc", "enable_broadcast", True)
ipv6_hosting = OptionBool("misc", "ipv6_hosting", False)
ipv6_staging = OptionBool("misc", "ipv6_staging", False)
api_warnings = OptionBool("misc", "api_warnings", True, protect=True)
no_penalties = OptionBool("misc", "no_penalties", False)
x_frame_options = OptionBool("misc", "x_frame_options", True)
allow_old_ssl_tls = OptionBool("misc", "allow_old_ssl_tls", False)
enable_season_sorting = OptionBool("misc", "enable_season_sorting", True)
verify_xff_header = OptionBool("misc", "verify_xff_header", False)

# Text values
rss_odd_titles = OptionList("misc", "rss_odd_titles", ["nzbindex.nl/", "nzbindex.com/", "nzbclub.com/"])
quick_check_ext_ignore = OptionList("misc", "quick_check_ext_ignore", ["nfo", "sfv", "srr"], validation=lower_case_ext)
req_completion_rate = OptionNumber("misc", "req_completion_rate", 100.2, minval=100, maxval=200)
selftest_host = OptionStr("misc", "selftest_host", "self-test.sabnzbd.org")
movie_rename_limit = OptionStr("misc", "movie_rename_limit", "100M")
episode_rename_limit = OptionStr("misc", "episode_rename_limit", "20M")
size_limit = OptionStr("misc", "size_limit", "0")
direct_unpack_threads = OptionNumber("misc", "direct_unpack_threads", 3, minval=1)
history_limit = OptionNumber("misc", "history_limit", 10, minval=0)
wait_ext_drive = OptionNumber("misc", "wait_ext_drive", 5, minval=1, maxval=60)
max_foldername_length = OptionNumber("misc", "max_foldername_length", DEF_FOLDER_MAX, minval=20, maxval=65000)
marker_file = OptionStr("misc", "nomedia_marker")
ipv6_servers = OptionBool("misc", "ipv6_servers", True)
url_base = OptionStr("misc", "url_base", "", validation=validate_url_base)
host_whitelist = OptionList("misc", "host_whitelist", validation=all_lowercase)
local_ranges = OptionList("misc", "local_ranges", protect=True)
max_url_retries = OptionNumber("misc", "max_url_retries", 10, minval=1)
downloader_sleep_time = OptionNumber("misc", "downloader_sleep_time", 10, minval=0)
receive_threads = OptionNumber("misc", "receive_threads", 2, minval=1)
switchinterval = OptionNumber("misc", "switchinterval", 0.005, minval=0.001)
ssdp_broadcast_interval = OptionNumber("misc", "ssdp_broadcast_interval", 15, minval=1, maxval=600)
ext_rename_ignore = OptionList("misc", "ext_rename_ignore", validation=lower_case_ext)
unrar_parameters = OptionStr("misc", "unrar_parameters", validation=supported_unrar_parameters)


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
email_dir = OptionDir("misc", "email_dir")
email_rss = OptionBool("misc", "email_rss", False)
email_cats = OptionList("misc", "email_cats", ["*"])

# [ncenter]
ncenter_enable = OptionBool("ncenter", "ncenter_enable", sabnzbd.MACOS)
ncenter_cats = OptionList("ncenter", "ncenter_cats", ["*"])
ncenter_prio_startup = OptionBool("ncenter", "ncenter_prio_startup", False)
ncenter_prio_download = OptionBool("ncenter", "ncenter_prio_download", False)
ncenter_prio_pause_resume = OptionBool("ncenter", "ncenter_prio_pause_resume", False)
ncenter_prio_pp = OptionBool("ncenter", "ncenter_prio_pp", False)
ncenter_prio_complete = OptionBool("ncenter", "ncenter_prio_complete", True)
ncenter_prio_failed = OptionBool("ncenter", "ncenter_prio_failed", True)
ncenter_prio_disk_full = OptionBool("ncenter", "ncenter_prio_disk_full", True)
ncenter_prio_new_login = OptionBool("ncenter", "ncenter_prio_new_login", False)
ncenter_prio_warning = OptionBool("ncenter", "ncenter_prio_warning", False)
ncenter_prio_error = OptionBool("ncenter", "ncenter_prio_error", False)
ncenter_prio_queue_done = OptionBool("ncenter", "ncenter_prio_queue_done", False)
ncenter_prio_other = OptionBool("ncenter", "ncenter_prio_other", True)

# [acenter]
acenter_enable = OptionBool("acenter", "acenter_enable", sabnzbd.WINDOWS)
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
acenter_prio_queue_done = OptionBool("acenter", "acenter_prio_queue_done", False)
acenter_prio_other = OptionBool("acenter", "acenter_prio_other", True)

# [ntfosd]
ntfosd_enable = OptionBool("ntfosd", "ntfosd_enable", not sabnzbd.WINDOWS and not sabnzbd.MACOS)
ntfosd_cats = OptionList("ntfosd", "ntfosd_cats", ["*"])
ntfosd_prio_startup = OptionBool("ntfosd", "ntfosd_prio_startup", False)
ntfosd_prio_download = OptionBool("ntfosd", "ntfosd_prio_download", False)
ntfosd_prio_pause_resume = OptionBool("ntfosd", "ntfosd_prio_pause_resume", False)
ntfosd_prio_pp = OptionBool("ntfosd", "ntfosd_prio_pp", False)
ntfosd_prio_complete = OptionBool("ntfosd", "ntfosd_prio_complete", True)
ntfosd_prio_failed = OptionBool("ntfosd", "ntfosd_prio_failed", True)
ntfosd_prio_disk_full = OptionBool("ntfosd", "ntfosd_prio_disk_full", True)
ntfosd_prio_new_login = OptionBool("ntfosd", "ntfosd_prio_new_login", False)
ntfosd_prio_warning = OptionBool("ntfosd", "ntfosd_prio_warning", False)
ntfosd_prio_error = OptionBool("ntfosd", "ntfosd_prio_error", False)
ntfosd_prio_queue_done = OptionBool("ntfosd", "ntfosd_prio_queue_done", False)
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
prowl_prio_queue_done = OptionNumber("prowl", "prowl_prio_queue_done", -3)
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
pushover_prio_queue_done = OptionNumber("pushover", "pushover_prio_queue_done", -3)
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

# [apprise]
apprise_enable = OptionBool("apprise", "apprise_enable")
apprise_cats = OptionList("apprise", "apprise_cats", ["*"])
apprise_urls = OptionStr("apprise", "apprise_urls")
apprise_target_startup = OptionStr("apprise", "apprise_target_startup")
apprise_target_startup_enable = OptionBool("apprise", "apprise_target_startup_enable", False)
apprise_target_download = OptionStr("apprise", "apprise_target_download")
apprise_target_download_enable = OptionBool("apprise", "apprise_target_download_enable", False)
apprise_target_pause_resume = OptionStr("apprise", "apprise_target_pause_resume")
apprise_target_pause_resume_enable = OptionBool("apprise", "apprise_target_pause_resume_enable", False)
apprise_target_pp = OptionStr("apprise", "apprise_target_pp")
apprise_target_pp_enable = OptionBool("apprise", "apprise_target_pp_enable", False)
apprise_target_complete = OptionStr("apprise", "apprise_target_complete")
apprise_target_complete_enable = OptionBool("apprise", "apprise_target_complete_enable", True)
apprise_target_failed = OptionStr("apprise", "apprise_target_failed")
apprise_target_failed_enable = OptionBool("apprise", "apprise_target_failed_enable", True)
apprise_target_disk_full = OptionStr("apprise", "apprise_target_disk_full")
apprise_target_disk_full_enable = OptionBool("apprise", "apprise_target_disk_full_enable", False)
apprise_target_new_login = OptionStr("apprise", "apprise_target_new_login")
apprise_target_new_login_enable = OptionBool("apprise", "apprise_target_new_login_enable", True)
apprise_target_warning = OptionStr("apprise", "apprise_target_warning")
apprise_target_warning_enable = OptionBool("apprise", "apprise_target_warning_enable", False)
apprise_target_error = OptionStr("apprise", "apprise_target_error")
apprise_target_error_enable = OptionBool("apprise", "apprise_target_error_enable", False)
apprise_target_queue_done = OptionStr("apprise", "apprise_target_queue_done")
apprise_target_query_done_enable = OptionBool("apprise", "apprise_target_queue_done_enable", False)
apprise_target_other = OptionStr("apprise", "apprise_target_other")
apprise_target_other_enable = OptionBool("apprise", "apprise_target_other_enable", True)

# [nscript]
nscript_enable = OptionBool("nscript", "nscript_enable")
nscript_cats = OptionList("nscript", "nscript_cats", ["*"])
nscript_script = OptionStr("nscript", "nscript_script", validation=validate_script)
nscript_parameters = OptionStr("nscript", "nscript_parameters")
nscript_prio_startup = OptionBool("nscript", "nscript_prio_startup", False)
nscript_prio_download = OptionBool("nscript", "nscript_prio_download", False)
nscript_prio_pause_resume = OptionBool("nscript", "nscript_prio_pause_resume", False)
nscript_prio_pp = OptionBool("nscript", "nscript_prio_pp", False)
nscript_prio_complete = OptionBool("nscript", "nscript_prio_complete", True)
nscript_prio_failed = OptionBool("nscript", "nscript_prio_failed", True)
nscript_prio_disk_full = OptionBool("nscript", "nscript_prio_disk_full", True)
nscript_prio_new_login = OptionBool("nscript", "nscript_prio_new_login", False)
nscript_prio_warning = OptionBool("nscript", "nscript_prio_warning", False)
nscript_prio_error = OptionBool("nscript", "nscript_prio_error", False)
nscript_prio_queue_done = OptionBool("nscript", "nscript_prio_queue_done", False)
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
    backup_dir.set_root(home)
    dirscan_dir.set_root(home)
    log_dir.set_root(lcldata)
    password_file.set_root(home)


def set_root_folders2():
    https_cert.set_root(admin_dir.get_path())
    https_key.set_root(admin_dir.get_path())
    https_chain.set_root(admin_dir.get_path())


##############################################################################
# Callbacks for settings
##############################################################################
def new_limit():
    """Callback for article cache changes"""
    if sabnzbd.__INITIALIZED__:
        # Only update after full startup
        sabnzbd.ArticleCache.new_limit(cache_limit.get_int())


def guard_restart():
    """Callback for config options requiring a restart"""
    sabnzbd.RESTART_REQ = True


def guard_top_only():
    """Callback for change of top_only option"""
    sabnzbd.NzbQueue.set_top_only(top_only())


def guard_pause_on_pp():
    """Callback for change of pause-download-on-pp"""
    if pause_on_post_processing():
        pass  # Not safe to idle downloader, because we don't know
        # if post-processing is active now
    else:
        sabnzbd.Downloader.resume_from_postproc()


def guard_quota_size():
    """Callback for change of quota_size"""
    sabnzbd.BPSMeter.change_quota()


def guard_quota_dp():
    """Callback for change of quota_day or quota_period"""
    sabnzbd.Scheduler.restart()


def guard_language():
    """Callback for change of the interface language"""
    sabnzbd.lang.set_language(language())
    sabnzbd.api.clear_trans_cache()


def guard_https_ver():
    """Callback for change of https verification"""
    sabnzbd.misc.set_https_verification(enable_https_verification())


##############################################################################
# Conversions
##############################################################################


def config_conversions():
    """Update sections of the config, only once"""
    # Basic old conversions
    if config_conversion_version() < 1:
        logging.info("Config conversion set 1")
        # Convert auto-sort
        if auto_sort() == "0":
            auto_sort.set("")
        elif auto_sort() == "1":
            auto_sort.set("avg_age asc")

        # Convert old series/date/movie sorters
        if not sorters_converted():
            sabnzbd.misc.convert_sorter_settings()
            sorters_converted.set(True)

        # Convert duplicate settings
        if no_series_dupes():
            no_smart_dupes.set(no_series_dupes())
            no_series_dupes.set(0)

        # Convert history retention setting
        if history_retention():
            sabnzbd.misc.convert_history_retention()
            history_retention.set("")

        # Add hostname to the whitelist
        if not host_whitelist():
            host_whitelist.set(socket.gethostname())

        # Set cache limit for new users
        if not cache_limit():
            cache_limit.set(sabnzbd.misc.get_cache_limit())

        # Done
        config_conversion_version.set(1)

    # url_base conversion
    if config_conversion_version() < 2:
        # We did not end up applying this conversion, so we skip this conversion_version
        logging.info("Config conversion set 2")
        config_conversion_version.set(2)

    # Switch to par2cmdline-turbo on Windows
    if config_conversion_version() < 3:
        logging.info("Config conversion set 3")
        if sabnzbd.WINDOWS and par_option():
            # Just empty it, so we don't pass the wrong parameters
            logging.warning(T("The par2 application was switched, any custom par2 parameters were removed"))
            par_option.set("")

        # Done
        config_conversion_version.set(3)

    # Convert Certificate Validation
    if config_conversion_version() < 4:
        logging.info("Config conversion set 4")

        all_servers = get_servers()
        for server in all_servers:
            if all_servers[server].ssl_verify() == 2:
                all_servers[server].ssl_verify.set(3)

        # Done
        config_conversion_version.set(4)

    # Make sure we store the new values
    save_config()
