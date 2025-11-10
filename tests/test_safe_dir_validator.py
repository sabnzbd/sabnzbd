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
Tests for sabnzbd.validators.safe_dir_validator module
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

from sabnzbd.validators import SafeDirValidator, safe_dir_validator


class TestSafeDirValidator(unittest.TestCase):
    """Test safe directory validator functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.validator = SafeDirValidator()
        self.root = "/test/root"
        self.default = "/default/path"

    @patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True)
    @patch.object(SafeDirValidator, "_postprocessor_empty")
    @patch.object(SafeDirValidator, "_nzbqueue_is_empty")
    def test_safe_dir_validator_empty_queues_allows_change(self, mock_is_empty, mock_empty, mock_initialized):
        """Test that directory change is allowed when queues are empty"""
        mock_empty.return_value = True
        mock_is_empty.return_value = True

        error, result = self.validator.validate(self.root, "/new/path", self.default)
        self.assertIsNone(error)
        self.assertEqual(result, "/new/path")

    @patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True)
    @patch.object(SafeDirValidator, "_postprocessor_empty")
    @patch.object(SafeDirValidator, "_nzbqueue_is_empty")
    def test_safe_dir_validator_non_empty_queues_blocks_change(self, mock_is_empty, mock_empty, mock_initialized):
        """Test that directory change is blocked when queues are not empty"""
        mock_empty.return_value = False
        mock_is_empty.return_value = False

        error, result = self.validator.validate(self.root, "/new/path", self.default)
        self.assertIsNotNone(error)
        self.assertIn("Queue not empty, cannot change folder.", error)
        self.assertIsNone(result)

    @patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=False)
    def test_safe_dir_validator_not_initialized_allows_change(self, mock_initialized):
        """Test that directory change is allowed when not initialized"""
        error, result = self.validator.validate(self.root, "/new/path", self.default)
        self.assertIsNone(error)
        self.assertEqual(result, "/new/path")

    @patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True)
    @patch.object(SafeDirValidator, "_postprocessor_empty")
    @patch.object(SafeDirValidator, "_nzbqueue_is_empty")
    @patch("sabnzbd.validators.safe_dir_validator._helpful_warning")
    def test_safe_dir_validator_network_path_warning(self, mock_warning, mock_is_empty, mock_empty, mock_initialized):
        """Test that network paths trigger warnings"""
        mock_empty.return_value = True
        mock_is_empty.return_value = True

        # Mock network path detection
        with (
            patch.object(self.validator, "_is_network_path", return_value=True),
            patch.object(self.validator, "_real_path", return_value="//network/share"),
            patch.object(
                self.validator,
                "_validate_default_if_empty",
                return_value=(None, "//network/share"),
            ),
        ):
            error, result = self.validator.validate(self.root, "//network/share", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "//network/share")
            mock_warning.assert_called_once()

    @patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True)
    @patch.object(SafeDirValidator, "_postprocessor_empty")
    @patch.object(SafeDirValidator, "_nzbqueue_is_empty")
    @patch("sabnzbd.validators.safe_dir_validator._helpful_warning")
    def test_safe_dir_validator_local_path_no_warning(self, mock_warning, mock_is_empty, mock_empty, mock_initialized):
        """Test that local paths don't trigger warnings"""
        mock_empty.return_value = True
        mock_is_empty.return_value = True

        # Mock local path detection
        with (
            patch.object(self.validator, "_is_network_path", return_value=False),
            patch.object(self.validator, "_real_path", return_value="/local/path"),
            patch.object(
                self.validator,
                "_validate_default_if_empty",
                return_value=(None, "/local/path"),
            ),
        ):
            error, result = self.validator.validate(self.root, "/local/path", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "/local/path")
            mock_warning.assert_not_called()

    @patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True)
    @patch.object(SafeDirValidator, "_postprocessor_empty")
    @patch.object(SafeDirValidator, "_nzbqueue_is_empty")
    def test_safe_dir_validator_empty_value_uses_default(self, mock_is_empty, mock_empty, mock_initialized):
        """Test that empty value returns default"""
        mock_empty.return_value = True
        mock_is_empty.return_value = True

        with (
            patch.object(self.validator, "_is_network_path", return_value=False),
            patch.object(self.validator, "_real_path", return_value=""),
            patch.object(
                self.validator,
                "_validate_default_if_empty",
                return_value=(None, self.default),
            ),
        ):
            error, result = self.validator.validate(self.root, "", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, self.default)

    @patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True)
    @patch.object(SafeDirValidator, "_postprocessor_empty")
    @patch.object(SafeDirValidator, "_nzbqueue_is_empty")
    def test_safe_dir_validator_non_empty_value_preserved(self, mock_is_empty, mock_empty, mock_initialized):
        """Test that non-empty value is preserved"""
        mock_empty.return_value = True
        mock_is_empty.return_value = True

        with (
            patch.object(self.validator, "_is_network_path", return_value=False),
            patch.object(self.validator, "_real_path", return_value="/custom/path"),
            patch.object(
                self.validator,
                "_validate_default_if_empty",
                return_value=(None, "/custom/path"),
            ),
        ):
            error, result = self.validator.validate(self.root, "/custom/path", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "/custom/path")

    def test_safe_dir_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        self.assertIsNotNone(safe_dir_validator)
        self.assertTrue(callable(safe_dir_validator))

        # Test that the instance works correctly with valid parameters
        with (
            patch.object(safe_dir_validator, "_is_network_path", return_value=False),
            patch.object(safe_dir_validator, "_real_path", return_value="/test/path"),
            patch.object(
                safe_dir_validator,
                "_validate_default_if_empty",
                return_value=(None, "/test/path"),
            ),
            patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True),
            patch.object(
                safe_dir_validator,
                "_postprocessor_empty",
                return_value=True,
            ),
            patch.object(
                safe_dir_validator,
                "_nzbqueue_is_empty",
                return_value=True,
            ),
        ):
            error, result = safe_dir_validator(self.root, "/test/path", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "/test/path")

    def test_safe_dir_validator_edge_cases(self):
        """Test edge cases for safe directory validation"""
        # Test with None values
        with (
            patch("sabnzbd.validators.safe_dir_validator._is_initialized", return_value=True),
            patch.object(
                self.validator,
                "_postprocessor_empty",
                return_value=True,
            ),
            patch.object(
                self.validator,
                "_nzbqueue_is_empty",
                return_value=True,
            ),
            patch.object(self.validator, "_is_network_path", return_value=False),
            patch.object(self.validator, "_real_path", return_value=""),
            patch.object(self.validator, "_validate_default_if_empty", return_value=(None, "")),
        ):
            error, result = self.validator.validate(self.root, "", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "")

    def test_safe_dir_validator_helper_methods(self):
        """Test the helper methods work correctly"""
        # Test _is_network_path
        with patch("sabnzbd.filesystem.is_network_path") as mock_network:
            mock_network.return_value = True
            result = self.validator._is_network_path("/test/path")
            self.assertTrue(result)
            mock_network.assert_called_once_with("/test/path")

        # Test _real_path
        with patch("sabnzbd.filesystem.real_path") as mock_real:
            mock_real.return_value = "/absolute/path"
            result = self.validator._real_path("/root", "relative/path")
            self.assertEqual(result, "/absolute/path")
            mock_real.assert_called_once_with("/root", "relative/path")

        # Test _validate_default_if_empty
        error, result = self.validator._validate_default_if_empty("", self.default)
        self.assertIsNone(error)
        self.assertEqual(result, self.default)

        error, result = self.validator._validate_default_if_empty("/custom/path", self.default)
        self.assertIsNone(error)
        self.assertEqual(result, "/custom/path")

    def test_safe_dir_validator_from_cfg_tests(self):
        """Test cases originally from cfg.py test file"""
        assert safe_dir_validator("", "", "def") == (None, "def")
        assert safe_dir_validator("", "C:\\", "") == (None, "C:\\")


if __name__ == "__main__":
    unittest.main()
