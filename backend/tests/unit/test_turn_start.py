# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Beginning a turn: the three request shapes, and everything that refuses one.

``application.Turns.start`` and ``regenerate`` over the fakes
(``tests/turns.py``). What is tested here is the control flow and the rules it
applies -- which parent a message may hang under, whose conversation it is,
what a new chat is titled -- and never the store, which has a contract suite
of its own.

The shapes are the ones a turn request has (``docs/specs/wire.md``): a new
conversation with an agent, a new message in one that exists (a continuation
or an edit, told apart only by the parent it names), and a regeneration, which
appends no message at all.
"""

from __future__ import annotations

import uuid

import pytest

from aio import asyncio_test
from conversations import AGENT, OTHER_CONVERSATION, agent_definition
from fakes import CountingIdSource, FakeClock, MemoryConversationStore, ScriptedAgent, says
from robinauts.application import Turns
from robinauts.domain import (
    ACTIVE_RUN_STATES,
    ConversationNotFoundError,
    Engine,
    InvalidMessageTreeError,
    InvalidValueError,
    MessageNotFoundError,
    RunAlreadyActiveError,
    RunState,
    TextPart,
    UnknownAgentError,
)
from turns import AUTHOR, NOW, SOMEBODY_ELSE, begun, stored_messages, wired

ANSWER = "Someone who plays fair."


class Watched(MemoryConversationStore):
    """The store, with a note of every call that writes. Nothing else differs."""

    def __init__(self) -> None:
        super().__init__()
        self.wrote: list[str] = []

    async def start_run(self, **kwargs: object) -> None:
        self.wrote.append("start_run")
        await super().start_run(**kwargs)  # type: ignore[arg-type]

    async def add_conversation(self, conversation: object) -> None:
        self.wrote.append("add_conversation")
        await super().add_conversation(conversation)  # type: ignore[arg-type]

    async def append_message(self, *args: object, **kwargs: object) -> None:
        self.wrote.append("append_message")
        await super().append_message(*args, **kwargs)  # type: ignore[arg-type]

    async def touch_conversation(self, *args: object, **kwargs: object) -> object:
        self.wrote.append("touch_conversation")
        return await super().touch_conversation(*args, **kwargs)  # type: ignore[arg-type]


# --- a new conversation ------------------------------------------------------


@asyncio_test
async def test_a_new_chat_stores_the_conversation_the_question_and_the_run_at_once() -> None:
    wiring = wired(store=Watched())

    begun_turn = await wiring.turns.start(AUTHOR, agent_id=AGENT, text="What is a robinaut?")

    # One call, because a turn begins all at once or not at all: a
    # conversation with no question in it, or a question with no run, is
    # something no process may be able to leave behind.
    assert wiring.store.wrote == ["start_run"]  # type: ignore[attr-defined]
    stored = await wiring.store.conversation_by_id(begun_turn.conversation.id)
    assert stored is not None
    assert stored.owner_id == AUTHOR.id
    assert stored.agent == AGENT
    assert stored.active_leaf_id == begun_turn.message.id
    assert [message.text for message in await stored_messages(wiring.store, stored.id)] == [
        "What is a robinaut?"
    ]
    assert begun_turn.run.state is RunState.RUNNING
    assert begun_turn.run.message_id == begun_turn.message.id
    assert begun_turn.run.engine is wiring.definition.engine
    assert begun_turn.run.model == wiring.definition.model
    # Nothing has taken it up yet; the start is stamped when it ends.
    assert begun_turn.run.started_at is None
    assert begun_turn.run.created_at == NOW


@asyncio_test
async def test_a_new_chat_is_titled_from_the_beginning_of_its_first_message() -> None:
    wiring = wired()

    begun_turn = await wiring.turns.start(
        AUTHOR,
        agent_id=AGENT,
        text="\n \nWhat   is a robinaut?\nAnd what is not one?",
    )

    assert begun_turn.conversation.title == "What is a robinaut?"


@asyncio_test
async def test_a_new_chat_cannot_hang_under_a_message() -> None:
    wiring = wired()

    with pytest.raises(MessageNotFoundError):
        await wiring.turns.start(AUTHOR, agent_id=AGENT, text="Under what?", parent_id=uuid.uuid4())


@asyncio_test
async def test_an_agent_this_deployment_does_not_have_is_refused() -> None:
    wiring = wired()

    with pytest.raises(UnknownAgentError):
        await wiring.turns.start(AUTHOR, agent_id="nobody", text="Hello?")
    # And a name that is not an id at all is refused as a value, before
    # anything is looked up.
    with pytest.raises(InvalidValueError):
        await wiring.turns.start(AUTHOR, agent_id="NOT AN ID", text="Hello?")


@asyncio_test
async def test_a_turn_names_an_agent_or_a_conversation_and_not_both() -> None:
    wiring = wired()

    with pytest.raises(InvalidValueError):
        await wiring.turns.start(AUTHOR, text="Where does this go?")
    with pytest.raises(InvalidValueError):
        await wiring.turns.start(AUTHOR, agent_id=AGENT, conversation_id=uuid.uuid4(), text="Both?")


# --- the question itself -----------------------------------------------------


@asyncio_test
async def test_a_message_with_nothing_in_it_is_refused() -> None:
    wiring = wired()

    for nothing in ("", "   \n\t ", "\x00"):
        with pytest.raises(InvalidValueError):
            await wiring.turns.start(AUTHOR, agent_id=AGENT, text=nothing)
    with pytest.raises(InvalidValueError):
        await wiring.turns.start(AUTHOR, agent_id=AGENT, text=None)  # type: ignore[arg-type]


@asyncio_test
async def test_what_a_browser_sent_is_repaired_before_it_is_stored() -> None:
    wiring = wired()

    begun_turn = await wiring.turns.start(AUTHOR, agent_id=AGENT, text="a\x00b\ud800c")

    # The NUL is dropped and the lone surrogate replaced: what is stored is
    # storable, and the message is not lost over a character.
    assert begun_turn.message.text == "ab�c"


@asyncio_test
async def test_a_message_longer_than_one_part_is_carried_in_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The bound made small, so that a test about splitting is not a test about
    # a megabyte of text.
    monkeypatch.setattr("robinauts.domain.conversation.MAX_PART_CHARS", 4)
    wiring = wired()

    begun_turn = await wiring.turns.start(AUTHOR, agent_id=AGENT, text="abcdefghij")

    assert begun_turn.message.parts == (TextPart("abcd"), TextPart("efgh"), TextPart("ij"))
    assert begun_turn.message.text == "abcdefghij"


# --- a message in a conversation that exists ---------------------------------


@asyncio_test
async def test_a_message_continues_the_branch_it_names() -> None:
    wiring = wired(*says(ANSWER))
    first = await begun(wiring)
    await wiring.turns.execute(first)
    answered = (await stored_messages(wiring.store, first.conversation_id))[-1]

    begun_turn = await wiring.turns.start(
        AUTHOR, conversation_id=first.conversation_id, text="And why?", parent_id=answered.id
    )

    assert begun_turn.message is not None
    assert begun_turn.message.parent_id == answered.id
    assert begun_turn.run.message_id == begun_turn.message.id
    assert begun_turn.run.agent == AGENT


@asyncio_test
async def test_an_edit_is_a_sibling_under_the_parent_it_names() -> None:
    wiring = wired(*says(ANSWER))
    first = await begun(wiring)
    await wiring.turns.execute(first)
    answered = (await stored_messages(wiring.store, first.conversation_id))[-1]
    followed = await wiring.turns.start(
        AUTHOR, conversation_id=first.conversation_id, text="And why?", parent_id=answered.id
    )
    await wiring.turns.execute(followed.run)

    edited = await wiring.turns.start(
        AUTHOR,
        conversation_id=first.conversation_id,
        text="No: why not?",
        parent_id=answered.id,
    )

    # Beside the message it replaces, under the same parent: nothing is
    # overwritten and the earlier branch is still there.
    assert edited.message.parent_id == followed.message.parent_id
    stored = await stored_messages(wiring.store, first.conversation_id)
    assert followed.message.id in {message.id for message in stored}


@asyncio_test
async def test_editing_the_first_question_gives_the_conversation_another_root() -> None:
    wiring = wired(*says(ANSWER))
    first = await begun(wiring)
    await wiring.turns.execute(first)

    edited = await wiring.turns.start(
        AUTHOR, conversation_id=first.conversation_id, text="Ask it another way.", parent_id=None
    )

    assert edited.message.parent_id is None
    assert edited.run.message_id == edited.message.id


@asyncio_test
async def test_a_parent_from_another_conversation_is_simply_not_there() -> None:
    wiring = wired()
    first = await begun(wiring)
    elsewhere = await wiring.turns.start(AUTHOR, agent_id=AGENT, text="Another chat.")

    with pytest.raises(MessageNotFoundError):
        await wiring.turns.start(
            AUTHOR,
            conversation_id=first.conversation_id,
            text="Across?",
            parent_id=elsewhere.message.id,
        )


@asyncio_test
async def test_a_question_does_not_hang_under_a_question() -> None:
    wiring = wired()
    first = await begun(wiring)

    with pytest.raises(InvalidMessageTreeError):
        await wiring.turns.start(
            AUTHOR,
            conversation_id=first.conversation_id,
            text="Two in a row?",
            parent_id=first.message_id,
        )


# --- regenerating ------------------------------------------------------------


@asyncio_test
async def test_regenerating_answers_the_question_that_began_the_turn() -> None:
    wiring = wired(*says(ANSWER))
    first = await begun(wiring)
    await wiring.turns.execute(first)
    answered = (await stored_messages(wiring.store, first.conversation_id))[-1]

    again = await wiring.turns.regenerate(
        AUTHOR, conversation_id=first.conversation_id, message_id=answered.id
    )

    assert again.message is None
    assert again.run.message_id == first.message_id
    assert again.run.id != first.id
    # Nothing was appended: the question is already there.
    assert len(await stored_messages(wiring.store, first.conversation_id)) == 2


@asyncio_test
async def test_only_an_answer_is_regenerated() -> None:
    wiring = wired()
    first = await begun(wiring)

    with pytest.raises(InvalidMessageTreeError):
        await wiring.turns.regenerate(
            AUTHOR, conversation_id=first.conversation_id, message_id=first.message_id
        )


@asyncio_test
async def test_regenerating_a_message_that_is_not_there_is_a_message_not_found() -> None:
    wiring = wired()
    first = await begun(wiring)

    with pytest.raises(MessageNotFoundError):
        await wiring.turns.regenerate(
            AUTHOR, conversation_id=first.conversation_id, message_id=uuid.uuid4()
        )


# --- ownership ---------------------------------------------------------------


@asyncio_test
async def test_somebody_elses_conversation_answers_exactly_like_one_that_is_not_there() -> None:
    wiring = wired()
    first = await begun(wiring)

    with pytest.raises(ConversationNotFoundError) as theirs:
        await wiring.turns.start(
            SOMEBODY_ELSE, conversation_id=first.conversation_id, text="Let me in."
        )
    with pytest.raises(ConversationNotFoundError) as missing:
        await wiring.turns.start(
            SOMEBODY_ELSE, conversation_id=OTHER_CONVERSATION, text="Let me in."
        )

    assert type(theirs.value) is type(missing.value)
    # And regenerating is the same door.
    with pytest.raises(ConversationNotFoundError):
        await wiring.turns.regenerate(
            SOMEBODY_ELSE, conversation_id=first.conversation_id, message_id=first.message_id
        )


# --- one active run ----------------------------------------------------------


@asyncio_test
async def test_a_second_turn_while_one_is_going_is_refused() -> None:
    wiring = wired(*says(ANSWER))
    first = await begun(wiring)

    with pytest.raises(RunAlreadyActiveError):
        await wiring.turns.start(AUTHOR, conversation_id=first.conversation_id, text="And another?")
    # Nothing of the refused turn was written.
    assert len(await stored_messages(wiring.store, first.conversation_id)) == 1
    assert len(await wiring.store.runs_of(first.conversation_id)) == 1


@asyncio_test
async def test_a_regeneration_while_one_is_going_is_refused_too() -> None:
    wiring = wired(*says(ANSWER))
    first = await begun(wiring)
    await wiring.turns.execute(first)
    answered = (await stored_messages(wiring.store, first.conversation_id))[-1]
    await wiring.turns.start(AUTHOR, conversation_id=first.conversation_id, text="And why?")

    with pytest.raises(RunAlreadyActiveError):
        await wiring.turns.regenerate(
            AUTHOR, conversation_id=first.conversation_id, message_id=answered.id
        )


@asyncio_test
async def test_once_the_run_has_ended_the_next_turn_begins() -> None:
    wiring = wired(*says(ANSWER))
    first = await begun(wiring)
    await wiring.turns.execute(first)

    followed = await wiring.turns.start(
        AUTHOR, conversation_id=first.conversation_id, text="And why?"
    )

    assert followed.run.is_active
    assert await wiring.store.active_run_of(first.conversation_id) == followed.run
    assert not [run for run in await wiring.store.runs_in(ACTIVE_RUN_STATES) if run.id == first.id]


# --- wiring ------------------------------------------------------------------


def test_an_agent_whose_engine_is_not_wired_is_a_deployment_that_does_not_start() -> None:
    # Caught where the mistake is -- at wiring -- and not at the first turn of
    # the conversation somebody started with that agent.
    definition = agent_definition(engine=Engine.LANGGRAPH)

    with pytest.raises(InvalidValueError):
        Turns(
            store=MemoryConversationStore(),
            clock=FakeClock(),
            ids=CountingIdSource(),
            agents={definition.id: definition},
            engines={Engine.PYDANTIC_AI: ScriptedAgent()},
        )


def test_an_agent_filed_under_a_name_that_is_not_its_own_is_refused() -> None:
    definition = agent_definition()

    with pytest.raises(InvalidValueError):
        Turns(
            store=MemoryConversationStore(),
            clock=FakeClock(),
            ids=CountingIdSource(),
            agents={"somebody-else": definition},
            engines={definition.engine: ScriptedAgent()},
        )


def test_a_turn_service_refuses_limits_that_are_not_limits() -> None:
    for changes in (
        {"history_chars": 0},
        {"history_chars": True},
        {"turn_seconds": 0},
        {"turn_seconds": -1.0},
        {"turn_seconds": "soon"},
    ):
        with pytest.raises(InvalidValueError):
            wired(**changes)  # type: ignore[arg-type]
