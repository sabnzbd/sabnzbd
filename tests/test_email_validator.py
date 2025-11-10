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
Tests for sabnzbd.validators.email_validator module
"""

from unittest.mock import patch

import pytest

from sabnzbd.validators import EmailValidator, email_validator


class TestEmailValidator:
    """Test email validator functionality"""

    def test_email_validator_valid_emails(self):
        """Test valid email addresses"""
        validator = EmailValidator()

        # Valid single email
        error, result = validator.validate("test@example.com")
        assert error is None
        assert result == "test@example.com"

        # Valid email with subdomain
        error, result = validator.validate("user@sub.domain.org")
        assert error is None
        assert result == "user@sub.domain.org"

        # Valid email with plus addressing
        error, result = validator.validate("user+tag@example.com")
        assert error is None
        assert result == "user+tag@example.com"

    def test_email_validator_invalid_emails(self):
        """Test invalid email addresses"""
        validator = EmailValidator()

        # Mock email functions to return True (email notifications enabled)
        with (
            patch("sabnzbd.cfg.email_endjob") as mock_endjob,
            patch("sabnzbd.cfg.email_full") as mock_full,
            patch("sabnzbd.cfg.email_rss") as mock_rss,
        ):
            mock_endjob.return_value = True
            mock_full.return_value = True
            mock_rss.return_value = True

            # Invalid email format - missing @
            error, result = validator.validate("invalid-email")
            assert error is not None
            assert "not a valid email address" in error
            assert result is None

            # Invalid email - missing domain
            error, result = validator.validate("user@")
            assert error is not None
            assert "not a valid email address" in error
            assert result is None

            # Invalid email - missing local part
            error, result = validator.validate("@domain.com")
            assert error is not None
            assert "not a valid email address" in error
            assert result is None

            # Invalid email - multiple @ symbols
            error, result = validator.validate("user@domain@com")
            assert error is not None
            assert "not a valid email address" in error
            assert result is None

    def test_email_validator_email_list(self):
        """Test email validation with lists"""
        validator = EmailValidator()

        # Mock email functions to return True (email notifications enabled)
        with (
            patch("sabnzbd.cfg.email_endjob") as mock_endjob,
            patch("sabnzbd.cfg.email_full") as mock_full,
            patch("sabnzbd.cfg.email_rss") as mock_rss,
        ):
            mock_endjob.return_value = True
            mock_full.return_value = True
            mock_rss.return_value = True

            # Valid email list
            error, result = validator.validate(["test@example.com", "user@domain.org"])
            assert error is None
            assert result == ["test@example.com", "user@domain.org"]

            # Invalid email in list
            error, result = validator.validate(["valid@example.com", "invalid"])
            assert error is not None
            assert "not a valid email address" in error
            assert result is None

    def test_email_validator_conditional_validation(self):
        """Test that email validation only happens when email notifications are enabled"""
        validator = EmailValidator()

        # Mock email functions to return False (no email notifications enabled)
        with (
            patch("sabnzbd.cfg.email_endjob") as mock_endjob,
            patch("sabnzbd.cfg.email_full") as mock_full,
            patch("sabnzbd.cfg.email_rss") as mock_rss,
        ):
            mock_endjob.return_value = False
            mock_full.return_value = False
            mock_rss.return_value = False

            # Email validation should NOT happen when notifications are disabled
            error, result = validator.validate("invalid-email")
            assert error is None
            assert result == "invalid-email"

    def test_email_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        assert email_validator is not None
        assert callable(email_validator)

        # Mock email functions to return True (email notifications enabled)
        with (
            patch("sabnzbd.cfg.email_endjob") as mock_endjob,
            patch("sabnzbd.cfg.email_full") as mock_full,
            patch("sabnzbd.cfg.email_rss") as mock_rss,
        ):
            mock_endjob.return_value = True
            mock_full.return_value = True
            mock_rss.return_value = True

            # Test that the instance works correctly
            error, result = email_validator("test@example.com")
            assert error is None
            assert result == "test@example.com"

    def test_email_validator_edge_cases(self):
        """Test edge cases for email validation"""
        validator = EmailValidator()

        # Empty string
        error, result = validator.validate("")
        assert error is None
        assert result == ""

        # None value
        error, result = validator.validate(None)
        assert error is None
        assert result is None

        # Very long but valid email
        long_email = "a" * 64 + "@" + "b" * 63 + ".com"
        error, result = validator.validate(long_email)
        assert error is None
        assert result == long_email


if __name__ == "__main__":
    pytest.main([__file__])
