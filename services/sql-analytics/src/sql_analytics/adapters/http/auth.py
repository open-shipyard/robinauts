# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The bearer token: who a request comes from.

Every principal has one token, read from the environment at start-up. A request is let
through when its `Authorization: Bearer <token>` matches one of them, compared in constant time
against every principal so the time taken says nothing about which one, or how close the
guess was. The principal is put on the request's state for the tools to read, through
`principal_of`. Nothing about a refused token is logged or answered.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

from sql_analytics.contract import Principal, Secret

_STATE_KEY = "sql_analytics_principal"


class Authenticator:
    def __init__(self, tokens: Iterable[tuple[Secret, Principal]]) -> None:
        self._tokens = [(secret.reveal().encode(), principal) for secret, principal in tokens]

    def authenticate(self, authorization: str | None) -> Principal | None:
        """The principal whose token this `Authorization` header carries, if any."""
        if not authorization:
            return None
        scheme, _, token = authorization.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            return None
        candidate = token.encode()
        found = None
        for secret, principal in self._tokens:
            # Every token is compared, matched or not.
            if hmac.compare_digest(secret, candidate):
                found = principal
        return found


class BearerAuthMiddleware:
    """Refuses an HTTP request without a known token, except on the paths left `open`."""

    def __init__(self, app: ASGIApp, authenticator: Authenticator, open: Iterable[str]) -> None:
        self.app = app
        self.authenticator = authenticator
        self.open = frozenset(open)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.open:
            await self.app(scope, receive, send)
            return
        authorization = None
        for name, value in scope["headers"]:
            if name == b"authorization":
                authorization = value.decode("latin-1")
                break
        principal = self.authenticator.authenticate(authorization)
        if principal is None:
            await _unauthorized(send)
            return
        scope.setdefault("state", {})[_STATE_KEY] = principal
        await self.app(scope, receive, send)


def principal_of(state: object) -> Principal | None:
    """The principal a request was let through as, from the request's `state`."""
    principal = getattr(state, _STATE_KEY, None)
    return principal if isinstance(principal, Principal) else None


async def _unauthorized(send: Send) -> None:
    body = json.dumps({"error": "a valid bearer token is required"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
