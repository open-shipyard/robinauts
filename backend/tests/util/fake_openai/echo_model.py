# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A model that answers with the last thing the user said."""

from __future__ import annotations

from typing import Any


class EchoModel:
    def reply(self, messages: list[dict[str, Any]]) -> str:
        last = next(m for m in reversed(messages) if m["role"] == "user")
        content = last["content"]
        if isinstance(content, str):
            return content
        return "".join(part.get("text", "") for part in content)
