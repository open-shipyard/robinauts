# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Agents are configuration: the engine that runs one, and how ids are spelt.

An agent is a name, a system prompt, a model and an engine
(``docs/specs/agents.md``); the operator writes them in the configuration and
users do not create them. Reading that configuration belongs to a later step.
What the conversation format needs of it is here: the engine a message was
produced by, and the shape of the ids an agent and a model are referred to by.
"""

from __future__ import annotations

import re
from enum import StrEnum

from robinauts.domain.errors import InvalidValueError
from robinauts.domain.values import describe

MAX_CONFIG_ID_CHARS = 40

_CONFIG_ID = re.compile(rf"[a-z0-9][a-z0-9_-]{{0,{MAX_CONFIG_ID_CHARS - 1}}}")
"""What an id the operator writes in the configuration may be spelt with.

Deliberately the same rule as a provider's id
(``robinauts.domain.sign_in.is_provider_id``), and for the same reason: these
ids are keys of a configuration table, they travel in URLs, and they are
recorded on every message an agent produced. One spelling rule means an
operator learns it once, and nothing downstream has to wonder how long an id
can be or what may be in it.
"""


def is_config_id(value: object) -> bool:
    """Whether ``value`` is spelt the way an agent's or a model's id is spelt."""
    return isinstance(value, str) and _CONFIG_ID.fullmatch(value) is not None


def checked_config_id(value: object, what: str) -> str:
    """``value`` if it is an id of that shape; ``InvalidValueError`` if not."""
    if not isinstance(value, str) or _CONFIG_ID.fullmatch(value) is None:
        raise InvalidValueError(
            f"{what} is a name: lower-case letters, digits, '-' and '_', at most "
            f"{MAX_CONFIG_ID_CHARS} of them, not {describe(value)}"
        )
    return value


class Engine(StrEnum):
    """The agent frameworks a turn can be run by (``docs/specs/agents.md``).

    A property of the agent, recorded on every message, so that a conversation
    says which engine produced which answer after the agent has been changed.
    The values are the ones the configuration is written with.
    """

    LANGGRAPH = "langgraph"
    PYDANTIC_AI = "pydantic-ai"
