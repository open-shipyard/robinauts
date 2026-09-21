#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The dependency licence gate: the policy of DEPENDENCIES.md over the whole
# locked set of backend/uv.lock. Further arguments are passed on to the gate;
# see scripts/licence_gate.py --help.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root/backend"

# Run under the synced environment: the gate reads the licence metadata of
# what is installed, and asks PyPI only about what this platform leaves out.
uv run --locked python "$root/scripts/licence_gate.py" "$@"
