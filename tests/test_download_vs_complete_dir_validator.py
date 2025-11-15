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
Tests for sabnzbd.validators.download_vs_complete_dir_validator module
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

from sabnzbd.constants import DEF_COMPLETE_DIR, DEF_DOWNLOAD_DIR
from sabnzbd.validators import (
    DownloadVsCompleteDirValidator,
    download_vs_complete_dir_validator,
)


class TestDownloadVsCompleteDirValidator(unittest.TestCase):
    """Test download vs complete directory validator functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.validator = DownloadVsCompleteDirValidator()
        self.root = "/test/root"
        self.default_complete = DEF_COMPLETE_DIR
        self.default_download = DEF_DOWNLOAD_DIR

    @patch.object(DownloadVsCompleteDirValidator, "_get_download_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_get_complete_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_same_directory")
    def test_download_vs_complete_dir_validator_same_directory_error(
        self, mock_same, mock_get_complete, mock_get_download
    ):
        """Test that same directory triggers error"""
        mock_get_download.return_value = "/downloads"
        mock_get_complete.return_value = "/downloads"
        mock_same.return_value = True

        # Test with complete_dir default
        error, result = self.validator.validate(self.root, "/downloads", self.default_complete)
        self.assertIsNotNone(error)
        self.assertIn("Completed Download Folder", error)
        self.assertIn("Temporary Download Folder", error)
        self.assertIsNone(result)

        # Test with download_dir default
        error, result = self.validator.validate(self.root, "/downloads", self.default_download)
        self.assertIsNotNone(error)
        self.assertIn("Completed Download Folder", error)
        self.assertIn("Temporary Download Folder", error)
        self.assertIsNone(result)

    @patch.object(DownloadVsCompleteDirValidator, "_get_download_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_get_complete_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_same_directory")
    @patch.object(DownloadVsCompleteDirValidator, "_default_if_empty_validator")
    def test_download_vs_complete_dir_validator_complete_dir_success(
        self, mock_default, mock_same, mock_get_complete, mock_get_download
    ):
        """Test successful validation for complete_dir"""
        mock_get_download.return_value = "/downloads"
        mock_get_complete.return_value = "/completed"
        mock_same.return_value = False
        mock_default.return_value = (None, "/new/complete")

        error, result = self.validator.validate(self.root, "/new/complete", self.default_complete)
        self.assertIsNone(error)
        self.assertEqual(result, "/new/complete")
        mock_default.assert_called_once_with(self.root, "/new/complete", self.default_complete)

    @patch.object(DownloadVsCompleteDirValidator, "_get_download_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_get_complete_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_same_directory")
    @patch.object(DownloadVsCompleteDirValidator, "_safe_dir_validator")
    def test_download_vs_complete_dir_validator_download_dir_success(
        self, mock_safe, mock_same, mock_get_complete, mock_get_download
    ):
        """Test successful validation for download_dir"""
        mock_get_download.return_value = "/downloads"
        mock_get_complete.return_value = "/completed"
        mock_same.return_value = False
        mock_safe.return_value = (None, "/new/download")

        error, result = self.validator.validate(self.root, "/new/download", self.default_download)
        self.assertIsNone(error)
        self.assertEqual(result, "/new/download")
        mock_safe.assert_called_once_with(self.root, "/new/download", self.default_download)

    def test_download_vs_complete_dir_validator_invalid_default_raises_error(self):
        """Test that invalid default raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.validator.validate(self.root, "/some/path", "invalid_default")

        self.assertIn(
            "Validator can only be used for download_dir/complete_dir",
            str(context.exception),
        )

    @patch.object(DownloadVsCompleteDirValidator, "_get_download_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_get_complete_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_same_directory")
    def test_download_vs_complete_dir_validator_different_paths_success(
        self, mock_same, mock_get_complete, mock_get_download
    ):
        """Test that different paths pass validation"""
        mock_get_download.return_value = "/downloads/temp"
        mock_get_complete.return_value = "/downloads/complete"
        mock_same.return_value = False

        # Mock the helper validators
        with (
            patch.object(self.validator, "_default_if_empty_validator") as mock_default,
            patch.object(self.validator, "_safe_dir_validator") as mock_safe,
        ):
            mock_default.return_value = (None, "/downloads/complete")
            mock_safe.return_value = (None, "/downloads/temp")

            # Test complete_dir
            error, result = self.validator.validate(self.root, "/downloads/complete", self.default_complete)
            self.assertIsNone(error)
            self.assertEqual(result, "/downloads/complete")

            # Test download_dir
            error, result = self.validator.validate(self.root, "/downloads/temp", self.default_download)
            self.assertIsNone(error)
            self.assertEqual(result, "/downloads/temp")

    def test_download_vs_complete_dir_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        self.assertIsNotNone(download_vs_complete_dir_validator)
        self.assertTrue(callable(download_vs_complete_dir_validator))

        # Test that the instance works correctly
        with (
            patch.object(download_vs_complete_dir_validator, "_get_download_dir_path") as mock_get_download,
            patch.object(download_vs_complete_dir_validator, "_get_complete_dir_path") as mock_get_complete,
            patch.object(download_vs_complete_dir_validator, "_same_directory") as mock_same,
            patch.object(download_vs_complete_dir_validator, "_default_if_empty_validator") as mock_default,
        ):
            mock_get_download.return_value = "/downloads"
            mock_get_complete.return_value = "/completed"
            mock_same.return_value = False
            mock_default.return_value = (None, "/new/complete")

            error, result = download_vs_complete_dir_validator(self.root, "/new/complete", self.default_complete)
            self.assertIsNone(error)
            self.assertEqual(result, "/new/complete")

    def test_download_vs_complete_dir_validator_helper_methods(self):
        """Test the helper methods work correctly"""
        # Test _get_download_dir_path
        with patch("sabnzbd.cfg.download_dir.get_path") as mock_get_path:
            mock_get_path.return_value = "/download/path"
            result = self.validator._get_download_dir_path()
            self.assertEqual(result, "/download/path")
            mock_get_path.assert_called_once()

        # Test _get_complete_dir_path
        with patch("sabnzbd.cfg.complete_dir.get_path") as mock_get_path:
            mock_get_path.return_value = "/complete/path"
            result = self.validator._get_complete_dir_path()
            self.assertEqual(result, "/complete/path")
            mock_get_path.assert_called_once()

        # Test _real_path
        with patch("sabnzbd.filesystem.real_path") as mock_real:
            mock_real.return_value = "/absolute/path"
            result = self.validator._real_path("/root", "relative/path")
            self.assertEqual(result, "/absolute/path")
            mock_real.assert_called_once_with("/root", "relative/path")

        # Test _same_directory
        with patch("sabnzbd.filesystem.same_directory") as mock_same:
            mock_same.return_value = True
            result = self.validator._same_directory("/path1", "/path2")
            self.assertTrue(result)
            mock_same.assert_called_once_with("/path1", "/path2")

        # Test _default_if_empty_validator
        with patch("sabnzbd.validators.default_if_empty_validator") as mock_default:
            mock_default.return_value = (None, "/default/path")
            error, result = self.validator._default_if_empty_validator(self.root, "", self.default_complete)
            self.assertIsNone(error)
            self.assertEqual(result, "/default/path")
            mock_default.assert_called_once_with(self.root, "", self.default_complete)

        # Test _safe_dir_validator
        with patch("sabnzbd.validators.safe_dir_validator") as mock_safe:
            mock_safe.return_value = (None, "/safe/path")
            error, result = self.validator._safe_dir_validator(self.root, "/safe/path", self.default_download)
            self.assertIsNone(error)
            self.assertEqual(result, "/safe/path")
            mock_safe.assert_called_once_with(self.root, "/safe/path", self.default_download)

    @patch.object(DownloadVsCompleteDirValidator, "_get_download_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_get_complete_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_same_directory")
    def test_download_vs_complete_dir_validator_edge_cases(self, mock_same, mock_get_complete, mock_get_download):
        """Test edge cases for download vs complete directory validation"""
        mock_get_download.return_value = "/downloads"
        mock_get_complete.return_value = "/completed"
        mock_same.return_value = False

        with (
            patch.object(self.validator, "_default_if_empty_validator") as mock_default,
            patch.object(self.validator, "_safe_dir_validator") as mock_safe,
        ):
            mock_default.return_value = (None, "/default/path")
            mock_safe.return_value = (None, "/safe/path")

            # Test with empty value for complete_dir
            error, result = self.validator.validate(self.root, "", self.default_complete)
            self.assertIsNone(error)
            self.assertEqual(result, "/default/path")

            # Test with empty value for download_dir
            error, result = self.validator.validate(self.root, "", self.default_download)
            self.assertIsNone(error)
            self.assertEqual(result, "/safe/path")

            # Test with None value
            mock_default.return_value = (None, None)
            error, result = self.validator.validate(self.root, None, self.default_complete)
            self.assertIsNone(error)
            self.assertIsNone(result)

    @patch.object(DownloadVsCompleteDirValidator, "_get_download_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_get_complete_dir_path")
    @patch.object(DownloadVsCompleteDirValidator, "_same_directory")
    def test_download_vs_complete_dir_validator_nested_paths_error(
        self, mock_same, mock_get_complete, mock_get_download
    ):
        """Test that nested paths trigger error"""
        mock_get_download.return_value = "/downloads/temp"
        mock_get_complete.return_value = "/downloads"
        mock_same.return_value = True  # Same directory detection includes subfolders

        error, result = self.validator.validate(self.root, "/downloads", self.default_complete)
        self.assertIsNotNone(error)
        self.assertIn("Completed Download Folder", error)
        self.assertIn("Temporary Download Folder", error)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
