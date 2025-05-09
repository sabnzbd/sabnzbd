#!/usr/bin/python3

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
import socket

from sabnzbd.getipaddress import local_ipv4


def generate_key(key_size=2048, output_file="key.pem"):
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


def generate_local_cert(private_key, days_valid=3560, output_file="cert.cert", LN="SABnzbd", ON="SABnzbd"):
    """Generate a certificate, using basic information.
    Ported from cryptography docs/x509/tutorial.rst
    """
    # Various details about who we are. For a self-signed certificate the
    # subject and issuer are always the same.
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.LOCALITY_NAME, LN),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ON),
            # x509.NameAttribute(NameOID.COMMON_NAME, CN),
        ]
    )

    # build Subject Alternate Names (aka SAN) list
    # First the host names, add with x509.DNSName():
    san_list = [x509.DNSName("localhost"), x509.DNSName(str(socket.gethostname()))]

    # Then the host IP addresses, add with x509.IPAddress()
    # Inside a try-except, just to be sure
    try:
        import ipaddress

        san_list.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))
        san_list.append(x509.IPAddress(ipaddress.IPv6Address("::1")))

        # append local v4 ip
        mylocalipv4 = local_ipv4()
        if mylocalipv4:
            san_list.append(x509.IPAddress(ipaddress.IPv4Address(str(mylocalipv4))))
    except Exception:
        pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days_valid))
        .serial_number(x509.random_serial_number())
        .add_extension(x509.SubjectAlternativeName(san_list), critical=True)
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
