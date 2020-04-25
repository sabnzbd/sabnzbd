#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.sorting - Sorting Functions
Series Sorting - Sorting downloads into seasons & episodes
Date Sorting - Sorting downloads by a custom date matching
Generic Sorting - Sorting large files by a custom matching
"""

import os
import logging
import re

import sabnzbd
from sabnzbd.filesystem import move_to_path, cleanup_empty_directories, get_unique_path, \
    get_unique_filename, get_ext, renamer, sanitize_foldername, clip_path
from sabnzbd.constants import series_match, date_match, year_match, sample_match
import sabnzbd.cfg as cfg

RE_SAMPLE = re.compile(sample_match, re.I)
# Do not rename .vob files as they are usually DVD's
EXCLUDED_FILE_EXTS = ('.vob', '.bin')

LOWERCASE = ('the', 'of', 'and', 'at', 'vs', 'a', 'an', 'but', 'nor', 'for', 'on',
                         'so', 'yet', 'with')
UPPERCASE = ('III', 'II', 'IV')

REPLACE_AFTER = {
    '()': '',
    '..': '.',
    '__': '_',
    '  ': ' ',
    ' .%ext': '.%ext'
}

# Title() function messes up country names, so need to replace them instead
COUNTRY_REP = ('(US)', '(UK)', '(EU)', '(CA)', '(YU)', '(VE)', '(TR)', '(CH)',
               '(SE)', '(ES)', '(KR)', '(ZA)', '(SK)', '(SG)', '(RU)', '(RO)',
               '(PR)', '(PT)', '(PL)', '(PH)', '(PK)', '(NO)', '(NG)', '(NZ)',
               '(NL)', '(MX)', '(MY)', '(MK)', '(KZ)', '(JP)', '(JM)', '(IT)',
               '(IL)', '(IE)', '(IN)', '(IS)', '(HU)', '(HK)', '(HN)', '(GR)',
               '(GH)', '(DE)', '(FR)', '(FI)', '(DK)', '(CZ)', '(HR)', '(CR)',
               '(CO)', '(CN)', '(CL)', '(BG)', '(BR)', '(BE)', '(AT)', '(AU)',
               '(AW)', '(AR)', '(AL)', '(AF)')


def ends_in_file(path):
    """ Return True when path ends with '.%ext' or '%fn' """
    _RE_ENDEXT = re.compile(r'\.%ext[{}]*$', re.I)
    _RE_ENDFN = re.compile(r'%fn[{}]*$', re.I)
    return bool(_RE_ENDEXT.search(path) or _RE_ENDFN.search(path))


def move_to_parent_folder(workdir):
    """ Move all in 'workdir' into 'workdir/..' """
    # Determine 'folder'/..
    workdir = os.path.abspath(os.path.normpath(workdir))
    dest = os.path.abspath(os.path.normpath(os.path.join(workdir, '..')))

    # Check for DVD folders and stop if found
    for item in os.listdir(workdir):
        if item.lower() in ('video_ts', 'audio_ts', 'bdmv'):
            return workdir, True

    for root, dirs, files in os.walk(workdir):
        for _file in files:
            path = os.path.join(root, _file)
            new_path = path.replace(workdir, dest)
            ok, new_path = move_to_path(path, new_path)
            if not ok:
                return dest, False

    cleanup_empty_directories(workdir)
    return dest, True


class Sorter:
    """ Generic Sorter class """

    def __init__(self, nzo, cat):
        self.sorter = None
        self.type = None
        self.sort_file = False
        self.nzo = nzo
        self.cat = cat
        self.ext = ''

    def detect(self, job_name, complete_dir):
        """ Detect which kind of sort applies """
        self.sorter = SeriesSorter(self.nzo, job_name, complete_dir, self.cat)
        if self.sorter.matched:
            complete_dir = self.sorter.get_final_path()
            self.type = 'tv'
            self.sort_file = True
            return complete_dir

        self.sorter = DateSorter(self.nzo, job_name, complete_dir, self.cat)
        if self.sorter.matched:
            complete_dir = self.sorter.get_final_path()
            self.type = 'date'
            self.sort_file = True
            return complete_dir

        self.sorter = MovieSorter(self.nzo, job_name, complete_dir, self.cat)
        if self.sorter.matched:
            complete_dir = self.sorter.get_final_path()
            self.type = 'movie'
            self.sort_file = True
            return complete_dir

        self.sort_file = False
        return complete_dir

    def rename(self, newfiles, workdir_complete):
        """ Rename files of the job """
        if self.sorter.rename_or_not:
            self.sorter.rename(newfiles, workdir_complete)

    def rename_with_ext(self, workdir_complete):
        """ Special renamer for %ext """
        if self.sorter.rename_or_not and '%ext' in workdir_complete and self.ext:
            # Replace %ext with extension
            newpath = workdir_complete.replace('%ext', self.ext)
            try:
                renamer(workdir_complete, newpath)
            except:
                return newpath, False
            return newpath, True
        else:
            return workdir_complete, True

    def move(self, workdir_complete):
        ok = True
        if self.type == 'movie':
            move_to_parent = True
            # check if we should leave the files inside an extra folder
            if cfg.movie_extra_folders():
                # if there is a folder in the download, leave it in an extra folder
                move_to_parent = not check_for_folder(workdir_complete)
            if move_to_parent:
                workdir_complete, ok = move_to_parent_folder(workdir_complete)
        else:
            workdir_complete, ok = move_to_parent_folder(workdir_complete)
        if not ok:
            return workdir_complete, False

        path, part = os.path.split(workdir_complete)
        if '%fn' in part and self.sorter.fname:
            old = workdir_complete
            workdir_complete = os.path.join(path, part.replace('%fn', self.sorter.fname))
            workdir_complete = get_unique_path(workdir_complete, create_dir=False)
            try:
                renamer(old, workdir_complete)
            except:
                logging.error(T('Cannot create directory %s'), clip_path(workdir_complete))
                workdir_complete = old
                ok = False
        return workdir_complete, ok


class SeriesSorter:
    """ Methods for Series Sorting """

    def __init__(self, nzo, job_name, path, cat):
        self.matched = False

        self.original_job_name = job_name
        self.original_path = path
        self.nzo = nzo
        self.cat = cat
        self.sort_string = cfg.tv_sort_string()
        self.cats = cfg.tv_categories()
        self.filename_set = ''
        self.fname = ''  # Value for %fn substitution in folders
        self.final_path = ''

        self.match_obj = None
        self.extras = None

        self.rename_or_not = False

        self.show_info = {}

        # Check if it is a TV show on init()
        self.match()

    def match(self, force=False):
        """ Checks the regex for a match, if so set self.match to true """
        if force or (cfg.enable_tv_sorting() and cfg.tv_sort_string()):
            if force or (not self.cats) or (self.cat and self.cat.lower() in self.cats) or (not self.cat and 'None' in self.cats):
                # First check if the show matches TV episode regular expressions. Returns regex match object
                self.match_obj, self.extras = check_regexs(self.original_job_name, series_match)
                if self.match_obj:
                    logging.debug("Found TV Show (%s)", self.original_job_name)
                    self.matched = True

    def is_match(self):
        """ Returns whether there was a match or not """
        return self.matched

    def get_final_path(self):
        """ Collect and construct all the variables such as episode name, show names """
        if self.get_values():
            # Get the final path
            path = self.construct_path()
            self.final_path = os.path.join(self.original_path, path)
            return self.final_path
        else:
            # Error Sorting
            return os.path.join(self.original_path, self.original_job_name)

    def get_multi_ep_naming(self, one, two, extras):
        """ Returns a list of unique values joined into a string and separated by - (ex:01-02-03-04) """
        extra_list = [one]
        extra2_list = [two]
        for extra in extras:
            if extra not in (extra_list, extra2_list):
                ep_no2 = extra.rjust(2, '0')
                extra_list.append(extra)
                extra2_list.append(ep_no2)

        one = '-'.join(extra_list)
        two = '-'.join(extra2_list)
        return one, two

    def get_shownames(self):
        """ Get the show name from the match object and format it """
        # Get the formatted title and alternate title formats
        self.show_info['show_tname'], self.show_info['show_tname_two'], self.show_info['show_tname_three'] = get_titles(self.nzo, self.match_obj, self.original_job_name, True)
        self.show_info['show_name'], self.show_info['show_name_two'], self.show_info['show_name_three'] = get_titles(self.nzo, self.match_obj, self.original_job_name)

    def get_seasons(self):
        """ Get the season number from the match object and format it """
        try:
            season = self.match_obj.group(1).strip('_')  # season number
        except AttributeError:
            season = '1'

        # Provide alternative formatting (0 padding)
        if season.lower() == 's':
            season2 = season
        else:
            try:
                season = str(int(season))
            except:
                pass
            season2 = season.rjust(2, '0')

        self.show_info['season_num'] = season
        self.show_info['season_num_alt'] = season2

    def get_episodes(self):
        """ Get the episode numbers from the match object, format and join them """
        try:
            ep_no = self.match_obj.group(2)  # episode number
        except AttributeError:
            ep_no = '1'
        # Store the original episode number

        # Provide alternative formatting (0 padding)
        ep_no2 = ep_no.rjust(2, '0')
        try:
            ep_no = str(int(ep_no))
        except:
            pass

        # Dual episode support
        if self.extras:
            ep_no, ep_no2 = self.get_multi_ep_naming(ep_no, ep_no2, self.extras)

        self.show_info['episode_num'] = ep_no
        self.show_info['episode_num_alt'] = ep_no2

    def get_showdescriptions(self):
        """ Get the show descriptions from the match object and format them """
        self.show_info['ep_name'], self.show_info['ep_name_two'], self.show_info['ep_name_three'] = get_descriptions(self.nzo, self.match_obj, self.original_job_name)

    def get_values(self):
        """ Collect and construct all the values needed for path replacement """
        try:
            # - Show Name
            self.get_shownames()

            # - Season
            self.get_seasons()

            # - Episode Number
            self.get_episodes()

            # - Episode Name
            self.get_showdescriptions()

            return True

        except:
            logging.error(T('Error getting TV info (%s)'), clip_path(self.original_job_name))
            logging.info("Traceback: ", exc_info=True)
            return False

    def construct_path(self):
        """ Replaces the sort string with real values such as Show Name and Episode Number """

        sorter = self.sort_string.replace('\\', '/')
        mapping = []

        if ends_in_file(sorter):
            extension = True
            sorter = sorter.replace('.%ext', '')
        else:
            extension = False

        # Replace Show name
        mapping.append(('%sn', self.show_info['show_tname']))
        mapping.append(('%s.n', self.show_info['show_tname_two']))
        mapping.append(('%s_n', self.show_info['show_tname_three']))
        mapping.append(('%sN', self.show_info['show_name']))
        mapping.append(('%s.N', self.show_info['show_name_two']))
        mapping.append(('%s_N', self.show_info['show_name_three']))

        # Replace season number
        mapping.append(('%s', self.show_info['season_num']))
        mapping.append(('%0s', self.show_info['season_num_alt']))

        # Original dir name
        mapping.append(('%dn', self.original_job_name))

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

        for key, name in REPLACE_AFTER.items():
            path = path.replace(key, name)

        # Lowercase all characters wrapped in {}
        path = to_lowercase(path)

        # Strip any extra ' ' '.' or '_' around foldernames
        path = strip_folders(path)

        # Split the last part of the path up for the renamer
        if extension:
            head, tail = os.path.split(path)
            self.filename_set = tail
            self.rename_or_not = True
        else:
            head = path

        if head:
            return os.path.normpath(head)
        else:
            # The normpath function translates "" to "."
            # which results in wrong path.join later on
            return head

    def rename(self, files, current_path):
        """ Rename for Series """
        logging.debug("Renaming Series")
        largest = (None, None, 0)

        def to_filepath(f, current_path):
            if is_full_path(f):
                filepath = os.path.normpath(f)
            else:
                filepath = os.path.normpath(os.path.join(current_path, f))
            return filepath

        # Create a generator of filepaths, ignore sample files and excluded files (vobs ect)
        filepaths = ((file, to_filepath(file, current_path)) for file in files if not RE_SAMPLE.search(file)
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
            self.fname, self.ext = os.path.splitext(os.path.split(file)[1])
            newname = "%s%s" % (self.filename_set, self.ext)
            # Replace %fn with the original filename
            newname = newname.replace('%fn', self.fname)
            newpath = os.path.join(current_path, newname)
            # Replace %ext with extension
            newpath = newpath.replace('%ext', self.ext)
            try:
                logging.debug("Rename: %s to %s", filepath, newpath)
                renamer(filepath, newpath)
            except:
                logging.error(T('Failed to rename: %s to %s'), clip_path(current_path), clip_path(newpath))
                logging.info("Traceback: ", exc_info=True)
            rename_similar(current_path, self.ext, self.filename_set, ())
        else:
            logging.debug('Nothing to rename, %s', files)


_RE_MULTIPLE = (
    re.compile(r'cd\W?(\d+)\W?', re.I),        # .cd1.mkv
    re.compile(r'\w\W?([\w\d])[{}]*$', re.I),  # blah1.mkv blaha.mkv
    re.compile(r'\w\W([\w\d])\W', re.I)        # blah-1-ok.mkv blah-a-ok.mkv
)


def check_for_multiple(files):
    """ Return list of files that looks like a multi-part post """
    for regex in _RE_MULTIPLE:
        matched_files = check_for_sequence(regex, files)
        if matched_files:
            return matched_files
    return ''


def check_for_sequence(regex, files):
    """ Return list of files that looks like a sequence, using 'regex' """
    matches = {}
    prefix = None
    # Build up a dictionary of matches
    # The key is based off the match, ie {1:'blah-part1.mkv'}
    for _file in files:
        name, ext = os.path.splitext(_file)
        match1 = regex.search(name)
        if match1:
            if not prefix or prefix == name[:match1.start()]:
                matches[match1.group(1)] = name + ext
                prefix = name[:match1.start()]

    # Don't do anything if only one or no files matched
    if len(list(matches.keys())) < 2:
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
            # convert {'b':'filename-b.mkv'} to {'2', 'filename-b.mkv'}
            item = matches.pop(akey)
            matches[str(key)] = item

    if passed:
        return matches
    else:
        return {}


class MovieSorter:
    """ Methods for Generic Sorting """

    def __init__(self, nzo, job_name, path, cat):
        self.matched = False

        self.original_job_name = job_name
        self.original_path = path
        self.sort_string = cfg.movie_sort_string()
        self.extra = cfg.movie_sort_extra()
        self.cats = cfg.movie_categories()
        self.cat = cat
        self.nzo = nzo
        self.filename_set = ''
        self.fname = ''  # Value for %fn substitution in folders
        self.final_path = ''

        self.match_obj = None

        self.rename_or_not = False

        self.movie_info = {}

        # Check if we match the category in init()
        self.match()

    def match(self, force=False):
        """ Checks the category for a match, if so set self.match to true """
        if force or (cfg.enable_movie_sorting() and self.sort_string):
            # First check if the show matches TV episode regular expressions. Returns regex match object
            if force or (self.cat and self.cat.lower() in self.cats) or (not self.cat and 'None' in self.cats):
                logging.debug("Found Movie (%s)", self.original_job_name)
                self.matched = True

    def get_final_path(self):
        """ Collect and construct all the variables such as episode name, show names """
        if self.get_values():
            # Get the final path
            path = self.construct_path()
            self.final_path = os.path.join(self.original_path, path)
            return self.final_path
        else:
            # Error Sorting
            return os.path.join(self.original_path, self.original_job_name)

    def get_values(self):
        """ Collect and construct all the values needed for path replacement """
        # - Get Year
        if self.nzo:
            year = self.nzo.nzo_info.get('year')
        else:
            year = ''
        if year:
            year_m = None
        else:
            job_name = self.original_job_name.replace('_', ' ')
            RE_YEAR = re.compile(year_match, re.I)
            year_m = RE_YEAR.search(job_name)
            if year_m:
                # Find the last matched date
                # Keep year_m to use in get_titles
                year = RE_YEAR.findall(job_name)[-1][0]
            else:
                year = ''
        self.movie_info['year'] = year

        # - Get Decades
        self.movie_info['decade'], self.movie_info['decade_two'] = get_decades(year)

        # - Get Title
        self.movie_info['ttitle'], self.movie_info['ttitle_two'], self.movie_info['ttitle_three'] = get_titles(self.nzo, year_m, self.original_job_name, True)
        self.movie_info['title'], self.movie_info['title_two'], self.movie_info['title_three'] = get_titles(self.nzo, year_m, self.original_job_name)

        return True

    def construct_path(self):
        """ Return path reconstructed from original and sort expression """
        sorter = self.sort_string.replace('\\', '/')
        mapping = []

        if ends_in_file(sorter):
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

        mapping.append(('%sn', self.movie_info['title']))
        mapping.append(('%s.n', self.movie_info['title_two']))
        mapping.append(('%s_n', self.movie_info['title_three']))

        mapping.append(('%sN', self.movie_info['ttitle']))
        mapping.append(('%s.N', self.movie_info['ttitle_two']))
        mapping.append(('%s_N', self.movie_info['ttitle_three']))

        # Replace year
        mapping.append(('%y', self.movie_info['year']))

        # Replace decades
        mapping.append(('%decade', self.movie_info['decade']))
        mapping.append(('%0decade', self.movie_info['decade_two']))

        # Original dir name
        mapping.append(('%dn', self.original_job_name))

        path = path_subst(sorter, mapping)

        for key, name in REPLACE_AFTER.items():
            path = path.replace(key, name)

        # Lowercase all characters wrapped in {}
        path = to_lowercase(path)

        # Strip any extra ' ' '.' or '_' around foldernames
        path = strip_folders(path)

        # Split the last part of the path up for the renamer
        if extension:
            head, tail = os.path.split(path)
            self.filename_set = tail
            self.rename_or_not = True
        else:
            head = path

        if head:
            return os.path.normpath(head)
        else:
            # The normpath function translates "" to "."
            # which results in wrong path.join later on
            return head

    def rename(self, _files, current_path):
        """ Rename for Generic files """
        logging.debug("Renaming Generic file")

        def filter_files(_file, current_path):
            if is_full_path(_file):
                filepath = os.path.normpath(_file)
            else:
                filepath = os.path.normpath(os.path.join(current_path, _file))
            if os.path.exists(filepath):
                size = os.stat(filepath).st_size
                if size >= cfg.movie_rename_limit.get_int() and not RE_SAMPLE.search(_file) \
                   and get_ext(_file) not in EXCLUDED_FILE_EXTS:
                    return True
            return False

        # remove any files below the limit from this list
        files = [_file for _file in _files if filter_files(_file, current_path)]

        length = len(files)
        # Single File Handling
        if length == 1:
            file = files[0]
            if is_full_path(file):
                filepath = os.path.normpath(file)
            else:
                filepath = os.path.normpath(os.path.join(current_path, file))
            if os.path.exists(filepath):
                self.fname, ext = os.path.splitext(os.path.split(file)[1])
                newname = "%s%s" % (self.filename_set, ext)
                newname = newname.replace('%fn', self.fname)
                newpath = os.path.join(current_path, newname)
                try:
                    logging.debug("Rename: %s to %s", filepath, newpath)
                    renamer(filepath, newpath)
                except:
                    logging.error(T('Failed to rename: %s to %s'), clip_path(filepath), clip_path(newpath))
                    logging.info("Traceback: ", exc_info=True)
                rename_similar(current_path, ext, self.filename_set, ())

        # Sequence File Handling
        # if there is more than one extracted file check for CD1/1/A in the title
        elif self.extra:
            matched_files = check_for_multiple(files)
            # rename files marked as in a set
            if matched_files:
                logging.debug("Renaming a series of generic files (%s)", matched_files)
                renamed = list(matched_files.values())
                for index, file in matched_files.items():
                    filepath = os.path.join(current_path, file)
                    renamed.append(filepath)
                    self.fname, ext = os.path.splitext(os.path.split(file)[1])
                    name = '%s%s' % (self.filename_set, self.extra)
                    name = name.replace('%1', str(index)).replace('%fn', self.fname)
                    name = name + ext
                    newpath = os.path.join(current_path, name)
                    try:
                        logging.debug("Rename: %s to %s", filepath, newpath)
                        renamer(filepath, newpath)
                    except:
                        logging.error(T('Failed to rename: %s to %s'), clip_path(filepath), clip_path(newpath))
                        logging.info("Traceback: ", exc_info=True)
                rename_similar(current_path, ext, self.filename_set, renamed)
            else:
                logging.debug("Movie files not in sequence %s", _files)


class DateSorter:
    """ Methods for Date Sorting """

    def __init__(self, nzo, job_name, path, cat):
        self.matched = False

        self.original_job_name = job_name
        self.original_path = path
        self.sort_string = cfg.date_sort_string()
        self.cats = cfg.date_categories()
        self.cat = cat
        self.nzo = nzo
        self.filename_set = ''
        self.fname = ''  # Value for %fn substitution in folders

        self.match_obj = None

        self.rename_or_not = False
        self.date_type = None

        self.date_info = {}
        self.final_path = ''

        # Check if we match the category in init()
        self.match()

    def match(self, force=False):
        """ Checks the category for a match, if so set self.matched to true """
        if force or (cfg.enable_date_sorting() and self.sort_string):
            # First check if the show matches TV episode regular expressions. Returns regex match object
            if force or (self.cat and self.cat.lower() in self.cats) or (not self.cat and 'None' in self.cats):
                self.match_obj, self.date_type = check_for_date(self.original_job_name, date_match)
                if self.match_obj:
                    logging.debug("Found date for sorting (%s)", self.original_job_name)
                    self.matched = True

    def is_match(self):
        """ Returns whether there was a match or not """
        return self.matched

    def get_final_path(self):
        """ Collect and construct all the variables such as episode name, show names """
        if self.get_values():
            # Get the final path
            path = self.construct_path()
            self.final_path = os.path.join(self.original_path, path)
            return self.final_path
        else:
            # Error Sorting
            return os.path.join(self.original_path, self.original_job_name)

    def get_values(self):
        """ Collect and construct all the values needed for path replacement """

        # 2008-10-16
        if self.date_type == 1:
            self.date_info['year'] = self.match_obj.group(1)
            self.date_info['month'] = self.match_obj.group(2)
            self.date_info['date'] = self.match_obj.group(3)
        # 10.16.2008
        else:
            self.date_info['year'] = self.match_obj.group(3)
            self.date_info['month'] = self.match_obj.group(1)
            self.date_info['date'] = self.match_obj.group(2)

        self.date_info['month_two'] = self.date_info['month'].rjust(2, '0')
        self.date_info['date_two'] = self.date_info['date'].rjust(2, '0')

        # - Get Decades
        self.date_info['decade'], self.date_info['decade_two'] = get_decades(self.date_info['year'])

        # - Get Title
        self.date_info['ttitle'], self.date_info['ttitle_two'], self.date_info['ttitle_three'] = get_titles(self.nzo, self.match_obj, self.original_job_name, True)
        self.date_info['title'], self.date_info['title_two'], self.date_info['title_three'] = get_titles(self.nzo, self.match_obj, self.original_job_name)

        self.date_info['ep_name'], self.date_info['ep_name_two'], self.date_info['ep_name_three'] = get_descriptions(self.nzo, self.match_obj, self.original_job_name)

        return True

    def construct_path(self):
        """ Return path reconstructed from original and sort expression """
        sorter = self.sort_string.replace('\\', '/')
        mapping = []

        if ends_in_file(sorter):
            extension = True
            sorter = sorter.replace(".%ext", '')
        else:
            extension = False

        # Replace title
        mapping.append(('%title', self.date_info['title']))
        mapping.append(('%.title', self.date_info['title_two']))
        mapping.append(('%_title', self.date_info['title_three']))

        mapping.append(('%t', self.date_info['title']))
        mapping.append(('%.t', self.date_info['title_two']))
        mapping.append(('%_t', self.date_info['title_three']))

        mapping.append(('%sn', self.date_info['ttitle']))
        mapping.append(('%s.n', self.date_info['ttitle_two']))
        mapping.append(('%s_n', self.date_info['ttitle_three']))
        mapping.append(('%sN', self.date_info['title']))
        mapping.append(('%s.N', self.date_info['title_two']))
        mapping.append(('%s_N', self.date_info['title_three']))

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

        # Replace dir-name before replacing %d for month
        mapping.append(('%dn', self.original_job_name))

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

        for key, name in REPLACE_AFTER.items():
            path = path.replace(key, name)

        # Lowercase all characters wrapped in {}
        path = to_lowercase(path)

        # Strip any extra ' ' '.' or '_' around foldernames
        path = strip_folders(path)

        # Split the last part of the path up for the renamer
        if extension:
            head, tail = os.path.split(path)
            self.filename_set = tail
            self.rename_or_not = True
        else:
            head = path

        if head:
            return os.path.normpath(head)
        else:
            # The normpath function translates "" to "."
            # which results in wrong path.join later on
            return head

    def rename(self, files, current_path):
        """ Renaming Date file """
        logging.debug("Renaming Date file")
        # find the master file to rename
        for file in files:
            if is_full_path(file):
                filepath = os.path.normpath(file)
            else:
                filepath = os.path.normpath(os.path.join(current_path, file))

            if os.path.exists(filepath):
                size = os.stat(filepath).st_size
                if size > cfg.movie_rename_limit.get_int():
                    if 'sample' not in file:
                        self.fname, ext = os.path.splitext(os.path.split(file)[1])
                        newname = "%s%s" % (self.filename_set, ext)
                        newname = newname.replace('%fn', self.fname)
                        newpath = os.path.join(current_path, newname)
                        if not os.path.exists(newpath):
                            try:
                                logging.debug("Rename: %s to %s", filepath, newpath)
                                renamer(filepath, newpath)
                            except:
                                logging.error(T('Failed to rename: %s to %s'), clip_path(current_path), clip_path(newpath))
                                logging.info("Traceback: ", exc_info=True)
                            rename_similar(current_path, ext, self.filename_set, ())
                            break


def path_subst(path, mapping):
    """ Replace the sort sting elements by real values.
        Non-elements are copied literally.
        path = the sort string
        mapping = array of tuples that maps all elements to their values
    """
    # Added ugly hack to prevent %ext from being masked by %e
    newpath = []
    plen = len(path)
    n = 0
    while n < plen:
        result = path[n]
        if result == '%':
            for key, value in mapping:
                if path.startswith(key, n) and not path.startswith('%ext', n):
                    n += len(key) - 1
                    result = value
                    break
        newpath.append(result)
        n += 1
    return ''.join(newpath)


def get_titles(nzo, match, name, titleing=False):
    """ The title will be the part before the match
        Clean it up and title() it

        ''.title() isn't very good under python so this contains
        a lot of little hacks to make it better and for more control
    """
    if nzo:
        title = nzo.nzo_info.get('propername')
    else:
        title = ''
    if not title:
        if match:
            name = name[:match.start()]

        # Replace .US. with (US)
        if cfg.tv_sort_countries() == 1:
            for rep in COUNTRY_REP:
                # (us) > (US)
                name = replace_word(name, rep.lower(), rep)
                # (Us) > (US)
                name = replace_word(name, rep.title(), rep)
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

        if titleing:
            title = title.title()  # title the show name so it is in a consistent letter case

            # title applied uppercase to 's Python bug?
            title = title.replace("'S", "'s")

            # Replace titled country names, (Us) with (US) and so on
            if cfg.tv_sort_countries() == 1:
                for rep in COUNTRY_REP:
                    title = title.replace(rep.title(), rep)
            # Remove country names, ie (Us)
            elif cfg.tv_sort_countries() == 2:
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

            # Make sure the first letter of the title is always uppercase
            if title:
                title = title[0].title() + title[1:]

    # The title with spaces replaced by dots
    dots = title.replace(" - ", "-").replace(' ', '.').replace('_', '.')
    dots = dots.replace('(', '.').replace(')', '.').replace('..', '.').rstrip('.')

    # The title with spaces replaced by underscores
    underscores = title.replace(' ', '_').replace('.', '_').replace('__', '_').rstrip('_')

    return title, dots, underscores


def replace_word(word_input, one, two):
    """ Regex replace on just words """
    regex = re.compile(r'\W(%s)(\W|$)' % one, re.I)
    matches = regex.findall(word_input)
    if matches:
        for unused in matches:
            word_input = word_input.replace(one, two)
    return word_input


def get_descriptions(nzo, match, name):
    """ If present, get a description from the nzb name.
        A description has to be after the matched item, separated either
        like ' - Description' or '_-_Description'
    """
    if nzo:
        ep_name = nzo.nzo_info.get('episodename')
    else:
        ep_name = ''
    if not ep_name:
        if match:
            ep_name = name[match.end():]  # Need to improve for multi-ep support
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


def get_decades(year):
    """ Return 4 digit and 2 digit decades given 'year' """
    if year:
        try:
            decade = year[2:3] + '0'
            decade2 = year[:3] + '0'
        except:
            decade = ''
            decade2 = ''
    else:
        decade = ''
        decade2 = ''
    return decade, decade2


def check_for_folder(path):
    """ Return True if any folder is found in the tree at 'path' """
    for _root, dirs, _files in os.walk(path):
        if dirs:
            return True
    return False


def to_lowercase(path):
    """ Lowercases any characters enclosed in {} """
    _RE_LOWERCASE = re.compile(r'{([^{]*)}')
    while True:
        m = _RE_LOWERCASE.search(path)
        if not m:
            break
        path = path[:m.start()] + m.group(1).lower() + path[m.end():]

    # just in case
    path = path.replace('{', '')
    path = path.replace('}', '')
    return path


def strip_folders(path):
    """ Return 'path' without leading and trailing spaces and underscores in each element
        For Windows, also remove leading and trailing dots
    """
    unc = sabnzbd.WIN32 and (path.startswith('//') or path.startswith('\\\\'))
    f = path.strip('/').split('/')

    # For path beginning with a slash, insert empty element to prevent loss
    if path.strip()[0] in '/\\':
        f.insert(0, '')

    def strip_all(x):
        """ Strip all leading/trailing underscores also dots for Windows """
        x = x.strip().strip('_')
        if sabnzbd.WIN32:
            # OSX and Linux should keep dots, because leading dots are significant
            # while Windows cannot handle trailing dots
            x = x.strip('.')
        x = x.strip()
        return x

    path = os.path.normpath('/'.join([strip_all(x) for x in f]))
    if unc:
        return '\\' + path
    else:
        return path


def rename_similar(folder, skip_ext, name, skipped_files):
    """ Rename all other files in the 'folder' hierarchy after 'name'
        and move them to the root of 'folder'.
        Files having extension 'skip_ext' will be moved, but not renamed.
        Don't touch files in list `skipped_files`
    """
    logging.debug('Give files in set "%s" matching names.', name)
    folder = os.path.normpath(folder)
    skip_ext = skip_ext.lower()

    for root, dirs, files in os.walk(folder):
        for f in files:
            path = os.path.join(root, f)
            if path in skipped_files:
                continue
            org, ext = os.path.splitext(f)
            if ext.lower() == skip_ext:
                # Move file, but do not rename
                newpath = os.path.join(folder, f)
            else:
                # Move file and rename
                newname = "%s%s" % (name, ext)
                newname = newname.replace('%fn', org)
                newpath = os.path.join(folder, newname)
            if path != newpath:
                newpath = get_unique_filename(newpath)
                try:
                    logging.debug("Rename: %s to %s", path, newpath)
                    renamer(path, newpath)
                except:
                    logging.error(T('Failed to rename similar file: %s to %s'), clip_path(path), clip_path(newpath))
                    logging.info("Traceback: ", exc_info=True)
    cleanup_empty_directories(folder)


def check_regexs(filename, matchers):
    """ Regular Expression match for a list of regexes
        Returns the MatchObject if a match is made
        This version checks for an additional match
    """
    extras = []
    for expressions in matchers:
        expression, extramatchers = expressions
        match1 = expression.search(filename)
        if match1:
            for m in extramatchers:
                match2 = m.findall(filename, match1.end())
                if match2:
                    for match in match2:
                        if type(match) == type(()) and len(match) > 1:
                            extras.append(match[1])
                        else:
                            extras.append(match)
                    break
            return match1, extras
    return None, None


def check_for_date(filename, matcher):
    """ Regular Expression match for date based files
        Returns the MatchObject if a match is made
    """
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
    """ Return True if path is absolute """
    if file.startswith('\\') or file.startswith('/'):
        return True
    try:
        if file[1:3] == ':\\':
            return True
    except:
        pass
    return False


def eval_sort(sorttype, expression, name=None, multipart=''):
    """ Preview a sort expression, to be used by API """
    from sabnzbd.api import Ttemplate
    path = ''
    name = sanitize_foldername(name)
    if sorttype == 'series':
        name = name or ('%s S01E05 - %s [DTS]' % (Ttemplate('show-name'), Ttemplate('ep-name')))
        sorter = SeriesSorter(None, name, path, 'tv')
    elif sorttype == 'movie':
        name = name or (Ttemplate('movie-sp-name') + ' (2009)')
        sorter = MovieSorter(None, name, path, 'tv')
    elif sorttype == 'date':
        name = name or (Ttemplate('show-name') + ' 2009-01-02')
        sorter = DateSorter(None, name, path, 'tv')
    else:
        return None
    sorter.sort_string = expression
    sorter.match(force=True)
    path = sorter.get_final_path()
    path = os.path.normpath(os.path.join(path, sorter.filename_set))
    fname = Ttemplate('orgFilename')
    fpath = path
    if sorttype == 'movie' and '%1' in multipart:
        fname = fname + multipart.replace('%1', '1')
        fpath = fpath + multipart.replace('%1', '1')
    if '%fn' in path:
        path = path.replace('%fn', fname + '.mkv')
    else:
        if sorter.rename_or_not:
            path = fpath + '.mkv'
        else:
            if sabnzbd.WIN32:
                path += '\\'
            else:
                path += '/'
    return path
