#!/usr/bin/python -OO
# Copyright 2008-2011 The SABnzbd-Team <team@sabnzbd.org>
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
from sabnzbd.misc import move_to_path, cleanup_empty_directories, get_unique_path, \
                         get_unique_filename, get_ext, renamer, remove_dir
from sabnzbd.constants import series_match, date_match, year_match, sample_match
import sabnzbd.cfg as cfg
from sabnzbd.encoding import titler

RE_SAMPLE = re.compile(sample_match, re.I)
# Do not rename .vob files as they are usually DVD's
EXCLUDED_FILE_EXTS = ('.vob', '.bin')

LOWERCASE = ('the','of','and','at','vs','a','an','but','nor','for','on',\
                         'so','yet')
UPPERCASE = ('III', 'II', 'IV')

REPLACE_AFTER = {
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

_RE_ENDEXT = re.compile(r'\.%ext[{}]*$', re.I)

def endswith_ext(path):
    m = _RE_ENDEXT.search(path)
    return m is not None


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
            new_path = get_unique_filename(new_path)
            move_to_path(path, new_path, False)

    cleanup_empty_directories(workdir)
    try:
        remove_dir(workdir)
    except:
        pass

    return path1


class Sorter(object):
    def __init__(self, cat):
        self.sorter = None
        self.type = None
        self.sort_file = False
        self.cat = cat

    def detect(self, dirname, complete_dir):
        self.sorter = SeriesSorter(dirname, complete_dir, self.cat)
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
            if cfg.movie_extra_folders():
                #if there is a folder in the download, leave it in an extra folder
                move_to_parent = not check_for_folder(workdir_complete)
            if move_to_parent:
                workdir_complete = move_to_parent_folder(workdir_complete)
        else:
            workdir_complete = move_to_parent_folder(workdir_complete)
        path, part = os.path.split(workdir_complete)
        if '%fn' in part and self.sorter.fname:
            old = workdir_complete
            workdir_complete = os.path.join(path, part.replace('%fn', self.sorter.fname))
            workdir_complete = get_unique_path(workdir_complete, create_dir=False)
            try:
                renamer(old, workdir_complete)
            except:
                logging.error(Ta('Cannot create directory %s'), workdir_complete)
                workdir_complete = old
        return workdir_complete

    def is_sortfile(self):
        return self.sort_file

class SeriesSorter(object):
    def __init__(self, dirname, path, cat, force=False):
        self.matched = False

        self.original_dirname = dirname
        self.original_path = path
        self.cat = cat
        self.sort_string = cfg.tv_sort_string()
        self.cats = cfg.tv_categories()
        self.filename_set = ''
        self.fname = '' # Value for %fn substitution in folders

        self.match_obj = None
        self.extras = None
        self.descmatch = None

        self.rename_or_not = False

        self.show_info = {}

        #Check if it is a TV show on init()
        self.match(force)


    def match(self, force=False):
        ''' Checks the regex for a match, if so set self.match to true '''
        if force or (cfg.enable_tv_sorting() and cfg.tv_sort_string()):
            if force or (not self.cats) or (self.cat and self.cat.lower() in self.cats) or (not self.cat and 'None' in self.cats):
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
            logging.error(Ta('Error getting TV info (%s)'), self.original_dirname)
            logging.info("Traceback: ", exc_info = True)
            return False


    def construct_path(self):
        ''' Replaces the sort string with real values such as Show Name and Episode Number '''

        sorter = self.sort_string.replace('\\', '/')
        mapping = []

        if endswith_ext(sorter):
            extension = True
            sorter = sorter.replace('.%ext', '')
        else:
            extension = False


        # Replace Show name
        mapping.append(('%sn', self.show_info['show_name']))
        mapping.append(('%s.n', self.show_info['show_name_two']))
        mapping.append(('%s_n', self.show_info['show_name_three']))

        # Replace season number
        mapping.append(('%s', self.show_info['season_num']))
        mapping.append(('%0s', self.show_info['season_num_alt']))

        # Original dir name
        mapping.append(('%dn', self.original_dirname))

        # Replace episode names
        if self.show_info['ep_name']:
            mapping.append(('%en', self.show_info['ep_name']))
            mapping.append(('%e.n', self.show_info['ep_name_two']))
            mapping.append(('%e_n', self.show_info['ep_name_three']))
        else:
            mapping.append(('%en', ''))
            mapping.append(('%e.n', ''))
            mapping.append(('%e_n', ''))

        # Replace episode number
        mapping.append(('%e', self.show_info['episode_num']))
        mapping.append(('%0e', self.show_info['episode_num_alt']))

        # Make sure unsupported %desc is removed
        mapping.append(('%desc', ''))

        # Replace elements
        path = path_subst(sorter, mapping)

        for key, name in REPLACE_AFTER.iteritems():
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
            self.fname = tmp
            newname = "%s%s" % (self.filename_set,ext)
            # Replace %fn with the original filename
            newname = newname.replace('%fn',tmp)
            newpath = os.path.join(current_path, newname)
            if not os.path.exists(newpath):
                try:
                    logging.debug("Rename: %s to %s", filepath,newpath)
                    renamer(filepath,newpath)
                except:
                    logging.error("Failed to rename: %s to %s", current_path, newpath)
                    logging.info("Traceback: ", exc_info = True)
                rename_similar(current_path, file, self.filename_set)
            else:
                logging.debug('Current path already exists, skipping rename, %s', newpath)
        else:
            logging.debug('Nothing to rename, %s', files)


_RE_MULTIPLE = ( \
    re.compile(r'cd\W?(\d+)\W?', re.I),        # .cd1.avi
    re.compile(r'\w\W?([\w\d])[{}]*$', re.I),  # blah1.avi blaha.avi
    re.compile(r'\w\W([\w\d])\W', re.I)        # blah-1-ok.avi blah-a-ok.avi
)
def check_for_multiple(files):
    for regex in _RE_MULTIPLE:
        matched_files = check_for_sequence(regex, files)
        if matched_files:
            return matched_files
    return ''


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
    alphabet = 'abcdefghijklmnopqrstuvwxyz'

    # Check the dictionary to see if the keys are in a numeric or alphabetic sequence
    for akey in sorted(matches.keys()):
        if akey.isdigit():
            key = int(akey)
        elif akey in alphabet:
            key = alphabet.find(akey) + 1
        else:
            passed = False

        if passed:
            if not key_prev:
                key_prev = key
            else:
                if key_prev + 1 == key:
                    key_prev = key
                else:
                    passed = False
        if passed:
            # convert {'b':'filename-b.avi'} to {'2', 'filename-b.avi'}
            item = matches.pop(akey)
            matches[str(key)] = item

    if passed:
        return matches
    else:
        return {}




class GenericSorter(object):
    def __init__(self, dirname, path, cat):
        self.matched = False

        self.original_dirname = dirname
        self.original_path = path
        self.sort_string = cfg.movie_sort_string()
        self.extra = cfg.movie_sort_extra()
        self.cats = cfg.movie_categories()
        self.cat = cat
        self.filename_set = ''
        self.fname = '' # Value for %fn substitution in folders

        self.match_obj = None

        self.rename_or_not = False

        self.movie_info = {}

        # Check if we match the category in init()
        self.match()


    def match(self):
        ''' Checks the category for a match, if so set self.match to true '''
        if cfg.enable_movie_sorting() and self.sort_string:
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
        dirname = self.original_dirname.replace('_', ' ')
        RE_YEAR = re.compile(year_match, re.I)
        year_m = RE_YEAR.search(dirname)
        if year_m:
            # Find the last matched date
            # Keep year_m to use in getTitles
            year = RE_YEAR.findall(dirname)[-1][0]
            self.movie_info['year'] = year
        else:
            self.movie_info['year'] = ''

        ## - Get Decades
        self.movie_info['decade'], self.movie_info['decade_two'] = getDecades(self.movie_info['year'])

        ## - Get Title
        self.movie_info['title'], self.movie_info['title_two'], self.movie_info['title_three'] = getTitles(year_m, self.original_dirname)

        return True


    def construct_path(self):

        sorter = self.sort_string.replace('\\', '/')
        mapping = []

        if endswith_ext(sorter):
            extension = True
            sorter = sorter.replace(".%ext", '')
        else:
            extension = False

        # Replace title
        mapping.append(('%title', self.movie_info['title']))
        mapping.append(('%.title', self.movie_info['title_two']))
        mapping.append(('%_title', self.movie_info['title_three']))

        # Replace title (short forms)
        mapping.append(('%t', self.movie_info['title']))
        mapping.append(('%.t', self.movie_info['title_two']))
        mapping.append(('%_t', self.movie_info['title_three']))

        # Replace year
        mapping.append(('%y', self.movie_info['year']))

        # Replace decades
        mapping.append(('%decade', self.movie_info['decade']))
        mapping.append(('%0decade', self.movie_info['decade_two']))

        path = path_subst(sorter, mapping)

        for key, name in REPLACE_AFTER.iteritems():
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
                self.fname = tmp
                newname = "%s%s" % (self.filename_set,ext)
                newname = newname.replace('%fn',tmp)
                newpath = os.path.join(current_path, newname)
                try:
                    logging.debug("Rename: %s to %s", filepath,newpath)
                    renamer(filepath,newpath)
                except:
                    logging.error(Ta('Failed to rename: %s to %s'), filepath, newpath)
                    logging.info("Traceback: ", exc_info = True)
                rename_similar(current_path, file, self.filename_set)

        ## Sequence File Handling
        # if there is more than one extracted file check for CD1/1/A in the title
        elif self.extra:
            matched_files = check_for_multiple(files)
            # rename files marked as in a set
            if matched_files:
                logging.debug("Renaming a series of generic files (%s)", matched_files)
                for index, file in matched_files.iteritems():
                    filepath = os.path.join(current_path, file)
                    tmp, ext = os.path.splitext(file)
                    self.fname = tmp
                    name = '%s%s' % (self.filename_set, self.extra)
                    name = name.replace('%1', str(index)).replace('%fn',tmp)
                    name = name + ext
                    newpath = os.path.join(current_path, name)
                    try:
                        logging.debug("Rename: %s to %s", filepath,newpath)
                        renamer(filepath,newpath)
                    except:
                        logging.error(Ta('Failed to rename: %s to %s'), filepath, newpath)
                        logging.info("Traceback: ", exc_info = True)
                    rename_similar(current_path, file, self.filename_set)
            else:
                logging.debug("Movie files not in sequence %s", _files)


class DateSorter(object):
    def __init__(self, dirname, path, cat):
        self.matched = False

        self.original_dirname = dirname
        self.original_path = path
        self.sort_string = cfg.date_sort_string()
        self.cats = cfg.date_categories()
        self.cat = cat
        self.filename_set = ''
        self.fname = '' # Value for %fn substitution in folders

        self.match_obj = None

        self.rename_or_not = False
        self.date_type = None

        self.date_info = {}
        self.final_path = ''

        # Check if we match the category in init()
        self.match()


    def match(self):
        ''' Checks the category for a match, if so set self.matched to true '''
        if cfg.enable_date_sorting() and self.sort_string:
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

        sorter = self.sort_string.replace('\\', '/')
        mapping = []

        if endswith_ext(sorter):
            extension = True
            sorter= sorter.replace(".%ext", '')
        else:
            extension = False

        # Replace title
        mapping.append(('%title', self.date_info['title']))
        mapping.append(('%.title', self.date_info['title_two']))
        mapping.append(('%_title', self.date_info['title_three']))

        mapping.append(('%t', self.date_info['title']))
        mapping.append(('%.t', self.date_info['title_two']))
        mapping.append(('%_t', self.date_info['title_three']))

        mapping.append(('%sn', self.date_info['title']))
        mapping.append(('%s.n', self.date_info['title_two']))
        mapping.append(('%s_n', self.date_info['title_three']))

        # Replace year
        mapping.append(('%year', self.date_info['year']))
        mapping.append(('%y', self.date_info['year']))

        if self.date_info['ep_name']:
            mapping.append(('%desc', self.date_info['ep_name']))
            mapping.append(('%.desc', self.date_info['ep_name_two']))
            mapping.append(('%_desc', self.date_info['ep_name_three']))
        else:
            mapping.append(('%desc', ''))
            mapping.append(('%.desc', ''))
            mapping.append(('%_desc', ''))

        # Replace decades
        mapping.append(('%decade', self.date_info['decade']))
        mapping.append(('%0decade', self.date_info['decade_two']))

        # Replace month
        mapping.append(('%m', self.date_info['month']))
        mapping.append(('%0m', self.date_info['month_two']))

        # Replace date
        mapping.append(('%d', self.date_info['date']))
        mapping.append(('%0d', self.date_info['date_two']))

        path = path_subst(sorter, mapping)

        for key, name in REPLACE_AFTER.iteritems():
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
                        self.fname = tmp
                        newname = "%s%s" % (self.filename_set,ext)
                        newname = newname.replace('%fn',tmp)
                        newpath = os.path.join(current_path, newname)
                        if not os.path.exists(newpath):
                            try:
                                logging.debug("Rename: %s to %s", filepath,newpath)
                                renamer(filepath,newpath)
                            except:
                                logging.error(Ta('Failed to rename: %s to %s'), current_path, newpath)
                                logging.info("Traceback: ", exc_info = True)
                            rename_similar(current_path, file, self.filename_set)
                            break


def path_subst(path, mapping):
    """ Replace the sort sting elements by real values.
        Non-elements are copied literally.
        path = the sort string
        mapping = array of tuples that maps all elements to their values
    """
    newpath = []
    plen = len(path)
    n = 0
    while n < plen:
        result = path[n]
        if result == '%':
            for key, value in mapping:
                if path.startswith(key, n):
                    n += len(key)-1
                    result = value
                    break
        newpath.append(result)
        n += 1
    return ''.join(newpath)


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
    if cfg.tv_sort_countries() == 1:
        for rep in COUNTRY_REP:
            # (us) > (US)
            name = replace_word(name, rep.lower(), rep)
            # (Us) > (US)
            name = replace_word(name, titler(rep), rep)
            # .US. > (US)
            dotted_country = '.%s.' % (rep.strip('()'))
            name = replace_word(name, dotted_country, rep)
    # Remove .US. and (US)
    elif cfg.tv_sort_countries() == 2:
        for rep in COUNTRY_REP:
            # Remove (US)
            name = replace_word(name, rep, '')
            dotted_country = '.%s.' % (rep.strip('()'))
            # Remove .US.
            name = replace_word(name, dotted_country, '.')

    title = name.replace('.', ' ').replace('_', ' ')
    title = title.strip().strip('(').strip('_').strip('-').strip().strip('_')

    title = titler(title) # title the show name so it is in a consistant letter case

    #title applied uppercase to 's Python bug?
    title = title.replace("'S", "'s")

    # Replace titled country names, (Us) with (US) and so on
    if cfg.tv_sort_countries() == 1:
        for rep in COUNTRY_REP:
            title = title.replace(titler(rep), rep)
    # Remove country names, ie (Us)
    elif cfg.tv_sort_countries() == 2:
        for rep in COUNTRY_REP:
            title = title.replace(titler(rep), '').strip()

    # Make sure some words such as 'and' or 'of' stay lowercased.
    for x in LOWERCASE:
        xtitled = titler(x)
        title = replace_word(title, xtitled, x)

    # Make sure some words such as 'III' or 'IV' stay uppercased.
    for x in UPPERCASE:
        xtitled = titler(x)
        title = replace_word(title, xtitled, x)

    # Make sure the first letter of the title is always uppercase
    if title:
        title = titler(title[0]) + title[1:]

    # The title with spaces replaced by dots
    dots = title.replace(" - ", "-").replace(' ','.').replace('_','.')
    dots = dots.replace('(', '.').replace(')','.').replace('..','.').rstrip('.')

    # The title with spaces replaced by underscores
    underscores = title.replace(' ','_').replace('.','_').replace('__','_').rstrip('_')

    return title, dots, underscores

def replace_word(input, one, two):
    ''' Regex replace on just words '''
    regex = re.compile(r'\W(%s)(\W|$)' % one, re.I)
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
    ep_name = ep_name.strip(' _.')
    if ep_name.startswith('-'):
        ep_name = ep_name.strip('- _.')
    if '.' in ep_name and ' ' not in ep_name:
        ep_name = ep_name.replace('.', ' ')
    ep_name = ep_name.replace('_', ' ')
    ep_name2 = ep_name.replace(" - ", "-").replace(" ", ".")
    ep_name3 = ep_name.replace(" ", "_")
    return ep_name, ep_name2, ep_name3


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

_RE_LOWERCASE = re.compile(r'{([^{]*)}')
def toLowercase(path):
    ''' Lowercases any characters enclosed in {} '''
    while True:
        m = _RE_LOWERCASE.search(path)
        if not m:
            break
        path = path[:m.start()] + m.group(1).lower() + path[m.end():]

    # just incase
    path = path.replace('{', '')
    path = path.replace('}', '')
    return path

def stripFolders(folders):
    f = folders.strip('/').split('/')

    # For path beginning with a slash, insert empty element to prevent loss
    if folders.strip()[0] in '/\\':
        f.insert(0, '')

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
                        renamer(fpath,newpath)
                    except:
                        logging.error(Ta('Failed to rename similar file: %s to %s'), path, newpath)
                        logging.info("Traceback: ", exc_info = True)




def check_regexs(filename, matchers, double=False):
    """
    Regular Expression match for a list of regexes
    Returns the MatchObject if a match is made
    This version checks for an additional match
    """
    #if double:
    #   matcher, extramatchers = matchers
    #else:
    #    matcher = matchers
    #    extramatchers = []

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


def eval_sort(sorttype, expression, name=None):
    """ Preview a sort expression, to be used by API """
    from sabnzbd.api import Ttemplate
    path = ''
    if sorttype == 'series':
        name = name or ('%s S01E03 - %s [DTS]' % (Ttemplate('show-name'), Ttemplate('ep-name')))
        sorter = sabnzbd.tvsort.SeriesSorter(name, path, 'tv', force=True)
    elif sorttype == 'generic':
        name = name or (Ttemplate('movie-sp-name') + ' (2009)')
        sorter = sabnzbd.tvsort.GenericSorter(name, path, 'tv')
    elif sorttype == 'date':
        name = name or (Ttemplate('show-name') + ' 2009-01-02')
        sorter = sabnzbd.tvsort.DateSorter(name, path, 'tv')
    else:
        return None
    sorter.sort_string = expression
    sorter.matched = True
    path = sorter.get_final_path()
    path = os.path.normpath(os.path.join(path, sorter.filename_set))
    if sorter.rename_or_not:
        path += '.avi'
    else:
        if sabnzbd.WIN32:
            path += '\\'
        else:
            path += '/'
    return path
