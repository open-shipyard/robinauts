# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What the model is told about answers that failed, when the conversation goes on.

The engine remembers nothing of a turn that failed: the next turn continues from the last
answer that finished. So the prompt carries what it missed (docs/specs/ui.md): every
question since then whose answer failed, with what that answer did, best-effort; then the
new question; and, on a retry, that the person pressed retry.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from robinauts.controller.contract.domain import Message, TextPart, ToolCallPart, ToolResultPart

LONGEST = 500
"""How much of a tool result, or of the text written, the note quotes."""


def prompt_after_failures(
    question: str,
    earlier: Sequence[tuple[str, Message]] = (),
    retried: Message | None = None,
) -> str:
    """The prompt for ``question``: after the failed exchanges ``earlier`` (each a question
    and its failed answer, oldest first), and with a note on ``retried`` if it is a retry."""
    lines = []
    if earlier:
        lines += ["Earlier messages in this conversation got no answer, because answering failed:"]
        for asked, failed in earlier:
            lines += ["", f"Message: {asked}", "Your answer to it failed before it finished."]
            lines += [*_what_it_did(failed), "The user was told it failed."]
        lines += ["", "---", "The user's new message:", ""]
    lines.append(question)
    if retried is not None:
        lines += ["", "---", "Your previous answer to this message failed before it finished."]
        lines += [*_what_it_did(retried)]
        lines.append("The user was told it failed, and pressed the retry button.")
    return "\n".join(lines)


def _what_it_did(failed: Message) -> list[str]:
    results = {p.call_id: p for p in failed.parts if isinstance(p, ToolResultPart)}
    calls = [p for p in failed.parts if isinstance(p, ToolCallPart)]
    lines = ["Before it failed, it made these tool calls:"] if calls else []
    for call in calls:
        result = results.get(call.call_id)
        if result is None:
            outcome = "no result"
        else:
            outcome = ("error: " if result.is_error else "result: ") + result.text[:LONGEST]
        lines.append(f"- {call.name}({json.dumps(dict(call.arguments))}) -> {outcome}")
    written = "".join(p.text for p in failed.parts if isinstance(p, TextPart))
    if written:
        lines.append(f"It had written: {written[:LONGEST]}")
    return lines
