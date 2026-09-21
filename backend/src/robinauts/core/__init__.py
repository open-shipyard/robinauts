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
from robinauts.core.hashing import pkce_challenge, secret_hash
from robinauts.core.sign_in_config import parse_sign_in_config
from robinauts.core.urls import is_loopback, normalise_issuer, normalise_origin

__all__ = [
    "CLOCK_SKEW_SECONDS",
    "GMAIL_DOMAINS",
    "MAX_ID_TOKEN_CHARS",
    "accepted_issuers",
    "ascii_lower",
    "check_id_token_claims",
    "check_published_issuer",
    "decode_id_token",
    "identity_from_claims",
    "identity_from_id_token",
    "is_allowed",
    "is_loopback",
    "matches",
    "normalise_issuer",
    "normalise_origin",
    "parse_sign_in_config",
    "pkce_challenge",
    "secret_hash",
    "verified_email",
]
