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
sabnzbd.validators - Validation framework for configuration and data validation
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, List, Optional, Tuple, TypeVar, Union

# Type definitions for validation results
ValidateResult = Union[Tuple[None, str], Tuple[None, List[str]], Tuple[str, None]]
T = TypeVar("T")


class ValidationError(Exception):
    """Base exception for validation errors"""

    def __init__(self, message: str, field: Optional[str] = None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class BaseValidator(ABC, Generic[T]):
    """Abstract base class for all validators"""

    @abstractmethod
    def validate(self, value: T, *args, **kwargs) -> Tuple[Optional[str], T]:
        """
        Validate a value.

        Args:
            value: The value to validate
            *args: Additional positional arguments for contextual validators
            **kwargs: Additional keyword arguments for contextual validators

        Returns:
            Tuple[Optional[str], T]: (error_message, validated_value)
            If error_message is None, validation succeeded.
        """
        pass

    def __call__(self, value: T, *args, **kwargs) -> Tuple[Optional[str], T]:
        return self.validate(value, *args, **kwargs)


class StringValidator(BaseValidator[str]):
    """Base validator for string values"""

    pass


class ContextualValidator(BaseValidator[str]):
    """Base validator for string values that require additional context"""

    pass


class DirectoryValidator(BaseValidator[str]):
    """Base validator for directory paths"""

    pass


class ListValidator(BaseValidator[List[str]]):
    """Base validator for list values"""

    pass


# Common regular expressions for validation
RE_EMAIL = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
RE_SIMPLE_STRING = re.compile(r"^[a-zA-Z0-9._-]+$")
RE_ALPHANUMERIC = re.compile(r"^[a-zA-Z0-9]+$")

# Import validators
from sabnzbd.validators.email_validator import EmailValidator, email_validator
from sabnzbd.validators.host_validator import HostValidator, host_validator
from sabnzbd.validators.permissions_validator import (
    PermissionsValidator,
    permissions_validator,
)
from sabnzbd.validators.safe_dir_validator import SafeDirValidator, safe_dir_validator
from sabnzbd.validators.script_dir_not_appdir_validator import (
    ScriptDirNotAppDirValidator,
    script_dir_not_appdir_validator,
)
from sabnzbd.validators.script_validator import ScriptValidator, script_validator
from sabnzbd.validators.server_validator import ServerValidator, server_validator
from sabnzbd.validators.single_tag_validator import (
    SingleTagValidator,
    single_tag_validator,
)
from sabnzbd.validators.url_base_validator import UrlBaseValidator, url_base_validator

# Export common types and base classes
__all__ = [
    "ValidateResult",
    "ValidationError",
    "BaseValidator",
    "StringValidator",
    "ListValidator",
    "DirectoryValidator",
    "RE_EMAIL",
    "RE_SIMPLE_STRING",
    "RE_ALPHANUMERIC",
    # Email validator
    "EmailValidator",
    "email_validator",
    # Host validator
    "HostValidator",
    "host_validator",
    # Permissions validator
    "PermissionsValidator",
    "permissions_validator",
    # Script validator
    "ScriptValidator",
    "script_validator",
    # Safe directory validator
    "SafeDirValidator",
    "safe_dir_validator",
    # Script directory not app directory validator
    "ScriptDirNotAppDirValidator",
    "script_dir_not_appdir_validator",
    # Server validator
    "ServerValidator",
    "server_validator",
    # URL base validator
    "UrlBaseValidator",
    "url_base_validator",
    # Single tag validator
    "SingleTagValidator",
    "single_tag_validator",
]
