#!/usr/bin/python -OO
# Copyright 2008 The SABnzbd-Team <team@sabnzbd.org>
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
__NAME__ = "sabnzbd.database"

try:
    import sqlite3
except:
    try:
        from pysqlite2 import sqlite3
    except:
        pass

import os
import time
import zlib
import logging
from threading import Thread

import sabnzbd
from sabnzbd.constants import DB_HISTORY_VERSION

# Note: Add support for execute return values

class HistoryDB:
    def __init__(self, db_path):
        #Thread.__init__(self)
        if not os.path.exists(db_path):
            create_table = True
        else:
            create_table = False
        self.con = sqlite3.connect(db_path)
        self.con.row_factory = dict_factory
        self.c = self.con.cursor()
        if create_table:
            self.create_history_db()
            
    def execute(self, command, args=(), save=False):
        ''' Wrapper for executing SQL commands '''
        try:
            if args:
                self.c.execute(command, args)
            else:
                self.c.execute(command)
            if save:
                self.save()
            return True
        except:
            logging.error('[%s] SQL Command Failed, see log', __NAME__)
            logging.debug("[%s] SQL: %s" , __NAME__, command)
            logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
            try:
                self.con.rollback()
            except:
                logging.debug("[%s] Rollback Failed:", __NAME__, exc_info = True)
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
            logging.error('[%s] SQL Commit Failed, see log', __NAME__)
            logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
        
    def close(self):
        try:
            self.c.close()
            self.con.close()
        except:
            logging.error('[%s] Failed to close database, see log', __NAME__)
            logging.debug("[%s] Traceback: ", __NAME__, exc_info = True)
        
    def remove_all(self):
        return self.execute("""DELETE FROM history""")
        
    def remove_history(self, jobs=None):       
        if jobs == None:
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
        
    def fetch_history(self, start=None, limit=None,):
        
        # Get the number of results
        if self.execute('select count(*) from History'):
            total_items = self.c.fetchone()
        else:
            total_items = -1
        
        if start and limit:
            t = (start,limit)
            fetch_ok = self.execute('SELECT * FROM history ORDER BY completed desc LIMIT ?, ?', t)
        else:        
            fetch_ok = self.execute('SELECT * FROM history ORDER BY completed desc')
        if fetch_ok:
            items = self.c.fetchall()
        else:
            items = []
    
        # Unpack the single line stage log
        # Stage Name is seperated by ::: stage lines by ; and stages by \r\n
        items = [unpack_history_info(item) for item in items]
        
        return (items, total_items)
    
    def get_history_size(self):
        if self.execute('SELECT sum(bytes) FROM history'):
            f = self.c.fetchone()
            return f['sum(bytes)']
        return 0
    
    
    def get_script_log(self, nzo_id):
        t = (nzo_id,)
        if self.execute('SELECT script_log FROM history WHERE nzo_id=?', t):
            f = self.c.fetchone()
            return zlib.decompress(f['script_log'])
        else:
            return ''
    
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def build_history_info(nzo, storage='', path='', postproc_time=0, script_output='', script_line=''):
    ''' Collects all the information needed for the database '''
    
    flagRepair, flagUnpack, flagDelete = nzo.get_repair_opts()
    nzo_info = nzo.get_nzo_info()
    
    # Get the url and newzbin msgid 
    report = nzo_info.get('msgid', '')
    if report:
        url = 'https://newzbin.com/browse/post/%s/' % (report)
    else:
        url = nzo_info.get('url', '')
    
    #group = nzo.get_group()
    
    completed = int(time.time())
    name = nzo.get_original_dirname()
    
    nzb_name = nzo.get_filename()
    category = nzo.get_cat()
    pps = ['','R','U','D']
    try:
        pp = pps[sabnzbd.opts_to_pp(flagRepair, flagUnpack, flagDelete)]
    except:
        pp = ''
    script = nzo.get_script()
    status = nzo.get_status()
    nzo_id = nzo.get_nzo_id()
    bytes = nzo.get_bytes_downloaded()
    
    if script_output:        
        # Compress the output of the script
        script_log = sqlite3.Binary(zlib.compress(script_output))
        #
    else:
        script_log = ''
    
    download_time = nzo_info.get('download_time', 0)

    downloaded = nzo.get_bytes_downloaded()
    completeness = 0
    fail_message = nzo.get_fail_msg()
    url_info = nzo_info.get('more_info', '')
    
    # Get the dictionary containing the stages and their unpack process
    stages = nzo.get_unpack_info()
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
            logging.error('[%s] Invalid stage logging in history for %s (\\r\\n)', __NAME__, item['name'])
            logging.debug('[%s] Lines: %s', __NAME__, item['stage_log'])
            lines = []
        item['stage_log'] = []
        for line in lines:
            stage = {}
            try:
                key, logs = line.split(':::')
            except:
                logging.debug('[%s] Missing key:::logs "%s"', __NAME__, line)
                key = line
                logs = ''
            stage['name'] = key
            stage['actions'] = []
            try:
                logs = logs.split(';')
            except:
                logging.error('[%s] Invalid stage logging in history for %s (;)', __NAME__, item['name'])
                logging.debug('[%s] Logs: %s', __NAME__, logs)
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