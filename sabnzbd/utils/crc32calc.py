#!/usr/bin/python3 -OO

"""
Functions for doing CRC32 calculations
Written by animetosho
https://github.com/sabnzbd/sabnzbd/issues/2396
"""

CRC32_POLYNOMIAL = 0xEDB88320


def crc_multiply(a: int, b: int):
    prod = 0
    while b != 0:
        prod ^= -(b >> 31) & a
        a = (a >> 1) ^ (CRC32_POLYNOMIAL & -(a & 1))
        b = (b << 1) & 0xFFFFFFFF
    return prod


# compute 2**n (without LUT)
def crc_2pow_slow(n: int):
    k = 0x80000000
    for bit in range(0, 32):
        k = crc_multiply(k, k)
        if n & (0x80000000 >> bit):
            k = (k >> 1) ^ (CRC32_POLYNOMIAL & -(k & 1))
    return k


CRC32_POWER_TABLE = [[crc_2pow_slow(v << (tbl * 4)) for v in range(0, 16)] for tbl in range(0, 8)]


# append `zeroes` null bytes to `crc`
def crc_zero_pad(crc: int, zeroes: int):
    return crc_multiply(crc ^ 0xFFFFFFFF, crc_2pow(zeroes * 8)) ^ 0xFFFFFFFF


# remove `zeroes` null bytes from end of crc
def crc_zero_unpad(crc: int, zeroes: int):
    inverse = ((zeroes * 8) % 0xFFFFFFFF) ^ 0xFFFFFFFF
    return crc_multiply(crc ^ 0xFFFFFFFF, crc_2pow(inverse)) ^ 0xFFFFFFFF


# compute 2**n
def crc_2pow(n: int):
    result = CRC32_POWER_TABLE[0][n & 15]
    n >>= 4
    tbl = 1
    while n:
        if n & 15:
            result = crc_multiply(result, CRC32_POWER_TABLE[tbl & 7][n & 15])
        n >>= 4
        tbl += 1
    return result


# compute CRC(A + B) given CRC(A) and CRC(B) (and byte length of B)
def crc_concat(crc1: int, crc2: int, len2: int):
    return crc_multiply(crc1, crc_2pow(len2 * 8)) ^ crc2
