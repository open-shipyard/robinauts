# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The LangChain engine: a LangGraph agent per turn over a saver whose thread is the session.

The engine is handed its memory; ``init_langchain`` picks it for the storage asked, and
nothing here knows which storage that was.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import AsyncGenerator, Iterator
from contextlib import aclosing
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallRequest, ToolErrorMiddleware
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from mcp.shared.exceptions import McpError

from robinauts.agent_engines.contract.domain import (
    AgentDefinition,
    CheckpointNotFoundError,
    Done,
    Event,
    ProviderKind,
    ReasoningDelta,
    SessionNotFoundError,
    TextDelta,
    ToolCall,
    ToolResult,
)
from robinauts.agent_engines.contract.ports import AgentEngine, EngineSettings
from robinauts.agent_engines.langchain_engine.clients import chat_model, force_tracing_off
from robinauts.agent_engines.langchain_engine.memory import Memory
from robinauts.agent_engines.langchain_engine.tools import tools_for

FASTEST_MODEL_CALL = 1.0
"""Seconds: a turn may make one model call per second of its timeout. Real rounds are slower;
a loop faster than that is runaway, and this bounds what it costs."""


class LangChainEngine(AgentEngine):
    def __init__(self, settings: EngineSettings, memory: Memory) -> None:
        self._settings = settings
        self._memory = memory
        force_tracing_off()

    def kinds(self) -> frozenset[ProviderKind]:
        return frozenset(ProviderKind)

    async def setup(self) -> None:
        await self._memory.setup()

    async def create(self, session_id: uuid.UUID) -> None:
        await self._memory.create(session_id)

    async def exists(self, session_id: uuid.UUID) -> bool:
        return await self._memory.exists(session_id)

    async def stream(
        self,
        session_id: uuid.UUID,
        agent: AgentDefinition,
        prompt: str,
        *,
        model: str,
        checkpoint_id: str | None,
        timeout_seconds: float,
        resume: bool = False,
    ) -> AsyncGenerator[Event, None]:
        if not await self._memory.exists(session_id):
            raise SessionNotFoundError(str(session_id))
        thread: RunnableConfig = {"configurable": {"thread_id": str(session_id)}}
        # Without a checkpoint the saver loads the thread's latest state: clear its messages.
        start: RunnableConfig = thread
        fresh: list[BaseMessage] = [RemoveMessage(id=REMOVE_ALL_MESSAGES)]
        if checkpoint_id is not None:
            fresh = []
            start = {"configurable": {"thread_id": str(session_id), "checkpoint_id": checkpoint_id}}
            if await self._memory.saver.aget_tuple(start) is None:
                raise CheckpointNotFoundError(checkpoint_id)

        graph = create_agent(
            chat_model(model, self._settings),
            await tools_for(agent, self._settings),
            system_prompt=agent.system_prompt,
            checkpointer=self._memory.saver,
            middleware=[ToolErrorMiddleware(tool_failed)],
        )
        # A model call and its tool round are two steps of the graph.
        calls = math.ceil(timeout_seconds / FASTEST_MODEL_CALL)
        limited: RunnableConfig = {**start, "recursion_limit": 2 * calls + 1}
        stream = graph.astream(
            {"messages": [*fresh, HumanMessage(prompt)]},
            limited,
            stream_mode=["messages", "updates"],
        )
        # The deadline bounds the run, not the caller's handling of what is yielded.
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        async with aclosing(stream):
            while True:
                async with asyncio.timeout_at(deadline):
                    item = await anext(stream, None)
                if item is None:
                    break
                for event in events_of(*item):
                    yield event
        state = await graph.aget_state(thread)
        yield Done(
            text=str(state.values["messages"][-1].text),
            checkpoint_id=state.config["configurable"]["checkpoint_id"],
        )

    async def fork(self, source_id: uuid.UUID, target_id: uuid.UUID, *, checkpoint_id: str) -> None:
        raise NotImplementedError("fork")

    async def forget(self, session_id: uuid.UUID) -> None:
        await self._memory.forget(session_id)


def tool_failed(error: Exception, _request: ToolCallRequest) -> str:
    """What the model is told of a tool call that raised, so that the turn goes on: the MCP
    session's own words, such as a timeout's, or else the kind of error alone. An ``isError``
    result of the server's is already its own answer."""
    if isinstance(error, McpError):
        return str(error)
    return f"The tool call failed: {type(error).__name__}."


def events_of(mode: str, payload: Any) -> Iterator[Event]:
    if mode == "messages":
        chunk, _ = payload
        if isinstance(chunk, AIMessageChunk):
            for block in chunk.content_blocks:
                if block["type"] == "text" and block["text"]:
                    yield TextDelta(block["text"])
                elif block["type"] == "reasoning" and block.get("reasoning"):
                    yield ReasoningDelta(block["reasoning"])
        return
    for update in payload.values():
        for message in update["messages"]:
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    yield ToolCall(str(call["id"]), call["name"], call["args"])
            elif isinstance(message, ToolMessage):
                yield ToolResult(
                    message.tool_call_id, str(message.name), message.text, message.status == "error"
                )
