#!/usr/bin/python -OO
# Copyright 2005 Gregor Kaufmann <tdian@users.sourceforge.net>
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
sabnzbd.misc - misc classes
"""
__NAME__ = "sabnzbd.misc"

import os
import time
import logging
import sabnzbd
import cherrypy
import urllib
import zipfile

from threading import *
from sabnzbd.nzbstuff import NzbObject
from sabnzbd import nzbgrab

#------------------------------------------------------------------------------
class DirScanner(Thread):
    def __init__(self, dirscan_dir, repair, unpack, delete):
        Thread.__init__(self)
        
        self.dirscan_dir = dirscan_dir
        
        self.r = repair
        self.u = unpack
        self.d = delete
        
        self.shutdown = False
        
    def stop(self):
        logging.info('[%s] Dirscanner shutting down', __NAME__)
        self.shutdown = True
        
    def run(self):
        logging.info('[%s] Dirscanner starting up', __NAME__)
        
        while not self.shutdown:
            time.sleep(1.0)
            try:
                files = os.listdir(self.dirscan_dir)
                
                for filename in files:
                    path = os.path.join(self.dirscan_dir, filename)
                    root, ext = os.path.splitext(path)
                    if ext.lower() in ('.nzb', '.zip'):
                        try:
                            logging.info('[%s] Trying to import %s', __NAME__, path)
                            stat_tuple = os.stat(path)
                            
                            while 1:
                                time.sleep(1.0)
                                stat_tuple_tmp = os.stat(path)
                                if stat_tuple == stat_tuple_tmp:
                                    break
                                else:
                                    stat_tuple = stat_tuple_tmp
                                    
                            if ext.lower() == '.nzb':
                                f = open(path, 'rb')
                                data = f.read()
                                f.close()
                                sabnzbd.add_nzo(NzbObject(filename, self.r, self.u, 
                                                          self.d, data))
                                sabnzbd.backup_nzb(filename, data)
                            else:
                                zf = zipfile.ZipFile(path)
                                try:
                                    for name in zf.namelist():
                                        data = zf.read(name)
                                        name = os.path.basename(name)
                                        if data:
                                            sabnzbd.add_nzo(NzbObject(name, self.r, self.u, 
                                                                      self.d, data))
                                            sabnzbd.backup_nzb(name, data)
                                finally:
                                    zf.close()
                        finally:
                            try:
                                os.remove(path)
                            except:
                                logging.exception("[%s] Error removing %s", 
                                                  __NAME__, path)
            except:
                logging.exception("Error importing")
                
class MSGIDGrabber(Thread):
    def __init__(self, nzbun, nzbpw, msgid, future_nzo):
        Thread.__init__(self)        
        self.nzbun = nzbun
        self.nzbpw = nzbpw
        self.msgid = msgid
        self.future_nzo = future_nzo
        
    def run(self):
        try:
            filename, data, cat_root, cat_tail = nzbgrab.grabnzb(self.msgid, self.nzbun, self.nzbpw)
            if filename and data:
                sabnzbd.insert_future_nzo(self.future_nzo, filename, data, cat_root, cat_tail)                        
            else:
                sabnzbd.remove_nzo(self.future_nzo.nzo_id, False)
        except:
            logging.exception("[%s] Error fetching msgid %s", 
                              __NAME__, self.msgid)
            sabnzbd.remove_nzo(self.future_nzo.nzo_id, False)
            
class URLGrabber(Thread):
    def __init__(self, url, future_nzo):
        Thread.__init__(self)
        self.url = url
        self.future_nzo = future_nzo
    
    def run(self):
        try:
            opener = urllib.FancyURLopener({})
            opener.prompt_user_passwd = None
            fn, header = opener.retrieve(self.url)
            
            filename, data = (None, None)
            f = open(fn, 'r')
            data = f.read()
            f.close()
            os.remove(fn)
            
            for tup in header.items():
                for item in tup:
                    if "filename=" in item:
                        filename = item[item.index("filename=") + 9:]
                        break
                        
            if data:
                if not filename:
                     filename = os.path.basename(self.url)
                sabnzbd.insert_future_nzo(self.future_nzo, filename, data)
            else:
                sabnzbd.remove_nzo(self.future_nzo.nzo_id, False)
                
        except:
            logging.exception("[%s] Error adding url %s", __NAME__, self.url)
            sabnzbd.remove_nzo(self.future_nzo.nzo_id, False)
