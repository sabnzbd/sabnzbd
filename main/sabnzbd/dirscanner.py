#!/usr/bin/python -OO
# Copyright 2008-2009 The SABnzbd-Team <team@sabnzbd.org>
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
import re
import zipfile
import gzip
import threading

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.utils.rarfile import is_rarfile, RarFile
import sabnzbd.nzbstuff as nzbstuff
import sabnzbd.misc as misc
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.nzbqueue
from sabnzbd.lang import Ta

################################################################################
# Wrapper functions
################################################################################

__SCANNER = None  # Global pointer to dir-scanner instance

def init():
    global __SCANNER
    if __SCANNER:
        __SCANNER.__init__()
    else:
        __SCANNER = DirScanner()

def start():
    global __SCANNER
    if __SCANNER: __SCANNER.start()

def stop():
    global __SCANNER
    if __SCANNER:
        __SCANNER.stop()
        try:
            __SCANNER.join()
        except:
            pass

def save():
    global __SCANNER
    if __SCANNER: __SCANNER.save()

def alive():
    global __SCANNER
    if __SCANNER:
        return __SCANNER.isAlive()
    else:
        return False


################################################################################
# Body
################################################################################

RE_CAT = re.compile(r'^{{(\w+)}}(.+)') # Category prefix
def name_to_cat(fname, cat=None):
    """
        Translate Get options associated with the category.
        Category options have priority over default options.
    """
    if cat is None:
        m = RE_CAT.search(fname)
        if m and m.group(1) and m.group(2):
            cat = m.group(1).lower()
            fname = m.group(2)
            logging.debug('Job %s has category %s', fname, cat)

    return fname, cat


def CompareStat(tup1, tup2):
    """ Test equality of two stat-tuples, content-related parts only """
    if tup1.st_ino   != tup2.st_ino:   return False
    if tup1.st_size  != tup2.st_size:  return False
    if tup1.st_mtime != tup2.st_mtime: return False
    if tup1.st_ctime != tup2.st_ctime: return False
    return True


def ProcessArchiveFile(filename, path, pp=None, script=None, cat=None, catdir=None, keep=False, priority=None):
    """ Analyse ZIP file and create job(s).
        Accepts ZIP files with ONLY nzb/nfo/folder files in it.
        returns: -1==Error/Retry, 0==OK, 1==Ignore
    """
    if catdir is None:
        catdir = cat

    filename, cat = name_to_cat(filename, catdir)

    if path.lower().endswith('.zip'):
        try:
            zf = zipfile.ZipFile(path)
        except:
            return -1
    elif is_rarfile(path):
        try:
            zf = RarFile(path)
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
                name = misc.sanitize_foldername(name)
                if data:
                    try:
                        nzo = nzbstuff.NzbObject(name, 0, pp, script, data, cat=cat, priority=priority)
                    except:
                        nzo = None
                    if nzo:
                        sabnzbd.nzbqueue.add_nzo(nzo)
        zf.close()
        try:
            if not keep: os.remove(path)
        except:
            logging.error(Ta('error-remove@1'), path)
            logging.debug("Traceback: ", exc_info = True)
            status = 1
    else:
        zf.close()
        status = 1

    return status


def ProcessSingleFile(filename, path, pp=None, script=None, cat=None, catdir=None, keep=False, priority=None, nzbname=None):
    """ Analyse file and create a job from it
        Supports NZB, NZB.GZ and GZ.NZB-in-disguise
        returns: -2==Error/retry, -1==Error, 0==OK, 1==OK-but-ignorecannot-delete
    """
    if catdir is None:
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
        logging.warning(Ta('warn-noRead@1'), path)
        logging.debug("Traceback: ", exc_info = True)
        return -2


    if name:
        name, cat = name_to_cat(name, catdir)
        # The name is used as the name of the folder, so sanitize it using folder specific santization
        name = misc.sanitize_foldername(name)

    try:
        nzo = nzbstuff.NzbObject(name, 0, pp, script, data, cat=cat, priority=priority, nzbname=nzbname)
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
        sabnzbd.nzbqueue.add_nzo(nzo)
    try:
        if not keep: os.remove(path)
    except:
        logging.error(Ta('error-remove@1'), path)
        logging.debug("Traceback: ", exc_info = True)
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
    def __init__(self):
        threading.Thread.__init__(self)

        self.newdir()
        try:
            dir, self.ignored, self.suspected = sabnzbd.load_data(SCAN_FILE_NAME, remove = False)
            if dir != self.dirscan_dir:
                self.ignored = {}
                self.suspected = {}
        except:
            self.ignored = {}   # Will hold all unusable files and the
                                # successfully processed ones that cannot be deleted
            self.suspected = {} # Will hold name/attributes of suspected candidates

        self.shutdown = False
        self.error_reported = False # Prevents mulitple reporting of missing watched folder
        self.dirscan_dir = cfg.DIRSCAN_DIR.get_path()
        self.dirscan_speed = cfg.DIRSCAN_SPEED.get()
        cfg.DIRSCAN_DIR.callback(self.newdir)

    def newdir(self):
        """ We're notified of a dir change """
        self.ignored = {}
        self.suspected = {}
        self.dirscan_dir = cfg.DIRSCAN_DIR.get_path()
        self.dirscan_speed = cfg.DIRSCAN_SPEED.get()

    def stop(self):
        self.save()
        logging.info('Dirscanner shutting down')
        self.shutdown = True

    def save(self):
        sabnzbd.save_data((self.dirscan_dir, self.ignored, self.suspected), sabnzbd.SCAN_FILE_NAME)

    def run(self):
        def run_dir(folder, catdir):
            try:
                files = os.listdir(folder)
            except:
                if not self.error_reported and not catdir:
                    logging.error(Ta('error-readWatched@1'), folder)
                    self.error_reported = True
                files = []

            for filename in files:
                path = os.path.join(folder, filename)
                if os.path.isdir(path) or path in self.ignored:
                    continue

                root, ext = os.path.splitext(path)
                ext = ext.lower()
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
                    logging.info('Trying to import %s', path)

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
                        res = ProcessArchiveFile(filename, path, catdir=catdir)
                        if res == -1:
                            self.suspected[path] = stat_tuple
                        elif res == 0:
                            self.error_reported = False
                        else:
                            self.ignored[path] = 1

                    # Handle .nzb, .nzb.gz or gzip-disguised-as-nzb
                    elif ext == '.nzb' or filename.lower().endswith('.nzb.gz'):
                        res = ProcessSingleFile(filename, path, catdir=catdir)
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

        logging.info('Dirscanner starting up')
        self.shutdown = False

        while not self.shutdown:
            # Use variable scan delay
            dirscan_dir = self.dirscan_dir
            x = self.dirscan_speed
            while (x > 0) and not self.shutdown:
                time.sleep(1.0)
                x = x - 1

            if dirscan_dir and not self.shutdown and not sabnzbd.PAUSED_ALL:
                run_dir(dirscan_dir, None)

                try:
                    list = os.listdir(dirscan_dir)
                except:
                    if not self.error_reported:
                        logging.error(Ta('error-readWatched@1'), dirscan_dir)
                        self.error_reported = True
                    list = []

                cats = config.get_categories()
                for dd in list:
                    dpath = os.path.join(dirscan_dir, dd)
                    if os.path.isdir(dpath) and dd.lower() in cats:
                        run_dir(dpath, dd.lower())

