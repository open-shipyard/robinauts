# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The controller's turn events as AG-UI events over server-sent events (``docs/specs/wire.md``).

The run id is the turn's id, and the thread id the session's: each turn is a run of its own.
A comment goes out whenever nothing has for ``KEEP_ALIVE_SECONDS``, so that nothing in front of
the deployment closes a stream that is only quiet: a long tool call or model call is silence.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from ag_ui.core import (
    BaseEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedCancelledOutcome,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui.encoder import EventEncoder

from robinauts.controller.contract.domain import (
    ArgumentsPiece,
    CallCompleted,
    CallStarted,
    MessageCompleted,
    MessageStarted,
    NumberedEvent,
    ReasoningPiece,
    ResultLanded,
    Role,
    TextPiece,
    TurnEnded,
    TurnEvent,
    TurnState,
)

ENCODER = EventEncoder()

KEEP_ALIVE = ": keep-alive\n\n"
"""An SSE comment: the client reads past it, and the connection carries a byte."""

KEEP_ALIVE_SECONDS = 15.0
"""How long a stream may go without sending anything; proxies cut idle ones from 60 s."""

ENDED_BADLY = {
    TurnState.FAILED: "the agent could not finish this answer",
    TurnState.INTERRUPTED: "the deployment stopped while this answer was being produced",
}


def sse(event: BaseEvent, position: int | None = None) -> str:
    numbered = "" if position is None else f"id: {position}\n"
    return f"{numbered}event: {event.type.value}\n{ENCODER.encode(event)}"


def mapped(thread_id: str, run_id: str, event: TurnEvent) -> list[BaseEvent]:
    match event:
        case MessageStarted(role=Role.ASSISTANT):
            return [TextMessageStartEvent(message_id=str(event.message_id), role="assistant")]
        case TextPiece():
            return [TextMessageContentEvent(message_id=str(event.message_id), delta=event.text)]
        case CallStarted():
            return [
                ToolCallStartEvent(
                    tool_call_id=event.call_id,
                    tool_call_name=event.name,
                    parent_message_id=str(event.message_id),
                )
            ]
        case ArgumentsPiece():
            return [ToolCallArgsEvent(tool_call_id=event.call_id, delta=event.text)]
        case CallCompleted():
            return [ToolCallEndEvent(tool_call_id=event.call_id)]
        case ResultLanded():
            return [
                ToolCallResultEvent(
                    message_id=str(event.message_id),
                    tool_call_id=event.call_id,
                    content=event.text,
                    role="tool",
                    metadata={"isError": True} if event.is_error else None,
                )
            ]
        case MessageCompleted():
            return [TextMessageEndEvent(message_id=str(event.message_id))]
        case TurnEnded(state=TurnState.FINISHED):
            return [RunFinishedEvent(thread_id=thread_id, run_id=run_id)]
        case TurnEnded(state=TurnState.CANCELLED):
            return [
                RunFinishedEvent(
                    thread_id=thread_id, run_id=run_id, outcome=RunFinishedCancelledOutcome()
                )
            ]
        case TurnEnded():
            return [RunErrorEvent(message=ENDED_BADLY[event.state], code=event.state.value)]
    return []


async def stream(
    thread_id: str,
    run_id: str,
    events: AsyncIterator[NumberedEvent],
    keep_alive_seconds: float = KEEP_ALIVE_SECONDS,
) -> AsyncIterator[str]:
    """``RUN_STARTED``, then each event; the position goes on the last wire event of each.
    ``KEEP_ALIVE`` whenever ``keep_alive_seconds`` pass without one."""
    yield sse(RunStartedEvent(thread_id=thread_id, run_id=run_id))
    thinking: str | None = None
    # Closed when this is: an `async for` left early does not close what it iterates.
    async with contextlib.aclosing(_with_quiet(events, keep_alive_seconds)) as quiet:
        async for numbered in quiet:
            if numbered is None:
                yield KEEP_ALIVE
                continue
            event, position = numbered.event, numbered.position
            if isinstance(event, ReasoningPiece):
                if thinking is None:
                    thinking = f"{event.message_id}:reasoning:{position}"
                    yield sse(ReasoningMessageStartEvent(message_id=thinking))
                content = ReasoningMessageContentEvent(message_id=thinking, delta=event.text)
                yield sse(content, position)
                continue
            if thinking is not None:
                yield sse(ReasoningMessageEndEvent(message_id=thinking))
                thinking = None
            wire = mapped(thread_id, run_id, event)
            for index, sent in enumerate(wire):
                yield sse(sent, position if index == len(wire) - 1 else None)


async def _with_quiet(
    events: AsyncIterator[NumberedEvent], seconds: float
) -> AsyncIterator[NumberedEvent | None]:
    """Each event, and ``None`` whenever ``seconds`` pass without one. The wait for the next
    event goes on across a ``None``; it is cancelled only when this stops early."""
    waiting: asyncio.Future[NumberedEvent | None] | None = None
    try:
        while True:
            if waiting is None:
                waiting = asyncio.ensure_future(anext(events, None))
            done, _ = await asyncio.wait({waiting}, timeout=seconds)
            if not done:
                yield None
                continue
            numbered = waiting.result()
            waiting = None
            if numbered is None:
                return
            yield numbered
    finally:
        if waiting is not None:
            waiting.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiting
