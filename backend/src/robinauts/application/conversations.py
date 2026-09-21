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
    MAX_TITLE_CHARS,
    Conversation,
    ConversationNotFoundError,
    InvalidValueError,
    Message,
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
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE:
            raise InvalidValueError(
                f"a page holds between 1 and {MAX_PAGE} conversations, not {limit!r}"
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

        The snapshot is decoded here and the point is found by
        ``core.resume_point``, rather than asked of the store: the rule is one
        sentence in ``core`` and a store that answered it would be a second
        place it lived. A run in flight has the events of one turn, so this is
        a short read; if it ever stops being one, the query it would become is
        written out on ``core.resume_point``.
        """
        checked_uuid(conversation_id, "a conversation's id")
        checked_uuid(user.id, "a user's id")
        snapshot = await self._store.conversation_snapshot(conversation_id)
        conversation = self._owner_of(user, conversation_id, snapshot.conversation)
        tree = tree_of_stored(
            [message_from_stored(document) for document in snapshot.messages],
            conversation_id=conversation.id,
        )
        leaf = tree.default_leaf(conversation)
        active = snapshot.active_run
        if active is None:
            return OpenedConversation(conversation=conversation, tree=tree, leaf=leaf)
        events = [run_event_from_stored(document) for document in snapshot.events]
        return OpenedConversation(
            conversation=conversation,
            tree=tree,
            leaf=leaf,
            run_id=active.id,
            resume=resume_point(events, answering=active.message_id),
        )

    async def rename(self, user: User, conversation_id: uuid.UUID, title: str) -> Conversation:
        """Give it a new title. A renamed title is never overwritten afterwards.

        What comes back is what the **store wrote**, not the record read a
        moment earlier with a new title put on it: between the two a run may
        have completed a message and moved the conversation on, and an
        interface drawn from the older record would put back a position that
        has already changed.
        """
        kept = checked_line(title, "a conversation's title", MAX_TITLE_CHARS)
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

        A conversation already gone when the delete reached it is not an
        error: what was asked for is what is true.
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
        return self._owner_of(
            user, conversation_id, await self._store.conversation_by_id(conversation_id)
        )

    @staticmethod
    def _owner_of(
        user: User, conversation_id: uuid.UUID, found: Conversation | None
    ) -> Conversation:
        """``found`` if it is this person's, however it was read.

        The rule itself, so that the call that reads a conversation on its own
        and the one that reads a whole snapshot answer with the same error.
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
