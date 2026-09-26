# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# What demo/start.sh and demo/stop.sh both need: where the demo keeps its
# state, how it borrows a PostgreSQL, and how it says something went wrong.
# Sourced, never run --- there is one entry point for starting the demo and one
# for stopping it, and this is neither.
#
# It expects `demo` to be set to this directory by whoever sources it, since a
# sourced file cannot ask where it is.

# shellcheck shell=sh

root=$(CDPATH= cd -- "$demo/.." && pwd)
state="$demo/.state"

CONFIG="$state/robinauts.toml"
PID_FILE="$state/server.pid"
LOG_FILE="$state/server.log"
PGDATA="$state/pgdata"
VENV="$state/venv"

ROBINAUTS="$VENV/bin/robinauts"
# The demo installs the platform into an environment of its own, **not** into
# backend/.venv, and not editably. Both halves matter:
#
# - the interface is served from inside the installed package, as
#   `robinauts/ui/`, which is where the wheel's build hook puts frontend/dist
#   (backend/hatch_build.py). An editable install has no such directory, and
#   /ui/ would answer the "not built" page however many times the frontend had
#   been built (app.packaged_ui);
# - a developer's backend/.venv is what the tests and `uv run` use, and a demo
#   is no reason to turn it into something else.
#
# `demo/stop.sh --reset` deletes it with the rest of demo/.state, so a demo
# started again from nothing really is.

PGSERVER_VERSION=0.1.4
# The exact version of the PostgreSQL-in-a-wheel the demo borrows a server
# from, pinned here and recorded with its licence in demo/README.md. It is a
# demo-only tool, fetched by `uv run --with`, and deliberately not a dependency
# of the platform: nothing under backend/ imports it and it is not in
# backend/uv.lock (DEPENDENCIES.md).

PYTHON=3.12
# The one interpreter the demo uses, for everything. Named rather than left to
# `uv`, which would take the newest it has, for two reasons at once:
#
# - it is the version CI runs every gate on (.github/workflows/ci.yml,
#   PYTHON_VERSION) and the one backend/uv.lock is resolved and checked
#   against, so the demo runs the platform on the interpreter that was judged
#   rather than on whichever one this machine happens to have;
# - pgserver publishes no wheel for the newest CPython, so naming one it builds
#   for is the difference between a demo that starts and an unsatisfiable
#   resolution.

HOST=127.0.0.1
# The demo's whole world. The local development mode refuses any other bind
# address before it binds a socket (docs/specs/sign-in.md).

DEFAULT_PORT=8000
PORT=${ROBINAUTS_DEMO_PORT:-$DEFAULT_PORT}

fail() {
    # One line and a non-zero exit. 2 is "put this right and run it again", 1 is
    # "something went wrong while it was running".
    printf '%s\n' "$1" >&2
    exit "${2:-1}"
}

say() {
    printf '%s\n' "$1"
}

file_mode() {
    # That file's permission bits in octal, or nothing at all when neither
    # spelling of `stat` is the one this machine has. GNU's `-c` is Linux's and
    # BSD's `-f` is macOS's; a caller that gets nothing says so rather than
    # reading "" as "safe".
    stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null || true
}

pg() {
    # demo/pg.py, with the PostgreSQL binaries `uv` fetched for it. Everything
    # about where the server lives is here, so the two scripts cannot disagree
    # about which cluster they mean.
    uv run --no-project --python "$PYTHON" \
        --with "pgserver==$PGSERVER_VERSION" python "$demo/pg.py" "$@" \
        --pgdata "$PGDATA"
}

server_pid() {
    # The pid of a server that is really there, or nothing. A pid file left
    # behind by a process that has gone says nothing about now, so it is
    # removed rather than believed.
    #
    # And a pid is handed out again: the process is asked **what it is** before
    # anything signals it, so that stopping the demo can never end a stranger's
    # program that happened to be given the number. Where there is no /proc to
    # ask, the answer is the pid file, as it was before.
    [ -f "$PID_FILE" ] || return 0
    found=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$found" ] && kill -0 "$found" 2>/dev/null; then
        cmdline="/proc/$found/cmdline"
        # The **executable this demo started**, not the word "robinauts": a
        # developer's own `robinauts start` from backend/.venv is somebody
        # else's server, and stopping the demo must not stop it.
        if [ ! -r "$cmdline" ] || tr '\0' '\n' <"$cmdline" | grep -qxF "$ROBINAUTS"; then
            printf '%s\n' "$found"
            return 0
        fi
    fi
    rm -f "$PID_FILE"
}
