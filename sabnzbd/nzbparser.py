#!/usr/bin/python3 -OO
# Copyright 2008-2017 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.nzbparser - Parse and import NZB files
"""
import bz2
import gzip
import re
import io
import time
import logging
import hashlib
import html
import xml.etree.ElementTree
import datetime
from typing import Optional, Dict, Any, Union

import sabnzbd
from sabnzbd import filesystem, nzbstuff
from sabnzbd.encoding import utob, correct_unknown_encoding
from sabnzbd.filesystem import is_archive, get_filename
from sabnzbd.misc import name_to_cat


class RegexException(Exception):
    def __init__(self, message):
        super().__init__(message)


class LineFeeder:
    """Split lines by \r or \n"""

    def __init__(self, reader):
        self.reader = reader
        self.linecache = []
        self.regex = re.compile(r"[\r\n]+")

    def __iter__(self):
        return self

    def __next__(self):
        if not self.linecache:
            line = self.reader.readline()
            if not line:
                raise StopIteration
            self.linecache = self.regex.split(line)
            # Remove empty element after last line break
            if len(self.linecache) > 1:
                self.linecache.pop()
        if self.linecache:
            return self.linecache.pop(0)
        else:
            raise StopIteration

    def readline(self):
        return self.__next__()


def nzbfile_parser(raw_data: str, nzo):
    # For type-hinting
    nzo: sabnzbd.nzbstuff.NzbObject

    # Try regex parser
    if nzbfile_regex_parser(raw_data, nzo):
        return

    # Load data as file-object
    raw_data = re.sub(r"""\s(xmlns="[^"]+"|xmlns='[^']+')""", "", raw_data, count=1)
    nzb_tree = xml.etree.ElementTree.fromstring(raw_data)

    # Hash for dupe-checking
    md5sum = hashlib.md5()

    # Average date
    avg_age_sum = 0

    # In case of failing timestamps and failing files
    time_now = time.time()
    skipped_files = 0
    valid_files = 0

    # Parse the header
    if nzb_tree.find("head"):
        for meta in nzb_tree.find("head").iter("meta"):
            meta_type = meta.attrib.get("type")
            if meta_type and meta.text:
                # Meta tags can occur multiple times
                if meta_type not in nzo.meta:
                    nzo.meta[meta_type] = []
                nzo.meta[meta_type].append(meta.text)
    logging.debug("NZB file meta-data = %s", nzo.meta)

    # Parse the files
    for file in nzb_tree.iter("file"):
        # Get subject and date
        file_name = ""
        if file.attrib.get("subject"):
            file_name = file.attrib.get("subject")

        # Don't fail if no date present
        try:
            file_date = datetime.datetime.fromtimestamp(int(file.attrib.get("date")))
            file_timestamp = int(file.attrib.get("date"))
        except:
            file_date = datetime.datetime.fromtimestamp(time_now)
            file_timestamp = time_now

        # Get group
        for group in file.iter("group"):
            if group.text not in nzo.groups:
                nzo.groups.append(group.text)

        # Get segments
        raw_article_db = {}
        file_bytes = 0
        if file.find("segments"):
            for segment in file.find("segments").iter("segment"):
                try:
                    article_id = segment.text
                    segment_size = int(segment.attrib.get("bytes"))
                    partnum = int(segment.attrib.get("number"))

                    # Update hash
                    md5sum.update(utob(article_id))

                    # Duplicate parts?
                    if partnum in raw_article_db:
                        if article_id != raw_article_db[partnum][0]:
                            logging.info(
                                "Duplicate part %s, but different ID-s (%s // %s)",
                                partnum,
                                raw_article_db[partnum][0],
                                article_id,
                            )
                            nzo.increase_bad_articles_counter("duplicate_articles")
                        else:
                            logging.info("Skipping duplicate article (%s)", article_id)
                    elif segment_size <= 0 or segment_size >= 2 ** 23:
                        # Perform sanity check (not negative, 0 or larger than 8MB) on article size
                        # We use this value later to allocate memory in cache and sabyenc
                        logging.info("Skipping article %s due to strange size (%s)", article_id, segment_size)
                        nzo.increase_bad_articles_counter("bad_articles")
                    else:
                        raw_article_db[partnum] = (article_id, segment_size)
                        file_bytes += segment_size
                except:
                    # In case of missing attributes
                    pass

        # Sort the articles by part number, compatible with Python 3.5
        raw_article_db_sorted = [raw_article_db[partnum] for partnum in sorted(raw_article_db)]

        # Create NZF
        nzf = sabnzbd.nzbstuff.NzbFile(file_date, file_name, raw_article_db_sorted, file_bytes, nzo)

        # Check if we already have this exact NZF (see custom eq-checks)
        if nzf in nzo.files:
            logging.info("File %s occured twice in NZB, skipping", nzf.filename)
            continue

        # Add valid NZF's
        if file_name and nzf.valid and nzf.nzf_id:
            logging.info("File %s added to queue", nzf.filename)
            nzo.files.append(nzf)
            nzo.files_table[nzf.nzf_id] = nzf
            nzo.bytes += nzf.bytes
            valid_files += 1
            avg_age_sum += file_timestamp
        else:
            logging.info("Error importing %s, skipping", file_name)
            if nzf.nzf_id:
                sabnzbd.remove_data(nzf.nzf_id, nzo.admin_path)
            skipped_files += 1

    # Final bookkeeping
    nr_files = max(1, valid_files)
    nzo.avg_stamp = avg_age_sum / nr_files
    nzo.avg_date = datetime.datetime.fromtimestamp(avg_age_sum / nr_files)
    nzo.md5sum = md5sum.hexdigest()

    if skipped_files:
        logging.warning(T("Failed to import %s files from %s"), skipped_files, nzo.filename)


def nzbfile_regex_parser(raw_data: str, nzo):
    # Hash for dupe-checking
    md5sum = hashlib.md5()

    # Average date
    avg_age_sum = 0

    # In case of failing timestamps and failing files
    time_now = time.time()
    valid_files = 0

    success = 0

    # Header and end
    encoding_re = re.compile(r'<\?xml [^>]*encoding="([^"]*)"')
    meta_re = re.compile(r'^\s*<meta type="([^"]*)">([^<]*)</meta>\s*$')
    nzbtag_re = re.compile(r"^\s*<nzb[^>]*>\s*$")
    endnzb_re = re.compile(r"^\s*</nzb>\s*$")

    # Main part
    group_re = re.compile(r"^\s*(?:<groups>\s*|)<group>([^<]*)</group>(?:\s*</groups>|)\s*$")
    file_re = re.compile(r"^\s*<file([^>]*)>\s*$")
    fileend_re = re.compile(r"^\s*</file>\s*$")
    segment_re = re.compile(r"^\s*<segment( [^>]*)>([^<]*)</segment>\s*$")
    ignorable_re = re.compile(r"^\s*(?:</?segments>|</?groups>|</?head>)\s*$")

    # Sub parts of <file>
    subject_re = re.compile(r' subject="([^"]*)"')
    date_re = re.compile(r' date="([^"]*)"')

    # Sub parts of <segment>
    bytes_re = re.compile(r' bytes="([^"]*)"')
    number_re = re.compile(r' number="([^"]*)"')

    # Misc
    comment_re = re.compile(r"<!--[^<>]*-->")
    whitespace_re = re.compile(r"^\s*$")

    try:
        reader = LineFeeder(io.StringIO(raw_data))
        open_file_tag = 0
        linecount = 0
        res = 0
        header = ""

        # Read header data until <nzb tag
        while not res:
            line = reader.readline()
            linecount += 1
            if linecount > 20:
                raise RegexException("Could not find <nzb tag in header: %s" % header)
            if not line:
                continue
            header += line
            line = re.sub(comment_re, "", line)
            res = nzbtag_re.search(line)

        # Get encoding (sanity check)
        res = encoding_re.search(header)
        if not res:
            raise RegexException("Could not find encoding in header: %s" % header)

        # Read the rest of the file
        for line in reader:
            linecount += 1
            if not line:
                continue

            line = re.sub(comment_re, "", line)

            # <segment bytes="100" number="1">articleid</segment>
            res = segment_re.search(line)
            if res:
                if not open_file_tag:
                    raise RegexException("Found segment without file tag at line %s: %s" % (linecount, line))
                article_id = html.unescape(res.group(2))
                segment_size = int(bytes_re.search(res.group(1)).group(1))
                partnum = int(number_re.search(res.group(1)).group(1))

                # Update hash
                md5sum.update(utob(article_id))

                # Duplicate parts?
                if partnum in raw_article_db:
                    if article_id != raw_article_db[partnum][0]:
                        raise RegexException(
                            "Duplicate part %s, but different ID-s (%s // %s)"
                            % (partnum, raw_article_db[partnum][0], article_id)
                        )
                    else:
                        raise RegexException("Duplicate article (%s)" % article_id)
                elif segment_size <= 0 or segment_size >= 2 ** 23:
                    # Perform sanity check (not negative, 0 or larger than 8MB) on article size
                    # We use this value later to allocate memory in cache and sabyenc
                    raise RegexException(
                        "Article %s at line %s has strange size (%s): %s" % (article_id, linecount, segment_size, line)
                    )
                else:
                    raw_article_db[partnum] = (article_id, segment_size)
                    file_bytes += segment_size
                    continue

            # <group>a.b.a</group>
            res = group_re.search(line)
            if res:
                if res.group(1) not in nzo.groups:
                    nzo.groups.append(res.group(1))
                continue

            # </file>
            res = fileend_re.search(line)
            if res:
                if open_file_tag:
                    open_file_tag = 0
                else:
                    raise RegexException("Found closing file tag without start at line %s: %s" % (linecount, line))

                if not file_name:
                    raise RegexException("Found closing file tag with no file_name at line %s: %s" % (linecount, line))

                # Sort the articles by part number, compatible with Python 3.5
                raw_article_db_sorted = [raw_article_db[partnum] for partnum in sorted(raw_article_db)]

                # Create NZF
                nzf = sabnzbd.nzbstuff.NzbFile(file_date, file_name, raw_article_db_sorted, file_bytes, nzo)

                # Check if we already have this exact NZF (see custom eq-checks)
                if nzf in nzo.files:
                    logging.info("File %s occured twice in NZB, skipping", nzf.filename)
                    continue

                # Add valid NZF's
                if nzf.valid and nzf.nzf_id:
                    logging.info("File %s added to queue", nzf.filename)
                    nzo.files.append(nzf)
                    nzo.files_table[nzf.nzf_id] = nzf
                    nzo.bytes += nzf.bytes
                    valid_files += 1
                    avg_age_sum += file_timestamp
                    continue
                else:
                    raise RegexException(
                        "Found closing file tag with invalid nzf (valid %s, nzf_id %s) at line %s: %s"
                        % (nzf.valid, nzf.nzf_id, linecount, line)
                    )

            # <file>
            res = file_re.search(line)
            if res:
                if open_file_tag:
                    raise RegexException(
                        "Found open file tag when already in a file at line %s: %s" % (linecount, line)
                    )
                else:
                    open_file_tag = 1

                raw_article_db = {}
                file_bytes = 0

                file_name = html.unescape(subject_re.search(res.group(1)).group(1))
                tmpdate = date_re.search(res.group(1))
                # Don't fail if no date present
                try:
                    file_date = datetime.datetime.fromtimestamp(int(tmpdate.group(1)))
                    file_timestamp = int(tmpdate.group(1))
                except:
                    file_date = datetime.datetime.fromtimestamp(time_now)
                    file_timestamp = time_now
                continue

            # Junk
            res = ignorable_re.search(line)
            if res:
                continue

            # <meta type="password">password123</meta>
            res = meta_re.search(line)
            if res:
                # logging.debug("Got meta")
                meta_type = res.group(1)
                meta_text = html.unescape(res.group(2))
                if meta_type and meta_text:
                    # Meta tags can occur multiple times
                    if meta_type not in nzo.meta:
                        nzo.meta[meta_type] = []
                    nzo.meta[meta_type].append(meta_text)
                continue

            res = whitespace_re.search(line)
            if res:
                continue

            # </nzb>
            res = endnzb_re.search(line)
            if res:
                if open_file_tag:
                    raise RegexException("Found closing <nzb tag while in file at line %s: %s" % (linecount, line))
                success = 1
                break

            # raise RegexException("Unrecognized line #%s: %s (%s)" % (linecount, line, binascii.hexlify(line.encode())))
            raise RegexException("Unrecognized line #%s: %s" % (linecount, line))
    except StopIteration as e:
        logging.debug("Regex parsing: Unexpected end of file %s at line %d", nzo.filename, linecount)
    except (RegexException, IndexError, AttributeError) as e:
        logging.debug("Regex parsing: %s failed: %s", nzo.filename, e)

    if success:
        # Final bookkeeping
        logging.debug("Regex parsing: Read %d lines. NZB Meta-data = %s", linecount, nzo.meta)
        nr_files = max(1, valid_files)
        nzo.avg_stamp = avg_age_sum / nr_files
        nzo.avg_date = datetime.datetime.fromtimestamp(avg_age_sum / nr_files)
        nzo.md5sum = md5sum.hexdigest()
        return True
    else:
        # Remove all data added to the nzo
        for nzf in nzo.files:
            nzf.remove_admin()
        nzo.first_articles = []
        nzo.first_articles_count = 0
        nzo.bytes_par2 = 0
        nzo.files = []
        nzo.files_table = {}
        nzo.bytes = 0
        return False


def process_nzb_archive_file(
    filename: str,
    path: str,
    pp: Optional[int] = None,
    script: Optional[str] = None,
    cat: Optional[str] = None,
    catdir: Optional[str] = None,
    keep: bool = False,
    priority: Optional[Union[int, str]] = None,
    nzbname: Optional[str] = None,
    reuse: Optional[str] = None,
    nzo_info: Optional[Dict[str, Any]] = None,
    dup_check: bool = True,
    url: Optional[str] = None,
    password: Optional[str] = None,
    nzo_id: Optional[str] = None,
):
    """Analyse ZIP file and create job(s).
    Accepts ZIP files with ONLY nzb/nfo/folder files in it.
    returns (status, nzo_ids)
        status: -1==Error, 0==OK, 1==Ignore
    """
    nzo_ids = []
    if catdir is None:
        catdir = cat

    filename, cat = name_to_cat(filename, catdir)
    # Returns -1==Error/Retry, 0==OK, 1==Ignore
    status, zf, extension = is_archive(path)

    if status != 0:
        return status, []

    status = 1
    names = zf.namelist()
    nzbcount = 0
    for name in names:
        name = name.lower()
        if name.endswith(".nzb"):
            status = 0
            nzbcount += 1

    if status == 0:
        if nzbcount != 1:
            nzbname = None
        for name in names:
            if name.lower().endswith(".nzb"):
                try:
                    data = correct_unknown_encoding(zf.read(name))
                except OSError:
                    logging.error(T("Cannot read %s"), name, exc_info=True)
                    zf.close()
                    return -1, []
                name = filesystem.setname_from_path(name)
                if data:
                    nzo = None
                    try:
                        nzo = nzbstuff.NzbObject(
                            name,
                            pp=pp,
                            script=script,
                            nzb_data=data,
                            cat=cat,
                            url=url,
                            priority=priority,
                            nzbname=nzbname,
                            nzo_info=nzo_info,
                            reuse=reuse,
                            dup_check=dup_check,
                        )
                        if not nzo.password:
                            nzo.password = password
                    except (TypeError, ValueError):
                        # Duplicate or empty, ignore
                        pass
                    except:
                        # Something else is wrong, show error
                        logging.error(T("Error while adding %s, removing"), name, exc_info=True)

                    if nzo:
                        if nzo_id:
                            # Re-use existing nzo_id, when a "future" job gets it payload
                            sabnzbd.NzbQueue.remove(nzo_id, delete_all_data=False)
                            nzo.nzo_id = nzo_id
                            nzo_id = None
                        nzo_ids.append(sabnzbd.NzbQueue.add(nzo))
                        nzo.update_rating()
        zf.close()
        try:
            if not keep:
                filesystem.remove_file(path)
        except OSError:
            logging.error(T("Error removing %s"), filesystem.clip_path(path))
            logging.info("Traceback: ", exc_info=True)
    else:
        zf.close()
        status = 1

    return status, nzo_ids


def process_single_nzb(
    filename: str,
    path: str,
    pp: Optional[int] = None,
    script: Optional[str] = None,
    cat: Optional[str] = None,
    catdir: Optional[str] = None,
    keep: bool = False,
    priority: Optional[Union[int, str]] = None,
    nzbname: Optional[str] = None,
    reuse: Optional[str] = None,
    nzo_info: Optional[Dict[str, Any]] = None,
    dup_check: bool = True,
    url: Optional[str] = None,
    password: Optional[str] = None,
    nzo_id: Optional[str] = None,
):
    """Analyze file and create a job from it
    Supports NZB, NZB.BZ2, NZB.GZ and GZ.NZB-in-disguise
    returns (status, nzo_ids)
        status: -2==Error/retry, -1==Error, 0==OK
    """
    nzo_ids = []
    if catdir is None:
        catdir = cat

    try:
        with open(path, "rb") as nzb_file:
            check_bytes = nzb_file.read(2)

        if check_bytes == b"\x1f\x8b":
            # gzip file or gzip in disguise
            filename = filename.replace(".nzb.gz", ".nzb")
            nzb_reader_handler = gzip.GzipFile
        elif check_bytes == b"BZ":
            # bz2 file or bz2 in disguise
            filename = filename.replace(".nzb.bz2", ".nzb")
            nzb_reader_handler = bz2.BZ2File
        else:
            nzb_reader_handler = open

        # Let's get some data and hope we can decode it
        with nzb_reader_handler(path, "rb") as nzb_file:
            data = correct_unknown_encoding(nzb_file.read())

    except OSError:
        logging.warning(T("Cannot read %s"), filesystem.clip_path(path))
        logging.info("Traceback: ", exc_info=True)
        return -2, nzo_ids

    if filename:
        filename, cat = name_to_cat(filename, catdir)
        # The name is used as the name of the folder, so sanitize it using folder specific santization
        if not nzbname:
            # Prevent embedded password from being damaged by sanitize and trimming
            nzbname = get_filename(filename)

    try:
        nzo = nzbstuff.NzbObject(
            filename,
            pp=pp,
            script=script,
            nzb_data=data,
            cat=cat,
            url=url,
            priority=priority,
            nzbname=nzbname,
            nzo_info=nzo_info,
            reuse=reuse,
            dup_check=dup_check,
        )
        if not nzo.password:
            nzo.password = password
    except TypeError:
        # Duplicate, ignore
        if nzo_id:
            sabnzbd.NzbQueue.remove(nzo_id)
        nzo = None
    except ValueError:
        # Empty
        return 1, nzo_ids
    except:
        if data.find("<nzb") >= 0 > data.find("</nzb"):
            # Looks like an incomplete file, retry
            return -2, nzo_ids
        else:
            # Something else is wrong, show error
            logging.error(T("Error while adding %s, removing"), filename, exc_info=True)
            return -1, nzo_ids

    if nzo:
        if nzo_id:
            # Re-use existing nzo_id, when a "future" job gets it payload
            sabnzbd.NzbQueue.remove(nzo_id, delete_all_data=False)
            nzo.nzo_id = nzo_id
        nzo_ids.append(sabnzbd.NzbQueue.add(nzo, quiet=bool(reuse)))
        nzo.update_rating()

    try:
        if not keep:
            filesystem.remove_file(path)
    except OSError:
        # Job was still added to the queue, so throw error but don't report failed add
        logging.error(T("Error removing %s"), filesystem.clip_path(path))
        logging.info("Traceback: ", exc_info=True)

    return 0, nzo_ids
