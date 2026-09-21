# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The shapes the JSON API sends, and therefore what OpenAPI describes.

They are the api's own, not the domain's: a ``User`` carries rows a browser
has no business with, and a response that was a domain object would make every
column added later a change to the wire. These say exactly what goes out, and
``backend/openapi.json`` is the committed snapshot of what they add up to
(``docs/specs/backend.md``).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from robinauts.domain import User


class ProviderSummary(BaseModel):
    """One provider to offer a sign-in button for. No secret, no endpoint."""

    id: str
    title: str


class UserSummary(BaseModel):
    """Who is signed in, as the interface shows them in the profile block."""

    id: uuid.UUID
    name: str | None = None
    email: str | None = None
    """Their address, only where the provider verified it."""
    provider: str

    @classmethod
    def of(cls, user: User) -> UserSummary:
        """The summary of a user; the fields the browser is told about."""
        return cls(id=user.id, name=user.name, email=user.email, provider=user.provider)


class SessionResponse(BaseModel):
    """What ``GET /auth/session`` answers, signed in or not.

    ``sign_in`` is whether this deployment has a sign-in configuration at all;
    without one there are no providers and nobody to be.
    """

    sign_in: bool
    public_url: str | None = None
    providers: list[ProviderSummary] = []
    user: UserSummary | None = None


class HealthResponse(BaseModel):
    """What ``GET /health`` answers. It holds no data and says nothing else."""

    status: str


class ErrorResponse(BaseModel):
    """Every refusal, in one shape (``robinauts.api.errors``)."""

    error: str
    """The name of the error class, which is what a client branches on."""
    detail: str
