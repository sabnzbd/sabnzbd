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
Tests for sabnzbd.validators.url_base_validator module
"""

import unittest
from unittest.mock import patch

import pytest

from sabnzbd.validators import UrlBaseValidator, url_base_validator


class TestUrlBaseValidator(unittest.TestCase):
    """Test URL base validator functionality"""

    def test_url_base_validator_adds_starting_slash(self):
        """Test that starting slash is added if not present"""
        validator = UrlBaseValidator()

        test_cases = [
            ("sabnzbd", "/sabnzbd"),
            ("api", "/api"),
            ("dashboard", "/dashboard"),
            ("admin", "/admin"),
        ]

        for input_value, expected_value in test_cases:
            with self.subTest(url_base=input_value):
                error, result = validator.validate(input_value)
                self.assertIsNone(error)
                self.assertEqual(result, expected_value)

    def test_url_base_validator_removes_trailing_slash(self):
        """Test that trailing slash is removed"""
        validator = UrlBaseValidator()

        test_cases = [
            ("/sabnzbd/", "/sabnzbd"),
            ("/api/", "/api"),
            ("/dashboard/", "/dashboard"),
            ("/admin/", "/admin"),
        ]

        for input_value, expected_value in test_cases:
            with self.subTest(url_base=input_value):
                error, result = validator.validate(input_value)
                self.assertIsNone(error)
                self.assertEqual(result, expected_value)

    def test_url_base_validator_preserves_correct_format(self):
        """Test that already correct formats are preserved"""
        validator = UrlBaseValidator()

        test_cases = [
            ("/sabnzbd", "/sabnzbd"),
            ("/api", "/api"),
            ("/dashboard", "/dashboard"),
            ("/admin", "/admin"),
        ]

        for input_value, expected_value in test_cases:
            with self.subTest(url_base=input_value):
                error, result = validator.validate(input_value)
                self.assertIsNone(error)
                self.assertEqual(result, expected_value)

    def test_url_base_validator_empty_value(self):
        """Test empty URL base value"""
        validator = UrlBaseValidator()

        error, result = validator.validate("")
        self.assertIsNone(error)
        self.assertEqual(result, "")

    def test_url_base_validator_none_value(self):
        """Test None URL base value"""
        validator = UrlBaseValidator()

        error, result = validator.validate(None)
        self.assertIsNone(error)
        self.assertIsNone(result)

    def test_url_base_validator_complex_paths(self):
        """Test complex URL paths"""
        validator = UrlBaseValidator()

        test_cases = [
            ("sabnzbd/api/v1/", "/sabnzbd/api/v1"),
            ("my/app/path", "/my/app/path"),
            ("/deep/nested/path/", "/deep/nested/path"),
            ("custom-path", "/custom-path"),
        ]

        for input_value, expected_value in test_cases:
            with self.subTest(url_base=input_value):
                error, result = validator.validate(input_value)
                self.assertIsNone(error)
                self.assertEqual(result, expected_value)

    def test_url_base_validator_edge_cases(self):
        """Test edge cases for URL base validation"""
        validator = UrlBaseValidator()

        # Single slash
        error, result = validator.validate("/")
        self.assertIsNone(error)
        self.assertEqual(result, "")

        # Multiple slashes - rstrip removes all trailing slashes
        error, result = validator.validate("///")
        self.assertIsNone(error)
        self.assertEqual(result, "")

        # Path with spaces
        error, result = validator.validate("my path")
        self.assertIsNone(error)
        self.assertEqual(result, "/my path")

        # Path with special characters
        error, result = validator.validate("api-v2")
        self.assertIsNone(error)
        self.assertEqual(result, "/api-v2")

    def test_url_base_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        self.assertIsNotNone(url_base_validator)
        self.assertTrue(callable(url_base_validator))

        # Test that the instance works correctly with valid URL base
        error, result = url_base_validator("sabnzbd")
        self.assertIsNone(error)
        self.assertEqual(result, "/sabnzbd")

        # Test that the instance works correctly with already formatted URL base
        error, result = url_base_validator("/api")
        self.assertIsNone(error)
        self.assertEqual(result, "/api")

        # Test that the instance works correctly with trailing slash
        error, result = url_base_validator("/dashboard/")
        self.assertIsNone(error)
        self.assertEqual(result, "/dashboard")

    def test_url_base_validator_non_string_values(self):
        """Test non-string values (should be handled gracefully)"""
        validator = UrlBaseValidator()

        # Integer (not converted to string in current implementation)
        error, result = validator.validate(123)
        self.assertIsNone(error)
        self.assertEqual(result, 123)

        # Boolean (not converted to string in current implementation)
        error, result = validator.validate(True)
        self.assertIsNone(error)
        self.assertEqual(result, True)

    def test_url_base_validator_multiple_operations(self):
        """Test that both operations (add start slash and remove end slash) work together"""
        validator = UrlBaseValidator()

        test_cases = [
            ("sabnzbd/", "/sabnzbd"),  # Add start, remove end
            ("api/v1/", "/api/v1"),  # Add start, remove end
            ("/admin/", "/admin"),  # Already has start, remove end
            ("dashboard", "/dashboard"),  # Add start, no end to remove
        ]

        for input_value, expected_value in test_cases:
            with self.subTest(url_base=input_value):
                error, result = validator.validate(input_value)
                self.assertIsNone(error)
                self.assertEqual(result, expected_value)


if __name__ == "__main__":
    unittest.main()
