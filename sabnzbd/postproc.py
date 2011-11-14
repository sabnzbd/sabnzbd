#!/usr/bin/python -OO
# Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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

from sabnzbd.newsunpack import unpack_magic, par2_repair, external_processing, sfv_check
from threading import Thread
from sabnzbd.misc import real_path, get_unique_path, create_dirs, move_to_path, \
                         get_unique_filename, make_script_path, \
                         on_cleanup_list, renamer, remove_dir, remove_all, globber
from sabnzbd.tvsort import Sorter
from sabnzbd.constants import REPAIR_PRIORITY, POSTPROC_QUEUE_FILE_NAME, \
     POSTPROC_QUEUE_VERSION, sample_match, JOB_ADMIN
from sabnzbd.encoding import TRANS, unicoder
from sabnzbd.newzbin import Bookmarks
import sabnzbd.emailer as emailer
import sabnzbd.dirscanner as dirscanner
import sabnzbd.downloader
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.nzbqueue
import sabnzbd.database as database
from sabnzbd.utils import osx


#------------------------------------------------------------------------------
class PostProcessor(Thread):
    """ PostProcessor thread, designed as Singleton """
    do = None  # Link to instance of the thread

    def __init__ (self, queue=None, history_queue=None):
        """ Initialize, optionally passing existing queue """
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
        self.__stop = False
        self.paused = False
        PostProcessor.do = self

        self.__busy = False # True while a job is being processed

    def save(self):
        """ Save postproc queue """
        logging.info("Saving postproc queue")
        sabnzbd.save_admin((POSTPROC_QUEUE_VERSION, self.history_queue), POSTPROC_QUEUE_FILE_NAME)

    def load(self):
        """ Save postproc queue """
        self.history_queue = []
        logging.info("Loading postproc queue")
        data = sabnzbd.load_admin(POSTPROC_QUEUE_FILE_NAME)
        if data is None:
            return
        try:
            version, history_queue = data
            if POSTPROC_QUEUE_VERSION != version:
                logging.warning(Ta('Failed to load postprocessing queue: Wrong version (need:%s, found:%s)'), POSTPROC_QUEUE_VERSION, version)
            if isinstance(history_queue, list):
                self.history_queue = [nzo for nzo in history_queue if os.path.exists(nzo.downpath)]
        except:
            logging.info('Corrupt %s file, discarding', POSTPROC_QUEUE_FILE_NAME)
            logging.info("Traceback: ", exc_info = True)

    def delete(self, nzo_id, del_files=False):
        """ Remove a job from the post processor queue """
        for nzo in self.history_queue:
            if nzo.nzo_id == nzo_id:
                self.remove(nzo)
                nzo.purge_data(keep_basic=True, del_files=del_files)
                logging.info('Removed job %s from postproc queue', nzo.work_name)
                nzo.work_name = '' # Mark as deleted job
                break

    def process(self, nzo):
        """ Push on finished job in the queue """
        if nzo not in self.history_queue:
            self.history_queue.append(nzo)
        self.queue.put(nzo)
        self.save()

    def remove(self, nzo):
        """ Remove given nzo from the queue """
        try:
            self.history_queue.remove(nzo)
        except:
            nzo_id = getattr(nzo, 'nzo_id', 'unknown id')
            logging.error(Ta('Failed to remove nzo from postproc queue (id)'), nzo_id)
        self.save()

    def stop(self):
        """ Stop thread after finishing running job """
        self.queue.put(None)
        self.save()
        self.__stop = True

    def empty(self):
        """ Return True if pp queue is empty """
        return self.queue.empty() and not self.__busy

    def get_queue(self):
        """ Return list of NZOs that still need to be processed """
        return [nzo for nzo in self.history_queue if nzo.work_name]

    def get_path(self, nzo_id):
        """ Return download path for given nzo_id or None when not found """
        for nzo in self.history_queue:
            if nzo.nzo_id == nzo_id:
                return nzo.downpath
        return None

    def run(self):
        """ Actual processing """
        check_eoq = False

        while not self.__stop:
            self.__busy = False

            if self.paused:
                time.sleep(5)
                continue

            try:
                nzo = self.queue.get(timeout=3)
            except Queue.Empty:
                if check_eoq:
                    check_eoq = False
                    handle_empty_queue()
                continue

            ## Stop job
            if not nzo:
                continue

            ## Job was already deleted.
            if not nzo.work_name:
                check_eoq = True
                continue

            ## Flag NZO as being processed
            nzo.pp_active = True

            ## Pause downloader, if users wants that
            if cfg.pause_on_post_processing():
                sabnzbd.downloader.Downloader.do.wait_for_postproc()

            self.__busy = True
            if process_job(nzo):
                self.remove(nzo)
            check_eoq = True

            ## Allow download to proceed
            sabnzbd.downloader.Downloader.do.resume_from_postproc()

#end PostProcessor class


#------------------------------------------------------------------------------
def process_job(nzo):
    """ Process one job """
    assert isinstance(nzo, sabnzbd.nzbstuff.NzbObject)
    start = time.time()

    # keep track of whether we can continue
    all_ok = True
    # keep track of par problems
    par_error = False
    # keep track of any unpacking errors
    unpack_error = False
    nzb_list = []
    # These need to be initialised incase of a crash
    workdir_complete = ''
    postproc_time = 0
    script_log = ''
    script_line = ''
    crash_msg = ''

    ## Get the job flags
    nzo.save_attribs()
    flag_repair, flag_unpack, flag_delete = nzo.repair_opts
    # Normalize PP
    if flag_delete: flag_unpack = True
    if flag_unpack: flag_repair = True

    # Get the NZB name
    filename = nzo.final_name
    msgid = nzo.msgid

    if cfg.allow_streaming() and not (flag_repair or flag_unpack or flag_delete):
        # After streaming, force +D
        nzo.set_pp(3)
        nzo.status = 'Failed'
        nzo.save_attribs()
        all_ok = False

    try:
        if nzo.aborted:
            crash_msg = T('Download aborted due to admin errros')
            raise IOError

        # Get the folder containing the download result
        workdir = nzo.downpath
        tmp_workdir_complete = None

        # if no files are present (except __admin__), fail the job
        if len(globber(workdir)) < 2:
            emsg = T('Download failed - Out of your server\'s retention?')
            nzo.fail_msg = emsg
            nzo.status = 'Failed'
            # do not run unpacking or parity verification
            flag_repair = flag_unpack = False
            par_error = unpack_error = True
            all_ok = False

        script = nzo.script
        cat = nzo.cat

        logging.info('Starting PostProcessing on %s' + \
                     ' => Repair:%s, Unpack:%s, Delete:%s, Script:%s, Cat:%s',
                     filename, flag_repair, flag_unpack, flag_delete, script, cat)

        ## Par processing, if enabled
        if flag_repair:
            par_error, re_add = parring(nzo, workdir)
            if re_add:
                # Try to get more par files
                return False

        ## Check if user allows unsafe post-processing
        if flag_repair and cfg.safe_postproc():
            all_ok = all_ok and not par_error

        # Set complete dir to workdir in case we need to abort
        workdir_complete = workdir
        dirname = nzo.final_name

        if all_ok:
            one_folder = False
            ## Determine class directory
            if cfg.create_group_folders():
                complete_dir = addPrefixes(cfg.complete_dir.get_path(), nzo.dirprefix)
                complete_dir = create_dirs(complete_dir)
            else:
                catdir = config.get_categories(cat).dir()
                if catdir.endswith('*'):
                    catdir = catdir.strip('*')
                    one_folder = True
                complete_dir = real_path(cfg.complete_dir.get_path(), catdir)

            ## TV/Movie/Date Renaming code part 1 - detect and construct paths
            file_sorter = Sorter(cat)
            complete_dir = file_sorter.detect(dirname, complete_dir)
            if file_sorter.is_sortfile():
                one_folder = False

            if one_folder:
                workdir_complete = create_dirs(complete_dir)
            elif file_sorter.is_fullpath:
                workdir_complete = get_unique_path(complete_dir, create_dir=True)
            else:
                workdir_complete = get_unique_path(os.path.join(complete_dir, dirname), create_dir=True)
            if not workdir_complete or not os.path.exists(workdir_complete):
                crash_msg = T('Cannot create final folder %s') % unicoder(os.path.join(complete_dir, dirname))
                raise IOError

            if cfg.folder_rename() and not one_folder:
                tmp_workdir_complete = prefix(workdir_complete, '_UNPACK_')
                try:
                    renamer(workdir_complete, tmp_workdir_complete)
                except:
                    pass # On failure, just use the original name
            else:
                tmp_workdir_complete = workdir_complete

            newfiles = []
            ## Run Stage 2: Unpack
            if flag_unpack:
                if all_ok:
                    #set the current nzo status to "Extracting...". Used in History
                    nzo.status = 'Extracting'
                    logging.info("Running unpack_magic on %s", filename)
                    unpack_error, newfiles = unpack_magic(nzo, workdir, tmp_workdir_complete, flag_delete, one_folder, (), (), (), ())
                    logging.info("unpack_magic finished on %s", filename)
                else:
                    nzo.set_unpack_info('Unpack', T('No post-processing because of failed verification'))

            if cfg.safe_postproc():
                all_ok = all_ok and not unpack_error

            if all_ok:
                ## Move any (left-over) files to destination
                nzo.status = 'Moving'
                nzo.set_action_line(T('Moving'), '...')
                for root, dirs, files in os.walk(workdir):
                    if not root.endswith(JOB_ADMIN):
                        for file_ in files:
                            path = os.path.join(root, file_)
                            new_path = path.replace(workdir, tmp_workdir_complete)
                            new_path = get_unique_filename(new_path)
                            move_to_path(path, new_path, unique=False)

            ## Set permissions right
            if not sabnzbd.WIN32:
                perm_script(tmp_workdir_complete, cfg.umask())

            if all_ok:
                ## Remove files matching the cleanup list
                cleanup_list(tmp_workdir_complete, True)

                ## Check if this is an NZB-only download, if so redirect to queue
                ## except when PP was Download-only
                if flag_repair:
                    nzb_list = nzb_redirect(tmp_workdir_complete, nzo.final_name, nzo.pp, script, cat, priority=nzo.priority)
                else:
                    nzb_list = None
                if nzb_list:
                    nzo.set_unpack_info('Download', T('Sent %s to queue') % unicoder(nzb_list))
                    try:
                        remove_dir(tmp_workdir_complete)
                    except:
                        pass
                else:
                    cleanup_list(tmp_workdir_complete, False)

        script_output = ''
        script_ret = 0
        if not nzb_list:
            ## Give destination its final name
            if cfg.folder_rename() and tmp_workdir_complete and not one_folder:
                if not all_ok:
                    workdir_complete = tmp_workdir_complete.replace('_UNPACK_', '_FAILED_')
                    workdir_complete = get_unique_path(workdir_complete, n=0, create_dir=False)
                try:
                    collapse_folder(tmp_workdir_complete, workdir_complete)
                except:
                    logging.error(Ta('Error renaming "%s" to "%s"'), tmp_workdir_complete, workdir_complete)
                    logging.info("Traceback: ", exc_info = True)

            job_result = int(par_error) + int(unpack_error)*2

            if cfg.ignore_samples() > 0:
                remove_samples(workdir_complete)

            ## TV/Movie/Date Renaming code part 2 - rename and move files to parent folder
            if all_ok:
                if newfiles and file_sorter.is_sortfile():
                    file_sorter.rename(newfiles, workdir_complete)
                    workdir_complete = file_sorter.move(workdir_complete)

            ## Run the user script
            script_path = make_script_path(script)
            if all_ok and (not nzb_list) and script_path:
                #set the current nzo status to "Ext Script...". Used in History
                nzo.status = 'Running'
                nzo.set_action_line(T('Running script'), unicoder(script))
                nzo.set_unpack_info('Script', T('Running user script %s') % unicoder(script), unique=True)
                script_log, script_ret = external_processing(script_path, workdir_complete, nzo.filename,
                                                             msgid, dirname, cat, nzo.group, job_result)
                script_line = get_last_line(script_log)
                if script_log:
                    script_output = nzo.nzo_id
                if script_line:
                    nzo.set_unpack_info('Script', unicoder(script_line), unique=True)
                else:
                    nzo.set_unpack_info('Script', T('Ran %s') % unicoder(script), unique=True)
            else:
                script = ""
                script_line = ""
                script_ret = 0

        ## Email the results
        if (not nzb_list) and cfg.email_endjob():
            if (cfg.email_endjob() == 1) or (cfg.email_endjob() == 2 and (unpack_error or par_error)):
                emailer.endjob(dirname, msgid, cat, all_ok, workdir_complete, nzo.bytes_downloaded,
                               nzo.unpack_info, script, TRANS(script_log), script_ret)

        if script_output:
            # Can do this only now, otherwise it would show up in the email
            if script_ret:
                script_ret = 'Exit(%s) ' % script_ret
            else:
                script_ret = ''
            if script_line:
                nzo.set_unpack_info('Script',
                                    u'%s%s <a href="./scriptlog?name=%s">(%s)</a>' % (script_ret, unicoder(script_line), urllib.quote(script_output),
                                     T('More')), unique=True)
            else:
                nzo.set_unpack_info('Script',
                                    u'%s<a href="./scriptlog?name=%s">%s</a>' % (script_ret, urllib.quote(script_output),
                                    T('View script output')), unique=True)

        ## Cleanup again, including NZB files
        if all_ok:
            cleanup_list(workdir_complete, False)

        ## Remove newzbin bookmark, if any
        if msgid and all_ok:
            Bookmarks.do.del_bookmark(msgid)
        elif all_ok:
            sabnzbd.proxy_rm_bookmark(nzo.url)

        ## Show final status in history
        if all_ok:
            osx.sendGrowlMsg(T('Download Completed'), filename, osx.NOTIFICATION['complete'])
            nzo.status = 'Completed'
        else:
            osx.sendGrowlMsg(T('Download Failed'), filename, osx.NOTIFICATION['complete'])
            nzo.status = 'Failed'

    except:
        logging.error(Ta('Post Processing Failed for %s (%s)'), filename, crash_msg)
        if not crash_msg:
            logging.info("Traceback: ", exc_info = True)
            crash_msg = T('see logfile')
        nzo.fail_msg = T('PostProcessing was aborted (%s)') % unicoder(crash_msg)
        osx.sendGrowlMsg(T('Download Failed'), filename, osx.NOTIFICATION['complete'])
        nzo.status = 'Failed'
        par_error = True
        all_ok = False

    if all_ok:
        # If the folder only contains one file OR folder, have that as the path
        # Be aware that series/generic/date sorting may move a single file into a folder containing other files
        workdir_complete = one_file_or_folder(workdir_complete)
        workdir_complete = os.path.normpath(workdir_complete)

    # Log the overall time taken for postprocessing
    postproc_time = int(time.time() - start)

    # Create the history DB instance
    history_db = database.get_history_handle()
    # Add the nzo to the database. Only the path, script and time taken is passed
    # Other information is obtained from the nzo
    history_db.add_history_db(nzo, workdir_complete, nzo.downpath, postproc_time, script_log, script_line)
    # The connection is only used once, so close it here
    history_db.close()

    ## Clean up the NZO
    try:
        logging.info('Cleaning up %s (keep_basic=%s)', filename, str(not all_ok))
        sabnzbd.nzbqueue.NzbQueue.do.cleanup_nzo(nzo, keep_basic=not all_ok)
    except:
        logging.error(Ta('Cleanup of %s failed.'), nzo.final_name)
        logging.info("Traceback: ", exc_info = True)

    ## Remove download folder
    if all_ok:
        try:
            if os.path.exists(workdir):
                logging.debug('Removing workdir %s', workdir)
                remove_all(workdir, recursive=True)
        except:
            logging.error(Ta('Error removing workdir (%s)'), workdir)
            logging.info("Traceback: ", exc_info = True)

    return True



#------------------------------------------------------------------------------
def parring(nzo, workdir):
    """ Perform par processing. Returns: (par_error, re_add)
    """
    filename = nzo.final_name
    osx.sendGrowlMsg(T('Post-processing'), nzo.final_name, osx.NOTIFICATION['pp'])
    logging.info('Par2 check starting on %s', filename)

    ## Collect the par files
    if nzo.partable:
        par_table = nzo.partable.copy()
    else:
        par_table = {}
    repair_sets = par_table.keys()

    re_add = False
    par_error = False

    if repair_sets:

        for set_ in repair_sets:
            logging.info("Running repair on set %s", set_)
            parfile_nzf = par_table[set_]
            need_re_add, res = par2_repair(parfile_nzf, nzo, workdir, set_)
            if need_re_add:
                re_add = True
            else:
                par_error = par_error or not res

        if re_add:
            logging.info('Readded %s to queue', filename)
            nzo.priority = REPAIR_PRIORITY
            sabnzbd.nzbqueue.add_nzo(nzo)
            sabnzbd.downloader.Downloader.do.resume_from_postproc()

        logging.info('Par2 check finished on %s', filename)

    if par_error or not repair_sets:
        # See if alternative SFV check is possible
        if cfg.sfv_check():
            sfvs = globber(workdir, '*.sfv')
        else:
            sfvs = None
        if sfvs:
            par_error = False
            nzo.set_unpack_info('Repair', T('Trying SFV verification'))
            for sfv in sfvs:
                if not sfv_check(sfv):
                    nzo.set_unpack_info('Repair', T('Some files failed to verify against "%s"') % unicoder(os.path.basename(sfv)))
                    par_error = True
            if not par_error:
                nzo.set_unpack_info('Repair', T('Verified successfully using SFV files'))
        elif not repair_sets:
            logging.info("No par2 sets for %s", filename)
            nzo.set_unpack_info('Repair', T('[%s] No par2 sets') % unicoder(filename))

    return par_error, re_add



#------------------------------------------------------------------------------

def perm_script(wdir, umask):
    """ Give folder tree and its files their proper permissions """
    from os.path import join

    try:
        # Make sure that user R is on
        umask = int(umask, 8) | int('0400', 8)
        report_errors = True
    except ValueError:
        # No or no valid permissions
        # Use the effective permissions of the session
        # Don't report errors (because the system might not support it)
        umask = int('0777', 8) & (sabnzbd.ORG_UMASK ^ int('0777', 8))
        report_errors = False

    # Remove X bits for files
    umask_file = umask & int('7666', 8)

    # Parse the dir/file tree and set permissions
    for root, dirs, files in os.walk(wdir):
        try:
            os.chmod(root, umask)
        except:
            if report_errors:
                logging.error(Ta('Cannot change permissions of %s'), root)
                logging.info("Traceback: ", exc_info = True)
        for name in files:
            try:
                os.chmod(join(root, name), umask_file)
            except:
                if report_errors:
                    logging.error(Ta('Cannot change permissions of %s'), join(root, name))
                    logging.info("Traceback: ", exc_info = True)


def addPrefixes(path, dirprefix):
    """ Add list of prefixes as sub folders to path
        '/my/path' and ['a', 'b', 'c'] will give '/my/path/a/b/c'
    """
    for folder in dirprefix:
        if not folder:
            continue
        if not path:
            break
        basepath = os.path.basename(os.path.abspath(path))
        if folder != basepath.lower():
            path = os.path.join(path, folder)
    return path


def handle_empty_queue():
    """ Check if empty queue calls for action """
    if sabnzbd.nzbqueue.NzbQueue.do.actives() == 0:
        sabnzbd.save_state()
        logging.info("Queue has finished, launching: %s (%s)", \
            sabnzbd.QUEUECOMPLETEACTION, sabnzbd.QUEUECOMPLETEARG)
        if sabnzbd.QUEUECOMPLETEARG:
            sabnzbd.QUEUECOMPLETEACTION(sabnzbd.QUEUECOMPLETEARG)
        else:
            Thread(target=sabnzbd.QUEUECOMPLETEACTION).start()

        sabnzbd.change_queue_complete_action(cfg.queue_complete(), new=False)


def cleanup_list(wdir, skip_nzb):
    """ Remove all files whose extension matches the cleanup list,
        optionally ignoring the nzb extension """
    if cfg.cleanup_list():
        try:
            files = os.listdir(wdir)
        except:
            files = ()
        for file in files:
            path = os.path.join(wdir, file)
            if os.path.isdir(path):
                cleanup_list(path, skip_nzb)
            else:
                if on_cleanup_list(file, skip_nzb):
                    try:
                        logging.info("Removing unwanted file %s", path)
                        os.remove(path)
                    except:
                        logging.error(Ta('Removing %s failed'), path)
                        logging.info("Traceback: ", exc_info = True)


def prefix(path, pre):
    """ Apply prefix to last part of path
        '/my/path' and 'hi_' will give '/my/hi_path'
    """
    p, d = os.path.split(path)
    return os.path.join(p, pre + d)


def nzb_redirect(wdir, nzbname, pp, script, cat, priority):
    """ Check if this job contains only NZB files,
        if so send to queue and remove if on CleanList
        Returns list of processed NZB's
    """
    lst = []

    try:
        files = os.listdir(wdir)
    except:
        files = []

    for file_ in files:
        if os.path.splitext(file_)[1].lower() != '.nzb':
            return lst

    # For a single NZB, use the current job name
    if len(files) != 1:
        nzbname = None

    # Process all NZB files
    for file_ in files:
        if file_.lower().endswith('.nzb'):
            dirscanner.ProcessSingleFile(file_, os.path.join(wdir, file_), pp, script, cat,
                                         priority=priority, keep=False, dup_check=False, nzbname=nzbname)
            lst.append(file_)

    return lst


def one_file_or_folder(folder):
    """ If the dir only contains one file or folder, join that file/folder onto the path """
    if os.path.exists(folder) and os.path.isdir(folder):
        cont = os.listdir(folder)
        if len(cont) == 1:
            folder = os.path.join(folder, cont[0])
            folder = one_file_or_folder(folder)
    return folder


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
    """ Remove all files that match the sample pattern """
    RE_SAMPLE = re.compile(sample_match, re.I)
    for root, dirs, files in os.walk(path):
        for file_ in files:
            if RE_SAMPLE.search(file_):
                path = os.path.join(root, file_)
                try:
                    logging.info("Removing unwanted sample file %s", path)
                    os.remove(path)
                except:
                    logging.error(Ta('Removing %s failed'), path)
                    logging.info("Traceback: ", exc_info = True)


#------------------------------------------------------------------------------
def collapse_folder(oldpath, newpath):
    """ Rename folder, collapsing when there's just a single subfolder
        oldpath --> newpath OR oldpath/subfolder --> newpath
    """
    orgpath = oldpath
    items = globber(oldpath)
    if len(items) == 1:
        folder_path = items[0]
        folder = os.path.split(folder_path)[1]
        if os.path.isdir(folder_path) and folder not in ('VIDEO_TS', 'AUDIO_TS'):
            logging.info('Collapsing %s', os.path.join(newpath, folder))
            oldpath = folder_path

    renamer(oldpath, newpath)
    try:
        remove_dir(orgpath)
    except:
        pass
