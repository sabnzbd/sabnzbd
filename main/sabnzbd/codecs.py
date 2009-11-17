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
sabnzbd.codecs - Unicoded filename support
"""

import os
import sys
import locale
from xml.sax.saxutils import escape
from Cheetah.Filters import Filter

import sabnzbd

try:
    gUTF = locale.getdefaultlocale()[1].lower().find('utf') >= 0
except:
    # Incorrect locale implementation, assume the worst
    gUTF = False

def reliable_unpack_names():
    """ See if it is safe to rely on unrar names """
    if sabnzbd.WIN32 or sabnzbd.DARWIN:
        return True
    else:
        return gUTF

def name_fixer(p):
    """ Return UTF-8 encoded string, if appropriate for the platform """

    if sabnzbd.DARWIN:
        return p.decode('Latin-1', 'replace').encode('utf-8', 'replace').replace('?', '_')
    else:
        return p

def special_fixer(p):
    """ Return string appropriate for the platform.
        Also takes care of the situation where a non-Windows/UTF-8 system
        receives a latin-1 encoded name.
    """
    if sabnzbd.WIN32:
        return p
    else:
        if gUTF or sabnzbd.DARWIN:
            try:
                # First see if it isn't just UTF-8
                p.decode('utf-8')
                return p
            except:
                # Now assume it's latin-1
                return p.decode('Latin-1').encode('utf-8')
        else:
            return p

def unicoder(p):
    """ Make sure a Unicode string is returned """
    if isinstance(p, unicode):
        return p
    if isinstance(p, str):
        if sabnzbd.DARWIN or gUTF:
            try:
                return p.decode('utf-8')
            except:
                return p.decode('latin-1', 'replace')
        return p.decode('latin-1', 'replace')
    else:
        return unicode(str(p))

def unicode2local(p):
    """ Convert Unicode filename to appropriate local encoding
    """
    if sabnzbd.WIN32:
        return p.encode('Latin-1', 'replace').replace('?', '_')
    else:
        return p.encode('utf-8', 'replace').replace('?', '_')


def xml_name(p, keep_escape=False, encoding=None):
    """ Prepare name for use in HTML/XML contect """

    if isinstance(p, unicode):
        pass
    elif isinstance(p, str):
        if sabnzbd.DARWIN or encoding == 'utf-8':
            p = p.decode('utf-8', 'replace')
        elif gUTF:
            p = p.decode('utf-8', 'replace')
        else:
            p = p.decode('Latin-1', 'replace')
    else:
        p = str(p)

    if keep_escape:
        return p.encode('ascii', 'xmlcharrefreplace')
    else:
        return escape(p).encode('ascii', 'xmlcharrefreplace')



def encode_for_xml(ustr, encoding='ascii'):
    """
    Encode unicode_data for use as XML or HTML, with characters outside
    of the encoding converted to XML numeric character references.
    """
    if isinstance(ustr, unicode):
        pass
    elif isinstance(ustr, str):
        ustr = ustr.decode('Latin-1', 'replace')
    else:
        ustr = unicode(str(ustr))
    return ustr.encode(encoding, 'xmlcharrefreplace')


def titler(p):
    """ title() replacement
        Python's title() fails with Latin-1, so use Unicode detour.
    """
    if gUTF:
        try:
            return p.decode('utf-8').title().encode('utf-8')
        except:
            return p.decode('latin-1', 'replace').title().encode('latin-1', 'replace')
    else:
        return p.decode('latin-1', 'replace').title().encode('latin-1', 'replace')


class LatinFilter(Filter):
    """ Make sure Cheetah gets only Unicode strings """
    def filter(self, val,
               str=str,
               **kw):
        if isinstance(val, unicode):
            return val
        elif isinstance(val, basestring):
            return val.decode('latin-1', 'replace')
        elif val is None:
            return ''
        else:
            return str(val)


################################################################################
#
# Map CodePage-850 characters to Python's pseudo-Unicode 8bit ASCII
#
# Use to transform 8-bit console output to plain Python strings
#
import string
gTABLE850 = string.maketrans(
    "\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8A\x8B\x8C\x8D\x8E\x8F"
    "\x90\x91\x92\x93\x94\x95\x96\x97\x98\x99\x9A\x9B\x9C\x9D\x9E\x9F"
    "\xA0\xA1\xA2\xA3\xA4\xA5\xA6\xA7\xA8\xA9\xAA\xAB\xAC\xAD\xAE\xAF"
    "\xB0\xB1\xB2\xB3\xB4\xB5\xB6\xB7\xB8\xB9\xBA\xBB\xBC\xBD\xBE\xBF"
    "\xC0\xC1\xC2\xC3\xC4\xC5\xC6\xC7\xC8\xC9\xCA\xCB\xCC\xCD\xCE\xCF"
    "\xD0\xD1\xD2\xD3\xD4\xD5\xD6\xD7\xD8\xD9\xDA\xDB\xDC\xDD\xDE\xDF"
    "\xE0\xE1\xE2\xE3\xE4\xE5\xE6\xE7\xE8\xE9\xEA\xEB\xEC\xED\xEE\xEF"
    "\xF0\xF1\xF2\xF3\xF4\xF5\xF6\xF7\xF8\xF9\xFA\xFB\xFC\xFD\xFE\xFF" ,

    "\xC7\xFC\xE9\xE2\xE4\xE0\xE5\xE7\xEA\xEB\xE8\xEF\xEE\xEC\xC4\xC5"
    "\xC9\xE6\xC6\xF4\xF6\xF2\xFB\xF9\xFF\xD6\xDC\xF8\xA3\xD8\xD7\x66"
    "\xE1\xED\xF3\xFA\xF1\xD1\xAA\xBA\xBF\xAE\xAC\xDB\xBC\xA1\xAB\xBB"
    "\x7E\x7E\x7E\x7E\x7E\xC1\xC2\xC0\xA9\x7E\x7E\x7E\x7E\xA2\xA5\x7E"
    "\x7E\x7E\x7E\x7E\x7E\x7E\xE3\xc3\x7E\x7E\x7E\x7E\x7E\x7E\x7E\xA4"
    "\xF0\xD0\xCA\xCB\xC8\x7E\xCD\xCE\xCF\x7E\x7E\x7E\x7E\xA6\xCC\x7E"
    "\xD3\xDF\xD4\xD2\xF5\xD5\xB5\xFE\xDE\xDA\xDB\xD9\xFD\xDD\xAF\xB4"
    "\xAD\xB1\x5F\xBE\xB6\xA7\xF7\xB8\xB0\xA8\xB7\xB9\xB3\xB2\x7E\xA0" )


def TRANS(p):
    """ For Windows: Translate CP850 to Python's Latin-1
    """
    global gTABLE850
    if sabnzbd.WIN32:
        return p.translate(gTABLE850)
    else:
        return p
