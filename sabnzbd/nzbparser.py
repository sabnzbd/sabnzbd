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

import time
import logging
import hashlib
import xml.etree.ElementTree
import datetime

import sabnzbd
from sabnzbd.encoding import utob


def nzbfile_parser(raw_data, nzo):
    # Load data as file-object
    raw_data = raw_data.replace("http://www.newzbin.com/DTD/2003/nzb", "", 1)
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
    logging.debug("NZB Meta-data = %s", nzo.meta)

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
        raw_article_db_sorted = [raw_article_db[partnum] for partnum in sorted(raw_article_db.keys())]

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
                sabnzbd.remove_data(nzf.nzf_id, nzo.workpath)
            skipped_files += 1

    # Final bookkeeping
    nr_files = max(1, valid_files)
    nzo.avg_stamp = avg_age_sum / nr_files
    nzo.avg_date = datetime.datetime.fromtimestamp(avg_age_sum / nr_files)
    nzo.md5sum = md5sum.hexdigest()

    if skipped_files:
        logging.warning(T("Failed to import %s files from %s"), skipped_files, nzo.filename)
