#!/usr/bin/python -OO
# Copyright 2008 sw1tch <swi-tch@users.sourceforge.net>
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
sabnzbd.tvsort - Sorting downloads into seasons & episodes
"""
#------------------------------------------------------------------------------

__NAME__ = "tvsort"

import os
import Queue
import logging
import shutil
import re

import sabnzbd
from sabnzbd.misc import move_to_path, cleanup_empty_directories
from sabnzbd.constants import tv_episode_match


def TVSeasonCheck(path, dirname):
    """ Determine if seasonal job """
    #   'dirname' base-name of the job.
    #   Even when files will go into the season folder a temporary workdir
    #   is used.
    #   Return base-name of destination, potentially a folder-tree (nothing is created).
    #       Examples: "The One Movie" or "My Show/Season 1/Episode 1"
    #   unique=True for normal handling
    #   unique=False when later the folder content will be copied to "folder/.."

    tv_file = False
    filename_set = None
    _path = path
    if sabnzbd.ENABLE_TV_SORTING and sabnzbd.TV_SORT_STRING:
        #First check if the show matches TV episode regular expressions. Returns regex match object
        match1, match2 = checkForTVShow(dirname, tv_episode_match)
        if match1:
            logging.debug("[%s] Found TV Show - Starting folder sort (%s)", __NAME__, dirname)
            folders, filename_set, tv_file = getTVInfo(match1, match2, dirname)
            if folders:
                path = os.path.realpath(os.path.join(path, folders))
        else:
            dvdmatch = []
            #check if the show matches DVD episode naming
            '''DISABLE FOR NOW
            dvdmatch = checkForTVDVD(dirname)
            if dvdmatch:
                logging.debug("[%s] Found TV DVD - Starting folder sort (%s)", __NAME__, dirname)
                dirname, unique_dir = formatFolders(dirname, dvdmatch, dvd = True)
                unique_dir = False'''

    return path, filename_set, tv_file



def getTVInfo(match1, match2, dirname):
    """
    Returns Title, Season and Episode naming from a REGEX match
    """
    try:
        title = dirname[:match1.start()].replace('.', ' ')
        title = title.strip().strip('_').strip('-').strip()
        title = title.title() # title
        #title applied uppercase to 's Python bug?
        title = title.replace("'S", "'s")
    
        season = int(match1.group(1).strip('_')) # season number
        ep_no = int(match1.group(2)) # episode number
    
        #gather the episode name
        spl = dirname[match1.start():].split(' - ',2)
    
        try:
            ep_name = spl[1].strip('_').strip().strip('_')
        except:
            ep_name = ''
            
        #provide alternatve formatting   
        _season = str(season)
        if season < 10:
            season = '0%s' % (season)
        else:
            season = str(season)
            
        _ep_no = str(ep_no)
        if ep_no < 10:
            ep_no = '0%s' % (ep_no)
        else:
            ep_no = str(ep_no)
            
        #dual episode support
        if match2: #match2 is only present if a second REGEX match has been made
            ep_no2 = int(match2.group(2)) # two part episode#
            _ep_no2 = ep_no2
            if int(ep_no2) < 10:
                ep_no2 = '0%s' % (ep_no2)
            ep_no = '%s-%s' % (ep_no,ep_no2)
            _ep_no = '%s-%s' % (_ep_no,_ep_no2)
            
        path = sabnzbd.TV_SORT_STRING
        #replace showname
        show_name2 = title.replace(" ", ".")
        show_name3 = title.replace(" ", "_")
        extension = False
        #do this last
        if path.endswith('.%ext'):
            extension = True
            path = path.replace(".%ext", '')

            
        path = path.replace("%s.n", title)
        path = path.replace("%s_n", title)
        path = path.replace("%sn", title)
        #replace season
        path = path.replace("%0s", season)
        path = path.replace("%s", _season)
        
        if ep_name:
            #replace episodename
            ep_name2 = ep_name.replace(" ", ".")
            ep_name3 = ep_name.replace(" ", "_")
            path = path.replace("%e.n", ep_name2)
            path = path.replace("%e_n", ep_name2)
            path = path.replace("%en", ep_name)
        else:
            epname_match = re.compile('(\W*)(%e\.?\_?n)(\s?)').search(path)
            if epname_match:
                path = path.replace(path[epname_match.start(0):epname_match.end(2)], '')
        
        #replace episode number
        path = path.replace("%0e", ep_no)
        path = path.replace("%e", _ep_no)
    
            
        #do this last
        if extension:
            head, tail = os.path.split(path)
        else:
            head = path
            tail = ''
            
        return head, tail, True
    except:
        logging.error("[%s] Error getting TV info (%s)", __NAME__, dirname)
        return '', '', False


def checkForTVDVD(filename):
    """
    Regular Expression match for TV DVD's such as ShowName - Season 1 [DVD 1] ShowName S1D1
    Returns the MatchObject if a match is made
    """
    regularexpressions = [re.compile('Season (\d+) \[?DVD\s?(\d+)(\/\d)?\]?'),# Season 1 [DVD1]
                            re.compile('S(\d+) ?D(\d+)')]# S1D1
    for regex in regularexpressions:
        match = regex.search(filename)

    if match:
        return match
    return None




def checkForTVShow(filename, matcher): #checkfortvshow > formatfolders > gettvinfo
    """
    Regular Expression match for TV episodes named either 1x01 or S01E01
    Returns the MatchObject if a match is made
    """
    match2 = None
    if matcher:
        for expression in matcher:
            regex = re.compile(expression)
            match1 = regex.search(filename)
            if match1:
                match2 = regex.search(filename,match1.end())
                return match1, match2
    return None, None


def TVSeasonMove(workdir):
    """ Move content of 'workdir' to 'workdir/..' possibly skipping some files
        If afterwards the directory is not empty, rename it to _JUNK_folder, else remove it.
    """
    skipped = False # Keep track of any skipped files
    path1 = os.path.abspath(os.path.join(workdir, '..')) #move things to the folder below

    for root, dirs, files in os.walk(workdir):
        for _file in files:
            path = os.path.join(root, _file)
            new_path = path.replace(workdir, path1)
            move_to_path(path, new_path, False)

    cleanup_empty_directories(workdir)
    try:
        os.rmdir(workdir)
    except:
        pass
        
    return path1
        
def TVRenamer(path, files, name):
    renamed = None
    #find the master file to rename
    for file in files:
        filepath = os.path.join(path, file)
        if os.path.exist(filepath):
            size = os.stat(filepath).st_size
            if size > 130000000:
                if 'sample' not in file:
                    tmp, ext = os.path.splitext(file)
                    newname = "%s%s" % (name,ext)
                    newpath = os.path.join(path, newname)
                    if not os.path.exists(newpath):
                        try:
                            os.rename(filepath,newpath)
                            renamed = tmp
                            break
                        except:
                            logging.error("[%s] Failed to rename: %s to %s", path, newpath)
                        
    #rename any files that were named the same as the master file
    if renamed: 
        for root, dirs, files in os.walk(path):
            for _file in files:
                fpath = os.path.join(root, _file)
                tmp, ext = os.path.splitext(_file)
                if tmp == renamed:
                    newname = "%s%s" % (name,ext)
                    newpath = os.path.join(path, newname)
                    if not os.path.exists(newpath):
                        try:
                            os.rename(fpath,newpath)
                        except:
                            logging.error("[%s] Failed to rename: %s to %s", path, newpath)
            
    