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
tests.test_utils - Testing sabnzdb utils
"""

from sabnzbd.utils.certgen import generate_key, generate_local_cert


class TestCertGen:
    def test_generate_key(self):
        # Generate private key
        private_key = generate_key()

        assert private_key.key_size == 2048

    def test_generate_local_cert(self):
        # Generate private key
        private_key = generate_key()
        # Generate local certificate using private key
        local_cert = generate_local_cert(private_key)

        assert local_cert

