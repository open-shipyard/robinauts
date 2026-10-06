# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The start and the stop of what the composition built, in order: what the app's lifespan
runs, and what a test that needs no app runs in its place. The worker runs in this process,
or in a process of its own (``spawn_worker_in_subprocess``)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import BinaryIO

from robinauts.controller.composition import Composed
from robinauts.web.worker_process import PARENT_VARIABLE, READY_VARIABLE

_log = logging.getLogger(__name__)

WORKER_MODULE = "robinauts.web.worker_process"

WORKER_START_SECONDS = 60.0
"""How long `start` waits for the worker's process to say its worker has started, before it
kills it and fails."""

WORKER_STOP_SECONDS = 15.0
"""How long `stop` waits for the worker's process after its SIGTERM before it kills it: more
than the worker waits for its tasks."""


class Lifecycle:
    def __init__(self, composed: Composed, *, spawn_worker_in_subprocess: bool = False) -> None:
        """``spawn_worker_in_subprocess`` runs the worker in a process of its own, which suits
        PostgreSQL alone: a store in memory cannot be shared between processes."""
        self.composed = composed
        self._spawn_worker_in_subprocess = spawn_worker_in_subprocess
        self._process: asyncio.subprocess.Process | None = None
        self._watching: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Open the controller, then start the worker, which opens a store of its own. Return
        once the worker has started, so that a server which says it is up runs turns."""
        await self.composed.controller.open()
        if not self._spawn_worker_in_subprocess:
            await self.composed.worker.start()
            return
        read_end, write_end = os.pipe()
        environment = {
            **os.environ,
            PARENT_VARIABLE: str(os.getpid()),
            READY_VARIABLE: str(write_end),
        }
        try:
            self._process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", WORKER_MODULE, env=environment, pass_fds=(write_end,)
            )
        finally:
            os.close(write_end)
        with os.fdopen(read_end, "rb") as ready:
            await self._wait_until_ready(self._process, ready)
        self._watching = asyncio.create_task(self._watch(self._process), name="worker process")

    async def _wait_until_ready(self, process: asyncio.subprocess.Process, ready: BinaryIO) -> None:
        """Wait for the worker's line, or stop its process and fail: it ended first, or it
        took longer than ``WORKER_START_SECONDS``."""
        reader = asyncio.StreamReader()
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), ready
        )
        try:
            line = await asyncio.wait_for(reader.readline(), WORKER_START_SECONDS)
        except TimeoutError:
            line = b""
        finally:
            transport.close()
        if line != b"ready\n":
            await self._stop_process(process)
            raise RuntimeError(
                f"the worker process did not start within {WORKER_START_SECONDS:g} s"
            )

    async def stop(self) -> None:
        """Stop the worker, which waits for the turns it runs, then close the controller."""
        if self._process is None:
            await self.composed.worker.stop()
        else:
            await self._stop_process(self._process)
        await self.composed.controller.close()

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        if self._watching is not None:
            self._watching.cancel()
            await asyncio.gather(self._watching, return_exceptions=True)
        if process.returncode is None:
            process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), WORKER_STOP_SECONDS)
            except TimeoutError:
                _log.warning("the worker process did not stop in %s s: killed", WORKER_STOP_SECONDS)
                process.kill()
                await process.wait()
        self._process = None

    async def _watch(self, process: asyncio.subprocess.Process) -> None:
        """Say so when the worker's process ends before `stop` asks it to: no turn runs from
        then on, until the server restarts."""
        code = await process.wait()
        _log.error("the worker process ended with code %s: no turn runs any more", code)
