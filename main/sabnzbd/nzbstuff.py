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
sabnzbd.nzbstuff - misc
"""

import os
import time
import re
import logging
import sabnzbd
import datetime
import xml.sax
import xml.sax.handler
import xml.sax.xmlreader
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import sabnzbd
from sabnzbd.constants import *
from sabnzbd.misc import to_units, cat_to_opts, cat_convert, sanitize_foldername
import sabnzbd.cfg as cfg
from sabnzbd.trylist import TryList
from sabnzbd.lang import T, Ta
from sabnzbd.codecs import unicoder

RE_NEWZBIN = re.compile(r"msgid_(\w+) (.+)(\.nzb)$", re.I)
RE_NORMAL  = re.compile(r"(.+)(\.nzb)", re.I)
SUBJECT_FN_MATCHER = re.compile(r'"(.*)"')
RE_SAMPLE = re.compile(sample_match, re.I)
PROBABLY_PAR2_RE = re.compile(r'(.*)\.vol(\d*)\+(\d*)\.par2', re.I)


################################################################################
# Article                                                                      #
################################################################################
class Article(TryList):
    def __init__ (self, article, bytes, partnum, nzf):
        TryList.__init__(self)

        self.fetcher = None
        self.allow_fill_server = False

        self.article = article
        self.art_id = None
        self.bytes = bytes
        self.partnum = partnum
        self.nzf = nzf

    def get_article(self, server):
        if server.fillserver and (not self.allow_fill_server) and sabnzbd.active_primaries():
            return None

        if not self.fetcher and not self.server_in_try_list(server):
            self.fetcher = server
            return self

    def get_art_id(self):
        if not self.art_id:
            self.art_id = sabnzbd.get_new_id("article")
        return self.art_id

    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['_TryList__try_list']
        del odict['fetcher']
        return odict

    def __setstate__(self, _dict):
        self.__dict__.update(_dict)
        TryList.__init__(self)
        self.fetcher = None
        self.allow_fill_server = False

    def __repr__(self):
        return "<Article: article=%s, bytes=%s, partnum=%s, art_id=%s>" % \
               (self.article, self.bytes, self.partnum, self.art_id)

################################################################################
# NzbFile                                                                      #
################################################################################
SUBJECT_FN_MATCHER = re.compile(r'"(.*)"')
class NzbFile(TryList):
    def __init__(self, date, subject, article_db, bytes, nzo):
        TryList.__init__(self)

        # Private
        self.__date = date
        self.__subject = subject
        self.__filename = None
        self.__type = None

        match = re.search(SUBJECT_FN_MATCHER, subject)
        if match:
            self.__filename = match.group(1).strip('"')

        self.__ispar2file = False
        self.__vol = None
        self.__blocks = None
        self.__setname = None
        self.__extrapars = None

        self.__initial_article = None

        self.__articles = []
        self.__decodetable = {}

        self.__bytes = bytes
        self.__bytes_left = bytes
        self.__article_count = 0

        # Public
        self.nzo = nzo
        self.nzf_id = sabnzbd.get_new_id("nzf")
        self.deleted = False

        self.valid = False
        self.import_finished = False

        self.md5sum = None

        self.valid = bool(article_db)

        if self.valid and self.nzf_id:
            sabnzbd.save_data(article_db, self.nzf_id)

    ## begin nzf.Mutators #####################################################
    ## excluding nzf.__try_list ###############################################
    def increase_article_count(self):
        self.__article_count += 1

    def finish_import(self):
        logging.info("Finishing import on %s", self.__subject)

        article_db = sabnzbd.load_data(self.nzf_id)
        if article_db:
            for partnum in article_db:
                art_id = article_db[partnum][0]
                bytes = article_db[partnum][1]

                article = Article(art_id, bytes, partnum, self)

                self.__articles.append(article)
                self.__decodetable[partnum] = article

            # Look for article with lowest number
            self.__initial_article = self.__decodetable[self.lowest_partnum()]
            self.import_finished = True

    def remove_article(self, article):
        self.__articles.remove(article)
        self.__bytes_left -= article.bytes

        reset = False
        if article.partnum == self.lowest_partnum() and self.__articles:
            # Issue reset
            self.__initial_article = None
            self.reset_try_list()
            reset = True

        done = True
        if self.__articles:
            done = False

        return (done, reset)

    def set_type(self, _type):
        self.__type = _type

    def set_filename(self, filename):
        self.__filename = filename

    def set_par2(self, setname, vol, blocks):
        self.__ispar2file = True
        self.__setname = setname
        self.__vol = vol
        self.__blocks = int(blocks)

    def set_extrapars(self, extrapars):
        self.__extrapars = extrapars

    def remove_extrapar(self, extrapar):
        self.__extrapars.remove(extrapar)

    def is_par2(self):
        return self.__ispar2file

    ## end nzf.Mutators #######################################################
    ###########################################################################
    def get_article_count(self):
        return self.__article_count

    def get_article(self, server):
        if self.__initial_article:
            article = self.__initial_article.get_article(server)
            if article:
                return article

        else:
            for article in self.__articles:
                article = article.get_article(server)
                if article:
                    return article

        self.add_to_try_list(server)

    def reset_all_try_lists(self):
        for art in self.__articles:
            art.reset_try_list()
        self.reset_try_list()

    def bytes(self):
        return self.__bytes

    def bytes_left(self):
        return self.__bytes_left

    def get_subject(self):
        return self.__subject

    def get_date(self):
        return self.__date

    def get_filename(self):
        return self.__filename

    def get_decodetable(self):
        return self.__decodetable

    def get_type(self):
        return self.__type

    def get_extrapars(self):
        return self.__extrapars

    def get_blocks(self):
        return self.__blocks

    def get_setname(self):
        return self.__setname

    def completed(self):
        return not bool(self.__articles)

    def lowest_partnum(self):
        return min(self.__decodetable)

    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['_TryList__try_list']
        return odict

    def __setstate__(self, _dict):
        self.__dict__.update(_dict)
        TryList.__init__(self)

    def __repr__(self):
        return "<NzbFile: filename=%s, type=%s>" % \
               (self.__filename, self.__type)


################################################################################
# NzbParser                                                                    #
################################################################################
class NzbParser(xml.sax.handler.ContentHandler):
    """ Forgiving parser for NZB's """
    # Accesses private variables of NzbObject instances to keep
    # queue-compatibility with previous trunk versions.
    # Ideally the methods of this class could be added to NzbObject,
    # but this would also break compatibility.
    # Hence, this solution.
    def __init__ (self, nzo):
        self.nzo = nzo
        self.in_nzb = False
        self.in_file = False
        self.in_groups = False
        self.in_group = False
        self.in_segments = False
        self.in_segment = False
        self.filename = ''
        self.avg_age = 0
        self.valids = 0
        self.skipped_files = 0
        self.nzf_list = []

    def startDocument(self):
        self.filter = cfg.IGNORE_SAMPLES()

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
            subject = attrs.get('subject', '')
            match = re.search(SUBJECT_FN_MATCHER, subject)
            if match:
                self.filename = match.group(1).strip('"').strip()
            else:
                self.filename = subject.strip()

            if self.filter == 2 and RE_SAMPLE.search(subject):
                logging.info('Skipping sample file %s', subject)
            else:
                self.in_file = True
                if isinstance(subject, unicode):
                    subject = subject.encode('latin-1', 'replace')
                self.fileSubject = subject
                try:
                    self.file_date = int(attrs.get('date'))
                except:
                    # NZB has non-standard timestamp, assume 1
                    self.file_date = 1
                self.article_db = {}
                self.file_bytes = 0

        elif name == 'group' and self.in_nzb and self.in_file and self.in_groups:
            self.in_group = True
            self.group_name = []

        elif name == 'groups' and self.in_nzb and self.in_file:
            self.in_groups = True
            self.groups = []

        elif name == 'nzb':
            self.in_nzb = True

    def characters (self, content):
        if self.in_group:
            self.group_name.append(content)
        elif self.in_segment:
            self.article_id.append(content)

    def endElement(self, name):
        if name == 'group' and self.in_group:
            self.groups.append(str(''.join(self.group_name)))
            self.in_group = False

        elif name == 'segment' and self.in_segment:
            partnum = self.article_nr
            segm = str(''.join(self.article_id))
            if partnum in self.article_db:
                if segm != self.article_db[partnum][0]:
                    logging.error(Ta('error-qDupPart@3'),
                                         partnum, self.article_db[partnum][0], segm)
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
                logging.warning(Ta('warn-emptyFile@1'), self.filename)
                return
            tm = datetime.datetime.fromtimestamp(self.file_date)
            nzf = NzbFile(tm, self.filename, self.article_db, self.file_bytes, self.nzo)
            if nzf.valid and nzf.nzf_id:
                logging.info('File %s added to queue', self.filename)
                self.nzo._NzbObject__files.append(nzf)
                self.nzo._NzbObject__files_table[nzf.nzf_id] = nzf
                self.nzo._NzbObject__bytes += nzf.bytes()
                self.avg_age += self.file_date
                self.valids += 1
                self.nzf_list.append(nzf)
            else:
                logging.info('Error importing %s, skipping', self.filename)
                if nzf.nzf_id:
                    sabnzbd.remove_data(nzf.nzf_id)
                self.skipped_files += 1

        elif name == 'nzb':
            self.in_nzb = False

    def endDocument(self):
        """ End of the file """
        self.nzo._NzbObject__group = self.groups
        self.nzo._NzbObject__avg_date = datetime.datetime.fromtimestamp(self.avg_age / self.valids)
        if self.skipped_files:
            logging.warning(Ta('warn-badImport@2'),
                            self.skipped_files, self.nzo.get_filename())

    def remove_files(self):
        """ Remove all created NZF objects """
        for nzf in self.nzf_list:
            sabnzbd.remove_data(nzf.nzf_id)


################################################################################
# NzbObject                                                                    #
################################################################################

class NzbObject(TryList):
    def __init__(self, filename, msgid, pp, script, nzb = None,
                 futuretype = False, cat = None, url=None,
                 priority=NORMAL_PRIORITY, nzbname=None, status="Queued", nzo_info=None):
        TryList.__init__(self)

        if pp is None:
            r = u = d = None
        else:
            r, u, d = sabnzbd.pp_to_opts(pp)

        self.__filename = filename    # Original filename
        if nzbname and nzb:
            dirname = nzbname         # Use nzbname if set and only for non-future slot
        else:
            dirname = filename

        # If non-future: create safe folder name stripped from ".nzb" and junk
        if nzb and dirname and dirname.lower().endswith('.nzb'):
            dname, ext = os.path.splitext(dirname) # Used for folder name for final unpack
            if ext.lower() == '.nzb':
                dirname = dname
            dirname = sanitize_foldername(dirname)
        dirname, password = scan_password(dirname)

        self.__dirname = dirname      # Keeps track of the working folder
        self.__original_dirname = dirname # TAKE NOTE: Used for folder name for final unpack
                                          # The name is wrong, required for backward compatibility!

        self.__created = False        # dirprefixes + dirname created
        self.__bytes = 0              # Original bytesize
        self.__bytes_downloaded = 0   # Downloaded byte
        self.__repair = r             # True if we want to repair this set
        self.__unpack = u             # True if we want to unpack this set
        self.__delete = d             # True if we want to delete this set
        self.__script = script        # External script for this set
        self.__msgid = '0'            # Newzbin msgid
        self.__cat = cat              # Newzbin category
        if futuretype:
            self.__url = str(url)     # Either newzbin-id or URL queued (future-type only)
        else:
            self.__url = ''
        self.__group = []
        self.__avg_date = datetime.datetime.fromtimestamp(0.0)
        self.__dirprefix = []

        self.__partable = {}          # Holds one parfile-name for each set
        self.__extrapars = {}         # Holds the extra parfile names for all sets
        self.md5packs = {}            # Holds the md5pack for each set

        self.__files = []
        self.__files_table = {}

        self.__finished_files = []

        #the current status of the nzo eg:
        #Queued, Downloading, Repairing, Unpacking, Failed, Complete
        self.__status = status
        self.__avg_bps_freq = 0
        self.__avg_bps_total = 0
        try:
            self.__priority = int(priority)
        except:
            self.__priority = DEFAULT_PRIORITY

        self.__dupe_table = {}

        self.saved_articles = []

        self.nzo_id = None

        self.futuretype = futuretype
        self.deleted = False
        self.parsed = False

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

        # Temporary store for custom foldername - needs to be stored because of url/newzbin fetching
        self.extra1 = nzbname

        self.extra2 = password
        self.extra3 = None # Will hold earliest next save time of NZO
        self.extra4 = None # Will hold save timeout for this NZO
        self.extra5 = None
        self.extra6 = None

        self.create_group_folder = cfg.CREATE_GROUP_FOLDERS()

        # Remove leading msgid_XXXX and trailing .nzb
        self.__dirname, self.__msgid = SplitFileName(self.__dirname)
        if msgid:
            self.__msgid = msgid

        if not nzb:
            # This is a slot for a future NZB, ready now
            return

        # Apply conversion option to final folder, called __original_dirname
        # Yeah, I know :(
        if cfg.REPLACE_DOTS() and ' ' not in self.__original_dirname:
            logging.info('Replacing dots with spaces in %s', self.__original_dirname)
            self.__original_dirname = self.__original_dirname.replace('.',' ')
        if cfg.REPLACE_SPACES():
            logging.info('Replacing spaces with underscores in %s', self.__dirname)
            self.__original_dirname = self.__original_dirname.replace(' ','_')

        if sabnzbd.backup_exists(filename):
            # File already exists and we have no_dupes set
            logging.warning(Ta('warn-skipDup@1'), filename)
            raise TypeError

        # Must create a lower level XML parser because we must
        # disable the reading of the DTD file from newzbin.com
        # by setting "feature_external_ges" to 0.

        handler = NzbParser(self)
        parser = xml.sax.make_parser()
        parser.setFeature(xml.sax.handler.feature_external_ges, 0)
        parser.setContentHandler(handler)
        parser.setErrorHandler(xml.sax.handler.ErrorHandler())
        inpsrc = xml.sax.xmlreader.InputSource()
        inpsrc.setByteStream(StringIO(nzb))
        try:
            parser.parse(inpsrc)
        except xml.sax.SAXParseException, err:
            handler.remove_files()
            logging.warning(Ta('warn-badNZB@3'),
                          filename, err.getMessage(), err.getLineNumber())
            raise ValueError
        except Exception, err:
            handler.remove_files()
            logging.warning(Ta('warn-badNZB@3'), filename, err, 0)
            raise ValueError

        sabnzbd.backup_nzb(filename, nzb)

        if cat is None:
            for grp in self.__group:
                cat = cat_convert(grp)
                if cat:
                    break

        # Determine category and find pp/script values
        self.__cat, pp, self.__script, self.__priority = cat_to_opts(cat, pp, script, self.__priority)
        self.__repair, self.__unpack, self.__delete = sabnzbd.pp_to_opts(pp)

        if cfg.CREATE_GROUP_FOLDERS():
            self.__dirprefix.append(self.get_group())

        if cfg.AUTO_SORT():
            self.__files.sort(cmp=_nzf_cmp_date)
        else:
            self.__files.sort(cmp=_nzf_cmp_name)

        # Set nzo save-delay to 6 sec per GB with a max of 5 min
        self.extra4 = min(6.0 * float(self.__bytes) / GIGI, 300.0)

    ## begin nzo.Mutators #####################################################
    ## excluding nzo.__try_list ###############################################
    def check_for_dupe(self, nzf):
        filename = nzf.get_filename()

        dupe = False

        if filename in self.__dupe_table:
            old_nzf = self.__dupe_table[filename]
            if nzf.get_article_count() <= old_nzf.get_article_count():
                dupe = True

        if not dupe:
            self.__dupe_table[filename] = nzf

        return dupe

    def update_bytes(self, bytes):
        self.__bytes_downloaded += bytes

    def update_avg_kbs(self, bps):
        if bps:
            self.__avg_bps_total += bps / 1024
            self.__avg_bps_freq += 1

    def remove_nzf(self, nzf):
        if nzf in self.__files:
            self.__files.remove(nzf)
            self.__finished_files.append(nzf)
            nzf.deleted = True
        return not bool(self.__files)

    def reset_all_try_lists(self):
        for nzf in self.__files:
            nzf.reset_all_try_lists()
        self.reset_try_list()

    def remove_article(self, article):
        nzf = article.nzf
        file_done, reset = nzf.remove_article(article)

        if file_done:
            self.remove_nzf(nzf)

        if reset:
            self.reset_try_list()

        ## Special treatment for first part of par2 file
        fn = nzf.get_filename()
        if (not nzf.is_par2()) and fn and fn.strip().lower().endswith('.par2'):
            if fn:
                par2match = re.search(PROBABLY_PAR2_RE, fn)
                ## Is a par2file and repair mode activated
                if par2match and self.__repair:
                    head = par2match.group(1)
                    nzf.set_par2(par2match.group(1),
                                par2match.group(2),
                                par2match.group(3))
                    ## Already got a parfile for this set?
                    if head in self.__partable:
                        nzf.set_extrapars(self.__extrapars[head])
                        ## Set the smallest par2file as initialparfile
                        ## But only do this if our last initialparfile
                        ## isn't already done (e.g two small parfiles)
                        if nzf.get_blocks() < self.__partable[head].get_blocks() \
                        and self.__partable[head] in self.__files:
                            self.__partable[head].reset_try_list()
                            self.__files.remove(self.__partable[head])
                            self.__extrapars[head].append(self.__partable[head])
                            self.__partable[head] = nzf

                        ## This file either has more blocks,
                        ## or initialparfile is already decoded
                        else:
                            if not file_done:
                                nzf.reset_try_list()
                                self.__files.remove(nzf)
                                self.__extrapars[head].append(nzf)
                    ## No par2file in this set yet, set this as
                    ## initialparfile
                    else:
                        self.__partable[head] = nzf
                        self.__extrapars[head] = []
                        nzf.set_extrapars(self.__extrapars[head])
                ## Is not a par2file or nothing todo
                else:
                    pass
            ## No filename in seg 1? Probably not uu or yenc encoded
            ## Set subject as filename
            else:
                nzf.set_filename(nzf.get_subject())

        post_done = False
        if not self.__files:
            post_done = True
            #set the nzo status to return "Queued"
            self.set_status('Queued')
            self.set_download_report()

        return (file_done, post_done, reset)

    def set_opts(self, pp):
        self.__repair, self.__unpack, self.__delete = sabnzbd.pp_to_opts(pp)

    def set_script(self, script):
        self.__script = script

    def set_cat(self, cat):
        self.__cat = cat

    def set_dirname(self, dirname, created = False):
        self.__dirname = dirname
        self.__created = created

    def set_filename(self, filename):
        self.__filename = filename

    def get_original_dirname(self):
        return self.__original_dirname

    def show_dir_name(self):
        if self.extra2:
            return '%s / %s' % (self.__original_dirname, self.extra2)
        else:
            return self.__original_dirname

    def get_password(self):
        return self.extra2

    def set_original_dirname(self, name):
        if isinstance(name, str):
            self.__original_dirname = name.strip()
        else:
            self.__original_dirname = name

    def set_name(self, name):
        if isinstance(name, str):
            name, self.extra2 = scan_password(name)
            self.__original_dirname = sanitize_foldername(name)
            return True
        return False

    def pause_nzo(self):
        try:
            self.__status = 'Paused'
        except:
            pass

    def resume_nzo(self):
        try:
            self.__status = 'Queued'
        except:
            pass

    def get_priority(self):
        return self.__priority

    def set_priority(self, priority):
        try:
            self.__priority = priority
        except:
            pass

    def get_msgid(self):
        return self.__msgid

    def add_parfile(self, parfile):
        self.__files.append(parfile)
        parfile.remove_extrapar(parfile)

    def remove_parset(self, setname):
        self.__partable.pop(setname)

    def set_status(self, status):
        #sets a string outputting the current status of the job, eg:
        #Queued, Downloading, Repairing, Unpacking, Failed, Complete
        self.__status = status

    def get_status(self):
        #returns a string of the current queued status
        return self.__status

    def get_nzo_id(self):
        return self.nzo_id

    def get_files(self):
        return self.__finished_files

    def set_download_report(self):
        if self.__avg_bps_total and self.__bytes_downloaded and self.__avg_bps_freq:
            #get the deltatime since the download started
            avg_bps = self.__avg_bps_total / self.__avg_bps_freq
            timecompleted = datetime.timedelta(seconds=self.__bytes_downloaded / (avg_bps*1024))

            seconds = timecompleted.seconds
            #find the total time including days
            totaltime = (timecompleted.days/86400) + seconds
            self.set_nzo_info('download_time',totaltime)

            #format the total time the download took, in days, hours, and minutes, or seconds.
            complete_time = format_time_string(seconds, timecompleted.days)

            self.set_unpack_info('Download', T('msg-DownloadedIn@2') %
                                 (complete_time, to_units(avg_bps*1024)), unique=True)



    def get_article(self, server):
        article = None
        nzf_remove_list = []

        for nzf in self.__files:
            # Don't try to get an article if server is in try_list of nzf
            if not nzf.server_in_try_list(server):
                if not nzf.import_finished:
                    nzf.finish_import()
                    # Still not finished? Something went wrong...
                    if not nzf.import_finished:
                        logging.error(Ta('error-qImport@1'), nzf)
                        nzf_remove_list.append(nzf)
                        continue

                article = nzf.get_article(server)
                if article:
                    break

        for nzf in nzf_remove_list:
            self.__files.remove(nzf)

        if article:
            return article
        else:
            # No articles for this server, block for next time
            self.add_to_try_list(server)
            return

    def move_top_bulk(self, nzf_ids):
        self.__cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            target = range(len(nzf_ids))

            while 1:
                self.move_up_bulk(nzf_ids, cleanup = False)

                pos_nzf_table = self.__build_pos_nzf_table(nzf_ids)

                keys = pos_nzf_table.keys()
                keys.sort()

                if target == keys:
                    break

    def move_bottom_bulk(self, nzf_ids):
        self.__cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            target = range(len(self.__files)-len(nzf_ids), len(self.__files))

            while 1:
                self.move_down_bulk(nzf_ids, cleanup = False)

                pos_nzf_table = self.__build_pos_nzf_table(nzf_ids)

                keys = pos_nzf_table.keys()
                keys.sort()

                if target == keys:
                    break

    def move_up_bulk(self, nzf_ids, cleanup = True):
        if cleanup:
            self.__cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            pos_nzf_table = self.__build_pos_nzf_table(nzf_ids)

            while pos_nzf_table:
                pos = min(pos_nzf_table)
                nzf = pos_nzf_table.pop(pos)

                if pos > 0:
                    tmp_nzf = self.__files[pos-1]
                    if tmp_nzf.nzf_id not in nzf_ids:
                        self.__files[pos-1] = nzf
                        self.__files[pos] = tmp_nzf

    def move_down_bulk(self, nzf_ids, cleanup = True):
        if cleanup:
            self.__cleanup_nzf_ids(nzf_ids)
        if nzf_ids:
            pos_nzf_table = self.__build_pos_nzf_table(nzf_ids)

            while pos_nzf_table:
                pos = max(pos_nzf_table)
                nzf = pos_nzf_table.pop(pos)

                if pos < len(self.__files)-1:
                    tmp_nzf = self.__files[pos+1]
                    if tmp_nzf.nzf_id not in nzf_ids:
                        self.__files[pos+1] = nzf
                        self.__files[pos] = tmp_nzf

    ## end nzo.Mutators #######################################################
    ###########################################################################
    def get_dirprefix(self):
        return self.__dirprefix[:]

    #def get_group(self):
    #    if self.__dirprefix:
    #        return self.__dirprefix[0]
    #    else:
    #        return ''

    def get_bytes_downloaded(self):
        return self.__bytes_downloaded

    def get_bytes(self):
        return self.__bytes

    def get_partable(self):
        return self.__partable.copy()

    def get_dirname(self):
        return self.__dirname

    def get_dirname_rename(self):
        return self.extra1

    def get_dirname_created(self):
        return self.__created

    def get_filename(self):
        return self.__filename

    #def get_cat(self):
    #    if self.__cat:
    #        return self.__cat
    #    else:
    #        return ''

    def get_group(self):
        if self.__group:
            return self.__group[0]
        else:
            return None

    def purge_data(self):
        for nzf in self.__files:
            sabnzbd.remove_data(nzf.nzf_id)

        for _set in self.__extrapars:
            for nzf in self.__extrapars[_set]:
                sabnzbd.remove_data(nzf.nzf_id)

        for nzf in self.__finished_files:
            sabnzbd.remove_data(nzf.nzf_id)

    def get_avg_date(self):
        return self.__avg_date

    def bytes(self):
        return self.__bytes

    def bytes_left(self):
        bytes = 0
        for _file in self.__files:
            bytes += _file.bytes_left()
        return bytes

    def gather_info(self, for_cli = False):
        bytes_left_all = 0

        active_files = []
        queued_files = []
        finished_files = []

        for _file in self.__finished_files:
            bytes = _file.bytes()
            filename = _file.get_filename()
            if not filename:
                filename = _file.get_subject()
            date = _file.get_date()
            if for_cli:
                date = time.mktime(date.timetuple())
            finished_files.append((0, bytes, filename, date))

        for _file in self.__files:
            bytes_left = _file.bytes_left()
            bytes = _file.bytes()
            filename = _file.get_filename()
            if not filename:
                filename = _file.get_subject()
            date = _file.get_date()
            if for_cli:
                date = time.mktime(date.timetuple())

            bytes_left_all += bytes_left
            active_files.append((bytes_left, bytes, filename, date,
                                 _file.nzf_id))

        for _set in self.__extrapars:
            for _file in self.__extrapars[_set]:
                bytes_left = _file.bytes_left()
                bytes = _file.bytes()
                filename = _file.get_filename()
                if not filename:
                    filename = _file.get_subject()
                date = _file.get_date()
                if for_cli:
                    date = time.mktime(date.timetuple())

                queued_files.append((_set, bytes_left, bytes, filename, date))

        avg_date = self.__avg_date
        if for_cli:
            avg_date = time.mktime(avg_date.timetuple())

        return (self.__repair, self.__unpack, self.__delete, self.__script,
                self.nzo_id, self.show_dir_name(), {},
                self.__msgid, self.__cat, self.__url,
                bytes_left_all, self.__bytes, avg_date,
                finished_files, active_files, queued_files, self.__status, self.__priority)

    def get_nzf_by_id(self, nzf_id):
        if nzf_id in self.__files_table:
            return self.__files_table[nzf_id]

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

    def get_unpack_info(self):
        return self.unpack_info

    def set_action_line(self, action, msg):
        if action and msg:
            self.action_line = '%s: %s' % (action, msg)
        else:
            self.action_line = ''

    def get_action_line(self):
        return self.action_line

    def set_fail_msg(self, msg):
        self.fail_msg = msg

    def get_fail_msg(self):
        return self.fail_msg

    def set_nzo_info(self, key, value):
        self.nzo_info[key] = value

    def get_nzo_info(self):
        return self.nzo_info

    def set_db_info(self, key, msg):
        self.nzo_info[key] = msg

    def get_repair_opts(self):
        return self.__repair, self.__unpack, self.__delete

    def get_pp(self):
        if self.__repair is None:
            return None
        else:
            return sabnzbd.opts_to_pp(self.__repair, self.__unpack, self.__delete)

    def get_script(self):
        return self.__script

    def get_cat(self):
        return self.__cat

    def get_future(self):
        return self.__url

    def get_md5pack(self, name):
        try:
            return self.md5packs[name]
        except:
            return None

    def set_md5pack(self, name, pack):
        self.md5packs[name] = pack

    def __build_pos_nzf_table(self, nzf_ids):
        pos_nzf_table = {}
        for nzf_id in nzf_ids:
            if nzf_id in self.__files_table:
                nzf = self.__files_table[nzf_id]
                pos = self.__files.index(nzf)
                pos_nzf_table[pos] = nzf

        return pos_nzf_table

    def __cleanup_nzf_ids(self, nzf_ids):
        for nzf_id in nzf_ids[:]:
            if nzf_id in self.__files_table:
                if self.__files_table[nzf_id] not in self.__files:
                    nzf_ids.remove(nzf_id)
            else:
                nzf_ids.remove(nzf_id)

    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['_TryList__try_list']
        return odict

    def __setstate__(self, _dict):
        self.__dict__.update(_dict)
        TryList.__init__(self)

    def __repr__(self):
        return "<NzbObject: filename=%s>" % self.__filename

#-------------------------------------------------------------------------------

def _nzf_get_filename(nzf):
    # Return filename, if the filename not set, try the
    # the full subject line instead. Can produce non-ideal results
    name = nzf.get_filename()
    if name:
        return name.lower()
    else:
        return nzf.get_subject().lower()


def _nzf_cmp_date(nzf1, nzf2):
    # Compare files based on date, but give vol-par files preference
    return _nzf_cmp_name(nzf1, nzf2, name=False)


def _nzf_cmp_name(nzf1, nzf2, name=True):
    # The comparison will sort .par2 files to the top of the queue followed by .rar files,
    # they will then be sorted by name.
    name1 = _nzf_get_filename(nzf1)
    name2 = _nzf_get_filename(nzf2)

    is_par1 = 'vol' in name1 and '.par2' in name1
    is_par2 = 'vol' in name2 and '.par2' in name2
    if is_par1 and not is_par2:
        return -1
    if is_par2 and not is_par1:
        return 1

    if name:
        # Prioritise .rar files above any other type of file (other than vol-par)
        # Useful for nzb streaming
        if  '.rar' in name1 and not is_par2 and '.rar' not in name2:
            return -1
        elif '.rar' in name2 and not is_par1 and '.rar' not in name1:
            return 1

        return cmp(name1, name2)
    else:
        # Do date comparision
        return cmp(nzf1.get_date(), nzf2.get_date())

#-------------------------------------------------------------------------------

################################################################################
# SplitFileName
#
# Isolate newzbin msgid from filename and remove ".nzb"
# Return (nice-name, msg-id)
################################################################################
def SplitFileName(name):
    name = name.strip()
    if name.find('://') < 0:
        m = RE_NEWZBIN.match(name)
        if (m):
            return m.group(2).rstrip('.').strip(), m.group(1)
        m = RE_NORMAL.match(name)
        if (m):
            return m.group(1).rstrip('.').strip(), ""
        else:
            return name.strip(), ""
        return "", ""
    else:
        return name.strip(), ""


def format_time_string(seconds, days=0):

    try:
        seconds = int(seconds)
    except:
        seconds = 0

    completestr = ''
    if days:
        completestr += '%s day%s ' % (days, s_returner(days))
    if (seconds/3600) >= 1:
        completestr += '%s hour%s ' % (seconds/3600, s_returner((seconds/3600)))
        seconds -= (seconds/3600)*3600
    if (seconds/60) >= 1:
        completestr += '%s minute%s ' % (seconds/60, s_returner((seconds/60)))
        seconds -= (seconds/60)*60
    if seconds > 0:
        completestr += '%s second%s ' % (seconds, s_returner(seconds))

    return completestr.strip()

def s_returner(value):
    if value > 1:
        return 's'
    else:
        return ''


RE_PASSWORD1 = re.compile(r'([^/\\]+)[/\\](.+)')
RE_PASSWORD2 = re.compile(r'(.+){{([^{}]+)}}$')
def scan_password(name):
    """ Get password (if any) from the title
    """
    if 'http://' in name or 'https://' in name:
        return name, None

    m = RE_PASSWORD1.search(name)
    if not m:
        m = RE_PASSWORD2.search(name)
    if m:
        return m.group(1).strip('. '), m.group(2).strip()
    else:
        return name.strip('. '), None
