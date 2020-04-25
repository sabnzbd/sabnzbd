#!/usr/bin/python3 -OO
# Copyright 2007-2020 The SABnzbd-Team <team@sabnzbd.org>
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
