#!/usr/bin/python3 -OO

"""
Functions for doing CRC32 calculations
Written by animetoshi
https://github.com/sabnzbd/sabnzbd/issues/2396
"""

CRC32_POLYNOMIAL = 0xEDB88320
CRC32_POWER_TABLE = [  # pre-computed 2**(2**n)
    0x40000000,
    0x20000000,
    0x08000000,
    0x00800000,
    0x00008000,
    0xEDB88320,
    0xB1E6B092,
    0xA06A2517,
    0xED627DAE,
    0x88D14467,
    0xD7BBFE6A,
    0xEC447F11,
    0x8E7EA170,
    0x6427800E,
    0x4D47BAE0,
    0x09FE548F,
    0x83852D0F,
    0x30362F1A,
    0x7B5A9CC3,
    0x31FEC169,
    0x9FEC022A,
    0x6C8DEDC4,
    0x15D6874D,
    0x5FDE7A4E,
    0xBAD90E37,
    0x2E4E5EEF,
    0x4EABA214,
    0xA8A472C0,
    0x429A969E,
    0x148D302A,
    0xC40BA6D0,
    0xC4E22C3C,
]


def crc_multiply(a: int, b: int):
    prod = 0
    while b != 0:
        prod ^= -(b >> 31) & a
        a = (a >> 1) ^ (CRC32_POLYNOMIAL & -(a & 1))
        b = (b << 1) & 0xFFFFFFFF
    return prod


# append `zeroes` null bytes to `crc`
def crc_zero_pad(crc: int, zeroes: int):
    return crc_multiply(crc ^ 0xFFFFFFFF, crc_2pow(zeroes * 8)) ^ 0xFFFFFFFF


# remove `zeroes` null bytes from end of crc
def crc_zero_unpad(crc: int, zeroes: int):
    inverse = ((zeroes * 8) % 0xFFFFFFFF) ^ 0xFFFFFFFF
    return crc_multiply(crc ^ 0xFFFFFFFF, crc_2pow(inverse)) ^ 0xFFFFFFFF


# compute 2**n
def crc_2pow(n: int):
    result = 0x80000000
    power = 0
    while n != 0:
        if n & 1 != 0:
            result = crc_multiply(result, CRC32_POWER_TABLE[power])
        n >>= 1
        power = (power + 1) & 31
    return result


# compute CRC(A + B) given CRC(A) and CRC(B) (and byte length of B)
def crc_concat(crc1: int, crc2: int, len2: int):
    return crc_multiply(crc1, crc_2pow(len2 * 8)) ^ crc2
