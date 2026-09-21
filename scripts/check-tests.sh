#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The backend test suite, including the architecture contracts of
# docs/layout.md. Further arguments are passed on to pytest.
#
# ROBINAUTS_TEST_DATABASE_URL, if it is set in the environment, is the
# PostgreSQL the tests under backend/tests/integration/ use; they create and
# drop a schema of their own in it. Without it those tests skip and the rest
# of the suite runs as it always does, so this script needs no argument and
# no mode: CONTRIBUTING.md says how to set it.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/backend"

# conftest.py stops bytecode being written, but not its own: pytest imports it
# before it can say so. A stray __pycache__ in the tree is what `reuse lint`
# then reads, so nothing is written at all here.
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

uv run --locked pytest "$@"
