#!/usr/bin/python3 -OO
# Copyright 2007-2025 by The SABnzbd-Team (sabnzbd.org)
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
Tests for sabnzbd.validators.default_if_empty_validator module
"""

import unittest
from unittest.mock import patch

import pytest

from sabnzbd.validators import (
    DefaultIfEmptyValidator,
    default_if_empty_validator,
)


class TestDefaultIfEmptyValidator(unittest.TestCase):
    """Test default if empty validator functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.validator = DefaultIfEmptyValidator()
        self.root = "/test/root"
        self.default = "/default/path"

    def test_default_if_empty_validator_empty_value_returns_default(self):
        """Test that empty value returns default"""
        error, result = self.validator.validate(self.root, "", self.default)
        self.assertIsNone(error)
        self.assertEqual(result, self.default)

    def test_default_if_empty_validator_non_empty_value_returns_value(self):
        """Test that non-empty value returns original value"""
        test_cases = [
            "/custom/path",
            "/another/path",
            "relative/path",
            "file.txt",
            "   path with spaces   ",
        ]

        for value in test_cases:
            with self.subTest(value=value):
                error, result = self.validator.validate(self.root, value, self.default)
                self.assertIsNone(error)
                self.assertEqual(result, value)

    def test_default_if_empty_validator_none_value_returns_default(self):
        """Test that None value returns default"""
        error, result = self.validator.validate(self.root, None, self.default)
        self.assertIsNone(error)
        self.assertEqual(result, self.default)

    def test_default_if_empty_validator_whitespace_only_returns_whitespace(self):
        """Test that whitespace-only value returns original whitespace"""
        test_cases = [
            "   ",
            "\t",
            "\n",
            "  \t  \n  ",
        ]

        for value in test_cases:
            with self.subTest(value=repr(value)):
                error, result = self.validator.validate(self.root, value, self.default)
                self.assertIsNone(error)
                self.assertEqual(result, value)

    def test_default_if_empty_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        self.assertIsNotNone(default_if_empty_validator)
        self.assertTrue(callable(default_if_empty_validator))

        # Test that the instance works correctly with empty value
        error, result = default_if_empty_validator(self.root, "", self.default)
        self.assertIsNone(error)
        self.assertEqual(result, self.default)

        # Test that the instance works correctly with non-empty value
        error, result = default_if_empty_validator(self.root, "/custom/path", self.default)
        self.assertIsNone(error)
        self.assertEqual(result, "/custom/path")

    def test_default_if_empty_validator_edge_cases(self):
        """Test edge cases for default if empty validation"""
        # Test with very long value
        long_value = "/" + "a" * 100 + "/path"
        error, result = self.validator.validate(self.root, long_value, self.default)
        self.assertIsNone(error)
        self.assertEqual(result, long_value)

        # Test with special characters
        special_value = "/path/with/special@#$%^&*()chars"
        error, result = self.validator.validate(self.root, special_value, self.default)
        self.assertIsNone(error)
        self.assertEqual(result, special_value)

        # Test with unicode characters
        unicode_value = "/path/with/unicode/测试/路径"
        error, result = self.validator.validate(self.root, unicode_value, self.default)
        self.assertIsNone(error)
        self.assertEqual(result, unicode_value)

    def test_default_if_empty_validator_different_defaults(self):
        """Test with different default values"""
        test_cases = [
            ("", "/default1", "/default1"),
            ("", "/default2", "/default2"),
            ("", "", ""),
            ("", None, None),
            ("", "custom_default", "custom_default"),
        ]

        for value, default, expected in test_cases:
            with self.subTest(value=value, default=default):
                error, result = self.validator.validate(self.root, value, default)
                self.assertIsNone(error)
                self.assertEqual(result, expected)

    def test_default_if_empty_validator_always_no_error(self):
        """Test that the validator never returns an error"""
        test_values = [
            "",
            "value",
            None,
            "   ",
            "/path/to/something",
            "relative",
        ]

        for value in test_values:
            with self.subTest(value=value):
                error, result = self.validator.validate(self.root, value, self.default)
                self.assertIsNone(error)

    def test_default_if_empty_validator_root_parameter_ignored(self):
        """Test that root parameter is ignored (for compatibility)"""
        # The root parameter is part of the signature for compatibility
        # but should not affect the validation logic
        test_roots = [
            "/root1",
            "/root2",
            "",
            None,
            "/different/root",
        ]

        for root in test_roots:
            with self.subTest(root=root):
                error, result = self.validator.validate(root, "", self.default)
                self.assertIsNone(error)
                self.assertEqual(result, self.default)

                error, result = self.validator.validate(root, "/custom/path", self.default)
                self.assertIsNone(error)
                self.assertEqual(result, "/custom/path")


if __name__ == "__main__":
    unittest.main()
