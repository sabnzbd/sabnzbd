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
sabnzbd.assembler - threaded assembly/decoding of files
"""

import os
import queue
import logging
import re
from threading import Thread
from time import sleep
import hashlib

import sabnzbd
from sabnzbd.misc import get_all_passwords
from sabnzbd.filesystem import set_permissions, clip_path, has_win_device, \
    diskspace, get_filename, get_ext
from sabnzbd.constants import Status, GIGI, MAX_ASSEMBLER_QUEUE
import sabnzbd.cfg as cfg
from sabnzbd.articlecache import ArticleCache
from sabnzbd.postproc import PostProcessor
import sabnzbd.downloader
import sabnzbd.par2file as par2file
import sabnzbd.utils.rarfile as rarfile
from sabnzbd.rating import Rating


class Assembler(Thread):
    do = None  # Link to the instance of this method

    def __init__(self):
        Thread.__init__(self)
        self.queue = queue.Queue()
        Assembler.do = self

    def stop(self):
        self.process(None)

    def process(self, job):
        self.queue.put(job)

    def queue_full(self):
        return self.queue.qsize() >= MAX_ASSEMBLER_QUEUE

    def run(self):
        while 1:
            job = self.queue.get()
            if not job:
                logging.info("Shutting down")
                break

            nzo, nzf, file_done = job

            if nzf:
                # Check if enough disk space is free after each file is done
                # If not enough space left, pause downloader and send email
                if file_done and diskspace(force=True)['download_dir'][1] < (cfg.download_free.get_float() + nzf.bytes) / GIGI:
                    # Only warn and email once
                    if not sabnzbd.downloader.Downloader.do.paused:
                        logging.warning(T('Too little diskspace forcing PAUSE'))
                        # Pause downloader, but don't save, since the disk is almost full!
                        sabnzbd.downloader.Downloader.do.pause()
                        sabnzbd.emailer.diskfull_mail()
                        # Abort all direct unpackers, just to be sure
                        sabnzbd.directunpacker.abort_all()

                # Prepare filepath
                filepath = nzf.prepare_filepath()

                if filepath:
                    logging.debug('Decoding part of %s', filepath)
                    try:
                        self.assemble(nzf, file_done)
                    except IOError as err:
                        # If job was deleted or in active post-processing, ignore error
                        if not nzo.deleted and not nzo.is_gone() and not nzo.pp_active:
                            # 28 == disk full => pause downloader
                            if err.errno == 28:
                                logging.error(T('Disk full! Forcing Pause'))
                            else:
                                logging.error(T('Disk error on creating file %s'), clip_path(filepath))
                            # Log traceback
                            logging.info('Traceback: ', exc_info=True)
                            # Pause without saving
                            sabnzbd.downloader.Downloader.do.pause()
                        continue
                    except:
                        logging.error(T('Fatal error in Assembler'), exc_info=True)
                        break

                    # Continue after partly written data
                    if not file_done:
                        continue

                    # Clean-up admin data
                    logging.info('Decoding finished %s', filepath)
                    nzf.remove_admin()

                    # Do rar-related processing
                    if rarfile.is_rarfile(filepath):
                        # Encryption and unwanted extension detection
                        rar_encrypted, unwanted_file = check_encrypted_and_unwanted_files(nzo, filepath)
                        if rar_encrypted:
                            if cfg.pause_on_pwrar() == 1:
                                logging.warning(remove_warning_label(T('WARNING: Paused job "%s" because of encrypted RAR file (if supplied, all passwords were tried)')), nzo.final_name)
                                nzo.pause()
                            else:
                                logging.warning(remove_warning_label(T('WARNING: Aborted job "%s" because of encrypted RAR file (if supplied, all passwords were tried)')), nzo.final_name)
                                nzo.fail_msg = T('Aborted, encryption detected')
                                sabnzbd.nzbqueue.NzbQueue.do.end_job(nzo)

                        if unwanted_file:
                            logging.warning(remove_warning_label(T('WARNING: In "%s" unwanted extension in RAR file. Unwanted file is %s ')), nzo.final_name, unwanted_file)
                            logging.debug(T('Unwanted extension is in rar file %s'), filepath)
                            if cfg.action_on_unwanted_extensions() == 1 and nzo.unwanted_ext == 0:
                                logging.debug('Unwanted extension ... pausing')
                                nzo.unwanted_ext = 1
                                nzo.pause()
                            if cfg.action_on_unwanted_extensions() == 2:
                                logging.debug('Unwanted extension ... aborting')
                                nzo.fail_msg = T('Aborted, unwanted extension detected')
                                sabnzbd.nzbqueue.NzbQueue.do.end_job(nzo)

                        # Add to direct unpack
                        nzo.add_to_direct_unpacker(nzf)

                    elif par2file.is_parfile(filepath):
                        # Parse par2 files, cloaked or not
                        nzo.handle_par2(nzf, filepath)

                    filter, reason = nzo_filtered_by_rating(nzo)
                    if filter == 1:
                        logging.warning(remove_warning_label(T('WARNING: Paused job "%s" because of rating (%s)')), nzo.final_name, reason)
                        nzo.pause()
                    elif filter == 2:
                        logging.warning(remove_warning_label(T('WARNING: Aborted job "%s" because of rating (%s)')), nzo.final_name, reason)
                        nzo.fail_msg = T('Aborted, rating filter matched (%s)') % reason
                        sabnzbd.nzbqueue.NzbQueue.do.end_job(nzo)

            else:
                sabnzbd.nzbqueue.NzbQueue.do.remove(nzo.nzo_id, add_to_history=False, cleanup=False)
                PostProcessor.do.process(nzo)

    def assemble(self, nzf, file_done):
        """ Assemble a NZF from its table of articles
            1) Partial write: write what we have
            2) Nothing written before: write all
        """
        # New hash-object needed?
        if not nzf.md5:
            nzf.md5 = hashlib.md5()

        with open(nzf.filepath, 'ab') as fout:
            for article in nzf.decodetable:
                # Break if deleted during writing
                if nzf.nzo.status is Status.DELETED:
                    break

                # Skip already written articles
                if article.on_disk:
                    continue

                # Write all decoded articles
                if article.decoded:
                    data = ArticleCache.do.load_article(article)
                    # Could be empty in case nzo was deleted
                    if data:
                        fout.write(data)
                        nzf.md5.update(data)
                        article.on_disk = True
                    else:
                        logging.info("No data found when trying to write %s", article)
                else:
                    # If the article was not decoded but the file
                    # is done, it is just a missing piece, so keep writing
                    if file_done:
                        continue
                    else:
                        # We reach an article that was not decoded
                        break

        # Final steps
        if file_done:
            set_permissions(nzf.filepath)
            nzf.md5sum = nzf.md5.digest()


def file_has_articles(nzf):
    """ Do a quick check to see if any articles are present for this file.
        Destructive: only to be used to differentiate between unknown encoding and no articles.
    """
    has = False
    for article in nzf.decodetable:
        sleep(0.01)
        data = ArticleCache.do.load_article(article)
        if data:
            has = True
    return has


RE_SUBS = re.compile(r'\W+sub|subs|subpack|subtitle|subtitles(?![a-z])', re.I)
SAFE_EXTS = ('.mkv', '.mp4', '.avi', '.wmv', '.mpg', '.webm')
def is_cloaked(nzo, path, names):
    """ Return True if this is likely to be a cloaked encrypted post """
    fname = os.path.splitext(get_filename(path.lower()))[0]
    for name in names:
        name = get_filename(name.lower())
        name, ext = os.path.splitext(name)
        if ext == '.rar' and fname.startswith(name) and (len(fname) - len(name)) < 8 and len(names) < 3 and not RE_SUBS.search(fname):
            # Only warn once
            if nzo.encrypted == 0:
                logging.warning(T('Job "%s" is probably encrypted due to RAR with same name inside this RAR'), nzo.final_name)
                nzo.encrypted = 1
            return True
        elif 'password' in name and ext not in SAFE_EXTS:
            # Only warn once
            if nzo.encrypted == 0:
                logging.warning(T('Job "%s" is probably encrypted: "password" in filename "%s"'), nzo.final_name, name)
                nzo.encrypted = 1
            return True
    return False


def check_encrypted_and_unwanted_files(nzo, filepath):
    """ Combines check for unwanted and encrypted files to save on CPU and IO """
    encrypted = False
    unwanted = None

    if (cfg.unwanted_extensions() and cfg.action_on_unwanted_extensions()) or (nzo.encrypted == 0 and cfg.pause_on_pwrar()):
        # These checks should not break the assembler
        try:
            # Rarfile freezes on Windows special names, so don't try those!
            if sabnzbd.WIN32 and has_win_device(filepath):
                return encrypted, unwanted

            # Is it even a rarfile?
            if rarfile.is_rarfile(filepath):
                # Open the rar
                rarfile.UNRAR_TOOL = sabnzbd.newsunpack.RAR_COMMAND
                zf = rarfile.RarFile(filepath, single_file_check=True)

                # Check for encryption
                if nzo.encrypted == 0 and cfg.pause_on_pwrar() and (zf.needs_password() or is_cloaked(nzo, filepath, zf.namelist())):
                    # Load all passwords
                    passwords = get_all_passwords(nzo)

                    # Cloaked job?
                    if is_cloaked(nzo, filepath, zf.namelist()):
                        encrypted = True
                    elif not passwords:
                        # Only error when no password was set
                        nzo.encrypted = 1
                        encrypted = True
                    else:
                        # Lets test if any of the password work
                        password_hit = False

                        for password in passwords:
                            if password:
                                logging.info('Trying password "%s" on job "%s"', password, nzo.final_name)
                                try:
                                    zf.setpassword(password)
                                except rarfile.Error:
                                    # On weird passwords the setpassword() will fail
                                    # but the actual rartest() will work
                                    pass
                                try:
                                    zf.testrar()
                                    password_hit = password
                                    break
                                except rarfile.RarCRCError:
                                    # On CRC error we can continue!
                                    password_hit = password
                                    break
                                except Exception as e:
                                    # Did we start from the right volume?
                                    if 'need to start extraction from a previous volume' in str(e):
                                        return encrypted, unwanted
                                    # This one failed
                                    pass

                        # Did any work?
                        if password_hit:
                            # We always trust the user's input
                            if not nzo.password:
                                nzo.password = password_hit
                            # Don't check other files
                            logging.info('Password "%s" matches for job "%s"', password_hit, nzo.final_name)
                            nzo.encrypted = -1
                            encrypted = False
                        else:
                            # Encrypted and none of them worked
                            nzo.encrypted = 1
                            encrypted = True

                # Check for unwanted extensions
                if cfg.unwanted_extensions() and cfg.action_on_unwanted_extensions():
                    for somefile in zf.namelist():
                        logging.debug('File contains: %s', somefile)
                        if get_ext(somefile).replace('.', '').lower() in cfg.unwanted_extensions():
                            logging.debug('Unwanted file %s', somefile)
                            unwanted = somefile
                zf.close()
                del zf
        except:
            logging.info('Error during inspection of RAR-file %s', filepath)
            logging.debug('Traceback: ', exc_info=True)

    return encrypted, unwanted


def nzo_filtered_by_rating(nzo):
    if Rating.do and cfg.rating_enable() and cfg.rating_filter_enable() and (nzo.rating_filtered < 2):
        rating = Rating.do.get_rating_by_nzo(nzo.nzo_id)
        if rating is not None:
            nzo.rating_filtered = 1
            reason = rating_filtered(rating, nzo.filename.lower(), True)
            if reason is not None:
                return 2, reason
            reason = rating_filtered(rating, nzo.filename.lower(), False)
            if reason is not None:
                return 1, reason
    return 0, ""


def rating_filtered(rating, filename, abort):
    def check_keyword(keyword):
        clean_keyword = keyword.strip().lower()
        return (len(clean_keyword) > 0) and (clean_keyword in filename)
    audio = cfg.rating_filter_abort_audio() if abort else cfg.rating_filter_pause_audio()
    video = cfg.rating_filter_abort_video() if abort else cfg.rating_filter_pause_video()
    spam = cfg.rating_filter_abort_spam() if abort else cfg.rating_filter_pause_spam()
    spam_confirm = cfg.rating_filter_abort_spam_confirm() if abort else cfg.rating_filter_pause_spam_confirm()
    encrypted = cfg.rating_filter_abort_encrypted() if abort else cfg.rating_filter_pause_encrypted()
    encrypted_confirm = cfg.rating_filter_abort_encrypted_confirm() if abort else cfg.rating_filter_pause_encrypted_confirm()
    downvoted = cfg.rating_filter_abort_downvoted() if abort else cfg.rating_filter_pause_downvoted()
    keywords = cfg.rating_filter_abort_keywords() if abort else cfg.rating_filter_pause_keywords()
    if (video > 0) and (rating.avg_video > 0) and (rating.avg_video <= video):
        return T('video')
    if (audio > 0) and (rating.avg_audio > 0) and (rating.avg_audio <= audio):
        return T('audio')
    if (spam and ((rating.avg_spam_cnt > 0) or rating.avg_encrypted_confirm)) or (spam_confirm and rating.avg_spam_confirm):
        return T('spam')
    if (encrypted and ((rating.avg_encrypted_cnt > 0) or rating.avg_encrypted_confirm)) or (encrypted_confirm and rating.avg_encrypted_confirm):
        return T('passworded')
    if downvoted and (rating.avg_vote_up < rating.avg_vote_down):
        return T('downvoted')
    if any(check_keyword(k) for k in keywords.split(',')):
        return T('keywords')
    return None


def remove_warning_label(msg):
    """ Standardize errors by removing obsolete
        "WARNING:" part in all languages """
    if ':' in msg:
        return msg.split(':')[1].strip()
    return msg
