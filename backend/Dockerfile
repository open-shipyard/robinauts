# syntax=docker/dockerfile:1

# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

# uv's official image, pinned to the project's Python (pyproject: requires-python >=3.12).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# uv settings tuned for containers:
#   - copy instead of hardlink: the cache mount and the venv live on different filesystems
#   - compile bytecode on install for a faster first request
#   - keep the project venv at a fixed path so a bind-mounted source cannot shadow it
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# socat forwards the published port to the loopback-bound dev server (see CMD):
# `--dev-no-sign-in` binds 127.0.0.1 only and refuses 0.0.0.0, which Docker's
# port publishing cannot otherwise reach.
RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first, in their own cached layer: pyproject.toml and uv.lock
# change rarely, so this layer is reused across ordinary source edits.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Then the source, and the editable install of the project itself. An editable
# install needs no built frontend (see backend/hatch_build.py), so this works in a
# checkout that has never run `npm run build`.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

EXPOSE 8000

# Startup, in shell form so the preflight check is readable here.
#
# PREFLIGHT (runs first): the agents/models config is bind-mounted at runtime, so
# a missing ./robinauts.toml cannot be caught at build time. If it is absent -- or
# is an empty folder, which Docker silently creates for the bind-mount when the
# host file does not exist -- fail fast with a human-friendly message instead of a
# Python stack trace.
#
# THEN: `db init` (a no-op once the schema is current, docs/deployment.md); the
# server binds loopback on 8001 (dev mode forbids 0.0.0.0); socat forwards the
# published port 8000 to it so `localhost:8000` reaches the API; the server runs
# with `exec` so the container's lifetime is the server's. ROBINAUTS_START_ARGS
# lets compose pass e.g. `--dev-no-sign-in`.
CMD CONFIG="${ROBINAUTS_CONFIG:-/config/robinauts.toml}"; \
    if [ ! -e "$CONFIG" ] || [ -d "$CONFIG" ]; then \
      echo ""; \
      echo "  ============================================================"; \
      echo "   Backend startup FAILED."; \
      echo ""; \
      echo "   Did you forget to create your robinauts.toml agents file?"; \
      echo ""; \
      echo "   Expected a config FILE at: $CONFIG"; \
      if [ -d "$CONFIG" ]; then \
        echo "   ...but found an empty FOLDER there. Docker creates one when"; \
        echo "   ./robinauts.toml does not exist on the host at 'up' time."; \
      fi; \
      echo ""; \
      echo "   To fix it:"; \
      echo "     1. docker compose down"; \
      echo "     2. rm -rf ./robinauts.toml      # clears any empty folder"; \
      echo "     3. create ./robinauts.toml      # see the sample in the README"; \
      echo "     4. docker compose up -d"; \
      echo "  ============================================================"; \
      echo ""; \
      exit 1; \
    fi; \
    uv run robinauts db init && \
    { socat TCP-LISTEN:8000,fork,reuseaddr TCP:127.0.0.1:8001 & \
      exec uv run robinauts start --host 127.0.0.1 --port 8001 ${ROBINAUTS_START_ARGS}; }
