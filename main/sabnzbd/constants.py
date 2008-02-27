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

PNFO_REPAIR_FIELD = 0
PNFO_UNPACK_FIELD = 1
PNFO_DELETE_FIELD = 2
PNFO_SCRIPT_FIELD = 3
PNFO_NZO_ID_FIELD = 4
PNFO_FILENAME_FIELD = 5
PNFO_UNPACKSTRHT_FIELD = 6
PNFO_MSGID_FIELD = 7
PNFO_EXTRA_FIELD1 = 8
PNFO_EXTRA_FIELD2 = 9
PNFO_BYTES_LEFT_FIELD = 10
PNFO_BYTES_FIELD = 11
PNFO_AVG_DATE_FIELD = 12
PNFO_FINISHED_FILES_FIELD = 13
PNFO_ACTIVE_FILES_FIELD = 14
PNFO_QUEUED_FILES_FIELD = 15

QNFO_BYTES_FIELD = 0
QNFO_BYTES_LEFT_FIELD = 1
QNFO_PNFO_LIST_FIELD = 2

ANFO_ARTICLE_SUM_FIELD = 0
ANFO_CACHE_SIZE_FIELD = 1
ANFO_CACHE_LIMIT_FIELD = 2

GIGI = float(2 ** 30)
MEBI = float(2 ** 20)
KIBI = float(2 ** 10)

STAGENAMES = {1:"Par2", 2:"Unrar", 3:"Unzip", 4:"Filejoin"}

BYTES_FILE_NAME  = 'bytes.sab'
QUEUE_FILE_NAME  = 'queue.sab'
RSS_FILE_NAME    = 'rss.sab'
BOOKMARK_FILE_NAME = 'bookmarks.sab'

DEF_DOWNLOAD_DIR = 'downloads/incomplete'
DEF_COMPLETE_DIR = 'downloads/complete'
DEF_CACHE_DIR    = 'cache'
DEF_LOG_DIR      = 'logs'
DEF_NZB_DIR      = ''
DEF_NZBBACK_DIR  = ''
DEF_INTERFACES   = 'interfaces'
DEF_STDINTF      = 'Default'
DEF_MAIN_TMPL    = 'templates/main.tmpl'
DEF_INI_FILE     = 'sabnzbd.ini'
DEF_HOST         = 'localhost'
DEF_PORT_WIN     = 8080
DEF_PORT_UNIX    = 8080
DEF_WORKDIR      = 'sabnzbd'
DEF_LOG_FILE     = 'sabnzbd.log'
DEF_LOG_ERRFILE  = 'sabnzbd.error.log'
DEF_LOG_CHERRY   = 'cherrypy.log'
DEF_TIMEOUT      = 120
MIN_TIMEOUT      = 30
MAX_TIMEOUT      = 200
DEF_LOGLEVEL     = 1
DEF_SCANRATE     = 5
DEF_QRATE        = 0
MIN_DECODE_QUEUE = 5
MAX_DECODE_QUEUE = 10
MAX_WARNINGS     = 20

TVSORTINGLIST = ['None', '\\TV\\ShowName\\Season 1\\01 - EpName\\', \
            '\\TV\\ShowName\\Season 1\\Episode 01 - EpName\\', \
            '\\TV\\ShowName\\1x01 - EpName\\', \
            '\\TV\\ShowName\\S01E01 - EpName\\', \
            '\\TV\\ShowName\\101 - EpName\\']

IGNORE_SAMPLE_LIST = ['.sample', '-sample', 'sample-']
