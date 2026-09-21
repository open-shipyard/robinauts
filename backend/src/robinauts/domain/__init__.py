# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The platform's shared vocabulary: dataclasses, enums, constants, errors.

Depends on nothing else inside ``robinauts``; everything may depend on it
(``docs/layout.md``). What sign-in needs is here; the conversation format
joins it later.
"""

from robinauts.domain.access import Permission
from robinauts.domain.errors import (
    DB_INIT_COMMAND,
    AuthenticationError,
    ConfigError,
    CrossSiteRequestError,
    InvalidIdTokenError,
    InvalidValueError,
    NotAllowedError,
    ProviderUnavailableError,
    RobinautsError,
    SchemaError,
    SignInError,
    SignInErrorCode,
    UnknownProviderError,
    UnsupportedMediaTypeError,
)
from robinauts.domain.identity import (
    MAX_PENDING_LOGINS,
    PENDING_LOGIN_MINUTES,
    Identity,
    PendingLogin,
    Session,
    User,
)
from robinauts.domain.local import (
    DEFAULT_LOCAL_HOST,
    LOCAL_PROVIDER,
    LOCAL_SUBJECT,
    LOCAL_USER_NAME,
    LocalMode,
    host_of,
    is_loopback,
    is_loopback_bind_host,
)
from robinauts.domain.sign_in import (
    DEFAULT_SCOPES,
    DEFAULT_SESSION_HOURS,
    GOOGLE_BARE_ISSUER,
    GOOGLE_HOST,
    GOOGLE_ISSUER,
    MAX_PROVIDER_ID_CHARS,
    MAX_SESSION_HOURS,
    TOKEN_ENDPOINT_AUTH_METHODS,
    AllowEntry,
    Matcher,
    ProviderConfig,
    SignInConfig,
    is_google_issuer,
    is_provider_id,
)

__all__ = [
    "DB_INIT_COMMAND",
    "DEFAULT_LOCAL_HOST",
    "DEFAULT_SCOPES",
    "DEFAULT_SESSION_HOURS",
    "GOOGLE_BARE_ISSUER",
    "GOOGLE_HOST",
    "GOOGLE_ISSUER",
    "LOCAL_PROVIDER",
    "LOCAL_SUBJECT",
    "LOCAL_USER_NAME",
    "MAX_PENDING_LOGINS",
    "MAX_PROVIDER_ID_CHARS",
    "MAX_SESSION_HOURS",
    "PENDING_LOGIN_MINUTES",
    "TOKEN_ENDPOINT_AUTH_METHODS",
    "AllowEntry",
    "AuthenticationError",
    "ConfigError",
    "CrossSiteRequestError",
    "Identity",
    "InvalidIdTokenError",
    "InvalidValueError",
    "LocalMode",
    "Matcher",
    "NotAllowedError",
    "PendingLogin",
    "Permission",
    "ProviderConfig",
    "ProviderUnavailableError",
    "RobinautsError",
    "SchemaError",
    "Session",
    "SignInConfig",
    "SignInError",
    "SignInErrorCode",
    "UnknownProviderError",
    "UnsupportedMediaTypeError",
    "User",
    "host_of",
    "is_google_issuer",
    "is_loopback",
    "is_loopback_bind_host",
    "is_provider_id",
]
