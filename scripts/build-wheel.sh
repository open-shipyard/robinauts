#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The release artifact: one wheel holding the backend, the schema and the built
# interface (docs/specs/frontend.md). The frontend is built first, because the
# wheel cannot be built without it -- backend/hatch_build.py refuses -- and
# because built files are never committed, so there is nothing to be stale.
#
# One argument: the directory to write the wheel into. It prints the path of
# the wheel it built and nothing else on stdout, so that a caller can read it.
set -eu

if [ "$#" -ne 1 ]; then
    printf 'usage: %s <output-directory>\n' "$0" >&2
    exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out=$1
mkdir -p "$out"
out=$(CDPATH= cd -- "$out" && pwd)

# nvm, if this machine has it, for the same reason check-frontend.sh does it:
# a laptop with an older Node in its PATH builds with the version .nvmrc names.
# Not on CI, where setup-node has already put that version there.
if [ -z "${CI:-}" ] && [ -z "${ROBINAUTS_NODE_CHOSEN:-}" ] &&
    [ -s "$HOME/.nvm/nvm.sh" ] && command -v bash >/dev/null 2>&1; then
    ROBINAUTS_NODE_CHOSEN=1
    export ROBINAUTS_NODE_CHOSEN
    exec bash -c '. "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 && nvm use >/dev/null 2>&1
        exec "$@"' bash "$root/scripts/build-wheel.sh" "$out"
fi

cd "$root/frontend"

# `npm ci` only when there is nothing installed. The frontend's own gate
# (check-frontend.sh) installs from the lock and runs just before this one in
# check-all.sh, and CI's wheel job starts from an empty runner, so the lock is
# what decides either way. What is never skipped is the build: the bundle in
# the wheel is always made here and now.
if [ ! -d node_modules ]; then
    npm ci --ignore-scripts >&2
fi
# CHECK_BUNDLED, as CI's frontend job sets it: the build compares
# bundled-packages.txt with what it would have written instead of rewriting it.
# Building a release must not quietly edit a committed record of what is in the
# bundle (docs/specs/open-source.md).
CHECK_BUNDLED=1 npm run build >&2

cd "$root/backend"

# Built into an empty directory of its own and moved out afterwards, so that
# "the wheel this build made" cannot be a wheel that was already in $out -- an
# earlier version, or one from another branch. Removed however this ends.
fresh=$(mktemp -d)
trap 'rm -rf "$fresh"' EXIT
trap 'rm -rf "$fresh"; exit 130' INT
trap 'rm -rf "$fresh"; exit 143' TERM

# --wheel alone: the source distribution carries no built frontend -- the files
# are outside this directory and are not in it -- so a wheel built from an
# sdist has no interface and is refused (backend/hatch_build.py). The wheel is
# the deliverable (docs/specs/operations.md), and it is built from a checkout.
uv build --wheel --out-dir "$fresh" >&2

count=$(ls -1 "$fresh" | wc -l)
if [ "$count" -ne 1 ]; then
    printf 'expected one wheel from the build, found %s:\n' "$count" >&2
    ls -1 "$fresh" >&2
    exit 1
fi
built=$(ls -1 "$fresh")
mv "$fresh/$built" "$out/$built"
printf '%s\n' "$out/$built"
