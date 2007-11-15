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
    def __init__(self, dirscan_dir, dirscan_speed, repair, unpack, delete, script):
        Thread.__init__(self)
        
        self.dirscan_dir = dirscan_dir
        self.dirscan_speed = dirscan_speed
        
        self.r = repair
        self.u = unpack
        self.d = delete
        self.s = script
        
        self.shutdown = False
        
    def stop(self):
        logging.info('[%s] Dirscanner shutting down', __NAME__)
        self.shutdown = True
        
    def run(self):
        logging.info('[%s] Dirscanner starting up', __NAME__)
        
        while not self.shutdown:

            # Use variable scan delay
            x = self.dirscan_speed
            while (x > 0) and not self.shutdown:
                time.sleep(1.0)
                x = x - 1

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
                                                          self.d, self.s, data))
                                sabnzbd.backup_nzb(filename, data)
                            else:
                                zf = zipfile.ZipFile(path)
                                try:
                                    for name in zf.namelist():
                                        data = zf.read(name)
                                        name = os.path.basename(name)
                                        if data:
                                            sabnzbd.add_nzo(NzbObject(name, self.r, self.u, 
                                                                      self.d, self.s, data))
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

                
#------------------------------------------------------------------------------
# Thread for newzbin msgid queue
#
class MSGIDGrabber(Thread):
    def __init__(self, nzbun, nzbpw):
        Thread.__init__(self)
        self.nzbun = nzbun
        self.nzbpw = nzbpw
        self.queue = []
		
    def grab(self, msgid, nzo):
        self.queue.append((msgid, nzo))
        logging.debug("Adding msgid %s to the queue", msgid)
        
    def run(self):
        while self.queue:
            (msgid, nzo) = self.queue.pop(0)
            logging.debug("[%s] Popping msgid %s", __NAME__, msgid)
            filename, data, cat_root, cat_tail = nzbgrab.grabnzb(msgid, self.nzbun, self.nzbpw)
            if filename and data:
                sabnzbd.insert_future_nzo(nzo, filename, data, cat_root, cat_tail)
            else:
                sabnzbd.remove_nzo(nzo.nzo_id, False)

#------------------------------------------------------------------------------          
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


################################################################################
# Real_Path                                                                    #
################################################################################
def real_path(loc, path):
    if not ((os.name == 'nt' and path[0].isalpha() and path[1] == ':') or \
            (path[0] == '/' or path[0] == '\\')):
        path = loc + '/' + path
    return os.path.normpath(os.path.abspath(path))


################################################################################
# Create_Real_Path                                                             #
################################################################################
def create_real_path(name, loc, path):
    if path:
        my_dir = real_path(loc, path)
        if not os.path.exists(my_dir):
            logging.info('%s directory: %s does not exist, try to create it', name, my_dir)
            try:
                os.makedirs(my_dir)
            except:
                logging.error('Cannot create directory %s', my_dir)
        if not os.access(my_dir, os.R_OK + os.W_OK):
            logging.error('%s directory: %s error accessing', name, my_dir)
            return ""
        return my_dir


################################################################################
# Get_User_ShellFolders
#
# Return a dictionary with Windows Special Folders
# Read info from the registry
################################################################################

def Get_User_ShellFolders():
    import _winreg
    dict = {}
 
    # Open registry hive
    try:
        hive = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    except WindowsError:
        logging.error("Cannot connect to registry hive HKEY_CURRENT_USER.")
        return dict
 
    # Then open the registry key where Windows stores the Shell Folder locations
    try:
        key = _winreg.OpenKey(hive, "Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
    except WindowsError:
        logging.error("Cannot open registry key Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders.")
        _winreg.CloseKey(hive)
        return dict
 
    try:
        for i in range(0, _winreg.QueryInfoKey(key)[1]):
            name, value, val_type = _winreg.EnumValue(key, i)
            dict[name] = value
            i += 1
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return dict
    except WindowsError:
        # On error, return empty dict.
        logging.error("Failed to read registry keys for special folders")
        _winreg.CloseKey(key)
        _winreg.CloseKey(hive)
        return {}


################################################################################
# save_configfile
#
################################################################################
def save_configfile(cfg):

    cfg.write()
    f = open(cfg.filename)
    x = f.read()
    f.close()
    f = open(cfg.filename, "w")
    f.write(x)
    f.flush()
    f.close()
