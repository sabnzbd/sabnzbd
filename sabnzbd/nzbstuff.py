#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.nzbstuff - misc
"""
import os
import time
import re
import logging
import datetime
import threading
import functools
import difflib
from typing import List, Dict, Any, Tuple, Optional

# SABnzbd modules
import sabnzbd
from sabnzbd.constants import (
    GIGI,
    ATTRIB_FILE,
    JOB_ADMIN,
    REPAIR_PRIORITY,
    FORCE_PRIORITY,
    HIGH_PRIORITY,
    NORMAL_PRIORITY,
    LOW_PRIORITY,
    DEFAULT_PRIORITY,
    PAUSED_PRIORITY,
    DUP_PRIORITY,
    STOP_PRIORITY,
    RENAMES_FILE,
    MAX_BAD_ARTICLES,
    Status,
    PNFO,
)
from sabnzbd.misc import (
    to_units,
    cat_to_opts,
    cat_convert,
    int_conv,
    format_time_string,
    calc_age,
    cmp,
    caller_name,
    opts_to_pp,
    pp_to_opts,
)
from sabnzbd.filesystem import (
    sanitize_foldername,
    get_unique_path,
    get_admin_path,
    remove_all,
    sanitize_filename,
    set_permissions,
    long_path,
    fix_unix_encoding,
    get_ext,
    get_filename,
    get_unique_filename,
    renamer,
    remove_file,
    get_filepath,
    make_script_path,
    globber,
    is_valid_script,
)
from sabnzbd.decorators import synchronized
import sabnzbd.config as config
import sabnzbd.cfg as cfg
import sabnzbd.nzbparser
from sabnzbd.downloader import Server
from sabnzbd.database import HistoryDB
from sabnzbd.deobfuscate_filenames import is_probably_obfuscated

# Name patterns
RE_SUBJECT_FILENAME_QUOTES = re.compile(r'"([^"]*)"')  # In the subject, we expect the filename within double quotes
RE_SUBJECT_BASIC_FILENAME = re.compile(r"([\w\-+()'\s.,]*\.\w{2,4})")  # Otherwise something that looks like a filename
RE_RAR = re.compile(r"(\.rar|\.r\d\d|\.s\d\d|\.t\d\d|\.u\d\d|\.v\d\d)$", re.I)
RE_PROPER = re.compile(r"(^|[\. _-])(PROPER|REAL|REPACK)([\. _-]|$)")


##############################################################################
# Trylist
##############################################################################

TRYLIST_LOCK = threading.Lock()


class TryList:
    """TryList keeps track of which servers have been tried for a specific article"""

    # Pre-define attributes to save memory
    __slots__ = ("try_list", "fetcher_priority")

    def __init__(self):
        self.try_list: List[Server] = []
        self.fetcher_priority: int = 0

    def server_in_try_list(self, server: Server):
        """ Return whether specified server has been tried """
        with TRYLIST_LOCK:
            return server in self.try_list

    def add_to_try_list(self, server: Server):
        """ Register server as having been tried already """
        with TRYLIST_LOCK:
            if server not in self.try_list:
                self.try_list.append(server)

    def reset_try_list(self):
        """ Clean the list """
        with TRYLIST_LOCK:
            self.try_list = []

    def __getstate__(self):
        """ Save the servers """
        return [server.id for server in self.try_list]

    def __setstate__(self, servers_ids: List[str]):
        self.try_list = []
        for server_id in servers_ids:
            if server_id in sabnzbd.Downloader.server_dict:
                self.add_to_try_list(sabnzbd.Downloader.server_dict[server_id])


##############################################################################
# Article
##############################################################################
ArticleSaver = ("article", "art_id", "bytes", "lowest_partnum", "decoded", "on_disk", "nzf")


class Article(TryList):
    """ Representation of one article """

    # Pre-define attributes to save memory
    __slots__ = ArticleSaver + ("fetcher", "fetcher_priority", "tries")

    def __init__(self, article, article_bytes, nzf):
        super().__init__()
        self.fetcher: Optional[Server] = None
        self.article: str = article
        self.art_id = None
        self.bytes = article_bytes
        self.lowest_partnum = False
        self.tries = 0  # Try count
        self.decoded = False
        self.on_disk = False
        self.nzf: NzbFile = nzf

    def get_article(self, server: Server, servers: List[Server]):
        """ Return article when appropriate for specified server """
        log = sabnzbd.LOG_ALL
        if not self.fetcher and not self.server_in_try_list(server):
            if log:
                logging.debug("Article %s | Server: %s | in second if", self.article, server.host)
            # Is the current selected server of the same priority as this article?
            if log:
                logging.debug(
                    "Article %s | Server: %s | Article priority: %s", self.article, server.host, self.fetcher_priority
                )
            if log:
                logging.debug(
                    "Article %s | Server: %s | Server priority: %s", self.article, server.host, server.priority
                )
            if server.priority == self.fetcher_priority:
                if log:
                    logging.debug("Article %s | Server: %s | same priority, use it", self.article, server.host)
                self.fetcher = server
                self.tries += 1
                if log:
                    logging.debug("Article %s | Server: %s | Article-try: %s", self.article, server.host, self.tries)
                return self
            else:
                if log:
                    logging.debug("Article %s | Server: %s | not the same priority", self.article, server.host)
                # No, so is it a lower priority?
                if server.priority > self.fetcher_priority:
                    if log:
                        logging.debug("Article %s | Server: %s | lower priority", self.article, server.host)
                    # Is there an available server that is a higher priority?
                    found_priority = 1000
                    # for server_check in config.get_servers():
                    for server_check in servers:
                        if log:
                            logging.debug("Article %s | Server: %s | checking", self.article, server.host)
                        if server_check.active and (server_check.priority < found_priority):
                            if server_check.priority < server.priority:
                                if not self.server_in_try_list(server_check):
                                    if log:
                                        logging.debug(
                                            "Article %s | Server: %s | setting found priority to %s",
                                            self.article,
                                            server.host,
                                            server_check.priority,
                                        )
                                    found_priority = server_check.priority
                    if found_priority == 1000:
                        # If no higher priority servers, use this server
                        self.fetcher_priority = server.priority
                        self.fetcher = server
                        self.tries += 1
                        if log:
                            logging.debug(
                                "Article %s | Server: %s | Article-try: %s", self.article, server.host, self.tries
                            )
                        return self
                    else:
                        # There is a higher priority server, so set article priority
                        if log:
                            logging.debug("Article %s | Server: %s | setting self priority", self.article, server.host)
                        self.fetcher_priority = found_priority
        if log:
            logging.debug("Article %s | Server: %s | Returning None", self.article, server.host)
        return None

    def get_art_id(self):
        """ Return unique article storage name, create if needed """
        if not self.art_id:
            self.art_id = sabnzbd.get_new_id("article", self.nzf.nzo.admin_path)
        return self.art_id

    def search_new_server(self):
        """Search for a new server for this article"""
        # Since we need a new server, this one can be listed as failed
        sabnzbd.BPSMeter.register_server_article_failed(self.fetcher.id)
        self.add_to_try_list(self.fetcher)
        for server in sabnzbd.Downloader.servers:
            if server.active and not self.server_in_try_list(server):
                if server.priority >= self.fetcher.priority:
                    self.tries = 0
                    # Allow all servers for this nzo and nzf again (but not for this article)
                    sabnzbd.NzbQueue.reset_try_lists(self, article_reset=False)
                    return True

        logging.info(T("%s => missing from all servers, discarding") % self)
        self.nzf.nzo.increase_bad_articles_counter("missing_articles")
        return False

    def __getstate__(self):
        """ Save to pickle file, selecting attributes """
        dict_ = {}
        for item in ArticleSaver:
            dict_[item] = getattr(self, item)
        dict_["try_list"] = super().__getstate__()
        return dict_

    def __setstate__(self, dict_):
        """ Load from pickle file, selecting attributes """
        for item in ArticleSaver:
            try:
                setattr(self, item, dict_[item])
            except KeyError:
                # Handle new attributes
                setattr(self, item, None)
        super().__setstate__(dict_.get("try_list", []))
        self.fetcher_priority = 0
        self.fetcher = None
        self.tries = 0

    def __eq__(self, other):
        """ Articles with the same usenet address are the same """
        return self.article == other.article

    def __hash__(self):
        """Required because we implement eq. Articles with the same
        usenet address can appear in different NZF's. So we make every
        article object unique, even though it is bad pratice.
        """
        return id(self)

    def __repr__(self):
        return "<Article: article=%s, bytes=%s, art_id=%s>" % (self.article, self.bytes, self.art_id)


##############################################################################
# NzbFile
##############################################################################
NzbFileSaver = (
    "date",
    "subject",
    "filename",
    "filename_checked",
    "filepath",
    "type",
    "is_par2",
    "vol",
    "blocks",
    "setname",
    "articles",
    "decodetable",
    "bytes",
    "bytes_left",
    "nzo",
    "nzf_id",
    "deleted",
    "valid",
    "import_finished",
    "md5sum",
    "md5of16k",
)


class NzbFile(TryList):
    """ Representation of one file consisting of multiple articles """

    # Pre-define attributes to save memory
    __slots__ = NzbFileSaver + ("md5",)

    def __init__(self, date, subject, raw_article_db, file_bytes, nzo):
        """ Setup object """
        super().__init__()

        self.date: datetime.datetime = date
        self.subject: str = subject
        self.type: Optional[str] = None
        self.filename: str = sanitize_filename(name_extractor(subject))
        self.filename_checked = False
        self.filepath: Optional[str] = None

        # Identifiers for par2 files
        self.is_par2: bool = False
        self.vol: Optional[int] = None
        self.blocks: Optional[int] = None
        self.setname: Optional[str] = None

        # Articles are removed from "articles" after being fetched
        self.articles: List[Article] = []
        self.decodetable: List[Article] = []

        self.bytes: int = file_bytes
        self.bytes_left: int = file_bytes

        self.nzo: NzbObject = nzo
        self.nzf_id: str = sabnzbd.get_new_id("nzf", nzo.admin_path)
        self.deleted = False
        self.valid = False
        self.import_finished = False

        self.md5 = None
        self.md5sum: Optional[bytes] = None
        self.md5of16k: Optional[bytes] = None
        self.valid = bool(raw_article_db)

        if self.valid and self.nzf_id:
            # Save first article separate so we can do
            # duplicate file detection and deobfuscate-during-download
            first_article = self.add_article(raw_article_db.pop(0))
            first_article.lowest_partnum = True
            self.nzo.first_articles.append(first_article)
            self.nzo.first_articles_count += 1

            # Count how many bytes are available for repair
            if sabnzbd.par2file.is_parfile(self.filename):
                self.nzo.bytes_par2 += self.bytes

            # Any articles left?
            if raw_article_db:
                # Save the rest
                sabnzbd.save_data(raw_article_db, self.nzf_id, nzo.admin_path)
            else:
                # All imported
                self.import_finished = True

    def finish_import(self):
        """ Load the article objects from disk """
        logging.debug("Finishing import on %s", self.filename)
        raw_article_db = sabnzbd.load_data(self.nzf_id, self.nzo.admin_path, remove=False)
        if raw_article_db:
            # Convert 2.x.x jobs
            if isinstance(raw_article_db, dict):
                raw_article_db = [raw_article_db[partnum] for partnum in sorted(raw_article_db)]

            for raw_article in raw_article_db:
                self.add_article(raw_article)

            # Make sure we have labeled the lowest part number
            # Also when DirectUnpack is disabled we need to know
            self.decodetable[0].lowest_partnum = True

            # Mark safe to continue
            self.import_finished = True

    def add_article(self, article_info):
        """ Add article to object database and return article object """
        article = Article(article_info[0], article_info[1], self)
        self.articles.append(article)
        self.decodetable.append(article)
        return article

    def remove_article(self, article: Article, success: bool) -> int:
        """ Handle completed article, possibly end of file """
        if article in self.articles:
            self.articles.remove(article)
            if success:
                self.bytes_left -= article.bytes
        return len(self.articles)

    def set_par2(self, setname, vol, blocks):
        """ Designate this this file as a par2 file """
        self.is_par2 = True
        self.setname = setname
        self.vol = vol
        self.blocks = int_conv(blocks)

    def get_article(self, server: Server, servers: List[Server]) -> Optional[Article]:
        """ Get next article to be downloaded """
        for article in self.articles:
            article = article.get_article(server, servers)
            if article:
                return article
        self.add_to_try_list(server)

    def reset_all_try_lists(self):
        """ Clear all lists of visited servers """
        for art in self.articles:
            art.reset_try_list()
        self.reset_try_list()

    def prepare_filepath(self):
        """ Do all checks before making the final path """
        if not self.filepath:
            self.nzo.verify_nzf_filename(self)
            filename = sanitize_filename(self.filename)
            self.filepath = get_filepath(long_path(cfg.download_dir.get_path()), self.nzo, filename)
            self.filename = get_filename(self.filepath)
        return self.filepath

    @property
    def completed(self):
        """ Is this file completed? """
        return self.import_finished and not bool(self.articles)

    def remove_admin(self):
        """ Remove article database from disk (sabnzbd_nzf_<id>)"""
        try:
            logging.debug("Removing article database for %s", self.nzf_id)
            remove_file(os.path.join(self.nzo.admin_path, self.nzf_id))
        except:
            pass

    def __getstate__(self):
        """ Save to pickle file, selecting attributes """
        dict_ = {}
        for item in NzbFileSaver:
            dict_[item] = getattr(self, item)
        dict_["try_list"] = super().__getstate__()
        return dict_

    def __setstate__(self, dict_):
        """ Load from pickle file, selecting attributes """
        for item in NzbFileSaver:
            try:
                setattr(self, item, dict_[item])
            except KeyError:
                # Handle new attributes
                setattr(self, item, None)
        super().__setstate__(dict_.get("try_list", []))

        # Convert 2.x.x jobs
        if isinstance(self.decodetable, dict):
            self.decodetable = [self.decodetable[partnum] for partnum in sorted(self.decodetable)]

        # Set non-transferable values
        self.md5 = None

    def __eq__(self, other):
        """Assume it's the same file if the numer bytes and first article
        are the same or if there are no articles left, use the filenames
        """
        if self.bytes == other.bytes:
            if self.decodetable and other.decodetable:
                return self.decodetable[0] == other.decodetable[0]
            # Fallback to filename comparison
            return self.filename == other.filename
        return False

    def __hash__(self):
        """Required because we implement eq. The same file can be spread
        over multiple NZO's so we make every NZF unique. Even though
        it's considered bad pratice.
        """
        return id(self)

    def __repr__(self):
        return "<NzbFile: filename=%s, bytes=%s, nzf_id=%s>" % (self.filename, self.bytes, self.nzf_id)


##############################################################################
# NzbObject
##############################################################################
NzbObjectSaver = (
    "filename",
    "work_name",
    "final_name",
    "created",
    "bytes",
    "bytes_downloaded",
    "bytes_tried",
    "bytes_missing",
    "bytes_par2",
    "repair",
    "unpack",
    "delete",
    "script",
    "cat",
    "url",
    "groups",
    "avg_date",
    "md5of16k",
    "partable",
    "extrapars",
    "md5packs",
    "files",
    "files_table",
    "finished_files",
    "status",
    "avg_bps_freq",
    "avg_bps_total",
    "priority",
    "saved_articles",
    "nzo_id",
    "futuretype",
    "deleted",
    "parsed",
    "action_line",
    "unpack_info",
    "fail_msg",
    "nzo_info",
    "custom_name",
    "password",
    "next_save",
    "save_timeout",
    "encrypted",
    "bad_articles",
    "duplicate",
    "oversized",
    "precheck",
    "incomplete",
    "reuse",
    "meta",
    "first_articles",
    "first_articles_count",
    "md5sum",
    "servercount",
    "unwanted_ext",
    "renames",
    "rating_filtered",
)

NzoAttributeSaver = ("cat", "pp", "script", "priority", "final_name", "password", "url")

# Lock to prevent errors when saving the NZO data
NZO_LOCK = threading.RLock()


class NzbObject(TryList):
    def __init__(
        self,
        filename,
        pp=None,
        script=None,
        nzb=None,
        futuretype=False,
        cat=None,
        url=None,
        priority=DEFAULT_PRIORITY,
        nzbname=None,
        status=Status.QUEUED,
        nzo_info=None,
        reuse=None,
        dup_check=True,
    ):
        super().__init__()

        self.filename = filename  # Original filename
        if nzbname and nzb:
            self.work_name = nzbname  # Use nzbname if set and only for non-future slot
        else:
            self.work_name = filename

        # For future-slots we keep the name given by URLGrabber
        if nzb is None:
            self.final_name = self.work_name = filename
        else:
            # Remove trailing .nzb and .par(2)
            self.work_name = create_work_name(self.work_name)

        # Extract password
        self.work_name, self.password = scan_password(self.work_name)
        if not self.work_name:
            # In case only /password was entered for nzbname
            self.work_name = filename
        self.final_name = self.work_name

        # Check for password also in filename
        if not self.password:
            _, self.password = scan_password(os.path.splitext(filename)[0])

        # Determine category and find pp/script values based on input
        # Later will be re-evaluated based on import steps
        if pp is None:
            r = u = d = None
        else:
            r, u, d = pp_to_opts(pp)

        self.priority: int = NORMAL_PRIORITY
        self.set_priority(priority)  # Parse priority of input
        self.repair: bool = r  # True if we want to repair this set
        self.unpack: bool = u  # True if we want to unpack this set
        self.delete: bool = d  # True if we want to delete this set
        self.script: str = script  # External script for this set
        if not is_valid_script(self.script):
            self.script = None
        self.cat = cat  # User-set category

        # Information fields
        self.url = url or filename
        self.groups = []
        self.avg_date = datetime.datetime(1970, 1, 1, 1, 0)
        self.avg_stamp = 0.0  # Avg age in seconds (calculated from avg_age)

        # Bookkeeping values
        self.meta = {}
        self.servercount: Dict[str, int] = {}  # Dict to keep bytes per server
        self.created = False  # dirprefixes + work_name created
        self.direct_unpacker: Optional[sabnzbd.directunpacker.DirectUnpacker] = None  # The DirectUnpacker instance
        self.bytes: int = 0  # Original bytesize
        self.bytes_par2: int = 0  # Bytes available for repair
        self.bytes_downloaded: int = 0  # Downloaded byte
        self.bytes_tried: int = 0  # Which bytes did we try
        self.bytes_missing: int = 0  # Bytes missing
        self.bad_articles: int = 0  # How many bad (non-recoverable) articles

        self.partable: Dict[str, NzbFile] = {}  # Holds one parfile-name for each set
        self.extrapars: Dict[str, List[NzbFile]] = {}  # Holds the extra parfile names for all sets
        self.md5packs: Dict[str, Dict[str, bytes]] = {}  # Holds the md5pack for each set (name: hash)
        self.md5of16k: Dict[bytes, str] = {}  # Holds the md5s of the first-16k of all files in the NZB (hash: name)

        self.files: List[NzbFile] = []  # List of all NZFs
        self.files_table: Dict[str, NzbFile] = {}  # Dictionary of NZFs indexed using NZF_ID
        self.renames: Dict[str, str] = {}  # Dictionary of all renamed files

        self.finished_files: List[NzbFile] = []  # List of all finished NZFs

        # The current status of the nzo eg:
        # Queued, Downloading, Repairing, Unpacking, Failed, Complete
        self.status: str = status
        self.avg_bps_freq = 0
        self.avg_bps_total = 0

        self.first_articles: List[Article] = []
        self.first_articles_count = 0
        self.saved_articles: List[Article] = []

        self.nzo_id = None

        self.futuretype = futuretype
        self.deleted = False
        self.to_be_removed = False
        self.parsed = False
        self.duplicate = False
        self.oversized = False
        self.precheck = False
        self.incomplete = False
        self.unwanted_ext = 0
        self.rating_filtered = 0
        self.reuse = reuse
        if self.status == Status.QUEUED and not reuse:
            self.precheck = cfg.pre_check()
            if self.precheck:
                self.status = Status.CHECKING

        # Store one line responses for filejoin/par2/unrar/unzip here for history display
        self.action_line = ""
        # Store the results from various filejoin/par2/unrar/unzip stages
        self.unpack_info: Dict[str, List[str]] = {}
        # Stores one line containing the last failure
        self.fail_msg = ""
        # Stores various info about the nzo to be
        self.nzo_info: Dict[str, Any] = nzo_info or {}

        # Temporary store for custom foldername - needs to be stored because of url fetching
        self.custom_name = nzbname

        self.next_save = None
        self.save_timeout = None
        self.encrypted = 0
        self.url_wait: Optional[float] = None
        self.url_tries = 0
        self.pp_active = False  # Signals active post-processing (not saved)
        self.md5sum: Optional[bytes] = None

        if nzb is None and not reuse:
            # This is a slot for a future NZB, ready now
            # It can also be a retry of a failed job with no extra NZB-file
            return

        # Apply conversion option to final folder
        if cfg.replace_spaces():
            logging.info("Replacing spaces with underscores in %s", self.final_name)
            self.final_name = self.final_name.replace(" ", "_")
        if cfg.replace_dots():
            logging.info("Replacing dots with spaces in %s", self.final_name)
            self.final_name = self.final_name.replace(".", " ")

        # Check against identical checksum or series/season/episode
        if (not reuse) and nzb and dup_check and self.priority != REPAIR_PRIORITY:
            duplicate, series = self.has_duplicates()
        else:
            duplicate = series = 0

        # Reuse the existing directory
        if reuse and os.path.exists(reuse):
            work_dir = long_path(reuse)
        else:
            # Determine "incomplete" folder
            work_dir = os.path.join(cfg.download_dir.get_path(), self.work_name)
            work_dir = get_unique_path(work_dir, create_dir=True)
            set_permissions(work_dir)

        # Always create the admin-directory, just to be sure
        admin_dir = os.path.join(work_dir, JOB_ADMIN)
        if not os.path.exists(admin_dir):
            os.mkdir(admin_dir)
        _, self.work_name = os.path.split(work_dir)
        self.created = True

        # When doing a retry or repair, remove old cache-files
        if reuse:
            remove_all(admin_dir, "SABnzbd_nz?_*", keep_folder=True)
            remove_all(admin_dir, "SABnzbd_article_*", keep_folder=True)

        if nzb and "<nzb" in nzb:
            try:
                sabnzbd.nzbparser.nzbfile_parser(nzb, self)
            except Exception as err:
                self.incomplete = True
                logging.warning(T("Invalid NZB file %s, skipping (reason=%s, line=%s)"), filename, err, "1")
                logging.info("Traceback: ", exc_info=True)

                # Some people want to keep the broken files
                if cfg.allow_incomplete_nzb():
                    self.pause()
                else:
                    self.purge_data()
                    raise ValueError

            sabnzbd.backup_nzb(filename, nzb)
            sabnzbd.save_compressed(admin_dir, filename, nzb)

        if not self.files and not reuse:
            self.purge_data()
            if self.url:
                logging.warning(T("Empty NZB file %s") + " [%s]", filename, self.url)
            else:
                logging.warning(T("Empty NZB file %s"), filename)
            raise ValueError

        if cat is None:
            for metacat in self.meta.get("category", ()):
                metacat = cat_convert(metacat)
                if metacat:
                    cat = metacat
                    break

        if cat is None:
            for grp in self.groups:
                cat = cat_convert(grp)
                if cat:
                    break

        # Pickup backed-up attributes when re-using
        if reuse:
            cat, pp, script = self.load_attribs()

        # Determine category and find pp/script values
        self.cat, pp_tmp, self.script, priority = cat_to_opts(cat, pp, script, self.priority)
        self.set_priority(priority)
        self.repair, self.unpack, self.delete = pp_to_opts(pp_tmp)

        # Run user pre-queue script if set and valid
        if not reuse and make_script_path(cfg.pre_script()):
            # Call the script
            accept, name, pp, cat_pp, script_pp, priority, group = sabnzbd.newsunpack.pre_queue(self, pp, cat)

            # Accept or reject
            accept = int_conv(accept)
            if accept < 1:
                self.purge_data()
                raise TypeError
            if accept == 2:
                self.fail_msg = T("Pre-queue script marked job as failed")

            # Process all options, only over-write if set by script
            # Beware that cannot do "if priority/pp", because those can
            # also have a valid value of 0, which shouldn't be ignored
            if name:
                self.set_final_name_and_scan_password(name)
            try:
                pp = int(pp)
            except:
                pp = None
            if cat_pp:
                cat = cat_pp
            try:
                priority = int(priority)
            except:
                priority = DEFAULT_PRIORITY
            if script_pp and is_valid_script(script_pp):
                script = script_pp
            if group:
                self.groups = [str(group)]

            # Re-evaluate results from pre-queue script
            self.cat, pp, self.script, priority = cat_to_opts(cat, pp, script, priority)
            self.set_priority(priority)
            self.repair, self.unpack, self.delete = pp_to_opts(pp)
        else:
            accept = 1

        # Pause if requested by the NZB-adding or the pre-queue script
        if self.priority == PAUSED_PRIORITY:
            self.pause()
            self.priority = NORMAL_PRIORITY

        # Pause job when above size limit
        limit = cfg.size_limit.get_int()
        if not reuse and abs(limit) > 0.5 and self.bytes > limit:
            logging.info("Job too large, forcing low prio and paused (%s)", self.final_name)
            self.pause()
            self.oversized = True
            self.priority = LOW_PRIORITY

        if duplicate and ((not series and cfg.no_dupes() == 1) or (series and cfg.no_series_dupes() == 1)):
            if cfg.warn_dupl_jobs():
                logging.warning(T('Ignoring duplicate NZB "%s"'), filename)
            self.purge_data()
            raise TypeError

        if duplicate and ((not series and cfg.no_dupes() == 3) or (series and cfg.no_series_dupes() == 3)):
            if cfg.warn_dupl_jobs():
                logging.warning(T('Failing duplicate NZB "%s"'), filename)
            # Move to history, utilizing the same code as accept&fail from pre-queue script
            self.fail_msg = T("Duplicate NZB")
            accept = 2
            duplicate = False

        if duplicate or self.priority == DUP_PRIORITY:
            self.duplicate = True
            if cfg.no_dupes() == 4 or cfg.no_series_dupes() == 4:
                if cfg.warn_dupl_jobs():
                    logging.warning('%s: "%s"', T("Duplicate NZB"), filename)
            else:
                if cfg.warn_dupl_jobs():
                    logging.warning(T('Pausing duplicate NZB "%s"'), filename)
                self.pause()

            # Only change priority it's currently set to duplicate, otherwise keep original one
            if self.priority == DUP_PRIORITY:
                self.priority = NORMAL_PRIORITY

        # Check if there is any unwanted extension in plain sight in the NZB itself
        for nzf in self.files:
            if (
                cfg.action_on_unwanted_extensions() >= 1
                and get_ext(nzf.filename).replace(".", "") in cfg.unwanted_extensions()
            ):
                # ... we found an unwanted extension
                logging.warning(T("Unwanted Extension in file %s (%s)"), nzf.filename, self.final_name)
                # Pause, or Abort:
                if cfg.action_on_unwanted_extensions() == 1:
                    logging.debug("Unwanted extension ... pausing")
                    self.unwanted_ext = 1
                    self.pause()
                if cfg.action_on_unwanted_extensions() == 2:
                    logging.debug("Unwanted extension ... aborting")
                    self.fail_msg = T("Aborted, unwanted extension detected")
                    accept = 2

        if reuse:
            self.check_existing_files(work_dir)

        # Sort the files in the queue
        self.sort_nzfs()

        # Copy meta fields to nzo_info, if not already set
        for kw in self.meta:
            if not self.nzo_info.get(kw):
                self.nzo_info[kw] = self.meta[kw][0]

        # Show first meta-password (if any), when there's no explicit password
        if not self.password and self.meta.get("password"):
            self.password = self.meta.get("password", [None])[0]

        # Set nzo save-delay to minimum 120 seconds
        self.save_timeout = max(120, min(6.0 * self.bytes / GIGI, 300.0))

        # In case pre-queue script or duplicate check want to move
        # to history we first need an nzo_id by entering the NzbQueue
        if accept == 2:
            sabnzbd.NzbQueue.add(self, quiet=True)
            sabnzbd.NzbQueue.end_job(self)
            # Raise error, so it's not added
            raise TypeError

    def update_download_stats(self, bps, serverid, bytes_received):
        if bps:
            self.avg_bps_total += bps / 1024
            self.avg_bps_freq += 1
        if serverid in self.servercount:
            self.servercount[serverid] += bytes_received
        else:
            self.servercount[serverid] = bytes_received

    @synchronized(NZO_LOCK)
    def remove_nzf(self, nzf: NzbFile) -> bool:
        if nzf in self.files:
            self.files.remove(nzf)
        if nzf not in self.finished_files:
            self.finished_files.append(nzf)
        nzf.import_finished = True
        nzf.deleted = True
        return not bool(self.files)

    def sort_nzfs(self):
        """Sort the files in the NZO based on name and type
        and then optimize for unwanted extensions search.
        """
        self.files.sort(key=functools.cmp_to_key(nzf_cmp_name))

        # In the hunt for Unwanted Extensions:
        # The file with the unwanted extension often is in the first or the last rar file
        # So put the last rar immediately after the first rar file so that it gets detected early
        if cfg.unwanted_extensions():
            # ... only useful if there are unwanted extensions defined and there is no sorting on date
            logging.debug("Unwanted Extension: putting last rar after first rar")
            firstrarpos = lastrarpos = 0
            for nzfposcounter, nzf in enumerate(self.files):
                if RE_RAR.search(nzf.filename.lower()):
                    # a NZF found with '.rar' in the name
                    if firstrarpos == 0:
                        # this is the first .rar found, so remember this position
                        firstrarpos = nzfposcounter
                    lastrarpos = nzfposcounter
                    lastrarnzf = nzf  # The NZF itself

            if firstrarpos != lastrarpos:
                # at least two different .rar's found
                logging.debug("Unwanted Extension: First rar at %s, Last rar at %s", firstrarpos, lastrarpos)
                logging.debug("Unwanted Extension: Last rar is %s", lastrarnzf.filename)
                try:
                    # Remove and add it back after the position of the first rar
                    self.files.remove(lastrarnzf)
                    self.files.insert(firstrarpos + 1, lastrarnzf)
                except:
                    logging.debug("The lastrar swap did not go well")

    def reset_all_try_lists(self):
        for nzf in self.files:
            nzf.reset_all_try_lists()
        self.reset_try_list()

    @synchronized(NZO_LOCK)
    def postpone_pars(self, nzf: NzbFile, parset: str):
        """ Move all vol-par files matching 'parset' to the extrapars table """
        # Create new extrapars if it didn't already exist
        # For example if created when the first par2 file was missing
        if parset not in self.extrapars:
            self.extrapars[parset] = []

        # Set this one as the main one
        self.partable[parset] = nzf

        lparset = parset.lower()
        for xnzf in self.files[:]:
            name = xnzf.filename or xnzf.subject
            # Move only when not current NZF and filename was extractable from subject
            if name:
                setname, vol, block = sabnzbd.par2file.analyse_par2(name)
                # Don't postpone header-only-files, to extract all possible md5of16k
                if setname and block and matcher(lparset, setname.lower()):
                    xnzf.set_par2(parset, vol, block)
                    # Don't postpone if all par2 are desired and should be kept or not repairing
                    if self.repair and not (cfg.enable_all_par() and not cfg.enable_par_cleanup()):
                        self.extrapars[parset].append(xnzf)
                        self.files.remove(xnzf)
                        # Already count these bytes as done
                        self.bytes_tried += xnzf.bytes_left

        # Sort the sets
        for setname in self.extrapars:
            self.extrapars[setname].sort(key=lambda x: x.blocks)

        # Also re-parse all filenames in case par2 came after first articles
        self.verify_all_filenames_and_resort()

    @synchronized(NZO_LOCK)
    def handle_par2(self, nzf: NzbFile, filepath):
        """ Check if file is a par2 and build up par2 collection """
        # Need to remove it from the other set it might be in
        self.remove_extrapar(nzf)

        # Reparse
        setname, vol, block = sabnzbd.par2file.analyse_par2(nzf.filename, filepath)
        nzf.set_par2(setname, vol, block)

        # Parse the file contents for hashes
        pack = sabnzbd.par2file.parse_par2_file(filepath, nzf.nzo.md5of16k)

        # If we couldn't parse it, we ignore it
        if pack:
            if pack not in self.md5packs.values():
                logging.debug("Got md5pack for set %s", nzf.setname)
                self.md5packs[setname] = pack
                # See if we need to postpone some pars
                self.postpone_pars(nzf, setname)
            else:
                # Need to add this to the set, first need setname
                for setname in self.md5packs:
                    if self.md5packs[setname] == pack:
                        break

                # Change the properties
                nzf.set_par2(setname, vol, block)
                logging.debug("Got additional md5pack for set %s", nzf.setname)

                # Make sure it exists, could be removed by newsunpack
                if setname not in self.extrapars:
                    self.extrapars[setname] = []
                self.extrapars[setname].append(nzf)

        elif self.repair:
            # For some reason this par2 file is broken but we still want repair
            self.promote_par2(nzf)

        # Is it an obfuscated file?
        if get_ext(nzf.filename) != ".par2":
            # Do cheap renaming so it gets better picked up by par2
            # Only basename has to be the same
            new_fname = get_unique_filename(os.path.join(self.download_path, "%s.par2" % setname))
            renamer(filepath, new_fname)
            self.renamed_file(get_filename(new_fname), nzf.filename)
            nzf.filename = get_filename(new_fname)

    @synchronized(NZO_LOCK)
    def promote_par2(self, nzf: NzbFile):
        """In case of a broken par2 or missing par2, move another
        of the same set to the top (if we can find it)
        """
        setname, vol, block = sabnzbd.par2file.analyse_par2(nzf.filename)
        # Now we need to identify if we have more in this set
        if setname and self.repair:
            # Maybe it was the first one
            if setname not in self.extrapars:
                self.postpone_pars(nzf, setname)
            # Get the next one
            for new_nzf in self.extrapars[setname]:
                if not new_nzf.completed:
                    self.add_parfile(new_nzf)
                    # Add it to the top
                    self.files.remove(new_nzf)
                    self.files.insert(0, new_nzf)
                    break

    def get_extra_blocks(self, setname, needed_blocks):
        """We want par2-files of all sets that are similar to this one
        So that we also can handle multi-sets with duplicate filenames
        Returns number of added blocks in case they are available
        In case of duplicate files for the same set, we might add too
        little par2 on the first add-run, but that's a risk we need to take.
        """
        logging.info("Need %s more blocks, checking blocks", needed_blocks)

        avail_blocks = 0
        block_list = []
        for setname_search in self.extrapars:
            # Do it for our set, or highlight matching one
            # We might catch too many par2's, but that's okay
            if setname_search == setname or difflib.SequenceMatcher(None, setname, setname_search).ratio() > 0.85:
                for nzf in self.extrapars[setname_search]:
                    # Don't count extrapars that are completed already
                    if nzf.completed:
                        continue
                    block_list.append(nzf)
                    avail_blocks += nzf.blocks

        # Sort by smallest blocks last, to be popped first
        block_list.sort(key=lambda x: x.blocks, reverse=True)
        logging.info("%s blocks available", avail_blocks)

        # Enough?
        if avail_blocks >= needed_blocks:
            added_blocks = 0
            while added_blocks < needed_blocks:
                new_nzf = block_list.pop()
                self.add_parfile(new_nzf)
                added_blocks += new_nzf.blocks

            logging.info("Added %s blocks to %s", added_blocks, self.final_name)
            return added_blocks
        else:
            # Not enough
            return False

    @synchronized(NZO_LOCK)
    def remove_article(self, article: Article, success: bool):
        """ Remove article from the NzbFile and do check if it can succeed"""
        job_can_succeed = True
        nzf = article.nzf

        # Update all statistics
        # Ignore bytes from par2 files that were postponed
        if nzf in self.files:
            self.bytes_tried += article.bytes
        if not success:
            # Increase missing bytes counter
            self.bytes_missing += article.bytes

            # Add extra parfiles when there was a damaged article and not pre-checking
            if self.extrapars and not self.precheck:
                self.prospective_add(nzf)

            # Sometimes a few CRC errors are still fine, abort otherwise
            if self.bad_articles > MAX_BAD_ARTICLES:
                self.abort_direct_unpacker()
        else:
            # Increase counter of actually finished bytes
            self.bytes_downloaded += article.bytes

        # First or regular article?
        if article.lowest_partnum and self.first_articles and article in self.first_articles:
            self.first_articles.remove(article)

            # All first articles done?
            if not self.first_articles:
                # Do we have rename information from par2
                if self.md5of16k:
                    self.verify_all_filenames_and_resort()

                # Check the availability of these first articles
                if cfg.fail_hopeless_jobs() and cfg.fast_fail():
                    job_can_succeed = self.check_first_article_availability()

        # Remove from file-tracking
        articles_left = nzf.remove_article(article, success)
        file_done = not articles_left

        # Only on fully loaded files we can know if it's really done
        if not nzf.import_finished:
            file_done = False

        # File completed, remove and do checks
        if file_done:
            self.remove_nzf(nzf)

        # Check if we can succeed when we have missing articles
        # Skip check if retry or first articles already deemed it hopeless
        if not success and job_can_succeed and not self.reuse and cfg.fail_hopeless_jobs():
            job_can_succeed, _ = self.check_availability_ratio()

        # Abort the job due to failure
        if not job_can_succeed:
            self.fail_msg = T("Aborted, cannot be completed") + " - https://sabnzbd.org/not-complete"
            self.set_unpack_info("Download", self.fail_msg, unique=False)
            logging.debug('Abort job "%s", due to impossibility to complete it', self.final_name)
            return True, True, True

        # Check if there are any files left here, so the check is inside the NZO_LOCK
        return articles_left, file_done, not self.files

    @synchronized(NZO_LOCK)
    def add_saved_article(self, article: Article):
        self.saved_articles.append(article)

    @synchronized(NZO_LOCK)
    def remove_saved_article(self, article: Article):
        try:
            self.saved_articles.remove(article)
        except ValueError:
            # It's not there if the job is fully missing
            # and this function is called from file_has_articles
            pass

    def check_existing_files(self, wdir: str):
        """ Check if downloaded files already exits, for these set NZF to complete """
        fix_unix_encoding(wdir)

        # Get a list of already present files, ignore folders
        files = globber(wdir, "*.*")

        # Substitute renamed files
        renames = sabnzbd.load_data(RENAMES_FILE, self.admin_path, remove=True)
        if renames:
            for name in renames:
                if name in files or renames[name] in files:
                    if name in files:
                        files.remove(name)
                    files.append(renames[name])
            self.renames = renames

        # Looking for the longest name first, minimizes the chance on a mismatch
        files.sort(key=len)

        # The NZFs should be tried shortest first, to improve the chance on a proper match
        nzfs = self.files[:]
        nzfs.sort(key=lambda x: len(x.subject))

        # Flag files from NZB that already exist as finished
        for filename in files[:]:
            for nzf in nzfs:
                subject = sanitize_filename(name_extractor(nzf.subject))
                if (nzf.filename == filename) or (subject == filename) or (filename in subject):
                    logging.info("Existing file %s matched to file %s of %s", filename, nzf.filename, self.final_name)
                    nzf.filename = filename
                    nzf.bytes_left = 0
                    self.remove_nzf(nzf)
                    nzfs.remove(nzf)
                    files.remove(filename)

                    # Set bytes correctly
                    self.bytes_tried += nzf.bytes
                    self.bytes_downloaded += nzf.bytes

                    # Process par2 files
                    filepath = os.path.join(wdir, filename)
                    if sabnzbd.par2file.is_parfile(filepath):
                        self.handle_par2(nzf, filepath)
                        self.bytes_par2 += nzf.bytes
                    break

        # Create an NZF for each remaining existing file
        try:
            for filename in files:
                # Create NZO's using basic information
                filepath = os.path.join(wdir, filename)
                logging.info("Existing file %s added to %s", filename, self.final_name)
                tup = os.stat(filepath)
                tm = datetime.datetime.fromtimestamp(tup.st_mtime)
                nzf = NzbFile(tm, filename, [], tup.st_size, self)
                self.files.append(nzf)
                self.files_table[nzf.nzf_id] = nzf
                nzf.filename = filename
                self.remove_nzf(nzf)

                # Set bytes correctly
                self.bytes += nzf.bytes
                self.bytes_tried += nzf.bytes
                self.bytes_downloaded += nzf.bytes

                # Process par2 files
                if sabnzbd.par2file.is_parfile(filepath):
                    self.handle_par2(nzf, filepath)
                    self.bytes_par2 += nzf.bytes

        except:
            logging.error(T("Error importing %s"), self.final_name)
            logging.info("Traceback: ", exc_info=True)

    @property
    def pp(self):
        if self.repair is None:
            return None
        else:
            return opts_to_pp(self.repair, self.unpack, self.delete)

    def set_pp(self, value):
        self.repair, self.unpack, self.delete = pp_to_opts(value)
        logging.info("Set pp=%s for job %s", value, self.final_name)
        # Abort unpacking if not desired anymore
        if not self.unpack:
            self.abort_direct_unpacker()

    def set_priority(self, value: Any):
        """ Check if this is a valid priority """
        # When unknown (0 is a known one), set to DEFAULT
        if value == "" or value is None:
            self.priority = DEFAULT_PRIORITY
            return

        # Convert input
        value = int_conv(value)
        if value in (
            REPAIR_PRIORITY,
            FORCE_PRIORITY,
            HIGH_PRIORITY,
            NORMAL_PRIORITY,
            LOW_PRIORITY,
            DEFAULT_PRIORITY,
            PAUSED_PRIORITY,
            DUP_PRIORITY,
            STOP_PRIORITY,
        ):
            self.priority = value
            return

        # Invalid value, set to normal priority
        self.priority = NORMAL_PRIORITY

    @property
    def labels(self):
        """ Return (translated) labels of job """
        labels = []
        if self.duplicate:
            labels.append(T("DUPLICATE"))
        if self.encrypted > 0:
            labels.append(T("ENCRYPTED"))
        if self.oversized:
            labels.append(T("TOO LARGE"))
        if self.incomplete:
            labels.append(T("INCOMPLETE"))
        if self.unwanted_ext:
            labels.append(T("UNWANTED"))
        if self.rating_filtered:
            labels.append(T("FILTERED"))

        # Waiting for URL fetching
        if isinstance(self.url_wait, float):
            dif = int(self.url_wait - time.time() + 0.5)
            if dif > 0:
                labels.append(T("WAIT %s sec") % dif)

        # Propagation delay label
        propagation_delay = float(cfg.propagation_delay() * 60)
        if propagation_delay and self.avg_stamp + propagation_delay > time.time() and self.priority != FORCE_PRIORITY:
            wait_time = int((self.avg_stamp + propagation_delay - time.time()) / 60 + 0.5)
            labels.append(T("PROPAGATING %s min") % wait_time)  # Queue indicator while waiting for propagation of post

        return labels

    @property
    def final_name_with_password(self):
        if self.password:
            return "%s / %s" % (self.final_name, self.password)
        else:
            return self.final_name

    def set_final_name_and_scan_password(self, name, password=None):
        if isinstance(name, str):
            if password is not None:
                self.password = password
            else:
                name, password = scan_password(name)
                if password is not None:
                    self.password = password

            self.final_name = sanitize_foldername(name)
            self.save_to_disk()

    def pause(self):
        self.status = Status.PAUSED
        # Prevent loss of paused state when terminated
        if self.nzo_id and not self.is_gone():
            self.save_to_disk()

    def resume(self):
        self.status = Status.QUEUED
        if self.encrypted > 0:
            # If user resumes after encryption warning, no more auto-pauses
            self.encrypted = 2
        if self.rating_filtered:
            # If user resumes after filtered warning, no more auto-pauses
            self.rating_filtered = 2
        # If user resumes after warning, reset duplicate/oversized/incomplete/unwanted indicators
        self.duplicate = False
        self.oversized = False
        self.incomplete = False
        if self.unwanted_ext:
            # If user resumes after "unwanted" warning, no more auto-pauses
            self.unwanted_ext = 2

    @synchronized(NZO_LOCK)
    def add_parfile(self, parfile):
        """Add parfile to the files to be downloaded
        Resets trylist just to be sure
        Adjust download-size accordingly
        """
        if not parfile.completed and parfile not in self.files and parfile not in self.finished_files:
            parfile.reset_all_try_lists()
            self.files.append(parfile)
            self.bytes_tried -= parfile.bytes_left

    @synchronized(NZO_LOCK)
    def remove_parset(self, setname):
        if setname in self.extrapars:
            self.extrapars.pop(setname)
        if setname in self.partable:
            self.partable.pop(setname)

    @synchronized(NZO_LOCK)
    def remove_extrapar(self, parfile: NzbFile):
        """ Remove par file from any/all sets """
        for _set in self.extrapars:
            if parfile in self.extrapars[_set]:
                self.extrapars[_set].remove(parfile)

    @synchronized(NZO_LOCK)
    def prospective_add(self, nzf: NzbFile):
        """Add par2 files to compensate for missing articles
        This fails in case of multi-sets with identical setnames
        """
        # Make sure to also select a parset if it was in the original filename
        original_filename = self.renames.get(nzf.filename, "")

        # Get some blocks!
        if not nzf.is_par2:
            # We have to find the right par-set
            blocks_new = 0
            for parset in self.extrapars.keys():
                if (parset in nzf.filename or parset in original_filename) and self.extrapars[parset]:
                    for new_nzf in self.extrapars[parset]:
                        self.add_parfile(new_nzf)
                        blocks_new += new_nzf.blocks
                        # Enough now?
                        if blocks_new >= self.bad_articles:
                            logging.info("Prospectively added %s repair blocks to %s", blocks_new, self.final_name)
                            break
                    # Reset NZO TryList
                    self.reset_try_list()

    def add_to_direct_unpacker(self, nzf: NzbFile):
        """ Start or add to DirectUnpacker """
        if not self.direct_unpacker:
            sabnzbd.directunpacker.DirectUnpacker(self)
        self.direct_unpacker.add(nzf)

    def abort_direct_unpacker(self):
        """ Abort any running DirectUnpackers """
        if self.direct_unpacker:
            self.direct_unpacker.abort()

    def check_availability_ratio(self):
        """ Determine if we are still meeting the required ratio """
        availability_ratio = req_ratio = cfg.req_completion_rate()

        # Rare case where the NZB only consists of par2 files
        if self.bytes > self.bytes_par2:
            # Calculate ratio based on byte-statistics
            availability_ratio = 100 * (self.bytes - self.bytes_missing) / (self.bytes - self.bytes_par2)

        logging.debug(
            "Availability ratio=%.2f, bad articles=%d, total bytes=%d, missing bytes=%d, par2 bytes=%d",
            availability_ratio,
            self.bad_articles,
            self.bytes,
            self.bytes_missing,
            self.bytes_par2,
        )

        # When there is no or little par2, we allow a few bad articles
        # This way RAR-only jobs might still succeed
        if self.bad_articles <= MAX_BAD_ARTICLES:
            return True, req_ratio

        # Check based on availability ratio
        return availability_ratio >= req_ratio, availability_ratio

    def check_first_article_availability(self):
        """Use the first articles to see if
        it's likely the job will succeed
        """
        # Ignore this check on retry
        if not self.reuse:
            # Ignore undamaged or small downloads
            if self.bad_articles and self.first_articles_count >= 10:
                # We need a float-division, see if more than 80% is there
                if self.bad_articles / self.first_articles_count >= 0.8:
                    return False
        return True

    @synchronized(NZO_LOCK)
    def set_download_report(self):
        """ Format the stats for the history information """
        # Pretty-format the per-server stats
        if self.servercount:
            # Sort the servers first
            servers = config.get_servers()
            server_names = sorted(
                servers,
                key=lambda svr: "%d%02d%s"
                % (int(not servers[svr].enable()), servers[svr].priority(), servers[svr].displayname().lower()),
            )
            msgs = [
                "%s=%sB" % (servers[server_name].displayname(), to_units(self.servercount[server_name]))
                for server_name in server_names
                if server_name in self.servercount
            ]
            self.set_unpack_info("Servers", ", ".join(msgs), unique=True)

            # In case there were no bytes available at all of this download
            # we list the number of bytes we used while trying
            if not self.bytes_downloaded:
                self.bytes_downloaded = sum(self.servercount.values())

        # Format information about the download itself
        download_msgs = []
        if self.avg_bps_total and self.bytes_downloaded and self.avg_bps_freq:
            # Get the seconds it took to complete the download
            avg_bps = self.avg_bps_total / self.avg_bps_freq
            download_time = int_conv(self.bytes_downloaded / (avg_bps * 1024))
            self.nzo_info["download_time"] = download_time

            # Format the total time the download took, in days, hours, and minutes, or seconds.
            complete_time = format_time_string(download_time)
            download_msgs.append(
                T("Downloaded in %s at an average of %sB/s") % (complete_time, to_units(avg_bps * 1024))
            )
            download_msgs.append(T("Age") + ": " + calc_age(self.avg_date, True))

        bad = self.nzo_info.get("bad_articles", 0)
        miss = self.nzo_info.get("missing_articles", 0)
        dups = self.nzo_info.get("duplicate_articles", 0)

        if bad:
            download_msgs.append(T("%s articles were malformed") % bad)
        if miss:
            download_msgs.append(T("%s articles were missing") % miss)
        if dups:
            download_msgs.append(T("%s articles had non-matching duplicates") % dups)
        self.set_unpack_info("Download", "<br/>".join(download_msgs), unique=True)

        if self.url:
            self.set_unpack_info("Source", self.url, unique=True)

    @synchronized(NZO_LOCK)
    def increase_bad_articles_counter(self, article_type):
        """ Record information about bad articles """
        if article_type not in self.nzo_info:
            self.nzo_info[article_type] = 0
        self.nzo_info[article_type] += 1
        self.bad_articles += 1

    def get_article(self, server: Server, servers: List[Server]) -> Optional[Article]:
        article = None
        nzf_remove_list = []

        # Did we go through all first-articles?
        if self.first_articles:
            for article_test in self.first_articles:
                article = article_test.get_article(server, servers)
                if article:
                    break

        # Move on to next ones
        if not article:
            for nzf in self.files:
                if nzf.deleted:
                    logging.debug("Skipping existing file %s", nzf.filename or nzf.subject)
                else:
                    # Don't try to get an article if server is in try_list of nzf
                    if not nzf.server_in_try_list(server):
                        if not nzf.import_finished:
                            # Only load NZF when it's a primary server
                            # or when it's a backup server without active primaries
                            if sabnzbd.Downloader.highest_server(server):
                                nzf.finish_import()
                                # Still not finished? Something went wrong...
                                if not nzf.import_finished and not self.is_gone():
                                    logging.error(T("Error importing %s"), nzf)
                                    nzf_remove_list.append(nzf)
                                    nzf.nzo.status = Status.PAUSED
                                    continue
                            else:
                                continue

                        article = nzf.get_article(server, servers)
                        if article:
                            break

        # Remove all files for which admin could not be read
        for nzf in nzf_remove_list:
            nzf.deleted = True
            self.files.remove(nzf)

        # If cleanup emptied the active files list, end this job
        if nzf_remove_list and not self.files:
            sabnzbd.NzbQueue.end_job(self)

        if not article:
            # No articles for this server, block for next time
            self.add_to_try_list(server)
        return article

    @synchronized(NZO_LOCK)
    def move_top_bulk(self, nzf_ids):
        self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            target = list(range(len(nzf_ids)))

            while 1:
                self.move_up_bulk(nzf_ids, cleanup=False)

                pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

                keys = list(pos_nzf_table)
                keys.sort()

                if target == keys:
                    break

    @synchronized(NZO_LOCK)
    def move_bottom_bulk(self, nzf_ids):
        self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            target = list(range(len(self.files) - len(nzf_ids), len(self.files)))

            while 1:
                self.move_down_bulk(nzf_ids, cleanup=False)

                pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

                keys = list(pos_nzf_table)
                keys.sort()

                if target == keys:
                    break

    @synchronized(NZO_LOCK)
    def move_up_bulk(self, nzf_ids, cleanup=True):
        if cleanup:
            self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

            while pos_nzf_table:
                pos = min(pos_nzf_table)
                nzf = pos_nzf_table.pop(pos)

                if pos > 0:
                    tmp_nzf = self.files[pos - 1]
                    if tmp_nzf.nzf_id not in nzf_ids:
                        self.files[pos - 1] = nzf
                        self.files[pos] = tmp_nzf

    @synchronized(NZO_LOCK)
    def move_down_bulk(self, nzf_ids, cleanup=True):
        if cleanup:
            self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

            while pos_nzf_table:
                pos = max(pos_nzf_table)
                nzf = pos_nzf_table.pop(pos)

                if pos < len(self.files) - 1:
                    tmp_nzf = self.files[pos + 1]
                    if tmp_nzf.nzf_id not in nzf_ids:
                        self.files[pos + 1] = nzf
                        self.files[pos] = tmp_nzf

    def verify_nzf_filename(self, nzf: NzbFile, yenc_filename: Optional[str] = None):
        """ Get filename from par2-info or from yenc """
        # Already done?
        if nzf.filename_checked:
            return

        # If writing already started, we can't rename anymore
        if nzf.filepath:
            return

        # If we have the md5, use it to rename
        if nzf.md5of16k and self.md5of16k:
            # Don't check again, even if no match
            nzf.filename_checked = True
            # Find the match and rename
            if nzf.md5of16k in self.md5of16k:
                new_filename = self.md5of16k[nzf.md5of16k]
                # Was it even new?
                if new_filename != nzf.filename:
                    logging.info("Detected filename based on par2: %s -> %s", nzf.filename, new_filename)
                    self.renamed_file(new_filename, nzf.filename)
                    nzf.filename = new_filename
                return

        # Fallback to yenc/nzb name (also when there is no partnum=1)
        # We also keep the NZB name in case it ends with ".par2" (usually correct)
        if (
            yenc_filename
            and yenc_filename != nzf.filename
            and not is_probably_obfuscated(yenc_filename)
            and not nzf.filename.endswith(".par2")
        ):
            logging.info("Detected filename from yenc: %s -> %s", nzf.filename, yenc_filename)
            self.renamed_file(yenc_filename, nzf.filename)
            nzf.filename = yenc_filename

    @synchronized(NZO_LOCK)
    def verify_all_filenames_and_resort(self):
        """Verify all filenames based on par2 info and then re-sort files.
        Locked so all files are verified at once without interuptions.
        """
        logging.info("Checking all filenames for %s", self.final_name)
        for nzf_verify in self.files:
            self.verify_nzf_filename(nzf_verify)
        logging.info("Re-sorting %s after getting filename information", self.final_name)
        self.sort_nzfs()

    @synchronized(NZO_LOCK)
    def renamed_file(self, name_set, old_name=None):
        """Save renames at various stages (Download/PP)
        to be used on Retry. Accepts strings and dicts.
        """
        if not old_name:
            # Add to dict
            self.renames.update(name_set)
        else:
            self.renames[name_set] = old_name

    # Determine if rating information (including site identifier so rating can be updated)
    # is present in metadata and if so store it
    @synchronized(NZO_LOCK)
    def update_rating(self):
        if cfg.rating_enable():
            try:

                def _get_first_meta(rating_type):
                    values = self.nzo_info.get("x-oznzb-rating-" + rating_type, None) or self.nzo_info.get(
                        "x-rating-" + rating_type, None
                    )
                    return values[0] if values and isinstance(values, list) else values

                rating_types = [
                    "url",
                    "host",
                    "video",
                    "videocnt",
                    "audio",
                    "audiocnt",
                    "voteup",
                    "votedown",
                    "spam",
                    "confirmed-spam",
                    "passworded",
                    "confirmed-passworded",
                ]
                fields = {}
                for k in rating_types:
                    fields[k] = _get_first_meta(k)
                sabnzbd.Rating.add_rating(_get_first_meta("id"), self.nzo_id, fields)
            except:
                pass

    @property
    def admin_path(self):
        """ Return the full path for my job-admin folder """
        return long_path(get_admin_path(self.work_name, self.futuretype))

    @property
    def download_path(self):
        """ Return the full path for the download folder """
        if self.futuretype:
            return ""
        else:
            return long_path(os.path.join(cfg.download_dir.get_path(), self.work_name))

    @property
    def group(self):
        if self.groups:
            return self.groups[0]
        else:
            return None

    @property
    def remaining(self):
        """ Return remaining bytes """
        return self.bytes - self.bytes_tried

    @synchronized(NZO_LOCK)
    def purge_data(self, delete_all_data=True):
        """ Remove (all) job data """
        logging.info(
            "[%s] Purging data for job %s (delete_all_data=%s)", caller_name(), self.final_name, delete_all_data
        )

        # Abort DirectUnpack and let it remove files
        self.abort_direct_unpacker()

        # Remove all cached files
        sabnzbd.ArticleCache.purge_articles(self.saved_articles)

        # Delete all, or just basic files
        if self.futuretype:
            # Remove temporary file left from URL-fetches
            sabnzbd.remove_data(self.nzo_id, self.admin_path)
        elif delete_all_data:
            remove_all(self.download_path, recursive=True)
        else:
            # We remove any saved articles and save the renames file
            remove_all(self.download_path, "SABnzbd_nz?_*", keep_folder=True)
            remove_all(self.download_path, "SABnzbd_article_*", keep_folder=True)
            sabnzbd.save_data(self.renames, RENAMES_FILE, self.admin_path, silent=True)

    def gather_info(self, full=False):
        queued_files = []
        if full:
            # extrapars can change during iteration
            with NZO_LOCK:
                for _set in self.extrapars:
                    for nzf in self.extrapars[_set]:
                        # Don't show files twice
                        if not nzf.completed and nzf not in self.files:
                            queued_files.append(nzf)

        return PNFO(
            self.repair,
            self.unpack,
            self.delete,
            self.script,
            self.nzo_id,
            self.final_name,
            self.labels,
            self.password,
            {},
            "",
            self.cat,
            self.url,
            self.remaining,
            self.bytes,
            self.avg_stamp,
            self.avg_date,
            self.finished_files if full else [],
            self.files if full else [],
            queued_files,
            self.status,
            self.priority,
            self.bytes_missing,
            self.direct_unpacker.get_formatted_stats() if self.direct_unpacker else 0,
        )

    def get_nzf_by_id(self, nzf_id: str) -> NzbFile:
        if nzf_id in self.files_table:
            return self.files_table[nzf_id]

    @synchronized(NZO_LOCK)
    def set_unpack_info(self, key: str, msg: str, setname: Optional[str] = None, unique: bool = False):
        """Builds a dictionary containing the stage name (key) and a message
        If unique is present, it will only have a single line message
        """
        # Add name of the set
        if setname:
            msg = "[%s] %s" % (setname, msg)

        # Unique messages allow only one line per stage(key)
        if not unique:
            if key not in self.unpack_info:
                self.unpack_info[key] = []
            self.unpack_info[key].append(msg)
        else:
            self.unpack_info[key] = [msg]

    def set_action_line(self, action=None, msg=None):
        if action and msg:
            self.action_line = "%s: %s" % (action, msg)
        else:
            self.action_line = ""
        # Make sure it's updated in the interface
        sabnzbd.history_updated()

    @property
    def repair_opts(self):
        return self.repair, self.unpack, self.delete

    @synchronized(NZO_LOCK)
    def save_to_disk(self):
        """ Save job's admin to disk """
        self.save_attribs()
        if self.nzo_id and not self.is_gone():
            sabnzbd.save_data(self, self.nzo_id, self.admin_path)

    def save_attribs(self):
        """ Save specific attributes for Retry """
        attribs = {}
        for attrib in NzoAttributeSaver:
            attribs[attrib] = getattr(self, attrib)
        logging.debug("Saving attributes %s for %s", attribs, self.final_name)
        sabnzbd.save_data(attribs, ATTRIB_FILE, self.admin_path, silent=True)

    def load_attribs(self) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """ Load saved attributes and return them to be parsed """
        attribs = sabnzbd.load_data(ATTRIB_FILE, self.admin_path, remove=False)
        logging.debug("Loaded attributes %s for %s", attribs, self.final_name)

        # If attributes file somehow does not exists
        if not attribs:
            return None, None, None

        # Only a subset we want to apply directly to the NZO
        for attrib in ("final_name", "priority", "password", "url"):
            # Only set if it is present and has a value
            if attribs.get(attrib):
                setattr(self, attrib, attribs[attrib])

        # Rest is to be used directly in the NZO-init flow
        return attribs["cat"], attribs["pp"], attribs["script"]

    @synchronized(NZO_LOCK)
    def build_pos_nzf_table(self, nzf_ids):
        pos_nzf_table = {}
        for nzf_id in nzf_ids:
            if nzf_id in self.files_table:
                nzf = self.files_table[nzf_id]
                pos = self.files.index(nzf)
                pos_nzf_table[pos] = nzf

        return pos_nzf_table

    @synchronized(NZO_LOCK)
    def cleanup_nzf_ids(self, nzf_ids):
        for nzf_id in nzf_ids[:]:
            if nzf_id in self.files_table:
                if self.files_table[nzf_id] not in self.files:
                    nzf_ids.remove(nzf_id)
            else:
                nzf_ids.remove(nzf_id)

    def has_duplicates(self):
        """Return (res, series)
        where "res" is True when this is a duplicate
        where "series" is True when this is an episode
        """

        no_dupes = cfg.no_dupes()
        no_series_dupes = cfg.no_series_dupes()
        series_propercheck = cfg.series_propercheck()

        # abort logic if dupe check is off for both nzb+series
        if not no_dupes and not no_series_dupes:
            return False, False

        series = False
        res = False
        history_db = HistoryDB()

        # dupe check off nzb contents
        if no_dupes:
            res = history_db.have_name_or_md5sum(self.final_name, self.md5sum)
            logging.debug(
                "Dupe checking NZB in history: filename=%s, md5sum=%s, result=%s", self.filename, self.md5sum, res
            )
            if not res and cfg.backup_for_duplicates():
                res = sabnzbd.backup_exists(self.filename)
                logging.debug("Dupe checking NZB against backup: filename=%s, result=%s", self.filename, res)
        # dupe check off nzb filename
        if not res and no_series_dupes:
            series, season, episode, misc = sabnzbd.newsunpack.analyse_show(self.final_name)
            if RE_PROPER.match(misc) and series_propercheck:
                logging.debug("Dupe checking series+season+ep in history aborted due to PROPER/REAL/REPACK found")
            else:
                res = history_db.have_episode(series, season, episode)
                logging.debug(
                    "Dupe checking series+season+ep in history: series=%s, season=%s, episode=%s, result=%s",
                    series,
                    season,
                    episode,
                    res,
                )

        history_db.close()
        return res, series

    def is_gone(self):
        """ Is this job still going somehow? """
        return self.status in (Status.COMPLETED, Status.DELETED, Status.FAILED)

    def __getstate__(self):
        """ Save to pickle file, selecting attributes """
        dict_ = {}
        for item in NzbObjectSaver:
            dict_[item] = getattr(self, item)
        dict_["try_list"] = super().__getstate__()
        return dict_

    def __setstate__(self, dict_):
        """ Load from pickle file, selecting attributes """
        for item in NzbObjectSaver:
            try:
                setattr(self, item, dict_[item])
            except KeyError:
                # Handle new attributes
                setattr(self, item, None)
        super().__setstate__(dict_.get("try_list", []))

        # Set non-transferable values
        self.pp_active = False
        self.avg_stamp = time.mktime(self.avg_date.timetuple())
        self.url_wait = None
        self.url_tries = 0
        self.to_be_removed = False
        self.direct_unpacker = None
        if self.meta is None:
            self.meta = {}
        if self.servercount is None:
            self.servercount = {}
        if self.md5of16k is None:
            self.md5of16k = {}
        if self.renames is None:
            self.renames = {}
        if self.bad_articles is None:
            self.bad_articles = 0
            self.first_articles_count = 0
        if self.bytes_missing is None:
            self.bytes_missing = 0
        if self.bytes_tried is None:
            # Fill with old info
            self.bytes_tried = 0
            for nzf in self.finished_files:
                # Emulate behavior of 1.0.x
                self.bytes_tried += nzf.bytes
            for nzf in self.files:
                self.bytes_tried += nzf.bytes - nzf.bytes_left
        if self.bytes_par2 is None:
            self.bytes_par2 = 0
            for nzf in self.files + self.finished_files:
                if sabnzbd.par2file.is_parfile(nzf.filename):
                    self.bytes_par2 += nzf.bytes

    def __repr__(self):
        return "<NzbObject: filename=%s, bytes=%s, nzo_id=%s>" % (self.filename, self.bytes, self.nzo_id)


def nzf_cmp_name(nzf1: NzbFile, nzf2: NzbFile):
    # The comparison will sort .par2 files to the top of the queue followed by .rar files,
    # they will then be sorted by name.
    nzf1_name = nzf1.filename.lower()
    nzf2_name = nzf2.filename.lower()

    # Determine vol-pars
    is_par1 = ".vol" in nzf1_name and ".par2" in nzf1_name
    is_par2 = ".vol" in nzf2_name and ".par2" in nzf2_name

    # mini-par2 in front
    if not is_par1 and nzf1_name.endswith(".par2"):
        return -1
    if not is_par2 and nzf2_name.endswith(".par2"):
        return 1

    # vol-pars go to the back
    if is_par1 and not is_par2:
        return 1
    if is_par2 and not is_par1:
        return -1

    # Prioritize .rar files above any other type of file (other than vol-par)
    m1 = RE_RAR.search(nzf1_name)
    m2 = RE_RAR.search(nzf2_name)
    if m1 and not (is_par2 or m2):
        return -1
    elif m2 and not (is_par1 or m1):
        return 1
    # Force .rar to come before 'r00'
    if m1 and m1.group(1) == ".rar":
        nzf1_name = nzf1_name.replace(".rar", ".r//")
    if m2 and m2.group(1) == ".rar":
        nzf2_name = nzf2_name.replace(".rar", ".r//")
    return cmp(nzf1_name, nzf2_name)


def create_work_name(name: str) -> str:
    """ Remove ".nzb" and ".par(2)" and sanitize, skip URL's """
    if name.find("://") < 0:
        # In case it was one of these, there might be more
        # Need to remove any invalid characters before starting
        name_base, ext = os.path.splitext(sanitize_foldername(name))
        while ext.lower() in (".nzb", ".par", ".par2"):
            name = name_base
            name_base, ext = os.path.splitext(name)
        # And make sure we remove invalid characters again
        return sanitize_foldername(name)
    else:
        return name.strip()


def scan_password(name: str) -> Tuple[str, Optional[str]]:
    """ Get password (if any) from the title """
    if "http://" in name or "https://" in name:
        return name, None

    braces = name[1:].find("{{")
    if braces < 0:
        braces = len(name)
    else:
        braces += 1
    slash = name.find("/")

    # Look for name/password, but make sure that '/' comes before any {{
    if 0 < slash < braces and "password=" not in name:
        # Is it maybe in 'name / password' notation?
        if slash == name.find(" / ") + 1 and name[: slash - 1].strip(". "):
            # Remove the extra space after name and before password
            return name[: slash - 1].strip(". "), name[slash + 2 :]
        if name[:slash].strip(". "):
            return name[:slash].strip(". "), name[slash + 1 :]

    # Look for "name password=password"
    pw = name.find("password=")
    if pw > 0 and name[:pw].strip(". "):
        return name[:pw].strip(". "), name[pw + 9 :]

    # Look for name{{password}}
    if braces < len(name):
        closing_braces = name.rfind("}}")
        if closing_braces > braces and name[:braces].strip(". "):
            return name[:braces].strip(". "), name[braces + 2 : closing_braces]

    # Look again for name/password
    if slash > 0 and name[:slash].strip(". "):
        return name[:slash].strip(". "), name[slash + 1 :]

    # No password found
    return name, None


def name_extractor(subject: str) -> str:
    """ Try to extract a file name from a subject line, return `subject` if in doubt """
    result = subject
    # Filename nicely wrapped in quotes
    for name in re.findall(RE_SUBJECT_FILENAME_QUOTES, subject):
        name = name.strip(' "')
        if name:
            result = name

    # Found nothing? Try a basic filename-like search
    if result == subject:
        for name in re.findall(RE_SUBJECT_BASIC_FILENAME, subject):
            name = name.strip()
            if name:
                result = name

    # Return the subject
    return result


def matcher(pattern, txt):
    """ Return True if `pattern` is sufficiently equal to `txt` """
    if txt.endswith(pattern):
        txt = txt[: txt.rfind(pattern)].strip()
        return (not txt) or txt.endswith('"')
    else:
        return False
