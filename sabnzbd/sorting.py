#!/usr/bin/python3 -OO
# Copyright 2007-2023 The SABnzbd-Team <team@sabnzbd.org>
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
"""

import os
import logging
import re
import guessit
from rebulk.match import MatchesDict
from string import whitespace, ascii_lowercase, punctuation
from typing import Optional, Union, List, Tuple, Dict

import sabnzbd
from sabnzbd.filesystem import (
    move_to_path,
    cleanup_empty_directories,
    get_unique_filename,
    get_ext,
    renamer,
    sanitize_foldername,
    clip_path,
)
import sabnzbd.cfg as cfg
from sabnzbd.constants import EXCLUDED_GUESSIT_PROPERTIES, IGNORED_MOVIE_FOLDERS
from sabnzbd.misc import is_sample
from sabnzbd.nzbstuff import NzbObject, scan_password

# Do not rename .vob files as they are usually DVD's
EXCLUDED_FILE_EXTS = (".vob", ".bin")

LOWERCASE = ("the", "of", "and", "at", "vs", "a", "an", "but", "nor", "for", "on", "so", "yet", "with")
UPPERCASE = ("III", "II", "IV")

REPLACE_AFTER = {"()": "", "..": ".", "__": "_", "  ": " ", " .%ext": ".%ext"}

RE_GI = re.compile(r"(%G([._]?)I<([\w]+)>)")  # %GI<property>, %G.I<property>, or %G_I<property>

# Prevent guessit/rebulk from spamming the log when debug logging is active in SABnzbd
logging.getLogger("rebulk").setLevel(logging.WARNING)


class BaseSorter:
    """Common methods for Sorter classes"""

    def __init__(
        self,
        nzo: Optional[NzbObject],
        job_name: str,
        path: str,
        cat: str,
        sort_string: str,
        cats: str,
        guess: Optional[MatchesDict],
        force: Optional[bool] = False,
    ):
        self.matched = False
        self.original_job_name = job_name
        self.original_path = path
        self.nzo = nzo
        self.cat = cat
        self.filename_set = ""
        self.fname = ""  # Value for %fn substitution in folders
        self.rename_files = False
        self.info = {}
        self.type = None
        self.guess = guess
        self.force = force
        self.sort_string = sort_string
        self.cats = cats

        # Check categories and do the guessing work, if necessary
        self.match()

    def match(self):
        """Implemented by child classes"""
        pass

    def get_values(self):
        """Implemented by child classes"""
        pass

    def get_final_path(self) -> str:
        if self.matched:
            # Construct the final path
            self.get_values()
            return os.path.join(self.original_path, self.construct_path())
        else:
            # Error Sorting
            return os.path.join(self.original_path, self.original_job_name)

    def get_names(self):
        """Get the show or movie name from the guess and format it"""
        # Get the formatted title and alternate title formats
        self.info["ttitle"], self.info["ttitle_two"], self.info["ttitle_three"] = get_titles(
            self.nzo, self.guess, self.original_job_name, True
        )
        self.info["title"], self.info["title_two"], self.info["title_three"] = get_titles(
            self.nzo, self.guess, self.original_job_name
        )

    def get_resolution(self):
        self.info["resolution"] = self.guess.get("screen_size", "")

    def get_showdescriptions(self):
        """Get the show descriptions based on metadata, guessit and jobname"""
        self.info["ep_name"], self.info["ep_name_two"], self.info["ep_name_three"] = get_descriptions(
            self.nzo, self.guess, self.original_job_name
        )

    def get_year(self):
        """Get the year and the corresponding two and four digit decade values"""
        year = ""
        if self.nzo:
            year = self.nzo.nzo_info.get("year")
        if not year:
            year = self.guess.get("year", "")
            if not year:
                # Try extracting the year from the guessed date instead
                try:
                    year = self.guess.get("date").year or ""
                except:
                    pass
        self.info["year"] = str(year)
        self.info["decade"] = ""
        self.info["decade_two"] = ""
        if self.info["year"]:
            try:
                self.info["decade"] = self.info["year"][2:3] + "0"
                self.info["decade_two"] = self.info["year"][:3] + "0"
            except TypeError:
                pass

    def is_proper(self):
        """Determine if the release is tagged 'Proper'. Note that guessit also sets this for similar
        tags such as 'Real' and 'Repack', saving us the trouble of checking for additional keywords."""
        other = self.guess.get("other", "")
        if isinstance(other, list):
            return "Proper" in other
        else:
            return other == "Proper"

    def construct_path(self) -> str:
        """Map all markers and replace the sort string with real values"""
        sorter = self.sort_string
        mapping = []

        if ends_in_file(sorter):
            extension = True
            if sorter.endswith(".%ext"):
                sorter = sorter[:-5]  # Strip '.%ext' off the end; other %ext may remain in sorter
        else:
            extension = False

        # Title
        mapping.append(("%title", self.info["title"]))
        mapping.append(("%.title", self.info["title_two"]))
        mapping.append(("%_title", self.info["title_three"]))
        # Legacy markers for the same; note that %t must come after %title
        mapping.append(("%t", self.info["title"]))
        mapping.append(("%.t", self.info["title_two"]))
        mapping.append(("%_t", self.info["title_three"]))
        mapping.append(("%sN", self.info["title"]))
        mapping.append(("%s.N", self.info["title_two"]))
        mapping.append(("%s_N", self.info["title_three"]))

        # Titlecased title
        mapping.append(("%sn", self.info["ttitle"]))
        mapping.append(("%s.n", self.info["ttitle_two"]))
        mapping.append(("%s_n", self.info["ttitle_three"]))

        # Original directory name
        mapping.append(("%dn", self.original_job_name))

        # Resolution
        mapping.append(("%r", self.info["resolution"]))

        # Year
        mapping.append(("%year", self.info["year"]))
        mapping.append(("%y", self.info["year"]))

        # Decades
        mapping.append(("%decade", self.info["decade"]))
        mapping.append(("%0decade", self.info["decade_two"]))

        # Handle some type-specific mappings
        if self.type in ("tv", "date"):
            # Episode name
            mapping.append(("%en", self.info["ep_name"]))
            mapping.append(("%e.n", self.info["ep_name_two"]))
            mapping.append(("%e_n", self.info["ep_name_three"]))

            # Legacy %desc
            if self.type == "date" and self.info.get("ep_name"):
                # For date, %desc was no longer listed but still supported in the backend. For tv,
                # it was invalid and %en (etc.) used instead. For backward compatibility, map %desc
                # to %en for 'date' only and remove for 'tv'.
                mapping.append(("%desc", self.info["ep_name"]))
            else:
                mapping.append(("%desc", ""))

            if self.type == "tv":
                # Season number
                mapping.append(("%s", self.info["season_num"]))
                mapping.append(("%0s", self.info["season_num_alt"]))

                # Episode number; note this must come after the %en variants
                mapping.append(("%e", self.info["episode_num"]))
                mapping.append(("%0e", self.info["episode_num_alt"]))

            if self.type == "date":
                # Month
                mapping.append(("%m", self.info["month"]))
                mapping.append(("%0m", self.info["month_two"]))

                # Day
                mapping.append(("%d", self.info["day"]))
                mapping.append(("%0d", self.info["day_two"]))

        # Handle generic guessit markers
        for marker, spacer, guess_property in re.findall(RE_GI, sorter):
            value = self.guess.get(guess_property, "") if self.guess else ""
            # Guessit returns a list for some properties in case they have multiple entries/values
            if isinstance(value, list):
                value = "-".join([str(v) for v in value])  # Format as value1-value2
            else:
                value = str(value)
            if spacer:
                value = value.replace(" ", spacer)
            mapping.append((marker, value))

        # Replace elements
        path = path_subst(sorter, mapping)

        for key, name in REPLACE_AFTER.items():
            path = path.replace(key, name)

        # Lowercase all characters wrapped in {}
        path = to_lowercase(path)

        # Strip any extra spaces, dots, and underscores around directory names
        path = strip_path_elements(path)

        # Split the last part of the path up for the renamer
        if extension:
            path, self.filename_set = os.path.split(path)
            self.rename_files = True

        # The normpath function translates "" to "." which results in an incorrect path
        return os.path.normpath(path) if path else path

    def rename(self, files: List[str], current_path: str, min_size: int) -> Tuple[str, bool]:
        largest = (None, None, 0)

        def to_filepath(file, current_path):
            if is_full_path(file):
                filepath = os.path.normpath(file)
            else:
                filepath = os.path.normpath(os.path.join(current_path, file))
            return filepath

        # Create a generator of filepaths, ignore samples and excluded files
        filepaths = (
            (file, to_filepath(file, current_path))
            for file in files
            if not is_sample(file) and get_ext(file) not in EXCLUDED_FILE_EXTS
        )

        # Find the largest file
        for file, fp in filepaths:
            # Skip any file that no longer exists (e.g. extension on the cleanup list)
            if not os.path.exists(fp):
                continue
            size = os.stat(fp).st_size
            f_file, f_fp, f_size = largest
            if size > f_size:
                largest = (file, fp, size)

        file, filepath, size = largest

        if filepath and size > min_size:
            self.fname, ext = os.path.splitext(os.path.split(file)[1])
            newpath = os.path.join(
                current_path, self.filename_set.replace("%fn", self.fname).replace("%ext", ext.lstrip(".")) + ext
            )
            if not os.path.exists(newpath):
                try:
                    logging.debug("Rename: %s to %s", filepath, newpath)
                    renamer(filepath, newpath)
                except:
                    logging.error(T("Failed to rename: %s to %s"), clip_path(current_path), clip_path(newpath))
                    logging.info("Traceback: ", exc_info=True)
                rename_similar(current_path, ext, self.filename_set)
        else:
            logging.debug("Nothing to rename, %s", files)

        return move_to_parent_directory(current_path)


class Sorter:
    """Generic Sorter"""

    def __init__(self, nzo: Optional[NzbObject], cat: str):
        self.sorter: Optional[BaseSorter] = None
        self.sorter_active = False
        self.nzo = nzo
        self.cat = cat

    def detect(self, job_name: str, complete_dir: str) -> str:
        """Detect the sorting type"""
        guess = guess_what(job_name)

        if guess["type"] == "episode":
            if "date" in guess:
                self.sorter = DateSorter(self.nzo, job_name, complete_dir, self.cat, guess)
            else:
                self.sorter = SeriesSorter(self.nzo, job_name, complete_dir, self.cat, guess)
        elif guess["type"] == "movie":
            self.sorter = MovieSorter(self.nzo, job_name, complete_dir, self.cat, guess)

        if self.sorter and self.sorter.matched:
            self.sorter_active = True

        return self.sorter.get_final_path() if self.sorter_active else complete_dir


class SeriesSorter(BaseSorter):
    """Methods for Series Sorting"""

    def __init__(
        self,
        nzo: Optional[NzbObject],
        job_name: str,
        path: Optional[str],
        cat: Optional[str],
        guess: Optional[MatchesDict] = None,
        force: Optional[bool] = False,
    ):
        super().__init__(nzo, job_name, path, cat, cfg.tv_sort_string(), cfg.tv_categories(), guess, force)

    def match(self):
        """Try to guess series info if config and category sort out or force is set"""
        if self.force or (cfg.enable_tv_sorting() and cfg.tv_sort_string() and self.cat.lower() in self.cats):
            if not self.guess:
                self.guess = guess_what(self.original_job_name, sort_type="episode")
            if self.guess.get("type") == "episode" and "date" not in self.guess:
                logging.debug("Using tv sorter for %s", self.original_job_name)
                self.matched = True
                self.type = "tv"

        # Require at least 1 category, this was not enforced before 3.4.0
        if cfg.enable_tv_sorting() and not self.cats:
            logging.warning("%s: %s", T("Series Sorting"), T("Select at least 1 category."))

    def get_values(self):
        """Collect all values needed for path replacement"""
        self.get_year()
        self.get_names()
        self.get_seasons()
        self.get_episodes()
        self.get_showdescriptions()
        self.get_resolution()

    def format_series_numbers(self, numbers: Union[int, List[int]], info_name: str):
        """Format the numbers in both plain and alternative (zero-padded) format and set as showinfo"""
        # Guessit returns multiple episodes or seasons as a list of integers, single values as int
        if isinstance(numbers, int):
            self.info[info_name] = str(numbers)  # 1
            self.info[info_name + "_alt"] = str(numbers).rjust(2, "0")  # 01
        else:
            self.info[info_name] = "-".join([str(num) for num in numbers])  # 1-2-3
            self.info[info_name + "_alt"] = "-".join([str(num).rjust(2, "0") for num in numbers])  # 01-02-03

    def get_seasons(self):
        """Fetch the guessed season number(s)"""
        self.format_series_numbers(self.guess.get("season", ""), "season_num")

    def get_episodes(self):
        """Fetch the guessed episode number(s)"""
        self.format_series_numbers(self.guess.get("episode", ""), "episode_num")

    def rename(self, files: List[str], current_path: str, min_size: int = -1) -> Tuple[str, bool]:
        """Rename for Series"""
        if min_size < 0:
            min_size = cfg.episode_rename_limit.get_int()
        if not self.rename_files:
            return move_to_parent_directory(current_path)
        else:
            logging.debug("Renaming series file(s)")
            return super().rename(files, current_path, min_size)


class MovieSorter(BaseSorter):
    """Methods for Movie Sorting"""

    def __init__(
        self,
        nzo: Optional[NzbObject],
        job_name: str,
        path: str,
        cat: str,
        guess: Optional[MatchesDict] = None,
        force: Optional[bool] = False,
    ):
        self.extra = cfg.movie_sort_extra()

        super().__init__(nzo, job_name, path, cat, cfg.movie_sort_string(), cfg.movie_categories(), guess, force)

    def match(self):
        """Try to guess movie info if config and category sort out or force is set"""
        if self.force or (cfg.enable_movie_sorting() and self.sort_string and self.cat.lower() in self.cats):
            if not self.guess:
                self.guess = guess_what(self.original_job_name, sort_type="movie")
            if self.guess.get("type") == "movie":
                logging.debug("Using movie sorter for %s", self.original_job_name)
                self.matched = True
                self.type = "movie"

        # Require at least 1 category, this was not enforced before 3.4.0
        if cfg.enable_movie_sorting() and not self.cats:
            logging.warning("%s: %s", T("Movie Sorting"), T("Select at least 1 category."))

    def get_values(self):
        """Collect all values needed for path replacement"""
        self.get_year()
        self.get_resolution()
        self.get_names()

    def rename(self, files, current_path, min_size: int = -1) -> Tuple[str, bool]:
        """Rename for movie files"""
        if min_size < 0:
            min_size = cfg.movie_rename_limit.get_int()

        if not self.rename_files:
            return move_to_parent_directory(current_path)

        logging.debug("Renaming movie file(s)")

        def filter_files(f, current_path):
            filepath = os.path.normpath(f) if is_full_path(f) else os.path.normpath(os.path.join(current_path, f))
            if os.path.exists(filepath):
                if os.stat(filepath).st_size >= min_size and not is_sample(f) and get_ext(f) not in EXCLUDED_FILE_EXTS:
                    return True
            return False

        # Filter samples and anything nonexistent or below the size limit
        files = [f for f in files if filter_files(f, current_path)]

        # Single movie file
        if len(files) == 1:
            return super().rename(files, current_path, min_size)

        # Multiple files, check for sequential filenames
        elif files and self.extra:
            matched_files = check_for_multiple(files)
            if matched_files:
                logging.debug("Renaming sequential files %s", matched_files)
                renamed = list(matched_files.values())
                for index, file in matched_files.items():
                    filepath = os.path.join(current_path, file)
                    renamed.append(filepath)
                    self.fname, ext = os.path.splitext(os.path.split(file)[1])
                    name = (self.filename_set + self.extra).replace("%1", str(index)).replace(
                        "%fn", self.fname
                    ).replace("%ext", ext.lstrip(".")) + ext
                    newpath = os.path.join(current_path, name)
                    try:
                        logging.debug("Rename: %s to %s", filepath, newpath)
                        renamer(filepath, newpath)
                    except:
                        logging.error(T("Failed to rename: %s to %s"), clip_path(filepath), clip_path(newpath))
                        logging.info("Traceback: ", exc_info=True)
                rename_similar(current_path, ext, self.filename_set, renamed)
            else:
                logging.debug("No sequential files in %s", files)

        return move_to_parent_directory(current_path)


class DateSorter(BaseSorter):
    """Methods for Date Sorting"""

    def __init__(
        self,
        nzo: Optional[NzbObject],
        job_name: str,
        path: str,
        cat: str,
        guess: Optional[MatchesDict] = None,
        force: Optional[bool] = False,
    ):
        super().__init__(nzo, job_name, path, cat, cfg.date_sort_string(), cfg.date_categories(), guess, force)

    def match(self):
        """Checks the category for a match, if so set self.matched to true"""
        if self.force or (cfg.enable_date_sorting() and self.sort_string and self.cat.lower() in self.cats):
            if not self.guess:
                self.guess = guess_what(self.original_job_name, sort_type="episode")
            if self.guess.get("type") == "episode" and "date" in self.guess:
                logging.debug("Using date sorter for %s", self.original_job_name)
                self.matched = True
                self.type = "date"

        # Require at least 1 category, this was not enforced before 3.4.0
        if cfg.enable_date_sorting() and not self.cats:
            logging.warning("%s: %s", T("Date Sorting"), T("Select at least 1 category."))

    def get_date(self):
        """Get month and day"""
        self.info["month"] = str(self.guess.get("date").month)
        self.info["day"] = str(self.guess.get("date").day)
        # Zero-padded versions of the same
        self.info["month_two"] = self.info["month"].rjust(2, "0")
        self.info["day_two"] = self.info["day"].rjust(2, "0")

    def get_values(self):
        """Collect all values needed for path replacement"""
        self.get_year()
        self.get_date()
        self.get_resolution()
        self.get_names()
        self.get_showdescriptions()

    def rename(self, files: List[str], current_path: str, min_size: int = -1) -> Tuple[str, bool]:
        """Renaming Date file"""
        if min_size < 0:
            min_size = cfg.episode_rename_limit.get_int()
        if not self.rename_files:
            return move_to_parent_directory(current_path)
        else:
            logging.debug("Renaming date file(s)")
            return super().rename(files, current_path, min_size)


def ends_in_file(path: str) -> bool:
    """Return True when path ends with '.%ext' or '%fn' while allowing for a lowercase marker"""
    RE_ENDEXT = re.compile(r"\.%ext}?$", re.I)
    RE_ENDFN = re.compile(r"%fn}?$", re.I)
    return bool(RE_ENDEXT.search(path) or RE_ENDFN.search(path))


def move_to_parent_directory(workdir: str) -> Tuple[str, bool]:
    """Move all files under 'workdir' into 'workdir/..'"""
    # Determine 'folder'/..
    workdir = os.path.abspath(os.path.normpath(workdir))
    dest = os.path.abspath(os.path.normpath(os.path.join(workdir, "..")))

    logging.debug("Moving all files from %s to %s", workdir, dest)

    # Check for DVD folders and bail out if found
    for item in os.listdir(workdir):
        if item.lower() in IGNORED_MOVIE_FOLDERS:
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


def guess_what(name: str, sort_type: Optional[str] = None) -> MatchesDict:
    """Guess metadata for movies or episodes from their name. The sort_type ('movie' or 'episode')
    is passed as a hint to guessit, if given."""

    if not name:
        raise ValueError("Need a name for guessing")

    # Remove any passwords from the name
    name = scan_password(name)[0]

    # Avoid trouble with names starting with a digit (esp. with no year in the name)
    digit_fix = "FIX" if name[0].isdigit() else ""

    guessit_options = {
        # "no-user-config": True,
        "expected_title": [],  # This isn't empty by default?
        # "allowed_countries": [],
        # "allowed_languages": [],
        "excludes": EXCLUDED_GUESSIT_PROPERTIES,
        "date_year_first": True,  # Make sure also short-dates are detected as YY-MM-DD
    }
    if sort_type:
        # Hint the type if known
        guessit_options["type"] = sort_type

    guess = guessit.api.guessit(digit_fix + name, options=guessit_options)
    logging.debug("Initial guess for %s is %s", digit_fix + name, guess)

    if digit_fix:
        # Unfix the title
        guess["title"] = guess.get("title", "")[len(digit_fix) :]

    # Force season to 1 for seasonless episodes with no date
    if guess.get("type") == "episode" and "date" not in guess:
        guess.setdefault("season", 1)

    # Try to avoid setting the type to movie on arbitrary jobs (e.g. 'Setup.exe') just because guessit defaults to that
    table = str.maketrans({char: "" for char in whitespace + "_.-()[]{}"})
    if guess.get("type") == "movie" and not sort_type == "movie":  # No movie hint
        if (
            guess.get("title", "").translate(table) == name.translate(table)  # Check for full name used as title
            or any(
                c in guess.get("release_group", "") for c in (whitespace + punctuation)
            )  # interpuction of white spaces in the groupname
            or not any(
                [key in guess for key in ("year", "screen_size", "video_codec")]
            )  # No typical movie properties set
        ):
            guess["type"] = "unknown"

    return guess


def path_subst(path: str, mapping: List[Tuple[str, str]]) -> str:
    """Replace the sort string elements in the path with the real values provided by the mapping;
    non-elements are copied verbatim."""
    # Added ugly hack to prevent %ext from being masked by %e
    newpath = []
    plen = len(path)
    n = 0
    while n < plen:
        result = path[n]
        if result == "%":
            for key, value in mapping:
                if path.startswith(key, n) and not path.startswith("%ext", n):
                    n += len(key) - 1
                    result = value
                    break
        if result:
            newpath.append(result)
        n += 1
    return "".join(newpath)


def get_titles(
    nzo: Optional[NzbObject], guess: Optional[MatchesDict], jobname: str, titleing: bool = False
) -> Tuple[str, str, str]:
    """Get the title from NZB metadata or jobname, and return it in various formats. Formatting
    mostly deals with working around quirks of Python's str.title(). NZB metadata is used as-is,
    further processing done only for info obtained from guessit or the jobname."""
    title = ""
    if nzo:
        # Fetch NZB metadata
        title = nzo.nzo_info.get("propername")
    if not title:
        # Try guessit next
        if guess:
            title = guess.get("title", "")

        # Fallback to the jobname if neither of the better options yielded a title
        if not title:
            title = jobname.replace(".", " ").replace("_", " ").strip(whitespace + "._-")

        if titleing:
            # Titlecase the show name so it is in a consistent letter case
            title = title.title()

            # Get rid of 's uppercased by str.title()
            title = title.replace("'S", "'s")

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

        if guess and "country" in guess:
            title += " " + str(guess.get("country"))  # Append ' CC'

    # Alternative formats
    dots = re.sub(
        r"\.{2,}",
        ".",
        title.replace(" - ", "-").replace(" ", ".").replace("_", ".").replace("(", ".").replace(")", "."),
    ).rstrip(".")
    underscores = re.sub("_{2,}", "_", title.replace(" ", "_").replace(".", "_")).rstrip("_")

    return title, dots, underscores


def replace_word(word_input: str, one: str, two: str) -> str:
    """Regex replace on just words"""
    RE_WORD = re.compile(r"\W(%s)(\W|$)" % one, re.I)
    matches = RE_WORD.findall(word_input)
    if matches:
        for _ in matches:
            word_input = word_input.replace(one, two)
    return word_input


def get_descriptions(nzo: Optional[NzbObject], guess: Optional[MatchesDict], jobname: str) -> Tuple[str, str, str]:
    """Try to get an episode title or similar description from the NZB metadata or jobname, e.g.
    'Download This' in Show.S01E23.Download.This.1080p.HDTV.x264 and return multiple formats"""
    ep_name = None
    if nzo:
        ep_name = nzo.nzo_info.get("episodename")
    if (not ep_name) and guess:
        ep_name = guess.get("episode_title")
    ep_name = ep_name or ""

    ep_name = ep_name.strip("- _.")
    if "." in ep_name and " " not in ep_name:
        ep_name = ep_name.replace(".", " ")

    # Return the episode names with spaces, dots, and underscores
    return ep_name.replace("_", " "), ep_name.replace(" - ", "-").replace(" ", "."), ep_name.replace(" ", "_")


def to_lowercase(path: str) -> str:
    """Lowercases any characters enclosed in {}"""
    RE_LOWERCASE = re.compile(r"{([^{]*)}")
    while True:
        m = RE_LOWERCASE.search(path)
        if not m:
            break
        path = path[: m.start()] + m.group(1).lower() + path[m.end() :]

    # Remove any remaining '{' and '}'
    return path.replace("{", "").replace("}", "")


def strip_path_elements(path: str) -> str:
    """Return 'path' without leading and trailing spaces and underscores in each element"""
    # Clear the most deviant of UNC notations
    path = clip_path(path)
    if sabnzbd.WIN32:
        path = path.replace("\\", "/")  # Switch to unix style directory separators
    is_unc = sabnzbd.WIN32 and path.startswith("//")

    path_elements = path.strip("/").split("/")
    # Insert an empty element to prevent loss, if path starts with a slash
    if not is_unc and path.strip()[0] in "/":
        path_elements.insert(0, "")

    # For Windows, also remove leading and trailing dots: it cannot handle trailing dots, and
    # leading dots carry no significance like on macOS, Linux, etc.
    chars = whitespace + "_" + ("." if sabnzbd.WIN32 else "")

    # Clean all elements and reconstruct the path
    path = os.path.normpath("/".join([element.strip(chars) for element in path_elements]))
    path = path.replace("//", "/")  # Re: https://bugs.python.org/issue26329

    return "\\\\" + path if is_unc else path


def rename_similar(folder: str, skip_ext: str, name: str, skipped_files: Optional[List[str]] = None):
    """Rename all other files in the 'folder' hierarchy after 'name'
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
            if skipped_files and path in skipped_files:
                continue
            org, ext = os.path.splitext(f)
            if ext.lower() == skip_ext:
                # Move file, but do not rename
                newpath = os.path.join(folder, f)
            else:
                # Move file and rename
                newname = "%s%s" % (name, ext)
                newname = newname.replace("%fn", org)
                newpath = os.path.join(folder, newname)
            if path != newpath:
                newpath = get_unique_filename(newpath)
                try:
                    logging.debug("Rename: %s to %s", path, newpath)
                    renamer(path, newpath)
                except:
                    logging.error(T("Failed to rename similar file: %s to %s"), clip_path(path), clip_path(newpath))
                    logging.info("Traceback: ", exc_info=True)
    cleanup_empty_directories(folder)


def is_full_path(file: str) -> bool:
    """Determine whether file has an absolute path"""
    return file.startswith("/") or (sabnzbd.WIN32 and (file.startswith("\\") or file[1:3] == ":\\"))


def eval_sort(sort_type: str, expression: str, name: str = None, multipart: str = "") -> Optional[str]:
    """Preview a sort expression, to be used by API"""
    from sabnzbd.api import Ttemplate

    path = ""
    name = sanitize_foldername(name)
    if sort_type == "series":
        name = name or ("%s S01E05 - %s [DTS]" % (Ttemplate("show-name"), Ttemplate("ep-name")))
        sorter = SeriesSorter(None, name, path, "tv", force=True)
    elif sort_type == "movie":
        name = name or (Ttemplate("movie-sp-name") + " (2009)")
        sorter = MovieSorter(None, name, path, "tv", force=True)
    elif sort_type == "date":
        name = name or (Ttemplate("show-name") + " 2009-01-02")
        sorter = DateSorter(None, name, path, "tv", force=True)
    else:
        return None
    sorter.sort_string = expression
    path = os.path.normpath(os.path.join(sorter.get_final_path(), sorter.filename_set))
    fname = Ttemplate("orgFilename")
    fpath = path
    if sort_type == "movie" and "%1" in multipart:
        fname = fname + multipart.replace("%1", "1")
        fpath = fpath + multipart.replace("%1", "1")
    if "%fn" in path:
        path = path.replace("%fn", fname + ".ext")
    else:
        if sorter.rename_files:
            path = fpath + ".ext"
        else:
            path += "\\" if sabnzbd.WIN32 else "/"
    return path


def check_for_multiple(files: List[str]) -> Optional[Dict[str, str]]:
    """Return list of files that looks like a multi-part post"""
    RE_MULTIPLE = (
        re.compile(r"cd\W?(\d+)\W?", re.I),  # .cd1.mkv
        re.compile(r"\w\W?([\w\d])[{}]*$", re.I),  # blah1.mkv blaha.mkv
        re.compile(r"\w\W([\w\d])\W", re.I),  # blah-1-ok.mkv blah-a-ok.mkv
    )
    for regex in RE_MULTIPLE:
        matched_files = check_for_sequence(regex, files)
        if matched_files:
            return matched_files
    return None


def check_for_sequence(regex, files: List[str]) -> Dict[str, str]:
    """Return list of files that looks like a sequence"""
    matches = {}
    prefix = None
    # Build a dictionary of matches with keys based on the matches, e.g. {1:'blah-part1.mkv'}
    for _file in files:
        name, ext = os.path.splitext(_file)
        match1 = regex.search(name)
        if match1:
            if not prefix or prefix == name[: match1.start()]:
                matches[match1.group(1)] = name + ext
                prefix = name[: match1.start()]

    # Don't do anything if only one or no files matched
    if len(list(matches)) < 2:
        return {}

    key_prev = 0
    passed = True

    # Check the dictionary to see if the keys form an alphanumeric sequence
    for akey in sorted(matches):
        if akey.isdigit():
            key = int(akey)
        elif akey in ascii_lowercase:
            key = ascii_lowercase.find(akey) + 1
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

    return matches if passed else {}
