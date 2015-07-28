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
sabnzbd.nzbstuff - misc
"""
# Standard Library
import os
import time
import re
import logging
import datetime
import xml.sax
import xml.sax.handler
import xml.sax.xmlreader
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
try:
    import hashlib
    new_md5 = hashlib.md5
except:
    import md5
    new_md5 = md5.new

# SABnzbd modules
import sabnzbd
from sabnzbd.constants import sample_match, GIGI, ATTRIB_FILE, JOB_ADMIN, \
     DEFAULT_PRIORITY, LOW_PRIORITY, NORMAL_PRIORITY, \
     HIGH_PRIORITY, PAUSED_PRIORITY, TOP_PRIORITY, DUP_PRIORITY, REPAIR_PRIORITY, \
     RENAMES_FILE, Status
from sabnzbd.misc import to_units, cat_to_opts, cat_convert, sanitize_foldername, \
     get_unique_path, get_admin_path, remove_all, format_source_url, \
     sanitize_filename, globber_full, sanitize_foldername, int_conv, \
     set_permissions, format_time_string, long_path, trim_win_path, \
     fix_unix_encoding
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.trylist import TryList
from sabnzbd.encoding import unicoder, platform_encode, name_fixer
from sabnzbd.database import get_history_handle
from sabnzbd.rating import Rating

__all__ = ['Article', 'NzbFile', 'NzbObject']

# Name potterns
RE_NORMAL  = re.compile(r"(.+)(\.nzb)", re.I)
SUBJECT_FN_MATCHER = re.compile(r'"([^"]*)"')
RE_SAMPLE = re.compile(sample_match, re.I)
PROBABLY_PAR2_RE = re.compile(r'(.*)\.vol(\d*)\+(\d*)\.par2', re.I)
REJECT_PAR2_RE = re.compile(r'\.par2\.\d+', re.I) # Reject duplicate par2 files
RE_NORMAL_NAME = re.compile(r'\.\w{2,5}$') # Test reasonably sized extension at the end

################################################################################
# Article                                                                      #
################################################################################
ArticleSaver = (
    'article', 'art_id' , 'bytes', 'partnum', 'nzf'
)

class Article(TryList):
    """ Representation of one article
    """
    def __init__ (self, article, bytes, partnum, nzf):
        TryList.__init__(self)

        self.fetcher = None
        self.fetcher_priority = 0
        self.allow_fill_server = False

        self.article = article
        self.art_id = None
        self.bytes = bytes
        self.partnum = partnum
        self.tries = 0 # Try count
        self.nzf = nzf

    def get_article(self, server, servers):
        """ Return article when appropriate for specified server """
        log = sabnzbd.LOG_ALL
        if not self.fetcher and not self.server_in_try_list(server):
            if log: logging.debug('Article %s | Server: %s | in second if', self.article, server.host)
            # Is the current selected server of the same priority as this article?
            if log: logging.debug('Article %s | Server: %s | Article priority: %s', self.article, server.host, self.fetcher_priority)
            if log: logging.debug('Article %s | Server: %s | Server priority: %s', self.article, server.host, server.priority)
            if server.priority == self.fetcher_priority:
                if log: logging.debug('Article %s | Server: %s | same priority, use it', self.article, server.host)
                self.fetcher = server
                self.tries += 1
                if log: logging.debug('Article %s | Server: %s | Article-try: %s', self.article, server.host, self.tries)
                return self
            else:
                if log: logging.debug('Article %s | Server: %s | not the same priorty', self.article, server.host)
                # No, so is it a lower priority?
                if (server.priority > self.fetcher_priority):
                    if log: logging.debug('Article %s | Server: %s | lower priority', self.article, server.host)
                    # Is there an available server that is a higher priority?
                    found_priority = 1000
                    #for server_check in config.get_servers():
                    for server_check in servers:
                        if log: logging.debug('Article %s | Server: %s | checking', self.article, server.host)
                        #if (server_check.priority() < found_priority and server_check.priority() < server.priority and not self.server_in_try_list(server_check)):
                        if (server_check.priority < found_priority):
                            if (server_check.priority < server.priority):
                                if (not self.server_in_try_list(server_check)) and self.server_allowed(server_check):
                                    if log: logging.debug('Article %s | Server: %s | setting found priority to %s', self.article, server.host, server_check.priority)
                                    found_priority = server_check.priority
                    if found_priority == 1000:
                        # If no higher priority servers, use this server
                        self.fetcher_priority = server.priority
                        self.fetcher = server
                        self.tries += 1
                        if log: logging.debug('Article %s | Server: %s | Article-try: %s', self.article, server.host, self.tries)
                        return self
                    else:
                        # There is a higher priorty server, so set article priority
                        if log: logging.debug('Article %s | Server: %s | setting self priority', self.article, server.host)
                        self.fetcher_priority = found_priority
        if log: logging.debug('Article %s | Server: %s | Returning None', self.article, server.host)
        return None

    def get_art_id(self):
        """ Return unique article storage name, create if needed """
        if not self.art_id:
            self.art_id = sabnzbd.get_new_id("article", self.nzf.nzo.workpath)
        return self.art_id

    def server_allowed(self, server):
        """ Return true if this server is allowed to download this article. """
        return self.nzf.nzo.server_allowed(server)

    def __getstate__(self):
        """ Save to pickle file, selecting attributes """
        dict_ = {}
        for item in ArticleSaver:
            dict_[item] = self.__dict__[item]
        return dict_

    def __setstate__(self, dict_):
        """ Load from pickle file, selecting attributes """
        for item in ArticleSaver:
            try:
                self.__dict__[item] = dict_[item]
            except KeyError:
                # Handle new attributes
                self.__dict__[item] = None
        TryList.__init__(self)
        self.fetcher = None
        self.fetcher_priority = 0
        self.allow_fill_server = False
        self.tries = 0

    def __repr__(self):
        return "<Article: article=%s, bytes=%s, partnum=%s, art_id=%s>" % \
               (self.article, self.bytes, self.partnum, self.art_id)


################################################################################
# NzbFile                                                                      #
################################################################################
NzbFileSaver = (
    'date', 'subject', 'filename', 'type', 'is_par2', 'vol', 'blocks', 'setname',
    'extrapars', 'initial_article', 'articles', 'decodetable', 'bytes', 'bytes_left',
    'article_count', 'nzo', 'nzf_id', 'deleted', 'valid', 'import_finished',
    'md5sum', 'valid', 'completed'
)


class NzbFile(TryList):
    """ Representation of one file consisting of multiple articles
    """
    def __init__(self, date, subject, article_db, bytes, nzo):
        """ Setup object """
        TryList.__init__(self)

        self.date = date
        self.subject = subject
        self.filename = None
        self.type = None

        self.filename = name_extractor(subject)

        self.is_par2 = False
        self.vol = None
        self.blocks = None
        self.setname = None
        self.extrapars = None

        self.initial_article = None

        self.articles = []
        self.decodetable = {}

        self.bytes = bytes
        self.bytes_left = bytes
        self.article_count = 0

        self.nzo = nzo
        self.nzf_id = sabnzbd.get_new_id("nzf", nzo.workpath)
        self.deleted = False
        self.completed = False

        self.valid = False
        self.import_finished = False

        self.md5sum = None

        self.valid = bool(article_db)

        if self.valid and self.nzf_id:
            sabnzbd.save_data(article_db, self.nzf_id, nzo.workpath)

    def finish_import(self):
        """ Load the article objects from disk """
        logging.debug("Finishing import on %s", self.subject)

        article_db = sabnzbd.load_data(self.nzf_id, self.nzo.workpath, remove=False)
        if article_db:
            for partnum in article_db:
                art_id = article_db[partnum][0]
                bytes = article_db[partnum][1]

                article = Article(art_id, bytes, partnum, self)

                self.articles.append(article)
                self.decodetable[partnum] = article

            # Look for article with lowest number
            self.initial_article = self.decodetable[self.lowest_partnum]
            self.import_finished = True

    def remove_article(self, article, found):
        """ Handle completed article, possibly end of file """
        if article in self.articles:
            self.articles.remove(article)
            if found:
                self.bytes_left -= article.bytes

        reset = False
        if article.partnum == self.lowest_partnum and self.articles:
            # Issue reset
            self.initial_article = None
            self.reset_try_list()
            reset = True

        done = True
        if self.articles:
            done = False

        return (done, reset)

    def set_par2(self, setname, vol, blocks):
        """ Designate this this file as a par2 file """
        self.is_par2 = True
        self.setname = setname
        self.vol = vol
        self.blocks = int(blocks)

    def get_article(self, server, servers):
        """ Get next article to be downloaded """
        if self.initial_article:
            article = self.initial_article.get_article(server, servers)
            if article:
                return article

        else:
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

    @property
    def completed(self):
        """ Is this file completed? """
        return self.import_finished and not bool(self.articles)

    @property
    def lowest_partnum(self):
        """ Get lowest article number of this file """
        return min(self.decodetable)

    def remove_admin(self):
        """ Remove article database from disk (sabnzbd_nzf_<id>)"""
        try:
            os.remove(os.path.join(self.nzo.workpath, self.nzf_id))
        except:
            pass

    def __getstate__(self):
        """ Save to pickle file, selecting attributes """
        dict_ = {}
        for item in NzbFileSaver:
            dict_[item] = self.__dict__[item]
        return dict_

    def __setstate__(self, dict_):
        """ Load from pickle file, selecting attributes """
        for item in NzbFileSaver:
            try:
                self.__dict__[item] = dict_[item]
            except KeyError:
                # Handle new attributes
                self.__dict__[item] = None
        TryList.__init__(self)

    def __repr__(self):
        return "<NzbFile: filename=%s, type=%s>" % (self.filename, self.type)


################################################################################
# NzbParser                                                                    #
################################################################################
class NzbParser(xml.sax.handler.ContentHandler):
    """ Forgiving parser for NZB's """
    def __init__ (self, nzo, remove_samples=False):
        self.nzo = nzo
        assert isinstance(self.nzo, NzbObject)
        self.in_nzb = False
        self.in_file = False
        self.in_groups = False
        self.in_group = False
        self.in_segments = False
        self.in_segment = False
        self.in_head = False
        self.in_meta = False
        self.meta_type = ''
        self.meta_types = {}
        self.meta_content = []
        self.filename = ''
        self.avg_age = 0
        self.valids = 0
        self.skipped_files = 0
        self.nzf_list = []
        self.groups = []
        self.md5 = new_md5()
        self.filter = remove_samples
        self.now = time.time()

    def startDocument(self):
        pass

    def startElement(self, name, attrs):
        if name == 'segment' and self.in_nzb and self.in_file and self.in_segments:
            try:
                self.seg_bytes = int(attrs.get('bytes'))
                self.article_nr = int(attrs.get('number'))
            except ValueError:
                return
            self.article_id = []
            self.file_bytes += self.seg_bytes
            self.in_segment = True

        elif name == 'segments' and self.in_nzb and self.in_file:
            self.in_segments = True

        elif name == 'file' and self.in_nzb:
            subject = attrs.get('subject', '').strip()
            self.filename = subject

            if self.filter and RE_SAMPLE.search(subject):
                logging.info('Skipping sample file %s', subject)
            else:
                self.in_file = True
                self.fileSubject = subject
                try:
                    self.file_date = int(attrs.get('date'))
                except:
                    # NZB has non-standard timestamp, assume now
                    self.file_date = self.now
                self.article_db = {}
                self.file_bytes = 0

        elif name == 'group' and self.in_nzb and self.in_file and self.in_groups:
            self.in_group = True
            self.group_name = []

        elif name == 'groups' and self.in_nzb and self.in_file:
            self.in_groups = True

        elif name == 'head' and self.in_nzb:
            self.in_head = True

        elif name == 'meta' and self.in_nzb and self.in_head:
            self.in_meta = True
            meta_type = attrs.get('type')
            if meta_type:
                self.meta_type = meta_type.lower()
            self.meta_content = []

        elif name == 'nzb':
            self.in_nzb = True

    def characters (self, content):
        if self.in_group:
            self.group_name.append(content)
        elif self.in_segment:
            self.article_id.append(content)
        elif self.in_meta:
            self.meta_content.append(content)

    def endElement(self, name):
        if name == 'group' and self.in_group:
            group = str(''.join(self.group_name))
            if group not in self.groups:
                self.groups.append(group)
            self.in_group = False

        elif name == 'segment' and self.in_segment:
            partnum = self.article_nr
            segm = str(''.join(self.article_id))
            self.md5.update(segm)
            if partnum in self.article_db:
                if segm != self.article_db[partnum][0]:
                    msg = 'Duplicate part %s, but different ID-s (%s // %s)' % (partnum, self.article_db[partnum][0], segm)
                    logging.info(msg)
                    self.nzo.inc_log('dup_art_log', msg)
                else:
                    logging.info("Skipping duplicate article (%s)", segm)
            else:
                self.article_db[partnum] = (segm, self.seg_bytes)
            self.in_segment = False

        elif name == 'groups' and self.in_groups:
            self.in_groups = False

        elif name == 'segments' and self.in_segments:
            self.in_segments = False

        elif name == 'file' and self.in_file:
            # Create an NZF
            self.in_file = False
            if not self.article_db:
                logging.warning(T('File %s is empty, skipping'), self.filename)
                return
            try:
                tm = datetime.datetime.fromtimestamp(self.file_date)
            except:
                tm = datetime.datetime.fromtimestamp(self.now)
                self.file_date = self.now
            nzf = NzbFile(tm, self.filename, self.article_db, self.file_bytes, self.nzo)
            if nzf.valid and nzf.nzf_id:
                logging.info('File %s added to queue', self.filename)
                self.nzo.files.append(nzf)
                self.nzo.files_table[nzf.nzf_id] = nzf
                self.nzo.bytes += nzf.bytes
                self.avg_age += self.file_date
                self.valids += 1
                self.nzf_list.append(nzf)
            else:
                logging.info('Error importing %s, skipping', self.filename)
                if nzf.nzf_id:
                    sabnzbd.remove_data(nzf.nzf_id, self.nzo.workpath)
                self.skipped_files += 1

        elif name == 'head':
            self.in_head = False

        elif name == 'meta':
            self.in_meta = False
            if self.meta_type:
                if self.meta_type not in self.meta_types:
                    self.meta_types[self.meta_type] = []
                self.meta_types[self.meta_type].append(''.join(self.meta_content))

        elif name == 'nzb':
            self.in_nzb = False

    def endDocument(self):
        """ End of the file """
        self.nzo.groups = self.groups
        self.nzo.meta = self.meta_types
        logging.debug('META-DATA = %s', self.nzo.meta)
        files = max(1, self.valids)
        self.nzo.avg_stamp = self.avg_age / files
        self.nzo.avg_date = datetime.datetime.fromtimestamp(self.avg_age / files)
        self.nzo.md5sum = self.md5.hexdigest()
        if self.skipped_files:
            logging.warning(T('Failed to import %s files from %s'),
                            self.skipped_files, self.nzo.filename)


################################################################################
# NzbObject                                                                    #
################################################################################
NzbObjectSaver = (
    'filename', 'work_name', 'final_name', 'created', 'bytes', 'bytes_downloaded', 'repair',
    'unpack', 'delete', 'script', 'cat', 'url', 'groups', 'avg_date', 'dirprefix',
    'partable', 'extrapars', 'md5packs', 'files', 'files_table', 'finished_files', 'status',
    'avg_bps_freq', 'avg_bps_total', 'priority', 'dupe_table', 'saved_articles', 'nzo_id',
    'futuretype', 'deleted', 'parsed', 'action_line', 'unpack_info', 'fail_msg', 'nzo_info',
    'custom_name', 'password', 'next_save', 'save_timeout', 'encrypted',
    'duplicate', 'oversized', 'create_group_folder', 'precheck', 'incomplete', 'reuse', 'meta',
    'md5sum', 'servercount', 'unwanted_ext', 'rating_filtered'
)

class NzbObject(TryList):
    def __init__(self, filename, pp, script, nzb = None,
                 futuretype = False, cat = None, url=None,
                 priority=NORMAL_PRIORITY, nzbname=None, status="Queued", nzo_info=None,
                 reuse=False, dup_check=True):
        TryList.__init__(self)

        filename = platform_encode(filename)
        nzbname = platform_encode(nzbname)

        if pp is None:
            r = u = d = None
        else:
            r, u, d = sabnzbd.pp_to_opts(pp)

        self.filename = filename    # Original filename
        if nzbname and nzb:
            work_name = nzbname         # Use nzbname if set and only for non-future slot
        else:
            work_name = filename

        # If non-future: create safe folder name stripped from ".nzb" and junk
        if nzb and work_name and work_name.lower().endswith('.nzb'):
            dname, ext = os.path.splitext(work_name) # Used for folder name for final unpack
            if ext.lower() == '.nzb':
                work_name = dname
        work_name, password = scan_password(work_name)
        if not work_name:
            work_name = filename
        if nzb and work_name and not reuse:
            work_name = sanitize_foldername(work_name)
        if not work_name:
            # In case only /password was entered for nzbname
            work_name = filename

        self.work_name = work_name
        self.final_name = work_name

        self.meta = {}
        self.servercount = {}       # Dict to keep bytes per server
        self.created = False        # dirprefixes + work_name created
        self.bytes = 0              # Original bytesize
        self.bytes_downloaded = 0   # Downloaded byte
        self.repair = r             # True if we want to repair this set
        self.unpack = u             # True if we want to unpack this set
        self.delete = d             # True if we want to delete this set
        self.script = script        # External script for this set
        self.cat = cat              # Indexer category
        if url:
            self.url = str(url)     # Source URL
        else:
            self.url = filename
        self.groups = []
        self.avg_date = datetime.datetime.fromtimestamp(0.0)
        self.avg_stamp = 0.0        # Avg age in seconds (calculated from avg_age)
        self.dirprefix = []

        self.partable = {}          # Holds one parfile-name for each set
        self.extrapars = {}         # Holds the extra parfile names for all sets
        self.md5packs = {}            # Holds the md5pack for each set

        self.files = []             # List of all NZFs
        self.files_table = {}       # Dictionary of NZFs indexed using NZF_ID

        self.finished_files = []    # List of al finished NZFs

        #the current status of the nzo eg:
        #Queued, Downloading, Repairing, Unpacking, Failed, Complete
        self.status = status
        self.avg_bps_freq = 0
        self.avg_bps_total = 0
        try:
            priority = int(priority)
        except:
            priority = DEFAULT_PRIORITY
        self.priority = priority

        self.dupe_table = {}

        self.saved_articles = []

        self.nzo_id = None

        self.futuretype = futuretype
        self.deleted = False
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
        self.action_line = ''
        # Store the results from various filejoin/par2/unrar/unzip stages
        self.unpack_info = {}
        # Stores one line containing the last failure
        self.fail_msg = ''
        # Stores various info about the nzo to be
        if nzo_info:
            self.nzo_info = nzo_info
        else:
            self.nzo_info = {}

        # Temporary store for custom foldername - needs to be stored because of url fetching
        self.custom_name = nzbname

        self.password = password
        self.next_save = None
        self.save_timeout = None
        self.encrypted = 0
        self.wait = None
        self.pp_active = False  # Signals active post-processing (not saved)
        self.md5sum = None

        self.create_group_folder = cfg.create_group_folders()

        # Remove trailing .nzb
        self.work_name = split_filename(self.work_name)

        if nzb is None:
            # This is a slot for a future NZB, ready now
            return

        # Apply conversion option to final folder
        if cfg.replace_dots() and ' ' not in self.final_name:
            logging.info('Replacing dots with spaces in %s', self.final_name)
            self.final_name = self.final_name.replace('.',' ')
        if cfg.replace_spaces():
            logging.info('Replacing spaces with underscores in %s', self.final_name)
            self.final_name = self.final_name.replace(' ','_')

        # Determine "incomplete" folder
        wdir = long_path(os.path.join(cfg.download_dir.get_path(), self.work_name))
        adir = os.path.join(wdir, JOB_ADMIN)

        if reuse:
            remove_all(adir, 'SABnzbd_nz?_*')
            remove_all(adir, 'SABnzbd_article_*')
        else:
            wdir = trim_win_path(wdir)
            wdir = get_unique_path(wdir, create_dir=True)
            set_permissions(wdir)
            adir = os.path.join(wdir, JOB_ADMIN)

        if not os.path.exists(adir):
            os.mkdir(adir)
        dummy, self.work_name = os.path.split(wdir)
        self.created = True

        # Must create a lower level XML parser because we must
        # disable the reading of the DTD file from an external website
        # by setting "feature_external_ges" to 0.

        if nzb and '<nzb' in nzb:
            if 'A&A)' in nzb:
                # Fix needed to compensate for some dumb NZB posters
                nzb = nzb.replace('A&A)', 'A&amp;A)')
            handler = NzbParser(self, cfg.ignore_samples() == 2 and not reuse)
            parser = xml.sax.make_parser()
            parser.setFeature(xml.sax.handler.feature_external_ges, 0)
            parser.setContentHandler(handler)
            parser.setErrorHandler(xml.sax.handler.ErrorHandler())
            inpsrc = xml.sax.xmlreader.InputSource()
            inpsrc.setByteStream(StringIO(nzb))
            try:
                parser.parse(inpsrc)
            except xml.sax.SAXParseException, err:
                self.incomplete = True
                if '</nzb>' not in nzb:
                    logging.warning(T('Incomplete NZB file %s'), filename)
                else:
                    logging.warning(T('Invalid NZB file %s, skipping (reason=%s, line=%s)'),
                                    filename, err.getMessage(), err.getLineNumber())
            except Exception, err:
                self.incomplete = True
                logging.warning(T('Invalid NZB file %s, skipping (reason=%s, line=%s)'), filename, err, 0)

            if self.incomplete:
                if cfg.allow_incomplete_nzb():
                    self.pause()
                else:
                    self.purge_data()
                    raise ValueError

            sabnzbd.backup_nzb(filename, nzb)
            sabnzbd.save_compressed(adir, filename, nzb)

        # Check against identical checksum or series/season/episode
        if (not reuse) and nzb and dup_check and priority != REPAIR_PRIORITY:
            duplicate = self.has_duplicates()
        else:
            duplicate = 0

        if not self.files and not reuse:
            self.purge_data(keep_basic=False)
            if cfg.warn_empty_nzb():
                mylog = logging.warning
            else:
                mylog = logging.info
            if self.url:
                mylog(T('Empty NZB file %s') + ' [%s]', filename, self.url)
            else:
                mylog(T('Empty NZB file %s'), filename)
            raise ValueError

        if cat is None:
            for metacat in self.meta.get('category', ()):
                metacat = cat_convert(metacat)
                if metacat:
                    cat = metacat
                    break

        if cat is None:
            for grp in self.groups:
                cat = cat_convert(grp)
                if cat:
                    break

        if cfg.create_group_folders():
            self.dirprefix.append(self.group)

        # Pickup backed-up attributes when re-using
        if reuse:
            cat, pp, script, priority, name, self.url = get_attrib_file(self.workpath, 6)
            cat = unicoder(cat)
            script = unicoder(script)
            if name:
                self.set_final_name_pw(unicoder(name))

        # Determine category and find pp/script values
        self.cat, pp_tmp, self.script, self.priority = cat_to_opts(cat, pp, script, priority)
        self.repair, self.unpack, self.delete = sabnzbd.pp_to_opts(pp_tmp)

        # Run user pre-queue script if needed
        if not reuse:
            accept, name, pp, cat, script, priority, group = \
                sabnzbd.proxy_pre_queue(self.final_name_pw_clean, pp, cat, script,
                                        priority, self.bytes, self.groups)
            accept = int_conv(accept)
            try:
                pp = int(pp)
            except:
                pp = None
            try:
                priority = int(priority)
            except:
                priority = None
            if accept < 1:
                self.purge_data()
                raise TypeError
            if name:
                self.set_final_name_pw(name)
            if group:
                self.groups = [str(group)]

            # Re-evaluate results from pre-queue script
            self.cat, pp, self.script, self.priority = cat_to_opts(cat, pp, script, priority)
            self.repair, self.unpack, self.delete = sabnzbd.pp_to_opts(pp)
        else:
            accept = 1


        # Pause job when above size limit
        limit = cfg.size_limit.get_int()
        if not reuse and abs(limit) > 0.5 and self.bytes > limit:
            logging.info('Job too large, forcing low prio and paused (%s)', self.work_name)
            self.pause()
            self.oversized = True
            self.priority = LOW_PRIORITY

        if duplicate and cfg.no_dupes() == 1:
            if cfg.warn_dupl_jobs(): logging.warning(T('Ignoring duplicate NZB "%s"'), filename)
            self.purge_data(keep_basic=False)
            raise TypeError

        if duplicate or self.priority == DUP_PRIORITY:
            if cfg.warn_dupl_jobs(): logging.warning(T('Pausing duplicate NZB "%s"'), filename)
            self.duplicate = True
            self.pause()
            self.priority = NORMAL_PRIORITY

        if self.priority == PAUSED_PRIORITY:
            self.pause()
            self.priority = NORMAL_PRIORITY

        if reuse:
            self.check_existing_files(wdir)

        if cfg.auto_sort():
            self.files.sort(cmp=nzf_cmp_date)
        else:
            self.files.sort(cmp=nzf_cmp_name)

        # In the hunt for Unwanted Extensions:
        # The file with the unwanted extension often is in the first or the last rar file
        # So put the last rar immediatly after the first rar file so that it gets detected early
        if cfg.unwanted_extensions() and not cfg.auto_sort():
            # ... only useful if there are unwanted extensions defined and there is no sorting on date
            logging.debug('Unwanted Extension: putting last rar after first rar')
            nzfposcounter = firstrarpos = lastrarpos = 0
            for nzf in self.files:
                nzfposcounter += 1
                if '.rar' in str(nzf):
                    # a NZF found with '.rar' in the name
                    if firstrarpos == 0:
                        # this is the first .rar found, so remember this position
                        firstrarpos = nzfposcounter
                    lastrarpos = nzfposcounter
                    lastrarnzf = nzf    # The NZF itself

            if firstrarpos != lastrarpos:
                # at least two different .rar's found
                logging.debug('Unwanted Extension: First rar at %s, Last rar at %s',firstrarpos, lastrarpos)
                logging.debug('Unwanted Extension: Last rar is %s', str(lastrarnzf))
                try:
                    self.files.remove(lastrarnzf)        # first remove. NB: remove() does searches for lastrarnzf
                    self.files.insert(firstrarpos,lastrarnzf)    # ... and only then add after position firstrarpos
                except:
                    logging.debug('The lastrar swap did not go well')

        # Copy meta fields to nzo_info, if not already set
        for kw in self.meta:
            if not self.nzo_info.get(kw):
                self.nzo_info[kw] = self.meta[kw][0]

        # Set nzo save-delay to 6 sec per GB with a max of 5 min
        self.save_timeout = min(6.0 * float(self.bytes) / GIGI, 300.0)


    def check_for_dupe(self, nzf):
        filename = nzf.filename

        dupe = False

        if filename in self.dupe_table:
            old_nzf = self.dupe_table[filename]
            if nzf.article_count <= old_nzf.article_count:
                dupe = True

        if not dupe:
            self.dupe_table[filename] = nzf

        return dupe

    def update_avg_kbs(self, bps):
        if bps:
            self.avg_bps_total += bps / 1024
            self.avg_bps_freq += 1

    def remove_nzf(self, nzf):
        if nzf in self.files:
            self.files.remove(nzf)
            self.finished_files.append(nzf)
            nzf.import_finished = True
            nzf.deleted = True
        return not bool(self.files)

    def reset_all_try_lists(self):
        for nzf in self.files:
            nzf.reset_all_try_lists()
        self.reset_try_list()

    def postpone_pars(self, nzf, parset):
        """ Move all vol-par files matching 'parset' to the extrapars table
        """
        postpone = cfg.quick_check() or not cfg.enable_all_par()
        self.partable[parset] = nzf
        self.extrapars[parset] = []
        nzf.extrapars = self.extrapars[parset]
        lparset = parset.lower()
        for xnzf in self.files[:]:
            name = xnzf.filename or platform_encode(xnzf.subject)
            # Move only when not current NZF and filename was extractable from subject
            if name and nzf is not xnzf:
                head, vol, block = analyse_par2(name)
                if head and matcher(lparset, head.lower()):
                    xnzf.set_par2(parset, vol, block)
                    self.extrapars[parset].append(xnzf)
                    if postpone and not self.precheck:
                        self.files.remove(xnzf)

    def handle_par2(self, nzf, file_done):
        """ Check if file is a par2 and build up par2 collection
        """
        fn = nzf.filename
        if fn:
            # We have a real filename now
            fn = fn.strip()
            lfn = fn.lower()
            if not nzf.is_par2:
                head, vol, block = analyse_par2(fn)
                ## Is a par2file and repair mode activated
                if head and (self.repair or cfg.allow_streaming()):
                    ## Skip if mini-par2 is not complete and there are more par2 files
                    if not block and nzf.bytes_left and self.extrapars.get(head):
                        return
                    nzf.set_par2(head, vol, block)
                    ## Already got a parfile for this set?
                    if head in self.partable:
                        nzf.extrapars = self.extrapars[head]
                        ## Set the smallest par2file as initialparfile
                        ## But only do this if our last initialparfile
                        ## isn't already done (e.g two small parfiles)
                        if nzf.blocks < self.partable[head].blocks \
                           and self.partable[head] in self.files:
                            self.partable[head].reset_try_list()
                            self.files.remove(self.partable[head])
                            self.extrapars[head].append(self.partable[head])
                            self.partable[head] = nzf

                        ## This file either has more blocks,
                        ## or initialparfile is already decoded
                        else:
                            if file_done:
                                if nzf in self.files: self.files.remove(nzf)
                                if nzf not in self.extrapars[head]: self.extrapars[head].append(nzf)
                            else:
                                nzf.reset_try_list()

                    ## No par2file in this set yet, set this as
                    ## initialparfile
                    else:
                        self.postpone_pars(nzf, head)
                ## Is not a par2file or nothing to do
                else:
                    pass
        ## No filename in seg 1? Probably not uu or yenc encoded
        ## Set subject as filename
        else:
            nzf.filename = nzf.subject


    def remove_article(self, article, found):
        nzf = article.nzf
        file_done, reset = nzf.remove_article(article, found)

        if file_done:
            self.remove_nzf(nzf)
            if not self.reuse and cfg.fail_hopeless() and not self.check_quality(99)[0]:
                #set the nzo status to return "Queued"
                self.status = Status.QUEUED
                self.set_download_report()
                self.fail_msg = T('Aborted, cannot be completed')
                self.set_unpack_info('Download', self.fail_msg, unique=False)
                logging.debug('Abort job "%s", due to impossibility to complete it', self.final_name_pw_clean)
                return True, True, True

        if reset:
            self.reset_try_list()

        if file_done:
            self.handle_par2(nzf, file_done)

        post_done = False
        if not self.files:
            post_done = True
            #set the nzo status to return "Queued"
            self.status = Status.QUEUED
            self.set_download_report()

        return (file_done, post_done, reset)


    def check_existing_files(self, wdir):
        """ Check if downloaded files already exits, for these set NZF to complete
        """
        fix_unix_encoding(wdir)

        # Get a list of already present files
        files = [os.path.basename(f) for f in globber_full(wdir) if os.path.isfile(f)]

        # Substitute renamed files
        renames = sabnzbd.load_data(RENAMES_FILE, self.workpath, remove=True)
        if renames:
            for name in renames:
                if name in files or renames[name] in files:
                    files.remove(name)
                    files.append(renames[name])

        # Looking for the longest name first, minimizes the chance on a mismatch
        files.sort(lambda x, y: len(y) - len(x))

        nzfs = self.files[:]
        # The NZFs should be tried shortest first, to improve the chance on a proper match
        nzfs.sort(lambda x, y: len(x.subject) - len(y.subject))

        # Flag files from NZB that already exist as finished
        for filename in files[:]:
            for nzf in nzfs:
                subject = sanitize_filename(name_extractor(nzf.subject))
                if (nzf.filename == filename) or (subject == filename) or (filename in subject):
                    nzf.filename = filename
                    nzf.completed = True
                    nzf.bytes_left = 0
                    self.handle_par2(nzf, file_done=True)
                    self.remove_nzf(nzf)
                    nzfs.remove(nzf)
                    files.remove(filename)
                    break

        try:
            # Create an NZF for each remaining existing file
            for filename in files:
                tup = os.stat(os.path.join(wdir, filename))
                tm = datetime.datetime.fromtimestamp(tup.st_mtime)
                nzf = NzbFile(tm, '"%s"' % filename, [], tup.st_size, self)
                self.files.append(nzf)
                self.files_table[nzf.nzf_id] = nzf
                self.bytes += nzf.bytes
                nzf.filename = filename
                nzf.completed = True
                nzf.bytes_left = 0
                self.handle_par2(nzf, file_done=True)
                self.remove_nzf(nzf)
                logging.info('File %s added to job', filename)
        except:
            logging.debug('Bad NZB handling')
            logging.info("Traceback: ", exc_info = True)

    @property
    def pp(self):
        if self.repair is None:
            return None
        else:
            return sabnzbd.opts_to_pp(self.repair, self.unpack, self.delete)

    def set_pp(self, value):
        self.repair, self.unpack, self.delete = sabnzbd.pp_to_opts(value)
        self.save_to_disk()

    @property
    def final_name_pw(self):
        prefix = ''
        if self.duplicate:
            prefix = T('DUPLICATE') + ' / ' #: Queue indicator for duplicate job
        if self.encrypted and self.status == 'Paused':
            prefix += T('ENCRYPTED') + ' / '  #: Queue indicator for encrypted job
        if self.oversized and self.status == 'Paused':
            prefix += T('TOO LARGE') + ' / ' #: Queue indicator for oversized job
        if self.incomplete and self.status == 'Paused':
            prefix += T('INCOMPLETE') + ' / ' #: Queue indicator for incomplete NZB
        if self.unwanted_ext and self.status == 'Paused':
            prefix += T('UNWANTED') + ' / ' #: Queue indicator for unwanted extensions
        if self.rating_filtered and self.status == 'Paused':
            prefix += Ta('FILTERED') + ' / ' #: Queue indicator for filtered
        if isinstance(self.wait, float):
            dif = int(self.wait - time.time() + 0.5)
            if dif > 0:
                prefix += T('WAIT %s sec') % dif + ' / ' #: Queue indicator for waiting URL fetch
        if self.password:
            return '%s%s / %s' % (prefix, self.final_name, self.password)
        else:
            return '%s%s' % (prefix, self.final_name)

    @property
    def final_name_pw_clean(self):
        if self.password:
            return '%s / %s' % (self.final_name, self.password)
        else:
            return self.final_name

    def set_final_name_pw(self, name, password=None):
        if isinstance(name, basestring):
            if password is not None:
                name = platform_encode(name)
                self.password = platform_encode(password)
            else:
                name, self.password = scan_password(platform_encode(name))
            self.final_name = sanitize_foldername(name)
            self.save_to_disk()

    def pause(self):
        self.status = Status.PAUSED
        # Prevent loss of paused state when terminated
        if self.nzo_id:
            sabnzbd.save_data(self, self.nzo_id, self.workpath)

    def resume(self):
        self.status = Status.QUEUED
        if self.encrypted:
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

    def add_parfile(self, parfile):
        if parfile not in self.files:
            self.files.append(parfile)
        if parfile.extrapars and parfile in parfile.extrapars:
            parfile.extrapars.remove(parfile)

    def remove_parset(self, setname):
        self.partable.pop(setname)

    __re_quick_par2_check = re.compile('\.par2\W*', re.I)
    def check_quality(self, req_ratio=0):
        """ Determine amount of articles present on servers
            and return (gross available, nett) bytes
        """
        need = 0L
        pars = 0L
        short = 0L
        anypars = False
        for nzf_id in self.files_table:
            nzf = self.files_table[nzf_id]
            assert isinstance(nzf, NzbFile)
            if nzf.deleted:
                short += nzf.bytes_left
            if self.__re_quick_par2_check.search(nzf.subject):
                pars += nzf.bytes
                anypars = True
            else:
                need += nzf.bytes
        have = need + pars - short
        ratio = float(have) / float(max(1, need))
        if anypars:
            enough = ratio * 100.0 >= (req_ratio or float(cfg.req_completion_rate()))
        else:
            enough = have >= need
        logging.debug('Download Quality: enough=%s, have=%s, need=%s, ratio=%s', enough, have, need, ratio)
        return enough, ratio


    def set_download_report(self):
        import sabnzbd.api
        if self.avg_bps_total and self.bytes_downloaded and self.avg_bps_freq:
            #get the deltatime since the download started
            avg_bps = self.avg_bps_total / self.avg_bps_freq
            timecompleted = datetime.timedelta(seconds=self.bytes_downloaded / (avg_bps*1024))

            seconds = timecompleted.seconds
            #find the total time including days
            totaltime = (timecompleted.days/86400) + seconds
            self.nzo_info['download_time'] = totaltime

            #format the total time the download took, in days, hours, and minutes, or seconds.
            complete_time = format_time_string(seconds, timecompleted.days)

            msg1 = T('Downloaded in %s at an average of %sB/s') % (complete_time, to_units(avg_bps*1024, dec_limit=1))
            msg1 += u'<br/>' + T('Age') + ': ' + sabnzbd.api.calc_age(self.avg_date, True)

            bad = self.nzo_info.get('bad_art_log', [])
            miss = self.nzo_info.get('missing_art_log', [])
            killed = self.nzo_info.get('killed_art_log', [])
            dups = self.nzo_info.get('dup_art_log', [])
            msg2 = msg3 = msg4 = msg5 = ''
            if bad:
                msg2 = (u'<br/>' + T('%s articles were malformed')) % len(bad)
            if miss:
                msg3 = (u'<br/>' + T('%s articles were missing')) % len(miss)
            if dups:
                msg4 = (u'<br/>' + T('%s articles had non-matching duplicates')) % len(dups)
            if killed:
                msg5 = (u'<br/>' + T('%s articles were removed')) % len(killed)
            msg = u''.join((msg1, msg2, msg3, msg4, msg5, ))
            self.set_unpack_info('Download', msg, unique=True)
            if self.url:
                self.set_unpack_info('Source', format_source_url(self.url), unique=True)
            servers = config.get_servers()
            if len(self.servercount) > 0:
                msgs = [ '%s=%sB' % (servers[server].displayname(), to_units(self.servercount[server])) for server in self.servercount if server in servers]
                self.set_unpack_info('Servers', ', '.join(msgs), unique=True)

    def inc_log(self, log, txt):
        """ Append string txt to nzo_info element "log"
        """
        try:
            self.nzo_info[log].append(txt)
        except:
            self.nzo_info[log] = [txt]

    def server_allowed(self, server):
        if not server.categories:
            return False
        if "Default" in server.categories:
            return True
        if self.cat in server.categories:
            return True
        # There are no default servers, and either we have no category, or no server matches our category
        return False

    def get_article(self, server, servers):
        article = None
        nzf_remove_list = []

        for nzf in self.files:
            assert isinstance(nzf, NzbFile)
            if nzf.deleted:
                logging.debug('Skipping existing file %s', nzf.filename or nzf.subject)
            else:
                # Don't try to get an article if server is in try_list of nzf
                if not nzf.server_in_try_list(server):
                    if not nzf.import_finished:
                        # Only load NZF when it's a primary server
                        # or when it's a backup server without active primaries
                        if sabnzbd.highest_server(server):
                            nzf.finish_import()
                            # Still not finished? Something went wrong...
                            if not nzf.import_finished:
                                logging.error(T('Error importing %s'), nzf)
                                nzf_remove_list.append(nzf)
                                continue
                        else:
                            continue

                    article = nzf.get_article(server, servers)
                    if article:
                        break

        # Remove all files for which admin could not be read
        for nzf in nzf_remove_list:
            nzf.deleted = True
            nzf.completed = True
            self.files.remove(nzf)
        # If cleanup emptied the active files list, end this job
        if nzf_remove_list and not self.files:
            sabnzbd.NzbQueue.do.end_job(self)

        if not article:
            # No articles for this server, block for next time
            self.add_to_try_list(server)
        return article

    def move_top_bulk(self, nzf_ids):
        self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            target = range(len(nzf_ids))

            while 1:
                self.move_up_bulk(nzf_ids, cleanup = False)

                pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

                keys = pos_nzf_table.keys()
                keys.sort()

                if target == keys:
                    break

    def move_bottom_bulk(self, nzf_ids):
        self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            target = range(len(self.files)-len(nzf_ids), len(self.files))

            while 1:
                self.move_down_bulk(nzf_ids, cleanup = False)

                pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

                keys = pos_nzf_table.keys()
                keys.sort()

                if target == keys:
                    break

    def move_up_bulk(self, nzf_ids, cleanup = True):
        if cleanup:
            self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

            while pos_nzf_table:
                pos = min(pos_nzf_table)
                nzf = pos_nzf_table.pop(pos)

                if pos > 0:
                    tmp_nzf = self.files[pos-1]
                    if tmp_nzf.nzf_id not in nzf_ids:
                        self.files[pos-1] = nzf
                        self.files[pos] = tmp_nzf

    def move_down_bulk(self, nzf_ids, cleanup = True):
        if cleanup:
            self.cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            pos_nzf_table = self.build_pos_nzf_table(nzf_ids)

            while pos_nzf_table:
                pos = max(pos_nzf_table)
                nzf = pos_nzf_table.pop(pos)

                if pos < len(self.files)-1:
                    tmp_nzf = self.files[pos+1]
                    if tmp_nzf.nzf_id not in nzf_ids:
                        self.files[pos+1] = nzf
                        self.files[pos] = tmp_nzf

        # Determine if rating information (including site identifier so rating can be updated)
    # is present in metadata and if so store it
    def update_rating(self):
        if cfg.rating_enable():
            try:
                def _get_first_meta(type):
                    values = self.meta.get('x-oznzb-rating-' + type, None) or self.meta.get('x-rating-' + type, None)
                    return values[0] if values else None
                rating_types = ['video', 'videocnt', 'audio', 'audiocnt', 'voteup' ,'votedown', \
                                'spam', 'confirmed-spam', 'passworded', 'confirmed-passworded']
                fields = {}
                for k in rating_types:
                    fields[k] = _get_first_meta(k)
                Rating.do.add_rating(_get_first_meta('id'), self.nzo_id, self.meta.get('x-rating-host'), fields)
            except:
                pass

    ## end nzo.Mutators #######################################################
    ###########################################################################
    @property
    def workpath(self):
        """ Return the full path for my job-admin folder (or old style cache) """
        return long_path(get_admin_path(self.work_name, self.futuretype))

    @property
    def downpath(self):
        """ Return the full path for my download folder """
        return long_path(os.path.join(cfg.download_dir.get_path(), self.work_name))

    @property
    def group(self):
        if self.groups:
            return self.groups[0]
        else:
            return None

    def purge_data(self, keep_basic=False, del_files=False):
        """ Remove all admin info, 'keep_basic' preserves attribs and nzb """
        wpath = self.workpath
        for nzf in self.files:
            sabnzbd.remove_data(nzf.nzf_id, wpath)

        for _set in self.extrapars:
            for nzf in self.extrapars[_set]:
                sabnzbd.remove_data(nzf.nzf_id, wpath)

        for nzf in self.finished_files:
            sabnzbd.remove_data(nzf.nzf_id, wpath)

        if not self.futuretype:
            if keep_basic:
                remove_all(wpath, 'SABnzbd_nz?_*')
                remove_all(wpath, 'SABnzbd_article_*')
            else:
                remove_all(wpath, recursive=True)
            if del_files:
                remove_all(self.downpath, recursive=True)
            else:
                try:
                    os.rmdir(self.downpath)
                except:
                    pass

    def remaining(self):
        """ Return remaining bytes """
        bytes_left = 0
        for nzf in self.files:
            bytes_left += nzf.bytes_left
        return bytes_left

    def total_and_remaining(self):
        """ Return total and remaining bytes """
        bytes = 0
        bytes_left = 0
        for nzf in self.files:
            bytes += nzf.bytes
            bytes_left += nzf.bytes_left
        return bytes, bytes_left

    def gather_info(self, for_cli = False):
        bytes_left_all = 0

        active_files = []
        queued_files = []
        finished_files = []

        for nzf in self.finished_files:
            bytes = nzf.bytes
            filename = nzf.filename
            if not filename:
                filename = nzf.subject
            date = nzf.date
            if for_cli:
                date = time.mktime(date.timetuple())
            finished_files.append((0, bytes, filename, date))

        for nzf in self.files:
            bytes_left = nzf.bytes_left
            bytes = nzf.bytes
            filename = nzf.filename
            if not filename:
                filename = nzf.subject
            date = nzf.date
            if for_cli:
                date = time.mktime(date.timetuple())

            bytes_left_all += bytes_left
            active_files.append((bytes_left, bytes, filename, date,
                                 nzf.nzf_id))

        for _set in self.extrapars:
            for nzf in self.extrapars[_set]:
                bytes_left = nzf.bytes_left
                bytes = nzf.bytes
                filename = nzf.filename
                if not filename:
                    filename = nzf.subject
                date = nzf.date
                if for_cli:
                    date = time.mktime(date.timetuple())

                queued_files.append((_set, bytes_left, bytes, filename, date))

        avg_date = self.avg_date
        if for_cli:
            avg_date = time.mktime(avg_date.timetuple())

        return (self.repair, self.unpack, self.delete, self.script,
                self.nzo_id, self.final_name_pw, {},
                '', self.cat, self.url,
                bytes_left_all, self.bytes, avg_date,
                finished_files, active_files, queued_files, self.status, self.priority,
                len(self.nzo_info.get('missing_art_log', []))
                )

    def get_nzf_by_id(self, nzf_id):
        if nzf_id in self.files_table:
            return self.files_table[nzf_id]

    def set_unpack_info(self, key, msg, set='', unique=False):
        '''
            Builds a dictionary containing the stage name (key) and a message
            If set is present, it will overwrite any other messages from the set of the same stage
            If unique is present, it will only have a single line message
        '''
        found = False
        # Unique messages allow only one line per stage(key)
        if not unique:
            if not self.unpack_info.has_key(key):
                self.unpack_info[key] = []
            # If set is present, look for previous message from that set and replace
            if set:
                set = unicoder('[%s]' % set)
                for x in xrange(len(self.unpack_info[key])):
                    if set in self.unpack_info[key][x]:
                        self.unpack_info[key][x] = msg
                        found = True
            if not found:
                self.unpack_info[key].append(msg)
        else:
            self.unpack_info[key] = [msg]

    def set_action_line(self, action=None, msg=None):
        if action and msg:
            self.action_line = '%s: %s' % (action, msg)
        else:
            self.action_line = ''

    @property
    def repair_opts(self):
        return self.repair, self.unpack, self.delete

    def save_to_disk(self):
        """ Save job's admin to disk """
        self.save_attribs()
        if self.nzo_id:
            sabnzbd.save_data(self, self.nzo_id, self.workpath)

    def save_attribs(self):
        set_attrib_file(self.workpath, (self.cat, self.pp, self.script, self.priority, self.final_name_pw_clean, self.url))

    def build_pos_nzf_table(self, nzf_ids):
        pos_nzf_table = {}
        for nzf_id in nzf_ids:
            if nzf_id in self.files_table:
                nzf = self.files_table[nzf_id]
                pos = self.files.index(nzf)
                pos_nzf_table[pos] = nzf

        return pos_nzf_table

    def cleanup_nzf_ids(self, nzf_ids):
        for nzf_id in nzf_ids[:]:
            if nzf_id in self.files_table:
                if self.files_table[nzf_id] not in self.files:
                    nzf_ids.remove(nzf_id)
            else:
                nzf_ids.remove(nzf_id)

    def has_duplicates(self):
        """ Return True when this NZB or episode is already in the History
        """
        no_dupes = cfg.no_dupes()
        no_series_dupes = cfg.no_series_dupes()
        if not no_dupes and not no_series_dupes:
            return 0

        res = 0
        history_db = get_history_handle()
        if no_series_dupes:
            series, season, episode, dummy = sabnzbd.newsunpack.analyse_show(self.final_name)
            if history_db.have_episode(series, season, episode):
                res = no_series_dupes
        if not res and no_dupes:
            if history_db.have_md5sum(self.md5sum):
                res = no_dupes
        history_db.close()
        return res

    def __getstate__(self):
        """ Save to pickle file, selecting attributes """
        dict_ = {}
        for item in NzbObjectSaver:
            dict_[item] = self.__dict__[item]
        return dict_

    def __setstate__(self, dict_):
        """ Load from pickle file, selecting attributes """
        for item in NzbObjectSaver:
            try:
                self.__dict__[item] = dict_[item]
            except KeyError:
                # Handle new attributes
                self.__dict__[item] = None
        self.pp_active = False
        self.avg_stamp = time.mktime(self.avg_date.timetuple())
        self.wait = None
        if self.meta is None:
            self.meta = {}
        if self.servercount is None:
            self.servercount = {}
        TryList.__init__(self)


    def __repr__(self):
        return "<NzbObject: filename=%s>" % self.filename


#-------------------------------------------------------------------------------

def nzf_get_filename(nzf):
    """ Return filename, if the filename not set, try the
        the full subject line instead. Can produce non-ideal results
    """
    name = nzf.filename
    if not name:
        name = nzf.subject
    if not name:
        name = ''
    return name.lower()


def get_ext_list():
    """ Return priority extenstion list, with extensions starting with a period
    """
    exts = []
    for ext in cfg.prio_sort_list():
        ext = ext.strip()
        if not ext.startswith('.'):
            ext = '.' + ext
        exts.append(ext)
    return exts


def ext_on_list(name, lst):
    """ Return True if `name` contains any extension in `lst`
    """
    for ext in lst:
        if name.rfind(ext) >= 0:
            return True
    return False


def nzf_cmp_date(nzf1, nzf2):
    """ Compare files based on date, but give vol-par files preference.
        Wrapper needed, because `cmp` function doesn't handle extra parms.
    """
    return nzf_cmp_name(nzf1, nzf2, name=False)


RE_RAR = re.compile(r'(\.rar|\.r\d\d|\.s\d\d|\.t\d\d|\.u\d\d|\.v\d\d)$', re.I)

def nzf_cmp_name(nzf1, nzf2, name=True):
    # The comparison will sort .par2 files to the top of the queue followed by .rar files,
    # they will then be sorted by name.
    name1 = nzf_get_filename(nzf1)
    name2 = nzf_get_filename(nzf2)

    # Determine vol-pars
    is_par1 = '.vol' in name1 and '.par2' in name1
    is_par2 = '.vol' in name2 and '.par2' in name2

    # mini-par2 in front
    if not is_par1 and name1.endswith('.par2'):
        return -1
    if not is_par2 and name2.endswith('.par2'):
        return 1

    # vol-pars go to the back
    if is_par1 and not is_par2:
        return 1
    if is_par2 and not is_par1:
        return -1

    # Anything with a priority extention goes first
    ext_list = get_ext_list()
    if ext_list:
        onlist1 = ext_on_list(name1, ext_list)
        onlist2 = ext_on_list(name2, ext_list)
        if onlist1 and not onlist2:
            return -1
        if onlist2 and not onlist1:
            return 1

    if name:
        # Prioritise .rar files above any other type of file (other than vol-par)
        # Useful for nzb streaming
        m1 = RE_RAR.search(name1)
        m2 = RE_RAR.search(name2)
        if  m1 and not (is_par2 or m2):
            return -1
        elif m2 and not (is_par1 or m1):
            return 1
        # Force .rar to come before 'r00'
        if m1 and m1.group(1) == '.rar': name1 = name1.replace('.rar', '.r//')
        if m2 and m2.group(1) == '.rar': name2 = name2.replace('.rar', '.r//')
        return cmp(name1, name2)
    else:
        # Do date comparision
        return cmp(nzf1.date, nzf2.date)

#-------------------------------------------------------------------------------

def split_filename(name):
    """ Remove ".nzb"
    """
    name = name.strip()
    if name.find('://') < 0:
        m = RE_NORMAL.match(name)
        if (m):
            return m.group(1).rstrip('.').strip()
        else:
            return name.strip()
        return ''
    else:
        return name.strip()


def scan_password(name):
    """ Get password (if any) from the title
    """
    if 'http://' in name or 'https://' in name:
        return name, None

    braces = name.find('{{')
    if braces < 0:
        braces = len(name)
    slash = name.find('/')

    # Look for name/password, but make sure that '/' comes before any {{
    if slash >= 0 and slash < braces and not 'password=' in name:
        return name[:slash].strip('. '), name[slash+1:]

    # Look for "name password=password"
    pw = name.find('password=')
    if pw >= 0:
        return name[:pw].strip('. '), name[pw+9:]

    # Look for name{{password}}
    if braces < len(name) and name.endswith('}}'):
        return name[:braces].strip('. '), name[braces+2:len(name)-2]

    # Look again for name/password
    if slash >= 0:
        return name[:slash].strip('. '), name[slash+1:]

    # No password found
    return name, None


def get_attrib_file(path, size):
    """ Read job's attributes from file """
    attribs = []
    path = os.path.join(path, ATTRIB_FILE)
    try:
        f = open(path, 'r')
    except:
        return [None for n in xrange(size)]

    for n in xrange(size):
        line = f.readline().strip('\r\n ')
        if line:
            if line.lower() == 'none':
                line = None
            try:
                line = int(line)
            except:
                pass
            attribs.append(line)
        else:
            attribs.append(None)
    f.close()
    return attribs


def set_attrib_file(path, attribs):
    """ Write job's attributes to file """
    path = os.path.join(path, ATTRIB_FILE)
    try:
        f = open(path, 'w')
    except:
        return

    for item in attribs:
        f.write('%s\n' % item)
    f.close()


def analyse_par2(name):
    """ Check if file is a par2-file and determine vol/block
        return head, vol, block
        head is empty when not a par2 file
    """
    head = None
    vol = block = 0
    if name and not REJECT_PAR2_RE.search(name):
        m = PROBABLY_PAR2_RE.search(name)
        if m:
            head = m.group(1)
            vol = m.group(2)
            block = m.group(3)
        elif name.lower().find('.par2') > 0:
            head = os.path.splitext(name)[0].strip()
        else:
            head = None
    return head, vol, block


def name_extractor(subject):
    """ Try to extract a file name from a subject line, return `subject` if in doubt
    """
    result = subject
    for name in re.findall(SUBJECT_FN_MATCHER, subject):
        name = name.strip(' "')
        if name and RE_NORMAL_NAME.search(name):
            result = name
    return platform_encode(result)


def matcher(pattern, txt):
    """ Return True if `pattern` is sufficiently equal to `txt`
    """
    if txt.endswith(pattern):
        txt = txt[:txt.rfind(pattern)].strip()
        return (not txt) or txt.endswith('"')
    else:
        return False
