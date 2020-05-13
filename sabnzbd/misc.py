#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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

import sabnzbd
from sabnzbd.constants import DEFAULT_PRIORITY, MEBI, DEF_ARTICLE_CACHE_DEFAULT, DEF_ARTICLE_CACHE_MAX
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.encoding import ubtou, platform_btou

TAB_UNITS = ("", "K", "M", "G", "T", "P")
RE_UNITS = re.compile(r"(\d+\.*\d*)\s*([KMGTP]{0,1})", re.I)
RE_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)")
RE_IP4 = re.compile(r"inet\s+(addr:\s*){0,1}(\d+\.\d+\.\d+\.\d+)")
RE_IP6 = re.compile(r"inet6\s+(addr:\s*){0,1}([0-9a-f:]+)", re.I)

# Check if strings are defined for AM and PM
HAVE_AMPM = bool(time.strftime("%p", time.localtime()))


def time_format(fmt):
    """ Return time-format string adjusted for 12/24 hour clock setting """
    if cfg.ampm() and HAVE_AMPM:
        return fmt.replace("%H:%M:%S", "%I:%M:%S %p").replace("%H:%M", "%I:%M %p")
    else:
        return fmt


def calc_age(date, trans=False):
    """ Calculate the age difference between now and date.
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


def monthrange(start, finish):
    """ Calculate months between 2 dates, used in the Config template """
    months = (finish.year - start.year) * 12 + finish.month + 1
    for i in range(start.month, months):
        year = (i - 1) / 12 + start.year
        month = (i - 1) % 12 + 1
        yield datetime.date(int(year), int(month), 1)


def safe_lower(txt):
    """ Return lowercased string. Return '' for None """
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


def cat_to_opts(cat, pp=None, script=None, priority=None):
    """ Derive options from category, if options not already defined.
        Specified options have priority over category-options.
        If no valid category is given, special category '*' will supply default values
    """
    def_cat = config.get_categories("*")
    cat = safe_lower(cat)
    if cat in ("", "none", "default"):
        cat = "*"
    try:
        my_cat = config.get_categories()[cat]
    except KeyError:
        cat = "*"
        my_cat = def_cat

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

    logging.debug("Cat->Attrib cat=%s pp=%s script=%s prio=%s", cat, pp, script, priority)
    return cat, pp, script, priority


def pp_to_opts(pp):
    """ Convert numeric processing options to (repair, unpack, delete) """
    # Convert the pp to an int
    pp = sabnzbd.interface.int_conv(pp)
    if pp == 0:
        return False, False, False
    if pp == 1:
        return True, False, False
    if pp == 2:
        return True, True, False
    return True, True, True


def opts_to_pp(repair, unpack, delete):
    """ Convert (repair, unpack, delete) to numeric process options """
    if repair is None:
        return None
    pp = 0
    if repair:
        pp = 1
    if unpack:
        pp = 2
    if delete:
        pp = 3
    return pp


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
    """ Convert plain wildcard string (with '*' and '?') to regex. """
    return "".join([_wildcard_to_regex.get(ch, ch) for ch in text])


def cat_convert(cat):
    """ Convert indexer's category/group-name to user categories.
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


def windows_variant():
    """ Determine Windows variant
        Return vista_plus, x64
    """
    from win32api import GetVersionEx
    from win32con import VER_PLATFORM_WIN32_NT
    import winreg

    vista_plus = x64 = False
    maj, _minor, _buildno, plat, _csd = GetVersionEx()

    if plat == VER_PLATFORM_WIN32_NT:
        vista_plus = maj > 5
        if vista_plus:
            # Must be done the hard way, because the Python runtime lies to us.
            # This does *not* work:
            #     return os.environ['PROCESSOR_ARCHITECTURE'] == 'AMD64'
            # because the Python runtime returns 'X86' even on an x64 system!
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
            )
            for n in range(winreg.QueryInfoKey(key)[1]):
                name, value, _val_type = winreg.EnumValue(key, n)
                if name == "PROCESSOR_ARCHITECTURE":
                    x64 = value.upper() == "AMD64"
                    break
            winreg.CloseKey(key)

    return vista_plus, x64


_SERVICE_KEY = "SYSTEM\\CurrentControlSet\\services\\"
_SERVICE_PARM = "CommandLine"


def get_serv_parms(service):
    """ Get the service command line parameters from Registry """
    import winreg

    service_parms = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY + service)
        for n in range(winreg.QueryInfoKey(key)[1]):
            name, service_parms, _val_type = winreg.EnumValue(key, n)
            if name == _SERVICE_PARM:
                break
        winreg.CloseKey(key)
    except WindowsError:
        pass

    # Always add the base program
    service_parms.insert(0, os.path.normpath(os.path.abspath(sys.argv[0])))

    return service_parms


def set_serv_parms(service, args):
    """ Set the service command line parameters in Registry """
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
    except WindowsError:
        return False
    return True


def get_from_url(url):
    """ Retrieve URL and return content """
    try:
        with urllib.request.urlopen(url) as response:
            return ubtou(response.read())
    except:
        return None


def convert_version(text):
    """ Convert version string to numerical value and a testversion indicator """
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
    """ Do an online check for the latest version

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
    data = get_from_url("https://raw.githubusercontent.com/sabnzbd/sabnzbd.github.io/master/latest.txt")
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

    if testver and current < latest:
        # This is a test version, but user has't seen the
        # "Final" of this one yet, so show the Final
        sabnzbd.NEW_VERSION = (latest_label, url)
    elif current < latest:
        # This one is behind, show latest final
        sabnzbd.NEW_VERSION = (latest_label, url)
    elif testver and current < latest_test:
        # This is a test version beyond the latest Final, so show latest Alpha/Beta/RC
        sabnzbd.NEW_VERSION = (latest_testlabel, url_beta)


def from_units(val):
    """ Convert K/M/G/T/P notation to float """
    val = str(val).strip().upper()
    if val == "-1":
        return val
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


def to_units(val, postfix=""):
    """ Convert number to K/M/G/T/P notation
        Show single decimal for M and higher
    """
    dec_limit = 1
    if val < 0:
        sign = "-"
    else:
        sign = ""
    val = str(abs(val)).strip()

    n = 0
    try:
        val = float(val)
    except:
        return ""
    while (val > 1023.0) and (n < 5):
        val = val / 1024.0
        n = n + 1
    unit = TAB_UNITS[n]
    if n > dec_limit:
        decimals = 1
    else:
        decimals = 0

    fmt = "%%s%%.%sf %%s%%s" % decimals
    return fmt % (sign, val, unit, postfix)


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

    # Modulename not available in the binaries, we can use the filename instead
    if hasattr(sys, "frozen"):
        module_name = inspect.getfile(parentframe)
    else:
        module_name = inspect.getmodule(parentframe).__name__

    # For decorated functions we have to go deeper
    if function_name in ("call_func", "wrap") and skip == 2:
        return caller_name(4)

    return ".".join([module_name, function_name])


def exit_sab(value):
    """ Leave the program after flushing stderr/stdout """
    sys.stderr.flush()
    sys.stdout.flush()
    if hasattr(sys, "frozen") and sabnzbd.DARWIN:
        sabnzbd.SABSTOP = True
        from PyObjCTools import AppHelper

        AppHelper.stopEventLoop()
    sys.exit(value)


def split_host(srv):
    """ Split host:port notation, allowing for IPV6 """
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
    """ Depending on OS, calculate cache limits.
        In ArticleCache it will make sure we stay
        within system limits for 32/64 bit
    """
    # Calculate, if possible
    try:
        if sabnzbd.WIN32:
            # Windows
            mem_bytes = get_windows_memory()
        elif sabnzbd.DARWIN:
            # macOS
            mem_bytes = get_darwin_memory()
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
    if sabnzbd.WIN32 and sabnzbd.DARWIN:
        return DEF_ARTICLE_CACHE_DEFAULT

    # If failed, leave empty for Linux so user needs to decide
    return ""


def get_windows_memory():
    """ Use ctypes to extract available memory """

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


def get_darwin_memory():
    """ Use system-call to extract total memory on macOS """
    system_output = sabnzbd.newsunpack.run_simple(["sysctl", "hw.memsize"])
    return float(system_output.split()[1])


def on_cleanup_list(filename, skip_nzb=False):
    """ Return True if a filename matches the clean-up list """
    lst = cfg.cleanup_list()
    if lst:
        name, ext = os.path.splitext(filename)
        ext = ext.strip().lower()
        name = name.strip()
        for k in lst:
            item = k.strip().strip(".").lower()
            item = "." + item
            if (item == ext or (ext == "" and item == name)) and not (skip_nzb and item == ".nzb"):
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
    """ Return 1, 5 and 15 minute load average of host or "" if not supported """
    p = ""
    if not sabnzbd.WIN32 and not sabnzbd.DARWIN:
        opt = cfg.show_sysload()
        if opt:
            try:
                p = "%.2f | %.2f | %.2f" % os.getloadavg()
            except:
                pass
            if opt > 1 and _HAVE_STATM:
                p = "%s | %s" % (p, memory_usage())
    return p


def format_time_string(seconds):
    """ Return a formatted and translated time string """

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


def int_conv(value):
    """ Safe conversion to int (can handle None) """
    try:
        value = int(value)
    except:
        value = 0
    return value


def create_https_certificates(ssl_cert, ssl_key):
    """ Create self-signed HTTPS certificates and store in paths 'ssl_cert' and 'ssl_key' """
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


def get_all_passwords(nzo):
    """ Get all passwords, from the NZB, meta and password file """
    if nzo.password:
        logging.info("Found a password that was set by the user: %s", nzo.password)
        passwords = [nzo.password.strip()]
    else:
        passwords = []

    meta_passwords = nzo.meta.get("password", [])
    pw = nzo.nzo_info.get("password")
    if pw:
        meta_passwords.append(pw)

    if meta_passwords:
        if nzo.password == meta_passwords[0]:
            # this nzo.password came from meta, so don't use it twice
            passwords.extend(meta_passwords[1:])
        else:
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
                logging.warning(
                    T(
                        "Your password file contains more than 30 passwords, testing all these passwords takes a lot of time. Try to only list useful passwords."
                    )
                )
        except:
            logging.warning("Failed to read the passwords file %s", pw_file)

    if nzo.password:
        # If an explicit password was set, add a retry without password, just in case.
        passwords.append("")
    elif not passwords or nzo.encrypted < 1:
        # If we're not sure about encryption, start with empty password
        # and make sure we have at least the empty password
        passwords.insert(0, "")
    return passwords


def find_on_path(targets):
    """ Search the PATH for a program and return full path """
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


def probablyipv4(ip):
    if ip.count(".") == 3 and re.sub("[0123456789.]", "", ip) == "":
        return True
    else:
        return False


def probablyipv6(ip):
    # Returns True if the given input is probably an IPv6 address
    # Square Brackets like '[2001::1]' are OK
    if ip.count(":") >= 2 and re.sub(r"[0123456789abcdefABCDEF:\[\]]", "", ip) == "":
        return True
    else:
        return False


def ip_extract():
    """ Return list of IP addresses of this system """
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
        p = subprocess.Popen(
            program,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            startupinfo=None,
            creationflags=0,
        )
        output = platform_btou(p.stdout.read())
        p.wait()
        for line in output.split("\n"):
            m = RE_IP4.search(line)
            if not (m and m.group(2)):
                m = RE_IP6.search(line)
            if m and m.group(2):
                ips.append(m.group(2))
    return ips


def get_base_url(url):
    """ Return only the true root domain for the favicon, so api.oznzb.com -> oznzb.com
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


def match_str(text, matches):
    """ Return first matching element of list 'matches' in 'text', otherwise None """
    for match in matches:
        if match in text:
            return match
    return None


def nntp_to_msg(text):
    """ Format raw NNTP bytes data for display """
    if isinstance(text, list):
        text = text[0]

    # Only need to split if it was raw data
    # Sometimes (failed login) we put our own texts
    if not isinstance(text, bytes):
        return text
    else:
        lines = text.split(b"\r\n")
        return ubtou(lines[0])
