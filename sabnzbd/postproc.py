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
sabnzbd.postproc - threaded post-processing of jobs
"""

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
    make_script_path, short_path, long_path, clip_path, \
    on_cleanup_list, renamer, remove_dir, remove_all, globber, globber_full, \
    set_permissions, cleanup_empty_directories, check_win_maxpath, fix_unix_encoding, \
    sanitize_and_trim_path
from sabnzbd.tvsort import Sorter
from sabnzbd.constants import REPAIR_PRIORITY, TOP_PRIORITY, POSTPROC_QUEUE_FILE_NAME, \
    POSTPROC_QUEUE_VERSION, sample_match, JOB_ADMIN, Status, VERIFIED_FILE
from sabnzbd.encoding import TRANS, unicoder
from sabnzbd.rating import Rating
import sabnzbd.emailer as emailer
import sabnzbd.dirscanner as dirscanner
import sabnzbd.downloader
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.nzbqueue
import sabnzbd.database as database
import sabnzbd.growler as growler


class PostProcessor(Thread):
    """ PostProcessor thread, designed as Singleton """
    do = None  # Link to instance of the thread

    def __init__(self, queue=None, history_queue=None):
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

        self.__busy = False  # True while a job is being processed

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
                logging.warning(T('Old queue detected, use Status->Repair to convert the queue'))
            elif isinstance(history_queue, list):
                self.history_queue = [nzo for nzo in history_queue if os.path.exists(nzo.downpath)]
        except:
            logging.info('Corrupt %s file, discarding', POSTPROC_QUEUE_FILE_NAME)
            logging.info("Traceback: ", exc_info=True)

    def delete(self, nzo_id, del_files=False):
        """ Remove a job from the post processor queue """
        for nzo in self.history_queue:
            if nzo.nzo_id == nzo_id:
                self.remove(nzo)
                nzo.purge_data(keep_basic=True, del_files=del_files)
                logging.info('Removed job %s from postproc queue', nzo.work_name)
                nzo.work_name = ''  # Mark as deleted job
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
            logging.error(T('Failed to remove nzo from postproc queue (id)') + ' ' + nzo_id)
            logging.info('Traceback: ', exc_info=True)
        self.save()

    def stop(self):
        """ Stop thread after finishing running job """
        self.__stop = True
        self.queue.put(None)
        self.save()

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
                nzo = self.queue.get(timeout=1)
            except Queue.Empty:
                if check_eoq:
                    check_eoq = False
                    handle_empty_queue()
                    continue
                else:
                    nzo = self.queue.get()

            # Stop job
            if not nzo:
                continue

            # Job was already deleted.
            if not nzo.work_name:
                check_eoq = True
                continue

            # Flag NZO as being processed
            nzo.pp_active = True

            # Pause downloader, if users wants that
            if cfg.pause_on_post_processing():
                sabnzbd.downloader.Downloader.do.wait_for_postproc()

            self.__busy = True
            process_job(nzo)
            self.remove(nzo)
            check_eoq = True

            # Allow download to proceed
            sabnzbd.downloader.Downloader.do.resume_from_postproc()


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
    # Signal empty download, for when 'empty_postproc' is enabled
    empty = False
    nzb_list = []
    # These need to be initialized in case of a crash
    workdir_complete = ''
    postproc_time = 0  # @UnusedVariable -- pep8 bug?
    script_log = ''
    script_line = ''
    crash_msg = ''

    # Get the job flags
    nzo.save_attribs()
    flag_repair, flag_unpack, flag_delete = nzo.repair_opts
    # Normalize PP
    if flag_delete:
        flag_unpack = True
    if flag_unpack:
        flag_repair = True

    # Get the NZB name
    filename = nzo.final_name

    if cfg.allow_streaming() and not (flag_repair or flag_unpack or flag_delete):
        # After streaming, force +D
        nzo.set_pp(3)
        nzo.status = Status.FAILED
        nzo.save_attribs()
        all_ok = False

    if nzo.fail_msg:  # Special case: aborted due to too many missing data
        nzo.status = Status.FAILED
        nzo.save_attribs()
        all_ok = False
        par_error = True
        unpack_error = 1

    try:

        # Get the folder containing the download result
        workdir = nzo.downpath
        tmp_workdir_complete = None

        # if no files are present (except __admin__), fail the job
        if all_ok and len(globber(workdir)) < 2:
            if nzo.precheck:
                _enough, ratio = nzo.check_quality()
                req_ratio = float(cfg.req_completion_rate()) / 100.0
                # Make sure that rounded ratio doesn't equal required ratio
                # when it is actually below required
                if (ratio < req_ratio) and (req_ratio - ratio) < 0.001:
                    ratio = req_ratio - 0.001
                emsg = '%.1f%%' % (ratio * 100.0)
                emsg2 = '%.1f%%' % float(cfg.req_completion_rate())
                emsg = T('Download might fail, only %s of required %s available') % (emsg, emsg2)
            else:
                emsg = T('Download failed - Not on your server(s)')
                empty = True
            nzo.fail_msg = emsg
            nzo.set_unpack_info('Fail', emsg)
            nzo.status = Status.FAILED
            # do not run unpacking or parity verification
            flag_repair = flag_unpack = False
            all_ok = cfg.empty_postproc() and empty
            if not all_ok:
                par_error = True
                unpack_error = 1

        script = nzo.script
        cat = nzo.cat

        logging.info('Starting PostProcessing on %s' +
                     ' => Repair:%s, Unpack:%s, Delete:%s, Script:%s, Cat:%s',
                     filename, flag_repair, flag_unpack, flag_delete, script, cat)

        # Set complete dir to workdir in case we need to abort
        workdir_complete = workdir
        dirname = nzo.final_name
        marker_file = None

        # Par processing, if enabled
        if all_ok and flag_repair:
            if not check_win_maxpath(workdir):
                crash_msg = T('Path exceeds 260, repair by "par2" is not possible')
                raise WindowsError
            par_error, re_add = parring(nzo, workdir)
            if re_add:
                # Try to get more par files
                return False

        # Check if user allows unsafe post-processing
        if flag_repair and cfg.safe_postproc():
            all_ok = all_ok and not par_error

        if all_ok:
            fix_unix_encoding(workdir)
            one_folder = False
            # Determine class directory
            if cfg.create_group_folders():
                complete_dir = addPrefixes(cfg.complete_dir.get_path(), nzo.dirprefix)
                complete_dir = create_dirs(complete_dir)
            else:
                catdir = config.get_categories(cat).dir()
                if catdir.endswith('*'):
                    catdir = catdir.strip('*')
                    one_folder = True
                complete_dir = real_path(cfg.complete_dir.get_path(), catdir)
            complete_dir = long_path(complete_dir)

            # TV/Movie/Date Renaming code part 1 - detect and construct paths
            if cfg.enable_meta():
                file_sorter = Sorter(nzo, cat)
            else:
                file_sorter = Sorter(None, cat)
            complete_dir = file_sorter.detect(dirname, complete_dir)
            if file_sorter.sort_file:
                one_folder = False

            complete_dir = sanitize_and_trim_path(complete_dir)

            if one_folder:
                workdir_complete = create_dirs(complete_dir)
            else:
                workdir_complete = get_unique_path(os.path.join(complete_dir, dirname), create_dir=True)
                marker_file = set_marker(workdir_complete)

            if not workdir_complete or not os.path.exists(workdir_complete):
                crash_msg = T('Cannot create final folder %s') % unicoder(os.path.join(complete_dir, dirname))
                raise IOError

            if cfg.folder_rename() and not one_folder:
                tmp_workdir_complete = prefix(workdir_complete, '_UNPACK_')
                try:
                    renamer(workdir_complete, tmp_workdir_complete)
                except:
                    pass  # On failure, just use the original name
            else:
                tmp_workdir_complete = workdir_complete

            newfiles = []
            # Run Stage 2: Unpack
            if flag_unpack:
                if all_ok:
                    # set the current nzo status to "Extracting...". Used in History
                    nzo.status = Status.EXTRACTING
                    logging.info("Running unpack_magic on %s", filename)
                    short_complete = short_path(tmp_workdir_complete)
                    unpack_error, newfiles = unpack_magic(nzo, short_path(workdir), short_complete, flag_delete, one_folder, (), (), (), (), ())
                    if short_complete != tmp_workdir_complete:
                        newfiles = [f.replace(short_complete, tmp_workdir_complete) for f in newfiles]
                    logging.info("unpack_magic finished on %s", filename)
                else:
                    nzo.set_unpack_info('Unpack', T('No post-processing because of failed verification'))

            if cfg.safe_postproc():
                all_ok = all_ok and not unpack_error

            if all_ok:
                # Move any (left-over) files to destination
                nzo.status = Status.MOVING
                nzo.set_action_line(T('Moving'), '...')
                for root, _dirs, files in os.walk(workdir):
                    if not root.endswith(JOB_ADMIN):
                        for file_ in files:
                            path = os.path.join(root, file_)
                            new_path = path.replace(workdir, tmp_workdir_complete)
                            ok, new_path = move_to_path(path, new_path)
                            newfiles.append(new_path)
                            if not ok:
                                nzo.set_unpack_info('Unpack', T('Failed moving %s to %s') % (unicoder(path), unicoder(new_path)))
                                all_ok = False
                                break

            # Set permissions right
            set_permissions(tmp_workdir_complete)

            if all_ok and marker_file:
                del_marker(os.path.join(tmp_workdir_complete, marker_file))
                remove_from_list(marker_file, newfiles)

            if all_ok:
                # Remove files matching the cleanup list
                cleanup_list(tmp_workdir_complete, True)

                # Check if this is an NZB-only download, if so redirect to queue
                # except when PP was Download-only
                if flag_repair:
                    nzb_list = nzb_redirect(tmp_workdir_complete, nzo.final_name, nzo.pp, script, cat, priority=nzo.priority)
                else:
                    nzb_list = None
                if nzb_list:
                    nzo.set_unpack_info('Download', T('Sent %s to queue') % unicoder(nzb_list))
                    cleanup_empty_directories(tmp_workdir_complete)
                else:
                    cleanup_list(tmp_workdir_complete, False)

        script_output = ''
        script_ret = 0
        if not nzb_list:
            # Give destination its final name
            if cfg.folder_rename() and tmp_workdir_complete and not one_folder:
                if all_ok:
                    try:
                        newfiles = rename_and_collapse_folder(tmp_workdir_complete, workdir_complete, newfiles)
                    except:
                        logging.error(T('Error renaming "%s" to "%s"'), clip_path(tmp_workdir_complete), clip_path(workdir_complete))
                        logging.info('Traceback: ', exc_info=True)
                        # Better disable sorting because filenames are all off now
                        file_sorter.sort_file = None
                else:
                    workdir_complete = tmp_workdir_complete.replace('_UNPACK_', '_FAILED_')
                    workdir_complete = get_unique_path(workdir_complete, n=0, create_dir=False)
                    workdir_complete = workdir_complete

            if empty:
                job_result = -1
            else:
                job_result = int(par_error) + int(bool(unpack_error)) * 2

            if cfg.ignore_samples() > 0:
                remove_samples(workdir_complete)

            # TV/Movie/Date Renaming code part 2 - rename and move files to parent folder
            if all_ok and file_sorter.sort_file:
                if newfiles:
                    file_sorter.rename(newfiles, workdir_complete)
                    workdir_complete, ok = file_sorter.move(workdir_complete)
                else:
                    workdir_complete, ok = file_sorter.rename_with_ext(workdir_complete)
                if not ok:
                    nzo.set_unpack_info('Unpack', T('Failed to move files'))
                    all_ok = False

            # Run the user script
            script_path = make_script_path(script)
            if (all_ok or not cfg.safe_postproc()) and (not nzb_list) and script_path:
                # set the current nzo status to "Ext Script...". Used in History
                nzo.status = Status.RUNNING
                nzo.set_action_line(T('Running script'), unicoder(script))
                nzo.set_unpack_info('Script', T('Running user script %s') % unicoder(script), unique=True)
                script_log, script_ret = external_processing(short_path(script_path, False), short_path(workdir_complete, False), nzo.filename,
                                                             dirname, cat, nzo.group, job_result,
                                                             nzo.nzo_info.get('failure', ''))
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

        # Maybe bad script result should fail job
        if script_ret and cfg.script_can_fail():
            script_error = True
            all_ok = False
            nzo.fail_msg = T('Script exit code is %s') % script_ret
        else:
            script_error = False

        # Email the results
        if (not nzb_list) and cfg.email_endjob():
            if (cfg.email_endjob() == 1) or (cfg.email_endjob() == 2 and (unpack_error or par_error or script_error)):
                emailer.endjob(dirname, cat, all_ok, workdir_complete, nzo.bytes_downloaded,
                               nzo.fail_msg, nzo.unpack_info, script, TRANS(script_log), script_ret)

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

        # Cleanup again, including NZB files
        if all_ok:
            cleanup_list(workdir_complete, False)

        # Force error for empty result
        all_ok = all_ok and not empty

        # Update indexer with results
        if cfg.rating_enable():
            if nzo.encrypted > 0:
                Rating.do.update_auto_flag(nzo.nzo_id, Rating.FLAG_ENCRYPTED)
            if empty:
                hosts = map(lambda s: s.host, sabnzbd.downloader.Downloader.do.nzo_servers(nzo))
                if not hosts:
                    hosts = [None]
                for host in hosts:
                    Rating.do.update_auto_flag(nzo.nzo_id, Rating.FLAG_EXPIRED, host)

        # Show final status in history
        if all_ok:
            growler.send_notification(T('Download Completed'), filename, 'complete')
            nzo.status = Status.COMPLETED
        else:
            growler.send_notification(T('Download Failed'), filename, 'failed')
            nzo.status = Status.FAILED

    except:
        logging.error(T('Post Processing Failed for %s (%s)'), filename, crash_msg)
        if not crash_msg:
            logging.info("Traceback: ", exc_info=True)
            crash_msg = T('see logfile')
        nzo.fail_msg = T('PostProcessing was aborted (%s)') % unicoder(crash_msg)
        growler.send_notification(T('Download Failed'), filename, 'failed')
        nzo.status = Status.FAILED
        par_error = True
        all_ok = False
        if cfg.email_endjob():
            emailer.endjob(dirname, cat, all_ok, clip_path(workdir_complete), nzo.bytes_downloaded,
                           nzo.fail_msg, nzo.unpack_info, '', '', 0)

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
    history_db.add_history_db(nzo, clip_path(workdir_complete), nzo.downpath, postproc_time, script_log, script_line)
    # The connection is only used once, so close it here
    history_db.close()

    # Clean up the NZO
    try:
        logging.info('Cleaning up %s (keep_basic=%s)', filename, str(not all_ok))
        sabnzbd.nzbqueue.NzbQueue.do.cleanup_nzo(nzo, keep_basic=not all_ok)
    except:
        logging.error(T('Cleanup of %s failed.'), nzo.final_name)
        logging.info("Traceback: ", exc_info=True)

    # Remove download folder
    if all_ok:
        try:
            if os.path.exists(workdir):
                logging.debug('Removing workdir %s', workdir)
                remove_all(workdir, recursive=True)
        except:
            logging.error(T('Error removing workdir (%s)'), clip_path(workdir))
            logging.info("Traceback: ", exc_info=True)

    # Use automatic retry link on par2 errors and encrypted/bad RARs
    if par_error or unpack_error in (2, 3):
        try_alt_nzb(nzo)

    return True


def parring(nzo, workdir):
    """ Perform par processing. Returns: (par_error, re_add) """
    assert isinstance(nzo, sabnzbd.nzbstuff.NzbObject)
    filename = nzo.final_name
    growler.send_notification(T('Post-processing'), nzo.final_name, 'pp')
    logging.info('Par2 check starting on %s', filename)

    # Get verification status of sets
    verified = sabnzbd.load_data(VERIFIED_FILE, nzo.workpath, remove=False) or {}

    # Collect the par files
    if nzo.partable:
        par_table = nzo.partable.copy()
    else:
        par_table = {}
    repair_sets = par_table.keys()

    re_add = False
    par_error = False
    single = len(repair_sets) == 1

    if repair_sets:
        for setname in repair_sets:
            if cfg.ignore_samples() > 0 and 'sample' in setname.lower():
                continue
            if not verified.get(setname, False):
                logging.info("Running repair on set %s", setname)
                parfile_nzf = par_table[setname]
                if os.path.exists(os.path.join(nzo.downpath, parfile_nzf.filename)) or parfile_nzf.extrapars:
                    need_re_add, res = par2_repair(parfile_nzf, nzo, workdir, setname, single=single)
                    re_add = re_add or need_re_add
                    if not res and not need_re_add and cfg.sfv_check():
                        res = try_sfv_check(nzo, workdir, setname)
                    verified[setname] = res
                else:
                    continue
                par_error = par_error or not res
    else:
        logging.info("No par2 sets for %s", filename)
        nzo.set_unpack_info('Repair', T('[%s] No par2 sets') % unicoder(filename))
        if cfg.sfv_check() and not verified.get('', False):
            par_error = not try_sfv_check(nzo, workdir, '')
            verified[''] = not par_error

    if re_add:
        logging.info('Readded %s to queue', filename)
        if nzo.priority != TOP_PRIORITY:
            nzo.priority = REPAIR_PRIORITY
        sabnzbd.nzbqueue.add_nzo(nzo)
        sabnzbd.downloader.Downloader.do.resume_from_postproc()

    sabnzbd.save_data(verified, VERIFIED_FILE, nzo.workpath)

    logging.info('Par2 check finished on %s', filename)
    return par_error, re_add


def try_sfv_check(nzo, workdir, setname):
    """ Attempt to verify set using SFV file
        Return True if verified, False when failed
        When setname is '', all SFV files will be used, otherwise only the matching one
        When setname is '' and no SFV files are found, True is returned
    """
    # Get list of SFV names; shortest name first, minimizes the chance on a mismatch
    sfvs = globber_full(workdir, '*.sfv')
    sfvs.sort(lambda x, y: len(x) - len(y))
    par_error = False
    found = False
    for sfv in sfvs:
        if setname.lower() in os.path.basename(sfv).lower():
            found = True
            nzo.set_unpack_info('Repair', T('Trying SFV verification'))
            failed = sfv_check(sfv)
            if failed:
                msg = T('Some files failed to verify against "%s"') % unicoder(os.path.basename(sfv))
                msg += '; '
                msg += '; '.join(failed)
                nzo.set_unpack_info('Repair', msg)
                par_error = True
            else:
                nzo.set_unpack_info('Repair', T('Verified successfully using SFV files'))
            if setname:
                break
    return (found or not setname) and not par_error


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
        logging.info("Queue has finished, launching: %s (%s)",
                     sabnzbd.QUEUECOMPLETEACTION, sabnzbd.QUEUECOMPLETEARG)
        if sabnzbd.QUEUECOMPLETEARG:
            sabnzbd.QUEUECOMPLETEACTION(sabnzbd.QUEUECOMPLETEARG)
        else:
            Thread(target=sabnzbd.QUEUECOMPLETEACTION).start()

        sabnzbd.change_queue_complete_action(cfg.queue_complete(), new=False)


def cleanup_list(wdir, skip_nzb):
    """ Remove all files whose extension matches the cleanup list,
        optionally ignoring the nzb extension
    """
    if cfg.cleanup_list():
        try:
            files = os.listdir(wdir)
        except:
            files = ()
        for filename in files:
            path = os.path.join(wdir, filename)
            if os.path.isdir(path):
                cleanup_list(path, skip_nzb)
            else:
                if on_cleanup_list(filename, skip_nzb):
                    try:
                        logging.info("Removing unwanted file %s", path)
                        os.remove(path)
                    except:
                        logging.error(T('Removing %s failed'), clip_path(path))
                        logging.info("Traceback: ", exc_info=True)
        if files:
            try:
                remove_dir(wdir)
            except:
                pass


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
    files = []
    for root, _dirs, names in os.walk(wdir):
        for name in names:
            files.append(os.path.join(root, name))

    for file_ in files:
        if os.path.splitext(file_)[1].lower() != '.nzb':
            return None

    # For multiple NZBs, cannot use the current job name
    if len(files) != 1:
        nzbname = None

    # Process all NZB files
    for file_ in files:
        dirscanner.ProcessSingleFile(os.path.split(file_)[1], file_, pp, script, cat,
                                     priority=priority, keep=False, dup_check=False, nzbname=nzbname)
    return files


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
    for root, _dirs, files in os.walk(path):
        for file_ in files:
            if RE_SAMPLE.search(file_):
                path = os.path.join(root, file_)
                try:
                    logging.info("Removing unwanted sample file %s", path)
                    os.remove(path)
                except:
                    logging.error(T('Removing %s failed'), clip_path(path))
                    logging.info("Traceback: ", exc_info=True)


def rename_and_collapse_folder(oldpath, newpath, files):
    """ Rename folder, collapsing when there's just a single subfolder
        oldpath --> newpath OR oldpath/subfolder --> newpath
        Modify list of filenames accordingly
    """
    orgpath = oldpath
    items = globber(oldpath)
    if len(items) == 1:
        folder = items[0]
        folder_path = os.path.join(oldpath, folder)
        if os.path.isdir(folder_path) and folder not in ('VIDEO_TS', 'AUDIO_TS'):
            logging.info('Collapsing %s', os.path.join(newpath, folder))
            oldpath = folder_path

    oldpath = os.path.normpath(oldpath)
    newpath = os.path.normpath(newpath)
    files = [os.path.normpath(f).replace(oldpath, newpath) for f in files]

    renamer(oldpath, newpath)
    try:
        remove_dir(orgpath)
    except:
        pass
    return files


def set_marker(folder):
    """ Set marker file and return name """
    name = cfg.marker_file()
    if name:
        path = os.path.join(folder, name)
        logging.debug('Create marker file %s', path)
        try:
            fp = open(path, 'w')
            fp.close()
        except:
            logging.info('Cannot create marker file %s', path)
            logging.info("Traceback: ", exc_info=True)
            name = None
    return name


def del_marker(path):
    """ Remove marker file """
    if path and os.path.exists(path):
        logging.debug('Removing marker file %s', path)
        try:
            os.remove(path)
        except:
            logging.info('Cannot remove marker file %s', path)
            logging.info("Traceback: ", exc_info=True)


def remove_from_list(name, lst):
    if name:
        for n in xrange(len(lst)):
            if lst[n].endswith(name):
                logging.debug('Popping %s', lst[n])
                lst.pop(n)
                return


def try_alt_nzb(nzo):
    """ Try to get a new NZB if available """
    url = nzo.nzo_info.get('failure')
    if url and cfg.new_nzb_on_failure():
        sabnzbd.add_url(url, nzo.pp, nzo.script, nzo.cat, nzo.priority)
