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
``Deployment`` takes a credential store, a conversation store, an identity
provider, a clock and a source of secrets -- so the route tests wire the in-memory fakes and the
stand-in provider and never touch a database, a file or the environment.
**Both stores or neither**: a deployment that is open has a credential store
*and* a conversation store, so handing in one of them and no database url is
refused rather than quietly leaving the other unbuilt. What
is *not* handed in is built here, and only what is built here is closed here
... with one exception, said plainly: an identity provider that holds an HTTP
client is closed whichever way it arrived, because the process holds it for
its life and a client nobody closes is a warning at shutdown.

**What the process holds includes work.** Runs execute on the loop that serves
requests (``docs/specs/backend.md``, "Background work"), so the lifespan opens
the executor that carries them and the signals their watchers wait on, wires
the three services the routes call -- ``conversations``, ``turns``, ``watch``
-- and, once the stores are open, **sweeps once**: a run still active when this
process starts was left by one that went away, and it is ended ``interrupted``
with the event that says so. Shutdown is the same in reverse and in this order:
say that the process is stopping, so that the runs its own shutdown cancels are
recorded as interrupted and not as cancelled; cancel them and wait, bounded;
then close the stores, because the last thing a cancelled run does is write its
end into one.

**There is one turn timeout**, and the deployment holds it: ``turn_seconds``
goes to the run lifecycle, which fails a turn that takes longer, and to the
watchers, which give up on a run that has stored nothing for as long. They are
the same question asked from the two sides, so a deployment that lengthens one
lengthens the other rather than discovering that the numbers were copies.

The environment is read through one ``SecretLookup`` (``adapters.environment``
by default), the same callable the client secrets are read with: a test
scripts what the environment holds by passing a mapping's ``get``, and sets no
real variable.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from robinauts.adapters import (
    AsyncioRunExecutor,
    HttpIdentityProvider,
    MemoryRunSignals,
    OsIdSource,
    OsSecretSource,
    SecretLookup,
    SystemClock,
    check_client_secrets,
    environment,
    read_toml,
)
from robinauts.api import create_api
from robinauts.application import (
    DEFAULT_TURN_SECONDS,
    DEFAULT_WAIT_SECONDS,
    ENDING_BUDGET_SECONDS,
    Conversations,
    LocalAccess,
    SignIn,
    Turns,
    Watch,
)
from robinauts.core import parse_sign_in_config
from robinauts.datastore import (
    PostgresConversationStore,
    PostgresCredentialStore,
    check_schema,
    open_pool,
)
from robinauts.domain import (
    LOCAL_PROVIDER,
    LOCAL_SUBJECT,
    AgentDefinition,
    ConfigError,
    Engine,
    InvalidValueError,
    LocalMode,
    SignInConfig,
    is_loopback_bind_host,
)
from robinauts.ports import (
    Agent,
    Clock,
    ConversationStore,
    CredentialStore,
    IdentityProvider,
    SecretSource,
)

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

NO_DATABASE = f"no database: set {DATABASE_URL_VARIABLE} to the PostgreSQL this deployment uses"
"""Said wherever a store this deployment needs would have to come from one.

Both stores are the same database, and a deployment that is open has both
(``Deployment.open``), so the url is wanted unless **every** store was handed
in -- which only a test does.
"""

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

SHUTDOWN_SLACK_SECONDS = 5.0
"""How much longer than one run's ending a shutdown waits, for everything else.

The wait is for tasks that were cancelled together: each has its own ending to
write, and they write them at the same time, so the bound is one ending's
worth and not one per run. This is what is added for the rest of a stop --
letting an engine go, the last event of each stream, the reports of work that
never began.
"""

SHUTDOWN_SECONDS = ENDING_BUDGET_SECONDS + SHUTDOWN_SLACK_SECONDS
"""How long this deployment's shutdown may take, in seconds.

**Derived, not chosen.** A cancelled run writes its ending under a shield,
every attempt bounded and tried a few times, and the application is what says
how long all of that may be (``application.ENDING_BUDGET_SECONDS``). A
shutdown bound shorter than that would abandon writes that were about to land
-- runs left ``running`` for the next start-up sweep to find, for no reason
but two numbers that had drifted apart. The adapter cannot read the
application's numbers (``docs/layout.md``), so the composition root adds them
up and hands the result to ``aclose``, which is what it is for.
"""

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
        conversation_store: ConversationStore | None = None,
        provider: IdentityProvider | None = None,
        clock: Clock | None = None,
        secrets: SecretSource | None = None,
        secret_for: SecretLookup = environment,
        agents: Mapping[str, AgentDefinition] | None = None,
        engines: Mapping[Engine, Agent] | None = None,
        turn_seconds: float = DEFAULT_TURN_SECONDS,
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
        self.turn_seconds = turn_seconds
        """How long one turn of this deployment may take, in seconds.

        **One number, given to both sides of the same question**: the run
        lifecycle fails a turn that takes longer than this
        (``Turns(turn_seconds=...)``), and a watcher gives up on a run that has
        stored nothing for as long as it (``Watch(quiet_seconds=...)``). Two
        of them would be a deployment that lengthened a turn and then gave up
        on watching one while it was still allowed to answer, or the other way
        about -- so a deployment that lengthens one lengthens the other. It is
        checked where it is used, by the services that are built with it.
        """
        self.sign_in: SignIn | None = None
        """The application's sign-in, between ``open`` and ``aclose``."""
        self.local_access: LocalAccess | None = None
        """The local development mode's one user, between ``open`` and ``aclose``."""
        self.conversation_store: ConversationStore | None = None
        """Conversations, messages, runs and their events, between ``open`` and ``aclose``.

        Built here on the same pool as the credential store, because it is the
        same database. It is exposed so that a deployment, and a test, can see
        what the process holds; what is built **on** it is below.
        """
        self.conversations: Conversations | None = None
        """Listing, opening, renaming and deleting conversations."""
        self.turns: Turns | None = None
        """The run lifecycle: beginning a turn, executing it, cancelling it."""
        self.watch: Watch | None = None
        """A run's events, from a position, for whoever may see them.

        The three services are what the routes of the next step call, and they
        are here because this is the only place that may build them
        (``docs/layout.md``): ``turns.begin`` / ``begin_again`` to start a
        turn, ``turns.cancel`` to stop one, ``conversations.open`` to be told
        where to attach, and ``watch.events`` to follow it from there.
        """
        self.pool: Any = None
        """The connection pool this opened, if it opened one; ``None`` after.

        Untyped on purpose: the driver is confined to ``robinauts.datastore``
        (``docs/layout.md``), so nothing here may name ``asyncpg.Pool``, not
        even in an annotation -- the contract is about what a module imports,
        and an annotation is an import. It is here so that an operator, a
        command and a test can see what the process is holding.
        """
        self._credentials = credentials
        self._conversation_store = conversation_store
        self._provider = provider
        self._clock = clock or SystemClock()
        self._secrets = secrets or OsSecretSource()
        self._secret_for = secret_for
        self._agents = dict(agents or {})
        """The agents this deployment offers, as the operator defined them.

        **Injected, and empty until a later step**: reading them out of the
        configuration file is its own piece of work (``docs/specs/agents.md``),
        and nothing is served on top of them yet. A deployment with none can do
        everything but answer a turn, which is what the routes of the steps
        after this one will begin to need.
        """
        self._engines = dict(engines or {})
        """The engine of each kind this deployment runs, likewise injected.

        This is the one place the choice of agent framework is made
        (``docs/layout.md``, "infrastructure"), and it is made by whoever
        builds the deployment until the step that constructs the two adapters
        here."""
        self._executor = AsyncioRunExecutor()
        """Where a run's work happens: tasks on the loop that serves requests."""
        self._signals = MemoryRunSignals()
        """How a watcher hears that a run has stored something new."""
        self._ids = OsIdSource()
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
        conversation_store: ConversationStore | None = None,
        provider: IdentityProvider | None = None,
        clock: Clock | None = None,
        secrets: SecretSource | None = None,
        agents: Mapping[str, AgentDefinition] | None = None,
        engines: Mapping[Engine, Agent] | None = None,
        turn_seconds: float = DEFAULT_TURN_SECONDS,
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
        if (credentials is None or conversation_store is None) and not url:
            problems.append(NO_DATABASE)
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
            conversation_store=conversation_store,
            provider=provider,
            clock=clock,
            secrets=secrets,
            secret_for=secret_for,
            agents=agents,
            engines=engines,
            turn_seconds=turn_seconds,
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
            self.conversation_store = self._conversation_store
            # **A deployment that is open has both stores.** Either is
            # injectable and neither is optional: one of them missing would be
            # a process that starts, serves, and fails on the first request
            # that needs it. So a pool is opened whenever either is still
            # missing, and whatever is still missing is built on it.
            if credentials is None or self.conversation_store is None:
                if not self.database_url:  # pragma: no cover -- `configured` refuses first
                    raise ConfigError([NO_DATABASE])
                self.pool = await open_pool(self.database_url)
                self._closing.append(self._closed_pool)
                # One check for the whole schema: `check_schema` looks for
                # every table of `schema.sql`, the conversation and run tables
                # among them, so a database made before they existed is a
                # deployment that does not start.
                await check_schema(self.pool)
                if credentials is None:
                    credentials = PostgresCredentialStore(self.pool)
                if self.conversation_store is None:
                    self.conversation_store = PostgresConversationStore(self.pool)
            # The services, in both modes: the local development mode changes
            # who is asking and nothing about conversations or runs.
            self.conversations = Conversations(store=self.conversation_store, clock=self._clock)
            self.turns = Turns(
                store=self.conversation_store,
                clock=self._clock,
                ids=self._ids,
                agents=self._agents,
                engines=self._engines,
                executor=self._executor,
                signals=self._signals,
                turn_seconds=self.turn_seconds,
            )
            self.watch = Watch(
                store=self.conversation_store,
                signals=self._signals,
                # Never longer than the silence it gives up after, which a
                # deployment with a short turn timeout would otherwise be
                # (``application.DEFAULT_WAIT_SECONDS``).
                wait_seconds=min(DEFAULT_WAIT_SECONDS, self.turn_seconds),
                quiet_seconds=self.turn_seconds,
            )
            # From here the process may hold work, so it has something to give
            # back before the pool goes: the closers are popped in reverse, and
            # this one was appended after the pool's.
            self._closing.append(self._closed_executor)
            await self._swept()
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

    async def _swept(self) -> None:
        """End the runs a process that went away left going. Once, at start-up.

        The POC is one process (``docs/working-notes/poc-scope.md``), so a run
        that is still ``running`` when this one starts is a run whose process
        is gone: it is marked ``interrupted``, with the event that ends it, so
        that its conversation is not blocked behind it and a watcher of it is
        told it is over (``docs/specs/runs.md``).

        **It does not stop the deployment.** The schema has just been checked,
        so a sweep that fails is a store that went away between two calls, and
        a process that refused to start over housekeeping would be a
        deployment down for a reason nobody asked about. It is logged, and the
        next start-up sweeps again.
        """
        assert self.turns is not None  # built a few lines above
        try:
            swept = await self.turns.sweep_interrupted()
        except Exception:
            _log.exception(
                "the start-up sweep could not end the runs left by a process that went"
                " away; they stay active until a later start-up sweeps them"
            )
            return
        _log.info(
            "the start-up sweep ended %d run(s) left going by a process that went away",
            len(swept),
        )

    async def _closed_executor(self) -> None:
        """Stop the work this process is carrying, under a bound.

        Every run still going is cancelled and writes that it was
        ``interrupted`` -- ``Turns.stopping`` has already said that this is a
        process going away rather than somebody cancelling. Nothing is
        drained, and what has not stopped when the bound (``SHUTDOWN_SECONDS``,
        added up from the application's own ending budget so that there is one
        number and not two that drift) passes is abandoned
        (``docs/working-notes/poc-scope.md``). Work the close gave up on
        before it ever began is reported to the application here too, while
        the stores are still open, and inside that same bound.
        """
        await self._executor.aclose(timeout=SHUTDOWN_SECONDS)

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

        **In order**: this process says it is stopping, so that every run its
        shutdown cancels is recorded as ``interrupted`` rather than
        ``cancelled``; then nothing can be reached to start anything new; then
        the work in flight is cancelled and waited for, under a bound; and
        only then are the stores let go of -- because the last thing a
        cancelled run does is write its end into one.
        """
        if self.turns is not None:
            self.turns.stopping()
        self.sign_in = None
        self.local_access = None
        self.conversations = None
        self.turns = None
        self.watch = None
        # The stores hold nothing of their own -- the pool is what is closed,
        # below -- so letting go of them is forgetting them.
        self.conversation_store = None
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
    conversation_store: ConversationStore | None = None,
    provider: IdentityProvider | None = None,
    clock: Clock | None = None,
    secrets: SecretSource | None = None,
    agents: Mapping[str, AgentDefinition] | None = None,
    engines: Mapping[Engine, Agent] | None = None,
    turn_seconds: float = DEFAULT_TURN_SECONDS,
) -> FastAPI:
    """The whole deployment as one ASGI application.

    ``ConfigError`` straight away if the configuration cannot be used, so that
    ``robinauts start`` fails before it binds a port. Everything that needs a
    running loop -- the pool, the schema check, the HTTP client -- happens in
    the lifespan, which an ASGI server runs before the first request and
    unwinds after the last.

    The collaborators are the arguments: pass **both** stores and no database
    is opened, pass an identity provider and none is built. Both stores,
    because a deployment that is open has both: one of them handed in and no
    database url is a start-up ``ConfigError``. That is
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
        conversation_store=conversation_store,
        provider=provider,
        clock=clock,
        secrets=secrets,
        agents=agents,
        engines=engines,
        turn_seconds=turn_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await deployment.open()
        app.state.sign_in = deployment.sign_in
        app.state.local = deployment.local_access
        # The conversation routes read these off the state at the moment of a
        # request, exactly as the auth routes read the sign-in, so they are
        # put there the moment they exist and taken away with everything else.
        app.state.conversations = deployment.conversations
        app.state.turns = deployment.turns
        try:
            yield
        finally:
            app.state.sign_in = None
            app.state.local = None
            app.state.conversations = None
            app.state.turns = None
            await deployment.aclose()

    app = create_api(lifespan=lifespan)
    app.state.deployment = deployment
    return app
