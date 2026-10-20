# syntax=docker/dockerfile:1

# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

# Node 24: frontend/package.json pins `engines.node >= 24`, and the host's Node 20
# is what produced the EBADENGINE warnings. Build this with the repo root as the
# context (see docker-compose.yml): `npm run generate` reads ../backend/openapi.json,
# so the backend's file has to be in the image too.
FROM node:24-bookworm-slim

# socat forwards this container's loopback :8000 to the `backend` service over the
# compose network. The Vite dev server proxies /api, /auth, /health and
# /openapi.json to a hardcoded http://127.0.0.1:8000 (frontend/vite.config.ts);
# this makes that address reach the backend without editing the config.
RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/frontend

# Dependencies first, in their own cached layer: package.json and the lockfile
# change rarely, so this layer is reused across ordinary source edits.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# The source, plus the backend's OpenAPI document `npm run generate` reads from
# ../backend (relative to this WORKDIR). Both are bind-mounted over in compose for
# live editing; these copies are what an image run without the mounts uses.
COPY frontend/ ./
COPY backend/openapi.json /app/backend/openapi.json

EXPOSE 5173

# Forward loopback :8000 to the backend (background), regenerate the API types,
# then run Vite bound to all interfaces so the published port is reachable.
CMD ["sh", "-c", "socat TCP-LISTEN:8000,fork,reuseaddr TCP:${BACKEND_HOST:-backend}:8000 & npm run generate && exec npx vite --host 0.0.0.0 --port 5173"]
