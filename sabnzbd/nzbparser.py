#!/usr/bin/python3 -OO
# Copyright 2008-2024 by The SABnzbd-Team (sabnzbd.org)
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
from sabnzbd.encoding import utob, correct_cherrypy_encoding
from sabnzbd.filesystem import (
    get_filename,
    is_valid_script,
    get_ext,
    clip_path,
    remove_file,
    remove_data,
)
from sabnzbd.misc import name_to_cat, cat_pp_script_sanitizer
from sabnzbd.constants import DEFAULT_PRIORITY, VALID_ARCHIVES, AddNzbFileResult
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
    dup_check: bool = True,
):
    """Add file, either a single NZB-file or an archive.
    All other parameters are passed to the NZO-creation.
    """
    # Base conversion of input
    cat, pp, script = cat_pp_script_sanitizer(cat, pp, script)

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
        filename = correct_cherrypy_encoding(nzbfile.filename)
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
            dup_check=dup_check,
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
            dup_check=dup_check,
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
    url: Optional[str] = None,
    password: Optional[str] = None,
    nzo_id: Optional[str] = None,
    dup_check: bool = True,
) -> Tuple[AddNzbFileResult, List[str]]:
    """Analyse archive and create job(s).
    Accepts archive files with ONLY nzb/nfo/folder files in it.
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
            return AddNzbFileResult.ERROR, []
    except:
        logging.info(T("Cannot read %s"), path, exc_info=True)
        return AddNzbFileResult.RETRY, []

    status: AddNzbFileResult = AddNzbFileResult.NO_FILES_FOUND
    names = zf.namelist()
    nzbcount = 0
    for name in names:
        name = name.lower()
        if name.endswith(".nzb"):
            status = AddNzbFileResult.OK
            nzbcount += 1

    if status == AddNzbFileResult.OK:
        if nzbcount != 1:
            nzbname = None
        for name in names:
            if name.lower().endswith(".nzb"):
                try:
                    datap = zf.open(name)
                except OSError:
                    logging.error(T("Cannot read %s"), name, exc_info=True)
                    zf.close()
                    return AddNzbFileResult.ERROR, []
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
                            password=password,
                            nzbname=nzbname,
                            nzo_info=nzo_info,
                            reuse=reuse,
                            nzo_id=nzo_id,
                            dup_check=dup_check,
                        )
                    except (sabnzbd.nzbstuff.NzbEmpty, sabnzbd.nzbstuff.NzbRejected):
                        # Empty or fully rejected
                        pass
                    except sabnzbd.nzbstuff.NzbRejectToHistory as err:
                        # Duplicate or unwanted extension directed to history
                        sabnzbd.NzbQueue.fail_to_history(err.nzo)
                        nzo_ids.append(err.nzo.nzo_id)
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
        status = AddNzbFileResult.NO_FILES_FOUND

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
    url: Optional[str] = None,
    password: Optional[str] = None,
    nzo_id: Optional[str] = None,
    dup_check: bool = True,
) -> Tuple[AddNzbFileResult, List[str]]:
    """Analyze file and create a job from it
    Supports NZB, NZB.BZ2, NZB.GZ and GZ.NZB-in-disguise
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
        return AddNzbFileResult.RETRY, []

    if filename:
        filename, cat = name_to_cat(filename, catdir)
        # The name is used as the name of the folder, so sanitize it using folder specific sanitization
        if not nzbname:
            # Prevent embedded password from being damaged by sanitize and trimming
            nzbname = get_filename(filename)

    # Parse the data
    result: AddNzbFileResult = AddNzbFileResult.OK
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
            password=password,
            nzbname=nzbname,
            nzo_info=nzo_info,
            reuse=reuse,
            nzo_id=nzo_id,
            dup_check=dup_check,
        )
    except sabnzbd.nzbstuff.NzbEmpty:
        # Malformed or might not be an NZB file
        result = AddNzbFileResult.NO_FILES_FOUND
    except sabnzbd.nzbstuff.NzbRejected:
        # Rejected as duplicate or by pre-queue script
        result = AddNzbFileResult.ERROR
    except sabnzbd.nzbstuff.NzbRejectToHistory as err:
        # Duplicate or unwanted extension directed to history
        sabnzbd.NzbQueue.fail_to_history(err.nzo)
        nzo_ids.append(err.nzo.nzo_id)
    except:
        # Something else is wrong, show error
        logging.error(T("Error while adding %s, removing"), filename, exc_info=True)
        result = AddNzbFileResult.ERROR
    finally:
        nzb_fp.close()

    if nzo:
        nzo_ids.append(sabnzbd.NzbQueue.add(nzo, quiet=bool(reuse)))

    try:
        if not keep and result in {AddNzbFileResult.ERROR, AddNzbFileResult.OK}:
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
                if len(element.find("segments")):
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
                                else:
                                    logging.info("Skipping duplicate article (%s)", article_id)
                            elif segment_size <= 0 or segment_size >= 2**23:
                                # Perform sanity check (not negative, 0 or larger than 8MB) on article size
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
                    logging.info("File %s occurred twice in NZB, skipping", nzf.filename)
                    remove_data(nzf.nzf_id, nzo.admin_path)
                    continue

                # Add valid NZF's
                if file_name and nzf.valid and nzf.nzf_id:
                    nzo.add_nzf(nzf)
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
