#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# ruff and black, over the backend and over the scripts of this repository.
set -eu

if [ "$#" -ne 0 ]; then
    printf '%s takes no arguments (got: %s)\n' "$0" "$*" >&2
    exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/backend"

# backend/pyproject.toml holds the only ruff and black configuration there is.
# The scripts live outside it, so the configuration is named explicitly rather
# than discovered, and they are checked under the same rules as the backend.
uv run --locked ruff check --config pyproject.toml . ../scripts
uv run --locked black --check --config pyproject.toml . ../scripts
