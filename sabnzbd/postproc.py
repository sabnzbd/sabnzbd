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
sabnzbd.postproc - threaded post-processing of jobs
"""

import os
import logging
import sabnzbd
import functools
import time
import re
import queue

from sabnzbd.newsunpack import (
    unpack_magic,
    par2_repair,
    external_processing,
    sfv_check,
    build_filelists,
    rar_sort,
    is_sfv_file,
)
from threading import Thread
from sabnzbd.misc import on_cleanup_list
from sabnzbd.filesystem import (
    real_path,
    get_unique_path,
    move_to_path,
    make_script_path,
    long_path,
    clip_path,
    renamer,
    remove_dir,
    globber,
    globber_full,
    set_permissions,
    cleanup_empty_directories,
    fix_unix_encoding,
    sanitize_and_trim_path,
    sanitize_files_in_folder,
    remove_file,
    recursive_listdir,
    setname_from_path,
    create_all_dirs,
    get_unique_filename,
)
from sabnzbd.sorting import Sorter
from sabnzbd.constants import (
    REPAIR_PRIORITY,
    TOP_PRIORITY,
    POSTPROC_QUEUE_FILE_NAME,
    POSTPROC_QUEUE_VERSION,
    sample_match,
    JOB_ADMIN,
    Status,
    VERIFIED_FILE,
)
from sabnzbd.rating import Rating
import sabnzbd.emailer as emailer
import sabnzbd.dirscanner as dirscanner
import sabnzbd.downloader
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.encoding as encoding
import sabnzbd.nzbqueue
import sabnzbd.database as database
import sabnzbd.notifier as notifier
import sabnzbd.utils.rarfile as rarfile
import sabnzbd.utils.rarvolinfo as rarvolinfo
import sabnzbd.utils.checkdir

MAX_FAST_JOB_COUNT = 3

# Match samples
RE_SAMPLE = re.compile(sample_match, re.I)


class PostProcessor(Thread):
    """ PostProcessor thread, designed as Singleton """

    do = None  # Link to instance of the thread

    def __init__(self):
        """ Initialize PostProcessor thread """
        Thread.__init__(self)

        # This history queue is simply used to log what active items to display in the web_ui
        self.load()

        if self.history_queue is None:
            self.history_queue = []

        # Fast-queue for jobs already finished by DirectUnpack
        self.fast_queue = queue.Queue()

        # Regular queue for jobs that might need more attention
        self.slow_queue = queue.Queue()

        # Load all old jobs
        for nzo in self.history_queue:
            self.process(nzo)

        # Counter to not only process fast-jobs
        self.__fast_job_count = 0

        # State variables
        self.__stop = False
        self.__busy = False
        self.paused = False
        PostProcessor.do = self

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
                logging.warning(T("Old queue detected, use Status->Repair to convert the queue"))
            elif isinstance(history_queue, list):
                self.history_queue = [nzo for nzo in history_queue if os.path.exists(nzo.downpath)]
        except:
            logging.info("Corrupt %s file, discarding", POSTPROC_QUEUE_FILE_NAME)
            logging.info("Traceback: ", exc_info=True)

    def delete(self, nzo_id, del_files=False):
        """ Remove a job from the post processor queue """
        for nzo in self.history_queue:
            if nzo.nzo_id == nzo_id:
                if nzo.status in (Status.FAILED, Status.COMPLETED):
                    nzo.to_be_removed = True
                elif nzo.status in (Status.DOWNLOADING, Status.QUEUED):
                    self.remove(nzo)
                    nzo.purge_data(delete_all_data=del_files)
                    logging.info("Removed job %s from postproc queue", nzo.final_name)
                    nzo.work_name = ""  # Mark as deleted job
                break

    def process(self, nzo):
        """ Push on finished job in the queue """
        if nzo not in self.history_queue:
            self.history_queue.append(nzo)

        # Fast-track if it has DirectUnpacked jobs or if it's still going
        if nzo.direct_unpacker and (nzo.direct_unpacker.success_sets or not nzo.direct_unpacker.killed):
            self.fast_queue.put(nzo)
        else:
            self.slow_queue.put(nzo)
        self.save()
        sabnzbd.history_updated()

    def remove(self, nzo):
        """ Remove given nzo from the queue """
        try:
            self.history_queue.remove(nzo)
        except:
            pass
        self.save()
        sabnzbd.history_updated()

    def stop(self):
        """ Stop thread after finishing running job """
        self.__stop = True
        self.slow_queue.put(None)
        self.fast_queue.put(None)

    def cancel_pp(self, nzo_id):
        """ Change the status, so that the PP is canceled """
        for nzo in self.history_queue:
            if nzo.nzo_id == nzo_id:
                nzo.abort_direct_unpacker()
                if nzo.pp_active:
                    nzo.pp_active = False
                return True
        return None

    def empty(self):
        """ Return True if pp queue is empty """
        return self.slow_queue.empty() and self.fast_queue.empty() and not self.__busy

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
        """ Postprocessor loop """
        # First we do a dircheck
        complete_dir = sabnzbd.cfg.complete_dir.get_path()
        if sabnzbd.utils.checkdir.isFAT(complete_dir):
            logging.warning(
                T("Completed Download Folder %s is on FAT file system, limiting maximum file size to 4GB")
                % complete_dir
            )
        else:
            logging.info("Completed Download Folder %s is not on FAT", complete_dir)

        # Start looping
        check_eoq = False
        while not self.__stop:
            self.__busy = False

            if self.paused:
                time.sleep(5)
                continue

            # Something in the fast queue?
            try:
                # Every few fast-jobs we should check allow a
                # slow job so that they don't wait forever
                if self.__fast_job_count >= MAX_FAST_JOB_COUNT and self.slow_queue.qsize():
                    raise queue.Empty

                nzo = self.fast_queue.get(timeout=2)
                self.__fast_job_count += 1
            except queue.Empty:
                # Try the slow queue
                try:
                    nzo = self.slow_queue.get(timeout=2)
                    # Reset fast-counter
                    self.__fast_job_count = 0
                except queue.Empty:
                    # Check for empty queue
                    if check_eoq:
                        check_eoq = False
                        handle_empty_queue()
                    # No fast or slow jobs, better luck next loop!
                    continue

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

            if nzo.to_be_removed:
                history_db = database.HistoryDB()
                history_db.remove_history(nzo.nzo_id)
                history_db.close()
                nzo.purge_data()

            # Processing done
            nzo.pp_active = False

            self.remove(nzo)
            check_eoq = True

            # Allow download to proceed
            sabnzbd.downloader.Downloader.do.resume_from_postproc()


def process_job(nzo):
    """ Process one job """
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
    workdir_complete = ""
    script_log = ""
    script_line = ""

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
                _enough, ratio = nzo.check_availability_ratio()
                req_ratio = float(cfg.req_completion_rate()) / 100.0
                # Make sure that rounded ratio doesn't equal required ratio
                # when it is actually below required
                if (ratio < req_ratio) and (req_ratio - ratio) < 0.001:
                    ratio = req_ratio - 0.001
                emsg = "%.1f%%" % (ratio * 100.0)
                emsg2 = "%.1f%%" % float(cfg.req_completion_rate())
                emsg = T("Download might fail, only %s of required %s available") % (emsg, emsg2)
            else:
                emsg = T("Download failed - Not on your server(s)")
                empty = True
            emsg += " - https://sabnzbd.org/not-complete"
            nzo.fail_msg = emsg
            nzo.set_unpack_info("Fail", emsg)
            nzo.status = Status.FAILED
            # do not run unpacking or parity verification
            flag_repair = flag_unpack = False
            all_ok = cfg.empty_postproc() and empty
            if not all_ok:
                par_error = True
                unpack_error = 1

        script = nzo.script
        logging.info(
            "Starting Post-Processing on %s => Repair:%s, Unpack:%s, Delete:%s, Script:%s, Cat:%s",
            filename,
            flag_repair,
            flag_unpack,
            flag_delete,
            script,
            nzo.cat,
        )

        # Set complete dir to workdir in case we need to abort
        workdir_complete = workdir

        # Par processing, if enabled
        if all_ok and flag_repair:
            par_error, re_add = parring(nzo, workdir)
            if re_add:
                # Try to get more par files
                return False

        # If we don't need extra par2, we can disconnect
        if sabnzbd.nzbqueue.NzbQueue.do.actives(grabs=False) == 0 and cfg.autodisconnect():
            # This was the last job, close server connections
            sabnzbd.downloader.Downloader.do.disconnect()

        # Sanitize the resulting files
        if sabnzbd.WIN32:
            sanitize_files_in_folder(workdir)

        # Check if user allows unsafe post-processing
        if flag_repair and cfg.safe_postproc():
            all_ok = all_ok and not par_error

        if all_ok:
            # Fix encodings
            fix_unix_encoding(workdir)

            # Use dirs generated by direct-unpacker
            if nzo.direct_unpacker and nzo.direct_unpacker.unpack_dir_info:
                (
                    tmp_workdir_complete,
                    workdir_complete,
                    file_sorter,
                    one_folder,
                    marker_file,
                ) = nzo.direct_unpacker.unpack_dir_info
            else:
                # Generate extraction path
                tmp_workdir_complete, workdir_complete, file_sorter, one_folder, marker_file = prepare_extraction_path(
                    nzo
                )

            newfiles = []
            # Run Stage 2: Unpack
            if flag_unpack:
                # Set the current nzo status to "Extracting...". Used in History
                nzo.status = Status.EXTRACTING
                logging.info("Running unpack_magic on %s", filename)
                unpack_error, newfiles = unpack_magic(
                    nzo, workdir, tmp_workdir_complete, flag_delete, one_folder, (), (), (), (), ()
                )
                logging.info("Unpacked files %s", newfiles)

                if sabnzbd.WIN32:
                    # Sanitize the resulting files
                    newfiles = sanitize_files_in_folder(tmp_workdir_complete)
                logging.info("Finished unpack_magic on %s", filename)

            if cfg.safe_postproc():
                all_ok = all_ok and not unpack_error

            if all_ok:
                # Move any (left-over) files to destination
                nzo.status = Status.MOVING
                nzo.set_action_line(T("Moving"), "...")
                for root, _dirs, files in os.walk(workdir):
                    if not root.endswith(JOB_ADMIN):
                        for file_ in files:
                            path = os.path.join(root, file_)
                            new_path = path.replace(workdir, tmp_workdir_complete)
                            ok, new_path = move_to_path(path, new_path)
                            if new_path:
                                newfiles.append(new_path)
                            if not ok:
                                nzo.set_unpack_info("Unpack", T("Failed moving %s to %s") % (path, new_path))
                                all_ok = False
                                break

            # Set permissions right
            set_permissions(tmp_workdir_complete)

            if all_ok and marker_file:
                del_marker(os.path.join(tmp_workdir_complete, marker_file))
                remove_from_list(marker_file, newfiles)

            if all_ok:
                # Remove files matching the cleanup list
                cleanup_list(tmp_workdir_complete, skip_nzb=True)

                # Check if this is an NZB-only download, if so redirect to queue
                # except when PP was Download-only
                if flag_repair:
                    nzb_list = nzb_redirect(
                        tmp_workdir_complete, nzo.final_name, nzo.pp, script, nzo.cat, priority=nzo.priority
                    )
                else:
                    nzb_list = None
                if nzb_list:
                    nzo.set_unpack_info("Download", T("Sent %s to queue") % nzb_list)
                    cleanup_empty_directories(tmp_workdir_complete)
                else:
                    # Full cleanup including nzb's
                    cleanup_list(tmp_workdir_complete, skip_nzb=False)

        script_output = ""
        script_ret = 0
        if not nzb_list:
            # Give destination its final name
            if cfg.folder_rename() and tmp_workdir_complete and not one_folder:
                if all_ok:
                    try:
                        newfiles = rename_and_collapse_folder(tmp_workdir_complete, workdir_complete, newfiles)
                    except:
                        logging.error(
                            T('Error renaming "%s" to "%s"'),
                            clip_path(tmp_workdir_complete),
                            clip_path(workdir_complete),
                        )
                        logging.info("Traceback: ", exc_info=True)
                        # Better disable sorting because filenames are all off now
                        file_sorter.sort_file = None
                else:
                    workdir_complete = tmp_workdir_complete.replace("_UNPACK_", "_FAILED_")
                    workdir_complete = get_unique_path(workdir_complete, n=0, create_dir=False)

            if empty:
                job_result = -1
            else:
                job_result = int(par_error) + int(bool(unpack_error)) * 2

            if cfg.ignore_samples():
                remove_samples(workdir_complete)

            # TV/Movie/Date Renaming code part 2 - rename and move files to parent folder
            if all_ok and file_sorter.sort_file:
                if newfiles:
                    file_sorter.rename(newfiles, workdir_complete)
                    workdir_complete, ok = file_sorter.move(workdir_complete)
                else:
                    workdir_complete, ok = file_sorter.rename_with_ext(workdir_complete)
                if not ok:
                    nzo.set_unpack_info("Unpack", T("Failed to move files"))
                    all_ok = False

            # Run the user script
            script_path = make_script_path(script)
            if (all_ok or not cfg.safe_postproc()) and (not nzb_list) and script_path:
                # Set the current nzo status to "Ext Script...". Used in History
                nzo.status = Status.RUNNING
                nzo.set_action_line(T("Running script"), script)
                nzo.set_unpack_info("Script", T("Running user script %s") % script, unique=True)
                script_log, script_ret = external_processing(
                    script_path, nzo, clip_path(workdir_complete), nzo.final_name, job_result
                )
                script_line = get_last_line(script_log)
                if script_log:
                    script_output = nzo.nzo_id
                if script_line:
                    nzo.set_unpack_info("Script", script_line, unique=True)
                else:
                    nzo.set_unpack_info("Script", T("Ran %s") % script, unique=True)
            else:
                script = ""
                script_line = ""
                script_ret = 0

        # Maybe bad script result should fail job
        if script_ret and cfg.script_can_fail():
            script_error = True
            all_ok = False
            nzo.fail_msg = T("Script exit code is %s") % script_ret
        else:
            script_error = False

        # Email the results
        if (not nzb_list) and cfg.email_endjob():
            if (cfg.email_endjob() == 1) or (cfg.email_endjob() == 2 and (unpack_error or par_error or script_error)):
                emailer.endjob(
                    nzo.final_name,
                    nzo.cat,
                    all_ok,
                    workdir_complete,
                    nzo.bytes_downloaded,
                    nzo.fail_msg,
                    nzo.unpack_info,
                    script,
                    script_log,
                    script_ret,
                )

        if script_output:
            # Can do this only now, otherwise it would show up in the email
            if script_ret:
                script_ret = "Exit(%s) " % script_ret
            else:
                script_ret = ""
            if len(script_log.rstrip().split("\n")) > 1:
                nzo.set_unpack_info(
                    "Script",
                    '%s%s <a href="./scriptlog?name=%s">(%s)</a>'
                    % (script_ret, script_line, encoding.xml_name(script_output), T("More")),
                    unique=True,
                )
            else:
                # No '(more)' button needed
                nzo.set_unpack_info("Script", "%s%s " % (script_ret, script_line), unique=True)

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
                hosts = [s.host for s in sabnzbd.downloader.Downloader.do.nzo_servers(nzo)]
                if not hosts:
                    hosts = [None]
                for host in hosts:
                    Rating.do.update_auto_flag(nzo.nzo_id, Rating.FLAG_EXPIRED, host)

    except:
        logging.error(T("Post Processing Failed for %s (%s)"), filename, T("see logfile"))
        logging.info("Traceback: ", exc_info=True)

        nzo.fail_msg = T("PostProcessing was aborted (%s)") % T("see logfile")
        notifier.send_notification(T("Download Failed"), filename, "failed", nzo.cat)
        nzo.status = Status.FAILED
        par_error = True
        all_ok = False

        if cfg.email_endjob():
            emailer.endjob(
                nzo.final_name,
                nzo.cat,
                all_ok,
                clip_path(workdir_complete),
                nzo.bytes_downloaded,
                nzo.fail_msg,
                nzo.unpack_info,
                "",
                "",
                0,
            )

    if all_ok:
        # If the folder only contains one file OR folder, have that as the path
        # Be aware that series/generic/date sorting may move a single file into a folder containing other files
        workdir_complete = one_file_or_folder(workdir_complete)
        workdir_complete = os.path.normpath(workdir_complete)

    # Clean up the NZO data
    try:
        nzo.purge_data(delete_all_data=all_ok)
    except:
        logging.error(T("Cleanup of %s failed."), nzo.final_name)
        logging.info("Traceback: ", exc_info=True)

    # Use automatic retry link on par2 errors and encrypted/bad RARs
    if par_error or unpack_error in (2, 3):
        try_alt_nzb(nzo)

    # Show final status in history
    if all_ok:
        notifier.send_notification(T("Download Completed"), filename, "complete", nzo.cat)
        nzo.status = Status.COMPLETED
    else:
        notifier.send_notification(T("Download Failed"), filename, "failed", nzo.cat)
        nzo.status = Status.FAILED

    # Log the overall time taken for postprocessing
    postproc_time = int(time.time() - start)

    # Create the history DB instance
    history_db = database.HistoryDB()
    # Add the nzo to the database. Only the path, script and time taken is passed
    # Other information is obtained from the nzo
    history_db.add_history_db(nzo, clip_path(workdir_complete), nzo.downpath, postproc_time, script_log, script_line)
    # Purge items
    history_db.auto_history_purge()
    # The connection is only used once, so close it here
    history_db.close()
    sabnzbd.history_updated()
    return True


def prepare_extraction_path(nzo):
    """ Based on the information that we have, generate
        the extraction path and create the directory.
        Separated so it can be called from DirectUnpacker
    """
    one_folder = False
    marker_file = None
    # Determine class directory
    catdir = config.get_categories(nzo.cat).dir()
    if catdir.endswith("*"):
        catdir = catdir.strip("*")
        one_folder = True
    complete_dir = real_path(cfg.complete_dir.get_path(), catdir)
    complete_dir = long_path(complete_dir)

    # TV/Movie/Date Renaming code part 1 - detect and construct paths
    if cfg.enable_meta():
        file_sorter = Sorter(nzo, nzo.cat)
    else:
        file_sorter = Sorter(None, nzo.cat)
    complete_dir = file_sorter.detect(nzo.final_name, complete_dir)
    if file_sorter.sort_file:
        one_folder = False

    complete_dir = sanitize_and_trim_path(complete_dir)

    if one_folder:
        workdir_complete = create_all_dirs(complete_dir, umask=True)
    else:
        workdir_complete = get_unique_path(os.path.join(complete_dir, nzo.final_name), create_dir=True)
        marker_file = set_marker(workdir_complete)

    if not workdir_complete or not os.path.exists(workdir_complete):
        logging.error(T("Cannot create final folder %s") % os.path.join(complete_dir, nzo.final_name))
        raise IOError

    if cfg.folder_rename() and not one_folder:
        prefixed_path = prefix(workdir_complete, "_UNPACK_")
        tmp_workdir_complete = get_unique_path(prefix(workdir_complete, "_UNPACK_"), create_dir=False)

        try:
            renamer(workdir_complete, tmp_workdir_complete)
        except:
            pass  # On failure, just use the original name

        # Is the unique path different? Then we also need to modify the final path
        if prefixed_path != tmp_workdir_complete:
            workdir_complete = workdir_complete + os.path.splitext(tmp_workdir_complete)[1]
    else:
        tmp_workdir_complete = workdir_complete

    return tmp_workdir_complete, workdir_complete, file_sorter, one_folder, marker_file


def parring(nzo, workdir):
    """ Perform par processing. Returns: (par_error, re_add) """
    job_name = nzo.final_name
    notifier.send_notification(T("Post-processing"), job_name, "pp", nzo.cat)
    logging.info("Starting verification and repair of %s", job_name)

    # Get verification status of sets
    verified = sabnzbd.load_data(VERIFIED_FILE, nzo.workpath, remove=False) or {}

    re_add = False
    par_error = False
    single = len(nzo.extrapars) == 1

    if nzo.extrapars:
        # Need to make a copy because it can change during iteration
        for setname in list(nzo.extrapars):
            if cfg.ignore_samples() and RE_SAMPLE.search(setname.lower()):
                continue
            # Skip sets that were already tried
            if not verified.get(setname, False):
                logging.info("Running verification and repair on set %s", setname)
                parfile_nzf = nzo.partable[setname]

                # Check if file maybe wasn't deleted and if we maybe have more files in the parset
                if os.path.exists(os.path.join(nzo.downpath, parfile_nzf.filename)) or nzo.extrapars[setname]:
                    need_re_add, res = par2_repair(parfile_nzf, nzo, workdir, setname, single=single)

                    # Was it aborted?
                    if not nzo.pp_active:
                        re_add = False
                        par_error = True
                        break

                    re_add = re_add or need_re_add
                    verified[setname] = res
                else:
                    continue
                par_error = par_error or not res

    elif not verified.get("", False):
        # No par2-sets found, skipped if already tried before
        logging.info("No par2 sets for %s", job_name)
        nzo.set_unpack_info("Repair", T("[%s] No par2 sets") % job_name)

        # Try SFV-based verification and rename
        sfv_check_result = None
        if cfg.sfv_check() and not verified.get("", False):
            sfv_check_result = try_sfv_check(nzo, workdir)
            par_error = sfv_check_result is False

        # If no luck with SFV, do RAR-check or RAR-rename
        if sfv_check_result is None and cfg.enable_unrar():
            _, _, rars, _, _ = build_filelists(workdir)
            # If there's no RAR's, they might be super-obfuscated
            if not rars:
                # Returns number of renamed RAR's
                if rar_renamer(nzo, workdir):
                    # Re-parse the files so we can do RAR-check
                    _, _, rars, _, _ = build_filelists(workdir)
            if rars:
                par_error = not try_rar_check(nzo, rars)

        # Save that we already tried SFV/RAR-verification
        verified[""] = not par_error

    if re_add:
        logging.info("Re-added %s to queue", job_name)
        if nzo.priority != TOP_PRIORITY:
            nzo.priority = REPAIR_PRIORITY
        nzo.status = Status.FETCHING
        sabnzbd.nzbqueue.NzbQueue.do.add(nzo)
        sabnzbd.downloader.Downloader.do.resume_from_postproc()

    sabnzbd.save_data(verified, VERIFIED_FILE, nzo.workpath)

    logging.info("Verification and repair finished for %s", job_name)
    return par_error, re_add


def try_sfv_check(nzo, workdir):
    """ Attempt to verify set using SFV file
        Return None if no SFV-sets, True/False based on verification
    """
    # Get list of SFV names
    sfvs = globber_full(workdir, "*.sfv")

    # If no files named *.sfv, lets search for obfuscated SFV files
    if not sfvs:
        files = globber_full(workdir, "*")
        for file in files:
            if is_sfv_file(file):
                logging.debug("Found and will use obfuscated SFV file: %s", file)
                sfvs.append(file)
        if not sfvs:
            # still no SFV, so:
            return None

    result = sfv_check(sfvs, nzo, workdir)
    if not result:
        print_sfv = [os.path.basename(sfv) for sfv in sfvs]
        fail_msg = T('Some files failed to verify against "%s"') % "; ".join(print_sfv)
        nzo.set_unpack_info("Repair", fail_msg)
        nzo.status = Status.FAILED
        nzo.fail_msg = fail_msg
        return False

    # Success
    nzo.set_unpack_info("Repair", T("Verified successfully using SFV files"))
    return True


def try_rar_check(nzo, rars):
    """ Attempt to verify set using the RARs
        Return True if verified, False when failed
        When setname is '', all RAR files will be used, otherwise only the matching one
        If no RAR's are found, returns True
    """
    # Sort for better processing
    rars.sort(key=functools.cmp_to_key(rar_sort))

    # Test
    if rars:
        setname = setname_from_path(rars[0])
        nzo.status = Status.VERIFYING
        nzo.set_unpack_info("Repair", T("Trying RAR-based verification"), setname)
        nzo.set_action_line(T("Trying RAR-based verification"), "...")
        try:
            # Set path to unrar and open the file
            # Requires de-unicode for RarFile to work!
            rarfile.UNRAR_TOOL = sabnzbd.newsunpack.RAR_COMMAND
            zf = rarfile.RarFile(rars[0])

            # Skip if it's encrypted
            if zf.needs_password():
                msg = T("[%s] RAR-based verification failed: %s") % (setname, T("Passworded"))
                nzo.set_unpack_info("Repair", msg)
                return True

            # Will throw exception if something is wrong
            zf.testrar()
            # Success!
            msg = T("RAR files verified successfully")
            nzo.set_unpack_info("Repair", msg, setname)
            logging.info(msg)
            return True
        except rarfile.Error as e:
            nzo.fail_msg = T("RAR files failed to verify")
            msg = T("[%s] RAR-based verification failed: %s") % (setname, e)
            nzo.set_unpack_info("Repair", msg, setname)
            logging.info(msg)
            return False
    else:
        # No rar-files, so just continue
        return True


def rar_renamer(nzo, workdir):
    """ Deobfuscate rar file names: Use header and content information to give RAR-files decent names """
    nzo.status = Status.VERIFYING
    nzo.set_unpack_info("Repair", T("Trying RAR-based verification"))
    nzo.set_action_line(T("Trying RAR-based verification"), "...")

    renamed_files = 0

    # This is the most important datastructure (in case of mixed obfuscated rarsets)
    rarvolnr = {}
    # rarvolnr will contain per rar vol number the rarfilenames and their respective contents (and maybe other characteristics, like filesizes).
    # for example: rarvolnr[6]['somerandomfilename.rar']={'readme.txt', 'linux.iso'},
    # which means 'somerandomfilename.rar' has rarvolnumber 6, and contents 'readme.txt' and 'linux.iso'
    # if we find a rarfile with rarvolnumber 7, and 'linux.iso' in it, we have a match!

    # The volume number and real extension of a (obfuscated) rar file
    # so volnrext['dfakjldfalkjdfl.blabla'] = (14, 'part014.rar') or (2, 'r000')
    # Not really needed, but handy to avoid a second lookup at the renaming
    volnrext = {}

    # Scan rar files in workdir, but not subdirs
    workdir_files = os.listdir(workdir)
    for file_to_check in workdir_files:
        file_to_check = os.path.join(workdir, file_to_check)
        # We only want files:
        if not (os.path.isfile(file_to_check)):
            continue
        # The function will check if it's a RAR-file
        # We do a sanity-check for the returned number
        rar_vol, new_extension = rarvolinfo.get_rar_extension(file_to_check)
        if 0 < rar_vol < 1000:
            logging.debug("Detected volume-number %s from RAR-header: %s ", rar_vol, file_to_check)
            volnrext[file_to_check] = (rar_vol, new_extension)
            # The files inside rar file
            rar_contents = rarfile.RarFile(os.path.join(workdir, file_to_check), single_file_check=True).filelist()
            try:
                rarvolnr[rar_vol]
            except:
                # does not yet exist, so create:
                rarvolnr[rar_vol] = {}
            rarvolnr[rar_vol][file_to_check] = rar_contents  # store them for matching (if needed)
        else:
            logging.debug("No RAR-volume-number found in %s", file_to_check)

    logging.debug("Deobfuscate: rarvolnr is: %s", rarvolnr)
    logging.debug("Deobfuscate: volnrext is: %s", volnrext)

    # Could be that there are no rar-files, we stop
    if not len(rarvolnr):
        return renamed_files

    # Check number of different obfuscated rar sets:
    numberofrarsets = len(rarvolnr[1])
    if numberofrarsets == 1:
        # Just one obfuscated rarset
        logging.debug("Deobfuscate: Just one obfuscated rarset")
        for filename in volnrext:
            new_rar_name = "%s.%s" % (nzo.final_name, volnrext[filename][1])
            new_rar_name = os.path.join(workdir, new_rar_name)
            new_rar_name = get_unique_filename(new_rar_name)
            logging.debug("Deobfuscate: Renaming %s to %s" % (filename, new_rar_name))
            renamer(filename, new_rar_name)
            renamed_files += 1
    else:
        # More than one obfuscated rarset, so we must do matching based of files inside the rar files
        logging.debug("Number of obfuscated rarsets: %s", numberofrarsets)

        # Assign (random) rar set names
        rarsetname = {}  # in which rar set it should be, so rar set 'A', or 'B', or ...
        mychar = "A"
        # First things first: Assigning a rarsetname to the rar file which have volume number 1
        for base_obfuscated_filename in rarvolnr[1]:
            rarsetname[base_obfuscated_filename] = mychar + "--" + nzo.final_name
            mychar = chr(ord(mychar) + 1)
        logging.debug("Deobfuscate: rarsetname %s", rarsetname)

        # Do the matching, layer by layer (read: rarvolnumber)
        # So, all rar files with rarvolnr 1, find the contents (files inside the rar),
        # and match with rarfiles with rarvolnr 2, and put them in the correct rarset.
        # And so on, until the highest rarvolnr minus 1 matched against highest rarvolnr
        for n in range(1, len(rarvolnr.keys())):
            logging.debug("Deobfuscate: Finding matches between rar sets %s and %s" % (n, n + 1))
            for base_obfuscated_filename in rarvolnr[n]:
                matchcounter = 0
                for next_obfuscated_filename in rarvolnr[n + 1]:
                    # set() method with intersection (less strict): set(rarvolnr[n][base_obfuscated_filename]).intersection(set(rarvolnr[n+1][next_obfuscated_filename]))
                    # check if the last filename inside the existing rar matches with the first filename in the following rar
                    if rarvolnr[n][base_obfuscated_filename][-1] == rarvolnr[n + 1][next_obfuscated_filename][0]:
                        try:
                            rarsetname[next_obfuscated_filename] = rarsetname[base_obfuscated_filename]
                            matchcounter += 1
                        except KeyError:
                            logging.warning("No matching earlier rar file for %s", next_obfuscated_filename)
                if matchcounter > 1:
                    logging.info("Deobfuscate: more than one match, so risk on false positive matching.")

        # Do the renaming:
        for filename in rarsetname:
            new_rar_name = "%s.%s" % (rarsetname[filename], volnrext[filename][1])
            new_rar_name = os.path.join(workdir, new_rar_name)
            new_rar_name = get_unique_filename(new_rar_name)
            logging.debug("Deobfuscate: Renaming %s to %s" % (filename, new_rar_name))
            renamer(filename, new_rar_name)
            renamed_files += 1

    # Done: The obfuscated rar files have now been renamed to regular formatted filenames
    return renamed_files


def handle_empty_queue():
    """ Check if empty queue calls for action """
    if sabnzbd.nzbqueue.NzbQueue.do.actives() == 0:
        sabnzbd.save_state()
        notifier.send_notification("SABnzbd", T("Queue finished"), "queue_done")

        # Perform end-of-queue action when one is set
        if sabnzbd.QUEUECOMPLETEACTION:
            logging.info(
                "Queue has finished, launching: %s (%s)", sabnzbd.QUEUECOMPLETEACTION, sabnzbd.QUEUECOMPLETEARG
            )
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
                        remove_file(path)
                    except:
                        logging.error(T("Removing %s failed"), clip_path(path))
                        logging.info("Traceback: ", exc_info=True)
        if files:
            # If directories only contained unwanted files, remove them
            cleanup_empty_directories(wdir)


def prefix(path, pre):
    """ Apply prefix to last part of path
        '/my/path' and 'hi_' will give '/my/hi_path'
    """
    p, d = os.path.split(path)
    return os.path.join(p, pre + d)


def nzb_redirect(wdir, nzbname, pp, script, cat, priority):
    """ Check if this job contains only NZB files,
        if so send to queue and remove if on clean-up list
        Returns list of processed NZB's
    """
    files = recursive_listdir(wdir)

    for file_ in files:
        if os.path.splitext(file_)[1].lower() != ".nzb":
            return None

    # For multiple NZBs, cannot use the current job name
    if len(files) != 1:
        nzbname = None

    # Process all NZB files
    for nzb_file in files:
        dirscanner.process_single_nzb(
            os.path.split(nzb_file)[1],
            file_,
            pp,
            script,
            cat,
            priority=priority,
            keep=False,
            dup_check=False,
            nzbname=nzbname,
        )
    return files


def one_file_or_folder(folder):
    """ If the dir only contains one file or folder, join that file/folder onto the path """
    if os.path.exists(folder) and os.path.isdir(folder):
        try:
            cont = os.listdir(folder)
            if len(cont) == 1:
                folder = os.path.join(folder, cont[0])
                folder = one_file_or_folder(folder)
        except WindowsError:
            # Can occur on paths it doesn't like, for example "C:"
            pass
    return folder


TAG_RE = re.compile(r"<[^>]+>")


def get_last_line(txt):
    """ Return last non-empty line of a text, trim to 150 max """
    # First we remove HTML code in a basic way
    txt = TAG_RE.sub(" ", txt)

    # Then we get the last line
    lines = txt.split("\n")
    n = len(lines) - 1
    while n >= 0 and not lines[n].strip("\r\t "):
        n = n - 1

    line = lines[n].strip("\r\t ")
    if len(line) >= 150:
        line = line[:147] + "..."
    return line


def remove_samples(path):
    """ Remove all files that match the sample pattern
        Skip deleting if it matches all files or there is only 1 file
    """
    files_to_delete = []
    nr_files = 0
    for root, _dirs, files in os.walk(path):
        for file_to_match in files:
            nr_files += 1
            if RE_SAMPLE.search(file_to_match):
                files_to_delete.append(os.path.join(root, file_to_match))

    # Make sure we skip false-positives
    if len(files_to_delete) < nr_files:
        for path in files_to_delete:
            try:
                logging.info("Removing unwanted sample file %s", path)
                remove_file(path)
            except:
                logging.error(T("Removing %s failed"), clip_path(path))
                logging.info("Traceback: ", exc_info=True)
    else:
        logging.info("Skipping sample-removal, false-positive")


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
        if os.path.isdir(folder_path) and folder not in ("VIDEO_TS", "AUDIO_TS"):
            logging.info("Collapsing %s", os.path.join(newpath, folder))
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
        logging.debug("Create marker file %s", path)
        try:
            fp = open(path, "w")
            fp.close()
        except:
            logging.info("Cannot create marker file %s", path)
            logging.info("Traceback: ", exc_info=True)
            name = None
    return name


def del_marker(path):
    """ Remove marker file """
    if path and os.path.exists(path):
        logging.debug("Removing marker file %s", path)
        try:
            remove_file(path)
        except:
            logging.info("Cannot remove marker file %s", path)
            logging.info("Traceback: ", exc_info=True)


def remove_from_list(name, lst):
    if name:
        for n in range(len(lst)):
            if lst[n].endswith(name):
                logging.debug("Popping %s", lst[n])
                lst.pop(n)
                return


def try_alt_nzb(nzo):
    """ Try to get a new NZB if available """
    url = nzo.nzo_info.get("failure")
    if url and cfg.new_nzb_on_failure():
        sabnzbd.add_url(url, nzo.pp, nzo.script, nzo.cat, nzo.priority)
