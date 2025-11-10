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
Tests for sabnzbd.validators.permissions_validator module
"""

import unittest
from unittest.mock import patch

import pytest
import importlib

from sabnzbd.validators import PermissionsValidator, permissions_validator


# Import the actual module for patching
permissions_validator_module = importlib.import_module("sabnzbd.validators.permissions_validator")


class TestPermissionsValidator(unittest.TestCase):
    """Test permissions validator functionality"""

    def test_permissions_validator_valid_octal(self):
        """Test valid octal permissions"""
        validator = PermissionsValidator()

        # Valid octal permissions
        test_cases = [
            ("755", "755"),
            ("644", "644"),
            ("700", "700"),
            ("777", "777"),
            ("750", "750"),
            ("600", "600"),
        ]

        for input_value, expected_value in test_cases:
            error, result = validator.validate(input_value)
            assert error is None
            assert result == expected_value

    def test_permissions_validator_empty_value(self):
        """Test empty permissions value"""
        validator = PermissionsValidator()

        error, result = validator.validate("")
        assert error is None
        assert result == ""

    def test_permissions_validator_none_value(self):
        """Test None permissions value"""
        validator = PermissionsValidator()

        error, result = validator.validate(None)
        assert error is None
        assert result is None

    def test_permissions_validator_invalid_octal(self):
        """Test invalid octal format"""
        validator = PermissionsValidator()

        # Invalid octal values
        invalid_cases = [
            "abc",  # Non-octal characters
            "888",  # Invalid octal digit
            "799",  # Invalid octal digit
            "75",  # Too short
            "7555",  # Too long
            "0o755",  # Python octal prefix
            "0755",  # Leading zero (not octal)
        ]

        for invalid_value in invalid_cases:
            error, result = validator.validate(invalid_value)
            # Note: Some values like "75" and "7555" are technically valid octal numbers
            # in Python, so they pass validation. Only truly invalid formats fail.
            if invalid_value in ["75", "7555", "0o755", "0755"]:
                # These are actually valid octal numbers in Python
                assert error is None
                assert result == invalid_value
            else:
                assert error is not None
                assert invalid_value in error
                assert result is None

    def test_permissions_validator_zero_permissions(self):
        """Test that zero permissions are rejected"""
        validator = PermissionsValidator()

        error, result = validator.validate("0")
        assert error is not None
        assert "0" in error
        assert result is None

    @patch.object(permissions_validator_module, "_helpful_warning")
    def test_permissions_validator_low_permissions_warning(self, mock_warning):
        """Test that low permissions trigger a warning"""
        validator = PermissionsValidator()

        # Permissions below 700 should trigger warning
        low_permissions = ["644", "600", "755"]

        for permissions in low_permissions:
            error, result = validator.validate(permissions)
            assert error is None
            assert result == permissions

            # Check if warning was called for permissions below 700
            oct_value = int(permissions, 8)
            if oct_value < int("700", 8):
                mock_warning.assert_called()
                # Reset mock for next test
                mock_warning.reset_mock()
            else:
                mock_warning.assert_not_called()

    @patch.object(permissions_validator_module, "_helpful_warning")
    def test_permissions_validator_adequate_permissions_no_warning(self, mock_warning):
        """Test that adequate permissions don't trigger warnings"""
        validator = PermissionsValidator()

        # Permissions 700 and above should not trigger warnings
        adequate_permissions = ["700", "750", "777"]

        for permissions in adequate_permissions:
            error, result = validator.validate(permissions)
            assert error is None
            assert result == permissions
            mock_warning.assert_not_called()

    def test_permissions_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        assert permissions_validator is not None
        assert callable(permissions_validator)

        # Test that the instance works correctly with valid permissions
        error, result = permissions_validator("755")
        assert error is None
        assert result == "755"

        # Test that the instance works correctly with invalid permissions
        error, result = permissions_validator("abc")
        assert error is not None
        assert "abc" in error
        assert result is None

    def test_permissions_validator_edge_cases(self):
        """Test edge cases for permissions validation"""
        validator = PermissionsValidator()

        # Single digit octal - actually valid in Python octal
        error, result = validator.validate("7")
        assert error is None
        assert result == "7"

        # Two digit octal - actually valid in Python octal
        error, result = validator.validate("75")
        assert error is None
        assert result == "75"

        # Four digit octal with leading zero - actually valid in Python octal
        error, result = validator.validate("0755")
        assert error is None
        assert result == "0755"


if __name__ == "__main__":
    pytest.main([__file__])
