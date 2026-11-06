# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The agent engines' store: the handle an engine's storage takes.

It is the engines' alone, apart from the core's records, which a worker reaches through its
``TurnBroker``. On PostgreSQL it is a pool of the worker's own, which the engines' tables are
read and written through; the core's tables never are.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class AgentEngineStore(ABC):
    @abstractmethod
    async def open(self) -> object | None:
        """What the engines take as their storage's handle: a PostgreSQL pool, or ``None``."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release what ``open`` took."""
        raise NotImplementedError


class PoolAgentEngineStore(AgentEngineStore):
    """A pool of the worker's own, which it hands the engines as their handle, and nothing
    else: not the core's store, whose tables a worker reaches through its ``TurnBroker`` alone.

    The composition hands it how to open and close the pool, so that the database's driver stays
    with the controller's adapters. The schema is not checked here: the server that reads the
    core's tables checks it, and the engines' tables are the ones ``robinauts db init`` set up.
    """

    def __init__(
        self,
        open_pool: Callable[[], Awaitable[object]],
        close_pool: Callable[[object], Awaitable[None]],
    ) -> None:
        self._open_pool = open_pool
        self._close_pool = close_pool
        self._pool: object | None = None

    async def open(self) -> object:
        if self._pool is None:
            self._pool = await self._open_pool()
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            pool, self._pool = self._pool, None
            await self._close_pool(pool)
