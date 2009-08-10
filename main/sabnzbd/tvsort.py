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
sabnzbd.tvsort - Sorting Functions
Series Sorting - Sorting downloads into seasons & episodes
Date sorting - Sorting downloads by a custom date matching
Generic Sorting - Sorting large files by a custom matching
"""

import os
import logging
import re

import sabnzbd
from sabnzbd.misc import move_to_path, cleanup_empty_directories, get_unique_filename, get_ext
from sabnzbd.constants import series_match, date_match, year_match, sample_match
import sabnzbd.cfg as cfg
from sabnzbd.lang import T

RE_SAMPLE = re.compile(sample_match, re.I)
# Do not rename .vob files as they are usually DVD's
EXCLUDED_FILE_EXTS = ('.vob', '.bin')

LOWERCASE = ('the','of','and','at','vs','a','an','but','nor','for','on',\
                         'so','yet')
UPPERCASE = ('III', 'II', 'IV')

replace_prev = {'\\':'/'}
replace_after = {
    '()': '',
    '..': '.',
    '__': '_',
    '  ': ' ',
    '//': '/',
    ' .%ext': '.%ext'
}

# Title() function messes up country names, so need to replace them instead
COUNTRY_REP = ('(US)', '(UK)', '(EU)', '(CA)', '(YU)', '(VE)', '(TR)', '(CH)', \
               '(SE)', '(ES)', '(KR)', '(ZA)', '(SK)', '(SG)', '(RU)', '(RO)', \
               '(PR)', '(PT)', '(PL)', '(PH)', '(PK)', '(NO)', '(NG)', '(NZ)', \
               '(NL)', '(MX)', '(MY)', '(MK)', '(KZ)', '(JP)', '(JM)', '(IT)', \
               '(IL)', '(IE)', '(IN)', '(IS)', '(HU)', '(HK)', '(HN)', '(GR)', \
               '(GH)', '(DE)', '(FR)', '(FI)', '(DK)', '(CZ)', '(HR)', '(CR)', \
               '(CO)', '(CN)', '(CL)', '(BG)', '(BR)', '(BE)', '(AT)', '(AU)', \
               '(AW)', '(AR)', '(AL)', '(AF)')

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


class Sorter:
    def __init__(self, cat):
        self.sorter = None
        self.type = None
        self.sort_file = False
        self.cat = cat

    def detect(self, dirname, complete_dir):
        self.sorter = SeriesSorter(dirname, complete_dir)
        if self.sorter.is_match():
            complete_dir = self.sorter.get_final_path()
            self.type = 'tv'
            self.sort_file = True
            return complete_dir

        self.sorter = DateSorter(dirname, complete_dir, self.cat)
        if self.sorter.is_match():
            complete_dir = self.sorter.get_final_path()
            self.type = 'date'
            self.sort_file = True
            return complete_dir

        self.sorter = GenericSorter(dirname, complete_dir, self.cat)
        if self.sorter.is_match():
            complete_dir = self.sorter.get_final_path()
            self.type = 'movie'
            self.sort_file = True
            return complete_dir

        self.sort_file = False
        return complete_dir

    def rename(self, newfiles, workdir_complete):
        if self.sorter.should_rename():
            self.sorter.rename(newfiles, workdir_complete)

    def move(self, workdir_complete):
        if self.type == 'movie':
            move_to_parent = True
            # check if we should leave the files inside an extra folder
            if cfg.MOVIE_EXTRA_FOLDER.get():
                #if there is a folder in the download, leave it in an extra folder
                move_to_parent = not check_for_folder(workdir_complete)
            if move_to_parent:
                workdir_complete = move_to_parent_folder(workdir_complete)
            return workdir_complete
        else:
            return move_to_parent_folder(workdir_complete)

    def is_sortfile(self):
        return self.sort_file

class SeriesSorter:
    def __init__(self, dirname, path):
        self.matched = False

        self.original_dirname = dirname
        self.original_path = path
        self.sort_string = cfg.TV_SORT_STRING.get()
        self.filename_set = ''

        self.match_obj = None
        self.extras = None
        self.descmatch = None

        self.rename_or_not = False

        self.show_info = {}

        #Check if it is a TV show on init()
        self.match()


    def match(self):
        ''' Checks the regex for a match, if so set self.match to true '''
        if cfg.ENABLE_TV_SORTING.get() and cfg.TV_SORT_STRING.get():
            #First check if the show matches TV episode regular expressions. Returns regex match object
            self.match_obj, self.extras = check_regexs(self.original_dirname, series_match, double=True)
            if self.match_obj:
                logging.debug("Found TV Show - Starting folder sort (%s)", self.original_dirname)
                self.matched = True


    def is_match(self):
        ''' Returns whether there was a match or not '''
        return self.matched


    def get_final_path(self):
        # Collect and construct all the variables such as episode name, show names
        if self.get_values():
            # Get the final path
            path = self.construct_path()
            self.final_path = os.path.join(self.original_path, path)
            return self.final_path
        else:
            # Error Sorting
            return os.path.join(self.original_path, self.original_dirname)


    def get_multi_ep_naming(self, one, two, extras):
        ''' Returns a list of unique values joined into a string and seperated by - (ex:01-02-03-04) '''
        extra_list = [one]
        extra2_list = [two]
        for extra in extras:
            if extra not in (extra_list, extra2_list):
                ep_no2 = extra.rjust(2,'0')
                extra_list.append(extra)
                extra2_list.append(ep_no2)

        one = '-'.join(extra_list)
        two = '-'.join(extra2_list)
        return (one, two)

    def get_shownames(self):
        ''' Get the show name from the match object and format it '''
        # Get the formatted title and alternate title formats
        self.show_info['show_name'], self.show_info['show_name_two'], self.show_info['show_name_three'] = getTitles(self.match_obj, self.original_dirname)


    def get_seasons(self):
        ''' Get the season number from the match object and format it '''
        season = self.match_obj.group(1).strip('_') # season number

        # Provide alternatve formatting (0 padding)
        if season.lower() == 's':
            season2 = season
        else:
            try:
                season = str(int(season))
            except:
                pass
            season2 = season.rjust(2,'0')

        self.show_info['season_num'] = season
        self.show_info['season_num_alt'] = season2


    def get_episodes(self):
        ''' Get the episode numbers from the match object, format and join them '''
        ep_no = self.match_obj.group(2) # episode number
        # Store the original episode number

        # Provide alternatve formatting (0 padding)
        ep_no2 = ep_no.rjust(2,'0')
        try:
            ep_no = str(int(ep_no))
        except:
            pass

        # Dual episode support
        if self.extras:
            ep_no,  ep_no2 = self.get_multi_ep_naming(ep_no,  ep_no2, self.extras)

        self.show_info['episode_num'] = ep_no
        self.show_info['episode_num_alt'] = ep_no2


    def get_showdescriptions(self):
        ''' Get the show descriptions from the match object and format them '''
        self.show_info['ep_name'], self.show_info['ep_name_two'], self.show_info['ep_name_three'] = getDescriptions(self.match_obj, self.original_dirname)


    def get_values(self):
        """ Collect and construct all the values needed for path replacement """
        try:
            ## - Show Name
            self.get_shownames()

            ## - Season
            self.get_seasons()

            ## - Episode Number
            self.get_episodes()

            ## - Episode Name
            self.get_showdescriptions()

            return True

        except:
            logging.error(T('error-tvInfo@1'), self.original_dirname)
            logging.debug("Traceback: ", exc_info = True)
            return False


    def construct_path(self):
        ''' Replaces the sort string with real values such as Show Name and Episode Number '''

        path = unicode(self.sort_string)

        if path.endswith('.%ext'):
            extension = True
            path = path.replace(".%ext", '')
        else:
            extension = False

        for key, name in replace_prev.iteritems():
            path = path.replace(key, name)

        path = path.replace('%sn', self.show_info['show_name'])
        path = path.replace('%s.n', self.show_info['show_name_two'])
        path = path.replace('%s_n', self.show_info['show_name_three'])
        
        # Replace season number
        path = path.replace('%s', self.show_info['season_num'])
        path = path.replace('%0s', self.show_info['season_num_alt'])

        # Replace episode names
        if self.show_info['ep_name']:
            path = path.replace('%en', self.show_info['ep_name'])
            path = path.replace('%e.n', self.show_info['ep_name_two'])
            path = path.replace('%e_n', self.show_info['ep_name_three'])
            
        # If no descriptions were found we need to replace %en and eat up surrounding characters
        path = removeDescription(path, '%e[\._]?n')

        # Replace episode number
        path = path.replace('%e', self.show_info['episode_num'])
        path = path.replace('%0e', self.show_info['episode_num_alt'])


        for key, name in replace_after.iteritems():
            path = path.replace(key, name)

        # Lowercase all characters encased in {}
        path = toLowercase(path)

        # Split the last part of the path up for the renamer
        if extension:
            head, tail = os.path.split(path)
            self.filename_set = tail
            self.rename_or_not = True
        else:
            head = path


        return head

    def should_rename(self):
        return self.rename_or_not

    def rename(self, files, current_path):
        logging.debug("Renaming Series")
        renamed = None
        largest = (None, None, 0)
        
        def to_filepath(f, current_path):
            if is_full_path(f):
                filepath = f.replace('_UNPACK_', '')
            else:
                filepath = os.path.join(current_path, f)
            return filepath
                
        # Create a generator of filepaths, ignore sample files and excluded files (vobs ect)
        filepaths = ((file, to_filepath(file, current_path)) for file in files if not RE_SAMPLE.search(file) \
                     and get_ext(file) not in EXCLUDED_FILE_EXTS)
        
        # Find the largest existing file
        for file, fp in filepaths:
            # If for some reason the file no longer exists, skip
            if not os.path.exists(fp):
                continue
            
            size = os.stat(fp).st_size
            f_file, f_fp, f_size = largest
            if size > f_size:
                largest = (file, fp, size)
                
        file, filepath, size = largest
        # >20MB
        if filepath and size > 20971520:
            tmp, ext = os.path.splitext(file)
            newname = "%s%s" % (self.filename_set,ext)
            # Replace %fn with the original filename
            newname = newname.replace('%fn',tmp)
            newpath = os.path.join(current_path, newname)
            if not os.path.exists(newpath):
                try:
                    logging.debug("Rename: %s to %s", filepath,newpath)
                    os.rename(filepath,newpath)
                except:
                    logging.error("Failed to rename: %s to %s", current_path, newpath)
                    logging.debug("Traceback: ", exc_info = True)
                rename_similar(current_path, file, self.filename_set)
            else:
                logging.debug('Current path already exists, skipping rename, %s', newpath)
        else:
            logging.debug('Nothing to rename, %s', files)


def check_for_sequence(regex, files):
    matches = {}
    prefix = None
    # Build up a dictionary of matches
    # The key is based off the match, ie {1:'blah-part1.avi'}
    for _file in files:
        name, ext = os.path.splitext(_file)
        match1 = regex.search(name)
        if match1:
            if not prefix or prefix == name[:match1.start()]:
                matches[match1.group(1)] = name+ext
                prefix = name[:match1.start()]

    # Don't do anything if only one or no files matched
    if len(matches.keys()) < 2:
        return {}

    key_prev = 0
    passed = True
    alphabet = ['a','b','c','d','e','f','g','h','i','j','k','l','m']

    # Check the dictionary to see if the keys are in a numeric or alphabetic sequence
    match_copy = matches.copy()
    for m in match_copy.iteritems():
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
                # convert {'b':'filename-b.avi'} to {'2', 'filename-b.avi'}
                matches.pop(key)
                matches[key_prev] = file

            else:
                passed = False

    if passed:
        return matches
    else:
        return {}




class GenericSorter:
    def __init__(self, dirname, path, cat):
        self.matched = False

        self.original_dirname = dirname
        self.original_path = path
        self.sort_string = cfg.MOVIE_SORT_STRING.get()
        self.extra = cfg.MOVIE_SORT_EXTRA.get()
        self.cats = cfg.MOVIE_CATEGORIES.get()
        self.cat = cat
        self.filename_set = ''

        self.match_obj = None

        self.rename_or_not = False

        self.movie_info = {}

        # Check if we match the category in init()
        self.match()


    def match(self):
        ''' Checks the category for a match, if so set self.match to true '''
        if cfg.ENABLE_MOVIE_SORTING.get() and self.sort_string:
            #First check if the show matches TV episode regular expressions. Returns regex match object
            if (self.cat and self.cat.lower() in self.cats) or (not self.cat and 'None' in self.cats):
                logging.debug("Movie Sorting - Starting folder sort (%s)", self.original_dirname)
                self.matched = True


    def is_match(self):
        ''' Returns whether there was a match or not '''
        return self.matched



    def get_final_path(self):
        # Collect and construct all the variables such as episode name, show names
        if self.get_values():
            # Get the final path
            path = self.construct_path()
            self.final_path = os.path.join(self.original_path, path)
            return self.final_path
        else:
            # Error Sorting
            return os.path.join(self.original_path, self.original_dirname)

    def get_values(self):
        """ Collect and construct all the values needed for path replacement """

        ## - Get Year
        RE_YEAR = re.compile(year_match, re.I)
        year_m = RE_YEAR.search(self.original_dirname)
        if year_m:
            # Find the last matched date
            # Keep year_m to use in getTitles
            year = RE_YEAR.findall(self.original_dirname)[-1]
            self.movie_info['year'] = year
        else:
            self.movie_info['year'] = ''

        ## - Get Decades
        self.movie_info['decade'], self.movie_info['decade_two'] = getDecades(self.movie_info['year'])

        ## - Get Title
        self.movie_info['title'], self.movie_info['title_two'], self.movie_info['title_three'] = getTitles(year_m, self.original_dirname)

        return True


    def construct_path(self):

        path = unicode(self.sort_string)

        if path.endswith('.%ext'):
            extension = True
            path = path.replace(".%ext", '')
        else:
            extension = False

        for key, name in replace_prev.iteritems():
            path = path.replace(key, name)

        # Replace title
        path = path.replace('%title', self.movie_info['title'])
        path = path.replace('%.title', self.movie_info['title_two'])
        path = path.replace('%_title', self.movie_info['title_three'])

        path = path.replace('%t', self.movie_info['title'])
        path = path.replace('%.t', self.movie_info['title_two'])
        path = path.replace('%_t', self.movie_info['title_three'])

        # Replace year
        path = path.replace('%y', self.movie_info['year'])

        # Replace decades
        path = path.replace('%decade', self.movie_info['decade'])
        path = path.replace('%0decade', self.movie_info['decade_two'])



        for key, name in replace_after.iteritems():
            path = path.replace(key, name)


        # Lowercase all characters encased in {}
        path = toLowercase(path)

        # Strip any extra ' ' '.' or '_' around foldernames
        path = stripFolders(path)

        # Split the last part of the path up for the renamer
        if extension:
            head, tail = os.path.split(path)
            self.filename_set = tail
            self.rename_or_not = True
        else:
            head = path

        return head

    def should_rename(self):
        return self.rename_or_not

    def rename(self, _files, current_path):
        logging.debug("Renaming Generic file")
        def filter_files(_file, current_path):
            if is_full_path(_file):
                filepath = _file.replace('_UNPACK_', '')
            else:
                filepath = os.path.join(current_path, _file)
            if os.path.exists(filepath):
                size = os.stat(filepath).st_size
                if size > 314572800 and not RE_SAMPLE.search(_file) \
                   and get_ext(_file) not in EXCLUDED_FILE_EXTS:
                    return True
            return False

        renamed = False
        # remove any files below 300MB from this list
        files = [_file for _file in _files if filter_files(_file, current_path)]

        length = len(files)
        ## Single File Handling
        if length == 1:
            file = files[0]
            if is_full_path(file):
                filepath = file.replace('_UNPACK_', '')
            else:
                filepath = os.path.join(current_path, file)
            if os.path.exists(filepath):
                tmp, ext = os.path.splitext(file)
                newname = "%s%s" % (self.filename_set,ext)
                newname = newname.replace('%fn',tmp)
                newpath = os.path.join(current_path, newname)
                try:
                    logging.debug("Rename: %s to %s", filepath,newpath)
                    os.rename(filepath,newpath)
                except:
                    logging.error(T('error-tvRename@2'), filepath,newpath)
                    logging.debug("Traceback: ", exc_info = True)
                rename_similar(current_path, file, self.filename_set)
                
        ## Sequence File Handling
        # if there is more than one extracted file check for CD1/1/A in the title
        elif self.extra:
            matched_files = self.check_for_multiple(files)
            # rename files marked as in a set
            if matched_files:
                logging.debug("Renaming a series of generic files (%s)", matched_files)
                for index, file in matched_files.iteritems():
                    filepath = os.path.join(current_path, file)
                    tmp, ext = os.path.splitext(file)
                    name = '%s%s' % (self.filename_set, self.extra)
                    name = name.replace('%1', str(index)).replace('%fn',tmp)
                    name = name + ext
                    newpath = os.path.join(current_path, name)
                    try:
                        logging.debug("Rename: %s to %s", filepath,newpath)
                        os.rename(filepath,newpath)
                    except:
                        logging.error(T('error-tvRename@2'), filepath,newpath)
                        logging.debug("Traceback: ", exc_info = True)
                    rename_similar(current_path, file, self.filename_set)
            else:
                logging.debug("Movie files not in sequence %s", _files)


    def check_for_multiple(self, files):
        expressions = []
        matched_files = []

        expressions.append(re.compile('cd\W?(\d)\W', re.I)) # .cd1.avi
        expressions.append(re.compile('\w\W?([\w\d])$', re.I)) # blah1.avi blaha.avi
        expressions.append(re.compile('\w\W([\w\d])\W', re.I)) # blah-1-ok.avi blah-a-ok.avi

        for regex in expressions:
            regex = re.compile(regex, re.I)
            matched_files = check_for_sequence(regex, files)
            if matched_files:
                return matched_files
        return ''


class DateSorter:
    def __init__(self, dirname, path, cat):
        self.matched = False

        self.original_dirname = dirname
        self.original_path = path
        self.sort_string = cfg.DATE_SORT_STRING.get()
        self.cats = cfg.DATE_CATEGORIES.get()
        self.cat = cat
        self.filename_set = ''

        self.match_obj = None

        self.rename_or_not = False
        self.date_type = None

        self.date_info = {}

        # Check if we match the category in init()
        self.match()


    def match(self):
        ''' Checks the category for a match, if so set self.matched to true '''
        if cfg.ENABLE_DATE_SORTING.get() and self.sort_string:
            #First check if the show matches TV episode regular expressions. Returns regex match object
            if (self.cat and self.cat.lower() in self.cats) or (not self.cat and 'None' in self.cats):
                self.match_obj, self.date_type = checkForDate(self.original_dirname, date_match)
                if self.match_obj:
                    logging.debug("Date Sorting - Starting folder sort (%s)", self.original_dirname)
                    self.matched = True


    def is_match(self):
        ''' Returns whether there was a match or not '''
        return self.matched


    def get_final_path(self):
        # Collect and construct all the variables such as episode name, show names
        if self.get_values():
            # Get the final path
            path = self.construct_path()
            self.final_path = os.path.join(self.original_path, path)
            return self.final_path
        else:
            # Error Sorting
            return os.path.join(self.original_path, self.original_dirname)

    def get_values(self):
        """ Collect and construct all the values needed for path replacement """

        if self.date_type == 1: #2008-10-16
            self.date_info['year'] = self.match_obj.group(1)
            self.date_info['month'] = self.match_obj.group(2)
            self.date_info['date'] =  self.match_obj.group(3)
        else:                       #10.16.2008
            self.date_info['year'] = self.match_obj.group(3)
            self.date_info['month'] = self.match_obj.group(1)
            self.date_info['date'] =  self.match_obj.group(2)

        self.date_info['month_two'] = self.date_info['month'].rjust(2,'0')
        self.date_info['date_two'] = self.date_info['date'].rjust(2,'0')

        ## - Get Decades
        self.date_info['decade'], self.date_info['decade_two'] = getDecades(self.date_info['year'])

        ## - Get Title
        self.date_info['title'], self.date_info['title_two'], self.date_info['title_three'] = getTitles(self.match_obj, self.original_dirname)

        self.date_info['ep_name'], self.date_info['ep_name_two'], self.date_info['ep_name_three'] = getDescriptions(self.match_obj, self.original_dirname)

        return True


    def construct_path(self):

        path = unicode(self.sort_string)

        if path.endswith('.%ext'):
            extension = True
            path = path.replace(".%ext", '')
        else:
            extension = False

        for key, name in replace_prev.iteritems():
            path = path.replace(key, name)

        # Replace title
        path = path.replace('%title', self.date_info['title'])
        path = path.replace('%.title', self.date_info['title_two'])
        path = path.replace('%_title', self.date_info['title_three'])

        path = path.replace('%t', self.date_info['title'])
        path = path.replace('%.t', self.date_info['title_two'])
        path = path.replace('%_t', self.date_info['title_three'])

        path = path.replace('%sn', self.date_info['title'])
        path = path.replace('%s.n', self.date_info['title_two'])
        path = path.replace('%s_n', self.date_info['title_three'])

        # Replace year
        path = path.replace('%year', self.date_info['year'])
        path = path.replace('%y', self.date_info['year'])

        if self.date_info['ep_name']:
            path = path.replace('%desc', self.date_info['ep_name'])
            path = path.replace('%.desc', self.date_info['ep_name_two'])
            path = path.replace('%_desc', self.date_info['ep_name_three'])

        # Replace decades
        path = path.replace('%decade', self.date_info['decade'])
        path = path.replace('%0decade', self.date_info['decade_two'])

        # Replace month
        path = path.replace('%m', self.date_info['month'])
        path = path.replace('%0m', self.date_info['month_two'])

        # Replace date
        path = path.replace('%d', self.date_info['date'])
        path = path.replace('%0d', self.date_info['date_two'])

        for key, name in replace_after.iteritems():
            path = path.replace(key, name)

        # Lowercase all characters encased in {}
        path = toLowercase(path)

        path = removeDescription(path, '%[\._]?desc')

        # Strip any extra ' ' '.' or '_' around foldernames
        path = stripFolders(path)

        # Split the last part of the path up for the renamer
        if extension:
            head, tail = os.path.split(path)
            self.filename_set = tail
            self.rename_or_not = True
        else:
            head = path

        return head

    def should_rename(self):
        return self.rename_or_not

    def rename(self, files, current_path):
        logging.debug("Renaming Date file")
        renamed = None
        #find the master file to rename
        for file in files:
            if is_full_path(file):
                filepath = file.replace('_UNPACK_', '')
            else:
                filepath = os.path.join(current_path, file)

            if os.path.exists(filepath):
                size = os.stat(filepath).st_size
                if size > 130000000:
                    if 'sample' not in file:
                        tmp, ext = os.path.splitext(file)
                        newname = "%s%s" % (self.filename_set,ext)
                        newname = newname.replace('%fn',tmp)
                        newpath = os.path.join(current_path, newname)
                        if not os.path.exists(newpath):
                            try:
                                logging.debug("Rename: %s to %s", filepath,newpath)
                                os.rename(filepath,newpath)
                            except:
                                logging.error(T('error-tvRename@2'), current_path, newpath)
                                logging.debug("Traceback: ", exc_info = True)
                            rename_similar(current_path, file, self.filename_set)
                            break



def getTitles(match, name):
    '''
    The title will be the part before the match
    Clean it up and title() it
    
    ''.title() isn't very good under python so this contains
    a lot of little hacks to make it better and for more control
    '''
    if match:
        name = name[:match.start()]
    
    # Replace .US. with (US)
    if cfg.TV_SORT_COUNTRIES.get() == 1:
        for rep in COUNTRY_REP:
            # (us) > (US)
            name = replace_word(name, rep.lower(), rep)
            # (Us) > (US)
            name = replace_word(name, rep.title(), rep)
            # .US. > (US)
            dotted_country = '.%s.' % (rep.strip('()'))
            name = replace_word(name, dotted_country, rep)
    # Remove .US. and (US)
    elif cfg.TV_SORT_COUNTRIES.get() == 2:
        for rep in COUNTRY_REP:
            # Remove (US)
            name = replace_word(name, rep, '')
            dotted_country = '.%s.' % (rep.strip('()'))
            # Remove .US.
            name = replace_word(name, dotted_country, '.')         
        
    title = name.replace('.', ' ').replace('_', ' ')
    title = title.strip().strip('(').strip('_').strip('-').strip().strip('_')
    
    title = title.title() # title the show name so it is in a consistant letter case
    
    #title applied uppercase to 's Python bug?
    title = title.replace("'S", "'s")
    
    # Replace titled country names, (Us) with (US) and so on
    if cfg.TV_SORT_COUNTRIES.get() == 1:
        for rep in COUNTRY_REP:
            title = title.replace(rep.title(), rep)
    # Remove country names, ie (Us)
    elif cfg.TV_SORT_COUNTRIES.get() == 2:
        for rep in COUNTRY_REP:
            title = title.replace(rep.title(), '').strip()
            
    # Make sure some words such as 'and' or 'of' stay lowercased.
    for x in LOWERCASE:
        xtitled = x.title()
        title = replace_word(title, xtitled, x)
                
    # Make sure some words such as 'III' or 'IV' stay uppercased.
    for x in UPPERCASE:
        xtitled = x.title()
        title = replace_word(title, xtitled, x)
        
    # The title with spaces replaced by dots
    dots = title.replace(" - ", "-").replace(' ','.').replace('_','.')
    dots = dots.replace('(', '.').replace(')','.').replace('..','.').rstrip('.')
    
    # The title with spaces replaced by underscores
    underscores = title.replace(' ','_').replace('.','_').replace('__','_').rstrip('_')

    return title, dots, underscores

def replace_word(input, one, two):
    ''' Regex replace on just words '''
    regex = re.compile('\W(%s)(\W|$)' % one, re.I)
    matches = regex.findall(input)
    if matches:
        for m in matches:
            input = input.replace(one, two)
    return input

def getDescriptions(match, name):
    '''
    If present, get a description from the nzb name.
    A description has to be after the matched item, seperated either
    like ' - Description' or '_-_Description'
    '''
    if match:
        ep_name = name[match.end():] # Need to improve for multi ep support
    else:
        ep_name = name
    RE_EPNAME = re.compile('_?-[_\W]', re.I)
    m = RE_EPNAME.search(ep_name)
    if m:
        ep_name = ep_name[m.end():].strip('_').strip().strip('_').replace('.', ' ').replace('_', ' ')
        ep_name2 = ep_name.replace(" - ", "-").replace(" ", ".")
        ep_name3 = ep_name.replace(" ", "_")
        return ep_name, ep_name2, ep_name3
    else:
        return '', '', ''

def removeDescription(path, desc_token):
    regex_string = '(\W*)(token)(\s?)'.replace('token', desc_token)
    epname_re = re.compile(regex_string)
    path = epname_re.sub('', path)
    return path

def getDecades(year):
    if year:
        try:
            decade = year[2:3]+'0'
            decade2 = year[:3]+'0'
        except:
            decade = ''
            decade2 = ''
    else:
        decade = ''
        decade2 = ''
    return decade, decade2

def check_for_folder(path):
    for root, dirs, files in os.walk(path):
        if dirs:
            return True
    return False

def toLowercase(path):
    ''' Lowercases any characters enclosed in {} '''
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
    return path

def stripFolders(folders):
    f = folders.strip('/').split('/')

    def strip_all(x):
        x = x.strip().strip('_')
        if sabnzbd.WIN32:
            # Don't want to strip . from folders such as /.sabnzbd/
            x = x.strip('.')
        x = x.strip()
        return x

    return '/'.join([strip_all(x) for x in f])


def rename_similar(path, file, name):
    logging.debug('Renaming files similar to: %s to %s', file, name)
    file_prefix, ext = os.path.splitext(file)
    for root, dirs, files in os.walk(path):
        for _file in files:
            fpath = os.path.join(root, _file)
            tmp, ext = os.path.splitext(_file)
            if tmp == file_prefix:
                newname = "%s%s" % (name,ext)
                newname = newname.replace('%fn',tmp)
                newpath = os.path.join(path, newname)
                if not os.path.exists(newpath):
                    try:
                        logging.debug("Rename: %s to %s", fpath,newpath)
                        os.rename(fpath,newpath)
                    except:
                        logging.error(T('error-tvSimRename@2'), path, newpath)
                        logging.debug("Traceback: ", exc_info = True)




def check_regexs(filename, matchers, double=False):
    """
    Regular Expression match for a list of regexes
    Returns the MatchObject if a match is made
    This version checks for an additional match
    """
    '''if double:
        matcher, extramatchers = matchers
    else:
        matcher = matchers
        extramatchers = []'''
    extras = []
    for expressions in matchers:
        expression, extramatchers = expressions
        regex = re.compile(expression)
        match1 = regex.search(filename)
        if match1:
            for m in extramatchers:
                regex = re.compile(m)
                match2 = regex.findall(filename,match1.end())
                if match2:
                    for match in match2:
                        if type(match) == type(()) and len(match) > 1:
                            extras.append(match[1])
                        else:
                            extras.append(match)
                    break
            return match1, extras
    return None, None


def checkForDate(filename, matcher):
    """
    Regular Expression match for date based files
    Returns the MatchObject if a match is made
    """
    match2 = None
    x = 0
    if matcher:
        for expression in matcher:
            regex = re.compile(expression)
            match1 = regex.search(filename)
            x += 1
            if match1:
                return match1, x
    return None, 0

def is_full_path(file):
    if file.startswith('\\') or file.startswith('/'):
        return True
    try:
        if file[1:3] == ':\\':
            return True
    except:
        pass
    return False
