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
sabnzbd.config - Configuration Support
"""
__NAME__ = "sabnzbd.config"

import os
import logging

import sabnzbd.misc
from sabnzbd.utils import listquote
from sabnzbd.utils import configobj



__CONFIG_VERSION = '18'     # Minumum INI file version required

CFG = {}                    # Holds INI structure
                            # uring re-write this variable is global allow
                            # direct access to INI structure

database = {}               # Holds the option dictionary

modified = False            # Signals a change in option dictionary
                            # Should be reset after saving to settings file


class Option:
    """ Basic option class, basic fields """
    def __init__(self, section, keyword, default_val=None, add=True):
        """ Basic option
            section     : single section or comma-separated list of sections
                          a list will be a hierarchy: "foo, bar" --> [foo][[bar]]
            keyword     : keyword in the (last) section
            default_val : value returned when no value has been set
            callback    : procedure to call when value is succesfully changed
        """
        self.__sections = section.split(',')
        self.__keyword = keyword
        self.__default_val = default_val
        self.__value = None
        self.__callback = None

        # Add myself to the config dictionary
        if add:
            global database
            anchor = database
            for section in self.__sections:
                if section not in anchor:
                    anchor[section] = {}
                anchor = anchor[section]
            anchor[keyword] = self

    def get(self):
        """ Retrieve value field """
        if self.__value != None:
            return self.__value
        else:
            return self.__default_val

    def get_dict(self):
        """ Return value a dictionary """
        return { 'value' : self.get() }

    def set_dict(self, dict):
        """ Set value based on dictionary """
        try:
            return self.set(dict['value'])
        except:
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

    def callback(self, callback):
        """ Set callback function """
        self.__callback = callback

    def ident(self):
        """ Return section-list and keyword """
        return self.__sections, self.__keyword



class OptionNumber(Option):
    """ Numeric option class, int/float is determined from default value """
    def __init__(self, section, keyword, default_val=0, minval=None, maxval=None, validation=None, add=True):
        Option.__init__(self, section, keyword, default_val, add=add)
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
            except:
                value = 0
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
    def __init__(self, section, keyword, default_val=False, add=True):
        Option.__init__(self, section, keyword, int(default_val), add=add)

    def set(self, value):
        if value == None:
            value = 0
        try:
            self._Option__set(int(value))
        except ValueError:
            self._Option__set(0)
        return None


class OptionDir(Option):
    """ Directory option class """
    def __init__(self, section, keyword, default_val='', apply_umask=False, create=True, validation=None, add=True):
        self.__validation = validation
        self.__root = ''   # Base directory for relative paths
        self.__apply_umask = apply_umask
        self.__create = create
        Option.__init__(self, section, keyword, default_val, add=add)

    def get_path(self):
        """ Return full absolute path """
        value = self.get()
        path = sabnzbd.misc.real_path(self.__root, value)
        if self.__create and not os.path.exists(path):
            res, path = sabnzbd.misc.create_real_path(self.ident()[1], self.__root, value, self.__apply_umask)
        return path

    def set_root(self, root):
        """ Set new root, is assumed to be valid """
        self.__root = root

    def set(self, value):
        """ Set new dir value, validate and create if needed
            Return None when directory is accepted
            Return error-string when not accepted, value will not be changed
        """
        error = None
        if value != None and value != self.get():
            if self.__validation:
                error, val = self.__validation(self.__root, value)
            if not error:
                if self.__create:
                    res, path = sabnzbd.misc.create_real_path(self.ident()[1], self.__root, value, self.__apply_umask)
                    if not res:
                        error = "Cannot create %s folder %s" % (self.ident()[1], path)
            if not error:
                self._Option__set(value)
        return error

class OptionList(Option):
    """ List option class """
    def __init__(self, section, keyword, default_val=None, add=True):
        if default_val == None:
            default_val = []
        Option.__init__(self, section, keyword, default_val, add=add)

    def set(self, value):
        """ Set value, convert single item to list of one """
        if value != None:
            if type(value) != type([]):
                value = [ value ]
            return self._Option__set(value)
        return None

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

    def set_string(self, txt):
        """ Set the list given a comma-separated string """
        if type(txt) == type(''):
            self._Option__set(listquote.simplelist(txt))
        else:
            self._Option__set(txt)


class OptionStr(Option):
    """ String class """
    def __init__(self, section, keyword, default_val='', validation=None, add=True):
        Option.__init__(self, section, keyword, default_val, add=add)
        self.__validation = validation

    def get_float(self):
        """ Return value converted to a float, allowing KMGT notation """
        return sabnzbd.misc.from_units(self.get())

    def set(self, value):
        """ Set stripped value """
        error = None
        if type(value) == type(''):
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

    def get(self):
        """ Return decoded password """
        value = self._Option__value
        if value == None:
            return self._Option__default_val
        else:
            return decode_password(value, self.ident())

    def get_stars(self):
        """ Return decoded password as asterisk string """
        return '*' * len(decode_password(self.get(), self.ident()))

    def set(self, pw):
        """ Set password, encode it """
        if (pw != None and pw == '') or (pw and pw.strip('*')):
            self._Option__set(encode_password(pw))
        return None


def add_to_database(section, keyword, object):
    global database
    if section not in database:
        database[section] = {}
    database[section][keyword] = object


def delete_from_database(section, keyword):
        global database, CFG, modified
        del database[section][keyword]
        try:
            del CFG[section][keyword]
        except KeyError:
            pass
        modified = True


class ConfigServer:
    """ Class defining a single server """
    def __init__(self, name, values):

        self.__name = name
        name = 'servers,' + self.__name

        self.host = OptionStr(name, 'host', '', add=False)
        self.port = OptionNumber(name, 'port', 119, 0, 2**16-1, add=False)
        self.timeout = OptionNumber(name, 'timeout', 120, 30, 240, add=False)
        self.username = OptionStr(name, 'username', '', add=False)
        self.password = OptionPassword(name, 'password', '', add=False)
        self.connections = OptionNumber(name, 'connections', 1, 0, 100, add=False)
        self.fillserver = OptionBool(name, 'fillserver', False, add=False)
        self.ssl = OptionBool(name, 'ssl', False, add=False)
        self.enable = OptionBool(name, 'enable', True, add=False)
        self.optional = OptionBool(name, 'optional', True, add=False)

        self.set_dict(values, all=True)
        add_to_database('servers', self.__name, self)

    def set_dict(self, values, all=False):
        """ Set one or more fields, passed as dictionary """
        for kw in ('host', 'port', 'timeout', 'username', 'password', 'connections',
                   'fillserver', 'ssl', 'enable', 'optional'):
            try:
                value = values[kw]
            except KeyError:
                if all:
                    value= None
                else:
                    continue
            exec 'self.%s.set(value)' % kw
        return True

    def get_dict(self):
        """ Return a dictionary with all attributes """
        dict = {}
        dict['host'] = self.host.get()
        dict['port'] = self.port.get()
        dict['timeout'] = self.timeout.get()
        dict['username'] = self.username.get()
        dict['password'] = self.password.get()
        dict['connections'] = self.connections.get()
        dict['fillserver'] = self.fillserver.get()
        dict['ssl'] = self.ssl.get()
        dict['enable'] = self.enable.get()
        dict['optional'] = self.optional.get()
        return dict

    def delete(self):
        """ Remove from database """
        delete_from_database('servers', self.__name)

    def ident(self):
        return 'servers', self.__name


class ConfigCat():
    """ Class defining a single category """
    def __init__(self, name, values):
        self.__name = name
        name = 'categories,' + name

        self.pp = OptionStr(name, 'pp', '', add=False)
        self.script = OptionStr(name, 'script', 'Default', add=False)
        self.dir = OptionDir(name, 'dir', add=False, create=False)
        self.newzbin = OptionList(name, 'newzbin', add=False)
        self.priority = OptionNumber(name, 'priority', add=False)

        self.set_dict(values, all=True)
        add_to_database('categories', self.__name, self)

    def set_dict(self, values, all=False):
        """ Set one or more fields, passed as dictionary """
        for kw in ('pp', 'script', 'dir', 'newzbin', 'priority'):
            try:
                value = values[kw]
            except KeyError:
                if all:
                    value= None
                else:
                    continue
            if kw == 'newzbin':
                exec 'self.%s.set_string(value)' % kw
            else:
                exec 'self.%s.set(value)' % kw
        return True
    
    def get_dict(self):
        """ Return a dictionary with all attributes """
        dict = {}
        dict['pp'] = self.pp.get()
        dict['script'] = self.script.get()
        dict['dir'] = self.dir.get()
        dict['newzbin'] = self.newzbin.get_string()
        dict['priority'] = self.priority.get()
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

    def get_dict(self):
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
        n = 0
        for kw in sorted(values.keys()):
            if kw.startswith('filter'):
                val = values[kw]
                if type(val) == type([]):
                    filters.append(val)
                else:
                    filters.append(listquote.simplelist(val))
                n = n + 1
        if n > 0:
            self.set(filters)


class ConfigRSS:
    """ Class defining a single Feed definition """
    def __init__(self, name, values):
        self.__name = name
        name = 'rss,' + name

        self.uri = OptionStr(name, 'uri', add=False)
        self.cat = OptionStr(name, 'cat', add=False)
        self.pp = OptionStr(name, 'pp', '', add=False)
        self.script = OptionStr(name, 'script', add=False)
        self.enable = OptionBool(name, 'enable', add=False)
        self.priority = OptionNumber(name, 'priority', 0, -1, 2, add=False)
        self.filters = OptionFilters(name, 'filters', add=False)
        self.filters.set([['', '', '', 'A', '*']])

        self.set_dict(values, all=True)
        add_to_database('rss', self.__name, self)

    def set_dict(self, values, all=False):
        """ Set one or more fields, passed as dictionary """
        for kw in ('uri', 'cat', 'pp', 'script', 'priority'):
            try:
                value = values[kw]
            except KeyError:
                if all:
                    value= None
                else:
                    continue
            exec 'self.%s.set(value)' % kw

        self.filters.set_dict(values)
        return True

    def get_dict(self):
        """ Return a dictionary with all attributes """
        dict = {}
        dict['uri'] = self.uri.get()
        dict['cat'] = self.cat.get()
        dict['pp'] = self.pp.get()
        dict['script'] = self.script.get()
        dict['enable'] = self.enable.get()
        dict['priority'] = self.priority.get()
        filters = self.filters.get_dict()
        for kw in filters:
            dict[kw] = filters[kw]
        return dict

    def delete(self):
        """ Remove from database """
        delete_from_database('rss', self.__name)

    def ident(self):
        return 'rss', self.__name



def find_item(args):
    """ Find config item based on 'section', 'keyword'
    """
    try:
        section = args['section']
        keyword = args['keyword']
    except:
        return None

    try:
        return database[section][keyword]
    except KeyError:
        return None


def get_dconfig(kwargs):
    """ Return a config values dictonary,
        based on dictionary with 'section', 'keyword'
    """
    item = find_item(kwargs)
    if item:
        return True, item.get_dict()
    else:
        return False, {}


def get_config(section, keyword):
    """ Return a config object, based on 'section', 'keyword'
    """
    try:
        item = database[section][keyword]
    except KeyError:
        item = None
        logging.exception('[%s], Missing configuration item %s,%s', __NAME__, section, keyword)

    return item


def set_config(kwargs):
    """ Set a config item, using values in dictionary
    """
    item = find_item(kwargs)
    if item:
        return item.set_dict(kwargs)
    else:
        return False


def delete(section, keyword):
    """ Delete specific config item
    """
    try:
        item = database[section][keyword]
        item.delete()
    except KeyError:
        return


################################################################################
#
# INI file support
#
# This does input and output of configuration to an INI file.
# It translates this data structure to the config database.


def read_config(path):
    """ Read the complete INI file and check its version number
        if OK, pass values to config-database
    """
    global CFG, database, categories, rss_feeds, servers, modified

    if not os.path.exists(path):
        # No file found, create default INI file
        try:
            fp = open(path, "w")
            fp.write("__version__=%s\n[misc]\n[logging]\n" % __CONFIG_VERSION)
            fp.close()
        except IOError:
            logging.error("[%s] Cannot create Config file %s", __NAME__, path)
            return False

    try:
        CFG = configobj.ConfigObj(path)
        try:
            if int(CFG['__version__']) > int(__CONFIG_VERSION):
                logging.error("[%s] Incorrect version number %s in %s", __NAME__, CFG['__version__'], path)
                return False
        except KeyError:
            CFG['__version__'] = __CONFIG_VERSION
        except ValueError:
            CFG['__version__'] = __CONFIG_VERSION
    except configobj.ConfigObjError, strerror:
        logging.error("[%s] Invalid Config file %s", __NAME__, path)
        return False

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

    categories = define_categories()
    rss_feeds = define_rss()
    servers = define_servers()

    modified = False
    return True


def save_config(force=False):
    """ Update Setup file with current option values """
    global CFG, database, modified

    if not (modified or force):
        return True

    for section in database:
        if section in ('servers', 'categories', 'rss'):
            try:
                CFG[section]
            except:
                CFG[section] = {}
            for subsec in database[section]:
                try:
                    CFG[section][subsec]
                except:
                    CFG[section][subsec] = {}
                items = database[section][subsec].get_dict()
                for item in items:
                    CFG[section][subsec][item] = items[item]
        else:
            for option in database[section]:
                sec, kw = database[section][option].ident()
                sec = sec[-1]
                try:
                    CFG[sec]
                except:
                    CFG[sec] = {}
                value = database[section][option].get()
                if type(value) == type(True):
                    CFG[sec][kw] = str(int(value))
                elif type(value) == type(0):
                    CFG[sec][kw] = str(value)
                else:
                    CFG[sec][kw] = value

    try:
        CFG.write()
        f = open(CFG.filename)
        x = f.read()
        f.close()
        f = open(CFG.filename, "w")
        f.write(x)
        f.flush()
        f.close()
        modified = False
        return True
    except IOError:
        return False


def save_configfile(dummy):
    """ Backwards compatible version, forced save """
    if not save_config(force=True):
        sabnzbd.misc.Panic('Cannot write to configuration file "%s".' % config.filename, \
              'Make sure file is writable and in a writable folder.')
        sabnzbd.misc.ExitSab(2)


def define_servers():
    """ Define servers listed in the Setup file
        return a list of ConfigServer instances
    """
    global CFG
    try:
        for server in CFG['servers']:
            svr = CFG['servers'][server]
            ConfigServer(server, svr)
    except KeyError:
        pass

def get_servers():
    global database
    try:
        return database['servers']
    except:
        return {}


def define_categories():
    """ Define categories listed in the Setup file
        return a list of ConfigCat instances
    """
    global CFG, categories
    cats = ['Unknown', 'Anime', 'Apps', 'Books', 'Consoles', 'Emulation', 'Games',
            'Misc', 'Movies', 'Music', 'PDA', 'Resources', 'TV']

    try:
        for cat in CFG['categories']:
            ConfigCat(cat, CFG['categories'][cat])
    except KeyError:
        for cat in cats:
            val = { 'newzbin' : cat, 'dir' : cat }
            ConfigCat(cat.lower(), val)

def get_categories():
    global database
    try:
        return database['categories']
    except:
        return {}

def define_rss():
    """ Define rss-ffeds listed in the Setup file
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
    except:
        return {}



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
            if c == '#' or cnum<33 or cnum>126:
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
                ch = chr( int(pw[n] + pw[n+1],16) )
            except:
                logging.error('[%s] Incorrectly encoded password %s', __NAME__, name)
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
        return '%s is not a correct octal value' % value, None


def validate_no_unc(root, value):
    """ Check if path isn't a UNC path """
    # Only need to check the 'value' part
    if value and not value.startswith(r'\\'):
        return None, value
    else:
        return 'UNC path %s not allowed here' % value, None


def validate_safedir(root, value):
    """ Allow only when queues are empty and no UNC """
    if sabnzbd.empty_queues():
        return validate_no_unc(root, value)
    else:
        return 'Error: Queue not empty, cannot change folder.', None
