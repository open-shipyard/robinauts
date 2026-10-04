# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What the prompt tells the model about answers that failed."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from robinauts.controller.contract.domain import (
    Message,
    MessagePart,
    Role,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from robinauts.controller.core.failures import LONGEST, prompt_after_failures

CALL = ToolCallPart("c1", "search", {"q": "capital"})
CLOSING = "The user was told it failed, and pressed the retry button."


def failed(*parts: MessagePart) -> Message:
    return Message(
        uuid.uuid4(),
        uuid.uuid4(),
        parent_id=uuid.uuid4(),
        role=Role.ASSISTANT,
        parts=parts,
        created_at=datetime.now(UTC),
        failed=True,
    )


@pytest.mark.parametrize(
    ("parts", "note"),
    [
        ((), [CLOSING]),
        (
            (CALL, ToolResultPart("c1", "No web results found", is_error=True)),
            [
                "Before it failed, it made these tool calls:",
                '- search({"q": "capital"}) -> error: No web results found',
                CLOSING,
            ],
        ),
        (
            (CALL, ToolResultPart("c1", "Paris", is_error=False)),
            [
                "Before it failed, it made these tool calls:",
                '- search({"q": "capital"}) -> result: Paris',
                CLOSING,
            ],
        ),
        (
            (CALL,),
            [
                "Before it failed, it made these tool calls:",
                '- search({"q": "capital"}) -> no result',
                CLOSING,
            ],
        ),
        ((TextPart("The capital is"),), ["It had written: The capital is", CLOSING]),
        (
            (CALL, ToolResultPart("c1", "x" * (LONGEST + 1), is_error=False)),
            [
                "Before it failed, it made these tool calls:",
                '- search({"q": "capital"}) -> result: ' + "x" * LONGEST,
                CLOSING,
            ],
        ),
    ],
)
def test_a_retry_is_the_question_then_what_the_failed_answer_did(
    parts: tuple[MessagePart, ...], note: list[str]
) -> None:
    head = ["What is the capital of France?", "", "---"]
    opening = "Your previous answer to this message failed before it finished."
    prompt = prompt_after_failures("What is the capital of France?", retried=failed(*parts))
    assert prompt.split("\n") == [*head, opening, *note]


ERROR = ToolResultPart("c1", "No web results found", is_error=True)
EXCHANGE = [
    "Your answer to it failed before it finished.",
    "Before it failed, it made these tool calls:",
    '- search({"q": "capital"}) -> error: No web results found',
    "The user was told it failed.",
]
NEW = ["", "---", "The user's new message:", "", "Was it my fault?"]


@pytest.mark.parametrize(
    ("earlier", "retried", "expected"),
    [
        ([], None, ["Was it my fault?"]),
        (
            [("Capital of France?", failed(CALL, ERROR))],
            None,
            [
                "Earlier messages in this conversation got no answer, because answering failed:",
                "",
                "Message: Capital of France?",
                *EXCHANGE,
                *NEW,
            ],
        ),
        (
            [("Capital of France?", failed()), ("And of Spain?", failed(CALL, ERROR))],
            None,
            [
                "Earlier messages in this conversation got no answer, because answering failed:",
                "",
                "Message: Capital of France?",
                "Your answer to it failed before it finished.",
                "The user was told it failed.",
                "",
                "Message: And of Spain?",
                *EXCHANGE,
                *NEW,
            ],
        ),
        (
            [("Capital of France?", failed())],
            failed(),
            [
                "Earlier messages in this conversation got no answer, because answering failed:",
                "",
                "Message: Capital of France?",
                "Your answer to it failed before it finished.",
                "The user was told it failed.",
                *NEW,
                "",
                "---",
                "Your previous answer to this message failed before it finished.",
                CLOSING,
            ],
        ),
    ],
)
def test_earlier_failed_exchanges_come_before_the_question(
    earlier: list[tuple[str, Message]], retried: Message | None, expected: list[str]
) -> None:
    assert prompt_after_failures("Was it my fault?", earlier, retried).split("\n") == expected
