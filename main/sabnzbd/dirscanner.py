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
sabnzbd.dirscanner - Scanner for Watched Folder
"""
__NAME__ = "sabnzbd.dirscanner"

import os
import sys
import time
import logging
import urllib
import re
import zipfile
import gzip
import webbrowser
import tempfile
import shutil
import threading

import sabnzbd
from sabnzbd.decorators import *
from sabnzbd.constants import *
import sabnzbd.nzbstuff as nzbstuff
import sabnzbd.utils.rarfile as rarfile
import sabnzbd.misc as misc


def CompareStat(tup1, tup2):
    """ Test equality of two stat-tuples, content-related parts only """
    if tup1.st_ino   != tup2.st_ino:   return False
    if tup1.st_size  != tup2.st_size:  return False
    if tup1.st_mtime != tup2.st_mtime: return False
    if tup1.st_ctime != tup2.st_ctime: return False
    return True


def ProcessArchiveFile(filename, path, pp=None, script=None, cat=None, catdir=None, priority=NORMAL_PRIORITY):
    """ Analyse ZIP file and create job(s).
        Accepts ZIP files with ONLY nzb/nfo/folder files in it.
        returns: -1==Error/Retry, 0==OK, 1==Ignore
    """
    if catdir == None:
        catdir = cat

    _cat, name, _pp, _script = misc.Cat2OptsDef(filename, catdir)
    if cat == None: cat = _cat
    if pp == None: pp = _pp
    if script == None: script = _script

    if path.lower().endswith('.zip'):
        try:
            zf = zipfile.ZipFile(path)
        except:
            return -1
    elif rarfile.is_rarfile(path):
        try:
            zf = rarfile.RarFile(path)
        except:
            return -1
    else:
        return 1

    status = 1
    names = zf.namelist()
    names.sort()
    for name in names:
        name = name.lower()
        if not (name.endswith('.nzb') or name.endswith('.nfo') or name.endswith('/')):
            status = 1
            break
        elif name.endswith('.nzb'):
            status = 0
    if status == 0:
        for name in names:
            if name.lower().endswith('.nzb'):
                try:
                    data = zf.read(name)
                except:
                    zf.close()
                    return -1
                name = re.sub(r'\[.*nzbmatrix.com\]', '', name)
                name = os.path.basename(name)
                name = sanitize_filename(name)
                if data:
                    try:
                        nzo = nzbstuff.NzbObject(name, pp, script, data, cat=cat, priority=priority)
                    except:
                        nzo = None
                    if nzo:
                        sabnzbd.add_nzo(nzo)
        zf.close()
        try:
            os.remove(path)
        except:
            logging.error("[%s] Error removing %s", __NAME__, path)
            logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
            status = 1
    else:
        zf.close()
        status = 1

    return status


def ProcessSingleFile(filename, path, pp=None, script=None, cat=None, catdir=None, keep=False, priority=NORMAL_PRIORITY):
    """ Analyse file and create a job from it
        Supports NZB, NZB.GZ and GZ.NZB-in-disguise
        returns: -2==Error/retry, -1==Error, 0==OK, 1==OK-but-ignorecannot-delete
    """
    if catdir == None:
        catdir = cat

    try:
        f = open(path, 'rb')
        b1 = f.read(1)
        b2 = f.read(1)
        f.close()

        if (b1 == '\x1f' and b2 == '\x8b'):
            # gzip file or gzip in disguise
            name = filename.replace('.nzb.gz', '.nzb')
            f = gzip.GzipFile(path, 'rb')
        else:
            name = filename
            f = open(path, 'rb')
        data = f.read()
        f.close()
    except:
        logging.warning('[%s] Cannot read %s', __NAME__, path)
        logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
        return -2

    _cat, name, _pp, _script = misc.Cat2OptsDef(name, catdir)
    if cat == None: cat = _cat
    if pp == None: pp = _pp
    if script == None: script = _script

    try:
        nzo = nzbstuff.NzbObject(name, pp, script, data, cat=cat, priority=priority)
    except TypeError:
        # Duplicate, ignore
        nzo = None
    except:
        if data.find("<nzb") >= 0 and data.find("</nzb") < 0:
            # Looks like an incomplete file, retry
            return -2
        else:
            return -1

    if nzo:
        sabnzbd.add_nzo(nzo)
    try:
        if not keep: os.remove(path)
    except:
        logging.error("[%s] Error removing %s", __NAME__, path)
        logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
        return 1

    return 0


def CleanList(list, folder, files):
    """ Remove elements of "list" not found in "files" """
    for path in sorted(list.keys()):
        fld, name = os.path.split(path)
        if fld == folder:
            present = False
            for name in files:
                if os.path.join(folder, name) == path:
                    present = True
                    break
            if not present:
                del list[path]
    

#------------------------------------------------------------------------------
class DirScanner(threading.Thread):
    """
    Thread that periodically scans a given directoty and picks up any
    valid NZB, NZB.GZ ZIP-with-only-NZB and even NZB.GZ named as .NZB
    Candidates which turned out wrong, will be remembered and skipped in
    subsequent scans, unless changed.
    """
    def __init__(self, dirscan_dir, dirscan_speed):
        threading.Thread.__init__(self)

        self.dirscan_dir = dirscan_dir
        self.dirscan_speed = dirscan_speed

        try:
            dir, self.ignored, self.suspected = sabnzbd.load_data(SCAN_FILE_NAME, remove = False)
            if dir != dirscan_dir:
                self.ignored = {}
                self.suspected = {}
        except:
            self.ignored = {}   # Will hold all unusable files and the
                                # successfully processed ones that cannot be deleted
            self.suspected = {} # Will hold name/attributes of suspected candidates

        self.shutdown = False
        self.error_reported = False # Prevents mulitple reporting of missing watched folder

    def stop(self):
        self.save()
        logging.info('[%s] Dirscanner shutting down', __NAME__)
        self.shutdown = True

    def save(self):
        sabnzbd.save_data((self.dirscan_dir, self.ignored, self.suspected), sabnzbd.SCAN_FILE_NAME)

    def run(self):
        def run_dir(folder, catdir):
            try:
                files = os.listdir(folder)
            except:
                if not self.error_reported and not catdir:
                    logging.error("Cannot read Watched Folder %s", folder)
                    self.error_reported = True
                files = []

            for filename in files:
                path = os.path.join(folder, filename)
                if os.path.isdir(path) or path in self.ignored:
                    continue

                root, ext = os.path.splitext(path)
                ext = ext.lower()
                priority = cfg.DIRSCAN_PRIORITY.get()
                candidate = ext in ('.nzb', '.zip', '.gz', '.rar')
                if candidate:
                    try:
                        stat_tuple = os.stat(path)
                    except:
                        continue
                else:
                    self.ignored[path] = 1

                if path in self.suspected:
                    if CompareStat(self.suspected[path], stat_tuple):
                        # Suspected file still has the same attributes
                        continue
                    else:
                        del self.suspected[path]

                if candidate and stat_tuple.st_size > 0:
                    logging.info('[%s] Trying to import %s', __NAME__, path)

                    # Wait until the attributes are stable for 1 second
                    # but give up after 3 sec
                    stable = False
                    for n in xrange(3):
                        time.sleep(1.0)
                        try:
                            stat_tuple_tmp = os.stat(path)
                        except:
                            continue
                        if CompareStat(stat_tuple, stat_tuple_tmp):
                            stable = True
                            break
                        else:
                            stat_tuple = stat_tuple_tmp

                    if not stable:
                        continue

                    # Handle ZIP files, but only when containing just NZB files
                    if ext in ('.zip', '.rar') :
                        res = ProcessArchiveFile(filename, path, catdir=catdir, priority=priority)
                        if res == -1:
                            self.suspected[path] = stat_tuple
                        elif res == 0:
                            self.error_reported = False
                        else:
                            self.ignored[path] = 1

                    # Handle .nzb, .nzb.gz or gzip-disguised-as-nzb
                    elif ext == '.nzb' or filename.lower().endswith('.nzb.gz'):
                        res = ProcessSingleFile(filename, path, catdir=catdir, priority=priority)
                        if res < 0:
                            self.suspected[path] = stat_tuple
                        elif res == 0:
                            self.error_reported = False
                        else:
                            self.ignored[path] = 1

                    else:
                        self.ignored[path] = 1

            CleanList(self.ignored, folder, files)
            CleanList(self.suspected, folder, files)

        logging.info('[%s] Dirscanner starting up', __NAME__)
        self.shutdown = False

        while not self.shutdown:
            # Use variable scan delay
            x = self.dirscan_speed
            while (x > 0) and not self.shutdown:
                time.sleep(1.0)
                x = x - 1

            if not self.shutdown:
                run_dir(self.dirscan_dir, None)

                try:
                    list = os.listdir(self.dirscan_dir)
                except:
                    if not self.error_reported:
                        logging.error("Cannot read Watched Folder %s", folder)
                        logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
                        self.error_reported = True
                    list = []

                for dd in list:
                    dpath = os.path.join(self.dirscan_dir, dd)
                    if os.path.isdir(dpath) and dd.lower() in sabnzbd.CFG['categories']:
                        run_dir(dpath, dd.lower())

