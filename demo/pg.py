#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The demo's own PostgreSQL: a throwaway cluster on the loopback interface.

The demo has to bring a database, and this machine may have none. ``pgserver``
ships PostgreSQL's own binaries in a wheel, so ``uv`` can fetch a server the
way it fetches a library and the demo needs nothing installed
(``demo/README.md`` records the version and the licence). It is **not a
dependency of the platform**: nothing under ``backend/`` imports it, it is not
in ``backend/uv.lock``, and it is run as a tool -- ``uv run --with
pgserver==<version> --no-project python demo/pg.py`` -- so that a demo script
cannot put a development tool into what a deployment installs.

``pgserver``'s own ``get_server`` is deliberately not used: it binds a unix
socket and no TCP port, and what the demo hands the server is a
``postgresql://`` URL with a host and a port in it, as a deployment's would be
(``docs/deployment.md``). So the two binaries that matter, ``initdb`` and
``pg_ctl``, are driven directly with the arguments this demo wants, which is
the same thing ``scripts/rehearse-deployment.sh`` does with the driver: borrow
the tool, decide nothing by accident.

Four commands, and each is safe to run again:

    start   the cluster is running and the database exists
    stop    the cluster is not running
    status  exit 0 if it is running, ``NOT_RUNNING`` if it is not
    url     print the URL of that database on that cluster

``start`` creates the database as well as starting the server, because
creating it needs the client binaries and this process is the only one that has
them; a second script would be a second copy of where they live.

**Loopback only, trust authentication, and no password anywhere.** There is no
password for a script to print, put in a file or leak into a log, and what
stands in its place is two walls: the server listens on ``127.0.0.1`` alone, so
nothing off this machine can reach it, and its unix socket lives in a directory
inside ``pgdata``, which ``initdb`` makes ``0700``, so nothing but this account
can reach *that*.

What those two do **not** stop is another account **on this machine** opening
the loopback port and being trusted as ``postgres``. That is what ``trust``
means, and it is the reason this is a demo on one person's laptop and not a way
to run anything: a deployment gives the database a role and a password of its
own (``docs/deployment.md``), and the README says so too.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import pgserver
from pgserver._commands import POSTGRES_BIN_PATH

HOST = "127.0.0.1"
"""Where the cluster listens, and the whole of who may reach it."""

SUPERUSER = "postgres"
"""The role ``initdb`` makes, named as the test cluster's is for one reason:
the URL a reader sees here is the URL they have seen before."""

PORT_VARIABLE = "ROBINAUTS_DEMO_PG_PORT"
"""What an operator changes the port with; demo/README.md lists it."""

DEFAULT_PORT = 54390
"""Not 5432, and not the 54329 the test suite's cluster uses: the demo must not
find somebody else's server on its port and must not be found on theirs."""

DEFAULT_DATABASE = "robinauts_demo"
"""A name nothing else would choose, so this cannot be a real deployment's."""

MAX_PORT = 65535

PORT_LINE = 4
"""Which line of ``postmaster.pid`` holds the port (pid, pgdata, start, port)."""

NOT_RUNNING = 3
"""What ``status`` exits when there is no server: ``pg_ctl``'s own code for it,
so that a reader who knows one knows the other."""

_DATABASE_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")
"""What a database this script will name in a statement may be called.

A database name is not a value in SQL and cannot be parametrised: every
statement here has to spell it out. Rather than quote it, the name is held to
something that needs no quoting -- which is enough for a demo that has one
database and a flag for changing its name.
"""

START_SECONDS = 60.0
"""``pg_ctl -w`` waits for the server itself; this bounds the wait."""

STOP_SECONDS = 60.0

TIME_ZONE = "Asia/Kathmandu"
"""Deliberately not UTC, and deliberately not a whole number of hours.

The demo is where somebody looks at times on a screen, and a server on UTC is
where a zone bug is invisible: a naive-to-aware round trip is exact when the
process and the server happen to agree. The platform sets no session zone
(``datastore/pool.py``), so this is the one place the demo can ask the question
at all.
"""


def is_database_name(value: str) -> bool:
    """Whether that name can be written into a statement as it stands."""
    return _DATABASE_NAME.fullmatch(value) is not None


def pgdata_default() -> Path:
    """``demo/.state/pgdata``, beside this file, wherever the demo was run from."""
    return Path(__file__).resolve().parent / ".state" / "pgdata"


def url_for(port: int, database: str) -> str:
    """The URL the server is handed: this machine, that port, that database."""
    return f"postgresql://{SUPERUSER}@{HOST}:{port}/{database}"


def listening_port(pgdata: Path) -> int | None:
    """The port the running server took, out of its own ``postmaster.pid``.

    The fourth line of that file, which a server writes when it starts and
    removes when it stops. It is how "it is running, but not where you think"
    is told from "it is running": a cluster that was started on another port --
    a ``ROBINAUTS_DEMO_PG_PORT`` changed while it was up -- is a server nothing
    would connect to, and a demo that carried on would hand the platform a URL
    that reaches nothing.
    """
    try:
        lines = (pgdata / "postmaster.pid").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < PORT_LINE:
        return None
    found = lines[PORT_LINE - 1].strip()
    return int(found) if found.isdigit() else None


def running(pgdata: Path, port: int | None = None) -> bool:
    """Whether a server is answering for that data directory, and on that port.

    Two questions, because either alone can be answered wrongly.
    ``pg_ctl status`` exits 0 when a process is there, 3 when the directory is
    and nothing is running, and 4 when there is no directory -- but a process
    that is still starting, or wedged, is not a server that answers. So
    ``pg_isready`` is asked too, on the port the caller means, and only both
    together are read as "yes": anything else is "start it", and starting an
    already-started server is refused by ``pg_ctl`` itself rather than by a
    guess made here.
    """
    if not (pgdata / "PG_VERSION").exists():
        return False
    if _ran(["status"], pgdata).returncode != 0:
        return False
    if port is None:
        return True
    return _tried([str(POSTGRES_BIN_PATH / "pg_isready"), "-h", HOST, "-p", str(port)]) == 0


def start(pgdata: Path, port: int, database: str) -> None:
    """The cluster is running on that port and holds that database."""
    taken = listening_port(pgdata)
    if taken is not None and taken != port and _ran(["status"], pgdata).returncode == 0:
        raise SystemExit(
            f"the cluster under {pgdata} is already running on port {taken}, not"
            f" {port}. Stop it first (demo/stop.sh), or set"
            f" {PORT_VARIABLE}={taken} to use it where it is."
        )
    pgdata.parent.mkdir(parents=True, exist_ok=True)
    if not (pgdata / "PG_VERSION").exists():
        pgdata.mkdir(parents=True, exist_ok=True)
        # `--auth=trust` on a server nothing off this machine can connect to.
        # A password would be a secret for a demo script to keep, and a demo
        # script is the worst place to keep one.
        pgserver.initdb(
            ["--auth=trust", "--auth-local=trust", "--encoding=utf8", "-U", SUPERUSER],
            pgdata=pgdata,
        )
    if not running(pgdata, port):
        sockets = pgdata / "sockets"
        sockets.mkdir(exist_ok=True)
        pgserver.pg_ctl(
            [
                "-w",
                "-l",
                str(pgdata / "log"),
                "-o",
                f"-h {HOST} -p {port} -k {sockets} -c timezone={TIME_ZONE}",
                "start",
            ],
            pgdata=pgdata,
            timeout=START_SECONDS,
        )
    _database(port, database)


def stop(pgdata: Path) -> bool:
    """Stop the cluster, and say whether there was one. Nothing to stop is fine.

    The port is deliberately not asked about here: a server that is up but not
    answering is still a server to stop, and ``stop`` is the one command that
    should take whatever it finds.
    """
    if not running(pgdata):
        return False
    pgserver.pg_ctl(["-w", "-m", "fast", "stop"], pgdata=pgdata, timeout=STOP_SECONDS)
    return True


def _database(port: int, database: str) -> None:
    """That database exists on that cluster.

    Asked for by name rather than created and forgiven: ``createdb`` on one
    that is there fails, and a failure that has to be read to be excused is a
    failure that hides the next one.
    """
    if _query(port, f"SELECT 1 FROM pg_database WHERE datname = '{database}'").strip():
        return
    pgserver.createdb(["-h", HOST, "-p", str(port), "-U", SUPERUSER, database])


def _query(port: int, statement: str) -> str:
    """One statement's answer, unaligned and with no header: for asking, not printing."""
    return pgserver.psql(
        ["-h", HOST, "-p", str(port), "-U", SUPERUSER, "-d", "postgres", "-tAc", statement]
    )


def _ran(arguments: list[str], pgdata: Path) -> subprocess.CompletedProcess[bytes]:
    """``pg_ctl`` with its exit code handed back rather than raised on.

    ``pgserver``'s wrappers pass ``check=True``, which is right for every call
    but this one: ``pg_ctl status`` answers a *question* with its exit code.
    """
    return subprocess.run(
        [str(POSTGRES_BIN_PATH / "pg_ctl"), "-D", str(pgdata), *arguments],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _tried(command: list[str]) -> int:
    """That command's exit code, with everything it said thrown away.

    The same reason as ``_ran``: ``pg_isready`` answers a question with its
    code, and what it prints is for a person at a terminal.
    """
    return subprocess.run(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    ).returncode


def main(argv: list[str] | None = None) -> int:
    """The command. Exits 2 for a usage or environment problem, 1 for a failure."""
    parser = argparse.ArgumentParser(
        prog="demo/pg.py", description="the demo's throwaway PostgreSQL"
    )
    parser.add_argument("command", choices=["start", "status", "stop", "url"])
    parser.add_argument("--pgdata", type=Path, default=None, help="the data directory")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"the port it listens on ({PORT_VARIABLE}, or {DEFAULT_PORT})",
    )
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    arguments = parser.parse_args(argv)
    pgdata = arguments.pgdata or pgdata_default()

    # The variable is read here rather than as the argument's default, so that
    # a variable holding something that is not a number is one line like every
    # other refusal instead of a traceback out of argparse.
    given = (os.environ.get(PORT_VARIABLE) or "").strip()
    if arguments.port is None:
        if given and not given.isdigit():
            print(f"{PORT_VARIABLE} is not a port: {given!r}", file=sys.stderr)
            return 2
        arguments.port = int(given) if given else DEFAULT_PORT
    if not 1 <= arguments.port <= MAX_PORT:
        print(f"{arguments.port} is not a port", file=sys.stderr)
        return 2
    if not is_database_name(arguments.database):
        # Every statement below names it, and none of them can parametrise a
        # database name: that is not a value in SQL.
        print(f"{arguments.database!r} is not a database name", file=sys.stderr)
        return 2
    if arguments.command == "url":
        print(url_for(arguments.port, arguments.database))
        return 0
    if arguments.command == "status":
        return 0 if running(pgdata, arguments.port) else NOT_RUNNING
    if arguments.command == "stop":
        stop(pgdata)
        return 0
    if not POSTGRES_BIN_PATH.is_dir():
        # Cannot happen through `uv run --with pgserver`; said plainly rather
        # than as a traceback if that wheel ever ships without its binaries.
        print(f"no PostgreSQL binaries at {POSTGRES_BIN_PATH}", file=sys.stderr)
        return 2
    start(pgdata, arguments.port, arguments.database)
    print(url_for(arguments.port, arguments.database))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
