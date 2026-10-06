# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The task dispatcher: where a claimed task runs, in this process or in another."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from robinauts.controller.contract.domain import Task

CLOSE = "close"
"""The reason a closing dispatcher cancels a task with. The runner ends such a turn as
``interrupted``, the deployment having stopped with the turn in it, not ``cancelled``."""

TaskRunner = Callable[[Task], Awaitable[None]]
"""What a dispatcher runs: the controller's ``run_task``, given the claimed task."""


class TaskDispatcher(ABC):
    @abstractmethod
    async def dispatch(self, task: Task) -> None:
        """Run the claimed task, somewhere, and return at once."""

    @abstractmethod
    def stop(self, task: uuid.UUID) -> bool:
        """Cancel the task if this process runs it, once however often it is asked, and return
        at once: true when this process runs it."""

    @abstractmethod
    async def cancel(self, task: uuid.UUID) -> bool:
        """Stop the task if this process runs it, and wait for it to end: true when it did,
        false when the task is not this process's."""

    @abstractmethod
    def running(self) -> list[uuid.UUID]:
        """The tasks this process runs, whose leases it renews."""

    @abstractmethod
    async def close(self, timeout: float) -> None:
        """Wait up to ``timeout`` seconds for the tasks this process runs, then cancel the rest
        naming ``CLOSE``, and wait for those too."""
