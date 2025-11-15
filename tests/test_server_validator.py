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
Tests for sabnzbd.validators.server_validator module
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

from sabnzbd.validators import ServerValidator, server_validator


class TestServerValidator(unittest.TestCase):
    """Test server validator functionality"""

    def test_server_validator_empty_server_with_email_enabled(self):
        """Test that empty server fails when email notifications are enabled"""
        validator = ServerValidator()

        # Mock email functions to return True (email enabled)
        with (
            patch.object(validator, "_email_endjob", return_value=True),
            patch.object(validator, "_email_full", return_value=True),
            patch.object(validator, "_email_rss", return_value=True),
        ):
            error, result = validator.validate("")
            self.assertIsNotNone(error)
            self.assertIn("Server address required", error)
            self.assertIsNone(result)

    def test_server_validator_empty_server_with_email_disabled(self):
        """Test that empty server passes when email notifications are disabled"""
        validator = ServerValidator()

        # Mock email functions to return False (email disabled)
        with (
            patch.object(validator, "_email_endjob", return_value=False),
            patch.object(validator, "_email_full", return_value=False),
            patch.object(validator, "_email_rss", return_value=False),
        ):
            error, result = validator.validate("")
            self.assertIsNone(error)
            self.assertEqual(result, "")

    def test_server_validator_valid_server_with_email_enabled(self):
        """Test that valid server passes when email notifications are enabled"""
        validator = ServerValidator()

        test_cases = [
            "smtp.gmail.com",
            "mail.example.com",
            "smtp-server.domain.org",
            "192.168.1.1",
            "localhost",
        ]

        # Mock email functions to return True (email enabled)
        with (
            patch.object(validator, "_email_endjob", return_value=True),
            patch.object(validator, "_email_full", return_value=True),
            patch.object(validator, "_email_rss", return_value=True),
        ):
            for server in test_cases:
                with self.subTest(server=server):
                    error, result = validator.validate(server)
                    self.assertIsNone(error)
                    self.assertEqual(result, server)

    def test_server_validator_valid_server_with_email_disabled(self):
        """Test that valid server passes when email notifications are disabled"""
        validator = ServerValidator()

        test_cases = [
            "smtp.gmail.com",
            "mail.example.com",
            "smtp-server.domain.org",
            "192.168.1.1",
            "localhost",
        ]

        # Mock email functions to return False (email disabled)
        with (
            patch.object(validator, "_email_endjob", return_value=False),
            patch.object(validator, "_email_full", return_value=False),
            patch.object(validator, "_email_rss", return_value=False),
        ):
            for server in test_cases:
                with self.subTest(server=server):
                    error, result = validator.validate(server)
                    self.assertIsNone(error)
                    self.assertEqual(result, server)

    def test_server_validator_none_value(self):
        """Test None server value"""
        validator = ServerValidator()

        # Mock email functions to return False (email disabled)
        with (
            patch.object(validator, "_email_endjob", return_value=False),
            patch.object(validator, "_email_full", return_value=False),
            patch.object(validator, "_email_rss", return_value=False),
        ):
            error, result = validator.validate(None)
            self.assertIsNone(error)
            self.assertIsNone(result)

    def test_server_validator_partial_email_enabled(self):
        """Test server validation with partial email notifications enabled"""
        validator = ServerValidator()

        # Test with only email_endjob enabled
        with (
            patch.object(validator, "_email_endjob", return_value=True),
            patch.object(validator, "_email_full", return_value=False),
            patch.object(validator, "_email_rss", return_value=False),
        ):
            error, result = validator.validate("")
            self.assertIsNotNone(error)
            self.assertIn("Server address required", error)
            self.assertIsNone(result)

        # Test with only email_full enabled
        with (
            patch.object(validator, "_email_endjob", return_value=False),
            patch.object(validator, "_email_full", return_value=True),
            patch.object(validator, "_email_rss", return_value=False),
        ):
            error, result = validator.validate("")
            self.assertIsNotNone(error)
            self.assertIn("Server address required", error)
            self.assertIsNone(result)

        # Test with only email_rss enabled
        with (
            patch.object(validator, "_email_endjob", return_value=False),
            patch.object(validator, "_email_full", return_value=False),
            patch.object(validator, "_email_rss", return_value=True),
        ):
            error, result = validator.validate("")
            self.assertIsNotNone(error)
            self.assertIn("Server address required", error)
            self.assertIsNone(result)

    def test_server_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        self.assertIsNotNone(server_validator)
        self.assertTrue(callable(server_validator))

        # Test that the instance works correctly with valid server
        with (
            patch.object(server_validator, "_email_endjob", return_value=False),
            patch.object(server_validator, "_email_full", return_value=False),
            patch.object(server_validator, "_email_rss", return_value=False),
        ):
            error, result = server_validator("smtp.gmail.com")
            self.assertIsNone(error)
            self.assertEqual(result, "smtp.gmail.com")

        # Test that the instance works correctly with empty server when email enabled
        with (
            patch.object(server_validator, "_email_endjob", return_value=True),
            patch.object(server_validator, "_email_full", return_value=False),
            patch.object(server_validator, "_email_rss", return_value=False),
        ):
            error, result = server_validator("")
            self.assertIsNotNone(error)
            self.assertIn("Server address required", error)
            self.assertIsNone(result)

    def test_server_validator_edge_cases(self):
        """Test edge cases for server validation"""
        validator = ServerValidator()

        # Test with whitespace-only server
        with (
            patch.object(validator, "_email_endjob", return_value=False),
            patch.object(validator, "_email_full", return_value=False),
            patch.object(validator, "_email_rss", return_value=False),
        ):
            error, result = validator.validate("   ")
            self.assertIsNone(error)
            self.assertEqual(result, "   ")

        # Test with very long server name
        long_server = "smtp." + "a" * 100 + ".com"
        with (
            patch.object(validator, "_email_endjob", return_value=False),
            patch.object(validator, "_email_full", return_value=False),
            patch.object(validator, "_email_rss", return_value=False),
        ):
            error, result = validator.validate(long_server)
            self.assertIsNone(error)
            self.assertEqual(result, long_server)

    def test_server_validator_email_functions_import(self):
        """Test that email functions are properly imported"""
        validator = ServerValidator()

        # Verify that the email function attributes exist
        self.assertTrue(hasattr(validator, "_email_endjob"))
        self.assertTrue(hasattr(validator, "_email_full"))
        self.assertTrue(hasattr(validator, "_email_rss"))


if __name__ == "__main__":
    unittest.main()
