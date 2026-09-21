# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Agents are configuration: the engine that runs one, and how ids are spelt.

An agent is a name, a system prompt, a model and an engine
(``docs/specs/agents.md``); the operator writes them in the configuration and
users do not create them. Reading that configuration belongs to a later step.
What the conversation format needs of it is here: the engine a message was
produced by, and the shape of the ids an agent and a model are referred to by.
So is ``AgentDefinition``, the record an operator's configuration is read into
-- the record alone, with no reading of any file: that belongs to the step
that has a configuration to read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from robinauts.domain.errors import InvalidValueError
from robinauts.domain.values import checked_line, checked_text, describe

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


MAX_AGENT_TITLE_CHARS = 120
"""The longest an agent's title may be.

A conversation's title's bound (``robinauts.domain.conversation``), because
both are shown in the same kind of place -- a list, a picker, a heading -- and
one bound is one thing for an operator to learn. It is not imported from
there: that module is built on this one.
"""

MAX_SYSTEM_PROMPT_CHARS = 100_000
"""The longest a system prompt may be.

Generous, since a long prompt is a real way of writing an agent, and bounded
all the same: it is read from a file the operator wrote, sent to a provider on
every turn, and a configuration that holds a megabyte of it is a mistake
somebody should be told about at start-up rather than at the first turn.
"""


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """An agent as the operator defined it: a name, a prompt, a model, an engine.

    The record alone (``docs/specs/agents.md``). **Reading the configuration
    is not here**: an adapter reads the raw tables and ``core`` turns them into
    these, as it does for sign-in, and that is a step of its own. What is here
    is what every layer above needs -- the application to run a turn with it,
    an agent adapter to be handed it -- and the rules it keeps to.

    The system prompt is **not a message** and is never stored in a
    conversation: it is taken from the agent's configuration at every turn, so
    editing an agent takes effect at the next turn of its existing
    conversations (``docs/specs/conversations.md``).
    """

    id: str
    """How the configuration and every message produced by it name this agent."""
    title: str
    """What a person picks it by."""
    system_prompt: str
    """What the agent is told before the conversation. May be empty."""
    model: str
    """The platform's own id for the model, not the vendor's name for it."""
    engine: Engine

    def __post_init__(self) -> None:
        checked_config_id(self.id, "an agent's id")
        checked_config_id(self.model, "a model's id")
        checked_line(self.title, "an agent's title", MAX_AGENT_TITLE_CHARS)
        if not self.title.strip():
            raise InvalidValueError("an agent has a title: it is what a person picks it by")
        checked_text(self.system_prompt, "an agent's system prompt", MAX_SYSTEM_PROMPT_CHARS)
        if not isinstance(self.engine, Engine):
            raise InvalidValueError(f"an engine is an Engine, not {describe(self.engine)}")
