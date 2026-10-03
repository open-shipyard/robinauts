#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The interface in a real browser: backend/tests/ui/, which a plain test run
# does not collect. It builds the interface, installs Playwright's Chromium and
# runs the tests against a server on the echo engine, which needs no key.
# Slower than the rest of the suite, so CI runs it after the fast tests.
# Further arguments are passed on to pytest.
#
# ROBINAUTS_TEST_DATABASE_URL must name a PostgreSQL the tests may create and
# drop a schema in, as for the database tests (CONTRIBUTING.md); the server
# stores there.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# nvm, if this machine has it, for the Node of frontend/.nvmrc; not on CI,
# where setup-node has already put it on the PATH (scripts/check-frontend.sh).
if [ -z "${CI:-}" ] && [ -z "${ROBINAUTS_NODE_CHOSEN:-}" ] &&
    [ -s "$HOME/.nvm/nvm.sh" ] && command -v bash >/dev/null 2>&1; then
    ROBINAUTS_NODE_CHOSEN=1
    export ROBINAUTS_NODE_CHOSEN
    exec bash -c 'cd "$1/frontend" && . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 &&
        nvm use >/dev/null 2>&1 && shift && exec "$@"' \
        bash "$root" "$root/scripts/check-ui.sh" "$@"
fi

# The interface the server serves, built from the lock. CHECK_BUNDLED keeps
# the build from rewriting bundled-packages.txt.
cd "$root/frontend"
npm ci --ignore-scripts
CHECK_BUNDLED=1 npm run build

cd "$root/backend"
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

# The Chromium of the locked Playwright; on CI, with the system libraries it
# needs, which the runner may lack.
uv run --locked --no-build playwright install ${CI:+--with-deps} chromium

uv run --locked --no-build pytest tests/ui "$@"
