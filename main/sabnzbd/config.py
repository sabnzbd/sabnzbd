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
from sabnzbd.utils import listquote
from sabnzbd.utils.configobj import ConfigObj, ConfigObjError


__CONFIG_VERSION = '18'     # Minumum INI file version required

CFG = {}                    # Holds INI structure
                            # uring re-write this variable is global allow
                            # direct access to INI structure

database = {}               # Holds the option dictionary

modified = False            # Signals a change in option dictionary
                            # Should be reset after saving to settings file


class Option:
    """ Basic option class, basic fields """
    def __init__(self, section, keyword, default_val=None):
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

    def __set(self, value):
        """ Set new value, no validation """
        global modified
        if (value != None) and (value != self.__value):
            self.__value = value
            modified = True
            if self.__callback:
                self.__callback()

    def set(self, value):
        self.__set(value)

    def callback(self, callback):
        """ Set callback function """
        self.__callback = callback
        
    def ident(self):
        """ Return section-list and keyword """
        return self.__sections, self.__keyword


class OptionNumber(Option):
    """ Numeric option class, int/float is determined from default value """
    def __init__(self, section, keyword, default_val=0, minval=None, maxval=None, validation=None):
        Option.__init__(self, section, keyword, default_val)
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
                self._Option__set(self.__validation(value, self.__minval, self.__maxval))
            else:
                if (self.__maxval != None) and value > self.__maxval:
                    value = self.__maxval
                elif (self.__minval != None) and value < self.__minval:
                    value = self.__minval
                self._Option__set(value)


    
class OptionBool(Option):
    """ Boolean option class """
    def __init__(self, section, keyword, default_val=False):
        Option.__init__(self, section, keyword, default_val)

    def set(self, value):
        if value == None:
            value = 0
        try:
            self._Option__set(bool(int(value)))
        except ValueError:
            self._Option__set(False)


class OptionDir(Option):
    """ Directory option class """
    def __init__(self, section, keyword, default_val='', root='', validation=None):
        if validation:
            self.__validation = validation
        else:
            self.__validation = std_dir_validation
        self.__root = root # Base directory for relative paths
        self.__path = ''   # Will contain absolute, normalized path
        Option.__init__(self, section, keyword, default_val)

    def get_path(self):
        """ Return full absolute path """
        return self.__path

    def set_root(self, root):
        """ Set new root, is assumed to be valid """
        self.__root = root

    def set(self, value):
        """ Set new dir value, validate and create if needed
            Return true when directory is accepted
            Return false when not accepted, value will not be changed
        """
        res = True
        if value != None:
            if self.__validation:
                res, value, path = self.__validation(self.__root, value)
                if not res:
                    print "log-problem-with-dir"
                    self._Option__set('')
                else:
                    self._Option__set(value)
                    self.__path = path
            else:
                self._Option__set(value)
        return res


class OptionList(Option):
    """ List option class """
    def __init__(self, section, keyword, default_val=None):
        if default_val == None:
            default_val = []
        Option.__init__(self, section, keyword, default_val)

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
        if txt != None:
            self._Option__set(listquote.simplelist(txt))


class OptionStr(Option):
    """ STring class """
    def __init__(self, section, keyword, default_val=''):
        Option.__init__(self, section, keyword, default_val)

    def set(self, value):
        """ Set stripped value """
        if type(value) == type(''):
            self._Option__set(value.strip())
        else:
            self._Option__set(value)

    
class OptionPassword(Option):
    """ Password class """
    def __init__(self, section, keyword, default_val=''):
        Option.__init__(self, section, keyword, default_val)

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
        if (pw and pw.strip('*')) or (pw and pw == ''):
            self._Option__set(encode_password(pw))


class ConfigServer:
    def __init__(self, name, values):

        self.__name = name
        name = 'servers,' + self.__name

        self.host = OptionStr(name, 'host', '')
        self.port = OptionNumber(name, 'port', 119, 0, 2**16-1)
        self.timeout = OptionNumber(name, 'timeout', 120, 30, 240)
        self.username = OptionStr(name, 'username', '')
        self.password = OptionPassword(name, 'password', '')
        self.connections = OptionNumber(name, 'connections', 1, 0, 100)
        self.fill_server = OptionBool(name, 'fill_server', False)
        self.ssl = OptionBool(name, 'ssl', False)
        self.enable = OptionBool(name, 'enable', True)

        self.set(values, all=True)

    def set(self, values, all=False):
        """ Set one or more fields, passed as dictionary """
        for kw in ('host', 'port', 'timeout', 'username', 'password', 'connections', 'fill_server', 'ssl', 'enable'):
            try:
                value = values[kw]
            except KeyError:
                if all:
                    value= None
                else:
                    continue
            exec 'self.%s.set(value)' % kw

    def delete(self):
        """ Remove from database """
        global database, modified
        del database['servers'][self.__name]
        modified = True
        del self

    def ident(self):
        return 'servers', self.__name


class ConfigCat:
    def __init__(self, name, values):

        self.__name = name
        name = 'categories,' + name

        self.pp = OptionNumber(name, 'pp', -1, -1, 3)
        self.script = OptionStr(name, 'script', 'Default')
        self.dir = OptionDir(name, 'dir')
        self.newzbin = OptionList(name, 'newzbin')
        self.priority = OptionNumber(name, 'priority')

        self.set(values, all=True)

    def set(self, values, all=False):
        """ Set one or more fields, passed as dictionary """
        for kw in ('pp', 'script', 'dir', 'newzbin', 'priority'):
            try:
                value = values[kw]
            except KeyError:
                if all:
                    value= None
                else:
                    continue
            exec 'self.%s.set(value)' % kw
    
    def delete(self):
        """ Remove from database """
        global database, modified
        del database['categories'][self.__name]
        modified = True
        del self

    def ident(self):
        return 'categories', self.__name


class ConfigRSS:
    def __init__(self, name, values):

        self.__name = name
        name = 'rss,' + name

        self.uri = OptionStr(name, 'uri')
        self.cat = OptionStr(name, 'cat')
        self.pp = OptionNumber(name, 'pp', -1, -1, 3)
        self.script = OptionStr(name, 'script')
        self.enable = OptionBool(name, 'enable')
        self.priority = OptionNumber(name, 'priority', 0, -1, 2)
        for kw in values:
            if kw.startswith('filter'):
                exec 'self.%s = OptionList(name, "%s")' % (kw, kw)

        self.set(values, all=True)

    def set(self, values, all=False):
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

        for kw in values:
            if kw.startswith('filter'):
                try:
                    exec 'self.%s.set(values["%s"])' % (kw, kw)
                except:
                    name = 'rss,' + self.__name
                    exec 'self.%s = OptionList(name, "%s")' % (kw, kw)
                    exec 'self.%s.set(values["%s"])' % (kw, kw)
            

    def delete(self):
        """ Remove from database """
        global database, modified
        del database['rss'][self.__name]
        modified = True
        del self

    def ident(self):
        return 'rss', self.__name




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
    global CFG, database, modified

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
        CFG = ConfigObj(path)
        try:
            if int(CFG['__version__']) > int(__CONFIG_VERSION):
                logging.error("[%s] Incorrect version number %s in %s", __NAME__, CFG['__version__'], path)
                return False
        except KeyError:
            CFG['__version__'] = __CONFIG_VERSION
        except ValueError:
            CFG['__version__'] = __CONFIG_VERSION
    except ConfigObjError, strerror:
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

    modified = False
    return True


def save_config(force=False):
    """ Update Setup file with current option values """
    global CFG, database, modified

    if not (modified or force):
        return True

    for section in database:
        if section in ('servers', 'categories', 'rss'):
            for subsec in sorted(database[section]):
                for option in database[section][subsec]:
                    sec, kw = database[section][subsec][option].ident()
                    sec = sec[-1]
                    try:
                        CFG[section][sec]
                    except:
                        CFG[section][sec] = {}
                    try:
                        CFG[section][subsec]
                    except:
                        CFG[section][subsec] = {}
                    CFG[section][subsec][kw] = database[section][subsec][option].get()
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
    save_config(force=True)


def define_servers():
    """ Define servers listed in the Setup file
        return a list of ConfigServer instances
    """
    global CFG
    servers = []
    name = 1
    try:
        for server in CFG['servers']:
            servers.append(ConfigServer('server%s' % name, CFG['servers'][server]))
            name += 1
    except KeyError:
        None
    return servers


def define_categories():
    """ Define categories listed in the Setup file
        return a list of ConfigCat instances
    """
    global CFG
    cats = []
    try:
        for cat in CFG['categories']:
            cats.append(ConfigCat(cat, CFG['categories'][cat]))
    except KeyError:
        None
    return cats
    

def define_rss():
    """ Define rss-ffeds listed in the Setup file
        return a list of ConfigRSS instances
    """
    global CFG
    rss = []
    try:
        for r in CFG['rss']:
            rss.append(ConfigRSS(r, CFG['rss'][r]))
    except KeyError:
        None
    return rss



################################################################################
#
# Default Validation handlers
#
__PW_PREFIX = '!!!encoded!!!'

def std_dir_validation(root, value):
    """ Standard directory validation """
    return True, value, os.path.join(root, value)

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
        for n in range(len(PW_PREFIX), len(pw), 2):
            try:
                ch = chr( int(pw[n] + pw[n+1],16) )
            except:
                logging.error('[%s] Incorrectly encoded password %s', __NAME__, name)
                return ''
            decPW += ch
        return decPW
    else:
        return pw
