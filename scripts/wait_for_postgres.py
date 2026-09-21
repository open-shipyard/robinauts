# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Wait until a PostgreSQL really answers a query, then exit.

For CI, before the tests. A container's health check cannot settle this on
its own: the official PostgreSQL image runs a private server while it sets
the data directory up, and `pg_isready` is satisfied by that one whatever
arguments it is given -- so a job can start, connect, and find the server
shut down underneath it a moment later.

What cannot be satisfied by that server is what this does: connect over TCP,
as the account and to the database the tests use, and run a statement. It
uses `asyncpg`, which is a dependency of the backend and therefore certainly
installed wherever the tests are about to run; nothing else is needed on the
runner.

    uv run python ../scripts/wait_for_postgres.py [url]

The URL comes from the argument, or from `ROBINAUTS_TEST_DATABASE_URL`.
Exit 0 when the server answered, 1 when it never did, 2 when there was
nothing to wait for.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import asyncpg

PATIENCE_SECONDS = 60.0
"""How long a server may take to come up before the wait is a failure."""

BETWEEN_TRIES_SECONDS = 1.0


async def wait_for(url: str, patience: float = PATIENCE_SECONDS) -> str | None:
    """Return ``None`` once the server answers, or why it never did.

    Every failure to connect is treated as "not yet", because at this point
    they are indistinguishable from it: a refused connection, a server still
    starting, a database not created. Only running out of time is a failure.
    """
    giving_up_at = time.monotonic() + patience
    last = "no attempt was made"
    while True:
        try:
            connection = await asyncpg.connect(url)
        except (OSError, asyncpg.PostgresError) as not_yet:
            last = f"{type(not_yet).__name__}: {not_yet}"
        else:
            try:
                await connection.fetchval("SELECT 1")
            finally:
                await connection.close()
            return None
        if time.monotonic() >= giving_up_at:
            return f"no answer after {patience:.0f}s; last attempt said {last}"
        await asyncio.sleep(BETWEEN_TRIES_SECONDS)


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else os.environ.get("ROBINAUTS_TEST_DATABASE_URL")
    if not url:
        print(
            "usage: wait_for_postgres.py [url] (or set ROBINAUTS_TEST_DATABASE_URL)",
            file=sys.stderr,
        )
        return 2
    problem = asyncio.run(wait_for(url))
    if problem is not None:
        print(f"the database never became ready: {problem}", file=sys.stderr)
        return 1
    print("the database answered a query; going on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
