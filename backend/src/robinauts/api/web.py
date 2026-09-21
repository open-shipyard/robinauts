# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The ASGI application: the routes, the middleware and the error handling.

``create_api`` builds it and decides nothing else. What it serves is handed
in: the api never constructs an application service, never opens a connection
and never reads a configuration file -- the composition root does all three
and hands over the result (``docs/layout.md``, "infrastructure").

**Nothing is served without a declaration.** ``create_api`` runs
``check_declarations`` over what it built, and the lifespan runs it again when
the application starts. Those are the two moments anything is looked at, so
**routes are added between them and never after**: one added to a running
application -- a mount, a plain route, a websocket handler, a frontend -- is
served without ever having been asked what it needs. Between building and
starting, it stops the deployment instead. The test that walks the routes is
still there; this is the same walk, run where a branch nobody tested still has
to pass it.

**No ``/docs`` and no ``/redoc``.** Both load their JavaScript from a content
delivery network, and this project serves nothing from a third-party origin
(``docs/specs/frontend.md``). ``/openapi.json`` is served: it is a document,
it reaches nothing, and the interface's typed client is generated from the
committed snapshot of it (``backend/openapi.json``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import FastAPI

from robinauts.api.access import check_declarations, public
from robinauts.api.auth_routes import auth_router
from robinauts.api.errors import install_handlers
from robinauts.api.protection import (
    SECURITY_HEADERS,
    RequestProtection,
    SecurityHeaders,
)
from robinauts.api.schemas import HealthResponse
from robinauts.application import SignIn

TITLE = "Robinauts"

API_VERSION = "0"
"""The version of the wire, not of the build.

The OpenAPI document is committed and a test keeps it in step, so a number
that moved with every release would make that test about releases.
"""

OPENAPI_URL = "/openapi.json"


Opening = Callable[[FastAPI], AbstractAsyncContextManager[None]]
"""What a lifespan is here: a context manager around the life of the process.

Narrower than Starlette's own type, which also allows one yielding a mapping
of state. Nothing here has state to hand to a request, and saying so keeps the
wrapping below honest rather than silently dropping what it was given.
"""


def create_api(sign_in: SignIn | None = None, *, lifespan: Opening | None = None) -> FastAPI:
    """The application serving the api, over the services it is given.

    ``sign_in`` is the deployment's sign-in flow, or ``None`` where none is
    configured -- then ``/auth/session`` says so and the sign-in routes are
    not found. The composition root may also set it from inside ``lifespan``,
    which is where a deployment's collaborators are opened: everything here
    reads ``app.state.sign_in`` at the moment of a request rather than holding
    it, so both ways work and neither is a special case.

    ``ConfigError`` -- at build time, and again at start-up -- if anything the
    application serves declares no permission, or if a router keeps routes
    somewhere ``robinauts.api.access`` does not read. Routes are added between
    those two moments; one added after start-up is never checked.
    """

    @asynccontextmanager
    async def opening(application: FastAPI) -> AsyncIterator[None]:
        check_declarations(application)
        if lifespan is None:
            yield
            return
        async with lifespan(application):
            yield

    app = FastAPI(
        title=TITLE,
        version=API_VERSION,
        summary="Conversational agents that play fair.",
        docs_url=None,
        redoc_url=None,
        openapi_url=OPENAPI_URL,
        lifespan=opening,
    )
    app.state.sign_in = sign_in
    install_handlers(app, headers=dict(SECURITY_HEADERS))
    # The last added is the outermost, so the headers go on everything that
    # comes back -- the protection's own refusals included -- and the
    # protection is still in front of every route.
    app.add_middleware(RequestProtection)
    app.add_middleware(SecurityHeaders)
    app.include_router(auth_router)

    @app.get("/health", tags=["health"], dependencies=[public()])
    async def health() -> HealthResponse:
        """Liveness, for a load balancer or a deployment script.

        Public, and deliberately empty of everything else: it says that this
        process is answering, and nothing about the database, the providers or
        anybody signed in. A health endpoint that read the database would be a
        way to ask about the database without signing in.
        """
        return HealthResponse(status="ok")

    check_declarations(app)
    return app


def openapi_document() -> dict[str, Any]:
    """The OpenAPI document of this build, as the committed snapshot holds it.

    Built from an application with nothing wired in: the document describes
    the routes, which are the same whatever a deployment is configured with.
    """
    return create_api().openapi()
