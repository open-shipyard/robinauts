# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Managing conversations: listing them, opening one, renaming, deleting.

What the panel and the chat ask for, and nothing that writes a message: the
turn -- creating a conversation, appending a question, starting a run -- is
the run lifecycle, next door.

**Ownership is one rule, applied in one place.** Every call here begins by
finding the conversation *and* checking who is asking, and a conversation that
belongs to somebody else is answered **exactly** like one that does not exist:
``ConversationNotFoundError``, whose body ``api`` fixes word for word
(``docs/specs/conversations.md``). It is that error rather than
``NotTheOwnerError`` deliberately -- the two are answered identically today,
and one path cannot drift from the other. Which of the two it really was is in
the error's own detail, which reaches the log and never the browser. The local
development user (``docs/specs/sign-in.md``) is a user like any other here:
their conversations are theirs, and nothing else's is.

**What must be indivisible is one call.** Deleting takes the conversation, its
messages, its runs and their events, and is refused while a run is going --
all of it decided inside the store, in one transaction, because a check up
here and a delete down there would leave a window for a run to begin in
(``robinauts.ports.ConversationStore``).

**Reading rows is not reading a request.** The messages come back as
documents, and the run's events too; they are decoded through ``core``'s
``*_stored`` readers, so a row this build cannot read is a fault of ours
(``StoredDataError``) and not a 404 for whoever opened the conversation. An id
the *request* named and that is not there stays a ``NotFoundError``.

The rules are ``core``'s throughout -- the tree, where a conversation opens,
where a watcher of a run in flight attaches -- and everything outside the
process is a port, handed in and never constructed (``docs/layout.md``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from robinauts.core import (
    ConversationTree,
    ResumePoint,
    message_from_stored,
    resume_point,
    run_event_from_stored,
    tree_of_stored,
)
from robinauts.domain import (
    FAULTED_RUN_STATES,
    MAX_TITLE_CHARS,
    Conversation,
    ConversationNotFoundError,
    InvalidValueError,
    Message,
    Run,
    User,
    checked_line,
    checked_uuid,
)
from robinauts.ports import MAX_PAGE, Clock, ConversationPage, ConversationStore

DEFAULT_PAGE = 30
"""How many conversations a caller that did not say gets: a panel's worth."""


@dataclass(frozen=True, slots=True)
class OpenedConversation:
    """A conversation as the interface needs it to draw one.

    Everything that reading it decided, together: a caller that had to ask
    three times would be asking about three moments.
    """

    conversation: Conversation
    tree: ConversationTree
    """Its messages, read once and checked once; every further question is a
    method on it (``core.ConversationTree``)."""
    leaf: Message | None
    """The message it opens on -- ``core.default_leaf`` -- or ``None`` while
    the conversation is empty."""
    run_id: uuid.UUID | None = None
    """The run in flight, if there is one; the stream is attached to by id."""
    resume: ResumePoint | None = None
    """Where a watcher of that run attaches, and what the next message there
    will hang under (``core.resume_point``). ``None`` with no run in flight."""
    ended_badly: Run | None = None
    """The most recent run, when nothing is in flight and that run failed, was
    cancelled or was interrupted.

    So that somebody who reloads a conversation after an answer went wrong is
    told what happened, instead of finding a turn that simply stops
    (``docs/specs/runs.md``). ``None`` when the last run finished, when there
    has been none, and while one is in flight -- what matters then is the run
    itself."""


class Conversations:
    """Everything the author of a conversation may do to it but write in it."""

    def __init__(self, *, store: ConversationStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    async def list_for(
        self, user: User, *, limit: int = DEFAULT_PAGE, cursor: str | None = None
    ) -> ConversationPage:
        """That person's conversations, most recently updated first.

        ``cursor`` is what the last page handed back, and is the store's to
        read: it came from a browser, so one that does not parse is refused as
        a value. One that parses and was never issued is only a position --
        this listing holds the caller's own conversations whatever it says.

        A ``limit`` outside the bound names the field and the rule and **not
        the number it was given**: this refusal is answered to whoever asked
        (``robinauts.api.errors``), and a body that repeated what a request
        carried would be reflecting it back.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE:
            raise InvalidValueError(
                f"limit is a whole number between 1 and {MAX_PAGE},"
                " which is what a page of conversations holds"
            )
        return await self._store.conversations_of(user.id, limit=limit, cursor=cursor)

    async def open(self, user: User, conversation_id: uuid.UUID) -> OpenedConversation:
        """A conversation, its messages, the branch it opens on and its run in flight.

        The messages that are **stored** -- every one that is complete -- and,
        if a run is going, where to attach to watch the rest of it arrive. The
        two together are what makes reopening a conversation in the middle of
        an answer show the answer arriving rather than a gap
        (``docs/specs/runs.md``).

        **One read, of one moment.** The messages, the run and its events come
        back from a single ``conversation_snapshot``, because a message
        completed between two reads would fall between them: read the messages
        first and it is in neither the tree nor the replay, which begins after
        it; read the events first and it is in both. Either way the person
        opening the conversation is shown the wrong thing, and the port is
        what makes it impossible.

        **Ownership is settled before that read, not after it.** The
        conversation's own row is looked up first, and a conversation that is
        not this person's stops there: a snapshot reads every message and
        every event of the run and decodes each document, so checking
        afterwards would make somebody else's conversation cost more than a
        conversation that is not there -- the difference is measurable, and
        measuring it is one of the ways an id is probed for existence. It also
        means no signed-in caller can make this deployment read a thousand
        messages belonging to somebody else. The check is made again on the
        snapshot, which costs nothing and is what answers a conversation
        deleted between the two reads: the same 404 as one that was never
        there.

        **What went wrong is told too.** When no run is in flight, the most
        recent one is looked at, and a run that failed, was cancelled or was
        interrupted comes back on ``ended_badly``: somebody who reloads a
        conversation after an answer went wrong is told so rather than finding
        a turn that simply stops.

        The snapshot is decoded here and the point is found by
        ``core.resume_point``, rather than asked of the store: the rule is one
        sentence in ``core`` and a store that answered it would be a second
        place it lived. A run in flight has the events of one turn, so this is
        a short read; if it ever stops being one, the query it would become is
        written out on ``core.resume_point``.
        """
        await self._owned(user, conversation_id)
        snapshot = await self._store.conversation_snapshot(conversation_id)
        conversation = owner_of(user, conversation_id, snapshot.conversation)
        tree = tree_of_stored(
            [message_from_stored(document) for document in snapshot.messages],
            conversation_id=conversation.id,
        )
        leaf = tree.default_leaf(conversation)
        active = snapshot.active_run
        if active is None:
            return OpenedConversation(
                conversation=conversation,
                tree=tree,
                leaf=leaf,
                ended_badly=await self._ended_badly(conversation.id),
            )
        events = [run_event_from_stored(document) for document in snapshot.events]
        return OpenedConversation(
            conversation=conversation,
            tree=tree,
            leaf=leaf,
            run_id=active.id,
            resume=resume_point(events, answering=active.message_id),
        )

    async def _ended_badly(self, conversation_id: uuid.UUID) -> Run | None:
        """The most recent run of that conversation, if it ended badly.

        A **second** read, and deliberately outside the snapshot: it is asked
        only when nothing is in flight, it changes nothing about the messages
        or the tree, and what it says is advisory -- a run that began between
        the two reads is a run the caller will be told about when it opens
        again. Keeping it in the snapshot would mean a port that returned a
        conversation's whole run history for every open.

        **One row**, because one is what this is about: a conversation
        answered a thousand times is not read a thousand runs at a time to
        look at the last of them.
        """
        runs = await self._store.runs_of(conversation_id, limit=1)
        if not runs or runs[0].state not in FAULTED_RUN_STATES:
            return None
        return runs[0]

    async def rename(self, user: User, conversation_id: uuid.UUID, title: str) -> Conversation:
        """Give it a new title. A renamed title is never overwritten afterwards.

        A title with nothing in it is refused: a conversation whose title is
        three spaces has a name nobody can read and one that no list can be
        sorted by, and the record cannot tell it from a title, since spaces are
        printable and on one line. It is refused the way an agent's title is
        (``domain.AgentDefinition``), with the rule and not the value -- this
        message is answered to whoever asked.

        What comes back is what the **store wrote**, not the record read a
        moment earlier with a new title put on it: between the two a run may
        have completed a message and moved the conversation on, and an
        interface drawn from the older record would put back a position that
        has already changed.
        """
        kept = checked_line(title, "a conversation's title", MAX_TITLE_CHARS)
        if not kept.strip():
            raise InvalidValueError("a conversation's title has something in it")
        conversation = await self._owned(user, conversation_id)
        written = await self._store.rename_conversation(
            conversation.id, kept, now=self._clock.now()
        )
        if written is None:
            raise _gone(conversation.id)
        return written

    async def select_branch(
        self, user: User, conversation_id: uuid.UUID, leaf_id: uuid.UUID
    ) -> Conversation:
        """Move the author to another branch: the conversation opens there next.

        Any message of the conversation will do, not only a leaf: what the
        author is on is a position, and ``core.default_leaf`` resolves it to
        the end of the branch below it when the conversation is opened. One
        that is no message of this conversation is a ``MessageNotFoundError``
        from the store, which is where that rule is kept.

        It does not date the conversation. Moving between branches writes
        nothing, so nothing climbs to the top of the panel
        (``docs/specs/conversations.md``). What comes back is what the store
        wrote, for the reason given on ``rename``.
        """
        checked_uuid(leaf_id, "a conversation's active leaf")
        conversation = await self._owned(user, conversation_id)
        written = await self._store.set_active_leaf(conversation.id, leaf_id)
        if written is None:
            raise _gone(conversation.id)
        return written

    async def delete(self, user: User, conversation_id: uuid.UUID) -> None:
        """Delete it for good, with its messages, its runs and their events.

        There is no trash in this version (``docs/working-notes/poc-scope.md``).

        **A conversation with a run going is not deleted**: the store refuses
        with ``RunAlreadyActiveError``, deciding it in the same transaction
        that would have deleted, and its author cancels the run first.
        Deleting under a run would leave a task writing messages into a
        conversation that is no longer there, and the alternative -- cancelling
        it on the author's behalf -- would hide a running answer behind a
        button that says "delete".

        **A conversation that is not there is not deleted, it is missed.** Like
        every other call here, this one begins by finding the conversation and
        checking who is asking, so deleting one that is not there -- or that is
        somebody else's -- raises ``ConversationNotFoundError`` and deleting
        twice raises it the second time. This is not idempotent, and a route
        over it is not either. What is tolerated is the **race**: a
        conversation that went between the check here and the store's own
        delete is not an error, because what was asked for is then true.
        """
        conversation = await self._owned(user, conversation_id)
        await self._store.delete_conversation(conversation.id, now=self._clock.now())

    async def _owned(self, user: User, conversation_id: uuid.UUID) -> Conversation:
        """That conversation, if it is this person's; ``ConversationNotFoundError`` if not.

        The one door. A conversation of somebody else's and a conversation
        that never existed leave here as the same error, and the detail --
        which says which it was, for the log -- is not part of what ``api``
        answers with.
        """
        checked_uuid(conversation_id, "a conversation's id")
        checked_uuid(user.id, "a user's id")
        return owner_of(
            user, conversation_id, await self._store.conversation_by_id(conversation_id)
        )


def owner_of(user: User, conversation_id: uuid.UUID, found: Conversation | None) -> Conversation:
    """``found`` if it is this person's; ``ConversationNotFoundError`` if not.

    **The ownership rule itself**, in one function, so that every way of
    reaching a conversation answers the same: read on its own or inside a
    snapshot, reached directly or through a run of it (``application.turns``).
    A conversation of somebody else's and one that never existed leave here as
    the same error, and the detail -- which says which it was, for the log --
    is not part of what ``api`` answers with.
    """
    if found is None:
        raise _gone(conversation_id)
    if found.owner_id != user.id:
        raise ConversationNotFoundError(
            f"conversation {conversation_id} belongs to {found.owner_id}, not to {user.id}"
        )
    return found


def _gone(conversation_id: uuid.UUID) -> ConversationNotFoundError:
    """What a conversation that is not there answers, wherever it is missed."""
    return ConversationNotFoundError(f"there is no conversation {conversation_id}")
