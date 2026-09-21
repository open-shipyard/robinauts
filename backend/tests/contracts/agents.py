# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What every ``Agent`` must do: the order of a turn, failure, cancellation.

The suite both engines are held to (``docs/specs/agents.md``), written now,
against the fake, so that the LangGraph and the Pydantic AI adapters are held
to one description rather than to whatever each of them happened to do. The
order itself is not restated here: it is ``core.check_engine_events``, which
is the same statement the application is written against.

**Subclass it and override ``new_agent``.** What the suite hands you is a
``Script`` -- what the model is to say, and how the turn is to end -- and what
it expects back is an ``Agent`` whose model does that and whose provider is
never reached. For the real engines that means the framework's own test model
stubbed with the script; for the fake it is the script turned into steps. The
suite never says how, and asks nothing about the framework.

``definition`` and ``history`` are overridable too: an engine that must be
handed its own model id or a longer history says so there. What is **not**
overridable is any of the promises below.

The five situations, which are the ones the application distinguishes:

- an answer that is **streamed**: announced, its text in deltas, completed
  with exactly what was streamed;
- an answer that is **not**: no delta at all, completed with the whole of it.
  Not every provider streams, and an engine is never required to;
- **several answers in one turn**, one after another, never interleaved;
- a **failure**: the engine raises, in the middle of an answer, and what it
  yielded stands as far as it got (``cut_short=True``);
- a **cancellation**: the task is cancelled, the ``CancelledError`` comes
  through, and it comes through **promptly**. An engine that swallowed one
  would leave a run nothing can stop.

And, after every one of them, that the engine **holds nothing** (``held``).
Letting a cancellation through is half the promise; the other half is the
response, the client or the file that the turn opened, which the ``finally``
of the generator releases when the stream is closed.

There is no test here about ids, positions, storing or publishing: an engine
has none of those, which is the whole point of the port.
"""

from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import dataclass, field
from enum import StrEnum

import pytest

from aio import asyncio_test
from conversations import agent_definition, question
from robinauts.core import check_engine_events
from robinauts.domain import (
    AgentDefinition,
    AnswerCompleted,
    AnswerStarted,
    AnswerTextDelta,
    EngineEvent,
    Message,
    TextPart,
)
from robinauts.ports import Agent

RELEASE_SECONDS = 5.0
"""How long a cancelled turn has to let the cancellation through.

Generous: it is not a measurement, it is the difference between "promptly"
and "never", and a test that hung would say the same thing hours later.
"""


class Ending(StrEnum):
    """How the turn the script describes comes to an end."""

    COMPLETE = "complete"
    """The last answer is completed and the turn returns."""
    FAIL = "fail"
    """The last answer is left open and the engine raises."""
    HANG = "hang"
    """The last answer is left open and nothing more ever happens."""


@dataclass(frozen=True, slots=True)
class Say:
    """One answer the model is to produce."""

    text: str
    streamed: bool = True
    """Whether it arrives in deltas. An engine that streams must complete with
    exactly what it streamed; one that does not may complete with anything."""


@dataclass(frozen=True, slots=True)
class Script:
    """What the model says in one turn, and how the turn ends."""

    answers: tuple[Say, ...] = field(default_factory=tuple)
    ending: Ending = Ending.COMPLETE


class AgentContract:
    """Subclass this and override ``new_agent``."""

    def new_agent(self, script: Script) -> Agent:
        """An engine whose model says that, and which reaches no provider."""
        raise NotImplementedError("an AgentContract subclass overrides `new_agent`")

    def held(self, agent: Agent) -> int:
        """How much that engine still holds open: a response, a client, a file.

        Zero when it has let go of everything. **Required**, because "an engine
        releases what it holds" is the promise a cancelled run depends on and
        it cannot be checked from outside: only the implementation knows what
        it opened. An engine over a framework answers with the number of
        streams, responses or clients it has not closed.
        """
        raise NotImplementedError("an AgentContract subclass overrides `held`")

    def definition(self) -> AgentDefinition:
        """The agent it is asked to run. Override for an engine that needs its own."""
        return agent_definition()

    def history(self) -> tuple[Message, ...]:
        """The history it is given: a path ending in the question to answer."""
        return (question("What is a robinaut?"),)

    async def turn(self, script: Script) -> list[EngineEvent]:
        """Every event of one turn, run to its end."""
        agent = self.new_agent(script)
        seen: list[EngineEvent] = []
        events = agent.run_turn(self.definition(), self.history())
        # The application closes the stream to release what the engine holds,
        # so the stream must be closeable: that is part of the port.
        assert hasattr(events, "aclose")
        async with aclosing(events):
            async for event in events:
                seen.append(event)
        assert self.held(agent) == 0
        return seen

    # --- what a turn produces ---

    @asyncio_test
    async def test_a_streamed_answer_is_announced_streamed_and_completed(self) -> None:
        seen = await self.turn(Script(answers=(Say("Someone who plays fair."),)))

        check_engine_events(seen)
        assert isinstance(seen[0], AnswerStarted)
        assert any(isinstance(event, AnswerTextDelta) for event in seen)
        assert _completed(seen) == ["Someone who plays fair."]

    @asyncio_test
    async def test_an_answer_that_was_not_streamed_still_completes(self) -> None:
        # Not every provider streams, and a turn through a path that does not
        # is a turn like any other.
        seen = await self.turn(Script(answers=(Say("All of it at once.", streamed=False),)))

        check_engine_events(seen)
        assert not [event for event in seen if isinstance(event, AnswerTextDelta)]
        assert _completed(seen) == ["All of it at once."]

    @asyncio_test
    async def test_a_turn_may_produce_several_answers_one_after_another(self) -> None:
        seen = await self.turn(Script(answers=(Say("First."), Say("Second."))))

        # One at a time and never interleaved: `check_engine_events` is what
        # says so, and it is the same rule the application publishes by.
        check_engine_events(seen)
        assert _completed(seen) == ["First.", "Second."]

    @asyncio_test
    async def test_what_was_streamed_is_what_the_answer_completes_with(self) -> None:
        seen = await self.turn(Script(answers=(Say("A whole answer, streamed."),)))

        streamed = "".join(event.text for event in seen if isinstance(event, AnswerTextDelta))
        assert streamed == _completed(seen)[0]

    # --- how a turn ends badly ---

    @asyncio_test
    async def test_a_failure_is_reported_by_raising_and_leaves_the_answer_open(self) -> None:
        agent = self.new_agent(Script(answers=(Say("As far as it g"),), ending=Ending.FAIL))
        seen: list[EngineEvent] = []

        with pytest.raises(Exception) as failure:  # noqa: B017 - an engine raises what it likes
            async with aclosing(agent.run_turn(self.definition(), self.history())) as events:
                async for event in events:
                    seen.append(event)

        assert not isinstance(failure.value, asyncio.CancelledError)
        # What it yielded stands as far as it got: an answer announced and
        # never completed is what a turn cut short looks like.
        check_engine_events(seen, cut_short=True)
        assert not _completed(seen)
        assert self.held(agent) == 0

    @asyncio_test
    async def test_a_cancelled_turn_lets_the_cancellation_through_promptly(self) -> None:
        agent = self.new_agent(Script(answers=(Say("Half of an ans"),), ending=Ending.HANG))
        seen: list[EngineEvent] = []
        arrived = asyncio.Event()

        async def watch() -> None:
            async with aclosing(agent.run_turn(self.definition(), self.history())) as events:
                async for event in events:
                    seen.append(event)
                    arrived.set()

        turn = asyncio.create_task(watch())
        # Cancelled while it is really running, not before it began: no sleep
        # decides that, the first event does.
        await arrived.wait()
        turn.cancel()

        async with asyncio.timeout(RELEASE_SECONDS):
            with pytest.raises(asyncio.CancelledError):
                await turn
        check_engine_events(seen, cut_short=True)
        # Let go of, not merely stopped: the promise a cancelled run depends
        # on is that the response, the client and the file go with it.
        assert self.held(agent) == 0


def _completed(events: list[EngineEvent]) -> list[str]:
    """The text of each answer the turn completed, in order."""
    return [
        "".join(part.text for part in event.parts if isinstance(part, TextPart))
        for event in events
        if isinstance(event, AnswerCompleted)
    ]
