# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The worker in a process of its own, which ``Lifecycle`` spawns on PostgreSQL.

It reads the configuration and the environment ``robinauts start`` read, composes as the
server does, and runs only the worker, until SIGTERM or SIGINT. It then stops the worker,
which waits for its tasks. It writes a line to its parent once the worker has started. On
Linux it also ends with its parent, killed or not.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import signal
import sys
from pathlib import Path

from robinauts.controller.composition import compose, load, storage_from

PARENT_VARIABLE = "ROBINAUTS_WORKER_PARENT"
"""The id of the process that spawned this one, which it ends with."""

READY_VARIABLE = "ROBINAUTS_WORKER_READY_FD"
"""The pipe this process writes ``READY_LINE`` to once its worker has started."""

READY_LINE = b"ready\n"

ACTIVITY_VARIABLE = "ROBINAUTS_WORKER_ACTIVITY_FILE"
"""The file this process's worker touches at every heartbeat, which its parent's health check
reads."""

_PR_SET_PDEATHSIG = 1


def _end_with_parent() -> None:
    """A SIGTERM when the parent ends, so that no worker outlives its server. Linux alone
    offers it; elsewhere a killed server leaves its worker running."""
    if sys.platform != "linux":
        return
    ctypes.CDLL(None, use_errno=True).prctl(_PR_SET_PDEATHSIG, signal.SIGTERM)
    # The parent may have ended before the request was made.
    if os.environ.get(PARENT_VARIABLE) != str(os.getppid()):
        os.kill(os.getpid(), signal.SIGTERM)


async def _run() -> None:
    config, secret_for = load(Path(os.environ["ROBINAUTS_CONFIG"]), os.environ)
    worker = compose(config, storage=storage_from(os.environ), secret_for=secret_for).worker
    worker.activity_file = Path(os.environ[ACTIVITY_VARIABLE])
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stopping.set)
    await worker.start()
    ready = int(os.environ[READY_VARIABLE])
    os.write(ready, READY_LINE)
    os.close(ready)
    try:
        await stopping.wait()
    finally:
        await worker.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _end_with_parent()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
