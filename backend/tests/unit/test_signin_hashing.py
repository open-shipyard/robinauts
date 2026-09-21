# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What is kept of a secret, and the PKCE challenge derived from a verifier."""

import base64
import hashlib

from robinauts.core import pkce_challenge, secret_hash


def test_a_secret_is_kept_as_its_sha256_in_hex() -> None:
    assert secret_hash("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert len(secret_hash("")) == 64


def test_the_hash_is_the_same_for_the_same_secret_and_not_for_another() -> None:
    assert secret_hash("s3cret") == secret_hash("s3cret")
    assert secret_hash("s3cret") != secret_hash("s3crey")


def test_a_secret_outside_ascii_is_hashed_rather_than_refused() -> None:
    assert len(secret_hash("café \U0001f512")) == 64


def test_the_pkce_challenge_is_the_one_rfc_7636_shows() -> None:
    # RFC 7636 appendix B.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_the_challenge_is_base64url_without_padding() -> None:
    challenge = pkce_challenge("a-verifier-of-no-consequence")
    assert "=" not in challenge
    assert "+" not in challenge and "/" not in challenge
    digest = base64.urlsafe_b64decode(challenge + "==")
    assert digest == hashlib.sha256(b"a-verifier-of-no-consequence").digest()
