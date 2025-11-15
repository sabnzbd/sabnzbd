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
Tests for sabnzbd.validators.script_dir_not_appdir_validator module
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest
import importlib

from sabnzbd.validators import (
    ScriptDirNotAppDirValidator,
    script_dir_not_appdir_validator,
)


# Import the actual module for patching
script_dir_not_appdir_validator_module = importlib.import_module("sabnzbd.validators.script_dir_not_appdir_validator")


class TestScriptDirNotAppDirValidator(unittest.TestCase):
    """Test script directory not app directory validator functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.validator = ScriptDirNotAppDirValidator()
        self.root = "/test/root"
        self.default = "/default/path"

    @patch.object(script_dir_not_appdir_validator_module, "_helpful_warning")
    def test_script_dir_not_appdir_validator_app_directory_warning(self, mock_warning):
        """Test that app directory usage triggers warning"""
        # Mock same_directory to return True (app directory detected)
        with (
            patch.object(self.validator, "_same_directory", return_value=True),
            patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
        ):
            error, result = self.validator.validate(self.root, "/app/scripts", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "/app/scripts")
            mock_warning.assert_called_once()

    @patch.object(script_dir_not_appdir_validator_module, "_helpful_warning")
    def test_script_dir_not_appdir_validator_non_app_directory_no_warning(self, mock_warning):
        """Test that non-app directory doesn't trigger warning"""
        # Mock same_directory to return False (not app directory)
        with (
            patch.object(self.validator, "_same_directory", return_value=False),
            patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
        ):
            error, result = self.validator.validate(self.root, "/custom/scripts", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "/custom/scripts")
            mock_warning.assert_not_called()

    @patch.object(script_dir_not_appdir_validator_module, "_helpful_warning")
    def test_script_dir_not_appdir_validator_empty_value_no_warning(self, mock_warning):
        """Test that empty value doesn't trigger warning"""
        with (
            patch.object(self.validator, "_same_directory", return_value=False),
            patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
        ):
            error, result = self.validator.validate(self.root, "", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "")
            mock_warning.assert_not_called()

    @patch.object(script_dir_not_appdir_validator_module, "_helpful_warning")
    def test_script_dir_not_appdir_validator_none_value_no_warning(self, mock_warning):
        """Test that None value doesn't trigger warning"""
        with (
            patch.object(self.validator, "_same_directory", return_value=False),
            patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
        ):
            error, result = self.validator.validate(self.root, None, self.default)
            self.assertIsNone(error)
            self.assertIsNone(result)
            mock_warning.assert_not_called()

    def test_script_dir_not_appdir_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        self.assertIsNotNone(script_dir_not_appdir_validator)
        self.assertTrue(callable(script_dir_not_appdir_validator))

        # Test that the instance works correctly with non-app directory
        with (
            patch.object(script_dir_not_appdir_validator, "_same_directory", return_value=False),
            patch.object(script_dir_not_appdir_validator_module, "_helpful_warning") as mock_warning,
            patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
        ):
            error, result = script_dir_not_appdir_validator(self.root, "/custom/scripts", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "/custom/scripts")
            mock_warning.assert_not_called()

        # Test that the instance works correctly with app directory
        with (
            patch.object(script_dir_not_appdir_validator, "_same_directory", return_value=True),
            patch.object(script_dir_not_appdir_validator_module, "_helpful_warning") as mock_warning,
            patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
        ):
            error, result = script_dir_not_appdir_validator(self.root, "/app/scripts", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "/app/scripts")
            mock_warning.assert_called_once()

    def test_script_dir_not_appdir_validator_edge_cases(self):
        """Test edge cases for script directory validation"""
        with (
            patch.object(self.validator, "_same_directory", return_value=False),
            patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
        ):
            # Test with whitespace-only value
            error, result = self.validator.validate(self.root, "   ", self.default)
            self.assertIsNone(error)
            self.assertEqual(result, "   ")

            # Test with very long path
            long_path = "/" + "a" * 100 + "/scripts"
            error, result = self.validator.validate(self.root, long_path, self.default)
            self.assertIsNone(error)
            self.assertEqual(result, long_path)

    def test_script_dir_not_appdir_validator_same_directory_method(self):
        """Test the _same_directory helper method"""
        # Test that _same_directory calls the filesystem function
        with patch("sabnzbd.filesystem.same_directory") as mock_same:
            mock_same.return_value = True
            result = self.validator._same_directory("/path1", "/path2")
            self.assertTrue(result)
            mock_same.assert_called_once_with("/path1", "/path2")

    @patch.object(script_dir_not_appdir_validator_module, "_helpful_warning")
    def test_script_dir_not_appdir_validator_various_paths(self, mock_warning):
        """Test various path scenarios"""
        test_cases = [
            # (path, is_app_directory, should_warn)
            ("/usr/local/sabnzbd/scripts", True, True),
            ("/opt/sabnzbd/scripts", True, True),
            ("/home/user/scripts", False, False),
            ("/var/lib/sabnzbd/scripts", False, False),
            ("C:\\Program Files\\SABnzbd\\scripts", True, True),
            ("D:\\Custom\\Scripts", False, False),
        ]

        for path, is_app_directory, should_warn in test_cases:
            with self.subTest(path=path):
                with (
                    patch.object(self.validator, "_same_directory", return_value=is_app_directory),
                    patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
                ):
                    error, result = self.validator.validate(self.root, path, self.default)
                    self.assertIsNone(error)
                    self.assertEqual(result, path)

                    if should_warn:
                        mock_warning.assert_called()
                        mock_warning.reset_mock()
                    else:
                        mock_warning.assert_not_called()

    def test_script_dir_not_appdir_validator_always_returns_value(self):
        """Test that the validator always returns the original value"""
        test_values = [
            "/app/scripts",
            "/custom/scripts",
            "",
            None,
            "   ",
            "/very/long/path/to/scripts/folder",
        ]

        for value in test_values:
            with self.subTest(value=value):
                with (
                    patch.object(self.validator, "_same_directory", return_value=False),
                    patch.object(script_dir_not_appdir_validator_module, "_get_prog_dir", return_value="/app"),
                ):
                    error, result = self.validator.validate(self.root, value, self.default)
                    self.assertIsNone(error)
                    self.assertEqual(result, value)


if __name__ == "__main__":
    unittest.main()
