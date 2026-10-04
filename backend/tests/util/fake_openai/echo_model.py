# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Models that answer with the last thing the user said."""

from __future__ import annotations

from typing import Any


class EchoModel:
    def reply(self, messages: list[dict[str, Any]]) -> str:
        last = next(m for m in reversed(messages) if m["role"] == "user")
        content = last["content"]
        if isinstance(content, str):
            return content
        return "".join(part.get("text", "") for part in content)


class PoisonEchoModel(EchoModel):
    """An echo that fails a message starting with ``poison``, as the echo engine does.

    A retry is sent with the question first, so it fails again; a later message is sent after a
    note on the failed one, so it does not.
    """

    def reply(self, messages: list[dict[str, Any]]) -> str:
        text = super().reply(messages)
        if text.startswith("poison"):
            raise RuntimeError("the message is poisoned")
        return text
