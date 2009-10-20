#!/usr/bin/python -OO
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

CONFIG_VERSION = 18
QUEUE_VERSION = 9
POSTPROC_QUEUE_VERSION = 1

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
PNFO_STATUS_FIELD = 16
PNFO_PRIORITY_FIELD = 17

QNFO_BYTES_FIELD = 0
QNFO_BYTES_LEFT_FIELD = 1
QNFO_PNFO_LIST_FIELD = 2

ANFO_ARTICLE_SUM_FIELD = 0
ANFO_CACHE_SIZE_FIELD = 1
ANFO_CACHE_LIMIT_FIELD = 2

GIGI = float(2 ** 30)
MEBI = float(2 ** 20)
KIBI = float(2 ** 10)

BYTES_FILE_NAME  = 'bytes%s.sab' % QUEUE_VERSION
QUEUE_FILE_NAME  = 'queue%s.sab' % QUEUE_VERSION
POSTPROC_QUEUE_FILE_NAME  = 'postproc%s.sab' % POSTPROC_QUEUE_VERSION
RSS_FILE_NAME    = 'rss_data.sab'
BOOKMARK_FILE_NAME = 'bookmarks.sab'
SCAN_FILE_NAME    = 'watched_data.sab'

DB_HISTORY_VERSION = 1
DB_QUEUE_VERSION = 1

DB_HISTORY_NAME = 'history%s.db' % DB_HISTORY_VERSION
DB_QUEUE_NAME = 'queue%s.db' % DB_QUEUE_VERSION

DEF_DOWNLOAD_DIR = 'downloads/incomplete'
DEF_COMPLETE_DIR = 'downloads/complete'
DEF_CACHE_DIR    = 'cache'
DEF_LOG_DIR      = 'logs'
DEF_NZBBACK_DIR  = ''
DEF_LANGUAGE     = 'language'
DEF_INTERFACES   = 'interfaces'
DEF_INT_LANGUAGE = 'language'
DEF_STDINTF      = 'Default'
DEF_MAIN_TMPL    = 'templates/main.tmpl'
DEF_INI_FILE     = 'sabnzbd.ini'
DEF_HOST         = 'localhost'
DEF_PORT_WIN     = 8080
DEF_PORT_UNIX    = 8080
DEF_PORT_WIN_SSL = 9090
DEF_PORT_UNIX_SSL= 9090
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

TOP_PRIORITY = 2
HIGH_PRIORITY = 1
NORMAL_PRIORITY = 0
LOW_PRIORITY = -1
DEFAULT_PRIORITY = -100

series_match = [ ('([sS]|[\d]+)x(\d+)', # 1x01
                     ['^[-\.]+([sS]|[\d])+x(\d+)', '^[-\.](\d+)'] ),  #(MATCHER, [EXTRA,MATCHERS])

                      ('[Ss](\d+)[\.\-]?[Ee](\d+)',  # S01E01
                       ['^[-\.]+[Ss](\d+)[\.\-]?[Ee](\d+)', '^[-\.](\d+)']) ] # Extra matchers

                      #possibly flawed - 101 - support: [\.\- \s]?(\d)(\d{2,2})[\.\- \s]?

date_match = ['(\d{4})\W(\d{1,2})\W(\d{1,2})', #2008-10-16
              '(\d{1,2})\W(\d{1,2})\W(\d{4})'] #10.16.2008

year_match = '[\W](\d{4})[\W]??' # Something '(YYYY)' or '.YYYY.' or ' YYYY '

sample_match = '((^|[\W_])sample\d*[\W_])|(-s\.)|(^s-)' # something-sample.avi s-something.avi something-s.avi
