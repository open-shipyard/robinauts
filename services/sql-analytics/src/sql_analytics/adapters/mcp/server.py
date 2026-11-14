# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The MCP server: the tools an agent finds its databases through, over the application.

Streamable HTTP at `/mcp`, stateless, with plain JSON answers, like the servers in `mcp/`.
Every tool answers twice: text the model reads, and structured content. Which principal is
asking is read from the request through `principal_of`, which the HTTP adapter provides and
`sql_analytics.composition` hands in; a tool never sees the token.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from sql_analytics.application.catalog import Catalog
from sql_analytics.contract import Principal

NAME = "sql-analytics"
INSTRUCTIONS = (
    "SQL Analytics answers questions about the company's SQL databases. "
    "Call list_sources first to learn which databases you may use."
)


class Source(BaseModel):
    id: str
    kind: str
    description: str
    default_schema: str | None


class Sources(BaseModel):
    sources: list[Source]


def _ui(*visibility: str) -> dict[str, object]:
    return {"ui": {"visibility": list(visibility)}}


def build_server(catalog: Catalog, principal_of: Callable[[object], Principal | None]) -> FastMCP:
    server = FastMCP(
        NAME,
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        log_level="WARNING",
    )

    def principal(context: Context) -> Principal:
        request = context.request_context.request
        found = principal_of(getattr(request, "state", None))
        if found is None:
            # Not reachable through the HTTP adapter, which refuses a request without a token.
            raise ToolError("this request carries no principal")
        return found

    @server.tool(
        title="Databases",
        description=(
            "List the databases you may query: each one's id, its kind, what it holds and its "
            "default schema."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
        meta=_ui("model"),
    )
    def list_sources(context: Context) -> Annotated[CallToolResult, Sources]:
        sources = catalog.list_sources(principal(context))
        if sources:
            lines = [f"{len(sources)} source(s):"]
            for source in sources:
                schema = (
                    f", default schema {source.default_schema}" if source.default_schema else ""
                )
                lines.append(f"- {source.id} ({source.kind}{schema}): {source.description}")
            text = "\n".join(lines)
        else:
            text = "No source is available to you."
        structured = Sources(
            sources=[
                Source(
                    id=source.id,
                    kind=source.kind,
                    description=source.description,
                    default_schema=source.default_schema,
                )
                for source in sources
            ]
        )
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent=structured.model_dump(mode="json"),
        )

    return server
