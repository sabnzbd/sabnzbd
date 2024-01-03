#!/usr/bin/python3 -OO
# Copyright 2007-2024 by The SABnzbd-Team (sabnzbd.org)
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
from string import whitespace, punctuation
from typing import Optional, Union, List, Tuple, Dict

import sabnzbd
from sabnzbd.filesystem import (
    move_to_path,
    cleanup_empty_directories,
    get_unique_filename,
    get_ext,
    globber,
    renamer,
    sanitize_foldername,
    clip_path,
)
import sabnzbd.config as config
import sabnzbd.cfg as cfg
from sabnzbd.constants import (
    EXCLUDED_GUESSIT_PROPERTIES,
    IGNORED_MOVIE_FOLDERS,
    GUESSIT_PART_INDICATORS,
    GUESSIT_SORT_TYPES,
)
from sabnzbd.misc import is_sample, from_units, sort_to_opts
from sabnzbd.nzbstuff import NzbObject, scan_password

# Do not rename .vob files as they are usually DVD's
EXCLUDED_FILE_EXTS = (".vob", ".bin")

LOWERCASE = ("the", "of", "and", "at", "vs", "a", "an", "but", "nor", "for", "on", "so", "yet", "with")
UPPERCASE = ("III", "II", "IV")

REPLACE_AFTER = {"()": "", "..": ".", "__": "_", "  ": " ", " .%ext": ".%ext"}

RE_GI = re.compile(r"(%G([._]?)I<(\w+)>)")  # %GI<property>, %G.I<property>, or %G_I<property>
RE_LOWERCASE = re.compile(r"{([^{]*)}")
RE_ENDEXT = re.compile(r"\.%ext}?$", re.I)
RE_ENDFN = re.compile(r"%fn}?$", re.I)

# Prevent guessit/rebulk from spamming the log when debug logging is active in SABnzbd
logging.getLogger("rebulk").setLevel(logging.WARNING)


class Sorter:
    """Generic Sorter class"""

    def __init__(
        self,
        nzo: Optional[NzbObject],
        job_name: str,
        path: Optional[str] = None,
        cat: Optional[str] = None,
        force: Optional[bool] = False,
        sorter_config: Optional[dict] = None,
    ):
        self.sorter_active = False
        self.original_job_name = job_name
        self.original_path = path
        self.nzo = nzo
        self.cat = cat
        self.sorter_config = sorter_config
        self.force = force
        self.filename_set = ""
        self.rename_files = False
        self.rename_limit = -1
        self.info = {}
        self.type = None  # tv, date, movie, unknown
        self.guess = None
        self.sort_string = None
        self.multipart_label = None
        self.is_season_pack = False
        self.season_pack_setname = ""

        self.match_sorters()

    def match_sorters(self):
        # If a sorter configuration is passed as an argument, only use that one
        sorters = [self.sorter_config] if self.sorter_config else config.get_ordered_sorters()

        # Figure out which sorter should be applied (if any)
        for sorter in sorters:
            # Check for category match (or forced)
            if self.force or (
                sorter["is_active"]
                and sorter["sort_string"]
                and sorter["sort_cats"]
                and self.cat
                and self.cat.lower() in [cat.lower() for cat in sorter["sort_cats"]]
            ):
                # Let guessit do its thing, and set the job type
                if not self.guess:
                    self.guess = guess_what(self.original_job_name)

                    # Set the detected job type
                    if self.guess["type"] == "episode":
                        self.type = "date" if self.guess.get("date") else "tv"
                    else:
                        self.type = self.guess["type"]  # movie, other

                # Check if the sorter should be applied to the guessed type (or forced)
                if (
                    not self.force
                    and sorter["sort_type"]
                    and not any(sort_to_opts(t) in sorter["sort_type"] for t in (self.type, "all"))
                ):
                    # Sorter is restricted to some other content type(s)
                    logging.debug(
                        "Guessed type %s of job %s doesn't match sorter %s (%s)",
                        self.type,
                        self.original_job_name,
                        sorter["name"],
                        ", ".join({GUESSIT_SORT_TYPES[t] for t in sorter["sort_type"]}),
                    )
                    # Move on to the next candidate
                    continue

                # Bingo!
                logging.debug(
                    "Matched sorter %s to job %s (forced: %s, custom: %s)",
                    sorter["name"],
                    self.original_job_name,
                    self.force,
                    bool(self.sorter_config),
                )
                self.sorter_active = True
                self.sort_string = sorter["sort_string"]
                self.multipart_label = sorter["multipart_label"]
                self.rename_limit = int(from_units(sorter["min_size"]))

                # Check for season pack indicators
                if (
                    self.type == "tv"
                    and cfg.enable_season_sorting()
                    and self.guess.get("season")
                    and not isinstance(self.guess.get("season"), list)  # No support for multi-season packs (yet)
                    and ((not self.guess.get("episode")) or isinstance(self.guess.get("episode"), list))
                ):
                    # The jobname indicates a season pack, i.e. guessit found a single season number but:
                    # either no episodes at all ("S01"), or multiple episodes ("S01E01-02-03")
                    self.is_season_pack = True
                    logging.debug("Activated season pack handling for job %s", self.original_job_name)

                # Don't consider any further sorters
                break
        else:
            logging.debug("No matching sorter found for job %s", self.original_job_name)

    def get_values(self):
        self.get_year()
        self.get_names()
        self.get_resolution()
        self.get_seasons()
        self.get_episodes()
        self.get_showdescriptions()
        self.get_date()

    def format_series_numbers(self, numbers: Union[int, List[int]], info_name: str):
        """Format the numbers in both plain and alternative (zero-padded) format and set as showinfo"""
        # Guessit returns multiple episodes or seasons as a list of integers, single values as int
        if isinstance(numbers, int):
            self.info[info_name] = str(numbers)  # 1
            self.info[info_name + "_alt"] = str(numbers).rjust(2, "0")  # 01
        else:
            self.info[info_name] = "-".join([str(num) for num in numbers])  # 1-2-3
            self.info[info_name + "_alt"] = "-".join([str(num).rjust(2, "0") for num in numbers])  # 01-02-03

    def get_date(self):
        """Get month and day"""
        self.info["month"] = self.info["day"] = self.info["month_two"] = self.info["day_two"] = ""

        try:
            self.info["month"] = str(self.guess.get("date").month)
            self.info["day"] = str(self.guess.get("date").day)
            # Zero-padded versions of the same
            if self.info["month"]:
                self.info["month_two"] = self.info["month"].rjust(2, "0")
            if self.info["day"]:
                self.info["day_two"] = self.info["day"].rjust(2, "0")
        except AttributeError:
            pass

    def get_episodes(self):
        """Fetch the guessed episode number(s)"""
        self.format_series_numbers(self.guess.get("episode", ""), "episode_num")

    def get_final_path(self) -> str:
        if self.sorter_active:
            # Construct the final path
            self.get_values()
            return os.path.join(self.original_path, self.construct_path())
        else:
            # No matching sorter found
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

    def get_seasons(self):
        """Fetch the guessed season number(s)"""
        self.format_series_numbers(self.guess.get("season", ""), "season_num")

    def get_showdescriptions(self):
        """Get the show descriptions based on metadata, guessit and jobname"""
        self.info["ep_name"], self.info["ep_name_two"], self.info["ep_name_three"] = get_descriptions(
            self.nzo, self.guess
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
                except Exception:
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

    def is_proper(self) -> bool:
        """Determine if the release is tagged 'Proper'. Note that guessit also sets this for similar
        tags such as 'Real' and 'Repack', saving us the trouble of checking for additional keywords."""
        if not self.guess:
            return False

        other = self.guess.get("other", "")
        if isinstance(other, list):
            return "Proper" in other
        else:
            return other == "Proper"

    def construct_path(self) -> str:
        """Map all markers and replace the sort string with real values"""
        sort_string = self.sort_string
        mapping = []

        if ends_in_file(sort_string):
            extension = True
            if sort_string.endswith(".%ext"):
                sort_string = sort_string[:-5]  # Strip '.%ext' off the end; other %ext may remain in sort_string
            if self.is_season_pack:
                # Create a record of the filename part of the sort_string
                _, self.season_pack_setname = os.path.split(sort_string)
                if not any(
                    substring in self.season_pack_setname
                    for substring in ("%e", "%0e", "%GI<episode>", "%G.I<episode>", "%G_I<episode>")
                ):
                    # Cancel season pack handling if the sort string for the filename lacks episode mapping
                    self.is_season_pack = False
                    logging.debug(
                        "Cancelled season pack handling for job %s: no episode mapper in season pack setname %s",
                        self.original_job_name,
                        self.season_pack_setname,
                    )
        else:
            extension = False
            if self.is_season_pack:
                self.is_season_pack = False
                logging.debug(
                    "Cancelled season pack handling for job %s: sort string %s does not rename files",
                    self.original_job_name,
                    sort_string,
                )

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

        # Episode name
        mapping.append(("%en", self.info["ep_name"]))
        mapping.append(("%e.n", self.info["ep_name_two"]))
        mapping.append(("%e_n", self.info["ep_name_three"]))

        # Legacy %desc
        if self.type == "date" and self.info.get("ep_name"):
            # For date, %desc was no longer listed but still supported in the backend. For tv,
            # it was invalid and %en (etc.) used instead. For backward compatibility, map %desc
            # to %en for 'date' only and remove for 'tv' and other types.
            mapping.append(("%desc", self.info["ep_name"]))
        else:
            mapping.append(("%desc", ""))

        # Season number
        mapping.append(("%s", self.info["season_num"]))
        mapping.append(("%0s", self.info["season_num_alt"]))

        # Month
        mapping.append(("%m", self.info["month"]))
        mapping.append(("%0m", self.info["month_two"]))

        # Day
        mapping.append(("%d", self.info["day"]))
        mapping.append(("%0d", self.info["day_two"]))

        # Handle generic guessit markers
        for marker, spacer, guess_property in re.findall(RE_GI, sort_string):
            # Keep the episode property around until after the season pack handling, same as %e and %0e
            if guess_property != "episode":
                value = self.guess.get(guess_property, "") if self.guess else ""
                # Guessit returns a list for some properties in case they have multiple entries/values
                if isinstance(value, list):
                    value = "-".join([str(v) for v in value])  # Format as value1-value2
                else:
                    value = str(value)
                if spacer:
                    value = value.replace(" ", spacer)
                mapping.append((marker, value))

        # Create a record of the season pack setname before the episode number markers are added to the mapping
        if self.is_season_pack:
            self.season_pack_setname = path_subst(self.season_pack_setname, mapping)
            for key, name in REPLACE_AFTER.items():
                self.season_pack_setname = self.season_pack_setname.replace(key, name)

        # Episode numbers; note these must come last (after both the %en variants and setting self.season_pack_setname)
        mapping.append(("%e", self.info["episode_num"]))
        mapping.append(("%0e", self.info["episode_num_alt"]))
        # Map the GI episode property to episode_num; their formatting is identical for every spacer option
        mapping.append(("%GI<episode>", self.info["episode_num"]))
        mapping.append(("%G.I<episode>", self.info["episode_num"]))
        mapping.append(("%G_I<episode>", self.info["episode_num"]))

        # Replace elements
        path = path_subst(sort_string, mapping)

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

        # Avoid turning the path absolute on *nix (e.g. sort_string '%r/...' with an empty mapping for %r)
        if path.startswith(os.path.sep) and not sort_string.startswith(os.path.sep):
            path = path.lstrip(os.path.sep)

        # The normpath function translates "" to "." which results in an incorrect path
        return os.path.normpath(path) if path else path

    def _rename_season_pack(self, files: List[str], base_path: str, all_job_files: List[str] = []) -> bool:
        success = False
        for f in files:
            f_name, f_ext = os.path.splitext(os.path.basename(f))
            if f_episode := guessit.api.guessit(f_name).get("episode"):
                # Insert formatted episode number(s) into self.info
                self.format_series_numbers(f_episode, "episode_num")

                # Build the new filename from self.season_pack_setname, filling in the remaining markers
                f_name_new = path_subst(
                    self.season_pack_setname,
                    [
                        ("%e", self.info["episode_num"]),
                        ("%GI<episode>", self.info["episode_num"]),
                        ("%G.I<episode>", self.info["episode_num"]),
                        ("%G_I<episode>", self.info["episode_num"]),
                        ("%0e", self.info["episode_num_alt"]),
                        ("%fn", f_name),
                        ("%ext", f_ext.lstrip(".")),
                    ],
                )
                f_new = to_lowercase(f_name_new + f_ext)

                try:
                    logging.debug("Renaming season pack file %s to %s", f, f_new)
                    renamer(self._to_filepath(f, base_path), self._to_filepath(f_new, base_path))
                    success = True
                except Exception:
                    logging.error("Failed to rename file %s to %s in season pack %s", f, f_new, self.original_job_name)
                    logging.info("Traceback: ", exc_info=True)
                    # Move on to the next file
                    continue

                # Rename similar files and move to base_path
                for sim_f in globber(base_path, f_name + "*"):
                    # Only take into consideration:
                    # * existing files (but not directories),
                    # * that were created as part of this job,
                    # * and didn't qualify for processing in the own right.
                    if os.path.isfile(os.path.join(base_path, sim_f)) and sim_f in all_job_files and sim_f not in files:
                        sim_f_new = os.path.basename(sim_f).replace(f_name, f_name_new, 1)
                        logging.debug("Renaming %s to %s (alongside season pack file %s)", sim_f, sim_f_new, f)
                        try:
                            renamer(self._to_filepath(sim_f, base_path), self._to_filepath(sim_f_new, base_path))
                        except Exception:
                            logging.error(
                                "Failed to rename similar file %s to %s (alongside %s in season pack %s)",
                                sim_f,
                                sim_f_new,
                                f,
                                self.original_job_name,
                            )
                            logging.info("Traceback: ", exc_info=True)
            else:
                logging.debug(
                    "Failed to get episode info from filename %s in season pack %s", f, self.original_job_name
                )
        return success

    def _rename_sequential(self, sequential_files: Dict[str, str], base_path: str) -> bool:
        success = False
        for index, f in sequential_files.items():
            filepath = self._to_filepath(f, base_path)
            f_name, f_ext = os.path.splitext(os.path.split(f)[1])
            new_filepath = os.path.join(
                base_path,
                to_lowercase(
                    path_subst(
                        self.filename_set + self.multipart_label,
                        [("%1", str(index)), ("%fn", f_name), ("%ext", f_ext.lstrip("."))],
                    )
                    + f_ext,
                ),
            )
            try:
                logging.debug("Renaming %s to %s", filepath, new_filepath)
                renamer(filepath, new_filepath)
                success = True
                rename_similar(base_path, f_ext, self.filename_set, [new_filepath])
            except Exception:
                logging.error(T("Failed to rename %s to %s"), clip_path(filepath), clip_path(new_filepath))
                logging.info("Traceback: ", exc_info=True)
        return success

    def _to_filepath(self, f: str, base_path: str) -> str:
        if not is_full_path(f):
            f = os.path.join(base_path, f)
        return os.path.normpath(f)

    def _filter_files(self, f: str, base_path: str) -> bool:
        filepath = self._to_filepath(f, base_path)
        return (
            not is_sample(f)
            and get_ext(f) not in EXCLUDED_FILE_EXTS
            and os.path.exists(filepath)
            and os.stat(filepath).st_size >= self.rename_limit
        )

    def rename(self, files: List[str], base_path: str) -> Tuple[str, bool]:
        if not self.rename_files:
            return move_to_parent_directory(base_path)

        # Log the minimum filesize for renaming
        if self.rename_limit > 0:
            logging.debug("Minimum filesize for renaming set to %s bytes", self.rename_limit)

        # Store the list of all files for later use
        all_files = files

        # Filter files to remove nonexistent, undersized, samples, and excluded extensions
        files = [f for f in files if self._filter_files(f, base_path)]

        if len(files) == 0:
            logging.debug("No files left to rename after applying filter")
            return move_to_parent_directory(base_path)

        # Check for season packs or sequential filenames and handle their renaming separately;
        # if neither applies or succeeds, fall back to going with the single largest file instead.
        if len(files) > 1:
            # Season packs handling
            if self.is_season_pack:
                logging.debug("Trying to rename season pack files %s", files)
                if self._rename_season_pack(files, base_path, all_files):
                    cleanup_empty_directories(base_path)
                    return move_to_parent_directory(base_path)
                else:
                    logging.debug("Season pack sorting didn´t rename any files")

            # Try generic sequential files handling
            if self.multipart_label and (sequential_files := check_for_multiple(files)):
                logging.debug("Trying to rename sequential files %s", sequential_files)
                if self._rename_sequential(sequential_files, base_path):
                    cleanup_empty_directories(base_path)
                    return move_to_parent_directory(base_path)
                else:
                    logging.debug("Sequential file handling didn't rename any files")

        # Find the largest file
        largest_file = {"name": None, "size": 0}
        for f in files:
            f_size = os.stat(self._to_filepath(f, base_path)).st_size
            if f_size > largest_file.get("size"):
                largest_file.update({"name": f, "size": f_size})

        # Rename it
        f_name, f_ext = os.path.splitext(largest_file.get("name"))
        filepath = self._to_filepath(largest_file.get("name"), base_path)
        new_filepath = os.path.join(
            base_path,
            to_lowercase(path_subst(self.filename_set, [("%fn", f_name), ("%ext", f_ext.lstrip("."))]) + f_ext),
        )
        if not os.path.exists(new_filepath):
            renamed_files = []
            try:
                logging.debug("Renaming %s to %s", filepath, new_filepath)
                renamer(filepath, new_filepath)
                renamed_files.append(new_filepath)
            except Exception:
                logging.error(T("Failed to rename %s to %s"), clip_path(base_path), clip_path(new_filepath))
                logging.info("Traceback: ", exc_info=True)

            rename_similar(base_path, f_ext, self.filename_set, renamed_files)
        else:
            logging.debug("Cannot rename %s, new path %s already exists.", largest_file.get("name"), new_filepath)

        return move_to_parent_directory(base_path)


class BasicAnalyzer(Sorter):
    def __init__(self, job_name: str):
        """Very basic sorter that doesn't require a config"""
        super().__init__(nzo=None, job_name=job_name)
        # Directly trigger setting all values
        self.get_values()

    def match_sorters(self):
        """Much more basic matching"""
        self.guess = guess_what(self.original_job_name)

        # Set the detected job type
        self.type = self.guess["type"]
        if self.guess["type"] == "episode":
            self.type = "date" if self.guess.get("date") else "tv"


def ends_in_file(path: str) -> bool:
    """Return True when path ends with '.%ext' or '%fn' while allowing for a lowercase marker"""
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


def guess_what(name: str) -> MatchesDict:
    """Guess metadata for movies or episodes from their name."""

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
    if guess.get("type") == "movie":
        if (
            guess.get("title", "").translate(table) == name.translate(table)  # Check for full name used as title
            or any(
                c in guess.get("release_group", "") for c in (whitespace + punctuation)
            )  # interpuction of white spaces in the groupname
            or not any(
                [key in guess for key in ("year", "screen_size", "video_codec")]
            )  # No typical movie properties set
            or (
                name.lower().startswith(("http://", "https://"))
                and name.lower().endswith(".nzb")
                and guess.get("container" == "nzb")
            )  # URL to an nzb file, can happen when pre-queue script rejects a job
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
    if matches := re.findall(r"\W(%s)(\W|$)" % one, word_input, re.I):
        for _ in matches:
            word_input = word_input.replace(one, two)
    return word_input


def get_descriptions(nzo: Optional[NzbObject], guess: Optional[MatchesDict]) -> Tuple[str, str, str]:
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
    try:
        if not is_unc and path.strip()[0] in "/":
            path_elements.insert(0, "")
    except IndexError:
        pass

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


def eval_sort(sort_string: str, job_name: str, multipart_label: str = "") -> Optional[str]:
    """Preview results for a given jobname and sort_string"""
    job_name = sanitize_foldername(job_name)
    if not job_name or not sort_string:
        return None

    # Fire up a dummy Sorter with settings and jobname from the preview
    sorter = Sorter(
        None,
        job_name,
        "",
        None,
        force=True,
        sorter_config={
            "name": "config__eval_sort",
            "order": 0,
            "min_size": -1,
            "multipart_label": multipart_label,
            "sort_string": sort_string,
            "sort_cats": [],  # Don't bother with categories or types, ignored with force=True
            "sort_type": [],
            "is_active": True,
        },
    )
    sorted_path = os.path.normpath(os.path.join(sorter.get_final_path(), sorter.filename_set))
    if not sorted_path:
        return None

    # Append a (placeholder) filename, multipart label, and extension or slash
    from sabnzbd.api import Ttemplate

    original_filename = Ttemplate("orgFilename")

    if "%fn" in sorted_path:
        sorted_path = sorted_path.replace("%fn", original_filename)
    if multipart_label:
        sorted_path = sorted_path.replace("%1", multipart_label.replace("%1", "1"))
    if sorter.rename_files:
        sorted_path += ".ext"
    else:
        sorted_path += "\\" if sabnzbd.WIN32 else "/"

    return sorted_path


def check_for_multiple(files: List[str]) -> Optional[Dict[str, str]]:
    """Return a dictionary of a single set of files that look like parts of
    a multi-part post. Takes a limited set of indicators from guessit into
    consideration and only accepts numerical sequences. The files argument
    is expected to be a list of basenames, not full paths."""
    candidates = {}
    wanted_title = None
    wanted_indicators = GUESSIT_PART_INDICATORS

    for f in files:
        # Add a prefix to make guessit hit on indicators at the start of filenames as well
        guess = guessit.api.guessit("PREFIX " + f)

        # Ignore filenames without part indicators
        if "title" in guess and any(key in guess for key in GUESSIT_PART_INDICATORS):
            # Create a record of the first title found
            if not wanted_title:
                wanted_title = guess["title"]

            # Take only files with a matching title into consideration
            if wanted_title == guess["title"]:
                for indicator in wanted_indicators:
                    if value := guess.get(indicator):
                        if isinstance(value, int) and value not in candidates.keys():
                            # Store the candidate
                            candidates[value] = f  # e.g. { int(1): str('filename part 1.txt') }
                            # Lock down the indicator, akin to the title
                            if len(wanted_indicators) > 1:
                                wanted_indicators = (indicator,)
                            break

    # Verify the candidates form a numerical sequence:
    if len(candidates) < 2 or sorted(candidates) != list(range(min(candidates), max(candidates) + 1)):
        return None
    else:
        # Return sequential files with the integer dictionary keys converted to strings
        return {str(key): value for key, value in candidates.items()}
