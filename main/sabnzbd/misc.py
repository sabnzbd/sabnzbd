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
import re
import zipfile
import webbrowser
import tempfile
import Queue

from threading import *
from sabnzbd.nzbstuff import NzbObject
from sabnzbd import nzbgrab
from sabnzbd.constants import *

RE_VERSION = re.compile('(\d+)\.(\d+)\.(\d+)([a-zA-Z]*)(\d*)')
RE_UNITS = re.compile('(\d+\.*\d*)\s*([KMGTP]*)', re.I)
TAB_UNITS = ('', 'K', 'M', 'G', 'T', 'P')

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
                    candidate = ext.lower() in ('.nzb', '.zip')
                    if candidate:
                        stat_tuple = os.stat(path)
                    if candidate and stat_tuple.st_size > 0:
                        try:
                            logging.info('[%s] Trying to import %s', __NAME__, path)
                            
                            # Wait until the attributes are stable for 1 second
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
        self.queue = Queue.Queue()

    def grab(self, msgid, nzo):
        logging.debug("Adding msgid %s to the queue", msgid)
        self.queue.put((msgid, nzo))

    def stop(self):
        # Put None on the queue to stop "run"
        self.queue.put((None, None))

    def run(self):
        while 1:
            (msgid, nzo) = self.queue.get()
            if not msgid:
                break
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


################################################################################
# Launch a browser for various purposes
# including panic messages
#
################################################################################
MSG_BAD_NEWS = r'''
    <html>
    <head>
    <title>Problem with %s %s</title>
    </head>
    <body>
    <h1><font color="#0000FF">Welcome to %s %s</font></h1>
    <p align="center">&nbsp;</p>
    <p align="center"><font size="5">
    <blockquote>
        %s
    </blockquote>
    <br>Program did not start!<br>
    </body>
</html>
'''

MSG_BAD_PORT = r'''
    SABnzbd needs a free tcp/ip port for its internal web server.<br>
    Port %s on %s was tried , but it is not available.<br>
    <br>
    Please restart SABnzbd with a different port number.<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --server %s:%s<br>
    <br>
    If you get this error message again, please try a different number.<br>
'''

MSG_BAD_QUEUE = r'''
    SABnzbd detected saved data from an older SABnzbd version<br>
    but cannot re-use the data of the older program.<br><br>
    You may want to finish your queue first with the older program.<br><br>
    After that, start this program with the "--clean" option.<br>
    This will erase the current queue and history!<br>
    <br>
    %s<br>
      &nbsp;&nbsp;&nbsp;&nbsp;%s --clean<br>
    <br>
'''

MSG_BAD_TEMPL = r'''
    SABnzbd cannot find its web interface files.<br>
    Please install the program again.<br>
    <br>
'''


def panic_message(panic, host, port):

    if os.name == 'nt':
        os_str = 'Press Startkey+R and type the line (example):'
    else:
        os_str = 'Open a Terminal window and type the line (example):'

    if panic == PANIC_PORT:
        newport = port + 1
        newport = "%s" % newport
        msg = MSG_BAD_PORT % (port, host, os_str, sabnzbd.MY_FULLNAME, host, newport)
    elif panic == PANIC_TEMPL:
        msg = MSG_BAD_TEMPL
    else:
        msg = MSG_BAD_QUEUE % (os_str, sabnzbd.MY_FULLNAME)


    msg = MSG_BAD_NEWS % (sabnzbd.MY_NAME, sabnzbd.__version__, sabnzbd.MY_NAME, sabnzbd.__version__, msg)
        
    msgfile, url = tempfile.mkstemp(suffix='.html')
    os.write(msgfile, msg)
    os.close(msgfile)
    return url

def launch_a_browser(host, port, panic=PANIC_NONE):
    """Launch a browser pointing to an URL or a to local errormessage page
    """
    if sabnzbd.NO_BROWSER:
        return

    if panic == PANIC_NONE:
        url = "http://%s:%s/sabnzbd" % (host, port)
    else:
        url = panic_message(panic, host, port)

    logging.info("Lauching browser with %s", url)
    try:
        webbrowser.open(url, 2, 1)
    except:
        # Python 2.4 does not support parameter new=2
        webbrowser.open(url, 1, 1)



################################################################################
# Check latest version
#
# Perform an online version check
# Formula
# - the online version is always: <major>.<minor>.<bugfix>
# - the local version is <major>.<minor>.<bugfix>[rc|beta]<cand>
#
# The <cand> value for the online version is assumned to be 99.
# The <cand> value for the local version is 1..98
# This is done to signal beta|rc users of availability of the final
# version (which is implicitly 99).
# People are NOT informed to upgrade to a higher beta|rc version, since these
# are not in the online version indicator.
#
################################################################################

def check_latest_version():
    try:
        fn = urllib.urlretrieve('http://sabnzbdplus.sourceforge.net/version/latest')[0]
        f = open(fn, 'r')
        data = f.read()
        f.close()
    except:
        return

    latest_label = data.split()[0]
    url = data.split()[1]
    m = RE_VERSION.search(latest_label)
    latest = int(m.group(1))*1000000 + int(m.group(2))*10000 + int(m.group(3))*100 + 99
    
    m = RE_VERSION.search(sabnzbd.__version__)
    current = int(m.group(1))*10000 + int(m.group(2))*10000 + int(m.group(3))*100
    try:
        current = current + int(m.group(5))
    except:
        current = current + 99

    logging.debug("Checked for a new release, cur= %s, latest= %s (on %s)", current, latest, url)

    if current < latest:
        sabnzbd.NEW_VERSION = "%s;%s" % (latest_label, url)


def from_units(val):
    """ Convert K/M/G/T/P notation to pure integer
    """
    val = str(val).strip().upper()
    if val == "-1":
        return val
    m = RE_UNITS.search(val)
    if m.group(2):
        val = float(m.group(1))
        unit = m.group(2)
        n = 0
        while unit != TAB_UNITS[n]:
            val = val * 1024.0
            n = n+1
    else:
        val = m.group(1)
    return float(val)


def to_units(val):
    """ Convert number to K/M/G/T/P notation
    """
    val = str(val).strip()
    if val == "-1":
        return val
    n= 0
    val = float(val)
    while (val > 1023.0) and (n < 5):
        val = val / 1024.0
        n= n+1
    unit = TAB_UNITS[n]
    if unit:
        return "%.1f %s" % (val, unit)
    else:
        return "%.0f" % val
