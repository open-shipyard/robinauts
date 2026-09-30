# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The demo's server (demo/compose/compose.yaml): a shallow clone of the repository at
# REF, its interface built, its backend installed from backend/uv.lock, and
# served in the local development mode. What it serves is whatever REF is when
# the image is built, not this checkout: the build context is demo/compose/ and
# only the entrypoint is taken from it (demo/compose/.dockerignore).

ARG UV_VERSION=0.12.6
# scripts/tool-versions.sh, the one CI installs. An ARG before the first FROM
# is the only way a version reaches the `FROM` below.

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM ubuntu:26.04

ARG REPO=https://github.com/open-shipyard/robinauts.git
ARG REF=main

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git socat xz-utils \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

# Rebuilt from here whenever REF moves: the answer changes with its commit, and
# a cached layer would otherwise keep serving the clone of the first build.
ADD https://api.github.com/repos/open-shipyard/robinauts/git/refs/heads/${REF} /tmp/ref.json
RUN git clone --depth 1 --branch "$REF" "$REPO" /src \
 && printf '%s at %s\n' "$REF" "$(git -C /src rev-parse --short HEAD)" >/src/.built-from

WORKDIR /src/frontend

# Node at the major .nvmrc names, as a developer's nvm would pick it, fetched
# over HTTPS alone (`--proto =https`, redirects included) and checked against
# the release's own SHASUMS256.txt before it is unpacked. Then the interface,
# with no package's install scripts run (`--ignore-scripts`, as .npmrc and CI
# have it). One RUN, since Node is here for this build and nothing else.
RUN major=$(cat .nvmrc) \
 && arch=$(dpkg --print-architecture | sed 's/amd64/x64/') \
 && base="https://nodejs.org/dist/latest-v${major}.x" \
 && curl --proto '=https' --tlsv1.2 -fsSL "$base/SHASUMS256.txt" -o /tmp/SHASUMS256.txt \
 && file=$(grep -o "node-v${major}[^ ]*-linux-${arch}\.tar\.xz" /tmp/SHASUMS256.txt | head -n 1) \
 && curl --proto '=https' --tlsv1.2 -fsSL "$base/$file" -o "/tmp/$file" \
 && (cd /tmp && grep " $file\$" SHASUMS256.txt | sha256sum -c -) \
 && tar -xJf "/tmp/$file" -C /usr/local --strip-components=1 \
 && rm -f "/tmp/$file" /tmp/SHASUMS256.txt \
 && npm ci --ignore-scripts \
 && npm run build

WORKDIR /src/backend

# CPython 3.12, as demo/local/start.sh and CI run it; the interface built above
# goes into the package the server imports. `--no-build`: every dependency
# comes as the wheel the lock names, and nothing runs a setup script -- uv
# still builds this project itself, which is the one package whose build
# script is ours.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --locked --no-dev --no-editable --no-build --python 3.12

COPY --chmod=755 container-entrypoint.sh /usr/local/bin/container-entrypoint.sh
RUN mkdir -p /etc/robinauts && chown ubuntu /etc/robinauts

USER ubuntu
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/container-entrypoint.sh"]
