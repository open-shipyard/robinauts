#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The demo in containers (compose.yaml): build the server's image from the
# repository's main, start it and its PostgreSQL, and wait until it answers.
# demo/compose/stop.sh takes it down again, and README.md beside this file is
# the whole of what it does.
#
# What it reads is demo/.env, the file demo/local/start.sh reads too, which is
# why this script exists at all: Compose looks for a .env beside compose.yaml
# only, and one file for both demos is one place to put a key. The environment
# wins over the file. Further arguments go to `docker compose up`.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE=$(CDPATH= cd -- "$here/.." && pwd)/.env
ENV_MODE=600
URL=http://127.0.0.1:8000/
HEALTH_SECONDS=180
# Generous on purpose: the first start builds an image, and the server then
# has a schema to create before it answers.

fail() {
    printf '%s\n' "$1" >&2
    exit "${2:-1}"
}

command -v docker >/dev/null 2>&1 ||
    fail "docker is not on the PATH: see https://docs.docker.com/engine/install/" 2
docker compose version >/dev/null 2>&1 ||
    fail "docker compose is not available: see https://docs.docker.com/compose/install/" 2

[ -f "$ENV_FILE" ] || fail "no $ENV_FILE: it holds the database's password and a model key (README.md)." 2
mode=$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null || true)
[ "$mode" = "$ENV_MODE" ] ||
    fail "$ENV_FILE is mode ${mode:-unreadable} and holds secrets: chmod $ENV_MODE it first." 2
if [ -z "${ROBINAUTS_DEMO_DB_PASSWORD:-}" ] &&
    ! grep -q '^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}ROBINAUTS_DEMO_DB_PASSWORD=.' "$ENV_FILE"; then
    fail "no ROBINAUTS_DEMO_DB_PASSWORD in $ENV_FILE; add one with:
    printf 'ROBINAUTS_DEMO_DB_PASSWORD=%s\\n' \"\$(openssl rand -hex 32)\" >> $ENV_FILE" 2
fi

compose() {
    docker compose --project-directory "$here" -f "$here/compose.yaml" --env-file "$ENV_FILE" "$@"
}

compose up --build --detach "$@" || fail "docker compose up failed; it said why above." 1

printf 'Waiting for %s ...\n' "$URL"
waited=0
until curl -fsS -o /dev/null "${URL}health" 2>/dev/null; do
    waited=$((waited + 1))
    if [ "$waited" -ge "$HEALTH_SECONDS" ]; then
        compose logs --tail 30 robinauts >&2 || true
        fail "the server did not answer within $HEALTH_SECONDS seconds; its log is above." 1
    fi
    sleep 1
done

printf '\nThe demo is up: %s\n' "$URL"
printf '  logs: docker compose -f %s logs -f robinauts\n' "$here/compose.yaml"
printf '  stop: demo/compose/stop.sh   (--reset also drops the database)\n'
