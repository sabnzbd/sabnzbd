#!/usr/bin/python3 -OO
# Copyright 2007-2021 The SABnzbd-Team <team@sabnzbd.org>
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
import argparse
import logging
import os
import re
import shutil
import threading
import uuid
from typing import List, Dict, Any, Callable, Optional, Union, Tuple
from urllib.parse import urlparse

import configobj

import sabnzbd.misc
from sabnzbd.constants import CONFIG_VERSION, NORMAL_PRIORITY, DEFAULT_PRIORITY
from sabnzbd.decorators import synchronized
from sabnzbd.filesystem import clip_path, real_path, create_real_path, renamer, remove_file, is_writable

CONFIG_LOCK = threading.Lock()
SAVE_CONFIG_LOCK = threading.Lock()


CFG: configobj.ConfigObj  # Holds INI structure
# during re-write this variable is global
# to allow direct access to INI structure

database = {}  # Holds the option dictionary

modified = False  # Signals a change in option dictionary
# Should be reset after saving to settings file

RE_PARAMFINDER = re.compile(r"""(?:'.*?')|(?:".*?")|(?:[^'",\s][^,]*)""")


class Option:
    """ Basic option class, basic fields """

    def __init__(self, section: str, keyword: str, default_val: Any = None, add: bool = True, protect: bool = False):
        """Basic option
        `section`     : single section or comma-separated list of sections
                        a list will be a hierarchy: "foo, bar" --> [foo][[bar]]
        `keyword`     : keyword in the (last) section
        `default_val` : value returned when no value has been set
        `callback`    : procedure to call when value is successfully changed
        `protect`     : Do not allow setting via the API (specifically set_dict)
        """
        self.__sections = section.split(",")
        self.__keyword: str = keyword
        self.__default_val: Any = default_val
        self.__value: Any = None
        self.__callback: Optional[Callable] = None
        self.__protect = protect

        # Add myself to the config dictionary
        if add:
            global database
            anchor = database
            for section in self.__sections:
                if section not in anchor:
                    anchor[section] = {}
                anchor = anchor[section]
            anchor[keyword] = self

    def get(self) -> Any:
        """ Retrieve value field """
        if self.__value is not None:
            return self.__value
        else:
            return self.__default_val

    def get_string(self) -> str:
        return str(self.get())

    def get_dict(self, safe: bool = False) -> Dict[str, Any]:
        """ Return value a dictionary """
        return {self.__keyword: self.get()}

    def set_dict(self, values: Dict[str, Any]):
        """ Set value based on dictionary """
        if not self.__protect:
            try:
                self.set(values["value"])
            except KeyError:
                pass

    def set(self, value: Any):
        """ Set new value, no validation """
        global modified
        if value is not None:
            if isinstance(value, list) or isinstance(value, dict) or value != self.__value:
                self.__value = value
                modified = True
                if self.__callback:
                    self.__callback()

    def default(self) -> Any:
        return self.__default_val

    def callback(self, callback: Callable):
        """ Set callback function """
        self.__callback = callback

    def ident(self):
        """ Return section-list and keyword """
        return self.__sections, self.__keyword


class OptionNumber(Option):
    """Numeric option class, int/float is determined from default value."""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: Union[int, float] = 0,
        minval: Optional[int] = None,
        maxval: Optional[int] = None,
        validation: Optional[Callable] = None,
        add: bool = True,
        protect: bool = False,
    ):
        self.__minval: Optional[int] = minval
        self.__maxval: Optional[int] = maxval
        self.__validation: Optional[Callable] = validation
        self.__int: bool = isinstance(default_val, int)
        super().__init__(section, keyword, default_val, add=add, protect=protect)

    def set(self, value: Any):
        """ set new value, limited by range """
        if value is not None:
            try:
                if self.__int:
                    value = int(value)
                else:
                    value = float(value)
            except ValueError:
                value = super().default()
            if self.__validation:
                _, val = self.__validation(value)
                super().set(val)
            else:
                if self.__maxval is not None and value > self.__maxval:
                    value = self.__maxval
                elif self.__minval is not None and value < self.__minval:
                    value = self.__minval
                super().set(value)

    def __call__(self) -> Union[int, float]:
        """ get() replacement """
        return self.get()


class OptionBool(Option):
    """ Boolean option class, always returns 0 or 1."""

    def __init__(self, section: str, keyword: str, default_val: bool = False, add: bool = True, protect: bool = False):
        super().__init__(section, keyword, int(default_val), add=add, protect=protect)

    def set(self, value: Any):
        # Store the value as integer, easier to parse when reading the config.
        super().set(sabnzbd.misc.int_conv(value))

    def __call__(self) -> int:
        """ get() replacement """
        return int(self.get())


class OptionDir(Option):
    """ Directory option class """

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: str = "",
        apply_umask: bool = False,
        create: bool = True,
        validation: Optional[Callable] = None,
        writable: bool = True,
        add: bool = True,
    ):
        self.__validation: Optional[Callable] = validation
        self.__root: str = ""  # Base directory for relative paths
        self.__apply_umask: bool = apply_umask
        self.__create: bool = create
        self.__writable: bool = writable
        super().__init__(section, keyword, default_val, add=add)

    def get(self) -> str:
        """ Return value, corrected for platform """
        p = super().get()
        if sabnzbd.WIN32:
            return p.replace("/", "\\") if "/" in p else p
        else:
            return p.replace("\\", "/") if "\\" in p else p

    def get_path(self) -> str:
        """ Return full absolute path """
        value = self.get()
        path = ""
        if value:
            path = real_path(self.__root, value)
            if self.__create and not os.path.exists(path):
                _, path, _ = create_real_path(self.ident()[1], self.__root, value, self.__apply_umask, self.__writable)
        return path

    def get_clipped_path(self) -> str:
        """ Return clipped full absolute path """
        return clip_path(self.get_path())

    def test_path(self) -> bool:
        """ Return True if path exists """
        value = self.get()
        if value:
            return os.path.exists(real_path(self.__root, value))
        else:
            return False

    def set_root(self, root: str):
        """ Set new root, is assumed to be valid """
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
                error, value = self.__validation(self.__root, value, super().default())
            if not error:
                if value and (self.__create or create):
                    res, path, error = create_real_path(
                        self.ident()[1], self.__root, value, self.__apply_umask, self.__writable
                    )
            if not error:
                super().set(value)
        return error

    def set_create(self, value: bool):
        """ Set auto-creation value """
        self.__create = value

    def __call__(self) -> str:
        """ get() replacement """
        return self.get()


class OptionList(Option):
    """ List option class """

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: Union[str, List, None] = None,
        validation: Optional[Callable] = None,
        add: bool = True,
        protect: bool = False,
    ):
        self.__validation: Optional[Callable] = validation
        if default_val is None:
            default_val = []
        super().__init__(section, keyword, default_val, add=add, protect=protect)

    def set(self, value: Union[str, List]) -> Optional[str]:
        """ Set the list given a comma-separated string or a list """
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

    def get_string(self) -> str:
        """ Return the list as a comma-separated string """
        return ", ".join(self.get())

    def default_string(self) -> str:
        """ Return the default list as a comma-separated string """
        return ", ".join(self.default())

    def __call__(self) -> List[str]:
        """ get() replacement """
        return self.get()


class OptionStr(Option):
    """ String class."""

    def __init__(
        self,
        section: str,
        keyword: str,
        default_val: str = "",
        validation: Optional[Callable] = None,
        add: bool = True,
        strip: bool = True,
        protect: bool = False,
    ):
        self.__validation: Optional[Callable] = validation
        self.__strip: bool = strip
        super().__init__(section, keyword, default_val, add=add, protect=protect)

    def get_float(self) -> float:
        """ Return value converted to a float, allowing KMGT notation """
        return sabnzbd.misc.from_units(self.get())

    def get_int(self) -> int:
        """ Return value converted to an int, allowing KMGT notation """
        return int(self.get_float())

    def set(self, value: Any) -> Optional[str]:
        """ Set stripped value """
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
        """ get() replacement """
        return self.get()


class OptionPassword(Option):
    """ Password class. """

    def __init__(self, section: str, keyword: str, default_val: str = "", add: bool = True):
        self.get_string = self.get_stars
        super().__init__(section, keyword, default_val, add=add)

    def get(self) -> Optional[str]:
        """ Return decoded password """
        return decode_password(super().get(), self.ident())

    def get_stars(self) -> Optional[str]:
        """ Return non-descript asterisk string """
        if self.get():
            return "*" * 10
        return ""

    def get_dict(self, safe: bool = False) -> Dict[str, str]:
        """ Return value a dictionary """
        if safe:
            return {self.ident()[1]: self.get_stars()}
        else:
            return {self.ident()[1]: self.get()}

    def set(self, pw: str):
        """ Set password, encode it """
        if (pw is not None and pw == "") or (pw and pw.strip("*")):
            super().set(encode_password(pw))

    def __call__(self) -> str:
        """ get() replacement """
        return self.get()


class ConfigServer:
    """ Class defining a single server """

    def __init__(self, name, values):

        self.__name = name
        name = "servers," + self.__name

        self.displayname = OptionStr(name, "displayname", add=False)
        self.host = OptionStr(name, "host", add=False)
        self.port = OptionNumber(name, "port", 119, 0, 2 ** 16 - 1, add=False)
        self.timeout = OptionNumber(name, "timeout", 60, 20, 240, add=False)
        self.username = OptionStr(name, "username", add=False)
        self.password = OptionPassword(name, "password", add=False)
        self.connections = OptionNumber(name, "connections", 1, 0, 1000, add=False)
        self.ssl = OptionBool(name, "ssl", False, add=False)
        # 0=No, 1=Normal, 2=Strict (hostname verification)
        self.ssl_verify = OptionNumber(name, "ssl_verify", 2, add=False)
        self.ssl_ciphers = OptionStr(name, "ssl_ciphers", add=False)
        self.enable = OptionBool(name, "enable", True, add=False)
        self.optional = OptionBool(name, "optional", False, add=False)
        self.retention = OptionNumber(name, "retention", 0, add=False)
        self.expire_date = OptionStr(name, "expire_date")
        self.quota_left = OptionStr(name, "quota_left")
        self.usage_at_start = OptionStr(name, "usage_at_start")
        self.send_group = OptionBool(name, "send_group", False, add=False)
        self.priority = OptionNumber(name, "priority", 0, 0, 99, add=False)
        self.notes = OptionStr(name, "notes", add=False)

        self.set_dict(values)
        add_to_database("servers", self.__name, self)

    def set_dict(self, values: Dict[str, Any]):
        """ Set one or more fields, passed as dictionary """
        # Replace usage_at_start value with most recent statistics if the user changes the quota value
        usage_at_start_new = values.get("usage_at_start_new", "")
        if usage_at_start_new and values.get("quota_left", "") != values.get("quota_left_old", ""):
            values["usage_at_start"] = usage_at_start_new

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
            "send_group",
            "enable",
            "optional",
            "retention",
            "expire_date",
            "quota_left",
            "usage_at_start",
            "priority",
            "notes",
        ):
            try:
                value = values[kw]
                getattr(self, kw).set(value)
            except KeyError:
                continue
        if not self.displayname():
            self.displayname.set(self.__name)

    def get_dict(self, safe: bool = False) -> Dict[str, Any]:
        """ Return a dictionary with all attributes """
        output_dict = {}
        output_dict["name"] = self.__name
        output_dict["displayname"] = self.displayname()
        output_dict["host"] = self.host()
        output_dict["port"] = self.port()
        output_dict["timeout"] = self.timeout()
        output_dict["username"] = self.username()
        if safe:
            output_dict["password"] = self.password.get_stars()
        else:
            output_dict["password"] = self.password()
        output_dict["connections"] = self.connections()
        output_dict["ssl"] = self.ssl()
        output_dict["ssl_verify"] = self.ssl_verify()
        output_dict["ssl_ciphers"] = self.ssl_ciphers()
        output_dict["enable"] = self.enable()
        output_dict["optional"] = self.optional()
        output_dict["retention"] = self.retention()
        output_dict["expire_date"] = self.expire_date()
        output_dict["quota_left"] = self.quota_left()
        output_dict["usage_at_start"] = self.usage_at_start()
        output_dict["send_group"] = self.send_group()
        output_dict["priority"] = self.priority()
        output_dict["notes"] = self.notes()
        return output_dict

    def delete(self):
        """ Remove from database """
        delete_from_database("servers", self.__name)

    def rename(self, name: str):
        """ Give server new display name """
        self.displayname.set(name)

    def ident(self) -> Tuple[str, str]:
        return "servers", self.__name


class ConfigCat:
    """ Class defining a single category """

    def __init__(self, name: str, values: Dict[str, Any]):
        self.__name = name
        name = "categories," + name

        self.order = OptionNumber(name, "order", 0, 0, 100, add=False)
        self.pp = OptionStr(name, "pp", add=False)
        self.script = OptionStr(name, "script", "Default", add=False)
        self.dir = OptionDir(name, "dir", add=False, create=False)
        self.newzbin = OptionList(name, "newzbin", add=False, validation=validate_single_tag)
        self.priority = OptionNumber(name, "priority", DEFAULT_PRIORITY, add=False)

        self.set_dict(values)
        add_to_database("categories", self.__name, self)

    def set_dict(self, values: Dict[str, Any]):
        """ Set one or more fields, passed as dictionary """
        for kw in ("order", "pp", "script", "dir", "newzbin", "priority"):
            try:
                value = values[kw]
                getattr(self, kw).set(value)
            except KeyError:
                continue

    def get_dict(self, safe: bool = False) -> Dict[str, Any]:
        """ Return a dictionary with all attributes """
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
        """ Remove from database """
        delete_from_database("categories", self.__name)


class OptionFilters(Option):
    """ Filter list class """

    def __init__(self, section, keyword, add=True):
        super().__init__(section, keyword, add=add)
        self.set([])

    def move(self, current: int, new: int):
        """ Move filter from position 'current' to 'new' """
        lst = self.get()
        try:
            item = lst.pop(current)
            lst.insert(new, item)
        except IndexError:
            return
        self.set(lst)

    def update(self, pos: int, value: Tuple):
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
        """ Remove filter 'pos' """
        lst = self.get()
        try:
            lst.pop(pos)
        except IndexError:
            return
        self.set(lst)

    def get_dict(self, safe: bool = False) -> Dict[str, str]:
        """ Return filter list as a dictionary with keys 'filter[0-9]+' """
        output_dict = {}
        for n, rss_filter in enumerate(self.get()):
            output_dict[f"filter{n}"] = rss_filter
        return output_dict

    def set_dict(self, values: Dict[str, Any]):
        """ Create filter list from dictionary with keys 'filter[0-9]+' """
        filters = []
        # We don't know how many filters there are, so just assume all values are filters
        for n in range(len(values)):
            kw = f"filter{n}"
            if kw in values:
                filters.append(values[kw])
        if filters:
            self.set(filters)

    def __call__(self) -> List[List[str]]:
        """ get() replacement """
        return self.get()


class ConfigRSS:
    """ Class defining a single Feed definition """

    def __init__(self, name, values):
        self.__name = name
        name = "rss," + name

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

    def set_dict(self, values: Dict[str, Any]):
        """ Set one or more fields, passed as dictionary """
        for kw in ("uri", "cat", "pp", "script", "priority", "enable"):
            try:
                value = values[kw]
                getattr(self, kw).set(value)
            except KeyError:
                continue
        self.filters.set_dict(values)

    def get_dict(self, safe: bool = False) -> Dict[str, Any]:
        """ Return a dictionary with all attributes """
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
        """ Remove from database """
        delete_from_database("rss", self.__name)

    def rename(self, new_name: str):
        """ Update the name and the saved entries """
        delete_from_database("rss", self.__name)
        sabnzbd.RSSReader.rename(self.__name, new_name)
        self.__name = new_name
        add_to_database("rss", self.__name, self)

    def ident(self) -> Tuple[str, str]:
        return "rss", self.__name


@synchronized(CONFIG_LOCK)
def add_to_database(section, keyword, obj):
    """ add object as section/keyword to INI database """
    global database
    if section not in database:
        database[section] = {}
    database[section][keyword] = obj


@synchronized(CONFIG_LOCK)
def delete_from_database(section, keyword):
    """ Remove section/keyword from INI database """
    global database, CFG, modified
    del database[section][keyword]
    if section == "servers" and "[" in keyword:
        keyword = keyword.replace("[", "{").replace("]", "}")
    try:
        del CFG[section][keyword]
    except KeyError:
        pass
    modified = True


def get_dconfig(section, keyword, nested=False):
    """Return a config values dictionary,
    Single item or slices based on 'section', 'keyword'
    """
    data = {}
    if not section:
        for section in database.keys():
            res, conf = get_dconfig(section, None, True)
            data.update(conf)

    elif not keyword:
        try:
            sect = database[section]
        except KeyError:
            return False, {}
        if section in ("servers", "categories", "rss"):
            data[section] = []
            for keyword in sect.keys():
                res, conf = get_dconfig(section, keyword, True)
                data[section].append(conf)
        else:
            data[section] = {}
            for keyword in sect.keys():
                res, conf = get_dconfig(section, keyword, True)
                data[section].update(conf)

    else:
        try:
            item = database[section][keyword]
        except KeyError:
            return False, {}
        data = item.get_dict(safe=True)
        if not nested:
            if section in ("servers", "categories", "rss"):
                data = {section: [data]}
            else:
                data = {section: data}

    return True, data


def get_config(section, keyword):
    """ Return a config object, based on 'section', 'keyword' """
    try:
        return database[section][keyword]
    except KeyError:
        logging.debug("Missing configuration item %s,%s", section, keyword)
        return None


def set_config(kwargs):
    """ Set a config item, using values in dictionary """
    try:
        item = database[kwargs.get("section")][kwargs.get("keyword")]
    except KeyError:
        return False
    item.set_dict(kwargs)
    return True


def delete(section: str, keyword: str):
    """ Delete specific config item """
    try:
        database[section][keyword].delete()
    except KeyError:
        return


##############################################################################
# INI file support
#
# This does input and output of configuration to an INI file.
# It translates this data structure to the config database.
##############################################################################
@synchronized(SAVE_CONFIG_LOCK)
def read_config(path):
    """Read the complete INI file and check its version number
    if OK, pass values to config-database
    """
    return _read_config(path)


def _read_config(path, try_backup=False):
    """Read the complete INI file and check its version number
    if OK, pass values to config-database
    """
    global CFG, database, modified

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
            if not sabnzbd.WIN32:
                prev = os.umask(0o77)
            with open(path, "w") as fp:
                fp.write("__version__=%s\n[misc]\n[logging]\n" % CONFIG_VERSION)
            if not sabnzbd.WIN32:
                os.umask(prev)
        except IOError:
            return False, "Cannot create INI file %s" % path

    try:
        # Let configobj open the file
        CFG = configobj.ConfigObj(infile=path, default_encoding="utf-8", encoding="utf-8")
    except (IOError, configobj.ConfigObjError, UnicodeEncodeError) as strerror:
        if try_backup:
            # No luck!
            return False, '"%s" is not a valid configuration file<br>Error message: %s' % (path, strerror)
        else:
            # Try backup file
            return _read_config(path, True)

    try:
        version = sabnzbd.misc.int_conv(CFG["__version__"])
        if version > int(CONFIG_VERSION):
            return False, "Incorrect version number %s in %s" % (version, path)
    except (KeyError, ValueError):
        pass

    CFG.filename = path
    CFG.encoding = "utf-8"
    CFG["__encoding__"] = "utf-8"
    CFG["__version__"] = str(CONFIG_VERSION)

    # Use CFG data to set values for all static options
    for section in database:
        if section not in ("servers", "categories", "rss"):
            for option in database[section]:
                sec, kw = database[section][option].ident()
                sec = sec[-1]
                try:
                    database[section][option].set(CFG[sec][kw])
                except KeyError:
                    pass

    # Define the special settings
    if "categories" in CFG:
        for cat in CFG["categories"]:
            ConfigCat(cat, CFG["categories"][cat])
    if "rss" in CFG:
        for rss_feed in CFG["rss"]:
            ConfigRSS(rss_feed, CFG["rss"][rss_feed])
    if "servers" in CFG:
        for server in CFG["servers"]:
            ConfigServer(server.replace("{", "[").replace("}", "]"), CFG["servers"][server])

    modified = False
    return True, ""


@synchronized(SAVE_CONFIG_LOCK)
def save_config(force=False):
    """ Update Setup file with current option values """
    global CFG, database, modified

    if not (modified or force):
        return True

    if sabnzbd.cfg.configlock():
        logging.warning(T("Configuration locked, cannot save settings"))
        return False

    for section in database:
        if section in ("servers", "categories", "rss"):
            try:
                CFG[section]
            except KeyError:
                CFG[section] = {}
            for subsec in database[section]:
                if section == "servers":
                    subsec_mod = subsec.replace("[", "{").replace("]", "}")
                else:
                    subsec_mod = subsec
                try:
                    CFG[section][subsec_mod]
                except KeyError:
                    CFG[section][subsec_mod] = {}
                items = database[section][subsec].get_dict()
                CFG[section][subsec_mod] = items
        else:
            for option in database[section]:
                sec, kw = database[section][option].ident()
                sec = sec[-1]
                try:
                    CFG[sec]
                except KeyError:
                    CFG[sec] = {}
                value = database[section][option]()
                # bool is a subclass of int, check first
                CFG[sec][kw] = value

    res = False
    filename = CFG.filename
    bakname = filename + ".bak"

    # Check if file is writable
    if not is_writable(filename):
        logging.error(T("Cannot write to INI file %s"), filename)
        return res

    # copy current file to backup
    try:
        shutil.copyfile(filename, bakname)
        shutil.copymode(filename, bakname)
    except:
        # Something wrong with the backup,
        logging.error(T("Cannot create backup file for %s"), bakname)
        logging.info("Traceback: ", exc_info=True)
        return res

    # Write new config file
    try:
        logging.info("Writing settings to INI file %s", filename)
        CFG.write()
        shutil.copymode(bakname, filename)
        modified = False
        res = True
    except:
        logging.error(T("Cannot write to INI file %s"), filename)
        logging.info("Traceback: ", exc_info=True)
        try:
            remove_file(filename)
        except:
            pass
        # Restore INI file from backup
        renamer(bakname, filename)

    return res


def get_servers() -> Dict[str, ConfigServer]:
    global database
    try:
        return database["servers"]
    except KeyError:
        return {}


def get_categories() -> Dict[str, ConfigCat]:
    """Return link to categories section.
    This section will always contain special category '*'
    """
    global database
    if "categories" not in database:
        database["categories"] = {}
    cats = database["categories"]

    # Add Default categories
    if "*" not in cats:
        ConfigCat("*", {"pp": "3", "script": "None", "priority": NORMAL_PRIORITY})
        # Add some category suggestions
        ConfigCat("movies", {})
        ConfigCat("tv", {})
        ConfigCat("audio", {})
        ConfigCat("software", {})

        # Save config for future use
        save_config(True)
    return cats


def get_category(cat: str = "*") -> ConfigCat:
    """Get one specific category or if not found the default one"""
    cats = get_categories()
    try:
        return cats[cat]
    except KeyError:
        return cats["*"]


def get_ordered_categories() -> List[Dict]:
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


def get_rss() -> Dict[str, ConfigRSS]:
    global database
    try:
        # We have to remove non-separator commas by detecting if they are valid URL's
        for feed_key in database["rss"]:
            feed = database["rss"][feed_key]
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

        return database["rss"]
    except KeyError:
        return {}


def get_filename():
    global CFG
    return CFG.filename


##############################################################################
# Default Validation handlers
##############################################################################
__PW_PREFIX = "!!!encoded!!!"


class ErrorCatchingArgumentParser(argparse.ArgumentParser):
    def error(self, status=0, message=None):
        # Need to override so it doesn't raise SystemExit
        if status:
            raise ValueError


def encode_password(pw):
    """ Encode password in hexadecimal if needed """
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


def decode_password(pw, name):
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


def clean_nice_ionice_parameters(value):
    """ Verify that the passed parameters are not exploits """
    if value:
        parser = ErrorCatchingArgumentParser()

        # Nice parameters
        parser.add_argument("-n", "--adjustment", type=int)

        # Ionice parameters, not supporting -p
        parser.add_argument("--classdata", type=int)
        parser.add_argument("-c", "--class", type=int)
        parser.add_argument("-t", "--ignore", action="store_true")

        try:
            parser.parse_args(value.split())
        except ValueError:
            # Also log at start-up if invalid parameter was set in the ini
            msg = "%s: %s" % (T("Incorrect parameter"), value)
            logging.error(msg)
            return msg, None
    return None, value


def all_lowercase(value):
    """ Lowercase everything! """
    if isinstance(value, list):
        # If list, for each item
        return None, [item.lower() for item in value]
    return None, value.lower()


def validate_octal(value):
    """ Check if string is valid octal number """
    if not value:
        return None, value
    try:
        int(value, 8)
        return None, value
    except:
        return T("%s is not a correct octal value") % value, None


def validate_no_unc(root, value, default):
    """ Check if path isn't a UNC path """
    # Only need to check the 'value' part
    if value and not value.startswith(r"\\"):
        return validate_notempty(root, value, default)
    else:
        return T('UNC path "%s" not allowed here') % value, None


def validate_safedir(root, value, default):
    """Allow only when queues are empty and no UNC"""
    if not sabnzbd.__INITIALIZED__ or (sabnzbd.PostProcessor.empty() and sabnzbd.NzbQueue.is_empty()):
        return validate_no_unc(root, value, default)
    else:
        return T("Error: Queue not empty, cannot change folder."), None


def validate_notempty(root, value, default):
    """ If value is empty, return default """
    if value:
        return None, value
    else:
        return None, default


def validate_strip_right_slash(value):
    """Strips the right slash"""
    if value:
        return None, value.rstrip("/")
    return None, value


def validate_single_tag(value):
    """Don't split single indexer tags like "TV > HD"
    into ['TV', '>', 'HD']
    """
    if len(value) == 3:
        if value[1] == ">":
            return None, " ".join(value)
    return None, value


def create_api_key():
    """ Return a new randomized API_KEY """
    return uuid.uuid4().hex
