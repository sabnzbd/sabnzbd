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
import os
import bz2
import gzip
import time
import logging
import hashlib
import xml.etree.ElementTree
import datetime
import zipfile
import tempfile
import cherrypy._cpreqbody
from typing import Optional, Dict, Any, Union, List, Tuple

import sabnzbd
from sabnzbd import nzbstuff
from sabnzbd.encoding import utob, correct_unknown_encoding, hardcore_correct_unknown_encoding
from sabnzbd.filesystem import (
    get_filename,
    is_valid_script,
    get_ext,
    clip_path,
    remove_file,
    remove_data,
)
from sabnzbd.misc import name_to_cat
from sabnzbd.constants import DEFAULT_PRIORITY, VALID_ARCHIVES
from sabnzbd.utils import rarfile


def add_nzbfile(
    nzbfile: Union[str, cherrypy._cpreqbody.Part],
    pp: Optional[Union[int, str]] = None,
    script: Optional[str] = None,
    cat: Optional[str] = None,
    catdir: Optional[str] = None,
    priority: Optional[Union[int, str]] = DEFAULT_PRIORITY,
    nzbname: Optional[str] = None,
    nzo_info=None,
    url: Optional[str] = None,
    keep: Optional[bool] = None,
    reuse: Optional[str] = None,
    password: Optional[str] = None,
    nzo_id: Optional[str] = None,
):
    """Add file, either a single NZB-file or an archive.
    All other parameters are passed to the NZO-creation.
    """
    if pp == "-1":
        pp = None
    if script and (script.lower() == "default" or not is_valid_script(script)):
        script = None
    if cat and cat.lower() == "default":
        cat = None

    if isinstance(nzbfile, str):
        # File coming from queue repair or local file-path
        path = nzbfile
        filename = os.path.basename(path)
        keep_default = True
        if not sabnzbd.WIN32:
            # If windows client sends file to Unix server backslashes may
            # be included, so convert these
            path = path.replace("\\", "/")
        logging.info("Attempting to add %s [%s]", filename, path)
    else:
        # File from file-upload object
        # CherryPy mangles unicode-filenames: https://github.com/cherrypy/cherrypy/issues/1766
        filename = hardcore_correct_unknown_encoding(nzbfile.filename)
        logging.info("Attempting to add %s", filename)
        keep_default = False
        try:
            # We have to create a copy, because we can't re-use the CherryPy temp-file
            # Just to be sure we add the extension to detect file type later on
            nzb_temp_file, path = tempfile.mkstemp(suffix=get_ext(filename))
            os.write(nzb_temp_file, nzbfile.file.read())
            os.close(nzb_temp_file)
        except OSError:
            logging.error(T("Cannot create temp file for %s"), filename)
            logging.info("Traceback: ", exc_info=True)
            return None
        finally:
            # Close the CherryPy reference
            nzbfile.file.close()

    # Externally defined if we should keep the file?
    if keep is None:
        keep = keep_default

    if get_ext(filename) in VALID_ARCHIVES:
        return process_nzb_archive_file(
            filename,
            path=path,
            pp=pp,
            script=script,
            cat=cat,
            catdir=catdir,
            priority=priority,
            nzbname=nzbname,
            keep=keep,
            reuse=reuse,
            nzo_info=nzo_info,
            url=url,
            password=password,
            nzo_id=nzo_id,
        )
    else:
        return process_single_nzb(
            filename,
            path=path,
            pp=pp,
            script=script,
            cat=cat,
            catdir=catdir,
            priority=priority,
            nzbname=nzbname,
            keep=keep,
            reuse=reuse,
            nzo_info=nzo_info,
            url=url,
            password=password,
            nzo_id=nzo_id,
        )


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
) -> Tuple[int, List[str]]:
    """Analyse archive and create job(s).
    Accepts archive files with ONLY nzb/nfo/folder files in it.
    returns (status, nzo_ids)
        status: -2==Error/retry, -1==Error, 0==OK, 1==No files found
    """
    nzo_ids = []
    if catdir is None:
        catdir = cat
    filename, cat = name_to_cat(filename, catdir)

    try:
        if zipfile.is_zipfile(path):
            zf = zipfile.ZipFile(path)
        elif rarfile.is_rarfile(path):
            zf = rarfile.RarFile(path)
        elif sabnzbd.newsunpack.is_sevenfile(path):
            zf = sabnzbd.newsunpack.SevenZip(path)
        else:
            logging.info("File %s is not a supported archive!", filename)
            return -1, []
    except:
        logging.info(T("Cannot read %s"), path, exc_info=True)
        return -2, []

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
                    datap = zf.open(name)
                except OSError:
                    logging.error(T("Cannot read %s"), name, exc_info=True)
                    zf.close()
                    return -1, []
                name = get_filename(name)
                if datap:
                    nzo = None
                    try:
                        nzo = nzbstuff.NzbObject(
                            name,
                            pp=pp,
                            script=script,
                            nzb_fp=datap,
                            cat=cat,
                            url=url,
                            priority=priority,
                            nzbname=nzbname,
                            nzo_info=nzo_info,
                            reuse=reuse,
                            nzo_id=nzo_id,
                            dup_check=dup_check,
                        )
                        if not nzo.password:
                            nzo.password = password
                    except (sabnzbd.nzbstuff.NzbEmpty, sabnzbd.nzbstuff.NzbRejected):
                        # Empty or fully rejected
                        pass
                    except sabnzbd.nzbstuff.NzbRejectedToHistory as err:
                        # Duplicate or unwanted extension that was failed to history
                        nzo_ids.append(err.nzo_id)
                    except:
                        # Something else is wrong, show error
                        logging.error(T("Error while adding %s, removing"), name, exc_info=True)
                    finally:
                        datap.close()

                    if nzo:
                        # We can only use existing nzo_id once
                        nzo_id = None
                        nzo_ids.append(sabnzbd.NzbQueue.add(nzo))

        # Close the pointer to the compressed file
        zf.close()

        try:
            if not keep:
                remove_file(path)
        except OSError:
            logging.error(T("Error removing %s"), clip_path(path))
            logging.info("Traceback: ", exc_info=True)
    else:
        zf.close()

    # If all were rejected/empty/etc, update status
    if not nzo_ids:
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
) -> Tuple[int, List[str]]:
    """Analyze file and create a job from it
    Supports NZB, NZB.BZ2, NZB.GZ and GZ.NZB-in-disguise
    returns (status, nzo_ids)
        status: -2==Error/retry, -1==Error, 0==OK
    """
    if catdir is None:
        catdir = cat

    try:
        with open(path, "rb") as nzb_file:
            check_bytes = nzb_file.read(2)

        if check_bytes == b"\x1f\x8b":
            # gzip file or gzip in disguise
            filename = filename.replace(".nzb.gz", ".nzb")
            nzb_fp = gzip.GzipFile(path, "rb")
        elif check_bytes == b"BZ":
            # bz2 file or bz2 in disguise
            filename = filename.replace(".nzb.bz2", ".nzb")
            nzb_fp = bz2.BZ2File(path, "rb")
        else:
            nzb_fp = open(path, "rb")

    except OSError:
        logging.warning(T("Cannot read %s"), clip_path(path))
        logging.info("Traceback: ", exc_info=True)
        return -2, []

    if filename:
        filename, cat = name_to_cat(filename, catdir)
        # The name is used as the name of the folder, so sanitize it using folder specific sanitization
        if not nzbname:
            # Prevent embedded password from being damaged by sanitize and trimming
            nzbname = get_filename(filename)

    # Parse the data
    result = 0
    nzo = None
    nzo_ids = []
    try:
        nzo = nzbstuff.NzbObject(
            filename,
            pp=pp,
            script=script,
            nzb_fp=nzb_fp,
            cat=cat,
            url=url,
            priority=priority,
            nzbname=nzbname,
            nzo_info=nzo_info,
            reuse=reuse,
            nzo_id=nzo_id,
            dup_check=dup_check,
        )
        if not nzo.password:
            nzo.password = password
    except (sabnzbd.nzbstuff.NzbEmpty, sabnzbd.nzbstuff.NzbRejected):
        # Empty or fully rejected
        result = -1
        pass
    except sabnzbd.nzbstuff.NzbRejectedToHistory as err:
        # Duplicate or unwanted extension that was failed to history
        nzo_ids.append(err.nzo_id)
    except:
        # Something else is wrong, show error
        logging.error(T("Error while adding %s, removing"), filename, exc_info=True)
        result = -1
    finally:
        nzb_fp.close()

    if nzo:
        nzo_ids.append(sabnzbd.NzbQueue.add(nzo, quiet=bool(reuse)))

    try:
        if not keep:
            remove_file(path)
    except OSError:
        # Job was still added to the queue, so throw error but don't report failed add
        logging.error(T("Error removing %s"), clip_path(path))
        logging.info("Traceback: ", exc_info=True)

    return result, nzo_ids


def nzbfile_parser(full_nzb_path: str, nzo):
    # For type-hinting
    nzo: sabnzbd.nzbstuff.NzbObject

    # Hash for dupe-checking
    md5sum = hashlib.md5()

    # Average date
    avg_age_sum = 0

    # In case of failing timestamps and failing files
    time_now = time.time()
    skipped_files = 0
    valid_files = 0

    # Use nzb.gz file from admin dir
    with gzip.open(full_nzb_path) as nzb_fh:
        for _, element in xml.etree.ElementTree.iterparse(nzb_fh):
            # For type-hinting
            element: xml.etree.ElementTree.Element

            # Ignore namespace
            _, has_namespace, postfix = element.tag.partition("}")
            if has_namespace:
                element.tag = postfix

            # Parse the header
            if element.tag.lower() == "head":
                for meta in element.iter("meta"):
                    meta_type = meta.attrib.get("type")
                    if meta_type and meta.text:
                        # Meta tags can occur multiple times
                        if meta_type not in nzo.meta:
                            nzo.meta[meta_type] = []
                        nzo.meta[meta_type].append(meta.text)
                element.clear()
                logging.debug("NZB file meta-data = %s", nzo.meta)
                continue

            # Parse the files
            if element.tag.lower() == "file":
                # Get subject and date
                # Don't fail, if subject is missing
                file_name = "unknown"
                if element.attrib.get("subject"):
                    file_name = element.attrib.get("subject")

                # Don't fail if no date present
                try:
                    file_date = datetime.datetime.fromtimestamp(int(element.attrib.get("date")))
                    file_timestamp = int(element.attrib.get("date"))
                except:
                    file_date = datetime.datetime.fromtimestamp(time_now)
                    file_timestamp = time_now

                # Get group
                for group in element.iter("group"):
                    if group.text not in nzo.groups:
                        nzo.groups.append(group.text)

                # Get segments
                raw_article_db = {}
                file_bytes = 0
                bad_articles = False
                if element.find("segments"):
                    for segment in element.find("segments").iter("segment"):
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
                                    bad_articles = True
                                else:
                                    logging.info("Skipping duplicate article (%s)", article_id)
                            elif segment_size <= 0 or segment_size >= 2**23:
                                # Perform sanity check (not negative, 0 or larger than 8MB) on article size
                                # We use this value later to allocate memory in cache and sabyenc
                                logging.info("Skipping article %s due to strange size (%s)", article_id, segment_size)
                                nzo.increase_bad_articles_counter("bad_articles")
                                bad_articles = True
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
                nzf.has_bad_articles = bad_articles

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
                        remove_data(nzf.nzf_id, nzo.admin_path)
                    skipped_files += 1
                element.clear()

    # Final bookkeeping
    nr_files = max(1, valid_files)
    nzo.avg_stamp = avg_age_sum / nr_files
    nzo.avg_date = datetime.datetime.fromtimestamp(avg_age_sum / nr_files)
    nzo.md5sum = md5sum.hexdigest()

    if skipped_files:
        logging.warning(T("Failed to import %s files from %s"), skipped_files, nzo.filename)
