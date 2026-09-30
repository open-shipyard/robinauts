#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The demo's server container (demo/compose/compose.yaml): write the configuration with
# the clone's own demo/config.py, create the schema, and serve.
#
# The same choices demo/local/start.sh makes, from the same variables: one provider
# key, OpenRouter first, then Anthropic, then OpenAI, unless
# ROBINAUTS_DEMO_PROVIDER names one; three models per key, which
# ROBINAUTS_DEMO_MODEL, _2 and _3 override; GitHub's MCP server when
# ROBINAUTS_GITHUB_TOKEN is set. The model table is start.sh's, and a change to
# one is a change to both.
#
# **No key is printed or written to a file**: the configuration names the
# variable, and every key but the chosen one is unset before the server starts.
# The database's password arrives as PGPASSWORD, which the driver reads itself.
#
# The local development mode binds the loopback interface and refuses any
# other, so the server listens on 127.0.0.1:8001 and socat forwards the
# container's port 8000 to it; compose.yaml publishes that on this machine's
# loopback alone.
set -eu

fail() {
    printf '%s\n' "$1" >&2
    exit 2
}

: "${ROBINAUTS_DATABASE_URL:?set ROBINAUTS_DATABASE_URL}"
[ -n "${PGPASSWORD:-}" ] || fail "set ROBINAUTS_DEMO_DB_PASSWORD in demo/.env"

SRC=/src
export ROBINAUTS_CONFIG=/etc/robinauts/robinauts.toml

title_of() {
    # demo/local/start.sh's rule: the default's title for the default model, and none
    # for one the operator chose, which config.py then calls by its name.
    if [ "$1" = "$2" ]; then printf '%s\n' "$3"; else printf '\n'; fi
}

chosen=${ROBINAUTS_DEMO_PROVIDER:-}
if [ -z "$chosen" ]; then
    if [ -n "${OPENROUTER_API_KEY:-}" ]; then
        chosen=openrouter
    elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        chosen=anthropic
    elif [ -n "${OPENAI_API_KEY:-}" ]; then
        chosen=openai
    else
        fail "set OPENROUTER_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY in demo/.env"
    fi
fi

case "$chosen" in
openrouter)
    [ -n "${OPENROUTER_API_KEY:-}" ] || fail "ROBINAUTS_DEMO_PROVIDER=openrouter, and OPENROUTER_API_KEY is not set"
    kind=anthropic-compatible key_variable=OPENROUTER_API_KEY base_url=https://openrouter.ai/api
    id=claude-sonnet-5 default=anthropic/claude-sonnet-5 default_title="Claude Sonnet 5"
    id_2=gpt-5-5 default_2=openai/gpt-5.5 default_title_2="GPT-5.5"
    id_3=gemini-3-8-flash default_3=google/gemini-3.8-flash default_title_3="Gemini 3.8 Flash"
    unset ANTHROPIC_API_KEY OPENAI_API_KEY
    ;;
anthropic)
    [ -n "${ANTHROPIC_API_KEY:-}" ] || fail "ROBINAUTS_DEMO_PROVIDER=anthropic, and ANTHROPIC_API_KEY is not set"
    kind=anthropic key_variable=ANTHROPIC_API_KEY base_url=
    id=claude-sonnet-5 default=claude-sonnet-5 default_title="Claude Sonnet 5"
    id_2=claude-opus-5-5 default_2=claude-opus-5-5 default_title_2="Claude Opus 5.5"
    id_3=claude-haiku-4-5 default_3=claude-haiku-4-5 default_title_3="Claude Haiku 4.5"
    unset OPENROUTER_API_KEY OPENAI_API_KEY
    ;;
openai)
    [ -n "${OPENAI_API_KEY:-}" ] || fail "ROBINAUTS_DEMO_PROVIDER=openai, and OPENAI_API_KEY is not set"
    kind=openai key_variable=OPENAI_API_KEY base_url=
    id=gpt-5-5 default=gpt-5.5 default_title="GPT-5.5"
    id_2=gpt-5-4-mini default_2=gpt-5.4-mini default_title_2="GPT-5.4 Mini"
    id_3=gpt-5-4-nano default_3=gpt-5.4-nano default_title_3="GPT-5.4 Nano"
    unset OPENROUTER_API_KEY ANTHROPIC_API_KEY
    ;;
*)
    fail "ROBINAUTS_DEMO_PROVIDER is openrouter, anthropic or openai, not $chosen"
    ;;
esac

model=${ROBINAUTS_DEMO_MODEL:-$default}
model_2=${ROBINAUTS_DEMO_MODEL_2:-$default_2}
model_3=${ROBINAUTS_DEMO_MODEL_3:-$default_3}

if [ -n "${ROBINAUTS_GITHUB_TOKEN:-}" ]; then
    github_env=ROBINAUTS_GITHUB_TOKEN
    tools="GitHub's MCP server, for both agents"
else
    unset ROBINAUTS_GITHUB_TOKEN
    github_env=
    tools="none (no ROBINAUTS_GITHUB_TOKEN)"
fi

/opt/venv/bin/python "$SRC/demo/config.py" \
    --template "$SRC/demo/robinauts.toml.in" --out "$ROBINAUTS_CONFIG" \
    --provider-id "$chosen" --kind "$kind" --key-variable "$key_variable" \
    --model "$id" "$model" "$(title_of "$model" "$default" "$default_title")" \
    --model "$id_2" "$model_2" "$(title_of "$model_2" "$default_2" "$default_title_2")" \
    --model "$id_3" "$model_3" "$(title_of "$model_3" "$default_3" "$default_title_3")" \
    --base-url "$base_url" --github-secret-env "$github_env"

printf 'Provider: %s (%s); models %s, %s, %s; key from %s.\n' \
    "$kind" "$chosen" "$model" "$model_2" "$model_3" "$key_variable"
printf 'Tools: %s.\n' "$tools"
printf 'Built from %s.\n' "$(cat "$SRC/.built-from")"

/opt/venv/bin/robinauts db init
socat TCP-LISTEN:8000,fork,reuseaddr TCP:127.0.0.1:8001 &
printf 'Serving on http://127.0.0.1:8000/ once the server says it is running.\n'
exec /opt/venv/bin/robinauts start --dev-no-sign-in --port 8001
