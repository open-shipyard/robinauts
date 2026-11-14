# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The ASGI application: one process, `/mcp` and `/healthz`.

Outermost, the Host check: a request whose `Host` is not the listening address, a loopback
name or one of `server.allowed_hosts` is refused, on every path, against DNS rebinding. Then
the bearer token, on every path but `/healthz`. The MCP SDK's own Host check is turned off so
that this one is the only one there is. TLS is the reverse proxy's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from sql_analytics.adapters.http.auth import Authenticator, BearerAuthMiddleware

HEALTHZ = "/healthz"
# Starlette reads the name before the first colon, so an IPv6 literal cannot be matched.
LOOPBACK = ("127.0.0.1", "localhost")


async def _healthz(request: Request) -> JSONResponse:
    """The process is up. It reads nothing and needs no token."""
    return JSONResponse({"status": "ok"})


def build_app(
    server: FastMCP,
    authenticator: Authenticator,
    host: str,
    allowed_hosts: Iterable[str],
) -> Starlette:
    # One Host check, the one below, for every path.
    server.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    mcp_app = server.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        # A mounted application's lifespan is not run, so the session manager is run here.
        async with server.session_manager.run():
            yield

    hosts = list(dict.fromkeys([host, *LOOPBACK, *allowed_hosts]))
    return Starlette(
        routes=[Route(HEALTHZ, _healthz, methods=["GET"]), Mount("/", app=mcp_app)],
        middleware=[
            Middleware(TrustedHostMiddleware, allowed_hosts=hosts),
            Middleware(BearerAuthMiddleware, authenticator=authenticator, open=[HEALTHZ]),
        ],
        lifespan=lifespan,
    )
