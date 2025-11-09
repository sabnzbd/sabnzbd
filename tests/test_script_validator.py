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
Tests for sabnzbd.validators.script_validator module
"""

from unittest.mock import patch

import pytest

from sabnzbd.validators import ScriptValidator, script_validator


class TestScriptValidator:
    """Test script validator functionality"""

    def test_script_validator_valid_scripts(self):
        """Test valid script names"""
        validator = ScriptValidator()

        # Valid script (mocked)
        with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
            mock_is_valid.return_value = True
            error, result = validator.validate("test_script.py")
            assert error is None
            assert result == "test_script.py"

            error, result = validator.validate("custom-script.sh")
            assert error is None
            assert result == "custom-script.sh"

    def test_script_validator_invalid_scripts(self):
        """Test invalid script names"""
        validator = ScriptValidator()

        # Invalid script (mocked)
        with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
            mock_is_valid.return_value = False
            error, result = validator.validate("invalid_script.xyz")
            assert error is not None
            assert "not a valid script" in error
            assert result is None

    def test_script_validator_none_value(self):
        """Test None value handling"""
        validator = ScriptValidator()

        # None value should return "None"
        with patch("sabnzbd.misc.is_none") as mock_is_none:
            mock_is_none.return_value = True
            error, result = validator.validate(None)
            assert error is None
            assert result == "None"

    def test_script_validator_empty_string(self):
        """Test empty string handling"""
        validator = ScriptValidator()

        # Empty string should pass validation
        with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
            mock_is_valid.return_value = True
            error, result = validator.validate("")
            assert error is None
            assert result == ""

    def test_script_validator_conditional_validation(self):
        """Test that script validation depends on initialization state"""
        validator = ScriptValidator()

        # When not initialized, any script should pass
        with (
            patch("sabnzbd.__INITIALIZED__", False),
            patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid,
        ):
            mock_is_valid.return_value = False  # Script is invalid
            error, result = validator.validate("invalid_script.xyz")
            assert error is None
            assert result == "invalid_script.xyz"

        # When initialized, validation should be enforced
        with (
            patch("sabnzbd.__INITIALIZED__", True),
            patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid,
        ):
            mock_is_valid.return_value = False
            error, result = validator.validate("invalid_script.xyz")
            assert error is not None
            assert "not a valid script" in error
            assert result is None

    def test_script_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        assert script_validator is not None
        assert callable(script_validator)

        # Test that the instance works correctly with valid script
        with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
            mock_is_valid.return_value = True
            error, result = script_validator("test_script.py")
            assert error is None
            assert result == "test_script.py"

        # Test that the instance works correctly with invalid script
        with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
            mock_is_valid.return_value = False
            error, result = script_validator("invalid_script.xyz")
            assert error is not None
            assert "not a valid script" in error
            assert result is None

    def test_script_validator_edge_cases(self):
        """Test edge cases for script validation"""
        validator = ScriptValidator()

        # Very long script name
        long_script = "a" * 100 + ".py"
        with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
            mock_is_valid.return_value = True
            error, result = validator.validate(long_script)
            assert error is None
            assert result == long_script

        # Script with special characters (should be handled by is_valid_script)
        special_script = "script-with-dashes_and_underscores.py"
        with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
            mock_is_valid.return_value = True
            error, result = validator.validate(special_script)
            assert error is None
            assert result == special_script

    def test_script_validator_none_conversion(self):
        """Test that None values are properly converted"""
        validator = ScriptValidator()

        # Test various None-like values
        with patch("sabnzbd.misc.is_none") as mock_is_none:
            mock_is_none.return_value = True

            # None value
            error, result = validator.validate(None)
            assert error is None
            assert result == "None"

            # Empty string (should not be converted to "None")
            mock_is_none.return_value = False
            with patch("sabnzbd.filesystem.is_valid_script") as mock_is_valid:
                mock_is_valid.return_value = True
                error, result = validator.validate("")
                assert error is None
                assert result == ""


if __name__ == "__main__":
    pytest.main([__file__])
