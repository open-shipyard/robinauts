# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The worker: everything about the tasks this process runs.

It builds the engines, claims queued tasks from the store and hands them to the dispatcher,
which runs each with ``run_task``. It renews the leases of the tasks the dispatcher runs, and
stops a task asked to stop, from any process. Every process runs one. A task is claimed by
one worker, whichever process stored it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from robinauts.agent_engines.contract.ports import AgentEngine, EngineFactory, installed
from robinauts.controller.application.engines import build_engines
from robinauts.controller.application.intervals import run_at_intervals
from robinauts.controller.application.turns import end_if_running, load_messages, run_turn
from robinauts.controller.contract.domain import (
    RUN_TURN,
    Config,
    Message,
    StorageConfig,
    StorageKind,
    Task,
    TextPart,
    Turn,
    TurnState,
    UnknownEngineError,
)
from robinauts.controller.core.engine_settings import (
    SecretLookup,
    engine_settings,
    engine_storage,
)
from robinauts.controller.core.failures import prompt_after_failures
from robinauts.controller.ports.dispatcher import CLOSE, TaskDispatcher
from robinauts.controller.ports.store import Store

_log = logging.getLogger(__name__)

QUEUE_WAIT_TIMEOUT = 5.0
"""How long the worker waits to hear of a queued turn before it looks again, in case the
announcement was lost."""

CLAIM_LIMIT = 10
"""How many turns one claim takes at most."""

CLOSE_TIMEOUT = 10.0
"""How long `stop` waits for the turns this process runs before it interrupts them."""


def _text(message: Message) -> str:
    return "".join(p.text for p in message.parts if isinstance(p, TextPart))


class Worker:
    def __init__(
        self,
        store: Store,
        dispatcher: TaskDispatcher,
        config: Config,
        *,
        storage: StorageConfig,
        secret_for: SecretLookup,
        engines: Mapping[str, EngineFactory] | None = None,
        wait_timeout: float = QUEUE_WAIT_TIMEOUT,
        close_timeout: float = CLOSE_TIMEOUT,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """``engines`` are the factories by engine name; the installed ones when not given."""
        self._store = store
        self._dispatcher = dispatcher
        self._config = config
        self._work = config.work
        self._storage = storage
        self._secret_for = secret_for
        self._given_engines = engines
        self._wait_timeout = wait_timeout
        self._close_timeout = close_timeout
        self._now = now or (lambda: datetime.now(UTC))
        self._engines: dict[str, AgentEngine] = {}
        self._factories: dict[str, EngineFactory] = {}
        self._handle: object | None = None
        self._claiming: asyncio.Task[None] | None = None
        self._heartbeat: asyncio.Task[None] | None = None

    def _sets_up_engines(self) -> bool:
        """On PostgreSQL `robinauts db init` set the engines up; the server never does."""
        return self._storage.kind is not StorageKind.POSTGRES

    async def start(self) -> None:
        """Build the engines, listen for cancels, then start renewing leases and claiming
        tasks, on the store the controller opened."""
        # Opened already: the store hands back the same handle, the engines' storage.
        self._handle = await self._store.open()
        self._factories = dict(installed() if self._given_engines is None else self._given_engines)
        self._engines = await build_engines(
            self._config,
            engine_settings(self._config, self._secret_for),
            engine_storage(self._storage, self._handle),
            self._factories,
            setup=self._sets_up_engines(),
        )
        await self._store.listen_for_cancels(self._dispatcher.stop)
        self._heartbeat = asyncio.create_task(
            run_at_intervals(self._work.heartbeat_seconds, self.renew_leases), name="heartbeat"
        )
        self._claiming = asyncio.create_task(self._claim_loop(), name="worker")

    async def stop(self) -> None:
        """Stop claiming, wait for the turns this process runs, bounded, and interrupt the
        rest. The leases are renewed until the last turn has ended."""
        await _cancel_and_wait(self._claiming)
        self._claiming = None
        await self._dispatcher.close(self._close_timeout)
        await _cancel_and_wait(self._heartbeat)
        self._heartbeat = None
        self._engines = {}

    async def dispatch_queued(self) -> bool:
        """Claim the queued tasks and dispatch each, until none is left or this process runs
        ``max_running_tasks_per_worker`` tasks: true in the second case."""
        while True:
            room = self._work.max_running_tasks_per_worker - len(self._dispatcher.running())
            if room <= 0:
                return True
            now = self._now()
            until = now + timedelta(seconds=self._work.lease_seconds)
            limit = min(CLAIM_LIMIT, room)
            claimed = await self._store.claim_tasks(now, until, limit)
            for task in claimed:
                await self._dispatcher.dispatch(task)
            if len(claimed) < limit:
                return False

    async def renew_leases(self) -> None:
        """Renew the lease of every task the dispatcher runs, and stop those asked to stop
        whose announcement was missed."""
        if tasks := self._dispatcher.running():
            now = self._now()
            until = now + timedelta(seconds=self._work.lease_seconds)
            for task in await self._store.renew_leases(tasks, now, until):
                self._dispatcher.stop(task)

    async def run_task(self, task: Task) -> None:
        """Run a claimed task, which names its turn: what the dispatcher runs."""
        if task.name != RUN_TURN:
            raise ValueError(f"a task this build does not run: {task.name!r}")
        found = await self._store.find_turn(uuid.UUID(task.payload["turn_id"]))
        if found is None:
            return
        owner, turn = found
        try:
            await self._run_turn(owner, turn, task)
        except asyncio.CancelledError as exc:
            # Cancelled before the runner's claim, the turn is ended here; after it, the
            # runner has ended it already.
            state = TurnState.INTERRUPTED if CLOSE in exc.args else TurnState.CANCELLED
            await end_if_running(self._store, owner, turn.session_id, turn.id, state, self._now())
            raise

    async def _engine(self, name: str) -> AgentEngine:
        """The engine of that name: built at `start` for the agents, or on demand for a
        session whose engine the configuration no longer names."""
        engine = self._engines.get(name)
        if engine is None:
            factory = self._factories.get(name)
            if factory is None:
                raise UnknownEngineError(f"engine {name!r}, which this build does not have")
            settings = engine_settings(self._config, self._secret_for)
            engine = factory(settings, engine_storage(self._storage, self._handle))
            if self._sets_up_engines():
                await engine.setup()
            self._engines[name] = engine
        return engine

    async def _run_turn(self, owner: uuid.UUID, turn: Turn, task: Task) -> None:
        session_id = turn.session_id
        session = await self._store.get_session(owner, session_id)
        engine = await self._engine(session.engine)
        if task.payload.get("create_session"):
            # A conversation's first turn: its engine holds nothing of it yet.
            await engine.create(session_id)
        by_id = {m.id: m for m in await load_messages(self._store, owner, session_id)}
        question = by_id[turn.follows]
        # The nearest answer up the thread that has a checkpoint: a failed answer has
        # none, and continuing from nothing would start the engine's memory again.
        checkpoint_id = None
        above = question.parent_id
        while above is not None and checkpoint_id is None:
            checkpoint_id = by_id[above].checkpoint_id
            above = by_id[above].parent_id
        agent_config = self._config.agents[session.agent]
        # The failed exchanges between the last answer that finished and this question,
        # oldest first: the engine remembers none of them, so the prompt carries them.
        earlier: list[tuple[str, Message]] = []
        above = question.parent_id
        while above is not None and by_id[above].failed:
            failed = by_id[above]
            asked = by_id[failed.parent_id] if failed.parent_id is not None else None
            if asked is None:
                break
            earlier.insert(0, (_text(asked), failed))
            above = asked.parent_id
        retried = None if turn.retries_message_id is None else by_id[turn.retries_message_id]
        prompt = prompt_after_failures(_text(question), earlier, retried)
        await run_turn(
            self._store,
            engine,
            owner,
            session,
            turn,
            question,
            prompt,
            agent_config,
            checkpoint_id,
            task.claimed_at or turn.started_at,
            self._work.max_turn_seconds,
        )

    async def _claim_loop(self) -> None:
        while True:
            try:
                # Full, it sleeps: queued tasks would end the store's wait at once.
                if await self.dispatch_queued():
                    await asyncio.sleep(self._wait_timeout)
                else:
                    await self._store.wait_for_queued(self._now(), self._wait_timeout)
            except Exception:
                _log.exception("the worker could not claim tasks")
                await asyncio.sleep(self._wait_timeout)


async def _cancel_and_wait(task: asyncio.Task[None] | None) -> None:
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
