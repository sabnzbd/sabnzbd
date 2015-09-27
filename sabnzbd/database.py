#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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
import zlib
import logging
import sys

import sabnzbd
import sabnzbd.cfg
from sabnzbd.constants import DB_HISTORY_NAME
from sabnzbd.encoding import unicoder
from sabnzbd.bpsmeter import this_week, this_month
from sabnzbd.misc import format_source_url

_HISTORY_DB = None        # Will contain full path to history database
_DONE_CLEANING = False    # Ensure we only do one Vacuum per session


def get_history_handle():
    """ Get an instance of the history db hanlder """
    global _HISTORY_DB
    if not _HISTORY_DB:
        _HISTORY_DB = os.path.join(sabnzbd.cfg.admin_dir.get_path(), DB_HISTORY_NAME)
    return HistoryDB(_HISTORY_DB)


def convert_search(search):
    """ Convert classic wildcard to SQL wildcard """
    if not search:
        # Default value
        search = ''
    else:
        # Allow * for wildcard matching and space
        search = search.replace('*', '%').replace(' ', '%')

    # Allow ^ for start of string and $ for end of string
    if search and search.startswith('^'):
        search = search.replace('^', '')
        search += '%'
    elif search and search.endswith('$'):
        search = search.replace('$', '')
        search = '%' + search
    else:
        search = '%' + search + '%'
    return search


# TODO: Add support for execute return values
class HistoryDB(object):

    def __init__(self, db_path):
        self.db_path = db_path
        self.con = self.c = None
        self.connect()

    def connect(self):
        global _DONE_CLEANING
        if not os.path.exists(self.db_path):
            create_table = True
        else:
            create_table = False
        self.con = sqlite3.connect(self.db_path)
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

        self.execute('PRAGMA user_version;')
        version = self.c.fetchone()['user_version']
        if version < 1:
            # Add any missing columns added since first DB version
            self.execute('PRAGMA user_version = 1;')
            self.execute('ALTER TABLE "history" ADD COLUMN series TEXT;')
            self.execute('ALTER TABLE "history" ADD COLUMN md5sum TEXT;')

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
            error = str(sys.exc_value)
            if 'readonly' in error:
                logging.error(T('Cannot write to History database, check access rights!'))
                # Report back success, because there's no recovery possible
                return True
            elif 'not a database' in error or 'malformed' in error:
                logging.error(T('Damaged History database, created empty replacement'))
                logging.info("Traceback: ", exc_info=True)
                self.close()
                try:
                    os.remove(self.db_path)
                except:
                    pass
                self.connect()
            else:
                logging.error(T('SQL Command Failed, see log'))
                logging.debug("SQL: %s", command)
                logging.info("Traceback: ", exc_info=True)
                try:
                    self.con.rollback()
                except:
                    logging.debug("Rollback Failed:", exc_info=True)
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
            "meta" TEXT,
            "series" TEXT,
            "md5sum" TEXT
        )
        """)
        self.execute('PRAGMA user_version = 1;')

    def save(self):
        try:
            self.con.commit()
        except:
            logging.error(T('SQL Commit Failed, see log'))
            logging.info("Traceback: ", exc_info=True)

    def close(self):
        try:
            self.c.close()
            self.con.close()
        except:
            logging.error(T('Failed to close database, see log'))
            logging.info("Traceback: ", exc_info=True)

    def remove_completed(self, search=None):
        search = convert_search(search)
        return self.execute("""DELETE FROM history WHERE name LIKE ? AND status = 'Completed'""", (search,), save=True)

    def get_failed_paths(self, search=None):
        """ Return list of all storage paths of failed jobs (may contain non-existing or empty paths) """
        search = convert_search(search)
        fetch_ok = self.execute("""SELECT path FROM history WHERE name LIKE ? AND status = 'Failed'""", (search,))
        if fetch_ok:
            return [item.get('path') for item in self.c.fetchall()]
        else:
            return []

    def remove_failed(self, search=None):
        search = convert_search(search)
        return self.execute("""DELETE FROM history WHERE name LIKE ? AND status = 'Failed'""", (search,), save=True)

    def remove_history(self, jobs=None):
        if jobs is None:
            self.remove_completed()
        else:
            if not isinstance(jobs, list):
                jobs = [jobs]

            for job in jobs:
                self.execute("""DELETE FROM history WHERE nzo_id=?""", (job,))

        self.save()

    def add_history_db(self, nzo, storage, path, postproc_time, script_output, script_line):

        t = build_history_info(nzo, storage, path, postproc_time, script_output, script_line)

        if self.execute("""INSERT INTO history (completed, name, nzb_name, category, pp, script, report,
        url, status, nzo_id, storage, path, script_log, script_line, download_time, postproc_time, stage_log,
        downloaded, completeness, fail_message, url_info, bytes, series, md5sum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", t):
            self.save()

    def fetch_history(self, start=None, limit=None, search=None, failed_only=0, categories=None):

        search = convert_search(search)

        post = ''
        if categories:
            categories = ['*' if c == 'Default' else c for c in categories]
            post = ' AND (CATEGORY = "'
            post += '" OR CATEGORY = "'.join(categories)
            post += '" )'
        if failed_only:
            post += ' AND STATUS = "Failed"'

        cmd = 'SELECT COUNT(*) FROM history WHERE name LIKE ?'
        res = self.execute(cmd + post, (search,))
        total_items = -1
        if res:
            try:
                total_items = self.c.fetchone().get('COUNT(*)')
            except AttributeError:
                pass

        if not start:
            start = 0
        if not limit:
            limit = total_items

        t = (search, start, limit)
        cmd = 'SELECT * FROM history WHERE name LIKE ?'
        fetch_ok = self.execute(cmd + post + ' ORDER BY completed desc LIMIT ?, ?', t)

        if fetch_ok:
            items = self.c.fetchall()
        else:
            items = []

        fetched_items = len(items)

        # Unpack the single line stage log
        # Stage Name is separated by ::: stage lines by ; and stages by \r\n
        items = [unpack_history_info(item) for item in items]

        return (items, fetched_items, total_items)

    def have_episode(self, series, season, episode):
        """ Check whether History contains this series episode """
        total = 0
        series = series.lower().replace('.', ' ').replace('_', ' ').replace('  ', ' ')
        if series and season and episode:
            pattern = '%s/%s/%s' % (series, season, episode)
            res = self.execute('select count(*) from History WHERE series = ? AND STATUS != "Failed"', (pattern,))
            if res:
                try:
                    total = self.c.fetchone().get('count(*)')
                except AttributeError:
                    pass
        return total > 0

    def have_md5sum(self, md5sum):
        """ Check whether this md5sum already in History """
        total = 0
        res = self.execute('select count(*) from History WHERE md5sum = ? AND STATUS != "Failed"', (md5sum,))
        if res:
            try:
                total = self.c.fetchone().get('count(*)')
            except AttributeError:
                pass
        return total > 0

    def get_history_size(self):
        """ Returns the total size of the history and
            amounts downloaded in the last month and week
        """
        # Total Size of the history
        total = 0
        if self.execute('''SELECT sum(bytes) FROM history'''):
            try:
                total = self.c.fetchone().get('sum(bytes)')
            except AttributeError:
                pass

        # Amount downloaded this month
        # r = time.gmtime(time.time())
        # month_timest = int(time.mktime((r.tm_year, r.tm_mon, 0, 0, 0, 1, r.tm_wday, r.tm_yday, r.tm_isdst)))
        month_timest = int(this_month(time.time()))

        month = 0
        if self.execute('''SELECT sum(bytes) FROM history WHERE "completed">?''', (month_timest,)):
            try:
                month = self.c.fetchone().get('sum(bytes)')
            except AttributeError:
                pass

        # Amount downloaded this week
        week_timest = int(this_week(time.time()))

        week = 0
        if self.execute('''SELECT sum(bytes) FROM history WHERE "completed">?''', (week_timest,)):
            try:
                week = self.c.fetchone().get('sum(bytes)')
            except AttributeError:
                pass

        return (total, month, week)

    def get_script_log(self, nzo_id):
        data = ''
        t = (nzo_id,)
        if self.execute('SELECT script_log FROM history WHERE nzo_id=?', t):
            try:
                data = zlib.decompress(self.c.fetchone().get('script_log'))
            except:
                pass
        return data

    def get_name(self, nzo_id):
        t = (nzo_id,)
        name = ''
        if self.execute('SELECT name FROM history WHERE nzo_id=?', t):
            try:
                name = self.c.fetchone().get('name')
            except AttributeError:
                pass
        return name

    def get_path(self, nzo_id):
        t = (nzo_id,)
        path = ''
        if self.execute('SELECT path FROM history WHERE nzo_id=?', t):
            try:
                path = self.c.fetchone().get('path')
            except AttributeError:
                pass
        return path

    def get_other(self, nzo_id):
        t = (nzo_id,)
        if self.execute('SELECT * FROM history WHERE nzo_id=?', t):
            try:
                items = self.c.fetchall()[0]
                dtype = items.get('report')
                url = items.get('url')
                pp = items.get('pp')
                script = items.get('script')
                cat = items.get('category')
            except AttributeError:
                return '', '', '', '', ''
        return dtype, url, pp, script, cat


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def build_history_info(nzo, storage='', downpath='', postproc_time=0, script_output='', script_line=''):
    """ Collects all the information needed for the database """

    if not downpath:
        downpath = nzo.downpath
    path = decode_factory(downpath)
    storage = decode_factory(storage)
    script_line = decode_factory(script_line)

    flagRepair, flagUnpack, flagDelete = nzo.repair_opts
    nzo_info = decode_factory(nzo.nzo_info)

    url = decode_factory(nzo.url)

    completed = int(time.time())
    name = decode_factory(nzo.final_name)

    nzb_name = decode_factory(nzo.filename)
    category = decode_factory(nzo.cat)
    pps = ['', 'R', 'U', 'D']
    try:
        pp = pps[sabnzbd.opts_to_pp(flagRepair, flagUnpack, flagDelete)]
    except:
        pp = ''
    script = decode_factory(nzo.script)
    status = decode_factory(nzo.status)
    nzo_id = nzo.nzo_id
    bytes = nzo.bytes_downloaded

    if script_output:
        # Compress the output of the script
        script_log = sqlite3.Binary(zlib.compress(script_output))
        #
    else:
        script_log = ''

    download_time = decode_factory(nzo_info.get('download_time', 0))

    downloaded = nzo.bytes_downloaded
    completeness = 0
    fail_message = decode_factory(nzo.fail_msg)
    url_info = nzo_info.get('details', '') or nzo_info.get('more_info', '')

    # Get the dictionary containing the stages and their unpack process
    stages = decode_factory(nzo.unpack_info)
    # Pack the dictionary up into a single string
    # Stage Name is separated by ::: stage lines by ; and stages by \r\n
    lines = []
    for key, results in stages.iteritems():
        lines.append('%s:::%s' % (key, ';'.join(results)))
    stage_log = '\r\n'.join(lines)

    # Reuse the old 'report' column to indicate a URL-fetch
    report = 'future' if nzo.futuretype else ''

    # Analyze series info only when job is finished
    series = u''
    if postproc_time:
        seriesname, season, episode, dummy = sabnzbd.newsunpack.analyse_show(nzo.final_name)
        if seriesname and season and episode:
            series = u'%s/%s/%s' % (seriesname.lower(), season, episode)

    return (completed, name, nzb_name, category, pp, script, report, url, status, nzo_id, storage, path,
            script_log, script_line, download_time, postproc_time, stage_log, downloaded, completeness,
            fail_message, url_info, bytes, series, nzo.md5sum)


def unpack_history_info(item):
    """ Expands the single line stage_log from the DB
        into a python dictionary for use in the history display
    """
    # Stage Name is separated by ::: stage lines by ; and stages by \r\n
    if item['stage_log']:
        try:
            lines = item['stage_log'].split('\r\n')
        except:
            logging.error(T('Invalid stage logging in history for %s') + ' (\\r\\n)', unicoder(item['name']))
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
                logging.error(T('Invalid stage logging in history for %s') + ' (;)', unicoder(item['name']))
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
    """ Recursively looks through the supplied argument
        and converts and text to Unicode
    """
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
