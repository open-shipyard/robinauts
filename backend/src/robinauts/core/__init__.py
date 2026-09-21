# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Pure functions: no IO, no clock, no randomness, no global state.

Every function here is testable with input and output alone; a time it needs
is passed in. It depends on ``robinauts.domain`` and on nothing else inside
the package (``docs/layout.md``). What sign-in needs is here: the allow list,
the ID token's claims, the URLs, and the configuration's rules.
"""

from robinauts.core.allow import ascii_lower, is_allowed, matches, verified_email
from robinauts.core.claims import (
    CLOCK_SKEW_SECONDS,
    GMAIL_DOMAINS,
    MAX_ID_TOKEN_CHARS,
    accepted_issuers,
    check_id_token_claims,
    check_published_issuer,
    decode_id_token,
    identity_from_claims,
    identity_from_id_token,
)
from robinauts.core.hashing import (
    MAX_PKCE_CHARS,
    MAX_SECRET_CHARS,
    MIN_SECRET_CHARS,
    UNRESERVED,
    URL_SAFE,
    checked_secret,
    is_secret_shaped,
    pkce_challenge,
    same_secret,
    secret_hash,
)
from robinauts.core.oidc import (
    AUTHORIZATION_PARAMETERS,
    MAX_CODE_CHARS,
    TOKEN_PARAMETERS,
    authorization_url,
    parameters_taken,
)
from robinauts.core.sign_in_config import parse_sign_in_config
from robinauts.core.urls import (
    DEFAULT_RETURN_TO,
    MAX_RETURN_TO,
    endpoint_query,
    is_loopback,
    normalise_endpoint,
    normalise_issuer,
    normalise_origin,
    safe_return_to,
)

__all__ = [
    "AUTHORIZATION_PARAMETERS",
    "CLOCK_SKEW_SECONDS",
    "DEFAULT_RETURN_TO",
    "GMAIL_DOMAINS",
    "MAX_CODE_CHARS",
    "MAX_ID_TOKEN_CHARS",
    "MAX_PKCE_CHARS",
    "MAX_RETURN_TO",
    "MAX_SECRET_CHARS",
    "MIN_SECRET_CHARS",
    "TOKEN_PARAMETERS",
    "UNRESERVED",
    "URL_SAFE",
    "accepted_issuers",
    "ascii_lower",
    "authorization_url",
    "check_id_token_claims",
    "check_published_issuer",
    "checked_secret",
    "decode_id_token",
    "endpoint_query",
    "identity_from_claims",
    "identity_from_id_token",
    "is_allowed",
    "is_loopback",
    "is_secret_shaped",
    "matches",
    "normalise_endpoint",
    "normalise_issuer",
    "normalise_origin",
    "parameters_taken",
    "parse_sign_in_config",
    "pkce_challenge",
    "safe_return_to",
    "same_secret",
    "secret_hash",
    "verified_email",
]
