#!/usr/bin/python3 -OO
# Copyright 2007-2026 by The SABnzbd-Team (sabnzbd.org)
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
sabnzbd.bitmap - a compact data structure of True/False
"""

from typing import Optional


class Bitmap:
    """
    Compact fixed-size bitmap backed by a bytearray.

    Stores boolean values as individual bits rather than Python bool objects,
    providing very memory-efficient storage.

    Example:
        >>> bm = Bitmap(10)
        >>> bm[3] = True
        >>> bm[3]
        True
        >>> list(bm)
        [False, False, False, True, False, False, False, False, False, False]

    Memory usage:
        A bitmap of N bits uses ceil(N / 8) bytes.

    Serialization:
        Bitmaps can be converted to raw bytes using `to_bytes()` and restored
        using `from_bytes()`.

        Example:
            >>> raw = bm.to_bytes()
            >>> restored = Bitmap.from_bytes(10, raw)

    Notes:
        - Indexing is zero-based.
        - Iteration yields bool values.
        - Size is fixed after creation.
    """

    def __init__(self, size: int, data: Optional[bytes] = None, default: bool = False):
        """
        Create a bitmap.

        Args:
            size:
                Number of bits in the bitmap.

            data:
                Optional existing packed bitmap bytes/bytearray.
                Length must equal ceil(size / 8).

            default:
                If True, initialize all bits to True.
                Ignored when `data` is provided.

        Raises:
            ValueError:
                If provided data length is invalid.
        """
        self.size = size
        num_bytes = (size + 7) // 8

        if data is not None:
            if len(data) != num_bytes:
                raise ValueError(f"Expected {num_bytes} bytes, got {len(data)}")
            self._data = bytearray(data)
        else:
            self._data = bytearray(num_bytes)

            if default:
                for i in range(num_bytes):
                    self._data[i] = 0xFF

                # Clear unused bits in final byte
                extra_bits = num_bytes * 8 - size
                if extra_bits:
                    mask = (1 << (8 - extra_bits)) - 1
                    self._data[-1] &= mask

    @classmethod
    def from_bytes(cls, size: int, data: bytes):
        """
        Construct a bitmap from packed bytes.

        Args:
            size:
                Number of bits in the bitmap.

            data:
                Packed bitmap bytes.

        Returns:
            Bitmap instance.
        """
        return cls(size=size, data=data)

    def to_bytes(self) -> bytes:
        """
        Return packed bitmap bytes.

        Returns:
            Immutable bytes object containing packed bits.
        """
        return bytes(self._data)

    def _check_index(self, index: int):
        """
        Validate bitmap index.

        Raises:
            IndexError if index is out of range.
        """
        if not 0 <= index < self.size:
            raise IndexError("bitmap index out of range")

    def __len__(self):
        """
        Return number of bits in bitmap.
        """
        return self.size

    def __getitem__(self, index):
        """
        Get bit value at index.

        Args:
            index:
                Bit index.

        Returns:
            bool value at index.
        """
        self._check_index(index)

        byte_index = index // 8
        bit_index = index % 8

        return bool((self._data[byte_index] >> bit_index) & 1)

    def __setitem__(self, index, value):
        """
        Set bit value at index.

        Args:
            index:
                Bit index.

            value:
                Truthy/falsy value to assign.
        """
        self._check_index(index)

        byte_index = index // 8
        bit_index = index % 8

        if value:
            self._data[byte_index] |= 1 << bit_index
        else:
            self._data[byte_index] &= ~(1 << bit_index)

    def __iter__(self):
        """
        Iterate over bitmap bits as bool values.
        """
        for i in range(self.size):
            yield self[i]

    def __repr__(self):
        bits = "".join("1" if b else "0" for b in self)
        return f"Bitmap({self.size}, '{bits}')"

    # Pickle support
    def __getstate__(self):
        return {
            "size": self.size,
            "data": bytes(self._data),
        }

    def __setstate__(self, state):
        self.size = state["size"]
        self._data = bytearray(state["data"])
