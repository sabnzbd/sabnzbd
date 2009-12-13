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
sabnzbd.lang - Language support
"""

# Skin-specific files cannot overrule previous texts.
# Every acronym will be prexifed with the skin name ("skin-").
# This is required, because two skins can be active at once.


import os
import glob
import logging
import re
import operator

_T = {}        # Global language dictionary
_DIRS = []     # List of active (language-folder, prefix) tuples

def T(txt):
    """ Translate an acronym to natural language """
    try:
        return _T[txt]
    except KeyError:
        # Missing text: create text from acronym with %s attached
        txt, num = _get_count(txt)
        return '#' + txt + '#' + ' %s'*num


def Ta(txt):
    """ Translate acronym, return  latin-1 encoding """
    return T(txt).encode('latin-1', 'replace')


def Tspec(txt):
    """ Translate special terms """
    if txt == 'None':
        return T('none')
    elif txt == 'Default':
        return T('default')
    else:
        return txt


def reset_language(language):
    """ Process active language folders with new language """
    # First fill the new dictionary and afterwards
    # replace the global one. This way there will
    # always be a valid dictionary available.
    global _T, _DIRS
    new_T = {}
    dirs = _DIRS
    _DIRS = []
    for tup in dirs:
        install_language(tup[0], language, tup[1], new_T)
    old = _T
    _T = new_T
    del old


def install_language(path, language, prefix='', dic=None):
    """ Read language file for the active language
        and default language.
    """
    # 'dic' parameter is for internal use by 'reset_language' only
    global _DIRS
    _DIRS.append((path, prefix))

    if dic is None:
        dic = _T
    if language != 'us-en':
        name = os.path.join(path, language+'.txt')
        if os.path.exists(name):
            _parse_lang_file(dic, name, prefix)

    name = os.path.join(path, 'us-en.txt')
    if os.path.exists(name):
        _parse_lang_file(dic, name, prefix)


def list_languages(path):
    """ Return list of languages-choices
        Each choice is a list, 0: short name, 1: long name
    """
    lst = []
    for name in glob.glob(path + '/*.txt'):
        lang = os.path.basename(name).replace('.txt','')
        try:
            fp = open(name, 'r')
        except IOError:
            continue

        encoding, language = _get_headers(fp)
        long_name = u"%s" % language
        lst.append((lang, long_name))
        fp.close()
    return sorted(lst ,key=operator.itemgetter(1))



# Matches : acronym     message text # comment
#          | (1)   |(2)|     (3)     |
_RE_LINE = re.compile(r'\s*(\S+)(\s*)([^#]*)')

def _parse_lang_file(dic, name, prefix=''):
    """ Parse language file and store new definitions in global dictionary
    """
    try:
        f = open(name, "r")
    except IOError:
        logging.error("Cannot open language file %s", name)
        return False

    encoding, language = _get_headers(f)
    logging.debug("Language file %s, encoding=%s, language=%s",
                  name, encoding, language)

    if prefix:
        prefix += '-'
    lcount = 0
    multi = False
    msg = ''
    for line in f.xreadlines():
        line = line.strip('\n').decode(encoding)
        lcount += 1
        m = re.search(_RE_LINE, line)
        if m and not m.group(1).startswith('#'):
            if multi:
                if msg.endswith('\\n') or msg.endswith('\\r'):
                    msg = msg + m.group(1) + m.group(2) + m.group(3)
                else:
                    msg = msg + " " + m.group(1) + m.group(2) + m.group(3)
            else:
                key = prefix + m.group(1)
                msg = m.group(3)
            if msg and msg.strip().endswith("\\"):
                msg = msg.strip().strip("\\")
                multi = True
            else:
                multi = False
                msg = msg.strip()
                if '\\' in msg:
                    msg = msg.replace('\\n', '<br />').replace('\\t', '\t').replace('\\@', '#').replace('\s', ' ').replace('\\r','\r\n')
                if key not in dic:
                    if msg.count('%s') == _get_count(key)[1]:
                        dic[key] = msg
                    else:
                        logging.error("[%s:%s] Incorrect message for %s, should have %s parameters",
                                      name, lcount, key, _get_count(key)[1])


    f.close()
    return True


def _get_headers(fp):
    """ Return encoding and language
        # -*- coding: latin-1 -*-
        # English (UK) # remarks
    """
    txt = fp.readline()
    m = re.search(r'#\s*-\*-\s+coding:\s+(\S+)\s+-\*-', txt)
    if m and m.group(1):
        encoding = m.group(1)
    else:
        encoding = 'latin-1'

    txt = fp.readline()
    m = re.search(r'#\s*([^#]+)#*', txt)
    if m:
        language = m.group(1).strip().decode(encoding)
    else:
        language = ''

    return encoding, language


_RE_COUNT = re.compile(r'(\S+)@(\d+)')
def _get_count(txt):
    """ Return base key and counter
        "CopyFile@2" --> "CopyFile", 2
        "Stop" --> "Stop", 0
    """
    m = re.search(_RE_COUNT, txt)
    if m and m.group(2).isdigit():
        return m.group(1), int(m.group(2))
    else:
        return txt, 0
