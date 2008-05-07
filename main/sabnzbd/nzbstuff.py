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
sabnzbd.nzbstuff - misc
"""
import time
import re
import logging
import sabnzbd
import datetime
from sabnzbd.constants import *

from sabnzbd.trylist import TryList

RE_NEWZBIN = re.compile(r"msgid_(\w+) (.+)(\.nzb)", re.I)
RE_NORMAL  = re.compile(r"(.+)(\.nzb)", re.I)

HAVE_CELEMENTTREE = True
try:
    from xml.etree.cElementTree import XML
except ImportError:
    try:
        from cElementTree import XML
    except ImportError:
        from elementtree.ElementTree import XML
        HAVE_CELEMENTTREE = False

__NAME__ = "nzbstuff"

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
        if server.fillserver and not self.allow_fill_server:
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
    def __init__(self, date, subject, segments, nzo):
        TryList.__init__(self)

        # Private
        self.__date = date
        self.__subject = subject
        self.__filename = None
        self.__type = None

        match = re.search(SUBJECT_FN_MATCHER, subject)
        if match:
            self.__filename = match.group(1)

        self.__ispar2file = False
        self.__vol = None
        self.__blocks = None
        self.__setname = None
        self.__extrapars = None

        self.__initial_article = None

        self.__articles = []
        self.__decodetable = {}

        self.__bytes = 0
        self.__bytes_left = 0
        self.__article_count = 0

        # Public
        self.nzo = nzo
        self.nzf_id = sabnzbd.get_new_id("nzf")
        self.deleted = False

        self.valid = False
        self.import_finished = False

        # Do a lazy import
        article_db = {}
        for segment in segments:
            bytes = int(segment.get('bytes'))
            partnum = int(segment.get('number'))

            if partnum in article_db:
                if segment.text == article_db[partnum][0]:
                    logging.warning("[%s] Skipping duplicate article (%s)", __NAME__, segment.text)
                else:
                    logging.error("[%s] INCORRECT NZB: Duplicate part %s, but different ID-s (%s // %s)",
                                     __NAME__, partnum, article_db[partnum][0], segment.text)
                continue

            self.__bytes += bytes
            self.__bytes_left += bytes

            self.valid = True

            article_db[partnum] = (segment.text, bytes)

        if self.valid and self.nzf_id:
            sabnzbd.save_data(article_db, self.nzf_id)

    ## begin nzf.Mutators #####################################################
    ## excluding nzf.__try_list ###############################################
    def increase_article_count(self):
        self.__article_count += 1

    def finish_import(self):
        logging.info("[%s] Finishing import on %s", __NAME__, self.__subject)

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
# NzbObject                                                                    #
################################################################################
DTD = '{http://www.newzbin.com/DTD/2003/nzb}'
NZBFN_MATCHER = re.compile(r"msgid_\d*_(.*).nzb", re.I)
PROBABLY_PAR2_RE = re.compile(r'(.*)\.vol(\d*)\+(\d*)\.par2', re.I)

class NzbObject(TryList):
    def __init__(self, filename, pp, script, nzb = None,
                 futuretype = False, cat = None, url=None):
        TryList.__init__(self)

        if cat and pp == None:
            try:
                pp = sabnzbd.CFG['categories'][cat.lower()]['pp']
            except:
                pass
        if cat and script == None:
            try:
                script = sabnzbd.CFG['categories'][cat.lower()]['script']
            except:
                pass

        if pp == None and futuretype:
            r = u = d = None
        else:
            r, u, d = sabnzbd.pp_to_opts(pp)

        if script == None and not futuretype:
            script = sabnzbd.DIRSCAN_SCRIPT

        self.__filename = filename    # Original filename
        self.__dirname = filename
        self.__original_dirname = filename
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
        self.__group = None
        self.__avg_date = None
        self.__dirprefix = []

        self.__partable = {}
        self.__extrapars = {}

        self.__files = []
        self.__files_table = {}

        self.__finished_files = []

        self.__unpackstrht = {}

        #the current status of the nzo eg:
        #Queued, Downloading, Repairing, Unpacking, Failed, Complete
        self.__status = "Queued"
        self.__avg_bps_freq = 0
        self.__avg_bps_total = 0

        self.__dupe_table = {}

        self.saved_articles = []

        self.nzo_id = None

        self.futuretype = futuretype
        self.deleted = False
        self.parsed = False

        self.create_group_folder = sabnzbd.CREATE_GROUP_FOLDERS

        match_result = re.search(NZBFN_MATCHER, filename)
        if match_result:
            self.__dirname = match_result.group(1)

        # Remove leading msgid_XXXX and trailing .nzb
        self.__dirname, msgid = SplitFileName(self.__dirname)
        self.__original_dirname = self.__dirname
        if sabnzbd.REPLACE_SPACES:
            self.__dirname = self.__dirname.replace(' ','_')
            self.__original_dirname = self.__dirname
            logging.info('[%s] Replacing spaces with underscores in %s', __NAME__, self.__dirname)

        if not nzb:
            # This is a slot for a future NZB, ready now
            return

        try:
            root = XML(nzb)
        except:
            logging.warning("[%s] Incorrect NZB file %s (trying anyway)", __NAME__, filename)

        try:
            root
        except:
            logging.error("[%s] Invalid NZB file %s, skipping", __NAME__, filename)
            raise ValueError

        sabnzbd.backup_nzb(filename, nzb)

        avg_age = 0
        valids = 0
        found = 0
        for _file in root:
            if not self.__group:
                groups = _file.find('%sgroups' % DTD)
                if not groups:
                    groups = _file.find('groups')
                self.__group = groups[0].text
            subject = _file.get('subject')

            if isinstance(subject, unicode):
                subject = subject.encode('utf-8')

            try:
                t = int(_file.get('date'))
            except:
                # NZB has non-standard timestamp, assume 1
                t = 1
            date = datetime.datetime.fromtimestamp(t)

            segments = _file.find('%ssegments' % DTD)
            if not segments:
                segments = _file.find('segments')
            nzf = NzbFile(date, subject, segments, self)

            if nzf.valid and nzf.nzf_id:
                found = 0
                fln = None
                if sabnzbd.IGNORE_SAMPLES:
                    if (nzf.get_filename()):
                        fln = nzf.get_filename()
                        fln = fln.lower()
                    else:
                        fln = nzf.get_subject()
                        fln = fln.lower()

                    for ignore in IGNORE_SAMPLE_LIST:
                        if ignore in fln:
                            found = 1
                            break

                if found:
                    if nzf.nzf_id:
                        logging.debug("[%s] Sample file found in file: %s, removing: %s." % (__NAME__,fln,nzf.nzf_id))
                        sabnzbd.remove_data(nzf.nzf_id)
                else:
                    logging.info('[%s] %s added to queue', __NAME__, subject)
                    avg_age += t
                    valids += 1
                    self.__files_table[nzf.nzf_id] = nzf
                    self.__bytes += nzf.bytes()
                    self.__files.append(nzf)

            else:
                logging.info('[%s] Error importing %s, skipping', __NAME__,
                             subject)
                if nzf.nzf_id:
                    sabnzbd.remove_data(nzf.nzf_id)

        if sabnzbd.CREATE_GROUP_FOLDERS:
            self.__dirprefix.append(self.__group)

        if sabnzbd.CREATE_CAT_FOLDERS and cat:
            self.__dirprefix.append(cat)

        self.__avg_date = datetime.datetime.fromtimestamp(avg_age / valids)


        if sabnzbd.AUTO_SORT:
            self.__files.sort(cmp=_nzf_cmp_date)
        else:
            self.__files.sort(cmp=_nzf_cmp_name)

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

    def remove_article(self, article):
        nzf = article.nzf
        file_done, reset = nzf.remove_article(article)

        if file_done:
            self.remove_nzf(nzf)

        if reset:
            self.reset_try_list()

        ## Special treatment for first part
        if article.partnum == nzf.lowest_partnum():
            fn = nzf.get_filename()
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
            self.set_status("Queued")
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


    def get_original_dirname(self):
        return self.__original_dirname

    def add_parfile(self, parfile):
        self.__files.append(parfile)
        parfile.remove_extrapar(parfile)

    def remove_parset(self, setname):
        self.__partable.pop(setname)

    def set_unpackstr(self, msg, action, stage):
        if stage not in self.__unpackstrht:
            self.__unpackstrht[stage] = {}
        self.__unpackstrht[stage][action] = msg

    def set_status(self, status):
        #sets a string outputting the current status of the job, eg:
        #Queued, Downloading, Repairing, Unpacking, Failed, Complete
        self.__status = status

    def get_status(self):
        #returns a string of the current history status
        return self.__status


    def set_download_report(self):
        if self.__avg_bps_total and self.__bytes_downloaded and self.__avg_bps_freq:
            #get the deltatime since the download started
            avg_bps = self.__avg_bps_total / self.__avg_bps_freq
            timecompleted = datetime.timedelta(seconds=self.__bytes_downloaded / (avg_bps*1024))
    
            seconds = timecompleted.seconds
            #find the total time including days
            totaltime = (timecompleted.days/86400) + seconds
    
            #format the total time the download took, in days, hours, and minutes, or seconds.
            completestr = ''
            if timecompleted.days:
                completestr += '%s day%s ' % (timecompleted.days, self.s_returner(timecompleted.days))
            if (seconds/3600) >= 1:
                completestr += '%s hour%s ' % (seconds/3600, self.s_returner((seconds/3600)))
                seconds -= (seconds/3600)*3600
            if (seconds/60) >= 1:
                completestr += '%s minute%s ' % (seconds/60, self.s_returner((seconds/60)))
                seconds -= (seconds/60)*60
            if seconds > 0:
                completestr += '%s second%s ' % (seconds, self.s_returner(seconds))
            #message 1 - total time
            completemsg = '%s' % (completestr)
            self.set_unpackstr(completemsg, '[Time-Taken]', 0)
            #message 2 - average speed
            completemsg = '%0.fkB/s' % (avg_bps)
            self.set_unpackstr(completemsg, '[Avg-Speed]', 0)


    def s_returner(self, value):
        if value > 1:
            return 's'
        else:
            return ''

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
                        logging.error("[%s] Error importing %s", __NAME__, nzf)
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

    def get_bytes_downloaded(self):
        return self.__bytes_downloaded

    def get_partable(self):
        return self.__partable.copy()

    def get_dirname(self):
        return self.__dirname

    def get_dirname_created(self):
        return self.__created

    def get_filename(self):
        return self.__filename

    def get_cat(self):
        if self.__cat:
            return self.__cat
        else:
            return ''

    def get_group(self):
        return self.__group

    def purge_data(self):
        nzf_ids = []

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
                self.nzo_id, self.__filename, self.__unpackstrht.copy(),
                self.__msgid, self.__cat, self.__url,
                bytes_left_all, self.__bytes, avg_date,
                finished_files, active_files, queued_files, self.__status)

    def get_nzf_by_id(self, nzf_id):
        if nzf_id in self.__files_table:
            return self.__files_table[nzf_id]

    def get_unpackstrht(self):
        return self.__unpackstrht.copy()

    def get_repair_opts(self):
        return self.__repair, self.__unpack, self.__delete

    def get_script(self):
        return self.__script

    def get_cat(self):
        return self.__cat

    def get_future(self):
        return self.__url

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

def _nzf_cmp_date(nzf1, nzf2):
    subject1 = nzf1.get_subject().lower()
    subject2 = nzf2.get_subject().lower()

    par2_found = 0
    ret = 0
    if 'vol' in subject1 and '.par2' in subject1:
        par2_found += 1
        ret -= 1

    if 'vol' in subject2 and '.par2' in subject2:
        par2_found += 1
        ret += 1

    if '.rar' in subject1 and not '.par' in subject2 and not '.rar' in subject2: #some nzbs dont get filename field populated, using subject instead
        return -1 #nzf1 contained '.rar' nzf2 didnt. Move nzf1 up in the queue

    if par2_found == 1:
        return ret
    else:
        return cmp(nzf1.get_date(), nzf2.get_date())

def _nzf_cmp_name(nzf1, nzf2):
    subject1 = nzf1.get_subject().lower()
    subject2 = nzf2.get_subject().lower()

    par2_found = 0
    ret = 0
    if 'vol' in subject1 and '.par2' in subject1:
        par2_found += 1
        ret -= 1

    if 'vol' in subject2 and '.par2' in subject2:
        par2_found += 1
        ret += 1

    if '.rar' in subject1 and not '.par' in subject2 and not '.rar' in subject2: #some nzbs dont get filename field populated, using subject instead
        return -1 #nzf1 contained '.rar' nzf2 didnt. Move nzf1 up in the queue

    if par2_found == 1:
        return ret
    else:
        return cmp(subject1, subject2)

#-------------------------------------------------------------------------------

################################################################################
# SplitFileName
#
# Isolate newzbin msgid from filename and remove ".nzb"
# Return (nice-name, msg-id)
################################################################################
def SplitFileName(name):
    m = RE_NEWZBIN.match(name)
    if (m):
        return m.group(2).rstrip('.').strip(), m.group(1)
    m = RE_NORMAL.match(name)
    if (m):
        return m.group(1).rstrip('.').strip(), ""
    else:
        return name.strip(), ""
    return "", ""


