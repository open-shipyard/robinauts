# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The shapes the JSON API sends, and therefore what OpenAPI describes.

They are the api's own, not the domain's: a ``User`` carries rows a browser
has no business with, and a response that was a domain object would make every
column added later a change to the wire. These say exactly what goes out, and
``backend/openapi.json`` is the committed snapshot of what they add up to
(``docs/specs/backend.md``).

**Every id crosses as text and every time as ISO-8601 in UTC.** A uuid is a
string in JSON, and ``utc`` is what makes one instant have one spelling
whatever time zone a store's session was in.

**A field that is always sent is required, and nullable where it can be
empty**: ``leaf_id``, ``next_cursor``, ``resume`` and the rest are declared
``X | None`` with **no default**, so a generated client types them ``T | null``
and not "may be absent". There is one shape for every answer, and a client
that has read one field has read them all. (``SessionResponse`` and
``UserSummary`` predate this and are left as they are.)

**A request body forbids what it does not know** (``extra="forbid"``): a field
spelt wrong, or one from a newer client, is a refusal naming it rather than a
write that quietly did something else. What goes out is not held to that -- a
client reads the fields it knows and reads past the rest, which is how a field
is added without a new version of the wire.

**Two of these are not in the document**: the bodies of the streaming
endpoints (``NewChatRequest``, ``TurnRequest``), whose routes are outside
OpenAPI and are described in ``docs/specs/wire.md`` instead
(``docs/specs/backend.md``). They are written here with the others all the
same, because what a request body may be is one subject and because the rules
this module states -- the bounds that are the record's own, and a field nobody
knows being a refusal -- are exactly as true of them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from robinauts.application import OpenedConversation
from robinauts.domain import (
    MAX_CONFIG_ID_CHARS,
    MAX_MESSAGE_CHARS,
    MAX_TITLE_CHARS,
    AgentDefinition,
    Channel,
    Conversation,
    Engine,
    Message,
    MessagePart,
    Provenance,
    ReasoningPart,
    Run,
    RunState,
    User,
)

SentKind = Literal["text"]
"""The kinds of content this build **sends**, which is one.

Not ``PartKind``, which names every kind the stored format has a
discriminator for: a document that offered ``reasoning`` here would describe
the one value ``MessageView.of`` guarantees is absent, and every client
generated from it would have a branch for content it can never be sent. The
day a kind is sent, this grows a value and the committed snapshot shows it --
which is what the snapshot is for.

``test_the_wire_sends_only_the_values_it_declares`` holds it to
``domain.SUPPORTED_PART_KINDS``.
"""

SentRole = Literal["assistant", "user"]
"""The roles a message can be sent with: ``domain.SUPPORTED_ROLES``.

``tool`` is in ``domain.Role`` and is refused by every message this build
reads or writes, so it is not on the wire either.
"""

SentBadEnd = Literal["cancelled", "failed", "interrupted"]
"""How a run can have ended badly: ``domain.FAULTED_RUN_STATES``.

A run that finished is not an ``ended_badly`` and neither is one still going,
so the three are the whole of what that field can say.
"""


class ProviderSummary(BaseModel):
    """One provider to offer a sign-in button for. No secret, no endpoint."""

    id: str
    title: str


class UserSummary(BaseModel):
    """Who is signed in, as the interface shows them in the profile block."""

    id: uuid.UUID
    name: str | None = None
    email: str | None = None
    """Their address, only where the provider verified it."""
    provider: str

    @classmethod
    def of(cls, user: User) -> UserSummary:
        """The summary of a user; the fields the browser is told about."""
        return cls(id=user.id, name=user.name, email=user.email, provider=user.provider)


class SessionResponse(BaseModel):
    """What ``GET /auth/session`` answers, signed in or not.

    ``sign_in`` is whether this deployment has a sign-in configuration at all;
    without one there are no providers and nobody to be.

    ``local_development`` is the exception to that last part: the local
    development mode has no sign-in and no providers, and yet somebody *is*
    signed in -- the one local user everything runs as. It is what the
    interface shows its permanent banner for (``docs/specs/frontend.md``), and
    it is why the two are separate fields rather than one: "nothing is
    configured" and "sign-in is deliberately off" are different things to say
    to a person, and only the second one has a user with it.
    """

    sign_in: bool
    local_development: bool = False
    public_url: str | None = None
    providers: list[ProviderSummary] = []
    user: UserSummary | None = None


class HealthResponse(BaseModel):
    """What ``GET /health`` answers. It holds no data and says nothing else."""

    status: str


class ErrorResponse(BaseModel):
    """Every refusal, in one shape (``robinauts.api.errors``)."""

    error: str
    """The name of the error class, which is what a client branches on."""
    detail: str


def utc(when: datetime) -> datetime:
    """``when`` in UTC, which is the one spelling a time crosses the wire in.

    Every time the platform writes is UTC (``docs/specs/conversations.md``),
    but a record read back from a store can carry the offset of that session's
    time zone, and two spellings of one instant is one too many for a client
    that compares strings. So the shift happens here, where everything that
    goes out passes.
    """
    return when.astimezone(UTC)


class ContentPart(BaseModel):
    """One piece of a message's content, named by its kind.

    ``kind`` is the discriminator the stored format uses
    (``docs/specs/conversations.md``), so a client reads the kinds it knows and
    can be given another without the shape moving. Text is the only kind this
    build sends (``SentKind``); ``text`` is the whole of it.
    """

    kind: SentKind
    text: str

    @classmethod
    def of(cls, part: MessagePart) -> ContentPart:
        # ``.value``: what goes out is the plain string the format is written
        # in, not an enum member that happens to compare equal to one.
        return cls(kind=part.kind.value, text=part.text)


class ProvenanceView(BaseModel):
    """What an answer records: the agent, the engine, the model and the run.

    On an assistant message and on no other (``domain.Message``). The model is
    the platform's own id for it -- what the configuration calls it -- and no
    vendor, endpoint or key is anywhere near the wire.
    """

    agent: str
    engine: Engine
    model: str
    run_id: uuid.UUID

    @classmethod
    def of(cls, provenance: Provenance) -> ProvenanceView:
        return cls(
            agent=provenance.agent,
            engine=provenance.engine,
            model=provenance.model,
            run_id=provenance.run_id,
        )


class MessageView(BaseModel):
    """One message of a conversation, with what places it in the tree.

    ``parent_id`` is what makes this a tree and not a list: it is ``None`` for
    a root, and a client walks it upwards to have a branch. **Reasoning is not
    here**: see ``of``.
    """

    id: uuid.UUID
    parent_id: uuid.UUID | None
    role: SentRole
    channel: Channel
    created_at: datetime
    parts: list[ContentPart]
    provenance: ProvenanceView | None

    @classmethod
    def of(cls, message: Message) -> MessageView:
        """The message as it is sent. **Reasoning is left out.**

        This build keeps no reasoning in a message at all: an engine may
        stream it and a watcher sees it arrive, and ``domain.kept_parts``
        drops it between the engine and the store, so there is nothing here to
        leave out today. The filter is what makes that true of the **wire**
        rather than of one write path: a row written by a build that keeps
        reasoning -- the day one does, or an operator rolling back past it --
        would otherwise have it read as part of the answer by every client
        generated from this document. When reasoning is sent, it is sent
        deliberately and as its own kind (``docs/specs/conversations.md``).
        """
        return cls(
            id=message.id,
            parent_id=message.parent_id,
            role=message.role.value,
            channel=message.channel,
            created_at=utc(message.created_at),
            parts=[
                ContentPart.of(part)
                for part in message.parts
                if not isinstance(part, ReasoningPart)
            ],
            provenance=(
                None if message.provenance is None else ProvenanceView.of(message.provenance)
            ),
        )


class ConversationSummary(BaseModel):
    """A conversation as the panel lists it and as a write answers with it.

    No owner: it is the person asking, on every route there is
    (``docs/specs/privacy.md``). ``active_leaf_id`` is the position its author
    is at, which is what ``PUT /api/conversations/{id}/leaf`` moves.
    """

    id: uuid.UUID
    title: str
    agent: str
    created_at: datetime
    updated_at: datetime
    active_leaf_id: uuid.UUID | None

    @classmethod
    def of(cls, conversation: Conversation) -> ConversationSummary:
        return cls(
            id=conversation.id,
            title=conversation.title,
            agent=conversation.agent,
            created_at=utc(conversation.created_at),
            updated_at=utc(conversation.updated_at),
            active_leaf_id=conversation.active_leaf_id,
        )


class ConversationListResponse(BaseModel):
    """One page of the caller's conversations, and how to ask for the next.

    ``next_cursor`` is ``null`` on the last page. It is opaque: a position
    inside this person's own listing, written by the store and read by it, and
    nothing a client should take apart (``docs/specs/conversations.md``).
    """

    items: list[ConversationSummary]
    next_cursor: str | None


class ResumeView(BaseModel):
    """Where to attach to the run in flight, and what its next message follows.

    ``after`` is the position to carry on from and ``follows`` is the id the
    next message announced after it will hang under -- the two things a
    watcher of that stream is checked with, handed over together so that
    neither is guessed (``docs/specs/runs.md``).
    """

    after: int
    follows: uuid.UUID | None


class EndedBadlyView(BaseModel):
    """The last run of the conversation, when it failed, was cancelled or was interrupted.

    So that a reload after an answer went wrong says so, instead of showing a
    turn that simply stops (``docs/specs/runs.md``).

    ``state`` is the whole of the reason, and it is the only one the platform
    records as a **kind**: what else a run holds is ``error``, free text made
    out of whatever a provider or a traceback said, written for an operator.
    It stays on the record and in the log, like the detail of every other
    refusal (``robinauts.api.errors``).
    """

    run_id: uuid.UUID
    state: SentBadEnd
    ended_at: datetime

    @classmethod
    def of(cls, run: Run) -> EndedBadlyView:
        # `finished_at` is set in every ended state (`domain.Run`), and this
        # is built from an ended one alone.
        assert run.finished_at is not None
        return cls(run_id=run.id, state=run.state.value, ended_at=utc(run.finished_at))


class OpenedConversationResponse(BaseModel):
    """A conversation opened: one moment of it, with everything drawing it needs.

    ``messages`` is **every message of the tree**, oldest first with ties
    broken by id, so the branches beside the one being shown are there to
    switch to without a second request. Each carries its ``parent_id``, and
    ``leaf_id`` is the message the conversation opens on
    (``docs/specs/conversations.md``): the branch is the walk from that id up
    the parents, which the client does and the server does not send twice.

    ``run_id`` and ``resume`` are there when a run is in flight, and
    ``ended_badly`` instead when the last one ended badly. Never both: what
    matters about a run that is going is the run.
    """

    conversation: ConversationSummary
    messages: list[MessageView]
    leaf_id: uuid.UUID | None
    run_id: uuid.UUID | None
    resume: ResumeView | None
    ended_badly: EndedBadlyView | None

    @classmethod
    def of(cls, opened: OpenedConversation) -> OpenedConversationResponse:
        return cls(
            conversation=ConversationSummary.of(opened.conversation),
            messages=[MessageView.of(message) for message in opened.tree.messages],
            leaf_id=None if opened.leaf is None else opened.leaf.id,
            run_id=opened.run_id,
            resume=(
                None
                if opened.resume is None
                else ResumeView(after=opened.resume.after, follows=opened.resume.follows)
            ),
            ended_badly=(
                None if opened.ended_badly is None else EndedBadlyView.of(opened.ended_badly)
            ),
        )


class RunView(BaseModel):
    """A run as a client sees it: where it got to, and when.

    ``ended_at`` is what the record calls ``finished_at``: a run that failed,
    was cancelled or was interrupted did not finish, and every ended run has
    one. ``started_at`` is ``null`` until a process took the run up, and
    ``ended_at`` until it ended. What went wrong is not here, for the reason
    given on ``EndedBadlyView``.
    """

    id: uuid.UUID
    state: RunState
    started_at: datetime | None
    ended_at: datetime | None

    @classmethod
    def of(cls, run: Run) -> RunView:
        return cls(
            id=run.id,
            state=run.state,
            started_at=None if run.started_at is None else utc(run.started_at),
            ended_at=None if run.finished_at is None else utc(run.finished_at),
        )


class AgentSummary(BaseModel):
    """One agent, as the picker on an empty chat offers it.

    Three fields, and deliberately no more: **no system prompt** -- it is the
    operator's, it is not a message and it never leaves the process
    (``docs/specs/conversations.md``) -- and no vendor, endpoint or key. The
    model is not here either: which model an agent runs is the operator's
    choice and shows on the answers it produced (``ProvenanceView``), where it
    is a fact about what happened rather than something to pick by.
    """

    id: str
    title: str
    engine: Engine

    @classmethod
    def of(cls, definition: AgentDefinition) -> AgentSummary:
        return cls(id=definition.id, title=definition.title, engine=definition.engine)


class AgentListResponse(BaseModel):
    """Every agent this deployment is configured with, in configuration order."""

    items: list[AgentSummary]


class RenameRequest(BaseModel):
    """A new title for a conversation. A renamed title is never overwritten.

    The bound is the record's own (``domain.MAX_TITLE_CHARS``), said here so
    that it is **in the document**: a client that knows how long a title may
    be can say so in its own form, instead of finding out by being refused.
    What the length cannot say -- one line, printable, and something other
    than spaces -- is the application's, and is refused there
    (``application.Conversations.rename``).
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)


class SelectLeafRequest(BaseModel):
    """The message its author is now on; any message of the conversation.

    Not only the end of a branch: what is recorded is a position, and opening
    the conversation resolves it to the branch below it
    (``docs/specs/conversations.md``).
    """

    model_config = ConfigDict(extra="forbid")

    message_id: uuid.UUID


class NewChatRequest(BaseModel):
    """A turn that **begins** a conversation: the agent, and the first question.

    ``agent_id`` is required, and the route decides nothing about it: the
    application takes either the agent to begin a conversation with or the
    conversation a turn is in, never both and never neither
    (``application.Turns.begin``), so the request names the agent rather than
    having one chosen for it. The picker is drawn from ``GET /api/agents``, and
    a deployment with one agent sends that one
    (``docs/specs/agents.md``).

    Both bounds are the record's own -- ``domain.MAX_CONFIG_ID_CHARS`` for an
    agent's id, ``domain.MAX_MESSAGE_CHARS`` for a message (every part of one,
    full) -- so a client can hold itself to them, and neither field is a length
    somebody else chooses. What a length cannot say -- the shape of a
    configured id, and that a message has something in it once what no store
    could hold has been taken out of it -- is decided below, and what it says
    is the rule.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=MAX_CONFIG_ID_CHARS)
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class TurnRequest(BaseModel):
    """A turn in a conversation that exists: a new message, or one produced again.

    **Exactly one of the two forms** (``docs/specs/wire.md``): ``text``, with
    the ``parent_id`` it hangs under -- nothing for a conversation's first
    question, and the parent of the message being replaced for an edit -- or
    ``regenerate``, the assistant message whose turn is to be produced again,
    which appends no message at all because the question is already there.
    Both, or neither, is refused with one fixed sentence
    (``robinauts.api.stream_routes.ONE_FORM``); the check is the route's rather
    than a discriminated union's, so that no tag of the sender's reaches a
    refusal's ``location`` (``robinauts.api.errors``).

    No ``agent_id``: a conversation is begun with an agent and stays with it
    (``docs/specs/conversations.md``), and the application refuses an agent and
    a conversation named together.
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=MAX_MESSAGE_CHARS)
    parent_id: uuid.UUID | None = None
    regenerate: uuid.UUID | None = None
