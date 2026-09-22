# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Running one turn: the seam between the platform and an agent framework.

**One method, because a turn is one thing** (``docs/specs/agents.md``): given
the agent the operator defined and the history to answer, stream what the
model said. Everything else about a turn -- which ids the messages get, what
they hang under, what is written down, what a watcher is told -- belongs to
the application, which is why none of it is in this signature.

**What crosses.** In: an ``AgentDefinition`` (the system prompt, the model and
the engine, read afresh every turn, because editing an agent takes effect at
the next turn of its existing conversations) and a **history**: the path from a
root to the user message being answered, already trimmed to what the model
will take (``robinauts.core.trim_history``). Trimming is above the port on
purpose -- both engines must behave the same, and a policy inside an adapter
would be two policies. Out: ``EngineEvent``s, which carry no ids, no times and
no provenance, because an engine has none.

**Both engines are stateless per turn** (ADR 0002). Nothing is remembered
between calls: the conversation record is the whole of the state, and the
history handed in is where a turn starts from, whichever engine ran the turn
before it.

**How it ends.**

- normally: the last event is an ``AnswerCompleted``. A turn produces at least
  one answer; one that produces none is a failed run
  (``docs/specs/runs.md``), and the application is what records that.
- by **raising**: any exception ends the turn. The application records the run
  ``failed`` with a description of what was raised and leaves the answer that
  was in flight uncompleted. An engine yields nothing after an error.
- by **cancellation**: the application cancels the task the iteration runs in,
  and closes the stream. An engine must not swallow ``CancelledError``; it
  lets it through, and what it holds is released by the ``finally`` of the
  generator, which closing runs.

**Waiting on tool calls is not here.** With tools, a turn ends either
"finished" or "waiting on these tool calls" (``docs/specs/runs.md``), and the
run is then suspended until the results are appended to the conversation and
it is resumed from the history. This version has no tools, so a turn always
ends finished; when they arrive, what says so is another engine event at the
end of this stream, and the application's lifecycle is what grows a
``waiting`` branch. Nothing here needs to change shape for it.

The contract suite both engines are held to is
``backend/tests/contracts/agents.py``, and the order it holds them to is
``robinauts.core.check_engine_events``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence

from robinauts.domain import AgentDefinition, EngineEvent, Message, ProviderKind


class Agent(ABC):
    """One engine, able to run one turn of one agent."""

    kinds: frozenset[ProviderKind] = frozenset()
    """The model provider kinds this engine has a client for.

    **Not every model exists under every engine** (``docs/specs/agents.md``),
    and not every provider's client passes the dependency policy at a given
    version (``DEPENDENCIES.md``). So an engine says what it can reach, and
    the composition root asks it rather than knowing: the configuration is
    then refused at start-up, naming the provider, instead of a person
    waiting for an answer from a client that was never built.

    Declared here and not in an adapter so that asking costs the root no
    second name from a framework's sub-package -- the one import and the one
    construction are what deleting an adapter must break, and nothing else
    (``docs/layout.md``, the discard test).

    Empty by default, which is a test double's honest answer: a scripted
    engine reaches no provider at all, and a deployment wired with one
    configures no model provider either.
    """

    @abstractmethod
    def run_turn(
        self, agent: AgentDefinition, history: Sequence[Message]
    ) -> AsyncGenerator[EngineEvent, None]:
        """Answer ``history`` as ``agent``, streaming the events of the turn.

        ``history`` is a path of the conversation ending in the **user
        message being answered**, already trimmed; it is never empty and never
        ends anywhere else. The system prompt is ``agent``'s and is not one of
        the messages (``docs/specs/conversations.md``).

        Not a coroutine: it hands back the stream, which is then iterated.

        **An async generator, and that is part of the port.** What it hands
        back must have ``aclose()``, because closing the stream is how the
        application releases what the engine holds -- when the turn ends,
        when it fails, and above all when the task running it is cancelled,
        which is how a run is cancelled. An implementation is therefore an
        ``async def`` with ``yield``s in it, whose ``finally`` releases the
        HTTP response, the client or the file; the contract suite asks the
        object for ``aclose`` and asks the engine what it still holds
        afterwards.

        The close is **bounded** by the application: an engine that takes too
        long to let go is abandoned rather than allowed to hold up the run
        that has already ended.
        """
        raise NotImplementedError
