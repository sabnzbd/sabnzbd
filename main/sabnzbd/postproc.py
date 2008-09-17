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
sabnzbd.postproc - threaded post-processing of jobs
"""
#------------------------------------------------------------------------------

__NAME__ = "postproc"

import os
import Queue
import logging
import sabnzbd
import shutil
import urllib
import re
from xml.sax.saxutils import escape
if os.name == 'nt':
    import subprocess

from sabnzbd.decorators import *
from sabnzbd.newsunpack import unpack_magic, par2_repair, external_processing
from threading import Thread, RLock
from sabnzbd.email import email_endjob
from sabnzbd.nzbstuff import SplitFileName
from sabnzbd.misc import real_path, get_unique_path, create_dirs, move_to_path, \
                         cleanup_empty_directories, get_unique_filename, \
                         OnCleanUpList, ProcessSingleFile
from sabnzbd.tvsort import TVSeasonCheck, TVSeasonMove, TVRenamer
from sabnzbd.constants import TOP_PRIORITY

#------------------------------------------------------------------------------
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
            if self.queue.empty(): HandleEmptyQueue()

            ## Get a job from the queue, quit on empty job
            nzo = self.queue.get()
            if not nzo: break
            
            ## Pause downloader, if users wants that
            if sabnzbd.pause_on_post_processing: sabnzbd.idle_downloader()

            parResult = True
            unpackError = False

            ## Get the job flags
            flagRepair, flagUnpack, flagDelete = nzo.get_repair_opts()
            pp = sabnzbd.opts_to_pp(flagRepair, flagUnpack, flagDelete)
            script = nzo.get_script()
            group = nzo.get_group()
            cat = nzo.get_cat()

            ## Collect the par files
            parTable = nzo.get_partable()
            repairSets = parTable.keys()

            # Get the NZB name
            filename = nzo.get_filename()

            # Get the folder containing the download result
            workdir = os.path.join(self.download_dir, nzo.get_dirname())

            # if the directory has not been made, no files were assembled
            if not os.path.exists(workdir):
                emsg = 'Download failed - Out of your server\'s retention?'
                nzo.set_unpackstr(emsg, '[Failed]', 0)
                # do not run unpacking or parity verification
                flagRepair = flagUnpack = parResult = False
                unpackError = True
                
            logging.info('[%s] Starting PostProcessing on %s' + \
                         ' => Repair:%s, Unpack:%s, Delete:%s, Script:%s',
                         __NAME__, filename, flagRepair, flagUnpack, flagDelete, script)

            ## Run Stage 1: Repair
            if flagRepair:
                logging.info('[%s] Par2 check starting on %s', __NAME__, filename)
                reAdd = False
                if not repairSets:
                    logging.info("[%s] No par2 sets for %s", __NAME__, filename)
                    nzo.set_unpackstr('=> No par2 sets', '[PAR-INFO]', 1)

                for _set in repairSets:
                    logging.info("[%s] Running repair on set %s", __NAME__, _set)
                    parfile_nzf = parTable[_set]
                    need_reAdd, res = par2_repair(parfile_nzf, nzo, workdir, _set)
                    if need_reAdd:
                        reAdd = True
                    else:
                        parResult = parResult and res

                if reAdd:
                    logging.info('[%s] Readded %s to queue', __NAME__, filename)
                    sabnzbd.QUEUECOMPLETEACTION_GO = False
                    sabnzbd.add_nzo(nzo, TOP_PRIORITY)
                    sabnzbd.unidle_downloader()
                    ## Break out, further downloading needed
                    continue

                logging.info('[%s] Par2 check finished on %s', __NAME__, filename)

            mailResult = parResult
            jobResult = 1
            if parResult: jobResult = 0

            ## Check if user allows unsafe post-processing
            if not sabnzbd.SAFE_POSTPROC:
                parResult = True

            ## Determine class directory
            if len(sabnzbd.CFG['categories']):
                complete_dir = Cat2Dir(cat, self.complete_dir)
            elif sabnzbd.CREATE_CAT_FOLDERS:
                if nzo.get_cat():
                    complete_dir = create_dirs(os.path.join(self.complete_dir, nzo.get_cat()))
                else:
                    complete_dir = self.complete_dir
            elif sabnzbd.CREATE_GROUP_FOLDERS:
                complete_dir = addPrefixes(self.complete_dir, nzo)
                complete_dir = create_dirs(complete_dir)
            else:
                complete_dir = self.complete_dir

            ## Determine destination directory
            dirname = nzo.get_original_dirname()
            complete_dir, filename_set, tv_file = TVSeasonCheck(complete_dir, dirname)
            nzo.set_dirname(dirname)
            if not tv_file:
                workdir_complete = get_unique_path(os.path.join(complete_dir, dirname), create_dir=True)
                tmp_workdir_complete = prefix(workdir_complete, '_UNPACK_')
                try:
                    os.rename(workdir_complete, tmp_workdir_complete)
                except:
                    pass # On failure, just use the original name
            else:
                tmp_workdir_complete = complete_dir
                
                workdir_complete = create_dirs(complete_dir)
                tmp_workdir_complete = create_dirs(prefix(os.path.join(workdir_complete, dirname), '_UNPACK_'))
                
            newfiles = []                
            ## Run Stage 2: Unpack
            if flagUnpack:
                if parResult:
                    #set the current nzo status to "Extracting...". Used in History
                    nzo.set_status("Extracting...")
                    logging.info("[%s] Running unpack_magic on %s", __NAME__, filename)
                    unpackError, newfiles = unpack_magic(nzo, workdir, tmp_workdir_complete, flagDelete, (), (), ())
                    logging.info("[%s] unpack_magic finished on %s", __NAME__, filename)
                else:
                    nzo.set_unpackstr('=> No post-processing because of failed verification', '[UNPACK]', 2)

            ## Move any (left-over) files to destination
            nzo.set_status("Moving...")
            for root, dirs, files in os.walk(workdir):
                for _file in files:
                    path = os.path.join(root, _file)
                    new_path = path.replace(workdir, tmp_workdir_complete)
                    path, new_path = get_unique_filename(path,new_path)
                    move_to_path(path, new_path, unique=False)

            ## Remove download folder
            try:
                os.rmdir(workdir)
            except:
                logging.error("[%s] Error removing workdir (%s)", __NAME__, workdir)

                                      
            ## Remove files matching the cleanup list
            if parResult: CleanUpList(tmp_workdir_complete, True)


            ## Give destination its final name
            if not tv_file:
                if unpackError or not parResult:
                    workdir_complete = tmp_workdir_complete.replace('_UNPACK_', '_FAILED_')
                    workdir_complete = get_unique_path(workdir_complete, n=0, create_dir=False)
                try:
                    os.rename(tmp_workdir_complete, workdir_complete)
                    nzo.set_dirname(os.path.basename(workdir_complete))
                except:
                    logging.error('[%s] Error renaming "%s" to "%s"', __NAME__, tmp_workdir_complete, workdir_complete)
            else:
                if unpackError or not parResult: 
                    workdir_complete = tmp_workdir_complete.replace('_UNPACK_', '_FAILED_')
                    workdir_complete = get_unique_path(workdir_complete, n=0, create_dir=False)
                    try:
                        os.rename(tmp_workdir_complete, workdir_complete)
                        nzo.set_dirname(os.path.basename(workdir_complete))
                    except:
                        logging.error('[%s] Error renaming "%s" to "%s"', __NAME__, tmp_workdir_complete, workdir_complete)
                else:
                    if newfiles and tv_file and filename_set: TVRenamer(tmp_workdir_complete, newfiles, filename_set)
                    workdir_complete = TVSeasonMove(tmp_workdir_complete)

            if unpackError: jobResult = jobResult + 2

            ## Clean up download dir
            cleanup_empty_directories(self.download_dir)

   
            ## Set permissions right
            if sabnzbd.UMASK and (os.name != 'nt'):
                perm_script(workdir_complete, sabnzbd.UMASK)

            ## Run the user script
            fname = ""
            ext_out = ""
            if sabnzbd.SCRIPT_DIR and script and script!='None' and script!='Default':
                #set the current nzo status to "Ext Script...". Used in History
                script = os.path.join(sabnzbd.SCRIPT_DIR, script)
                if os.path.exists(script):
                    nzo.set_status("Running Script...")
                    nzo.set_unpackstr('=> Running user script %s' % script, '[USER-SCRIPT]', 5)
                    ext_out = external_processing(script, workdir_complete, filename, dirname, cat, group, jobResult)
                    fname = MakeLogFile(filename, ext_out)
            else:
                script = ""

            ## Email the results
            if sabnzbd.EMAIL_ENDJOB:
                email_endjob(filename, cat, mailResult, workdir_complete, nzo.get_bytes_downloaded(),
                             nzo.get_unpackstrht(), script, ext_out)

            if fname:
                # Can do this only now, otherwise it would show up in the email
                nzo.set_unpackstr('=> <a href="./scriptlog?name=%s">Show script output</a>' % urllib.quote(fname), '[USER-SCRIPT]', 5)

            ## Remove newzbin bookmark, if any
            name, msgid = SplitFileName(filename)
            sabnzbd.delete_bookmark(msgid)

            ## Show final status in history
            if parResult and not unpackError:
                nzo.set_status("Completed")
            else:
                nzo.set_status("Failed")

            ## Check if this is an NZB-only download, if so redirect to queue
            if parResult:
                lst = NzbRedirect(workdir_complete, pp, script, cat)
                if lst: nzo.set_unpackstr('=> Sent %s to queue' % lst, '[QUEUE]', 6)

            # Another cleanup to remove any NZB that the users wants gone
            if parResult: CleanUpList(tmp_workdir_complete, False)

            ## Clean up the NZO
            try:
                logging.info('[%s] Cleaning up %s', __NAME__, filename)
                sabnzbd.cleanup_nzo(nzo)
            except:
                logging.error("[%s] Cleanup of %s failed.", __NAME__, nzo.get_filename())

            ## Allow download to proceed
            sabnzbd.unidle_downloader()
#end post-processor


#------------------------------------------------------------------------------

def MakeLogFile(name, content):
    """ Write 'content' to a logfile named 'name'.log """
    name = name.replace('.nzb', '.log')
    path = os.path.dirname(sabnzbd.LOGFILE)
    path = os.path.join(path, name)
    try:
        f = open(path, "w")
    except:
        logging.error("[%s] Cannot create logfile %s", __NAME__, path)
        return "a"
    f.write(content)
    f.close()
    return name


def perm_script(wdir, umask):
    """ Give folder tree and its files their proper permissions """
    from os.path import join

    try:
        # Make sure that user R is on
        umask = int(umask, 8) | int('0400', 8)
    except:
        return

    # Remove X bits for files
    umask_file = umask & int('7666', 8)

    # Parse the dir/file tree and set permissions
    for root, dirs, files in os.walk(wdir):
        os.chmod(root, umask)
        for name in files:
            os.chmod(join(root, name), umask_file)


def Cat2Dir(cat, defdir):
    """ Lookup destination dir for category """
    ddir = defdir
    if cat:
        try:
            ddir = sabnzbd.CFG['categories'][cat.lower()]['dir']
        except:
            return defdir
        ddir = real_path(sabnzbd.COMPLETE_DIR, ddir)
        ddir = create_dirs(ddir)
        if not ddir:
            ddir = defdir
    return ddir




def addPrefixes(path,nzo):
    dirprefix = nzo.get_dirprefix()
    for _dir in dirprefix:
            if not _dir:
                continue
            if not path:
                break
            basepath = os.path.basename(os.path.abspath(path))
            if _dir != basepath.lower():
                path = os.path.join(path, _dir)
    return path


def HandleEmptyQueue():
    """ Check if empty queue calls for action """        
    sabnzbd.save_state()

    if sabnzbd.QUEUECOMPLETEACTION_GO:
        logging.info("[%s] Queue has finished, launching: %s (%s)", \
            __NAME__,sabnzbd.QUEUECOMPLETEACTION, sabnzbd.QUEUECOMPLETEARG)
        if sabnzbd.QUEUECOMPLETEARG:
            sabnzbd.QUEUECOMPLETEACTION(sabnzbd.QUEUECOMPLETEARG)
        else:
            Thread(target=sabnzbd.QUEUECOMPLETEACTION).start()
            
        sabnzbd.QUEUECOMPLETEACTION = None
        sabnzbd.QUEUECOMPLETEARG = None
        sabnzbd.QUEUECOMPLETEACTION_GO = False


def CleanUpList(wdir, skip_nzb):
    """ Remove all files matching the cleanup list """

    if sabnzbd.CLEANUP_LIST:
        try:
            files = os.listdir(wdir)
        except:
            files = ()
        for _file in files:
            if OnCleanUpList(_file, skip_nzb):
                path = os.path.join(wdir, _file)
                try:
                    logging.info("[%s] Removing unwanted file %s", __NAME__, path)
                    os.remove(path)
                except:
                    logging.error("[%s] Removing %s failed", __NAME__, path)


def prefix(path, pre):
    """ Apply prefix to last part of path """
    p, d = os.path.split(path)
    return os.path.join(p, pre + d)


def NzbRedirect(wdir, pp, script, cat):
    """ Check if this job contains only NZB files,
        if so send to queue and remove if on CleanList
        Returns list of processed NZB's
    """
    list = []

    files = os.listdir(wdir)
    for file in files:
        if os.path.splitext(file)[1].lower() != '.nzb':
            return list
    
    # Process all NZB files
    keep = not OnCleanUpList("x.nzb", False)
    for file in files:
        if file.lower().endswith('.nzb'):
            ProcessSingleFile(file, os.path.join(wdir, file), pp, script, cat, keep=keep)
            list.append(file)

    try:
        # Folder will be removed when empty
        os.rmdir(wdir)
    except:
        pass
    return list
