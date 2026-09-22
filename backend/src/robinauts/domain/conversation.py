# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The platform's own conversation format: the tree, and what is in a message.

Owned by the platform, not by an agent framework and not by a model vendor
(`ADR 0002 <../../../docs/adr/0002-conversation-persistence.md>`_). Four seams
meet on these records -- both agent engines, the datastore, the wire and
export -- so what is here is deliberately small and explicit: nothing in it
is shaped by LangChain, Pydantic AI, OpenAI or Anthropic, and every name is
one the specs use.

A conversation is a **tree**: every message has a parent, editing a question
or regenerating an answer adds a sibling, and nothing is overwritten
(``docs/specs/conversations.md``). The rules over a collection of messages --
which parents are legal, what a branch is, which leaf a conversation opens on
-- are pure functions in ``robinauts.core.conversation_tree``, and the one
encoding of all this is ``robinauts.core.conversation_format``. A record here
holds and checks; it does not decide and it does not serialise.

**Room without building it.** The format names every kind of content the
specs give a message -- text, image, file, reasoning, tool call, tool result
-- and this version carries two of them, text and reasoning. The other kinds
are refused, by name, as not supported yet. Naming them now is what lets them
arrive without a stored conversation having to be rewritten: the discriminator
they will be stored under is already reserved, and a build that meets one it
cannot carry says so instead of guessing. The ``tool`` role is reserved the
same way.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from robinauts.domain.agents import Engine, checked_config_id
from robinauts.domain.errors import InvalidValueError, UnsupportedContentError
from robinauts.domain.values import (
    MAX_PART_CHARS,
    checked_instant,
    checked_line,
    checked_text,
    checked_uuid,
    describe,
)

FORMAT_VERSION = 1
"""The version of this format, recorded on everything written in it.

One number for the format, and it moves rarely. There are three ways to add
without moving it: a new kind of content, a new role, and anything at all
under the reserved ``extras`` key, which a build that does not use it reads
past. **Any other new key moves it**, as does any change to the meaning or
the shape of what is already written. A build reads every version up to its
own and refuses one above it. The rules and the upgrade path are in
``robinauts.core.conversation_format``.
"""

MAX_PARTS = 64
"""How many parts one message may hold."""

MAX_MESSAGE_CHARS = MAX_PARTS * MAX_PART_CHARS
"""The longest one message's text may be: every part of it, full.

Derived rather than chosen, so that it cannot drift from the two bounds it is
made of. It is what ``text_parts`` refuses past, and it is the bound the wire
states for a message somebody writes (``robinauts.api.schemas``): a client
that knows it can say so in its own form instead of finding out by being
refused.
"""

MAX_TITLE_CHARS = 120
"""The longest a conversation's title may be; it is shown in a list."""


class Role(StrEnum):
    """Who a message is from.

    ``TOOL`` is reserved and not carried: tool usage is planned
    (``docs/specs/agents.md``), and a message of that role is refused until it
    is built. It is named so that the stored spelling is settled now, and so
    that the rule about what may follow what can be written for it already
    (``robinauts.core.conversation_tree.may_follow``).
    """

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


SUPPORTED_ROLES: frozenset[Role] = frozenset({Role.USER, Role.ASSISTANT})
"""The roles this version carries."""


class Channel(StrEnum):
    """Where a message came from (``docs/specs/channels.md``).

    A conversation is not tied to one: each message records its own, so a
    conversation begun in the web UI and continued from somewhere else says
    which was which. Other channels join this enum with the bridge that
    serves them; a stored ``web`` never changes meaning.
    """

    WEB = "web"


class PartKind(StrEnum):
    """Every kind of content a message may hold (``docs/specs/conversations.md``).

    The whole table is named here, including the kinds this version does not
    carry, because these values are the discriminator stored data is written
    under. ``SUPPORTED_PART_KINDS`` says which of them exist as records today.
    """

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


SUPPORTED_PART_KINDS: frozenset[PartKind] = frozenset({PartKind.TEXT, PartKind.REASONING})
"""The kinds this version has a record for. The others are refused by name."""


def check_supported(kind: PartKind) -> PartKind:
    """``kind`` if this build carries it; ``UnsupportedContentError`` if not."""
    if kind not in SUPPORTED_PART_KINDS:
        raise UnsupportedContentError(f"content of kind {kind.value!r} is not supported yet")
    return kind


def check_supported_role(role: Role) -> Role:
    """``role`` if this build carries it; ``UnsupportedContentError`` if not."""
    if role not in SUPPORTED_ROLES:
        raise UnsupportedContentError(f"a message of role {role.value!r} is not supported yet")
    return role


@dataclass(frozen=True, slots=True)
class TextPart:
    """Text: what a person wrote, or what a model answered."""

    text: str
    kind: ClassVar[PartKind] = PartKind.TEXT

    def __post_init__(self) -> None:
        checked_text(self.text, "the text of a part", MAX_PART_CHARS)


@dataclass(frozen=True, slots=True)
class ReasoningPart:
    """The thinking some models emit, kept apart from the answer.

    Its own kind of content, never the answer, and never sent to a vendor
    other than the one that produced it (``docs/specs/conversations.md``).
    **This version stores none of it**: an engine may stream reasoning and may
    complete an answer with a part of this kind, and the application shows the
    first and drops the second (``docs/specs/runs.md``). The record and its
    encoding are here so that the day it is kept, nothing about the format
    changes.
    """

    text: str
    kind: ClassVar[PartKind] = PartKind.REASONING

    def __post_init__(self) -> None:
        checked_text(self.text, "the text of a part", MAX_PART_CHARS)


MessagePart = TextPart | ReasoningPart
"""The closed set of content a message may hold in this version.

A union rather than a base class: adding a kind is adding a record and a name
here, and every place that takes a part apart is a match a type checker can
tell is no longer exhaustive.
"""


def text_parts(text: str) -> tuple[TextPart, ...]:
    """``text`` as content, split where it is longer than one part may be.

    The bound on a part is not a bound on an answer: a model asked for a very
    long one is paid for either way, so what will not fit in one part is
    carried in the next rather than cut. The split falls between code points
    -- Python counts a string in code points, so no character is ever halved
    -- and nowhere in particular otherwise: it is a bound of the store, not a
    piece of meaning.

    Here rather than in ``core`` for the same reason as ``clean_text``: what
    turns a model's answer into the platform's content is an agent adapter,
    and an adapter may import ``domain`` and must not import ``core``
    (``docs/layout.md``). The bound, the repair and the splitting are one
    subject and live together.

    Text that is not storable is refused rather than mangled; run it through
    ``clean_text`` first if it came from a provider.
    """
    if not isinstance(text, str):
        raise InvalidValueError(f"content is made of text, not {describe(text)}")
    if len(text) > MAX_MESSAGE_CHARS:
        raise InvalidValueError(
            f"one message holds at most {MAX_MESSAGE_CHARS} characters, not {len(text)}"
        )
    if not text:
        return (TextPart(""),)
    return tuple(
        TextPart(text[start : start + MAX_PART_CHARS])
        for start in range(0, len(text), MAX_PART_CHARS)
    )


def kept_parts(parts: Iterable[MessagePart]) -> tuple[MessagePart, ...]:
    """What this version stores of the content an engine produced.

    Reasoning is dropped rather than refused: an engine translates what the
    model said and is not asked to know what the platform keeps
    (``docs/specs/conversations.md``). If nothing is left -- a model that only
    thought, or that said nothing at all -- what is stored is one empty piece
    of text, because a message must have content and because a conversation
    where the agent answered with nothing should say so rather than skip a
    turn.

    The application calls this between the engine and the store. The day
    reasoning is kept, this is where that changes.
    """
    kept = tuple(part for part in checked_parts(parts) if not isinstance(part, ReasoningPart))
    return kept or (TextPart(""),)


def checked_parts(parts: object) -> tuple[MessagePart, ...]:
    """``parts`` as a bounded, non-empty tuple of the content kinds we carry.

    The one rule, used by ``Message`` and by whatever reads a message back out
    of a store, so that a row cannot hold an empty message or a thousand
    parts that nothing built in code could.
    """
    if isinstance(parts, str) or not isinstance(parts, tuple | list):
        raise InvalidValueError(f"a message's parts are a sequence, not {describe(parts)}")
    kept = tuple(parts)
    if not kept:
        raise InvalidValueError("a message has at least one part")
    if len(kept) > MAX_PARTS:
        raise InvalidValueError(f"a message has at most {MAX_PARTS} parts, not {len(kept)}")
    for part in kept:
        if not isinstance(part, MessagePart):
            raise InvalidValueError(
                f"a message holds the content kinds of this format, not {describe(part)}"
            )
    return kept


@dataclass(frozen=True, slots=True)
class Provenance:
    """What produced an answer: the agent, the engine, the model, the run.

    Every assistant message records it and the interface can show it
    (``docs/specs/conversations.md``). It is what makes an engine swap
    visible after the fact: the answers of a conversation say which engine and
    which model each of them came from.
    """

    agent: str
    """The agent's id in the configuration."""
    engine: Engine
    model: str
    """The platform's own id for the model, not the vendor's name for it."""
    run_id: uuid.UUID

    def __post_init__(self) -> None:
        checked_config_id(self.agent, "an agent's id")
        checked_config_id(self.model, "a model's id")
        if not isinstance(self.engine, Engine):
            raise InvalidValueError(f"an engine is an Engine, not {describe(self.engine)}")
        checked_uuid(self.run_id, "a run's id")


@dataclass(frozen=True, slots=True)
class Message:
    """One message of a conversation: a node of the tree.

    ``parent_id`` is ``None`` for a root. A conversation has one root
    ordinarily and gains another when its first question is edited, which is
    the same branching as anywhere else in the tree.

    Token counts are **not** recorded. Usage reporting is planned, and whether
    to keep the provider's raw counts before it exists is open
    (``docs/specs/conversations.md``, "Open"); a field nobody writes would
    decide it.

    ``created_at`` is not compared with anything. A wall clock steps backwards
    now and then -- an NTP correction is enough -- and a record that refused
    to exist because of it would lose an answer in the middle of a turn. What
    orders a conversation is the tree; time only breaks ties.
    """

    id: uuid.UUID
    conversation_id: uuid.UUID
    parent_id: uuid.UUID | None
    role: Role
    parts: tuple[MessagePart, ...]
    created_at: datetime
    channel: Channel = Channel.WEB
    provenance: Provenance | None = None
    """What produced it: on an assistant message, and on no other."""

    def __post_init__(self) -> None:
        checked_uuid(self.id, "a message's id")
        checked_uuid(self.conversation_id, "a message's conversation id")
        if self.parent_id is not None:
            checked_uuid(self.parent_id, "a message's parent id")
            if self.parent_id == self.id:
                raise InvalidValueError("a message cannot be its own parent")
        # ``is``-shaped checks, not ``==``: ``Role`` and ``Channel`` are
        # ``StrEnum``s, so a bare string reads as one and would then take
        # branches this record never checked it against.
        if not isinstance(self.role, Role):
            raise InvalidValueError(f"a message's role is a Role, not {describe(self.role)}")
        check_supported_role(self.role)
        if not isinstance(self.channel, Channel):
            raise InvalidValueError(
                f"a message's channel is a Channel, not {describe(self.channel)}"
            )
        object.__setattr__(self, "parts", checked_parts(self.parts))
        checked_instant(self.created_at, "created_at")
        if self.role is Role.ASSISTANT:
            if not isinstance(self.provenance, Provenance):
                raise InvalidValueError(
                    "an assistant message records the agent, engine, model and run"
                    f" that produced it, not {describe(self.provenance)}"
                )
        elif self.provenance is not None:
            raise InvalidValueError(
                f"only an assistant message has provenance, not one of role {self.role.value!r}"
            )

    @property
    def text(self) -> str:
        """The message's text parts, joined. Reasoning is not the answer."""
        return "".join(part.text for part in self.parts if isinstance(part, TextPart))


@dataclass(frozen=True, slots=True)
class Conversation:
    """A conversation: one owner, one agent, and the branch it opens on.

    Private to its owner in this version; sharing and projects are out
    (``docs/working-notes/poc-scope.md``), and so is the trash -- deleting is
    for good -- so there are no fields for them.

    ``created_at`` and ``updated_at`` are not compared with each other, for
    the reason given on ``Message``: a clock that stepped backwards must not
    make a conversation unrecordable.
    """

    id: uuid.UUID
    owner_id: uuid.UUID
    """The user whose conversation it is. Every route checks it."""
    agent: str
    """The agent's id in the configuration; a conversation is bound to one."""
    created_at: datetime
    updated_at: datetime
    title: str = ""
    """Empty until the first question gives it one (``core.derive_title``)."""
    active_leaf_id: uuid.UUID | None = None
    """The message its author was last on; the branch it opens on."""

    def __post_init__(self) -> None:
        checked_uuid(self.id, "a conversation's id")
        checked_uuid(self.owner_id, "a conversation's owner")
        checked_config_id(self.agent, "an agent's id")
        checked_line(self.title, "a conversation's title", MAX_TITLE_CHARS)
        checked_instant(self.created_at, "created_at")
        checked_instant(self.updated_at, "updated_at")
        if self.active_leaf_id is not None:
            checked_uuid(self.active_leaf_id, "a conversation's active leaf")
