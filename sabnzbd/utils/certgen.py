#!/usr/bin/env python

"""
Adapted from the docs of cryptography
Creates a key and self-signed certificate for local use
"""

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime
import os
import struct


# Ported from cryptography/utils.py
def int_from_bytes(data, byteorder, signed=False):
    assert byteorder == 'big'
    assert not signed

    if len(data) % 4 != 0:
        data = (b'\x00' * (4 - (len(data) % 4))) + data

    result = 0

    while len(data) > 0:
        digit, = struct.unpack('>I', data[:4])
        result = (result << 32) + digit
        # TODO: this is quadratic in the length of data
        data = data[4:]

    return result


# Ported from cryptography/utils.py
def random_serial_number():
    return int_from_bytes(os.urandom(20), "big") >> 1


def generate_key(key_size=2048, output_file='key.pem'):
    # Generate our key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )

    # Write our key to disk for safe keeping
    with open(output_file, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    return private_key


def generate_local_cert(private_key, days_valid=356, output_file='cert.cert', LN='', ON='', CN=''):
    # Various details about who we are. For a self-signed certificate the
    # subject and issuer are always the same.
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.LOCALITY_NAME, LN),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, ON),
        x509.NameAttribute(NameOID.COMMON_NAME, CN),
    ])

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        # Our certificate will be valid for 10 days
        datetime.datetime.utcnow() + datetime.timedelta(days=days_valid)
    ).serial_number(
        random_serial_number()
    # Sign our certificate with our private key
    ).sign(private_key, hashes.SHA256(), default_backend())

    # Write our certificate out to disk.
    with open(output_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return cert

if __name__ == '__main__':
    print 'Making key'
    private_key = generate_key(key_size=2048, output_file='key.pem')
    print 'Making cert'
    cert = generate_local_cert(private_key, 356*10, 'cert.cert', u'SABnzbd', u'SABnzbd', u'SABnzbd')

