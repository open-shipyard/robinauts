#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The other end of demo/compose/start.sh: stop both containers.
#
#     demo/compose/stop.sh             stop them; the conversations stay
#     demo/compose/stop.sh --reset     and drop the database's volume
#
# --reset is also how a changed ROBINAUTS_DEMO_DB_PASSWORD is taken: the
# database reads it once, when its volume is first made.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

case "${1:-}" in
"") volumes= ;;
--reset) volumes=--volumes ;;
*)
    printf 'usage: demo/compose/stop.sh [--reset]\n' >&2
    exit 2
    ;;
esac
[ "$#" -le 1 ] || {
    printf 'usage: demo/compose/stop.sh [--reset]\n' >&2
    exit 2
}

# No --env-file: `down` interpolates the file too, and a missing password would
# stop it from taking down what is running. What it needs is the project's
# name, which compose.yaml says itself.
ROBINAUTS_DEMO_DB_PASSWORD=${ROBINAUTS_DEMO_DB_PASSWORD:-unused-by-down} \
    docker compose --project-directory "$here" -f "$here/compose.yaml" down $volumes
