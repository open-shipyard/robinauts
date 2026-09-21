# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Composition root: what a deployment is made of, and who owns its lifetime.

This is the one module that knows every layer at once (``docs/layout.md``,
"infrastructure"). It reads the configuration, builds the adapters and the
datastore, injects them into the application, and mounts the api. Nothing
below it constructs a collaborator, and nothing below it reads a file or an
environment variable.

Two moments, deliberately apart:

- **configuring**, which happens the moment ``create_app`` is called and needs
  no event loop: the TOML file is read (``adapters.read_toml``), ``core``
  turns it into a ``SignInConfig``, the client secrets are looked for, and
  **every problem found is reported together** in one ``ConfigError``. An
  operator with three mistakes fixes three mistakes, not one restart at a
  time (``docs/specs/operations.md``);
- **opening**, which happens in the ASGI lifespan, because that is where a
  process may hold something: the connection pool, the schema check, the
  identity provider's HTTP client. What the lifespan opens, the lifespan
  closes (``docs/specs/backend.md``, "Background work"). A deployment whose
  database is not the one this build was written against fails there, with the
  message ``domain.SchemaError`` writes, and the server does not start.

**It is testable without either.** Every collaborator may be handed in --
``Deployment`` takes a credential store, an identity provider, a clock and a
source of secrets -- so the route tests wire the in-memory fakes and the
stand-in provider and never touch a database, a file or the environment. What
is *not* handed in is built here, and only what is built here is closed here
... with one exception, said plainly: an identity provider that holds an HTTP
client is closed whichever way it arrived, because the process holds it for
its life and a client nobody closes is a warning at shutdown.

The environment is read through one ``SecretLookup`` (``adapters.environment``
by default), the same callable the client secrets are read with: a test
scripts what the environment holds by passing a mapping's ``get``, and sets no
real variable.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from robinauts.adapters import (
    HttpIdentityProvider,
    OsSecretSource,
    SecretLookup,
    SystemClock,
    check_client_secrets,
    environment,
    read_toml,
)
from robinauts.api import create_api
from robinauts.application import LocalAccess, SignIn
from robinauts.core import parse_sign_in_config
from robinauts.datastore import PostgresCredentialStore, check_schema, open_pool
from robinauts.domain import (
    LOCAL_PROVIDER,
    LOCAL_SUBJECT,
    ConfigError,
    InvalidValueError,
    LocalMode,
    SignInConfig,
    is_loopback_bind_host,
)
from robinauts.ports import Clock, CredentialStore, IdentityProvider, SecretSource

_log = logging.getLogger(__name__)

AUTH_CONFIG_VARIABLE = "ROBINAUTS_AUTH_CONFIG"
"""Names the TOML file describing sign-in (``docs/specs/sign-in.md``)."""

DATABASE_URL_VARIABLE = "ROBINAUTS_DATABASE_URL"
"""Names the one PostgreSQL of the deployment. It may hold a password."""

BOTH_MODES = (
    f"the local development mode has no sign-in: it cannot be combined with a sign-in"
    f" configuration, so unset {AUTH_CONFIG_VARIABLE} (or pass no configuration file), or"
    f" start without the local development mode"
)
"""Asking for both is a start-up refusal (``docs/specs/sign-in.md``)."""

NO_MODE = (
    f"a deployment is either signed in to or developed on: set {AUTH_CONFIG_VARIABLE} to the"
    f" TOML file describing sign-in, or ask for the local development mode"
)
"""Neither was given. ``configured`` says it with whatever else is missing."""

OFF_LOOPBACK = (
    "the local development mode serves the loopback interface only: %s is not an address of"
    " it. Serve it on 127.0.0.1, ::1 or localhost. It is not a way to deploy"
    " (docs/specs/operations.md)."
)
"""Why a bind host is refused, with the host put in by the caller.

The rule is ``domain.is_loopback_bind_host``, which is stricter than the one a
request's ``Host`` header is judged by: a name of another shape -- even
``dev.localhost`` -- is resolved by whatever this machine resolves names with,
and a bind address is not a thing to leave to a resolver."""

LOCAL_MODE_WARNING = (
    "SIGN-IN IS OFF. This is the local development mode: it serves %s and nothing else, and"
    " every request runs as the one local user %s:%s. It is not a way to deploy"
    " (docs/specs/operations.md)."
)
"""Logged once, at start-up, because a server that asks nobody who they are
has to say so wherever it is looked at. The interface says it too, in a
permanent banner (``docs/specs/frontend.md``)."""


class Deployment:
    """One deployment's collaborators: how they are made, and when they go.

    ``open`` builds what is missing and returns the application's ``SignIn``;
    ``aclose`` gives back what ``open`` took. Both are called by the ASGI
    lifespan in ``create_app``, and a test may call them itself.
    """

    def __init__(
        self,
        config: SignInConfig | None = None,
        *,
        local_development_host: str | None = None,
        database_url: str | None = None,
        credentials: CredentialStore | None = None,
        provider: IdentityProvider | None = None,
        clock: Clock | None = None,
        secrets: SecretSource | None = None,
        secret_for: SecretLookup = environment,
    ) -> None:
        if (config is None) == (local_development_host is None):
            raise ConfigError([BOTH_MODES] if config is not None else [NO_MODE])
        self.config = config
        """The sign-in configuration, or ``None`` in the local development mode."""
        self.local_mode = (
            None if local_development_host is None else LocalMode(host=local_development_host)
        )
        """The local development mode, or ``None`` in a deployment.

        Built here, which is where a non-loopback bind host is refused: the
        root binds no socket -- the command that starts the server does -- so
        the rule is kept at the one moment that is certain to happen, before
        anything is opened and long before anything is served.
        """
        self.database_url = database_url
        self.sign_in: SignIn | None = None
        """The application's sign-in, between ``open`` and ``aclose``."""
        self.local_access: LocalAccess | None = None
        """The local development mode's one user, between ``open`` and ``aclose``."""
        self.pool: Any = None
        """The connection pool this opened, if it opened one; ``None`` after.

        Untyped on purpose: the driver is confined to ``robinauts.datastore``
        (``docs/layout.md``), so nothing here may name ``asyncpg.Pool``, not
        even in an annotation -- the contract is about what a module imports,
        and an annotation is an import. It is here so that an operator, a
        command and a test can see what the process is holding.
        """
        self._credentials = credentials
        self._provider = provider
        self._clock = clock or SystemClock()
        self._secrets = secrets or OsSecretSource()
        self._secret_for = secret_for
        self._closing: list[Callable[[], Awaitable[object]]] = []
        self._opened = False

    @classmethod
    def configured(
        cls,
        *,
        config_path: str | os.PathLike[str] | None = None,
        local_development_host: str | None = None,
        database_url: str | None = None,
        secret_for: SecretLookup = environment,
        credentials: CredentialStore | None = None,
        provider: IdentityProvider | None = None,
        clock: Clock | None = None,
        secrets: SecretSource | None = None,
    ) -> Deployment:
        """Read the configuration and refuse, once, with everything wrong with it.

        ``config_path`` and ``database_url`` fall back to the environment.
        Every problem this can see goes in one ``ConfigError``: a file that
        cannot be read, a configuration ``core`` will not accept, a client
        secret whose variable is unset, a database that was not named. A file
        that does not parse means there is no configuration to check secrets
        against, so those problems are simply not among them.

        ``local_development_host`` asks for the **local development mode**, and
        is the address the server will be served on -- the mode is loopback
        only, and this is where that is refused, beside every other start-up
        problem. It is **never** read from the environment and there is no
        variable that switches it on: a mode that signs nobody in is asked for
        in the command that starts the server and nowhere else, so that
        nothing a process inherits -- a stale export, a unit file, a container
        image -- can turn sign-in off in a deployment. There is no
        configuration file in this mode, and asking for both is refused.
        """
        problems: list[str] = []
        path = config_path if config_path is not None else secret_for(AUTH_CONFIG_VARIABLE)
        url = database_url if database_url is not None else secret_for(DATABASE_URL_VARIABLE)
        if credentials is None and not url:
            problems.append(
                f"no database: set {DATABASE_URL_VARIABLE} to the PostgreSQL this"
                f" deployment uses"
            )
        config: SignInConfig | None = None
        if local_development_host is not None:
            if path:
                problems.append(BOTH_MODES)
            if not is_loopback_bind_host(local_development_host):
                problems.append(OFF_LOOPBACK % (local_development_host,))
        elif not path:
            problems.append(
                f"no sign-in configuration: set {AUTH_CONFIG_VARIABLE} to the TOML file"
                f" describing it"
            )
        else:
            try:
                config = parse_sign_in_config(read_toml(path))
            except ConfigError as exc:
                problems.extend(exc.problems)
        if config is not None:
            try:
                check_client_secrets(config, secret_for=secret_for)
            except ConfigError as exc:
                problems.extend(exc.problems)
        if problems or (config is None and local_development_host is None):
            raise ConfigError(problems)
        return cls(
            config,
            local_development_host=local_development_host,
            database_url=url,
            credentials=credentials,
            provider=provider,
            clock=clock,
            secrets=secrets,
            secret_for=secret_for,
        )

    async def open(self) -> SignIn | None:
        """Open what the process holds, and wire the application on top of it.

        ``None`` in the local development mode, which has no sign-in to
        return: what it wires instead is ``local_access``, the one user every
        request runs as. Either way the pool is opened and the schema checked
        first -- the mode changes who is asking, and nothing else about the
        platform.

        The pool is opened and the schema checked before anything is built on
        them: a database of another version is a deployment that does not
        start (``docs/specs/backend.md``). Anything that fails part way gives
        back what it already took -- there is no half-open deployment.

        **Once.** A second call would open a second pool and a second client
        over the first, and the first pair would be unreachable and never
        closed: connections held for the life of the process against a
        deployment that believes it has one set. One ``Deployment`` is one
        process's worth of collaborators, opened by the lifespan, and a second
        call is a mistake to say so about rather than to carry out.
        """
        if self._opened:
            raise InvalidValueError(
                "this deployment has been opened already; build another one rather than"
                " opening this one twice"
            )
        self._opened = True
        try:
            credentials = self._credentials
            if credentials is None:
                if not self.database_url:  # pragma: no cover -- `configured` refuses first
                    raise ConfigError([f"no database: set {DATABASE_URL_VARIABLE}"])
                self.pool = await open_pool(self.database_url)
                self._closing.append(self._closed_pool)
                await check_schema(self.pool)
                credentials = PostgresCredentialStore(self.pool)
            if self.local_mode is not None:
                # No identity provider is built: there is nobody to talk to,
                # and an HTTP client nothing uses is a client to close.
                self.local_access = LocalAccess(
                    self.local_mode, credentials=credentials, clock=self._clock
                )
                _log.warning(
                    LOCAL_MODE_WARNING, self.local_mode.host, LOCAL_PROVIDER, LOCAL_SUBJECT
                )
                return None
            assert self.config is not None  # one of the two, decided in __init__
            provider = self._provider or HttpIdentityProvider(secret_for=self._secret_for)
            closer = getattr(provider, "aclose", None)
            if callable(closer):
                self._closing.append(closer)
            self.sign_in = SignIn(
                self.config,
                credentials=credentials,
                provider=provider,
                clock=self._clock,
                secrets=self._secrets,
            )
            return self.sign_in
        except BaseException:
            await self.aclose()
            raise

    async def _closed_pool(self) -> None:
        """Close the pool and forget it, so that nothing reaches a shut one."""
        pool, self.pool = self.pool, None
        await pool.close()

    async def aclose(self) -> None:
        """Close everything ``open`` opened, in reverse, whatever any of it does.

        A close that fails is logged and the next one still runs: at shutdown
        there is nothing left to protect by stopping, and a pool left open
        because a client would not close is the worse of the two.

        Idempotent, and safe on a deployment that was never opened: each
        closer is taken off the list before it is called, so a second call has
        nothing left to do. A lifespan that unwinds twice -- and a test that
        closes what a ``finally`` has closed -- is then not a second close of
        anything.
        """
        self.sign_in = None
        self.local_access = None
        while self._closing:
            close = self._closing.pop()
            try:
                await close()
            except Exception:
                _log.exception("closing %r failed", close)


def create_app(
    *,
    config_path: str | os.PathLike[str] | None = None,
    local_development_host: str | None = None,
    database_url: str | None = None,
    secret_for: SecretLookup = environment,
    credentials: CredentialStore | None = None,
    provider: IdentityProvider | None = None,
    clock: Clock | None = None,
    secrets: SecretSource | None = None,
) -> FastAPI:
    """The whole deployment as one ASGI application.

    ``ConfigError`` straight away if the configuration cannot be used, so that
    ``robinauts start`` fails before it binds a port. Everything that needs a
    running loop -- the pool, the schema check, the HTTP client -- happens in
    the lifespan, which an ASGI server runs before the first request and
    unwinds after the last.

    The collaborators are the arguments: pass a credential store and no
    database is opened, pass an identity provider and none is built. That is
    how the tests wire fakes and a stand-in provider into the real application
    (``docs/layout.md``, "Testing strategy").

    ``local_development_host`` is how the **local development mode** is asked
    for, and the address it will be served on. It is never the default and no
    environment variable turns it on; a later step gives the command a flag
    (``--dev-no-sign-in``) that passes the host it is about to bind.
    """
    deployment = Deployment.configured(
        config_path=config_path,
        local_development_host=local_development_host,
        database_url=database_url,
        secret_for=secret_for,
        credentials=credentials,
        provider=provider,
        clock=clock,
        secrets=secrets,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await deployment.open()
        app.state.sign_in = deployment.sign_in
        app.state.local = deployment.local_access
        try:
            yield
        finally:
            app.state.sign_in = None
            app.state.local = None
            await deployment.aclose()

    app = create_api(lifespan=lifespan)
    app.state.deployment = deployment
    return app
