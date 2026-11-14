# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The one place the adapters are chosen and built, from the configuration."""

from __future__ import annotations

from typing import Any

from sql_analytics.adapters.http.app import build_app as build_http_app
from sql_analytics.adapters.http.auth import Authenticator, principal_of
from sql_analytics.adapters.mcp.server import build_server
from sql_analytics.application.catalog import Catalog
from sql_analytics.config import Config


def build_app(config: Config) -> Any:
    """The ASGI application the configuration describes."""
    catalog = Catalog(source.info() for source in config.sources)
    server = build_server(catalog, principal_of)
    authenticator = Authenticator(
        (principal.token, principal.principal()) for principal in config.principals
    )
    return build_http_app(server, authenticator, config.server.host, config.server.allowed_hosts)
