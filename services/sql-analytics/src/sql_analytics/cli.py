# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The `robinauts-sql-analytics` command: `serve` and `check`.

Both read the configuration whole first and stop, with every reason, when it cannot be used.
`check` stops there; once the connectors exist it will also connect to each source once.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from sql_analytics.composition import build_app
from sql_analytics.config import Config, ConfigError, load

PROG = "robinauts-sql-analytics"


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="SQL Analytics: an MCP server over streamable HTTP at /mcp.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help in (
        ("serve", "serve /mcp and /healthz"),
        ("check", "read and check the configuration, and stop"),
    ):
        command = commands.add_parser(name, help=help)
        command.add_argument(
            "--config",
            type=Path,
            default=os.environ.get("SQL_ANALYTICS_CONFIG") or None,
            required=not os.environ.get("SQL_ANALYTICS_CONFIG"),
            help="the TOML configuration file (SQL_ANALYTICS_CONFIG)",
        )
    return parser.parse_args(argv)


def _config(path: Path) -> Config | None:
    try:
        return load(path, os.environ)
    except ConfigError as error:
        print(f"{PROG}: {path} cannot be used:", file=sys.stderr)
        for problem in error.problems:
            print(f"  - {problem}", file=sys.stderr)
        return None


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _arguments(argv)
    config = _config(arguments.config)
    if config is None:
        return 2
    if arguments.command == "check":
        print(
            f"{arguments.config}: {len(config.principals)} principal(s), "
            f"{len(config.sources)} source(s); the configuration can be used",
        )
        return 0
    app = build_app(config)
    host, port = config.server.host, config.server.port
    print(f"sql-analytics at http://{host}:{port}/mcp", file=sys.stderr, flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
    return 0
