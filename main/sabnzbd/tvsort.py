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
from sabnzbd.misc import move_to_path, cleanup_empty_directories, get_unique_filename
from sabnzbd.constants import tv_episode_match, date_match


def TVSeasonCheck(path, dirname):
    """ Determine if seasonal job """
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
                path = os.path.abspath(os.path.join(path, folders))
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
        title, show_name3, show_name2 = getTitles(match1, dirname)
    
        season = int(match1.group(1).strip('_')) # season number
        ep_no = int(match1.group(2)) # episode number

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
        extension = False
        #do this last
        if path.endswith('.%ext'):
            extension = True
            path = path.replace(".%ext", '')

            
        path = path.replace("%s.n", show_name2)
        path = path.replace("%s_n", show_name3)
        path = path.replace("%sn", title)
        #replace season
        path = path.replace("%0s", season)
        path = path.replace("%s", _season)
        
        #gather the episode name
        ep_name, ep_name2, ep_name3, path = getDescriptions(match1, dirname, path, '%e\.?\_?n')
        
        path = path.replace("%e.n", ep_name2)
        path = path.replace("%e_n", ep_name3)
        path = path.replace("%en", ep_name)
        
        #replace episode number
        path = path.replace("%0e", ep_no)
        path = path.replace("%e", _ep_no)
        
        #Lowercase all characters encased in {}
        RE_LOWERCASE = re.compile('\{([^\{]*)\}', re.I)
        while 1:
            m = RE_LOWERCASE.match(path)
            if not m:
                break
            section = path[m.start(1):m.end(1)].lower()
            folders = path[:m.start()] + section + path[m.end():]
            
        # just incase
        path = path.replace('{', '')
        path = path.replace('}', '')
    
            
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


def move_to_parent_folder(workdir):
    """ Move content of 'workdir' to 'workdir/..' possibly skipping some files
        If afterwards the directory is not empty, rename it to _JUNK_folder, else remove it.
    """
    skipped = False # Keep track of any skipped files
    path1 = os.path.abspath(os.path.join(workdir, '..')) #move things to the folder below

    for root, dirs, files in os.walk(workdir):
        for _file in files:
            path = os.path.join(root, _file)
            new_path = path.replace(workdir, path1)
            path, new_path = get_unique_filename(path,new_path)
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
        if os.path.exists(filepath):
            size = os.stat(filepath).st_size
            if size > 130000000:
                if 'sample' not in file:
                    tmp, ext = os.path.splitext(file)
                    newname = "%s%s" % (name,ext)
                    newpath = os.path.join(path, newname)
                    if not os.path.exists(newpath):
                        try:
                            os.rename(filepath,newpath)
                        except:
                            logging.error("[%s] Failed to rename: %s to %s", path, newpath)
                        rename_similar(path, file, name)
                        break
                    
                    
                    
def MovieRenamer(path, _files, _name):
    renamed = False
    files = []
    
    # remove any files below 300MB from this list
    for file in _files:
        filepath = os.path.join(path, file)
        if os.path.exists(filepath):
            size = os.stat(filepath).st_size
            if size > 314572800:
                if 'sample' not in file:
                    files.append(file)
    
    length = len(files)
    # if there is only one extracted file rename it
    if length == 1:
        file = files[0]
        filepath = os.path.join(path, file)
        if os.path.exists(filepath):
            tmp, ext = os.path.splitext(file)
            newname = "%s%s" % (_name,ext)
            newpath = os.path.join(path, newname)
            try:
                os.rename(filepath,newpath)
            except:
                logging.error("[%s] Failed to rename: %s to %s", filepath,newpath)
            rename_similar(path, file, _name)
    # if there is more than one extracted file check for CD1/1/A in the title
    elif sabnzbd.MOVIE_SORT_EXTRA:
        expressions = []
        expressions.append(re.compile('\Wcd(\d)\W', re.I)) # .cd1.avi
        expressions.append(re.compile('\W(\d)\W', re.I)) # .1.avi
        expressions.append(re.compile('\W(\w)\W', re.I)) # .a.avi
        matched_files = []
        for regex in expressions:
            regex = re.compile(regex, re.I)
            matched_files = check_for_sequence(regex, files)
            if matched_files:
                break
            
        # rename files marked as in a set
        if matched_files:
            for m in matched_files.iteritems():
                index, file = m                
                for f in files:
                    if f == file:
                        filepath = os.path.join(path, f)
                        tmp, ext = os.path.splitext(file)
                        name = '%s%s' % (_name, sabnzbd.MOVIE_SORT_EXTRA)
                        name = name.replace('%1', index)
                        name = name + ext
                        newpath = os.path.join(path, name)
                        try:
                            os.rename(filepath,newpath)
                        except:
                            logging.error("[%s] Failed to rename: %s to %s", filepath,newpath)
                        rename_similar(path, f, _name)
        else:
            logging.debug("[%s] Movie files not in sequence %s", __NAME__, _files)
                        
    
def check_for_sequence(regex, files):
    matches = {}
    prefix = None
    for file in files:
        match1 = regex.search(file)
        if match1:
            if not prefix or prefix == file[:match1.start()]:
                matches[match1.group(1)] = file
                prefix = file[:match1.start()]
            
    # Don't do anything if only one or no files matched
    if len(matches.keys()) < 2:
        return []
            
    key_prev = 0
    passed = True
    alphabet = ['a','b','c','d','e','f','g','h','i','j','k','l','m']
    
    for m in matches.iteritems():
        key, file = m
        if key.isdigit():
            key = int(key)
            if not key_prev:
                key_prev = key
            else:
                if key - key_prev == 1:
                    key_prev = key
                else:
                    passed = False
        else:
            if alphabet[key_prev] == key:
                key_prev += 1
                # convert {'b':'filename.avi'} to {'2', 'filename.avi'}
                matches.pop(key)
                matches[key_prev] = file
                
            else:
                passed = False
            
    if passed:
        return matches
    else:
        return []

def MovieCheck(_path, dirname):
    if not sabnzbd.MOVIE_SORT_STRING:
        return _path, '', False
    folders = sabnzbd.MOVIE_SORT_STRING
    extension = False
    RE_YEAR = re.compile('\((\d{4})\)', re.I)
    year_match = RE_YEAR.search(dirname)
    if year_match:
        year = year_match.group(1)
        title = dirname[:year_match.start()]
    else:
        year = ''
        title = dirname
        
    try:
        decade = year[2:3]+'0'
    except:
        decade = ''
        
    title, title2, title3 = getTitles(year_match, dirname)

    
    # replace any backslashes with forward slashes
    folders = folders.replace('\\','/')
    # replace the titles
    folders = folders.replace('%title', title)
    folders = folders.replace('%.title', title2)
    folders = folders.replace('%_title', title3)
    # replace the year and decade
    folders = folders.replace('%y', year)
    folders = folders.replace('%decade', decade)
    # if year is missing, get rid left over characters
    folders = folders.replace('()', '')
    folders = folders.replace('..', '')
    folders = folders.replace('__', '')
    folders = folders.replace('  ', ' ')
    folders = folders.replace(' .%ext', '.%ext')
    
    #Lowercase all characters encased in {}
    RE_LOWERCASE = re.compile('\{([^\{]*)\}', re.I)
    while 1:
        m = RE_LOWERCASE.match(folders)
        if not m:
            break
        section = folders[m.start(1):m.end(1)].lower()
        folders = folders[:m.start()] + section + folders[m.end():]
        
    # just incase - remove extra {}
    folders = folders.replace('{', '')
    folders = folders.replace('}', '')
    
    if folders.endswith('.%ext'):
        extension = True
        folders = folders.replace(".%ext", '')
    
    folder_seq = folders.split('/')
    if len(folder_seq) > 1:
        folders = ''
        for folder in folder_seq:
            folders += folder.strip().strip('_').strip('.').strip()
            folders += '/'
    
    path = os.path.abspath(os.path.join(_path, folders))
    if extension:
        head, tail = os.path.split(path)
    else:
        head = path
        tail = ''
        
    return head, tail, True

def rename_similar(path, file, name):
    file_prefix, ext = os.path.splitext(file)
    for root, dirs, files in os.walk(path):
        for _file in files:
            fpath = os.path.join(root, _file)
            tmp, ext = os.path.splitext(_file)
            if tmp == file_prefix:
                newname = "%s%s" % (name,ext)
                newpath = os.path.join(path, newname)
                if not os.path.exists(newpath):
                    try:
                        os.rename(fpath,newpath)
                    except:
                        logging.error("[%s] Failed to rename similar file: %s to %s", path, newpath)
                        
                        


def DateCheck(path, dirname):
    if sabnzbd.ENABLE_DATE_SORTING and sabnzbd.DATE_SORT_STRING:
        match = checkForDate(dirname, date_match)
        if match:
            complete_dir, filename_set = formatDatePath(path, match, dirname)
            return complete_dir, filename_set, True
        
    return path, '', False
    
    
def checkForDate(filename, matcher):
    """
    Regular Expression match for date based files
    Returns the MatchObject if a match is made
    """
    match2 = None
    if matcher:
        for expression in matcher:
            regex = re.compile(expression)
            match1 = regex.search(filename)
            if match1:
                return match1
    return None

def formatDatePath(_path, match, dirname):
    if len(match.group(1)) > 2: #2008-10-16
        year = match.group(1)
        month = match.group(2)
        date =  match.group(3)
        decade = year[2:3]+'0'
    else:                       #10.16.2008
        year = match.group(3)
        month = match.group(1)
        date =  match.group(2)
        decade = year[2:3]+'0'
        
    month2 = month.rjust(2,'0')
    date2 = date.rjust(2,'0')
        
    extension = False
        
    title, title2, title3 = getTitles(match, dirname)
    folders = sabnzbd.DATE_SORT_STRING
    description, description2, description3, folders = getDescriptions(match, dirname, folders, '%\.?\_?desc')
    
    # replace any backslashes with forward slashes
    folders = folders.replace('\\','/')
    # replace the titles
    folders = folders.replace('%t', title)
    folders = folders.replace('%.t', title2)
    folders = folders.replace('%_t', title3)
    # replace the year and decade
    folders = folders.replace('%y', year)

    folders = folders.replace("%.desc", description2)
    folders = folders.replace("%_desc", description3)
    folders = folders.replace("%desc", description)
    
    folders = folders.replace('%decade', decade)
    folders = folders.replace('%m', month)
    folders = folders.replace('%d', date)
    folders = folders.replace('%0m', month2)
    folders = folders.replace('%0d', date2)
    
    # if year is missing, get rid left over characters
    
    folders = folders.replace('()', '')
    folders = folders.replace('..', '')
    folders = folders.replace('__', '')
    folders = folders.replace('  ', ' ')
    folders = folders.replace(' .%ext', '.%ext')
    
    #Lowercase all characters encased in {}
    RE_LOWERCASE = re.compile('\{([^\{]*)\}', re.I)
    while 1:
        m = RE_LOWERCASE.match(folders)
        if not m:
            break
        section = folders[m.start(1):m.end(1)].lower()
        folders = folders[:m.start()] + section + folders[m.end():]
        
    # just incase - remove extra {}
    folders = folders.replace('{', '')
    folders = folders.replace('}', '')
    
    if folders.endswith('.%ext'):
        extension = True
        folders = folders.replace(".%ext", '')
    
    folder_seq = folders.split('/')
    if len(folder_seq) > 1:
        folders = ''
        for folder in folder_seq:
            folders += folder.strip().strip('_').strip('.').strip()
            folders += '/'
    
    path = os.path.abspath(os.path.join(_path, folders))
    if extension:
        head, tail = os.path.split(path)
    else:
        head = path
        tail = ''
        
    return head, tail

def DateRenamer(path, files, name):
    
    renamed = None
    #find the master file to rename
    for file in files:
        filepath = os.path.join(path, file)
        if os.path.exists(filepath):
            size = os.stat(filepath).st_size
            if size > 130000000:
                if 'sample' not in file:
                    tmp, ext = os.path.splitext(file)
                    newname = "%s%s" % (name,ext)
                    newpath = os.path.join(path, newname)
                    if not os.path.exists(newpath):
                        try:
                            os.rename(filepath,newpath)
                        except:
                            logging.error("[%s] Failed to rename: %s to %s", path, newpath)
                        rename_similar(path, file, name)
                        break
    
    
def getTitles(match, name):
    '''
    The title will be the part before the match
    Clean it up and title() it
    '''
    if match:
        name = name[:match.start()]
    title = name.replace('.', ' ').replace('_', ' ')
    title = title.strip().strip('(').strip('_').strip('-').strip().strip('_')
    title = title.title() # title
    #title applied uppercase to 's Python bug?
    title = title.replace("'S", "'s")
    
    title2 = title.replace(" - ", "-").replace(' ','.').replace('_','.')
    title3 = title.replace(' ','_').replace('.','_')
    
    return title, title2, title3

def getDescriptions(match, name, path, desc_token):
    '''
    If present, get a description from the nzb name.
    A description has to be after the matched item, seperated either
    like ' - Description' or '_-_Description'
    '''
    if match:
        ep_name = name[match.end():]
    else:
        ep_name = name
    RE_EPNAME = re.compile('_?-[_\W]', re.I)
    m = RE_EPNAME.search(ep_name)
    if m:
        ep_name = ep_name[m.end():].strip('_').strip().strip('_').replace('.', ' ').replace('_', ' ')
        ep_name2 = ep_name.replace(" - ", "-").replace(" ", ".")
        ep_name3 = ep_name.replace(" ", "_")
        return ep_name, ep_name2, ep_name3, path
    else:
        regex_string = '(\W*)(token)(\s?)'.replace('token', desc_token)
        epname_match = re.compile(regex_string).search(path)
        if epname_match:
            path = path.replace(path[epname_match.start(0):epname_match.end(2)], '')
        return '', '', '', path
    
def check_for_folder(path):
    for root, dirs, files in os.walk(path):
        if dirs:
            return True
    return False
