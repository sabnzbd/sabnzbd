#!/usr/bin/python3

"""
Adapted from the docs of cryptography
Creates a key and self-signed certificate for local use
"""

import datetime
import ipaddress
import socket

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from sabnzbd.getipaddress import local_ipv4


def generate_key(key_size: int = 2048, output_file: str = "key.pem") -> rsa.RSAPrivateKey:
    """Generate the private-key file for the self-signed certificate
    Ported from cryptography docs/x509/tutorial.rst (set with no encryption)
    """
    # Generate our key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size, backend=default_backend())

    # Write our key to disk for safe keeping
    with open(output_file, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    return private_key


def generate_local_cert(
    private_key: rsa.RSAPrivateKey,
    days_valid: int = 3560,
    output_file: str = "cert.cert",
    LN: str = "SABnzbd",
    ON: str = "SABnzbd",
) -> x509.Certificate:
    """Generate a certificate, using basic information.
    Ported from cryptography docs/x509/tutorial.rst
    """
    # Various details about who we are. For a self-signed certificate the
    # subject and issuer are always the same.
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.LOCALITY_NAME, LN),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ON),
        ]
    )

    # Build the Subject Alternative Names (aka SAN) list.
    # First the host names, added with x509.DNSName(), then the loopback addresses.
    san_list = [
        x509.DNSName("localhost"),
        x509.DNSName(socket.gethostname()),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.IPAddress(ipaddress.IPv6Address("::1")),
    ]

    # Then the local LAN IPv4 address, if we can determine it
    if mylocalipv4 := local_ipv4():
        try:
            san_list.append(x509.IPAddress(ipaddress.IPv4Address(mylocalipv4)))
        except ValueError:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=days_valid))
        .serial_number(x509.random_serial_number())
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    # Write our certificate out to disk.
    with open(output_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return cert


if __name__ == "__main__":
    print("Making key")
    private_key = generate_key()
    print("Making cert")
    cert = generate_local_cert(private_key)
