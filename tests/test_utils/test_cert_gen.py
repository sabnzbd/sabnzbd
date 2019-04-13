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
from cryptography.hazmat.primitives.asymmetric import rsa
import OpenSSL
import datetime
import os.path
import pytest

class TestCertGen:

    def test_generate_key_default(self):
        # Generate private key with default key_size and file name
        private_key = generate_key()
        assert private_key.key_size == 2048

    @pytest.mark.parametrize('key_size, file_name',
            [(512, 'test_key.pem'), (1024, 'test_123_key.pem'), (4096, '123_key.pem') ])
    def test_generate_key_custom(self, key_size, file_name):
        # Generate private key
        private_key = generate_key(key_size=key_size, output_file=file_name)

        # validate generated private key
        assert private_key.key_size == key_size
        assert os.path.isfile(file_name)

    def test_generate_local_cert(self):
        # Generate private key
        private_key = generate_key()
        # Generate local certificate using private key
        local_cert = generate_local_cert(private_key)
        assert local_cert

        # Validating generated cert file
        public_key = local_cert.public_key()
        assert isinstance(public_key, rsa.RSAPublicKey)
        with open('cert.cert', 'r') as cert_file:
            cert_content = cert_file.read()
            x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert_content)

            # Validate that the timestamp at which the certificate stops being valid (expiration date) is in future
            cert_expiry_date = datetime.datetime.strptime( x509.get_notAfter().decode('ascii'), '%Y%m%d%H%M%SZ')
            assert datetime.datetime.now() < cert_expiry_date