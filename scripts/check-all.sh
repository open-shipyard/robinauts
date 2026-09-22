#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# Every gate CI runs, in one go. CI runs these same scripts, one per job, so a
# green run here is a green run there.
set -u

if [ "$#" -ne 0 ]; then
    printf '%s takes no arguments (got: %s)\n' "$0" "$*" >&2
    exit 2
fi

# No set -e here: every check runs, and the failures are collected below.
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2

failed=""
for check in lint tests licences audit frontend reuse dco; do
    printf '\n=== %s ===\n' "$check"
    if ! "$root/scripts/check-$check.sh"; then
        failed="$failed $check"
    fi
done

if [ -n "$failed" ]; then
    printf '\nFailed:%s\n' "$failed"
    exit 1
fi
printf '\nEvery check passed.\n'
