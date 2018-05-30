#!/usr/bin/python -OO
# Copyright 2007-2018 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.encoding - Unicoded filename support
"""

import locale
import string
from xml.sax.saxutils import escape
from Cheetah.Filters import Filter

import sabnzbd

gUTF = False


def auto_fsys():
    global gUTF
    try:
        if sabnzbd.DARWIN:
            gUTF = True
        else:
            gUTF = locale.getdefaultlocale()[1].lower().find('utf') >= 0
    except:
        # Incorrect locale implementation, assume the worst
        gUTF = False


def change_fsys(value):
    global gUTF
    if not sabnzbd.WIN32 and not sabnzbd.DARWIN:
        if value == 1:
            gUTF = False
        elif value == 2:
            gUTF = True
        else:
            auto_fsys()


def platform_encode(p):
    return p
    """ Return Unicode name, if not already Unicode, decode with UTF-8 or latin1 """
    if isinstance(p, str):
        try:
            return p.decode('utf-8')
        except:
            return p.decode(codepage, errors='replace').replace('?', '!')
    else:
        return p


def yenc_name_fixer(p):
    """ Return Unicode name of 8bit ASCII string, first try utf-8, then cp1252 """
    try:
        return p.decode('utf-8')
    except:
        return p.decode('cp1252', errors='replace').replace('?', '!')


def special_fixer(p):
    """ Return string appropriate for the platform.
        Also takes care of the situation where a non-Windows/UTF-8 system
        receives a latin-1 encoded name.
    """
    if p:
        # Remove \" constructions from incoming headers
        p = p.replace(r'\"', r'"')
    if not p or isinstance(p, str):
        return p
    try:
        # First see if it isn't just UTF-8
        p.decode('utf-8')
        if sabnzbd.DARWIN and '&#' in p:
            p = fixup_ff4(p)
        return p.decode('utf-8')
    except:
        # Now assume it's 8bit ASCII
        return p.decode(codepage)


def unicoder(p, force=False):
    return p
    """ Make sure a Unicode string is returned
        When `force` is True, ignore filesystem encoding
    """
    if isinstance(p, str):
        return p
    if isinstance(p, str):
        if gUTF or force:
            try:
                return p.decode('utf-8')
            except:
                return p.decode(codepage, 'replace')
        return p.decode(codepage, 'replace')
    else:
        return str(str(p))


def xml_name(p, keep_escape=False, encoding=None):
    return p
    """ Prepare name for use in HTML/XML contect """

    if isinstance(p, str):
        pass
    elif isinstance(p, str):
        if sabnzbd.DARWIN or encoding == 'utf-8':
            p = p.decode('utf-8', 'replace')
        elif gUTF:
            p = p.decode('utf-8', 'replace')
        else:
            p = p.decode(codepage, 'replace')
    else:
        p = str(p)

    if keep_escape:
        return p.encode('ascii', 'xmlcharrefreplace')
    else:
        return escape(p).encode('ascii', 'xmlcharrefreplace')


class LatinFilter(Filter):
    """ Make sure Cheetah gets only Unicode strings """

    def filter(self, val, str=str, **kw):
        if isinstance(val, str):
            return val
        else:
            return str(val)


class EmailFilter(Filter):
    """ Make sure Cheetah gets only Unicode strings
        First try utf-8, then 8bit ASCII
    """

    def filter(self, val, str=str, **kw):
        return val


        if isinstance(val, str):
            return val
        elif isinstance(val, str):
            try:
                return val.decode('utf-8')
            except:
                return val.decode(codepage, 'replace')
        elif val is None:
            return ''
        else:
            return str(str(val))


################################################################################
#
# Map CodePage-850 characters to Python's pseudo-Unicode 8bit ASCII
# Use to transform 8-bit console output to plain Python strings
# For example for unrar and par2 output
#



def TRANS(p):
    return p
    """ For Windows: Translate CP850 to Python's Latin-1 and return in Unicode
        Others: return original string
    """
    if sabnzbd.WIN32:
        if p:
            return p.translate(string.maketrans(TAB_850, TAB_LATIN)).decode('cp1252', 'replace')
        else:
            # translate() fails on empty or None strings
            return ''
    else:
        return unicoder(p)


def UNTRANS(p):
    return p
    """ For Windows: Translate Python's Latin-1 to CP850
        Others: return original string
    """
    global gTABLE_LATIN_850
    if sabnzbd.WIN32:
        if p:
            return p.encode('cp1252', 'replace').translate(gTABLE_LATIN_850)
        else:
            # translate() fails on empty or None strings
            return ''
    else:
        return p


def fixup_ff4(p):
    return p
    """ Fix incompatibility between CherryPy and Firefox-4 on OSX,
        where a filename contains &#xx; encodings
    """
    name = []
    num = 0
    start = amp = False
    for ch in p:
        if start:
            if ch.isdigit():
                num += ch
            elif ch == ';':
                name.append(chr(int(num)).encode('utf8'))
                start = False
            else:
                name.append('&#%s%s' % (num, ch))
                start = False
        elif ch == '&':
            amp = True
        elif amp:
            amp = False
            if ch == '#':
                start = True
                num = ''
            else:
                name.append('&' + ch)
        else:
            name.append(ch)
    return ''.join(name)


_HTML_TABLE = {
    #'&' : '&amp;', # Not yet, texts need to be cleaned from HTML first
    #'>' : '&gt;',  # Not yet, texts need to be cleaned from HTML first
    #'<' : '&lt;',  # Not yet, texts need to be cleaned from HTML first
    '"': '&quot;',
    "'": '&apos;'
}


def html_escape(txt):
    """ Replace HTML metacharacters with &-constructs """
    # Replacement for inefficient xml.sax.saxutils.escape function
    if any(ch in txt for ch in _HTML_TABLE):
        return ''.join((_HTML_TABLE.get(ch, ch) for ch in txt))
    else:
        return txt


def deunicode(p):
    return p
    """ Return the correct 8bit ASCII encoding for the platform:
        Latin-1 for Windows/Posix-non-UTF and UTF-8 for OSX/Posix-UTF
    """
    if isinstance(p, str):
        if gUTF:
            return p.encode('utf-8')
        else:
            return p.encode(codepage, 'replace')
    elif isinstance(p, str):
        if gUTF:
            try:
                p.decode('utf-8')
                return p
            except:
                return p.decode(codepage).encode('utf-8')
        else:
            try:
                return p.decode('utf-8').encode(codepage, 'replace')
            except:
                return p
    else:
        return str(p)


def utob(str_in):
    """ Shorthand for converting UTF-8 to bytes """
    return str_in.encode('utf-8')


def ubtou(str_in):
    """ Shorthand for converting unicode bytes to UTF-8 """
    return str_in.decode('utf-8')

