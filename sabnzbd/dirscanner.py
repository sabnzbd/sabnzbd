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
from sabnzbd.constants import *
from sabnzbd.utils.rarfile import is_rarfile, RarFile
from sabnzbd.newsunpack import is_sevenfile, SevenZip
import sabnzbd.nzbstuff as nzbstuff
import sabnzbd.misc as misc
import sabnzbd.config as config
import sabnzbd.cfg as cfg


def name_to_cat(fname, cat=None):
    """ Retrieve category from file name, but only if "cat" is None. """
    if cat is None and fname.startswith('{{'):
        n = fname.find('}}')
        if n > 2:
            cat = fname[2:n].strip()
            fname = fname[n + 2:].strip()
            logging.debug('Job %s has category %s', fname, cat)

    return fname, cat


def CompareStat(tup1, tup2):
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


def ProcessArchiveFile(filename, path, pp=None, script=None, cat=None, catdir=None, keep=False,
                       priority=None, url='', nzbname=None, password=None, nzo_id=None):
    """ Analyse ZIP file and create job(s).
        Accepts ZIP files with ONLY nzb/nfo/folder files in it.
        returns (status, nzo_ids)
            status: -1==Error/Retry, 0==OK, 1==Ignore
    """
    from sabnzbd.nzbqueue import add_nzo
    nzo_ids = []
    if catdir is None:
        catdir = cat

    filename, cat = name_to_cat(filename, catdir)

    if zipfile.is_zipfile(path):
        try:
            zf = zipfile.ZipFile(path)
        except:
            return -1, []
    elif is_rarfile(path):
        try:
            zf = RarFile(path)
        except:
            return -1, []
    elif is_sevenfile(path):
        try:
            zf = SevenZip(path)
        except:
            return -1, []
    else:
        return 1, []

    status = 1
    names = zf.namelist()
    names.sort()
    nzbcount = 0
    for name in names:
        name = name.lower()
        if not (name.endswith('.nzb') or name.endswith('.nfo') or name.endswith('/')):
            status = 1
            break
        elif name.endswith('.nzb'):
            status = 0
            nzbcount += 1
    if status == 0:
        if nzbcount != 1:
            nzbname = None
        for name in names:
            if name.lower().endswith('.nzb'):
                try:
                    data = zf.read(name)
                except:
                    zf.close()
                    return -1, []
                name = os.path.basename(name)
                if data:
                    try:
                        nzo = nzbstuff.NzbObject(name, pp, script, data, cat=cat, url=url,
                                                 priority=priority, nzbname=nzbname)
                        if not nzo.password:
                            nzo.password = password
                    except:
                        nzo = None
                    if nzo:
                        if nzo_id:
                            # Re-use existing nzo_id, when a "future" job gets it payload
                            sabnzbd.nzbqueue.NzbQueue.do.remove(nzo_id, add_to_history=False)
                            nzo.nzo_id = nzo_id
                        nzo_ids.append(add_nzo(nzo))
                        nzo.update_rating()
        zf.close()
        try:
            if not keep:
                os.remove(path)
        except:
            logging.error(T('Error removing %s'), misc.clip_path(path))
            logging.info("Traceback: ", exc_info=True)
            status = 1
    else:
        zf.close()
        status = 1

    return status, nzo_ids


def ProcessSingleFile(filename, path, pp=None, script=None, cat=None, catdir=None, keep=False,
                      priority=None, nzbname=None, reuse=False, nzo_info=None, dup_check=True, url='',
                      password=None, nzo_id=None):
    """ Analyze file and create a job from it
        Supports NZB, NZB.BZ2, NZB.GZ and GZ.NZB-in-disguise
        returns (status, nzo_ids)
            status: -2==Error/retry, -1==Error, 0==OK, 1==OK-but-ignorecannot-delete
    """
    from sabnzbd.nzbqueue import add_nzo
    nzo_ids = []
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
        elif (b1 == 'B' and b2 == 'Z'):
            # bz2 file or bz2 in disguise
            name = filename.replace('.nzb.bz2', '.nzb')
            f = bz2.BZ2File(path, 'rb')
        else:
            name = filename
            f = open(path, 'rb')
        data = f.read()
        f.close()
    except:
        logging.warning(T('Cannot read %s'), misc.clip_path(path))
        logging.info("Traceback: ", exc_info=True)
        return -2, nzo_ids

    if name:
        name, cat = name_to_cat(name, catdir)
        # The name is used as the name of the folder, so sanitize it using folder specific santization
        if not nzbname:
            # Prevent embedded password from being damaged by sanitize and trimming
            nzbname = os.path.split(name)[1]

    try:
        nzo = nzbstuff.NzbObject(name, pp, script, data, cat=cat, priority=priority, nzbname=nzbname,
                                 nzo_info=nzo_info, url=url, reuse=reuse, dup_check=dup_check)
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
        if data.find("<nzb") >= 0 and data.find("</nzb") < 0:
            # Looks like an incomplete file, retry
            return -2, nzo_ids
        else:
            return -1, nzo_ids

    if nzo:
        if nzo_id:
            # Re-use existing nzo_id, when a "future" job gets it payload
            sabnzbd.nzbqueue.NzbQueue.do.remove(nzo_id, add_to_history=False)
            nzo.nzo_id = nzo_id
        nzo_ids.append(add_nzo(nzo, quiet=reuse))
        nzo.update_rating()
    try:
        if not keep:
            os.remove(path)
    except:
        logging.error(T('Error removing %s'), misc.clip_path(path))
        logging.info("Traceback: ", exc_info=True)
        return 1, nzo_ids

    return 0, nzo_ids


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
            dir, self.ignored, self.suspected = sabnzbd.load_admin(SCAN_FILE_NAME)
            if dir != self.dirscan_dir:
                self.ignored = {}
                self.suspected = {}
        except:
            self.ignored = {}   # Will hold all unusable files and the
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
        self.save()
        logging.info('Dirscanner shutting down')
        self.shutdown = True

    def save(self):
        """ Save dir scanner bookkeeping """
        sabnzbd.save_admin((self.dirscan_dir, self.ignored, self.suspected), sabnzbd.SCAN_FILE_NAME)

    def run(self):
        """ Start the scanner """
        logging.info('Dirscanner starting up')
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
            except:
                if not self.error_reported and not catdir:
                    logging.error(T('Cannot read Watched Folder %s'), misc.clip_path(folder))
                    self.error_reported = True
                files = []

            for filename in files:
                path = os.path.join(folder, filename)
                if os.path.isdir(path) or path in self.ignored or filename[0] == '.':
                    continue

                ext = os.path.splitext(path)[1].lower()
                candidate = ext in ('.nzb', '.gz', '.bz2') or ext in VALID_ARCHIVES
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

                    # Handle archive files, but only when containing just NZB files
                    if ext in VALID_ARCHIVES:
                        res, nzo_ids = ProcessArchiveFile(filename, path, catdir=catdir, url=path)
                        if res == -1:
                            self.suspected[path] = stat_tuple
                        elif res == 0:
                            self.error_reported = False
                        else:
                            self.ignored[path] = 1

                    # Handle .nzb, .nzb.gz or gzip-disguised-as-nzb or .bz2
                    elif ext == '.nzb' or filename.lower().endswith('.nzb.gz') or filename.lower().endswith('.nzb.bz2'):
                        res, nzo_id = ProcessSingleFile(filename, path, catdir=catdir, url=path)
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

        if not self.busy:
            self.busy = True
            dirscan_dir = self.dirscan_dir
            if dirscan_dir and not sabnzbd.PAUSED_ALL:
                run_dir(dirscan_dir, None)

                try:
                    list = os.listdir(dirscan_dir)
                except:
                    if not self.error_reported:
                        logging.error(T('Cannot read Watched Folder %s'), misc.clip_path(dirscan_dir))
                        self.error_reported = True
                    list = []

                cats = config.get_categories()
                for dd in list:
                    dpath = os.path.join(dirscan_dir, dd)
                    if os.path.isdir(dpath) and dd.lower() in cats:
                        run_dir(dpath, dd.lower())
            self.busy = False


def dirscan():
    """ Wrapper required for scheduler """
    logging.info('Scheduled or manual watched folder scan')
    DirScanner.do.scan()
