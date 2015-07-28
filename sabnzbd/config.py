#!/usr/bin/python -OO
# Copyright 2008-2015 The SABnzbd-Team <team@sabnzbd.org>
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

import os
import re
import logging
import threading
import shutil
import sabnzbd.misc
from sabnzbd.constants import CONFIG_VERSION, NORMAL_PRIORITY, DEFAULT_PRIORITY
from sabnzbd.utils import listquote
from sabnzbd.utils import configobj
from sabnzbd.decorators import synchronized

CONFIG_LOCK = threading.Lock()
SAVE_CONFIG_LOCK = threading.Lock()


CFG = {}                    # Holds INI structure
                            # uring re-write this variable is global allow
                            # direct access to INI structure

database = {}               # Holds the option dictionary

modified = False            # Signals a change in option dictionary
                            # Should be reset after saving to settings file


class Option(object):
    """ Basic option class, basic fields """
    def __init__(self, section, keyword, default_val=None, add=True, protect=False):
        """ Basic option
            section     : single section or comma-separated list of sections
                          a list will be a hierarchy: "foo, bar" --> [foo][[bar]]
            keyword     : keyword in the (last) section
            default_val : value returned when no value has been set
            callback    : procedure to call when value is succesfully changed
            protect     : Do not allow setting via the API (specifically set_dict)
        """
        self.__sections = section.split(',')
        self.__keyword = keyword
        self.__default_val = default_val
        self.__value = None
        self.__callback = None
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

    def __call__(self):
        """ get() replacement """
        return self.get()

    def get(self):
        """ Retrieve value field """
        if self.__value != None:
            return self.__value
        else:
            return self.__default_val

    def get_string(self):
        return str(self.get())

    def get_dict(self, safe=False):
        """ Return value a dictionary """
        return { self.__keyword : self.get() }

    def set_dict(self, dict):
        """ Set value based on dictionary """
        if self.__protect:
            return False
        try:
            return self.set(dict['value'])
        except KeyError:
            return False

    def __set(self, value):
        """ Set new value, no validation """
        global modified
        if (value != None):
            if type(value) == type([]) or type(value) == type({}) or value != self.__value:
                self.__value = value
                modified = True
                if self.__callback:
                    self.__callback()
        return None

    def set(self, value):
        return self.__set(value)

    def default(self):
        return self.__default_val

    def callback(self, callback):
        """ Set callback function """
        self.__callback = callback

    def ident(self):
        """ Return section-list and keyword """
        return self.__sections, self.__keyword



class OptionNumber(Option):
    """ Numeric option class, int/float is determined from default value """
    def __init__(self, section, keyword, default_val=0, minval=None, maxval=None, validation=None, add=True, protect=False):
        Option.__init__(self, section, keyword, default_val, add=add, protect=protect)
        self.__minval = minval
        self.__maxval = maxval
        self.__validation = validation
        self.__int = type(default_val) == type(0)

    def set(self, value):
        """ set new value, limited by range """
        if value != None:
            try:
                if self.__int:
                    value = int(value)
                else:
                    value = float(value)
            except ValueError:
                value = self._Option__default_val
            if self.__validation:
                error, val = self.__validation(value)
                self._Option__set(val)
            else:
                if (self.__maxval != None) and value > self.__maxval:
                    value = self.__maxval
                elif (self.__minval != None) and value < self.__minval:
                    value = self.__minval
                self._Option__set(value)
        return None


class OptionBool(Option):
    """ Boolean option class """
    def __init__(self, section, keyword, default_val=False, add=True, protect=False):
        Option.__init__(self, section, keyword, int(default_val), add=add, protect=protect)

    def set(self, value):
        if value is None:
            value = 0
        try:
            self._Option__set(int(value))
        except ValueError:
            self._Option__set(0)
        return None


class OptionDir(Option):
    """ Directory option class """
    def __init__(self, section, keyword, default_val='', apply_umask=False, create=True, validation=None, writable=True, add=True):
        self.__validation = validation
        self.__root = ''   # Base directory for relative paths
        self.__apply_umask = apply_umask
        self.__create = create
        self.__writable = writable
        Option.__init__(self, section, keyword, default_val, add=add)

    def get(self):
        """ Return value, corrected for platform """
        if self._Option__value != None:
            p = self._Option__value
        else:
            p = self._Option__default_val
        if sabnzbd.WIN32:
            return p.replace('/', '\\') if '/' in p else p
        else:
            return p.replace('\\', '/') if '\\' in p else p
        

    def get_path(self):
        """ Return full absolute path """
        value = self.get()
        path = ''
        if value:
            path = sabnzbd.misc.real_path(self.__root, value)
            if self.__create and not os.path.exists(path):
                res, path = sabnzbd.misc.create_real_path(self.ident()[1], self.__root, value, self.__apply_umask, self.__writable)
        return path

    def test_path(self):
        """ Return True if path exists """
        value = self.get()
        if value:
            return os.path.exists(sabnzbd.misc.real_path(self.__root, value))
        else:
            return False

    def set_root(self, root):
        """ Set new root, is assumed to be valid """
        self.__root = root

    def set(self, value, create=False):
        """ Set new dir value, validate and create if needed
            Return None when directory is accepted
            Return error-string when not accepted, value will not be changed
            'create' means try to create (but don't set permanent create flag)
        """
        error = None
        if value != None and (create or value != self.get()):
            value = value.strip()
            if self.__validation:
                error, value = self.__validation(self.__root, value, self._Option__default_val)
            if not error:
                if value and (self.__create or create):
                    res, path = sabnzbd.misc.create_real_path(self.ident()[1], self.__root, value, self.__apply_umask, self.__writable)
                    if not res:
                        error = T('Cannot create %s folder %s') % (self.ident()[1], path)
            if not error:
                self._Option__set(value)
        return error

    def set_create(self, value):
        """ Set auto-creation value """
        self.__create = value

class OptionList(Option):
    """ List option class """
    def __init__(self, section, keyword, default_val=None, validation=None, add=True, protect=False):
        self.__validation = validation
        if default_val is None:
            default_val = []
        Option.__init__(self, section, keyword, default_val, add=add, protect=protect)

    def set(self, value):
        """ Set the list given a comma-separated string or a list"""
        error = None
        if value is not None:
            if not isinstance(value, list):
                if '"' not in value and ',' not in value:
                    value = value.split()
                else:
                    value = listquote.simplelist(value)
            if self.__validation:
                error, value = self.__validation(value)
            if not error:
                self._Option__set(value)
        return error

    def get_string(self):
        """ Return the list as a comma-separated string """
        lst = self.get()
        if type(lst) == type(""):
            return lst
        txt = ''
        r = len(lst)
        for n in xrange(r):
            txt += lst[n]
            if n < r-1: txt += ', '
        return txt


class OptionStr(Option):
    """ String class """
    def __init__(self, section, keyword, default_val='', validation=None, add=True, strip=True, protect=False):
        Option.__init__(self, section, keyword, default_val, add=add, protect=protect)
        self.__validation = validation
        self.__strip = strip

    def get_float(self):
        """ Return value converted to a float, allowing KMGT notation """
        return sabnzbd.misc.from_units(self.get())

    def get_int(self):
        """ Return value converted to an int, allowing KMGT notation """
        return int(self.get_float())

    def set(self, value):
        """ Set stripped value """
        error = None
        if type(value) == type('') and self.__strip:
            value = value.strip()
        if self.__validation:
            error, val = self.__validation(value)
            self._Option__set(val)
        else:
            self._Option__set(value)
        return error


class OptionPassword(Option):
    """ Password class """
    def __init__(self, section, keyword, default_val='', add=True):
        Option.__init__(self, section, keyword, default_val, add=add)
        self.get_string = self.get_stars

    def get(self):
        """ Return decoded password """
        value = self._Option__value
        if value is None:
            return self._Option__default_val
        else:
            return decode_password(value, self.ident())

    def get_stars(self):
        """ Return decoded password as asterisk string """
        return '*' * len(decode_password(self.get(), self.ident()))

    def get_dict(self, safe=False):
        """ Return value a dictionary """
        if safe:
            return { self._Option__keyword : self.get_stars() }
        else:
            return { self._Option__keyword : self.get() }

    def set(self, pw):
        """ Set password, encode it """
        if (pw != None and pw == '') or (pw and pw.strip('*')):
            self._Option__set(encode_password(pw))
        return None


@synchronized(CONFIG_LOCK)
def add_to_database(section, keyword, obj):
    """ add object as secion/keyword to INI database """
    global database
    if section not in database:
        database[section] = {}
    database[section][keyword] = obj


@synchronized(CONFIG_LOCK)
def delete_from_database(section, keyword):
    """ Remove section/keyword from INI database """
    global database, CFG, modified
    del database[section][keyword]
    if section == 'servers' and '[' in keyword:
        keyword = keyword.replace('[', '{').replace(']', '}')
    try:
        del CFG[section][keyword]
    except KeyError:
        pass
    modified = True


class ConfigServer(object):
    """ Class defining a single server """
    def __init__(self, name, values):

        self.__name = name
        name = 'servers,' + self.__name

        self.displayname = OptionStr(name, 'displayname', '', add=False)
        self.host = OptionStr(name, 'host', '', add=False)
        self.port = OptionNumber(name, 'port', 119, 0, 2**16-1, add=False)
        self.timeout = OptionNumber(name, 'timeout', 120, 30, 240, add=False)
        self.username = OptionStr(name, 'username', '', add=False)
        self.password = OptionPassword(name, 'password', '', add=False)
        self.connections = OptionNumber(name, 'connections', 1, 0, 100, add=False)
        self.ssl = OptionBool(name, 'ssl', False, add=False)
        self.enable = OptionBool(name, 'enable', True, add=False)
        self.optional = OptionBool(name, 'optional', False, add=False)
        self.retention = OptionNumber(name, 'retention', add=False)
        self.ssl_type = OptionStr(name, 'ssl_type', 't1', add=False)
        self.send_group = OptionBool(name, 'send_group', False, add=False)
        self.priority = OptionNumber(name, 'priority', 0, 0, 100, add=False)
        # 'fillserver' field only here in order to set a proper priority when converting
        self.fillserver = OptionBool(name, 'fillserver', False, add=False)
        self.categories = OptionList(name, 'categories', default_val=['Default'], add=False)
        self.notes = OptionStr(name, 'notes', '', add=False)

        self.set_dict(values)
        add_to_database('servers', self.__name, self)

    def set_dict(self, values):
        """ Set one or more fields, passed as dictionary """
        for kw in ('displayname', 'host', 'port', 'timeout', 'username', 'password', 'connections', 'fillserver',
                   'ssl', 'ssl_type', 'send_group', 'enable', 'optional', 'retention', 'priority',
                   'categories', 'notes'):
            try:
                value = values[kw]
            except KeyError:
                continue
            exec 'self.%s.set(value)' % kw
            if not self.displayname():
                self.displayname.set(self.__name)
        return True

    def get_dict(self, safe=False):
        """ Return a dictionary with all attributes """
        dict = {}
        dict['name'] = self.__name
        dict['displayname'] = self.displayname()
        dict['host'] = self.host()
        dict['port'] = self.port()
        dict['timeout'] = self.timeout()
        dict['username'] = self.username()
        if safe:
            dict['password'] = self.password.get_stars()
        else:
            dict['password'] = self.password()
        dict['connections'] = self.connections()
        dict['ssl'] = self.ssl()
        dict['enable'] = self.enable()
        dict['optional'] = self.optional()
        dict['retention'] = self.retention()
        dict['ssl_type'] = self.ssl_type()
        dict['send_group'] = self.send_group()
        dict['priority'] = self.priority()
        dict['categories'] = self.categories()
        dict['notes'] = self.notes()
        return dict

    def delete(self):
        """ Remove from database """
        delete_from_database('servers', self.__name)

    def rename(self, name):
        """ Give server new display name """
        self.displayname.set(name)

    def ident(self):
        return 'servers', self.__name


class ConfigCat(object):
    """ Class defining a single category """
    def __init__(self, name, values):
        self.__name = name
        name = 'categories,' + name

        self.pp = OptionStr(name, 'pp', '', add=False)
        self.script = OptionStr(name, 'script', 'Default', add=False)
        self.dir = OptionDir(name, 'dir', add=False, create=False)
        self.newzbin = OptionList(name, 'newzbin', add=False)
        self.priority = OptionNumber(name, 'priority', DEFAULT_PRIORITY, add=False)

        self.set_dict(values)
        add_to_database('categories', self.__name, self)

    def set_dict(self, values):
        """ Set one or more fields, passed as dictionary """
        for kw in ('pp', 'script', 'dir', 'newzbin', 'priority'):
            try:
                value = values[kw]
            except KeyError:
                continue
            exec 'self.%s.set(value)' % kw
        return True

    def get_dict(self, safe=False):
        """ Return a dictionary with all attributes """
        dict = {}
        dict['name'] = self.__name
        dict['pp'] = self.pp()
        dict['script'] = self.script()
        dict['dir'] = self.dir()
        dict['newzbin'] = self.newzbin.get_string()
        dict['priority'] = self.priority()
        return dict

    def delete(self):
        """ Remove from database """
        delete_from_database('categories', self.__name)


class OptionFilters(Option):
    """ Filter list class """
    def __init__(self, section, keyword, add=True):
        Option.__init__(self, section, keyword, add=add)
        self.set([])

    def move(self, current, new):
        """ Move filter from position 'current' to 'new' """
        lst = self.get()
        try:
            item = lst.pop(current)
            lst.insert(new, item)
        except IndexError:
            return
        self.set(lst)

    def update(self, pos, value):
        """ Update filter 'pos' definition, value is a list
            Append if 'pos' outside list
        """
        lst = self.get()
        try:
            lst[pos] = value
        except IndexError:
            lst.append(value)
        self.set(lst)

    def delete(self, pos):
        """ Remove filter 'pos' """
        lst = self.get()
        try:
            lst.pop(pos)
        except IndexError:
            return
        self.set(lst)

    def get_dict(self, safe=False):
        """ Return filter list as a dictionary with keys 'filter[0-9]+' """
        dict = {}
        n = 0
        for filter in self.get():
            dict['filter'+str(n)] = filter
            n = n + 1
        return dict

    def set_dict(self, values):
        """ Create filter list from dictionary with keys 'filter[0-9]+' """
        filters = []
        for n in xrange(len(values)):
            kw = 'filter%d' % n
            val = values.get(kw)
            if val is not None:
                val = values[kw]
                if type(val) == type([]):
                    filters.append(val)
                else:
                    filters.append(listquote.simplelist(val))
                while len(filters[-1]) < 7:
                    filters[-1].append('1')
                if not filters[-1][6]:
                    filters[-1][6] = '1'
        if filters:
            self.set(filters)
        return True

class ConfigRSS(object):
    """ Class defining a single Feed definition """
    def __init__(self, name, values):
        self.__name = name
        name = 'rss,' + name

        self.uri = OptionStr(name, 'uri', add=False)
        self.cat = OptionStr(name, 'cat', add=False)
        self.pp = OptionStr(name, 'pp', '', add=False)
        self.script = OptionStr(name, 'script', add=False)
        self.enable = OptionBool(name, 'enable', add=False)
        self.priority = OptionNumber(name, 'priority', DEFAULT_PRIORITY, DEFAULT_PRIORITY, 2, add=False)
        self.filters = OptionFilters(name, 'filters', add=False)
        self.filters.set([['', '', '', 'A', '*', DEFAULT_PRIORITY, '1']])

        self.set_dict(values)
        add_to_database('rss', self.__name, self)

    def set_dict(self, values):
        """ Set one or more fields, passed as dictionary """
        for kw in ('uri', 'cat', 'pp', 'script', 'priority', 'enable'):
            try:
                value = values[kw]
            except KeyError:
                continue
            exec 'self.%s.set(value)' % kw

        self.filters.set_dict(values)
        return True

    def get_dict(self, safe=False):
        """ Return a dictionary with all attributes """
        dict = {}
        dict['name'] = self.__name
        dict['uri'] = self.uri()
        dict['cat'] = self.cat()
        dict['pp'] = self.pp()
        dict['script'] = self.script()
        dict['enable'] = self.enable()
        dict['priority'] = self.priority()
        filters = self.filters.get_dict()
        for kw in filters:
            dict[kw] = filters[kw]
        return dict

    def delete(self):
        """ Remove from database """
        delete_from_database('rss', self.__name)

    def ident(self):
        return 'rss', self.__name



def get_dconfig(section, keyword, nested=False):
    """ Return a config values dictonary,
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
        if section in ('servers', 'categories', 'rss'):
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
            if section in ('servers', 'categories', 'rss'):
                data = {section : [ data ]}
            else:
                data = {section : data}

    return True, data


def get_config(section, keyword):
    """ Return a config object, based on 'section', 'keyword'
    """
    try:
        return database[section][keyword]
    except KeyError:
        logging.debug('Missing configuration item %s,%s', section, keyword)
        return None


def set_config(kwargs):
    """ Set a config item, using values in dictionary
    """
    try:
        item = database[kwargs.get('section')][kwargs.get('keyword')]
    except KeyError:
        return False
    item.set_dict(kwargs)
    return True


def delete(section, keyword):
    """ Delete specific config item
    """
    try:
        database[section][keyword].delete()
    except KeyError:
        return


################################################################################
#
# INI file support
#
# This does input and output of configuration to an INI file.
# It translates this data structure to the config database.

@synchronized(SAVE_CONFIG_LOCK)
def read_config(path):
    """ Read the complete INI file and check its version number
        if OK, pass values to config-database
    """
    return _read_config(path)


def _read_config(path, try_backup=False):
    """ Read the complete INI file and check its version number
        if OK, pass values to config-database
    """
    global CFG, database, modified

    if try_backup or not os.path.exists(path):
        # Not found, try backup
        try:
            shutil.copyfile(path + '.bak', path)
            try_backup = True
        except IOError:
            pass

    if not os.path.exists(path):
        # No file found, create default INI file
        try:
            if not sabnzbd.WIN32:
                prev = os.umask(077)
            fp = open(path, "w")
            fp.write("__version__=%s\n[misc]\n[logging]\n" % CONFIG_VERSION)
            fp.close()
            if not sabnzbd.WIN32:
                os.umask(prev)
        except IOError:
            return False, 'Cannot create INI file %s' % path

    try:
        fp = open(path, 'rb')
        lines = fp.read().split('\n')
        if len(lines) == 1:
            fp.seek(0)
            lines = fp.read().split('\r')
        lines = [line.rstrip('\r\n') for line in lines]
        fp.close()

        try:
            # First try UTF-8 encoding
            CFG = configobj.ConfigObj(lines, default_encoding='utf-8', encoding='utf-8')
        except UnicodeDecodeError:
            # Failed, enable retry
            CFG = {}

        if not re.search(r'utf[ -]*8', CFG.get('__encoding__', ''), re.I):
            # INI file is still in 8bit ASCII encoding, so try Latin-1 instead
            CFG = configobj.ConfigObj(lines, default_encoding='cp1252', encoding='cp1252')

    except (IOError, configobj.ConfigObjError, UnicodeEncodeError), strerror:
        if try_backup:
            if isinstance(strerror, UnicodeEncodeError):
                strerror = 'Character encoding of the file is inconsistent'
            return False, '"%s" is not a valid configuration file<br>Error message: %s' % (path, strerror)
        else:
            # Try backup file
            return _read_config(path, True)

    try:
        version = sabnzbd.misc.int_conv(CFG['__version__'])
        if version > int(CONFIG_VERSION):
            return False, "Incorrect version number %s in %s" % (version, path)
    except (KeyError, ValueError):
        pass

    CFG.filename = path
    CFG.encoding = 'utf-8'
    CFG['__encoding__'] = u'utf-8'
    CFG['__version__'] = unicode(CONFIG_VERSION)

    if 'misc' in CFG:
        compatibility_fix(CFG['misc'])

    # Use CFG data to set values for all static options
    for section in database:
        if section not in ('servers', 'categories', 'rss'):
            for option in database[section]:
                sec, kw = database[section][option].ident()
                sec = sec[-1]
                try:
                    database[section][option].set(CFG[sec][kw])
                except KeyError:
                    pass

    define_categories()
    define_rss()
    define_servers()

    modified = False
    return True, ""



@synchronized(SAVE_CONFIG_LOCK)
def save_config(force=False):
    """ Update Setup file with current option values """
    global CFG, database, modified
    assert isinstance(CFG, configobj.ConfigObj)

    if not (modified or force):
        return True

    for section in database:
        if section in ('servers', 'categories', 'rss'):
            try:
                CFG[section]
            except KeyError:
                CFG[section] = {}
            for subsec in database[section]:
                if section == 'servers':
                    subsec_mod = subsec.replace('[', '{').replace(']','}')
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
                if type(value) == type(True):
                    CFG[sec][kw] = str(int(value))
                elif type(value) == type(0):
                    CFG[sec][kw] = str(value)
                else:
                    CFG[sec][kw] = value

    res = False
    filename = CFG.filename
    bakname = filename + '.bak'

    # Check if file is writable
    if not sabnzbd.misc.is_writable(filename):
        logging.error(T('Cannot write to INI file %s'), filename)
        return res

    # copy current file to backup
    try:
        shutil.copyfile(filename, bakname)
    except:
        # Something wrong with the backup,
        logging.error(T('Cannot create backup file for %s'), bakname)
        logging.info("Traceback: ", exc_info = True)
        return res

    # Write new config file
    try:
        CFG.write()
        modified = False
        res = True
    except:
        logging.error(T('Cannot write to INI file %s'), filename)
        logging.info("Traceback: ", exc_info = True)
        try:
            os.remove(filename)
        except:
            pass
        # Restore INI file from backup
        sabnzbd.misc.renamer(bakname, filename)

    return res



def define_servers():
    """ Define servers listed in the Setup file
        return a list of ConfigServer instances
    """
    global CFG
    try:
        for server in CFG['servers']:
            svr = CFG['servers'][server]
            s = ConfigServer(server.replace('{', '[').replace('}', ']'), svr)
            if s.fillserver():
                # One time conversion of backup to priority 1
                s.priority.set(1)
                s.fillserver.set(False)
    except KeyError:
        pass

def get_servers():
    global database
    try:
        return database['servers']
    except KeyError:
        return {}


def define_categories(force=False):
    """ Define categories listed in the Setup file
        return a list of ConfigCat instances
    """
    global CFG, categories
    try:
        for cat in CFG['categories']:
            ConfigCat(cat, CFG['categories'][cat])
    except KeyError:
        pass


def old_def(item, default):
    """ Get old INI setting from [misc], if missing use 'default' """
    try:
        return CFG['misc'][item]
    except KeyError:
        return default


def get_categories(cat=0):
    """ Return link to categories section.
        This section will always contain special category '*'
        When 'cat' is given, a link to that category or to '*' is returned
    """
    global database
    if 'categories' not in database:
        database['categories'] = {}
    cats = database['categories']
    if '*' not in cats:
        ConfigCat('*', {'pp' : old_def('dirscan_opts', '3'), 'script' : old_def('dirscan_script', 'None'), \
                        'priority' : old_def('dirscan_priority', NORMAL_PRIORITY)})
        save_config(True)
    if not isinstance(cat, int):
        try:
            cats = cats[cat]
        except KeyError:
            cats = cats['*']
    return cats


def define_rss():
    """ Define rss-feeds listed in the Setup file
        return a list of ConfigRSS instances
    """
    global CFG
    try:
        for r in CFG['rss']:
            ConfigRSS(r, CFG['rss'][r])
    except KeyError:
        pass

def get_rss():
    global database
    try:
        return database['rss']
    except KeyError:
        return {}

def get_filename():
    global CFG
    return CFG.filename


################################################################################
#
# Default Validation handlers
#
__PW_PREFIX = '!!!encoded!!!'

#------------------------------------------------------------------------------
def encode_password(pw):
    """ Encode password in hexadecimal if needed """
    enc = False
    if pw:
        encPW = __PW_PREFIX
        for c in pw:
            cnum = ord(c)
            if c == '#' or cnum < 33 or cnum > 126:
                enc = True
            encPW += '%2x' % cnum
        if enc:
            return encPW
    return pw


def decode_password(pw, name):
    """ Decode hexadecimal encoded password
        but only decode when prefixed
    """
    decPW = ''
    if pw and pw.startswith(__PW_PREFIX):
        for n in range(len(__PW_PREFIX), len(pw), 2):
            try:
                ch = chr( int(pw[n] + pw[n+1], 16) )
            except ValueError:
                logging.error(T('Incorrectly encoded password %s'), name)
                return ''
            decPW += ch
        return decPW
    else:
        return pw


def no_nonsense(value):
    """ Strip and Filter out None and 'None' from strings """
    value = str(value).strip()
    if value.lower() == 'none':
        value = ''
    return None, value


def validate_octal(value):
    """ Check if string is valid octal number """
    if not value:
        return None, value
    try:
        int(value, 8)
        return None, value
    except:
        return T('%s is not a correct octal value') % value, None


def validate_no_unc(root, value, default):
    """ Check if path isn't a UNC path """
    # Only need to check the 'value' part
    if value and not value.startswith(r'\\'):
        return validate_notempty(root, value, default)
    else:
        return T('UNC path "%s" not allowed here') % value, None


def validate_safedir(root, value, default):
    """ Allow only when queues are empty and no UNC
        On Windows path should be 80 max
    """
    if sabnzbd.WIN32 and value and len(sabnzbd.misc.real_path(root, value)) > 80:
        return T('Error: Path length should be below 80.'), None
    if sabnzbd.empty_queues():
        return validate_no_unc(root, value, default)
    else:
        return T('Error: Queue not empty, cannot change folder.'), None


def validate_dir_exists(root, value, default):
    """ Check if directory exists """
    p = sabnzbd.misc.real_path(root, value)
    if os.path.exists(p):
        return None, value
    else:
        return T('Folder "%s" does not exist') % p, None


def validate_notempty(root, value, default):
    """ If value is empty, return default """
    if value:
        return None, value
    else:
        return None, default


def create_api_key():
    """ Return a new randomized API_KEY
    """
    import time
    try:
        from hashlib import md5
    except ImportError:
        from md5 import md5
    import random
    # Create some values to seed md5
    t = str(time.time())
    r = str(random.random())
    # Create the md5 instance and give it the current time
    m = md5(t)
    # Update the md5 instance with the random variable
    m.update(r)

    # Return a hex digest of the md5, eg 49f68a5c8493ec2c0bf489821c21fc3b
    return m.hexdigest()


#------------------------------------------------------------------------------
_FIXES = \
(
    ('enable_par_multicore', 'par2_multicore'),
)

def compatibility_fix(cf):
    """ Convert obsolete INI entries """
    for item in _FIXES:
        old, new = item
        try:
            cf[new]
        except KeyError:
            try:
                cf[new] = cf[old]
                del cf[old]
            except KeyError:
                pass
