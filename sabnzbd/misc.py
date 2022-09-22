#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.misc - misc classes
"""

import os
import ssl
import sys
import logging
import urllib.request
import urllib.parse
import re
import subprocess
import socket
import time
import datetime
import inspect
import ctypes
import html
import ipaddress
import socks
from threading import Thread
from typing import Union, Tuple, Any, AnyStr, Optional, List, Dict

import sabnzbd
import sabnzbd.getipaddress
from sabnzbd.constants import DEFAULT_PRIORITY, MEBI, DEF_ARTICLE_CACHE_DEFAULT, DEF_ARTICLE_CACHE_MAX, REPAIR_REQUEST
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.encoding import ubtou, platform_btou
from sabnzbd.filesystem import userxbit, make_script_path, remove_file, is_valid_script

if sabnzbd.WIN32:
    try:
        import win32process
        import win32con

        # Define scheduling priorities
        WIN_SCHED_PRIOS = {
            1: win32process.IDLE_PRIORITY_CLASS,
            2: win32process.BELOW_NORMAL_PRIORITY_CLASS,
            3: win32process.NORMAL_PRIORITY_CLASS,
            4: win32process.ABOVE_NORMAL_PRIORITY_CLASS,
        }
    except ImportError:
        pass

if sabnzbd.MACOS:
    from sabnzbd.utils import sleepless

TAB_UNITS = ("", "K", "M", "G", "T", "P")
RE_UNITS = re.compile(r"(\d+\.*\d*)\s*([KMGTP]?)", re.I)
RE_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)")
RE_SAMPLE = re.compile(r"((^|[\W_])(sample|proof))", re.I)  # something-sample or something-proof
RE_IP4 = re.compile(r"inet\s+(addr:\s*)?(\d+\.\d+\.\d+\.\d+)")
RE_IP6 = re.compile(r"inet6\s+(addr:\s*)?([0-9a-f:]+)", re.I)

# Check if strings are defined for AM and PM
HAVE_AMPM = bool(time.strftime("%p"))


def helpful_warning(*args, **kwargs):
    """Wrapper to ignore helpfull warnings if desired"""
    if sabnzbd.cfg.helpful_warnings():
        return logging.warning(*args, **kwargs)
    return logging.info(*args, **kwargs)


def time_format(fmt):
    """Return time-format string adjusted for 12/24 hour clock setting"""
    if cfg.ampm() and HAVE_AMPM:
        return fmt.replace("%H:%M:%S", "%I:%M:%S %p").replace("%H:%M", "%I:%M %p")
    else:
        return fmt


def format_time_left(totalseconds: int, short_format: bool = False) -> str:
    """Calculate the time left in the format [DD:]HH:MM:SS or [DD:][HH:]MM:SS (short_format)"""
    if totalseconds > 0:
        try:
            minutes, seconds = divmod(totalseconds, 60)
            hours, minutes = divmod(minutes, 60)
            days, hours = divmod(hours, 24)
            if seconds < 10:
                seconds = "0%s" % seconds
            if hours > 0 or not short_format:
                if minutes < 10:
                    minutes = "0%s" % minutes
                if days > 0:
                    if hours < 10:
                        hours = "0%s" % hours
                    return "%s:%s:%s:%s" % (days, hours, minutes, seconds)
                else:
                    return "%s:%s:%s" % (hours, minutes, seconds)
            else:
                return "%s:%s" % (minutes, seconds)
        except:
            pass
    if short_format:
        return "0:00"
    return "0:00:00"


def calc_age(date: datetime.datetime, trans: bool = False) -> str:
    """Calculate the age difference between now and date.
    Value is returned as either days, hours, or minutes.
    When 'trans' is True, time symbols will be translated.
    """
    if trans:
        d = T("d")  # : Single letter abbreviation of day
        h = T("h")  # : Single letter abbreviation of hour
        m = T("m")  # : Single letter abbreviation of minute
    else:
        d = "d"
        h = "h"
        m = "m"
    try:
        now = datetime.datetime.now()
        # age = str(now - date).split(".")[0] #old calc_age

        # time difference
        dage = now - date
        seconds = dage.seconds
        # only one value should be returned
        # if it is less than 1 day then it returns in hours, unless it is less than one hour where it returns in minutes
        if dage.days:
            age = "%d%s" % (dage.days, d)
        elif int(seconds / 3600):
            age = "%d%s" % (seconds / 3600, h)
        else:
            age = "%d%s" % (seconds / 60, m)
    except:
        age = "-"

    return age


def safe_lower(txt: Any) -> str:
    """Return lowercased string. Return '' for None"""
    if txt:
        return txt.lower()
    else:
        return ""


def cmp(x, y):
    """
    Replacement for built-in funciton cmp that was removed in Python 3

    Compare the two objects x and y and return an integer according to
    the outcome. The return value is negative if x < y, zero if x == y
    and strictly positive if x > y.
    """

    return (x > y) - (x < y)


def name_to_cat(fname, cat=None):
    """Retrieve category from file name, but only if "cat" is None."""
    if cat is None and fname.startswith("{{"):
        n = fname.find("}}")
        if n > 2:
            cat = fname[2:n].strip()
            fname = fname[n + 2 :].strip()
            logging.debug("Job %s has category %s", fname, cat)

    return fname, cat


def cat_to_opts(cat, pp=None, script=None, priority=None) -> Tuple[str, int, str, int]:
    """Derive options from category, if options not already defined.
    Specified options have priority over category-options.
    If no valid category is given, special category '*' will supply default values
    """
    def_cat = config.get_category()
    cat = safe_lower(cat)
    if cat in ("", "none", "default"):
        cat = "*"
    my_cat = config.get_category(cat)
    # Ignore the input category if we don't know it
    if my_cat == def_cat:
        cat = "*"

    if pp is None:
        pp = my_cat.pp()
        if pp == "":
            pp = def_cat.pp()

    if not script:
        script = my_cat.script()
        if safe_lower(script) in ("", "default"):
            script = def_cat.script()

    if priority is None or priority == "" or priority == DEFAULT_PRIORITY:
        priority = my_cat.priority()
        if priority == DEFAULT_PRIORITY:
            priority = def_cat.priority()

    logging.debug("Parsing category %s to attributes: pp=%s script=%s prio=%s", cat, pp, script, priority)
    return cat, pp, script, priority


def pp_to_opts(pp: int) -> Tuple[bool, bool, bool]:
    """Convert numeric processing options to (repair, unpack, delete)"""
    # Convert the pp to an int
    pp = sabnzbd.interface.int_conv(pp)
    if pp == 0:
        return False, False, False
    if pp == 1:
        return True, False, False
    if pp == 2:
        return True, True, False
    return True, True, True


def opts_to_pp(repair: bool, unpack: bool, delete: bool) -> int:
    """Convert (repair, unpack, delete) to numeric process options"""
    if delete:
        return 3
    if unpack:
        return 2
    if repair:
        return 1
    return 0


_wildcard_to_regex = {
    "\\": r"\\",
    "^": r"\^",
    "$": r"\$",
    ".": r"\.",
    "[": r"\[",
    "]": r"\]",
    "(": r"\(",
    ")": r"\)",
    "+": r"\+",
    "?": r".",
    "|": r"\|",
    "{": r"\{",
    "}": r"\}",
    "*": r".*",
}


def wildcard_to_re(text):
    """Convert plain wildcard string (with '*' and '?') to regex."""
    return "".join([_wildcard_to_regex.get(ch, ch) for ch in text])


def convert_filter(text):
    """Return compiled regex.
    If string starts with re: it's a real regex
    else quote all regex specials, replace '*' by '.*'
    """
    text = text.strip().lower()
    if text.startswith("re:"):
        txt = text[3:].strip()
    else:
        txt = wildcard_to_re(text)
    try:
        return re.compile(txt, re.I)
    except:
        logging.debug("Could not compile regex: %s", text)
        return None


def cat_convert(cat):
    """Convert indexer's category/group-name to user categories.
    If no match found, but indexer-cat equals user-cat, then return user-cat
    If no match found, but the indexer-cat starts with the user-cat, return user-cat
    If no match found, return None
    """
    if cat and cat.lower() != "none":
        cats = config.get_ordered_categories()
        raw_cats = config.get_categories()
        for ucat in cats:
            try:
                # Ordered cat-list has tags only as string
                indexer = raw_cats[ucat["name"]].newzbin()
                if not isinstance(indexer, list):
                    indexer = [indexer]
            except:
                indexer = []
            for name in indexer:
                if re.search("^%s$" % wildcard_to_re(name), cat, re.I):
                    if "." in name:
                        logging.debug('Convert group "%s" to user-cat "%s"', cat, ucat["name"])
                    else:
                        logging.debug('Convert index site category "%s" to user-cat "%s"', cat, ucat["name"])
                    return ucat["name"]

        # Try to find full match between user category and indexer category
        for ucat in cats:
            if cat.lower() == ucat["name"].lower():
                logging.debug('Convert index site category "%s" to user-cat "%s"', cat, ucat["name"])
                return ucat["name"]

        # Try to find partial match between user category and indexer category
        for ucat in cats:
            if cat.lower().startswith(ucat["name"].lower()):
                logging.debug('Convert index site category "%s" to user-cat "%s"', cat, ucat["name"])
                return ucat["name"]

    return None


_SERVICE_KEY = "SYSTEM\\CurrentControlSet\\services\\"
_SERVICE_PARM = "CommandLine"


def get_serv_parms(service):
    """Get the service command line parameters from Registry"""
    import winreg

    service_parms = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        for n in range(winreg.QueryInfoKey(key)[1]):
            name, service_parms, _val_type = winreg.EnumValue(key, n)
            if name == _SERVICE_PARM:
                break
        winreg.CloseKey(key)
    except OSError:
        pass

    # Always add the base program
    service_parms.insert(0, os.path.normpath(os.path.abspath(sys.argv[0])))

    return service_parms


def set_serv_parms(service, args):
    """Set the service command line parameters in Registry"""
    import winreg

    serv = []
    for arg in args:
        serv.append(arg[0])
        if arg[1]:
            serv.append(arg[1])

    try:
        key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        winreg.SetValueEx(key, _SERVICE_PARM, None, winreg.REG_MULTI_SZ, serv)
        winreg.CloseKey(key)
    except OSError:
        return False
    return True


def get_from_url(url: str) -> Optional[str]:
    """Retrieve URL and return content"""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "SABnzbd/%s" % sabnzbd.__version__)
        with urllib.request.urlopen(req) as response:
            return ubtou(response.read())
    except:
        return None


def convert_version(text):
    """Convert version string to numerical value and a testversion indicator"""
    version = 0
    test = True
    m = RE_VERSION.search(ubtou(text))
    if m:
        version = int(m.group(1)) * 1000000 + int(m.group(2)) * 10000 + int(m.group(3)) * 100
        try:
            if m.group(4).lower() == "rc":
                version = version + 80
            elif m.group(4).lower() == "beta":
                version = version + 40
            version = version + int(m.group(5))
        except:
            version = version + 99
            test = False
    return version, test


def check_latest_version():
    """Do an online check for the latest version

    Perform an online version check
    Syntax of online version file:
        <current-final-release>
        <url-of-current-final-release>
        <latest-alpha/beta-or-rc>
        <url-of-latest-alpha/beta/rc-release>
    The latter two lines are only present when an alpha/beta/rc is available.
    Formula for the version numbers (line 1 and 3).
        <major>.<minor>.<bugfix>[rc|beta|alpha]<cand>

    The <cand> value for a final version is assumned to be 99.
    The <cand> value for the beta/rc version is 1..98, with RC getting
    a boost of 80 and Beta of 40.
    This is done to signal alpha/beta/rc users of availability of the final
    version (which is implicitly 99).
    People will only be informed to upgrade to a higher alpha/beta/rc version, if
    they are already using an alpha/beta/rc.
    RC's are valued higher than Beta's, which are valued higher than Alpha's.
    """

    if not cfg.version_check():
        return

    current, testver = convert_version(sabnzbd.__version__)
    if not current:
        logging.debug("Unsupported release number (%s), will not check", sabnzbd.__version__)
        return

    # Fetch version info
    data = get_from_url("https://sabnzbd.org/latest.txt")
    if not data:
        logging.info("Cannot retrieve version information from GitHub.com")
        logging.debug("Traceback: ", exc_info=True)
        return

    version_data = data.split()
    try:
        latest_label = version_data[0]
        url = version_data[1]
    except:
        latest_label = ""
        url = ""

    try:
        latest_testlabel = version_data[2]
        url_beta = version_data[3]
    except:
        latest_testlabel = ""
        url_beta = ""

    latest = convert_version(latest_label)[0]
    latest_test = convert_version(latest_testlabel)[0]

    logging.debug(
        "Checked for a new release, cur=%s, latest=%s (on %s), latest_test=%s (on %s)",
        current,
        latest,
        url,
        latest_test,
        url_beta,
    )

    if latest_test and cfg.version_check() > 1:
        # User always wants to see the latest test release
        latest = latest_test
        latest_label = latest_testlabel
        url = url_beta

    notify_version = None
    if current < latest:
        # This is a test version, but user hasn't seen the
        # "Final" of this one yet, so show the Final
        # Or this one is behind, show latest final
        sabnzbd.NEW_VERSION = (latest_label, url)
        notify_version = latest_label
    elif testver and current < latest_test:
        # This is a test version beyond the latest Final, so show latest Alpha/Beta/RC
        sabnzbd.NEW_VERSION = (latest_testlabel, url_beta)
        notify_version = latest_testlabel

    if notify_version:
        sabnzbd.notifier.send_notification(T("Update Available!"), "SABnzbd %s" % notify_version, "other")


def upload_file_to_sabnzbd(url, fp):
    """Function for uploading nzbs to a running SABnzbd instance"""
    try:
        fp = urllib.parse.quote_plus(fp)
        url = "%s&mode=addlocalfile&name=%s" % (url, fp)
        # Add local API-key if it wasn't already in the registered URL
        apikey = cfg.api_key()
        if apikey and "apikey" not in url:
            url = "%s&apikey=%s" % (url, apikey)
        if "apikey" not in url:
            # Use alternative login method
            username = cfg.username()
            password = cfg.password()
            if username and password:
                url = "%s&ma_username=%s&ma_password=%s" % (url, username, password)
        get_from_url(url)
    except:
        logging.error(T("Failed to upload file: %s"), fp)
        logging.info("Traceback: ", exc_info=True)


def from_units(val: str) -> float:
    """Convert K/M/G/T/P notation to float
    Does not support negative numbers"""
    val = str(val).strip().upper()
    if val == "-1":
        return float(val)
    m = RE_UNITS.search(val)
    if m:
        if m.group(2):
            val = float(m.group(1))
            unit = m.group(2)
            n = 0
            while unit != TAB_UNITS[n]:
                val = val * 1024.0
                n = n + 1
        else:
            val = m.group(1)
        try:
            return float(val)
        except:
            return 0.0
    else:
        return 0.0


def to_units(val: Union[int, float], postfix="") -> str:
    """Convert number to K/M/G/T/P notation
    Show single decimal for M and higher
    Also supports negative numbers
    """
    if not isinstance(val, (int, float)):
        return ""

    if val < 0:
        sign = "-"
    else:
        sign = ""

    # Determine what form we are at
    val = abs(val)
    n = 0
    while (val > 1023) and (n < 5):
        val = val / 1024
        n = n + 1

    if n > 1:
        decimals = 1
    else:
        decimals = 0

    return ("%%s%%.%sf %%s%%s" % decimals) % (sign, val, TAB_UNITS[n], postfix)


def caller_name(skip=2):
    """Get a name of a caller in the format module.method
    Originally used: https://gist.github.com/techtonik/2151727
    Adapted for speed by using sys calls directly
    """
    # Only do the tracing on Debug (function is always called)
    if cfg.log_level() != 2:
        return "N/A"

    parentframe = sys._getframe(skip)
    function_name = parentframe.f_code.co_name

    # Module name is not available in the binaries, we can use the filename instead
    if hasattr(sys, "frozen"):
        module_name = inspect.getfile(parentframe)
    else:
        module_name = inspect.getmodule(parentframe).__name__

    # For decorated functions we have to go deeper
    if function_name in ("call_func", "wrap") and skip == 2:
        return caller_name(4)

    return ".".join([module_name, function_name])


def exit_sab(value: int):
    """Leave the program after flushing stderr/stdout"""
    sys.stderr.flush()
    sys.stdout.flush()
    # Cannot use sys.exit as it will not work inside the macOS-runner-thread
    os._exit(value)


def split_host(srv):
    """Split host:port notation, allowing for IPV6"""
    if not srv:
        return None, None

    # IPV6 literal (with no port)
    if srv[-1] == "]":
        return srv, None

    out = srv.rsplit(":", 1)
    if len(out) == 1:
        # No port
        port = None
    else:
        try:
            port = int(out[1])
        except ValueError:
            return srv, None

    return out[0], port


def get_cache_limit():
    """Depending on OS, calculate cache limits.
    In ArticleCache it will make sure we stay
    within system limits for 32/64 bit
    """
    # Calculate, if possible
    try:
        if sabnzbd.WIN32:
            # Windows
            mem_bytes = get_windows_memory()
        elif sabnzbd.MACOS:
            # macOS
            mem_bytes = get_macos_memory()
        else:
            # Linux
            mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")

        # Use 1/4th of available memory
        mem_bytes = mem_bytes / 4

        # We don't want to set a value that's too high
        if mem_bytes > from_units(DEF_ARTICLE_CACHE_MAX):
            return DEF_ARTICLE_CACHE_MAX

        # We make sure it's at least a valid value
        if mem_bytes > from_units("32M"):
            return to_units(mem_bytes)
    except:
        pass

    # Always at least minimum on Windows/macOS
    if sabnzbd.WIN32 and sabnzbd.MACOS:
        return DEF_ARTICLE_CACHE_DEFAULT

    # If failed, leave empty for Linux so user needs to decide
    return ""


def get_windows_memory():
    """Use ctypes to extract available memory"""

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

        def __init__(self):
            # have to initialize this to the size of MEMORYSTATUSEX
            self.dwLength = ctypes.sizeof(self)
            super(MEMORYSTATUSEX, self).__init__()

    stat = MEMORYSTATUSEX()
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return stat.ullTotalPhys


def get_macos_memory():
    """Use system-call to extract total memory on macOS"""
    system_output = run_command(["sysctl", "hw.memsize"])
    return float(system_output.split()[1])


def on_cleanup_list(filename: str, skip_nzb: bool = False) -> bool:
    """Return True if a filename matches the clean-up list"""
    cleanup_list = cfg.cleanup_list()
    if cleanup_list:
        name, ext = os.path.splitext(filename)
        ext = ext.strip().lower()
        name = name.strip()
        for cleanup_ext in cleanup_list:
            cleanup_ext = "." + cleanup_ext
            if (cleanup_ext == ext or (ext == "" and cleanup_ext == name)) and not (skip_nzb and cleanup_ext == ".nzb"):
                return True
    return False


def memory_usage():
    try:
        # Probably only works on Linux because it uses /proc/<pid>/statm
        with open("/proc/%d/statm" % os.getpid()) as t:
            v = t.read().split()
        virt = int(_PAGE_SIZE * int(v[0]) / MEBI)
        res = int(_PAGE_SIZE * int(v[1]) / MEBI)
        return "V=%sM R=%sM" % (virt, res)
    except IOError:
        pass
    except:
        logging.debug("Error retrieving memory usage")
        logging.info("Traceback: ", exc_info=True)


try:
    _PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
except:
    _PAGE_SIZE = 0
_HAVE_STATM = _PAGE_SIZE and memory_usage()


def loadavg():
    """Return 1, 5 and 15 minute load average of host or "" if not supported"""
    p = ""
    if not sabnzbd.WIN32 and not sabnzbd.MACOS:
        try:
            p = "%.2f | %.2f | %.2f" % os.getloadavg()
        except:
            pass
        if _HAVE_STATM:
            p = "%s | %s" % (p, memory_usage())
    return p


def format_time_string(seconds: float) -> str:
    """Return a formatted and translated time string"""

    def unit(single, n):
        # Seconds and minutes are special due to historical reasons
        if single == "minute" or (single == "second" and n == 1):
            single = single[:3]
        if n == 1:
            return T(single)
        return T(single + "s")

    # Format the string, size by size
    seconds = int_conv(seconds)
    completestr = []
    days = seconds // 86400
    if days >= 1:
        completestr.append("%s %s" % (days, unit("day", days)))
        seconds -= days * 86400
    hours = seconds // 3600
    if hours >= 1:
        completestr.append("%s %s" % (hours, unit("hour", hours)))
        seconds -= hours * 3600
    minutes = seconds // 60
    if minutes >= 1:
        completestr.append("%s %s" % (minutes, unit("minute", minutes)))
        seconds -= minutes * 60
    if seconds > 0:
        completestr.append("%s %s" % (seconds, unit("second", seconds)))

    # Zero or invalid integer
    if not completestr:
        completestr.append("0 %s" % unit("second", 0))

    return " ".join(completestr)


def int_conv(value: Any) -> int:
    """Safe conversion to int (can handle None)"""
    try:
        value = int(value)
    except:
        value = 0
    return value


def create_https_certificates(ssl_cert, ssl_key):
    """Create self-signed HTTPS certificates and store in paths 'ssl_cert' and 'ssl_key'"""
    try:
        from sabnzbd.utils.certgen import generate_key, generate_local_cert

        private_key = generate_key(key_size=2048, output_file=ssl_key)
        generate_local_cert(private_key, days_valid=3560, output_file=ssl_cert, LN="SABnzbd", ON="SABnzbd")
        logging.info("Self-signed certificates generated successfully")
    except:
        logging.error(T("Error creating SSL key and certificate"))
        logging.info("Traceback: ", exc_info=True)
        return False

    return True


def get_all_passwords(nzo) -> List[str]:
    """Get all passwords, from the NZB, meta and password file. In case a working password is
    already known, try it first."""
    passwords = []
    if nzo.correct_password:
        passwords.append(nzo.correct_password)

    if nzo.password:
        logging.info("Found a password that was set by the user: %s", nzo.password)
        passwords.append(nzo.password.strip())

    # Note that we get a reference to the list, so adding to it updates the original list!
    meta_passwords = nzo.meta.get("password", [])
    pw = nzo.nzo_info.get("password")
    if pw and pw not in meta_passwords:
        meta_passwords.append(pw)

    if meta_passwords:
        passwords.extend(meta_passwords)
        logging.info("Read %s passwords from meta data in NZB: %s", len(meta_passwords), meta_passwords)

    pw_file = cfg.password_file.get_path()
    if pw_file:
        try:
            with open(pw_file, "r") as pwf:
                lines = pwf.read().split("\n")
            # Remove empty lines and space-only passwords and remove surrounding spaces
            pws = [pw.strip("\r\n ") for pw in lines if pw.strip("\r\n ")]
            logging.debug("Read these passwords from file: %s", pws)
            passwords.extend(pws)
            logging.info("Read %s passwords from file %s", len(pws), pw_file)

            # Check size
            if len(pws) > 30:
                helpful_warning(
                    T(
                        "Your password file contains more than 30 passwords, testing all these passwords takes a lot of time. Try to only list useful passwords."
                    )
                )
        except:
            logging.warning(T("Failed to read the password file %s"), pw_file)
            logging.info("Traceback: ", exc_info=True)

    if nzo.password:
        # If an explicit password was set, add a retry without password, just in case.
        passwords.append("")
    elif not passwords or nzo.encrypted < 1:
        # If we're not sure about encryption, start with empty password
        # and make sure we have at least the empty password
        passwords.insert(0, "")

    unique_passwords = []
    for password in passwords:
        if password not in unique_passwords:
            unique_passwords.append(password)
    return unique_passwords


def is_sample(filename: str) -> bool:
    """Try to determine if filename is (most likely) a sample"""
    return bool(re.search(RE_SAMPLE, filename))


def find_on_path(targets):
    """Search the PATH for a program and return full path"""
    if sabnzbd.WIN32:
        paths = os.getenv("PATH").split(";")
    else:
        paths = os.getenv("PATH").split(":")

    if isinstance(targets, str):
        targets = (targets,)

    for path in paths:
        for target in targets:
            target_path = os.path.abspath(os.path.join(path, target))
            if os.path.isfile(target_path) and os.access(target_path, os.X_OK):
                return target_path
    return None


def strip_ipv4_mapped_notation(ip: str) -> str:
    """Convert an IP address in IPv4-mapped IPv6 notation (e.g. ::ffff:192.168.0.10) to its regular
    IPv4 form. Any value of ip that doesn't use the relevant notation is returned unchanged.

    CherryPy may report remote IP addresses in this notation. While the ipaddress module should be
    able to handle that, the latter has issues with the is_private/is_loopback properties for these
    addresses. See https://bugs.python.org/issue33433"""
    try:
        # Keep the original if ipv4_mapped is None
        ip = ipaddress.ip_address(ip).ipv4_mapped or ip
    except (AttributeError, ValueError):
        pass
    return str(ip)


def ip_in_subnet(ip: str, subnet: str) -> bool:
    """Determine whether ip is part of subnet. For the latter, the standard form with a prefix or
    netmask (e.g. "192.168.1.0/24" or "10.42.0.0/255.255.0.0") is expected. Input in SABnzbd's old
    cfg.local_ranges() settings style (e.g. "192.168.1."), intended for use with str.startswith(),
    is also accepted and internally converted to address/prefix form."""
    if not ip or not subnet:
        return False

    try:
        if subnet.find("/") < 0 and subnet.find("::") < 0:
            # The subnet doesn't include a prefix or netmask, or represent a single (compressed)
            # IPv6 address; try converting from the older local_ranges settings style.

            # Take the IP version of the subnet into account
            IP_LEN, IP_BITS, IP_SEP = (8, 16, ":") if subnet.find(":") >= 0 else (4, 8, ".")

            subnet = subnet.rstrip(IP_SEP).split(IP_SEP)
            prefix = IP_BITS * len(subnet)
            # Append as many zeros as needed
            subnet.extend(["0"] * (IP_LEN - len(subnet)))
            # Store in address/prefix form
            subnet = "%s/%s" % (IP_SEP.join(subnet), prefix)

        ip = strip_ipv4_mapped_notation(ip)
        return ipaddress.ip_address(ip) in ipaddress.ip_network(subnet, strict=True)
    except Exception:
        # Probably an invalid range
        return False


def is_ipv4_addr(ip: str) -> bool:
    """Determine if the ip is an IPv4 address"""
    try:
        return ipaddress.ip_address(ip).version == 4
    except ValueError:
        return False


def is_ipv6_addr(ip: str) -> bool:
    """Determine if the ip is an IPv6 address; square brackets ([2001::1]) are OK"""
    try:
        return ipaddress.ip_address(ip.strip("[]")).version == 6
    except (ValueError, AttributeError):
        return False


def is_loopback_addr(ip: str) -> bool:
    """Determine if the ip is an IPv4 or IPv6 local loopback address"""
    try:
        if ip.find(".") < 0:
            ip = ip.strip("[]")
        ip = strip_ipv4_mapped_notation(ip)
        return ipaddress.ip_address(ip).is_loopback
    except (ValueError, AttributeError):
        return False


def is_localhost(value: str) -> bool:
    """Determine if the input is some variety of 'localhost'"""
    return (value == "localhost") or is_loopback_addr(value)


def is_lan_addr(ip: str) -> bool:
    """Determine if the ip is a local area network address"""
    try:
        ip = strip_ipv4_mapped_notation(ip)
        return (
            # The ipaddress module considers these private, see https://bugs.python.org/issue38655
            not ip in ("0.0.0.0", "255.255.255.255")
            and not ip_in_subnet(ip, "::/128")  # Also catch (partially) exploded forms of "::"
            and ipaddress.ip_address(ip).is_private
            and not is_loopback_addr(ip)
        )
    except ValueError:
        return False


def ip_extract() -> List[str]:
    """Return list of IP addresses of this system"""
    ips = []
    program = find_on_path("ip")
    if program:
        program = [program, "a"]
    else:
        program = find_on_path("ifconfig")
        if program:
            program = [program]

    if sabnzbd.WIN32 or not program:
        try:
            info = socket.getaddrinfo(socket.gethostname(), None)
        except:
            # Hostname does not resolve, use localhost
            info = socket.getaddrinfo("localhost", None)
        for item in info:
            ips.append(item[4][0])
    else:
        output = run_command(program)
        for line in output.split("\n"):
            m = RE_IP4.search(line)
            if not (m and m.group(2)):
                m = RE_IP6.search(line)
            if m and m.group(2):
                ips.append(m.group(2))
    return ips


def get_server_addrinfo(host: str, port: int) -> socket.getaddrinfo:
    """Return processed getaddrinfo()"""
    try:
        int(port)
    except:
        port = 119
    opt = sabnzbd.cfg.ipv6_servers()
    """ ... with the following meaning for 'opt':
    Control the use of IPv6 Usenet server addresses. Meaning:
    0 = don't use
    1 = use when available and reachable (DEFAULT)
    2 = force usage (when SABnzbd's detection fails)
    """
    try:
        # Standard IPV4 or IPV6
        ips = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        if opt == 2 or (opt == 1 and sabnzbd.EXTERNAL_IPV6) or (opt == 1 and sabnzbd.cfg.load_balancing() == 2):
            # IPv6 forced by user, or IPv6 allowed and reachable, or IPv6 allowed and loadbalancing-with-IPv6 activated
            # So return all IP addresses, no matter IPv4 or IPv6:
            return ips
        else:
            # IPv6 unreachable or not allowed by user, so only return IPv4 address(es):
            return [ip for ip in ips if ":" not in ip[4][0]]
    except:
        if opt == 2 or (opt == 1 and sabnzbd.EXTERNAL_IPV6) or (opt == 1 and sabnzbd.cfg.load_balancing() == 2):
            try:
                # Try IPV6 explicitly
                return socket.getaddrinfo(
                    host, port, socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_IP, socket.AI_CANONNAME
                )
            except:
                # Nothing found!
                pass
        return []


def get_base_url(url: str) -> str:
    """Return only the true root domain for the favicon, so api.oznzb.com -> oznzb.com
    But also api.althub.co.za -> althub.co.za
    """
    url_host = urllib.parse.urlparse(url).hostname
    if url_host:
        url_split = url_host.split(".")
        # Exception for localhost and IPv6 addresses
        if len(url_split) < 3:
            return url_host
        return ".".join(len(url_split[-2]) < 4 and url_split[-3:] or url_split[-2:])
    else:
        return ""


def match_str(text: AnyStr, matches: Tuple[AnyStr, ...]) -> Optional[AnyStr]:
    """Return first matching element of list 'matches' in 'text', otherwise None"""
    text = text.lower()
    for match in matches:
        if match.lower() in text:
            return match
    return None


def nntp_to_msg(text: Union[List[AnyStr], str]) -> str:
    """Format raw NNTP bytes data for display"""
    if isinstance(text, list):
        text = text[0]

    # Only need to split if it was raw data
    # Sometimes (failed login) we put our own texts
    if not isinstance(text, bytes):
        return text
    else:
        lines = text.split(b"\r\n")
        return ubtou(lines[0])


def recursive_html_escape(input_dict_or_list: Union[Dict[str, Any], List], exclude_items: Tuple[str, ...] = ()):
    """Recursively update the input_dict in-place with html-safe values"""
    if isinstance(input_dict_or_list, (dict, list)):
        if isinstance(input_dict_or_list, dict):
            iterator = input_dict_or_list.items()
        else:
            # For lists we use enumerate
            iterator = enumerate(input_dict_or_list)

        for key, value in iterator:
            # Ignore any keys that are not safe to convert
            if key not in exclude_items:
                # We ignore any other than str
                if isinstance(value, str):
                    input_dict_or_list[key] = html.escape(value, quote=True)
                if isinstance(value, (dict, list)):
                    recursive_html_escape(value, exclude_items=exclude_items)
    else:
        raise ValueError("Expected dict or str, got %s" % type(input_dict_or_list))


def list2cmdline_unrar(lst: List[str]) -> str:
    """convert list to a unrar.exe-compatible command string
    Unrar uses "" instead of \" to escape the double quote"""
    nlst = []
    for arg in lst:
        if not arg:
            nlst.append('""')
        else:
            if isinstance(arg, str):
                arg = arg.replace('"', '""')
            nlst.append('"%s"' % arg)
    return " ".join(nlst)


def build_and_run_command(command: List[str], windows_unrar_command: bool = False, **kwargs):
    """Builds and then runs command with nessecary flags and optional
    IONice and Nice commands. Optional Popen arguments can be supplied.
    On Windows we need to run our own list2cmdline for Unrar.
    Returns the Popen-instance.
    """
    # command[0] should be set, and thus not None
    if not command[0]:
        logging.error(T("[%s] The command in build_command is undefined."), caller_name())
        raise IOError

    if not sabnzbd.WIN32:
        if command[0].endswith(".py"):
            with open(command[0], "r") as script_file:
                if not userxbit(command[0]):
                    # Inform user that Python scripts need x-bit and then stop
                    logging.error(T('Python script "%s" does not have execute (+x) permission set'), command[0])
                    raise IOError
                elif script_file.read(2) != "#!":
                    # No shebang (#!) defined, add default python
                    command.insert(0, sys.executable if sys.executable else "python")

        if sabnzbd.newsunpack.IONICE_COMMAND and cfg.ionice():
            ionice = cfg.ionice().split()
            command = ionice + command
            command.insert(0, sabnzbd.newsunpack.IONICE_COMMAND)
        if sabnzbd.newsunpack.NICE_COMMAND and cfg.nice():
            nice = cfg.nice().split()
            command = nice + command
            command.insert(0, sabnzbd.newsunpack.NICE_COMMAND)
        creationflags = 0
        startupinfo = None
    else:
        # For Windows we always need to add python interpreter
        if command[0].endswith(".py"):
            command.insert(0, "python.exe")
        if windows_unrar_command:
            command = list2cmdline_unrar(command)
        # On some Windows platforms we need to suppress a quick pop-up of the command window
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags = win32process.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = win32con.SW_HIDE
        creationflags = WIN_SCHED_PRIOS[cfg.win_process_prio()]

    # Set the basic Popen arguments
    popen_kwargs = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "startupinfo": startupinfo,
        "creationflags": creationflags,
    }
    # Update with the supplied ones
    popen_kwargs.update(kwargs)

    # Run the command
    logging.info("[%s] Running external command: %s", caller_name(), command)
    logging.debug("Popen arguments: %s", popen_kwargs)
    return subprocess.Popen(command, **popen_kwargs)


def run_command(cmd: List[str], **kwargs):
    """Run simple external command and return output as a string."""
    with build_and_run_command(cmd, **kwargs) as p:
        txt = platform_btou(p.stdout.read())
        p.wait()
    return txt


def run_script(script):
    """Run a user script (queue complete only)"""
    script_path = make_script_path(script)
    if script_path:
        try:
            script_output = run_command([script_path])
            logging.info("Output of queue-complete script %s: \n%s", script, script_output)
        except:
            logging.info("Failed queue-complete script %s, Traceback: ", script, exc_info=True)


def set_socks5_proxy():
    if cfg.socks5_proxy_url():
        proxy = urllib.parse.urlparse(cfg.socks5_proxy_url())
        logging.info("Using Socks5 proxy %s:%s", proxy.hostname, proxy.port)
        socks.set_default_proxy(
            socks.SOCKS5,
            proxy.hostname,
            proxy.port,
            True,  # use remote DNS, default
            proxy.username,
            proxy.password,
        )
        socket.socket = socks.socksocket


def set_https_verification(value):
    """Set HTTPS-verification state while returning current setting
    False = disable verification
    """
    prev = ssl._create_default_https_context == ssl.create_default_context
    if value:
        ssl._create_default_https_context = ssl.create_default_context
    else:
        ssl._create_default_https_context = ssl._create_unverified_context
    return prev


def test_ipv6():
    """Check if external IPv6 addresses are reachable"""
    if not cfg.selftest_host():
        # User disabled the test, assume active IPv6
        return True
    try:
        info = sabnzbd.getipaddress.addresslookup6(cfg.selftest_host())
    except:
        logging.debug(
            "Test IPv6: Disabling IPv6, because it looks like it's not available. Reason: %s", sys.exc_info()[0]
        )
        return False

    try:
        af, socktype, proto, canonname, sa = info[0]
        with socket.socket(af, socktype, proto) as sock:
            sock.settimeout(2)  # 2 second timeout
            sock.connect(sa[0:2])
        logging.debug("Test IPv6: IPv6 test successful. Enabling IPv6")
        return True
    except socket.error:
        logging.debug("Test IPv6: Cannot reach IPv6 test host. Disabling IPv6")
        return False
    except:
        logging.debug("Test IPv6: Problem during IPv6 connect. Disabling IPv6. Reason: %s", sys.exc_info()[0])
        return False


def test_cert_checking():
    """Test quality of certificate validation"""
    # User disabled the test, assume proper SSL certificates
    if not cfg.selftest_host():
        return True

    # Try a connection to our test-host
    try:
        ctx = ssl.create_default_context()
        base_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_sock = ctx.wrap_socket(base_sock, server_hostname=cfg.selftest_host())
        ssl_sock.settimeout(2.0)
        ssl_sock.connect((cfg.selftest_host(), 443))
        ssl_sock.close()
        return True
    except (socket.gaierror, socket.timeout):
        # Non-SSL related error.
        # We now assume that certificates work instead of forcing
        # lower quality just because some (temporary) internet problem
        logging.info("Could not determine system certificate validation quality due to connection problems")
        return True
    except:
        # Seems something is still wrong
        set_https_verification(False)
    return False


def request_repair():
    """Request a full repair on next restart"""
    path = os.path.join(cfg.admin_dir.get_path(), REPAIR_REQUEST)
    try:
        with open(path, "w") as f:
            f.write("\n")
    except:
        pass


def check_repair_request():
    """Return True if repair request found, remove afterwards"""
    path = os.path.join(cfg.admin_dir.get_path(), REPAIR_REQUEST)
    if os.path.exists(path):
        try:
            remove_file(path)
        except:
            pass
        return True
    return False


def system_shutdown():
    """Shutdown system after halting download and saving bookkeeping"""
    logging.info("Performing system shutdown")

    # Do not use regular shutdown, as we should be able to still send system-shutdown
    Thread(target=sabnzbd.halt).start()
    while sabnzbd.__INITIALIZED__:
        time.sleep(1.0)

    if sabnzbd.WIN32:
        sabnzbd.powersup.win_shutdown()
    elif sabnzbd.MACOS:
        sabnzbd.powersup.osx_shutdown()
    else:
        sabnzbd.powersup.linux_shutdown()


def system_hibernate():
    """Hibernate system"""
    logging.info("Performing system hybernation")
    if sabnzbd.WIN32:
        sabnzbd.powersup.win_hibernate()
    elif sabnzbd.MACOS:
        sabnzbd.powersup.osx_hibernate()
    else:
        sabnzbd.powersup.linux_hibernate()


def system_standby():
    """Standby system"""
    logging.info("Performing system standby")
    if sabnzbd.WIN32:
        sabnzbd.powersup.win_standby()
    elif sabnzbd.MACOS:
        sabnzbd.powersup.osx_standby()
    else:
        sabnzbd.powersup.linux_standby()


def change_queue_complete_action(action, new=True):
    """Action or script to be performed once the queue has been completed
    Scripts are prefixed with 'script_'
    When "new" is False, check whether non-script actions are acceptable
    """
    _action = None
    _argument = None
    if action.startswith("script_") and is_valid_script(action.replace("script_", "", 1)):
        # all scripts are labeled script_xxx
        _action = sabnzbd.misc.run_script
        _argument = action.replace("script_", "", 1)
    elif new or cfg.queue_complete_pers():
        if action == "shutdown_pc":
            _action = system_shutdown
        elif action == "hibernate_pc":
            _action = system_hibernate
        elif action == "standby_pc":
            _action = system_standby
        elif action == "shutdown_program":
            _action = sabnzbd.shutdown_program
        else:
            action = None
    else:
        action = None

    if new:
        cfg.queue_complete.set(action or "")
        config.save_config()

    sabnzbd.QUEUECOMPLETE = action
    sabnzbd.QUEUECOMPLETEACTION = _action
    sabnzbd.QUEUECOMPLETEARG = _argument


def keep_awake():
    """If we still have work to do, keep Windows/macOS system awake"""
    if sabnzbd.KERNEL32 or sabnzbd.FOUNDATION:
        if sabnzbd.cfg.keep_awake():
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            if (not sabnzbd.Downloader.is_paused() and not sabnzbd.NzbQueue.is_empty()) or (
                not sabnzbd.PostProcessor.paused and not sabnzbd.PostProcessor.empty()
            ):
                if sabnzbd.KERNEL32:
                    # Set ES_SYSTEM_REQUIRED until the next call
                    sabnzbd.KERNEL32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                else:
                    sleepless.keep_awake("SABnzbd is busy downloading and/or post-processing")
            else:
                if sabnzbd.KERNEL32:
                    # Allow the regular state again
                    sabnzbd.KERNEL32.SetThreadExecutionState(ES_CONTINUOUS)
                else:
                    sleepless.allow_sleep()


def history_updated():
    """To make sure we always have a fresh history"""
    sabnzbd.LAST_HISTORY_UPDATE += 1
    # Never go over the limit
    if sabnzbd.LAST_HISTORY_UPDATE + 1 >= sys.maxsize:
        sabnzbd.LAST_HISTORY_UPDATE = 1
