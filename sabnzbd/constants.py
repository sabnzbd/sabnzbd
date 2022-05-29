#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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

BYTES_FILE_NAME_OLD = "totals9.sab"
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

SABYENC_VERSION_REQUIRED = "5.4.2"

DB_HISTORY_VERSION = 1
DB_HISTORY_NAME = "history%s.db" % DB_HISTORY_VERSION

CONFIG_BACKUP_FILES = [
    BYTES_FILE_NAME,
    RSS_FILE_NAME,
    DB_HISTORY_NAME,
]

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
MAX_WARNINGS = 20
MAX_BAD_ARTICLES = 5

# Constants affecting download performance
MIN_DECODE_QUEUE = 10
LIMIT_DECODE_QUEUE = 100
DIRECT_WRITE_TRIGGER = 35
MAX_ASSEMBLER_QUEUE = 5

REPAIR_PRIORITY = 3
FORCE_PRIORITY = 2
HIGH_PRIORITY = 1
NORMAL_PRIORITY = 0
LOW_PRIORITY = -1
DEFAULT_PRIORITY = -100
PAUSED_PRIORITY = -2
DUP_PRIORITY = -3
STOP_PRIORITY = -4

INTERFACE_PRIORITIES = {
    FORCE_PRIORITY: "Force",
    REPAIR_PRIORITY: "Repair",
    HIGH_PRIORITY: "High",
    NORMAL_PRIORITY: "Normal",
    LOW_PRIORITY: "Low",
}

STAGES = {
    "Source": 0,
    "Download": 1,
    "Servers": 2,
    "Repair": 3,
    "Filejoin": 4,
    "Unpack": 5,
    "Deobfuscate": 6,
    "Script": 7,
}

VALID_ARCHIVES = (".zip", ".rar", ".7z")
VALID_NZB_FILES = (".nzb", ".gz", ".bz2")

CHEETAH_DIRECTIVES = {"directiveStartToken": "<!--#", "directiveEndToken": "#-->", "prioritizeSearchListOverSelf": True}

IGNORED_FILES_AND_FOLDERS = ("@eaDir", ".appleDouble", ".DS_Store")
IGNORED_MOVIE_FOLDERS = ("video_ts", "audio_ts", "bdmv")

EXCLUDED_GUESSIT_PROPERTIES = [
    "part",
]


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
    PROP = "Propagating"  # Q:  Delayed download
