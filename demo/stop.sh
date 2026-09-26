#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The other end of demo/start.sh: stop the server, then the PostgreSQL it was
# talking to. Safe to run when nothing is running, and safe to run twice.
#
#     demo/stop.sh             stop both; the conversations stay
#     demo/stop.sh --reset     and delete demo/.state, which is the data
#
# --reset is how the demo is started again from nothing: the data directory, the
# generated configuration, the log and the pid file all live under demo/.state
# and none of them is committed.
set -eu

demo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=demo/common.sh
. "$demo/common.sh"

TERM_SECONDS=30
# What the server is given to stop by itself. It shuts down gracefully -- open
# connections finish, the runs in flight are ended, the pool and the clients are
# given back -- and app.SHUTDOWN_SECONDS is the budget it does that in, so this
# is the bound on a stop that is working, not a guess at one.

TERM_TRIES_PER_SECOND=5

reset=no
case "${1:-}" in
"") ;;
--reset) reset=yes ;;
*) fail "usage: demo/stop.sh [--reset]" 2 ;;
esac
[ "$#" -le 1 ] || fail "usage: demo/stop.sh [--reset]" 2

# --- the server --------------------------------------------------------------

server=$(server_pid)
if [ -n "$server" ]; then
    say "Stopping the server (pid $server) ..."
    kill "$server" 2>/dev/null || true
    waited=0
    while kill -0 "$server" 2>/dev/null; do
        if [ "$waited" -ge $((TERM_SECONDS * TERM_TRIES_PER_SECOND)) ]; then
            # It was asked and would not go. A demo is not the place to leave a
            # process holding the port, so it is ended -- said out loud, because
            # a server that ignores SIGTERM is worth knowing about.
            say "It did not stop within ${TERM_SECONDS}s; ending it (SIGKILL)."
            kill -9 "$server" 2>/dev/null || true
            break
        fi
        waited=$((waited + 1))
        sleep 0.2
    done
    rm -f "$PID_FILE"
    say "The server has stopped."
else
    say "No server was running."
fi

# --- the database ------------------------------------------------------------

if [ ! -d "$PGDATA" ]; then
    say "There is no demo database to stop."
elif pg status; then
    say "Stopping the demo's PostgreSQL ..."
    pg stop || fail "the demo's PostgreSQL would not stop; its log is $PGDATA/log." 1
    say "The database has stopped."
else
    # A data directory with nothing running under it: the usual state after a
    # stop, and saying "stopped" over it would be a line that means nothing.
    say "No database was running."
fi

# --- and, if asked, the data -------------------------------------------------

if [ "$reset" = yes ]; then
    # Only ever this directory, and only after the cluster has been stopped:
    # deleting a running server's data directory is how a server is left running
    # with nothing under it.
    say "Deleting $state ..."
    rm -rf "$state"
    say "Gone. demo/start.sh starts again from nothing."
fi
