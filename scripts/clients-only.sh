#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# Says whether a pull request changes only files under clients/, in the form
# $GITHUB_OUTPUT reads. CI's `test` and `ui` jobs skip on `clients_only=true`.
# A rename counts as both of its paths, so a file moved into clients/ from
# elsewhere is a change elsewhere too. An empty diff answers false.
#
#     scripts/clients-only.sh <base> <head>
set -eu

if [ "$#" -ne 2 ]; then
    printf 'usage: %s <base> <head>\n' "$0" >&2
    exit 2
fi

changed=$(git diff --no-renames --name-only "$1...$2")

if [ -n "$changed" ] && ! printf '%s\n' "$changed" | grep -qv '^clients/'; then
    echo clients_only=true
else
    echo clients_only=false
fi
