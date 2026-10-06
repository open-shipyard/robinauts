# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The task dispatcher that runs each claimed task as an asyncio task in this process."""

from __future__ import annotations

import asyncio
import logging
import uuid

from robinauts.controller.contract.domain import Task
from robinauts.controller.ports.dispatcher import CLOSE, TaskDispatcher, TaskRunner

_log = logging.getLogger(__name__)


class InProcessDispatcher(TaskDispatcher):
    def __init__(self, run: TaskRunner | None = None) -> None:
        self.run = run
        """The worker's ``run_task``, handed over by the composition."""
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._stopped: set[uuid.UUID] = set()

    async def dispatch(self, task: Task) -> None:
        if self.run is None:
            raise RuntimeError("the dispatcher has nothing to run tasks with")
        running = asyncio.create_task(self.run(task))
        self._tasks[task.id] = running
        running.add_done_callback(lambda done: self._forget_task(task.id, done))

    def _forget_task(self, task: uuid.UUID, running: asyncio.Task[None]) -> None:
        self._tasks.pop(task, None)
        self._stopped.discard(task)
        if not running.cancelled() and (error := running.exception()) is not None:
            _log.error("task %s ended on an error", task, exc_info=error)

    def stop(self, task: uuid.UUID) -> bool:
        running = self._tasks.get(task)
        if running is None:
            return False
        if task not in self._stopped:
            self._stopped.add(task)
            running.cancel()
        return True

    async def cancel(self, task: uuid.UUID) -> bool:
        running = self._tasks.get(task)
        if running is None:
            return False
        self.stop(task)
        await asyncio.wait({running})
        return True

    def running(self) -> list[uuid.UUID]:
        return list(self._tasks)

    async def close(self, timeout: float) -> None:
        tasks = set(self._tasks.values())
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel(CLOSE)
        if pending:
            await asyncio.wait(pending)
