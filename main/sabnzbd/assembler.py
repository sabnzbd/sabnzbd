#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
#           2007 The ShyPike <shypike@users.sourceforge.net>
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
import re

from sabnzbd.decorators import *
from sabnzbd.newsunpack import unpack_magic, par2_repair, external_processing
from sabnzbd.interface import CheckFreeSpace
from threading import Thread, RLock
from time import sleep
from sabnzbd.email import email_endjob, prepare_msg
from sabnzbd.nzbstuff import SplitFileName
from sabnzbd.misc import real_path

DIR_LOCK = RLock()

#------------------------------------------------------------------------------
## perm_script
## Set permissions correctly for non-Windows
def perm_script(wdir, umask):
    from os.path import join

    try:
        umask = int(umask, 8)
    except:
        return

    # Remove X bits for files
    umask_file = umask & int('7666', 8)

    # Make sure that user R is on
    umask_file = umask | int('0400', 8)

    # Parse the dir/file tree and set permissions
    for root, dirs, files in os.walk(wdir):
        os.chmod(root, umask)
        for name in files:
            os.chmod(join(root, name), umask_file)


#------------------------------------------------------------------------------

## sabnzbd.add_nzo
## sabnzbd.cleanup_nzo
class PostProcessor(Thread):
    def __init__ (self, download_dir, complete_dir, queue = None):
        Thread.__init__(self)

        self.download_dir = download_dir
        self.complete_dir = complete_dir
        self.queue = queue

        if not self.queue:
            self.queue = Queue.Queue()

    def process(self, nzo):
        self.queue.put(nzo)

    def stop(self):
        self.queue.put(None)

    def run(self):
        while 1:
            if sabnzbd.AUTOSHUTDOWN_GO and self.queue.empty():
                Thread(target=_system_shutdown).start()

            nzo = self.queue.get()
            if not nzo:
                break

            try:
                result = False
                rep, unp, dele = nzo.get_repair_opts()
                script = nzo.get_script()

                partable = nzo.get_partable()
                repairsets = partable.keys()

                filename = nzo.get_filename()

                workdir = get_path(self.download_dir, nzo)

                logging.info('[%s] Starting PostProcessing on %s' + \
                             ' => Repair:%s, Unpack:%s, Delete:%s, Script:%s',
                             __NAME__, filename, rep, unp, dele, script)

                ## Run Stage 1: Repair
                if rep:
                    logging.info('[%s] Par2 check starting on %s', __NAME__, filename)
                    readd = False
                    if not repairsets:
                        logging.info("[%s] No par2 sets for %s", __NAME__, filename)
                        nzo.set_unpackstr('=> No par2 sets', '[PAR-INFO]', 1)
                        result = True

                    for _set in repairsets:
                        logging.info("[%s] Running repair on set %s", __NAME__, _set)
                        parfile_nzf = partable[_set]
                        need_readd, res = par2_repair(parfile_nzf, nzo, workdir, _set)
                        if need_readd:
                            readd = True
                        else:
                            result = result and res

                    if readd:
                        logging.info('[%s] Readded %s to queue', __NAME__, filename)
                        sabnzbd.AUTOSHUTDOWN_GO = False
                        sabnzbd.add_nzo(nzo, 0)
                        ## Break out
                        continue

                    logging.info('[%s] Par2 check finished on %s', __NAME__, filename)

                if not sabnzbd.SAFE_POSTPROC:
                    result = True

                workdir_complete = None

                if self.complete_dir:
                    dirname = "_UNPACKING_%s" % nzo.get_dirname()
                    nzo.set_dirname(dirname)
                    workdir_complete = get_path(self.complete_dir, nzo)

                ## Run Stage 2: Unpack
                if unp and result:
                    logging.info("[%s] Running unpack_magic on %s", __NAME__, filename)
                    unpack_magic(nzo, workdir, workdir_complete, dele, (), (), ())
                    logging.info("[%s] unpack_magic finished on %s", __NAME__, filename)

                if workdir_complete and workdir:
                    for root, dirs, files in os.walk(workdir):
                        for _file in files:
                            path = os.path.join(root, _file)
                            new_path = path.replace(workdir, workdir_complete)
                            move_to_path(path, new_path)
                    try:
                        os.rmdir(workdir)
                    except:
                        logging.exception("[%s] Error removing workdir (%s)",
                                          __NAME__, workdir)
                    
                        
                    rep1 = "_UNPACKING_"
                    rep2 = ""
                    workdir_final = workdir_complete.replace(rep1,rep2) #Get rid of _UNPACKING_ in foldername
                    dirname = dirname.replace(rep1,rep2) 
                    
                    try: #get rid of .1.2.3 ect from end of foldername
                        while 1:
                            if workdir_final[-2] == '.':
                                workdir_final = workdir_final[:-2]
                            else:
                                break
                        while 1:
                            if dirname[-2] == '.':
                                dirname = dirname[:-2]
                            else:
                                break
                    except:
                        print 'out of range error on workdir_final/dirname!'  
                        
                    nzo.set_dirname(dirname)

                    unique_dir = True
                    if sabnzbd.ENABLE_TV_SORTING:
                        #First check if the show matches TV episode regular expressions. Returns regex match object
                        match1, match2 = checkForTVShow(dirname)
                        if match1:
                            logging.debug("[%s] Found TV Show - Starting folder sort (%s)", __NAME__, dirname)
                            #formatFolders will create the neccissary folders for the title/season ect and return the final folderpack (does not create the last folder)
                            workdir_final, unique_dir = formatFolders(workdir_final, dirname, match1, match2)
                        else:
                            dvdmatch = []
                            #check if the show matches DVD episode naming
                            dvdmatch = checkForTVDVD(dirname)
                            if dvdmatch:
                                logging.debug("[%s] Found TV DVD - Starting folder sort (%s)", __NAME__, dirname)
                                workdir_final, unique_dir = formatFolders(workdir_final, dirname, dvdmatch, dvd = True)
                    
                    
                    if unique_dir:  
                        #If the folder is set to be unique (default true) then it will find itself a unique foldername and create it
                        workdir_final = get_unique_path(workdir_final, create_dir = True)
                    else:   
                        #else it just creates the folder. (Does NOT fail if the folder already exists)
                        workdir_final = create_dir(workdir_final)
                    for root, dirs, files in os.walk(workdir_complete):
                        #move the contents of workdir_complete (_UNPACKING_) to the final workdir_final folder.
                        for _file in files:
                            path = os.path.join(root, _file)
                            new_path = path.replace(workdir_complete, workdir_final)
                            move_to_path(path, new_path, unique_dir)
                    try:
                        #delete the complete DIR (the folder that starts with '_UNPACKING_')
                        os.rmdir(workdir_complete)
                    except:
                        logging.exception("[%s] Error removing workdir_complete (%s)",
                                          __NAME__, workdir_complete)
                    
                    workdir = workdir_final

                    cleanup_empty_directories(self.download_dir)

                for root, dirs, files in os.walk(workdir):
                    for _file in files:
                        path = os.path.join(root, _file)

                if sabnzbd.CLEANUP_LIST and result:
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

                if sabnzbd.UMASK and (os.name != 'nt'):
                    perm_script(workdir, sabnzbd.UMASK)

                if sabnzbd.SCRIPT_DIR and script:
                    script = real_path(sabnzbd.SCRIPT_DIR, script)
                if result and script:
                    logging.info('[%s] Running external script %s %s %s', __NAME__, script, workdir, filename)
                    ext_out = external_processing(script, workdir, filename, nzo.get_cat())
                else:
                    ext_out = ""

                if sabnzbd.EMAIL_ENDJOB:
                    email_endjob(filename, prepare_msg(nzo.get_bytes_downloaded(),nzo.get_unpackstrht(), script, ext_out))

                name, msgid = SplitFileName(filename)
                sabnzbd.delete_bookmark(msgid)
            except:
                logging.exception("[%s] Postprocessing of %s failed.", __NAME__,
                                  nzo.get_filename())
                email_endjob(nzo.get_filename(), "Postprocessing failed.")
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
                    CheckFreeSpace()
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


################################################################################
# Dir Creation                                                                 #
################################################################################
@synchronized(DIR_LOCK)
def get_path(work_dir_root, nzo, filename = None):
    path = work_dir_root
    dirprefix = nzo.get_dirprefix()
    dirname = nzo.get_dirname()
    created = nzo.get_dirname_created()
    #uniquefolder = nzo.get_unique_dir()

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
            os.mkdir(dirpath)
            if sabnzbd.UMASK and os.name != 'nt':
                os.chmod(dirpath, int(sabnzbd.UMASK, 8) | 00700)
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
                os.mkdir(path)
                if sabnzbd.UMASK and os.name != 'nt':
                    os.chmod(path, int(sabnzbd.UMASK, 8) | 00700)
            return path
        except:
            logging.exception('[%s] Creating directory %s failed', __NAME__,
                              path)
            return None

    else:
        return get_unique_path(dirpath, i=i+1, create_dir=create_dir)

@synchronized(DIR_LOCK)

def move_to_path(path, new_path, unique = True):
    logging.debug("[%s] move_to_path |path:%s newpath:%s unique:%s",
                                              __NAME__,path,new_path, unique)
    if unique:
        new_path = get_unique_path(new_path, create_dir=False)
    if new_path:
        try:
            shutil.move(path, new_path)
        except: 
            logging.exception("[%s] Failed moving (%s)",
                                              __NAME__,new_path)
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

#-------------------------------------------------------------------------------

def _system_shutdown():
    logging.info("[%s] Performing system shutdown", __NAME__)

    sabnzbd.halt()

    try:
        import win32security
        import win32api
        import ntsecuritycon

        flags = ntsecuritycon.TOKEN_ADJUST_PRIVILEGES | ntsecuritycon.TOKEN_QUERY
        htoken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), flags)
        id = win32security.LookupPrivilegeValue(None, ntsecuritycon.SE_SHUTDOWN_NAME)
        newPrivileges = [(id, ntsecuritycon.SE_PRIVILEGE_ENABLED)]
        win32security.AdjustTokenPrivileges(htoken, 0, newPrivileges)
        win32api.InitiateSystemShutdown("", "", 30, 1, 0)
    finally:
        os._exit(0)

        
        
def checkForTVShow(filename): #checkfortvshow > formatfolders > gettvinfo
    """
    Regular Expression match for TV episodes named either 1x01 or S01E01
    Returns the MatchObject if a match is made
    """
    regularexpressions = [re.compile('(\w+)x(\d+)'),# 1x01
                          re.compile('[Ss](\d+)[\.\-]?[Ee](\d+)')] # S01E01
                          #possibly flawed - 101 - support: [\.\- \s]?(\d)(\d{2,2})[\.\- \s]?
    match2 = None
    for regex in regularexpressions:
        match1 = regex.search(filename)
        if match1:
            match2 = regex.search(filename,match1.end())
            return match1, match2
    return None, None

def checkForTVDVD(filename):
    """
    Regular Expression match for TV DVD's such as ShowName - Season 1 [DVD 1] ShowName S1D1
    Returns the MatchObject if a match is made
    """
    regularexpressions = [re.compile('Season (\d+) \[?DVD\s?(\d+)(\/\d)?\]?'),# Season 1 [DVD1]
                            re.compile('S(\d+) ?D(\d+)')]# S1D1
    for regex in regularexpressions:
        match = regex.search(filename)

    if match:
        return match
    return None


def getTVInfo(match1, match2,dirname):
    """
    Returns Title, Season and Episode naming from a REGEX match
    """
    foldername = None
    unique_dir = True
    
    title = match1.start()
    title = dirname[0:title]
    title = title.replace('.', ' ')
    title = title.strip().strip('_').strip('-').strip()
    title = title.title() # title

    season = match1.group(1).strip('_') # season number
    epNo = int(match1.group(2)) # episode number

    if epNo < 10:
        epNo = '0%s' % (epNo)

    if match2: #match2 is only present if a second REGEX match has been made
        epNo2 = int(match2.group(2)) # two part episode#
        if int(epNo2) < 10:
            epNo2 = '0%s' % (epNo)
    else:
        epNo2 = ''

    spl = dirname[match1.start():].split(' - ',2)

    try:
        if match2:
            epNo2Temp = '-%s' % (epNo2)
        else:
            epNo2Temp = ''
        epName = '%s%s - %s' % (epNo, epNo2Temp, spl[1].strip())
    except:
        epName = epNo
        
    if sabnzbd.TV_SORT == 2:  #\\TV\\ShowName\\1 - EpName\\
        foldername = epName
        
    elif sabnzbd.TV_SORT == 3:  #\\TV\\ShowName\\1x01 - EpName\\
        foldername = '%sx%s' % (season,epName) # season#
        
    elif sabnzbd.TV_SORT == 4:  #\\TV\\ShowName\\S01E01 - EpName\\
        if season == 'S' or season == 's':
            foldername = 'S%s' % (epName)
        else:
            if int(season) < 10:
                season = '0%s' % (int(season))
            foldername = 'S%sE%s' % (season,epName) # season#
            
    elif sabnzbd.TV_SORT == 5:  #\\TV\\ShowName\\101 - EpName\\
        foldername = '%s%s' % (season,epName) # season#
        
    elif sabnzbd.TV_SORT == 6:    #\\TV\\ShowName\\Season 1\\Episode 01 - EpName\\ 
        if season == 'S' or season == 's':
            foldername = 'Number %s' % (epName)
        else:
            foldername = 'Episode %s' % (epName)

    if season == 'S' or season == 's':
        season = 'Specials'
    else:
        season = 'Season %s' % (season) # season#
        
    if sabnzbd.TV_SORT == 1:    #\\TV\\ShowName\\Season 1\\
        unique_dir = False
        foldername = season
    elif sabnzbd.TV_SORT == 2:#\\TV\\ShowName\\Season 1\\Original DirName
        foldername = dirname
        
    return (title, season, foldername, unique_dir)


    
def getTVDVDInfo(match,match2,dirname):
    """
    Returns Title, Season and DVD Number naming from a REGEX match
    """
    foldername = None
    unique_dir = True
    title = match.start()
    title = dirname[0:title]
    title = title.replace('.', ' ')
    title = title.strip().strip('-').strip()
    title = title.title() # title
    season = int(match.group(1))
    dvd = match.group(2) # dvd number

    if sabnzbd.TV_SORT == 2  or sabnzbd.TV_SORT == 6:    #\\TV\\ShowName\\Season 1\\DVD 1\\
        foldername = 'DVD %s' % (dvd) # dvd number#
    elif sabnzbd.TV_SORT == 3:  #\\TV\\ShowName\\1xDVD1\\
    
        foldername = '%sxDVD%s' % (season,dvd) # season#
    elif sabnzbd.TV_SORT == 4:  #\\TV\\ShowName\\S01DVD1\\
        if season < 10:
            season = '0%s' % (int(season))
        foldername = 'S%sDVD%s' % (season,dvd) # season#

    elif sabnzbd.TV_SORT == 5:  #\\TV\\ShowName\\1DVD1\\
        foldername = '%sDVD%s' % (season,dvd) # season#

    elif sabnzbd.TV_SORT == 1:  #\\TV\\ShowName\\DVD1\\
        foldername = 'DVD %s' % (season,dvd) # season#
        unique_dir = True
        
    season = 'Season %s' % (season) # season#

    return (title, season, foldername, unique_dir)
    

    
def formatFolders(dirpath, dirname, match1, match2 = None, dvd = False):
    """
    Creates directories from returned title and season. Returns final dirpath.
    Does not create the final foldername, but returns it as new_dirpath.
    """
    try:
        new_dirpath = dirpath
        new_dirpath  = new_dirpath.replace(dirname,'')
        
        if not dvd:
            title, season, foldername, unique_dir = getTVInfo(match1, match2, dirname)
        else:
            title, season, foldername, unique_dir = getTVDVDInfo(match1, match2, dirname)
            
    except:
        logging.error("[%s] Error creating tv folders. (workdir_final: %s)",
                                              __NAME__, new_dirpath)
        return dirpath, True
    
    try:  
        if title and season and foldername:
            new_dirpath = create_dir(os.path.join(new_dirpath, title))
            if sabnzbd.TV_SORT_SEASONS and season != foldername:
                new_dirpath = create_dir(os.path.join(new_dirpath, season))
                
            new_dirpath = os.path.join(new_dirpath, foldername)
            return new_dirpath, unique_dir
        else:    
            logging.debug("[%s] TV Sorting: title, season or foldername not present (%s)", __NAME__, dirname)
            return dirpath, True
    except:
        logging.error("[%s] Error creating tv folders. (workdir_final: %s title: %s season: %s foldername %s unique:%s dvd:%s)",
                                              __NAME__, new_dirpath, title,season,foldername, dvd)
        return dirpath, True