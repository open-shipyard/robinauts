# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Every error the platform raises, rooted at ``RobinautsError``.

A sign-in failure carries one of the fixed codes of
``docs/specs/sign-in.md``: the browser is told the code and nothing else,
while ``detail`` says what really happened and goes to the log.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class RobinautsError(Exception):
    """The root of the platform's error hierarchy."""


class InvalidValueError(RobinautsError, ValueError):
    """A value that no part of the platform can work with."""


class ConfigError(RobinautsError):
    """Configuration that cannot be used; ``problems`` lists every one found.

    The operator gets the whole list at once, as ``docs/specs/operations.md``
    asks: a start-up that fixed one problem at a time would take as many
    restarts as there are mistakes.
    """

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems: tuple[str, ...] = tuple(problems)
        if not self.problems:
            raise InvalidValueError("a ConfigError lists at least one problem")
        super().__init__("invalid configuration:\n" + "\n".join(self.problems))


class SignInErrorCode(StrEnum):
    """What the sign-in page is told when a sign-in does not complete.

    The set is fixed and public: it reaches the browser as a query parameter,
    so a code names a kind of failure and never the provider's own words.
    """

    EXPIRED = "expired"
    """The sign-in took longer than a pending sign-in lives, or was replayed."""
    STATE_MISMATCH = "state_mismatch"
    """The callback's ``state`` is not one this deployment handed out."""
    NOT_ALLOWED = "not_allowed"
    """The provider says who they are; the allow list does not have them."""
    UNKNOWN_PROVIDER = "unknown_provider"
    """No provider of that id is configured."""
    BUSY = "busy"
    """Too many sign-ins are already in progress."""
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    """The provider could not be reached, or answered nothing usable."""
    PROVIDER_REFUSED = "provider_refused"
    """The provider refused the sign-in, or the authorization code."""
    INVALID_ID_TOKEN = "invalid_id_token"
    """The ID token is not one for this sign-in."""


class SignInError(RobinautsError):
    """A sign-in that cannot complete.

    ``code`` is what the browser is told; ``detail`` is for the log alone and
    may hold what a provider said.
    """

    def __init__(self, code: SignInErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


class NotAllowedError(SignInError):
    """The provider authenticated someone the allow list does not accept."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.NOT_ALLOWED, detail)


class UnknownProviderError(SignInError):
    """A sign-in was asked for with a provider id that is not configured."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.UNKNOWN_PROVIDER, detail)


class InvalidIdTokenError(SignInError):
    """An ID token whose claims do not belong to this sign-in."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.INVALID_ID_TOKEN, detail)


class ProviderUnavailableError(SignInError):
    """The provider could not be reached, or answered something unusable."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.PROVIDER_UNAVAILABLE, detail)
