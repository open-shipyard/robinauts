# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The agent's tools, listed from its MCP servers with the server's credential."""

from __future__ import annotations

import asyncio
import base64
from datetime import timedelta

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

from robinauts.agent_engines.contract.domain import (
    AgentDefinition,
    ToolServerAuth,
    ToolServerConfig,
)
from robinauts.agent_engines.contract.ports import EngineSettings


def connection_for(server: ToolServerConfig, settings: EngineSettings) -> StreamableHttpConnection:
    headers = {}
    if server.auth is ToolServerAuth.BEARER:
        headers["Authorization"] = f"Bearer {settings.tool_secrets.secret_for(server.id)}"
    elif server.auth is ToolServerAuth.BASIC:
        pair = f"{server.user}:{settings.tool_secrets.secret_for(server.id)}"
        headers["Authorization"] = f"Basic {base64.b64encode(pair.encode()).decode('ascii')}"
    elif server.auth is ToolServerAuth.HEADER:
        headers[server.header] = settings.tool_secrets.secret_for(server.id)
    timeout = timedelta(seconds=server.timeout_seconds)
    return {
        "transport": "streamable_http",
        "url": server.url,
        "headers": headers,
        "timeout": timeout,
        "sse_read_timeout": timeout,
    }


async def tools_for(agent: AgentDefinition, settings: EngineSettings) -> list[BaseTool]:
    if not agent.tools:
        return []
    servers = settings.models.tool_servers
    # One connection per server, however often the agent names it.
    connections = {s: connection_for(servers[s], settings) for s in agent.tools}
    client = MultiServerMCPClient(connections)
    # Listing opens a session per server and each tool opens its own per call: nothing to close.
    # Per server, so that each one's `exclude` applies to its own tools' names.
    listed = await asyncio.gather(*(client.get_tools(server_name=s) for s in connections))
    return [
        tool
        for server_id, tools in zip(connections, listed, strict=True)
        for tool in tools
        if tool.name not in servers[server_id].exclude
    ]
