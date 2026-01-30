#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.nzb.file - NzbFile class for representing files in NZB downloads
"""

import datetime
import logging
import os
import threading
from typing import Optional, Any

import sabctools
from sabnzbd.nzb.article import TryList, Article
from sabnzbd.downloader import Server
from sabnzbd.filesystem import (
    sanitize_filename,
    get_unique_filename,
    get_filename,
    remove_file,
    get_new_id,
    save_data,
    load_data,
    RAR_RE,
)
from sabnzbd.misc import int_conv, subject_name_extractor
from sabnzbd.decorators import synchronized


##############################################################################
# NzbFile
##############################################################################
class SkippedNzbFile(Exception):
    pass


NzbFileSaver = (
    "date",
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
    "import_finished",
    "crc32",
    "assembled",
    "md5of16k",
)


class NzbFile(TryList):
    """Representation of one file consisting of multiple articles"""

    # Pre-define attributes to save memory
    __slots__ = NzbFileSaver + ("lock", "file_lock", "assembler_next_index")

    def __init__(self, date, subject, raw_article_db, file_bytes, nzo):
        """Setup object"""
        super().__init__()
        self.lock: threading.RLock = threading.RLock()
        self.file_lock: threading.RLock = threading.RLock()

        self.date: datetime.datetime = date
        self.type: Optional[str] = None
        self.filename: str = sanitize_filename(subject_name_extractor(subject))
        self.filename_checked = False
        self.filepath: Optional[str] = None

        # Identifiers for par2 files
        self.is_par2: bool = False
        self.vol: Optional[int] = None
        self.blocks: Optional[int] = None
        self.setname: Optional[str] = None

        # Articles are removed from "articles" after being fetched
        self.articles: dict[Article, Article] = {}
        self.decodetable: list[Article] = []

        self.bytes: int = file_bytes
        self.bytes_left: int = file_bytes

        self.nzo = nzo  # NzbObject reference
        self.deleted = False
        self.import_finished = False

        self.crc32: Optional[int] = 0
        self.assembled: bool = False
        self.md5of16k: Optional[bytes] = None
        self.assembler_next_index: int = 0

        # Add first article to decodetable, this way we can check
        # if this is maybe a duplicate nzf
        if raw_article_db:
            first_article = self.add_article(raw_article_db.pop(0))
            first_article.lowest_partnum = True

        if self in nzo.files:
            logging.info("File %s occurred twice in NZB, skipping", self.filename)
            raise SkippedNzbFile

        # Create file on disk, which can fail in case of disk errors
        self.nzf_id: str = get_new_id("nzf", nzo.admin_path)
        if not self.nzf_id:
            # Error already shown to user from get_new_id
            raise SkippedNzbFile

        # Any articles left?
        if raw_article_db:
            # Save the rest
            save_data(raw_article_db, self.nzf_id, nzo.admin_path)
        else:
            # All imported
            self.import_finished = True

    @property
    @synchronized()
    def assembler_next_article(self) -> Optional[Article]:
        if (next_index := self.assembler_next_index) < len(self.decodetable):
            return self.decodetable[next_index]
        return None

    def finish_import(self):
        """Load the article objects from disk"""
        logging.debug("Finishing import on %s", self.filename)
        if raw_article_db := load_data(self.nzf_id, self.nzo.admin_path, remove=False):
            for raw_article in raw_article_db:
                self.add_article(raw_article)

            # Make sure we have labeled the lowest part number
            # Also when DirectUnpack is disabled we need to know
            self.decodetable[0].lowest_partnum = True

            # Mark safe to continue
            self.import_finished = True

    @synchronized()
    def add_article(self, article_info):
        """Add article to object database and return article object"""
        article = Article(article_info[0], article_info[1], self)
        self.articles[article] = article
        self.decodetable.append(article)
        return article

    @synchronized()
    def remove_article(self, article: Article, success: bool) -> int:
        """Handle completed article, possibly end of file"""
        if self.articles.pop(article, None) is not None:
            if success:
                self.bytes_left -= article.bytes
        return len(self.articles)

    def set_par2(self, setname, vol, blocks):
        """Designate this file as a par2 file"""
        self.is_par2 = True
        self.setname = setname
        self.vol = vol
        self.blocks = int_conv(blocks)

    @synchronized()
    def update_crc32(self, crc32: Optional[int], length: int) -> None:
        if self.crc32 is None or crc32 is None:
            self.crc32 = None
        else:
            self.crc32 = sabctools.crc32_combine(self.crc32, crc32, length)

    @synchronized()
    def get_articles(self, server: Server, servers: list[Server], fetch_limit: int):
        """Get next articles to be downloaded"""
        articles = server.article_queue
        for article in self.articles:
            if article := article.get_article(server, servers):
                articles.append(article)
                if len(articles) >= fetch_limit:
                    return
        self.add_to_try_list(server)

    @synchronized()
    def reset_all_try_lists(self):
        """Reset all try lists. Locked so reset is performed
        for all items at the same time without chance of another
        thread changing any of the items while we are resetting"""
        for art in self.articles:
            art.reset_try_list()
        self.reset_try_list()

    def first_article_processed(self) -> bool:
        """Check if the first article has been processed.
        This ensures we have attempted to extract md5of16k and filename information
        before creating the filepath.
        """
        # The first article of decodetable is always the lowest
        first_article = self.decodetable[0]
        # If it's still in nzo.first_articles, it hasn't been processed yet
        return first_article not in self.nzo.first_articles

    def prepare_filepath(self):
        """Do all checks before making the final path"""
        if not self.filepath:
            # Wait for the first article to be processed so we can get md5of16k
            # and proper filename before creating the filepath
            if not self.first_article_processed():
                return None

            self.nzo.verify_nzf_filename(self)
            filename = sanitize_filename(self.filename)
            self.filepath = get_unique_filename(os.path.join(self.nzo.download_path, filename))
            self.filename = get_filename(self.filepath)
        return self.filepath

    @property
    def completed(self):
        """Is this file completed?"""
        if not self.import_finished:
            return False
        with self.lock:
            return not self.articles

    def remove_admin(self):
        """Remove article database from disk (sabnzbd_nzf_<id>)"""
        try:
            logging.debug("Removing article database for %s", self.nzf_id)
            remove_file(os.path.join(self.nzo.admin_path, self.nzf_id))
        except Exception:
            pass

    @synchronized()
    def contiguous_offset(self) -> int:
        """The next file offset to write to continue sequentially.

        Note: there could be non-sequential direct writes already beyond this point
        """
        with self.file_lock:
            # If last written article has valid yenc headers
            if self.assembler_next_index:
                article = self.decodetable[self.assembler_next_index - 1]
                if article.on_disk and article.data_size:
                    return article.data_begin + article.data_size

            # Fallback to summing decoded size
            offset = 0
            for article in self.decodetable[: self.assembler_next_index]:
                if not article.on_disk:
                    break
                if article.data_size:
                    offset = article.data_begin + article.decoded_size
                elif article.decoded_size is not None:
                    # queues from <= 4.5.5 do not have this attribute
                    offset += article.decoded_size
                elif os.path.exists(self.filepath):
                    # fallback for <= 4.5.5 because files were always opened in append mode, so use the file size
                    return os.path.getsize(self.filepath)
        return offset

    @synchronized()
    def contiguous_ready_bytes(self) -> int:
        """How many bytes from assembler_next_index onward are ready to write to file contiguously?"""
        bytes_ready: int = 0
        for article in self.decodetable[self.assembler_next_index :]:
            if not article.decoded:
                break
            if article.on_disk:
                continue
            if article.decoded_size is None:
                break
            bytes_ready += article.decoded_size
        return bytes_ready

    def sort_key(self) -> tuple[Any, ...]:
        """Comparison function for sorting NZB files.

        The comparison will sort .par2 files to the top of the queue followed by .rar files,
        they will then be sorted by name.
        """
        name = self.filename.lower()
        base, ext = os.path.splitext(name)

        is_par2 = ext == ".par2"
        is_vol_par2 = is_par2 and ".vol" in base
        is_mini_par2 = is_par2 and not is_vol_par2

        m = RAR_RE.search(name)
        is_rar = bool(m)
        is_main_rar = is_rar and m.group(1) == "rar"

        # Initially group by mini-par2, other files, vol-par2
        if is_mini_par2:
            tier = 0
        elif is_vol_par2:
            tier = 2
        else:
            tier = 1

        if tier == 1:
            if is_rar and m:
                # strip matched RAR suffix including leading dot (.part01.rar, .rar, .r00, ...)
                group_base = name[: m.start()]
                local_group = 0
                type_rank = 0 if is_main_rar else 1
            else:
                # nfo, sfv, sample.mkv, etc.
                group_base = base
                local_group = 1
                type_rank = 0
        else:
            # mini/vol par2 ignore the group base
            group_base = ""
            local_group = 0
            type_rank = 0

        return tier, group_base, local_group, type_rank, name

    def __getstate__(self):
        """Save to pickle file, selecting attributes"""
        dict_ = {}
        for item in NzbFileSaver:
            dict_[item] = getattr(self, item)
        dict_["try_list"] = super().__getstate__()
        return dict_

    def __setstate__(self, dict_):
        """Load from pickle file, selecting attributes"""
        for item in NzbFileSaver:
            try:
                setattr(self, item, dict_[item])
            except KeyError:
                # Handle new attributes
                setattr(self, item, None)
        self.lock = threading.RLock()
        self.file_lock = threading.RLock()
        self.assembler_next_index = 0
        if isinstance(self.articles, list):
            # Converted from list to dict
            self.articles = {x: x for x in self.articles}
        for article in self.articles:
            article.lock = self.lock
        super().__setstate__(dict_.get("try_list", []))

    def __lt__(self, other: "NzbFile"):
        return self.sort_key() < other.sort_key()

    def __eq__(self, other: "NzbFile"):
        """Assume it's the same file if the number bytes and first article
        are the same or if there are no articles left, use the filenames.
        Some NZB's are just a mess and report different sizes for the same article.
        We used to compare (__eq__) articles based on article-ID, however, this failed
        because some NZB's had the same article-ID twice within one NZF.
        """
        if other and (self.bytes == other.bytes or len(self.decodetable) == len(other.decodetable)):
            if self.decodetable and other.decodetable:
                return self.decodetable[0].article == other.decodetable[0].article
            # Fallback to filename comparison
            return self.filename == other.filename
        return False

    def __hash__(self):
        """Required because we implement eq. The same file can be spread
        over multiple NZO's so we make every NZF unique. Even though
        it's considered bad practice.
        """
        return id(self)

    def __repr__(self):
        return "<NzbFile: filename=%s, bytes=%s, nzf_id=%s>" % (self.filename, self.bytes, self.nzf_id)
