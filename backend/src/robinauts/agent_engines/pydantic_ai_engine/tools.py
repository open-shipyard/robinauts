# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The agent's tools, as toolsets of its MCP servers with the server's credential."""

from __future__ import annotations

import base64
from typing import Any

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from robinauts.agent_engines.contract.domain import (
    AgentDefinition,
    ToolServerAuth,
    ToolServerConfig,
)
from robinauts.agent_engines.contract.ports import EngineSettings


def toolset_for(server: ToolServerConfig, settings: EngineSettings) -> AbstractToolset[Any]:
    headers = {}
    if server.auth is ToolServerAuth.BEARER:
        headers["Authorization"] = f"Bearer {settings.tool_secrets.secret_for(server.id)}"
    elif server.auth is ToolServerAuth.BASIC:
        pair = f"{server.user}:{settings.tool_secrets.secret_for(server.id)}"
        headers["Authorization"] = f"Basic {base64.b64encode(pair.encode()).decode('ascii')}"
    elif server.auth is ToolServerAuth.HEADER:
        headers[server.header] = settings.tool_secrets.secret_for(server.id)
    # Nothing connects here: the agent's run opens the session and closes it when the run ends.
    toolset = MCPToolset(
        server.url,
        headers=headers,
        init_timeout=server.timeout_seconds,
        read_timeout=server.timeout_seconds,
    )
    if not server.exclude:
        return toolset
    excluded = set(server.exclude)
    return toolset.filtered(lambda _context, tool: tool.name not in excluded)


def toolsets_for(agent: AgentDefinition, settings: EngineSettings) -> list[AbstractToolset[Any]]:
    servers = settings.models.tool_servers
    return [toolset_for(servers[server_id], settings) for server_id in agent.tools]
