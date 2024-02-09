#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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

import os
from collections import namedtuple

CONFIG_VERSION = 19

QUEUE_VERSION = 10
POSTPROC_QUEUE_VERSION = 2

REC_RAR_VERSION = 550

ANFO = namedtuple("ANFO", "article_sum cache_size cache_limit")

# Leave some space for "_UNPACK_" which we append during post-proc
# Or, when extra ".1", ".2" etc. are added for identically named jobs
DEF_FOLDER_MAX = 256 - 10
DEF_FILE_MAX = 255 - 10  # max filename length on modern filesystems, minus some room for extra chars later on

GIGI = float(2**30)
MEBI = float(2**20)
KIBI = float(2**10)

BYTES_FILE_NAME = "totals10.sab"
QUEUE_FILE_TMPL = "queue%s.sab"
QUEUE_FILE_NAME = QUEUE_FILE_TMPL % QUEUE_VERSION
POSTPROC_QUEUE_FILE_NAME = "postproc%s.sab" % POSTPROC_QUEUE_VERSION
RSS_FILE_NAME = "rss_data.sab"
SCAN_FILE_NAME = "watched_data2.sab"
FUTURE_Q_FOLDER = "future"
JOB_ADMIN = "__ADMIN__"
VERIFIED_FILE = "__verified__"
RENAMES_FILE = "__renames__"
ATTRIB_FILE = "SABnzbd_attrib"
REPAIR_REQUEST = "repair-all.sab"

SABCTOOLS_VERSION_REQUIRED = "8.1.0"

DB_HISTORY_VERSION = 1
DB_HISTORY_NAME = "history%s.db" % DB_HISTORY_VERSION

DEF_DOWNLOAD_DIR = os.path.normpath("Downloads/incomplete")
DEF_COMPLETE_DIR = os.path.normpath("Downloads/complete")
DEF_ADMIN_DIR = "admin"
DEF_NZBBACK_DIR = ""
DEF_LANGUAGE = "locale"
DEF_INTERFACES = "interfaces"
DEF_EMAIL_TMPL = "email"
DEF_STD_CONFIG = "Config"
DEF_STD_WEB_DIR = "Glitter"
DEF_STD_WEB_COLOR = "Auto"
DEF_MAIN_TMPL = os.path.normpath("templates/main.tmpl")
DEF_INI_FILE = "sabnzbd.ini"
DEF_HOST = "127.0.0.1"
DEF_PORT = 8080
DEF_WORKDIR = "sabnzbd"
DEF_LOG_FILE = "sabnzbd.log"
DEF_LOG_ERRFILE = "sabnzbd.error.log"
DEF_LOG_CHERRY = "cherrypy.log"
DEF_ARTICLE_CACHE_DEFAULT = "500M"
DEF_ARTICLE_CACHE_MAX = "1G"
DEF_TIMEOUT = 60
DEF_SCANRATE = 5
DEF_HTTPS_CERT_FILE = "server.cert"
DEF_HTTPS_KEY_FILE = "server.key"
DEF_SORTER_RENAME_SIZE = "50M"
MAX_WARNINGS = 20
MAX_BAD_ARTICLES = 5

CONFIG_BACKUP_FILES = [
    BYTES_FILE_NAME,
    RSS_FILE_NAME,
    DB_HISTORY_NAME,
]
CONFIG_BACKUP_HTTPS = {  # "basename": "associated setting"
    DEF_HTTPS_CERT_FILE: "https_cert",
    DEF_HTTPS_KEY_FILE: "https_key",
    "server.chain": "https_chain",
}

# Constants affecting download performance
MAX_ASSEMBLER_QUEUE = 12
SOFT_QUEUE_LIMIT = 0.5
# Percentage of cache to use before adding file to assembler
ASSEMBLER_WRITE_THRESHOLD = 5
NNTP_BUFFER_SIZE = int(800 * KIBI)

REPAIR_PRIORITY = 3
FORCE_PRIORITY = 2
HIGH_PRIORITY = 1
NORMAL_PRIORITY = 0
LOW_PRIORITY = -1
DEFAULT_PRIORITY = -100
PAUSED_PRIORITY = -2
STOP_PRIORITY = -4

PP_LOOKUP = {0: "", 1: "R", 2: "U", 3: "D"}

INTERFACE_PRIORITIES = {
    FORCE_PRIORITY: "Force",
    REPAIR_PRIORITY: "Repair",
    HIGH_PRIORITY: "High",
    NORMAL_PRIORITY: "Normal",
    LOW_PRIORITY: "Low",
}

STAGES = {
    "RSS": 0,
    "Source": 1,
    "Download": 2,
    "Servers": 3,
    "Repair": 4,
    "Filejoin": 5,
    "Unpack": 6,
    "Deobfuscate": 7,
    "Script": 8,
}

VALID_ARCHIVES = (".zip", ".rar", ".7z")
VALID_NZB_FILES = (".nzb", ".gz", ".bz2")

CHEETAH_DIRECTIVES = {"directiveStartToken": "<!--#", "directiveEndToken": "#-->", "prioritizeSearchListOverSelf": True}

IGNORED_FILES_AND_FOLDERS = ("@eaDir", ".appleDouble", ".DS_Store")
IGNORED_MOVIE_FOLDERS = ("video_ts", "audio_ts", "bdmv")

EXCLUDED_GUESSIT_PROPERTIES = [
    "part",
]
GUESSIT_PART_INDICATORS = ("cd", "part")
GUESSIT_SORT_TYPES = {0: "all", 1: "tv", 2: "date", 3: "movie", 4: "unknown"}


class Status:
    IDLE = "Idle"  # Q: Nothing in the queue
    COMPLETED = "Completed"  # PP: Job is finished
    CHECKING = "Checking"  # Q:  Pre-check is running
    DOWNLOADING = "Downloading"  # Q:  Normal downloading
    EXTRACTING = "Extracting"  # PP: Archives are being extracted
    FAILED = "Failed"  # PP: Job has failed, now in History
    FETCHING = "Fetching"  # Q:  Job is downloading extra par2 files
    GRABBING = "Grabbing"  # Q:  Getting an NZB from an external site
    MOVING = "Moving"  # PP: Files are being moved
    PAUSED = "Paused"  # Q:  Job is paused
    QUEUED = "Queued"  # Q:  Job is waiting for its turn to download or post-process
    QUICK_CHECK = "QuickCheck"  # PP: QuickCheck verification is running
    REPAIRING = "Repairing"  # PP: Job is being repaired (by par2)
    RUNNING = "Running"  # PP: User's post processing script is running
    VERIFYING = "Verifying"  # PP: Job is being verified (by par2)
    DELETED = "Deleted"  # Q:  Job has been deleted (and is almost gone)
    PROPAGATING = "Propagating"  # Q:  Delayed download


class DuplicateStatus:
    DUPLICATE = "Duplicate"  # Simple duplicate
    DUPLICATE_ALTERNATIVE = "Duplicate Alternative"  # Alternative duplicate for a queued job
    SMART_DUPLICATE = "Smart Duplicate"  # Simple Series duplicate
    SMART_DUPLICATE_ALTERNATIVE = "Smart Duplicate Alternative"  # Alternative duplicate for a queued job
    DUPLICATE_IGNORED = "Duplicate Ignored"


class AddNzbFileResult:
    RETRY = "Retry"  # File could not be read
    ERROR = "Error"  # Rejected as duplicate, by pre-queue script or other failure to process file
    OK = "OK"  # Added to queue
    NO_FILES_FOUND = "No files found"  # Malformed or might not be an NZB file
