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
sabnzbd.postproc - threaded post-processing of jobs
"""
#------------------------------------------------------------------------------

import os
import Queue
import logging
import sabnzbd
import urllib
import time
import re
from xml.sax.saxutils import escape
import subprocess

from sabnzbd.decorators import synchronized
from sabnzbd.newsunpack import unpack_magic, par2_repair, external_processing
from threading import Thread, RLock
from sabnzbd.misc import real_path, get_unique_path, create_dirs, move_to_path, \
                         get_unique_filename, \
                         on_cleanup_list
from sabnzbd.tvsort import Sorter
from sabnzbd.constants import TOP_PRIORITY, DB_HISTORY_NAME, POSTPROC_QUEUE_FILE_NAME, \
     POSTPROC_QUEUE_VERSION, sample_match
from sabnzbd.codecs import TRANS
import sabnzbd.newzbin
import sabnzbd.email as email
import sabnzbd.dirscanner as dirscanner
import sabnzbd.downloader as downloader
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.nzbqueue
import sabnzbd.database as database
from sabnzbd.utils import osx
from sabnzbd.lang import T

#------------------------------------------------------------------------------
# Wrapper functions

__POSTPROC = None  # Global pointer to post-proc instance

def init():
    global __POSTPROC
    if __POSTPROC:
        __POSTPROC.__init__(__POSTPROC.queue(), __POSTPROC.get_queue())
    else:
        __POSTPROC = PostProcessor()

def start():
    global __POSTPROC
    if __POSTPROC: __POSTPROC.start()

def get_queue():
    global __POSTPROC
    if __POSTPROC: return __POSTPROC.get_queue()

def process(nzo):
    global __POSTPROC
    if __POSTPROC: __POSTPROC.process(nzo)

def empty():
    global __POSTPROC
    if __POSTPROC: return __POSTPROC.empty()

def history_queue():
    global __POSTPROC
    if __POSTPROC: return __POSTPROC.get_queue()

def stop():
    global __POSTPROC
    if __POSTPROC:
        __POSTPROC.stop()
        try:
            __POSTPROC.join()
        except:
            pass

def alive():
    global __POSTPROC
    if __POSTPROC:
        return __POSTPROC.isAlive()
    else:
        return False

def save():
    global __POSTPROC
    if __POSTPROC: __POSTPROC.save()

def load():
    global __POSTPROC
    if __POSTPROC: __POSTPROC.load()



#------------------------------------------------------------------------------
class PostProcessor(Thread):
    def __init__ (self, queue=None, history_queue=None):
        Thread.__init__(self)

        # This history queue is simply used to log what active items to display in the web_ui
        if history_queue:
            self.history_queue = history_queue
        else:
            self.load()

        if self.history_queue is None:
            self.history_queue = []

        if queue:
            self.queue = queue
        else:
            self.queue = Queue.Queue()
            for nzo in self.history_queue:
                self.process(nzo)


    def save(self):
        """ Save postproc queue """
        logging.info("Saving postproc queue")
        sabnzbd.save_data((POSTPROC_QUEUE_VERSION, self.history_queue), POSTPROC_QUEUE_FILE_NAME)

    def load(self):
        """ Save postproc queue """
        logging.info("Loading postproc queue")
        data = sabnzbd.load_data(POSTPROC_QUEUE_FILE_NAME)
        try:
            version, history_queue = data
            if POSTPROC_QUEUE_VERSION != version:
                logging.warning(T('warn-badPPQueue@2'), POSTPROC_QUEUE_VERSION, version)
            if isinstance(history_queue, list):
                self.history_queue = history_queue
                return True
            else:
                self.history_queue = []
                return False
        except:
            self.history_queue = []
            return False


    def process(self, nzo):
        if nzo not in self.history_queue:
            self.history_queue.append(nzo)
        self.queue.put(nzo)
        self.save()

    def remove(self, nzo):
        try:
            self.history_queue.remove(nzo)
        except:
            nzo_id = getattr(nzo, 'nzo_id', 'unknown id')
            logging.error(T('error-ppDelNzo'), nzo_id)
        self.save()

    def stop(self):
        self.queue.put(None)
        self.save()

    def empty(self):
        return self.queue.empty()

    def get_queue(self):
        return self.history_queue

    def run(self):
        while 1:
            if self.queue.empty(): HandleEmptyQueue()

            ## Get a job from the queue, quit on empty job
            nzo = self.queue.get()
            if not nzo: break

            ## Pause downloader, if users wants that
            if cfg.PAUSE_ON_POST_PROCESSING.get():
                downloader.idle_downloader()

            start = time.time()

            # keep track of if par2 fails
            parResult = True
            # keep track of any unpacking errors
            unpackError = False
            nzb_list = []
            # These need to be initialised incase of a crash
            workdir_complete = ''
            base_dir = ''
            rel_path = ''
            postproc_time = 0
            script_log = ''
            script_line = ''

            ## Get the job flags
            flagRepair, flagUnpack, flagDelete = nzo.get_repair_opts()
            pp = sabnzbd.opts_to_pp(flagRepair, flagUnpack, flagDelete)
            script = nzo.get_script()
            group = nzo.get_group()
            cat = nzo.get_cat()
            priority = nzo.get_priority()

            ## Collect the par files
            parTable = nzo.get_partable()
            repairSets = parTable.keys()

            # Get the NZB name
            filename = nzo.get_dirname()
            msgid = nzo.get_msgid()

            try:

                # Get the folder containing the download result
                workdir = os.path.join(cfg.DOWNLOAD_DIR.get_path(), nzo.get_dirname())

                # if the directory has not been made, no files were assembled
                if not os.path.exists(workdir):
                    emsg = 'Download failed - Out of your server\'s retention?'
                    nzo.set_fail_msg(emsg)
                    nzo.set_status('Failed')
                    # do not run unpacking or parity verification
                    flagRepair = flagUnpack = parResult = False
                    unpackError = True

                logging.info('Starting PostProcessing on %s' + \
                             ' => Repair:%s, Unpack:%s, Delete:%s, Script:%s',
                             filename, flagRepair, flagUnpack, flagDelete, script)
                osx.sendGrowlMsg("Post-processing",filename,osx.NOTIFICATION['pp'])
                ## Run Stage 1: Repair
                if flagRepair:
                    logging.info('Par2 check starting on %s', filename)
                    reAdd = False
                    if not repairSets:
                        logging.info("No par2 sets for %s", filename)
                        nzo.set_unpack_info('repair','[%s] No par2 sets' % filename)

                    for _set in repairSets:
                        logging.info("Running repair on set %s", _set)
                        parfile_nzf = parTable[_set]
                        need_reAdd, res = par2_repair(parfile_nzf, nzo, workdir, _set)
                        if need_reAdd:
                            reAdd = True
                        else:
                            parResult = parResult and res

                    if reAdd:
                        logging.info('Readded %s to queue', filename)
                        sabnzbd.QUEUECOMPLETEACTION_GO = False
                        nzo.set_priority(TOP_PRIORITY)
                        sabnzbd.nzbqueue.add_nzo(nzo)
                        downloader.unidle_downloader()
                        ## Break out, further downloading needed
                        continue

                    logging.info('Par2 check finished on %s', filename)

                mailResult = parResult
                jobResult = 1
                if parResult: jobResult = 0

                ## Check if user allows unsafe post-processing
                if not cfg.SAFE_POSTPROC.get():
                    parResult = True

                ## Determine class directory
                if config.get_categories():
                    complete_dir = Cat2Dir(cat, cfg.COMPLETE_DIR.get_path())
                elif cfg.CREATE_GROUP_FOLDERS.get():
                    complete_dir = addPrefixes(cfg.COMPLETE_DIR.get_path(), nzo)
                    complete_dir = create_dirs(complete_dir)
                else:
                    complete_dir = cfg.COMPLETE_DIR.get_path()
                base_dir = os.path.normpath(complete_dir)

                ## Determine destination directory
                dirname = nzo.get_original_dirname()
                nzo.set_dirname(dirname)

                ## TV/Movie/Date Renaming code part 1 - detect and construct paths
                file_sorter = Sorter(cat)
                complete_dir = file_sorter.detect(dirname, complete_dir)

                workdir_complete = get_unique_path(os.path.join(complete_dir, dirname), create_dir=True)
                tmp_workdir_complete = prefix(workdir_complete, '_UNPACK_')
                try:
                    os.rename(workdir_complete, tmp_workdir_complete)
                except:
                    pass # On failure, just use the original name

                newfiles = []
                ## Run Stage 2: Unpack
                if flagUnpack:
                    if parResult:
                        #set the current nzo status to "Extracting...". Used in History
                        nzo.set_status("Extracting...")
                        logging.info("Running unpack_magic on %s", filename)
                        unpackError, newfiles = unpack_magic(nzo, workdir, tmp_workdir_complete, flagDelete, (), (), (), ())
                        logging.info("unpack_magic finished on %s", filename)
                    else:
                        nzo.set_unpack_info('unpack','No post-processing because of failed verification')

                ## Move any (left-over) files to destination
                nzo.set_status("Moving...")
                nzo.set_action_line('Moving', '...')
                for root, dirs, files in os.walk(workdir):
                    for _file in files:
                        path = os.path.join(root, _file)
                        new_path = path.replace(workdir, tmp_workdir_complete)
                        path, new_path = get_unique_filename(path,new_path)
                        move_to_path(path, new_path, unique=False)

                ## Remove download folder
                try:
                    if os.path.exists(workdir):
                        os.rmdir(workdir)
                except:
                    logging.error(T('error-ppDelWorkdir@1'), workdir)
                    logging.debug("Traceback: ", exc_info = True)


                if parResult:
                    ## Remove files matching the cleanup list
                    CleanUpList(tmp_workdir_complete, True)

                    ## Check if this is an NZB-only download, if so redirect to queue
                    nzb_list = NzbRedirect(tmp_workdir_complete, pp, script, cat, priority=priority)
                    if nzb_list:
                        nzo.set_unpack_info('download', 'Sent %s to queue' % nzb_list)
                        try:
                            os.rmdir(tmp_workdir_complete)
                        except:
                            pass
                    else:
                        CleanUpList(tmp_workdir_complete, False)

                if not nzb_list:
                    ## Give destination its final name
                    if unpackError or not parResult:
                        workdir_complete = tmp_workdir_complete.replace('_UNPACK_', '_FAILED_')
                        workdir_complete = get_unique_path(workdir_complete, n=0, create_dir=False)

                    try:
                        os.rename(tmp_workdir_complete, workdir_complete)
                        nzo.set_dirname(os.path.basename(workdir_complete))
                    except:
                        logging.error(T('error-ppRename@2'), tmp_workdir_complete, workdir_complete)
                        logging.debug("Traceback: ", exc_info = True)

                    if unpackError: jobResult = jobResult + 2

                    if cfg.IGNORE_SAMPLES.get() > 0:
                        remove_samples(workdir_complete)

                    ## TV/Movie/Date Renaming code part 2 - rename and move files to parent folder
                    if not unpackError or parResult:
                        if newfiles and file_sorter.is_sortfile():
                            file_sorter.rename(newfiles, workdir_complete)
                            workdir_complete = file_sorter.move(workdir_complete)

                    ## Set permissions right
                    if cfg.UMASK.get() and not sabnzbd.WIN32:
                        perm_script(workdir_complete, cfg.UMASK.get())

                    ## Run the user script
                    fname = ""
                    if (not nzb_list) and cfg.SCRIPT_DIR.get_path() and script and script!='None' and script!='Default':
                        #set the current nzo status to "Ext Script...". Used in History
                        script_path = os.path.join(cfg.SCRIPT_DIR.get_path(), script)
                        if os.path.exists(script_path):
                            nzo.set_status("Running Script...")
                            nzo.set_action_line('Running Script', script)
                            nzo.set_unpack_info('script','Running user script %s' % script, unique=True)
                            script_log, script_ret = external_processing(script_path, workdir_complete, filename, msgid, dirname, cat, group, jobResult)
                            script_line = get_last_line(script_log)
                            if script_log:
                                fname = nzo.get_nzo_id()
                            if script_line:
                                nzo.set_unpack_info('script', script_line, unique=True)
                            else:
                                nzo.set_unpack_info('script', 'Ran %s' % script, unique=True)
                    else:
                        script = ""
                        script_line = ""
                        script_ret = 0

                    ## Email the results
                    if (not nzb_list) and cfg.EMAIL_ENDJOB.get():
                        if (cfg.EMAIL_ENDJOB.get() == 1) or (cfg.EMAIL_ENDJOB.get() == 2 and (unpackError or not parResult)):
                            email.endjob(dirname, msgid, cat, mailResult, workdir_complete, nzo.get_bytes_downloaded(),
                                         nzo.get_unpack_info(), script, TRANS(script_log), script_ret)

                    if fname:
                        # Can do this only now, otherwise it would show up in the email
                        if script_ret:
                            script_ret = 'Exit(%s) ' % script_ret
                        else:
                            script_ret = ''
                        if script_line:
                            nzo.set_unpack_info('script','%s%s <a href="./scriptlog?name=%s">(More)</a>' % (script_ret, script_line, urllib.quote(fname)), unique=True)
                        else:
                            nzo.set_unpack_info('script','%s<a href="./scriptlog?name=%s">View script output</a>' % (script_ret, urllib.quote(fname)), unique=True)

                ## Remove newzbin bookmark, if any
                if msgid:
                    sabnzbd.newzbin.delete_bookmark(msgid)

                ## Show final status in history
                if parResult and not unpackError:
                    osx.sendGrowlMsg("Download Completed",filename,osx.NOTIFICATION['pp'])
                    nzo.set_status("Completed")
                else:
                    osx.sendGrowlMsg("Download Failed",filename,osx.NOTIFICATION['pp'])
                    nzo.set_status("Failed")

            except:
                #Cause a crash when reparing par2 sets with accents
                #try:
                logging.error(T('error-ppFailed@1'), filename)
                #except:
                #    pass
                logging.debug("Traceback: ", exc_info = True)
                nzo.set_fail_msg('PostProcessing Crashed, see logfile')
                nzo.set_status("Failed")

            # If the folder only contains one file OR folder, have that as the path
            # Be aware that series/generic/date sorting may move a single file into a folder containing other files
            workdir_complete = one_file_or_folder(workdir_complete)
            workdir_complete = os.path.normpath(workdir_complete)

            # Create a relative path removing the complete_dir folder or category folder
            rel_path = os.path.normpath(workdir_complete).replace(base_dir, '')

            # Log the overall time taken for postprocessing
            postproc_time = int(time.time() - start)

            # Create the history DB instance
            history_db = database.get_history_handle()
            # Add the nzo to the database. Only the path, script and time taken is passed
            # Other information is obtained from the nzo
            history_db.add_history_db(nzo, workdir_complete, rel_path, postproc_time, script_log, script_line)
            # The connection is only used once, so close it here
            history_db.close()

            ## Clean up the NZO
            try:
                logging.info('Cleaning up %s', filename)
                sabnzbd.nzbqueue.cleanup_nzo(nzo)
            except:
                logging.error(T('error-ppCleanup@1'), nzo.get_dirname())
                logging.debug("Traceback: ", exc_info = True)

            # Remove the nzo from the history_queue list
            # This list is simply used for the creation of the history in interface.py
            self.remove(nzo)

            ## Allow download to proceed
            downloader.unidle_downloader()
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
        logging.error(T('error-ppLogFile@1'), path)
        logging.debug("Traceback: ", exc_info = True)
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
        try:
            os.chmod(root, umask)
        except:
            logging.error(T('error-ppPermissions@1'), root)
            logging.debug("Traceback: ", exc_info = True)
        for name in files:
            try:
                os.chmod(join(root, name), umask_file)
            except:
                logging.error(T('error-ppPermissions@1'), join(root, name))
                logging.debug("Traceback: ", exc_info = True)


def Cat2Dir(cat, defdir):
    """ Lookup destination dir for category """
    ddir = defdir
    if cat:
        item = config.get_config('categories', cat.lower())
        if item:
            ddir = item.dir.get()
        else:
            return defdir
        ddir = real_path(cfg.COMPLETE_DIR.get_path(), ddir)
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
        logging.info("Queue has finished, launching: %s (%s)", \
            sabnzbd.QUEUECOMPLETEACTION, sabnzbd.QUEUECOMPLETEARG)
        if sabnzbd.QUEUECOMPLETEARG:
            sabnzbd.QUEUECOMPLETEACTION(sabnzbd.QUEUECOMPLETEARG)
        else:
            Thread(target=sabnzbd.QUEUECOMPLETEACTION).start()

        sabnzbd.QUEUECOMPLETEACTION = None
        sabnzbd.QUEUECOMPLETEARG = None
        sabnzbd.QUEUECOMPLETEACTION_GO = False


def CleanUpList(wdir, skip_nzb):
    """ Remove all files matching the cleanup list """

    if cfg.CLEANUP_LIST.get():
        try:
            files = os.listdir(wdir)
        except:
            files = ()
        for _file in files:
            if on_cleanup_list(_file, skip_nzb):
                path = os.path.join(wdir, _file)
                try:
                    logging.info("Removing unwanted file %s", path)
                    os.remove(path)
                except:
                    logging.error(T('error-ppDelFailed@1'), path)
                    logging.debug("Traceback: ", exc_info = True)


def prefix(path, pre):
    """ Apply prefix to last part of path """
    p, d = os.path.split(path)
    return os.path.join(p, pre + d)


def NzbRedirect(wdir, pp, script, cat, priority):
    """ Check if this job contains only NZB files,
        if so send to queue and remove if on CleanList
        Returns list of processed NZB's
    """
    list = []

    try:
        files = os.listdir(wdir)
    except:
        files = []

    for file in files:
        if os.path.splitext(file)[1].lower() != '.nzb':
            return list

    # Process all NZB files
    keep = not on_cleanup_list("x.nzb", False)
    for file in files:
        if file.lower().endswith('.nzb'):
            dirscanner.ProcessSingleFile(file, os.path.join(wdir, file), pp, script, cat, priority=priority, keep=keep)
            list.append(file)

    return list


def one_file_or_folder(dir):
    """ If the dir only contains one file or folder, join that file/folder onto the path """
    if os.path.exists(dir) and os.path.isdir(dir):
        cont = os.listdir(dir)
        if len(cont) == 1:
            dir = os.path.join(dir, cont[0])
            dir = one_file_or_folder(dir)
    return dir


def get_last_line(txt):
    """ Return last non-empty line of a text, trim to 150 max """
    lines = txt.split('\n')
    n = len(lines) - 1
    while n >= 0 and not lines[n].strip('\r\t '):
        n = n - 1

    line = lines[n].strip('\r\t ')
    if len(line) >= 150:
        line = line[:147] + '...'
    return line

def remove_samples(path):
    RE_SAMPLE = re.compile(sample_match, re.I)
    for root, dirs, files in os.walk(path):
        for _file in files:
            if RE_SAMPLE.search(_file):
                path = os.path.join(root, _file)
                try:
                    logging.info("Removing unwanted sample file %s", path)
                    os.remove(path)
                except:
                    logging.error(T('error-ppDelFailed@1'), path)
                    logging.debug("Traceback: ", exc_info = True)
