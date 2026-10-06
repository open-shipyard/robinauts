# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The worker: everything about the tasks this process runs.

It claims queued tasks from the store and hands them to the dispatcher. It renews the
leases of the tasks the dispatcher runs, and stops a task asked to stop, from any process.
Every process runs one. A task is claimed by one worker, whichever process stored it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from robinauts.controller.application.intervals import run_at_intervals
from robinauts.controller.contract.domain import WorkConfig
from robinauts.controller.ports.dispatcher import TaskDispatcher
from robinauts.controller.ports.store import Store

_log = logging.getLogger(__name__)

QUEUE_WAIT_TIMEOUT = 5.0
"""How long the worker waits to hear of a queued turn before it looks again, in case the
announcement was lost."""

CLAIM_LIMIT = 10
"""How many turns one claim takes at most."""

CLOSE_TIMEOUT = 10.0
"""How long `stop` waits for the turns this process runs before it interrupts them."""


class Worker:
    def __init__(
        self,
        store: Store,
        dispatcher: TaskDispatcher,
        work: WorkConfig,
        *,
        wait_timeout: float = QUEUE_WAIT_TIMEOUT,
        close_timeout: float = CLOSE_TIMEOUT,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._dispatcher = dispatcher
        self._work = work
        self._wait_timeout = wait_timeout
        self._close_timeout = close_timeout
        self._now = now or (lambda: datetime.now(UTC))
        self._claiming: asyncio.Task[None] | None = None
        self._heartbeat: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Listen for cancels, then start renewing leases and claiming turns, on the store the
        controller opened."""
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
