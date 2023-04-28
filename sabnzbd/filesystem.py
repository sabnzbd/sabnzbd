#!/usr/bin/python3 -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.misc - filesystem operations
"""
import gzip
import os
import pickle
import sys
import logging
import re
import shutil
import tempfile
import threading
import time
import fnmatch
import stat
import ctypes
from typing import Union, List, Tuple, Any, Dict, Optional, BinaryIO

try:
    import win32api
    import win32file
except ImportError:
    pass

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import FUTURE_Q_FOLDER, JOB_ADMIN, GIGI, DEF_FILE_MAX, IGNORED_FILES_AND_FOLDERS
from sabnzbd.encoding import correct_unknown_encoding, utob, ubtou
from sabnzbd.utils import rarfile


# For Windows: determine executable extensions
if os.name == "nt":
    PATHEXT = os.environ.get("PATHEXT", "").lower().split(";")
else:
    PATHEXT = []


def get_ext(filename: str) -> str:
    """Return lowercased file extension"""
    try:
        return os.path.splitext(filename)[1].lower()
    except:
        return ""


def is_listed_ext(ext: str, ext_list: list) -> bool:
    """Check if the extension is listed. In case of a regexp the entire extension must be matched;
    partial matches aren't accepted (e.g. 'r[0-9]{2}' will be treated the same as '^r[0-9]{2}$' and
    thus return false for extensions such as 'r007' despite the substring match on 'r00').
    """
    for item in ext_list:
        if RE_EXT := sabnzbd.misc.convert_filter(item):
            try:
                if len(RE_EXT.match(ext).group()) == len(ext):
                    return True
            except Exception:
                pass
        elif item == ext:
            return True
    # No match found
    return False


def has_unwanted_extension(filename: str) -> bool:
    """Determine if a filename has an unwanted extension, given the configured mode"""
    extension = get_ext(filename).replace(".", "")
    if extension and sabnzbd.cfg.unwanted_extensions():
        return (
            # Blacklisted
            sabnzbd.cfg.unwanted_extensions_mode() == 0
            and is_listed_ext(extension, sabnzbd.cfg.unwanted_extensions())
        ) or (
            # Not whitelisted
            sabnzbd.cfg.unwanted_extensions_mode() == 1
            and not is_listed_ext(extension, sabnzbd.cfg.unwanted_extensions())
        )
    else:
        # Don't consider missing extensions unwanted to prevent indiscriminate blocking of
        # obfuscated jobs in whitelist mode. If there is an extension but nothing listed as
        # (un)wanted, the result only depends on the configured mode.
        return bool(extension and sabnzbd.cfg.unwanted_extensions_mode())


def get_filename(path: str) -> str:
    """Return path without the file extension"""
    try:
        return os.path.split(path)[1]
    except:
        return ""


def setname_from_path(path: str) -> str:
    """Get the setname from a path"""
    return os.path.splitext(os.path.basename(path))[0]


def is_writable(path: str) -> bool:
    """Return True is file is writable (also when non-existent)"""
    if os.path.isfile(path):
        return bool(os.stat(path).st_mode & stat.S_IWUSR)
    else:
        return True


def is_size(filepath: str, size: int) -> bool:
    """Return True if filepath exists and is specified size"""
    try:
        return os.path.getsize(filepath) == size
    except:
        return False


_DEVICES = (
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
)


def replace_win_devices(name: str) -> str:
    """Remove reserved Windows device names from a name.
    aux.txt ==> _aux.txt
    txt.aux ==> txt.aux
    """
    if name:
        lname = name.lower()
        for dev in _DEVICES:
            if lname == dev or lname.startswith(dev + "."):
                name = "_" + name
                break

        # Remove special NTFS filename
        if lname.startswith("$mft"):
            name = name.replace("$", "S", 1)

    return name


def has_win_device(filename: str) -> bool:
    """Return True if filename part contains forbidden name
    Before and after sanitizing
    """
    filename = os.path.split(filename)[1].lower()
    for dev in _DEVICES:
        if filename == dev or filename.startswith(dev + ".") or filename.startswith("_" + dev + "."):
            return True
    return False


CH_ILLEGAL = "\0/"
CH_LEGAL = "_+"
CH_ILLEGAL_WIN = '\\/<>?*|":'
CH_LEGAL_WIN = "++{}!@#'-"
for i in range(1, 32):
    CH_ILLEGAL_WIN += chr(i)
    CH_LEGAL_WIN += "_"


def sanitize_filename(name: str) -> str:
    """Return filename with illegal chars converted to legal ones
    and with the par2 extension always in lowercase
    """
    if not name:
        return name

    illegal = CH_ILLEGAL
    legal = CH_LEGAL

    if sabnzbd.WIN32 or sabnzbd.cfg.sanitize_safe():
        # Remove all bad Windows chars too
        illegal += CH_ILLEGAL_WIN
        legal += CH_LEGAL_WIN

    if ":" in name and sabnzbd.MACOS:
        # Compensate for the foolish way par2 on macOS handles a colon character
        name = name[name.rfind(":") + 1 :]

    lst = []
    for ch in name.strip():
        if ch in illegal:
            ch = legal[illegal.find(ch)]
        lst.append(ch)
    name = "".join(lst)

    if sabnzbd.WIN32 or sabnzbd.cfg.sanitize_safe():
        name = replace_win_devices(name)

    if not name:
        name = "unknown"

    # now split name into name, ext
    name, ext = os.path.splitext(name)

    # If filename is too long (more than DEF_FILE_MAX bytes), brute-force truncate it,
    # preserving the extension (max ext length 20)
    # Note: some filesystem can handle up to 255 UTF chars (which is more than 255 bytes) in the filename,
    # but we stay on the safe side: max DEF_FILE_MAX bytes
    if len(utob(name)) + len(utob(ext)) > DEF_FILE_MAX:
        logging.debug("Filename %s is too long, so truncating", name + ext)
        # Too long filenames are often caused by incorrect non-ascii chars,
        # so brute-force remove those non-ascii chars
        name = ubtou(name.encode("ascii", "ignore"))
        # Now it's plain ASCII, so no need for len(str.encode()) anymore; plain len() is enough
        if len(name) + len(ext) > DEF_FILE_MAX:
            # still too long, limit the extension
            maxextlength = 20  # max length of an extension
            if len(ext) > maxextlength:
                # allow first <maxextlength> chars, including the starting dot
                ext = ext[:maxextlength]
            if len(name) + len(ext) > DEF_FILE_MAX:
                # Still too long, limit the basename
                name = name[: DEF_FILE_MAX - len(ext)]

    lowext = ext.lower()
    if lowext == ".par2" and lowext != ext:
        ext = lowext
    return name + ext


def sanitize_foldername(name: str) -> str:
    """Return foldername with dodgy chars converted to safe ones
    Remove any leading and trailing dot and space characters
    """
    if not name:
        return name

    illegal = CH_ILLEGAL + ':"'
    legal = CH_LEGAL + "-'"

    if sabnzbd.WIN32 or sabnzbd.cfg.sanitize_safe():
        # Remove all bad Windows chars too
        illegal += CH_ILLEGAL_WIN
        legal += CH_LEGAL_WIN

    lst = []
    for ch in name.strip():
        if ch in illegal:
            ch = legal[illegal.find(ch)]
            lst.append(ch)
        else:
            lst.append(ch)
    name = "".join(lst)

    if sabnzbd.WIN32 or sabnzbd.cfg.sanitize_safe():
        name = replace_win_devices(name)

    if len(name) >= sabnzbd.cfg.max_foldername_length():
        name = name[: sabnzbd.cfg.max_foldername_length()]

    # And finally, make sure it doesn't end in a dot or a space
    # This is invalid on Windows and can cause trouble for some other tools
    if name != "." and name != "..":
        # This would be perfect for := operator in Python 3.8+
        while len(name.strip().rstrip(".")) < len(name):
            name = name.strip().rstrip(".")

    # Just to be sure we don't return nothing
    if not name:
        name = "unknown"

    return name


def sanitize_and_trim_path(path: str) -> str:
    """Remove illegal characters and trim element size"""
    path = path.strip()
    new_path = ""
    if sabnzbd.WIN32:
        if path.startswith("\\\\?\\UNC\\"):
            new_path = "\\\\?\\UNC\\"
            path = path[8:]
        elif path.startswith("\\\\?\\"):
            new_path = "\\\\?\\"
            path = path[4:]

    path = path.replace("\\", "/")
    parts = path.split("/")
    if sabnzbd.WIN32 and len(parts[0]) == 2 and ":" in parts[0]:
        new_path += parts[0] + "/"
        parts.pop(0)
    elif path.startswith("//"):
        new_path = "//"
    elif path.startswith("/"):
        new_path = "/"
    for part in parts:
        new_path = os.path.join(new_path, sanitize_foldername(part))
    return os.path.abspath(os.path.normpath(new_path))


def sanitize_files(folder: Optional[str] = None, filelist: Optional[List[str]] = None) -> List[str]:
    """Sanitize each file in the folder or list of filepaths, return list of new names"""
    logging.info("Checking if any resulting filenames need to be sanitized")
    if folder:
        filelist = listdir_full(folder)
    else:
        filelist = filelist or []

    # Loop over all the files
    output_filelist = []
    for old_path in filelist:
        # Will skip files if there's nothing to sanitize
        output_filelist.append(renamer(old_path, old_path))
    return output_filelist


def real_path(loc: str, path: str) -> str:
    """When 'path' is relative, return normalized join of 'loc' and 'path'
    When 'path' is absolute, return normalized path
    A path starting with ~ will be located in the user's Home folder
    """
    # The Windows part is a bit convoluted because
    # C: and C:\ are 2 different things
    if path:
        path = path.strip()
    else:
        path = ""
    if path:
        if not sabnzbd.WIN32 and path.startswith("~/"):
            path = path.replace("~", os.environ.get("HOME", sabnzbd.DIR_HOME), 1)
        if sabnzbd.WIN32:
            # The Windows-functions work differently on long-path
            # So we bring it back to normal and make it long-path at the end
            loc = clip_path(loc)
            path = path.replace("/", "\\")
            if len(path) > 1 and path[0].isalpha() and path[1] == ":":
                if len(path) == 2 or path[2] != "\\":
                    path = path.replace(":", ":\\", 1)
            elif path.startswith("\\\\"):
                pass
            elif path.startswith("\\"):
                if len(loc) > 1 and loc[0].isalpha() and loc[1] == ":":
                    path = loc[:2] + path
            else:
                path = os.path.join(loc, path)
        elif path[0] != "/":
            path = os.path.join(loc, path)
    else:
        path = loc

    return long_path(os.path.normpath(os.path.abspath(path)))


def create_real_path(
    name: str, loc: str, path: str, apply_permissions: bool = False, writable: bool = True
) -> Tuple[bool, str, Optional[str]]:
    """When 'path' is relative, create join of 'loc' and 'path'
    When 'path' is absolute, create normalized path
    'name' is used for logging.
    Optional 'umask' will be applied.
    'writable' means that an existing folder should be writable
    Returns ('success', 'full path', 'error_msg')
    """
    if path:
        my_dir = real_path(loc, path)
        if not os.path.exists(my_dir):
            if not create_all_dirs(my_dir, apply_permissions):
                msg = T("Cannot create directory %s") % clip_path(my_dir)
                logging.error(msg)
                return False, my_dir, msg

        checks = (os.W_OK + os.R_OK) if writable else os.R_OK
        if os.access(my_dir, checks):
            return True, my_dir, None
        else:
            msg = T("%s directory: %s error accessing") % (name, clip_path(my_dir))
            logging.error(msg)
            return False, my_dir, msg
    else:
        return False, path, None


def same_file(a: str, b: str) -> int:
    """Return 0 if A and B have nothing in common
    return 1 if A and B are actually the same path
    return 2 if B is a subfolder of A
    """
    if sabnzbd.WIN32 or sabnzbd.MACOS:
        a = clip_path(a.lower())
        b = clip_path(b.lower())

    a = os.path.normpath(os.path.abspath(a))
    b = os.path.normpath(os.path.abspath(b))

    # If it's the same file, it's also a sub-folder
    is_subfolder = 0
    if b.startswith(a):
        is_subfolder = 2

    try:
        # Only available on Linux
        if os.path.samefile(a, b) is True:
            return 1
        return is_subfolder
    except:
        if int(a == b):
            return 1
        else:
            return is_subfolder


def check_mount(path: str) -> bool:
    """Return False if volume isn't mounted on Linux or macOS
    Retry 6 times with an interval of 1 sec.
    """
    if sabnzbd.MACOS:
        m = re.search(r"^(/Volumes/[^/]+)", path, re.I)
    elif sabnzbd.WIN32:
        m = re.search(r"^([a-z]:\\)", path, re.I)
    else:
        m = re.search(r"^(/(?:mnt|media)/[^/]+)", path)

    if m:
        for n in range(sabnzbd.cfg.wait_ext_drive() or 1):
            if os.path.exists(m.group(1)):
                return True
            logging.debug("Waiting for %s to come online", m.group(1))
            time.sleep(1)
    return not m


RAR_RE = re.compile(r"\.(?P<ext>part\d*\.rar|rar|r\d\d|s\d\d|t\d\d|u\d\d|v\d\d|\d\d\d?\d)$", re.I)
SPLITFILE_RE = re.compile(r"\.(\d\d\d?\d$)", re.I)
ZIP_RE = re.compile(r"\.(zip$)", re.I)
SEVENZIP_RE = re.compile(r"\.7z$", re.I)
SEVENMULTI_RE = re.compile(r"\.7z\.\d+$", re.I)
TS_RE = re.compile(r"\.(\d+)\.(ts$)", re.I)


def build_filelists(
    workdir: Optional[str], workdir_complete: Optional[str] = None, check_both: bool = False, check_rar: bool = True
) -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
    """Build filelists, if workdir_complete has files, ignore workdir.
    Optionally scan both directories.
    Optionally test content to establish RAR-ness
    """
    sevens, joinables, zips, rars, ts, filelist = ([], [], [], [], [], [])

    if workdir_complete:
        filelist.extend(listdir_full(workdir_complete))

    if workdir and (not filelist or check_both):
        filelist.extend(listdir_full(workdir, recursive=False))

    for file in filelist:
        # Extra check for rar (takes CPU/disk)
        file_is_rar = False
        if check_rar:
            file_is_rar = rarfile.is_rarfile(file)

        # Run through all the checks
        if SEVENZIP_RE.search(file) or SEVENMULTI_RE.search(file):
            # 7zip
            sevens.append(file)
        elif SPLITFILE_RE.search(file) and not file_is_rar:
            # Joinables, optional with RAR check
            joinables.append(file)
        elif ZIP_RE.search(file):
            # ZIP files
            zips.append(file)
        elif RAR_RE.search(file):
            # RAR files
            rars.append(file)
        elif TS_RE.search(file):
            # TS split files
            ts.append(file)

    logging.debug("build_filelists(): joinables: %s", joinables)
    logging.debug("build_filelists(): zips: %s", zips)
    logging.debug("build_filelists(): rars: %s", rars)
    logging.debug("build_filelists(): 7zips: %s", sevens)
    logging.debug("build_filelists(): ts: %s", ts)

    return joinables, zips, rars, sevens, ts


def safe_fnmatch(f: str, pattern: str) -> bool:
    """fnmatch will fail if the pattern contains any of it's
    key characters, like [, ] or !.
    """
    try:
        return fnmatch.fnmatch(f, pattern)
    except re.error:
        return False


def globber(path: str, pattern: str = "*") -> List[str]:
    """Return matching base file/folder names in folder `path`"""
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        return [f for f in os.listdir(path) if safe_fnmatch(f, pattern)]
    return []


def globber_full(path: str, pattern: str = "*") -> List[str]:
    """Return matching full file/folder names in folder `path`"""
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        return [os.path.join(path, f) for f in os.listdir(path) if safe_fnmatch(f, pattern)]
    return []


def fix_unix_encoding(folder: str):
    """Fix bad name encoding for Unix systems
    This happens for example when files are created
    on Windows but unpacked/repaired on linux
    """
    if not sabnzbd.WIN32 and not sabnzbd.MACOS:
        for root, dirs, files in os.walk(folder):
            for name in files:
                new_name = correct_unknown_encoding(name)
                if name != new_name:
                    try:
                        renamer(os.path.join(root, name), os.path.join(root, new_name))
                    except:
                        logging.info("Cannot correct name of %s", os.path.join(root, name))


def is_valid_script(basename: str) -> bool:
    """Determine if 'basename' is a valid script"""
    return basename in list_scripts(default=False, none=False)


def list_scripts(default: bool = False, none: bool = True) -> List[str]:
    """Return a list of script names, optionally with 'Default' added"""
    lst = []
    path = sabnzbd.cfg.script_dir.get_path()
    if path and os.access(path, os.R_OK):
        for script in globber_full(path):
            if os.path.isfile(script):
                if (
                    (
                        sabnzbd.WIN32
                        and os.path.splitext(script)[1].lower() in PATHEXT
                        and not win32api.GetFileAttributes(script) & win32file.FILE_ATTRIBUTE_HIDDEN
                    )
                    or script.endswith(".py")
                    or (not sabnzbd.WIN32 and userxbit(script) and not os.path.basename(script).startswith("."))
                ):
                    lst.append(os.path.basename(script))
            # Make sure capitalization is ignored to avoid strange results
            lst = sorted(lst, key=str.casefold)
        if none:
            lst.insert(0, "None")
        if default:
            lst.insert(0, "Default")
    return lst


def make_script_path(script: str) -> Optional[str]:
    """Return full script path, if any valid script exists, else None"""
    script_path = None
    script_dir = sabnzbd.cfg.script_dir.get_path()
    if script_dir and script:
        if script.lower() not in ("none", "default") and is_valid_script(script):
            script_path = os.path.join(script_dir, script)
            if not os.path.exists(script_path):
                script_path = None
            else:
                # Paths to scripts should not be long-path notation
                script_path = clip_path(script_path)
    return script_path


def get_admin_path(name: str, future: bool):
    """Return news-style full path to job-admin folder of names job
    or else the old cache path
    """
    if future:
        return os.path.join(sabnzbd.cfg.admin_dir.get_path(), FUTURE_Q_FOLDER)
    else:
        return os.path.join(os.path.join(sabnzbd.cfg.download_dir.get_path(), name), JOB_ADMIN)


def set_chmod(path: str, permissions: int, allow_failures: bool = False):
    """Set 'permissions' on 'path'"""
    try:
        logging.debug("Applying permissions %s (octal) to %s", oct(permissions), path)
        os.chmod(path, permissions)
    except:
        if not allow_failures and not sabnzbd.misc.match_str(path, IGNORED_FILES_AND_FOLDERS):
            logging.error(T("Cannot change permissions of %s"), clip_path(path))
            logging.info("Traceback: ", exc_info=True)
        else:
            logging.debug("Could not change permissions of %s", path)


def set_permissions(path: str, recursive: bool = True):
    """Give folder tree and its files their proper permissions"""
    if not sabnzbd.WIN32:
        if custom_permissions := sabnzbd.cfg.permissions():
            # If user set permissions, parse them
            custom_permissions = int(custom_permissions, 8)

        if os.path.isdir(path):
            if recursive:
                # Parse the dir/file tree and set permissions
                for root, _, files in os.walk(path):
                    if custom_permissions:
                        set_chmod(root, custom_permissions)
                    for name in files:
                        removexbits(os.path.join(root, name), custom_permissions)
            elif custom_permissions:
                set_chmod(path, custom_permissions)
        else:
            removexbits(path, custom_permissions)


UNWANTED_FILE_PERMISSIONS = stat.S_ISUID | stat.S_ISGID | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def removexbits(path: str, custom_permissions: int = None):
    """Remove all the x-bits from files, respecting current or custom permissions"""
    if os.path.isfile(path):
        # Use custom permissions as base
        current_permissions = custom_permissions
        allow_failures = False
        if not custom_permissions:
            current_permissions = os.stat(path).st_mode
            # Allow failures if no custom permissions are set, changing permissions might not be supported
            allow_failures = True
        # Check if the file has any x-bits, no need to remove them otherwise
        if custom_permissions or current_permissions & UNWANTED_FILE_PERMISSIONS:
            # Mask out the X-bits
            set_chmod(path, current_permissions & ~UNWANTED_FILE_PERMISSIONS, allow_failures)


def userxbit(path: str) -> bool:
    """Returns boolean if the x-bit for user is set on the given file.
    This is a workaround: os.access(filename, os.X_OK) does not work
    on certain mounted file systems. Does not work at all on Windows.
    """
    # rwx rwx rwx
    # 876 543 210      # we want bit 6 from the right, counting from 0
    userxbit = 1 << 6  # bit 6
    rwxbits = os.stat(path)[0]  # the first element of os.stat() is "mode"
    # do logical AND, check if it is not 0:
    xbitset = (rwxbits & userxbit) > 0
    return xbitset


def clip_path(path: str) -> str:
    r"""Remove \\?\ or \\?\UNC\ prefix from Windows path"""
    if sabnzbd.WIN32 and path and "?" in path:
        path = path.replace("\\\\?\\UNC\\", "\\\\", 1).replace("\\\\?\\", "", 1)
    return path


def long_path(path: str) -> str:
    """For Windows, convert to long style path; others, return same path"""
    if sabnzbd.WIN32 and path and not path.startswith("\\\\?\\"):
        if path.startswith("\\\\"):
            # Special form for UNC paths
            path = path.replace("\\\\", "\\\\?\\UNC\\", 1)
        else:
            # Normal form for local paths
            path = "\\\\?\\" + path
    return path


##############################################################################
# Locked directory operations to avoid problems with simultaneous add/remove
##############################################################################
DIR_LOCK = threading.RLock()


@synchronized(DIR_LOCK)
def create_all_dirs(path: str, apply_permissions: bool = False) -> Union[str, bool]:
    """Create all required path elements and set permissions on all
    The apply_permissions argument is ignored on Windows
    Return path if elements could be made or exists
    """
    try:
        logging.info("Creating directories: %s", path)
        if sabnzbd.WIN32:
            # On Windows it can fail on UNC-paths in long-path notation
            # https://bugs.python.org/issue41705
            if not os.path.exists(path):
                os.makedirs(path)
        else:
            # We need to build the directory recursively, so we can
            # apply permissions to only the newly created folders
            # We cannot use os.makedirs() as it could ignore the mode
            path_part_combined = "/"
            for path_part in path.split("/"):
                if path_part:
                    path_part_combined = os.path.join(path_part_combined, path_part)
                    # Only create if it doesn't exist
                    if not os.path.exists(path_part_combined):
                        os.mkdir(path_part_combined)
                        # Try to set permissions if desired, ignore failures
                        if apply_permissions:
                            set_permissions(path_part_combined, recursive=False)
        return path
    except OSError:
        logging.error(T("Failed making (%s)"), clip_path(path), exc_info=True)
        return False


@synchronized(DIR_LOCK)
def get_unique_dir(path: str, n: int = 0, create_dir: bool = True) -> Union[str, bool]:
    """Determine a unique folder or filename"""
    if not check_mount(path):
        return path

    new_path = path
    if n:
        new_path = "%s.%s" % (path, n)

    if not os.path.exists(new_path):
        if create_dir:
            return create_all_dirs(new_path, apply_permissions=True)
        else:
            return new_path
    else:
        return get_unique_dir(path, n=n + 1, create_dir=create_dir)


@synchronized(DIR_LOCK)
def get_unique_filename(path: str) -> str:
    """Check if path is unique.
    If not, add number like: "/path/name.NUM.ext".
    """
    num = 1
    new_path, filename = os.path.split(path)
    name, ext = os.path.splitext(filename)
    while os.path.exists(path):
        filename = "%s.%d%s" % (name, num, ext)
        num += 1
        path = os.path.join(new_path, filename)
    return path


@synchronized(DIR_LOCK)
def listdir_full(input_dir: str, recursive: bool = True) -> List[str]:
    """List all files in dirs and sub-dirs"""
    filelist = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            # Ignore special folders and resources files created by macOS
            if not sabnzbd.misc.match_str(root, IGNORED_FILES_AND_FOLDERS) and not file.startswith("._"):
                filelist.append(os.path.join(root, file))
        if not recursive:
            break
    return filelist


@synchronized(DIR_LOCK)
def move_to_path(path: str, new_path: str) -> Tuple[bool, Optional[str]]:
    """Move a file to a new path, optionally give unique filename
    Return (ok, new_path)
    """
    ok = True
    overwrite = sabnzbd.cfg.overwrite_files()
    new_path = os.path.abspath(new_path)
    new_path_dir = os.path.dirname(new_path)
    if overwrite and os.path.exists(new_path):
        try:
            os.remove(new_path)
        except:
            overwrite = False
    if not overwrite:
        new_path = get_unique_filename(new_path)

    if new_path:
        logging.debug("Moving (overwrite: %s) %s => %s", overwrite, path, new_path)
        if not os.path.exists(new_path_dir):
            create_all_dirs(os.path.dirname(new_path), apply_permissions=True)
        try:
            # First try cheap rename
            renamer(path, new_path)
        except Exception as err:
            # Cannot rename, try copying
            logging.debug("File could not be renamed (error: %s), trying copying: %s", err, path)
            try:
                shutil.copyfile(path, new_path)
                os.remove(path)
            except:
                # Check if the old-file actually exists (possible delete-delays)
                if not os.path.exists(path):
                    logging.debug("File not moved, original path gone: %s", path)
                    return True, None
                if not (sabnzbd.cfg.marker_file() and sabnzbd.cfg.marker_file() in path):
                    logging.error(T("Failed moving %s to %s"), clip_path(path), clip_path(new_path))
                    logging.info("Traceback: ", exc_info=True)
                ok = False
    return ok, new_path


@synchronized(DIR_LOCK)
def cleanup_empty_directories(path: str):
    """Remove all empty folders inside (and including) 'path'"""
    path = os.path.normpath(path)
    while 1:
        repeat = False
        for root, dirs, files in os.walk(path, topdown=False):
            if not dirs and not files and root != path:
                try:
                    remove_dir(root)
                    repeat = True
                except:
                    pass
        if not repeat:
            break

    # Only remove if main folder is now also empty
    if not os.listdir(path):
        try:
            remove_dir(path)
        except:
            pass


@synchronized(DIR_LOCK)
def renamer(old: str, new: str, create_local_directories: bool = False) -> str:
    """Rename file/folder with retries for Win32
    Optionally allows the creation of local directories if they don't exist yet
    Returns new filename (which could be changed due to sanitize_filename) on success"""
    # Sanitize last part of new name
    path, name = os.path.split(new)
    new = os.path.join(path, sanitize_filename(name))

    # Skip if nothing changes
    if old == new:
        return new

    # In case we want nonexistent directories to be created, check for directory escape (forbidden)
    if create_local_directories:
        oldpath, _ = os.path.split(old)
        # Check not outside directory
        # In case of "same_file() == 1": same directory, so nothing to do
        if same_file(oldpath, path) == 0:
            # Outside current directory, this is most likely malicious
            logging.error(T("Blocked attempt to create directory %s"), path)
            raise OSError("Refusing to go outside directory")
        elif same_file(oldpath, path) == 2:
            # Sub-directory, so create if does not yet exist:
            create_all_dirs(path)

    logging.debug('Renaming "%s" to "%s"', old, new)
    if sabnzbd.WIN32:
        retries = 10
        while retries > 0:
            try:
                # First we try 3 times with os.rename
                if retries > 7:
                    os.rename(old, new)
                else:
                    # Now we try the back-up method
                    logging.debug("Could not rename, trying move for %s to %s", old, new)
                    shutil.move(old, new)
                return new
            except OSError as err:
                logging.debug('Error renaming "%s" to "%s" <%s>', old, new, err)
                if err.winerror == 17:
                    # Error 17 - Rename can't move to different disk
                    # Jump to moving with shutil.move
                    retries -= 3
                elif err.winerror == 32 or err.winerror == 5:
                    # Error 32 - Used by another process
                    # Error 5 - Access is denied (virus scanners)
                    logging.debug("File busy, retrying rename %s to %s", old, new)
                    retries -= 1
                    # Wait for the other process
                    time.sleep(2)
                else:
                    raise
        raise OSError("Failed to rename (Winerr %s)" % hex(ctypes.windll.ntdll.RtlGetLastNtStatus() + 2**32))
    else:
        shutil.move(old, new)
        return new


def remove_file(path: str):
    """Wrapper function so any file removal is logged"""
    logging.debug("[%s] Deleting file %s", sabnzbd.misc.caller_name(), path)
    os.remove(path)


@synchronized(DIR_LOCK)
def remove_dir(path: str):
    """Remove directory with retries for Win32"""
    logging.debug("[%s] Removing dir %s", sabnzbd.misc.caller_name(), path)
    if sabnzbd.WIN32:
        retries = 15
        while retries > 0:
            try:
                os.rmdir(path)
                return
            except OSError as err:
                # In use by another process
                if err.winerror == 32:
                    logging.debug("Retry delete %s", path)
                    retries -= 1
                else:
                    raise
            time.sleep(3)
        raise OSError("Failed to remove")
    else:
        os.rmdir(path)


@synchronized(DIR_LOCK)
def remove_all(path: str, pattern: str = "*", keep_folder: bool = False, recursive: bool = False):
    """Remove folder and all its content (optionally recursive)"""
    if path and os.path.exists(path):
        # Fast-remove the whole tree if recursive
        if pattern == "*" and not keep_folder and recursive:
            logging.debug("Removing dir recursively %s", path)
            try:
                shutil.rmtree(path)
            except:
                logging.info("Cannot remove folder %s", path, exc_info=True)
        else:
            # Get files based on pattern
            files = globber_full(path, pattern)
            if pattern == "*" and not sabnzbd.WIN32:
                files.extend(globber_full(path, ".*"))

            for f in files:
                if os.path.isfile(f):
                    try:
                        remove_file(f)
                    except:
                        logging.info("Cannot remove file %s", f, exc_info=True)
                elif recursive:
                    remove_all(f, pattern, False, True)
            if not keep_folder:
                try:
                    remove_dir(path)
                except:
                    logging.info("Cannot remove folder %s", path, exc_info=True)


##############################################################################
# Diskfree
##############################################################################
def disk_free_macos_clib_statfs64(directory: str) -> Tuple[int, int]:
    # MacOS only!
    # direct system call to c-lib's statfs(), not python's os.statvfs()
    # because statvfs() on MacOS has a rollover at 4TB (possibly a 32bit rollover with 10bit block size)
    # See https://bugs.python.org/issue43638
    # Based on code of pudquick and blackntan
    # Input: directory.
    # Output: disksize and available space, in bytes

    # format & parameters: on MacOS, see "man statfs", lines starting at
    # "struct statfs { /* when _DARWIN_FEATURE_64_BIT_INODE is defined */"
    class statfs64(ctypes.Structure):
        _fields_ = [
            ("f_bsize", ctypes.c_uint32),
            ("f_iosize", ctypes.c_int32),
            ("f_blocks", ctypes.c_uint64),
            ("f_bfree", ctypes.c_uint64),
            ("f_bavail", ctypes.c_uint64),
            ("f_files", ctypes.c_uint64),
            ("f_ffree", ctypes.c_uint64),
            ("f_fsid", ctypes.c_uint64),
            ("f_owner", ctypes.c_uint32),
            ("f_type", ctypes.c_uint32),
            ("f_flags", ctypes.c_uint32),
            ("f_fssubtype", ctypes.c_uint32),
            ("f_fstypename", ctypes.c_char * 16),
            ("f_mntonname", ctypes.c_char * 1024),
            ("f_mntfromname", ctypes.c_char * 1024),
            ("f_reserved", ctypes.c_uint32 * 8),
        ]

    fs_info64 = statfs64()  # set up the parameters to be filled out
    result = sabnzbd.MACOSLIBC.statfs64(
        ctypes.create_string_buffer(utob(directory)), ctypes.byref(fs_info64)
    )  # fs_info64 gets filled out via the byref()
    if result == 0:
        # result = 0: "Upon successful completion, a value of 0 is returned."
        return fs_info64.f_blocks * fs_info64.f_bsize, fs_info64.f_bavail * fs_info64.f_bsize
    else:
        # result = -1: "Otherwise, -1 is returned and the global variable errno is set to indicate the error."
        logging.debug("Call to MACOSLIBC.statfs64 not successful. Value of errno is %s", ctypes.get_errno())
        return 0, 0


def diskspace_base(dir_to_check: str) -> Tuple[float, float]:
    """Return amount of free and used diskspace in GBytes"""
    # Find first folder level that exists in the path
    x = "x"
    while x and not os.path.exists(dir_to_check):
        dir_to_check, x = os.path.split(dir_to_check)

    if sabnzbd.WIN32:
        # windows diskfree
        try:
            available, disk_size, total_free = win32api.GetDiskFreeSpaceEx(dir_to_check)
            return disk_size / GIGI, available / GIGI
        except:
            return 0.0, 0.0
    elif sabnzbd.MACOS:
        # MacOS diskfree ... via c-lib call statfs()
        disk_size, available = disk_free_macos_clib_statfs64(dir_to_check)
        return disk_size / GIGI, available / GIGI
    elif hasattr(os, "statvfs"):
        # posix diskfree
        try:
            s = os.statvfs(dir_to_check)
            if s.f_blocks < 0:
                disk_size = float(sys.maxsize) * float(s.f_frsize)
            else:
                disk_size = float(s.f_blocks) * float(s.f_frsize)
            if s.f_bavail < 0:
                available = float(sys.maxsize) * float(s.f_frsize)
            else:
                available = float(s.f_bavail) * float(s.f_frsize)
            return disk_size / GIGI, available / GIGI
        except:
            return 0.0, 0.0
    else:
        return 20.0, 10.0


# Store all results to speed things up
__DIRS_CHECKED = []
__DISKS_SAME = None
__LAST_DISK_RESULT = {"download_dir": (0.0, 0.0), "complete_dir": (0.0, 0.0)}
__LAST_DISK_CALL = 0


def diskspace(force: bool = False) -> Dict[str, Tuple[float, float]]:
    """Wrapper to cache results"""
    global __DIRS_CHECKED, __DISKS_SAME, __LAST_DISK_RESULT, __LAST_DISK_CALL

    # Reset everything when folders changed
    dirs_to_check = [sabnzbd.cfg.download_dir.get_path(), sabnzbd.cfg.complete_dir.get_path()]
    if __DIRS_CHECKED != dirs_to_check:
        __DIRS_CHECKED = dirs_to_check
        __DISKS_SAME = None
        __LAST_DISK_RESULT = {"download_dir": [], "complete_dir": []}
        __LAST_DISK_CALL = 0

    # When forced, ignore any cache to avoid problems in UI
    if force:
        __LAST_DISK_CALL = 0

    # Check against cache
    if time.time() > __LAST_DISK_CALL + 10.0:
        # Same disk? Then copy-paste
        __LAST_DISK_RESULT["download_dir"] = diskspace_base(sabnzbd.cfg.download_dir.get_path())
        __LAST_DISK_RESULT["complete_dir"] = (
            __LAST_DISK_RESULT["download_dir"] if __DISKS_SAME else diskspace_base(sabnzbd.cfg.complete_dir.get_path())
        )
        __LAST_DISK_CALL = time.time()

    # Do we know if it's same disk?
    if __DISKS_SAME is None:
        __DISKS_SAME = __LAST_DISK_RESULT["download_dir"] == __LAST_DISK_RESULT["complete_dir"]

    return __LAST_DISK_RESULT


def get_new_id(prefix, folder, check_list=None):
    """Return unique prefixed admin identifier within folder
    optionally making sure that id is not in the check_list.
    """
    for n in range(100):
        try:
            if not os.path.exists(folder):
                os.makedirs(folder)
            fd, path = tempfile.mkstemp("", "SABnzbd_%s_" % prefix, folder)
            os.close(fd)
            head, tail = os.path.split(path)
            if not check_list or tail not in check_list:
                return tail
        except:
            logging.error(T("Failure in tempfile.mkstemp"))
            logging.info("Traceback: ", exc_info=True)
            break
    # Cannot create unique id, crash the process
    raise IOError


def save_data(data, _id, path, do_pickle=True, silent=False):
    """Save data to a diskfile"""
    if not silent:
        logging.debug("[%s] Saving data for %s in %s", sabnzbd.misc.caller_name(), _id, path)
    path = os.path.join(path, _id)

    # We try 3 times, to avoid any dict or access problems
    for t in range(3):
        try:
            with open(path, "wb") as data_file:
                if do_pickle:
                    pickle.dump(data, data_file, protocol=pickle.HIGHEST_PROTOCOL)
                else:
                    data_file.write(data)
            break
        except:
            if silent:
                # This can happen, probably a removed folder
                pass
            elif t == 2:
                logging.error(T("Saving %s failed"), path)
                logging.info("Traceback: ", exc_info=True)
            else:
                # Wait a tiny bit before trying again
                time.sleep(0.1)


def load_data(data_id, path, remove=True, do_pickle=True, silent=False):
    """Read data from disk file"""
    path = os.path.join(path, data_id)

    if not os.path.exists(path):
        logging.info("[%s] %s missing", sabnzbd.misc.caller_name(), path)
        return None

    if not silent:
        logging.debug("[%s] Loading data for %s from %s", sabnzbd.misc.caller_name(), data_id, path)

    try:
        with open(path, "rb") as data_file:
            if do_pickle:
                try:
                    data = pickle.load(data_file, encoding=sabnzbd.encoding.CODEPAGE)
                except UnicodeDecodeError:
                    # Could be Python 2 data that we can load using old encoding
                    data = pickle.load(data_file, encoding="latin1")
            else:
                data = data_file.read()

        if remove:
            remove_file(path)
    except:
        logging.error(T("Loading %s failed"), path)
        logging.info("Traceback: ", exc_info=True)
        return None

    return data


def remove_data(_id: str, path: str):
    """Remove admin file"""
    path = os.path.join(path, _id)
    try:
        if os.path.exists(path):
            remove_file(path)
    except:
        logging.debug("Failed to remove %s", path)


def save_admin(data: Any, data_id: str):
    """Save data in admin folder in specified format"""
    logging.debug("[%s] Saving data for %s", sabnzbd.misc.caller_name(), data_id)
    save_data(data, data_id, sabnzbd.cfg.admin_dir.get_path())


def load_admin(data_id: str, remove=False, silent=False) -> Any:
    """Read data in admin folder in specified format"""
    logging.debug("[%s] Loading data for %s", sabnzbd.misc.caller_name(), data_id)
    return load_data(data_id, sabnzbd.cfg.admin_dir.get_path(), remove=remove, silent=silent)


def check_incomplete_vs_complete():
    """Make sure download_dir and complete_dir are not identical
    or that download_dir is not a subfolder of complete_dir"""
    complete = sabnzbd.cfg.complete_dir.get_path()
    if same_file(sabnzbd.cfg.download_dir.get_path(), complete):
        if real_path("X", sabnzbd.cfg.download_dir()) == long_path(sabnzbd.cfg.download_dir()):
            # Abs path, so set download_dir as an abs path inside the complete_dir
            sabnzbd.cfg.download_dir.set(os.path.join(complete, "incomplete"))
        else:
            sabnzbd.cfg.download_dir.set("incomplete")
        return False
    return True


def wait_for_download_folder():
    """Wait for download folder to become available"""
    while not sabnzbd.cfg.download_dir.test_path():
        logging.debug("Waiting for incomplete folder")
        time.sleep(2.0)


def backup_exists(filename: str) -> bool:
    """Return True if backup exists and no_dupes is set"""
    path = sabnzbd.cfg.nzb_backup_dir.get_path()
    return path and os.path.exists(os.path.join(path, filename + ".gz"))


def backup_nzb(nzb_path: str):
    """Backup NZB file, return path to nzb if it was saved"""
    if nzb_backup_dir := sabnzbd.cfg.nzb_backup_dir.get_path():
        logging.debug("Saving copy of %s in %s", get_filename(nzb_path), nzb_backup_dir)
        shutil.copy(nzb_path, nzb_backup_dir)


def save_compressed(folder: str, filename: str, data_fp: BinaryIO) -> str:
    """Save compressed NZB file in folder, return path to saved nzb file"""
    # Make sure it's a clean filename
    filename = sanitize_filename(filename)
    if filename.endswith(".nzb"):
        filename += ".gz"
    else:
        filename += ".nzb.gz"
    full_nzb_path = os.path.join(folder, filename)

    # Skip existing ones, as it might be queue-repair
    if not os.path.exists(full_nzb_path):
        logging.info("Saving %s", full_nzb_path)
        try:
            # Have to get around the path being put inside the tgz
            with open(full_nzb_path, "wb") as tgz_file:
                # We only need minimal compression to prevent huge files
                with gzip.GzipFile(filename, mode="wb", compresslevel=1, fileobj=tgz_file) as gzip_file:
                    shutil.copyfileobj(data_fp, gzip_file)
        except:
            logging.error(T("Saving %s failed"), full_nzb_path)
            logging.info("Traceback: ", exc_info=True)
    else:
        logging.info("Skipping existing file %s", full_nzb_path)

    return full_nzb_path


def directory_is_writable_with_file(mydir, myfilename):
    filename = os.path.join(mydir, myfilename)
    if os.path.exists(filename):
        try:
            os.remove(filename)
        except:
            return False
    try:
        with open(filename, "w") as f:
            f.write("Some random content")
        os.remove(filename)
        return True
    except:
        return False


def directory_is_writable(test_dir: str) -> bool:
    """Checks if dir is writable at all, and (on non-Windows), writable with special chars.
    Returns True if all OK, otherwise False"""
    if directory_is_writable_with_file(test_dir, "sab_test.txt"):
        if not sabnzbd.WIN32 and not directory_is_writable_with_file(test_dir, "sab_test \\ bla :: , bla.txt"):
            sabnzbd.misc.helpful_warning(
                T("%s is not writable with special character filenames. This can cause problems."), test_dir
            )
            return False
    else:
        sabnzbd.misc.helpful_warning(T("%s is not writable at all. This blocks downloads."), test_dir)
        return False
    return True
