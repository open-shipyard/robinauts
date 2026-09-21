#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The backend test suite, including the architecture contracts of
# docs/layout.md. Further arguments are passed on to pytest.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/backend"

uv run --locked pytest "$@"
