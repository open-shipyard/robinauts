# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""SHA-256 where sign-in needs it: stored secrets, and the PKCE challenge.

Making a secret is not here. It needs randomness, which no pure function has;
the application asks a port for it (``docs/layout.md``, "core").
"""

from __future__ import annotations

import base64
import hashlib


def secret_hash(secret: str) -> str:
    """What the credential store keeps of a secret, and finds it by.

    Session cookies and the ``state`` of a sign-in in progress each carry 256
    random bits and are never chosen by a person, so a plain hash is enough to
    make a stolen table useless; and a lookup by hash needs no comparison in
    constant time, since the hash of a guess is not the hash of the secret.
    """
    return hashlib.sha256(secret.encode("utf-8", "surrogatepass")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    """The ``S256`` code challenge for a PKCE verifier (RFC 7636 4.2).

    Base64url of the SHA-256 of the verifier's ASCII, without padding.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
