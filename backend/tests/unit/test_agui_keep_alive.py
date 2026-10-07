# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A quiet stream sends ``: keep-alive`` while it waits, and loses no event to it."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from robinauts.controller.contract.domain import NumberedEvent, TextPiece, TurnEnded, TurnState
from robinauts.web.agui import KEEP_ALIVE, stream
from util.aio import asyncio_test

ANSWER = uuid.uuid4()


async def quiet_then(seconds: float, closed: list[bool]) -> AsyncIterator[NumberedEvent]:
    """Silence for ``seconds``, then a piece of text and the end."""
    try:
        await asyncio.sleep(seconds)
        yield NumberedEvent(1, TextPiece(ANSWER, "hello"))
        yield NumberedEvent(2, TurnEnded(TurnState.FINISHED))
    finally:
        closed.append(True)


@asyncio_test
async def test_a_quiet_stream_keeps_alive_and_then_says_what_came() -> None:
    sent = [chunk async for chunk in stream("t", "r", quiet_then(0.35, []), 0.1)]

    assert sent[0].startswith("event: RUN_STARTED")
    assert sent[1:4] == [KEEP_ALIVE] * 3
    pieces = [chunk for chunk in sent[4:] if chunk != KEEP_ALIVE]
    assert [chunk.split("\n")[0] for chunk in pieces] == ["id: 1", "id: 2"]
    assert '"delta":"hello"' in pieces[0]


@asyncio_test
async def test_a_stream_left_while_quiet_stops_waiting() -> None:
    closed: list[bool] = []
    sent = stream("t", "r", quiet_then(60, closed), 0.05)
    await anext(sent)
    assert await anext(sent) == KEEP_ALIVE

    await sent.aclose()

    assert closed == [True]
