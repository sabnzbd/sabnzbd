#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
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
sabnzbd.assembler - threaded assembly/decoding of files
"""
#------------------------------------------------------------------------------

__NAME__ = "assembler"

import os
import Queue
import binascii
import logging
import sabnzbd
import cPickle
import shutil

from sabnzbd.decorators import *
from sabnzbd.newsunpack import unpack_magic, par2_repair, external_processing
from threading import Thread, RLock
from time import sleep

DIR_LOCK = RLock()

#------------------------------------------------------------------------------

## sabnzbd.add_nzo
## sabnzbd.cleanup_nzo
class PostProcessor(Thread):
    def __init__ (self, download_dir, complete_dir, extern_proc, restore_name, queue = None):
        Thread.__init__(self)
        
        self.download_dir = download_dir
        self.complete_dir = complete_dir
        self.extern_proc = extern_proc
        self.restore_name= restore_name
        self.queue = queue
        
        if not self.queue:
            self.queue = Queue.Queue()
        
    def process(self, nzo):
        self.queue.put(nzo)
        
    def stop(self):
        self.queue.put(None)
        
    def run(self):
        while 1:
            nzo = self.queue.get()
            if not nzo:
                break
                
            try:
                rep, unp, dele, scr = nzo.get_repair_opts()
                
                partable = nzo.get_partable()
                repairsets = partable.keys()
                
                filename = nzo.get_filename()
                
                workdir = get_path(self.download_dir, nzo)
                
                logging.info('[%s] Starting PostProcessing on %s' + \
                             ' => Repair:%s, Unpack:%s, Delete:%s, Script:%s',
                             __NAME__, filename, rep, unp, dele, scr)
                             
                ## Run Stage 1: Repair
                if rep:
                    logging.info('[%s] Par2 check starting on %s', __NAME__, filename)
                    readd = False
                    if not repairsets:
                        logging.info("[%s] No par2 sets for %s", __NAME__, filename)
                        nzo.set_unpackstr('=> No par2 sets', '[PAR-INFO]', 1)
                        
                    for _set in repairsets:
                        logging.info("[%s] Running repair on set %s", __NAME__, _set)
                        parfile_nzf = partable[_set]
                        need_readd = par2_repair(parfile_nzf, nzo, workdir, _set)
                        if need_readd:
                            readd = True
                            
                    if readd:
                        logging.info('[%s] Readded %s to queue', __NAME__, filename)
                        sabnzbd.add_nzo(nzo, 0)
                        ## Break out
                        continue
                        
                    logging.info('[%s] Par2 check finished on %s', __NAME__, filename)
                    
                workdir_complete = None
                
                if self.complete_dir:
                    dirname = "__UNPACK_IN_PROGRESS__%s" % nzo.get_dirname()
                    nzo.set_dirname(dirname)
                    workdir_complete = get_path(self.complete_dir, nzo)
                    
                ## Run Stage 2: Unpack
                if unp:
                    logging.info("[%s] Running unpack_magic on %s", __NAME__, filename)
                    unpack_magic(nzo, workdir, workdir_complete, dele, (), (), ())
                    logging.info("[%s] unpack_magic finished on %s", __NAME__, filename)
                    
                if workdir_complete:
                    for root, dirs, files in os.walk(workdir):
                        for _file in files:
                            path = os.path.join(root, _file)
                            new_path = path.replace(workdir, workdir_complete)
                            move_to_unique_path(path, new_path)
                    try:
                        os.rmdir(workdir)
                    except:
                        logging.exception("[%s] Error removing workdir (%s)",
                                          __NAME__, workdir)
                                          
                    workdir_final = workdir_complete.replace("__UNPACK_IN_PROGRESS__", 
                                                             "")
                    
                    workdir_final = move_to_unique_path(workdir_complete, workdir_final)
                    
                    workdir = workdir_final
                    
                    cleanup_empty_directories(self.download_dir)
                    
                for root, dirs, files in os.walk(workdir):
                    for _file in files:
                        path = os.path.join(root, _file)
                        try:
                            logging.debug("[%s] Setting umask %s to %s", 
                                          __NAME__, sabnzbd.UMASK, path)
                            os.chmod(path, sabnzbd.UMASK)
                        except:
                            logging.exception("[%s] Setting umask %s to %s failed", 
                                              __NAME__, sabnzbd.UMASK, path)
                                              
                if sabnzbd.CLEANUP_LIST:
                    try:
                        files = os.listdir(workdir)
                    except:
                        files = ()
                        
                    for _file in files:
                        root, ext = os.path.splitext(_file)
                        
                        if ext in sabnzbd.CLEANUP_LIST:
                            path = os.path.join(workdir, _file)
                            try:
                                logging.info("[%s] Removing unwanted file %s",
                                             __NAME__, path)
                                os.remove(path)
                            except:
                                logging.exception("[%s] Removing %s failed",
                                                  __NAME__, path)

                if self.restore_name:
                    root, ext = os.path.splitext(filename)
                    wpath, wname = os.path.split(workdir)
                    newdir= wpath + "/" + root
                    os.rename(workdir, newdir)
                    logging.info('[%s] Renamed %s to %s', __NAME__, workdir, newdir)

                if scr and self.extern_proc:
                    logging.info('[%s] Running external script %s %s %s', __NAME__, self.extern_proc, workdir, filename)
                    external_processing(self.extern_proc, workdir, filename)
            except:
                logging.exception("[%s] Postprocessing of %s failed.", __NAME__,
                                  nzo.get_filename())
            try:
                logging.info('[%s] Cleaning up %s', __NAME__, filename)
                sabnzbd.cleanup_nzo(nzo)
            except:
                logging.exception("[%s] Cleanup of %s failed.", __NAME__,
                                  nzo.get_filename())
                                  
#------------------------------------------------------------------------------
## sabnzbd.pause_downloader
class Assembler(Thread):
    def __init__ (self, download_dir, queue = None):
        Thread.__init__(self)
        
        self.download_dir = download_dir
        self.queue = queue
        
        if not self.queue:
            self.queue = Queue.Queue()
            
    def stop(self):
        self.process(None)
        
    def process(self, nzf):
        self.queue.put(nzf)
        
    def run(self):
        while 1:
            nzo_nzf_tuple = self.queue.get()
            if not nzo_nzf_tuple:
                logging.info("[%s] Shutting down", __NAME__)
                break
            
            nzo, nzf = nzo_nzf_tuple
            
            if nzf:
                try:
                    filename = nzf.get_filename()
                    
                    dupe = nzo.check_for_dupe(nzf)
                    
                    filepath = get_path(self.download_dir, nzo, filename)
                    
                    if filepath:
                        logging.info('[%s] Decoding %s %s', __NAME__, filepath, 
                                     nzf.get_type())
                        try:
                            _assemble(nzf, filepath, dupe)
                        except IOError, (errno, strerror):
                            # 28 == disk full => pause downloader
                            if errno == 28:
                                sabnzbd.pause_downloader()
                                logging.warning('[%s] Disk full! Forcing Pause', 
                                                __NAME__)
                            else:
                                logging.exception('[%s] Disk exception', 
                                                  __NAME__)
                                fixed_filename = sabnzbd.fix_filename(filename)
                                if fixed_filename != filename:
                                    logging.info('[%s] Retrying %s with new' + \
                                                 ' filename %s', 
                                                 __NAME__, filename, fixed_filename)
                                    try:
                                        filepath = get_filepath(self.download_dir,
                                                                nzo, fixed_filename)
                                        _assemble(nzf, filepath, dupe)
                                    except IOError:
                                        logging.exception('[%s] Disk exception', 
                                                           __NAME__)
                                                           
                except:
                    logging.exception("[%s] Assembly of %s failed.", __NAME__, nzf)
            else:
                sabnzbd.postprocess_nzo(nzo)
                
def _assemble(nzf, path, dupe):
    if os.path.exists(path):
        unique_path = get_unique_path(path, create_dir = False)
        if dupe:
            path = unique_path
        else:
            os.rename(path, unique_path)
            
    fout = open(path, 'ab')
    
    _type = nzf.get_type()
    decodetable = nzf.get_decodetable()
    
    for articlenum in decodetable:
        sleep(0.01)
        article = decodetable[articlenum]
        
        data = sabnzbd.load_article(article)
        
        if not data:
            logging.warning('[%s] %s missing', __NAME__, article)
        else:
            # yenc data already decoded, flush it out
            if _type == 'yenc':
                fout.write(data)
            # need to decode uu data now
            elif _type == 'uu':
                data = data.split('\r\n')
                
                chunks = []
                for line in data:
                    if not line:
                        continue
                        
                    if line == '-- ' or line.startswith('Posted via '):
                        continue
                    try:
                        tmpdata = binascii.a2b_uu(line)
                        chunks.append(tmpdata)
                    except binascii.Error, msg:
                        ## Workaround for broken uuencoders by 
                        ##/Fredrik Lundh
                        nbytes = (((ord(line[0])-32) & 63) * 4 + 5) / 3
                        try:
                            tmpdata = binascii.a2b_uu(line[:nbytes])
                            chunks.append(tmpdata)
                        except binascii.Error, msg:
                            logging.info('[%s] Decode failed in part %s: %s',
                                         __NAME__, article.article, msg)
                fout.write(''.join(chunks))
            
    fout.flush()
    fout.close()
    try:
        os.chmod(path, sabnzbd.UMASK)
    except:
        pass
        
################################################################################
# Dir Creation                                                                 #
################################################################################
@synchronized(DIR_LOCK)
def get_path(work_dir_root, nzo, filename = None):
    path = work_dir_root
    dirprefix = nzo.get_dirprefix()
    dirname = nzo.get_dirname()
    created = nzo.get_dirname_created()
    
    for _dir in dirprefix:
        if not _dir:
            continue
        if not path:
            break
        path = create_dir(os.path.join(path, _dir))
            
    if path and created:
        path = create_dir(os.path.join(path, dirname))
    elif path:
        path = get_unique_path(os.path.join(path, dirname))
        if path:
            nzo.set_dirname(os.path.basename(path), created = True)
            
    if path and filename:
        path = os.path.join(path, filename)
        
    return path
    
@synchronized(DIR_LOCK)  
def create_dir(dirpath):
    if not os.path.exists(dirpath):
        logging.info('[%s] Creating directory: %s', __NAME__, dirpath)
        try:
            os.mkdir(dirpath, sabnzbd.UMASK)
        except:
            logging.exception('[%s] Creating directory %s failed', __NAME__,
                              dirpath)
            return None
            
    return dirpath
    
@synchronized(DIR_LOCK)
def get_unique_path(dirpath, i=0, create_dir=True):
    path = dirpath
    if i:
        path = "%s.%s" % (dirpath, i)
        
    if not os.path.exists(path):
        logging.info('[%s] Creating directory: %s', __NAME__, path)
        try:
            if create_dir:
                os.mkdir(path, sabnzbd.UMASK)
                
            return path
        except:
            logging.exception('[%s] Creating directory %s failed', __NAME__,
                              path)
            return None
            
    else:
        return get_unique_path(dirpath, i=i+1, create_dir=create_dir)
        
@synchronized(DIR_LOCK)
def move_to_unique_path(path, new_path):
    new_path = get_unique_path(new_path, create_dir=False)
    if new_path:
        shutil.move(path, new_path)
        return new_path
        
@synchronized(DIR_LOCK)
def cleanup_empty_directories(path):
    path = os.path.normpath(path)
    while 1:
        repeat = False
        for root, dirs, files in os.walk(path, topdown=False):
            if not dirs and not files and root != path:
                try:
                    os.rmdir(root)
                    repeat = True
                except:
                    pass
        if not repeat:
            break
