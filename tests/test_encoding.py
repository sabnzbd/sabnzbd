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
tests.test_misc - Testing functions in encoding.py
"""

import sabnzbd.encoding as enc


class TestEncoding:
    def test_correct_unknown_encoding(self):
        # Windows encoding in bytes
        assert "frènch_german_demö" == enc.correct_unknown_encoding(b"fr\xe8nch_german_dem\xf6")
        # Windows encoding in string that's already UTF8
        assert "demotöwers" == enc.correct_unknown_encoding("demot\udcf6wers")

    def test_correct_cherrypy_encoding(self):
        raw_input = "aaazzz"  # correct UTF8
        corrected_output = enc.correct_cherrypy_encoding(raw_input)
        assert corrected_output == "aaazzz"

        # typical use code: raw chars in a string: 4-byte UTF8
        raw_input = "aaa" + chr(0xF0) + chr(0x9F) + chr(0x9A) + chr(0x80) + "zzz"  # "correct" 4-byte UTF8 for "rocket"
        corrected_output = enc.correct_cherrypy_encoding(raw_input)
        assert corrected_output == "aaa🚀zzz"

        # typical use code: raw chars in a string: 2-byte UTF8
        # Ω (capital omega) in UTF8: 0xCE 0xA9
        raw_input = "aaa" + chr(0xCE) + chr(0xA9) + "zzz"  # Ω (capital omega)
        corrected_output = enc.correct_cherrypy_encoding(raw_input)
        assert corrected_output == "aaaΩzzz"

        nice_utf8_string = "aaa你好🚀🤔zzzαβγ"  # correct UTF8
        # now break it
        raw_input = ""
        for i in nice_utf8_string.encode("utf-8"):
            raw_input += chr(i)
        assert raw_input != nice_utf8_string
        corrected_output = enc.correct_cherrypy_encoding(raw_input)
        assert corrected_output == nice_utf8_string

        # this is not UTF8, so string cannot be repaired, so stay the same
        raw_input = "aaa" + chr(0xF0) + chr(0x9F) + "zzz"  # two bytes ... not valid UTF8
        corrected_output = enc.correct_cherrypy_encoding(raw_input)
        assert corrected_output == raw_input  # check nothing changed
