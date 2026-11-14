#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The services of this repository (services/README.md): each is a Python project
# of its own, which stands alone and which an operator deploys. For each, in turn:
# its locked environment with every extra, so every optional driver is installed
# and imported where its tests reach it; ruff and black under its own
# configuration (the backend's rules, copied); its import-linter contracts; and
# its tests, but the ones that cost money (tests/adapters_metered/), which run by
# hand. Their licences are checked by scripts/check-licences.sh.
set -eu

if [ "$#" -ne 0 ]; then
    printf '%s takes no arguments (got: %s)\n' "$0" "$*" >&2
    exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# As scripts/check-tests.sh: nothing writes bytecode into the tree.
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

for project in "$root"/services/*/; do
    [ -f "$project/pyproject.toml" ] || continue
    printf '\n== services/%s ==\n' "$(basename "$project")"
    cd "$project"
    uv sync --locked --all-extras
    uv run --locked ruff check .
    uv run --locked black --check .
    uv run --locked lint-imports --no-cache
    uv run --locked pytest -q -p no:cacheprovider --ignore=tests/adapters_metered
done
