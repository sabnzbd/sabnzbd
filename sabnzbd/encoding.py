#!/usr/bin/python3 -OO
# Copyright 2007-2022 The SABnzbd-Team <team@sabnzbd.org>
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
import chardet
from xml.sax.saxutils import escape
from typing import AnyStr

CODEPAGE = locale.getpreferredencoding()


def utob(str_in: AnyStr) -> bytes:
    """Shorthand for converting UTF-8 string to bytes"""
    if isinstance(str_in, bytes):
        return str_in
    return str_in.encode("utf-8")


def ubtou(str_in: AnyStr) -> str:
    """Shorthand for converting unicode bytes to UTF-8 string"""
    if not isinstance(str_in, bytes):
        return str_in
    return str_in.decode("utf-8")


def platform_btou(str_in: AnyStr) -> str:
    """Return Unicode string, if not already Unicode, decode with locale encoding.
    NOTE: Used for POpen because universal_newlines/text parameter doesn't
    always work! We cannot use encoding-parameter because it's Python 3.7+
    """
    if isinstance(str_in, bytes):
        try:
            return ubtou(str_in)
        except UnicodeDecodeError:
            return str_in.decode(CODEPAGE, errors="replace").replace("?", "!")
    else:
        return str_in


def correct_unknown_encoding(str_or_bytes_in: AnyStr) -> str:
    """Files created on Windows but unpacked/repaired on
    linux can result in invalid filenames. Try to fix this
    encoding by going to bytes and then back to unicode again.
    Last resort we use chardet package
    """
    # If already string, back to bytes
    if not isinstance(str_or_bytes_in, bytes):
        str_or_bytes_in = str_or_bytes_in.encode("utf-8", "surrogateescape")

    # Try simple bytes-to-string
    try:
        return ubtou(str_or_bytes_in)
    except UnicodeDecodeError:
        try:
            # Try using 8-bit ASCII, if came from Windows
            return str_or_bytes_in.decode("ISO-8859-1")
        except ValueError:
            # Last resort we use the slow chardet package
            return str_or_bytes_in.decode(chardet.detect(str_or_bytes_in)["encoding"])


def correct_cherrypy_encoding(somestring: str) -> str:
    """convert somestring with seperate, individual chars (1-255) to valid string (with UTF8 encoding)"""
    try:
        correctedstring = somestring.encode("raw_unicode_escape").decode("utf8")
    except:
        # not possible to convert to UTF8, so don't change anything:
        correctedstring = somestring
    return correctedstring


def xml_name(input_value) -> str:
    """Prepare name for use in HTML/XML context"""
    if input_value is not None:
        return escape(str(input_value))
    return ""
