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


def TVSeasonCheck(dirname):
    """ Determine if seasonal job """
    #   'dirname' base-name of the job.
    #   Even when files will go into the season folder a temporary workdir
    #   is used.
    #   Return base-name of destination, potentially a folder-tree (nothing is created).
    #       Examples: "The One Movie" or "My Show/Season 1/Episode 1"
    #   unique=True for normal handling
    #   unique=False when later the folder content will be copied to "folder/.."

    unique_dir = True
    if sabnzbd.ENABLE_TV_SORTING:
        #First check if the show matches TV episode regular expressions. Returns regex match object
        match1, match2 = checkForTVShow(dirname)
        if match1:
            logging.debug("[%s] Found TV Show - Starting folder sort (%s)", __NAME__, dirname)
            #formatFolders will create the neccissary folders for the title/season ect and return the final folderpack (does not create the last folder)
            dirname, unique_dir = formatFolders(dirname, match1, match2)
        else:
            dvdmatch = []
            #check if the show matches DVD episode naming
            dvdmatch = checkForTVDVD(dirname)
            if dvdmatch:
                logging.debug("[%s] Found TV DVD - Starting folder sort (%s)", __NAME__, dirname)
                dirname, unique_dir = formatFolders(dirname, dvdmatch, dvd = True)

    return dirname, unique_dir



def formatFolders(dirname, match1, match2 = None, dvd = False):
    """
    Creates directories from returned title and season. Returns final dirpath.
    Does not create the final foldername, but returns it as new_dirpath.
    """
    if not dvd:
        title, season, foldername, unique_dir = getTVInfo(match1, match2, dirname)
    else:
        title, season, foldername, unique_dir = getTVDVDInfo(match1, match2, dirname)

    if title and season and foldername:
        #put files inside a folder named 'TV' if not already
        new_dirname = title
        if sabnzbd.TV_SORT_SEASONS and season != foldername:
            new_dirname = os.path.join(new_dirname, season)
        new_dirname = os.path.join(new_dirname, foldername)
        return new_dirname, unique_dir
    else:
        logging.debug("[%s] TV Sorting: title, season or foldername not present (%s)", __NAME__, dirname)
        return dirname, True


def getTVDVDInfo(match,match2,dirname):
    """
    Returns Title, Season and DVD Number naming from a REGEX match
    """
    foldername = None
    unique_dir = True
    title = match.start()
    title = dirname[0:title]
    title = title.replace('.', ' ')
    title = title.strip().strip('-').strip()
    title = title.title() # title
    if "'S" in title: #title() creates an upperclass 'S
        title.replace("'S", "'s")
    season = int(match.group(1))
    dvd = match.group(2) # dvd number

    if sabnzbd.TV_SORT == 2  or sabnzbd.TV_SORT == 6:    #/TV/ShowName/Season 1/DVD 1/
        foldername = 'DVD %s' % (dvd) # dvd number#

    elif sabnzbd.TV_SORT == 3:  #/TV/ShowName/1xDVD1/
        foldername = '%sxDVD%s' % (season,dvd) # season#

    elif sabnzbd.TV_SORT == 4:  #/TV/ShowName/S01DVD1/
        if season < 10:
            season = '0%s' % (int(season))
        foldername = 'S%sDVD%s' % (season,dvd) # season#

    elif sabnzbd.TV_SORT == 5:  #/TV/ShowName/1DVD1/
        foldername = '%sDVD%s' % (season,dvd) # season#

    elif sabnzbd.TV_SORT == 1:  #/TV/ShowName/DVD1/
        foldername = 'DVD %s' % (season,dvd) # season#
        unique_dir = True

    elif sabnzbd.TV_SORT == 0:#/TV/ShowName/Season 1/Original DirName
        foldername = dirname

    season = 'Season %s' % (season) # season#

    return (title, season, foldername, unique_dir)


def getTVInfo(match1, match2,dirname):
    """
    Returns Title, Season and Episode naming from a REGEX match
    """
    foldername = None
    unique_dir = True

    title = match1.start()
    title = dirname[0:title]
    title = title.replace('.', ' ')
    title = title.strip().strip('_').strip('-').strip()
    title = title.title() # title

    season = match1.group(1).strip('_') # season number
    epNo = int(match1.group(2)) # episode number

    if epNo < 10:
        epNo = '0%s' % (epNo)

    if match2: #match2 is only present if a second REGEX match has been made
        epNo2 = int(match2.group(2)) # two part episode#
        if int(epNo2) < 10:
            epNo2 = '0%s' % (epNo)
    else:
        epNo2 = ''

    spl = dirname[match1.start():].split(' - ',2)

    try:
        if match2:
            epNo2Temp = '-%s' % (epNo2)
        else:
            epNo2Temp = ''
        epName = '%s%s - %s' % (epNo, epNo2Temp, spl[1].strip('_').strip().strip('_'))
    except:
        epName = epNo

    if sabnzbd.TV_SORT == 2:  #/TV/ShowName/01 - EpName/
        foldername = epName

    elif sabnzbd.TV_SORT == 3:  #/TV/ShowName/1x01 - EpName/
        foldername = '%sx%s' % (season,epName) # season#

    elif sabnzbd.TV_SORT == 4:  #/TV/ShowName/S01E01 - EpName/
        if season == 'S' or season == 's':
            foldername = 'S%s' % (epName)
        else:
            if int(season) < 10:
                _season = '0%s' % (int(season))
            foldername = 'S%sE%s' % (_season,epName) # season#

    elif sabnzbd.TV_SORT == 5:  #/TV/ShowName/101 - EpName/
        foldername = '%s%s' % (season,epName) # season#

    elif sabnzbd.TV_SORT == 6:    #/TV/ShowName/Season 1/Episode 01 - EpName/
        if season == 'S' or season == 's':
            foldername = 'Number %s' % (epName)
        else:
            foldername = 'Episode %s' % (epName)

    if season == 'S' or season == 's':
        season = 'Specials'
    else:
        season = 'Season %s' % (season) # season#

    if sabnzbd.TV_SORT == 1:    #/TV/ShowName/Season 1/
        unique_dir = False
        foldername = season
    elif sabnzbd.TV_SORT == 0:#/TV/ShowName/Season 1/Original DirName
        foldername = dirname

    return (title, season, foldername, unique_dir)


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




def checkForTVShow(filename): #checkfortvshow > formatfolders > gettvinfo
    """
    Regular Expression match for TV episodes named either 1x01 or S01E01
    Returns the MatchObject if a match is made
    """
    regularexpressions = [re.compile('(\w+)x(\d+)'),# 1x01
                          re.compile('[Ss](\d+)[\.\-]?[Ee](\d+)')] # S01E01
                          #possibly flawed - 101 - support: [\.\- \s]?(\d)(\d{2,2})[\.\- \s]?
    match2 = None
    for regex in regularexpressions:
        match1 = regex.search(filename)
        if match1:
            match2 = regex.search(filename,match1.end())
            return match1, match2
    return None, None


def TVSeasonMove(nzo, workdir, finalname):
    """ Move content of 'workdir' to 'workdir/..' possibly skipping some files
        If afterwards the directory is not empty, rename it to _JUNK_folder, else remove it.
    """
    skipped = False # Keep track of any skipped files

    for root, dirs, files in os.walk(workdir):
        for _file in files:
            path = os.path.join(root, _file)
            new_path = os.path.abspath(os.path.join(workdir, '..'))
            move_to_path(path, new_path, True)

    if skipped:
        junk_dir = work_dir.replace('_UNPACK_', '_JUNK_')
        try:
            os.rename(work_dir, junk_dir)
        except:
            pass
    else:
        cleanup_empty_directories(work_dir)
        try:
            os.rmdir(work_dir)
        except:
            pass
