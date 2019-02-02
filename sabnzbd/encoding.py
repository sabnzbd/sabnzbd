#!/usr/bin/python3 -OO
# Copyright 2007-2019 The SABnzbd-Team <team@sabnzbd.org>
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
sabnzbd.encoding - Unicode/byte translation functions
"""

import locale
from xml.sax.saxutils import escape


CODEPAGE = locale.getpreferredencoding()


def utob(str_in):
    """ Shorthand for converting UTF-8 to bytes """
    if isinstance(str_in, bytes):
        return str_in
    return str_in.encode('utf-8')


def ubtou(str_in):
    """ Shorthand for converting unicode bytes to UTF-8 """
    if not isinstance(str_in, bytes):
        return str_in
    return str_in.decode('utf-8')


def platform_btou(str_in):
    """ Return Unicode, if not already Unicode, decode with locale encoding.
        NOTE: Used for POpen because universal_newlines/text parameter doesn't
        always work! We cannot use encoding-parameter because it's Python 3.7+
    """
    if isinstance(str_in, bytes):
        try:
            return ubtou(str_in)
        except UnicodeDecodeError:
            return str_in.decode(CODEPAGE, errors='replace').replace('?', '!')
    else:
        return str_in


def correct_unknown_encoding(str_in):
    """ Files created on Windows but unpacked/repaired on
        linux can result in invalid filenames. Try to fix this
        encoding by going to bytes and then back to unicode again.
    """
    try:
        return str_in.encode('utf-8', 'surrogateescape').decode('ISO-8859-1')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # TODO: Use chardet-package?
        return str_in


def xml_name(p):
    """ Prepare name for use in HTML/XML contect """
    return escape(str(p))


