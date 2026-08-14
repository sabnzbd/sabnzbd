#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.config - Configuration Support
"""

import logging
import os
import re
import shutil
import threading
import time
import uuid
import io
import zipfile
from itertools import chain
from typing import Any, Callable, Optional, TypeAlias
from urllib.parse import urlparse

import configobj

import sabnzbd
from sabnzbd.constants import (
    CONFIG_VERSION,
    NORMAL_PRIORITY,
    DEFAULT_PRIORITY,
    CONFIG_BACKUP_FILES,
    CONFIG_BACKUP_HTTPS,
    DB_HISTORY_NAME,
    DEF_INI_FILE,
    DEF_SORTER_RENAME_SIZE,
    DEF_PIPELINING_REQUESTS,
    CONFIG_RESTORE_FILES,
)
from sabnzbd.decorators import synchronized
from sabnzbd.filesystem import clip_path, real_path, create_real_path, renamer, remove_file, is_writable

RE_PARAMFINDER = re.compile(r"""'.*?'|".*?"|[^'",\s][^,]*""")


class Option:
    """Basic option class, basic fields"""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: Any = None,
        add: bool = True,
        public: bool = True,
        protect: bool = False,
    ):
        """Basic option
        `section`     : single section for this option
        `keyword`     : keyword in the section
        `default_val` : value returned when no value has been set
        `callback`    : procedure to call when value is successfully changed
        `public`      : if this value should be shown in API calls
        `protect`     : do not allow setting via the API (specifically set_dict)
        """
        self.__section = section
        self.__keyword: str = keyword
        self.__default_val: Any = default_val
        self.__value: Any = None
        self.__callback: Optional[Callable] = None
        self.__public: bool = public
        self.__protect = protect

        # Add myself to the config dictionary
        if add:
            add_to_database(section, keyword, self)

    def get(self) -> Any:
        """Retrieve value field"""
        if self.__value is not None:
            return self.__value
        else:
            return self.__default_val

    def get_string(self) -> str:
        return str(self.get())

    def get_dict(self, for_public_api: bool = False) -> dict[str, Any]:
        """Return value as a dictionary.
        Will not show non-public options if needed for the API"""
        if not self.__public and for_public_api:
            return {}
        return {self.__keyword: self.get()}

    def set_dict(self, values: dict[str, Any]):
        """Set value based on dictionary"""
        if not self.__protect:
            try:
                self.set(values["value"])
            except KeyError:
                pass

    def get_from_dict(self, values: dict[str, Any], kw: str) -> Any:
        """Extract this option's value from a dict by key, raising KeyError if absent"""
        return values[kw]

    def set(self, value: Any):
        """Set new value, no validation"""
        if value is not None:
            # Use get() to make sure we use default if nothing was set yet
            if isinstance(value, list) or isinstance(value, dict) or value != self.get():
                self.__value = value
                CONFIG.modified = True
                if self.__callback:
                    self.__callback()

    @property
    def section(self) -> Any:
        return self.__section

    @property
    def keyword(self) -> Any:
        return self.__keyword

    @property
    def default(self) -> Any:
        return self.__default_val

    def callback(self, callback: Callable):
        """Set callback function"""
        self.__callback = callback

    def __call__(self) -> Any:
        """get() replacement"""
        return self.get()


class OptionNumber(Option):
    """Numeric option class, int/float is determined from default value."""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: float = 0,
        minval: Optional[float] = None,
        maxval: Optional[float] = None,
        validation: Optional[Callable] = None,
        add: bool = True,
        public: bool = True,
        protect: bool = False,
    ):
        self.__minval: Optional[float] = minval
        self.__maxval: Optional[float] = maxval
        self.__validation: Optional[Callable] = validation
        self.__int: bool = isinstance(default_val, int)
        super().__init__(section, keyword, default_val, add=add, public=public, protect=protect)

    def set(self, value: Any):
        """set new value, limited by range"""
        if value is not None:
            try:
                if self.__int:
                    value = int(value)
                else:
                    value = float(value)
            except ValueError:
                value = super().default
            if self.__validation:
                _, val = self.__validation(value)
                super().set(val)
            else:
                if self.__maxval is not None and value > self.__maxval:
                    value = self.__maxval
                elif self.__minval is not None and value < self.__minval:
                    value = self.__minval
                super().set(value)

    def __call__(self) -> int | float:
        """get() replacement"""
        return self.get()


class OptionBool(Option):
    """Boolean option class, always returns 0 or 1."""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: bool = False,
        add: bool = True,
        public: bool = True,
        protect: bool = False,
    ):
        super().__init__(section, keyword, int(default_val), add=add, public=public, protect=protect)

    def set(self, value: Any):
        # Store the value as integer, easier to parse when reading the config.
        super().set(sabnzbd.misc.bool_conv(value))

    def __call__(self) -> int:
        """Many places assume 0/1 is used for historical reasons.
        Using pure bools breaks in random places"""
        return int(self.get())


class OptionDir(Option):
    """Directory option class"""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: str = "",
        apply_permissions: bool = False,
        create: bool = True,
        validation: Optional[Callable] = None,
        writable: bool = True,
        add: bool = True,
        public: bool = True,
        protect: bool = False,
    ):
        self.__validation: Optional[Callable] = validation
        self.__root: str = ""  # Base directory for relative paths
        self.__apply_permissions: bool = apply_permissions
        self.__create: bool = create
        self.__writable: bool = writable
        super().__init__(section, keyword, default_val, add=add, public=public, protect=protect)

    def create_path(self, path: Optional[str] = None):
        if not path:
            path = self.get()
        return create_real_path(self.keyword, self.__root, path, self.__apply_permissions, self.__writable)

    def get(self) -> str:
        """Return value, corrected for platform"""
        p = super().get()
        if sabnzbd.WINDOWS:
            return p.replace("/", "\\") if "/" in p else p
        else:
            return p.replace("\\", "/") if "\\" in p else p

    def get_path(self) -> str:
        """Return full absolute path, create it if necessary"""
        path = ""
        if value := self.get():
            path = real_path(self.__root, value)
            if self.__create and not os.path.exists(path):
                _, path, _ = self.create_path(value)
        return path

    def get_clipped_path(self) -> str:
        """Return clipped full absolute path"""
        return clip_path(self.get_path())

    def test_path(self) -> bool:
        """Return True if path exists"""
        if value := self.get():
            return os.path.exists(real_path(self.__root, value))
        else:
            return False

    def set_root(self, root: str):
        """Set new root, is assumed to be valid"""
        self.__root = root

    def set(self, value: str, create: bool = False) -> Optional[str]:
        """Set new dir value, validate and create if needed
        Return None when directory is accepted
        Return error-string when not accepted, value will not be changed
        'create' means try to create (but don't set permanent create flag)
        """
        error = None
        if value is not None and (value != self.get() or create):
            value = value.strip()
            if self.__validation:
                error, value = self.__validation(self.__root, value, super().default)
            if not error:
                if value and (self.__create or create):
                    _success, _path, error = self.create_path(value)
            if not error:
                super().set(value)
        return error

    def set_create(self, value: bool):
        """Set auto-creation value"""
        self.__create = value

    def __call__(self) -> str:
        """get() replacement"""
        return self.get()


class OptionList(Option):
    """List option class"""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: str | list | None = None,
        validation: Optional[Callable] = None,
        add: bool = True,
        public: bool = True,
        protect: bool = False,
    ):
        self.__validation: Optional[Callable] = validation
        if default_val is None:
            default_val = []
        super().__init__(section, keyword, default_val, add=add, public=public, protect=protect)

    def set(self, value: str | list) -> Optional[str]:
        """Set the list given a comma-separated string or a list"""
        error = None
        if value is not None:
            if not isinstance(value, list):
                if '"' not in value and "," not in value:
                    value = value.split()
                else:
                    value = RE_PARAMFINDER.findall(value)
            if self.__validation:
                error, value = self.__validation(value)
            if not error:
                super().set(value)
        return error

    def get_from_dict(self, values: dict[str, Any], kw: str) -> Any:
        """Extract list value using getlist() for MultiDict sources, falling back to plain key access"""
        if hasattr(values, "getlist"):
            if lst := values.getlist(kw):
                return lst
            raise KeyError(kw)
        return values[kw]

    def get_string(self) -> str:
        """Return the list as a comma-separated string"""
        return ", ".join(self.get())

    def default_string(self) -> str:
        """Return the default list as a comma-separated string"""
        return ", ".join(self.default)

    def __call__(self) -> list[str]:
        """get() replacement"""
        return self.get()


class OptionStr(Option):
    """String class."""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: str = "",
        validation: Optional[Callable] = None,
        add: bool = True,
        strip: bool = True,
        public: bool = True,
        protect: bool = False,
    ):
        self.__validation: Optional[Callable] = validation
        self.__strip: bool = strip
        super().__init__(section, keyword, default_val, add=add, public=public, protect=protect)

    def get_float(self) -> float:
        """Return value converted to a float, allowing KMGT notation"""
        return sabnzbd.misc.from_units(self.get())

    def get_int(self) -> int:
        """Return value converted to an int, allowing KMGT notation"""
        return int(self.get_float())

    def set(self, value: Any) -> Optional[str]:
        """Set stripped value"""
        error = None
        if isinstance(value, str) and self.__strip:
            value = value.strip()
        if self.__validation:
            error, val = self.__validation(value)
            super().set(val)
        else:
            super().set(value)
        return error

    def __call__(self) -> str:
        """get() replacement"""
        return self.get()


class OptionPassword(Option):
    """Password class."""

    def __init__(self, section: str, keyword: str, default_val: str = "", add: bool = True):
        super().__init__(section, keyword, default_val, add=add)

    def get(self) -> Optional[str]:
        """Return decoded password"""
        return decode_password(super().get(), self.keyword)

    def get_string(self) -> str:
        """Passwords are shown masked"""
        return self.get_stars()

    def get_stars(self) -> str:
        """Return non-descript asterisk string"""
        if self.get():
            return "*" * 10
        return ""

    def get_dict(self, for_public_api: bool = False) -> dict[str, str]:
        """Return value a dictionary"""
        if for_public_api:
            return {self.keyword: self.get_stars()}
        else:
            return {self.keyword: self.get()}

    def set(self, pw: str):
        """Set password, encode it"""
        if (pw is not None and pw == "") or (pw and pw.strip("*")):
            super().set(encode_password(pw))

    def __call__(self) -> str:
        """get() replacement"""
        return self.get()


class ConfigServer:
    """Class defining a single server"""

    def __init__(self, name, values):
        self.__name = clean_section_name(name)
        name = "servers," + self.__name

        self.displayname = OptionStr(name, "displayname", add=False)
        self.host = OptionStr(name, "host", validation=sabnzbd.cfg.all_lowercase, add=False)
        self.port = OptionNumber(name, "port", 119, 0, 2**16 - 1, add=False)
        self.timeout = OptionNumber(name, "timeout", 60, 20, 240, add=False)
        self.username = OptionStr(name, "username", add=False)
        self.password = OptionPassword(name, "password", add=False)
        self.connections = OptionNumber(name, "connections", 1, 0, 500, add=False)
        self.ssl = OptionBool(name, "ssl", False, add=False)
        # 0=No, 1=Minimal, 2=Medium, 3=Strict
        self.ssl_verify = OptionNumber(name, "ssl_verify", 3, add=False)
        self.ssl_ciphers = OptionStr(name, "ssl_ciphers", add=False)
        self.enable = OptionBool(name, "enable", True, add=False)
        self.required = OptionBool(name, "required", False, add=False)
        self.optional = OptionBool(name, "optional", False, add=False)
        self.pipelining_requests = OptionNumber(name, "pipelining_requests", DEF_PIPELINING_REQUESTS, 1, 20, add=False)
        self.retention = OptionNumber(name, "retention", 0, add=False)
        self.expire_date = OptionStr(name, "expire_date", add=False)
        self.quota = OptionStr(name, "quota", add=False)
        self.usage_at_start = OptionNumber(name, "usage_at_start", add=False)
        self.priority = OptionNumber(name, "priority", 0, 0, 99, add=False)
        self.notes = OptionStr(name, "notes", add=False)

        self.set_dict(values)
        add_to_database("servers", self.__name, self)

    def set_dict(self, values: dict[str, Any]):
        """Set one or more fields, passed as dictionary"""
        # Replace usage_at_start value with most recent statistics if the user changes the quota value
        # Only when we are updating it from the Config
        if sabnzbd.WEBUI_READY and values.get("quota", "") != self.quota():
            values["usage_at_start"] = sabnzbd.BPSMeter.grand_total.get(self.__name, 0)

        # Store all values
        for kw in (
            "displayname",
            "host",
            "port",
            "timeout",
            "username",
            "password",
            "connections",
            "ssl",
            "ssl_verify",
            "ssl_ciphers",
            "enable",
            "required",
            "optional",
            "pipelining_requests",
            "retention",
            "expire_date",
            "quota",
            "usage_at_start",
            "priority",
            "notes",
        ):
            try:
                attr = getattr(self, kw)
                attr.set(attr.get_from_dict(values, kw))
            except KeyError:
                continue
        if not self.displayname():
            self.displayname.set(self.__name)

    def get_dict(self, for_public_api: bool = False) -> dict[str, Any]:
        """Return a dictionary with all attributes"""
        output_dict = {}
        output_dict["name"] = self.__name
        output_dict["displayname"] = self.displayname()
        output_dict["host"] = self.host()
        output_dict["port"] = self.port()
        output_dict["timeout"] = self.timeout()
        output_dict["username"] = self.username()
        if for_public_api:
            output_dict["password"] = self.password.get_stars()
        else:
            output_dict["password"] = self.password()
        output_dict["connections"] = self.connections()
        output_dict["ssl"] = self.ssl()
        output_dict["ssl_verify"] = self.ssl_verify()
        output_dict["ssl_ciphers"] = self.ssl_ciphers()
        output_dict["enable"] = self.enable()
        output_dict["required"] = self.required()
        output_dict["optional"] = self.optional()
        output_dict["pipelining_requests"] = self.pipelining_requests()
        output_dict["retention"] = self.retention()
        output_dict["expire_date"] = self.expire_date()
        output_dict["quota"] = self.quota()
        output_dict["usage_at_start"] = self.usage_at_start()
        output_dict["priority"] = self.priority()
        output_dict["notes"] = self.notes()
        return output_dict

    def delete(self):
        """Remove from database"""
        delete_from_database("servers", self.__name)

    def rename(self, name: str):
        """Give server new display name"""
        self.displayname.set(name)


class ConfigCat:
    """Class defining a single category"""

    def __init__(self, name: str, values: dict[str, Any]):
        self.__name = clean_section_name(name)
        name = "categories," + self.__name

        self.order = OptionNumber(name, "order", 0, 0, 100, add=False)
        self.pp = OptionStr(name, "pp", add=False)
        self.script = OptionStr(name, "script", "Default", add=False)
        self.dir = OptionDir(name, "dir", add=False, create=False)
        self.newzbin = OptionList(name, "newzbin", add=False, validation=sabnzbd.cfg.validate_single_tag)
        self.priority = OptionNumber(name, "priority", DEFAULT_PRIORITY, add=False)

        self.set_dict(values)
        add_to_database("categories", self.__name, self)

    def set_dict(self, values: dict[str, Any]):
        """Set one or more fields, passed as dictionary"""
        for kw in ("order", "pp", "script", "dir", "newzbin", "priority"):
            try:
                attr = getattr(self, kw)
                attr.set(attr.get_from_dict(values, kw))
            except KeyError:
                continue

    def get_dict(self, for_public_api: bool = False) -> dict[str, Any]:
        """Return a dictionary with all attributes"""
        output_dict = {}
        output_dict["name"] = self.__name
        output_dict["order"] = self.order()
        output_dict["pp"] = self.pp()
        output_dict["script"] = self.script()
        output_dict["dir"] = self.dir()
        output_dict["newzbin"] = self.newzbin.get_string()
        output_dict["priority"] = self.priority()
        return output_dict

    def delete(self):
        """Remove from database"""
        delete_from_database("categories", self.__name)


class ConfigSorter:
    """Class defining a single Sorter"""

    def __init__(self, name, values):
        self.__name = clean_section_name(name)
        name = "sorters," + self.__name

        self.order = OptionNumber(name, "order", len(get_sorters()), 0, 100, add=False)
        self.min_size = OptionStr(name, "min_size", DEF_SORTER_RENAME_SIZE, add=False)
        self.multipart_label = OptionStr(name, "multipart_label", add=False)
        self.sort_string = OptionStr(name, "sort_string", add=False)
        self.sort_cats = OptionList(name, "sort_cats", add=False)
        self.sort_type = OptionList(name, "sort_type", add=False)
        self.is_active = OptionBool(name, "is_active", add=False)

        self.set_dict(values)
        add_to_database("sorters", self.__name, self)

    def set_dict(self, values: dict[str, Any]):
        """Set one or more fields, passed as dictionary"""
        for kw in ("order", "min_size", "multipart_label", "sort_string", "sort_cats", "sort_type", "is_active"):
            try:
                attr = getattr(self, kw)
                attr.set(attr.get_from_dict(values, kw))
            except KeyError:
                continue

    def get_dict(self, for_public_api: bool = False) -> dict[str, Any]:
        """Return a dictionary with all attributes"""
        output_dict = {}
        output_dict["name"] = self.__name
        output_dict["order"] = self.order()
        output_dict["min_size"] = self.min_size()
        output_dict["multipart_label"] = self.multipart_label()
        output_dict["sort_string"] = self.sort_string()
        output_dict["sort_cats"] = self.sort_cats()
        output_dict["sort_type"] = [int(num) for num in self.sort_type()]
        output_dict["is_active"] = self.is_active()
        return output_dict

    def delete(self):
        """Remove from database"""
        delete_from_database("sorters", self.__name)

    def rename(self, new_name: str):
        """Update the name and the saved entries"""
        delete_from_database("sorters", self.__name)
        self.__name = new_name
        add_to_database("sorters", self.__name, self)


class OptionFilters(Option):
    """Filter list class"""

    def __init__(self, section, keyword, add=True):
        super().__init__(section, keyword, add=add)
        self.set([])

    def move(self, current: int, new: int):
        """Move filter from position 'current' to 'new'"""
        lst = self.get()
        try:
            item = lst.pop(current)
            lst.insert(new, item)
        except IndexError:
            return
        self.set(lst)

    def update(self, pos: int, value: tuple):
        """Update filter 'pos' definition, value is a list
        Append if 'pos' outside list
        """
        lst = self.get()
        try:
            lst[pos] = value
        except IndexError:
            lst.append(value)
        self.set(lst)

    def delete(self, pos: int):
        """Remove filter 'pos'"""
        lst = self.get()
        try:
            lst.pop(pos)
        except IndexError:
            return
        self.set(lst)

    def get_dict(self, for_public_api: bool = False) -> dict[str, str]:
        """Return filter list as a dictionary with keys 'filter[0-9]+'"""
        output_dict = {}
        for n, rss_filter in enumerate(self.get()):
            output_dict[f"filter{n}"] = rss_filter
        return output_dict

    def set_dict(self, values: dict[str, Any]):
        """Create filter list from dictionary with keys 'filter[0-9]+'"""
        filters = []
        # We don't know how many filters there are, so just assume all values are filters
        for n in range(len(values)):
            kw = f"filter{n}"
            if kw in values:
                filters.append(values[kw])
        if filters:
            self.set(filters)

    def __call__(self) -> list[list[str]]:
        """get() replacement"""
        return self.get()


class ConfigRSS:
    """Class defining a single Feed definition"""

    def __init__(self, name, values):
        self.__name = clean_section_name(name)
        name = "rss," + self.__name

        self.uri = OptionList(name, "uri", add=False)
        self.cat = OptionStr(name, "cat", add=False)
        self.pp = OptionStr(name, "pp", add=False)
        self.script = OptionStr(name, "script", add=False)
        self.enable = OptionBool(name, "enable", add=False)
        self.priority = OptionNumber(name, "priority", DEFAULT_PRIORITY, DEFAULT_PRIORITY, 2, add=False)
        self.filters = OptionFilters(name, "filters", add=False)
        self.filters.set([["", "", "", "A", "*", DEFAULT_PRIORITY, "1"]])

        self.set_dict(values)
        add_to_database("rss", self.__name, self)

    def set_dict(self, values: dict[str, Any]):
        """Set one or more fields, passed as dictionary"""
        for kw in ("uri", "cat", "pp", "script", "priority", "enable"):
            try:
                attr = getattr(self, kw)
                attr.set(attr.get_from_dict(values, kw))
            except KeyError:
                continue
        self.filters.set_dict(values)

    def get_dict(self, for_public_api: bool = False) -> dict[str, Any]:
        """Return a dictionary with all attributes"""
        output_dict = {}
        output_dict["name"] = self.__name
        output_dict["uri"] = self.uri()
        output_dict["cat"] = self.cat()
        output_dict["pp"] = self.pp()
        output_dict["script"] = self.script()
        output_dict["enable"] = self.enable()
        output_dict["priority"] = self.priority()
        filters = self.filters.get_dict()
        for kw in filters:
            output_dict[kw] = filters[kw]
        return output_dict

    def delete(self):
        """Remove from database"""
        delete_from_database("rss", self.__name)

    def rename(self, new_name: str) -> str:
        """Update the name and the saved entries"""
        # Sanitize the name before using it
        new_name = clean_section_name(new_name)
        delete_from_database("rss", self.__name)
        with sabnzbd.rss.rss_repository() as repo:
            repo.rename(self.__name, new_name)
        self.__name = new_name
        add_to_database("rss", self.__name, self)
        return self.__name


# Add typing to the options database-dict
AllConfigTypes: TypeAlias = Option | ConfigCat | ConfigSorter | ConfigRSS | ConfigServer


class SABnzbdConfig(configobj.ConfigObj):
    """The parsed INI structure (this object) plus SABnzbd's option database and dirty flag.

    Subclassing ConfigObj means the object *is* the INI structure, so it can be accessed
    directly (CONFIG["misc"], CONFIG.filename, CONFIG.write()). The extra state and the
    config-management behaviour that operates on it live here as methods. A single instance
    is held in the module-global CONFIG; tests get a clean slate by replacing that instance.
    """

    # INI sections that hold multiple named sub-sections, each backed by a Config* class.
    # Single source of truth for the "special" sections handled differently from flat options.
    SPECIAL_SECTIONS: dict[str, type] = {
        "categories": ConfigCat,
        "rss": ConfigRSS,
        "servers": ConfigServer,
        "sorters": ConfigSorter,
    }

    def __init__(self, *args, **kwargs):
        # SABnzbd always reads and writes the INI as UTF-8
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("default_encoding", "utf-8")
        super().__init__(*args, **kwargs)
        # Single lock guarding all config access. The @synchronized() methods below
        # lock on it; the module-level wrapper functions stay lock-free.
        self.lock = threading.RLock()
        # Holds all the Option/Config* objects, keyed by section and keyword
        self.database: dict[str, dict[str, AllConfigTypes]] = {}
        # Signals a change in the option database, reset after saving to the settings file
        self.modified: bool = False

    @synchronized()
    def add_to_database(self, section: str, keyword: str, obj: AllConfigTypes):
        """add object as section/keyword to INI database"""
        if section not in self.database:
            self.database[section] = {}
        self.database[section][keyword] = obj

    @synchronized()
    def delete_from_database(self, section: str, keyword: str):
        """Remove section/keyword from INI database"""
        del self.database[section][keyword]
        try:
            del self[section][keyword]
        except KeyError:
            pass
        self.modified = True

    @synchronized()
    def read_config(self, path: str, try_backup: bool = False) -> tuple[bool, str]:
        """Read the complete INI file and check its version number.
        If OK, re-parse it into this object in place (keeping the registered
        option database) and pass the values to the config-database.
        """
        if try_backup or not os.path.exists(path):
            # Not found, try backup
            try:
                shutil.copyfile(path + ".bak", path)
                try_backup = True
            except IOError:
                pass

        if not os.path.exists(path):
            # No file found, create default INI file
            try:
                if not sabnzbd.WINDOWS:
                    prev = os.umask(0o77)
                with open(path, "w") as fp:
                    fp.write("__version__=%s\n[misc]\n[logging]\n" % CONFIG_VERSION)
                if not sabnzbd.WINDOWS:
                    os.umask(prev)
            except IOError:
                return False, "Cannot create INI file %s" % path

        # Validate the file parses before touching our own state, so a corrupt file
        # leaves the current config (and filename) intact instead of being destroyed
        # by reload() clearing us first.
        try:
            configobj.ConfigObj(infile=path, default_encoding="utf-8", encoding="utf-8")
        except (IOError, configobj.ConfigObjError, UnicodeEncodeError) as strerror:
            if try_backup:
                # No luck!
                return False, '"%s" is not a valid configuration file<br>Error message: %s' % (path, strerror)
            else:
                # Try backup file
                return self.read_config(path, True)

        # The file parses, so re-parse it into this object in place, keeping our
        # database/lock/modified state (reload() only touches the INI structure)
        self.filename = path
        self.reload()

        try:
            version = sabnzbd.misc.int_conv(self["__version__"])
            if version > int(CONFIG_VERSION):
                return False, "Incorrect version number %s in %s" % (version, path)
        except (KeyError, ValueError):
            pass

        self["__encoding__"] = "utf-8"
        self["__version__"] = str(CONFIG_VERSION)

        # Use CFG data to set values for all static options
        for section in self.database:
            if section not in self.SPECIAL_SECTIONS:
                for option in self.database[section]:
                    config_option = self.database[section][option]
                    try:
                        config_option.set(self[config_option.section][config_option.keyword])
                    except KeyError:
                        pass

        # Rebuild the special sections from scratch, each backed by its own Config* class.
        # Clearing first drops entries from a previous read (e.g. restoring a backup) so
        # they don't linger in the database and get written back.
        for special_section, section_class in self.SPECIAL_SECTIONS.items():
            if special_section in self.database:
                self.database[special_section].clear()
            if special_section in self:
                for name in self[special_section]:
                    section_class(name, self[special_section][name])

        self.modified = False
        return True, ""

    @synchronized()
    def save_config(self, force: bool = False) -> bool:
        """Update Setup file with current option values"""
        if not (self.modified or force):
            return True

        if not self.filename:
            # Nothing has been read yet, so there is no INI file to write to
            logging.error("Cannot save settings, no INI file has been read yet")
            return False

        if sabnzbd.cfg.configlock():
            logging.warning(T("Configuration locked, cannot save settings"))
            return False

        for section in self.database:
            if section in self.SPECIAL_SECTIONS:
                if section not in self:
                    self[section] = {}

                for subsection in self.database[section]:
                    if subsection not in self[section]:
                        self[section][subsection] = {}
                    self[section][subsection] = self.database[section][subsection].get_dict()
            else:
                for option in self.database[section]:
                    config_option = self.database[section][option]
                    if config_option.section not in self:
                        self[config_option.section] = {}
                    self[config_option.section][config_option.keyword] = self.database[section][option]()

        res = False
        filename = self.filename
        bakname = filename + ".bak"

        # Check if file is writable
        if not is_writable(filename):
            logging.error(T("Cannot write to INI file %s"), filename)
            return res

        # copy current file to backup
        try:
            shutil.copyfile(filename, bakname)
            shutil.copymode(filename, bakname)
        except Exception:
            # Something wrong with the backup,
            logging.error(T("Cannot create backup file for %s"), bakname)
            logging.info("Traceback: ", exc_info=True)
            return res

        # Write new config file
        try:
            logging.info("Writing settings to INI file %s", filename)
            self.write()
            shutil.copymode(bakname, filename)
            self.modified = False
            res = True
        except Exception:
            logging.error(T("Cannot write to INI file %s"), filename)
            logging.info("Traceback: ", exc_info=True)
            try:
                remove_file(filename)
            except Exception:
                pass
            # Restore INI file from backup
            renamer(bakname, filename)

        return res

    def create_config_backup(self) -> str | bool:
        """Put config data in a zip file, returns path on success"""
        admin_path = sabnzbd.cfg.admin_dir.get_path()
        output_filename = "sabnzbd_backup_%s_%s.zip" % (sabnzbd.__version__, time.strftime("%Y.%m.%d_%H.%M.%S"))

        # Check if there is a backup folder set, use complete otherwise
        if sabnzbd.cfg.backup_dir():
            backup_dir = sabnzbd.cfg.backup_dir.get_path()
        else:
            backup_dir = sabnzbd.cfg.complete_dir.get_path()
        complete_path = os.path.join(backup_dir, output_filename)
        logging.debug("Backing up %s + %s in %s", admin_path, self.filename, complete_path)

        try:
            with open(complete_path, "wb") as zip_buffer:
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_ref:
                    for filename in CONFIG_BACKUP_FILES:
                        full_path = os.path.join(admin_path, filename)
                        if not os.path.isfile(full_path):
                            continue
                        # A raw copy of the live database file misses un-checkpointed WAL
                        # transactions and can be inconsistent while SABnzbd runs, so take
                        # a snapshot through SQLite's online backup instead. Fall back to
                        # a plain file copy if the snapshot fails.
                        if filename == DB_HISTORY_NAME and (snapshot := sabnzbd.database.history_db_snapshot()):
                            zip_ref.writestr(filename, snapshot)
                        else:
                            with open(full_path, "rb") as data:
                                zip_ref.writestr(filename, data.read())
                    for filename, setting in CONFIG_BACKUP_HTTPS.items():
                        full_path = getattr(sabnzbd.cfg, setting).get_path()
                        # Only accept HTTPS config files that were successfully loaded by cherrypy on
                        # startup to protect against last-minute breaking config changes as well as
                        # inclusion of unrelated files in the backup through manipulated settings.
                        if full_path and os.path.isfile(full_path) and full_path in sabnzbd.CONFIG_BACKUP_HTTPS_OK:
                            logging.debug("Adding %s file %s to backup", setting, full_path)
                            with open(full_path, "rb") as data:
                                # Add the https cert/key/chain files with a fixed relative filename,
                                # regardless of where they are actually stored on the filesystem
                                zip_ref.writestr(filename, data.read())
                    with open(self.filename, "rb") as data:
                        zip_ref.writestr(DEF_INI_FILE, data.read())
            return clip_path(complete_path)
        except Exception:
            logging.info("Failed to create backup: ", exc_info=True)
            return False

    @staticmethod
    def validate_config_backup(config_backup_data: bytes) -> bool:
        """Check that the zip file contains a sabnzbd.ini"""
        try:
            with io.BytesIO(config_backup_data) as backup_ref:
                with zipfile.ZipFile(backup_ref, "r") as zip_ref:
                    # Will throw KeyError if not present
                    zip_ref.getinfo(DEF_INI_FILE)
                    return True
        except Exception:
            return False

    @synchronized()
    def restore_config_backup(self, config_backup_data: bytes):
        """Restore configuration files from zip file"""
        try:
            with io.BytesIO(config_backup_data) as backup_ref:
                with zipfile.ZipFile(backup_ref, "r") as zip_ref:
                    # Write config file first and read it
                    logging.debug("Writing backup of config-file to %s", self.filename)
                    with open(self.filename, "wb") as destination_ref:
                        destination_ref.write(zip_ref.read(DEF_INI_FILE))
                    logging.debug("Loading settings from backup config-file")
                    loaded, error = self.read_config(self.filename)
                    if not loaded:
                        # A corrupt backup left the current config intact; don't persist over it
                        logging.warning(T("Could not restore backup"))
                        logging.info("Restoring backup failed: %s", error)
                        return

                    # Write the rest of the admin files that we want to recover
                    adminpath = sabnzbd.cfg.admin_dir.get_path()
                    for filename in chain(CONFIG_BACKUP_FILES, CONFIG_RESTORE_FILES, CONFIG_BACKUP_HTTPS.keys()):
                        try:
                            zip_ref.getinfo(filename)
                            destination_file = os.path.join(adminpath, filename)
                            logging.debug("Writing backup of %s to %s", filename, destination_file)
                            with open(destination_file, "wb") as destination_ref:
                                destination_ref.write(zip_ref.read(filename))
                            if filename == DB_HISTORY_NAME:
                                # Remove any stale WAL sidecar files left by the replaced
                                # database, so SQLite cannot try to recover the restored
                                # database with the old write-ahead log
                                for sidecar in (destination_file + "-wal", destination_file + "-shm"):
                                    if os.path.isfile(sidecar):
                                        logging.debug("Removing stale database sidecar %s", sidecar)
                                        remove_file(sidecar)
                            # For HTTPS config files, point the associated setting to the restored file
                            if setting := CONFIG_BACKUP_HTTPS.get(filename):
                                logging.debug("Setting value of %s to restored file %s", setting, filename)
                                getattr(sabnzbd.cfg, setting).set(filename)
                                self.modified = True
                        except KeyError:
                            # File not in archive
                            pass
                    self.save_config()
        except Exception:
            logging.warning(T("Could not restore backup"))
            logging.info("Traceback: ", exc_info=True)

    @synchronized()
    def get_dconfig(self, section: str, keyword: Optional[str], nested: bool = False) -> dict:
        """Return a config values dictionary,
        Single item or slices based on 'section', 'keyword'
        """
        data = {}
        if not section:
            for section in self.database.keys():
                conf = self.get_dconfig(section, None, True)
                data.update(conf)

        elif not keyword:
            try:
                sect = self.database[section]
            except KeyError:
                return {}

            if section == "categories":
                data[section] = get_ordered_categories()
            elif section == "sorters":
                data[section] = get_ordered_sorters()
            elif section in self.SPECIAL_SECTIONS.keys() - {"categories", "sorters"}:
                # The remaining special sections (servers, rss) serialize as a list
                data[section] = []
                for keyword in sect.keys():
                    conf = self.get_dconfig(section, keyword, True)
                    data[section].append(conf)
            else:
                data[section] = {}
                for keyword in sect.keys():
                    conf = self.get_dconfig(section, keyword, True)
                    data[section].update(conf)

        else:
            try:
                item = self.database[section][keyword]
            except KeyError:
                return {}
            data = item.get_dict(for_public_api=True)
            if not nested:
                if section in self.SPECIAL_SECTIONS:
                    data = {section: [data]}
                else:
                    data = {section: data}

        return data

    @synchronized()
    def get_config(self, section: str, keyword: str) -> Optional[AllConfigTypes]:
        """Return a config object, based on 'section', 'keyword'"""
        try:
            return self.database[section][keyword]
        except KeyError:
            logging.debug("Missing configuration item %s,%s", section, keyword)
            return None

    @synchronized()
    def set_config(self, kwargs) -> bool:
        """Set a config item, using values in dictionary"""
        try:
            item = self.database[kwargs.get("section")][kwargs.get("keyword")]
        except KeyError:
            return False
        item.set_dict(kwargs)
        return True

    @synchronized()
    def delete_config(self, section: str, keyword: str):
        """Delete specific config item"""
        try:
            self.database[section][keyword].delete()
        except KeyError:
            return

    @synchronized()
    def get_servers(self) -> dict[str, ConfigServer]:
        try:
            return self.database["servers"]
        except KeyError:
            return {}

    @synchronized()
    def get_sorters(self) -> dict[str, ConfigSorter]:
        try:
            return self.database["sorters"]
        except KeyError:
            return {}

    @synchronized()
    def get_categories(self) -> dict[str, ConfigCat]:
        """Return link to categories section.
        This section will always contain special category '*'
        """
        if "categories" not in self.database:
            self.database["categories"] = {}
        cats = self.database["categories"]

        # Add Default categories
        if "*" not in cats:
            ConfigCat("*", {"order": 0, "pp": "3", "script": "None", "priority": NORMAL_PRIORITY})
            # Add some category suggestions
            ConfigCat("movies", {"order": 1})
            ConfigCat("tv", {"order": 2})
            ConfigCat("audio", {"order": 3})
            ConfigCat("software", {"order": 4})

            # Save config for future use
            save_config(True)
        return cats

    @synchronized()
    def get_rss(self) -> dict[str, ConfigRSS]:
        try:
            # We have to remove non-separator commas by detecting if they are valid URL's
            for feed_key in self.database["rss"]:
                feed = self.database["rss"][feed_key]
                # Only modify if we have to, to prevent repeated config-saving
                have_new_uri = False
                # Create a new corrected list
                new_feed_uris = []
                for feed_uri in feed.uri():
                    if new_feed_uris and not urlparse(feed_uri).scheme and urlparse(new_feed_uris[-1]).scheme:
                        # Current one has no scheme but previous one does, append to previous
                        new_feed_uris[-1] += "," + feed_uri
                        have_new_uri = True
                        continue
                    # Add full working URL
                    new_feed_uris.append(feed_uri)
                # Set new list
                if have_new_uri:
                    feed.uri.set(new_feed_uris)

            return self.database["rss"]
        except KeyError:
            return {}


# Holds INI structure, option database and dirty flag; always a real instance
CONFIG = SABnzbdConfig()


def add_to_database(section: str, keyword: str, obj: AllConfigTypes):
    """add object as section/keyword to INI database"""
    CONFIG.add_to_database(section, keyword, obj)


def delete_from_database(section, keyword):
    """Remove section/keyword from INI database"""
    CONFIG.delete_from_database(section, keyword)


def get_dconfig(section: str, keyword: Optional[str], nested: bool = False) -> dict:
    """Return a config values dictionary,
    Single item or slices based on 'section', 'keyword'
    """
    return CONFIG.get_dconfig(section, keyword, nested)


def get_config(section: str, keyword: str) -> Optional[AllConfigTypes]:
    """Return a config object, based on 'section', 'keyword'"""
    return CONFIG.get_config(section, keyword)


def set_config(kwargs) -> bool:
    """Set a config item, using values in dictionary"""
    return CONFIG.set_config(kwargs)


def delete(section: str, keyword: str):
    """Delete specific config item"""
    CONFIG.delete_config(section, keyword)


def read_config(path):
    """Read the complete INI file and check its version number
    if OK, pass values to config-database
    """
    return CONFIG.read_config(path)


def save_config(force=False):
    """Update Setup file with current option values"""
    return CONFIG.save_config(force)


def create_config_backup() -> str | bool:
    """Put config data in a zip file, returns path on success"""
    return CONFIG.create_config_backup()


def validate_config_backup(config_backup_data: bytes) -> bool:
    """Check that the zip file contains a sabnzbd.ini"""
    return CONFIG.validate_config_backup(config_backup_data)


def restore_config_backup(config_backup_data: bytes):
    """Restore configuration files from zip file"""
    CONFIG.restore_config_backup(config_backup_data)


def get_servers() -> dict[str, ConfigServer]:
    return CONFIG.get_servers()


def get_sorters() -> dict[str, ConfigSorter]:
    return CONFIG.get_sorters()


def get_ordered_sorters() -> list[dict]:
    """Return sorters as an ordered list"""
    database_sorters = get_sorters()

    sorters = [database_sorters[sorter].get_dict() for sorter in database_sorters.keys()]
    sorters.sort(key=lambda sorter: sorter["order"])

    return sorters


def get_categories() -> dict[str, ConfigCat]:
    """Return link to categories section.
    This section will always contain special category '*'
    """
    return CONFIG.get_categories()


def get_category(cat: str = "*") -> ConfigCat:
    """Get one specific category or if not found the default one"""
    cats = get_categories()
    try:
        return cats[cat]
    except KeyError:
        return cats["*"]


def get_ordered_categories() -> list[dict]:
    """Return list-copy of categories section that's ordered
    by user's ordering including Default-category
    """
    database_cats = get_categories()

    # Transform to list and sort
    categories = []
    for cat in database_cats.keys():
        if cat != "*":
            categories.append(database_cats[cat].get_dict())

    # Sort and add default * category
    categories.sort(key=lambda cat: cat["order"])
    categories.insert(0, database_cats["*"].get_dict())

    return categories


def get_rss() -> dict[str, ConfigRSS]:
    return CONFIG.get_rss()


def get_filename():
    return CONFIG.filename


def clean_section_name(section: str) -> str:
    """Make a section name suitable to be used in the INI,
    since it can't have starting "[" or a trailing "]".
    Unfortuantly, ConfigObj doesn't do this for us."""
    new_section_name = section.strip("[]")
    if not new_section_name:
        raise ValueError("Invalid section name %s, nothing left after cleaning" % section)
    return new_section_name


__PW_PREFIX = "!!!encoded!!!"


def encode_password(pw):
    """Encode password in hexadecimal if needed"""
    enc = False
    if pw:
        encPW = __PW_PREFIX
        for c in pw:
            cnum = ord(c)
            if c == "#" or cnum < 33 or cnum > 126:
                enc = True
            encPW += "%2x" % cnum
        if enc:
            return encPW
    return pw


def decode_password(pw: str, name: str) -> str:
    """Decode hexadecimal encoded password
    but only decode when prefixed
    """
    decPW = ""
    if pw and pw.startswith(__PW_PREFIX):
        for n in range(len(__PW_PREFIX), len(pw), 2):
            try:
                ch = chr(int(pw[n] + pw[n + 1], 16))
            except ValueError:
                logging.error(T("Incorrectly encoded password %s"), name)
                return ""
            decPW += ch
        return decPW
    else:
        return pw


def create_api_key():
    """Return a new randomized API_KEY"""
    return uuid.uuid4().hex
