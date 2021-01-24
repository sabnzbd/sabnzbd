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

import os
import sys
import logging
import re
import shutil
import threading
import time
import fnmatch
import stat
import zipfile
from typing import Union, List, Tuple, Any, Dict, Optional

try:
    import win32api
    import win32file
except ImportError:
    pass

import sabnzbd
from sabnzbd.decorators import synchronized
from sabnzbd.constants import FUTURE_Q_FOLDER, JOB_ADMIN, GIGI, DEF_FILE_MAX
from sabnzbd.encoding import correct_unknown_encoding
from sabnzbd.utils import rarfile

# For Windows: determine executable extensions
if os.name == "nt":
    PATHEXT = os.environ.get("PATHEXT", "").lower().split(";")
else:
    PATHEXT = []


def get_ext(filename: str) -> str:
    """ Return lowercased file extension """
    try:
        return os.path.splitext(filename)[1].lower()
    except:
        return ""


def get_filename(path: str) -> str:
    """ Return path without the file extension """
    try:
        return os.path.split(path)[1]
    except:
        return ""


def setname_from_path(path: str) -> str:
    """ Get the setname from a path """
    return os.path.splitext(os.path.basename(path))[0]


def is_writable(path: str) -> bool:
    """ Return True is file is writable (also when non-existent) """
    if os.path.isfile(path):
        return bool(os.stat(path).st_mode & stat.S_IWUSR)
    else:
        return True


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


CH_ILLEGAL = "/"
CH_LEGAL = "+"
CH_ILLEGAL_WIN = '\\/<>?*|"\t:'
CH_LEGAL_WIN = "++{}!@#'+-"


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

    if ":" in name and sabnzbd.DARWIN:
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
    if len(name.encode("utf8")) + len(ext.encode("utf8")) > DEF_FILE_MAX:
        logging.debug("Filename %s is too long, so truncating", name + ext)
        # Too long filenames are often caused by incorrect non-ascii chars,
        # so brute-force remove those non-ascii chars
        name = str(name.encode("ascii", "ignore"), "utf-8")
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

    repl = sabnzbd.cfg.replace_illegal()
    lst = []
    for ch in name.strip():
        if ch in illegal:
            if repl:
                ch = legal[illegal.find(ch)]
                lst.append(ch)
        else:
            lst.append(ch)
    name = "".join(lst)
    name = name.strip()

    if sabnzbd.WIN32 or sabnzbd.cfg.sanitize_safe():
        name = replace_win_devices(name)

    if len(name) >= sabnzbd.cfg.max_foldername_length():
        name = name[: sabnzbd.cfg.max_foldername_length()]

    # And finally, make sure it doesn't end in a dot
    if name != "." and name != "..":
        name = name.rstrip(".")
    if not name:
        name = "unknown"

    return name


def sanitize_and_trim_path(path: str) -> str:
    """ Remove illegal characters and trim element size """
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


def sanitize_files_in_folder(folder):
    """Sanitize each file in the folder, return list of new names"""
    lst = []
    for root, _, files in os.walk(folder):
        for file_ in files:
            path = os.path.join(root, file_)
            new_path = os.path.join(root, sanitize_filename(file_))
            if path != new_path:
                try:
                    os.rename(path, new_path)
                    path = new_path
                except:
                    logging.debug("Cannot rename %s to %s", path, new_path)
            lst.append(path)
    return lst


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
    name: str, loc: str, path: str, umask: bool = False, writable: bool = True
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
            logging.info("%s directory: %s does not exist, try to create it", name, my_dir)
            if not create_all_dirs(my_dir, umask):
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
    if sabnzbd.WIN32 or sabnzbd.DARWIN:
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


def is_archive(path: str) -> Tuple[int, Any, str]:
    """Check if file in path is an ZIP, RAR or 7z file
    :param path: path to file
    :return: (zf, status, expected_extension)
            status: -1==Error/Retry, 0==OK, 1==Ignore
    """
    if zipfile.is_zipfile(path):
        try:
            zf = zipfile.ZipFile(path)
            return 0, zf, ".zip"
        except:
            logging.info(T("Cannot read %s"), path, exc_info=True)
            return -1, None, ""
    elif rarfile.is_rarfile(path):
        try:
            # Set path to tool to open it
            rarfile.UNRAR_TOOL = sabnzbd.newsunpack.RAR_COMMAND
            zf = rarfile.RarFile(path)
            return 0, zf, ".rar"
        except:
            logging.info(T("Cannot read %s"), path, exc_info=True)
            return -1, None, ""
    elif sabnzbd.newsunpack.is_sevenfile(path):
        try:
            zf = sabnzbd.newsunpack.SevenZip(path)
            return 0, zf, ".7z"
        except:
            logging.info(T("Cannot read %s"), path, exc_info=True)
            return -1, None, ""
    else:
        logging.info("Archive %s is not a real archive!", os.path.basename(path))
        return 1, None, ""


def check_mount(path: str) -> bool:
    """Return False if volume isn't mounted on Linux or macOS
    Retry 6 times with an interval of 1 sec.
    """
    if sabnzbd.DARWIN:
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


def safe_fnmatch(f: str, pattern: str) -> bool:
    """fnmatch will fail if the pattern contains any of it's
    key characters, like [, ] or !.
    """
    try:
        return fnmatch.fnmatch(f, pattern)
    except re.error:
        return False


def globber(path: str, pattern: str = "*") -> List[str]:
    """ Return matching base file/folder names in folder `path` """
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        return [f for f in os.listdir(path) if safe_fnmatch(f, pattern)]
    return []


def globber_full(path: str, pattern: str = "*") -> List[str]:
    """ Return matching full file/folder names in folder `path` """
    # Cannot use glob.glob() because it doesn't support Windows long name notation
    if os.path.exists(path):
        return [os.path.join(path, f) for f in os.listdir(path) if safe_fnmatch(f, pattern)]
    return []


def fix_unix_encoding(folder: str):
    """Fix bad name encoding for Unix systems
    This happens for example when files are created
    on Windows but unpacked/repaired on linux
    """
    if not sabnzbd.WIN32 and not sabnzbd.DARWIN:
        for root, dirs, files in os.walk(folder):
            for name in files:
                new_name = correct_unknown_encoding(name)
                if name != new_name:
                    try:
                        renamer(os.path.join(root, name), os.path.join(root, new_name))
                    except:
                        logging.info("Cannot correct name of %s", os.path.join(root, name))


def is_valid_script(basename: str) -> bool:
    """ Determine if 'basename' is a valid script """
    return basename in list_scripts(default=False, none=False)


def list_scripts(default: bool = False, none: bool = True) -> List[str]:
    """ Return a list of script names, optionally with 'Default' added """
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
    """ Return full script path, if any valid script exists, else None """
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


def set_chmod(path: str, permissions: int, report: bool):
    """ Set 'permissions' on 'path', report any errors when 'report' is True """
    try:
        logging.debug("Applying permissions %s (octal) to %s", oct(permissions), path)
        os.chmod(path, permissions)
    except:
        lpath = path.lower()
        if report and ".appledouble" not in lpath and ".ds_store" not in lpath:
            logging.error(T("Cannot change permissions of %s"), clip_path(path))
            logging.info("Traceback: ", exc_info=True)


def set_permissions(path: str, recursive: bool = True):
    """ Give folder tree and its files their proper permissions """
    if not sabnzbd.WIN32:
        umask = sabnzbd.cfg.umask()
        try:
            # Make sure that user R+W+X is on
            umask = int(umask, 8) | int("0700", 8)
            report = True
        except ValueError:
            # No or no valid permissions
            # Use the effective permissions of the session
            # Don't report errors (because the system might not support it)
            umask = int("0777", 8) & (sabnzbd.ORG_UMASK ^ int("0777", 8))
            report = False

        # Remove executable and special permissions for files
        umask_file = umask & int("0666", 8)

        if os.path.isdir(path):
            if recursive:
                # Parse the dir/file tree and set permissions
                for root, _dirs, files in os.walk(path):
                    set_chmod(root, umask, report)
                    for name in files:
                        set_chmod(os.path.join(root, name), umask_file, report)
            else:
                set_chmod(path, umask, report)
        else:
            set_chmod(path, umask_file, report)


def userxbit(filename: str) -> bool:
    """Returns boolean if the x-bit for user is set on the given file.
    This is a workaround: os.access(filename, os.X_OK) does not work
    on certain mounted file systems. Does not work at all on Windows.
    """
    # rwx rwx rwx
    # 876 543 210      # we want bit 6 from the right, counting from 0
    userxbit = 1 << 6  # bit 6
    rwxbits = os.stat(filename)[0]  # the first element of os.stat() is "mode"
    # do logical AND, check if it is not 0:
    xbitset = (rwxbits & userxbit) > 0
    return xbitset


def clip_path(path: str) -> str:
    r""" Remove \\?\ or \\?\UNC\ prefix from Windows path """
    if sabnzbd.WIN32 and path and "?" in path:
        path = path.replace("\\\\?\\UNC\\", "\\\\", 1).replace("\\\\?\\", "", 1)
    return path


def long_path(path: str) -> str:
    """ For Windows, convert to long style path; others, return same path """
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
def create_all_dirs(path: str, apply_umask: bool = False) -> Union[str, bool]:
    """Create all required path elements and set umask on all
    The umask argument is ignored on Windows
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
            # We need to build the directory recursively so we can
            # apply permissions to only the newly created folders
            # We cannot use os.makedirs() as it could ignore the mode
            umask = sabnzbd.cfg.umask()
            if umask:
                umask = int(umask, 8) | int("0700", 8)

            # Build path from root
            path_part_combined = "/"
            for path_part in path.split("/"):
                if path_part:
                    path_part_combined = os.path.join(path_part_combined, path_part)
                    # Only create if it doesn't exist
                    if not os.path.exists(path_part_combined):
                        os.mkdir(path_part_combined)
                        # Try to set permissions if desired, ignore failures
                        if umask and apply_umask:
                            set_chmod(path_part_combined, umask, report=False)
        return path
    except OSError:
        logging.error(T("Failed making (%s)"), clip_path(path), exc_info=True)
        return False


@synchronized(DIR_LOCK)
def get_unique_path(dirpath: str, n: int = 0, create_dir: bool = True) -> str:
    """ Determine a unique folder or filename """

    if not check_mount(dirpath):
        return dirpath

    path = dirpath
    if n:
        path = "%s.%s" % (dirpath, n)

    if not os.path.exists(path):
        if create_dir:
            return create_all_dirs(path, apply_umask=True)
        else:
            return path
    else:
        return get_unique_path(dirpath, n=n + 1, create_dir=create_dir)


@synchronized(DIR_LOCK)
def get_unique_filename(path: str) -> str:
    """Check if path is unique.
    If not, add number like: "/path/name.NUM.ext".
    """
    num = 1
    new_path, fname = os.path.split(path)
    name, ext = os.path.splitext(fname)
    while os.path.exists(path):
        fname = "%s.%d%s" % (name, num, ext)
        num += 1
        path = os.path.join(new_path, fname)
    return path


@synchronized(DIR_LOCK)
def listdir_full(input_dir: str, recursive: bool = True) -> List[str]:
    """ List all files in dirs and sub-dirs """
    filelist = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if ".AppleDouble" not in root and ".DS_Store" not in root:
                p = os.path.join(root, file)
                filelist.append(p)
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
    if overwrite and os.path.exists(new_path):
        try:
            os.remove(new_path)
        except:
            overwrite = False
    if not overwrite:
        new_path = get_unique_filename(new_path)

    if new_path:
        logging.debug("Moving (overwrite: %s) %s => %s", overwrite, path, new_path)
        try:
            # First try cheap rename
            renamer(path, new_path)
        except:
            # Cannot rename, try copying
            logging.debug("File could not be renamed, trying copying: %s", path)
            try:
                create_all_dirs(os.path.dirname(new_path), apply_umask=True)
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
    """ Remove all empty folders inside (and including) 'path' """
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
def get_filepath(path: str, nzo, filename: str):
    """ Create unique filepath """
    # This procedure is only used by the Assembler thread
    # It does no umask setting
    # It uses the dir_lock for the (rare) case that the
    # download_dir is equal to the complete_dir.
    new_dirname = dirname = nzo.work_name
    if not nzo.created:
        for n in range(200):
            new_dirname = dirname
            if n:
                new_dirname += "." + str(n)
            try:
                os.mkdir(os.path.join(path, new_dirname))
                break
            except:
                pass
        nzo.work_name = new_dirname
        nzo.created = True

    filepath = os.path.join(os.path.join(path, new_dirname), filename)
    filepath, ext = os.path.splitext(filepath)
    n = 0
    while True:
        if n:
            fullpath = "%s.%d%s" % (filepath, n, ext)
        else:
            fullpath = filepath + ext
        if os.path.exists(fullpath):
            n = n + 1
        else:
            break

    return fullpath


@synchronized(DIR_LOCK)
def renamer(old: str, new: str):
    """ Rename file/folder with retries for Win32 """
    # Sanitize last part of new name
    path, name = os.path.split(new)
    new = os.path.join(path, sanitize_filename(name))

    # Skip if nothing changes
    if old == new:
        return

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
                return
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
        raise OSError("Failed to rename")
    else:
        shutil.move(old, new)


def remove_file(path: str):
    """ Wrapper function so any file removal is logged """
    logging.debug("[%s] Deleting file %s", sabnzbd.misc.caller_name(), path)
    os.remove(path)


@synchronized(DIR_LOCK)
def remove_dir(path: str):
    """ Remove directory with retries for Win32 """
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
    """ Remove folder and all its content (optionally recursive) """
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
def diskspace_base(dir_to_check: str) -> Tuple[float, float]:
    """ Return amount of free and used diskspace in GBytes """
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
    """ Wrapper to cache results """
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
