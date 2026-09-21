# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The platform's shared vocabulary: dataclasses, enums, constants, errors.

Depends on nothing else inside ``robinauts``; everything may depend on it
(``docs/layout.md``). What sign-in needs is here; the conversation format
joins it later.
"""

from robinauts.domain.errors import (
    ConfigError,
    InvalidIdTokenError,
    InvalidValueError,
    NotAllowedError,
    ProviderUnavailableError,
    RobinautsError,
    SignInError,
    SignInErrorCode,
    UnknownProviderError,
)
from robinauts.domain.identity import (
    MAX_PENDING_LOGINS,
    PENDING_LOGIN_MINUTES,
    Identity,
    PendingLogin,
    Session,
    User,
)
from robinauts.domain.sign_in import (
    DEFAULT_SCOPES,
    DEFAULT_SESSION_HOURS,
    GOOGLE_BARE_ISSUER,
    GOOGLE_HOST,
    GOOGLE_ISSUER,
    MAX_SESSION_HOURS,
    TOKEN_ENDPOINT_AUTH_METHODS,
    AllowEntry,
    Matcher,
    ProviderConfig,
    SignInConfig,
    is_google_issuer,
)

__all__ = [
    "DEFAULT_SCOPES",
    "DEFAULT_SESSION_HOURS",
    "GOOGLE_BARE_ISSUER",
    "GOOGLE_HOST",
    "GOOGLE_ISSUER",
    "MAX_PENDING_LOGINS",
    "MAX_SESSION_HOURS",
    "PENDING_LOGIN_MINUTES",
    "TOKEN_ENDPOINT_AUTH_METHODS",
    "AllowEntry",
    "ConfigError",
    "Identity",
    "InvalidIdTokenError",
    "InvalidValueError",
    "Matcher",
    "NotAllowedError",
    "PendingLogin",
    "ProviderConfig",
    "ProviderUnavailableError",
    "RobinautsError",
    "Session",
    "SignInConfig",
    "SignInError",
    "SignInErrorCode",
    "UnknownProviderError",
    "User",
    "is_google_issuer",
]
