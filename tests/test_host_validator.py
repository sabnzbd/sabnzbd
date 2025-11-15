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
Tests for sabnzbd.validators.host_validator module
"""

import socket
from unittest.mock import patch

import pytest

from sabnzbd.validators import HostValidator, host_validator


class TestHostValidator:
    """Test host validator functionality"""

    def test_host_validator_valid_ipv4(self):
        """Test valid IPv4 addresses"""
        validator = HostValidator()

        # Valid IPv4 addresses
        error, result = validator.validate("192.168.1.1")
        assert error is None
        assert result == "192.168.1.1"

        error, result = validator.validate("8.8.8.8")
        assert error is None
        assert result == "8.8.8.8"

        error, result = validator.validate("127.0.0.1")
        assert error is None
        assert result == "127.0.0.1"

    def test_host_validator_valid_ipv6(self):
        """Test valid IPv6 addresses"""
        validator = HostValidator()

        # Valid IPv6 addresses
        error, result = validator.validate("::1")
        assert error is None
        assert result == "::1"

        error, result = validator.validate("2001:db8::1")
        assert error is None
        assert result == "2001:db8::1"

        error, result = validator.validate("fe80::1")
        assert error is None
        assert result == "fe80::1"

    def test_host_validator_valid_hostnames(self):
        """Test valid hostnames with mocked DNS resolution"""
        validator = HostValidator()

        # Valid hostname with mocked IPv4 resolution
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = []  # Simulate successful resolution
            error, result = validator.validate("google.com")
            assert error is None
            assert result == "google.com"

        # Valid hostname with mocked IPv6 resolution
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Mock IPv4 failure but IPv6 success
            def side_effect(host, port, family):
                if family == socket.AF_INET:
                    raise Exception("No IPv4")
                return []  # IPv6 succeeds

            mock_getaddrinfo.side_effect = side_effect
            error, result = validator.validate("example.com")
            assert error is None
            assert result == "example.com"

    def test_host_validator_invalid_hostnames(self):
        """Test invalid hostnames"""
        validator = HostValidator()

        # Plain number (invalid)
        error, result = validator.validate("100")
        assert error is not None
        assert "Invalid hostname" in error
        assert result is None

        # Invalid hostname (mocked DNS failure for both IPv4 and IPv6)
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = Exception("DNS failure")
            error, result = validator.validate("invalid-hostname")
            assert error is not None
            assert "Invalid hostname" in error
            assert result is None

    def test_host_validator_edge_cases(self):
        """Test edge cases for host validation"""
        validator = HostValidator()

        # Empty string
        error, result = validator.validate("")
        assert error is not None
        assert "Invalid hostname" in error
        assert result is None

        # Very long but valid IP
        long_ip = "192.168." + "1." * 60 + "1"
        # This will be too long for IPv4 format, so it should fail
        error, result = validator.validate(long_ip)
        assert error is not None
        assert "Invalid hostname" in error
        assert result is None

    def test_host_validator_instance(self):
        """Test the convenience validator instance"""
        # Test that the instance exists and is callable
        assert host_validator is not None
        assert callable(host_validator)

        # Test that the instance works correctly with valid IP
        error, result = host_validator("192.168.1.1")
        assert error is None
        assert result == "192.168.1.1"

        # Test that the instance works correctly with invalid host
        error, result = host_validator("100")
        assert error is not None
        assert "Invalid hostname" in error
        assert result is None

    def test_host_validator_mixed_scenarios(self):
        """Test mixed valid/invalid scenarios"""
        validator = HostValidator()

        # Valid FQDN
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = []
            error, result = validator.validate("sub.domain.example.com")
            assert error is None
            assert result == "sub.domain.example.com"

        # Invalid: multiple dots without domain
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("Invalid hostname")
            error, result = validator.validate("..")
            assert error is not None
            assert "Invalid hostname" in error
            assert result is None

        # Invalid: special characters
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("Invalid hostname")
            error, result = validator.validate("host@name")
            assert error is not None
            assert "Invalid hostname" in error
            assert result is None

    def test_host_validator_from_cfg_tests(self):
        """Test cases originally from cfg.py test file"""
        # valid input
        assert host_validator("127.0.0.1") == (None, "127.0.0.1")
        assert host_validator("0.0.0.0") == (None, "0.0.0.0")
        assert host_validator("1.1.1.1") == (None, "1.1.1.1")
        assert host_validator("::1") == (None, "::1")
        assert host_validator("::") == (None, "::")

        # non-valid input. Should return None as second parameter
        assert not host_validator("0.0.0.0.")[1]  # Trailing dot
        assert not host_validator("kajkdjflkjasd")[1]  # does not resolve
        assert not host_validator("100")[1]  # just a number


if __name__ == "__main__":
    pytest.main([__file__])
