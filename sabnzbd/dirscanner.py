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
sabnzbd.dirscanner - Scanner for Watched Folder
"""

import os
import time
import logging
import zipfile
import gzip
import bz2
import threading

import sabnzbd
from sabnzbd.constants import SCAN_FILE_NAME, VALID_ARCHIVES, VALID_NZB_FILES
import sabnzbd.utils.rarfile as rarfile
from sabnzbd.decorators import NzbQueueLocker
from sabnzbd.encoding import correct_unknown_encoding
from sabnzbd.newsunpack import is_sevenfile, SevenZip
import sabnzbd.nzbstuff as nzbstuff
import sabnzbd.filesystem as filesystem
import sabnzbd.config as config
import sabnzbd.cfg as cfg


def name_to_cat(fname, cat=None):
    """ Retrieve category from file name, but only if "cat" is None. """
    if cat is None and fname.startswith("{{"):
        n = fname.find("}}")
        if n > 2:
            cat = fname[2:n].strip()
            fname = fname[n + 2 :].strip()
            logging.debug("Job %s has category %s", fname, cat)

    return fname, cat


def compare_stat_tuple(tup1, tup2):
    """ Test equality of two stat-tuples, content-related parts only """
    if tup1.st_ino != tup2.st_ino:
        return False
    if tup1.st_size != tup2.st_size:
        return False
    if tup1.st_mtime != tup2.st_mtime:
        return False
    if tup1.st_ctime != tup2.st_ctime:
        return False
    return True


def is_archive(path):
    """ Check if file in path is an ZIP, RAR or 7z file
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
    elif is_sevenfile(path):
        try:
            zf = SevenZip(path)
            return 0, zf, ".7z"
        except:
            logging.info(T("Cannot read %s"), path, exc_info=True)
            return -1, None, ""
    else:
        logging.info("Archive %s is not a real archive!", os.path.basename(path))
        return 1, None, ""


def clean_file_list(inp_list, folder, files):
    """ Remove elements of "inp_list" not found in "files" """
    for path in sorted(inp_list.keys()):
        fld, name = os.path.split(path)
        if fld == folder:
            present = False
            for name in files:
                if os.path.join(folder, name) == path:
                    present = True
                    break
            if not present:
                del inp_list[path]


@NzbQueueLocker
def process_nzb_archive_file(
    filename,
    path,
    pp=None,
    script=None,
    cat=None,
    catdir=None,
    keep=False,
    priority=None,
    url="",
    nzbname=None,
    password=None,
    nzo_id=None,
):
    """ Analyse ZIP file and create job(s).
        Accepts ZIP files with ONLY nzb/nfo/folder files in it.
        returns (status, nzo_ids)
            status: -1==Error/Retry, 0==OK, 1==Ignore
    """
    nzo_ids = []
    if catdir is None:
        catdir = cat

    filename, cat = name_to_cat(filename, catdir)
    status, zf, extension = is_archive(path)

    if status != 0:
        return status, []

    status = 1
    names = zf.namelist()
    nzbcount = 0
    for name in names:
        name = name.lower()
        if name.endswith(".nzb"):
            status = 0
            nzbcount += 1

    if status == 0:
        if nzbcount != 1:
            nzbname = None
        for name in names:
            if name.lower().endswith(".nzb"):
                try:
                    data = correct_unknown_encoding(zf.read(name))
                except OSError:
                    logging.error(T("Cannot read %s"), name, exc_info=True)
                    zf.close()
                    return -1, []
                name = filesystem.setname_from_path(name)
                if data:
                    nzo = None
                    try:
                        nzo = nzbstuff.NzbObject(
                            name, pp, script, data, cat=cat, url=url, priority=priority, nzbname=nzbname
                        )
                        if not nzo.password:
                            nzo.password = password
                    except (TypeError, ValueError):
                        # Duplicate or empty, ignore
                        pass
                    except:
                        # Something else is wrong, show error
                        logging.error(T("Error while adding %s, removing"), name, exc_info=True)

                    if nzo:
                        if nzo_id:
                            # Re-use existing nzo_id, when a "future" job gets it payload
                            sabnzbd.nzbqueue.NzbQueue.do.remove(nzo_id, add_to_history=False, delete_all_data=False)
                            nzo.nzo_id = nzo_id
                            nzo_id = None
                        nzo_ids.append(sabnzbd.nzbqueue.NzbQueue.do.add(nzo))
                        nzo.update_rating()
        zf.close()
        try:
            if not keep:
                filesystem.remove_file(path)
        except OSError:
            logging.error(T("Error removing %s"), filesystem.clip_path(path))
            logging.info("Traceback: ", exc_info=True)
            status = 1
    else:
        zf.close()
        status = 1

    return status, nzo_ids


@NzbQueueLocker
def process_single_nzb(
    filename,
    path,
    pp=None,
    script=None,
    cat=None,
    catdir=None,
    keep=False,
    priority=None,
    nzbname=None,
    reuse=False,
    nzo_info=None,
    dup_check=True,
    url="",
    password=None,
    nzo_id=None,
):
    """ Analyze file and create a job from it
        Supports NZB, NZB.BZ2, NZB.GZ and GZ.NZB-in-disguise
        returns (status, nzo_ids)
            status: -2==Error/retry, -1==Error, 0==OK, 1==OK-but-ignorecannot-delete
    """
    nzo_ids = []
    if catdir is None:
        catdir = cat

    try:
        with open(path, "rb") as nzb_file:
            check_bytes = nzb_file.read(2)

        if check_bytes == b"\x1f\x8b":
            # gzip file or gzip in disguise
            name = filename.replace(".nzb.gz", ".nzb")
            nzb_reader_handler = gzip.GzipFile
        elif check_bytes == b"BZ":
            # bz2 file or bz2 in disguise
            name = filename.replace(".nzb.bz2", ".nzb")
            nzb_reader_handler = bz2.BZ2File
        else:
            name = filename
            nzb_reader_handler = open

        # Let's get some data and hope we can decode it
        with nzb_reader_handler(path, "rb") as nzb_file:
            data = correct_unknown_encoding(nzb_file.read())

    except:
        logging.warning(T("Cannot read %s"), filesystem.clip_path(path))
        logging.info("Traceback: ", exc_info=True)
        return -2, nzo_ids

    if name:
        name, cat = name_to_cat(name, catdir)
        # The name is used as the name of the folder, so sanitize it using folder specific santization
        if not nzbname:
            # Prevent embedded password from being damaged by sanitize and trimming
            nzbname = os.path.split(name)[1]

    try:
        nzo = nzbstuff.NzbObject(
            name,
            pp,
            script,
            data,
            cat=cat,
            priority=priority,
            nzbname=nzbname,
            nzo_info=nzo_info,
            url=url,
            reuse=reuse,
            dup_check=dup_check,
        )
        if not nzo.password:
            nzo.password = password
    except TypeError:
        # Duplicate, ignore
        if nzo_id:
            sabnzbd.nzbqueue.NzbQueue.do.remove(nzo_id, add_to_history=False)
        nzo = None
    except ValueError:
        # Empty, but correct file
        return -1, nzo_ids
    except:
        if data.find("<nzb") >= 0 > data.find("</nzb"):
            # Looks like an incomplete file, retry
            return -2, nzo_ids
        else:
            # Something else is wrong, show error
            logging.error(T("Error while adding %s, removing"), name, exc_info=True)
            return -1, nzo_ids

    if nzo:
        if nzo_id:
            # Re-use existing nzo_id, when a "future" job gets it payload
            sabnzbd.nzbqueue.NzbQueue.do.remove(nzo_id, add_to_history=False, delete_all_data=False)
            nzo.nzo_id = nzo_id
        nzo_ids.append(sabnzbd.nzbqueue.NzbQueue.do.add(nzo, quiet=reuse))
        nzo.update_rating()
    try:
        if not keep:
            filesystem.remove_file(path)
    except OSError:
        logging.error(T("Error removing %s"), filesystem.clip_path(path))
        logging.info("Traceback: ", exc_info=True)
        return 1, nzo_ids

    return 0, nzo_ids


class DirScanner(threading.Thread):
    """ Thread that periodically scans a given directory and picks up any
        valid NZB, NZB.GZ ZIP-with-only-NZB and even NZB.GZ named as .NZB
        Candidates which turned out wrong, will be remembered and skipped in
        subsequent scans, unless changed.
    """

    do = None  # Access to instance of DirScanner

    def __init__(self):
        threading.Thread.__init__(self)

        self.newdir()
        try:
            dirscan_dir, self.ignored, self.suspected = sabnzbd.load_admin(SCAN_FILE_NAME)
            if dirscan_dir != self.dirscan_dir:
                self.ignored = {}
                self.suspected = {}
        except:
            self.ignored = {}  # Will hold all unusable files and the
            # successfully processed ones that cannot be deleted
            self.suspected = {}  # Will hold name/attributes of suspected candidates

        self.shutdown = False
        self.error_reported = False  # Prevents mulitple reporting of missing watched folder
        self.dirscan_dir = cfg.dirscan_dir.get_path()
        self.dirscan_speed = cfg.dirscan_speed()
        self.busy = False
        self.trigger = False
        cfg.dirscan_dir.callback(self.newdir)
        cfg.dirscan_speed.callback(self.newspeed)
        DirScanner.do = self

    def newdir(self):
        """ We're notified of a dir change """
        self.ignored = {}
        self.suspected = {}
        self.dirscan_dir = cfg.dirscan_dir.get_path()
        self.dirscan_speed = cfg.dirscan_speed()

    def newspeed(self):
        """ We're notified of a scan speed change """
        self.dirscan_speed = cfg.dirscan_speed()
        self.trigger = True

    def stop(self):
        """ Stop the dir scanner """
        logging.info("Dirscanner shutting down")
        self.shutdown = True

    def save(self):
        """ Save dir scanner bookkeeping """
        sabnzbd.save_admin((self.dirscan_dir, self.ignored, self.suspected), SCAN_FILE_NAME)

    def run(self):
        """ Start the scanner """
        logging.info("Dirscanner starting up")
        self.shutdown = False

        while not self.shutdown:
            # Use variable scan delay
            x = max(self.dirscan_speed, 1)
            while (x > 0) and not self.shutdown and not self.trigger:
                time.sleep(1.0)
                x = x - 1

            self.trigger = False
            if self.dirscan_speed and not self.shutdown:
                self.scan()

    def scan(self):
        """ Do one scan of the watched folder """

        def run_dir(folder, catdir):
            try:
                files = os.listdir(folder)
            except OSError:
                if not self.error_reported and not catdir:
                    logging.error(T("Cannot read Watched Folder %s"), filesystem.clip_path(folder))
                    self.error_reported = True
                files = []

            for filename in files:
                path = os.path.join(folder, filename)
                if os.path.isdir(path) or path in self.ignored or filename[0] == ".":
                    continue

                ext = os.path.splitext(path)[1].lower()
                candidate = ext in VALID_NZB_FILES + VALID_ARCHIVES
                if candidate:
                    try:
                        stat_tuple = os.stat(path)
                    except OSError:
                        continue
                else:
                    self.ignored[path] = 1

                if path in self.suspected:
                    if compare_stat_tuple(self.suspected[path], stat_tuple):
                        # Suspected file still has the same attributes
                        continue
                    else:
                        del self.suspected[path]

                if candidate and stat_tuple.st_size > 0:
                    logging.info("Trying to import %s", path)

                    # Wait until the attributes are stable for 1 second
                    # but give up after 3 sec
                    stable = False
                    for n in range(3):
                        time.sleep(1.0)
                        try:
                            stat_tuple_tmp = os.stat(path)
                        except OSError:
                            continue
                        if compare_stat_tuple(stat_tuple, stat_tuple_tmp):
                            stable = True
                            break
                        else:
                            stat_tuple = stat_tuple_tmp

                    if not stable:
                        continue

                    # Handle archive files, but only when containing just NZB files
                    if ext in VALID_ARCHIVES:
                        res, nzo_ids = process_nzb_archive_file(filename, path, catdir=catdir, url=path)
                        if res == -1:
                            self.suspected[path] = stat_tuple
                        elif res == 0:
                            self.error_reported = False
                        else:
                            self.ignored[path] = 1

                    # Handle .nzb, .nzb.gz or gzip-disguised-as-nzb or .bz2
                    elif ext == ".nzb" or filename.lower().endswith(".nzb.gz") or filename.lower().endswith(".nzb.bz2"):
                        res, nzo_id = process_single_nzb(filename, path, catdir=catdir, url=path)
                        if res < 0:
                            self.suspected[path] = stat_tuple
                        elif res == 0:
                            self.error_reported = False
                        else:
                            self.ignored[path] = 1

                    else:
                        self.ignored[path] = 1

            clean_file_list(self.ignored, folder, files)
            clean_file_list(self.suspected, folder, files)

        if not self.busy:
            self.busy = True
            dirscan_dir = self.dirscan_dir
            if dirscan_dir and not sabnzbd.PAUSED_ALL:
                run_dir(dirscan_dir, None)

                try:
                    dirscan_list = os.listdir(dirscan_dir)
                except OSError:
                    if not self.error_reported:
                        logging.error(T("Cannot read Watched Folder %s"), filesystem.clip_path(dirscan_dir))
                        self.error_reported = True
                    dirscan_list = []

                cats = config.get_categories()
                for dd in dirscan_list:
                    dpath = os.path.join(dirscan_dir, dd)
                    if os.path.isdir(dpath) and dd.lower() in cats:
                        run_dir(dpath, dd.lower())
            self.busy = False


def dirscan():
    """ Wrapper required for scheduler """
    logging.info("Scheduled or manual watched folder scan")
    DirScanner.do.scan()
