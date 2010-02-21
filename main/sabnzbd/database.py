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

"""
sabnzbd.database - Database Support
"""

try:
    import sqlite3
except:
    try:
        import pysqlite2.dbapi2 as sqlite3
    except:
        pass

import os
import time
import datetime
from calendar import MONDAY
import zlib
import logging

import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DB_HISTORY_NAME
from sabnzbd.lang import T, Ta
from sabnzbd.codecs import unicoder

_HISTORY_DB = None        # Will contain full path to history database
_DONE_CLEANING = False    # Ensure we only do one Vacuum per session

def get_history_handle():
    """ Get an instance of the history db hanlder """
    global _HISTORY_DB
    if not _HISTORY_DB:
        _HISTORY_DB = os.path.join(sabnzbd.cfg.admin_dir.get_path(), DB_HISTORY_NAME)
    return HistoryDB(_HISTORY_DB)


# Note: Add support for execute return values

class HistoryDB:
    def __init__(self, db_path):
        global _DONE_CLEANING
        #Thread.__init__(self)
        if not os.path.exists(db_path):
            create_table = True
        else:
            create_table = False
        if sabnzbd.WIN32:
            self.con = sqlite3.connect(db_path.decode('latin-1').encode('utf-8'))
        else:
            self.con = sqlite3.connect(db_path)
        self.con.row_factory = dict_factory
        self.c = self.con.cursor()
        if create_table:
            self.create_history_db()
        elif not _DONE_CLEANING:
            # Run VACUUM on sqlite
            # When an object (table, index, or trigger) is dropped from the database, it leaves behind empty space
            # http://www.sqlite.org/lang_vacuum.html
            _DONE_CLEANING = True
            self.execute('VACUUM')

    def execute(self, command, args=(), save=False):
        ''' Wrapper for executing SQL commands '''
        try:
            if args and isinstance(args, tuple):
                self.c.execute(command, args)
            else:
                self.c.execute(command)
            if save:
                self.save()
            return True
        except:
            logging.error(Ta('error-sqlCmd'))
            logging.debug("SQL: %s" , command)
            logging.debug("Traceback: ", exc_info = True)
            try:
                self.con.rollback()
            except:
                logging.debug("Rollback Failed:", exc_info = True)
            return False

    def create_history_db(self):
        self.execute("""
        CREATE TABLE "history" (
            "id" INTEGER PRIMARY KEY,
            "completed" INTEGER NOT NULL,
            "name" TEXT NOT NULL,
            "nzb_name" TEXT NOT NULL,
            "category" TEXT,
            "pp" TEXT,
            "script" TEXT,
            "report" TEXT,
            "url" TEXT,
            "status" TEXT,
            "nzo_id" TEXT,
            "storage" TEXT,
            "path" TEXT,
            "script_log" BLOB,
            "script_line" TEXT,
            "download_time" INTEGER,
            "postproc_time" INTEGER,
            "stage_log" TEXT,
            "downloaded" INTEGER,
            "completeness" INTEGER,
            "fail_message" TEXT,
            "url_info" TEXT,
            "bytes" INTEGER,
            "meta" TEXT
        )
        """)

    def save(self):
        try:
            self.con.commit()
        except:
            logging.error(Ta('error-sqlCommit'))
            logging.debug("Traceback: ", exc_info = True)

    def close(self):
        try:
            self.c.close()
            self.con.close()
        except:
            logging.error(Ta('error-sqlClose'))
            logging.debug("Traceback: ", exc_info = True)

    def remove_all(self):
        return self.execute("""DELETE FROM history""")

    def remove_failed(self):
        return self.execute('''DELETE FROM history WHERE status="Failed"''', save=True)

    def remove_history(self, jobs=None):
        if jobs is None:
            self.remove_all()
        else:
            if type(jobs) == type(''):
                jobs = [jobs]

            for job in jobs:
                self.execute("""DELETE FROM history WHERE nzo_id=?""", (job,))

        self.save()

    def add_history_db(self, nzo, storage, path, postproc_time, script_output, script_line):


        t = build_history_info(nzo, storage, path, postproc_time, script_output, script_line)

        if self.execute("""INSERT INTO history (completed, name, nzb_name, category, pp, script, report,
        url, status, nzo_id, storage, path, script_log, script_line, download_time, postproc_time, stage_log,
        downloaded, completeness, fail_message, url_info, bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", t):
            self.save()

    def fetch_history(self, start=None, limit=None, search=None):

        if not search:
            # Default value
            search = ''
        else:
            # Allow * for wildcard matching and space
            search = search.replace('*','%').replace(' ', '%')

        # Allow ^ for start of string and $ for end of string
        if search and search.startswith('^'):
            search = search.replace('^','')
            search += '%'
        elif search and search.endswith('$'):
            search = search.replace('$','')
            search = '%' + search
        else:
            search = '%' + search + '%'

        # Get the number of results
        if self.execute('select count(*) from History WHERE name LIKE ?', (search,)):
            total_items = self.c.fetchone()['count(*)']
        else:
            total_items = -1

        if not start:
            start = 0
        if not limit:
            limit = total_items

        t = (search, start,limit)
        fetch_ok = self.execute("""SELECT * FROM history WHERE name LIKE ? ORDER BY completed desc LIMIT ?, ?""", t)

        if fetch_ok:
            items = self.c.fetchall()
        else:
            items = []

        fetched_items = len(items)

        # Unpack the single line stage log
        # Stage Name is seperated by ::: stage lines by ; and stages by \r\n
        items = [unpack_history_info(item) for item in items]

        return (items, fetched_items, total_items)

    def get_history_size(self):
        """
        Returns the total size of the history and
        amounts downloaded in the last month and week
        """
        # Total Size of the history
        if self.execute('''SELECT sum(bytes) FROM history'''):
            f = self.c.fetchone()
            total = f['sum(bytes)']
        else:
            total = 0

        # Amount downloaded this month
        r = time.gmtime(time.time())
        month_timest = int(time.mktime((r.tm_year, r.tm_mon, 0, 0, 0, 1, r.tm_wday, r.tm_yday, r.tm_isdst)))

        if self.execute('''SELECT sum(bytes) FROM history WHERE "completed">?''', (month_timest,)):
            f = self.c.fetchone()
            month = f['sum(bytes)']
        else:
            month = 0

        # Amount downloaded this week
        monday = find_monday()
        week_timest = int(time.mktime(find_monday()))

        if self.execute('''SELECT sum(bytes) FROM history WHERE "completed">?''', (week_timest,)):
            f = self.c.fetchone()
            week = f['sum(bytes)']
        else:
            week = 0

        return (total, month, week)


    def get_script_log(self, nzo_id):
        t = (nzo_id,)
        if self.execute('SELECT script_log FROM history WHERE nzo_id=?', t):
            f = self.c.fetchone()
            return zlib.decompress(f['script_log'])
        else:
            return ''

    def get_name(self, nzo_id):
        t = (nzo_id,)
        if self.execute('SELECT name FROM history WHERE nzo_id=?', t):
            return self.c.fetchone()['name']
        else:
            return ''


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def build_history_info(nzo, storage='', path='', postproc_time=0, script_output='', script_line=''):
    ''' Collects all the information needed for the database '''

    path = decode_factory(path)
    storage = decode_factory(storage)
    script_line = decode_factory(script_line)

    flagRepair, flagUnpack, flagDelete = nzo.get_repair_opts()
    nzo_info = decode_factory(nzo.get_nzo_info())

    # Get the url and newzbin msgid
    report = decode_factory(nzo_info.get('msgid', ''))
    if report:
        url = 'https://newzbin.com/browse/post/%s/' % (report)
    else:
        url = decode_factory(nzo_info.get('url', ''))

    #group = nzo.get_group()

    completed = int(time.time())
    name = decode_factory(nzo.get_original_dirname())

    nzb_name = decode_factory(nzo.get_filename())
    category = decode_factory(nzo.get_cat())
    pps = ['','R','U','D']
    try:
        pp = pps[sabnzbd.opts_to_pp(flagRepair, flagUnpack, flagDelete)]
    except:
        pp = ''
    script = decode_factory(nzo.get_script())
    status = decode_factory(nzo.get_status())
    nzo_id = nzo.get_nzo_id()
    bytes = nzo.get_bytes_downloaded()

    if script_output:
        # Compress the output of the script
        script_log = sqlite3.Binary(zlib.compress(script_output))
        #
    else:
        script_log = ''

    download_time = decode_factory(nzo_info.get('download_time', 0))

    downloaded = nzo.get_bytes_downloaded()
    completeness = 0
    fail_message = decode_factory(nzo.get_fail_msg())
    url_info = nzo_info.get('more_info', '')

    # Get the dictionary containing the stages and their unpack process
    stages = decode_factory(nzo.get_unpack_info())
    # Pack the ditionary up into a single string
    # Stage Name is seperated by ::: stage lines by ; and stages by \r\n
    lines = []
    for key, results in stages.iteritems():
        lines.append('%s:::%s' % (key, ';'.join(results)))
    stage_log = '\r\n'.join(lines)

    return (completed, name, nzb_name, category, pp, script, report, url, status, nzo_id, storage, path, \
            script_log, script_line, download_time, postproc_time, stage_log, downloaded, completeness, \
            fail_message, url_info, bytes,)

def unpack_history_info(item):
    '''
        Expands the single line stage_log from the DB
        into a python dictionary for use in the history display
    '''
    # Stage Name is seperated by ::: stage lines by ; and stages by \r\n
    if item['stage_log']:
        try:
            lines = item['stage_log'].split('\r\n')
        except:
            logging.error(T('error-badHisNewline@1'), unicoder(item['name']))
            logging.debug('Lines: %s', item['stage_log'])
            lines = []
        item['stage_log'] = []
        for line in lines:
            stage = {}
            try:
                key, logs = line.split(':::')
            except:
                logging.debug('Missing key:::logs "%s"', line)
                key = line
                logs = ''
            stage['name'] = key
            stage['actions'] = []
            try:
                logs = logs.split(';')
            except:
                logging.error(T('error-badHisSemic@1'), unicoder(item['name']))
                logging.debug('Logs: %s', logs)
                logs = []
            for log in logs:
                stage['actions'].append(log)
            item['stage_log'].append(stage)
    if item['script_log']:
        item['script_log'] = zlib.decompress(item['script_log'][:])
    # The action line is only available for items in the postproc queue
    if not item.has_key('action_line'):
        item['action_line'] = ''
    return item


def decode_factory(text):
    '''
        Recursivly looks through the supplied argument
        and converts and text to Unicode
    '''
    if isinstance(text, str):
        return unicoder(text)

    elif isinstance(text, list):
        new_text = []
        for t in text:
            new_text.append(decode_factory(t))
        return new_text

    elif isinstance(text, dict):
        new_text = {}
        for key in text:
            new_text[key] = decode_factory(text[key])
        return new_text
    else:
        return text


def find_monday():
    last_monday = datetime.date.today()
    minus_one_day = datetime.timedelta(days=1)
    while last_monday.weekday() != MONDAY:
        last_monday -= minus_one_day
    return (last_monday.year, last_monday.month, last_monday.day, 0, 1, 1, 0, 0, 0)

