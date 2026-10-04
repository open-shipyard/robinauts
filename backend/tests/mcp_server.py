# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A real MCP server for the tests: FastMCP over streamable HTTP, on this machine's loopback."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP


@contextmanager
def mcp_server(*tools: Callable[..., Any]) -> Iterator[str]:
    """The server's URL while it offers ``tools``, stopped when the block ends."""
    server = FastMCP("tests", stateless_http=True)
    for tool in tools:
        server.add_tool(tool)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(
        server.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning"
    )
    running = uvicorn.Server(config)
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    for _ in range(500):
        if running.started:
            break
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        running.should_exit = True
        thread.join(10)
